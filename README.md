# Clipsy

A Claude Code skill that turns a long recording — a Zoom masterclass, webinar or cohort
session — into standalone, publish-ready LinkedIn clips.

**Claude decides what is worth publishing and exactly where to cut. ffmpeg renders. You
upload and post.** The editorial judgment is the hard part and the only part that
needs a model; everything else is mechanical.

```
recording.mp4
  → transcript          Deepgram nova-3, word-level timestamps + diarization
  → editorial pass      what deserves publishing, and precisely where each clip starts/ends
  → QC + scores         each clip rated /10 with reasoning
  → REVIEW TABLE        ← you approve or veto here, before anything is rendered
  → finished MP4s       captioned, loudness-normalised, self-checked; ~30s for five clips
  → tracker rows        TSV with Drive links, pasted into a Google Sheet
```

## Install (new machine, about 2 minutes)

The skill installs as `video-repurposer`. Claude Code picks up any skill in
`~/.claude/skills/`, so cloning into that folder is the whole install:

```bash
git clone https://github.com/rajesh-ezio/clipsy ~/.claude/skills/video-repurposer
```

Next, install ffmpeg (on macOS, `brew install ffmpeg`) and save a Deepgram API key. There's a
free tier at [console.deepgram.com](https://console.deepgram.com). The key lives outside the
repo, so it can never be committed:

```bash
printf '%s' 'YOUR_DEEPGRAM_KEY' > ~/.deepgram_key && chmod 600 ~/.deepgram_key
```

Then check the machine. The script names the exact fix for anything missing:

```bash
python3 ~/.claude/skills/video-repurposer/scripts/check_setup.py --online
```

That's it. Open Claude Code in any folder, hand it a recording, and ask for clips.

| Need | Notes |
|---|---|
| Python 3.9+ | Standard library only, so no pip and no venv. |
| `ffmpeg` + `ffprobe` | Needs libass, loudnorm and libx264; Homebrew's build has all three. `uv tool install static-ffmpeg` also works. |
| Deepgram key | `~/.deepgram_key` or `$DEEPGRAM_API_KEY`. About $0.10 per 22 minutes of audio. |

The scripts are **stdlib-only Python 3.9+** — no venv, no pip install. Deepgram decodes the
video server-side, so the editorial pipeline needs no ffmpeg at all; ffmpeg is only for
rendering.

## Use

Drop a recording and ask for clips. The skill triggers on its own — it does not need to be
named. Set `VIDEO_REPURPOSER_HOME` to the folder holding the recording and work from there:
data lands in `input/`, `transcripts/`, `analysis/`, `output/`, while the skill keeps config,
fonts and scripts.

The approval gate is the point of the design. It is far cheaper to kill a clip in the review
table than after it has been rendered and uploaded. Scores are meant to be honest rather than
flattering — in testing, a clip scored 6/10 with "kill this first" in its reasoning was
independently judged bad on viewing, and a 9/10 judged good.

To change a cut, edit that clip's `keep_segments` in the plan and re-render it with `--clip`.
The plan is the single record of what is in every clip; nothing is hand-edited in a video editor.

## Features

**Full build report, with measured results and verification: [`docs/REPORT.md`](docs/REPORT.md).**

**Editorial.** The whole transcript is analysed before anything is chosen. Every clip has an
honest /10 score with its reasoning, plus a hook, a summary and a target audience. Rejected
passages are written down with reasons. Openings must pass the cold-open test, and the
approval gate comes before any render.

**Cutting.**
- Word-edge boundaries from Deepgram timestamps, with padding clamped to silence.
- Filler and stutters removed ("um", "you know", "kind of", repeats, half-word false starts
  like "con conversions"), never across a sentence boundary.
- Trimming a pause never deletes a word, even one left in a very short piece of audio.
- Pauses over 0.7 s trimmed to 0.25 s.
- Non-adjacent passages stitched into one clip.
- The validator fails the plan if a removed word is still inside a keep.

**Rendering.**
- Frame-accurate cuts, within one frame of the plan.
- 12 ms fades at every seam, so there are no clicks.
- Voice and picture fade in (0.3 s video, 0.15 s audio) and out (0.5 s).
- Two-pass loudness normalisation with true peak capped at −1.5 dBTP.
- The source's own dimensions, with no cropping.
- H.264 CRF 20, AAC at 160k, `+faststart`.
- Three clips render in parallel; `--clip` re-renders one.
- Optional pop-up callouts: a labelled box slides in from the right to explain a name the
  viewer won't know, holds, then slides out (`callouts` in the plan).
- Optional added text: cover part of the slide for the whole clip and put new text there,
  e.g. replace a slide title that doesn't match what the clip is about (`slide_cover`).
- Title cards: centre a question on an empty slide, or cover a borrowed line's slide for just
  that line (`slide_cover` with `align` and `from`/`to`); pop-ups around them can be pinned.
- Approved long clips (`long_approved`) and clips added later that take the next number
  (`append_after_existing`, numbered per batch).
- Source timestamps in the clip name — `16 How to discover topics (0.58.49-1.04.40)` — for a
  whole recording or from a given clip number on (`name_timestamps`).

**Captions (on by default).**
- White Inter Bold on a 78%-opacity dark box, placed clear of the slide's accent bar. Every
  style value is in config.
- Lines break at phrases and never end on "and" or "the".
- At most 7 words, 4 s and 42 characters per line; a line breaks before the word that would
  overflow it.
- One-word orphans fold into a neighbour.
- Short gaps are bridged so the box never blinks, and each caption stays up at least 0.8 s.
- One continuous timeline across all cuts, plus an SRT export.

**QC built in.** Every clip prints OK, CHECK or FAIL, covering runtime against the plan,
loudness, peak, and caption blinks, orphans and dangling words. One frame per clip is saved
for a visual check.

**Tracking.** Numbered clip names are shared by the MP4, the SRT and the sheet row. There's
an 11-column tracker TSV, with a verbatim transcript rebuilt from word data.

## What it knows that a generic clipper does not

These rules came from real failures, not theory:

- **The cold-open test.** A clip is watched with nothing before it. Opening on a connective
  ("So…", "Let's take an example of…") or naming something it never shows ("the *other*
  filters") makes it unusable. The validator flags these automatically.
- **Running-example company operations are rarely standalone.** Teaching sessions lean on
  one company; passages narrating *that company's* operations are connective tissue, not
  lessons. The test is what survives if you delete the company.
- **`duration_sec` is the sum of kept segments** — the finished runtime — not the width of
  the source window. A clip stitching a 7-second setup line onto a passage four minutes
  later has a 5:35 window and a 1:39 runtime.
- **Captions that read like a person made them.** Lines break on phrases and never end on
  "and" or "the"; lone one-word captions fold into a neighbour; the box holds between
  phrases instead of blinking. Every render reports these, so they are checked, not hoped for.
- **Screen-share framing.** Keep the presenter's camera box; never crop to vertical, which
  destroys the slide carrying the message.

## Honest state

Working and tested end to end: transcription, clip selection, QC, scoring, the review table,
ffmpeg rendering (frame-accurate, duration-checked, loudness-normalised, captioned), caption
SRTs, tracker TSV. Verified from a clean directory by subagents with no prior context.

Known limits, all deliberate rather than unfinished:

- **The Google Drive connector cannot write spreadsheet cells** — it is file-level only. So
  tracker rows are emitted as TSV for pasting, not appended via API.
- **Loudness lands around -15.5 LUFS, not exactly -14.** Zoom recordings' peaks rule out a
  clean linear gain of that size; -15.5 sits inside the band social video plays at.
- **The approval gate has not been exercised end to end** — every test run was told to stop
  at the table.
- **No CapCut.** Earlier versions built CapCut drafts by writing its project files directly.
  That was removed once the renderer covered cuts, captions and loudness: CapCut has no API,
  its export needed macOS Accessibility on the host app, and its automation hooks break on
  app updates. It remains in git history.

## Layout

| Path | What |
|---|---|
| `SKILL.md` | The workflow Claude follows. Start here. |
| `references/editorial.md` | How to choose and cut clips; the content-plan schema. |
| `references/gotchas.md` | Environment, Deepgram, editorial and rendering gotchas already paid for. |
| `scripts/` | The pipeline. Stdlib only. `_paths.py` resolves skill vs working directory. |
| `config/` | Defaults and the content-plan JSON schema. A recording can override locally. |
| `assets/fonts/` | Inter, used for burned-in captions. |
| `docs/REPORT.md` | Build report: design, features, measured results, verification, lessons. |

## Licence note

Inter is included under its OFL licence (`assets/fonts/OFL-Inter.txt`). Nothing else
third-party is in the current tree.
