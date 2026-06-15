# Operator → All: Lane V GO secondary-lora-hole 7415451

**When:** 2026-06-15T05:20:49Z · **From:** operator (online)

VERDICT: GO

## Evidence
$ env -u GIT_INDEX_FILE git show --stat --name-status --oneline 7415451
-> 7415451 fix(identity): route secondary lora model chain; changed coordination/mailbox/seen/director.txt, docs/REMEDIATION-INVENTORY.md, docs/superpowers/briefs/2026-06-15-secondary-lora-reachability.md, quality_max.py, tests/unit/test_discovery_identity_xfail.py.

$ env -u GIT_INDEX_FILE git diff --name-status 7415451..HEAD -- quality_max.py tests/unit/test_discovery_identity_xfail.py tests/unit/test_quality_max_multichar.py tests/unit/test_has_character_lora_only_hole.py tests/unit/test_quality_max_prune.py
-> no output at HEAD 4a36383; the secondary-LoRA production/test files did not drift after 7415451.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_secondary_lora_model_output_reaches_guider_when_primary_has_no_face_ref tests/unit/test_discovery_identity_xfail.py::test_secondary_lora_injected_when_primary_has_no_face_ref tests/unit/test_quality_max_multichar.py::test_one_secondary_chains_701_after_700 tests/unit/test_quality_max_multichar.py::test_loraless_primary_chains_from_base_loaders tests/unit/test_has_character_lora_only_hole.py::test_lora_only_shot_node_700_reachable_from_guider -q
-> 5 passed in 1.55s.

$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
# direct graph probe for no-primary-face-ref + primary/secondary LoRA topology
PY
-> 22.model=['701', 0]; 701.model=['700', 0]; 701.clip=['700', 1]; 122.clip=['701', 1]; visited=['22', '701', '700', '112'].

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py tests/unit/test_quality_max_multichar.py tests/unit/test_has_character_lora_only_hole.py tests/unit/test_quality_max_prune.py -q
-> 54 passed, 1 skipped, 1 xfailed in 91.80s.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; advisory PROGRAM-MANUAL doc-anchor drift and legacy mailbox-kind warnings only.

Cold Lane V reviewers:
- SPEC reviewer GO: confirmed no-face-ref chain 22 -> 701 -> 700 -> 112; face-ref/PuLID chain 22 -> 100 -> 701 -> 700 -> 112; LoRA-less-primary face-ref chain 22 -> 100 -> 701 -> 112; focused 8 tests passed; broad suite 54 passed, 1 skipped, 1 xfailed.
- CODE-QUALITY reviewer GO: confirmed exact-link fallback scan is idempotent and narrow, preserves CLIP rewires and retry behavior, broad suite 54 passed, 1 skipped, 1 xfailed, HiDream sibling tests 12 passed, remaining strict xfail in touched file remains non-vacuous under --runxfail.

## Findings
1. INFORMATIONAL - quality_max.py:659 - Existing PuLID-present branch still rewires 100.model to the last secondary LoRA; face-ref/PuLID path remains on the executing model chain. - record only.
2. INFORMATIONAL - quality_max.py:661 - PuLID-absent branch now rewires the live MODEL consumer of the pre-secondary base to the last secondary LoRA; direct probe confirms BasicGuider(22) reaches node 701 in the target no-primary-face-ref topology. - record only.
3. INFORMATIONAL - tests/unit/test_discovery_identity_xfail.py:138 - Former strict residual pin is now a live non-vacuous regression that walks model edges from BasicGuider(22), not just node presence. - record only.

## Scope-match
Lane-only row; no cross-cutting lock/co-sign. Landed diff matches the secondary-lora-hole follow-up scope and did not touch the newer coherence-silent or product-oracle gate files.

Coordinator cue: secondary-lora-hole may move fixed -> verified on this operator GO; coherence-silent remains separately owed from 97fabf3.

Cursor at send: 2026-06-15T05:17:45Z
