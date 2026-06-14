"""R-VERIFY-TIER (B) CI pin for a confirmed-but-unfixed defect.

GAP (the "has_character LoRA-only prune hole"): `generate_ai_broll_max` derives
`has_character = bool(character_image and os.path.exists(character_image))` (quality_max.py:1006)
— keyed off the FACE REFERENCE only. A LoRA-only shot (a character with a trained per-char LoRA
registered in `settings["char_lora_paths"]` but NO `primary_reference` on disk) therefore gets
`has_character=False`, so `_prune_unavailable` drops node 700 (`LoraLoader`) along with the PuLID
stack (:386-388) AND `_inject_identity` early-returns (:504) — the trained LoRA is SILENTLY
DROPPED and the shot renders with zero identity conditioning. The ArcFace gate does not rescue it
(`should_halt`/`needs_regenerate` key off the same `has_character=False`), so a bad frame ships
with no retry signal.

Production-reachable via two paths (Rule #12 grep-the-writes): `scripts/_register_aria_lora.py:35`
writes `char_lora_paths[char_id]` with ZERO reference-image checks; and post-training deletion of
the reference files (`get_reference_image` returns None when no candidate exists on disk,
domain/character_manager.py:506-518). Config-reachable-only under pure web-UI authoring (the
train-lora endpoint couples a LoRA to >=15 uploaded references, web_server.py:762).

Surfaced: operator-1 (125be5e §2). Re-verified high-confidence: operator-1 workflow wf_1e47eeb0-08b
(4 adversarial Sonnet passes — reachability / call-chain / dual-char+landscape safety / fix-shape).
Dispositioned: director-1 PM7 handoff Carry#2 — DESIGN backlog (defer to a focused TDD session).

DUAL-CHAR is SAFE (primary rides primary_reference, secondary rides its own ref+lora independently);
the genuine LANDSCAPE prune (no character in frame) is CORRECT and must NOT be broken by the fix.
The naive fix (`has_character = ... or char_lora_path`) is UNSAFE (crashes `_upload_with_cache(None)`
at :1044 + leaves PuLID nodes with no face anchor). The safe fix DECOUPLES `has_face_ref` (gates the
PuLID/face nodes 93/99/100/101/610 + face upload) from `has_char_lora` (gates node 700 + the
`_inject_identity` LoRA arm, which already supports LoRA-without-face-anchor at :507 vs :538).

The fix is a ~24-site refactor (director-1's design call); the gap is testable NOW. This strict-xfail
makes CI carry the defect (not the next session's agents). When director-1 lands the decouple fix,
`_prune_unavailable`/`_inject_identity` gain a `has_char_lora` param — update the calls below; the
XPASS (or signature TypeError) under strict=True is the signal to revise/delete this file.

See memory: project_secondary_char_needs_lora; realism_production_plus_char_lora (ADR-024/025).
"""
import pytest

import quality_max as qm


def _max_workflow_with_full_availability():
    """Load pulid_max.json and an `available` set covering every class_type, so the ONLY prune
    that can fire is the has_character / has_init logic (not pod-availability)."""
    wf = qm._load_max_workflow()
    wf.pop("_metadata", None)
    available = {n["class_type"] for n in wf.values()
                 if isinstance(n, dict) and "class_type" in n}
    return wf, available


def test_node_700_is_the_per_char_lora_loader():
    """Reference (passes): pin node 700's identity so the xfail below is unambiguous."""
    wf, _ = _max_workflow_with_full_availability()
    assert wf["700"]["class_type"] == "LoraLoader"


def test_landscape_no_lora_correctly_prunes_lora_node():
    """Reference (passes): a genuine no-character shot (no face ref AND no LoRA) SHOULD drop the
    LoRA node — this prune is correct and the fix must preserve it."""
    wf, available = _max_workflow_with_full_availability()
    qm._prune_unavailable(wf, available, has_face_ref=False, has_char_lora=False, has_init=False)
    assert "700" not in wf


def test_full_character_with_face_ref_wires_lora():
    """Reference (passes): with a face reference present (has_face_ref=True) a registered LoRA is
    kept and wired — proving the wiring path itself works; the hole is purely the has_character gate."""
    wf, available = _max_workflow_with_full_availability()
    qm._prune_unavailable(wf, available, has_face_ref=True, has_char_lora=True, has_init=False)
    qm._inject_identity(wf, "aria_v1.safetensors", None, {}, has_face_ref=True)
    assert "700" in wf
    assert wf["700"]["inputs"]["lora_name"] == "aria_v1.safetensors"


def test_lora_only_shot_should_keep_and_wire_trained_lora():
    """A LoRA-only shot (a registered per-char LoRA, but no face reference on disk) SHOULD retain
    and wire its trained LoRA so the character still binds.

    Fixed by decoupling has_face_ref (gates PuLID/face nodes) from has_char_lora (gates LoRA node
    700 + _inject_identity LoRA arm). This was previously an xfail pin tracking the defect.
    """
    char_lora_path = "aria_v1.safetensors"
    # no primary_reference on disk for this character
    wf, available = _max_workflow_with_full_availability()
    qm._prune_unavailable(wf, available, has_face_ref=False, has_char_lora=True, has_init=False)
    qm._inject_identity(wf, char_lora_path, None, {}, has_face_ref=False)

    assert "700" in wf, "LoRA node 700 must be kept for a LoRA-only shot"
    assert wf["700"]["inputs"].get("lora_name") == "aria_v1.safetensors", "trained LoRA must be wired"


def test_lora_only_shot_node_700_reachable_from_guider():
    """Non-vacuity guard (the bypass trap): for a LoRA-only shot, node 700 must be reachable
    from BasicGuider(22) by walking 'model' edges — proving the LoRA is IN the executing
    chain, not orphaned/bypassed to [112,0].

    A passing '"700" in wf' is NOT enough: the FLUX-incompat bridge can rewire
    22.model -> [112,0] even when 700 survives as an orphaned node. This assertion
    walks model edges to prove 700 is in the live chain.
    """
    char_lora_path = "aria_v1.safetensors"
    wf, available = _max_workflow_with_full_availability()
    qm._prune_unavailable(wf, available, has_face_ref=False, has_char_lora=True, has_init=False)
    qm._inject_identity(wf, char_lora_path, None, {}, has_face_ref=False)

    # Walk 'model' edges backward from node 22 (BasicGuider)
    def reachable_via_model(workflow, start_nid):
        """BFS/DFS over 'model' input edges; return all node ids reached."""
        visited = set()
        stack = [start_nid]
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            node = workflow.get(cur)
            if not isinstance(node, dict):
                continue
            model_ref = node.get("inputs", {}).get("model")
            if isinstance(model_ref, list) and len(model_ref) == 2:
                src = str(model_ref[0])
                if src in workflow:
                    stack.append(src)
        return visited

    reachable = reachable_via_model(wf, "22")
    assert "700" in reachable, (
        f"Node 700 (LoraLoader) is NOT reachable from BasicGuider(22) via 'model' edges — "
        f"the LoRA is orphaned/bypassed. Reachable model-chain nodes: {reachable}"
    )
