#!/usr/bin/env python3
"""Isolated Veo native-audio confirmation — direct generate_video() call, no pipeline.

Operator live-validation of the Veo native-audio path (cycle-17). The director's
config-threading fix (8846134 + f6d6995) made veo_native.generate_video() actually
thread generate_audio/duration/resolution into GenerateVideosConfig. This script
confirms — with a single real Veo call (~$0.30, 5s/720p) — that an actual synced
audio track comes out. It SIDESTEPS the pipeline + the headless plan-review gate
(§B) entirely: one VeoNativeAPI().generate_video(..., generate_audio=True) call,
then ffprobe the output for a real audio stream.

Guard: aborts (no spend) unless the client lands on the Vertex backend, since
generate_audio is silently ignored on the Gemini fallback (no audio possible).

Verdict: PASS iff the output file exists AND ffprobe reports an audio stream.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from veo_native import VeoNativeAPI

# Existing canonical face (portrait) — start frame for an image-to-video talking-head.
REF_PHOTO = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/canonical.jpg"
OUTPUT = "temp/veo_isolated_audio_check.mp4"

PROMPT = (
    "Close-up of a woman looking directly at the camera and speaking warmly to the "
    'viewer. She clearly says aloud: "Hello. I have been waiting a long time to '
    'finally meet you." Soft natural key light, shallow depth of field, '
    "photorealistic, subtle natural head movement. Clear synchronized speech audio."
)


def ffprobe_streams(path):
    """Full ffprobe stream dump for a media file, or an error tuple."""
    if not path or not os.path.exists(path):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,sample_rate,channels,duration:format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        return json.loads(out.stdout or "{}")
    except Exception as e:  # noqa: BLE001
        return {"ffprobe_error": str(e)[:200]}


def main():
    assert os.path.exists(REF_PHOTO), f"REF_PHOTO missing: {REF_PHOTO}"
    os.makedirs("temp", exist_ok=True)
    if os.path.exists(OUTPUT):
        os.remove(OUTPUT)  # ensure we measure THIS run, not a stale file

    started = time.time()
    print("=" * 78)
    print("VEO ISOLATED NATIVE-AUDIO CHECK")
    print(f"  ref_photo: {REF_PHOTO}")
    print(f"  output:    {OUTPUT}")
    print("=" * 78)

    api = VeoNativeAPI()
    # Hard guard: no spend unless audio is actually possible.
    if api._backend != "vertex":
        print(f"ABORT (no spend): backend={api._backend!r}, not 'vertex' — "
              f"generate_audio is ignored off Vertex, so this test would be meaningless.")
        return 3
    print(f"BACKEND: {api._backend}  MODEL: {api._model}  (audio-capable)")

    result = api.generate_video(
        image_path=REF_PHOTO,
        prompt=PROMPT,
        output_path=OUTPUT,
        duration="5s",        # Veo minimum — cheapest
        resolution="720p",    # cheapest
        generate_audio=True,  # THE thing under test
    )

    elapsed = (time.time() - started) / 60.0
    print("\n" + "=" * 78)
    print(f"generate_video returned: {result!r}   (elapsed {elapsed:.1f} min)")

    probe = ffprobe_streams(result)
    print(f"ffprobe: {json.dumps(probe, indent=2) if isinstance(probe, dict) else probe}")

    has_audio = False
    audio_codec = None
    if isinstance(probe, dict):
        for s in probe.get("streams", []):
            if s.get("codec_type") == "audio":
                has_audio = True
                audio_codec = s.get("codec_name")

    print("=" * 78)
    if result and os.path.exists(result) and has_audio:
        size_mb = os.path.getsize(result) / (1024 * 1024)
        print(f"VERDICT: PASS — real audio stream present (codec={audio_codec}), "
              f"file {size_mb:.1f} MB at {result}")
        return 0
    if result and os.path.exists(result) and not has_audio:
        print(f"VERDICT: FAIL — video generated but NO audio stream "
              f"(generate_audio=True did not yield audio).")
        return 1
    print(f"VERDICT: FAIL — no output produced (generation returned {result!r}; "
          f"check log above for RAI filter / API error).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
