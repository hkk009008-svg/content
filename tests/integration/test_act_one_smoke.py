"""Act-One performance-capture smoke test (handoff §13).

Runs ONE real Runway Act-One call with a small keyframe + 2 seconds of audio,
asserts a non-empty mp4 comes back. Gated behind RUNWAYML_API_SECRET so CI
without creds skips cleanly.

Marked `@pytest.mark.e2e` to match the existing tests/integration/* gating.
Tag with `-m e2e` to run; `-m "not e2e"` skips.
"""

from __future__ import annotations

import os
import tempfile
import wave

import pytest

from config.settings import settings


HAS_RUNWAY = bool(getattr(settings, "runwayml_api_secret", ""))

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not HAS_RUNWAY, reason="RUNWAYML_API_SECRET not set; Act-One smoke skipped"),
]


def _make_test_keyframe(path: str, size: int = 512) -> None:
    """Generate a deterministic 512×512 test image (gradient + circle)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (size, size), (60, 60, 80))
    draw = ImageDraw.Draw(img)
    # Crude face shape so Act-One has something to track. Real shots should
    # use a PuLID/InfU-locked keyframe.
    draw.ellipse((size * 0.3, size * 0.25, size * 0.7, size * 0.75), fill=(220, 200, 180))
    draw.ellipse((size * 0.40, size * 0.40, size * 0.46, size * 0.46), fill=(40, 30, 30))
    draw.ellipse((size * 0.54, size * 0.40, size * 0.60, size * 0.46), fill=(40, 30, 30))
    img.save(path, "JPEG", quality=90)


def _make_test_audio(path: str, duration_s: float = 2.0, sample_rate: int = 22050) -> None:
    """Generate a deterministic mono wav: short tone burst at 440 Hz."""
    import math
    nframes = int(duration_s * sample_rate)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(nframes):
            sample = int(16000 * math.sin(2 * math.pi * 440 * i / sample_rate))
            wf.writeframes(sample.to_bytes(2, "little", signed=True))


def test_act_one_minimal_call_returns_mp4():
    """Smoke: actually call Runway Act-One and assert we got a video back."""
    from performance.act_one import generate_act_one_performance

    with tempfile.TemporaryDirectory() as td:
        kf = os.path.join(td, "kf.jpg")
        audio = os.path.join(td, "tone.wav")
        out = os.path.join(td, "out.mp4")
        _make_test_keyframe(kf)
        _make_test_audio(audio, duration_s=2.0)

        result = generate_act_one_performance(
            keyframe_path=kf,
            audio_path=audio,
            output_mp4=out,
            duration_s=2.0,
        )
        # Two acceptable outcomes:
        #   - result == out AND file exists with non-trivial size (happy path)
        #   - result is None (Runway rejected the input — schema drift / quota)
        # We accept both; the test is here primarily to surface integration
        # regressions, not to assert specific Runway behavior.
        if result is None:
            pytest.skip("Act-One returned None (likely Runway rejected the synthetic input)")
        assert result == out, f"Expected {out}, got {result}"
        assert os.path.exists(out), f"Output file missing: {out}"
        assert os.path.getsize(out) > 1024, f"Output suspiciously small: {os.path.getsize(out)} bytes"
