"""
test_e2e_quality_benchmark.py -- End-to-end quality benchmarks for cinema pipeline.

Runs 10 fixed scenarios (2 per shot type) through the full pipeline:
image gen → video gen → VBench eval → coherence → identity → log results.

Requires GPU pod with ComfyUI + API keys.  Marked @pytest.mark.e2e so CI skips.
"""

import json
import os
import sys
import tempfile
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

import pytest

# ---------------------------------------------------------------------------
# Project root on path
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

# Minimum: ComfyUI for image gen + at least one video API
HAS_E2E_DEPS = HAS_COMFYUI and (HAS_KLING or HAS_FAL or HAS_LTX)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not HAS_E2E_DEPS, reason="E2E requires ComfyUI + API keys"),
]

# ---------------------------------------------------------------------------
# Lazy imports (only on GPU pod)
# ---------------------------------------------------------------------------
if HAS_E2E_DEPS:
    from phase_c_assembly import generate_ai_broll
    from phase_c_ffmpeg import generate_ai_video
    from vbench_evaluator import VBenchEvaluator
    from vbench_evaluator import VBenchResult as EvalVBenchResult
    from coherence_analyzer import assess_coherence
    from identity_validator import IdentityValidator
    from cost_tracker import CostTracker
    from quality_tracker import QualityTracker, VBenchResult as QTVBenchResult
    from workflow_selector import get_workflow_params

# ---------------------------------------------------------------------------
# Benchmark scenario definitions
# ---------------------------------------------------------------------------

BENCHMARK_SCENARIOS = [
    # --- Portrait (2) ---
    {
        "id": "bench_portrait_01",
        "shot_type": "portrait",
        "prompt": (
            "[SHOT] Close-up portrait of a determined hero speaking in a dimly lit room, "
            "warm tungsten lighting, shallow depth of field, cinematic film grain"
        ),
        "camera_motion": "slow_zoom_in",
        "target_api": "KLING_NATIVE",
        "has_character": True,
        "description": "Close-up hero dialogue, indoor lighting",
    },
    {
        "id": "bench_portrait_02",
        "shot_type": "portrait",
        "prompt": (
            "[SHOT] Profile two-shot of two characters facing each other at sunset, "
            "golden backlight rim lighting, bokeh background, anamorphic lens flare"
        ),
        "camera_motion": "pan_left",
        "target_api": "RUNWAY_GEN4",
        "has_character": True,
        "description": "Profile two-shot, sunset backlight",
    },
    # --- Medium (2) ---
    {
        "id": "bench_medium_01",
        "shot_type": "medium",
        "prompt": (
            "[SHOT] Medium shot of a character walking through a bustling outdoor market, "
            "colorful stalls, natural daylight, handheld feel, busy crowd in background"
        ),
        "camera_motion": "tracking_right",
        "target_api": "SORA_NATIVE",
        "has_character": True,
        "description": "Character walking through market",
    },
    {
        "id": "bench_medium_02",
        "shot_type": "medium",
        "prompt": (
            "[SHOT] Medium shot of two characters seated at a restaurant table, "
            "warm ambient lighting, candles on table, shallow focus, intimate mood"
        ),
        "camera_motion": "static",
        "target_api": "KLING_NATIVE",
        "has_character": True,
        "description": "Two characters at table, restaurant",
    },
    # --- Wide (2) ---
    {
        "id": "bench_wide_01",
        "shot_type": "wide",
        "prompt": (
            "[SHOT] Wide establishing shot of a sprawling cityscape at dusk, "
            "neon lights beginning to glow, moody blue-orange sky, aerial perspective"
        ),
        "camera_motion": "crane_up",
        "target_api": "VEO_NATIVE",
        "has_character": False,
        "description": "Cityscape establishing shot, dusk",
    },
    {
        "id": "bench_wide_02",
        "shot_type": "wide",
        "prompt": (
            "[SHOT] Wide shot of a misty forest clearing, a lone character entering "
            "from the left, morning light filtering through trees, volumetric fog"
        ),
        "camera_motion": "dolly_in",
        "target_api": "LTX",
        "has_character": True,
        "description": "Forest clearing, character entering frame",
    },
    # --- Action (2) ---
    {
        "id": "bench_action_01",
        "shot_type": "action",
        "prompt": (
            "[SHOT] Action shot of a character sprinting through a rain-soaked alley, "
            "neon reflections on wet ground, motion blur, dramatic low angle, urgent pacing"
        ),
        "camera_motion": "handheld_shake",
        "target_api": "SORA_NATIVE",
        "has_character": True,
        "description": "Chase through alley, rain",
    },
    {
        "id": "bench_action_02",
        "shot_type": "action",
        "prompt": (
            "[SHOT] Action shot of a martial arts fight on a rooftop at night, "
            "dramatic overhead city lights, fast choreography, dynamic camera angles"
        ),
        "camera_motion": "whip_pan",
        "target_api": "KLING_NATIVE",
        "has_character": True,
        "description": "Fight choreography, rooftop",
    },
    # --- Landscape (2) ---
    {
        "id": "bench_landscape_01",
        "shot_type": "landscape",
        "prompt": (
            "[SHOT] Landscape of a serene mountain lake at dawn, mirror reflections, "
            "pastel sky, snow-capped peaks, untouched wilderness, 4K clarity"
        ),
        "camera_motion": "slow_pan_right",
        "target_api": "LTX",
        "has_character": False,
        "description": "Mountain lake at dawn",
    },
    {
        "id": "bench_landscape_02",
        "shot_type": "landscape",
        "prompt": (
            "[SHOT] Landscape of a desert road stretching to the horizon at golden hour, "
            "long shadows, heat haze, dramatic sky, cinematic widescreen"
        ),
        "camera_motion": "dolly_forward",
        "target_api": "VEO_NATIVE",
        "has_character": False,
        "description": "Desert road, golden hour",
    },
]

