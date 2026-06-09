#!/usr/bin/env python3
"""VEO-only portrait re-check (Option A) — one-off, NOT committed.

Re-confirms VEO_NATIVE can produce a live 9:16 portrait clip after the full
preflight's VEO check was RAI-content-filter-blocked on the default keyframe.
Uses a DIFFERENT keyframe (a face VEO has generated before) since Vertex RAI is
content/identity-based. Pins VEO via video_fallbacks (no cascade) + PF-1
cascade_retry_limit=0 (single billed call). ~$0.40, or FREE if RAI blocks again.

PASS = generate_ai_video returns a clip AND ffprobe reports height > width.
"""
import json
import os
import subprocess
import sys
import tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

from cinema.context import PipelineContext           # noqa: E402
from phase_c_ffmpeg import generate_ai_video          # noqa: E402

_DEFAULT_KF = os.path.join(
    _REPO, "domain/projects/aa777d858e71/characters/char_1cff3b80a401/canonical.jpg"
)


def _dims(path: str):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        s = json.loads(r.stdout or "{}").get("streams", [{}])[0]
        return s.get("width"), s.get("height")
    except Exception:
        return None, None


def main() -> int:
    keyframe = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_KF
    if not os.path.exists(keyframe):
        print(f"ABORT: keyframe not found: {keyframe}")
        return 2

    print("=" * 64)
    print("VEO-ONLY PORTRAIT RE-CHECK (Option A)  —  9:16  (LIVE SPEND)")
    print("=" * 64)
    print(f"keyframe : {keyframe}")

    ctx = PipelineContext(global_settings={"aspect_ratio": "9:16", "cascade_retry_limit": 0})
    with tempfile.TemporaryDirectory(prefix="veo_recheck_") as wd:
        out_path = os.path.join(wd, "veo_recheck.mp4")
        try:
            out = generate_ai_video(
                image_path=keyframe,
                camera_motion="zoom_in_slow",
                target_api="VEO_NATIVE",
                output_mp4=out_path,
                shot_type="portrait",
                ctx=ctx,
                video_fallbacks=["VEO_NATIVE"],
            )
        except Exception as exc:  # noqa: BLE001
            print(f"VEO_RECHECK FAIL  exception: {exc!r}"[:200])
            return 1

        if out and os.path.exists(out):
            w, h = _dims(out)
            if w and h and h > w:
                print(f"VEO_RECHECK PASS  {w}x{h}")
                return 0
            print(f"VEO_RECHECK FAIL  wrong-orientation {w}x{h}")
            return 1
        print("VEO_RECHECK FAIL  generate_ai_video returned None (RAI block or API error)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
