"""Link-integrity invariants for quality_max._prune_unavailable.

Regression for the max-tier Lane V (2026-06-01) F1 finding, ported to the
shared 6679ef2 base (this branch's pulid_max.json is the 56-node subset):

  F1 (CRITICAL): the no-character path pops the identity stack
  (700/93/97/99/101/100, rewiring only 100 -> base UNet 112) without
  rewiring FaceDetailer(600).clip off the popped LoraLoader 700 ([700, 1])
  or ReActor(610).source_image off the popped face LoadImage 93 ([93, 0]).
  Both links are reachable from SaveImage -> ComfyUI /prompt validation
  reject -> queue_prompt raises -> caught at phase_c_assembly -> silent
  fallback to PRODUCTION tier for landscape/establishing max shots. (Not
  exercised by the live runs, which used has_character=True.)

  F1b (CRITICAL, this version only): the no-INIT path prunes the Redux
  conditioning chain (800/801/803/804/810) and rewires the main guider
  (22.conditioning -> base FluxGuidance [60, 0]) but NOT the sibling
  FaceDetailer(600), which reads the same pruned [804, 0] for both its
  positive and negative conditioning. A character text-to-image shot
  (has_character, no init) therefore leaves 600.positive/negative -> [804, 0]
  dangling -> the same /prompt-reject -> silent production-tier fallback. Does
  NOT exist on the max-tier 60-node version; a divergence this ported test
  surfaced. Fix mirrors the 22 -> [60, 0] rewire for 600 (Rule #13 symmetric
  completion).

What is DIFFERENT from the max-tier (60-node) version:
  - NO FLUX-incompat bridging loop here -> no 22.model / 600.model -> [100]
    dangling (the no-char branch's 100 -> 112 rewire already handles every
    [100, slot] reference), so that half of the max-tier fix is N/A.
  - NO SUPIR_conditioner(504) / CheckpointLoaderSimple(505) on the 56-node
    json -> F2 (504/505 prune-gap) is N/A; no orphan test here.

The invariant: after the graph-surgery steps, no node reachable from the
SaveImage output references a node that was pruned away (orphans excluded,
matching ComfyUI validate_prompt's reachability semantics).
"""
from __future__ import annotations

import pytest

from quality_max import (
    _inject_conditioning,
    _inject_identity,
    _inject_latent_source,
    _inject_post_passes,
    _inject_sampling,
    _load_max_workflow,
    _prune_unavailable,
)


def _all_class_types(workflow: dict) -> set:
    return {
        node["class_type"]
        for node in workflow.values()
        if isinstance(node, dict) and "class_type" in node
    }


def _output_node_id(workflow: dict):
    for nid, node in workflow.items():
        if isinstance(node, dict) and node.get("class_type") == "SaveImage":
            return nid
    return None


def _reachable_dangling(workflow: dict, original_ids: set) -> list:
    """Links from a SaveImage-reachable node to a now-missing original node.

    Walks input links backward from SaveImage. A ComfyUI link is
    [source_node_id, output_slot]. A dangling-reachable link is one whose
    source was a real node pre-prune but is gone post-prune -- exactly what
    ComfyUI's reachability-based validate_prompt rejects. Orphaned nodes
    (unreachable from SaveImage) are intentionally NOT flagged.
    """
    out = _output_node_id(workflow)
    if out is None:
        return [("<no SaveImage node>", "", None)]
    seen = {out}
    stack = [out]
    dangling = []
    while stack:
        cur = stack.pop()
        node = workflow.get(cur)
        if not isinstance(node, dict):
            continue
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, list) and len(val) == 2 and isinstance(val[1], int):
                ref = str(val[0])
                if ref in workflow:
                    if ref not in seen:
                        seen.add(ref)
                        stack.append(ref)
                elif ref in original_ids:
                    dangling.append((cur, key, val))
    return dangling


@pytest.mark.parametrize(
    "has_character,has_init",
    [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ],
)
def test_prune_unavailable_leaves_no_reachable_dangling_links(has_character, has_init):
    """F1: _prune_unavailable must never leave a SaveImage-reachable dangling link,
    for any (has_character, has_init) on a full pod (nothing pruned by availability)."""
    workflow = _load_max_workflow()
    original_ids = set(workflow.keys())
    available = _all_class_types(workflow)

    _prune_unavailable(workflow, available, has_character=has_character, has_init=has_init)

    dangling = _reachable_dangling(workflow, original_ids)
    assert not dangling, (
        f"has_character={has_character} has_init={has_init}: "
        f"{len(dangling)} reachable dangling link(s): {dangling}"
    )


