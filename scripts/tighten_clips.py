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
import math
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (SKILL_HOME, WORKDIR, INPUT_DIR, TRANSCRIPTS_DIR, ANALYSIS_DIR,
                    PLANS_DIR, CAPTIONS_DIR, settings_path,
                    ensure_dirs)
PROJECT_ROOT = WORKDIR
SETTINGS_PATH = settings_path()




# Short real words that are also the start of longer ones ("in into", "we were", "the
# these"). A word in this list is never treated as a false start, however it is followed.
REAL_SHORT_WORDS = set("""
a an and any are as at be but by can car do for from go he her here his how i if in into is
it its let me more my no not now of off on one or our out over per pro sell she so than that
the them then there these they this to too two up us use was way we well were what when who
why will with you your all also back come day even get give has have just like look make
man many most much new old only own part put same see some such take tell than time very
""".split())


# Doubled words that are real English, not stutters: "a win win proposition" lost its
# meaning as "a win proposition"; "had had" and "that that" are grammatical.
REAL_DOUBLES = {"win", "had", "that"}


def is_fragment_of(frag, word):
    """True if `frag` looks like an abandoned start of `word` - "con" before "conversions"."""
    return (2 <= len(frag) <= 5 and len(word) >= len(frag) + 2 and word.startswith(frag)
            and frag.isalpha() and frag not in REAL_SHORT_WORDS)


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
    # Cut edges round DOWN. Rounding to nearest can land a few ms after the next kept
    # word starts, and that word then drops out of the transcript and captions.
    down = lambda t: math.floor(t * 100) / 100

    if cfg["remove_stutters"]:
        for i, (a, b) in enumerate(zip(inside, inside[1:])):
            # a repeat across a sentence boundary is not a stutter - "This is not ICP.
            # ICP need to be razor sharp" loses its first sentence if you cut one
            if a["word"].endswith((".", "?", "!")):
                continue
            # start no earlier than the previous word's end: overlapping timings let the
            # cut on "very, very" swallow the "Gong" before it
            cut_start = max(a["start"], inside[i - 1]["end"]) if i else a["start"]
            if cut_start >= b["start"] - 0.02:
                continue  # words nested in the timings: no clean cut, keep the stutter
            if (norm(a["word"]) == norm(b["word"]) and len(norm(a["word"])) > 1
                    and norm(a["word"]) not in REAL_DOUBLES):
                # drop the first utterance of the doubled word, keep the second
                filler.append((down(cut_start), down(b["start"]), f"{a['word']} {b['word']}"))
            elif is_fragment_of(norm(a["word"]), norm(b["word"])) and b["start"] - a["end"] < 0.6:
                # a false start on the next word: "con conversions". The doubled-word rule
                # alone left "con con conversions" as "con conversions".
                filler.append((down(cut_start), down(b["start"]), f"{a['word']} {b['word']}"))

    for phrase in cfg["filler_phrases"]:
        parts = phrase.split()
        for i in range(len(inside) - len(parts) + 1):
            window = inside[i:i + len(parts)]
            if [norm(w["word"]) for w in window] != parts:
                continue
            # never cut a phrase that opens a sentence - it leaves a hanging start
            if i > 0 and inside[i - 1]["word"].endswith((".", "?", "!")):
                continue
            # stop at the next word's start: Deepgram timings can overlap, and a cut that
            # runs past it drops that word ("strike" vanished from "you know, strike a")
            end = window[-1]["end"]
            if i + len(parts) < len(inside):
                end = min(end, inside[i + len(parts)]["start"])
            start = max(window[0]["start"], inside[i - 1]["end"]) if i else window[0]["start"]
            if down(end) - down(start) < 0.02:
                continue  # overlapping timings leave nothing clean to cut
            filler.append((down(start), down(end), phrase))

    return sorted(silence), sorted(filler)


def subtract(keeps, cuts, min_fragment, words):
    """Remove cut spans from keep spans, dropping slivers that hold no whole word.

    A short leftover is usually a breath, but not always: trimming the pause before
    "And the TAM minus SAM" left "And" alone in a 0.28s sliver, and dropping it made
    the next caption open lowercase. A sliver survives if a word sits wholly inside it.
    """
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
    def holds_word(s, e):
        return any(s - 0.01 <= w["start"] and w["end"] <= e + 0.01 for w in words)

    return [{"start": round(s, 2), "end": round(e, 2), "note": n}
            for s, e, n in spans if e - s >= min_fragment or holds_word(s, e)]


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
        clip["keep_segments"] = subtract(clip["keep_segments"], cuts, cfg["min_fragment_sec"], words)
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