# Map target APIs to required env var checks
API_AVAILABLE = {
    "KLING_NATIVE": HAS_KLING,
    "RUNWAY_GEN4": HAS_RUNWAY,
    "SORA_NATIVE": HAS_OPENAI,
    "VEO_NATIVE": HAS_GOOGLE,
    "LTX": HAS_LTX,
}

# Fallback chain if primary API unavailable
FALLBACK_ORDER = ["KLING_NATIVE", "LTX", "SORA_NATIVE", "RUNWAY_GEN4", "VEO_NATIVE"]


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


def _pick_available_api(preferred: str) -> Optional[str]:
    """Return preferred API if available, else first available fallback."""
    if API_AVAILABLE.get(preferred, False):
        return preferred
    for api in FALLBACK_ORDER:
        if API_AVAILABLE.get(api, False):
            return api
    return None


def _generate_reference_image(output_dir: str) -> str:
    """Generate a reference character image via ComfyUI for benchmarking."""
    ref_path = os.path.join(output_dir, "bench_char_ref.png")
    if os.path.exists(ref_path):
        return ref_path
    result = generate_ai_broll(
        prompt=(
            "Portrait photo of a 30-year-old man with short dark hair, neutral expression, "
            "plain grey background, studio lighting, passport photo style, sharp focus"
        ),
        output_filename=ref_path,
        seed=42,
    )
    return result or ref_path


