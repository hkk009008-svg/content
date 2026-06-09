#!/usr/bin/env python3
"""Extract the inline video_bytes from a captured Veo operation dump + ffprobe it.
Lets us confirm the audio stream from the ALREADY-generated video (no re-spend)."""
import base64
import json
import os
import re
import subprocess
import sys

SRC = sys.argv[1]
OUT = "temp/veo_extracted.mp4"

text = open(SRC, "r", encoding="utf-8", errors="replace").read()
m = re.search(r'"video_bytes":\s*"([^"]+)"', text)
if not m:
    print("NO video_bytes found in dump")
    sys.exit(2)

s = m.group(1).replace("-", "+").replace("_", "/")  # urlsafe -> standard
s += "=" * (-len(s) % 4)                              # repad
raw = base64.b64decode(s)
os.makedirs("temp", exist_ok=True)
with open(OUT, "wb") as f:
    f.write(raw)
print(f"wrote {OUT}: {len(raw)} bytes ({len(raw)/1024/1024:.2f} MB)")
print(f"header: {raw[:16]!r}")

p = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries",
     "stream=codec_type,codec_name,sample_rate,channels,duration:format=duration,format_name",
     "-of", "json", OUT],
    capture_output=True, text=True, timeout=30,
)
if p.stderr.strip():
    print(f"ffprobe stderr: {p.stderr.strip()[:300]}")
pj = json.loads(p.stdout or "{}")
print(json.dumps(pj, indent=2))
audio = [s for s in pj.get("streams", []) if s.get("codec_type") == "audio"]
video = [s for s in pj.get("streams", []) if s.get("codec_type") == "video"]
print("=" * 70)
print(f"VIDEO streams: {len(video)}   AUDIO streams: {len(audio)}")
if video and audio:
    a = audio[0]
    print(f"VERDICT: PASS — real audio stream present "
          f"(codec={a.get('codec_name')}, {a.get('sample_rate')}Hz, {a.get('channels')}ch)")
elif video:
    print("VERDICT: FAIL — video but NO audio stream")
else:
    print("VERDICT: FAIL — no video stream parsed")
