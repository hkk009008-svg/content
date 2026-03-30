import pathlib
import tempfile
import unittest

from quality_tracker import QualityTracker, VBenchResult


class QualityTrackerTests(unittest.TestCase):
    def test_file_backed_tracker_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = pathlib.Path(tmpdir) / "experiments.db"
            tracker = QualityTracker(str(db_path))

            tracker.log_shot_quality(
                shot_id="shot-1",
                video_id="video-1",
                shot_type="portrait",
                target_api="kling",
                vbench_result=VBenchResult(
                    identity_score=0.91,
                    flicker_score=0.82,
                    motion_score=0.74,
                    aesthetic_score=0.88,
                    prompt_adherence_score=0.79,
                    physics_score=0.77,
                    overall_vbench=0.84,
                ),
                identity_similarity=0.93,
                coherence_score=0.86,
                generation_cost=1.25,
                llm_cost=0.15,
            )

            baseline = tracker.get_baseline()
            self.assertAlmostEqual(baseline["overall_vbench"], 0.84)
            self.assertAlmostEqual(baseline["identity_score"], 0.91)

            cost_summary = tracker.get_video_cost_summary("video-1")
            self.assertEqual(cost_summary["shot_count"], 1)
            self.assertAlmostEqual(cost_summary["total_cost_usd"], 1.40)
            self.assertAlmostEqual(cost_summary["generation_cost_usd"], 1.25)
            self.assertAlmostEqual(cost_summary["llm_cost_usd"], 0.15)

            leaderboard = tracker.get_quality_leaderboard()
            self.assertEqual(len(leaderboard), 1)
            self.assertEqual(leaderboard[0]["target_api"], "kling")

    def test_in_memory_tracker_keeps_data_between_calls(self) -> None:
        tracker = QualityTracker(":memory:")

        tracker.log_shot_quality(
            shot_id="shot-2",
            video_id="video-2",
            shot_type="wide",
            target_api="runway",
            vbench_result=VBenchResult(
                identity_score=0.63,
                overall_vbench=0.66,
            ),
        )

        stats = tracker.get_api_quality_stats()
        self.assertIn("runway", stats)
        self.assertIn("wide", stats["runway"])
        self.assertEqual(stats["runway"]["wide"]["count"], 1)
        self.assertAlmostEqual(stats["runway"]["wide"]["avg_vbench"], 0.66)


if __name__ == "__main__":
    unittest.main()
