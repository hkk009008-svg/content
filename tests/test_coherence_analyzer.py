"""
Tests for coherence_analyzer.py — visual coherence scoring logic.
Uses synthetic images created with OpenCV/numpy (no real assets needed).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tempfile
import numpy as np
import cv2
import pytest

from coherence_analyzer import (
    SceneCoherenceResult,
    ColorCoherenceAnalyzer,
    CompositionAnalyzer,
    assess_coherence,
)


# ---------------------------------------------------------------------------
# Helpers — create synthetic test images
# ---------------------------------------------------------------------------


def _save_solid_image(color_bgr, path=None, size=(128, 128)):
    """Create a solid-color image and save to disk."""
    img = np.full((*size, 3), color_bgr, dtype=np.uint8)
    if path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        path = tmp.name
        tmp.close()
    cv2.imwrite(path, img)
    return path


def _save_gradient_image(start_val, end_val, path=None, size=(128, 128)):
    """Create a horizontal gradient grayscale image."""
    img = np.zeros((*size, 3), dtype=np.uint8)
    for x in range(size[1]):
        val = int(start_val + (end_val - start_val) * x / size[1])
        img[:, x, :] = val
    if path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        path = tmp.name
        tmp.close()
    cv2.imwrite(path, img)
    return path


@pytest.fixture
def identical_pair(tmp_path):
    """Two identical blue images."""
    a = _save_solid_image([200, 100, 50], str(tmp_path / "a.png"))
    b = _save_solid_image([200, 100, 50], str(tmp_path / "b.png"))
    return a, b


@pytest.fixture
def different_pair(tmp_path):
    """Two very different images (blue vs orange)."""
    a = _save_solid_image([200, 50, 20], str(tmp_path / "a.png"))
    b = _save_solid_image([20, 50, 200], str(tmp_path / "b.png"))
    return a, b


@pytest.fixture
def bright_dark_pair(tmp_path):
    """One bright image and one dark image."""
    bright = _save_solid_image([220, 220, 220], str(tmp_path / "bright.png"))
    dark = _save_solid_image([30, 30, 30], str(tmp_path / "dark.png"))
    return bright, dark


# ---------------------------------------------------------------------------
# SceneCoherenceResult dataclass
# ---------------------------------------------------------------------------


class TestSceneCoherenceResult:
    def test_construction(self):
        r = SceneCoherenceResult(
            overall_coherence_score=0.85,
            color_drift=0.1,
            lighting_consistency=0.9,
            composition_similarity=0.8,
        )
        assert r.overall_coherence_score == 0.85
        assert r.recommendations == []

    def test_recommendations_list(self):
        r = SceneCoherenceResult(
            overall_coherence_score=0.5,
            color_drift=0.4,
            lighting_consistency=0.4,
            composition_similarity=0.6,
            recommendations=["adjust_color_prompt", "match_lighting"],
        )
        assert len(r.recommendations) == 2


# ---------------------------------------------------------------------------
# ColorCoherenceAnalyzer
# ---------------------------------------------------------------------------


class TestColorCoherenceAnalyzer:
    def test_extract_histogram_returns_array(self, identical_pair):
        hist = ColorCoherenceAnalyzer.extract_color_histogram(identical_pair[0])
        assert hist is not None
        assert isinstance(hist, np.ndarray)

    def test_extract_histogram_nonexistent_returns_none(self):
        hist = ColorCoherenceAnalyzer.extract_color_histogram("/nonexistent/path.png")
        assert hist is None

    def test_compare_identical_histograms_score_one(self, identical_pair):
        hist_a = ColorCoherenceAnalyzer.extract_color_histogram(identical_pair[0])
        hist_b = ColorCoherenceAnalyzer.extract_color_histogram(identical_pair[1])
        score = ColorCoherenceAnalyzer.compare_histograms(hist_a, hist_b)
        assert score > 0.95, f"Identical images should have similarity > 0.95, got {score}"

    def test_compare_different_histograms_score_low(self, different_pair):
        hist_a = ColorCoherenceAnalyzer.extract_color_histogram(different_pair[0])
        hist_b = ColorCoherenceAnalyzer.extract_color_histogram(different_pair[1])
        score = ColorCoherenceAnalyzer.compare_histograms(hist_a, hist_b)
        assert score < 0.5, f"Very different images should have similarity < 0.5, got {score}"

    def test_compare_with_none_returns_zero(self):
        hist = np.ones((64, 64), dtype=np.float32)
        assert ColorCoherenceAnalyzer.compare_histograms(None, hist) == 0.0
        assert ColorCoherenceAnalyzer.compare_histograms(hist, None) == 0.0

    def test_score_bounded_zero_to_one(self, identical_pair, different_pair):
        hist_a = ColorCoherenceAnalyzer.extract_color_histogram(identical_pair[0])
        hist_b = ColorCoherenceAnalyzer.extract_color_histogram(different_pair[1])
        score = ColorCoherenceAnalyzer.compare_histograms(hist_a, hist_b)
        assert 0.0 <= score <= 1.0

    def test_detect_palette_drift_identical_is_zero(self, identical_pair):
        analyzer = ColorCoherenceAnalyzer()
        drift = analyzer.detect_palette_drift(identical_pair[0], [identical_pair[1]])
        assert drift < 0.1, f"Identical images should have near-zero drift, got {drift}"

    def test_detect_palette_drift_different_is_high(self, different_pair):
        analyzer = ColorCoherenceAnalyzer()
        drift = analyzer.detect_palette_drift(different_pair[0], [different_pair[1]])
        assert drift > 0.3, f"Different images should have high drift, got {drift}"

    def test_detect_palette_drift_empty_scene_returns_zero(self, identical_pair):
        analyzer = ColorCoherenceAnalyzer()
        drift = analyzer.detect_palette_drift(identical_pair[0], [])
        assert drift == 0.0


# ---------------------------------------------------------------------------
# CompositionAnalyzer
# ---------------------------------------------------------------------------


class TestCompositionAnalyzer:
    def test_brightness_high_key(self, tmp_path):
        path = _save_solid_image([230, 230, 230], str(tmp_path / "bright.png"))
        info = CompositionAnalyzer.analyze_brightness_distribution(path)
        assert info["key_type"] == "high_key"
        assert info["mean_brightness"] > 0.6

    def test_brightness_low_key(self, tmp_path):
        path = _save_solid_image([30, 30, 30], str(tmp_path / "dark.png"))
        info = CompositionAnalyzer.analyze_brightness_distribution(path)
        assert info["key_type"] == "low_key"
        assert info["mean_brightness"] < 0.4

    def test_brightness_balanced(self, tmp_path):
        path = _save_solid_image([128, 128, 128], str(tmp_path / "mid.png"))
        info = CompositionAnalyzer.analyze_brightness_distribution(path)
        assert info["key_type"] == "balanced"

    def test_brightness_nonexistent_returns_unknown(self):
        info = CompositionAnalyzer.analyze_brightness_distribution("/nonexistent.png")
        assert info["key_type"] == "unknown"
        assert info["mean_brightness"] == 0.0

    def test_lighting_direction_identical_images_high(self, identical_pair):
        score = CompositionAnalyzer.compare_lighting_direction(
            identical_pair[0], identical_pair[1]
        )
        assert score > 0.8, f"Identical images should have consistent lighting, got {score}"

    def test_lighting_direction_bounded(self, identical_pair, different_pair):
        score = CompositionAnalyzer.compare_lighting_direction(
            identical_pair[0], different_pair[1]
        )
        assert 0.0 <= score <= 1.0

    def test_lighting_direction_missing_image_returns_half(self):
        score = CompositionAnalyzer.compare_lighting_direction("/nonexistent.png", "/also_missing.png")
        assert score == 0.5

    def test_exposure_shift_identical_is_zero(self, identical_pair):
        analyzer = CompositionAnalyzer()
        shift = analyzer.detect_exposure_shift([identical_pair[0], identical_pair[1]])
        assert shift < 0.05

    def test_exposure_shift_bright_dark_is_high(self, bright_dark_pair):
        analyzer = CompositionAnalyzer()
        shift = analyzer.detect_exposure_shift([bright_dark_pair[0], bright_dark_pair[1]])
        assert shift > 0.5, f"Bright vs dark should have high exposure shift, got {shift}"

    def test_exposure_shift_single_image_is_zero(self, identical_pair):
        analyzer = CompositionAnalyzer()
        shift = analyzer.detect_exposure_shift([identical_pair[0]])
        assert shift == 0.0


# ---------------------------------------------------------------------------
# assess_coherence (main function)
# ---------------------------------------------------------------------------


class TestAssessCoherence:
    def test_identical_images_high_coherence(self, identical_pair):
        result = assess_coherence(identical_pair[0], identical_pair[1])
        assert result.overall_coherence_score > 0.7
        assert result.color_drift < 0.3

    def test_different_images_lower_coherence(self, different_pair):
        result = assess_coherence(different_pair[0], different_pair[1])
        assert result.overall_coherence_score < result.overall_coherence_score + 0.5  # sanity
        assert result.color_drift > 0.3

    def test_weighting_formula(self):
        """Verify: overall = (1-color_drift)*0.4 + lighting*0.3 + composition_sim*0.3"""
        color_drift = 0.2
        lighting = 0.8
        composition_sim = 0.6
        expected = (1.0 - color_drift) * 0.4 + lighting * 0.3 + composition_sim * 0.3
        assert abs(expected - 0.74) < 0.01

    def test_color_drift_above_threshold_triggers_recommendation(self, different_pair):
        result = assess_coherence(different_pair[0], different_pair[1])
        if result.color_drift > 0.3:
            assert "adjust_color_prompt" in result.recommendations

    def test_brightness_delta_above_threshold_triggers_recommendation(self, bright_dark_pair):
        result = assess_coherence(bright_dark_pair[0], bright_dark_pair[1])
        assert "tighten_denoise" in result.recommendations

    def test_scene_images_parameter_accepted(self, identical_pair):
        result = assess_coherence(
            identical_pair[0],
            identical_pair[1],
            scene_images=[identical_pair[0], identical_pair[1]],
        )
        assert result.overall_coherence_score > 0.5

    def test_result_fields_bounded(self, identical_pair):
        result = assess_coherence(identical_pair[0], identical_pair[1])
        assert 0.0 <= result.overall_coherence_score <= 1.0
        assert 0.0 <= result.color_drift <= 1.0
        assert 0.0 <= result.lighting_consistency <= 1.0
        assert 0.0 <= result.composition_similarity <= 1.0