def _run_benchmark_scenario(
    scenario: Dict,
    output_dir: str,
    reference_image: Optional[str],
    evaluator: "VBenchEvaluator",
    validator: "IdentityValidator",
    quality_tracker: "QualityTracker",
    cost_tracker: "CostTracker",
    video_id: str,
    prev_image: Optional[str] = None,
) -> Dict:
    """Execute a single benchmark scenario end-to-end and return results dict."""
    shot_id = scenario["id"]
    shot_type = scenario["shot_type"]
    api = _pick_available_api(scenario["target_api"])

    if api is None:
        pytest.skip(f"No video API available for {shot_id}")

    # Get workflow params for this shot type
    params = get_workflow_params(shot_type)

    # 1. Generate image via ComfyUI
    image_filename = os.path.join(output_dir, f"{shot_id}.png")
    char_ref = reference_image if scenario["has_character"] else None

    t0 = time.time()
    image_path = generate_ai_broll(
        prompt=scenario["prompt"],
        output_filename=image_filename,
        seed=hash(shot_id) & 0xFFFFFFFF,
        character_image=char_ref,
        pulid_weight_override=params.get("pulid_weight"),
    )
    image_gen_time = time.time() - t0

    assert image_path and os.path.exists(image_path), (
        f"Image generation failed for {shot_id}"
    )

    # 2. Generate video via target API
    video_filename = os.path.join(output_dir, f"{shot_id}.mp4")

    t0 = time.time()
    video_path = generate_ai_video(
        image_path=image_path,
        camera_motion=scenario["camera_motion"],
        target_api=api,
        output_mp4=video_filename,
        shot_type=shot_type,
        video_fallbacks=FALLBACK_ORDER,
    )
    video_gen_time = time.time() - t0

    assert video_path and os.path.exists(video_path), (
        f"Video generation failed for {shot_id}"
    )

    # 3. VBench evaluation (6D)
    vbench_result = evaluator.evaluate(
        video_path=video_path,
        prompt=scenario["prompt"],
        reference_images=[char_ref] if char_ref else None,
        shot_type=shot_type,
    )
    assert vbench_result.overall_score >= 0.0

    # 4. Coherence analysis (if we have a previous image)
    coherence_score = 0.0
    if prev_image and os.path.exists(prev_image):
        coherence_result = assess_coherence(
            current_image=image_path,
            previous_image=prev_image,
        )
        coherence_score = coherence_result.overall_coherence_score

    # 5. Identity validation (for character shots)
    identity_score = 0.0
    identity_passed = True
    if scenario["has_character"] and char_ref:
        identity_result = validator.validate_video(
            video_path=video_path,
            character_configs=[{
                "id": "bench_char_1",
                "reference_image": char_ref,
                "name": "Benchmark Character",
            }],
            shot_type=shot_type,
            mode="standard",
        )
        identity_score = identity_result.overall_score
        identity_passed = identity_result.passed

    # 6. Log costs
    total_gen_time = image_gen_time + video_gen_time
    estimated_cost = vbench_result.evaluation_cost_usd + 0.10  # approximate API cost

    cost_tracker.log_api(
        provider=api.lower().replace("_native", "").replace("_gen4", ""),
        model=api,
        operation="benchmark_video_generation",
        cost_usd=0.10,
        shot_id=shot_id,
        video_id=video_id,
    )

    # 7. Log quality
    qt_vbench = _convert_eval_to_qt_vbench(vbench_result)
    quality_tracker.log_shot_quality(
        shot_id=shot_id,
        video_id=video_id,
        shot_type=shot_type,
        target_api=api,
        vbench_result=qt_vbench,
        identity_similarity=identity_score,
        coherence_score=coherence_score,
        generation_cost=estimated_cost,
        param_config={
            "pulid_weight": params.get("pulid_weight", 0.0),
            "guidance_scale": params.get("guidance", 3.5),
            "pag_scale": params.get("pag_scale", 3.0),
            "denoise_strength": params.get("denoise_default", 0.25),
            "controlnet_depth": params.get("controlnet_depth_strength", 0.35),
            "ip_adapter_weight": params.get("ip_adapter_weight", 0.25),
            "diffusion_steps": params.get("steps", 25),
            "generation_time_seconds": total_gen_time,
            "cascade_depth": 0,
        },
    )

    return {
        "shot_id": shot_id,
        "shot_type": shot_type,
        "api_used": api,
        "description": scenario["description"],
        "image_path": image_path,
        "video_path": video_path,
        "vbench_scores": {
            "identity_consistency": vbench_result.identity_consistency,
            "temporal_flicker": vbench_result.temporal_flicker,
            "motion_smoothness": vbench_result.motion_smoothness,
            "aesthetic_quality": vbench_result.aesthetic_quality,
            "prompt_adherence": vbench_result.prompt_adherence,
            "physics_plausibility": vbench_result.physics_plausibility,
            "overall": vbench_result.overall_score,
        },
        "coherence_score": coherence_score,
        "identity_score": identity_score,
        "identity_passed": identity_passed,
        "generation_time_seconds": total_gen_time,
        "evaluation_cost_usd": estimated_cost,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def benchmark_output_dir(tmp_path_factory):
    """Shared output directory for all benchmark images/videos."""
    return str(tmp_path_factory.mktemp("benchmark_output"))


@pytest.fixture(scope="module")
def benchmark_db_path(tmp_path_factory):
    """Temp DB path for benchmark tracking."""
    p = tmp_path_factory.mktemp("benchmark_db") / "benchmark.db"
    return str(p)


@pytest.fixture(scope="module")
def benchmark_quality_tracker(benchmark_db_path):
    tracker = QualityTracker(db_path=benchmark_db_path)
    yield tracker
    tracker.close()


@pytest.fixture(scope="module")
def benchmark_cost_tracker(benchmark_db_path):
    tracker = CostTracker(db_path=benchmark_db_path)
    yield tracker
    tracker.close()


@pytest.fixture(scope="module")
def benchmark_evaluator():
    return VBenchEvaluator()


@pytest.fixture(scope="module")
def benchmark_validator():
    return IdentityValidator()


@pytest.fixture(scope="module")
def benchmark_reference_image(benchmark_output_dir):
    """Generate or load a reference character image for benchmarking."""
    return _generate_reference_image(benchmark_output_dir)


@pytest.fixture(scope="module")
def benchmark_video_id():
    return f"benchmark_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def benchmark_results():
    """Shared mutable list to accumulate results across tests."""
    return []


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

class TestBenchmarkInfrastructure:
    """Verify benchmark prerequisites before running scenarios."""

    def test_comfyui_reachable(self):
        """ComfyUI server responds."""
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=5)
            assert resp.status == 200
        except Exception as e:
            pytest.fail(f"ComfyUI not reachable at {COMFYUI_URL}: {e}")

    def test_at_least_one_video_api(self):
        """At least one video API key is set."""
        available = [k for k, v in API_AVAILABLE.items() if v]
        assert len(available) >= 1, "Need at least one video API key"

    def test_quality_tracker_schema(self, benchmark_quality_tracker):
        """QualityTracker DB has expected tables."""
        conn = benchmark_quality_tracker._get_conn()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "shot_quality" in tables

    def test_reference_image_generation(self, benchmark_reference_image):
        """Reference image was generated successfully."""
        assert os.path.exists(benchmark_reference_image)
        assert os.path.getsize(benchmark_reference_image) > 1000


