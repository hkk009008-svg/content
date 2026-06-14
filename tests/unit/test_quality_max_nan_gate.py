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

from quality_max import (
    _validate_overlay_value,
    _finite_or,
    _inject_identity,
    _inject_secondary_loras,
)


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

    def test_pos_inf_on_float_knob_is_rejected(self):
        """+inf on a float knob must be REJECTED (accepted is None) by the
        isfinite guard — not merely clamped to a finite bound. The previous
        if-guarded form was VACUOUS post-fix: accepted is None, so its
        assertion body never ran (it would have passed even with the guard
        deleted). This unconditional form actually exercises the :172 reject."""
        accepted, warning = _validate_overlay_value("max_regenerate_floor_arc", float("inf"))
        assert accepted is None, f"expected None (rejected), got {accepted!r}"
        assert warning, "expected a truthy 'non-finite; skipped' warning"

    def test_neg_inf_on_float_knob_is_rejected(self):
        """-inf on a float knob must be REJECTED (accepted is None) by the
        isfinite guard."""
        accepted, warning = _validate_overlay_value("max_regenerate_floor_arc", float("-inf"))
        assert accepted is None, f"expected None (rejected), got {accepted!r}"
        assert warning, "expected a truthy 'non-finite; skipped' warning"


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

    def test_none_default_yields_none_for_nonfinite(self):
        """_finite_or(x, None) is the building block for the img2img guard:
        a non-finite/non-coercible value must yield None so the caller can
        skip the write and keep the template default."""
        assert _finite_or(float("nan"), None) is None
        assert _finite_or(float("inf"), None) is None
        assert _finite_or(float("-inf"), None) is None
        assert _finite_or("abc", None) is None
        assert _finite_or(0.0, None) == pytest.approx(0.0)  # 0.0 is finite, preserved

    def test_huge_int_returns_default(self):
        """float(10**309) raises OverflowError (an ArithmeticError, NOT Type/ValueError),
        so a try/except over (TypeError, ValueError) lets it propagate. A huge JSON integer
        in project.json's char_lora_strengths must fall back to the default, not abort the
        max-tier run. Mirrors _validate_overlay_value's OverflowError guard (7b4d377)."""
        assert _finite_or(10 ** 309, 0.5) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# _finite_or callsite integration — exercise the exact read-expressions
# at quality_max.py:1083/1084/1085 (params) + :1102 (get_project_setting)
# ---------------------------------------------------------------------------

class TestResolveHaltThresholds:
    """Couples to the production read _resolve_halt_thresholds (best-of-N halt
    loop). Unlike a bare _finite_or test, these go RED if the _finite_or
    wrapping is stripped from the helper — they enforce that the guard stays on
    the callsite, not merely that the helper works in isolation. The reads are
    a read-side BACKSTOP (the _validate_overlay_value chokepoint covers only the
    UI-overlay path; these guard a non-finite reaching params from any path)."""

    def test_nan_halt_composite_falls_back_to_default(self):
        from quality_max import _resolve_halt_thresholds
        c, a, r = _resolve_halt_thresholds({"halt_threshold_composite": float("nan")})
        assert c == pytest.approx(0.92)

    def test_nan_halt_arc_falls_back_to_default(self):
        from quality_max import _resolve_halt_thresholds
        c, a, r = _resolve_halt_thresholds({"halt_threshold_arc": float("nan")})
        assert a == pytest.approx(0.85)

    def test_inf_regen_floor_falls_back_to_default(self):
        from quality_max import _resolve_halt_thresholds
        c, a, r = _resolve_halt_thresholds({"regenerate_floor_arc": float("inf")})
        assert r == pytest.approx(0.82)

    def test_valid_values_pass_through(self):
        from quality_max import _resolve_halt_thresholds
        c, a, r = _resolve_halt_thresholds(
            {"halt_threshold_composite": 0.95, "halt_threshold_arc": 0.88,
             "regenerate_floor_arc": 0.80})
        assert (c, a, r) == pytest.approx((0.95, 0.88, 0.80))

    def test_missing_keys_use_defaults(self):
        from quality_max import _resolve_halt_thresholds
        assert _resolve_halt_thresholds({}) == pytest.approx((0.92, 0.85, 0.82))


