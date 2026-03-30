"""
Offline Parameter Sweep Framework
===================================
Systematically varies tunable parameters and records quality metrics
to generate data for parameter tuning. No API calls needed.

Usage:
    pytest tests/test_parameter_sweep.py -v          # run as tests
    python tests/test_parameter_sweep.py             # run standalone, export CSV
"""

import sys
import os
import json
import csv
import tempfile
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest

from identity_types import SHOT_TYPE_THRESHOLDS, get_threshold_for_shot
from quality_tracker import QualityTracker, VBenchResult


# ---------------------------------------------------------------------------
# Sweep result container
# ---------------------------------------------------------------------------


@dataclass
class SweepResult:
    """Single data point from a parameter sweep."""
    sweep_name: str
    parameter_name: str
    parameter_value: float
    shot_type: str
    metric_name: str
    metric_value: float
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Synthetic similarity distribution simulator
# ---------------------------------------------------------------------------


def simulate_identity_checks(
    threshold: float,
    shot_type: str,
    n_samples: int = 200,
    rng_seed: int = 42,
) -> Dict[str, float]:
    """
    Simulate identity validation against synthetic similarity distributions.

    Different shot types have different natural similarity distributions:
    - portrait: mean=0.72, std=0.10 (clearer faces -> higher similarity)
    - medium:   mean=0.65, std=0.12
    - wide:     mean=0.55, std=0.15 (smaller faces -> more variance)
    - action:   mean=0.60, std=0.14 (motion blur reduces similarity)

    Returns: {
        "pass_rate": float,      # fraction passing threshold
        "mean_similarity": float,
        "false_reject_rate": float,  # good samples incorrectly rejected
    }
    """
    distributions = {
        "portrait": (0.72, 0.10),
        "medium": (0.65, 0.12),
        "wide": (0.55, 0.15),
        "action": (0.60, 0.14),
        "landscape": (0.0, 0.0),
    }

    mean, std = distributions.get(shot_type, distributions["medium"])
    if shot_type == "landscape":
        return {"pass_rate": 1.0, "mean_similarity": 0.0, "false_reject_rate": 0.0}

    rng = np.random.RandomState(rng_seed)
    similarities = rng.normal(mean, std, n_samples)
    similarities = np.clip(similarities, 0.0, 1.0)

    passes = similarities >= threshold
    pass_rate = float(np.mean(passes))

    # "Good" samples are those with similarity >= 0.5 (truly matching)
    good_mask = similarities >= 0.5
    if good_mask.sum() > 0:
        false_reject_rate = float(1.0 - np.mean(passes[good_mask]))
    else:
        false_reject_rate = 0.0

    return {
        "pass_rate": round(pass_rate, 4),
        "mean_similarity": round(float(np.mean(similarities)), 4),
        "false_reject_rate": round(false_reject_rate, 4),
    }


# ---------------------------------------------------------------------------
# ParameterSweepRunner
# ---------------------------------------------------------------------------


