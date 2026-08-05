"""The runtime graph must stay pinned to the committed Kijai/VHS contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from comfyui_client import ComfyUIReadinessError, ComfyUIClient
from performance.live_portrait_workflow import (
    LIVE_PORTRAIT_INGEST_WIDTH,
    LIVE_PORTRAIT_REQUIRED_NODE_CLASSES,
    build_live_portrait_workflow,
)


_OBJECT_INFO = Path(__file__).parents[1] / "fixtures" / "liveportrait_object_info.json"


def test_graph_passes_the_pinned_object_info_contract():
    workflow = build_live_portrait_workflow(
        "remote-frame.png", "remote-driving.mp4", 2.0
    )
    object_info = json.loads(_OBJECT_INFO.read_text(encoding="utf-8"))

    ComfyUIClient._validate_workflow_contract(workflow, object_info)

    assert {node["class_type"] for node in workflow.values()} == set(
        LIVE_PORTRAIT_REQUIRED_NODE_CLASSES
    )
    assert workflow["11"]["inputs"]["frame_load_cap"] == 50
    assert workflow["11"]["inputs"]["custom_width"] == LIVE_PORTRAIT_INGEST_WIDTH
    assert workflow["11"]["inputs"]["custom_height"] == 0
    assert workflow["19"]["inputs"] == {
        "images": ["18", 0],
        "frame_rate": 25,
        "loop_count": 0,
        "filename_prefix": "live_portrait",
        "format": "video/h264-mp4",
        "pingpong": False,
        "save_output": True,
    }


def test_old_inline_graph_shape_fails_the_pinned_contract():
    old_graph = {
        "20": {
            "class_type": "LivePortraitProcess",
            "inputs": {
                "source_image": ["10", 0],
                "driving_video": ["11", 0],
                "frame_load_cap": 50,
            },
        }
    }
    object_info = json.loads(_OBJECT_INFO.read_text(encoding="utf-8"))

    with pytest.raises(ComfyUIReadinessError, match="missing inputs"):
        ComfyUIClient._validate_workflow_contract(old_graph, object_info)


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf"), 8.01])
def test_graph_rejects_unbounded_or_invalid_duration(duration):
    with pytest.raises(ValueError):
        build_live_portrait_workflow("frame.png", "driving.mp4", duration)


def test_eight_second_production_cap_is_exactly_two_hundred_frames():
    workflow = build_live_portrait_workflow("frame.png", "driving.mp4", 8.0)
    assert workflow["11"]["inputs"]["frame_load_cap"] == 200
