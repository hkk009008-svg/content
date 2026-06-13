"""NaN/inf gate tests for quality_max — TDD RED-first.

Triple-verified defect class: NaN/inf float values survive project.json because
json.load(allow_nan=True) is the default, so bare NaN tokens persist on disk.
NaN defeats numeric gates because `NaN < x` and `NaN > x` are BOTH False.

Sites fixed (symbol-anchored — line numbers drift):
  - _validate_overlay_value — write-side chokepoint: rejects non-finite floats
    BEFORE the range clamps (a NaN slips past `< lo`/`> hi`, both False).
  - _finite_or helper — read-side guard for the best-of-N halt/regen reads
    (halt_threshold_composite/_arc, regenerate_floor_arc) + identity_strictness.
"""
from __future__ import annotations

import math
import pytest

from quality_max import _validate_overlay_value, _finite_or


# ---------------------------------------------------------------------------
# _validate_overlay_value — NaN/inf rejection (write-side chokepoint)
# ---------------------------------------------------------------------------

class TestNanGateChokepoint:
    """NaN on a float knob must be REJECTED (not returned unclamped)."""

    def test_nan_on_regen_floor_arc_is_rejected(self):
        """NaN on max_regenerate_floor_arc -> accepted is None, warning is truthy.

        This is the MAJOR site: regen_floor_arc guards PuLID identity-rescue.
        NaN -> best.arc_score < NaN always False -> retry never fires -> weak
        identity ship as-is.
        """
        accepted, warning = _validate_overlay_value("max_regenerate_floor_arc", float("nan"))
        assert accepted is None, "NaN must be rejected (accepted should be None)"
        assert warning, "A truthy warning string must be present"

    def test_nan_on_halt_threshold_composite_is_rejected(self):
        accepted, warning = _validate_overlay_value("max_halt_threshold_composite", float("nan"))
        assert accepted is None
        assert warning

    def test_nan_on_halt_threshold_arc_is_rejected(self):
        accepted, warning = _validate_overlay_value("max_halt_threshold_arc", float("nan"))
        assert accepted is None
        assert warning

    def test_nan_on_controlnet_pose_strength_is_rejected(self):
        """Proves the cn_pose_strength prune-gate is protected: a NaN
        cn_pose_strength would bypass the `<= 0.001` prune and inject NaN
        strength into live ComfyUI ControlNet nodes. controlnet_pose_strength
        rides the registry, so the chokepoint reject covers it (no edit there)."""
        accepted, warning = _validate_overlay_value("controlnet_pose_strength", float("nan"))
        assert accepted is None
        assert warning

    def test_pos_inf_on_float_knob_does_not_return_non_finite(self):
        """+inf must never escape as a non-finite float. Post-fix the isfinite
        guard REJECTS it (returns None) before the range clamp; pre-fix the
        `> hi` clamp caught it. Invariant either way: accepted is None or
        finite, never +inf."""
        accepted, warning = _validate_overlay_value("max_regenerate_floor_arc", float("inf"))
        if accepted is not None:
            assert math.isfinite(accepted), f"accepted {accepted!r} is not finite"

    def test_neg_inf_on_float_knob_does_not_return_non_finite(self):
        """-inf must never escape as a non-finite float. Post-fix the isfinite
        guard REJECTS it (returns None) before the range clamp; invariant:
        accepted is None or finite, never -inf."""
        accepted, warning = _validate_overlay_value("max_regenerate_floor_arc", float("-inf"))
        if accepted is not None:
            assert math.isfinite(accepted), f"accepted {accepted!r} is not finite"


# ---------------------------------------------------------------------------
# Non-regression: valid in-range values must STILL pass
# ---------------------------------------------------------------------------

class TestNonRegressionValidValues:
    """Valid in-range float/int values must still pass cleanly."""

    def test_regen_floor_arc_0_50_passes(self):
        accepted, warning = _validate_overlay_value("max_regenerate_floor_arc", 0.50)
        assert accepted == pytest.approx(0.50)
        assert warning is None

    def test_regen_floor_arc_1_00_passes(self):
        accepted, warning = _validate_overlay_value("max_regenerate_floor_arc", 1.00)
        assert accepted == pytest.approx(1.00)
        assert warning is None

    def test_int_knob_max_candidate_count_passes(self):
        """int knob must be unaffected by the float-NaN guard."""
        accepted, warning = _validate_overlay_value("max_candidate_count", 5)
        assert accepted == 5
        assert warning is None


# ---------------------------------------------------------------------------
# _finite_or helper — read-side guard
# ---------------------------------------------------------------------------

class TestFiniteOrHelper:
    """Unit tests for the _finite_or(value, default) helper."""

    def test_nan_returns_default(self):
        assert _finite_or(float("nan"), 0.82) == pytest.approx(0.82)

    def test_pos_inf_returns_default(self):
        assert _finite_or(float("inf"), 0.6) == pytest.approx(0.6)

    def test_neg_inf_returns_default(self):
        assert _finite_or(float("-inf"), 0.6) == pytest.approx(0.6)

    def test_numeric_string_coerced(self):
        assert _finite_or("0.8", 0.6) == pytest.approx(0.8)

    def test_non_numeric_string_returns_default(self):
        assert _finite_or("abc", 0.6) == pytest.approx(0.6)

    def test_valid_float_passthrough(self):
        assert _finite_or(0.9, 0.6) == pytest.approx(0.9)

    def test_none_returns_default(self):
        assert _finite_or(None, 0.6) == pytest.approx(0.6)
