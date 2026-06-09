#!/usr/bin/env python3
"""Validate the RAI-free dialogue fallback: still photoreal keyframe + speech -> talking-head
via fal Omnihuman v1.5 (fal-ai/bytedance/omnihuman/v1.5). Called DIRECTLY, bypassing
lip_sync.lipsync_generation (which has a settings-shadowing crash bug + a dead Hedra id).
None of these fal engines is Veo, so Veo's RAI output filter never applies.
Usage: _lipsync_gen_test.py [img] [audio] [out]
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

# Load FAL_KEY from .env (fal_client reads it from the environment).
for line in open(".env"):
    if line.startswith("FAL_KEY="):
        os.environ["FAL_KEY"] = line.split("=", 1)[1].strip()
        break

import fal_client  # noqa: E402

IMG = sys.argv[1] if len(sys.argv) > 1 else "logs/falprod_v2s055_4_studio.jpg"
AUD = sys.argv[2] if len(sys.argv) > 2 else "domain/projects/66c9483624ab/temp/audio_scene_34acebe7b968.mp3"
OUT = sys.argv[3] if len(sys.argv) > 3 else "logs/lipsync_gen_v2studio.mp4"


def main():
    for p in (IMG, AUD):
        if not os.path.exists(p):
            print(f"ABORT missing: {p}", flush=True)
            return 2
    if os.path.exists(OUT):
        os.remove(OUT)
    print("=" * 70, flush=True)
    print(f"Omnihuman v1.5 talking-head (RAI-free)  keyframe={IMG}", flush=True)
    print(f"  audio={AUD}  out={OUT}", flush=True)
    print("=" * 70, flush=True)

    t0 = time.time()
    image_url = fal_client.upload_file(IMG)
    audio_url = fal_client.upload_file(AUD)
    print("uploaded image+audio to fal; calling fal-ai/bytedance/omnihuman/v1.5...", flush=True)
    result = fal_client.subscribe(
        "fal-ai/bytedance/omnihuman/v1.5",
        arguments={
            "image_url": image_url,
            "audio_url": audio_url,
            "resolution": "720p",
            "turbo_mode": False,
        },
        with_logs=True,
    )
    video_url = (result or {}).get("video", {}).get("url")
    print(f"omnihuman -> video_url={video_url}  ({(time.time() - t0) / 60:.1f} min)", flush=True)
    if not video_url:
        print(f"VERDICT: ❌ FAIL — no video url. result keys={list((result or {}).keys())}", flush=True)
        print(f"result(trunc): {json.dumps(result)[:600]}", flush=True)
        return 4

    urllib.request.urlretrieve(video_url, OUT)
    pr = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height:format=duration", "-of", "json", OUT],
        capture_output=True, text=True, timeout=30)
    probe = json.loads(pr.stdout or "{}")
    has_a = any(s.get("codec_type") == "audio" for s in probe.get("streams", []))
    has_v = any(s.get("codec_type") == "video" for s in probe.get("streams", []))
    sz = os.path.getsize(OUT) / 1024 / 1024
    print(f"ffprobe: {json.dumps(probe)}", flush=True)
    print("=" * 70, flush=True)
    if has_v and has_a:
        print(f"VERDICT: ✅ PASS — {OUT} ({sz:.1f} MB, video+audio talking-head, RAI-free)", flush=True)
        return 0
    print(f"VERDICT: ⚠️ PARTIAL — {OUT} ({sz:.1f} MB, v={has_v} a={has_a})", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
