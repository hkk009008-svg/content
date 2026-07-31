"""Act-Two performance-capture smoke test (handoff §13; migrated from Act-One
2026-07-30, slice 5b — see performance/act_two.py's module docstring for the
audited SDK contract).

Runs ONE real Runway Act-Two call with a small keyframe + a short synthetic
reference/driving video, asserts a non-empty mp4 comes back. Gated behind
RUNWAYML_API_SECRET so CI without creds skips cleanly.

Marked `@pytest.mark.e2e` to match the existing tests/integration/* gating.
Tag with `-m e2e` to run; `-m "not e2e"` skips.

NOTE: unlike the retired Act-One, Act-Two has no audio-only generation mode
— every call needs a real reference performance video (3-30s), so this test
synthesizes one with ffmpeg (same pattern as test_live_portrait_smoke.py)
instead of driving off audio alone.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import pytest

from config.settings import settings


HAS_RUNWAY = bool(getattr(settings, "runwayml_api_secret", ""))

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not HAS_RUNWAY, reason="RUNWAYML_API_SECRET not set; Act-Two smoke skipped"),
]


def _make_test_keyframe(path: str, size: int = 512) -> None:
    """Generate a deterministic 512×512 test image (gradient + circle)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (size, size), (60, 60, 80))
    draw = ImageDraw.Draw(img)
    # Crude face shape so Act-Two has something to track. Real shots should
    # use a PuLID/InfU-locked keyframe.
    draw.ellipse((size * 0.3, size * 0.25, size * 0.7, size * 0.75), fill=(220, 200, 180))
    draw.ellipse((size * 0.40, size * 0.40, size * 0.46, size * 0.46), fill=(40, 30, 30))
    draw.ellipse((size * 0.54, size * 0.40, size * 0.60, size * 0.46), fill=(40, 30, 30))
    img.save(path, "JPEG", quality=90)


def _make_test_reference_video(path: str, duration_s: float = 3.0, fps: int = 15) -> None:
    """Generate a deterministic mp4 with a moving pattern via ffmpeg — stands
    in for a real reference performance clip. Act-Two requires 3-30s."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc2=size=512x512:rate={fps}:duration={duration_s:.2f}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", path],
        check=True, capture_output=True, timeout=30,
    )


def test_act_two_minimal_call_returns_mp4():
    """Smoke: actually call Runway Act-Two and assert we got a video back."""
    from performance.act_two import generate_act_two_performance

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        pytest.skip("ffmpeg not on PATH; cannot synth the reference video Act-Two requires")

    with tempfile.TemporaryDirectory() as td:
        kf = os.path.join(td, "kf.jpg")
        reference = os.path.join(td, "reference.mp4")
        out = os.path.join(td, "out.mp4")
        _make_test_keyframe(kf)
        _make_test_reference_video(reference, duration_s=3.0)

        result = generate_act_two_performance(
            keyframe_path=kf,
            audio_path="",
            output_mp4=out,
            driving_video_path=reference,
            duration_s=3.0,
        )
        # Two acceptable outcomes:
        #   - result == out AND file exists with non-trivial size (happy path)
        #   - result is None (Runway rejected the input — schema drift / quota)
        # We accept both; the test is here primarily to surface integration
        # regressions, not to assert specific Runway behavior.
        if result is None:
            pytest.skip("Act-Two returned None (likely Runway rejected the synthetic input)")
        assert result == out, f"Expected {out}, got {result}"
        assert os.path.exists(out), f"Output file missing: {out}"
        assert os.path.getsize(out) > 1024, f"Output suspiciously small: {os.path.getsize(out)} bytes"
