#!/usr/bin/env python3
"""Diagnostic: WHY did Veo return an empty response? (cycle-17 audio-validation debug)

Replicates veo_native.generate_video()'s EXACT call (same model, image, config,
prompt) but DUMPS operation.error + response.rai_media_filtered_count/_reasons +
generated_videos + the full operation, instead of swallowing them into the generic
"empty response" branch. Identical behavioral params to the first failed run — the
only change is observability (not a behavioral variable), per systematic-debugging
Phase-1 evidence-gathering.

The first attempt completed in ~12s with an empty response (Veo bills filtered/
rejected results at ~$0), so this repeat is almost certainly ~free; it exists to
surface the real reason (RAI policy filter vs. operation error vs. param issue).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.genai import types
from veo_native import VeoNativeAPI, _build_generate_videos_config

REF_PHOTO = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/canonical.jpg"
PROMPT = (
    "Close-up of a woman looking directly at the camera and speaking warmly to the "
    'viewer. She clearly says aloud: "Hello. I have been waiting a long time to '
    'finally meet you." Soft natural key light, shallow depth of field, '
    "photorealistic, subtle natural head movement. Clear synchronized speech audio."
)


def _dump(label, obj):
    try:
        if hasattr(obj, "model_dump"):
            print(f"{label} (model_dump):\n{json.dumps(obj.model_dump(mode='json'), indent=2, default=str)}")
        else:
            print(f"{label}: {obj!r}")
    except Exception as e:  # noqa: BLE001
        print(f"{label}: <dump error {e!r}>  raw={obj!r}")


def main():
    assert os.path.exists(REF_PHOTO), f"REF_PHOTO missing: {REF_PHOTO}"
    api = VeoNativeAPI()
    if api._backend != "vertex":
        print(f"ABORT: backend={api._backend!r} (not vertex)")
        return 3

    start_image = types.Image.from_file(location=REF_PHOTO)
    # 4s = smallest duration VALID for image_to_video on veo-3.1-generate-001
    # (server: supported are [8,4,6]; 5s — our first attempt — is rejected).
    config = _build_generate_videos_config(
        generate_audio=True, duration="4s", resolution="720p", reference_images=None,
    )
    print("=" * 78)
    print("CONFIG SENT:")
    _dump("  config", config)
    print(f"MODEL: {api._model}")
    print("=" * 78)

    started = time.time()
    op = api.client.models.generate_videos(
        model=api._model, prompt=PROMPT, image=start_image, config=config,
    )
    print(f"operation submitted: {getattr(op, 'name', '<no name>')!r}")
    polls = 0
    while not op.done:
        if polls >= 120:
            print("TIMEOUT after 1200s")
            break
        time.sleep(10)
        polls += 1
        op = api.client.operations.get(op)
    elapsed = time.time() - started
    print(f"\nDONE={op.done}  elapsed={elapsed:.0f}s  polls={polls}")

    # The fields veo_native NEVER inspects:
    print("-" * 78)
    print(f"operation.error: {getattr(op, 'error', '<no attr>')!r}")
    resp = getattr(op, "response", None)
    result = getattr(op, "result", None)
    print(f"operation.response is None: {resp is None}")
    print(f"operation.result   is None: {result is None}")
    for name, r in (("response", resp), ("result", result)):
        if r is not None:
            print(f"--- {name}.rai_media_filtered_count:   {getattr(r, 'rai_media_filtered_count', '<none>')!r}")
            print(f"--- {name}.rai_media_filtered_reasons: {getattr(r, 'rai_media_filtered_reasons', '<none>')!r}")
            print(f"--- {name}.generated_videos:           {getattr(r, 'generated_videos', '<none>')!r}")
    print("-" * 78)
    _dump("FULL operation", op)

    # On success, download + ffprobe for a real audio stream (the actual goal).
    vids = getattr(resp, "generated_videos", None) or getattr(result, "generated_videos", None)
    if not vids:
        print("=" * 78)
        print(f"VERDICT: NO VIDEO — error={getattr(op, 'error', None)!r}")
        return 1

    import subprocess
    os.makedirs("temp", exist_ok=True)
    out = "temp/veo_audio_diagnostic.mp4"
    data = api.client.files.download(file=vids[0].video)
    with open(out, "wb") as f:
        f.write(data)
    size_mb = os.path.getsize(out) / (1024 * 1024)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,sample_rate,channels,duration:format=duration",
         "-of", "json", out],
        capture_output=True, text=True, timeout=30,
    )
    pj = json.loads(probe.stdout or "{}")
    print("=" * 78)
    print(f"DOWNLOADED: {out} ({size_mb:.1f} MB)")
    print(f"ffprobe:\n{json.dumps(pj, indent=2)}")
    audio = [s for s in pj.get("streams", []) if s.get("codec_type") == "audio"]
    video = [s for s in pj.get("streams", []) if s.get("codec_type") == "video"]
    print("=" * 78)
    if video and audio:
        print(f"VERDICT: PASS — video + REAL AUDIO stream "
              f"(audio codec={audio[0].get('codec_name')}, "
              f"{audio[0].get('sample_rate')}Hz, {audio[0].get('channels')}ch)")
        return 0
    if video and not audio:
        print("VERDICT: FAIL — video generated but NO audio stream "
              "(generate_audio=True yielded no audio).")
        return 2
    print("VERDICT: FAIL — no video stream in output.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
