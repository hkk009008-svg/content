"""Schema-driven validation for MaxTier UI overlay values.

Guards the overlay block in `quality_max.generate_ai_broll_max` against
out-of-range / wrong-type values arriving via `ctx.global_settings`.

Bounds mirror the React sliders in
`web/src/components/settings/AdvancedSection.tsx::MaxTierComfyControls`.
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


class TestUnschemadKey:
    def test_halt_knob_passes_through_unchanged(self):
        # max_* halt knobs are intentionally not in this schema (separate
        # follow-up). Unknown keys should NOT be silently dropped.
        accepted, warning = _validate_overlay_value("max_candidate_count", 99)
        assert accepted == 99
        assert warning is None


class TestSchemaCoverage:
    """Lock down the 17 ComfyControls knobs the commit ec8b1d9 overlays."""

    EXPECTED_KEYS = {
        "slg_scale",
        "freeu_b1", "freeu_b2", "freeu_s1", "freeu_s2",
        "ays_steps",
        "detail_daemon_amount",
        "controlnet_canny_strength",
        "controlnet_pose_strength",
        "controlnet_tile_strength",
        "redux_strength",
        "hires_fix_enabled", "hires_fix_denoise",
        "face_detailer_enabled", "face_detailer_guide_size",
        "supir_enabled", "supir_steps",
    }

    def test_schema_covers_all_17_comfycontrols(self):
        assert set(_MAX_TIER_KNOB_SCHEMA.keys()) == self.EXPECTED_KEYS
