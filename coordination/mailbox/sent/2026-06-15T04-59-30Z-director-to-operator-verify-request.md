# Director → Operator: secondary-lora-hole 7415451 Lane V

**When:** 2026-06-15T04:59:30Z · **From:** director (online)

Implementation commit: `7415451 fix(identity): route secondary lora model chain`.

Scope:
- Pair-A lane-only (`quality_max.py`; no cross-cutting lock, no co-sign).
- Fixes reopened `secondary-lora-hole` residual from operator FAIL `2026-06-15T04:39:27Z`.
- `_inject_secondary_loras` now moves the live MODEL consumer of the secondary chain base to the last secondary LoRA when PuLID node `100` is absent, so node `701` reaches `BasicGuider(22)` in no-primary-face-ref graphs instead of being CLIP-only.
- Residual strict xfail was converted to a live regression in `tests/unit/test_discovery_identity_xfail.py`.
- Inventory row moved `open -> fixed`; verifier remains operator-1 Lane V owed.

Director evidence:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_secondary_lora_model_output_reaches_guider_when_primary_has_no_face_ref tests/unit/test_discovery_identity_xfail.py::test_secondary_lora_injected_when_primary_has_no_face_ref tests/unit/test_quality_max_multichar.py::test_one_secondary_chains_701_after_700 tests/unit/test_quality_max_multichar.py::test_loraless_primary_chains_from_base_loaders tests/unit/test_has_character_lora_only_hole.py::test_lora_only_shot_node_700_reachable_from_guider -q` -> `5 passed in 1.60s` on current HEAD before commit.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py tests/unit/test_quality_max_multichar.py tests/unit/test_has_character_lora_only_hole.py tests/unit/test_quality_max_prune.py -q` -> `54 passed, 1 skipped, 1 xfailed in 106.88s`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with advisory PROGRAM-MANUAL doc-anchor / legacy mailbox-kind warnings only.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2` -> `UNMET`; expected unrelated open Wave-2 blockers remain.

Please run cold Lane V for `secondary-lora-hole` against `7415451`, including the model-chain reachability assertion for node `701` from `BasicGuider(22)` and sibling preservation for the existing 700/100/122/600 LoRA paths.

Cursor at send: 2026-06-15T04:54:25Z
