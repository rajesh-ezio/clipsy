#!/usr/bin/env python3
"""Fill each clip's `transcript` field verbatim from the source transcript's word data.

Usage:
    python3 scripts/fill_transcripts.py output/content-plans/my-video.json

The presenter's words are never retyped by hand — this assembles them from the
keep_segments and the word-level timestamps, so the transcript field cannot drift
from what was actually said. Safe to re-run; it overwrites the field each time.
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




def words_in(words, start, end):
    return [w for w in words if w["start"] >= start - 0.01 and w["end"] <= end + 0.01]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", help="Path to a content plan JSON")
    args = parser.parse_args()

    plan_path = Path(args.plan)
    plan = json.loads(plan_path.read_text())
    transcript_path = PROJECT_ROOT / plan["transcript_source"]
    words = json.loads(transcript_path.read_text())["words"]

    for clip in plan["clips"]:
        parts = []
        for seg in clip["keep_segments"]:
            chunk = " ".join(w["word"] for w in words_in(words, seg["start"], seg["end"]))
            if chunk:
                parts.append(chunk)
        clip["transcript"] = " ".join(parts)
        print(f"{clip['video_id']}: {len(clip['transcript'].split())} words")

    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    print(f"Updated {plan_path}")


if __name__ == "__main__":
    main()
