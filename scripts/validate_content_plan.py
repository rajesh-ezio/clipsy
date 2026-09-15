#!/usr/bin/env python3
"""Validate a content plan against config/schema/content_plan.schema.json + cross-field rules.

Usage:
    python3 scripts/validate_content_plan.py output/content-plans/my-video.json
    python3 scripts/validate_content_plan.py            # validate every plan in output/content-plans/

Exits 1 on errors. Warnings do not fail the run. Stdlib only.
"""
import argparse
import json
import sys
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (SKILL_HOME, WORKDIR, INPUT_DIR, TRANSCRIPTS_DIR, ANALYSIS_DIR,
                    PLANS_DIR, CAPTIONS_DIR, settings_path,
                    ensure_dirs)
PROJECT_ROOT = WORKDIR
SETTINGS_PATH = settings_path()


EPS = 0.5

TOP_REQUIRED = ["video_id", "video_name", "source_video", "source_duration_sec",
                "transcript_source", "generated_at", "presenter_label", "clips",
                "rejected_sections"]
CLIP_REQUIRED = ["video_id", "title", "core_value_point", "target_audience", "why_standalone",
                 "source_start", "source_end", "duration_sec", "keep_segments", "remove_segments",
                 "other_speaker_segments", "silence_segments", "filler_segments",
                 "recommended_hook", "recommended_ending", "confidence_score", "transcript",
                 # The review fields are not decoration: they ARE the review table and the
                 # tracker row. Without them the approval gate prints blank columns and
                 # nothing explains why, so treat their absence as a hard error.
                 "short_name", "topic", "summary", "score", "score_reasoning", "hook_line"]
SEGMENT_FIELDS = ["keep_segments", "remove_segments", "other_speaker_segments",
                  "silence_segments", "filler_segments"]


# A clip is watched cold, with nothing before it. These openings tell the viewer they
# arrived late — either a connective implying a preceding sentence, or an outright
# reference to material the clip does not contain.
COLD_OPEN_CONNECTIVES = {
    "so", "and", "but", "also", "then", "now", "because", "however", "anyway",
    "therefore", "hence", "thus", "besides", "meanwhile", "again", "right",
}
COLD_OPEN_PHRASES = [
    "let me talk about", "let me show you", "let's take an example",
    "there are multiple", "as i said", "as i mentioned", "i just spoke",
    "we discussed", "we talked about", "coming back", "as we saw",
    "the other", "another example", "the next thing", "the second", "the third",
    "the fourth", "similarly", "likewise",
]
# A dangling reference anywhere in the opening sentence is worse than a soft connective:
# it names something the viewer was never shown.
DANGLING_REFERENCES = [
    "other filters", "as i said", "as i mentioned", "i just spoke", "we discussed",
    "earlier", "previously", "as we saw", "that we saw", "the framework we",
]


# Openings that dive into a story or experiment before saying what the clip is about.
# "We did a AB test where we had a product page..." left a LinkedIn reader asking who, why
# and on what; opening on "Customer stories are nothing but case studies..." fixed it.
STORY_OPENINGS = (
    "we did", "we ran", "we tried", "we tested", "we launched", "we built", "we sponsored",
    "we had", "we went", "i did", "i ran", "i tried", "i was", "i remember", "so we",
    "let me take an example", "let me give you an example", "let's take an example",
    "for example", "here is a story", "here's a story",
)


# Preamble that points at something the viewer never saw. "The biggest learning from the
# Salesforce video is making your customer the hero" -> "what learning? why Salesforce?"
# Starting on "making your customer the hero" fixed it.
PREAMBLE_OPENINGS = (
    "the biggest learning", "the key learning", "the biggest lesson", "the key lesson",
    "the key takeaway", "the biggest takeaway", "the lesson from", "the learning from",
    "the takeaway from", "the point here is",
)


def check_topic_first(text, tag, rep):
    """The viewer must know what the clip is about before the story or experiment starts."""
    opening = " ".join(text.lower().split()[:6]).strip('.,!?;:"\'')
    for phrase in PREAMBLE_OPENINGS:
        if opening.startswith(phrase):
            rep.warn(f"{tag}: opens on preamble ({phrase!r}) that points at something unseen - "
                     f"start a few words later, on the idea itself")
            return
    for phrase in STORY_OPENINGS:
        if opening.startswith(phrase):
            rep.warn(f"{tag}: opens on a story ({phrase!r}) before saying what it is about - "
                     f"a LinkedIn reader asks who, why and on what. Pull in the line that "
                     f"names the topic, even from earlier in the recording, and keep time order")
            return


