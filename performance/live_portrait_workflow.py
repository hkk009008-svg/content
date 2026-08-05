"""Pinned API workflow for ComfyUI-LivePortraitKJ 1.1.0.

This graph targets commit ``4d9dc6205b793ffd0fb319816136d9b8c0dbfdff``
and Video Helper Suite commit ``4ee72c065db22c9d96c2427954dc69e7b908444b``.
Keep changes synchronized with the worker revision manifest and the committed
``/object_info`` contract fixture.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


LIVE_PORTRAIT_FPS = 25
LIVE_PORTRAIT_INGEST_WIDTH = 512
# Production envelope for the local 25 fps worker: no request may admit more
# than 200 driving frames into the GPU batch.  The controller independently
# derives this from scene-duration / shot-count and the UI reports the same cap.
MAX_LIVE_PORTRAIT_DURATION_S = 8.0


def _frame_load_cap(duration_s: float) -> int:
    try:
        duration = float(duration_s)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("LivePortrait duration must be a finite number") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("LivePortrait duration must be greater than zero")
    if duration > MAX_LIVE_PORTRAIT_DURATION_S:
        raise ValueError(
            f"LivePortrait duration cannot exceed {MAX_LIVE_PORTRAIT_DURATION_S:g} seconds"
        )
    return max(1, int(round(duration * LIVE_PORTRAIT_FPS)))


def build_live_portrait_workflow(
    remote_keyframe: str,
    remote_driving_video: str,
    duration_s: float,
) -> dict[str, dict[str, Any]]:
    """Build the commercial-friendly MediaPipe LivePortrait graph."""

    if not isinstance(remote_keyframe, str) or not remote_keyframe.strip():
        raise ValueError("remote_keyframe must be a non-empty filename")
    if not isinstance(remote_driving_video, str) or not remote_driving_video.strip():
        raise ValueError("remote_driving_video must be a non-empty filename")

    return {
        "10": {
            "class_type": "LoadImage",
            "inputs": {"image": remote_keyframe},
        },
        "11": {
            "class_type": "VHS_LoadVideo",
            "inputs": {
                "video": remote_driving_video,
                "force_rate": LIVE_PORTRAIT_FPS,
                # Bound the frame batch before it enters LivePortrait. Leaving
                # both dimensions at zero preserves arbitrary source size and
                # can expand a short 4K upload into tens of gigabytes of float
                # tensors. VHS derives height from aspect ratio when it is 0.
                "custom_width": LIVE_PORTRAIT_INGEST_WIDTH,
                "custom_height": 0,
                "frame_load_cap": _frame_load_cap(duration_s),
                "skip_first_frames": 0,
                "select_every_nth": 1,
            },
        },
        "12": {
            "class_type": "DownloadAndLoadLivePortraitModels",
            "inputs": {"precision": "fp16", "mode": "human"},
        },
        "13": {
            "class_type": "LivePortraitLoadMediaPipeCropper",
            "inputs": {
                "landmarkrunner_onnx_device": "CPU",
                "keep_model_loaded": True,
            },
        },
        "14": {
            "class_type": "LivePortraitCropper",
            "inputs": {
                "pipeline": ["12", 0],
                "cropper": ["13", 0],
                "source_image": ["10", 0],
                "dsize": 512,
                "scale": 2.3,
                "vx_ratio": 0.0,
                "vy_ratio": -0.125,
                "face_index": 0,
                "face_index_order": "large-small",
                "rotate": True,
            },
        },
        "15": {
            "class_type": "LivePortraitCropper",
            "inputs": {
                "pipeline": ["12", 0],
                "cropper": ["13", 0],
                "source_image": ["11", 0],
                "dsize": 512,
                "scale": 2.3,
                "vx_ratio": 0.0,
                "vy_ratio": -0.125,
                "face_index": 0,
                "face_index_order": "large-small",
                "rotate": True,
            },
        },
        "16": {
            "class_type": "LivePortraitRetargeting",
            "inputs": {
                "driving_crop_info": ["15", 1],
                "eye_retargeting": True,
                "eyes_retargeting_multiplier": 1.0,
                "lip_retargeting": True,
                "lip_retargeting_multiplier": 1.0,
            },
        },
        "17": {
            "class_type": "LivePortraitProcess",
            "inputs": {
                "pipeline": ["12", 0],
                "crop_info": ["14", 1],
                "source_image": ["10", 0],
                "driving_images": ["11", 0],
                "lip_zero": False,
                "lip_zero_threshold": 0.03,
                "stitching": True,
                "delta_multiplier": 1.0,
                "mismatch_method": "constant",
                "relative_motion_mode": "relative",
                "driving_smooth_observation_variance": 0.000003,
                "opt_retargeting_info": ["16", 0],
                "expression_friendly": True,
                "expression_friendly_multiplier": 1.0,
            },
        },
        "18": {
            "class_type": "LivePortraitComposite",
            "inputs": {
                "source_image": ["10", 0],
                "cropped_image": ["17", 0],
                "liveportrait_out": ["17", 1],
            },
        },
        "19": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["18", 0],
                "frame_rate": LIVE_PORTRAIT_FPS,
                "loop_count": 0,
                "filename_prefix": "live_portrait",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
            },
        },
    }


def required_live_portrait_node_classes(
    workflow: Mapping[str, Mapping[str, Any]] | None = None,
) -> frozenset[str]:
    graph = workflow or build_live_portrait_workflow(
        "contract-keyframe.png", "contract-driving.mp4", 2.0
    )
    return frozenset(
        node["class_type"]
        for node in graph.values()
        if isinstance(node.get("class_type"), str)
    )


LIVE_PORTRAIT_REQUIRED_NODE_CLASSES = required_live_portrait_node_classes()
