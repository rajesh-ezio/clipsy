#!/usr/bin/env python3
"""Generate an SRT per clip, timed to the EDITED timeline (not the source).

Usage:
    python3 scripts/make_captions.py output/content-plans/my-video.json

Each clip is a stitch of keep_segments, so a word's timeline position is its offset
within its own segment plus the run time of every segment before it. Cues never span
a cut, so a caption can never bridge two pieces of removed audio.

Writes output/captions/<clip name>.srt - standalone captions for any player or upload.
render_clips.py burns the same cues into the video.
Stdlib only.
"""
import argparse
import json
import sys
from pathlib import Path

from naming import numbered_names  # noqa: E402

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (SKILL_HOME, WORKDIR, INPUT_DIR, TRANSCRIPTS_DIR, ANALYSIS_DIR,
                    PLANS_DIR, CAPTIONS_DIR, settings_path,
                    ensure_dirs)
PROJECT_ROOT = WORKDIR
SETTINGS_PATH = settings_path()



def srt_ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def timeline_words(clip, words):
    """Every kept word as (timeline_start, timeline_end, text), across all segments.

    Cues are built on this continuous list rather than per segment, so a filler cut in the
    middle of a sentence no longer forces a caption break - that was producing one- and
    two-word orphan cues at every seam."""
    out, offset = [], 0.0
    for seg in clip["keep_segments"]:
        for w in words:
            if w["start"] >= seg["start"] - 0.01 and w["end"] <= seg["end"] + 0.01:
                out.append((offset + w["start"] - seg["start"],
                            offset + w["end"] - seg["start"], w["word"]))
        offset += seg["end"] - seg["start"]
    return out


def polish_cues(cues, cfg):
    """Make the cue list read like professional captions rather than a word dump.

    - Fold orphans (two words or fewer) into a neighbour, so a lone "dark." or "Or," never
      flashes up on its own. Orphans join the previous cue where they can, otherwise the next.
    - Hold each cue until the next one starts when the gap is short, so the caption box
      stays up and swaps text instead of blinking off and on between phrases.
    - Give any cue that is still very brief a minimum on-screen time.
    """
    soft_max = cfg.get("max_chars", 42) + 12
    bridge = cfg.get("bridge_gap", 0.8)
    min_dur = cfg.get("min_duration", 0.8)
    ends = (".", "?", "!")

    back = []
    for a, b, t in cues:
        if (back and len(t.split()) <= 2 and t.endswith(ends) and a - back[-1][1] < 1.0
                and len(back[-1][2]) + len(t) + 1 <= soft_max):
            pa, _, pt = back[-1]
            back[-1] = (pa, b, f"{pt} {t}")
        else:
            back.append((a, b, t))

    merged, i = [], 0
    while i < len(back):
        a, b, t = back[i]
        # anything still an orphan after the backward pass could not fold back - including
        # a clip's opening "Alright.", which has nothing before it - so it folds forward
        if (len(t.split()) <= 2 and i + 1 < len(back)
                and back[i + 1][0] - b < 1.0 and len(t) + len(back[i + 1][2]) + 1 <= soft_max):
            _, nb, nt = back[i + 1]
            merged.append((a, nb, f"{t} {nt}"))
            i += 2
        else:
            merged.append((a, b, t))
            i += 1

    final = []
    for i, (a, b, t) in enumerate(merged):
        nxt = merged[i + 1][0] if i + 1 < len(merged) else None
        if nxt is not None and nxt - b < bridge:
            b = nxt
        elif b - a < min_dur:
            b = a + min_dur if nxt is None else min(a + min_dur, nxt)
        final.append((round(a, 3), round(b, 3), t))
    return final


BREAK_BEFORE = {"and", "but", "or", "so", "which", "because", "where", "when", "who",
                "while", "then", "if", "whereas"}


# A caption line never ends on one of these - "...common and", "...build our go to".
WEAK_END = {"and", "or", "but", "so", "nor", "the", "a", "an", "of", "to", "for", "in", "on",
            "at", "with", "by", "from", "into", "about", "our", "your", "their", "my", "his",
            "her", "its", "this", "that", "these", "those", "which", "who", "because", "if",
            "than", "as"}


