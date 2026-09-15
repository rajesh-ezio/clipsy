# Editorial method — choosing and cutting clips

> **Field list note:** this reference describes the *cut* fields. Every clip additionally
> needs the seven review fields (`video_name`, `short_name`, `topic`, `summary`, `score`,
> `score_reasoning`, `hook_line`) listed in SKILL.md step 3 — they are required by the
> schema and they are what the review table and tracker row are built from.
>
> **Cut boundaries when there is no silence:** the guidance below says to land inside the
> gap between utterances. Plenty of speakers run sentences together with a 0.00s gap, which
> makes that impossible. Then cut exactly on the word edge and accept a harder cut — never
> pad into a neighbouring word to find silence, because that drags the dropped word back in.
>
> **`remove_segments` does not cut anything.** The gaps between `keep_segments` are the
> real removals; `remove_segments` records intent for a human reader. Express every removal
> as a gap in the keeps or it ships. The validator now errors when it catches this.

Read this during step 3 of SKILL.md. Two stages on purpose: decide *what is worth
publishing*, then decide *exactly where to cut*. Collapsing them produces clips
chosen for convenient boundaries instead of editorial merit.

---


## Content analysis

The editorial judgment step. You read the **entire** recording and decide what is
worth publishing — before anyone thinks about cut points.

Input: `transcripts/<stem>.txt` (the readable one).
Output: `analysis/<stem>_analysis.md`.

## Non-negotiable: read the whole thing first

Read the complete transcript before naming a single candidate clip. Do not start
proposing clips from the first strong passage you hit. An argument that begins at
04:00 may only pay off at 09:30, and the best standalone video is often the
combination. Judging locally produces clips that feel truncated.

## What you are looking for

Prioritize:

- strong insights
- useful frameworks
- actionable advice
- surprising or contrarian points
- clear explanations
- strong opinions
- interesting examples
- complete arguments
- content that stands alone without the viewer needing the original recording

Reject:

- repetition
- introductions and housekeeping. The exception is the line that names the topic: "Today,
  we're gonna talk about the power of customer stories" opens the first clip, not the bin.
- weak explanations
- rambling
- incomplete thoughts
- sections that depend heavily on previous context
- low-value conversation
- participant interruptions
- sections where the presenter is not making a useful point

## How many clips

**There is no target number.** Create as many as the source genuinely supports, and no
more. A 22-minute recording might yield six strong clips or two. Both are correct
answers if that is what the material holds.

Two failure modes, equally bad:

- **Padding** — promoting a mediocre passage to hit a count. If you find yourself
  writing a justification that amounts to "it's reasonably interesting", cut it.
- **Forcing coverage** — trying to account for every minute of source. Most recordings
  contain long stretches that should simply never be published. That is expected.

The test for every candidate: *would someone who has never seen the original
recording get complete value from this alone?* If it needs a setup the clip does not
contain, it fails — unless the missing setup is itself short enough to include, in
which case widen the window.

## Length

Each clip can run from genuinely-short up to a **hard maximum of 5 minutes (300s)**.
Let the idea decide the length. Do not stretch a 90-second point to look substantial,
and do not truncate a complete 4-minute argument to chase brevity.

If a passage only works at over 5 minutes, either find the tighter argument inside it
or drop it. Do not split one continuous argument across two clips to dodge the cap —
that produces two clips that each fail the standalone test.

## Speakers

The transcript is diarized: `PRESENTER` is the primary speaker, `OTHER_N` are
participants. The presenter is what gets published.

- A clip's substance must be presenter content.
- Note every `OTHER_N` span inside a candidate window — these get removed or flagged
  downstream, so record them even when brief.
- Watch for presenter answers that only make sense as a response to a question you are
  cutting. Either widen the clip to include the question as context, have the answer
  restate the question, or reject the passage. Never leave an orphaned answer.