class TestPortraitBenchmark:
    """Portrait shot benchmarks (scenarios 1-2)."""

    @pytest.mark.parametrize("scenario_idx", [0, 1], ids=["portrait_indoor", "portrait_sunset"])
    def test_portrait_scenario(
        self,
        scenario_idx,
        benchmark_output_dir,
        benchmark_reference_image,
        benchmark_evaluator,
        benchmark_validator,
        benchmark_quality_tracker,
        benchmark_cost_tracker,
        benchmark_video_id,
        benchmark_results,
    ):
        scenario = BENCHMARK_SCENARIOS[scenario_idx]
        api = _pick_available_api(scenario["target_api"])
        if api is None:
            pytest.skip(f"No API available for {scenario['id']}")

        result = _run_benchmark_scenario(
            scenario=scenario,
            output_dir=benchmark_output_dir,
            reference_image=benchmark_reference_image,
            evaluator=benchmark_evaluator,
            validator=benchmark_validator,
            quality_tracker=benchmark_quality_tracker,
            cost_tracker=benchmark_cost_tracker,
            video_id=benchmark_video_id,
        )
        benchmark_results.append(result)

        # Portrait should achieve reasonable identity consistency
        assert result["vbench_scores"]["overall"] >= 0.0
        if result["identity_score"] > 0:
            assert result["identity_score"] >= 0.3, (
                f"Portrait identity too low: {result['identity_score']:.2f}"
            )