class ParameterSweepRunner:
    """Runs offline parameter sweeps and collects structured results."""

    def __init__(self):
        self.results: List[SweepResult] = []

    def sweep_identity_thresholds(self) -> List[SweepResult]:
        """
        Sweep identity thresholds across shot types, modes, and attempts.
        Records pass_rate and false_reject_rate at each threshold level.
        """
        results = []
        shot_types = ["portrait", "medium", "wide", "action"]
        modes = ["strict", "standard", "lenient"]

        for shot_type in shot_types:
            for mode in modes:
                for attempt in range(4):
                    threshold = get_threshold_for_shot(
                        shot_type, mode=mode, attempt=attempt, max_attempts=4
                    )
                    sim_results = simulate_identity_checks(threshold, shot_type)

                    results.append(SweepResult(
                        sweep_name="identity_thresholds",
                        parameter_name=f"threshold_{mode}",
                        parameter_value=threshold,
                        shot_type=shot_type,
                        metric_name="pass_rate",
                        metric_value=sim_results["pass_rate"],
                        extra={
                            "mode": mode,
                            "attempt": attempt,
                            "false_reject_rate": sim_results["false_reject_rate"],
                            "mean_similarity": sim_results["mean_similarity"],
                        },
                    ))

        self.results.extend(results)
        return results

    def sweep_custom_thresholds(self) -> List[SweepResult]:
        """
        Sweep custom threshold values from 0.30 to 0.85 in 0.05 steps
        to find optimal values per shot type.
        """
        results = []
        shot_types = ["portrait", "medium", "wide", "action"]

        for shot_type in shot_types:
            for threshold in np.arange(0.30, 0.86, 0.05):
                threshold = round(float(threshold), 2)
                sim_results = simulate_identity_checks(threshold, shot_type)

                results.append(SweepResult(
                    sweep_name="custom_thresholds",
                    parameter_name="identity_threshold",
                    parameter_value=threshold,
                    shot_type=shot_type,
                    metric_name="pass_rate",
                    metric_value=sim_results["pass_rate"],
                    extra={
                        "false_reject_rate": sim_results["false_reject_rate"],
                        "mean_similarity": sim_results["mean_similarity"],
                    },
                ))

        self.results.extend(results)
        return results

    def sweep_coherence_thresholds(self) -> List[SweepResult]:
        """
        Sweep color_drift and brightness_delta thresholds.
        Simulates how often corrections are triggered at different thresholds.
        """
        results = []
        rng = np.random.RandomState(42)

        # Simulate 100 shot-pair color drift values
        color_drifts = rng.beta(2, 5, 100)  # skewed toward low drift

        for threshold in np.arange(0.15, 0.51, 0.05):
            threshold = round(float(threshold), 2)
            trigger_rate = float(np.mean(color_drifts > threshold))

            results.append(SweepResult(
                sweep_name="coherence_thresholds",
                parameter_name="color_drift_threshold",
                parameter_value=threshold,
                shot_type="all",
                metric_name="trigger_rate",
                metric_value=round(trigger_rate, 4),
            ))

        # Simulate brightness deltas
        brightness_deltas = rng.exponential(0.08, 100)

        for threshold in np.arange(0.05, 0.31, 0.05):
            threshold = round(float(threshold), 2)
            trigger_rate = float(np.mean(brightness_deltas > threshold))

            results.append(SweepResult(
                sweep_name="coherence_thresholds",
                parameter_name="brightness_delta_threshold",
                parameter_value=threshold,
                shot_type="all",
                metric_name="trigger_rate",
                metric_value=round(trigger_rate, 4),
            ))

        self.results.extend(results)
        return results

    def sweep_vbench_weights(self) -> List[SweepResult]:
        """
        Test sensitivity of overall VBench score to weight redistribution.
        Uses fixed dimension scores, varies weight assignments.
        """
        results = []

        # Fixed dimension scores (representative "typical" shot)
        fixed_scores = {
            "identity_consistency": 0.75,
            "temporal_flicker": 0.90,
            "motion_smoothness": 0.70,
            "aesthetic_quality": 0.65,
            "prompt_adherence": 0.72,
            "physics_plausibility": 0.80,
        }
        dims = list(fixed_scores.keys())

        # Current weights
        current_weights = {
            "identity_consistency": 0.25,
            "temporal_flicker": 0.20,
            "motion_smoothness": 0.15,
            "aesthetic_quality": 0.15,
            "prompt_adherence": 0.15,
            "physics_plausibility": 0.10,
        }

        # For each dimension, test increasing its weight by 0.10 (taking from others proportionally)
        for target_dim in dims:
            for delta in [-0.10, -0.05, 0.0, 0.05, 0.10]:
                weights = dict(current_weights)
                original_w = weights[target_dim]
                new_w = max(0.05, min(0.40, original_w + delta))
                actual_delta = new_w - original_w

                if abs(actual_delta) < 0.001:
                    weights_adjusted = dict(weights)
                else:
                    # Redistribute delta across other dimensions proportionally
                    weights_adjusted = dict(weights)
                    weights_adjusted[target_dim] = new_w
                    other_dims = [d for d in dims if d != target_dim]
                    other_total = sum(weights[d] for d in other_dims)
                    for d in other_dims:
                        proportion = weights[d] / other_total
                        weights_adjusted[d] = max(0.05, weights[d] - actual_delta * proportion)

                    # Normalize to sum=1
                    total = sum(weights_adjusted.values())
                    weights_adjusted = {d: w / total for d, w in weights_adjusted.items()}

                overall = sum(fixed_scores[d] * weights_adjusted[d] for d in dims)

                results.append(SweepResult(
                    sweep_name="vbench_weights",
                    parameter_name=f"weight_{target_dim}",
                    parameter_value=round(weights_adjusted[target_dim], 3),
                    shot_type="all",
                    metric_name="overall_vbench",
                    metric_value=round(overall, 4),
                    extra={
                        "delta": delta,
                        "weights": {d: round(w, 3) for d, w in weights_adjusted.items()},
                    },
                ))

        self.results.extend(results)
        return results

    def sweep_denoise_range(self) -> List[SweepResult]:
        """
        Sweep denoise strength from 0.20 to 0.60.
        Simulates the trade-off: lower denoise = more temporal consistency
        but less creative freedom, modeled as inverse relationship.
        """
        results = []
        rng = np.random.RandomState(42)

        for denoise in np.arange(0.20, 0.61, 0.05):
            denoise = round(float(denoise), 2)

            # Model: consistency inversely proportional to denoise strength
            # creativity proportional to denoise strength
            consistency_score = 1.0 - denoise * 0.8  # 0.84 at 0.20, 0.52 at 0.60
            creativity_score = denoise * 1.2  # 0.24 at 0.20, 0.72 at 0.60

            # Add noise to simulate real-world variance
            consistency_score = np.clip(consistency_score + rng.normal(0, 0.05), 0, 1)
            creativity_score = np.clip(creativity_score + rng.normal(0, 0.05), 0, 1)

            # Composite: we want both consistency and creativity
            composite = 0.6 * consistency_score + 0.4 * creativity_score

            results.append(SweepResult(
                sweep_name="denoise_range",
                parameter_name="denoise_strength",
                parameter_value=denoise,
                shot_type="all",
                metric_name="composite_score",
                metric_value=round(float(composite), 4),
                extra={
                    "consistency": round(float(consistency_score), 4),
                    "creativity": round(float(creativity_score), 4),
                },
            ))

        self.results.extend(results)
        return results

    def export_csv(self, filepath: str):
        """Export all sweep results to CSV."""
        if not self.results:
            return

        fieldnames = [
            "sweep_name", "parameter_name", "parameter_value",
            "shot_type", "metric_name", "metric_value", "extra",
        ]

        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in self.results:
                row = asdict(r)
                row["extra"] = json.dumps(row["extra"])
                writer.writerow(row)

    def export_json(self, filepath: str):
        """Export all sweep results to JSON."""
        data = [asdict(r) for r in self.results]
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def get_summary(self) -> Dict[str, Any]:
        """Generate a summary of all sweeps."""
        summary = {}
        for r in self.results:
            sweep = r.sweep_name
            if sweep not in summary:
                summary[sweep] = {"count": 0, "parameters": set(), "shot_types": set()}
            summary[sweep]["count"] += 1
            summary[sweep]["parameters"].add(r.parameter_name)
            summary[sweep]["shot_types"].add(r.shot_type)

        # Convert sets to lists for JSON serialization
        for k, v in summary.items():
            v["parameters"] = sorted(v["parameters"])
            v["shot_types"] = sorted(v["shot_types"])

        return summary


