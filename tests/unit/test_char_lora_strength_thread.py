"""TDD tests for Task 7: thread per-character char_lora_strength to ComfyUI injection.

Four hops verified:
  1. cinema/context.py        -- char_lora_strengths field declared
  2. cinema/shots/controller  -- reads strength from settings, forwards at call site
  3. phase_c_assembly         -- char_lora_strength param forwarded to generate_ai_broll_max
  4. quality_max              -- _inject_identity uses char_lora_strength over tier default

Backward-compat invariant: absent/None strength → tier default (params["lora_strength_model"]).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Hop 4: _inject_identity honors char_lora_strength
# ---------------------------------------------------------------------------

def test_inject_identity_honors_char_lora_strength():
    """When char_lora_strength=0.55, node-700 strength_model/strength_clip must be 0.55."""
    import quality_max
    wf = {"700": {"class_type": "LoraLoader", "inputs": {}}}
    params = {"lora_strength_model": 1.0, "lora_strength_clip": 1.0}
    quality_max._inject_identity(
        wf, "mara.safetensors", None, params, True, char_lora_strength=0.55
    )
    assert wf["700"]["inputs"]["strength_model"] == 0.55, (
        f"expected strength_model=0.55, got {wf['700']['inputs']['strength_model']!r}"
    )
    assert wf["700"]["inputs"]["strength_clip"] == 0.55, (
        f"expected strength_clip=0.55, got {wf['700']['inputs']['strength_clip']!r}"
    )


def test_inject_identity_uses_tier_default_when_strength_none():
    """When char_lora_strength=None, node-700 must use params['lora_strength_model'] (tier default)."""
    import quality_max
    wf = {"700": {"class_type": "LoraLoader", "inputs": {}}}
    params = {"lora_strength_model": 1.0, "lora_strength_clip": 1.0}
    quality_max._inject_identity(
        wf, "mara.safetensors", None, params, True, char_lora_strength=None
    )
    assert wf["700"]["inputs"]["strength_model"] == 1.0, (
        f"expected strength_model=1.0 (tier default), got {wf['700']['inputs']['strength_model']!r}"
    )
    assert wf["700"]["inputs"]["strength_clip"] == 1.0


def test_inject_identity_uses_tier_default_when_strength_absent():
    """When char_lora_strength is not passed at all (old callers), tier default must apply."""
    import quality_max
    wf = {"700": {"class_type": "LoraLoader", "inputs": {}}}
    params = {"lora_strength_model": 0.9, "lora_strength_clip": 0.9}
    # Don't pass char_lora_strength at all — backward compat
    quality_max._inject_identity(
        wf, "mara.safetensors", None, params, True
    )
    assert wf["700"]["inputs"]["strength_model"] == 0.9
    assert wf["700"]["inputs"]["strength_clip"] == 0.9


def test_inject_identity_strength_zero_is_honored():
    """Strength=0.0 is a valid override (not falsy-treated as None)."""
    import quality_max
    wf = {"700": {"class_type": "LoraLoader", "inputs": {}}}
    params = {"lora_strength_model": 1.0, "lora_strength_clip": 1.0}
    quality_max._inject_identity(
        wf, "mara.safetensors", None, params, True, char_lora_strength=0.0
    )
    assert wf["700"]["inputs"]["strength_model"] == 0.0


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


def test_phase_c_assembly_forwards_char_lora_strength_to_max():
    """In max-tier dispatch, char_lora_strength must be forwarded to generate_ai_broll_max.

    The import of quality_max is inside the function body (lazy), so we patch it
    via sys.modules before the call to intercept the internal call.
    """
    import sys
    import importlib

    fake_result = MagicMock()
    fake_result.__bool__ = lambda self: True

    mock_max = MagicMock(return_value=fake_result)
    fake_qm = MagicMock()
    fake_qm.generate_ai_broll_max = mock_max

    import phase_c_assembly

    old_qm = sys.modules.get("quality_max")
    sys.modules["quality_max"] = fake_qm
    try:
        phase_c_assembly.generate_ai_broll(
            "test prompt",
            "/tmp/out.jpg",
            quality_tier="max",
            char_lora_path="/fake/mara.safetensors",
            char_lora_strength=0.55,
        )
    finally:
        if old_qm is None:
            sys.modules.pop("quality_max", None)
        else:
            sys.modules["quality_max"] = old_qm

    mock_max.assert_called_once()
    call_kwargs = mock_max.call_args.kwargs
    assert "char_lora_strength" in call_kwargs, (
        f"generate_ai_broll_max must be called with char_lora_strength; "
        f"got kwargs: {list(call_kwargs.keys())}"
    )
    assert call_kwargs["char_lora_strength"] == 0.55, (
        f"expected char_lora_strength=0.55, got {call_kwargs['char_lora_strength']!r}"
    )