class TestResolveIdentityThreshold:
    """Couples to the production read _resolve_identity_threshold — the identity
    acceptance bar for best-of-N scoring. This is the ONE gate read with NO
    write-side chokepoint (it comes via get_project_setting, bypassing
    _validate_overlay_value), so _finite_or is its SOLE NaN barrier. Goes RED if
    that guard is stripped."""

    def test_nan_identity_strictness_in_ctx_falls_back(self):
        from quality_max import _resolve_identity_threshold
        from cinema.context import PipelineContext
        ctx = PipelineContext()
        ctx.global_settings = {"identity_strictness": float("nan")}
        assert _resolve_identity_threshold(ctx) == pytest.approx(0.60)

    def test_none_ctx_returns_default(self):
        from quality_max import _resolve_identity_threshold
        assert _resolve_identity_threshold(None) == pytest.approx(0.60)

    def test_valid_identity_strictness_passes_through(self):
        from quality_max import _resolve_identity_threshold
        from cinema.context import PipelineContext
        ctx = PipelineContext()
        ctx.global_settings = {"identity_strictness": 0.75}
        assert _resolve_identity_threshold(ctx) == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# nit-2 — +inf/-inf on an INT knob must be skipped, not raise OverflowError
# ---------------------------------------------------------------------------

class TestIntKnobNonFiniteOverflow:
    """int(float('inf')) raises OverflowError (an ArithmeticError, NOT
    TypeError/ValueError), so a +inf/-inf on an int knob escaped the line-170
    except and propagated out of the overlay loop — aborting the whole
    max-tier run instead of emitting a per-knob skip warning."""

    def test_pos_inf_on_int_knob_is_skipped_not_raised(self):
        accepted, warning = _validate_overlay_value("max_candidate_count", float("inf"))
        assert accepted is None, "expected skip (None), not a raised OverflowError"
        assert warning, "expected a truthy 'not coercible; skipped' warning"

    def test_neg_inf_on_int_knob_is_skipped_not_raised(self):
        accepted, warning = _validate_overlay_value("max_candidate_count", float("-inf"))
        assert accepted is None
        assert warning

    def test_nan_on_int_knob_is_skipped(self):
        """Non-regression: int(float('nan')) raises ValueError (already caught)."""
        accepted, warning = _validate_overlay_value("max_candidate_count", float("nan"))
        assert accepted is None
        assert warning

    def test_valid_int_knob_still_passes(self):
        """Non-regression: a valid int value is unaffected."""
        accepted, warning = _validate_overlay_value("max_candidate_count", 5)
        assert accepted == 5
        assert warning is None


# ---------------------------------------------------------------------------
# Rule#13 siblings — non-finite LoRA strengths must not reach LoraLoader nodes
# (found by the symmetric audit; both write directly into ComfyUI node inputs)
# ---------------------------------------------------------------------------

class TestPrimaryCharLoraStrengthGuard:
    """_inject_identity — a non-finite char_lora_strength (NaN/inf token in
    project.json's char_lora_strengths) must NOT be written into LoraLoader(700)
    strength_model/clip; it falls back to the tier default like an unset value."""

    def _wf(self):
        return {"700": {"inputs": {}}}

    def test_nan_char_lora_strength_falls_back_to_tier_default(self):
        wf = self._wf()
        params = {"lora_strength_model": 0.8, "lora_strength_clip": 0.7}
        _inject_identity(wf, "alice.safetensors", None, params, True,
                         char_lora_strength=float("nan"))
        sm = wf["700"]["inputs"]["strength_model"]
        sc = wf["700"]["inputs"]["strength_clip"]
        assert math.isfinite(sm), f"strength_model {sm!r} non-finite"
        assert math.isfinite(sc), f"strength_clip {sc!r} non-finite"
        assert sm == pytest.approx(0.8)
        assert sc == pytest.approx(0.7)

    def test_inf_char_lora_strength_falls_back(self):
        wf = self._wf()
        params = {"lora_strength_model": 0.9, "lora_strength_clip": 0.9}
        _inject_identity(wf, "alice.safetensors", None, params, True,
                         char_lora_strength=float("inf"))
        assert wf["700"]["inputs"]["strength_model"] == pytest.approx(0.9)

    def test_valid_char_lora_strength_passes_through(self):
        """Non-regression: a finite per-char strength still overrides the default."""
        wf = self._wf()
        params = {"lora_strength_model": 1.0, "lora_strength_clip": 1.0}
        _inject_identity(wf, "alice.safetensors", None, params, True,
                         char_lora_strength=0.55)
        assert wf["700"]["inputs"]["strength_model"] == pytest.approx(0.55)
        assert wf["700"]["inputs"]["strength_clip"] == pytest.approx(0.55)

    def test_zero_char_lora_strength_is_honored(self):
        """Non-regression: 0.0 is a finite, intentional strength (not falsy→default)."""
        wf = self._wf()
        params = {"lora_strength_model": 1.0, "lora_strength_clip": 1.0}
        _inject_identity(wf, "alice.safetensors", None, params, True,
                         char_lora_strength=0.0)
        assert wf["700"]["inputs"]["strength_model"] == pytest.approx(0.0)


