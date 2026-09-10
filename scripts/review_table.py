#!/usr/bin/env python3
"""Produce the pre-clip review table, and the TSV row block for the tracker sheet.

Usage:
    python3 scripts/review_table.py <plan> --review        # markdown table for in-session review
    python3 scripts/review_table.py <plan> --tsv           # TSV rows for "Zoom Video Clips"
    python3 scripts/review_table.py <plan> --tsv --links links.json

Workflow (see RUNBOOK.md):
  1. --review  -> user reads the table in session and vetoes anything
  2. render the clips (render_clips.py); the user uploads them to Drive
  3. once uploaded, --tsv --links to emit rows with Drive links, and paste them
     into the sheet. The Drive connector cannot write cells, so pasting is deliberate.

`clip_name` is the number plus a short label, numbered in ORIGINAL VIDEO ORDER, e.g.
"01 What is an ICP". That name is also the rendered filename and the SRT filename,
so a row in the sheet and a file on disk always match.

Sheet columns (10), in the tracker's own order - Hook precedes Score:
  Video | Clip name | Topic | Summary | Hook | Score | Score reasoning |
  Drive link | Approved | Posted | Transcript

`Video` is a short label for the source recording (e.g. "ICP"), set as `video_name` in
the plan, so rows can be filtered by recording. Approved and Posted default to "No".

Stdlib only.
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
from naming import numbered_names
PROJECT_ROOT = WORKDIR
SETTINGS_PATH = settings_path()


# Column order is fixed by the live tracker sheet - Hook sits BEFORE Score.
HEADERS = ["Video", "Clip name", "Topic", "Summary", "Hook", "Score", "Score reasoning",
           "Drive link", "Approved", "Posted", "Transcript"]


def ordered(plan):
    """Clips in original-video order, carrying the same numbered name the
    rendered file and the SRT use - see naming.numbered_names."""
    names = numbered_names(plan)
    clips = sorted(plan["clips"], key=lambda c: c["keep_segments"][0]["start"])
    for c in clips:
        c["_name"] = names[c["video_id"]]
    return clips


def cell(text, limit=None):
    t = " ".join(str(text or "").split())
    if limit and len(t) > limit:
        t = t[: limit - 1].rstrip() + "…"
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--review", action="store_true", help="markdown table for session review")
    ap.add_argument("--tsv", action="store_true", help="TSV rows for the tracker sheet")
    ap.add_argument("--links", help="JSON mapping clip_name -> Drive URL")
    args = ap.parse_args()

    plan = json.loads(Path(args.plan).read_text())
    clips = ordered(plan)
    video = plan.get("video_name") or plan.get("source_video", "").split("/")[-1]
    links = json.loads(Path(args.links).read_text()) if args.links else {}

    if args.review or not args.tsv:
        # Pre-clip review: no Drive link, no Approved/Posted - those do not exist yet.
        print(f"\n**{video}** — {len(clips)} clips, "
              f"{sum(c['duration_sec'] for c in clips)/60:.1f} min\n")
        print("| Clip name | Topic | Summary (points discussed) | Score | Score reasoning | Hook |")
        print("|---|---|---|---|---|---|")
        for c in clips:
            print(f"| {c['_name']} | {cell(c.get('topic'))} | {cell(c.get('summary'))} | "
                  f"{c.get('score', '')}/10 | {cell(c.get('score_reasoning'))} | "
                  f"{cell(c.get('hook_line'))} |")
        print()

    if args.tsv:
        print("\t".join(HEADERS))
        for c in clips:
            row = [video, c["_name"], c.get("topic", ""), c.get("summary", ""),
                   c.get("hook_line", ""), str(c.get("score", "")),
                   c.get("score_reasoning", ""),
                   links.get(c["_name"]) or links.get(c["title"], ""), "No", "No",
                   # verbatim words of the clip, rebuilt by fill_transcripts from the
                   # word data - never retyped, so it cannot drift from what was said
                   c.get("transcript", "")]
            print("\t".join(cell(x).replace("\t", " ") for x in row))


if __name__ == "__main__":
    main()
