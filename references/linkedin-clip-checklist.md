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
user called a good first iteration - and review took it to 12. Week 2 (3h45) started at 15 chapter clips and shipped 14 after one
review round - one discarded (Zoom gallery only), eight re-opened, none rejected for content. Merge same-chapter clips when
the result reads as one lesson (01 + 02 personas, trimming overlap with the buying-committee
clip); drop repeats, thin Q&A and clips whose key line is misheard.

**15. Borrow the signpost line just before the cut.** When an opener is vague, the fix is
usually a few seconds earlier: the line where he announces the topic. Week 2 fixed four clips
this way - "So let's start with the industry stories", "So then let's spend some time on
LinkedIn", "And then the next important one is the review sites", and "I think all of you
should use LinkedIn as one of your primary distribution channels" in front of a clip that
opened "So then comes distribution". Then drop any connective left dangling after the
borrowed line ("So then comes distribution" went, straight to "So this is the framework").

**16. A story's setup line beats a clean mid-story start.** "Alright, so this is another
classical Girish" tells the viewer a story is coming; starting at "Girish was the founder of
Freshworks" was cut for its stutter and read as a vague start. Keep the setup, filler and all.

**17. The opener carries the topic in his own words - a pop-up can't.** A cold-calling Q&A
answer opened on "the best way to start was yesterday" with a question pop-up saying what it
was about; the user asked for his own line instead: "Call works amazingly well from India."
Pop-ups add context; they never replace a topic line.

**18. One clip, one thing its opener names.** A clip that stitched Q&A distribution tactics
onto the repurposing slide read as vague twice - the only line framing it as content
distribution came 18 minutes later. Don't move that line to the front (time order, check 5);
offer the choice. The user kept time order: the clip starts on the framing line and the
earlier half was dropped.

**19. The screen must be a slide that fits.** Drop a clip that is only the Zoom gallery
("presentation ended, just people tiles"), however good the answer. A slide whose title fights
the words (a cold-calling answer over "Cracking the LinkedIn game") gets `slide_cover` - the
title painted over and replaced with the clip's question, "Does cold calling work?".

**20. "We" is not automatically the running-example company.** Add a company pop-up only
where he names the company or the slide or context makes it certain. A "we had 150+ blogs"
clip got an Acme Commerce pop-up by inference, and the user removed it.

**Company pop-up wording follows what he says.** If he names the company ("let's do it for
Acme Commerce"), use the plain company pop-up: the company as the label, what it does as
the text. If he only says "we" and the user confirms which company that is, write it as
context: label "Context", text 'Here "we" refers to Acme Commerce, a B2B SaaS that lets
retailers launch their own online store.' Place it on his first company "we" - not a generic
"how do we repurpose the content".

**21. Caption fixes must land and must be true.**
- **One line each:** a fix that straddles a caption line break silently does nothing - 27 did
  in Week 2 until they were split into shorter pieces. Rebuild the cues and check no misheard
  word is left on screen.
- **Check the fact before "fixing" it:** "Oracle civil conference" was changed to "Oracle
  OpenWorld"; the stunt was at Siebel's conference ("civil" = Siebel). A wrong fix is worse
  than the mishearing.

**22. Numbering: match by timestamp, recheck after re-cuts.** The user's sheet comments can
be off by one ("02 start from 42:04" meant clip 03) - identify the clip by the timestamp and
say which reading you used. A re-cut that moves a clip's start past its neighbour renumbers
both: rename the untouched file, move the old one to the Trash, render the new number.

**23. Every company "we" gets context - and if unsure, ask.** Week 2 needed company boxes
added by hand on six clips. Three habits caused it:
- **Reading rule 20 ("don't infer") as "leave it out".** If you can't tell which company "we"
  is, ask the user before rendering - never silently skip the box.
- **Dropping the box because the company's logo is on the slide.** A logo doesn't tell a
  stranger what the company does, or that "we" means them.
- **Letting a topic box take the opening slot.** The company box comes first; a topic box
  ("Buying committee") that competes with it goes.

**24. Fewer boxes, each one earning its place.** Two boxes in a clip's first seconds compete.
The user removed a topic box from one clip, and a company box from a clip whose first line
already names the company and whose chart tells the story.

**25. When the picture fights the words, put a title card over it.**
- **A Q&A answer over a bare title slide:** hide the old title and centre the clip's question
  on the empty slide, in the slide's title colour, larger than a heading ("Does cold calling
  work?"). Left at the top, it looked like bullets were about to appear.
- **A borrowed opener line brings its slide with it:** cover that slide for that line only
  ("LinkedIn organic growth"), keeping the camera tile and the slide's accent bar. Check the
  picture every time you borrow a line.
- Pin the pop-ups that have to sit around the card (SKILL.md, step 6).

**26. Two slides are two topics - two clips, not one squeezed under the cap.** A PR clip
stopped halfway through the story-types slide and jumped to the next slide's how-to to stay
under 5 minutes. The fix: finish the slide in its own clip (5:25, approved long) and make the
how-to its own clip.

**27. A clip added after publication takes the next number.** The split-off PR clip became
15 (`append_after_existing`), so clips 12-14, their files and their sheet rows didn't move.

**28. Overlap means the same span of the recording, not the same subject.** Two clips overlap
when they use the same passage, or repeat the same story, example or number - clip 19 was
reaching into clip 05's span (1:28:27-1:32:29) and Week 3's clip 11 replayed 30 seconds of
clip 10. Two different passages are two clips even when the topic label matches: Week 2 names
the industry-stories pillar at 29:41 and goes deep on it at 42:04, thirteen minutes and one
slide later, which is how a class is taught. Compare source ranges and examples, never
headings. Judging by heading is how the CPC/CPM benchmark example got cut out of clip 25 -
the user: "its not overlap its different part of the long video". A pillar that arrives with
less substance than its neighbours is a sign the cut is wrong, not that the material is thin.

**29. Source timestamps in the clip name.** From Week 2 clip 15 on, a clip name carries the
range it came from - `16 How to discover topics (0.58.49-1.04.40)`, h.mm.ss because colons
can't go in filenames. Set the plan's `"name_timestamps"` to `true` for a whole recording, or
to a clip number to start there: clips already in the tracker and in Drive keep their names,
because renaming them orphans their rows and links.

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
