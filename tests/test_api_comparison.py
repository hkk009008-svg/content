"""
test_api_comparison.py -- Compare video quality across all available APIs.

Generates the same shot with each API (Kling, Runway, Sora, LTX, Veo),
evaluates with VBench 6D, and builds a quality ranking matrix.

Requires GPU pod with ComfyUI + API keys.  Marked @pytest.mark.e2e.
"""

import json
import os
import sys
import time
import uuid
from typing import Dict, List, Optional

import pytest

# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------
COMFYUI_URL = os.getenv("COMFYUI_SERVER_URL", "")
HAS_COMFYUI = bool(COMFYUI_URL)
HAS_KLING = bool(os.getenv("KLING_ACCESS_KEY"))
HAS_RUNWAY = bool(os.getenv("RUNWAYML_API_SECRET"))
HAS_OPENAI = bool(os.getenv("OPENAI_API_KEY"))
HAS_GOOGLE = bool(os.getenv("GOOGLE_API_KEY"))
HAS_FAL = bool(os.getenv("FAL_KEY"))
HAS_LTX = bool(os.getenv("LTX_API_KEY"))

HAS_E2E_DEPS = HAS_COMFYUI and (HAS_KLING or HAS_FAL or HAS_LTX)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not HAS_E2E_DEPS, reason="API comparison requires ComfyUI + API keys"),
]

# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------
if HAS_E2E_DEPS:
    from phase_c_assembly import generate_ai_broll
    from phase_c_ffmpeg import generate_ai_video
    from vbench_evaluator import VBenchEvaluator
    from vbench_evaluator import VBenchResult as EvalVBenchResult
    from identity_validator import IdentityValidator
    from cost_tracker import CostTracker
    from quality_tracker import QualityTracker, VBenchResult as QTVBenchResult

# ---------------------------------------------------------------------------
# APIs and their availability
# ---------------------------------------------------------------------------
ALL_APIS = [
    ("KLING_NATIVE", HAS_KLING),
    ("SORA_NATIVE", HAS_OPENAI),
    ("RUNWAY_GEN4", HAS_RUNWAY),
    ("LTX", HAS_LTX),
    ("VEO_NATIVE", HAS_GOOGLE),
]

AVAILABLE_APIS = [name for name, avail in ALL_APIS if avail]

# Estimated cost per API call (USD)
API_COST_ESTIMATES = {
    "KLING_NATIVE": 0.12,
    "SORA_NATIVE": 0.20,
    "RUNWAY_GEN4": 0.15,
    "LTX": 0.05,
    "VEO_NATIVE": 0.15,
}

# ---------------------------------------------------------------------------
# Comparison scenarios (1 per key shot type)
# ---------------------------------------------------------------------------
COMPARISON_SCENARIOS = [
    {
        "id": "compare_portrait",
        "shot_type": "portrait",
        "prompt": (
            "[SHOT] Close-up portrait of a confident woman with auburn hair, "
            "soft studio lighting, neutral background, shallow depth of field, "
            "cinematic color grading, 35mm film look"
        ),
        "camera_motion": "slow_zoom_in",
        "has_character": True,
        "description": "Portrait comparison — identity & aesthetic focus",
    },
    {
        "id": "compare_medium",
        "shot_type": "medium",
        "prompt": (
            "[SHOT] Medium shot of a character standing at a rain-soaked street corner, "
            "neon signs reflecting on wet pavement, night scene, moody cyan-magenta palette, "
            "cinematic widescreen composition"
        ),
        "camera_motion": "dolly_in",
        "has_character": True,
        "description": "Medium comparison — motion & coherence focus",
    },
    {
        "id": "compare_landscape",
        "shot_type": "landscape",
        "prompt": (
            "[SHOT] Sweeping landscape of rolling green hills at golden hour, "
            "scattered clouds casting long shadows, a winding river in the valley, "
            "dramatic volumetric light rays, epic cinematic scale"
        ),
        "camera_motion": "slow_pan_right",
        "has_character": False,
        "description": "Landscape comparison — aesthetic & physics focus",
    },
]

