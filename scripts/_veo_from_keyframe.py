#!/usr/bin/env python3
"""Step 3: Veo native-audio clip from a chosen clean keyframe.

Takes a finished max-tier keyframe (clean neck + A-tuned natural skin) and
animates it into an 8s talking-head with SYNCED NATIVE AUDIO (Veo 3.1, Vertex).
Identity rides the start frame (Bug #4: refs are mutually exclusive with image).
ffprobe-verifies video + audio. Usage: _veo_from_keyframe.py [keyframe] [out]
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from veo_native import VeoNativeAPI

KEYFRAME = sys.argv[1] if len(sys.argv) > 1 else "logs/max_clean_s191034308.jpg"
OUT = sys.argv[2] if len(sys.argv) > 2 else "logs/max_final_polished.mp4"

PROMPT = (
    "The woman looks directly at the camera and speaks warmly and naturally to the "
    'viewer. She clearly says aloud: "It took everything we had, but we finally '
    'made it work." Subtle natural head movement, blinking, gentle smile, '
    "photorealistic, soft natural key light, shallow depth of field. "
    "Clear synchronized speech audio."
)


def ffprobe_streams(path):
    if not path or not os.path.exists(path):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height,sample_rate,channels,duration:format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=30)
        return json.loads(out.stdout or "{}")
    except Exception as e:  # noqa: BLE001
        return {"ffprobe_error": str(e)[:200]}


def main():
    t0 = time.time()
    if not os.path.exists(KEYFRAME):
        print(f"ABORT: keyframe missing: {KEYFRAME}"); return 2
    if os.path.exists(OUT):
        os.remove(OUT)
    print("=" * 70, flush=True)
    print(f"VEO POLISHED CLIP  keyframe={KEYFRAME}  out={OUT}", flush=True)
    print("=" * 70, flush=True)

    api = VeoNativeAPI()
    if getattr(api, "_backend", None) != "vertex":
        print(f"ABORT: backend={api._backend!r} not vertex — no native audio."); return 3
    print(f"backend=vertex model={api._model}  8s/720p/audio=True", flush=True)

    # Veo's RAI output filter is stochastic on photorealistic talking-heads;
    # retry up to 3x (blocked generations are not charged).
    video = None
    for attempt in range(1, 4):
        print(f"--- attempt {attempt}/3 ---", flush=True)
        video = api.generate_video(
            image_path=KEYFRAME, prompt=PROMPT, output_path=OUT,
            duration="8s", resolution="720p", generate_audio=True,
        )
        if video and os.path.exists(video):
            break
        print(f"attempt {attempt}: no output (likely RAI filter); "
              f"{'retrying' if attempt < 3 else 'giving up'}", flush=True)
    print(f"generate_video -> {video!r}  ({(time.time()-t0)/60:.1f} min)", flush=True)

    probe = ffprobe_streams(video)
    print(f"ffprobe: {json.dumps(probe)}", flush=True)
    has_a = has_v = False
    if isinstance(probe, dict):
        for s in probe.get("streams", []):
            has_a = has_a or s.get("codec_type") == "audio"
            has_v = has_v or s.get("codec_type") == "video"
    print("=" * 70, flush=True)
    if video and os.path.exists(video) and has_v and has_a:
        print(f"VERDICT: ✅ PASS — {video} ({os.path.getsize(video)/1024/1024:.1f} MB, video+audio)", flush=True)
        return 0
    if video and os.path.exists(video) and has_v:
        print(f"VERDICT: ⚠️ PARTIAL — video but NO audio: {video}", flush=True); return 1
    print(f"VERDICT: ❌ FAIL — no usable output ({video!r})", flush=True); return 4


if __name__ == "__main__":
    sys.exit(main())
