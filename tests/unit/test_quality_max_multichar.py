"""Tests for quality_max multi-character helpers (P1-1 slice 2, Tasks 4-7).

Covers:
  - _assemble_max_prompt: trigger-token prepend logic
  - _inject_identity: lora_name basename normalization
  - _inject_secondary_loras: per-secondary LoraLoader chain (§3b)
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

from quality_max import (
    _assemble_max_prompt,
    _inject_identity,
    _inject_secondary_loras,
    _load_max_workflow,
    _prune_node,
    _prune_unavailable,
)
from tests.unit.test_quality_max_prune import _all_class_types, _reachable_dangling

_AVAILABLE = _all_class_types(_load_max_workflow())   # full pod class set


def _params():
    return {}   # minimal params, matching test_quality_max_prune.py usage


def _sec(char_id="char_b", lora="/l/b.safetensors", strength=0.5):
    return {"char_id": char_id, "reference": f"/r/{char_id}.jpg",
            "lora_path": lora, "lora_strength": strength, "trigger": None,
            "identity_anchor": "", "multi_angle_refs": [], "fidelity": "lora"}


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
# _inject_secondary_loras — per-secondary LoraLoader chain (§3b)
# ---------------------------------------------------------------------------

def test_one_secondary_chains_701_after_700():
    wf = _load_max_workflow()
    _inject_identity(wf, "/l/a.safetensors", None, _params(), True)
    _inject_secondary_loras(wf, [_sec()])
    assert wf["701"]["class_type"] == "LoraLoader"
    assert wf["701"]["inputs"]["model"] == ["700", 0]
    assert wf["701"]["inputs"]["clip"] == ["700", 1]
    assert wf["701"]["inputs"]["lora_name"] == "b.safetensors"
    # consumers moved to the END of the chain
    assert wf["100"]["inputs"]["model"] == ["701", 0]
    assert wf["122"]["inputs"]["clip"] == ["701", 1]
    assert wf["600"]["inputs"]["clip"] == ["701", 1]


def test_two_secondaries_chain_702_after_701_consumers_on_702():
    wf = _load_max_workflow()
    _inject_identity(wf, "/l/a.safetensors", None, _params(), True)
    _inject_secondary_loras(wf, [_sec(), _sec("char_c", "/l/c.safetensors")])
    assert wf["702"]["inputs"]["model"] == ["701", 0]
    assert wf["100"]["inputs"]["model"] == ["702", 0]
    assert wf["122"]["inputs"]["clip"] == ["702", 1]


def test_loraless_primary_chains_from_base_loaders():
    wf = _load_max_workflow()
    _inject_identity(wf, None, None, _params(), True)   # prunes 700
    _inject_secondary_loras(wf, [_sec()])
    assert "700" not in wf
    assert wf["701"]["inputs"]["model"] == ["112", 0]
    assert wf["701"]["inputs"]["clip"] == ["11", 0]
    assert wf["100"]["inputs"]["model"] == ["701", 0]


def test_strength_clamped_at_055_and_below_clamp_passthrough():
    wf = _load_max_workflow()
    _inject_identity(wf, "/l/a.safetensors", None, _params(), True)
    _inject_secondary_loras(wf, [_sec(strength=0.9)])
    assert wf["701"]["inputs"]["strength_model"] == 0.55
    assert wf["701"]["inputs"]["strength_clip"] == 0.55
    # below-clamp values pass through untouched (a future S3 tune that
    # accidentally inverted min() to max() would fail HERE, not silently)
    _inject_secondary_loras(wf, [_sec(strength=0.3)])
    assert wf["701"]["inputs"]["strength_model"] == 0.3


def test_no_lora_secondaries_is_noop():
    wf = _load_max_workflow()
    _inject_identity(wf, "/l/a.safetensors", None, _params(), True)
    before = copy.deepcopy(wf)
    _inject_secondary_loras(wf, [dict(_sec(), lora_path=None)])
    _inject_secondary_loras(wf, None)
    assert wf == before


def test_inject_secondary_loras_idempotent_after_identity_rerun():
    """The PuLID-boost retry re-calls _inject_identity (boosted params).
    Plan-review established the retry CANNOT break the chain today: the
    consumer rewires live only in the LoRA-less else-branch, guarded by
    'if "700" in workflow:' — after the first LoRA-less call pruned 700, the
    retry skips the branch entirely. The defensive re-injection must
    therefore be a clean no-op-equivalent: chain intact, no duplicates."""
    wf = _load_max_workflow()
    _inject_identity(wf, None, None, _params(), True)
    _inject_secondary_loras(wf, [_sec()])
    _inject_identity(wf, None, None, _params(), True)   # retry re-call
    assert wf["100"]["inputs"]["model"] == ["701", 0]   # chain SURVIVES (no reset)
    _inject_secondary_loras(wf, [_sec()])               # defensive re-inject
    assert wf["100"]["inputs"]["model"] == ["701", 0]   # still correct
    assert wf["701"]["inputs"]["model"] == ["112", 0]   # still chained from base
    assert "702" not in wf                              # no duplicate chain


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
