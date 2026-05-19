import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from quality_tracker import QualityTracker, VBenchResult, RegressionAlert, VBENCH_DIMENSIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracker() -> QualityTracker:
    """Create an in-memory QualityTracker for testing."""
    return QualityTracker(db_path=":memory:")


def _log_sample_shot(
    tracker: QualityTracker,
    shot_id: str = "shot_001",
    video_id: str = "vid_001",
    shot_type: str = "closeup",
    target_api: str = "kling",
    vbench: VBenchResult | None = None,
    identity_similarity: float = 0.85,
    coherence_score: float = 0.9,
    generation_cost: float = 0.05,
    llm_cost: float = 0.01,
    attempt: int = 1,
) -> None:
    tracker.log_shot_quality(
        shot_id=shot_id,
        video_id=video_id,
        shot_type=shot_type,
        target_api=target_api,
        vbench_result=vbench,
        identity_similarity=identity_similarity,
        coherence_score=coherence_score,
        generation_cost=generation_cost,
        llm_cost=llm_cost,
        attempt=attempt,
    )


# ---------------------------------------------------------------------------
# 1. Initialization
# ---------------------------------------------------------------------------

class TestInit:
    def test_initializes_with_memory_db(self):
        tracker = _make_tracker()
        assert tracker.db_path == ":memory:"
        assert tracker._persistent_conn is not None


# ---------------------------------------------------------------------------
# 2-3. log_shot_quality
# ---------------------------------------------------------------------------

class TestLogShotQuality:
    def test_stores_and_retrieves_shot(self):
        tracker = _make_tracker()
        _log_sample_shot(tracker)
        # Verify data exists via get_video_cost_summary
        summary = tracker.get_video_cost_summary("vid_001")
        assert summary["shot_count"] == 1
        assert summary["generation_cost_usd"] == pytest.approx(0.05)
        assert summary["llm_cost_usd"] == pytest.approx(0.01)
        assert summary["total_cost_usd"] == pytest.approx(0.06)

    def test_stores_vbench_dimensions(self):
        tracker = _make_tracker()
        vb = VBenchResult(
            identity_score=0.9,
            flicker_score=0.85,
            motion_score=0.8,
            aesthetic_score=0.75,
            prompt_adherence_score=0.7,
            physics_score=0.65,
            overall_vbench=0.78,
        )
        _log_sample_shot(tracker, vbench=vb)

        # Retrieve via baseline (window=1 gives us that exact shot)
        baseline = tracker.get_baseline(window=1)
        assert baseline["identity_score"] == pytest.approx(0.9)
        assert baseline["flicker_score"] == pytest.approx(0.85)
        assert baseline["motion_score"] == pytest.approx(0.8)
        assert baseline["aesthetic_score"] == pytest.approx(0.75)
        assert baseline["prompt_adherence_score"] == pytest.approx(0.7)
        assert baseline["physics_score"] == pytest.approx(0.65)
        assert baseline["overall_vbench"] == pytest.approx(0.78)


# ---------------------------------------------------------------------------
# 4-6. get_baseline
# ---------------------------------------------------------------------------

class TestGetBaseline:
    def test_no_data_returns_zeros(self):
        tracker = _make_tracker()
        baseline = tracker.get_baseline()
        for dim in VBENCH_DIMENSIONS:
            assert baseline[dim] == 0.0

    def test_computes_correct_averages(self):
        tracker = _make_tracker()
        vb1 = VBenchResult(overall_vbench=0.8, identity_score=0.9)
        vb2 = VBenchResult(overall_vbench=0.6, identity_score=0.7)
        _log_sample_shot(tracker, shot_id="s1", vbench=vb1)
        _log_sample_shot(tracker, shot_id="s2", vbench=vb2)

        baseline = tracker.get_baseline(window=20)
        assert baseline["overall_vbench"] == pytest.approx(0.7)
        assert baseline["identity_score"] == pytest.approx(0.8)

    def test_respects_window_size(self):
        tracker = _make_tracker()
        # Log 5 shots: first 3 with low scores, last 2 with high scores
        for i in range(3):
            vb = VBenchResult(overall_vbench=0.2)
            _log_sample_shot(tracker, shot_id=f"old_{i}", vbench=vb)
        for i in range(2):
            vb = VBenchResult(overall_vbench=0.9)
            _log_sample_shot(tracker, shot_id=f"new_{i}", vbench=vb)

        # Window of 2 should only capture the two most recent (0.9 each)
        baseline = tracker.get_baseline(window=2)
        assert baseline["overall_vbench"] == pytest.approx(0.9)

        # Window of 5 should average all: (0.2*3 + 0.9*2) / 5 = 2.4/5 = 0.48
        baseline_all = tracker.get_baseline(window=5)
        assert baseline_all["overall_vbench"] == pytest.approx(0.48)