# Lines where the presenter announces a new topic - a question or a signpost. They are the
# best opening a clip can have, even on "And" or a lowercase word: the sheet's Topic column
# is invisible to a LinkedIn viewer, so the video itself must say what it is about.
# Learned from Events 04/06/07/08, each fixed by starting a few seconds earlier:
# "How do we maximize the sponsorship?", "And then comes post event.", "let me tell my
# experience of...", "and then comes the next one."
TOPIC_SIGNPOSTS = (
    # the session's own opening names the first clip's topic - "Today, we're gonna talk
    # about the power of customer stories" was wrongly cut as intro housekeeping
    "today we're gonna", "today we are gonna", "today we are going to", "today we will",
    "today i'm gonna", "today i am going to", "we're gonna talk about", "we are going to talk about",
    "how do", "how can", "how should", "how does", "what is", "what are", "what's the",
    "why do", "why should", "and then comes", "then comes", "now comes", "let me tell",
    "let's talk about", "let's start with", "let's look at", "now let's", "so let's",
    "let's kind of", "the next one", "number one", "number two", "number three",
    "step one", "step two", "step three",
)


# Lines that look like signposts but are not topic lines: housekeeping, example lead-ins,
# course back-references, and preamble ("What is the biggest learning...") the user rejected.
NOT_TOPIC_LINES = ("jump straight", "jump right", "get started", "let's begin", "example",
                   "again", "biggest learning", "key learning", "takeaway", "the lesson")


def _collapse(text):
    """Lowercase, strip punctuation, and drop stuttered repeats: 'and then and then comes'."""
    toks = [t.strip('.,!?;:"\'') for t in text.lower().split()]
    toks = [t for t in toks if t]
    out = []
    for t in toks:
        out.append(t)
        for n in (3, 2, 1):             # remove an immediately repeated 1-3 word run
            if len(out) >= 2 * n and out[-n:] == out[-2 * n:-n]:
                del out[-n:]
                break
    return " ".join(out)


def is_signpost(opening):
    o = _collapse(opening)
    if any(bad in o for bad in NOT_TOPIC_LINES):
        return False
    if any(o.startswith(s) for s in TOPIC_SIGNPOSTS):
        return True
    for lead in ("and ", "so ", "now ", "alright ", "okay "):
        if o.startswith(lead):
            return any(o[len(lead):].startswith(s) for s in TOPIC_SIGNPOSTS)
    return False


def check_topic_opener(clip, words, tag, rep, lookback=25.0):
    """Point at a topic line the presenter said just before this clip starts.

    A topic line starts a sentence or a clause - "...for an event, how do we maximize the
    sponsorship?" counts from "how". Lines within 1.5s of the clip start are the clip's own
    opening and are ignored.
    """
    keeps = clip.get("keep_segments") or []
    if not keeps or not words:
        return
    start = min(k["start"] for k in keeps)
    before = [i for i, w in enumerate(words) if start - lookback <= w["start"] < start - 1.5]
    for i in reversed(before):          # nearest to the clip first
        if i and not words[i - 1]["word"].endswith((".", "?", "!", ",")):
            continue                    # not the start of a sentence or clause
        line = " ".join(w["word"] for w in words[i:i + 12])
        if is_signpost(line):
            t = words[i]["start"]
            rep.warn(f"{tag}: a topic line sits {start - t:.0f}s before this clip, at "
                     f"{int(t // 60):02d}:{t % 60:04.1f}: \"{' '.join(line.split()[:9])}...\" - "
                     f"start there so a viewer knows the topic")
            return


