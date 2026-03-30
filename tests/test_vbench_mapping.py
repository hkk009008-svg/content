"""Tests for vbench_evaluator → quality_tracker field mapping."""

import pytest

from quality_tracker import (
    VBenchResult,
    VBENCH_EVALUATOR_FIELD_MAP,
    map_vbench_result,
)


# ---------------------------------------------------------------------------
# Mapping from dataclass
# ---------------------------------------------------------------------------


class TestMapVbenchResultFromDataclass:
    """map_vbench_result with a vbench_evaluator.VBenchResult dataclass."""

    def test_all_fields_mapped(self, evaluator_vbench_result):
        result = map_vbench_result(evaluator_vbench_result)
        assert isinstance(result, VBenchResult)
        assert result.identity_score == 0.95
        assert result.flicker_score == 0.88
        assert result.motion_score == 0.76
        assert result.aesthetic_score == 0.82
        assert result.prompt_adherence_score == 0.91
        assert result.physics_score == 0.70
        assert result.overall_vbench == 0.85

    def test_default_zeros(self):
        """Evaluator result with all defaults maps to tracker zeros."""
        from vbench_evaluator import VBenchResult as EvalResult

        result = map_vbench_result(EvalResult())
        assert result.overall_vbench == 0.0
        assert result.identity_score == 0.0

    def test_returns_quality_tracker_type(self, evaluator_vbench_result):
        result = map_vbench_result(evaluator_vbench_result)
        assert type(result).__module__ == "quality_tracker"


# ---------------------------------------------------------------------------
# Mapping from dict
# ---------------------------------------------------------------------------


class TestMapVbenchResultFromDict:
    """map_vbench_result with a plain dictionary."""

    def test_dict_all_keys(self):
        src = {
            "identity_consistency": 0.90,
            "temporal_flicker": 0.80,
            "motion_smoothness": 0.70,
            "aesthetic_quality": 0.60,
            "prompt_adherence": 0.50,
            "physics_plausibility": 0.40,
            "overall_score": 0.65,
        }
        result = map_vbench_result(src)
        assert result.identity_score == 0.90
        assert result.flicker_score == 0.80
        assert result.motion_score == 0.70
        assert result.aesthetic_score == 0.60
        assert result.prompt_adherence_score == 0.50
        assert result.physics_score == 0.40
        assert result.overall_vbench == 0.65

    def test_dict_missing_keys_default_zero(self):
        result = map_vbench_result({"identity_consistency": 0.5})
        assert result.identity_score == 0.5
        assert result.flicker_score == 0.0
        assert result.overall_vbench == 0.0

    def test_empty_dict(self):
        result = map_vbench_result({})
        for dim in [
            "identity_score",
            "flicker_score",
            "motion_score",
            "aesthetic_score",
            "prompt_adherence_score",
            "physics_score",
            "overall_vbench",
        ]:
            assert getattr(result, dim) == 0.0


# ---------------------------------------------------------------------------
# Field map completeness
# ---------------------------------------------------------------------------


class TestFieldMapConsistency:
    """Ensure the mapping covers all evaluator and tracker fields."""

    def test_all_evaluator_dimensions_mapped(self):
        from vbench_evaluator import DIMENSION_WEIGHTS

        for dim in DIMENSION_WEIGHTS:
            assert dim in VBENCH_EVALUATOR_FIELD_MAP, f"{dim} not in field map"

    def test_all_tracker_dimensions_present(self):
        from quality_tracker import VBENCH_DIMENSIONS

        mapped_targets = set(VBENCH_EVALUATOR_FIELD_MAP.values())
        for dim in VBENCH_DIMENSIONS:
            assert dim in mapped_targets, f"{dim} not a mapping target"

    def test_map_is_bijective(self):
        """Each evaluator field maps to a unique tracker field."""
        values = list(VBENCH_EVALUATOR_FIELD_MAP.values())
        assert len(values) == len(set(values)), "Duplicate target fields"
