import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from workflow_selector import (
    classify_shot_type,
    get_workflow_params,
    apply_workflow_params,
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
