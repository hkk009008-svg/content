#!/usr/bin/env python
"""measure_cartesia_prosody.py — committed R-MEASURE instrument for the
sonic-2 -> sonic-3.5 decision.

WHY THIS EXISTS
    audio/dialogue.py pins ``model_id="sonic-2"`` deliberately: swapping to
    sonic-3.5 is a QUALITY question, and Korean prosody is product-critical
    for this program. Cartesia has scheduled sonic-2 for sunset 2026-10-20,
    so the swap is coming — but the repo's R-MEASURE rule says a number
    backing a GO/NO-GO must come from a COMMITTED instrument and land in a
    logs/ artifact. An ad-hoc REPL measurement does not count.

WHAT IT MEASURES (objective signals only)
    duration_s        ffprobe wall duration of the rendered speech
    wpm               words / (duration/60) — the same arithmetic
                      audio/dialogue.py:_pace_factor uses, reused not re-derived
    silence_ratio     fraction of the clip below a quiet threshold, via
                      ffmpeg silencedetect — a proxy for pause structure
    rms_dbfs / peak   loudness via ffmpeg volumedetect

WHAT IT DOES *NOT* MEASURE — and will not pretend to
    Naturalness, expressiveness, accent quality, and "which one sounds better
    in Korean" are HUMAN judgments. This script deliberately emits no
    composite "quality score", because a single number invites exactly the
    mistake this repo already made once: on 2026-07-18 a loudness proxy was
    used to call one engine less natural than another, and the human listener
    judged the opposite. The proxy was wrong. Numbers here are inputs to a
    listening decision, not a substitute for one.

SPEND
    4 Cartesia TTS calls (2 lines x 2 models), a few seconds of audio.
    Per-character billing on CARTESIA_API_KEY. Re-running re-spends: the
    adapter caches by output path, and this script writes to a fresh
    timestamped directory each run, so nothing is silently reused.

USAGE
    .venv/bin/python scripts/measure_cartesia_prosody.py
    .venv/bin/python scripts/measure_cartesia_prosody.py --dry-run   # no spend
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The measurement MUST go through the production adapter, not a private HTTP
# call — otherwise it measures a code path the product does not use.
from audio.dialogue import generate_cartesia, _probe_audio_duration  # noqa: E402

MODELS = ("sonic-2", "sonic-3.5")

# Short lines on purpose: enough speech to measure pace and pause structure,
# little enough to keep spend negligible.
SAMPLES = (
    {
        "id": "korean",
        "language": "ko",
        # ~14 syllables of ordinary declarative Korean.
        "text": "우리는 오늘 밤 강을 건너야 한다. 시간이 얼마 남지 않았어.",
        "words": 10,
        "why": "Korean prosody is the product-critical case (project memory).",
    },
    {
        "id": "english_control",
        "language": "en",
        "text": "We have to cross the river tonight. There is not much time left.",
        "words": 13,
        "why": "Control: isolates model change from language handling.",
    },
)

DEFAULT_VOICES = {
    # Korean: the project's OWN configured Cartesia voice, so the measurement
    # reflects what production would actually ship — not an arbitrary demo
    # voice. Source: domain/language_defaults.py "Korean" ->
    # cartesia_default_female_voice (Seoyun — Warm Guide), itself verified
    # against the live voices API on 2026-06-08.
    "ko": os.environ.get("CARTESIA_VOICE_KO",
                         "ce9ca2b6-2bed-4452-99bb-052e1ec0b534"),
    # English: language_defaults carries no Cartesia id for English (the
    # English lane routes to ElevenLabs), so the control uses a real English
    # voice pulled from GET /voices on 2026-08-01. It exists only to separate
    # "the model changed" from "Korean handling changed" — it is not a claim
    # about the English production path.
    "en": os.environ.get("CARTESIA_VOICE_EN",
                         "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"),
}


def _ffmpeg_stat(path: str) -> dict:
    """RMS/peak dBFS + silence ratio. Returns {} when unmeasurable — never a
    fabricated number."""
    out: dict = {}
    try:
        vol = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        ).stderr or ""
        m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", vol)
        p = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", vol)
        if m:
            out["rms_dbfs"] = float(m.group(1))
        if p:
            out["peak_dbfs"] = float(p.group(1))
    except Exception:
        pass
    try:
        sil = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", path,
             "-af", "silencedetect=noise=-35dB:d=0.15", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        ).stderr or ""
        total = sum(float(x) for x in re.findall(r"silence_duration:\s*(\d+(?:\.\d+)?)", sil))
        out["silence_total_s"] = round(total, 3)
    except Exception:
        pass
    return out


def measure_one(sample: dict, model_id: str, out_dir: str, dry_run: bool) -> dict:
    path = os.path.join(out_dir, f"{sample['id']}__{model_id}.wav")
    voice = DEFAULT_VOICES.get(sample["language"]) or ""
    row = {
        "sample": sample["id"],
        "language": sample["language"],
        "model_id": model_id,
        "words": sample["words"],
        "voice_id": voice or "(adapter default)",
    }
    if dry_run:
        row["status"] = "dry-run — no API call made"
        return row

    ok = generate_cartesia(
        text=sample["text"],
        voice_id=voice,
        output_path=path,
        language=sample["language"],
        model_id=model_id,
    )
    if not ok or not os.path.exists(path):
        # Honest failure. No number is better than an invented one.
        row["status"] = "FAILED — no audio produced; see stderr above"
        return row

    dur = _probe_audio_duration(path)
    row["status"] = "ok"
    row["duration_s"] = round(dur, 3)
    row["wpm"] = round(sample["words"] / (dur / 60.0), 1) if dur > 0 else None
    row.update(_ffmpeg_stat(path))
    if row.get("silence_total_s") is not None and dur > 0:
        row["silence_ratio"] = round(row["silence_total_s"] / dur, 3)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and exit without spending")
    args = ap.parse_args()

    if not args.dry_run and not os.environ.get("CARTESIA_API_KEY"):
        try:
            from config.settings import settings
            if not settings.cartesia_api_key:
                raise RuntimeError
        except Exception:
            print("measure_cartesia_prosody: no CARTESIA_API_KEY — refusing to "
                  "run. (Use --dry-run to see the plan without spending.)",
                  file=sys.stderr)
            return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs = os.path.join(root, "logs")
    os.makedirs(logs, exist_ok=True)
    audio_dir = tempfile.mkdtemp(prefix=f"cartesia-prosody-{stamp}-")

    calls = 0 if args.dry_run else len(SAMPLES) * len(MODELS)
    print(f"cartesia prosody measurement — {len(SAMPLES)} lines x {len(MODELS)} models "
          f"= {calls} API call(s)")
    print(f"audio -> {audio_dir}")

    rows = []
    for sample in SAMPLES:
        for model in MODELS:
            print(f"  {sample['id']:16s} {model}")
            rows.append(measure_one(sample, model, audio_dir, args.dry_run))

    artifact = {
        "instrument": "scripts/measure_cartesia_prosody.py",
        "measured_at": stamp,
        "why": "sonic-2 sunsets 2026-10-20; migration needs measured evidence "
               "(R-MEASURE), not a provider claim.",
        "api_calls_made": calls,
        "models": list(MODELS),
        "rows": rows,
        "not_measured": [
            "naturalness / expressiveness — a HUMAN judgment; deliberately no "
            "composite score is emitted (2026-07-18 precedent: a loudness proxy "
            "contradicted the human listener and the proxy was wrong)",
            "accent and pronunciation quality",
            "listener preference",
        ],
        "audio_dir": audio_dir,
    }
    out = os.path.join(logs, f"cartesia-prosody-{stamp}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, ensure_ascii=False)

    print(f"\nartifact -> {os.path.relpath(out, root)}")
    print(f"{'sample':18s}{'model':10s}{'dur_s':>8s}{'wpm':>8s}{'sil_ratio':>11s}{'rms_dbfs':>10s}")
    for r in rows:
        print(f"{r['sample']:18s}{r['model_id']:10s}"
              f"{str(r.get('duration_s','-')):>8s}{str(r.get('wpm','-')):>8s}"
              f"{str(r.get('silence_ratio','-')):>11s}{str(r.get('rms_dbfs','-')):>10s}")
    print("\nThese numbers do NOT decide the migration. Listen to the audio in "
          f"{audio_dir} before choosing a model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
