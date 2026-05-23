import pytest

from workflow_selector import (
    classify_shot_type,
    get_workflow_params,
    apply_workflow_params,
    WORKFLOW_TEMPLATES,
    SHOT_TYPE_KEYWORDS,
    MOTION_FIDELITY_FLOORS,
    get_adaptive_pulid_weight,
)
from domain.shot_types import (
    SHOT_TYPE_CLOSE,
    SHOT_TYPE_PORTRAIT,
    SHOT_TYPE_MEDIUM,
    SHOT_TYPE_WIDE,
    SHOT_TYPE_LANDSCAPE,
    SHOT_TYPE_ACTION,
)
from identity.types import FailureReason


# Valid target_api / video_fallback values accepted by the cinema pipeline.
# Sourced from WORKFLOW_TEMPLATES + handoff §3.3 valid-api list.
_VALID_APIS = {
    "KLING_NATIVE",
    "LTX",
    "SORA_NATIVE",
    "RUNWAY_GEN4",
    "VEO_NATIVE",
    "KLING_3_0",
    "SEEDANCE",
}


# --- classify_shot_type ---

class TestClassifyShotType:
    def test_no_characters_returns_landscape(self):
        shot = {"prompt": "a beautiful sunset", "characters_in_frame": []}
        assert classify_shot_type(shot) == "landscape"

    def test_no_characters_key_returns_landscape(self):
        shot = {"prompt": "a beautiful sunset"}
        assert classify_shot_type(shot) == "landscape"

    def test_close_up_in_prompt_returns_portrait(self):
        shot = {"prompt": "A close-up of the detective", "characters_in_frame": ["char1"]}
        assert classify_shot_type(shot) == "portrait"

    def test_wide_shot_in_prompt_returns_wide(self):
        shot = {"prompt": "A wide shot of the city streets", "characters_in_frame": ["char1"]}
        assert classify_shot_type(shot) == "wide"

    def test_tracking_shot_in_prompt_returns_action(self):
        shot = {"prompt": "A tracking shot following the hero", "characters_in_frame": ["char1"]}
        assert classify_shot_type(shot) == "action"

    def test_medium_shot_in_prompt_returns_medium(self):
        shot = {"prompt": "A medium shot of two people talking", "characters_in_frame": ["char1"]}
        assert classify_shot_type(shot) == "medium"

    def test_no_matching_keywords_defaults_to_medium(self):
        shot = {"prompt": "The character stands still", "characters_in_frame": ["char1"]}
        assert classify_shot_type(shot) == "medium"

    def test_keyword_in_camera_field_matches(self):
        shot = {
            "prompt": "The character looks around",
            "camera": "85mm lens portrait framing",
            "characters_in_frame": ["char1"],
        }
        assert classify_shot_type(shot) == "portrait"

    def test_shot_section_extraction_works(self):
        shot = {
            "prompt": "[SHOT] close-up of face [ACTION] walking forward",
            "characters_in_frame": ["char1"],
        }
        assert classify_shot_type(shot) == "portrait"


# --- get_workflow_params ---

class TestGetWorkflowParams:
    def test_known_shot_type_returns_correct_params(self):
        params = get_workflow_params("portrait")
        assert params["pulid_weight"] == 1.0
        assert params["guidance"] == 3.5
        assert params["steps"] == 25

    def test_unknown_type_falls_back_to_medium(self):
        params = get_workflow_params("nonexistent_type")
        expected = get_workflow_params("medium")
        assert params == expected

    def test_returns_copy_not_reference(self):
        params1 = get_workflow_params("portrait")
        params2 = get_workflow_params("portrait")
        params1["steps"] = 999
        assert params2["steps"] != 999


# --- apply_workflow_params ---

class TestApplyWorkflowParams:
    def _make_workflow(self):
        return {
            "100": {"inputs": {"weight": 0, "start_at": 0, "end_at": 0}},
            "60": {"inputs": {"guidance": 0}},
            "17": {"inputs": {"steps": 0, "scheduler": ""}},
            "16": {"inputs": {"sampler_name": ""}},
            "301": {"inputs": {"scale": 0}},
        }

    def test_sets_correct_node_values(self):
        workflow = self._make_workflow()
        params = get_workflow_params("portrait")
        result = apply_workflow_params(workflow, params)

        assert result["100"]["inputs"]["weight"] == 1.0
        assert result["100"]["inputs"]["start_at"] == 0.2
        assert result["100"]["inputs"]["end_at"] == 1.0
        assert result["60"]["inputs"]["guidance"] == 3.5
        assert result["17"]["inputs"]["steps"] == 25
        assert result["17"]["inputs"]["scheduler"] == "sgm_uniform"
        assert result["16"]["inputs"]["sampler_name"] == "dpmpp_2m"
        assert result["301"]["inputs"]["scale"] == 3.0

    def test_missing_nodes_doesnt_crash(self):
        workflow = {"999": {"inputs": {}}}
        params = get_workflow_params("portrait")
        result = apply_workflow_params(workflow, params)
        assert result is workflow  # returns same object, no error


