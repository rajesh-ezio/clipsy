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

Every render is checked afterwards: the output duration must match the length its cuts
should produce (the plan's duration_sec plus up to a frame per cut, see rendered_length),
or the clip is reported as a failure rather than silently shipped.

Needs ffmpeg/ffprobe (~/.local/bin, via `uv tool install static-ffmpeg`). Otherwise stdlib.
"""
import argparse
import json
import math
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
from naming import body_range, numbered_names  # noqa: E402
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


def source_seeks(segments):
    """One source input per run of segments, so a clip can open on a line borrowed from
    far away - even from later in the recording (Week 4 clip 07 opens on a line from 2:00
    before its body at 0:43). A segment that jumps backwards, or more than 10 minutes
    forward, starts a new input seeked just before it; decoding the gap would cost minutes.
    Returns [(input_index, seek_seconds)] per segment and the list of seeks per input."""
    seeks, per_seg, prev_end = [], [], None
    for s, e in segments:
        if prev_end is None or s < prev_end - 0.01 or s - prev_end > 600:
            seeks.append(max(0.0, s - PREROLL))
        per_seg.append((len(seeks) - 1, seeks[-1]))
        prev_end = e
    return per_seg, seeks


def rendered_length(segments, t0, fps):
    """The runtime the renderer will actually produce, which is not the plan's exact sum.

    Each video trim lands on whole frames, and concat pads every segment to its longer
    stream so sync resets at each cut. Every cut can therefore add up to a frame: a 26-cut
    clip planned at 156.76s renders at 156.88s. Checking against the plan's sum flagged
    that as a failure; checking against this still catches a dropped or mis-trimmed
    segment. It also times the closing fade, so the last frames don't sit on black.
    """
    total = 0.0
    for (s, e), (_, t0) in zip(segments, source_seeks(segments)[0]):
        off = math.ceil(t0 * fps - 1e-9) / fps - t0      # first output frame after the seek
        a, b = round(s - t0, 3), round(e - t0, 3)
        frames = math.ceil((b - off) * fps - 1e-9) - math.ceil((a - off) * fps - 1e-9)
        total += max(frames / fps, b - a)
    return total


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


def fix_captions(cues, fixes):
    """Apply a clip's `caption_fixes` - [["heard", "meant"], ...] - to the on-screen captions.

    Transcription mishears ("PLDR" for PLG, "two access quadrant" for two-axis); the fix
    list corrects what the viewer reads while the plan's transcript stays verbatim. A
    phrase is matched on word boundaries, case-sensitive, within one caption line - so a
    fix that straddles two lines won't apply. Check that every fix landed before rendering
    (build the cues with cues_for_clip and look for the heard phrase)."""
    import re
    out = []
    for a, b, t in cues:
        for heard, meant in fixes:
            t = re.sub(r"(?<!\w)" + re.escape(heard) + r"(?!\w)", meant, t)
        out.append((a, b, t))
    return out


CALLOUT_SLIDE = 0.4     # seconds to slide in, and again to slide out


def clip_time(segments, t):
    """Source seconds -> seconds into the finished clip. A time inside a cut maps to the
    start of the next keep."""
    acc, starts = 0.0, []
    for s, e in segments:
        if s <= t <= e:
            return acc + t - s
        starts.append((s, acc))
        acc += e - s
    later = [(s, a) for s, a in starts if s > t]
    return min(later)[1] if later else acc


# Inter Bold advance widths in ems, measured by rendering each character through libass
# (the renderer the boxes are drawn with). Counting characters instead under-sized boxes
# for wide-letter text: "Loyalty and ecommerce SaaS for" spilled white text off the box.
INTER_BOLD_EM = {
    " ": .187, "!": .271, '"': .448, "#": .534, "$": .539, "%": .833, "&": .552, "'": .273,
    "(": .307, ")": .307, "*": .454, "+": .556, ",": .271, "-": .382, ".": .27, "/": .319,
    "0": .555, "1": .351, "2": .515, "3": .531, "4": .555, "5": .512, "6": .532, "7": .477,
    "8": .535, "9": .532, ":": .27, ";": .279, "<": .555, "=": .554, ">": .555, "?": .457,
    "@": .836, "A": .614, "B": .542, "C": .609, "D": .593, "E": .499, "F": .48, "G": .617,
    "H": .612, "I": .225, "J": .48, "K": .59, "L": .465, "M": .764, "N": .624, "O": .633,
    "P": .531, "Q": .637, "R": .539, "S": .539, "T": .547, "U": .6, "V": .615, "W": .858,
    "X": .606, "Y": .602, "Z": .546, "[": .307, "\\": .639, "]": .307, "^": .398, "_": .394,
    "`": .293, "a": .476, "b": .516, "c": .481, "d": .515, "e": .489, "f": .327, "g": .519,
    "h": .511, "i": .217, "j": .221, "k": .477, "l": .217, "m": .749, "n": .511, "o": .504,
    "p": .516, "q": .515, "r": .332, "s": .462, "t": .3, "u": .511, "v": .494, "w": .702,
    "x": .477, "y": .494, "z": .468, "{": .383, "|": .298, "}": .383, "~": .556}


def text_width(s, fs):
    """Rendered width of `s` in Inter Bold at ASS font size `fs`, with 3% headroom."""
    return sum(INTER_BOLD_EM.get(ch, .6) for ch in s) * fs * 1.03


def _wrap_to(text, max_w, fs):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and text_width(trial, fs) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def _wrap(text, max_chars):
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > max_chars:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + ([cur] if cur else [])


def callout_box(co, w, h):
    """Where a callout box sits and how big it is, in video pixels.

    `side` ("right" default, or "left") and `y` (the box centre as a fraction of the
    height, default 0.42) place it; place_callouts.py picks both from the slide so the
    box lands on empty space instead of a table or chart."""
    k = h / 1080
    pad, label_fs, body_fs = 26 * k, 24 * k, 34 * k
    max_text_w = co.get("max_width", 520) * k     # narrower boxes wrap onto more lines
    text = co["text"]
    # fewest lines that fit, then balanced so the last line is not a lone word
    n = max(1, math.ceil(text_width(text, body_fs) / max_text_w))
    target = text_width(text, body_fs) / n * 1.08
    lines = _wrap_to(text, target, body_fs)
    label = co.get("label", "").upper()
    box_w = 2 * pad + max(max(text_width(x, body_fs) for x in lines),
                          text_width(label, label_fs) + len(label) * 2 * k)   # \fsp tracking
    box_h = pad * 0.85 + label_fs * 1.6 + len(lines) * body_fs + pad * 1.1
    if "x" in co:                       # left edge as a fraction of the width (place_callouts)
        x = co["x"] * w
    else:
        x = w - 40 * k - box_w if co.get("side", "right") == "right" else 40 * k
    y = h * co.get("y", 0.42) - box_h / 2
    return {"k": k, "pad": pad, "label_fs": label_fs, "body_fs": body_fs, "lines": lines,
            "w": box_w, "h": box_h, "x": x, "y": y}


def callout_ass(clip, segments, w, h, brand):
    """A pop-up box that slides in from the right, holds, and slides back out.

    Plan field, per clip: "callouts": [{"at": <source seconds>, "hold": 4.5,
    "label": "Acme Commerce", "text": "B2B SaaS that lets retailers ..."}]. `at` is
    usually the moment the presenter says the name. The box sits middle-right: clear of the
    captions at the bottom and the Zoom camera tile at the top right."""
    ts = lambda t: f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
    events = []
    for co in clip.get("callouts", []):
        g = callout_box(co, w, h)
        k, pad, label_fs, body_fs, lines = g["k"], g["pad"], g["label_fs"], g["body_fs"], g["lines"]
        box_w, box_h, x_on, y = g["w"], g["h"], g["x"], g["y"]
        # slides in from its own side: off the right edge, or off the left edge
        # boxes against an edge slide all the way in from it; a box placed in the middle of
        # the slide (on white space between content) fades in and out where it sits - any
        # movement would carry it across the slide content next to it
        right = co.get("side", "right") == "right"
        edge = (w - (x_on + box_w)) if right else x_on
        if edge <= 60 * k:
            x_off, fade_in = (w + 10 * k if right else -box_w - 10 * k), ""
        else:
            x_off, fade_in = x_on, "\\fad(300,0)"      # stays put: fade in and out only
        r = 16 * k
        W, H = box_w, box_h
        shape = (f"m {r:.0f} 0 l {W - r:.0f} 0 b {W:.0f} 0 {W:.0f} 0 {W:.0f} {r:.0f} "
                 f"l {W:.0f} {H - r:.0f} b {W:.0f} {H:.0f} {W:.0f} {H:.0f} {W - r:.0f} {H:.0f} "
                 f"l {r:.0f} {H:.0f} b 0 {H:.0f} 0 {H:.0f} 0 {H - r:.0f} l 0 {r:.0f} b 0 0 0 0 {r:.0f} 0")
        box = (f"{{\\an7\\bord0\\shad0\\1c{ass_colour('#141414')}\\1a&H22&\\p1}}{shape}")
        text = (f"{{\\an7\\bord0\\shad0\\fn{brand.get('caption_font_name', 'Inter')}"
                f"\\b1\\fs{label_fs:.0f}\\fsp{2 * k:.1f}\\1c{ass_colour('#B79CFF')}}}"
                f"{co.get('label', '').upper()}\\N"
                f"{{\\fsp0\\fs{body_fs:.0f}\\1c{ass_colour('#FFFFFF')}}}" + "\\N".join(lines))
        t = clip_time(segments, co["at"])
        hold = co.get("hold", 4.5)
        s = CALLOUT_SLIDE
        ms = int(s * 1000)
        # slide in, hold, slide out - the box on layer 0, its text on layer 1 above it
        phases = [(t, t + s, x_off, x_on, fade_in),
                  (t + s, t + s + hold, x_on, x_on, ""),
                  (t + s + hold, t + 2 * s + hold, x_on, x_off, "\\fad(0,150)" if x_off != x_on else "\\fad(0,350)")]
        for a, b, x0, x1, extra in phases:
            for layer, body, dx, dy in ((0, box, 0, 0), (1, text, pad, pad * 0.85)):
                p0, p1, yy = x0 + dx, x1 + dx, y + dy
                m = (f"\\pos({p1:.0f},{yy:.0f})" if x0 == x1 else
                     f"\\move({p0:.0f},{yy:.0f},{p1:.0f},{yy:.0f},0,{ms})")
                events.append(f"Dialogue: {layer},{ts(a)},{ts(b)},Callout,,0,0,0,,"
                              f"{{{m}{extra}}}{body}")
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}",
        "ScaledBorderAndShadow: yes", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Callout,{brand.get('caption_font_name', 'Inter')},30,&H00FFFFFF,&H00FFFFFF,"
        "&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1", "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events, ""])


def cover_ass(clip, w, h, brand, segments=None):
    """Paint over part of the slide for the whole clip, optionally with new text on top.

    For a clip whose slide doesn't match what he's saying (a cold-calling Q&A answer played
    over a bare "Cracking the LinkedIn game" title). Plan field, per clip:
    "slide_cover": [{"box": [x0, y0, x1, y1], "fill": "#FFFFFF", "text": "Does cold calling
    work?", "text_at": [x, y], "align": 7, "color": "#663497", "size": 0.0583}] - box and text_at as
    fractions of the frame, size as a fraction of its height. Match fill to the slide's
    background and color/size to its title so it reads as the slide's own heading - by
    measuring the rendered frame: a sampled #FDFDFD rendered 2 levels darker than the slide
    and showed as a faint box. Drawn under the captions and pop-ups."""
    ts = lambda t: f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
    events = []
    for c in clip.get("slide_cover", []):
        if c.get("image"):
            continue    # a held still frame: drawn by the overlay chain, not painted here
        # optional "from"/"to" in SOURCE seconds limit the cover to part of the clip - e.g.
        # only the opening line borrowed from another slide, whose picture doesn't fit
        a = clip_time(segments, c["from"]) if segments and "from" in c else 0.0
        b = clip_time(segments, c["to"]) if segments and "to" in c else 35999.0
        span = f"{ts(a)},{ts(b)}"
        if c.get("box"):                # an entry can be text only (no cover box)
            x0, y0, x1, y1 = (c["box"][0] * w, c["box"][1] * h, c["box"][2] * w, c["box"][3] * h)
            shape = f"m 0 0 l {x1 - x0:.0f} 0 l {x1 - x0:.0f} {y1 - y0:.0f} l 0 {y1 - y0:.0f}"
            events.append(f"Dialogue: 0,{span},Cover,,0,0,0,,{{\\an7\\pos({x0:.0f},{y0:.0f})"
                          f"\\bord0\\shad0\\1c{ass_colour(c.get('fill', '#FFFFFF'))}\\p1}}{shape}")
        if c.get("text"):
            # `align` is the ASS numpad anchor for text_at: 7 = top-left (default), 5 = centre,
            # so a question can sit centred on an empty slide like a title card
            tx, ty = c.get("text_at", (c.get("box") or [0, 0])[:2])
            events.append(f"Dialogue: 1,{span},Cover,,0,0,0,,{{\\an{c.get('align', 7)}\\pos({tx * w:.0f},{ty * h:.0f})"
                          f"\\bord0\\shad0\\fn{c.get('font', 'Inter')}\\fs{c.get('size', 0.037) * h:.0f}"
                          f"\\1c{ass_colour(c.get('color', '#000000'))}}}{c['text']}")
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}",
        "ScaledBorderAndShadow: yes", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Cover,Inter,30,&H00000000,&H00000000,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1", "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events, ""])


def filter_graph(segments, t0, subtitles, polish, total, stills=()):
    """One trim per keep segment, faded at the seams, concatenated, then finished.

    Finishing = captions, a short fade in from black and out at the end, and loudness
    normalisation. Zoom audio typically lands around -25 LUFS; social feeds play near -14,
    so an unnormalised clip sounds noticeably weak next to everything around it."""
    parts, pads = [], []
    for i, ((s, e), (src, t0)) in enumerate(zip(segments, source_seeks(segments)[0])):
        a, b, d = s - t0, e - t0, e - s
        parts.append(f"[{src}:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[{src}:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
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
        # loudnorm emits its first frames with crowded timestamps (~120 near-zero-length
        # AAC packets in the first 0.1s). Local players ignore that; Google Drive's
        # transcoder honours it and warps the opening audio. Renumber the samples.
        # loudnorm's linear mode can still overshoot its -1.5 dBTP target (one Week 1 clip
        # peaked at 0.0 dBTP), so a sample-peak limiter sits after it. The ceiling has to
        # allow for AAC overshoot, which is much larger than it looks: a dense, heavily
        # limited passage measured -2.50 dBFS as PCM and +0.14 dBFS once encoded - 2.6 dB
        # of overshoot, and raising the bitrate to 192k or 256k changed nothing (Week 3
        # clip 20). -4 dBFS keeps the encoded true peak under -0.5 dBTP on that material
        # and never touches a clip whose own peaks sit lower. latency=true keeps sync.
        audio += [polish["loudnorm"], "aresample=48000",
                  "alimiter=limit=0.63:attack=5:release=50:level=false:latency=true",
                  "asetpts=N/SR/TB"]
    if fi:
        audio.append(f"afade=t=in:d={min(fi, 0.15)}")
    if fo:
        audio.append(f"afade=t=out:st={max(total - fo, 0):.3f}:d={fo}")

    # A still frame held over part of the clip: the screen went somewhere irrelevant (a
    # different slide, an editor window) while the point being made is still the one on the
    # frozen slide. Cropped to a box so the live camera tile keeps moving, and drawn before
    # the caption/pop-up chain so those still sit on top.
    vlabel, alabel = "[vc]", "[ac]"
    for n, (idx, a, b, box, pop) in enumerate(stills, 1):
        crop = f"crop={box[2]}:{box[3]}:{box[0]}:{box[1]}," if box else ""
        pos = f"{box[0]}:{box[1]}" if box else "0:0"
        if pop:
            # an image pop-up: scaled to its width, slides in from the side like a callout,
            # holds, and slides back out
            xon, xoff, y, s = pop["x"], pop["x_off"], pop["y"], CALLOUT_SLIDE
            crop = f"format=rgba,scale={pop['w']}:-1,"
            pos = (f"x='if(lt(t,{a + s:.3f}),{xoff}+({xon}-({xoff}))*(t-{a:.3f})/{s},"
                   f"if(gt(t,{b - s:.3f}),{xon}+(({xoff})-{xon})*(t-{b - s:.3f})/{s},{xon}))':y={y}")
        parts.append(f"[{idx}:v]{crop}setsar=1[im{n}]")
        parts.append(f"{vlabel}[im{n}]overlay={pos}:eof_action=pass:"
                     f"enable='between(t,{a:.3f},{b:.3f})'[vi{n}]")
        vlabel = f"[vi{n}]"
    if video:
        parts.append(f"{vlabel}{','.join(video)}[vout]")
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
    per_seg, seeks = source_seeks(segments)
    for i, ((s, e), (src_i, t0)) in enumerate(zip(segments, per_seg)):
        parts.append(f"[{src_i}:a]atrim=start={s - t0:.3f}:end={e - t0:.3f},asetpts=PTS-STARTPTS[m{i}]")
        pads.append(f"[m{i}]")
    parts.append(f"{''.join(pads)}concat=n={len(segments)}:v=0:a=1,"
                 f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json[out]")
    inputs = [x for t in seeks for x in ("-ss", f"{t:.3f}", "-i", str(src))]
    r = subprocess.run([opts["ffmpeg"], "-hide_banner", *inputs,
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
            cues = fix_captions(cues_for_clip(clip, opts["words"], opts["caption_cfg"]),
                                clip.get("caption_fixes", []))
            (work / "c.srt").write_text("\n".join(
                f"{i}\n{srt_ts(a)} --> {srt_ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1)))
            # Run ffmpeg inside the temp dir and name the SRT relatively: filtergraph
            # escaping of paths with spaces ("Claude Code") is more fragile than it is worth.
            subtitles = (f"subtitles=c.srt:fontsdir={FONTS_DIR}:"
                         f"force_style='{opts['style']}'")
        if clip.get("callouts"):
            (work / "co.ass").write_text(callout_ass(clip, segments, opts["width"],
                                                     opts["height"], opts["brand"]))
            subtitles = ",".join(filter(None, [subtitles, f"ass=co.ass:fontsdir={FONTS_DIR}"]))
        if clip.get("slide_cover"):
            # first in the chain, so captions and pop-ups draw on top of it
            (work / "cover.ass").write_text(cover_ass(clip, opts["width"], opts["height"],
                                                      opts["brand"], segments))
            subtitles = ",".join(filter(None, [f"ass=cover.ass:fontsdir={FONTS_DIR}", subtitles]))
        polish = dict(opts["polish"])
        if polish.get("loudness_lufs") is not None:
            polish["loudnorm"] = measure_loudness(opts, src, t0, segments,
                                                  polish["loudness_lufs"])
        expected = rendered_length(segments, t0, opts["fps"])
        stills, still_inputs = [], []
        for c in clip.get("slide_cover", []):
            if not c.get("image"):
                continue
            a = clip_time(segments, c["from"]) if "from" in c else 0.0
            b = clip_time(segments, c["to"]) if "to" in c else expected
            box, pop = None, None
            if c.get("popup"):
                # {"image", "from": source sec, "hold": sec, "popup": {"x", "y", "w", "side"}}
                # x/y/w as frame fractions; x is the resting left edge
                p = c["popup"]
                b = a + c.get("hold", 6.0) + 2 * CALLOUT_SLIDE
                pw = int(p["w"] * opts["width"])
                pop = {"w": pw, "x": int(p["x"] * opts["width"]), "y": int(p["y"] * opts["height"]),
                       "x_off": opts["width"] + 10 if p.get("side", "right") == "right" else -pw - 10}
            elif c.get("box"):
                x0, y0, x1, y1 = c["box"]
                box = (int(x0 * opts["width"]), int(y0 * opts["height"]),
                       int((x1 - x0) * opts["width"]), int((y1 - y0) * opts["height"]))
            img = Path(c["image"])
            if not img.is_absolute():
                img = WORKDIR / img
            stills.append((len(source_seeks(segments)[1]) + len(stills), a, b, box, pop))
            still_inputs += ["-loop", "1", "-framerate", f"{opts['fps']:.3f}", "-i", str(img)]
        graph, vlabel, alabel = filter_graph(segments, t0, subtitles, polish, expected, stills)

        out = out_dir / f"{name}.mp4"
        part = out_dir / f".{name}.part.mp4"
        cmd = [opts["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y",
               *[x for t in source_seeks(segments)[1] for x in ("-ss", f"{t:.3f}", "-i", str(src))],
               *still_inputs,
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
        want = expected
        qc = {"got": got, "want": want, "plan": clip["duration_sec"],
              "size": out.stat().st_size / 1e6,
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
    clips = sorted(plan["clips"], key=lambda c: body_range(c["keep_segments"], c.get("opener_spans", ()))[0])
    if args.clip:
        clips = [c for c in clips if c["video_id"] in args.clip]
        if not clips:
            raise SystemExit(f"no clip matching {args.clip}")

    captions = not args.no_captions and (args.captions or rcfg.get("captions", True))
    words = None
    if captions:
        tp = Path(plan["transcript_source"])
        words = json.loads((tp if tp.is_absolute() else WORKDIR / tp).read_text())["words"]

    # resolved, because ffmpeg runs from a temp dir (for the subtitle path) - a relative
    # --out would otherwise point inside that temp dir and fail to open
    out_dir = (Path(args.out).expanduser() if args.out else CLIPS_DIR).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    ffprobe = tool("ffprobe")
    vs = json.loads(subprocess.check_output(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=r_frame_rate,width,height", "-of", "json", str(src)], text=True))["streams"][0]
    num, den = vs["r_frame_rate"].split("/")
    opts = {
        "ffmpeg": tool("ffmpeg"), "ffprobe": ffprobe, "fps": int(num) / int(den),
        "width": vs["width"], "height": vs["height"],
        "brand": settings.get("branding", {}),
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
            flags.append(f"duration {qc['got'] - qc['want']:+.2f}s off the expected "
                         f"{qc['want']:.2f}s - a segment was dropped or mis-trimmed")
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
