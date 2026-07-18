"""TDD tests for Task 7: thread per-character char_lora_strength to ComfyUI injection.

Three hops verified (of the original four — Hop 4, quality_max._inject_identity,
retired WS1 Task 4 with no production replacement; char_lora_strength is
registered in char_lora_strengths for a future consumer, currently dormant):
  1. cinema/context.py        -- char_lora_strengths field declared
  2. cinema/shots/controller  -- reads strength from settings, forwards at call site
  3. phase_c_assembly         -- char_lora_strength param accepted (forwarding
                                  target retired; param is dormant-preserved)

Backward-compat invariant: absent/None strength → tier default (params["lora_strength_model"]).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Hop 1: cinema/context.py declares char_lora_strengths field
# ---------------------------------------------------------------------------

def test_pipeline_context_has_char_lora_strengths_field():
    """PipelineContext must declare char_lora_strengths as a dict field."""
    from cinema.context import PipelineContext
    ctx = PipelineContext(global_settings={})
    assert hasattr(ctx, "char_lora_strengths"), (
        "PipelineContext must have char_lora_strengths field (Task 7 Hop 1)"
    )
    assert isinstance(ctx.char_lora_strengths, dict)


# ---------------------------------------------------------------------------
# Hop 2: controller reads char_lora_strengths and forwards char_lora_strength
# ---------------------------------------------------------------------------

def _build_controller_for_lora_strength():
    """Minimal controller that can reach the generate_ai_broll seam.

    Mirrors _build_keyframe_controller() in test_hidream_image_routing.py.
    """
    from cinema.shots.controller import ShotController

    char_id = "char_abc"
    shot = {
        "id": "shot_1_0",
        "plan_status": "approved",
        "characters_in_frame": [char_id],
        "primary_character": char_id,
        "camera": "medium_shot",
        "target_api": "AUTO",
    }
    scene = {
        "id": "scene_1",
        "title": "T",
        "action": "A",
        "location_id": None,
        "shots": [shot],
    }
    project = {
        "id": "proj_1",
        "scenes": [scene],
        "characters": [],
        "objects": [],
        "locations": [],
        "global_settings": {
            "char_lora_paths": {char_id: "/fake/mara.safetensors"},
            "char_lora_strengths": {char_id: 0.55},
        },
    }

    host = MagicMock()
    host._refresh_project_snapshot.return_value = project
    lifecycle = MagicMock()
    runstate = MagicMock()
    runstate.shot_results = {}
    core = MagicMock()
    core.project = project
    core.project_dir = "/tmp/fake_project"
    core.continuity.enhance_shot_prompt.return_value = {
        "prompt": "base prompt",
        "continuity_config": {},
    }
    core.cost_tracker = MagicMock()
    # Pre-spend budget gate (FOLLOW-UP (a)): an unconfigured MagicMock's
    # would_exceed(...) return value is itself a truthy MagicMock, which
    # would spuriously trip the gate before this helper's seam is reached.
    core.cost_tracker.would_exceed.return_value = False

    ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
    ctrl._take_output_path = MagicMock(return_value="/nonexistent/keyframe.jpg")
    ctrl._resolve_previous_approved_keyframe = MagicMock(return_value="")
    ctrl._mutate_shot = MagicMock()
    return ctrl, project, char_id


def test_controller_forwards_char_lora_strength():
    """Controller reads char_lora_strengths[primary_char_id] and passes it to generate_ai_broll."""
    ctrl, project, char_id = _build_controller_for_lora_strength()

    with patch("cinema.shots.controller.generate_ai_broll") as mock_broll:
        ctrl.generate_keyframe_take("scene_1", "shot_1_0", positive_prompt="a test prompt")

    mock_broll.assert_called_once()
    kwargs = mock_broll.call_args.kwargs
    assert "char_lora_strength" in kwargs, (
        f"generate_ai_broll must be called with char_lora_strength kwarg; "
        f"got kwargs keys: {list(kwargs.keys())}"
    )
    assert kwargs["char_lora_strength"] == 0.55, (
        f"expected char_lora_strength=0.55, got {kwargs['char_lora_strength']!r}"
    )


def test_controller_passes_none_when_no_strength_set():
    """When char_lora_strengths is absent from settings, char_lora_strength=None is forwarded."""
    ctrl, project, char_id = _build_controller_for_lora_strength()
    # Remove the strengths dict from settings
    del project["global_settings"]["char_lora_strengths"]

    with patch("cinema.shots.controller.generate_ai_broll") as mock_broll:
        ctrl.generate_keyframe_take("scene_1", "shot_1_0", positive_prompt="a test prompt")

    mock_broll.assert_called_once()
    kwargs = mock_broll.call_args.kwargs
    assert kwargs.get("char_lora_strength") is None, (
        f"expected char_lora_strength=None when no strengths dict; "
        f"got {kwargs.get('char_lora_strength')!r}"
    )


# ---------------------------------------------------------------------------
# Hop 3: phase_c_assembly.generate_ai_broll accepts + forwards char_lora_strength
# ---------------------------------------------------------------------------

def test_phase_c_assembly_accepts_char_lora_strength_param():
    """generate_ai_broll must accept a char_lora_strength kwarg (not TypeError)."""
    import inspect
    import phase_c_assembly
    sig = inspect.signature(phase_c_assembly.generate_ai_broll)
    assert "char_lora_strength" in sig.parameters, (
        f"phase_c_assembly.generate_ai_broll must declare char_lora_strength param; "
        f"current params: {list(sig.parameters.keys())}"
    )

