#!/usr/bin/env python3
"""A/B: Hedra Character-3 talking-head (premium engine) from the SAME keyframe+audio
as the Veo/Omnihuman tests, for a head-to-head. Direct Hedra API (api.hedra.com);
key from .env HEDRA_API_KEY (gitignored). Flow confirmed from hedra-api-starter + docs:
create asset -> upload -> POST /generations (Character-3) -> poll /status -> download_url.
Usage: _hedra_test.py [img] [audio] [out]
"""
import json
import os
import subprocess
import sys
import time

import requests

# Load HEDRA_API_KEY from .env (never hardcode the secret).
for _line in open(".env"):
    if _line.startswith("HEDRA_API_KEY="):
        os.environ["HEDRA_API_KEY"] = _line.split("=", 1)[1].strip()
        break

BASE = "https://api.hedra.com/web-app/public"
KEY = os.environ.get("HEDRA_API_KEY", "")
HEADERS = {"x-api-key": KEY}
CHAR3 = "d1dd37a3-e39a-4854-a298-6510289f9cf2"  # Character-3 model id (confirmed)

IMG = sys.argv[1] if len(sys.argv) > 1 else "logs/falprod_v2s055_4_studio.jpg"
AUD = sys.argv[2] if len(sys.argv) > 2 else "domain/projects/66c9483624ab/temp/audio_scene_34acebe7b968.mp3"
OUT = sys.argv[3] if len(sys.argv) > 3 else "logs/hedra_v2studio.mp4"
PROMPT = ("A woman speaks warmly and naturally to the camera, subtle natural head "
          "movement, gentle smile, photorealistic, soft natural light.")


def create_and_upload(path, atype):
    r = requests.post(f"{BASE}/assets", headers={**HEADERS, "Content-Type": "application/json"},
                      json={"name": os.path.basename(path), "type": atype}, timeout=30)
    r.raise_for_status()
    aid = r.json()["id"]
    with open(path, "rb") as f:
        up = requests.post(f"{BASE}/assets/{aid}/upload", headers=HEADERS,
                           files={"file": f}, timeout=180)
        up.raise_for_status()
    print(f"  uploaded {atype} -> asset {aid}", flush=True)
    return aid


def main():
    if not KEY:
        print("ABORT: HEDRA_API_KEY not set in .env", flush=True)
        return 2
    for p in (IMG, AUD):
        if not os.path.exists(p):
            print(f"ABORT missing: {p}", flush=True)
            return 2
    if os.path.exists(OUT):
        os.remove(OUT)
    print("=" * 70, flush=True)
    print(f"HEDRA Character-3 talking-head  keyframe={IMG}", flush=True)
    print(f"  audio={AUD}  out={OUT}", flush=True)
    print("=" * 70, flush=True)

    t0 = time.time()
    image_id = create_and_upload(IMG, "image")
    audio_id = create_and_upload(AUD, "audio")
    body = {
        "type": "video",
        "ai_model_id": CHAR3,
        "start_keyframe_id": image_id,
        "audio_id": audio_id,
        "generated_video_inputs": {
            "text_prompt": PROMPT,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        },
    }
    g = requests.post(f"{BASE}/generations", headers={**HEADERS, "Content-Type": "application/json"},
                      json=body, timeout=30)
    if g.status_code >= 400:
        print(f"GENERATION REJECT {g.status_code}: {g.text[:700]}", flush=True)
        return 3
    gid = g.json()["id"]
    print(f"  generation {gid} submitted; polling /status...", flush=True)

    url = None
    for i in range(150):  # up to ~12.5 min
        time.sleep(5)
        s = requests.get(f"{BASE}/generations/{gid}/status", headers=HEADERS, timeout=30)
        s.raise_for_status()
        st = s.json()
        status = st.get("status")
        if i % 6 == 0:
            print(f"  status={status} progress={st.get('progress')}", flush=True)
        if status == "complete":
            url = st.get("download_url") or st.get("url")
            break
        if status == "error":
            print(f"VERDICT: ❌ FAIL — error: {st.get('error_message')}", flush=True)
            return 4
    if not url:
        print("VERDICT: ❌ FAIL — timeout / no url", flush=True)
        return 4

    print(f"  complete; downloading ({(time.time() - t0) / 60:.1f} min)...", flush=True)
    v = requests.get(url, timeout=300)
    v.raise_for_status()
    with open(OUT, "wb") as f:
        f.write(v.content)

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
        print(f"VERDICT: ✅ PASS — {OUT} ({sz:.1f} MB, video+audio Character-3 talking-head)", flush=True)
        return 0
    print(f"VERDICT: ⚠️ PARTIAL — {OUT} ({sz:.1f} MB, v={has_v} a={has_a})", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
