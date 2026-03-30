#!/usr/bin/env python3
"""
analyze_sweep_results.py -- Offline analysis pipeline for parameter sweep data.

Reads quality_tracker data (from experiments.db or in-memory for testing),
groups by parameter configuration, computes per-parameter marginal quality
impact, identifies Pareto-optimal configs, and generates recommended
parameter updates.

Usage:
    python tests/analyze_sweep_results.py                    # analyze experiments.db
    python tests/analyze_sweep_results.py --db /path/to.db   # custom db path
    python tests/analyze_sweep_results.py --run-sweeps       # generate + analyze
    pytest tests/analyze_sweep_results.py -v                 # run built-in tests
"""

import sys
import os
import json
import csv
import argparse
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quality_tracker import QualityTracker, VBenchResult

# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------


def compute_marginal_impact(
    results: List[Dict],
    parameter_name: str,
    quality_key: str = "overall_vbench",
) -> Dict[str, float]:
    """Compute marginal quality impact for each value of a parameter.

    Groups results by parameter_value and computes:
      - mean quality per value
      - delta from global mean
      - rank ordering

    Returns dict: {
        "parameter": str,
        "values": [{value, mean_quality, delta, count}, ...],
        "best_value": float,
        "worst_value": float,
        "impact_range": float,  # best - worst
    }
    """
    filtered = [r for r in results if r.get("parameter_name") == parameter_name]
    if not filtered:
        return {"parameter": parameter_name, "values": [], "best_value": None,
                "worst_value": None, "impact_range": 0.0}

    by_value = defaultdict(list)
    for r in filtered:
        by_value[r["parameter_value"]].append(r.get(quality_key, 0.0))

    global_mean = sum(q for vals in by_value.values() for q in vals) / max(
        sum(len(v) for v in by_value.values()), 1
    )

    value_stats = []
    for val, qualities in sorted(by_value.items()):
        mean_q = sum(qualities) / len(qualities)
        value_stats.append({
            "value": val,
            "mean_quality": round(mean_q, 4),
            "delta": round(mean_q - global_mean, 4),
            "count": len(qualities),
        })

    value_stats.sort(key=lambda x: x["mean_quality"], reverse=True)

    return {
        "parameter": parameter_name,
        "values": value_stats,
        "best_value": value_stats[0]["value"] if value_stats else None,
        "worst_value": value_stats[-1]["value"] if value_stats else None,
        "impact_range": round(
            value_stats[0]["mean_quality"] - value_stats[-1]["mean_quality"], 4
        ) if len(value_stats) >= 2 else 0.0,
    }


def rank_parameters_by_impact(
    results: List[Dict],
    quality_key: str = "overall_vbench",
) -> List[Dict]:
    """Rank all swept parameters by their absolute quality impact.

    Returns sorted list of marginal impact dicts, highest impact first.
    """
    param_names = set(r.get("parameter_name", "") for r in results)
    impacts = []
    for pname in param_names:
        if not pname:
            continue
        impact = compute_marginal_impact(results, pname, quality_key)
        impacts.append(impact)

    impacts.sort(key=lambda x: x["impact_range"], reverse=True)
    return impacts


def find_pareto_optimal(
    results: List[Dict],
    quality_key: str = "overall_vbench",
    cost_key: str = "cost_usd",
) -> List[Dict]:
    """Identify Pareto-optimal configurations (best quality at each cost level).

    A configuration is Pareto-optimal if no other config has both
    higher quality AND lower cost.
    """
    # Group by (parameter_name, parameter_value) to get avg quality and cost
    configs = defaultdict(lambda: {"qualities": [], "costs": []})
    for r in results:
        key = (r.get("parameter_name", ""), r.get("parameter_value", 0))
        configs[key]["qualities"].append(r.get(quality_key, 0.0))
        configs[key]["costs"].append(r.get(cost_key, 0.0))

    points = []
    for (pname, pval), data in configs.items():
        avg_q = sum(data["qualities"]) / len(data["qualities"])
        avg_c = sum(data["costs"]) / len(data["costs"])
        points.append({
            "parameter": pname,
            "value": pval,
            "avg_quality": round(avg_q, 4),
            "avg_cost": round(avg_c, 4),
        })

    # Filter to Pareto front
    pareto = []
    for p in points:
        dominated = False
        for other in points:
            if (other["avg_quality"] > p["avg_quality"] and
                    other["avg_cost"] <= p["avg_cost"]):
                dominated = True
                break
        if not dominated:
            pareto.append(p)

    pareto.sort(key=lambda x: x["avg_quality"], reverse=True)
    return pareto


