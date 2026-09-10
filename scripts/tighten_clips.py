#!/usr/bin/env python3
"""Cut silences, stutters and filler phrases out of a plan's keep_segments.

Usage:
    python3 scripts/tighten_clips.py output/content-plans/my-video.json

Turns silence_segments and filler_segments from flags into real cuts: every span it
finds is subtracted from keep_segments and recorded in the matching array, so the plan
says exactly what was removed. Re-run safe - it recomputes from the current keeps.

Thresholds live in config/settings.json under "tightening". Stdlib only.
"""
import argparse
import json
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (SKILL_HOME, WORKDIR, INPUT_DIR, TRANSCRIPTS_DIR, ANALYSIS_DIR,
                    PLANS_DIR, CAPTIONS_DIR, settings_path,
                    ensure_dirs)
PROJECT_ROOT = WORKDIR
SETTINGS_PATH = settings_path()




def find_cuts(words, keeps, cfg):
    """Return (silence_cuts, filler_cuts) as lists of (start, end, label)."""
    inside = [w for w in words if any(k["start"] <= w["start"] <= k["end"] for k in keeps)]
    silence, filler = [], []

    # Pauses must be measured WITHIN a single keep segment. Two words either side of a
    # cut are adjacent in `inside`, so treating them as consecutive reports the whole
    # removed span as one enormous "pause" - that once claimed 128% of a clip was silence.
    for k in keeps:
        span = [w for w in inside if k["start"] <= w["start"] and w["end"] <= k["end"] + 0.01]
        for a, b in zip(span, span[1:]):
            gap = b["start"] - a["end"]
            if gap <= cfg["silence_threshold_sec"]:
                continue
            # leave a natural beat on each side, cut the excess out of the middle
            keep_each = cfg["silence_keep_sec"] / 2
            start, end = a["end"] + keep_each, b["start"] - keep_each
            if end - start > 0.05:
                silence.append((round(start, 2), round(end, 2), f"{gap:.2f}s pause"))

    norm = lambda s: s.lower().strip(".,?!")

    if cfg["remove_stutters"]:
        for a, b in zip(inside, inside[1:]):
            # a repeat across a sentence boundary is not a stutter - "This is not ICP.
            # ICP need to be razor sharp" loses its first sentence if you cut one
            if a["word"].endswith((".", "?", "!")):
                continue
            if norm(a["word"]) == norm(b["word"]) and len(norm(a["word"])) > 1:
                # drop the first utterance of the doubled word, keep the second
                filler.append((round(a["start"], 2), round(b["start"], 2), f"{a['word']} {b['word']}"))

    for phrase in cfg["filler_phrases"]:
        parts = phrase.split()
        for i in range(len(inside) - len(parts) + 1):
            window = inside[i:i + len(parts)]
            if [norm(w["word"]) for w in window] != parts:
                continue
            # never cut a phrase that opens a sentence - it leaves a hanging start
            if i > 0 and inside[i - 1]["word"].endswith((".", "?", "!")):
                continue
            filler.append((round(window[0]["start"], 2), round(window[-1]["end"], 2), phrase))

    return sorted(silence), sorted(filler)


def subtract(keeps, cuts, min_fragment):
    """Remove cut spans from keep spans, dropping slivers."""
    spans = [(k["start"], k["end"], k.get("note", "")) for k in keeps]
    for cs, ce, _ in sorted(cuts):
        out = []
        for s, e, note in spans:
            if ce <= s or cs >= e:
                out.append((s, e, note))
                continue
            if s < cs:
                out.append((s, cs, note))
            if ce < e:
                out.append((ce, e, note))
        spans = out
    return [{"start": round(s, 2), "end": round(e, 2), "note": n}
            for s, e, n in spans if e - s >= min_fragment]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    args = parser.parse_args()

    ensure_dirs()
    cfg = json.loads(SETTINGS_PATH.read_text())["tightening"]
    plan_path = Path(args.plan)
    plan = json.loads(plan_path.read_text())
    words = json.loads((PROJECT_ROOT / plan["transcript_source"]).read_text())["words"]

    for clip in plan["clips"]:
        before = sum(k["end"] - k["start"] for k in clip["keep_segments"])
        silence, filler = find_cuts(words, clip["keep_segments"], cfg)
        # Pauses are cut when remove_silences is true (the default); set it false to only
        # record where they are. Filler words and stutters are always cut.
        cuts = filler + (silence if cfg["remove_silences"] else [])
        clip["keep_segments"] = subtract(clip["keep_segments"], cuts, cfg["min_fragment_sec"])
        clip["silence_segments"] = [{"start": s, "end": e} for s, e, _ in silence]
        clip["filler_segments"] = [{"start": s, "end": e, "text": t} for s, e, t in filler]
        after = sum(k["end"] - k["start"] for k in clip["keep_segments"])
        clip["duration_sec"] = round(after, 2)
        clip["source_start"] = clip["keep_segments"][0]["start"]
        clip["source_end"] = clip["keep_segments"][-1]["end"]
        print(f"{clip['video_id']}: {before:6.1f}s -> {after:6.1f}s  "
              f"(-{before - after:4.1f}s: {len(silence)} pauses, {len(filler)} filler) "
              f"{len(clip['keep_segments'])} segments")

    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    print(f"Updated {plan_path}")


if __name__ == "__main__":
    main()
