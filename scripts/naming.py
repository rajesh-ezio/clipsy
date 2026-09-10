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


def numbered_names(plan):
    """clip video_id -> "01 Short Name", numbered by where each clip starts in the source."""
    ordered = sorted(plan["clips"], key=lambda c: c["keep_segments"][0]["start"])
    return {c["video_id"]: slug(f"{i:02d} {c.get('short_name') or c['title']}")
            for i, c in enumerate(ordered, 1)}