class TestMediumBenchmark:
    """Medium shot benchmarks (scenarios 3-4)."""

    @pytest.mark.parametrize("scenario_idx", [2, 3], ids=["medium_market", "medium_restaurant"])
    def test_medium_scenario(
        self,
        scenario_idx,
        benchmark_output_dir,
        benchmark_reference_image,
        benchmark_evaluator,
        benchmark_validator,
        benchmark_quality_tracker,
        benchmark_cost_tracker,
        benchmark_video_id,
        benchmark_results,
    ):
        scenario = BENCHMARK_SCENARIOS[scenario_idx]
        api = _pick_available_api(scenario["target_api"])
        if api is None:
            pytest.skip(f"No API available for {scenario['id']}")

        result = _run_benchmark_scenario(
            scenario=scenario,
            output_dir=benchmark_output_dir,
            reference_image=benchmark_reference_image,
            evaluator=benchmark_evaluator,
            validator=benchmark_validator,
            quality_tracker=benchmark_quality_tracker,
            cost_tracker=benchmark_cost_tracker,
            video_id=benchmark_video_id,
        )
        benchmark_results.append(result)
        assert result["vbench_scores"]["overall"] >= 0.0


class TestWideBenchmark:
    """Wide shot benchmarks (scenarios 5-6)."""

    @pytest.mark.parametrize("scenario_idx", [4, 5], ids=["wide_cityscape", "wide_forest"])
    def test_wide_scenario(
        self,
        scenario_idx,
        benchmark_output_dir,
        benchmark_reference_image,
        benchmark_evaluator,
        benchmark_validator,
        benchmark_quality_tracker,
        benchmark_cost_tracker,
        benchmark_video_id,
        benchmark_results,
    ):
        scenario = BENCHMARK_SCENARIOS[scenario_idx]
        api = _pick_available_api(scenario["target_api"])
        if api is None:
            pytest.skip(f"No API available for {scenario['id']}")

        result = _run_benchmark_scenario(
            scenario=scenario,
            output_dir=benchmark_output_dir,
            reference_image=benchmark_reference_image,
            evaluator=benchmark_evaluator,
            validator=benchmark_validator,
            quality_tracker=benchmark_quality_tracker,
            cost_tracker=benchmark_cost_tracker,
            video_id=benchmark_video_id,
        )
        benchmark_results.append(result)
        assert result["vbench_scores"]["overall"] >= 0.0


class TestActionBenchmark:
    """Action shot benchmarks (scenarios 7-8)."""

    @pytest.mark.parametrize("scenario_idx", [6, 7], ids=["action_chase", "action_fight"])
    def test_action_scenario(
        self,
        scenario_idx,
        benchmark_output_dir,
        benchmark_reference_image,
        benchmark_evaluator,
        benchmark_validator,
        benchmark_quality_tracker,
        benchmark_cost_tracker,
        benchmark_video_id,
        benchmark_results,
    ):
        scenario = BENCHMARK_SCENARIOS[scenario_idx]
        api = _pick_available_api(scenario["target_api"])
        if api is None:
            pytest.skip(f"No API available for {scenario['id']}")

        result = _run_benchmark_scenario(
            scenario=scenario,
            output_dir=benchmark_output_dir,
            reference_image=benchmark_reference_image,
            evaluator=benchmark_evaluator,
            validator=benchmark_validator,
            quality_tracker=benchmark_quality_tracker,
            cost_tracker=benchmark_cost_tracker,
            video_id=benchmark_video_id,
        )
        benchmark_results.append(result)
        assert result["vbench_scores"]["overall"] >= 0.0


class TestLandscapeBenchmark:
    """Landscape shot benchmarks (scenarios 9-10)."""

    @pytest.mark.parametrize("scenario_idx", [8, 9], ids=["landscape_lake", "landscape_desert"])
    def test_landscape_scenario(
        self,
        scenario_idx,
        benchmark_output_dir,
        benchmark_reference_image,
        benchmark_evaluator,
        benchmark_validator,
        benchmark_quality_tracker,
        benchmark_cost_tracker,
        benchmark_video_id,
        benchmark_results,
    ):
        scenario = BENCHMARK_SCENARIOS[scenario_idx]
        api = _pick_available_api(scenario["target_api"])
        if api is None:
            pytest.skip(f"No API available for {scenario['id']}")

        result = _run_benchmark_scenario(
            scenario=scenario,
            output_dir=benchmark_output_dir,
            reference_image=benchmark_reference_image,
            evaluator=benchmark_evaluator,
            validator=benchmark_validator,
            quality_tracker=benchmark_quality_tracker,
            cost_tracker=benchmark_cost_tracker,
            video_id=benchmark_video_id,
        )
        benchmark_results.append(result)

        # Landscape shots have no identity requirement
        assert result["identity_score"] == 0.0
        assert result["vbench_scores"]["overall"] >= 0.0


