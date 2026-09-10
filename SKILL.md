---
name: video-repurposer
description: Turn a long recording (Zoom masterclass, webinar, cohort session, screen-share teaching video) into standalone LinkedIn clips - transcribe with Deepgram, choose the cuts, QC and score them, show a review table for approval, then render finished captioned MP4s with ffmpeg and emit tracker-sheet rows. Use this whenever the user drops a video file or recording and wants clips, or says any of "clip this", "repurpose this recording", "cut this into clips", "make LinkedIn videos from this", "which parts of this are worth posting", "score these clips", or asks to update the Zoom Video Clips tracker or add Drive links to it. Use it even when they only hand over a video path with little explanation - a long recording plus any mention of clips, posting, or LinkedIn is this skill.
---

# Video repurposer

Long recording in, publishable standalone clips out.

**You decide what to publish and exactly where to cut. ffmpeg renders finished files. The
user uploads and posts.** Holding that line is what keeps this reliable — the editorial
judgment is the hard part and the only part that needs you.

## Division of labour — the user does these, not you

| You | The user, manually |
|---|---|
| Transcribe, choose cuts, QC, score | Approves the review table |
| Render the finished MP4s | Watches them; asks for a cut to be adjusted if one needs it |
| Read Drive links back, emit the TSV | Uploads to Drive, pastes the TSV, posts |

One settled constraint, not a gap to fix: the Google Drive connector is **file-level only —
it cannot write spreadsheet cells**, so rows are emitted as TSV for the user to paste.
Don't relitigate it mid-run.

## Setup

**First, check the machine.** It takes a second and names the exact fix for anything
missing (ffmpeg, the Deepgram key, fonts). Run it at the start of every job; on a new
machine it is the difference between a clean run and a failure at step 2 or step 6:

```bash
python3 ~/.claude/skills/video-repurposer/scripts/check_setup.py
```

If it reports a missing Deepgram key, ask the user to create the key file themselves with
the command it prints. Never ask for the key in chat, and never write it anywhere inside
this skill folder. The folder is a git repo, and part of it is public.

Scripts live in this skill and run from anywhere. Point them at the recording's folder:

```bash
export VIDEO_REPURPOSER_HOME=/path/to/this/recordings/folder   # defaults to cwd
cd "$VIDEO_REPURPOSER_HOME"                                    # then stay here
export PATH="$HOME/.local/bin:$PATH"                           # ffmpeg/ffprobe
S=~/.claude/skills/video-repurposer/scripts
```

**Work from inside `VIDEO_REPURPOSER_HOME`.** The scripts resolve their data dirs against
it, but plan paths you pass as arguments resolve against the current directory. Running
from somewhere else means juggling two frames of reference for no benefit.

The Deepgram key is global at `~/.deepgram_key` (or `$DEEPGRAM_API_KEY`), so any session
on this machine works with no per-project setup. `ffmpeg`/`ffprobe` are at `~/.local/bin`.

Data lands under `VIDEO_REPURPOSER_HOME`: `input/`, `transcripts/`, `analysis/`,
`output/content-plans/`, `output/captions/`, `output/clips/`. Config resolves from that
folder first (`config/settings.json`) and falls back to the skill's defaults, so a
recording can override clip caps or filler words without touching the installed skill.

## The flow

### 1. Ask for the recording, and settle where the work happens

If the user hasn't given a file, ask them to drop the video in and tell you the path.
Also ask for a **short label for the recording** (e.g. `ICP`) — it becomes the `Video`
column so rows filter by source.

Then settle the working folder before creating anything. `VIDEO_REPURPOSER_HOME` defaults
to the current directory, which in a fresh session is wherever the user happened to open
it — dumping `input/`, `transcripts/` and `output/` into their home or Downloads folder is
a poor surprise. If `~/Claude Code/video-repurposer` exists, that is the established home
for this work; otherwise propose a folder and confirm before making directories.

Copy the video in rather than working in place, so the original stays untouched:

```bash
mkdir -p "$VIDEO_REPURPOSER_HOME/input" && cp "<their file>" "$VIDEO_REPURPOSER_HOME/input/"
```

### 2. Transcribe

```bash
python3 $S/transcribe.py input/<file>.mp4
```

Deepgram nova-3 with diarization and word timestamps. About a minute and ~$0.10 for 22
minutes. Produces `transcripts/<stem>.json` (word-level, for cut boundaries) and
`transcripts/<stem>.txt` (readable, for your editorial pass).

### 3. Decide the clips

**Read the whole `.txt` before choosing anything** — arguments that open early often pay
off late, and you cannot spot a self-contained idea from a fragment.

Write your reasoning to `analysis/<stem>_analysis.md` first: candidates, rough windows,
what you're rejecting and why. Then turn it into `output/content-plans/<stem>.json`.
`references/editorial.md` has the full method, the content-plan schema and the segment
types. Read it — the timestamp discipline there is what makes the cuts land on words
instead of mid-syllable.

