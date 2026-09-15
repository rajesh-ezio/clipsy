#!/usr/bin/env python3
"""Put every pop-up callout on blank slide space - never over slide content.

Usage: python3 scripts/place_callouts.py output/content-plans/<stem>.json

Screen-share slides fill the frame, and a fixed spot covers the very table or chart the
presenter is talking about. For each callout this samples the source frames across the
whole time it is on screen and searches every position on the slide (a grid over x and
y) for one where the box, plus a clearance margin, touches no slide content - no
non-white pixels in any sampled frame. Among the clean spots it prefers the right-hand
side at mid height, then the nearest to that. It writes `x`, `y` and `side` (the edge
the box slides in from, whichever is nearer) into the plan.

If no clean spot exists anywhere, the callout is flagged: move its `at` to a moment
when the slide has room, shorten the text, or drop it. Nothing is placed over content
silently. Re-run after anything that rebuilds the plan. Needs ffmpeg; otherwise stdlib.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import WORKDIR  # noqa: E402
from render_clips import callout_box, tool  # noqa: E402

SCALE = 3          # analyse at a third of the resolution; plenty for "is anything here"
INK = 225          # luminance below this counts as slide content (slides are white)
CLEAR = 12         # px of empty margin required around the box, at full resolution
CAPTION_TOP = 0.80 # keep boxes above the caption band


def gray_frame(ffmpeg, src, t, w, h):
    out = subprocess.run([ffmpeg, "-v", "error", "-ss", f"{t:.2f}", "-i", str(src),
                          "-frames:v", "1", "-vf", f"scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    return out if len(out) == w * h else None


def integral(frame, w, h):
    """Summed-area table of ink pixels, so any box's ink count is four lookups."""
    s = [[0] * (w + 1) for _ in range(h + 1)]
    for y in range(h):
        row, acc, prev, cur = frame[y * w:(y + 1) * w], 0, s[y], s[y + 1]
        for x in range(w):
            acc += row[x] < INK
            cur[x + 1] = prev[x + 1] + acc
    return s


def ink_in(s, x0, y0, x1, y1):
    return s[y1][x1] - s[y0][x1] - s[y1][x0] + s[y0][x0]


def main():
    plan_path = Path(sys.argv[1])
    plan = json.loads(plan_path.read_text())
    src = Path(plan["source_video"])
    src = src if src.is_absolute() else WORKDIR / src
    ffmpeg, ffprobe = tool("ffmpeg"), tool("ffprobe")
    W, H = (int(v) for v in subprocess.check_output(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(src)], text=True).strip().split(",")[:2])
    fw, fh = W // SCALE, H // SCALE
    flagged = 0
    for clip in plan["clips"]:
        for co in clip.get("callouts", []):
            span = co.get("hold", 4.5) + 0.8
            tables = [integral(f, fw, fh) for f in
                      (gray_frame(ffmpeg, src, co["at"] + d, fw, fh)
                       for d in (0.3, span * 0.25, span * 0.5, span * 0.75, span)) if f]
            best = None
            # try the normal box first, then narrower ones (more lines, less width) - a tall
            # narrow box often fits a gap beside a title or diagram that a wide one doesn't
            for width in (520, 380, 290):
                g = callout_box(dict(co, side="right", max_width=width), W, H)
                bw, bh = g["w"] + 2 * CLEAR, g["h"] + 2 * CLEAR
                pref_x, pref_y = W - 40 * g["k"] - g["w"] - CLEAR, H * 0.42 - bh / 2
                for py in range(int(H * 0.06), int(H * CAPTION_TOP - bh), 8):
                    for px in range(8, int(W - bw - 8), 8):
                        x0, y0 = px // SCALE, py // SCALE
                        x1, y1 = min(fw, (px + int(bw)) // SCALE + 1), min(fh, (py + int(bh)) // SCALE + 1)
                        if any(ink_in(s, x0, y0, x1, y1) for s in tables):
                            continue
                        d = ((px - pref_x) / W) ** 2 + ((py - pref_y) / H) ** 2
                        if best is None or d < best[0]:
                            best = (d, px, py, width, g)
                if best:
                    break
            if best is None:
                flagged += 1
                co.pop("x", None)
                co.pop("max_width", None)
                print(f"{clip['video_id']}  {co.get('label', '')[:24]:<24} NO CLEAN SPOT - move `at`, "
                      f"shorten the text or drop it")
                continue
            _, px, py, width, g = best
            co.pop("max_width", None)
            if width != 520:
                co["max_width"] = width
            box_x, box_y = px + CLEAR, py + CLEAR
            co["x"] = round(box_x / W, 4)
            co["y"] = round((box_y + g["h"] / 2) / H, 4)
            co["side"] = "right" if box_x + g["w"] / 2 > W / 2 else "left"
            print(f"{clip['video_id']}  {co.get('label', '')[:24]:<24} x={co['x']:.2f} y={co['y']:.2f} "
                  f"slides from {co['side']}")
    # two pop-ups on screen at once stack or overlap - cuts inside a clip move a callout
    # earlier than its source time suggests, so check in finished-clip time
    from render_clips import clip_time, CALLOUT_SLIDE
    for clip in plan["clips"]:
        segs = [(k["start"], k["end"]) for k in clip["keep_segments"]]
        spans = sorted((clip_time(segs, co["at"]),
                        clip_time(segs, co["at"]) + co.get("hold", 4.5) + 2 * CALLOUT_SLIDE + 0.3,
                        co.get("label", "")) for co in clip.get("callouts", []))
        for (a0, a1, la), (b0, b1, lb) in zip(spans, spans[1:]):
            if b0 < a1:
                flagged += 1
                print(f"{clip['video_id']}  '{lb}' at {b0:.1f}s starts before '{la}' leaves ({a1:.1f}s) "
                      f"- move its `at` later")
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False))
    print(f"Updated {plan_path}" + (f" - {flagged} callout(s) need a decision" if flagged else ""))
    if flagged:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
