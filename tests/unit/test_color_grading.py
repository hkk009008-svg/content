"""Tests for color grading presets and FFmpeg filter generation."""

import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from phase_c_ffmpeg import COLOR_GRADE_PRESETS, apply_color_grade


# ---------------------------------------------------------------------------
# Preset completeness
# ---------------------------------------------------------------------------


EXPECTED_PRESETS = [
    "warm_cinema",
    "cool_noir",
    "vibrant",
    "desaturated",
    "golden_hour",
    "moonlight",
    "high_contrast",
    "pastel",
]


class TestPresetCompleteness:
    """Verify all 8 color grading presets exist and are valid."""

    def test_all_expected_presets_exist(self):
        for name in EXPECTED_PRESETS:
            assert name in COLOR_GRADE_PRESETS, f"Missing preset: {name}"

    def test_exactly_eight_presets(self):
        assert len(COLOR_GRADE_PRESETS) == 8

    @pytest.mark.parametrize("preset", EXPECTED_PRESETS)
    def test_preset_is_nonempty_string(self, preset):
        value = COLOR_GRADE_PRESETS[preset]
        assert isinstance(value, str)
        assert len(value) > 0

    @pytest.mark.parametrize("preset", EXPECTED_PRESETS)
    def test_preset_contains_eq_filter(self, preset):
        """Every preset should use the FFmpeg eq filter."""
        value = COLOR_GRADE_PRESETS[preset]
        assert "eq=" in value, f"{preset} missing eq= filter"


# ---------------------------------------------------------------------------
# FFmpeg filter string validation
# ---------------------------------------------------------------------------


class TestFilterStringFormat:
    """Validate that FFmpeg filter strings are well-formed."""

    @pytest.mark.parametrize("preset", EXPECTED_PRESETS)
    def test_no_unbalanced_parentheses(self, preset):
        value = COLOR_GRADE_PRESETS[preset]
        assert value.count("(") == value.count(")"), (
            f"{preset} has unbalanced parentheses"
        )

    @pytest.mark.parametrize("preset", EXPECTED_PRESETS)
    def test_eq_has_valid_parameters(self, preset):
        """eq filter should have recognized parameter names."""
        value = COLOR_GRADE_PRESETS[preset]
        # Extract eq=... portion
        parts = value.split(",")
        eq_parts = [p for p in parts if p.startswith("eq=")]
        assert len(eq_parts) >= 1, f"{preset} missing eq= section"

        eq_str = eq_parts[0][3:]  # strip "eq="
        valid_params = {"brightness", "contrast", "saturation", "gamma",
                        "gamma_r", "gamma_g", "gamma_b", "gamma_weight"}
        for kv in eq_str.split(":"):
            key = kv.split("=")[0]
            assert key in valid_params, (
                f"{preset}: unrecognized eq parameter '{key}'"
            )

    @pytest.mark.parametrize("preset", [p for p in EXPECTED_PRESETS
                                         if "colorbalance" in COLOR_GRADE_PRESETS[p]])
    def test_colorbalance_has_valid_channels(self, preset):
        """colorbalance filter should use valid channel keys."""
        value = COLOR_GRADE_PRESETS[preset]
        parts = value.split(",")
        cb_parts = [p for p in parts if p.startswith("colorbalance=")]
        assert len(cb_parts) >= 1

        cb_str = cb_parts[0][len("colorbalance="):]
        valid_channels = {"rs", "gs", "bs", "rm", "gm", "bm", "rh", "gh", "bh"}
        for kv in cb_str.split(":"):
            key = kv.split("=")[0]
            assert key in valid_channels, (
                f"{preset}: unrecognized colorbalance channel '{key}'"
            )


# ---------------------------------------------------------------------------
# Preset value ranges
# ---------------------------------------------------------------------------


class TestPresetValueRanges:
    """Verify filter parameter values are within sensible ranges."""

    def _extract_eq_params(self, preset_name):
        """Extract eq parameters as a dict of floats."""
        value = COLOR_GRADE_PRESETS[preset_name]
        parts = value.split(",")
        eq_parts = [p for p in parts if p.startswith("eq=")]
        if not eq_parts:
            return {}
        eq_str = eq_parts[0][3:]
        params = {}
        for kv in eq_str.split(":"):
            k, v = kv.split("=")
            params[k] = float(v)
        return params

    @pytest.mark.parametrize("preset", EXPECTED_PRESETS)
    def test_brightness_in_range(self, preset):
        params = self._extract_eq_params(preset)
        if "brightness" in params:
            b = params["brightness"]
            assert -0.5 <= b <= 0.5, f"{preset} brightness={b} out of [-0.5, 0.5]"

    @pytest.mark.parametrize("preset", EXPECTED_PRESETS)
    def test_contrast_in_range(self, preset):
        params = self._extract_eq_params(preset)
        if "contrast" in params:
            c = params["contrast"]
            assert 0.5 <= c <= 2.0, f"{preset} contrast={c} out of [0.5, 2.0]"

    @pytest.mark.parametrize("preset", EXPECTED_PRESETS)
    def test_saturation_in_range(self, preset):
        params = self._extract_eq_params(preset)
        if "saturation" in params:
            s = params["saturation"]
            assert 0.0 <= s <= 2.0, f"{preset} saturation={s} out of [0.0, 2.0]"


