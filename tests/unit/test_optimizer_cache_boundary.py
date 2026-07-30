"""Public optimizer-cache shape and historical consumer compatibility pins."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    "historical_cache",
    [
        ["not-a-mapping"],
        "not-a-mapping",
        {"source_prompt": "a test prompt", "spec": ["not-a-mapping"]},
        {"source_prompt": "a test prompt", "spec": "not-a-mapping"},
        {"source_prompt": "a test prompt", "spec": None},
    ],
)
def test_keyframe_consumer_treats_historical_non_mapping_cache_as_empty(
    historical_cache,
):
    """Exercise the real controller cache/spec `.get()` path near line 816."""

    from tests.unit.test_hidream_image_routing import (
        _build_keyframe_controller,
    )

    ctrl, project = _build_keyframe_controller()
    project["global_settings"]["prompt_optimizer_enabled"] = True
    project["scenes"][0]["shots"][0]["optimizer_cache"] = historical_cache
    valid_spec = {
        "image_prompt": "optimized prompt",
        "suggested_image_api": "FLUX_DEV",
    }

    with (
        patch("cinema.shots.controller.generate_ai_broll") as generate,
        patch(
            "llm.prompt_optimizer.optimize_shot_prompt",
            return_value=valid_spec,
        ),
    ):
        ctrl.generate_keyframe_take(
            "scene_1",
            "shot_1_0",
            positive_prompt="a test prompt",
        )

    generate.assert_called_once()


@pytest.mark.parametrize(
    "historical_cache",
    [
        ["not-a-mapping"],
        "not-a-mapping",
        {"spec": ["not-a-mapping"]},
        {"spec": "not-a-mapping"},
        {"spec": None},
    ],
)
def test_motion_consumer_treats_historical_non_mapping_cache_as_empty(
    tmp_path,
    historical_cache,
):
    """Exercise the real controller cache/spec `.get()` path near line 1900."""

    from tests.unit import test_dialogue_routing as routing

    harness = routing.TestAutoRoutingDecisions()
    project = harness._make_project(tmp_path, target_api="AUTO")
    project["scenes"][0]["shots"][0]["optimizer_cache"] = historical_cache

    with patch(
        "tests.unit.test_dialogue_routing._controller_routing_snapshot",
        return_value=routing._ready_veo_snapshot(),
    ):
        kwargs = harness._run_and_capture_gen_vid_kwargs(project, tmp_path)

    assert kwargs.get("target_api") == "AUTO"
    assert isinstance(kwargs.get("video_fallbacks"), list)