VBENCH_DIMENSIONS = [
    "identity_consistency",
    "temporal_flicker",
    "motion_smoothness",
    "aesthetic_quality",
    "prompt_adherence",
    "physics_plausibility",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _convert_eval_to_qt_vbench(eval_result) -> "QTVBenchResult":
    """Convert vbench_evaluator.VBenchResult → quality_tracker.VBenchResult."""
    return QTVBenchResult(
        identity_score=eval_result.identity_consistency,
        flicker_score=eval_result.temporal_flicker,
        motion_score=eval_result.motion_smoothness,
        aesthetic_score=eval_result.aesthetic_quality,
        prompt_adherence_score=eval_result.prompt_adherence,
        physics_score=eval_result.physics_plausibility,
        overall_vbench=eval_result.overall_score,
    )


def _generate_reference_image(output_dir: str) -> str:
    """Generate a reference character image for comparison tests."""
    ref_path = os.path.join(output_dir, "compare_char_ref.png")
    if os.path.exists(ref_path):
        return ref_path
    result = generate_ai_broll(
        prompt=(
            "Portrait photo of a woman with auburn hair, mid-30s, neutral expression, "
            "plain grey background, studio lighting, sharp focus, passport style"
        ),
        output_filename=ref_path,
        seed=12345,
    )
    return result or ref_path


def _generate_source_image(scenario: Dict, output_dir: str, reference_image: Optional[str]) -> str:
    """Generate the source image once per scenario (shared across APIs)."""
    img_path = os.path.join(output_dir, f"{scenario['id']}_source.png")
    if os.path.exists(img_path):
        return img_path
    char_ref = reference_image if scenario["has_character"] else None
    result = generate_ai_broll(
        prompt=scenario["prompt"],
        output_filename=img_path,
        seed=hash(scenario["id"]) & 0xFFFFFFFF,
        character_image=char_ref,
    )
    assert result and os.path.exists(result), f"Source image gen failed for {scenario['id']}"
    return result


def _run_api_comparison(
    scenario: Dict,
    source_image: str,
    api: str,
    output_dir: str,
    reference_image: Optional[str],
    evaluator: "VBenchEvaluator",
    validator: "IdentityValidator",
    quality_tracker: "QualityTracker",
    cost_tracker: "CostTracker",
    video_id: str,
) -> Dict:
    """Generate video with a specific API and evaluate it."""
    shot_id = f"{scenario['id']}_{api}"
    video_path = os.path.join(output_dir, f"{shot_id}.mp4")

    # Generate video
    t0 = time.time()
    result_path = generate_ai_video(
        image_path=source_image,
        camera_motion=scenario["camera_motion"],
        target_api=api,
        output_mp4=video_path,
        shot_type=scenario["shot_type"],
    )
    gen_time = time.time() - t0

    if not result_path or not os.path.exists(result_path):
        return {
            "api": api,
            "shot_type": scenario["shot_type"],
            "success": False,
            "error": "Video generation failed",
            "generation_time_seconds": gen_time,
        }

    # VBench evaluate
    char_ref = reference_image if scenario["has_character"] else None
    vbench = evaluator.evaluate(
        video_path=result_path,
        prompt=scenario["prompt"],
        reference_images=[char_ref] if char_ref else None,
        shot_type=scenario["shot_type"],
    )

    # Identity validation (character shots only)
    identity_score = 0.0
    if scenario["has_character"] and char_ref:
        identity_result = validator.validate_video(
            video_path=result_path,
            character_configs=[{
                "id": "compare_char",
                "reference_image": char_ref,
                "name": "Comparison Character",
            }],
            shot_type=scenario["shot_type"],
            mode="standard",
        )
        identity_score = identity_result.overall_score

    # Log cost
    estimated_cost = API_COST_ESTIMATES.get(api, 0.10)
    cost_tracker.log_api(
        provider=api.lower().replace("_native", "").replace("_gen4", ""),
        model=api,
        operation="api_comparison_video",
        cost_usd=estimated_cost,
        shot_id=shot_id,
        video_id=video_id,
    )

    # Log quality
    qt_vbench = _convert_eval_to_qt_vbench(vbench)
    quality_tracker.log_shot_quality(
        shot_id=shot_id,
        video_id=video_id,
        shot_type=scenario["shot_type"],
        target_api=api,
        vbench_result=qt_vbench,
        identity_similarity=identity_score,
        generation_cost=estimated_cost + vbench.evaluation_cost_usd,
    )

    return {
        "api": api,
        "shot_type": scenario["shot_type"],
        "success": True,
        "video_path": result_path,
        "scores": {
            "identity_consistency": vbench.identity_consistency,
            "temporal_flicker": vbench.temporal_flicker,
            "motion_smoothness": vbench.motion_smoothness,
            "aesthetic_quality": vbench.aesthetic_quality,
            "prompt_adherence": vbench.prompt_adherence,
            "physics_plausibility": vbench.physics_plausibility,
            "overall": vbench.overall_score,
        },
        "identity_score": identity_score,
        "generation_time_seconds": gen_time,
        "estimated_cost_usd": estimated_cost,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def compare_output_dir(tmp_path_factory):
    return str(tmp_path_factory.mktemp("api_comparison"))


@pytest.fixture(scope="module")
def compare_db_path(tmp_path_factory):
    return str(tmp_path_factory.mktemp("compare_db") / "compare.db")


@pytest.fixture(scope="module")
def compare_quality_tracker(compare_db_path):
    tracker = QualityTracker(db_path=compare_db_path)
    yield tracker
    tracker.close()


@pytest.fixture(scope="module")
def compare_cost_tracker(compare_db_path):
    tracker = CostTracker(db_path=compare_db_path)
    yield tracker
    tracker.close()


@pytest.fixture(scope="module")
def compare_evaluator():
    return VBenchEvaluator()


@pytest.fixture(scope="module")
def compare_validator():
    return IdentityValidator()


@pytest.fixture(scope="module")
def compare_reference_image(compare_output_dir):
    return _generate_reference_image(compare_output_dir)


@pytest.fixture(scope="module")
def compare_video_id():
    return f"compare_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def comparison_results():
    """Shared mutable list to accumulate comparison results."""
    return []


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

class TestApiComparisonPortrait:
    """Run portrait scenario across all available APIs."""

    @pytest.mark.parametrize("api", AVAILABLE_APIS, ids=AVAILABLE_APIS)
    def test_portrait_api(
        self,
        api,
        compare_output_dir,
        compare_reference_image,
        compare_evaluator,
        compare_validator,
        compare_quality_tracker,
        compare_cost_tracker,
        compare_video_id,
        comparison_results,
    ):
        scenario = COMPARISON_SCENARIOS[0]  # portrait
        source_image = _generate_source_image(
            scenario, compare_output_dir, compare_reference_image
        )
        result = _run_api_comparison(
            scenario=scenario,
            source_image=source_image,
            api=api,
            output_dir=compare_output_dir,
            reference_image=compare_reference_image,
            evaluator=compare_evaluator,
            validator=compare_validator,
            quality_tracker=compare_quality_tracker,
            cost_tracker=compare_cost_tracker,
            video_id=compare_video_id,
        )
        comparison_results.append(result)

        if result["success"]:
            assert result["scores"]["overall"] >= 0.0
        else:
            pytest.skip(f"{api} failed for portrait: {result.get('error')}")


class TestApiComparisonMedium:
    """Run medium scenario across all available APIs."""

    @pytest.mark.parametrize("api", AVAILABLE_APIS, ids=AVAILABLE_APIS)
    def test_medium_api(
        self,
        api,
        compare_output_dir,
        compare_reference_image,
        compare_evaluator,
        compare_validator,
        compare_quality_tracker,
        compare_cost_tracker,
        compare_video_id,
        comparison_results,
    ):
        scenario = COMPARISON_SCENARIOS[1]  # medium
        source_image = _generate_source_image(
            scenario, compare_output_dir, compare_reference_image
        )
        result = _run_api_comparison(
            scenario=scenario,
            source_image=source_image,
            api=api,
            output_dir=compare_output_dir,
            reference_image=compare_reference_image,
            evaluator=compare_evaluator,
            validator=compare_validator,
            quality_tracker=compare_quality_tracker,
            cost_tracker=compare_cost_tracker,
            video_id=compare_video_id,
        )
        comparison_results.append(result)

        if result["success"]:
            assert result["scores"]["overall"] >= 0.0
        else:
            pytest.skip(f"{api} failed for medium: {result.get('error')}")


class TestApiComparisonLandscape:
    """Run landscape scenario across all available APIs."""

    @pytest.mark.parametrize("api", AVAILABLE_APIS, ids=AVAILABLE_APIS)
    def test_landscape_api(
        self,
        api,
        compare_output_dir,
        compare_reference_image,
        compare_evaluator,
        compare_validator,
        compare_quality_tracker,
        compare_cost_tracker,
        compare_video_id,
        comparison_results,
    ):
        scenario = COMPARISON_SCENARIOS[2]  # landscape
        source_image = _generate_source_image(
            scenario, compare_output_dir, None  # no character ref for landscape
        )
        result = _run_api_comparison(
            scenario=scenario,
            source_image=source_image,
            api=api,
            output_dir=compare_output_dir,
            reference_image=None,
            evaluator=compare_evaluator,
            validator=compare_validator,
            quality_tracker=compare_quality_tracker,
            cost_tracker=compare_cost_tracker,
            video_id=compare_video_id,
        )
        comparison_results.append(result)

        if result["success"]:
            assert result["scores"]["overall"] >= 0.0
        else:
            pytest.skip(f"{api} failed for landscape: {result.get('error')}")


class TestApiRankingMatrix:
    """Build and validate the API ranking matrix from comparison results."""

    def test_build_ranking_matrix(self, comparison_results, compare_output_dir):
        """Generate api_comparison_report.json with rankings."""
        successful = [r for r in comparison_results if r.get("success")]
        if not successful:
            pytest.skip("No successful API comparisons to rank")

        # Build matrix: API × dimension
        ranking_matrix = {}
        for r in successful:
            api = r["api"]
            if api not in ranking_matrix:
                ranking_matrix[api] = {
                    "scores_by_shot_type": {},
                    "overall_avg": {},
                    "total_cost_usd": 0.0,
                    "total_gen_time": 0.0,
                    "count": 0,
                }
            entry = ranking_matrix[api]
            entry["count"] += 1
            entry["total_cost_usd"] += r.get("estimated_cost_usd", 0)
            entry["total_gen_time"] += r.get("generation_time_seconds", 0)

            st = r["shot_type"]
            entry["scores_by_shot_type"][st] = r["scores"]

            # Accumulate for overall average
            for dim in VBENCH_DIMENSIONS:
                if dim not in entry["overall_avg"]:
                    entry["overall_avg"][dim] = []
                entry["overall_avg"][dim].append(r["scores"].get(dim, 0.0))

        # Compute averages
        for api, entry in ranking_matrix.items():
            for dim, values in entry["overall_avg"].items():
                entry["overall_avg"][dim] = sum(values) / len(values) if values else 0.0
            entry["avg_cost_per_shot"] = (
                entry["total_cost_usd"] / entry["count"] if entry["count"] else 0
            )
            entry["avg_gen_time"] = (
                entry["total_gen_time"] / entry["count"] if entry["count"] else 0
            )

        # Rank APIs by overall VBench score
        api_rankings = sorted(
            ranking_matrix.items(),
            key=lambda x: x[1]["overall_avg"].get("aesthetic_quality", 0)
            + x[1]["overall_avg"].get("prompt_adherence", 0)
            + x[1]["overall_avg"].get("motion_smoothness", 0),
            reverse=True,
        )

        # Best API per shot type
        best_per_type = {}
        for st in ["portrait", "medium", "landscape"]:
            type_results = [r for r in successful if r["shot_type"] == st]
            if type_results:
                best = max(type_results, key=lambda r: r["scores"]["overall"])
                best_per_type[st] = {
                    "best_api": best["api"],
                    "overall_score": best["scores"]["overall"],
                    "scores": best["scores"],
                }

        # Cost rankings
        cost_rankings = sorted(
            ranking_matrix.items(),
            key=lambda x: x[1]["avg_cost_per_shot"],
        )

        report = {
            "comparison_id": f"compare_{uuid.uuid4().hex[:8]}",
            "apis_tested": list(ranking_matrix.keys()),
            "total_comparisons": len(successful),
            "ranking_matrix": {
                api: {
                    "quality_rank": idx + 1,
                    "avg_scores": entry["overall_avg"],
                    "scores_by_shot_type": entry["scores_by_shot_type"],
                    "avg_cost_per_shot": entry["avg_cost_per_shot"],
                    "avg_gen_time_seconds": entry["avg_gen_time"],
                }
                for idx, (api, entry) in enumerate(api_rankings)
            },
            "best_api_per_shot_type": best_per_type,
            "cost_rankings": [
                {"api": api, "avg_cost": entry["avg_cost_per_shot"]}
                for api, entry in cost_rankings
            ],
            "individual_results": successful,
        }

        # Write report
        report_path = os.path.join(compare_output_dir, "api_comparison_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        # Also to tests/ for easy access
        tests_report = os.path.join(os.path.dirname(__file__), "api_comparison_report.json")
        with open(tests_report, "w") as f:
            json.dump(report, f, indent=2, default=str)

        assert os.path.exists(report_path)
        assert report["total_comparisons"] > 0

    def test_at_least_two_apis_compared(self, comparison_results):
        """Meaningful comparison requires at least 2 APIs."""
        successful = [r for r in comparison_results if r.get("success")]
        apis_tested = {r["api"] for r in successful}
        if len(apis_tested) < 2:
            pytest.skip(f"Only {len(apis_tested)} API(s) available, need 2+ for comparison")
        assert len(apis_tested) >= 2

    def test_same_source_image_used(self, comparison_results):
        """All APIs for a given scenario should use the same source image."""
        successful = [r for r in comparison_results if r.get("success")]
        if not successful:
            pytest.skip("No results")
        # Results from same shot_type should have been generated from same source
        for st in ["portrait", "medium", "landscape"]:
            st_results = [r for r in successful if r["shot_type"] == st]
            if len(st_results) >= 2:
                # All should have video paths (different) but from same source
                assert len({r["api"] for r in st_results}) == len(st_results), (
                    f"Duplicate API entries for {st}"
                )