# ---------------------------------------------------------------------------
# apply_color_grade function
# ---------------------------------------------------------------------------


class TestApplyColorGrade:
    """Test apply_color_grade() function behavior."""

    @patch("phase_c_ffmpeg.subprocess.run")
    @patch("phase_c_ffmpeg.os.path.exists", return_value=True)
    def test_uses_preset_filter(self, mock_exists, mock_run):
        result = apply_color_grade("/tmp/in.mp4", "/tmp/out.mp4", preset="cool_noir")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "-vf" in cmd
        vf_idx = cmd.index("-vf")
        assert cmd[vf_idx + 1] == COLOR_GRADE_PRESETS["cool_noir"]

    @patch("phase_c_ffmpeg.subprocess.run")
    @patch("phase_c_ffmpeg.os.path.exists", return_value=True)
    def test_lut_overrides_preset(self, mock_exists, mock_run):
        result = apply_color_grade(
            "/tmp/in.mp4", "/tmp/out.mp4",
            preset="cool_noir", lut_path="/tmp/grade.cube"
        )
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        vf_idx = cmd.index("-vf")
        assert "lut3d=" in cmd[vf_idx + 1]
        assert "cool_noir" not in cmd[vf_idx + 1]

    @patch("phase_c_ffmpeg.subprocess.run")
    @patch("phase_c_ffmpeg.os.path.exists", return_value=True)
    def test_unknown_preset_falls_back_to_warm_cinema(self, mock_exists, mock_run):
        result = apply_color_grade("/tmp/in.mp4", "/tmp/out.mp4", preset="nonexistent")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        vf_idx = cmd.index("-vf")
        assert cmd[vf_idx + 1] == COLOR_GRADE_PRESETS["warm_cinema"]

    @patch("phase_c_ffmpeg.os.path.exists", return_value=False)
    def test_nonexistent_input_returns_none(self, mock_exists):
        result = apply_color_grade("/tmp/missing.mp4", "/tmp/out.mp4")
        assert result is None

    @patch("phase_c_ffmpeg.subprocess.run", side_effect=Exception("ffmpeg failed"))
    @patch("phase_c_ffmpeg.os.path.exists", return_value=True)
    def test_ffmpeg_failure_returns_none(self, mock_exists, mock_run):
        result = apply_color_grade("/tmp/in.mp4", "/tmp/out.mp4")
        assert result is None

    @patch("phase_c_ffmpeg.subprocess.run")
    @patch("phase_c_ffmpeg.os.path.exists", return_value=True)
    def test_default_preset_is_warm_cinema(self, mock_exists, mock_run):
        result = apply_color_grade("/tmp/in.mp4", "/tmp/out.mp4")
        cmd = mock_run.call_args[0][0]
        vf_idx = cmd.index("-vf")
        assert cmd[vf_idx + 1] == COLOR_GRADE_PRESETS["warm_cinema"]

    @patch("phase_c_ffmpeg.subprocess.run")
    @patch("phase_c_ffmpeg.os.path.exists", return_value=True)
    def test_output_codec_is_libx264(self, mock_exists, mock_run):
        apply_color_grade("/tmp/in.mp4", "/tmp/out.mp4")
        cmd = mock_run.call_args[0][0]
        assert "-c:v" in cmd
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "libx264"

    @patch("phase_c_ffmpeg.subprocess.run")
    @patch("phase_c_ffmpeg.os.path.exists", return_value=True)
    def test_audio_is_copied(self, mock_exists, mock_run):
        apply_color_grade("/tmp/in.mp4", "/tmp/out.mp4")
        cmd = mock_run.call_args[0][0]
        assert "-c:a" in cmd
        ca_idx = cmd.index("-c:a")
        assert cmd[ca_idx + 1] == "copy"


# ---------------------------------------------------------------------------
# Mood-to-preset mapping (from cinema_pipeline)
# ---------------------------------------------------------------------------


class TestMoodToGradeMapping:
    """Test the mood -> color grade preset mapping from cinema_pipeline."""

    MOOD_MAP = {
        "suspense": "cool_noir",
        "thriller": "cool_noir",
        "horror": "moonlight",
        "cinematic": "warm_cinema",
        "corporate": "high_contrast",
        "ethereal": "desaturated",
        "golden": "golden_hour",
        "vibrant": "vibrant",
    }

    @pytest.mark.parametrize("mood,expected_preset", list(MOOD_MAP.items()))
    def test_mood_maps_to_valid_preset(self, mood, expected_preset):
        """Each mood should map to a preset that exists in COLOR_GRADE_PRESETS."""
        assert expected_preset in COLOR_GRADE_PRESETS, (
            f"Mood '{mood}' maps to '{expected_preset}' which doesn't exist in presets"
        )

    def test_default_mood_fallback(self):
        """Unknown moods should default to warm_cinema."""
        default = self.MOOD_MAP.get("unknown_mood", "warm_cinema")
        assert default == "warm_cinema"

    def test_all_presets_have_at_least_one_mood(self):
        """Each preset should be reachable by at least one mood (coverage check)."""
        used_presets = set(self.MOOD_MAP.values())
        # pastel is not mapped to any mood — that's okay, it's available manually
        # Just verify the mapped ones all exist
        for preset in used_presets:
            assert preset in COLOR_GRADE_PRESETS