# --- Template completeness ---

class TestTemplateCompleteness:
    REQUIRED_KEYS = ["target_api", "video_fallbacks", "pulid_weight", "guidance", "steps"]

    @pytest.mark.parametrize("shot_type", WORKFLOW_TEMPLATES.keys())
    def test_each_shot_type_has_required_keys(self, shot_type):
        template = WORKFLOW_TEMPLATES[shot_type]
        for key in self.REQUIRED_KEYS:
            assert key in template, f"{shot_type} missing required key '{key}'"


# --- Parameter value bounds ---


class TestParameterBounds:
    """Verify all template parameters are within sensible ranges."""

    @pytest.mark.parametrize("shot_type", WORKFLOW_TEMPLATES.keys())
    def test_pulid_weight_range(self, shot_type):
        p = WORKFLOW_TEMPLATES[shot_type]["pulid_weight"]
        assert 0.0 <= p <= 1.0, f"{shot_type} pulid_weight={p} out of [0,1]"

    @pytest.mark.parametrize("shot_type", WORKFLOW_TEMPLATES.keys())
    def test_guidance_range(self, shot_type):
        g = WORKFLOW_TEMPLATES[shot_type]["guidance"]
        assert 1.0 <= g <= 10.0, f"{shot_type} guidance={g} out of [1,10]"

    @pytest.mark.parametrize("shot_type", WORKFLOW_TEMPLATES.keys())
    def test_steps_range(self, shot_type):
        s = WORKFLOW_TEMPLATES[shot_type]["steps"]
        assert 10 <= s <= 50, f"{shot_type} steps={s} out of [10,50]"


# --- Full keyword sweep ---------------------------------------------------


class TestClassifyShotTypeKeywords:
    """Every entry in SHOT_TYPE_KEYWORDS must route to its declared bucket."""

    @pytest.mark.parametrize(
        "kw,expected_bucket",
        [(kw, b) for b, kws in SHOT_TYPE_KEYWORDS.items() for kw in kws],
    )
    def test_keyword_routes_to_bucket(self, kw, expected_bucket):
        # Landscape keywords still need characters_in_frame so the
        # no-character short-circuit doesn't pre-empt the keyword check.
        shot = {
            "prompt": f"a {kw} of something",
            "camera": "",
            "characters_in_frame": ["c1"],
        }
        assert classify_shot_type(shot) == expected_bucket, (
            f"keyword '{kw}' (declared in {expected_bucket}) routed elsewhere"
        )


# --- Shot-section priority over full prompt -------------------------------


class TestClassifyShotTypePriority:
    def test_shot_section_wins_over_full_prompt(self):
        """[SHOT] section wins when full prompt contains a conflicting keyword."""
        shot = {
            "prompt": "[SHOT] portrait headshot [SCENE] wide angle landscape vista",
            "camera": "",
            "characters_in_frame": ["c1"],
        }
        assert classify_shot_type(shot) == "portrait"


# --- WORKFLOW_TEMPLATES structural shape ----------------------------------


class TestWorkflowTemplatesShape:
    EXPECTED_KEYS = {"portrait", "medium", "wide", "action", "landscape"}

    def test_exactly_five_shot_types(self):
        assert set(WORKFLOW_TEMPLATES.keys()) == self.EXPECTED_KEYS

    @pytest.mark.parametrize("shot_type", WORKFLOW_TEMPLATES.keys())
    def test_target_api_is_valid(self, shot_type):
        target = WORKFLOW_TEMPLATES[shot_type]["target_api"]
        assert target in _VALID_APIS, (
            f"{shot_type} target_api={target!r} not in valid API set"
        )

    @pytest.mark.parametrize("shot_type", WORKFLOW_TEMPLATES.keys())
    def test_video_fallbacks_nonempty_and_valid(self, shot_type):
        fallbacks = WORKFLOW_TEMPLATES[shot_type]["video_fallbacks"]
        assert isinstance(fallbacks, list) and len(fallbacks) > 0, (
            f"{shot_type} video_fallbacks must be a non-empty list"
        )
        for api in fallbacks:
            assert api in _VALID_APIS, (
                f"{shot_type} video_fallback {api!r} not in valid API set"
            )


# --- MOTION_FIDELITY_FLOORS keys and sentinels ----------------------------


class TestMotionFidelityFloors:
    CANONICAL = {
        SHOT_TYPE_CLOSE,
        SHOT_TYPE_PORTRAIT,
        SHOT_TYPE_MEDIUM,
        SHOT_TYPE_WIDE,
        SHOT_TYPE_LANDSCAPE,
        SHOT_TYPE_ACTION,
    }

    def test_keys_subset_of_canonical_shot_types(self):
        assert set(MOTION_FIDELITY_FLOORS.keys()) <= self.CANONICAL, (
            "MOTION_FIDELITY_FLOORS has key(s) outside the canonical "
            "domain.shot_types set"
        )

    def test_landscape_floor_is_none(self):
        # Sentinel: None means "motion capture doesn't apply" for pure
        # landscape shots (no characters to retarget).
        assert MOTION_FIDELITY_FLOORS["landscape"] is None