# ---------------------------------------------------------------------------
# Pytest tests — validate sweep logic correctness
# ---------------------------------------------------------------------------


class TestSimulateIdentityChecks:
    def test_high_threshold_low_pass_rate(self):
        result = simulate_identity_checks(0.90, "portrait")
        assert result["pass_rate"] < 0.5

    def test_low_threshold_high_pass_rate(self):
        result = simulate_identity_checks(0.30, "portrait")
        assert result["pass_rate"] > 0.9

    def test_portrait_higher_pass_rate_than_wide(self):
        """Portrait has higher mean similarity -> higher pass rate at same threshold."""
        portrait = simulate_identity_checks(0.60, "portrait")
        wide = simulate_identity_checks(0.60, "wide")
        assert portrait["pass_rate"] > wide["pass_rate"]

    def test_landscape_always_passes(self):
        result = simulate_identity_checks(0.50, "landscape")
        assert result["pass_rate"] == 1.0

    def test_result_keys(self):
        result = simulate_identity_checks(0.65, "medium")
        assert "pass_rate" in result
        assert "mean_similarity" in result
        assert "false_reject_rate" in result

    def test_pass_rate_bounded(self):
        for shot_type in ["portrait", "medium", "wide", "action"]:
            for threshold in [0.3, 0.5, 0.7, 0.9]:
                result = simulate_identity_checks(threshold, shot_type)
                assert 0.0 <= result["pass_rate"] <= 1.0


class TestSweepIdentityThresholds:
    def test_generates_results(self):
        runner = ParameterSweepRunner()
        results = runner.sweep_identity_thresholds()
        assert len(results) > 0

    def test_covers_all_shot_types(self):
        runner = ParameterSweepRunner()
        results = runner.sweep_identity_thresholds()
        shot_types = {r.shot_type for r in results}
        assert {"portrait", "medium", "wide", "action"} <= shot_types

    def test_pass_rate_decreases_with_stricter_threshold(self):
        runner = ParameterSweepRunner()
        results = runner.sweep_identity_thresholds()
        # For portrait, attempt=0: strict should have lower pass rate than lenient
        portrait_strict = [r for r in results if r.shot_type == "portrait"
                          and r.extra.get("mode") == "strict" and r.extra.get("attempt") == 0]
        portrait_lenient = [r for r in results if r.shot_type == "portrait"
                           and r.extra.get("mode") == "lenient" and r.extra.get("attempt") == 0]
        if portrait_strict and portrait_lenient:
            assert portrait_strict[0].metric_value <= portrait_lenient[0].metric_value