# ---------------------------------------------------------------------------
# 7-9. check_regression
# ---------------------------------------------------------------------------

class TestCheckRegression:
    def _setup_baseline(self, tracker: QualityTracker, score: float = 0.8) -> None:
        """Populate tracker with shots so baseline settles at *score*."""
        for i in range(5):
            vb = VBenchResult(
                identity_score=score,
                flicker_score=score,
                motion_score=score,
                aesthetic_score=score,
                prompt_adherence_score=score,
                physics_score=score,
                overall_vbench=score,
            )
            _log_sample_shot(tracker, shot_id=f"base_{i}", vbench=vb)

    def test_no_regression_when_above_baseline(self):
        tracker = _make_tracker()
        self._setup_baseline(tracker, score=0.8)
        current = VBenchResult(
            identity_score=0.85,
            flicker_score=0.85,
            motion_score=0.85,
            aesthetic_score=0.85,
            prompt_adherence_score=0.85,
            physics_score=0.85,
            overall_vbench=0.85,
        )
        alerts = tracker.check_regression(current, tolerance=0.05)
        assert alerts == []

    def test_detects_regression_below_tolerance(self):
        tracker = _make_tracker()
        self._setup_baseline(tracker, score=0.8)
        # Drop identity_score well below baseline - tolerance (0.8 - 0.05 = 0.75)
        current = VBenchResult(
            identity_score=0.5,
            flicker_score=0.85,
            motion_score=0.85,
            aesthetic_score=0.85,
            prompt_adherence_score=0.85,
            physics_score=0.85,
            overall_vbench=0.85,
        )
        alerts = tracker.check_regression(current, tolerance=0.05)
        assert len(alerts) == 1
        assert alerts[0].dimension == "identity_score"
        assert alerts[0].current == pytest.approx(0.5)
        assert alerts[0].baseline == pytest.approx(0.8)
        assert alerts[0].delta == pytest.approx(-0.3)

    def test_tolerance_boundary_no_alert(self):
        tracker = _make_tracker()
        self._setup_baseline(tracker, score=0.8)
        # Exactly at baseline - tolerance (0.75) should NOT trigger alert
        current = VBenchResult(
            identity_score=0.75,
            flicker_score=0.75,
            motion_score=0.75,
            aesthetic_score=0.75,
            prompt_adherence_score=0.75,
            physics_score=0.75,
            overall_vbench=0.75,
        )
        alerts = tracker.check_regression(current, tolerance=0.05)
        assert alerts == []


# ---------------------------------------------------------------------------
# 10. get_api_quality_stats
# ---------------------------------------------------------------------------

class TestGetApiQualityStats:
    def test_groups_by_api_and_shot_type(self):
        tracker = _make_tracker()
        vb1 = VBenchResult(overall_vbench=0.9, identity_score=0.85)
        vb2 = VBenchResult(overall_vbench=0.7, identity_score=0.65)
        vb3 = VBenchResult(overall_vbench=0.8, identity_score=0.75)

        _log_sample_shot(tracker, shot_id="s1", target_api="kling", shot_type="closeup", vbench=vb1, generation_cost=0.10)
        _log_sample_shot(tracker, shot_id="s2", target_api="kling", shot_type="wide", vbench=vb2, generation_cost=0.08)
        _log_sample_shot(tracker, shot_id="s3", target_api="sora", shot_type="closeup", vbench=vb3, generation_cost=0.20)

        stats = tracker.get_api_quality_stats()

        assert "kling" in stats
        assert "sora" in stats
        assert "closeup" in stats["kling"]
        assert "wide" in stats["kling"]
        assert "closeup" in stats["sora"]

        assert stats["kling"]["closeup"]["avg_vbench"] == pytest.approx(0.9)
        assert stats["kling"]["closeup"]["avg_identity"] == pytest.approx(0.85)
        assert stats["kling"]["closeup"]["count"] == 1

        assert stats["kling"]["wide"]["avg_vbench"] == pytest.approx(0.7)
        assert stats["sora"]["closeup"]["avg_vbench"] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# 11-12. get_video_cost_summary
