#!/usr/bin/env python3
"""Check this machine can run the whole pipeline, and say exactly how to fix what it can't.

Run it first on a new machine, or whenever a step fails for a reason that looks
environmental. It never prints the API key, only whether one was found.

    python3 scripts/check_setup.py            # local checks
    python3 scripts/check_setup.py --online   # also confirm the Deepgram key is accepted
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import SKILL_HOME, WORKDIR, settings_path  # noqa: E402

FFMPEG_FIX = ("macOS: brew install ffmpeg  |  or: uv tool install static-ffmpeg, then symlink "
              "its ffmpeg/ffprobe into ~/.local/bin")
KEY_FIX = ("get a free key at https://console.deepgram.com, then:  "
           "printf '%s' 'YOUR_KEY' > ~/.deepgram_key && chmod 600 ~/.deepgram_key")

results = []


def check(ok, label, detail="", fix=""):
    results.append(ok)
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not ok and fix:
        print(f"        fix: {fix}")


def find_tool(name):
    found = shutil.which(name) or str(Path.home() / ".local/bin" / name)
    return found if Path(found).exists() else None


def deepgram_key():
    key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if key:
        return key, "$DEEPGRAM_API_KEY"
    path = Path.home() / ".deepgram_key"
    if path.exists() and path.read_text().strip():
        return path.read_text().strip(), "~/.deepgram_key"
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--online", action="store_true", help="confirm the Deepgram key with one API call")
    args = ap.parse_args()

    print(f"Skill:   {SKILL_HOME}")
    print(f"Workdir: {WORKDIR}  (set VIDEO_REPURPOSER_HOME to change)\n")

    check(sys.version_info >= (3, 9), "Python 3.9+", sys.version.split()[0],
          "install a newer python3")

    skills_root = Path.home() / ".claude" / "skills"
    check(SKILL_HOME.parent == skills_root, "installed where Claude Code finds skills",
          str(SKILL_HOME.parent),
          f"git clone <repo> {skills_root / 'video-repurposer'}")

    ffmpeg, ffprobe = find_tool("ffmpeg"), find_tool("ffprobe")
    check(bool(ffmpeg), "ffmpeg", ffmpeg or "not found", FFMPEG_FIX)
    check(bool(ffprobe), "ffprobe", ffprobe or "not found", FFMPEG_FIX)
    if ffmpeg:
        filters = subprocess.run([ffmpeg, "-hide_banner", "-filters"],
                                 capture_output=True, text=True).stdout
        encoders = subprocess.run([ffmpeg, "-hide_banner", "-encoders"],
                                  capture_output=True, text=True).stdout
        check(" subtitles " in filters, "ffmpeg has libass (burned-in captions)", "",
              "use a full build: " + FFMPEG_FIX)
        check(" loudnorm " in filters, "ffmpeg has loudnorm", "", FFMPEG_FIX)
        check("libx264" in encoders, "ffmpeg has libx264", "", "use a full build: " + FFMPEG_FIX)

    fonts = sorted(p.name for p in (SKILL_HOME / "assets" / "fonts").glob("*.otf"))
    check("Inter-Bold.otf" in fonts, "caption font (Inter Bold)", ", ".join(fonts) or "none",
          "re-clone the repo; assets/fonts/ is part of it")

    check(settings_path().exists(), "settings", str(settings_path()),
          "re-clone the repo; config/settings.json is part of it")

    key, source = deepgram_key()
    check(bool(key), "Deepgram API key", f"from {source}" if key else "not found", KEY_FIX)
    if key and args.online:
        req = urllib.request.Request("https://api.deepgram.com/v1/projects",
                                     headers={"Authorization": f"Token {key}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                check(r.status == 200, "Deepgram accepts the key", f"HTTP {r.status}")
        except urllib.error.HTTPError as e:
            check(False, "Deepgram accepts the key", f"HTTP {e.code}",
                  "the key was rejected - create a new one and replace ~/.deepgram_key")
        except urllib.error.URLError as e:
            check(False, "Deepgram reachable", str(e.reason), "check the network connection")

    try:
        WORKDIR.mkdir(parents=True, exist_ok=True)
        probe = WORKDIR / ".write_test"
        probe.write_text("")
        probe.unlink()
        check(True, "workdir writable")
    except OSError as e:
        check(False, "workdir writable", str(e), "set VIDEO_REPURPOSER_HOME to a folder you own")

    failed = results.count(False)
    print(f"\n{'Ready.' if not failed else f'{failed} problem(s) - fix them before running the pipeline.'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
