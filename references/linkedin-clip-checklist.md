# The LinkedIn reader pass

Run this on every clip **before showing the review table**. Every rule here came from a clip
the user rejected or had re-cut.

**Why it exists:** each finished clip becomes the video under a LinkedIn post, and the post is
written from the clip's transcript. The viewer arrives cold, mid-scroll, often with the sound
off and reading the captions. So a clip is judged as a standalone piece a stranger reads, not
as an excerpt of a lecture they attended.

## The checks

**0. Start on the topic line.** When the presenter opens a new topic, he announces it a few
seconds before the content, either as a question ("How do we…?", "What is…?") or as a
signpost ("And then comes…", "Let me tell you…", "Now let's look at…"). Start the clip on
that line, even when it begins with "And" or a lowercase word.

- **Why:** it's the only place a LinkedIn viewer learns the topic. The Topic column in the
  sheet is visible to the user, not to the viewer. Only what's in the video reaches them.
- **Where it usually is:** most fixes were just a few seconds before the old cut.
- **Help from the validator:** it points at the nearest topic line within 25 s before each
  clip's start.

**The session's opening line counts.** "Today, we're gonna talk about the power of customer
stories" is the presenter naming the first clip's topic, and it's usually the best opening that
clip can have. Don't reject it with the "Hi everyone" housekeeping around it. Customer marketing
01 started at 00:11 on "Customer stories are nothing but case studies…" until the user moved it
to 00:05. His words: "he literally says what the clip is going to be."

The Events marketing re-cuts that taught it:

| Clip | Old start | New start (seconds earlier) |
|---|---|---|
| 04 Book meetings before the event | "It all starts with the pre event." | "How do we maximize the sponsorship?" |
| 06 The post-event follow-up | "What would typically happen is everyone will have fun." | "And then comes post event." |
| 07 The 3 pillars of an event | "I was part of the team who hosted…" | "Let me tell my experience of…" |
| 08 Unstick stalled deals | "We can also do events to accelerate your pipeline." | "And then comes the next one." |

**1. One post angle.** Write one line saying what a post built on this transcript would
teach: a framework, a number, a mistake or a repeatable tactic. If you can't, drop or re-cut
the clip. Lists of tactics and rambling passages fail this even when they're on topic. (Events
"A booth alone is useless" passed the score bar but failed here.)

**2. The first sentence names the topic.** After the first sentence, a stranger must be able
to say what the clip is about. A story, experiment or example comes after the topic, never
first.

- Before: "We did a AB test where we had a product page, which didn't really had any customer
  story." The reader asks who ran it, why, and on what.
- After: "Customer stories are nothing but case studies in a very simple term. Customer
  stories is one of the key tactics which most of the companies don't really unlock the
  maximum value of it." Then the test.

**3. Cut preamble that points at something unseen.** Start a few words later, on the idea
itself. A lowercase first word is fine when it reads as a clean sentence.

- Before: "The biggest learning from the Salesforce video is making your customer the hero."
  The reader asks what learning, and why Salesforce.
- After: "making your customer the hero or the heroine. So what essentially end up happening
  when you build a customer story is…"

**4. Every story says who, why and on what.** Keep the one line that says who "we" are and
who the customer is, even for the running-example company: "Acme Commerce is a
ecommerce platform, which can be used by brands to set up their own online store" and "a
customer story of a restaurant chain". The running-example rule cuts narration of that company's
*operations*; it doesn't cut the one line that makes the story make sense.

