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

from quality_max import _load_max_workflow, _prune_unavailable


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
        pytest.param(True, False, marks=pytest.mark.xfail(
            reason="F1b: no-init conditioning dangling (600.positive/negative<-[804,0]); "
                   "separate finding, fixed in the follow-up commit",
            strict=True)),
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
