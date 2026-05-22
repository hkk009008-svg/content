"""ArcFace identity gate for performance-capture output.

Performance engines (Act-One, LivePortrait, Viggle) can drift the character's
face away from the approved keyframe. This module samples one frame from
the generated take and scores it against the character's face anchor.

Returns:
  - The cosine similarity in [0, 1] on success.
  - None when scoring isn't possible (no anchor, no face detected, no
    ffmpeg/cv2 available). Callers should treat None as "gate inconclusive"
    and fall back to operator review, NOT auto-fail.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from typing import Optional

# Use the public IdentityValidator (not face_validator_gate._arcface_score —
# that's a private symbol and could change). Lazy-loaded singleton so we
# don't pay the ArcFace weight load per call.
try:
    from identity.validator import IdentityValidator
    _ID_VALIDATOR_AVAILABLE = True
except Exception:
    _ID_VALIDATOR_AVAILABLE = False

_VALIDATOR: Optional["IdentityValidator"] = None
_VALIDATOR_LOCK = threading.Lock()


# Threshold below which auto-approval is suppressed. Set conservatively —
# 0.7 is the IdentityValidator default "looks like the same person" floor.
DEFAULT_PERFORMANCE_FLOOR = 0.70


def _get_validator() -> Optional["IdentityValidator"]:
    global _VALIDATOR
    if not _ID_VALIDATOR_AVAILABLE:
        return None
    if _VALIDATOR is not None:
        return _VALIDATOR
    with _VALIDATOR_LOCK:
        if _VALIDATOR is None:
            try:
                _VALIDATOR = IdentityValidator()
            except Exception as e:
                print(f"[PerformanceGate] IdentityValidator init failed: {e}")
                return None
        return _VALIDATOR


def _arcface_score(frame_path: str, anchor_path: str) -> Optional[float]:
    """Score a single frame against the anchor. Wrapper around IdentityValidator."""
    v = _get_validator()
    if v is None:
        return None
    try:
        result = v.validate_image(frame_path, anchor_path, threshold=0.0)
        return float(result.overall_score)
    except Exception as e:
        print(f"[PerformanceGate] ArcFace score failed: {e}")
        return None


def _extract_sample_frame(video_path: str, dest_png: str) -> Optional[str]:
    """Extract a frame near 1s into `video_path` to `dest_png`. ffmpeg-first."""
    if not os.path.exists(video_path):
        return None
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "1.0", "-i", video_path,
             "-frames:v", "1", "-q:v", "2", dest_png],
            check=True, capture_output=True, timeout=30,
        )
        return dest_png if os.path.exists(dest_png) else None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def validate_performance_take(
    video_path: str,
    face_anchor: str,
    floor: float = DEFAULT_PERFORMANCE_FLOOR,
) -> Optional[float]:
    """Score a performance take against the character face anchor.

    Returns the ArcFace similarity in [0, 1] or None if the gate can't run.
    None should be treated as "inconclusive" — leave the auto-approve
    decision to the operator gate.
    """
    if not video_path or not os.path.exists(video_path):
        return None
    if not face_anchor or not os.path.exists(face_anchor):
        return None

    with tempfile.TemporaryDirectory() as td:
        frame_png = os.path.join(td, "sample.png")
        if not _extract_sample_frame(video_path, frame_png):
            return None
        return _arcface_score(frame_png, face_anchor)