# ---------------------------------------------------------------------------
# LoRA-less identity path (_inject_identity with no char_lora)
# ---------------------------------------------------------------------------

_PLACEHOLDER_LORA = "PLACEHOLDER_char.safetensors"


def test_inject_identity_loraless_prunes_700_no_placeholder():
    """No trained per-char LoRA -> LoraLoader(700) must be pruned (not left with
    the PLACEHOLDER_char filename, which fails ComfyUI validation). PuLID(100) +
    CLIP consumers rewire to the base loaders (112/11); no reachable dangling.

    A character max shot without a LoRA is the common first-run case (PuLID
    carries identity); today it hard-fails on PLACEHOLDER_char.safetensors."""
    workflow = _load_max_workflow()
    original_ids = set(workflow.keys())
    available = _all_class_types(workflow)

    _prune_unavailable(workflow, available, has_character=True, has_init=True)
    _inject_identity(workflow, char_lora=None, face_anchor_remote=None,
                     params={}, has_character=True)

    assert "700" not in workflow, "LoraLoader(700) must be pruned when no char_lora"
    for node in workflow.values():
        if isinstance(node, dict):
            assert node.get("inputs", {}).get("lora_name") != _PLACEHOLDER_LORA, (
                "PLACEHOLDER_char.safetensors must not survive into the queued graph"
            )
    assert workflow["100"]["inputs"]["model"] == ["112", 0], "PuLID.model -> base UNet"
    assert workflow["122"]["inputs"]["clip"] == ["11", 0], "CLIPTextEncode.clip -> base CLIP"
    if "600" in workflow:
        assert workflow["600"]["inputs"]["clip"] == ["11", 0], "FaceDetailer.clip -> base CLIP"
    assert not _reachable_dangling(workflow, original_ids)


def test_inject_identity_with_lora_keeps_700():
    """A real per-char LoRA keeps LoraLoader(700) wired with the LoRA name; the
    identity stack stays intact and there are no reachable dangling links."""
    workflow = _load_max_workflow()
    original_ids = set(workflow.keys())
    available = _all_class_types(workflow)

    _prune_unavailable(workflow, available, has_character=True, has_init=True)
    _inject_identity(workflow, char_lora="mara_v1.safetensors", face_anchor_remote=None,
                     params={}, has_character=True)

    assert workflow["700"]["inputs"]["lora_name"] == "mara_v1.safetensors"
    assert workflow["100"]["inputs"]["model"] == ["700", 0], "PuLID.model stays on the LoRA"
    assert not _reachable_dangling(workflow, original_ids)


# ---------------------------------------------------------------------------
# Availability-pruning reachability (production-pod runs max: SUPIR/FaceDetailer/
# Redux/DetailDaemon classes absent). Coverage for the path the full-pod tests
# above don't exercise.
# ---------------------------------------------------------------------------

_MAX_EXTRA_CLASSES = {
    "SUPIR_model_loader_v2", "SUPIR_first_stage", "SUPIR_sample", "SUPIR_decode",
    "SUPIR_conditioner", "FaceDetailer", "UltralyticsDetectorProvider",
    "StyleModelApplyAdvanced", "DetailDaemonSamplerNode",
}


@pytest.mark.parametrize(
    "has_character,has_init",
    [(True, True), (True, False), (False, True), (False, False)],
)
def test_max_extras_absent_full_sequence_no_dangling(has_character, has_init):
    """Production-pod-runs-max: the heavy max classes (SUPIR/FaceDetailer/Redux/
    DetailDaemon) are absent. After the FULL production graph-surgery sequence
    (prune + the inject_* steps, as generate_ai_broll_max runs them), the queued
    graph must leave no SaveImage-reachable dangling link, for any shot type.

    The SUPIR feed-rewire (950.image) lives in _inject_post_passes, so the
    invariant only holds across the whole sequence -- mirroring the director's F2
    test, which called _prune_unavailable + _inject_post_passes together."""
    workflow = _load_max_workflow()
    original_ids = set(workflow.keys())
    available = _all_class_types(workflow) - _MAX_EXTRA_CLASSES
    params: dict = {}

    _prune_unavailable(workflow, available, has_character=has_character, has_init=has_init)
    _inject_identity(workflow, None, None, params, has_character)
    _inject_conditioning(workflow, "a prompt", None, None, params, has_character)
    _inject_sampling(workflow, params)
    _inject_latent_source(workflow, None, params)
    _inject_post_passes(workflow, params, available)

    dangling = _reachable_dangling(workflow, original_ids)
    assert not dangling, (
        f"has_character={has_character} has_init={has_init}: "
        f"{len(dangling)} reachable dangling link(s): {dangling}"
    )