def _ends_well(word):
    """A word that closes a sentence is always a fine line ending ("...like this."). Otherwise
    the line must not end on an article, preposition, conjunction or possessive."""
    if word.endswith((".", "?", "!")):
        return True
    return word.lower().strip(".,?!;:") not in WEAK_END


def _phrase_break(cur, max_chars=None):
    """Where to split a caption that has run long. Returns an index into cur, or None to
    flush the whole line.

    Prefers a phrase boundary - after a comma, or before a conjunction - as long as the line
    it leaves behind ends on a word that can end a line and still fits. With no usable
    boundary, backs off to the last point that fits AND ends well. The length cap is checked
    after a word is appended, so one long word can push a line well past it ("...problem
    statements different" hit 51 characters); breaking before the overflowing word fixes that
    and keeps the next line from becoming an orphan it cannot fold."""
    def fits(j):
        return max_chars is None or len(" ".join(x[2] for x in cur[:j])) <= max_chars

    best = None
    for j in range(3, len(cur)):
        before, word = cur[j - 1][2], cur[j][2].lower().strip(".,?!;:")
        if (before.endswith((",", ";", ":")) or word in BREAK_BEFORE) \
                and _ends_well(before) and fits(j):
            best = j
    if best is not None:
        return best
    if _ends_well(cur[-1][2]) and fits(len(cur)):
        return None
    for j in range(len(cur) - 1, 1, -1):
        if _ends_well(cur[j - 1][2]) and fits(j):
            return j
    return None


def cues_for_clip(clip, words, cfg):
    """Words -> (timeline_start, timeline_end, text) cues, timed to the EDITED timeline.

    Breaks at sentence ends and at commas once a cue has a few words. When a cue hits the
    word/second/character cap it backs up to the last phrase boundary rather than cutting
    wherever the cap landed, and carries the remainder into the next cue."""
    cues, cur = [], []

    def flush(part):
        cues.append((part[0][0], part[-1][1], " ".join(x[2] for x in part)))

    for a, b, word in timeline_words(clip, words):
        cur.append((a, b, word))
        text = " ".join(x[2] for x in cur)
        # a comma only counts as a break when the word carrying it can end a line - the
        # speaker's "annual revenue of, let's say" must not leave "...revenue of," hanging
        if word.endswith((".", "?", "!")) or (word.endswith((",", ";", ":")) and len(cur) >= 4
                                               and _ends_well(word)):
            flush(cur)
            cur = []
        elif (len(cur) >= cfg["max_words"] or b - cur[0][0] >= cfg["max_seconds"]
              or len(text) >= cfg["max_chars"]):
            j = _phrase_break(cur, cfg["max_chars"])
            flush(cur[:j] if j else cur)
            cur = cur[j:] if j else []
    if cur:
        flush(cur)
    return polish_cues(cues, cfg)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    args = parser.parse_args()

    ensure_dirs()
    settings = json.loads(SETTINGS_PATH.read_text())
    cfg = settings.get("captions", {"max_words": 7, "max_seconds": 3.0, "max_chars": 42})
    plan = json.loads(Path(args.plan).read_text())
    words = json.loads((PROJECT_ROOT / plan["transcript_source"]).read_text())["words"]

    CAPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    names = numbered_names(plan)
    for clip in plan["clips"]:
        cues = cues_for_clip(clip, words, cfg)
        body = "\n".join(
            f"{i}\n{srt_ts(a)} --> {srt_ts(b)}\n{t}\n"
            for i, (a, b, t) in enumerate(cues, 1)
        )
        out = CAPTIONS_DIR / f"{names[clip['video_id']]}.srt"
        out.write_text(body)
        last = cues[-1][1] if cues else 0
        flag = "" if last <= clip["duration_sec"] + 0.05 else "  <-- OVERRUNS CLIP"
        print(f"{len(cues):>4} cues  ends {last:6.2f}s / {clip['duration_sec']:.2f}s  "
              f"{out.name}{flag}")
    print(f"\nWrote {len(plan['clips'])} SRT files to {CAPTIONS_DIR}")


if __name__ == "__main__":
    main()