- Check the header's speaker-time summary. If `PRESENTER` is not the dominant speaker,
  stop and flag it — the labelling may be wrong (see the transcription skill).

## Write the analysis

Write `analysis/<stem>_analysis.md`. This is a reasoning artifact for a human to
review and for clip-selection to act on — not the final deliverable.

```markdown
## Analysis: <stem>

Source: input/<file>  ·  Duration: MM:SS  ·  Speakers: PRESENTER 87%, OTHER_1 13%

## Overview
2-4 sentences: what this recording is, who the presenter is talking to, the overall
shape of the material and its general publishability.

## Candidate clips

### C1 — <working title>
- Rough window: MM:SS – MM:SS (~Ns)
- Core value point: the single idea a viewer takes away
- Why standalone: what makes this publishable on its own
- Target audience: who specifically
- Strength: strong | solid | marginal
- Other speakers inside window: MM:SS–MM:SS OTHER_1 (question about X)
- Problems to fix downstream: rambling at MM:SS, repeated point at MM:SS
- Notes: dependencies on earlier context, needed setup, anything clip-selection
  must resolve

### C2 — ...

## Rejected sections
- MM:SS–MM:SS — housekeeping and intros
- MM:SS–MM:SS — repeats the C1 point with a weaker example
(Cover the significant unused stretches, with a real reason for each. This is the
record of what was considered and passed over.)

## Recommendation
How many clips this recording genuinely supports and why. Call out marginal
candidates explicitly so a human can overrule.
```

Rough windows are fine here — exact boundaries are clip-selection's job. Get the
*editorial* call right and leave the frame-accuracy to the next step.

---


## Clip selection

Converts editorial candidates into the machine-readable deliverable. The judgment of
*what is worth publishing* is already made — your job is precision: exact boundaries,
exact removals, verbatim transcripts.

Inputs: `analysis/<stem>_analysis.md` and `transcripts/<stem>.json` (word-level).
Output: `output/content-plans/<stem>.json`, conforming to
`config/schema/content_plan.schema.json`.

## Work from the word-level JSON

The analysis gives rough windows. Snap them to real boundaries using the `words` array
in the transcript JSON, which carries a `start` and `end` for every word.

- Start on the **first word of a complete sentence**. Never mid-sentence, never mid-clause.
- End on the **last word of a completed thought**, not wherever the timer ran out.
- Take the gap: begin a few hundred ms before the first word's `start` and end a beat
  after the last word's `end`, so the clip does not clip the speech itself. Land inside
  the silence between utterances — check the neighbouring words' timestamps rather than
  padding by a fixed amount into whatever is there.
- Never cut off a word. If a boundary lands inside one, move to the word edge.

## Segment types

Every clip carries five span arrays, all in **seconds into the source video** (never
timeline-relative):

- `keep_segments` — presenter content to keep, in order. These are the spans that
  survive into the published video; the gaps between them are the cuts. At least one
  is required. Each takes a short `note` describing the kept line.
- `remove_segments` — spans **inside** the clip window to cut: rambling, repetition, a
  weak restatement, a false start. Give each a `reason`. Material trimmed off the
  *edges* of a clip — a trailing transition, a stumbling lead-in — is not a removal,
  it is simply not in the clip; record that in the plan's `rejected_sections` instead.
- `other_speaker_segments` — spans where an `OTHER_N` speaks. Record the `speaker`
  and a `note` on whether it is cut or deliberately retained as context.
- `silence_segments` — long pauses and dead air worth tightening. Find these as gaps
  between consecutive words in the JSON; roughly 1.5s+ of silence is worth recording.
- `filler_segments` — filler and low-value passages ("um", "uh", throat-clearing, a
  meandering aside). Include the offending `text`. The transcript keeps filler words
  deliberately so you can find them here.

`keep_segments` must tile the clip window minus everything removed. A span appearing in
both keep and remove is a contradiction — resolve it before writing the file.