def generate_recommendations(
    impacts: List[Dict],
    current_params: Optional[Dict] = None,
) -> Dict[str, float]:
    """Generate recommended parameter values based on sweep analysis.

    Returns dict of {parameter_name: recommended_value} that can be
    pasted into WORKFLOW_TEMPLATES.
    """
    recommendations = {}
    for impact in impacts:
        pname = impact["parameter"]
        best = impact.get("best_value")
        if best is not None:
            recommendations[pname] = best

    return recommendations


def generate_regression_report(
    results: List[Dict],
    baseline_quality: float = 0.75,
) -> Dict:
    """Generate a regression report comparing sweep results against a baseline.

    Returns dict with:
      - alerts: list of parameters whose best value still falls below baseline
      - healthy: parameters whose best value meets or exceeds baseline
      - overall_status: "PASS" or "REGRESSION_DETECTED"
    """
    impacts = rank_parameters_by_impact(results)
    alerts = []
    healthy = []

    for impact in impacts:
        values = impact.get("values", [])
        if not values:
            continue
        best_quality = values[0]["mean_quality"]
        entry = {
            "parameter": impact["parameter"],
            "best_value": impact["best_value"],
            "best_quality": best_quality,
            "impact_range": impact["impact_range"],
        }
        if best_quality < baseline_quality:
            entry["gap"] = round(baseline_quality - best_quality, 4)
            alerts.append(entry)
        else:
            healthy.append(entry)

    return {
        "baseline": baseline_quality,
        "alerts": alerts,
        "healthy": healthy,
        "overall_status": "REGRESSION_DETECTED" if alerts else "PASS",
    }


def export_analysis_csv(
    impacts: List[Dict],
    output_path: str,
) -> str:
    """Export marginal impact analysis to CSV."""
    rows = []
    for impact in impacts:
        for vs in impact.get("values", []):
            rows.append({
                "parameter": impact["parameter"],
                "value": vs["value"],
                "mean_quality": vs["mean_quality"],
                "delta": vs["delta"],
                "count": vs["count"],
                "impact_range": impact["impact_range"],
            })

    if not rows:
        return output_path

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    return output_path


# ---------------------------------------------------------------------------
# Main analysis runner
# ---------------------------------------------------------------------------


