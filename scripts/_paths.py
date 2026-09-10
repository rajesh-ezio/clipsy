"""Path resolution so the scripts work from any directory.

Two roots, deliberately separate:

  SKILL_HOME  - where this skill lives. Holds config defaults, fonts and scripts.
                Read-only as far as a run is concerned.
  WORKDIR     - where THIS recording's data lives: input/, transcripts/, analysis/,
                output/. Defaults to the current directory, override with
                $VIDEO_REPURPOSER_HOME.

Settings resolve WORKDIR-first so a project can override the skill defaults (clip
caps, filler phrases, branding) without editing the installed skill.
"""
import os
from pathlib import Path

SKILL_HOME = Path(__file__).resolve().parent.parent
WORKDIR = Path(os.environ.get("VIDEO_REPURPOSER_HOME") or Path.cwd()).resolve()

INPUT_DIR = WORKDIR / "input"
TRANSCRIPTS_DIR = WORKDIR / "transcripts"
ANALYSIS_DIR = WORKDIR / "analysis"
PLANS_DIR = WORKDIR / "output" / "content-plans"
CAPTIONS_DIR = WORKDIR / "output" / "captions"


def settings_path() -> Path:
    local = WORKDIR / "config" / "settings.json"
    return local if local.exists() else SKILL_HOME / "config" / "settings.json"


def ensure_dirs():
    for d in (INPUT_DIR, TRANSCRIPTS_DIR, ANALYSIS_DIR, PLANS_DIR, CAPTIONS_DIR):
        d.mkdir(parents=True, exist_ok=True)
