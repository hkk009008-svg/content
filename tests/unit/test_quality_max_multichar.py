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
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import helpers under test
# ---------------------------------------------------------------------------

from quality_max import (
    _assemble_max_prompt,
    _inject_conditioning,
    _inject_identity,
    _inject_post_passes,
    _inject_secondary_faceswap,
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


def test_three_lora_secondaries_truncate_at_two():
    # Defense-in-depth pin (Task-5 review fold): the router already caps at 2,
    # but the injector's own [:2] must hold if a future caller bypasses it.
    wf = _load_max_workflow()
    _inject_identity(wf, "/l/a.safetensors", None, _params(), True)
    _inject_secondary_loras(
        wf, [_sec(), _sec("char_c", "/l/c.safetensors"),
             _sec("char_d", "/l/d.safetensors")])
    assert "701" in wf and "702" in wf
    assert "703" not in wf
    assert wf["100"]["inputs"]["model"] == ["702", 0]   # chain ends at 702


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

    # F3 enrichment: lora_path + trigger fields must ride through identically
    # (minimal dict previously had no teeth for those keys).
    secondary = [{"char_id": "char_b", "reference": "/r/b.jpg",
                  "lora_path": "/l/b.safetensors", "trigger": "TOKman",
                  "lora_strength": 0.55, "fidelity": "lora",
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


def test_phase_c_assembly_secondary_chars_dict_values_ride_through():
    """PIN (F3): the forwarded secondary_chars first-dict CONTENT (char_id, lora_path,
    trigger) must equal the caller-supplied values — not just list identity.
    Ensures the dispatch boundary doesn't silently drop or transform fields.
    """
    import phase_c_assembly

    fake_result = MagicMock()
    fake_result.__bool__ = lambda self: True

    mock_max = MagicMock(return_value=fake_result)
    fake_qm = MagicMock()
    fake_qm.generate_ai_broll_max = mock_max

    secondary = [{"char_id": "char_b", "reference": "/r/b.jpg",
                  "lora_path": "/l/b.safetensors", "trigger": "TOKman",
                  "lora_strength": 0.55, "fidelity": "lora",
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

    call_kwargs = mock_max.call_args.kwargs
    forwarded = call_kwargs["secondary_chars"]
    assert len(forwarded) == 1
    fwd = forwarded[0]
    assert fwd["char_id"] == "char_b", f"char_id mismatch: {fwd['char_id']!r}"
    assert fwd["lora_path"] == "/l/b.safetensors", f"lora_path mismatch: {fwd['lora_path']!r}"
    assert fwd["trigger"] == "TOKman", f"trigger mismatch: {fwd['trigger']!r}"


def test_phase_c_assembly_production_tier_does_not_call_max():
    """PIN (F1): quality_tier='production' must NOT route through generate_ai_broll_max
    even when secondary_char_refs and char_lora_trigger are supplied.
    (The 'if quality_tier == "max"' guard means those kwargs are absorbed by
    the production path without ever touching quality_max.)
    """
    import phase_c_assembly

    mock_max = MagicMock()
    fake_qm = MagicMock()
    fake_qm.generate_ai_broll_max = mock_max

    secondary = [{"char_id": "char_b", "reference": "/r/b.jpg",
                  "lora_path": "/l/b.safetensors", "trigger": "TOKman",
                  "lora_strength": 0.55, "fidelity": "lora",
                  "multi_angle_refs": [], "identity_anchor": ""}]

    old_qm = sys.modules.get("quality_max")
    sys.modules["quality_max"] = fake_qm
    try:
        # Production path is network-coupled (pod/FAL/Pollinations); accept any
        # raise/return as long as generate_ai_broll_max is never invoked. Mock the
        # network seams so it stays offline instead of burning ~85s of real
        # connect-timeouts:
        #   - RunPodComfyUI (pod) goes through phase_c_assembly's module-level `requests`
        #   - fal_client is imported inside the function → stub via sys.modules
        #   - the Pollinations last-resort uses urllib.request.urlopen (NOT `requests`)
        with patch.object(phase_c_assembly, "requests", MagicMock()), \
             patch("urllib.request.urlopen", MagicMock()), \
             patch.dict(sys.modules, {"fal_client": MagicMock()}):
            try:
                phase_c_assembly.generate_ai_broll(
                    "test prompt",
                    "/tmp/out.jpg",
                    quality_tier="production",
                    char_lora_trigger="TOKwoman",
                    secondary_char_refs=secondary,
                )
            except Exception:
                pass  # mock-shaped responses, missing config, etc. — all acceptable
    finally:
        if old_qm is None:
            sys.modules.pop("quality_max", None)
        else:
            sys.modules["quality_max"] = old_qm

    assert mock_max.call_count == 0, (
        f"generate_ai_broll_max must NOT be called for quality_tier='production'; "
        f"was called {mock_max.call_count} time(s)"
    )


# ---------------------------------------------------------------------------
# _inject_secondary_faceswap — dual ReActor splice (spec §3c Pass A)
# ---------------------------------------------------------------------------

def test_faceswap_injects_94_and_611_and_rewires_consumers():
    wf = _load_max_workflow()
    _inject_secondary_faceswap(wf, "sec_face_remote.jpg")
    assert wf["94"] == {"inputs": {"image": "sec_face_remote.jpg"},
                        "class_type": "LoadImage"}
    n = wf["611"]
    assert n["class_type"] == "ReActorFaceSwap"
    assert n["inputs"]["input_image"] == ["610", 0]
    assert n["inputs"]["source_image"] == ["94", 0]
    assert n["inputs"]["input_faces_index"] == "1"   # string, like 610's "0"
    assert n["inputs"]["source_faces_index"] == "0"
    # 610's static consumer moves to 611 (501.image in the full graph)
    assert wf["501"]["inputs"]["image"] == ["611", 0]
    # 611 inherits 610's scalar config (swap model, restore model, ordering)
    assert n["inputs"]["swap_model"] == wf["610"]["inputs"]["swap_model"]
    assert n["inputs"]["input_faces_order"] == "left-right"


def test_faceswap_noop_without_remote_or_without_610():
    wf = _load_max_workflow()
    before = copy.deepcopy(wf)
    _inject_secondary_faceswap(wf, None)
    assert wf == before
    _prune_node(wf, "610", rewire_to=("600", 0))
    _inject_secondary_faceswap(wf, "x.jpg")
    assert "611" not in wf and "94" not in wf


def test_faceswap_idempotent_double_call_no_dangling():
    wf = _load_max_workflow()
    original_ids = set(wf)
    _inject_secondary_faceswap(wf, "a.jpg")
    _inject_secondary_faceswap(wf, "b.jpg")
    assert wf["94"]["inputs"]["image"] == "b.jpg"
    assert wf["501"]["inputs"]["image"] == ["611", 0]
    # exactly one 611 in the graph, nothing dangling
    assert _reachable_dangling(wf, original_ids | {"611", "94"}) == []


def test_faceswap_after_full_prune_sequence_when_reactor_pruned():
    """When ReActorFaceSwap is NOT in the pod's available classes,
    _prune_unavailable drops 610 — the injector must no-op, and the graph
    stays clean end-to-end."""
    wf = _load_max_workflow()
    available = set(_AVAILABLE) - {"ReActorFaceSwap"}
    _prune_unavailable(wf, available, has_face_ref=True, has_char_lora=True, has_init=False)
    assert "610" not in wf
    before = copy.deepcopy(wf)
    _inject_secondary_faceswap(wf, "x.jpg")
    assert wf == before


def test_faceswap_after_post_passes_supir_absent_feeds_611():
    """THE ordering pin (adversarial plan-review CRITICAL): when SUPIR is
    absent, _inject_post_passes re-feeds 950 from a 610-priority list that
    does not know 611 (the ("610","600","902","8") feed tuple in
    _inject_post_passes' SUPIR-absent branch). Injecting the faceswap AFTER
    post_passes makes the dynamic consumer-rewire catch that fresh
    950.image<-[610,0] and move it to 611. (Injected BEFORE, 611 would be
    silently bypassed — generated but never consumed.)"""
    wf = _load_max_workflow()
    available = set(_AVAILABLE) - {"SUPIR_model_loader_v2"}
    _prune_unavailable(wf, available, has_face_ref=True, has_char_lora=True, has_init=False)
    _inject_identity(wf, None, None, _params(), True)
    _inject_post_passes(wf, _params(), available)       # re-feeds 950 from 610
    assert wf["950"]["inputs"]["image"] == ["610", 0]
    _inject_secondary_faceswap(wf, "sec.jpg")           # production order: AFTER
    assert wf["950"]["inputs"]["image"] == ["611", 0]
    # Retry leg on the SUPIR-absent graph (Task-7 review fold): the teardown
    # restores 950<-610, the re-rewire must catch it again — the retry never
    # re-runs _inject_post_passes, so this is the full combination.
    _inject_identity(wf, None, None, dict(_params(), pulid_weight=1.0), True)
    _inject_secondary_faceswap(wf, "sec.jpg")
    assert wf["950"]["inputs"]["image"] == ["611", 0]


# ---------------------------------------------------------------------------
# Task 7: Wire-up sequence tests
# ---------------------------------------------------------------------------

def test_full_multichar_sequence_no_dangling_and_retry_safe():
    """Mirror of the production order in generate_ai_broll_max with
    secondaries, including the PuLID-boost retry re-injection. ORDER IS
    LOAD-BEARING: loras after identity; faceswap after post_passes
    (adversarial plan-review CRITICAL — see the 950 re-feed pin)."""
    wf = _load_max_workflow()
    original_ids = set(wf)
    params = _params()
    available = set(_AVAILABLE)
    _prune_unavailable(wf, available, has_face_ref=True, has_char_lora=True, has_init=False)
    _inject_identity(wf, None, None, params, True)          # LoRA-less primary
    _inject_secondary_loras(wf, [_sec()])
    prompt = _assemble_max_prompt("a prompt", None, [_sec()])
    _inject_conditioning(wf, prompt, None, None, params, True)
    _inject_post_passes(wf, params, available)
    _inject_secondary_faceswap(wf, "sec.jpg")               # AFTER post_passes
    # retry leg (defensive re-injection)
    _inject_identity(wf, None, None, dict(params, pulid_weight=1.0), True)
    _inject_secondary_loras(wf, [_sec()])
    _inject_secondary_faceswap(wf, "sec.jpg")
    assert wf["100"]["inputs"]["model"] == ["701", 0]
    assert wf["122"]["inputs"]["clip"] == ["701", 1]
    assert wf["501"]["inputs"]["image"] == ["611", 0]       # 611 consumed
    assert _reachable_dangling(wf, original_ids | {"701", "611", "94"}) == []


# ---------------------------------------------------------------------------
# _resolve_shot_info — partial-hint merge (Pass-A landscape misclassification,
# 2026-06-11: shot_hint={"shot_type": "two_shot"} replaced the inferred
# fallback wholesale → characters_in_frame=[] → landscape params zeroed the
# identity stack and disabled the arc halt-gate)
# ---------------------------------------------------------------------------

def test_resolve_shot_info_partial_hint_keeps_identity_inference():
    from quality_max import _resolve_shot_info
    from workflow_selector import classify_shot_type
    info = _resolve_shot_info(
        prompt="a woman on the left and a man on the right, medium two-shot",
        character_image="/refs/aria.jpg",
        char_lora_path=None,
        secondary_chars=[_sec()],
        shot_hint={"shot_type": "two_shot"},
    )
    assert info["characters_in_frame"]
    assert classify_shot_type(info) == "medium"


def test_resolve_shot_info_no_hint_matches_legacy_inference():
    from quality_max import _resolve_shot_info
    with_char = _resolve_shot_info("p", "/r/a.jpg", None, None, None)
    assert with_char == {"prompt": "p", "characters_in_frame": ["char"]}
    without = _resolve_shot_info("p", None, None, None, None)
    assert without == {"prompt": "p", "characters_in_frame": []}


def test_resolve_shot_info_explicit_empty_chars_honored():
    # The controller's real landscape hint (characters_in_frame=[]) must win
    # over inference — explicit keys beat inferred defaults.
    from quality_max import _resolve_shot_info
    info = _resolve_shot_info(
        "aerial valley scenery", "/r/a.jpg", None, None,
        {"prompt": "aerial valley scenery", "characters_in_frame": [],
         "camera": ""},
    )
    assert info["characters_in_frame"] == []


def test_resolve_shot_info_lora_or_secondaries_count_as_characters():
    from quality_max import _resolve_shot_info
    lora_only = _resolve_shot_info("p", None, "/l/a.safetensors", None, None)
    assert lora_only["characters_in_frame"]
    sec_only = _resolve_shot_info("p", None, None, [_sec()], None)
    assert sec_only["characters_in_frame"]


def test_resolve_shot_info_none_hint_values_do_not_clobber():
    from quality_max import _resolve_shot_info
    info = _resolve_shot_info(
        "real prompt", "/r/a.jpg", None, None,
        {"prompt": None, "image_api": None, "camera": "85mm"},
    )
    assert info["prompt"] == "real prompt"
    assert "image_api" not in info
    assert info["camera"] == "85mm"


def test_resolve_shot_info_wired_into_dispatch_source():
    import inspect
    import quality_max
    src = inspect.getsource(quality_max.generate_ai_broll_max)
    assert "_resolve_shot_info(" in src
    # the all-or-nothing `shot_hint or {...}` replacement must be gone —
    # including the image_api read, which now goes through the resolved dict
    assert "shot_hint or {" not in src


def test_wireup_call_order_in_source():
    import inspect
    import quality_max
    src = inspect.getsource(quality_max.generate_ai_broll_max)
    i_id = src.index("_inject_identity(")
    i_loras = src.index("_inject_secondary_loras(")
    i_cond = src.index("_inject_conditioning(")
    i_post = src.index("_inject_post_passes(")
    i_swap = src.index("_inject_secondary_faceswap(")
    # loras right after identity; faceswap AFTER post_passes (the SUPIR-absent
    # 950 re-feed in _inject_post_passes' SUPIR-absent branch would bypass
    # an earlier 611)
    assert i_id < i_loras < i_cond < i_post < i_swap
    # retry leg re-injects both, after the boosted _inject_identity
    retry = src[src.index("boosted_params"):]
    assert "_inject_secondary_loras(" in retry
    assert "_inject_secondary_faceswap(" in retry
    assert "_assemble_max_prompt(" in src