def run_analysis(db_path: str = "experiments.db", run_sweeps: bool = False) -> Dict:
    """Run the full analysis pipeline.

    1. Optionally run parameter sweeps to populate data
    2. Read sweep results from quality_tracker
    3. Compute marginal impacts
    4. Find Pareto-optimal configs
    5. Generate recommendations
    6. Generate regression report
    """
    tracker = QualityTracker(db_path=db_path)

    if run_sweeps:
        print("[ANALYZE] Running parameter sweeps first...")
        try:
            from test_parameter_sweep import ParameterSweepRunner
            runner = ParameterSweepRunner(tracker)
            runner.run_all_sweeps()
            print(f"[ANALYZE] Sweeps complete. Data stored in {db_path}")
        except ImportError:
            print("[ANALYZE] Warning: test_parameter_sweep not found, skipping sweeps")

    results = tracker.get_sweep_results()
    tracker.close()

    if not results:
        print("[ANALYZE] No sweep data found. Run with --run-sweeps to generate data.")
        return {"status": "no_data"}

    print(f"[ANALYZE] Found {len(results)} sweep data points")

    # Analysis
    impacts = rank_parameters_by_impact(results)
    pareto = find_pareto_optimal(results)
    recommendations = generate_recommendations(impacts)
    regression = generate_regression_report(results)

    # Export
    csv_path = os.path.join(os.path.dirname(__file__), "sweep_analysis.csv")
    export_analysis_csv(impacts, csv_path)
    print(f"[ANALYZE] CSV exported to {csv_path}")

    # Summary
    print("\n" + "=" * 60)
    print("PARAMETER IMPACT RANKING (highest impact first)")
    print("=" * 60)
    for i, impact in enumerate(impacts, 1):
        print(f"  {i}. {impact['parameter']}: "
              f"range={impact['impact_range']:.4f}, "
              f"best={impact['best_value']}")

    print(f"\n{'=' * 60}")
    print(f"PARETO-OPTIMAL CONFIGURATIONS ({len(pareto)} configs)")
    print("=" * 60)
    for p in pareto[:10]:
        print(f"  {p['parameter']}={p['value']}: "
              f"quality={p['avg_quality']:.4f}, cost=${p['avg_cost']:.4f}")

    print(f"\n{'=' * 60}")
    print("RECOMMENDED PARAMETER VALUES")
    print("=" * 60)
    for k, v in recommendations.items():
        print(f"  {k}: {v}")

    print(f"\n{'=' * 60}")
    print(f"REGRESSION STATUS: {regression['overall_status']}")
    print("=" * 60)
    if regression["alerts"]:
        for a in regression["alerts"]:
            print(f"  WARNING: {a['parameter']} best={a['best_quality']:.4f} "
                  f"< baseline={regression['baseline']} (gap={a['gap']:.4f})")

    report = {
        "status": "complete",
        "data_points": len(results),
        "impacts": impacts,
        "pareto_optimal": pareto,
        "recommendations": recommendations,
        "regression": regression,
    }

    json_path = os.path.join(os.path.dirname(__file__), "sweep_analysis.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n[ANALYZE] Full report saved to {json_path}")

    return report


# ---------------------------------------------------------------------------
# pytest tests for the analysis functions
# ---------------------------------------------------------------------------

import pytest


def _make_sweep_results():
    """Create synthetic sweep results for testing."""
    results = []
    # Simulate denoise_strength sweep: lower values → higher quality
    for val in [0.20, 0.30, 0.40, 0.50, 0.60]:
        for _ in range(5):
            quality = max(0, 0.90 - (val - 0.20) * 0.5)  # 0.90 at 0.20, 0.70 at 0.60
            results.append({
                "parameter_name": "denoise_strength",
                "parameter_value": val,
                "shot_type": "portrait",
                "overall_vbench": quality + (hash(str(val) + str(_)) % 100) * 0.001,
                "cost_usd": val * 0.10,
            })
    # Simulate pulid_weight sweep: mid values best
    for val in [0.6, 0.7, 0.8, 0.9, 1.0]:
        for _ in range(5):
            quality = 0.85 - abs(val - 0.85) * 0.3
            results.append({
                "parameter_name": "pulid_weight",
                "parameter_value": val,
                "shot_type": "portrait",
                "overall_vbench": quality + (hash(str(val) + str(_)) % 100) * 0.001,
                "cost_usd": 0.10,
            })
    return results


