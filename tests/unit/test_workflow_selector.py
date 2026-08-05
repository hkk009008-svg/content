from datetime import date

import pytest

from domain.provider_catalog import RuntimeSnapshot
from domain.shot_types import (
    SHOT_TYPE_ACTION,
    SHOT_TYPE_CLOSE,
    SHOT_TYPE_LANDSCAPE,
    SHOT_TYPE_MEDIUM,
    SHOT_TYPE_PORTRAIT,
    SHOT_TYPE_WIDE,
)
from domain.video_engine_policy import VideoPolicyReason
from workflow_selector import (
    MOTION_FIDELITY_FLOORS,
    SHOT_TYPE_KEYWORDS,
    WORKFLOW_TEMPLATES,
    classify_shot_type,
    get_motion_fidelity_floor,
    get_resolved_workflow_routing,
)


PRE_SUNSET = date(2026, 9, 23)
SUNSET = date(2026, 9, 24)


def _fal_snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(credentials={"fal_key"}, modules={"fal_client"})


class TestClassifyShotType:
    @pytest.mark.parametrize(
        ("shot", "expected"),
        [
            ({"prompt": "a beautiful sunset", "characters_in_frame": []}, "landscape"),
            ({"prompt": "A close-up of the detective", "characters_in_frame": ["c1"]}, "portrait"),
            ({"prompt": "A wide shot of the city", "characters_in_frame": ["c1"]}, "wide"),
            ({"prompt": "A tracking shot follows the hero", "characters_in_frame": ["c1"]}, "action"),
            ({"prompt": "A medium shot", "characters_in_frame": ["c1"]}, "medium"),
            ({"prompt": "The character waits", "characters_in_frame": ["c1"]}, "medium"),
        ],
    )
    def test_classification(self, shot, expected):
        assert classify_shot_type(shot) == expected

    def test_camera_and_structured_shot_text_are_classified(self):
        assert classify_shot_type(
            {
                "prompt": "The character looks around",
                "camera": "85mm portrait framing",
                "characters_in_frame": ["c1"],
            }
        ) == "portrait"
        assert classify_shot_type(
            {
                "prompt": "[SHOT] close-up of face [ACTION] walking forward",
                "characters_in_frame": ["c1"],
            }
        ) == "portrait"

    @pytest.mark.parametrize(
        ("keyword", "bucket"),
        [(keyword, bucket) for bucket, keywords in SHOT_TYPE_KEYWORDS.items() for keyword in keywords],
    )
    def test_every_declared_keyword_routes_to_its_bucket(self, keyword, bucket):
        expected = "wide" if bucket == "landscape" else bucket
        shot = {
            "prompt": f"a {keyword} of something",
            "camera": "",
            "characters_in_frame": ["c1"],
        }
        assert classify_shot_type(shot) == expected

    def test_character_bearing_landscape_routes_wide(self):
        shot = {
            "prompt": "an aerial vista of the valley",
            "camera": "",
            "characters_in_frame": ["hero"],
        }
        assert classify_shot_type(shot) == "wide"

    def test_shot_section_precedence_is_stable(self):
        shot = {
            "prompt": "[SHOT] portrait headshot [SCENE] wide angle landscape vista",
            "camera": "",
            "characters_in_frame": ["c1"],
        }
        assert classify_shot_type(shot) == "portrait"


class TestWorkflowTemplates:
    EXPECTED_TYPES = {"portrait", "medium", "wide", "action", "landscape"}
    REQUIRED_KEYS = {"target_api", "video_fallbacks", "description"}

    def test_exactly_five_provider_neutral_templates(self):
        assert set(WORKFLOW_TEMPLATES) == self.EXPECTED_TYPES
        for template in WORKFLOW_TEMPLATES.values():
            assert set(template) == self.REQUIRED_KEYS
            assert template["target_api"] == "GEMINI_OMNI"
            assert isinstance(template["video_fallbacks"], list)
            assert template["video_fallbacks"]
            assert "SORA_NATIVE" not in template["video_fallbacks"]

    def test_action_seed_order(self):
        assert WORKFLOW_TEMPLATES["action"]["video_fallbacks"] == [
            "VEO_NATIVE",
            "SEEDANCE",
            "KLING_3_0",
            "RUNWAY_GEN4",
            "LTX",
        ]


class TestResolvedWorkflowRouting:
    def test_filters_unavailable_providers_without_reordering(self):
        routing = get_resolved_workflow_routing(
            "portrait",
            runtime_snapshot=_fal_snapshot(),
            on_date=PRE_SUNSET,
        )
        assert routing.candidates == ("KLING_3_0", "SEEDANCE")
        assert routing.primary == "KLING_3_0"
        assert routing.fallbacks == ("SEEDANCE",)
        assert [(item.key, item.reason) for item in routing.rejections] == [
            ("GEMINI_OMNI", VideoPolicyReason.RUNTIME_UNAVAILABLE),
            ("VEO_NATIVE", VideoPolicyReason.RUNTIME_UNAVAILABLE),
            ("RUNWAY_GEN4", VideoPolicyReason.RUNTIME_UNAVAILABLE),
        ]

    def test_empty_runtime_returns_auto(self):
        routing = get_resolved_workflow_routing(
            "landscape",
            runtime_snapshot=RuntimeSnapshot(),
            on_date=PRE_SUNSET,
        )
        assert routing.candidates == ()
        assert routing.primary == "AUTO"
        assert routing.fallbacks == ()

    def test_project_disabled_engines_are_removed(self):
        routing = get_resolved_workflow_routing(
            "action",
            settings={
                "api_engines": {
                    "SEEDANCE": {"enabled": False},
                    "KLING_3_0": {"enabled": False},
                    "LTX": {"enabled": False},
                }
            },
            runtime_snapshot=_fal_snapshot(),
            on_date=PRE_SUNSET,
        )
        assert routing.candidates == ()
        assert {
            item.key
            for item in routing.rejections
            if item.reason is VideoPolicyReason.PROJECT_DISABLED
        } == {"SEEDANCE", "KLING_3_0", "LTX"}

    def test_automatic_routing_never_reintroduces_sora(self):
        snapshot = RuntimeSnapshot(
            credentials={"fal_key", "openai_api_key"},
            modules={"fal_client", "openai"},
        )
        for day in (PRE_SUNSET, SUNSET):
            routing = get_resolved_workflow_routing(
                "action",
                runtime_snapshot=snapshot,
                on_date=day,
            )
            assert "SORA_NATIVE" not in routing.candidates
            assert all(item.key != "SORA_NATIVE" for item in routing.rejections)


class TestMotionFidelityFloors:
    CANONICAL = {
        SHOT_TYPE_CLOSE,
        SHOT_TYPE_PORTRAIT,
        SHOT_TYPE_MEDIUM,
        SHOT_TYPE_WIDE,
        SHOT_TYPE_LANDSCAPE,
        SHOT_TYPE_ACTION,
    }

    def test_keys_and_landscape_sentinel(self):
        assert set(MOTION_FIDELITY_FLOORS) <= self.CANONICAL
        assert MOTION_FIDELITY_FLOORS["landscape"] is None
        assert get_motion_fidelity_floor("landscape") is None
        assert get_motion_fidelity_floor("unknown") is None