**5. Pull context from earlier, but keep time order.** A clip may reach back minutes for its
topic line (clip 01's opener comes from 00:11, and its test starts at 00:56). The pieces still
play in source order. A reordered "story order" version (result first, then context) was
tested and rejected: the slides jump back and forth and the joins sound wrong.

**6. Read the captions, not just the plan.** Misheard words appear on screen: "time value"
for TAM value, "customer.ai" for CustomFit, "$25,300", "put market" for mid-market, "fancy
cue" for crew. Cut the line or move the boundary to avoid it. Flag whatever remains in
`score_reasoning`.

**7. Every sentence earns its place.** After tightening, print the rebuilt transcript and
read it end to end once. Cut false starts ("service addressable market, serviceable…"),
repeated lines, asides and garbled bits.

**8. Take the title from the presenter's words** when he names the topic himself: "Today,
we're gonna talk about the power of customer stories" became *01 The power of customer
stories*.

**9. `hook_line` is the first line as heard in the finished clip,** after stutter removal, not
the raw transcript ("into into", "in in fact, flew flew" slipped through once).

**10. The opener is the most important line - rewrite it before showing the table.** Print
every clip's first ~30 words. Move the start to the strongest line nearby and trim filler in
front of it ("So let's start with", "this is the ___", "Right? Hey.", a rambling self-intro, a
misheard word). Openers the user approved: a definition that names the topic ("Personas are
nothing but people who buy your product"), the topic question ("How do we use the
jobs-to-be-done framework to craft the messaging for your own product?"), a called-out
mistake, a surprising fact ("Drift started as a web based live chat tool"), a bold claim
("The whole magic of SaaS is you can build from India for the world"). Keep the topic word in
the opener even when a punchier line is nearby - "typically, in a midsize company, there will be
multiple people in the buying committee" was praised *because* it says "buying committee".
Show the opening line as a column in the table.

**11. Cover the slide, not a fragment of it.** Screen-share slides build bullet by bullet. A
clip should start when the slide starts (first bullet) and end when it is complete - never
join a slide mid-build. Two re-cuts taught it: the JTBD clip had to run through every bullet
of "JTBD - a simple framework" (milkshake, two dimensions, how to discover jobs), and the
country clip jumped onto "New country launch strategy" at its third point until it was re-cut
to open on the first. Extract frames across the section to see where each slide starts and
ends before setting boundaries. If covering the whole slide runs past 5 minutes, trim asides
inside it - or ask; the user accepted 7:55 for a complete slide.

**12. Fix what the captions say.** Deepgram mishears jargon and names (PLG as "PLDR", jobs to
be done as "Jobstubrint", McDonald's as "my notes", designations as "resignations"). Read the
opener and the key lines of every clip and add `caption_fixes`; check each fix lands on a
caption line (a fix split across two lines won't apply). Use the corrected wording in the hook
and the transcripts file too - the user writes posts from it.

**13. Pop-ups give context where the viewer needs it.**
- **At the moment of need, not at 0:00 by default.** A company pop-up goes where he names the
  company or where "we"/"our" first refers to it (05 moved from 0:00 to "our restaurant
  solution page" at 0:59). If the clip never mentions it, don't add it (removed from 02).
- **Not only companies:** a named framework, "the example I showed you", "we were talking
  about X" (earlier in the session), a participant's example.
- **Skip it when the slide already says it** - check the frame.
- **Neutral third-person text,** no "the presenter's former company" / "where the presenter worked".
- **Never over slide content, never two at once** - run place_callouts.py; a cut before a
  pop-up moves it earlier in the clip, so check timings in clip time.

**14. Long recordings: one clip per chapter.** A 4-hour session first produced 31 candidates;
the user said "way too much". Merging each chapter's pieces in time order gave 14 - which the
user called a good first iteration - and review took it to 12. Merge same-chapter clips when
the result reads as one lesson (01 + 02 personas, trimming overlap with the buying-committee
clip); drop repeats, thin Q&A and clips whose key line is misheard.

## Selection defaults for this account

- **Score bar:** keep 8+ only; quality over quantity.
- **Merging:** merge only when one clip needs another for context, and never exceed 5
  minutes.
  - A merge must flow as one argument: TAM/SAM followed by volume vs value worked.
  - Two examples stitched together read as a list: the "two TAM formulas" merge was weaker
    for it.
- **Stories:** keep a war story if it teaches something; the post caption can carry the
  story.
- **Approval:** show the table before rendering, unless the user says to render straight
  into the folder.

## The worked example: Customer marketing 01

- **Before:** 1:12, opened on "We did a AB test…". The user's verdict: "a reader on LinkedIn
  sees this and has no context".
- **After:** 1:49, in time order:
  1. The topic: "Customer stories are nothing but case studies…"
  2. The A/B test.
  3. Who: "the one highlighted in purple is a customer story of a restaurant chain… one of our customers of
     Acme Commerce. Acme Commerce is a ecommerce platform…"
  4. The result: 22% more conversions, 100 vs 122.
  5. The close: social proof drives demos.
- **Title:** renamed "The power of customer stories". The user's verdict: "this is awesome".
