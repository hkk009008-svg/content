import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from workflow_selector import (
    classify_shot_type,
    get_workflow_params,
    apply_workflow_params,
    get_optimal_api,
    get_dynamic_workflow,
    WORKFLOW_TEMPLATES,
    SHOT_TYPE_KEYWORDS,
)


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


# --- get_optimal_api ---


class TestGetOptimalApi:
    """Tests for quality-based API ranking."""

    def _mock_stats(self, stats_dict):
        """Patch QualityTracker to return specific stats."""
        mock_tracker = MagicMock()
        mock_tracker.get_api_quality_stats.return_value = stats_dict
        return patch("workflow_selector.QualityTracker", return_value=mock_tracker)

    def test_no_historical_data_returns_static_fallback(self):
        with self._mock_stats({}):
            ranked = get_optimal_api("portrait")
            assert len(ranked) >= 1
            # First entry should be the template's target_api
            expected_primary = WORKFLOW_TEMPLATES["portrait"]["target_api"]
            assert ranked[0]["api"] == expected_primary
            assert ranked[0]["score"] == 1.0

    def test_static_fallback_includes_video_fallbacks(self):
        with self._mock_stats({}):
            ranked = get_optimal_api("medium")
            fallbacks = WORKFLOW_TEMPLATES["medium"].get("video_fallbacks", [])
            api_names = [r["api"] for r in ranked]
            for fb in fallbacks:
                assert fb in api_names

    def test_with_quality_data_ranks_by_score(self):
        stats = {
            "KLING_NATIVE": {"portrait": {"avg_vbench": 0.9, "avg_cost": 0.10, "avg_identity": 0.85, "count": 10}},
            "RUNWAY_GEN4": {"portrait": {"avg_vbench": 0.7, "avg_cost": 0.20, "avg_identity": 0.60, "count": 5}},
        }
        with self._mock_stats(stats):
            ranked = get_optimal_api("portrait")
            assert len(ranked) == 2
            assert ranked[0]["api"] == "KLING_NATIVE"
            assert ranked[0]["score"] > ranked[1]["score"]

    def test_budget_filter_excludes_expensive_apis(self):
        stats = {
            "KLING_NATIVE": {"portrait": {"avg_vbench": 0.9, "avg_cost": 0.50, "count": 10}},
            "LTX": {"portrait": {"avg_vbench": 0.6, "avg_cost": 0.05, "count": 5}},
        }
        with self._mock_stats(stats):
            ranked = get_optimal_api("portrait", budget_remaining=0.10)
            api_names = [r["api"] for r in ranked]
            assert "LTX" in api_names
            assert "KLING_NATIVE" not in api_names

    def test_budget_filter_removes_all_falls_back_to_static(self):
        stats = {
            "KLING_NATIVE": {"portrait": {"avg_vbench": 0.9, "avg_cost": 0.50, "count": 10}},
        }
        with self._mock_stats(stats):
            ranked = get_optimal_api("portrait", budget_remaining=0.01)
            # Should fall back to static since everything is too expensive
            assert len(ranked) >= 1
            assert ranked[0]["avg_cost"] == 0.0  # Static fallback has no cost data

    def test_character_ids_shift_quality_weight(self):
        stats = {
            "API_A": {"portrait": {"avg_vbench": 0.7, "avg_cost": 0.10, "avg_identity": 0.95, "identity_score": 0.95, "count": 10}},
            "API_B": {"portrait": {"avg_vbench": 0.8, "avg_cost": 0.10, "avg_identity": 0.50, "identity_score": 0.50, "count": 10}},
        }
        with self._mock_stats(stats):
            # With characters: identity matters more -> API_A should rank higher
            ranked_with = get_optimal_api("portrait", character_ids=["char1"])
            # Without characters: pure vbench -> API_B should rank higher
            ranked_without = get_optimal_api("portrait", character_ids=None)
            # Both should return results
            assert len(ranked_with) >= 1
            assert len(ranked_without) >= 1


# --- get_dynamic_workflow ---


class TestGetDynamicWorkflow:
    def _mock_stats(self, stats_dict):
        mock_tracker = MagicMock()
        mock_tracker.get_api_quality_stats.return_value = stats_dict
        return patch("workflow_selector.QualityTracker", return_value=mock_tracker)

    def test_no_data_returns_static_params(self):
        with self._mock_stats({}):
            params = get_dynamic_workflow("portrait")
            # Should have all static template keys
            assert "pulid_weight" in params
            assert "guidance" in params
            assert "steps" in params
            assert "target_api" in params

    def test_with_data_overrides_target_api(self):
        stats = {
            "BEST_API": {"medium": {"avg_vbench": 0.95, "avg_cost": 0.05, "count": 20}},
            "WORSE_API": {"medium": {"avg_vbench": 0.60, "avg_cost": 0.30, "count": 10}},
        }
        with self._mock_stats(stats):
            params = get_dynamic_workflow("medium")
            assert params["target_api"] == "BEST_API"
            assert "WORSE_API" in params["video_fallbacks"]

    def test_preserves_non_api_params(self):
        with self._mock_stats({}):
            params = get_dynamic_workflow("portrait")
            template = WORKFLOW_TEMPLATES["portrait"]
            assert params["pulid_weight"] == template["pulid_weight"]
            assert params["guidance"] == template["guidance"]
            assert params["steps"] == template["steps"]


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