# ---------------------------------------------------------------------------

class TestGetVideoCostSummary:
    def test_existing_video(self):
        tracker = _make_tracker()
        _log_sample_shot(tracker, shot_id="s1", video_id="vid_A", generation_cost=0.10, llm_cost=0.02)
        _log_sample_shot(tracker, shot_id="s2", video_id="vid_A", generation_cost=0.15, llm_cost=0.03)

        summary = tracker.get_video_cost_summary("vid_A")
        assert summary["shot_count"] == 2
        assert summary["generation_cost_usd"] == pytest.approx(0.25)
        assert summary["llm_cost_usd"] == pytest.approx(0.05)
        assert summary["total_cost_usd"] == pytest.approx(0.30)

    def test_nonexistent_video_returns_zeros(self):
        tracker = _make_tracker()
        summary = tracker.get_video_cost_summary("does_not_exist")
        assert summary["shot_count"] == 0
        assert summary["total_cost_usd"] == 0.0
        assert summary["generation_cost_usd"] == 0.0
        assert summary["llm_cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# 13-14. get_batch_quality_summary
# ---------------------------------------------------------------------------

class TestGetBatchQualitySummary:
    def test_no_data_returns_message(self):
        tracker = _make_tracker()
        result = tracker.get_batch_quality_summary()
        assert result == "No shot quality data available yet."

    def test_with_data_returns_formatted_string(self):
        tracker = _make_tracker()
        vb = VBenchResult(
            overall_vbench=0.85,
            identity_score=0.9,
            flicker_score=0.8,
            motion_score=0.75,
            aesthetic_score=0.7,
            prompt_adherence_score=0.65,
            physics_score=0.6,
        )
        for i in range(5):
            _log_sample_shot(
                tracker,
                shot_id=f"s_{i}",
                target_api="kling",
                vbench=vb,
                generation_cost=0.10,
            )

        result = tracker.get_batch_quality_summary(window=10)
        assert "Batch Quality Summary" in result
        assert "kling" in result
        assert "Overall VBench" in result
        assert "Identity" in result
        assert "Trend" in result
        assert "Cost Efficiency" in result


# ---------------------------------------------------------------------------
# 15. get_quality_leaderboard
# ---------------------------------------------------------------------------

class TestGetQualityLeaderboard:
    def test_returns_apis_sorted_by_quality(self):
        tracker = _make_tracker()
        # Kling: high quality
        for i in range(3):
            vb = VBenchResult(overall_vbench=0.9)
            _log_sample_shot(tracker, shot_id=f"k_{i}", target_api="kling", vbench=vb, generation_cost=0.10)

        # Sora: medium quality
        for i in range(3):
            vb = VBenchResult(overall_vbench=0.7)
            _log_sample_shot(tracker, shot_id=f"s_{i}", target_api="sora", vbench=vb, generation_cost=0.20)

        # Veo: low quality
        for i in range(3):
            vb = VBenchResult(overall_vbench=0.5)
            _log_sample_shot(tracker, shot_id=f"v_{i}", target_api="veo", vbench=vb, generation_cost=0.05)

        leaderboard = tracker.get_quality_leaderboard()
        assert len(leaderboard) == 3

        # Sorted descending by avg_quality
        assert leaderboard[0]["target_api"] == "kling"
        assert leaderboard[1]["target_api"] == "sora"
        assert leaderboard[2]["target_api"] == "veo"

        assert leaderboard[0]["avg_quality"] == pytest.approx(0.9)
        assert leaderboard[1]["avg_quality"] == pytest.approx(0.7)
        assert leaderboard[2]["avg_quality"] == pytest.approx(0.5)

        # Check quality_per_dollar is computed (avg_cost includes llm_cost default of 0.01)
        assert leaderboard[0]["avg_cost"] == pytest.approx(0.11)
        assert leaderboard[0]["quality_per_dollar"] == pytest.approx(0.9 / 0.11)
