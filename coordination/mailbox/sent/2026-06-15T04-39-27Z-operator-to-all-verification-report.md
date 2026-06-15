# Operator → All: Lane V FAIL — 23c99e3 has-char/secondary LoRA

**When:** 2026-06-15T04:39:27Z · **From:** operator (online)

VERDICT: FAIL

Scope: Pair-A Lane V for `23c99e3` (`has-char-lora-hole` + `secondary-lora-hole`). No production fixes authored by operator. No cross-cutting lock applies to `quality_max.py`.

## Evidence
$ python .claude/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2 --smoke
→ failed: `zsh:1: command not found: python`.

$ .venv/bin/python .claude/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2 --smoke
→ smoke OK; Wave 2 UNMET; operator inbox was consumed before this report.

$ .venv/bin/python scripts/ci_smoke.py
→ OK; advisory doc-anchor / legacy mailbox-kind warnings only; ceremony check R1 PASS, R2 WARN, R3 PASS, R4 PASS.

$ .venv/bin/python scripts/wave_gate_check.py 2
→ exit 1; Wave 2 UNMET; latest observed counts `{'fixed': 3, 'open': 21, 'verified': 5}`.

$ env -u GIT_INDEX_FILE git show --stat --oneline 23c99e3
→ `23c99e3 fix(identity): decouple has_face_ref from has_char_lora`; 26 files changed, including `quality_max.py`, `tests/unit/test_has_character_lora_only_hole.py`, `tests/unit/test_discovery_identity_xfail.py`, and `tests/unit/test_quality_max_prune.py`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_has_character_lora_only_hole.py tests/unit/test_discovery_identity_xfail.py::test_secondary_lora_injected_when_primary_has_no_face_ref tests/unit/test_discovery_identity_xfail.py::test_secondary_lora_model_output_reaches_guider_when_primary_has_no_face_ref tests/unit/test_quality_max_prune.py::test_prune_unavailable_leaves_no_reachable_dangling_links tests/unit/test_quality_max_prune.py::test_max_extras_absent_full_sequence_no_dangling -q
→ `18 passed, 1 xfailed in 2.48s`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest --runxfail tests/unit/test_discovery_identity_xfail.py::test_secondary_lora_model_output_reaches_guider_when_primary_has_no_face_ref -q
→ FAILED as intended: `secondary LoraLoader(701) is not reachable from BasicGuider(22) via model edges; reachable model-chain nodes: {'22', '700', '112'}`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_secondary_lora_model_output_reaches_guider_when_primary_has_no_face_ref -q
→ `1 xfailed in 2.51s`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_has_character_lora_only_hole.py::test_lora_only_shot_node_700_reachable_from_guider -q
→ after restoring the mutation probe, `1 passed in 1.64s`.

Direct graph probe for no-face-ref primary+secondary LoRA:
→ `22.model ['700', 0]`; `122.clip ['701', 1]`; `701.model ['700', 0]`; `model_chain ['112', '22', '700']`; `700_reachable True`; `701_reachable False`.

Mutation evidence for the primary LoRA path:
→ temporary mutation `_surviving_model_src` priority `('100','112')` made `test_lora_only_shot_node_700_reachable_from_guider` fail with reachable nodes `{'112', '22'}`; restoring `('100','700','112')` made it pass.

Cold Lane V subagents:
→ verifier A: FAIL, same secondary node-701 model-chain bypass.
→ verifier B: NITS, confirmed the secondary test duplicated gate shape and required durable production-path/mutation evidence before GO.

## Findings
1. IMPORTANT — `quality_max.py:657` / `quality_max.py:1149` — `secondary-lora-hole` is not closed. In the no-primary-face-ref topology, `_prune_unavailable` removes PuLID node `100` and face passes, so `_inject_secondary_loras` cannot rely on rewiring `100.model`. It inserts node `701` and rewires `122.clip`, but `22.model` remains on `700`; `701` is not model-chain reachable from BasicGuider. A ComfyUI `LoraLoader` exposes both MODEL and CLIP outputs; bypassing the MODEL output means the secondary LoRA is not actually applied to the executing model chain. — FAIL.
2. INFORMATIONAL — `quality_max.py:396` / `tests/unit/test_has_character_lora_only_hole.py:93` — `has-char-lora-hole` primary node-700 reachability is independently supported: node 700 reaches `22.model`, and the reachability pin goes RED under the reverted bridge mutation and GREEN after restore. — primary row candidate GO, but combined commit remains FAIL because the secondary row is still blocking.
3. INFORMATIONAL — `tests/unit/test_discovery_identity_xfail.py:139` — added strict-xfail pin `test_secondary_lora_model_output_reaches_guider_when_primary_has_no_face_ref`; `--runxfail` fails for the defect and normal mode xfails, so CI now carries the uncovered secondary reachability gap. — pin only, not a production fix.

## Disposition
- `has-char-lora-hole`: primary LoRA-only path appears verified by executed reachability + mutation evidence.
- `secondary-lora-hole`: FAIL. Keep row unverified; director should fix node-701 model-chain reachability for no-primary-face-ref cases, then request a nit/fix re-verification.
- No lock release.

Cursor at send: 2026-06-15T04:35:30Z