def check_cold_open(clip, tag, rep):
    """A clip must make sense from its first word. See RUNBOOK.md."""
    text = (clip.get("transcript") or "").strip()
    if not text:
        return
    first_word = text.split()[0]
    bare = first_word.lower().strip('.,!?;:"\'')
    opening = " ".join(text.split()[:14]).lower()
    if is_signpost(" ".join(text.split()[:12])):
        return  # opens on a line naming the topic - the best opening, "And" or not
    check_topic_first(text, tag, rep)

    if first_word[:1].islower():
        rep.warn(f"{tag}: opens mid-sentence on a lowercase word ({first_word!r}) — "
                 f"the clip starts in the middle of a thought")
    if bare in COLD_OPEN_CONNECTIVES:
        rep.warn(f"{tag}: opens on the connective {first_word!r} — implies a sentence "
                 f"the viewer never heard")
    for phrase in COLD_OPEN_PHRASES:
        if opening.startswith(phrase):
            rep.warn(f"{tag}: opens on {phrase!r} — a continuation, not a cold open")
            break
    for ref in DANGLING_REFERENCES:
        if ref in opening:
            rep.warn(f"{tag}: opening sentence refers to {ref!r} — a dangling reference "
                     f"to material this clip does not contain")
            break


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def check_spans(spans, where, clip_start, clip_end, rep: Report, must_be_inside=True):
    prev_end = None
    for i, span in enumerate(spans):
        tag = f"{where}[{i}]"
        if not isinstance(span, dict) or "start" not in span or "end" not in span:
            rep.error(f"{tag}: needs numeric 'start' and 'end'")
            continue
        start, end = span["start"], span["end"]
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            rep.error(f"{tag}: start/end must be numbers")
            continue
        if end <= start:
            rep.error(f"{tag}: end ({end}) must be greater than start ({start})")
        if must_be_inside and (start < clip_start - EPS or end > clip_end + EPS):
            rep.warn(f"{tag}: {start}-{end} falls outside the clip window {clip_start}-{clip_end}")
        if prev_end is not None and start < prev_end - EPS:
            rep.warn(f"{tag}: starts at {start}, before the previous span ended at {prev_end} (out of order or overlapping)")
        prev_end = end