Every clip needs these seven fields alongside the cut data, because they *are* the review
table and the tracker row. They are in the schema and the validator requires them — a plan
without them validates as incomplete rather than printing a table with blank columns:

| Field | What it is |
|---|---|
| `video_name` (top level) | Short label for the recording, e.g. `ICP`. The tracker's `Video` column. |
| `short_name` | 3-6 words. Numbered by source order it becomes `01 What is an ICP`. |
| `topic` | Subject area, a few words. |
| `summary` | The points actually discussed in the clip. |
| `score` | Publish-worthiness out of 10. |
| `score_reasoning` | Why that score — what is strong, what it lost marks for. |
| `hook_line` | The clip's opening line as the viewer hears it. Not the same as `recommended_hook`, which is advice about how to open. |

`score` (out of 10) and `confidence_score` (0-1) should agree directionally — a 9/10 clip
is not 0.4 confidence — but `score` is your publish recommendation and `confidence_score`
is how sure you are the boundaries are right. Don't compute one from the other.

### 4. Tighten, then validate

```bash
python3 $S/tighten_clips.py     output/content-plans/<stem>.json
python3 $S/fill_transcripts.py  output/content-plans/<stem>.json
python3 $S/validate_content_plan.py output/content-plans/<stem>.json
```

`tighten_clips` cuts pauses, filler words and stutters out of the keeps. `fill_transcripts`
rebuilds each clip's verbatim transcript from the word data, so the presenter's words can
never drift from what was actually said.

Fix every ERROR. **Read every cold-open warning rather than clearing it** — they're
warnings because judgment is required, not because they're safe to skip.

Two warnings are expected rather than wrong:

- **"opens mid-sentence on a lowercase word"** is often the *result* of obeying the
  cold-open rule. Trim a leading "So" and the clip now starts on the next word, which is
  lowercase in the transcript but is a perfectly good sentence opening. Check the actual
  first words of the rebuilt transcript; if it reads as a clean sentence, the cut is right.
- **A removal error** (`words still inside a keep_segment`) is never cosmetic. `keep_segments`
  are what actually cut — the gaps between them *are* the removals. `remove_segments` is
  documentation. If a removal still overlaps a keep, you recorded the intent but never
  applied it, and that material ships in the clip.

Clips also warn below **30 seconds** (`min_clip_duration_sec`). Short is often good — a
43-second template clip was the most useful in one set — but check it is a whole thought
and not a fragment.

### 5. QC, show the table, and STOP

```bash
python3 $S/review_table.py output/content-plans/<stem>.json --review
```

Show that table in the session and **wait for approval before rendering anything.** This
gate is the point of the whole workflow — it is far cheaper for the user to kill a clip
here than after it's been rendered and uploaded.

Score honestly out of 10. A low score with clear reasoning is more useful than a
flattering one, because the user is deciding what to spend their audience's attention on.
Expect to drop clips: a 22-minute session yielding 5 good clips out of 7 candidates is
healthy, not underperformance.

### 6. On approval, render the clips

```bash
python3 $S/render_clips.py output/content-plans/<stem>.json                # captioned MP4s
python3 $S/render_clips.py output/content-plans/<stem>.json --no-captions  # clean cut
python3 $S/render_clips.py output/content-plans/<stem>.json --clip clip-03 --clip clip-06
```

ffmpeg cuts each clip straight from its `keep_segments`. The plan is already a complete edit
decision list, so there is no app, no permissions and no export step. Files land in
`output/clips/` under the numbered clip name, so they match the tracker rows. Five clips
from a 22-minute source render in about 25 seconds, three in parallel.

Every render is checked after the fact: the output duration must match `duration_sec`
within 0.15s or the clip is reported FAIL instead of shipped. Cuts land within one frame of
the plan (verified against source frames), and a 12ms fade at every seam removes the click
of cutting mid-speech.

Render only what the user approved — `--clip` takes a subset. If you are rendering only
some clips for a test or preview, pick the highest-scoring ones: rendering the shortest is
quicker but leaves you unable to tell a pipeline problem from a clip that was always weak.

Captions are on by default (`render.captions` in settings, `--no-captions` to skip). They
burn in white Inter Bold on a dark box, styled from `branding` in settings. The cues are
built to read like professional captions: lines break on phrase boundaries and never end on
a weak word ("...common and"), one- and two-word orphans fold into a neighbour, and each
caption holds until the next begins so the box never blinks off between phrases. Whether to
caption is the user's call.

Every render is also finished: loudness-normalised in two passes (Zoom audio arrives near
-25 LUFS; renders land around -15, inside the -14 to -16 band social video plays at) and
faded in over 0.3s and out over 0.5s. All of it is tunable under `render` in settings.