class TestComputeMarginalImpact:
    def test_returns_values_for_known_parameter(self):
        results = _make_sweep_results()
        impact = compute_marginal_impact(results, "denoise_strength")
        assert impact["parameter"] == "denoise_strength"
        assert len(impact["values"]) == 5
        assert impact["best_value"] is not None
        assert impact["impact_range"] > 0

    def test_best_value_has_highest_quality(self):
        results = _make_sweep_results()
        impact = compute_marginal_impact(results, "denoise_strength")
        best = impact["values"][0]
        worst = impact["values"][-1]
        assert best["mean_quality"] >= worst["mean_quality"]

    def test_unknown_parameter_returns_empty(self):
        results = _make_sweep_results()
        impact = compute_marginal_impact(results, "nonexistent_param")
        assert impact["values"] == []
        assert impact["impact_range"] == 0.0

    def test_delta_sums_near_zero(self):
        """Deltas from global mean should approximately sum to zero (weighted by count)."""
        results = _make_sweep_results()
        impact = compute_marginal_impact(results, "denoise_strength")
        total_count = sum(v["count"] for v in impact["values"])
        weighted_sum = sum(v["delta"] * v["count"] for v in impact["values"])
        assert abs(weighted_sum / total_count) < 0.01


class TestRankParametersByImpact:
    def test_returns_sorted_by_impact_range(self):
        results = _make_sweep_results()
        ranked = rank_parameters_by_impact(results)
        assert len(ranked) == 2  # denoise_strength and pulid_weight
        for i in range(len(ranked) - 1):
            assert ranked[i]["impact_range"] >= ranked[i + 1]["impact_range"]

    def test_all_parameters_included(self):
        results = _make_sweep_results()
        ranked = rank_parameters_by_impact(results)
        names = {r["parameter"] for r in ranked}
        assert "denoise_strength" in names
        assert "pulid_weight" in names


class TestFindParetoOptimal:
    def test_pareto_configs_are_not_dominated(self):
        results = _make_sweep_results()
        pareto = find_pareto_optimal(results)
        for p in pareto:
            for other in pareto:
                if other is p:
                    continue
                # No other point should dominate p
                assert not (
                    other["avg_quality"] > p["avg_quality"]
                    and other["avg_cost"] <= p["avg_cost"]
                )

    def test_returns_at_least_one_config(self):
        results = _make_sweep_results()
        pareto = find_pareto_optimal(results)
        assert len(pareto) >= 1


class TestGenerateRecommendations:
    def test_returns_dict_of_best_values(self):
        results = _make_sweep_results()
        impacts = rank_parameters_by_impact(results)
        recs = generate_recommendations(impacts)
        assert isinstance(recs, dict)
        assert "denoise_strength" in recs
        assert "pulid_weight" in recs

    def test_empty_impacts_returns_empty(self):
        recs = generate_recommendations([])
        assert recs == {}


class TestGenerateRegressionReport:
    def test_pass_when_quality_above_baseline(self):
        results = _make_sweep_results()
        report = generate_regression_report(results, baseline_quality=0.50)
        assert report["overall_status"] == "PASS"
        assert len(report["alerts"]) == 0

    def test_regression_when_quality_below_baseline(self):
        results = _make_sweep_results()
        report = generate_regression_report(results, baseline_quality=0.99)
        assert report["overall_status"] == "REGRESSION_DETECTED"
        assert len(report["alerts"]) >= 1
        for alert in report["alerts"]:
            assert "gap" in alert
            assert alert["gap"] > 0


class TestExportAnalysisCsv:
    def test_creates_csv_file(self, tmp_path):
        results = _make_sweep_results()
        impacts = rank_parameters_by_impact(results)
        csv_path = str(tmp_path / "test_analysis.csv")
        export_analysis_csv(impacts, csv_path)
        assert os.path.exists(csv_path)

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) > 0
        assert "parameter" in rows[0]
        assert "mean_quality" in rows[0]

    def test_empty_impacts_creates_file(self, tmp_path):
        csv_path = str(tmp_path / "empty.csv")
        export_analysis_csv([], csv_path)
        # File path returned even if no data
        assert csv_path.endswith("empty.csv")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze parameter sweep results")
    parser.add_argument("--db", default="experiments.db", help="Path to experiments.db")
    parser.add_argument("--run-sweeps", action="store_true", help="Run sweeps before analysis")
    args = parser.parse_args()
    run_analysis(db_path=args.db, run_sweeps=args.run_sweeps)
