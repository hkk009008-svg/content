"""Tests for quality_max multi-character helpers (P1-1 slice 2, Task 4).

Covers:
  - _assemble_max_prompt: trigger-token prepend logic
  - _inject_identity: lora_name basename normalization
  - phase_c_assembly dispatch: char_lora_trigger + secondary_chars forwarded to max
"""
import copy
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Import helpers under test
# ---------------------------------------------------------------------------

from quality_max import _assemble_max_prompt, _inject_identity


# ---------------------------------------------------------------------------
# _inject_identity lora_name basename normalization
# ---------------------------------------------------------------------------

def _minimal_workflow_with_700():
    """Return a minimal workflow dict that includes node 700 (LoraLoader)."""
    return {
        "700": {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": "PLACEHOLDER_char.safetensors",
                "strength_model": 1.0,
                "strength_clip": 1.0,
                "model": ["112", 0],
                "clip": ["11", 0],
            },
        },
        "100": {
            "class_type": "ApplyPulidFlux",
            "inputs": {
                "model": ["700", 0],
            },
        },
    }


def test_inject_identity_lora_name_is_basename_not_abspath():
    """lora_name must be the basename, not the full absolute path.

    pod-side placement of the .safetensors into ComfyUI's loras/ dir under
    this basename is the slice-2 POD-SESSION step (spec §7.2).
    """
    wf = _minimal_workflow_with_700()
    _inject_identity(wf, "/abs/path/char_lora_fal_v2.safetensors", None, {}, True)
    assert wf["700"]["inputs"]["lora_name"] == "char_lora_fal_v2.safetensors"


def test_inject_identity_with_relative_path_lora_basename_unchanged():
    """A relative/basename path is also normalized safely (idempotent for basenames)."""
    wf = _minimal_workflow_with_700()
    _inject_identity(wf, "mara_v1.safetensors", None, {}, True)
    assert wf["700"]["inputs"]["lora_name"] == "mara_v1.safetensors"


# ---------------------------------------------------------------------------
# _assemble_max_prompt
# ---------------------------------------------------------------------------

def test_assemble_max_prompt_no_triggers_is_identity():
    assert _assemble_max_prompt("a prompt", None, None) == "a prompt"
    # secondary trigger WITHOUT lora_path contributes nothing
    assert _assemble_max_prompt("a prompt", None, [{"trigger": "TOKman"}]) == "a prompt"


def test_assemble_max_prompt_prepends_primary_then_lora_secondaries():
    out = _assemble_max_prompt(
        "a prompt", "TOKwoman",
        [{"trigger": "TOKman", "lora_path": "/l/b.safetensors"},
         {"trigger": "TOKthird", "lora_path": None}])
    assert out == "TOKwoman, TOKman, a prompt"


def test_assemble_max_prompt_primary_only_no_secondaries():
    out = _assemble_max_prompt("a prompt", "TOKwoman", [])
    assert out == "TOKwoman, a prompt"


def test_assemble_max_prompt_secondary_only_with_lora():
    out = _assemble_max_prompt("a prompt", None,
                                [{"trigger": "TOKman", "lora_path": "/l/b.safetensors"}])
    assert out == "TOKman, a prompt"


def test_assemble_max_prompt_empty_trigger_string_is_skipped():
    # Empty string is falsy — should not appear in output
    assert _assemble_max_prompt("a prompt", "", None) == "a prompt"


# ---------------------------------------------------------------------------
# phase_c_assembly dispatch: char_lora_trigger + secondary_chars forwarded
# ---------------------------------------------------------------------------

def test_phase_c_assembly_forwards_char_lora_trigger_and_secondary_chars_to_max():
    """In max-tier dispatch, char_lora_trigger + secondary_chars must be forwarded
    to generate_ai_broll_max.

    The import of quality_max is inside the function body (lazy), so we patch it
    via sys.modules before the call to intercept the internal call.
    """
    import phase_c_assembly

    fake_result = MagicMock()
    fake_result.__bool__ = lambda self: True

    mock_max = MagicMock(return_value=fake_result)
    fake_qm = MagicMock()
    fake_qm.generate_ai_broll_max = mock_max

    secondary = [{"char_id": "char_b", "reference": "/r/b.jpg",
                  "multi_angle_refs": ["/r/b1.jpg"], "identity_anchor": "anchor b"}]

    old_qm = sys.modules.get("quality_max")
    sys.modules["quality_max"] = fake_qm
    try:
        phase_c_assembly.generate_ai_broll(
            "test prompt",
            "/tmp/out.jpg",
            quality_tier="max",
            char_lora_path="/fake/mara.safetensors",
            char_lora_trigger="TOKwoman",
            secondary_char_refs=secondary,
        )
    finally:
        if old_qm is None:
            sys.modules.pop("quality_max", None)
        else:
            sys.modules["quality_max"] = old_qm

    mock_max.assert_called_once()
    call_kwargs = mock_max.call_args.kwargs

    assert "char_lora_trigger" in call_kwargs, (
        f"generate_ai_broll_max must be called with char_lora_trigger; "
        f"got kwargs: {list(call_kwargs.keys())}"
    )
    assert call_kwargs["char_lora_trigger"] == "TOKwoman", (
        f"expected char_lora_trigger='TOKwoman', got {call_kwargs['char_lora_trigger']!r}"
    )
    assert "secondary_chars" in call_kwargs, (
        f"generate_ai_broll_max must be called with secondary_chars; "
        f"got kwargs: {list(call_kwargs.keys())}"
    )
    assert call_kwargs["secondary_chars"] == secondary, (
        f"expected secondary_chars={secondary!r}, got {call_kwargs['secondary_chars']!r}"
    )
