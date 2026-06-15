# R-BRIEF: secondary-lora-hole residual — make secondary LoRA MODEL output reach BasicGuider

PRIORITY: MEDIUM        LANE: A (image/identity)
CROSS-CUTTING: no (`quality_max.py` only; not `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`). LOCK: none. CO-SIGN: N/A.
WAVE: 2. Author: director-1. Verifier: operator-1 (Lane V, impl != verifier).
R-SKILL: `comfyui-mastery` loaded before judging/editing the ComfyUI graph shape.

## The Defect

`23c99e3` fixed the secondary LoRA injection gate, but operator Lane V
`2026-06-15T04-39-27Z` found the residual graph defect: in a no-primary-face-ref
topology, `_prune_unavailable` removes PuLID node `100`, then
`_inject_secondary_loras` creates node `701` and rewires CLIP consumers, but it
only rewires `100.model`. Because `100` is absent, `BasicGuider(22).model`
remains on node `700`, so `701` is not on the executing MODEL chain.

ComfyUI graph rule from `comfyui-mastery`: `LoraLoader` output slot 0 is MODEL
and slot 1 is CLIP. Both links must be carried when the LoRA is intended to
affect rendering; CLIP-only reachability is not enough.

## Rule #12 - Grep-The-Writes

TARGET SYMBOL: secondary LoRA `lora_path` and `_inject_secondary_loras` MODEL/CLIP write path.

`$ rg -n "secondary_chars|secondary_char_refs|lora_path" cinema/shots/controller.py quality_max.py web_server.py domain tests/unit -g '*.py'`

Output proving production population and runtime consumption:

```text
cinema/shots/controller.py:332:    char_lora_paths = settings.get("char_lora_paths", {}) or {}
cinema/shots/controller.py:338:    secondary = cc.get("secondary_chars") or []
cinema/shots/controller.py:366:            sec_lora = char_lora_paths.get(sec_id) or None
cinema/shots/controller.py:372:                lora_path=sec_lora,
quality_max.py:629:    entries = [e for e in (secondary_chars or []) if e.get("lora_path")][:2]
quality_max.py:647:                "lora_name": os.path.basename(entry["lora_path"]),
quality_max.py:658:        workflow["100"]["inputs"]["model"] = [last, 0]
quality_max.py:660:        workflow["122"]["inputs"]["clip"] = [last, 1]
quality_max.py:662:        workflow["600"]["inputs"]["clip"] = [last, 1]
quality_max.py:1150:        _inject_secondary_loras(workflow, secondary_chars)
quality_max.py:1255:            _inject_secondary_loras(workflow, secondary_chars)
```

`$ rg -n "_inject_secondary_loras\\(|workflow\\[\\\"100\\\"\\]\\[\\\"inputs\\\"\\]\\[\\\"model\\\"\\]|\\[last, 0\\]|\\[last, 1\\]" quality_max.py tests/unit/test_discovery_identity_xfail.py tests/unit/test_quality_max_multichar.py tests/unit/test_has_character_lora_only_hole.py`

Output proving the single current MODEL consumer write:

```text
quality_max.py:607:def _inject_secondary_loras(workflow: dict, secondary_chars: Optional[list]):
quality_max.py:658:        workflow["100"]["inputs"]["model"] = [last, 0]
quality_max.py:660:        workflow["122"]["inputs"]["clip"] = [last, 1]
quality_max.py:662:        workflow["600"]["inputs"]["clip"] = [last, 1]
tests/unit/test_discovery_identity_xfail.py:162:    qm._inject_secondary_loras(
```

## Rule #13 - Symmetric / Sibling Audit

SHARED STATE: the secondary LoRA chain base and its downstream MODEL/CLIP consumers.

Audited siblings:

```text
tests/unit/test_quality_max_multichar.py:138:    assert wf["100"]["inputs"]["model"] == ["701", 0]
tests/unit/test_quality_max_multichar.py:139:    assert wf["122"]["inputs"]["clip"] == ["701", 1]
tests/unit/test_quality_max_multichar.py:140:    assert wf["600"]["inputs"]["clip"] == ["701", 1]
tests/unit/test_discovery_identity_xfail.py:183:    assert "701" in visited, (
```

Fold: preserve the existing `100.model`, `122.clip`, and `600.clip` rewires.
Add the missing no-`100` MODEL consumer rewire so direct consumers of the chain
base's MODEL output, such as `22.model -> 700`, move to `[last, 0]`. Do not
rewrite node `701`'s own `model` input, or the chain becomes self-referential.

## Full-Shape Pattern Reference

MIRROR: `quality_max.py:269-276` in `_swap_to_hidream` rewires live consumers
after PuLID node `100` is stripped:

```text
quality_max.py:269:    # Rewire whatever consumed ApplyPulidFlux output (was node 100) back to
quality_max.py:270:    # the LoRA chain (node 700).
quality_max.py:271:    for node in workflow.values():
quality_max.py:274:        for k, v in list(node["inputs"].items()):
quality_max.py:275:            if isinstance(v, list) and len(v) == 2 and str(v[0]) == "100":
quality_max.py:276:                node["inputs"][k] = ["700", 0]
```

Use the same explicit link-rewrite shape, but scoped to MODEL-slot consumers of
the pre-injection chain base and excluding the newly inserted secondary LoRA
nodes from that consumer rewrite.

## The Fix

Bounded code change in `quality_max._inject_secondary_loras`:

- Store the initial `model_src` / `clip_src` chain base before inserting nodes.
- Insert `701` / `702` exactly as today.
- If `100` survives, keep the established `workflow["100"]["inputs"]["model"] = [last, 0]`.
- If `100` is absent, rewrite existing direct MODEL consumers of the initial chain base to `[last, 0]`, excluding nodes `701` and `702`.
- Keep existing CLIP rewires to `122.clip` and `600.clip`.

Bounded tests:

- Remove the strict xfail from
  `tests/unit/test_discovery_identity_xfail.py::test_secondary_lora_model_output_reaches_guider_when_primary_has_no_face_ref`.
- The same test must pass and prove node `701` is reachable from `BasicGuider(22)` by MODEL edges.

## Verification The Operator/CI Will Run

Expected focused command:

```bash
.venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_secondary_lora_model_output_reaches_guider_when_primary_has_no_face_ref tests/unit/test_discovery_identity_xfail.py::test_secondary_lora_injected_when_primary_has_no_face_ref tests/unit/test_quality_max_multichar.py::test_one_secondary_chains_701_after_700 tests/unit/test_quality_max_multichar.py::test_loraless_primary_chains_from_base_loaders tests/unit/test_has_character_lora_only_hole.py::test_lora_only_shot_node_700_reachable_from_guider -q
```

Expected result: all pass. Then run the relevant full identity/multichar slices
and `scripts/ci_smoke.py`; Wave 2 remains red for unrelated open pins.