**Read the QC report before handing over.** Every clip prints its duration against plan,
the finished file's loudness, and - when captioned - its cue count. Blinking captions,
orphans, lines ending on a weak word, quiet audio, near-clipping peaks or a duration
mismatch mark the clip CHECK with the reason. One frame per clip, taken mid-caption, lands
in `output/clips/qc/`: look at each one to confirm the caption sits clear of the slide
content and the camera box. That look is the whole visual check - seconds per clip, not
rounds of re-rendering. The first captioned clip took four render-and-inspect rounds to
tune; everything those rounds measured by hand is now in this report.

**Adjusting a cut.** If the user wants a clip to start later, end sooner or lose a line,
edit that clip's `keep_segments` in the plan, re-run step 4, and re-render just that clip
with `--clip`. It takes seconds, and the plan stays the single record of what is in every
clip - which is why cuts are never hand-edited in a video editor.

Then tell the user where the files are.

### 7. Ask for the Drive folder

Once they've uploaded the rendered files, ask for the Drive folder link. Read it with the
Drive connector's `search_files` using `parentId = '<folder id>'`.

If the folder isn't visible, it's almost always an **account mismatch** — the connector is
authenticated as one Google account and the folder lives in another. Ask them to share it
with the connector's account rather than guessing.

### 8. Emit the tracker rows

Build `links.json` mapping clip name → Drive URL, then:

```bash
python3 $S/review_table.py output/content-plans/<stem>.json --tsv --links links.json
```

Give the user the TSV in a code block to paste. Match Drive files to clips **by clip
name, never by title** — titles carry quote marks, which has silently broken the match
before.

## Naming — this is what makes the loop match up

`clip_name` = **two-digit number + short label**, numbered in **original video order**:
`01 What is an ICP`, `02 Why the right ICP converts 4x`, `04 ICP fill in the blanks`.

The same string is the rendered filename, the SRT filename and the sheet's `Clip name`.
That's what lets Drive files match tracker rows with no manual mapping. Numbering restarts
per recording. `naming.numbered_names()` is the single source of truth — every script
imports it rather than deriving names independently.

## The tracker sheet

"Zoom Video Clips", 11 columns, **`Hook` before `Score`**:

```
Video | Clip name | Topic | Summary | Hook | Score | Score reasoning | Drive link | Approved | Posted | Transcript
```

`Transcript` is the clip's verbatim words, rebuilt by `fill_transcripts` from the word
data — never retyped, so it cannot drift from what was actually said. It sits last so the
long text does not push the columns you scan into the distance.

`Video` is the short recording label. `Approved` and `Posted` default to `No`.
Getting this order wrong silently shifts three columns — it has happened.

## What makes a clip viable

These decide whether a clip exists at all, and they came from real failures.

**The cold-open test.** A clip is watched with nothing before it. It fails if it opens on
a connective ("So…", "There are multiple…", "Let's take an example of…") or names
something it never shows ("the other filters" — other than what?). Move the start, or drop
the clip. The validator flags these, but only it sees the words; whether a reference truly
dangles is your call.

**Running-example company operations are rarely standalone.** Teaching sessions lean on one
company throughout. Passages narrating *that company's own* operations — why they chose a
segment, how their launch went, what their numbers were — are usually connective tissue for
the lesson, not lessons. You cannot rescue those by stitching a context line onto the front;
that just adds a non-sequitur.

The test is not whether a company is named, it is **what survives if you delete the company.**
"We interviewed retailers and found three maturity stages, and the middle one converts
easiest because it already feels the pain" is a transferable lesson wearing a first-person
coat — the framework stands without the company. "We picked electronics in 2015 because our
consumers were ready" is a story about that company; delete it and nothing is left.

Keep the first kind and say in `score_reasoning` why you kept it. Cut the second. When it is
genuinely borderline, keep it, score it lower, and flag it in the review table — that is what
the approval gate is for. Also end a clip before any "so let me show you with an example"
that hands off into company-specific narration.

**Don't force a numbers-first hook.** Lead with a number when there is one. Most clips have
none, and the cold-open test is the only universal one.

**One idea per clip.** The audience is practitioners scrolling a feed; tight beats
complete. No fixed clip count — as many as the source genuinely supports. 5 minutes is a
hard cap, and `duration_sec` is the sum of `keep_segments` (finished runtime), never
`source_end - source_start`.

## Framing (screen-share recordings)

The slide fills the frame and the presenter is a small camera box in a corner.
**Always keep that camera box** — a face, even small, reads as a person talking rather
than a screen recording. **Never crop to vertical or 1:1**; it destroys the slide, which
carries the message. Renders keep the source's own dimensions, so nothing is scaled or
letterboxed.

## Reference files

- `references/editorial.md` — how to choose clips, the content-plan schema, segment types,
  timestamp discipline, confidence scoring. Read during step 3.
- `references/gotchas.md` — environment, Deepgram, editorial and rendering gotchas already
  paid for. Read before a new recording.
