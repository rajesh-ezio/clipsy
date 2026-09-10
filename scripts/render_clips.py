#!/usr/bin/env python3
"""Render finished MP4 clips straight from a content plan, with ffmpeg.

Usage:
    python3 $S/render_clips.py output/content-plans/<stem>.json              # every clip
    python3 $S/render_clips.py <plan> --clip clip-06                          # one clip
    python3 $S/render_clips.py <plan> --no-captions                           # clean cut, no text
    python3 $S/render_clips.py <plan> --jobs 3 --out ~/Desktop/clips

The content plan is already a complete edit decision list: each clip is its keep_segments
in source seconds, and the gaps between them are the cuts. This renders exactly that - no
app, no permissions, no manual export. Files land in output/clips/ named with the same
numbered clip name as the SRT and the tracker row ("01 What is an ICP.mp4").

Every render is checked afterwards: the output duration must match the plan's duration_sec,
or the clip is reported as a failure rather than silently shipped.

Needs ffmpeg/ffprobe (~/.local/bin, via `uv tool install static-ffmpeg`). Otherwise stdlib.
"""
import argparse
import json
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import SKILL_HOME, WORKDIR, settings_path  # noqa: E402
from naming import numbered_names  # noqa: E402
from make_captions import cues_for_clip, srt_ts, _ends_well  # noqa: E402

CLIPS_DIR = WORKDIR / "output" / "clips"
FONTS_DIR = SKILL_HOME / "assets" / "fonts"
# Seek to just before the first kept word rather than decoding the source from zero.
# A clip at minute 18 would otherwise decode 18 minutes of video it throws away.
PREROLL = 2.0
# Hard cuts on continuous speech click. A 12ms fade either side of every seam is
# inaudible as a fade but removes the click.
SEAM_FADE = 0.012
DURATION_TOLERANCE = 0.15


def tool(name):
    found = shutil.which(name) or str(Path.home() / ".local/bin" / name)
    if not Path(found).exists():
        raise SystemExit(f"{name} not found. Install: uv tool install static-ffmpeg, then "
                         f"symlink its binaries into ~/.local/bin (see references/gotchas.md).")
    return found


def ass_colour(hex_rgb, opacity=1.0):
    """#RRGGBB + opacity -> ASS &HAABBGGRR. ASS alpha is inverted: 00 is opaque."""
    h = hex_rgb.lstrip("#")
    alpha = round((1 - opacity) * 255)
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def caption_style(brand):
    fg = brand.get("caption_text_color", "#FFFFFF")
    bg = brand.get("caption_background_color") or "#000000"
    opacity = brand.get("caption_box_opacity", 0.8)
    # BorderStyle=3 draws an opaque box behind each line. libass paints that box with the
    # outline colour, so both outline and back colour are set - that is the white-on-black
    # caption box. Sizes are relative to libass's 288-line SRT canvas.
    return ",".join([
        f"FontName={brand.get('caption_font_name', 'Inter')}",
        "Bold=1",
        f"FontSize={brand.get('caption_render_size', 15)}",
        f"PrimaryColour={ass_colour(fg)}",
        f"OutlineColour={ass_colour(bg, opacity)}",
        f"BackColour={ass_colour(bg, opacity)}",
        "BorderStyle=3",
        f"Outline={brand.get('caption_box_padding', 5)}",
        "Shadow=0",
        "Alignment=2",
        f"MarginV={brand.get('caption_margin_v', 22)}",
    ])


def filter_graph(segments, t0, subtitles, polish):
    """One trim per keep segment, faded at the seams, concatenated, then finished.

    Finishing = captions, a short fade in from black and out at the end, and loudness
    normalisation. Zoom audio typically lands around -25 LUFS; social feeds play near -14,
    so an unnormalised clip sounds noticeably weak next to everything around it."""
    parts, pads = [], []
    total = sum(e - s for s, e in segments)
    for i, (s, e) in enumerate(segments):
        a, b, d = s - t0, e - t0, e - s
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={SEAM_FADE},"
                     f"afade=t=out:st={max(d - SEAM_FADE, 0):.3f}:d={SEAM_FADE}[a{i}]")
        pads.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(pads)}concat=n={len(segments)}:v=1:a=1[vc][ac]")

    fi, fo = polish.get("fade_in", 0), polish.get("fade_out", 0)
    video = [subtitles] if subtitles else []
    if fi:
        video.append(f"fade=t=in:st=0:d={fi}")
    if fo:
        video.append(f"fade=t=out:st={max(total - fo, 0):.3f}:d={fo}")
    audio = []
    if polish.get("loudnorm"):
        audio += [polish["loudnorm"], "aresample=48000"]
    if fi:
        audio.append(f"afade=t=in:d={min(fi, 0.15)}")
    if fo:
        audio.append(f"afade=t=out:st={max(total - fo, 0):.3f}:d={fo}")

    vlabel, alabel = "[vc]", "[ac]"
    if video:
        parts.append(f"[vc]{','.join(video)}[vout]")
        vlabel = "[vout]"
    if audio:
        parts.append(f"[ac]{','.join(audio)}[aout]")
        alabel = "[aout]"
    return ";".join(parts), vlabel, alabel


