"""Wave-2 identity/quality regressions from the Phase-0 hardening-campaign
discovery bug-hunt (discovery-wf_13f9d2f6-f93.json).

Confirmed indices and prefixes:
  confirmed[3]  W2:MEDIUM:identity-nan-arc-bypass
  confirmed[28] W2:MEDIUM:secondary-lora-hole (RETIRED WS1 Task 4 — its only
                implementation lived in quality_max.py, now deleted with no
                production replacement; regression tests retired alongside it)
  confirmed[29] Wdefer:MINOR:identity-arcface-embselect

All three were confirmed by refute-first verifiers in the discovery workflow (two
independent passes each, finalVerdict=CONFIRMED, production-reachable). The
remaining two rows are live regressions after their fixes.

When a remaining strict pin is fixed, XPASS is the signal to revise or delete it.
Mirror style: tests/unit/test_has_character_lora_only_hole.py,
              tests/unit/test_lane_silent_gate_siblings_xfail.py.
"""
import math
import os

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# confirmed[3]: W2:MEDIUM:identity-nan-arc-bypass
# face_validator_gate.py:326-341 (needs_regenerate)
# ---------------------------------------------------------------------------
# When arc_score is NaN and has_arc=True, `needs_regenerate` should return True
# (non-finite score -> regen must fire). Currently `float('nan') < 0.82` evaluates
# to False in Python, so the function returns False -> the PuLID weight-boost regen
# retry is silently skipped. The NaN reaches here because `_arcface_score` returns
# `float(result.overall_score)` without an isnan/isfinite guard, and NaN is not None
# so the `if arc is not None:` branch in score_candidate sets has_arc=True.
#
# Entry vectors (both production-reachable):
#   (a) A corrupted DeepFace/GhostFaceNet embedding propagates NaN through numpy
#       cosine arithmetic without raising an exception (the except-guard catches
#       exceptions, not silent NaN propagation).
#   (b) A CandidateScore deserialized from a cached project state with arc_score=NaN.
#
# Fixed by adding an isfinite guard before the raw arc_score comparison in
# needs_regenerate. This remains as a live regression for the Wave-2 row.
def test_needs_regenerate_returns_true_for_nan_arc_score():
    """needs_regenerate with arc_score=NaN, has_arc=True should return True
    (non-finite score must trigger regen)."""
    from face_validator_gate import CandidateScore, needs_regenerate

    best = CandidateScore(
        image_path="/tmp/test_candidate.png",
        seed=1,
        arc_score=float("nan"),
        has_arc=True,
    )
    assert math.isnan(best.arc_score), "precondition: arc_score must be NaN"
    assert best.has_arc is True, "precondition: has_arc must be True"

    result = needs_regenerate(best, regenerate_floor_arc=0.82, has_character=True)

    assert result is True, (
        "needs_regenerate must return True when arc_score is NaN (non-finite) and "
        "has_arc=True — NaN < threshold is always False in Python so the regen retry "
        "is silently skipped; fix requires an isfinite guard before the comparison"
    )


# ---------------------------------------------------------------------------
# confirmed[28]: W2:MEDIUM:secondary-lora-hole — RETIRED WS1 Task 4.
# Its only implementation (_inject_secondary_loras / _prune_unavailable /
# _inject_identity in quality_max.py) was deleted with no production
# replacement; the pinning tests were removed alongside it. See
# tests/unit/test_has_character_lora_only_hole.py for the still-open sibling
# design question (surfaced separately for explicit disposition).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# confirmed[29]: Wdefer:MINOR:identity-arcface-embselect
# identity/validator.py:940-943
# ---------------------------------------------------------------------------
# Live regression: the DeepFace detector can return multiple faces in arbitrary
# order, but the reference embedding should match the binding instrument's
# largest-OK selection rather than emb_list[0].
def test_get_embedding_uses_largest_ok_face_not_first_detection(monkeypatch):
    import identity.validator as validator_module

    first_small = np.array([1.0, 0.0, 0.0])
    second_largest_ok = np.array([0.0, 1.0, 0.0])
    detections = [
        {
            "embedding": first_small.tolist(),
            "facial_area": {"x": 5, "y": 5, "w": 80, "h": 80},
            "face_confidence": 0.99,
        },
        {
            "embedding": second_largest_ok.tolist(),
            "facial_area": {"x": 20, "y": 20, "w": 160, "h": 160},
            "face_confidence": 0.99,
        },
    ]

    class FakeImage:
        size = (400, 400)

    class FakePILImage:
        @staticmethod
        def open(_path):
            return FakeImage()

    monkeypatch.setattr(validator_module, "DEEPFACE_AVAILABLE", True)
    monkeypatch.setattr(validator_module, "_PIL_AVAILABLE", True)
    monkeypatch.setattr(validator_module, "_PILImage", FakePILImage)
    monkeypatch.setattr(
        validator_module,
        "_represent_deterministic",
        lambda _path: detections,
    )

    validator = validator_module.IdentityValidator()

    embedding = validator._get_embedding("/ref-with-two-faces.jpg", "char_ref")

    assert np.array_equal(embedding, second_largest_ok), (
        "_get_embedding must select the largest OK detection for reference images "
        "instead of trusting arbitrary DeepFace detection order"
    )