def validate_clip(clip, idx, settings, rep: Report, words=None):
    tag = f"clips[{idx}]"
    missing = [f for f in CLIP_REQUIRED if f not in clip]
    for field in missing:
        rep.error(f"{tag}: missing required field '{field}'")

    for field in ["video_id", "title", "core_value_point", "target_audience", "why_standalone",
                  "recommended_hook", "recommended_ending", "transcript",
                  "short_name", "topic", "summary", "score_reasoning", "hook_line"]:
        if field in missing:
            continue
        value = clip.get(field)
        if not isinstance(value, str) or not value.strip():
            rep.error(f"{tag}.{field}: must be a non-empty string")

    if "confidence_score" not in missing:
        score = clip.get("confidence_score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 1:
            rep.error(f"{tag}.confidence_score: must be a number between 0 and 1")

    if "score" not in missing:
        sc = clip.get("score")
        if not isinstance(sc, (int, float)) or isinstance(sc, bool) or not 0 <= sc <= 10:
            rep.error(f"{tag}.score: must be a number between 0 and 10")
        elif isinstance(clip.get("confidence_score"), (int, float)):
            # They measure different things but should not contradict: a clip you would
            # publish at 9/10 is not one you are 30% sure about.
            if abs(sc / 10 - clip["confidence_score"]) > 0.35:
                rep.warn(f"{tag}: score {sc}/10 and confidence {clip['confidence_score']} "
                         f"point in different directions - check one of them is not a typo")

    start, end, duration = clip.get("source_start"), clip.get("source_end"), clip.get("duration_sec")
    if not all(isinstance(v, (int, float)) for v in [start, end, duration]):
        if not {"source_start", "source_end", "duration_sec"} & set(missing):
            rep.error(f"{tag}: source_start, source_end and duration_sec must all be numbers")
        return

    if end <= start:
        rep.error(f"{tag}: source_end ({end}) must be greater than source_start ({start})")

    keeps = clip.get("keep_segments")
    if isinstance(keeps, list) and keeps and all(
        isinstance(k, dict) and isinstance(k.get("start"), (int, float))
        and isinstance(k.get("end"), (int, float)) for k in keeps
    ):
        kept = sum(k["end"] - k["start"] for k in keeps)
        if abs(duration - kept) > EPS:
            rep.error(f"{tag}: duration_sec ({duration}) does not match the sum of keep_segments ({kept:.2f})")
        if abs(start - keeps[0]["start"]) > EPS:
            rep.error(f"{tag}: source_start ({start}) should equal the first keep_segment start ({keeps[0]['start']})")
        if abs(end - keeps[-1]["end"]) > EPS:
            rep.error(f"{tag}: source_end ({end}) should equal the last keep_segment end ({keeps[-1]['end']})")

    if duration > settings["max_clip_duration_sec"]:
        rep.error(f"{tag}: duration {duration}s exceeds the {settings['max_clip_duration_sec']}s cap")
    if duration < settings["min_clip_duration_sec"]:
        rep.warn(f"{tag}: duration {duration}s is below the {settings['min_clip_duration_sec']}s floor")

    check_cold_open(clip, tag, rep)
    if words:
        check_topic_opener(clip, words, tag, rep)

    # keep_segments are what actually cut - the gaps between them ARE the removals.
    # remove_segments is documentation. A remove that still sits inside a keep was
    # recorded but never applied, and that material ships into the draft uncut.
    if isinstance(keeps, list) and keeps:
        for i, rm in enumerate(clip.get("remove_segments") or []):
            if not (isinstance(rm, dict) and isinstance(rm.get("start"), (int, float))
                    and isinstance(rm.get("end"), (int, float))):
                continue
            for k in keeps:
                lo, hi = max(rm["start"], k["start"]), min(rm["end"], k["end"])
                if hi <= lo:
                    continue
                # Only spoken words matter. Declared removal boundaries and snapped,
                # padded keep boundaries rarely align to the millisecond, so a bare
                # time overlap is usually just the silence between two words.
                stranded = [w["word"] for w in words if w["start"] >= lo - 0.01
                            and w["end"] <= hi + 0.01] if words else None
                if stranded:
                    rep.error(f"{tag}.remove_segments[{i}]: {len(stranded)} word(s) marked for "
                              f"removal are still inside a keep_segment and would ship in the "
                              f"clip: {' '.join(stranded[:8])!r}")
                    break
                if stranded is None and hi - lo > EPS:
                    rep.warn(f"{tag}.remove_segments[{i}]: overlaps a keep_segment by "
                             f"{hi - lo:.2f}s (no transcript available to check for words)")
                    break

    for field in SEGMENT_FIELDS:
        spans = clip.get(field)
        if not isinstance(spans, list):
            rep.error(f"{tag}.{field}: must be an array")
            continue
        if field == "keep_segments" and not spans:
            rep.error(f"{tag}.keep_segments: must contain at least one segment")
        check_spans(spans, f"{tag}.{field}", start, end, rep)


def validate_plan(path: Path, settings) -> Report:
    rep = Report()
    try:
        plan = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        rep.error(f"invalid JSON: {e}")
        return rep

    for field in TOP_REQUIRED:
        if field not in plan:
            rep.error(f"missing required top-level field '{field}'")

    words = None
    src = plan.get("transcript_source")
    if src:
        tp = Path(src)
        tp = tp if tp.is_absolute() else WORKDIR / src
        if tp.exists():
            words = json.loads(tp.read_text()).get("words")

    clips = plan.get("clips")
    if not isinstance(clips, list) or not clips:
        rep.error("'clips' must be a non-empty array")
        return rep

    seen_ids = set()
    for i, clip in enumerate(clips):
        if not isinstance(clip, dict):
            rep.error(f"clips[{i}]: must be an object")
            continue
        cid = clip.get("video_id")
        if cid in seen_ids:
            rep.error(f"clips[{i}]: duplicate video_id '{cid}'")
        seen_ids.add(cid)
        validate_clip(clip, i, settings, rep, words)

    # Compare the spans actually kept, not the outer windows: a clip that stitches an
    # early setup line onto a later passage has a window engulfing other clips while
    # sharing no source material with them.
    kept = sorted(
        (k["start"], k["end"], c.get("video_id"))
        for c in clips for k in (c.get("keep_segments") or [])
        if isinstance(k, dict) and isinstance(k.get("start"), (int, float))
        and isinstance(k.get("end"), (int, float))
    )
    for (s1, e1, id1), (s2, e2, id2) in zip(kept, kept[1:]):
        if id1 != id2 and s2 < e1 - EPS:
            rep.warn(f"clips '{id1}' and '{id2}' both publish source audio {s2:.2f}-{min(e1, e2):.2f}")

    for i, section in enumerate(plan.get("rejected_sections", [])):
        if not isinstance(section, dict) or not section.get("reason"):
            rep.error(f"rejected_sections[{i}]: needs a 'reason'")
    check_spans(plan.get("rejected_sections", []), "rejected_sections", 0,
                plan.get("source_duration_sec", 0), rep, must_be_inside=False)

    return rep


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", nargs="?", help="Path to a content plan JSON. Omit to validate all.")
    args = parser.parse_args()

    settings = json.loads(SETTINGS_PATH.read_text())
    targets = [Path(args.plan)] if args.plan else sorted(PLANS_DIR.glob("*.json"))
    if not targets:
        raise SystemExit(f"No content plans found in {PLANS_DIR}")

    failed = False
    for path in targets:
        rep = validate_plan(path, settings)
        status = "FAIL" if rep.errors else ("PASS (with warnings)" if rep.warnings else "PASS")
        print(f"\n{path.name}: {status}")
        for e in rep.errors:
            print(f"  ERROR   {e}")
        for w in rep.warnings:
            print(f"  warning {w}")
        failed = failed or bool(rep.errors)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
