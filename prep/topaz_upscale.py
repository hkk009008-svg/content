"""Topaz Video AI (Astra) — local CLI wrapper.

HONEST CAVEAT
-------------
Topaz Video AI has no cloud REST API. The ONLY way to invoke it from a pipeline
is via the local `tvai-cli` binary that ships with the desktop license. That
means:

  1. You must own a Topaz Video AI license (commercial product).
  2. You must install Topaz Video AI on the machine that runs this pipeline.
  3. The `tvai-cli` (or `ffmpeg` with their custom filter plugin) must be on PATH.

If those aren't true, this module is a no-op. The pipeline will keep using
SeedVR2 for cloud video upscaling.

WHY IT'S WORTH IT ANYWAY
------------------------
Topaz Astra is the industry standard for final-master video upscaling — better
than SeedVR2 for the absolute hero pass. If you own it, integrate it. If you
don't, SeedVR2 covers ~95% of the perceptual quality at ~50% the cost.

WHAT YOU PROVIDE
----------------
Either:
  (a) Topaz Video AI installed locally + `tvai-cli` on PATH, or
  (b) ffmpeg with Topaz's filter library (`tvai_up`, `tvai_fi`) compiled in

WHAT THIS DOES
--------------
upscale_with_topaz(input_path, output_path, model='auto', scale=2) -> path|None
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


# Astra-class Topaz models — picked based on content type
_TOPAZ_MODEL_RECOMMENDATIONS = {
    "auto":              "prob-3",       # general-purpose (Proteus v3)
    "cinema":            "rhea-1",       # film grain preserved
    "vfx":               "iris-2",       # cgi / digital art
    "low_quality":       "thd-3",        # heavy artifact removal first
    "interview":         "gaia-cg-1",    # talking heads
    "stylized":          "artemis-3",    # animation / illustration
}


def _detect_cli() -> Optional[str]:
    """Return a usable Topaz CLI invocation form, or None.

    Tries (in order):
      1. tvai-cli on PATH
      2. ffmpeg with Topaz filter (the `tvai_up` filter is the indicator)
      3. Topaz's veai CLI (older naming)
    """
    for binary in ("tvai-cli", "veai", "veai-cli"):
        if shutil.which(binary):
            return binary
    # ffmpeg-with-topaz-filter — confirm via `ffmpeg -filters | grep tvai`
    ff = shutil.which("ffmpeg")
    if ff:
        try:
            out = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=5)
            if "tvai_up" in (out.stdout or ""):
                return ff
        except Exception:
            pass  # ffmpeg probe failed — Topaz filter not detected, return None
    return None


def upscale_with_topaz(
    input_path: str,
    output_path: str,
    model: str = "auto",
    scale: int = 2,
    target_fps: Optional[int] = None,
    target_resolution: Optional[str] = None,  # "4k" | "8k" — overrides scale
) -> Optional[str]:
    """Upscale a video using Topaz Video AI locally. Returns output_path on
    success, None on any failure (so the caller can fall back to SeedVR2).

    Args:
        input_path:        local source video
        output_path:       where to write the upscaled MP4
        model:             one of _TOPAZ_MODEL_RECOMMENDATIONS keys, OR a raw Topaz model name
        scale:             integer scale factor (2 or 4)
        target_fps:        optional frame-interpolation target (e.g., 60)
        target_resolution: optional "4k" | "8k" — if set, overrides scale
    """
    if not input_path or not os.path.exists(input_path):
        return None

    cli = _detect_cli()
    if not cli:
        print("[Topaz] tvai-cli not on PATH. Install Topaz Video AI (paid license required) "
              "or set up ffmpeg with the Topaz filter library. Falling back to cloud upscaler.")
        return None

    # Map friendly name → Topaz model id
    model_id = _TOPAZ_MODEL_RECOMMENDATIONS.get(model, model)

    # Build the command. The tvai-cli flag surface differs across Topaz Video
    # AI versions; we target the 4.x+ command shape and accept whatever errors
    # come back from older builds (caller falls through gracefully).
    if "tvai-cli" in cli or "veai" in cli:
        cmd = [cli, "upscale",
               "--input", input_path,
               "--output", output_path,
               "--model", model_id,
               "--scale", str(scale)]
        if target_resolution:
            cmd += ["--resolution", target_resolution]
        if target_fps:
            cmd += ["--fps", str(target_fps)]
    else:
        # ffmpeg-with-topaz-filter path
        filter_str = f"tvai_up=model={model_id}:scale={scale}"
        if target_fps:
            filter_str += f",tvai_fi=fps={target_fps}"
        cmd = [cli, "-y", "-i", input_path, "-vf", filter_str,
               "-c:v", "h264", "-crf", "16", "-preset", "slow",
               "-c:a", "copy", output_path]

    print(f"[Topaz] running: {' '.join(cmd[:4])} ... (model={model_id}, scale={scale}x)")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            print(f"[Topaz] exited with code {result.returncode}")
            if result.stderr:
                print(f"[Topaz] stderr: {result.stderr[:500]}")
            return None
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
            print(f"[Topaz] output missing or empty: {output_path}")
            return None
        print(f"[Topaz] ✅ upscaled → {output_path}")
        return output_path
    except subprocess.TimeoutExpired:
        print(f"[Topaz] timed out after 1 hour")
        return None
    except Exception as e:
        print(f"[Topaz] error: {e}")
        return None


def is_available() -> bool:
    """Cheap check for UI — does this host have Topaz Video AI installed?"""
    return _detect_cli() is not None
