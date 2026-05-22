"""Unit tests for performance/motion_gate.py.

The motion gate is fully testable offline — pure cv2/numpy math on two
videos. We synthesize two pairs of clips:
  1. Same motion (rectangle moving left→right) → high score
  2. Opposite motion (left→right vs right→left) → noticeably lower score

cv2 is the only requirement; the test skips cleanly when it's missing.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import pytest


# Skip if cv2 isn't installed (it's a runtime optional dep for the gate)
try:
    import cv2  # noqa: F401
    import numpy  # noqa: F401
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


pytestmark = pytest.mark.skipif(not HAS_CV2, reason="cv2/numpy missing; motion_gate skip-tests it too")


def _has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _make_motion_clip(path: str, direction: str = "right", fps: int = 25, duration: float = 1.5):
    """Synthesize a clip where a white rectangle slides across a dark background.

    direction='right': rect translates left→right
    direction='left':  rect translates right→left
    Both clips have the same magnitude of motion; only direction differs —
    so a direction-aware similarity should distinguish them.
    """
    width, height, size = 320, 180, 40
    nframes = int(fps * duration)
    out_dir = tempfile.mkdtemp(prefix="motion_test_")
    frame_paths = []

    import numpy as np
    for i in range(nframes):
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        if direction == "right":
            x = int((width - size) * (i / max(1, nframes - 1)))
        else:
            x = int((width - size) * (1 - i / max(1, nframes - 1)))
        y = (height - size) // 2
        canvas[y:y+size, x:x+size] = (255, 255, 255)
        fpath = os.path.join(out_dir, f"frame_{i:04d}.png")
        cv2.imwrite(fpath, canvas)
        frame_paths.append(fpath)

    # Encode to mp4 via ffmpeg
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps),
         "-i", os.path.join(out_dir, "frame_%04d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", path],
        check=True, capture_output=True, timeout=30,
    )

    # Clean up frame stills
    for p in frame_paths:
        try: os.remove(p)
        except OSError: pass
    try: os.rmdir(out_dir)
    except OSError: pass


def test_motion_gate_inconclusive_on_missing_file():
    """Missing files → None (the 'inconclusive' contract)."""
    from performance.motion_gate import score_motion_fidelity
    assert score_motion_fidelity("/nope_a.mp4", "/nope_b.mp4") is None


def test_motion_gate_needs_remotion_only_when_scored():
    """needs_remotion is False when the gate didn't run (score=None)."""
    from performance.motion_gate import needs_remotion
    assert needs_remotion(None) is False
    assert needs_remotion(0.30, floor_override=0.50) is True
    assert needs_remotion(0.80, floor_override=0.50) is False
    assert needs_remotion(0.50, floor_override=0.50) is False  # ==floor doesn't fail


def test_needs_remotion_portrait_above_floor_passes():
    """score ≥ portrait floor (0.42) → no re-motion needed."""
    from performance.motion_gate import needs_remotion
    assert needs_remotion(0.50, shot_type="portrait") is False


def test_needs_remotion_wide_below_floor_fails():
    """score < wide floor (0.65) → re-motion required."""
    from performance.motion_gate import needs_remotion
    assert needs_remotion(0.50, shot_type="wide") is True


def test_needs_remotion_landscape_always_passes():
    """landscape opts out of motion-gate entirely — any score, even 0.0, returns False."""
    from performance.motion_gate import needs_remotion
    assert needs_remotion(0.0, shot_type="landscape") is False
    assert needs_remotion(0.0, shot_type="landscape") is False  # deterministic


def test_needs_remotion_floor_override_beats_shot_type():
    """floor_override takes priority over shot_type, even when shot_type would opt out."""
    from performance.motion_gate import needs_remotion
    # landscape would normally opt out; override forces the comparison
    assert needs_remotion(0.30, shot_type="landscape", floor_override=0.5) is True


def test_needs_remotion_unknown_shot_type_opts_out():
    """Unknown shot types route through the None branch and never trigger re-motion.

    Keeps a typo'd shot_type from blocking a shot — per the audit note at
    motion_gate.py:207-211 (unknown/typo'd shot types treated same as opt-out).
    """
    from performance.motion_gate import needs_remotion
    assert needs_remotion(0.10, shot_type="xyzzy") is False


def test_motion_gate_matches_same_direction_above_opposite_direction():
    """Same-direction clips score higher than opposite-direction clips.

    Not asserting absolute values (those depend on ffmpeg's encoding noise),
    only the inequality: motion(right, right) > motion(right, left).
    This is the core behavioral guarantee — direction-aware scoring.
    """
    if not _has_ffmpeg():
        pytest.skip("ffmpeg not on PATH; cannot synthesize test clips")

    from performance.motion_gate import score_motion_fidelity

    with tempfile.TemporaryDirectory() as td:
        right1 = os.path.join(td, "right1.mp4")
        right2 = os.path.join(td, "right2.mp4")
        left = os.path.join(td, "left.mp4")
        _make_motion_clip(right1, direction="right")
        _make_motion_clip(right2, direction="right")
        _make_motion_clip(left, direction="left")

        same_score = score_motion_fidelity(right1, right2, num_pairs=4)
        opposite_score = score_motion_fidelity(right1, left, num_pairs=4)

        assert same_score is not None, "same-direction comparison should produce a score"
        assert opposite_score is not None, "opposite-direction comparison should produce a score"
        # Same-direction should beat opposite-direction. Margin can be small
        # because the histogram bins are coarse; a 0.05 gap is enough to
        # demonstrate the direction component is doing work.
        assert same_score > opposite_score + 0.05, (
            f"expected same > opposite + 0.05; got same={same_score:.3f} opp={opposite_score:.3f}"
        )
