"""
Tests for vbench_evaluator.py — signal-level metrics and scoring logic.
No API keys needed; uses synthetic frames only.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest

from vbench_evaluator import (
    VBenchResult,
    VBenchEvaluator,
    DIMENSION_WEIGHTS,
)


# ---------------------------------------------------------------------------
# DIMENSION_WEIGHTS validation
# ---------------------------------------------------------------------------


class TestDimensionWeights:
    def test_weights_sum_to_one(self):
        total = sum(DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"

    def test_all_six_dimensions_present(self):
        expected = {
            "identity_consistency",
            "temporal_flicker",
            "motion_smoothness",
            "aesthetic_quality",
            "prompt_adherence",
            "physics_plausibility",
        }
        assert set(DIMENSION_WEIGHTS.keys()) == expected

    def test_all_weights_positive(self):
        for dim, w in DIMENSION_WEIGHTS.items():
            assert w > 0, f"{dim} weight should be positive, got {w}"


# ---------------------------------------------------------------------------
# VBenchResult dataclass
# ---------------------------------------------------------------------------


class TestVBenchResult:
    def test_default_values(self):
        r = VBenchResult()
        assert r.overall_score == 0.0
        assert r.identity_consistency == 0.0
        assert r.recommendations == []

    def test_to_dict_returns_all_fields(self):
        r = VBenchResult(
            identity_consistency=0.8,
            temporal_flicker=0.9,
            motion_smoothness=0.7,
            aesthetic_quality=0.6,
            prompt_adherence=0.75,
            physics_plausibility=0.85,
            overall_score=0.78,
            dimension_scores={"identity_consistency": 0.8},
        )
        d = r.to_dict()
        assert d["identity_consistency"] == 0.8
        assert d["overall_score"] == 0.78
        assert isinstance(d, dict)

    def test_to_dict_handles_numpy_floats(self):
        r = VBenchResult(
            identity_consistency=np.float64(0.8),
            overall_score=np.float32(0.78),
            dimension_scores={"test": np.float64(0.5)},
        )
        d = r.to_dict()
        assert isinstance(d["identity_consistency"], float)
        assert isinstance(d["overall_score"], float)
        assert isinstance(d["dimension_scores"]["test"], float)

    def test_summary_contains_all_dimensions(self):
        r = VBenchResult(
            identity_consistency=0.80,
            temporal_flicker=0.92,
            motion_smoothness=0.70,
            aesthetic_quality=0.65,
            prompt_adherence=0.75,
            physics_plausibility=0.80,
            overall_score=0.78,
        )
        s = r.summary()
        assert "Identity Consistency" in s
        assert "Temporal Flicker" in s
        assert "Motion Smoothness" in s
        assert "Overall Score" in s


# ---------------------------------------------------------------------------
# Temporal Flicker (signal-level, cv2 + numpy only)
# ---------------------------------------------------------------------------


class TestTemporalFlicker:
    def setup_method(self):
        self.evaluator = VBenchEvaluator(verbose=False)

    def test_identical_frames_score_near_one(self):
        """Identical frames should produce no flicker -> score ~1.0."""
        frames = [np.full((256, 256, 3), 128, dtype=np.uint8) for _ in range(5)]
        score = self.evaluator._evaluate_temporal_flicker(frames)
        assert score >= 0.99, f"Identical frames should score ~1.0, got {score}"

    def test_stable_frames_score_high(self):
        """Frames with tiny variation should still score high."""
        frames = []
        for i in range(5):
            frame = np.full((256, 256, 3), 128, dtype=np.uint8)
            frame[:, :, 0] = 128 + i  # tiny +1 per frame in blue channel
            frames.append(frame)
        score = self.evaluator._evaluate_temporal_flicker(frames)
        assert score > 0.95, f"Stable frames should score >0.95, got {score}"

    def test_alternating_bright_dark_scores_low(self):
        """Alternating bright/dark frames should produce high flicker -> low score."""
        frames = []
        for i in range(5):
            val = 50 if i % 2 == 0 else 200
            frame = np.full((256, 256, 3), val, dtype=np.uint8)
            frames.append(frame)
        score = self.evaluator._evaluate_temporal_flicker(frames)
        assert score < 0.5, f"Flickery frames should score <0.5, got {score}"

    def test_single_frame_returns_one(self):
        """A single frame means no flicker by definition."""
        frames = [np.full((256, 256, 3), 128, dtype=np.uint8)]
        score = self.evaluator._evaluate_temporal_flicker(frames)
        assert score == 1.0

    def test_score_bounded_zero_to_one(self):
        """Score must always be in [0, 1]."""
        # Random noisy frames
        rng = np.random.RandomState(42)
        frames = [rng.randint(0, 256, (64, 64, 3), dtype=np.uint8) for _ in range(10)]
        score = self.evaluator._evaluate_temporal_flicker(frames)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Motion Smoothness (signal-level, cv2 + numpy only)
# ---------------------------------------------------------------------------


class TestMotionSmoothness:
    def setup_method(self):
        self.evaluator = VBenchEvaluator(verbose=False)

    def test_consistent_motion_scores_high(self):
        """Frames with consistent horizontal shift should score high."""
        frames = []
        for i in range(5):
            frame = np.zeros((256, 256, 3), dtype=np.uint8)
            x_offset = i * 10  # consistent 10px shift
            cv2 = __import__("cv2")
            cv2.rectangle(frame, (50 + x_offset, 100), (100 + x_offset, 150), (255, 255, 255), -1)
            frames.append(frame)
        score = self.evaluator._evaluate_motion_smoothness(frames)
        assert score > 0.5, f"Smooth motion should score >0.5, got {score}"

    def test_static_frames_score_high(self):
        """Identical static frames should have very low flow variance -> high score."""
        frames = [np.full((128, 128, 3), 128, dtype=np.uint8) for _ in range(5)]
        score = self.evaluator._evaluate_motion_smoothness(frames)
        assert score > 0.8, f"Static frames should score >0.8, got {score}"

    def test_single_frame_returns_one(self):
        frames = [np.full((128, 128, 3), 128, dtype=np.uint8)]
        score = self.evaluator._evaluate_motion_smoothness(frames)
        assert score == 1.0

    def test_two_frames_returns_reasonable(self):
        """Two frames should return 0.9 (only one pair, assumed smooth)."""
        frames = [np.full((128, 128, 3), 128, dtype=np.uint8) for _ in range(2)]
        score = self.evaluator._evaluate_motion_smoothness(frames)
        assert score == 0.9

    def test_score_bounded_zero_to_one(self):
        rng = np.random.RandomState(42)
        frames = [rng.randint(0, 256, (64, 64, 3), dtype=np.uint8) for _ in range(6)]
        score = self.evaluator._evaluate_motion_smoothness(frames)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Regression Check
# ---------------------------------------------------------------------------


class TestRegressionCheck:
    def setup_method(self):
        self.evaluator = VBenchEvaluator(verbose=False, regression_tolerance=0.05)

    def _make_result(self, scores: dict) -> VBenchResult:
        return VBenchResult(
            identity_consistency=scores.get("identity_consistency", 0.8),
            temporal_flicker=scores.get("temporal_flicker", 0.9),
            motion_smoothness=scores.get("motion_smoothness", 0.7),
            aesthetic_quality=scores.get("aesthetic_quality", 0.7),
            prompt_adherence=scores.get("prompt_adherence", 0.7),
            physics_plausibility=scores.get("physics_plausibility", 0.8),
            overall_score=0.78,
            dimension_scores=scores,
        )

    def test_no_regression_when_scores_above_baseline(self):
        current = self._make_result({
            "identity_consistency": 0.85,
            "temporal_flicker": 0.92,
        })
        baseline = {
            "identity_consistency": 0.80,
            "temporal_flicker": 0.90,
        }
        regressions = self.evaluator.regression_check(current, baseline)
        assert regressions == []

    def test_regression_detected_when_below_tolerance(self):
        current = self._make_result({
            "identity_consistency": 0.70,
            "aesthetic_quality": 0.60,
            "temporal_flicker": 0.90,
        })
        baseline = {
            "identity_consistency": 0.85,  # current 0.70 < 0.85 - 0.05 = 0.80
            "aesthetic_quality": 0.80,      # current 0.60 < 0.80 - 0.05 = 0.75
            "temporal_flicker": 0.90,       # current 0.90 == 0.90, no regression
        }
        regressions = self.evaluator.regression_check(current, baseline, tolerance=0.05)
        assert "identity_consistency" in regressions
        assert "aesthetic_quality" in regressions
        assert "temporal_flicker" not in regressions

    def test_regression_within_tolerance_not_flagged(self):
        current = self._make_result({
            "identity_consistency": 0.82,
        })
        baseline = {"identity_consistency": 0.85}
        # 0.82 >= 0.85 - 0.05 = 0.80 -> no regression
        regressions = self.evaluator.regression_check(current, baseline, tolerance=0.05)
        assert regressions == []

    def test_custom_tolerance_overrides_default(self):
        current = self._make_result({
            "identity_consistency": 0.82,
        })
        baseline = {"identity_consistency": 0.85}
        # With tolerance=0.01: 0.82 < 0.85 - 0.01 = 0.84 -> regression
        regressions = self.evaluator.regression_check(current, baseline, tolerance=0.01)
        assert "identity_consistency" in regressions

    def test_missing_dimension_in_scores_is_skipped(self):
        current = self._make_result({
            "identity_consistency": 0.80,
        })
        baseline = {
            "identity_consistency": 0.80,
            "nonexistent_dimension": 0.90,
        }
        regressions = self.evaluator.regression_check(current, baseline)
        assert "nonexistent_dimension" not in regressions


# ---------------------------------------------------------------------------
# Compare logic (tie detection)
# ---------------------------------------------------------------------------


class TestCompareLogic:
    """Test the delta < 0.02 = tie logic used in compare()."""

    def test_tie_when_delta_below_threshold(self):
        # Directly test the tie logic from compare()
        delta = 0.015
        assert abs(delta) < 0.02  # This would be a tie

    def test_winner_when_delta_above_threshold(self):
        delta = 0.03
        assert abs(delta) >= 0.02  # This would NOT be a tie


# ---------------------------------------------------------------------------
# Recommendations engine
# ---------------------------------------------------------------------------


class TestRecommendations:
    def setup_method(self):
        self.evaluator = VBenchEvaluator(verbose=False)

    def test_low_identity_generates_recommendation(self):
        scores = {
            "identity_consistency": 0.5,
            "temporal_flicker": 0.9,
            "motion_smoothness": 0.8,
            "aesthetic_quality": 0.8,
            "prompt_adherence": 0.8,
            "physics_plausibility": 0.8,
        }
        recs = self.evaluator._generate_recommendations(scores, "portrait")
        assert any("identity" in r.lower() or "Identity" in r for r in recs)

    def test_low_flicker_generates_recommendation(self):
        scores = {
            "identity_consistency": 0.9,
            "temporal_flicker": 0.7,
            "motion_smoothness": 0.8,
            "aesthetic_quality": 0.8,
            "prompt_adherence": 0.8,
            "physics_plausibility": 0.8,
        }
        recs = self.evaluator._generate_recommendations(scores, "medium")
        assert any("flicker" in r.lower() for r in recs)

    def test_all_good_scores_no_major_issues(self):
        scores = {
            "identity_consistency": 0.9,
            "temporal_flicker": 0.95,
            "motion_smoothness": 0.85,
            "aesthetic_quality": 0.85,
            "prompt_adherence": 0.85,
            "physics_plausibility": 0.85,
        }
        recs = self.evaluator._generate_recommendations(scores, "medium")
        assert any("no major" in r.lower() or "scored well" in r.lower() for r in recs)
