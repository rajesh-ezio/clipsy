#!/usr/bin/env python3
"""Video -> transcript JSON + readable TXT, via Deepgram (word timestamps + diarization).

Usage:
    python3 scripts/transcribe.py input/my-video.mp4
    python3 scripts/transcribe.py                 # process every input/* video missing a transcript

Reads the API key from $DEEPGRAM_API_KEY, else ~/.deepgram_key (matching this
project's other ~/.<service>_key convention). No third-party packages required.
"""
import argparse
import json
import mimetypes
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (SKILL_HOME, WORKDIR, INPUT_DIR, TRANSCRIPTS_DIR, ANALYSIS_DIR,
                    PLANS_DIR, CAPTIONS_DIR, settings_path,
                    ensure_dirs)
PROJECT_ROOT = WORKDIR
SETTINGS_PATH = settings_path()


VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}


def load_settings():
    return json.loads(SETTINGS_PATH.read_text())


def load_api_key(settings):
    key = os.environ.get(settings["api_key_env"])
    if key:
        return key.strip()
    key_file = Path(settings["api_key_file"]).expanduser()
    if key_file.exists():
        return key_file.read_text().strip()
    raise SystemExit(
        f"No Deepgram API key found. Set ${settings['api_key_env']} or save one to {key_file}.\n"
        "Get a free key at https://deepgram.com/free-transcription"
    )


def call_deepgram(video_path: Path, api_key: str, settings: dict) -> dict:
    mime, _ = mimetypes.guess_type(str(video_path))
    mime = mime or "video/mp4"
    params = dict(settings["params"])
    params["model"] = settings["model"]
    query = "&".join(f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in params.items())
    url = f"https://api.deepgram.com/v1/listen?{query}"

    data = video_path.read_bytes()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Token {api_key}")
    req.add_header("Content-Type", mime)

    print(f"Uploading {video_path.name} ({len(data) / 1e6:.1f} MB) to Deepgram ({settings['model']})...")
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Deepgram error {e.code}: {e.read().decode(errors='replace')}")


def fmt_ts(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build_transcript(raw: dict, video_path: Path, settings: dict) -> dict:
    presenter_label = settings["presenter_label"]
    other_prefix = settings["other_speaker_label_prefix"]
    model = settings["transcription"]["model"]
    results = raw["results"]
    utterances = results.get("utterances")
    if not utterances:
        words = results["channels"][0]["alternatives"][0]["words"]
        raise SystemExit(
            "Deepgram returned no utterances (utterances=true should always produce them). "
            f"Got {len(words)} raw words instead — check the response manually."
        )

    duration_by_speaker: dict[int, float] = {}
    for u in utterances:
        spk = u.get("speaker", 0)
        duration_by_speaker[spk] = duration_by_speaker.get(spk, 0.0) + (u["end"] - u["start"])

    presenter_speaker = max(duration_by_speaker, key=duration_by_speaker.get)
    speaker_labels: dict[int, str] = {}
    other_n = 0
    for spk in sorted(duration_by_speaker, key=lambda s: -duration_by_speaker[s]):
        if spk == presenter_speaker:
            speaker_labels[spk] = presenter_label
        else:
            other_n += 1
            speaker_labels[spk] = f"{other_prefix}_{other_n}"

    out_utterances = []
    for u in utterances:
        spk = u.get("speaker", 0)
        out_utterances.append({
            "start": u["start"],
            "end": u["end"],
            "speaker_raw": spk,
            "speaker_label": speaker_labels[spk],
            "text": u["transcript"],
            "words": [
                {"word": w["punctuated_word"], "start": w["start"], "end": w["end"], "confidence": w.get("confidence")}
                for w in u.get("words", [])
            ],
        })

    all_words = results["channels"][0]["alternatives"][0]["words"]
    source_duration = max((w["end"] for w in all_words), default=0.0)

    return {
        "video": str(video_path.relative_to(PROJECT_ROOT)),
        "source_duration_sec": source_duration,
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "presenter_label": presenter_label,
        "speaker_seconds": {speaker_labels[s]: round(d, 2) for s, d in duration_by_speaker.items()},
        "speakers": {str(s): label for s, label in speaker_labels.items()},
        "utterances": out_utterances,
        "words": [
            {
                "word": w["punctuated_word"],
                "start": w["start"],
                "end": w["end"],
                "confidence": w.get("confidence"),
                "speaker_label": speaker_labels.get(w.get("speaker", 0), "UNKNOWN"),
            }
            for w in all_words
        ],
    }


def write_readable_txt(transcript: dict, out_path: Path):
    lines = [f"# {transcript['video']}  (duration {fmt_ts(transcript['source_duration_sec'])})", ""]
    lines.append("Speaker time: " + ", ".join(
        f"{label} {fmt_ts(secs)}" for label, secs in
        sorted(transcript["speaker_seconds"].items(), key=lambda kv: -kv[1])
    ))
    lines.append("")
    for u in transcript["utterances"]:
        lines.append(f"[{fmt_ts(u['start'])}–{fmt_ts(u['end'])}] {u['speaker_label']}: {u['text']}")
    out_path.write_text("\n".join(lines) + "\n")


def process(video_path: Path, settings: dict, api_key: str):
    stem = video_path.stem
    json_out = TRANSCRIPTS_DIR / f"{stem}.json"
    txt_out = TRANSCRIPTS_DIR / f"{stem}.txt"
    if json_out.exists():
        print(f"Skip {video_path.name}: {json_out} already exists.")
        return

    raw = call_deepgram(video_path, api_key, settings["transcription"])
    transcript = build_transcript(raw, video_path, settings)

    TRANSCRIPTS_DIR.mkdir(exist_ok=True)
    json_out.write_text(json.dumps(transcript, indent=2))
    write_readable_txt(transcript, txt_out)

    print(f"Wrote {json_out}")
    print(f"Wrote {txt_out}")
    print("Speaker breakdown:")
    for label, secs in sorted(transcript["speaker_seconds"].items(), key=lambda kv: -kv[1]):
        pct = 100 * secs / transcript["source_duration_sec"] if transcript["source_duration_sec"] else 0
        print(f"  {label}: {fmt_ts(secs)} ({pct:.0f}%)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", nargs="?", help="Path to a video file. Omit to process all of input/*.")
    args = parser.parse_args()

    ensure_dirs()
    settings = load_settings()
    api_key = load_api_key(settings["transcription"])

    if args.video:
        targets = [Path(args.video).resolve()]
    else:
        targets = sorted(p for p in INPUT_DIR.iterdir() if p.suffix.lower() in VIDEO_EXTS)
        if not targets:
            raise SystemExit(f"No video files found in {INPUT_DIR}")

    for video_path in targets:
        if not video_path.exists():
            raise SystemExit(f"Not found: {video_path}")
        process(video_path, settings, api_key)


if __name__ == "__main__":
    main()