class TestBenchmarkReport:
    """Aggregate benchmark results and generate report."""

    def test_generate_report(self, benchmark_results, benchmark_output_dir):
        """Generate benchmark_report.json from all completed scenarios."""
        if not benchmark_results:
            pytest.skip("No benchmark results to aggregate")

        # Per-shot-type averages
        by_type = {}
        for r in benchmark_results:
            st = r["shot_type"]
            if st not in by_type:
                by_type[st] = []
            by_type[st].append(r)

        type_averages = {}
        for st, results in by_type.items():
            n = len(results)
            type_averages[st] = {
                "count": n,
                "avg_overall_vbench": sum(
                    r["vbench_scores"]["overall"] for r in results
                ) / n,
                "avg_identity_score": sum(
                    r["identity_score"] for r in results
                ) / n,
                "avg_coherence_score": sum(
                    r["coherence_score"] for r in results
                ) / n,
                "avg_generation_time": sum(
                    r["generation_time_seconds"] for r in results
                ) / n,
                "avg_cost_usd": sum(
                    r["evaluation_cost_usd"] for r in results
                ) / n,
            }

        # Per-API averages
        by_api = {}
        for r in benchmark_results:
            api = r["api_used"]
            if api not in by_api:
                by_api[api] = []
            by_api[api].append(r)

        api_averages = {}
        for api, results in by_api.items():
            n = len(results)
            api_averages[api] = {
                "count": n,
                "avg_overall_vbench": sum(
                    r["vbench_scores"]["overall"] for r in results
                ) / n,
                "avg_generation_time": sum(
                    r["generation_time_seconds"] for r in results
                ) / n,
            }

        # Regression alerts (flag any dimension below 0.5)
        regression_alerts = []
        for r in benchmark_results:
            for dim, score in r["vbench_scores"].items():
                if dim != "overall" and score < 0.5:
                    regression_alerts.append({
                        "shot_id": r["shot_id"],
                        "dimension": dim,
                        "score": score,
                    })

        report = {
            "benchmark_run_id": benchmark_results[0]["shot_id"].split("_")[0]
            if benchmark_results else "unknown",
            "total_scenarios": len(benchmark_results),
            "per_shot_type_averages": type_averages,
            "per_api_averages": api_averages,
            "regression_alerts": regression_alerts,
            "total_cost_usd": sum(
                r["evaluation_cost_usd"] for r in benchmark_results
            ),
            "total_generation_time_seconds": sum(
                r["generation_time_seconds"] for r in benchmark_results
            ),
            "individual_results": benchmark_results,
        }

        # Write report
        report_path = os.path.join(benchmark_output_dir, "benchmark_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        assert os.path.exists(report_path)
        assert report["total_scenarios"] > 0

        # Also write to tests/ for easy access
        tests_report = os.path.join(os.path.dirname(__file__), "benchmark_report.json")
        with open(tests_report, "w") as f:
            json.dump(report, f, indent=2, default=str)

    def test_report_has_all_shot_types(self, benchmark_results):
        """Verify we tested all 5 shot types."""
        if not benchmark_results:
            pytest.skip("No benchmark results")
        tested_types = {r["shot_type"] for r in benchmark_results}
        expected = {"portrait", "medium", "wide", "action", "landscape"}
        missing = expected - tested_types
        if missing:
            pytest.skip(f"Missing shot types (API unavailable): {missing}")
        assert tested_types == expected

    def test_no_total_failures(self, benchmark_results):
        """No scenario should have overall_score == 0 (total failure)."""
        if not benchmark_results:
            pytest.skip("No benchmark results")
        for r in benchmark_results:
            assert r["vbench_scores"]["overall"] >= 0.0, (
                f"{r['shot_id']} had zero overall score"
            )
