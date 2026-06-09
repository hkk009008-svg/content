#!/usr/bin/env python3
"""Veo-visual + YOUR-voice: a Veo clip + your TTS line -> lip_sync OVERLAY (MuseTalk cascade:
sync-lipsync/v3 -> musetalk -> latentsync -> sync-lipsync/v2). Re-syncs the MOUTH region to
your TTS and muxes your fixed character voice onto Veo's superior video. Gives "Veo's look +
consistent voice". Usage: _musetalk_overlay_test.py [video] [audio] [out]
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lip_sync import lipsync_overlay

VIDEO = sys.argv[1] if len(sys.argv) > 1 else "logs/veo_v2studio_trim.mp4"
AUDIO = sys.argv[2] if len(sys.argv) > 2 else "domain/projects/66c9483624ab/temp/audio_scene_34acebe7b968.mp3"
OUT = sys.argv[3] if len(sys.argv) > 3 else "logs/veo_musetalk_v2studio.mp4"


def main():
    for p in (VIDEO, AUDIO):
        if not os.path.exists(p):
            print(f"ABORT missing: {p}", flush=True)
            return 2
    if os.path.exists(OUT):
        os.remove(OUT)
    print("=" * 70, flush=True)
    print(f"MuseTalk OVERLAY (Veo video + your TTS)  video={VIDEO}", flush=True)
    print(f"  audio={AUDIO}  out={OUT}", flush=True)
    print("=" * 70, flush=True)

    meta: dict = {}
    t0 = time.time()
    res = lipsync_overlay(VIDEO, AUDIO, OUT, settings=None, _cascade_out=meta)
    print(f"\nlipsync_overlay -> {res!r}", flush=True)
    print(f"engine_meta={meta}  ({(time.time() - t0) / 60:.1f} min)", flush=True)

    if res and os.path.exists(res):
        pr = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height:format=duration", "-of", "json", res],
            capture_output=True, text=True, timeout=30)
        probe = json.loads(pr.stdout or "{}")
        has_a = any(s.get("codec_type") == "audio" for s in probe.get("streams", []))
        has_v = any(s.get("codec_type") == "video" for s in probe.get("streams", []))
        sz = os.path.getsize(res) / 1024 / 1024
        print(f"ffprobe: {json.dumps(probe)}", flush=True)
        print("=" * 70, flush=True)
        eng = meta.get("cascade_metadata", {}).get("engine")
        if has_v and has_a:
            print(f"VERDICT: ✅ PASS — {res} ({sz:.1f} MB, video+audio, engine={eng})", flush=True)
            return 0
        print(f"VERDICT: ⚠️ PARTIAL — {res} ({sz:.1f} MB, v={has_v} a={has_a})", flush=True)
        return 1
    print("VERDICT: ❌ FAIL — no output (prereq blockers / engine errors above)", flush=True)
    return 4


if __name__ == "__main__":
    sys.exit(main())
