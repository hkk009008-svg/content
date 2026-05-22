"""Motion fidelity gate for performance-capture output.

WHY THIS EXISTS
---------------
The ArcFace identity gate (identity_gate.py) catches WHO is in the shot —
did the face stay on-model? But it doesn't catch HOW they moved. A performance
take can score 0.95 ArcFace and still have the character standing motionless
while the driving video showed someone leaning in to speak.

This module compares dense optical flow between the driving video and the
final motion clip. High histogram correlation = the character moved like the
performance reference. Low correlation = the engine ignored the driving signal
and produced its own motion — exactly the failure mode that erodes the value
of the whole performance-capture stage.

ALGORITHM (deliberately simple)
-------------------------------
1. Sample ``num_samples`` frame-pairs from each video at uniform intervals.
2. Compute Farneback dense optical flow on each pair within each clip.
3. Bin flow magnitude+direction into a 2D histogram per clip.
4. Cosine similarity between the per-clip aggregate histograms → score in [0, 1].

This is rotation/position-invariant: the character "leaning in" earns the
same flow signature regardless of where they're standing in frame.

RETURN CONTRACT
---------------
Returns float in [0, 1] on success, None when the gate can't run (missing
cv2, missing video, no shared duration). None means "inconclusive" — callers
should NOT auto-fail; leave the decision to the operator's PERFORMANCE_REVIEW gate.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional


# Default suppression threshold — below this we recommend the operator reject.
# Set conservatively. Real cinema review will surface 0.55 as "obvious", 0.75
# as "looks right", 0.9+ as "almost matches frame-for-frame". 0.50 = "moved
# like the reference at least in direction and amplitude, not exact timing".
DEFAULT_MOTION_FLOOR = 0.50

# Sampling defaults — tune via env var if needed.
_NUM_SAMPLE_PAIRS = int(os.environ.get("MOTION_GATE_SAMPLES", "8"))
_FLOW_HIST_BINS = 12  # magnitude × direction → 12 bins each (144 total)


def _try_imports():
    """Probe optional deps; return (cv2_module, numpy_module) or (None, None)."""
    try:
        import cv2
        import numpy as np
        return cv2, np
    except Exception:
        return None, None


def _sample_frame_pairs(video_path: str, num_pairs: int, cv2_mod, np_mod):
    """Sample ``num_pairs`` consecutive frame pairs uniformly across the clip.

    Returns a list of (prev_gray, next_gray) numpy arrays. Empty list on any
    failure. Frame pairs are needed for dense flow computation — each pair
    yields one flow field.
    """
    pairs = []
    cap = cv2_mod.VideoCapture(video_path)
    try:
        total = int(cap.get(cv2_mod.CAP_PROP_FRAME_COUNT) or 0)
        if total < 2:
            return []
        # Choose sample frame indices, leaving room for the second-of-pair.
        step = max(1, (total - 1) // max(1, num_pairs))
        indices = [min(i * step, total - 2) for i in range(num_pairs)]
        for idx in indices:
            cap.set(cv2_mod.CAP_PROP_POS_FRAMES, idx)
            ok1, frame1 = cap.read()
            ok2, frame2 = cap.read()
            if not (ok1 and ok2):
                continue
            g1 = cv2_mod.cvtColor(frame1, cv2_mod.COLOR_BGR2GRAY)
            g2 = cv2_mod.cvtColor(frame2, cv2_mod.COLOR_BGR2GRAY)
            # Normalize to a common resolution so flow magnitude is comparable
            # across clips that were rendered at different sizes.
            g1 = cv2_mod.resize(g1, (320, 180), interpolation=cv2_mod.INTER_AREA)
            g2 = cv2_mod.resize(g2, (320, 180), interpolation=cv2_mod.INTER_AREA)
            pairs.append((g1, g2))
    finally:
        cap.release()
    return pairs


def _flow_histogram(pairs, cv2_mod, np_mod):
    """Aggregate optical-flow histogram across all sampled frame-pairs.

    Each pair produces a dense flow field (h×w×2). We bin (magnitude, direction)
    pairs into a 2D histogram, sum across all pairs, L1-normalize. The result
    is a fixed-length vector summarizing "how the clip moved overall".
    """
    if not pairs:
        return None
    hist_total = np_mod.zeros((_FLOW_HIST_BINS, _FLOW_HIST_BINS), dtype=np_mod.float64)
    for g1, g2 in pairs:
        flow = cv2_mod.calcOpticalFlowFarneback(
            g1, g2, None,
            pyr_scale=0.5, levels=3, winsize=15, iterations=3,
            poly_n=5, poly_sigma=1.2, flags=0,
        )
        # flow[..., 0] = dx, flow[..., 1] = dy
        mag, ang = cv2_mod.cartToPolar(flow[..., 0], flow[..., 1])
        # Clip magnitude so noise pixels don't dominate the histogram.
        mag = np_mod.clip(mag, 0.0, 8.0)
        # Bin (magnitude, direction) → 2D histogram
        h2d, _, _ = np_mod.histogram2d(
            mag.flatten(), ang.flatten(),
            bins=[_FLOW_HIST_BINS, _FLOW_HIST_BINS],
            range=[[0.0, 8.0], [0.0, 2 * np_mod.pi]],
        )
        hist_total += h2d
    s = hist_total.sum()
    if s <= 0:
        return None
    return hist_total / s


def _cosine_similarity(a, b, np_mod) -> float:
    """Cosine similarity in [0, 1] for non-negative histogram vectors."""
    av = a.flatten()
    bv = b.flatten()
    denom = float(np_mod.linalg.norm(av) * np_mod.linalg.norm(bv))
    if denom <= 0:
        return 0.0
    return float(np_mod.dot(av, bv) / denom)


def score_motion_fidelity(
    motion_clip_path: str,
    driving_clip_path: str,
    *,
    num_pairs: int = _NUM_SAMPLE_PAIRS,
) -> Optional[float]:
    """Score how closely ``motion_clip_path`` follows the motion of ``driving_clip_path``.

    Args:
        motion_clip_path: the final motion render (what generate_ai_video produced)
        driving_clip_path: the performance-capture driving reference
        num_pairs: sample size; default tuned for typical 5-8s clips

    Returns:
        float in [0, 1] on success — 1.0 means identical motion signature,
        0.0 means orthogonal motion. None when scoring isn't possible (e.g.,
        cv2 missing, file missing, no frames extractable).
    """
    cv2_mod, np_mod = _try_imports()
    if cv2_mod is None:
        return None
    if not (motion_clip_path and os.path.exists(motion_clip_path)):
        return None
    if not (driving_clip_path and os.path.exists(driving_clip_path)):
        return None

    try:
        motion_pairs = _sample_frame_pairs(motion_clip_path, num_pairs, cv2_mod, np_mod)
        driving_pairs = _sample_frame_pairs(driving_clip_path, num_pairs, cv2_mod, np_mod)
        if not motion_pairs or not driving_pairs:
            return None

        motion_hist = _flow_histogram(motion_pairs, cv2_mod, np_mod)
        driving_hist = _flow_histogram(driving_pairs, cv2_mod, np_mod)
        if motion_hist is None or driving_hist is None:
            return None
        return _cosine_similarity(motion_hist, driving_hist, np_mod)
    except Exception as e:
        # Any unexpected failure is "inconclusive", not "fail".
        print(f"[motion_gate] scoring failed: {e}")
        return None


def needs_remotion(
    score: Optional[float],
    floor: float = DEFAULT_MOTION_FLOOR,
) -> bool:
    """True when the gate's score is below ``floor`` AND the gate ran.

    Returns False when score is None (inconclusive — defer to operator).
    """
    if score is None:
        return False
    return score < floor