# --- get_adaptive_pulid_weight --------------------------------------------


class _StubStats:
    """Minimal validator stub: returns a fixed rolling-stats dict."""

    def __init__(self, stats: dict):
        self._stats = stats

    def get_rolling_stats(self, character_id: str) -> dict:  # noqa: ARG002
        return self._stats


class TestGetAdaptivePulidWeight:
    """Cover all 4 boost paths + clamp + face-failure suppression."""

    def test_returns_base_when_validator_none(self):
        # portrait base is 1.0 (matches WORKFLOW_TEMPLATES["portrait"])
        result = get_adaptive_pulid_weight("portrait", "char_a", None)
        assert result == pytest.approx(1.0)

    def test_no_samples_returns_base(self):
        validator = _StubStats({"sample_count": 0})
        # medium base is 0.9
        result = get_adaptive_pulid_weight("medium", "char_a", validator)
        assert result == pytest.approx(0.9)

    def test_failure_boost_plus_010(self):
        validator = _StubStats(
            {
                "sample_count": 5,
                "suggested_pulid_delta": 0.10,
                "common_failure": None,
            }
        )
        # medium base 0.9 + 0.10 → 1.0 (also exactly hits the upper clamp)
        result = get_adaptive_pulid_weight("medium", "char_a", validator)
        assert result == pytest.approx(1.0)

    def test_near_pass_boost_plus_005(self):
        validator = _StubStats(
            {
                "sample_count": 5,
                "suggested_pulid_delta": 0.05,
                "common_failure": None,
            }
        )
        # action base 0.8 + 0.05 → 0.85
        result = get_adaptive_pulid_weight("action", "char_a", validator)
        assert result == pytest.approx(0.85)

    def test_overperform_reduces_minus_005(self):
        validator = _StubStats(
            {
                "sample_count": 5,
                "suggested_pulid_delta": -0.05,
                "common_failure": None,
            }
        )
        # action base 0.8 + (-0.05) → 0.75
        result = get_adaptive_pulid_weight("action", "char_a", validator)
        assert result == pytest.approx(0.75)

    def test_clamped_to_unit_interval(self):
        # Upper clamp: explicit base_params with weight 0.95, delta +0.10 → 1.0
        validator_hi = _StubStats(
            {
                "sample_count": 5,
                "suggested_pulid_delta": 0.10,
                "common_failure": None,
            }
        )
        hi = get_adaptive_pulid_weight(
            "portrait", "char_a", validator_hi, base_params={"pulid_weight": 0.95}
        )
        assert hi == pytest.approx(1.0)

        # Lower clamp: base_params weight 0.05, delta -0.20 → 0.0
        validator_lo = _StubStats(
            {
                "sample_count": 5,
                "suggested_pulid_delta": -0.20,
                "common_failure": None,
            }
        )
        lo = get_adaptive_pulid_weight(
            "portrait", "char_a", validator_lo, base_params={"pulid_weight": 0.05}
        )
        assert lo == pytest.approx(0.0)

    def test_face_angle_extreme_zeros_positive_delta(self):
        # delta=+0.10 must be suppressed to 0 → adapted == base
        validator = _StubStats(
            {
                "sample_count": 5,
                "suggested_pulid_delta": 0.10,
                "common_failure": FailureReason.FACE_ANGLE_EXTREME,
            }
        )
        # portrait base 1.0; suppression keeps it at 1.0
        result = get_adaptive_pulid_weight(
            "portrait",
            "char_a",
            validator,
            base_params={"pulid_weight": 0.80},
        )
        assert result == pytest.approx(0.80)

    def test_face_angle_extreme_negative_delta_passes_through(self):
        # FACE_ANGLE_EXTREME is asymmetric: `delta = min(delta, 0.0)`
        # zeros POSITIVE deltas (don't boost PuLID for a problem it can't
        # fix) but leaves NEGATIVE deltas alone (still allowed to relax
        # PuLID when identity is over-performing). This guards that
        # asymmetry against an accidental symmetric `delta = 0.0` rewrite.
        validator = _StubStats(
            {
                "sample_count": 5,
                "suggested_pulid_delta": -0.05,
                "common_failure": FailureReason.FACE_ANGLE_EXTREME,
            }
        )
        result = get_adaptive_pulid_weight(
            "portrait",
            "char_a",
            validator,
            base_params={"pulid_weight": 0.80},
        )
        assert result == pytest.approx(0.75)  # 0.80 + (-0.05)

    def test_small_face_region_zeros_delta(self):
        # SMALL_FACE_REGION zeros the delta entirely (positive OR negative)
        validator = _StubStats(
            {
                "sample_count": 5,
                "suggested_pulid_delta": 0.10,
                "common_failure": FailureReason.SMALL_FACE_REGION,
            }
        )
        result = get_adaptive_pulid_weight(
            "wide",
            "char_a",
            validator,
            base_params={"pulid_weight": 0.65},
        )
        assert result == pytest.approx(0.65)