class TestSweepCoherenceThresholds:
    def test_generates_results(self):
        runner = ParameterSweepRunner()
        results = runner.sweep_coherence_thresholds()
        assert len(results) > 0

    def test_higher_threshold_lower_trigger_rate(self):
        runner = ParameterSweepRunner()
        results = runner.sweep_coherence_thresholds()
        color_results = [r for r in results if r.parameter_name == "color_drift_threshold"]
        if len(color_results) >= 2:
            low_thresh = min(color_results, key=lambda r: r.parameter_value)
            high_thresh = max(color_results, key=lambda r: r.parameter_value)
            assert low_thresh.metric_value >= high_thresh.metric_value


class TestSweepVbenchWeights:
    def test_generates_results(self):
        runner = ParameterSweepRunner()
        results = runner.sweep_vbench_weights()
        assert len(results) > 0

    def test_overall_scores_bounded(self):
        runner = ParameterSweepRunner()
        results = runner.sweep_vbench_weights()
        for r in results:
            assert 0.0 <= r.metric_value <= 1.0, f"Overall VBench {r.metric_value} out of bounds"


class TestSweepDenoiseRange:
    def test_generates_results(self):
        runner = ParameterSweepRunner()
        results = runner.sweep_denoise_range()
        assert len(results) > 0

    def test_denoise_values_in_range(self):
        runner = ParameterSweepRunner()
        results = runner.sweep_denoise_range()
        for r in results:
            assert 0.20 <= r.parameter_value <= 0.60


class TestExport:
    def test_csv_export(self, tmp_path):
        runner = ParameterSweepRunner()
        runner.sweep_identity_thresholds()
        filepath = str(tmp_path / "sweep.csv")
        runner.export_csv(filepath)
        assert os.path.exists(filepath)
        with open(filepath) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) > 0

    def test_json_export(self, tmp_path):
        runner = ParameterSweepRunner()
        runner.sweep_coherence_thresholds()
        filepath = str(tmp_path / "sweep.json")
        runner.export_json(filepath)
        assert os.path.exists(filepath)
        with open(filepath) as f:
            data = json.load(f)
        assert len(data) > 0

    def test_summary(self):
        runner = ParameterSweepRunner()
        runner.sweep_identity_thresholds()
        runner.sweep_coherence_thresholds()
        summary = runner.get_summary()
        assert "identity_thresholds" in summary
        assert "coherence_thresholds" in summary
        assert summary["identity_thresholds"]["count"] > 0


class TestQualityTrackerIntegration:
    """Verify sweep results can be stored in the existing QualityTracker."""

    def test_log_sweep_results_as_shot_quality(self):
        tracker = QualityTracker(db_path=":memory:")
        try:
            # Simulate logging sweep results as shot quality records
            for i, threshold in enumerate([0.55, 0.65, 0.75]):
                sim = simulate_identity_checks(threshold, "portrait")
                vbench = VBenchResult(
                    identity_score=sim["pass_rate"],
                    overall_vbench=sim["pass_rate"] * 0.9,
                )
                tracker.log_shot_quality(
                    shot_id=f"sweep_portrait_{i}",
                    video_id="sweep_run_001",
                    shot_type="portrait",
                    target_api="SWEEP_TEST",
                    vbench_result=vbench,
                )

            # Verify data persisted
            baseline = tracker.get_baseline(window=10)
            assert baseline["identity_score"] > 0
            assert baseline["overall_vbench"] > 0
        finally:
            tracker.close()


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("=" * 60)
    print("Parameter Sweep Runner — Offline Mode")
    print("=" * 60)

    runner = ParameterSweepRunner()

    print("\n1. Sweeping identity thresholds...")
    results = runner.sweep_identity_thresholds()
    print(f"   Generated {len(results)} data points")

    print("\n2. Sweeping custom thresholds...")
    results = runner.sweep_custom_thresholds()
    print(f"   Generated {len(results)} data points")

    print("\n3. Sweeping coherence thresholds...")
    results = runner.sweep_coherence_thresholds()
    print(f"   Generated {len(results)} data points")

    print("\n4. Sweeping VBench weights...")
    results = runner.sweep_vbench_weights()
    print(f"   Generated {len(results)} data points")

    print("\n5. Sweeping denoise range...")
    results = runner.sweep_denoise_range()
    print(f"   Generated {len(results)} data points")

    # Export
    csv_path = os.path.join(os.path.dirname(__file__), "..", "sweep_results.csv")
    json_path = os.path.join(os.path.dirname(__file__), "..", "sweep_results.json")

    runner.export_csv(csv_path)
    runner.export_json(json_path)

    print(f"\nTotal results: {len(runner.results)}")
    print(f"Exported to: {csv_path}")
    print(f"Exported to: {json_path}")

    summary = runner.get_summary()
    print("\nSummary:")
    for sweep_name, info in summary.items():
        print(f"  {sweep_name}: {info['count']} points, "
              f"params={info['parameters']}, types={info['shot_types']}")
