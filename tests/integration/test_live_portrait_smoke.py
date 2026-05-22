"""LivePortrait performance-capture smoke (handoff §13).

Calls the existing ComfyUI pod's LivePortrait workflow with a synthetic
keyframe + a 2s driving video (a tiny generated mp4). Gated behind
COMFYUI_SERVER_URL.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import pytest

from config.settings import settings


HAS_COMFYUI = bool(getattr(settings, "comfyui_server_url", ""))

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not HAS_COMFYUI, reason="COMFYUI_SERVER_URL not set; LivePortrait smoke skipped"),
]


def _make_test_keyframe(path: str) -> None:
    """Tiny portrait-shaped keyframe."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (512, 512), (60, 60, 80))
    draw = ImageDraw.Draw(img)
    draw.ellipse((150, 130, 360, 380), fill=(220, 200, 180))
    draw.ellipse((210, 220, 235, 245), fill=(40, 30, 30))
    draw.ellipse((278, 220, 303, 245), fill=(40, 30, 30))
    img.save(path, "JPEG", quality=88)


def _make_test_driving_video(path: str, frames: int = 30, fps: int = 15) -> None:
    """Generate a deterministic mp4 with a small moving rectangle via ffmpeg."""
    # ffmpeg's testsrc2 gives a movement pattern with timestamps — sufficient
    # for LivePortrait to ingest as a driving signal.
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc2=size=256x256:rate={fps}:duration={frames/fps:.2f}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", path],
        check=True, capture_output=True, timeout=30,
    )


def test_live_portrait_pod_round_trip():
    """Pod accepts the workflow + returns a video file. Asserts shape, not quality."""
    from performance.live_portrait import generate_live_portrait_performance

    # Confirm ffmpeg is available — otherwise we can't make the driving video.
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        pytest.skip("ffmpeg not on PATH; cannot synth test driving video")

    with tempfile.TemporaryDirectory() as td:
        kf = os.path.join(td, "kf.jpg")
        driving = os.path.join(td, "driving.mp4")
        out = os.path.join(td, "out.mp4")
        _make_test_keyframe(kf)
        _make_test_driving_video(driving)

        result = generate_live_portrait_performance(
            keyframe_path=kf,
            driving_video_path=driving,
            output_mp4=out,
            duration_s=2.0,
            poll_timeout_s=120,  # tighter for smoke
        )
        # Acceptable outcomes:
        #   - result == out + file exists → pod is configured correctly
        #   - result is None → LivePortrait node not installed / pod busy
        # The test is informative, not a fail signal for missing node installs.
        if result is None:
            pytest.skip("LivePortrait returned None (node likely not installed on pod)")
        assert result == out
        assert os.path.exists(out)
        assert os.path.getsize(out) > 1024