class TestSecondaryLoraStrengthGuard:
    """_inject_secondary_loras — the intended ceiling min(strength, 0.55) is
    BROKEN for NaN (min(nan, 0.55) == nan). A non-finite secondary lora_strength
    must fall back to the bleed-mitigation ceiling, not slip into LoraLoader(701)."""

    def _wf(self):
        return {"700": {"inputs": {}}}

    def test_nan_secondary_strength_falls_back_to_ceiling(self):
        wf = self._wf()
        _inject_secondary_loras(wf, [{"lora_path": "bob.safetensors",
                                      "lora_strength": float("nan")}])
        assert "701" in wf
        sm = wf["701"]["inputs"]["strength_model"]
        sc = wf["701"]["inputs"]["strength_clip"]
        assert math.isfinite(sm), f"strength_model {sm!r} non-finite"
        assert math.isfinite(sc), f"strength_clip {sc!r} non-finite"
        assert sm == pytest.approx(0.55)

    def test_valid_secondary_strength_passes(self):
        """Non-regression: a finite under-ceiling strength is used as-is."""
        wf = self._wf()
        _inject_secondary_loras(wf, [{"lora_path": "bob.safetensors",
                                      "lora_strength": 0.40}])
        assert wf["701"]["inputs"]["strength_model"] == pytest.approx(0.40)

    def test_over_ceiling_secondary_strength_is_clamped(self):
        """Non-regression: an over-ceiling finite strength clamps to 0.55."""
        wf = self._wf()
        _inject_secondary_loras(wf, [{"lora_path": "bob.safetensors",
                                      "lora_strength": 0.80}])
        assert wf["701"]["inputs"]["strength_model"] == pytest.approx(0.55)

    def test_unset_secondary_strength_uses_ceiling(self):
        """Non-regression: a missing lora_strength defaults to the ceiling."""
        wf = self._wf()
        _inject_secondary_loras(wf, [{"lora_path": "bob.safetensors"}])
        assert wf["701"]["inputs"]["strength_model"] == pytest.approx(0.55)


# ---------------------------------------------------------------------------
# nit-1 — img2img_denoise clamp extracted to a testable pure helper
# ---------------------------------------------------------------------------

class TestImg2imgDenoiseClamp:
    """_clamp_img2img_denoise makes the previously-accidental clamp-luck
    explicit: non-finite -> None (caller keeps template default); finite ->
    clamped to [0.2, 0.6]."""

    def test_nonfinite_returns_none(self):
        from quality_max import _clamp_img2img_denoise
        assert _clamp_img2img_denoise(float("nan")) is None
        assert _clamp_img2img_denoise(float("inf")) is None
        assert _clamp_img2img_denoise(float("-inf")) is None

    def test_in_range_passes_through(self):
        from quality_max import _clamp_img2img_denoise
        assert _clamp_img2img_denoise(0.4) == pytest.approx(0.4)

    def test_above_range_clamps_to_hi(self):
        from quality_max import _clamp_img2img_denoise
        assert _clamp_img2img_denoise(0.9) == pytest.approx(0.6)

    def test_below_range_clamps_to_lo(self):
        from quality_max import _clamp_img2img_denoise
        assert _clamp_img2img_denoise(0.1) == pytest.approx(0.2)