def measure_loudness(opts, src, t0, segments, target):
    """First pass of two: measure the finished edit's audio, return an exact loudnorm spec.

    Single-pass loudnorm undershoots on short clips (one landed at -16.2 LUFS against a -14
    target). Measuring first costs about a second - audio only, no video decode - and moves
    the result far closer. It can still land short of target when the recording's
    peaks rule out a straight linear gain - loudnorm then falls back to dynamic mode.
    On the ICP clip: -24.8 LUFS in, -15.5 out, against -14."""
    parts, pads = [], []
    for i, (s, e) in enumerate(segments):
        parts.append(f"[0:a]atrim=start={s - t0:.3f}:end={e - t0:.3f},asetpts=PTS-STARTPTS[m{i}]")
        pads.append(f"[m{i}]")
    parts.append(f"{''.join(pads)}concat=n={len(segments)}:v=0:a=1,"
                 f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json[out]")
    r = subprocess.run([opts["ffmpeg"], "-hide_banner", "-ss", f"{t0:.3f}", "-i", str(src),
                        "-filter_complex", ";".join(parts), "-map", "[out]", "-f", "null", "-"],
                       capture_output=True, text=True)
    err = r.stderr
    m = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    return (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:"
            f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
            f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")


def caption_qc(cues):
    """The checks done by hand while tuning the first captioned clip, now run on every render."""
    gaps = [cues[i + 1][0] - cues[i][1] for i in range(len(cues) - 1)]
    return {
        "cues": len(cues),
        "blinks": sum(0.05 < g < 0.8 for g in gaps),
        "orphans": sum(len(t.split()) <= 2 for _, _, t in cues),
        "dangling": sum(not _ends_well(t.split()[-1]) for _, _, t in cues),
        "longest": max((len(t) for _, _, t in cues), default=0),
    }


def output_loudness(opts, path):
    """Integrated loudness and true peak of the finished file - what the viewer hears."""
    r = subprocess.run([opts["ffmpeg"], "-hide_banner", "-i", str(path), "-vn",
                        "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    return float(m["input_i"]), float(m["input_tp"])


def render_one(job):
    clip, name, src, out_dir, opts = job
    segments = [(k["start"], k["end"]) for k in clip["keep_segments"]]
    t0 = max(0.0, segments[0][0] - PREROLL)
    work = Path(tempfile.mkdtemp(prefix="render_"))
    try:
        subtitles, cues = None, []
        if opts["captions"]:
            cues = cues_for_clip(clip, opts["words"], opts["caption_cfg"])
            (work / "c.srt").write_text("\n".join(
                f"{i}\n{srt_ts(a)} --> {srt_ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1)))
            # Run ffmpeg inside the temp dir and name the SRT relatively: filtergraph
            # escaping of paths with spaces ("Claude Code") is more fragile than it is worth.
            subtitles = (f"subtitles=c.srt:fontsdir={FONTS_DIR}:"
                         f"force_style='{opts['style']}'")
        polish = dict(opts["polish"])
        if polish.get("loudness_lufs") is not None:
            polish["loudnorm"] = measure_loudness(opts, src, t0, segments,
                                                  polish["loudness_lufs"])
        graph, vlabel, alabel = filter_graph(segments, t0, subtitles, polish)

        out = out_dir / f"{name}.mp4"
        part = out_dir / f".{name}.part.mp4"
        cmd = [opts["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y",
               "-ss", f"{t0:.3f}", "-i", str(src),
               "-filter_complex", graph, "-map", vlabel, "-map", alabel,
               "-c:v", "libx264", "-preset", opts["preset"], "-crf", str(opts["crf"]),
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
               "-movflags", "+faststart", str(part)]
        started = time.time()
        r = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
        took = time.time() - started
        if r.returncode:
            if part.exists():
                part.unlink()
            return name, False, {"error": f"ffmpeg failed: {r.stderr.strip()[-600:]}"}, took
        part.replace(out)

        got = float(subprocess.check_output(
            [opts["ffprobe"], "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(out)], text=True).strip())
        want = clip["duration_sec"]
        qc = {"got": got, "want": want, "size": out.stat().st_size / 1e6,
              "duration_ok": abs(got - want) <= DURATION_TOLERANCE}
        qc["lufs"], qc["peak"] = output_loudness(opts, out)
        if cues:
            qc.update(caption_qc(cues))

        # One frame per clip for the visual check, taken mid-way through the caption nearest
        # the middle so it shows the caption, the slide and the camera box together.
        at = got / 2
        if cues:
            a, b, _ = min(cues, key=lambda c: abs((c[0] + c[1]) / 2 - got / 2))
            at = (a + b) / 2
        qc_dir = out_dir / "qc"
        qc_dir.mkdir(exist_ok=True)
        frame = qc_dir / f"{name}.png"
        subprocess.run([opts["ffmpeg"], "-hide_banner", "-v", "error", "-y", "-ss", f"{at:.2f}",
                        "-i", str(out), "-frames:v", "1", str(frame)], check=False)
        qc["frame"] = frame
        return name, qc["duration_ok"], qc, took
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--clip", action="append", help="clip video_id to render; repeatable")
    ap.add_argument("--captions", action="store_true", help="force captions on")
    ap.add_argument("--no-captions", action="store_true",
                    help="render without captions (they are on by default: render.captions)")
    ap.add_argument("--jobs", type=int, help="parallel renders (default from settings)")
    ap.add_argument("--out", help="output directory (default output/clips)")
    args = ap.parse_args()

    settings = json.loads(settings_path().read_text())
    rcfg = settings.get("render", {})
    plan = json.loads(Path(args.plan).read_text())
    src = Path(plan["source_video"])
    src = src if src.is_absolute() else WORKDIR / src
    if not src.exists():
        raise SystemExit(f"source video missing: {src}")

    names = numbered_names(plan)
    clips = sorted(plan["clips"], key=lambda c: c["keep_segments"][0]["start"])
    if args.clip:
        clips = [c for c in clips if c["video_id"] in args.clip]
        if not clips:
            raise SystemExit(f"no clip matching {args.clip}")

    captions = not args.no_captions and (args.captions or rcfg.get("captions", True))
    words = None
    if captions:
        tp = Path(plan["transcript_source"])
        words = json.loads((tp if tp.is_absolute() else WORKDIR / tp).read_text())["words"]

    out_dir = Path(args.out).expanduser() if args.out else CLIPS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "ffmpeg": tool("ffmpeg"), "ffprobe": tool("ffprobe"),
        "crf": rcfg.get("crf", 20), "preset": rcfg.get("preset", "medium"),
        "captions": captions, "words": words,
        "caption_cfg": settings.get("captions",
                                    {"max_words": 7, "max_seconds": 3.0, "max_chars": 42}),
        "style": caption_style(settings.get("branding", {})),
        "polish": {"loudness_lufs": rcfg.get("loudness_lufs", -14),
                   "fade_in": rcfg.get("fade_in", 0.3), "fade_out": rcfg.get("fade_out", 0.5)},
    }
    jobs = args.jobs or rcfg.get("jobs", 3)
    print(f"Rendering {len(clips)} clip(s) -> {out_dir}  "
          f"(jobs={jobs}, crf={opts['crf']}, captions={'on' if captions else 'off'})\n")

    started = time.time()
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(render_one,
                                [(c, names[c["video_id"]], src, out_dir, opts) for c in clips]))
    failed = [r for r in results if not r[1]]
    target = opts["polish"]["loudness_lufs"]
    flagged = 0
    for name, ok, qc, took in results:
        if "error" in qc:
            print(f"  FAIL  {name}\n        {qc['error']}")
            continue
        flags = []
        if not qc["duration_ok"]:
            flags.append(f"duration {qc['got'] - qc['want']:+.2f}s off plan")
        if target is not None and qc["lufs"] < target - 3:
            flags.append(f"quiet ({qc['lufs']:.1f} LUFS)")
        if qc["peak"] > -0.5:
            flags.append(f"peaks near clipping ({qc['peak']:.1f} dBTP)")
        for k in ("blinks", "orphans", "dangling"):
            if qc.get(k):
                flags.append(f"{qc[k]} caption {k}")
        flagged += bool(flags)
        status = "FAIL" if not ok else ("CHECK" if flags else "OK")
        cap = f"{qc['cues']:>3} cues" if "cues" in qc else "no captions"
        print(f"  {status:<5} {name:<36} {qc['got']:6.2f}s ({qc['got'] - qc['want']:+.2f})  "
              f"{qc['size']:4.1f} MB  {qc['lufs']:5.1f} LUFS  {cap}  [{took:4.1f}s]")
        if flags:
            print(f"        -> {'; '.join(flags)}")
    print(f"\n{len(results) - len(failed)}/{len(results)} rendered in "
          f"{time.time() - started:.1f}s, {flagged} flagged for a look")
    print(f"QC frames, one per clip - look at each before handing over: {out_dir / 'qc'}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
