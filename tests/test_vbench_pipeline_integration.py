"""Integration tests: vbench evaluation → mapping → quality tracker storage."""

import pytest

from quality_tracker import QualityTracker, VBenchResult as TrackerResult, map_vbench_result
from vbench_evaluator import VBenchResult as EvalResult


class TestVbenchPipelineIntegration:
    """End-to-end: evaluator result → map → log → retrieve via baseline."""

    def test_mapped_result_stored_correctly(self, quality_tracker):
        eval_result = EvalResult(
            identity_consistency=0.92,
            temporal_flicker=0.85,
            motion_smoothness=0.78,
            aesthetic_quality=0.80,
            prompt_adherence=0.88,
            physics_plausibility=0.65,
            overall_score=0.82,
        )
        mapped = map_vbench_result(eval_result)

        quality_tracker.log_shot_quality(
            shot_id="shot_int_1",
            video_id="vid_001",
            shot_type="close-up",
            target_api="kling",
            vbench_result=mapped,
        )

        # get_baseline returns avg over last N shots (only 1 shot here)
        baseline = quality_tracker.get_baseline(window=10)
        assert baseline["identity_score"] == pytest.approx(0.92, abs=1e-6)
        assert baseline["flicker_score"] == pytest.approx(0.85, abs=1e-6)
        assert baseline["motion_score"] == pytest.approx(0.78, abs=1e-6)
        assert baseline["aesthetic_score"] == pytest.approx(0.80, abs=1e-6)
        assert baseline["prompt_adherence_score"] == pytest.approx(0.88, abs=1e-6)
        assert baseline["physics_score"] == pytest.approx(0.65, abs=1e-6)
        assert baseline["overall_vbench"] == pytest.approx(0.82, abs=1e-6)

    def test_multiple_shots_averaged_baseline(self, quality_tracker):
        for i, overall in enumerate([0.80, 0.90]):
            mapped = map_vbench_result(EvalResult(overall_score=overall))
            quality_tracker.log_shot_quality(
                shot_id=f"shot_avg_{i}",
                video_id="vid_avg",
                shot_type="medium",
                target_api="runway",
                vbench_result=mapped,
            )

        baseline = quality_tracker.get_baseline(window=10)
        assert baseline["overall_vbench"] == pytest.approx(0.85, abs=1e-6)

    def test_dict_source_round_trips(self, quality_tracker):
        src = {
            "identity_consistency": 0.77,
            "temporal_flicker": 0.66,
            "motion_smoothness": 0.55,
            "aesthetic_quality": 0.44,
            "prompt_adherence": 0.33,
            "physics_plausibility": 0.22,
            "overall_score": 0.50,
        }
        mapped = map_vbench_result(src)
        quality_tracker.log_shot_quality(
            shot_id="shot_dict_1",
            video_id="vid_dict",
            shot_type="wide",
            target_api="sora",
            vbench_result=mapped,
        )

        baseline = quality_tracker.get_baseline(window=10)
        assert baseline["identity_score"] == pytest.approx(0.77, abs=1e-6)
        assert baseline["overall_vbench"] == pytest.approx(0.50, abs=1e-6)

    def test_regression_detection_with_mapped_result(self, quality_tracker):
        """Mapping preserves values accurately enough for regression checks."""
        # Log a good baseline shot
        good = map_vbench_result(EvalResult(
            identity_consistency=0.90,
            temporal_flicker=0.90,
            motion_smoothness=0.90,
            aesthetic_quality=0.90,
            prompt_adherence=0.90,
            physics_plausibility=0.90,
            overall_score=0.90,
        ))
        quality_tracker.log_shot_quality(
            shot_id="shot_good",
            video_id="vid_reg",
            shot_type="wide",
            target_api="kling",
            vbench_result=good,
        )

        # Check a degraded result triggers regression
        bad = map_vbench_result(EvalResult(
            identity_consistency=0.50,
            temporal_flicker=0.50,
            motion_smoothness=0.50,
            aesthetic_quality=0.50,
            prompt_adherence=0.50,
            physics_plausibility=0.50,
            overall_score=0.50,
        ))
        alerts = quality_tracker.check_regression(bad, tolerance=0.05)
        assert len(alerts) > 0
        dims_alerted = {a.dimension for a in alerts}
        assert "identity_score" in dims_alerted
        assert "overall_vbench" in dims_alerted
