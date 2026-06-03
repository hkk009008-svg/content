"""Schema-driven validation for MaxTier UI overlay values.

Guards the overlay blocks in `quality_max.generate_ai_broll_max` against
out-of-range / wrong-type values arriving via `ctx.global_settings`.

Bounds mirror the React sliders in:
  * `web/src/components/settings/AdvancedSection.tsx::MaxTierComfyControls`
    (17 sampler / CN / post-pass knobs)
  * `web/src/components/settings/MaxQualityTierSection.tsx`
    (7 best-of-N halt knobs)
"""
from __future__ import annotations

import pytest

from quality_max import _MAX_TIER_KNOB_SCHEMA, _validate_overlay_value


class TestNumericClamping:
    def test_in_range_float_passes_through(self):
        accepted, warning = _validate_overlay_value("freeu_b1", 1.3)
        assert accepted == pytest.approx(1.3)
        assert warning is None

    def test_below_min_clamps_to_min_with_warning(self):
        accepted, warning = _validate_overlay_value("freeu_b1", 0.5)
        assert accepted == pytest.approx(1.0)
        assert warning is not None and "below" in warning

    def test_above_max_clamps_to_max_with_warning(self):
        # Reviewer's example: freeu_b1=99 silently passing to ComfyUI.
        accepted, warning = _validate_overlay_value("freeu_b1", 99.0)
        assert accepted == pytest.approx(1.8)
        assert warning is not None and "above" in warning

    def test_int_knob_preserves_int_type_after_clamp(self):
        accepted, _ = _validate_overlay_value("ays_steps", 999)
        assert accepted == 40
        assert isinstance(accepted, int)

    def test_int_knob_in_range_returns_int(self):
        accepted, warning = _validate_overlay_value("ays_steps", 28)
        assert accepted == 28
        assert isinstance(accepted, int)
        assert warning is None

    def test_non_coercible_numeric_is_rejected(self):
        accepted, warning = _validate_overlay_value("freeu_b1", "huge")
        assert accepted is None
        assert warning is not None and "coercible" in warning


class TestEnumValidation:
    def test_valid_enum_passes_through(self):
        accepted, warning = _validate_overlay_value("redux_strength", "high")
        assert accepted == "high"
        assert warning is None

    def test_unknown_enum_is_rejected_with_warning(self):
        accepted, warning = _validate_overlay_value("redux_strength", "EXTREME")
        assert accepted is None
        assert warning is not None and "EXTREME" in warning

    def test_face_detailer_guide_size_accepts_valid_choice(self):
        accepted, _ = _validate_overlay_value("face_detailer_guide_size", 1024)
        assert accepted == 1024

    def test_face_detailer_guide_size_rejects_unknown(self):
        accepted, warning = _validate_overlay_value("face_detailer_guide_size", 1500)
        assert accepted is None
        assert warning is not None


class TestBoolValidation:
    def test_true_passes_through(self):
        accepted, warning = _validate_overlay_value("hires_fix_enabled", True)
        assert accepted is True
        assert warning is None

    def test_false_passes_through(self):
        accepted, warning = _validate_overlay_value("hires_fix_enabled", False)
        assert accepted is False
        assert warning is None

    def test_non_bool_is_rejected(self):
        accepted, warning = _validate_overlay_value("hires_fix_enabled", "yes")
        assert accepted is None
        assert warning is not None


class TestHaltKnobValidation:
    """The 7 best-of-N halt knobs from MaxQualityTierSection.tsx."""

    def test_max_candidate_count_clamps_above_max_and_preserves_int(self):
        # UI slider stops at 16; JSON API could POST 999.
        accepted, warning = _validate_overlay_value("max_candidate_count", 999)
        assert accepted == 16
        assert isinstance(accepted, int)
        assert warning is not None and "above" in warning

    def test_max_halt_rule_rejects_unknown_enum(self):
        # Only the three documented rules are valid; everything else falls
        # back to the template default so the halt loop doesn't go undefined.
        accepted, warning = _validate_overlay_value("max_halt_rule", "always_halt")
        assert accepted is None
        assert warning is not None and "always_halt" in warning

    def test_max_halt_threshold_arc_clamps_below_min(self):
        # Arc floor is 0.50 (not 0.70 like composite): raw ArcFace lives lower
        # than the composite score, so this looser bound is intentional.
        accepted, warning = _validate_overlay_value("max_halt_threshold_arc", 0.10)
        assert accepted == pytest.approx(0.50)
        assert warning is not None and "below" in warning


class TestUnschemadKey:
    def test_unknown_key_passes_through_unchanged(self):
        # A knob added to the overlay block before its schema entry lands
        # should pass through, not be silently dropped.
        accepted, warning = _validate_overlay_value("some_future_knob", 99)
        assert accepted == 99
        assert warning is None


class TestSchemaCoverage:
    """Lock down the schema's coverage of both UI knob groups."""

    COMFYCONTROLS_KEYS = {
        "slg_scale",
        "freeu_b1", "freeu_b2", "freeu_s1", "freeu_s2",
        "ays_steps",
        "detail_daemon_amount",
        "controlnet_canny_strength",
        "controlnet_pose_strength",
        "controlnet_tile_strength",
        "redux_strength",
        "hires_fix_enabled", "hires_fix_denoise", "hires_fix_steps",
        "face_detailer_enabled", "face_detailer_guide_size",
        "supir_enabled", "supir_steps",
    }

    HALT_KNOB_KEYS = {
        "max_candidate_count",
        "max_candidate_batch",
        "max_halt_threshold_composite",
        "max_halt_threshold_arc",
        "max_halt_min_n",
        "max_regenerate_floor_arc",
        "max_halt_rule",
    }

    # ADR-010: parallelism knob for the N=8 best-of loop (commit 11c3e02).
    PARALLEL_KNOB_KEYS = {
        "max_quality_parallel_workers",
    }

    def test_schema_covers_comfycontrols_and_halt_knobs(self):
        # 18 ComfyControls + 7 halt knobs + 1 parallelism knob = 26 total schemad keys.
        # (T3 added hires_fix_steps alongside hires_fix_enabled/hires_fix_denoise.)
        assert set(_MAX_TIER_KNOB_SCHEMA.keys()) == (
            self.COMFYCONTROLS_KEYS | self.HALT_KNOB_KEYS | self.PARALLEL_KNOB_KEYS
        )
