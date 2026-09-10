# Pipeline gotchas

Every item here cost real debugging time. Read before a new recording.

---

## Environment (one-time, already done on this machine)

| Need | Where it came from |
|---|---|
| `ffmpeg` + `ffprobe` | `uv tool install static-ffmpeg`, then symlink the `darwin_arm64` binaries into `~/.local/bin` as bare `ffmpeg`/`ffprobe`. No brew on this machine. |
| Deepgram key | `~/.deepgram_key`, mode 600. |
| `uv` | `~/.local/bin/uv`. Only used to install static-ffmpeg. |

- **System Python is 3.9.6.** No `Path.hardlink_to` (3.10+) — use `os.link`. No `dict[int, float]`
  annotations at runtime in scripts that must run on it.
- The repurposer scripts are **stdlib only** by design. Keep them that way; ffmpeg is only
  needed for rendering, not by the editorial pipeline.

---

## Transcription — Deepgram

`POST https://api.deepgram.com/v1/listen` with the **raw file bytes** as the body and
`Content-Type` set from the file's mimetype. Params that matter:

```
model=nova-3 diarize=true punctuate=true smart_format=true utterances=true filler_words=true
```

- `filler_words=true` is what preserves "um"/"uh" so they can be cut later. Without it
  Deepgram silently cleans them and you cannot find them.
- Response shape: `results.channels[0].alternatives[0].words[]` — each word has
  `punctuated_word`, `start`, `end`, `confidence`, `speaker`. Plus `results.utterances[]`,
  already grouped into speaker turns, which is what the readable `.txt` is built from.
- **Presenter = the speaker with the most total speaking time.** Reliable for this format.
- 38 MB / 22 min uploaded and returned in well under a minute. Cost ~$0.10.
- Smoke-test a key without spending: `GET /v1/projects`. To test the full param string
  cheaply, POST `{"url":"https://dpgr.am/spacewalk.wav"}` as JSON instead of file bytes.

---

## Editorial gotchas (all of these were real bugs)

- **`duration_sec` = sum of `keep_segments`, NOT `source_end - source_start`.** A clip that
  stitches a 7-second setup line from 00:42 onto a story at 04:46 has a 5:35 *window* but a
  1:39 *runtime*. The 300s cap applies to runtime. Getting this wrong falsely trips the cap.
- **Overlap detection must compare `keep_segments`, not clip windows.** Same stitched-clip
  reason: its window engulfs other clips while sharing no actual audio.
- **`remove_segments` = internal cuts only.** Material trimmed off a clip's *edges* isn't a
  removal, it's just not in the clip — record it in `rejected_sections`.
- **Never treat a repeat across a sentence boundary as a stutter.** "This is not ICP. ICP
  need to be razor sharp" → cutting the first "ICP" destroys the first sentence. Guard on
  the preceding word ending in `.?!`.
- **Clamp boundary padding to real silence.** Padding a cut outward by 0.15s can reach
  *across* a neighbouring word and pull a dropped stutter back in — into the video, not just
  the transcript. Clamp to the previous word's end / next word's start.
- **Hunt course artifacts before cutting.** Grep the transcript for: `watch the next part`,
  `another conversation`, `in this session`, `I just spoke`, `earlier`, `workbook`,
  `before I end`, `across this whole video`. Each one breaks standalone comprehension and
  several sat inside otherwise-perfect clips.
- **Verify seams after every re-cut.** Print the last ~7 words before and first ~9 after each
  seam. This caught orphan words bleeding across cuts ("...for Acme Corp. **I**").
- This presenter had **zero "um"/"uh"** — his filler is word stutters and "you know" / "kind
  of" / "sort of". Measure before assuming which filler a speaker actually uses.

## Clip viability rules (learned 2026-09-02, QC pass on the first 7 clips)

**1. The cold-open test. A clip must make sense from its first word.**
It is watched with nothing before it. Two failure modes, both fatal:
- *Connective openings* — "So…", "And…", "There are multiple…", "Let's take an example of…",
  "let me talk about…" all tell the viewer they arrived late.
