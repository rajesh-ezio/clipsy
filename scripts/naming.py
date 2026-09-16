"""Clip naming - the one string that ties every artefact of a clip together.

numbered_names() gives each clip "NN Short name", numbered in ORIGINAL VIDEO ORDER. The same
string is the rendered filename, the SRT filename and the tracker's Clip name, which is what
lets a Drive file be matched to its sheet row without any manual mapping. Numbering restarts
per recording; the tracker's Video column disambiguates. Every script imports this rather than
deriving names itself - three scripts deriving them separately is how names once drifted.
"""


def slug(title: str) -> str:
    """Filesystem-safe but still readable: quotes dropped, ':' -> ' -', trailing dots stripped."""
    s = title.replace(":", " -").replace("/", "-").replace('"', "").replace("'", "")
    return " ".join(s.split()).rstrip(". ")


def source_range(clip):
    """"0.58.29-1.04.40" - where the clip starts and ends in the original recording.

    Colons are not usable in filenames, so h.mm.ss. The range is the first keep's start to
    the last keep's end: what you seek to in the source to see the clip in context.
    """
    hms = lambda t: f"{int(t // 3600)}.{int(t % 3600 // 60):02d}.{int(t % 60):02d}"
    a = clip.get("source_start", clip["keep_segments"][0]["start"])
    b = clip.get("source_end", clip["keep_segments"][-1]["end"])
    return f"{hms(a)}-{hms(b)}"


def numbered_names(plan):
    """clip video_id -> "01 Short Name", numbered by where each clip starts in the source.

    With plan-level "name_timestamps" the source range goes in the name too - "16 How to
    discover topics (0.58.29-1.04.40)". Set it to true for a whole recording, or to a clip
    number to start there (Week 2 got it from 15 on; 01-14 were already in the tracker and
    a rename there would orphan their rows and Drive files).
    """
    want_times = plan.get("name_timestamps")
    first = want_times if isinstance(want_times, int) and want_times is not True else 1
    # a clip added after the set was published takes the next number instead of shifting
    # everyone after it ("append_after_existing": true, or 2, 3... for later batches, so an
    # earlier addition keeps its number too) - filenames and sheet rows stay put
    ordered = sorted(plan["clips"], key=lambda c: (int(c.get("append_after_existing") or 0),
                                                   c["keep_segments"][0]["start"]))
    names = {}
    for i, c in enumerate(ordered, 1):
        name = f"{i:02d} {c.get('short_name') or c['title']}"
        if want_times and i >= first:
            name += f" ({source_range(c)})"
        names[c["video_id"]] = slug(name)
    return names
