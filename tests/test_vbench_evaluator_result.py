"""Tests for vbench_evaluator.VBenchResult dataclass."""

import pytest

from vbench_evaluator import VBenchResult, DIMENSION_WEIGHTS


class TestVBenchResultDataclass:
    """Verify the evaluator's VBenchResult fields and helpers."""

    def test_default_values(self):
        r = VBenchResult()
        assert r.identity_consistency == 0.0
        assert r.temporal_flicker == 0.0
        assert r.motion_smoothness == 0.0
        assert r.aesthetic_quality == 0.0
        assert r.prompt_adherence == 0.0
        assert r.physics_plausibility == 0.0
        assert r.overall_score == 0.0
        assert r.dimension_scores == {}
        assert r.recommendations == []
        assert r.evaluation_cost_usd == 0.0

    def test_custom_values(self, evaluator_vbench_result):
        r = evaluator_vbench_result
        assert r.identity_consistency == 0.95
        assert r.overall_score == 0.85

    def test_to_dict(self, evaluator_vbench_result):
        d = evaluator_vbench_result.to_dict()
        assert isinstance(d, dict)
        assert d["identity_consistency"] == 0.95
        assert d["overall_score"] == 0.85

    def test_summary_contains_dimensions(self, evaluator_vbench_result):
        s = evaluator_vbench_result.summary()
        assert "Identity Consistency" in s
        assert "Temporal Flicker" in s
        assert "Overall Score" in s


class TestDimensionWeights:
    """Validate weight configuration."""

    def test_weights_sum_to_one(self):
        total = sum(DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_all_weights_positive(self):
        for dim, w in DIMENSION_WEIGHTS.items():
            assert w > 0, f"{dim} has non-positive weight"

    def test_six_dimensions(self):
        assert len(DIMENSION_WEIGHTS) == 6