- *Dangling references* — naming something the clip never showed. The killer example was
  clip-05 opening on "let me talk about some of the **other** filters" — other than what?
  Unrecoverable; the clip was dropped.

`validate_content_plan.py` now checks this automatically (`check_cold_open`) and warns on
lowercase openings, connectives, continuation phrases and dangling references. **Warnings,
not errors** — a soft "So…" can be acceptable (clip-04 opens that way and is fine). A
dangling reference almost never is. Read every warning; do not auto-suppress them.

**2. Running-example company operations are rarely a standalone clip.** (SKILL.md has the test:
what survives if you delete the company.)
A teaching session leans on one company throughout. Passages narrating *that company's own
operations* — why they chose a segment, how their launch went, what their numbers were — only
carry meaning inside the teaching thread. They cannot be rescued by stitching context onto
the front; that just adds a non-sequitur. Cut them, and cut before any "so let me show you
with an example" that hands off to one.

This is what killed clip-02 (the electronics-vs-apparel story) and what forced clip-06 to end
before its filled-in example. The generic template stands alone; the filled-in version does not.

**3. Do NOT force a numbers-first hook.**
Lead with a number when there is one, but most clips have none, and burying a number is not
by itself a defect. The only universal test is the cold-open test. (I marked clip-03 down for
this and was wrong — it is a fine clip.)

## Editorial decisions locked for this account

- Audience is **marketing folks**. One idea per clip; tight beats complete.
- **Keep the presenter's camera box (PIP) always.** Never crop or cover it.
- **Never crop to vertical/1:1** — it destroys the slide, which carries the message.
- **Pauses, filler words and stutters are all cut in the plan** (`remove_silences: true`).
  Pauses were once left for CapCut's silence removal, but drafts written as JSON never
  triggered it, so nobody removed them. CapCut has since been removed entirely.

---

## Rendering — ffmpeg (`render_clips.py`)

- **Fonts ship with the skill** in `assets/fonts/` (Inter, OFL-licensed) and reach libass via
  `fontsdir`. If Inter goes missing, libass silently substitutes another face: captions still
  render, in the wrong font. `-loglevel verbose` shows the `fontselect` line if the look drifts.
- **The SRT is written into a temp dir and named relatively.** Filtergraph escaping of paths
  containing spaces ("Claude Code") is more fragile than it is worth.
- **Seek to 2s before the first kept word** (`-ss` before `-i`) instead of decoding from zero.
- **Cuts land one frame (40ms at 25fps) after the plan**, consistently: trim rounds to the next
  frame boundary. Audio and video resync at every seam, so it never accumulates.
- **12ms fades at every seam** remove the click of cutting mid-speech.
- **Loudness is two-pass.** Measure the edit's audio first (audio only, about a second), then
  correct. Single-pass undershot to -16.2 LUFS; two-pass reached -15.5 on the ICP clip. Exactly
  -14 is out of reach when the recording's peaks rule out a clean linear gain.
- **libass `BorderStyle=3` paints the caption box with OutlineColour**, so outline and back
  colour are both set. Sizes are relative to libass's 288-line SRT canvas.
- **The caption length cap is checked after a word is appended**, so the breaker backs off to
  the last point that fits - otherwise one long word pushes a line to 51 characters and strands
  the next few words as an orphan.
- **Every render self-checks** - duration against plan, output loudness, caption blinks,
  orphans and dangling line-ends - and saves a mid-caption frame per clip in `output/clips/qc/`.

## CapCut — retired 2026-09-10

The skill once built CapCut drafts by writing CapCut's project JSON straight to disk. It was
removed once the renderer covered cuts, captions and loudness, and a cut can be adjusted by
editing the plan and re-rendering in seconds. CapCut has no API, its export needed macOS
Accessibility on the host app, and its automation hooks break on app updates. The bridge and
its notes remain in this repo's git history.