**`duration_sec` is the sum of `keep_segments` — the runtime of the finished clip —
not `source_end - source_start`.** The source window is wider than the clip whenever
anything is cut from the middle, and dramatically wider when a clip stitches a short
setup line from early in the recording onto a passage from much later. The 300s cap
applies to the runtime a viewer experiences. `source_start` and `source_end` are just
the first keep's start and the last keep's end.

`keep_segments` are exactly the spans `render_clips.py` cuts from the source, in order,
which is why the frame of reference must stay source-relative.

## Hook and ending

- `recommended_hook` — how the clip should open so it earns attention in the first
  seconds. Prefer the presenter's own strongest line, pulled forward if the natural
  opening is slow. Say which words, and where they come from.
- `recommended_ending` — where and how it should land. A clip ending on a completed
  point beats one trailing into the next topic.

Both are editorial recommendations in prose, not a rewrite of the presenter's words.

## Transcript field

`transcript` is the **complete verbatim transcript of the proposed clip** — the
presenter's words from the `keep_segments`, concatenated in order, exactly as they
appear in the transcript.

**Never rewrite, tidy, paraphrase, or summarize the presenter's words.** No fixing
grammar, no smoothing phrasing. If a `keep_segment` contains filler, the filler stays
in this field — it is a record of what is in the clip, not the polished caption.

## Confidence score

0-1, how confident you are this clip should be published as-is:

- **0.85-1.0** — strong standalone idea, clean boundaries, no dependency on cut context
- **0.6-0.84** — solid, but needs the flagged removals to work, or the hook needs care
- **0.4-0.59** — marginal; a human should decide
- **below 0.4** — should not be in the plan; drop it instead

Do not inflate. A plan of three honest 0.9s is worth more than six 0.6s.

## Write, then validate

Write `output/content-plans/<stem>.json` with every field required by the schema:
top-level `video_id`, `source_video`, `source_duration_sec`, `transcript_source`,
`generated_at`, `presenter_label`, `clips`, `rejected_sections`; per clip all 17
fields. Carry `rejected_sections` over from the analysis so the plan records what was
passed over and why.

Then always run:

```bash
python3 scripts/validate_content_plan.py output/content-plans/<stem>.json
```

It checks the structure plus the rules a schema cannot express: `duration_sec` matches
the sum of `keep_segments`, the 300s cap, spans ordered and inside the clip window,
confidence in range, unique clip IDs, no two clips publishing the same source audio,
and the cold-open test on every clip's opening words.

Fix every ERROR. Warnings are judgment calls — resolve them or say why you are leaving
them. Do not report the plan as done until validation passes.

## Report back

Give the user a short summary: how many clips, each with title, timestamp window,
duration and confidence, plus anything marginal they should overrule. The JSON is the
deliverable; the summary is how they decide whether to trust it.

## Two rules that decide whether a clip exists at all

**The cold-open test.** Play the first sentence in your head with nothing before it. If it
opens on a connective ("So", "And", "There are multiple", "Let's take an example of") or
names something the clip never shows ("the other filters", "as I mentioned"), it fails.
Move the start, or drop the clip. `validate_content_plan.py` flags these, but it only sees
the transcript — judgment about whether a reference actually dangles is yours.

**The topic-first test.** A story or experiment needs its topic stated first. "We did a AB
test where we had a product page…" leaves the viewer asking who, why and on what; opening on
"Customer stories are nothing but case studies…" and then the test made the same clip work.
Add the topic line (and who the "we" is) even if it comes from earlier in the recording, but
keep the keeps in time order — a reordered "story order" version was tested and rejected.

**Running-example company operations are never standalone.** Teaching sessions lean on one
company throughout. Passages about *that company's own* operations — segment choice, launch
story, internal numbers — are connective tissue for the lesson, not lessons themselves.
Do not try to rescue them by stitching a context line onto the front; that produces a
non-sequitur. Cut them entirely, and end a clip before any hand-off into one.
