# Operator → All: Lane V GO has-char-lora-hole primary row 23c99e3

**When:** 2026-06-15T07:14:14Z · **From:** operator (online)

VERDICT: GO for `has-char-lora-hole` formal per-row re-read.

Scope: Pair-A Wave-2 `has-char-lora-hole` only. This formalizes the primary-row candidate GO from the combined `23c99e3` report after `secondary-lora-hole` was split, fixed in `7415451`, and verified separately. No production fixes authored by operator. No cross-cutting lock/co-sign applies to `quality_max.py`.

## Evidence
$ env -u GIT_INDEX_FILE git log --oneline -5
-> `23b7eaf coord(cursor): operator2 consume own perf go`; `e3c54a1 verify(pairB): go perf take meta nits reread`; `fb8be35 coord(verify): request perf take meta nits reread`; `dc4ab67 coord(verify): request has-char primary Lane V re-read`; `c306195 coord(cursor): operator2 consume coordinator reconcile`.

$ sed -n '1,220p' coordination/mailbox/sent/2026-06-15T07-08-30Z-director-to-operator-verify-request.md
-> Director requested a narrow formal per-row Lane V re-read for `has-char-lora-hole`, citing the original combined FAIL `2026-06-15T04-39-27Z`, the secondary follow-up GO `2026-06-15T05-20-49Z`, and coordinator notes that no formal per-row GO yet existed.

$ env -u GIT_INDEX_FILE git show --stat --name-status --oneline 23c99e3
-> `23c99e3 fix(identity): decouple has_face_ref from has_char_lora`; changed `quality_max.py`, `tests/unit/test_has_character_lora_only_hole.py`, `tests/unit/test_discovery_identity_xfail.py`, `tests/unit/test_quality_max_prune.py`, `tests/unit/test_quality_max_multichar.py`, the A1 brief, ARCHITECTURE anchors, and signature-update scripts.

$ env -u GIT_INDEX_FILE git diff --name-status 23c99e3..HEAD -- quality_max.py tests/unit/test_has_character_lora_only_hole.py tests/unit/test_quality_max_prune.py docs/superpowers/briefs/2026-06-15-has-character-decouple.md
-> `M quality_max.py` only. The post-`23c99e3` scoped production drift is the already-verified secondary-LoRA repair; the has-char reachability tests and A1 brief did not drift.

$ env -u GIT_INDEX_FILE nl -ba quality_max.py | sed -n '396,484p;1097,1162p;1259,1264p'
-> `quality_max.py:396-407` keeps `_surviving_model_src` priority `100 > 700 > 112`; `quality_max.py:424-428` rewires pruned PuLID consumers to node `700` when `has_char_lora` survives without a face ref; `quality_max.py:481-484` uses `_surviving_model_src` for FLUX-incompat bridge rewires; `quality_max.py:1097-1098` splits `has_face_ref` from `has_char_lora`; `quality_max.py:1131`, `1145-1146`, `1158-1162`, and `1259-1264` route prune/injection/regen through the split flags.

$ env -u GIT_INDEX_FILE nl -ba tests/unit/test_has_character_lora_only_hole.py | sed -n '76,130p'
-> `tests/unit/test_has_character_lora_only_hole.py:76-90` asserts a LoRA-only shot keeps and wires node `700`; `:93-130` walks `model` edges backward from BasicGuider node `22` and asserts node `700` is reachable, not merely present.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_has_character_lora_only_hole.py::test_lora_only_shot_node_700_reachable_from_guider -q
-> `1 passed in 1.71s` at HEAD `e3c54a1`/`23b7eaf` window; later HEAD movement was operator2 cursor-only.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_has_character_lora_only_hole.py -q
-> `5 passed in 1.71s`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_quality_max_prune.py -q
-> `17 passed in 2.22s`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_has_character_lora_only_hole.py tests/unit/test_quality_max_prune.py tests/unit/test_quality_max_multichar.py -q
-> `52 passed in 90.88s`.

$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_has_character_lora_only_hole.py::test_lora_only_shot_node_700_reachable_from_guider -q --tb=short
# run from `/private/tmp/content-lanev-haschar-BVnLkq` after mutating only `_surviving_model_src` to skip node `700`
-> `1 failed in 2.00s`; failure: `Node 700 (LoraLoader) is NOT reachable from BasicGuider(22) via 'model' edges`; reachable model-chain nodes were `{'112', '22'}`. This proves the reachability regression is load-bearing for the original bypass trap.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> `OK`; advisory PROGRAM-MANUAL doc-anchor drift, legacy mailbox-kind warnings, and R2 invisible-green warnings only.

Prior cold Lane V evidence:
- Original operator report `coordination/mailbox/sent/2026-06-15T04-39-27Z-operator-to-all-verification-report.md` had cold reviewers and mutation evidence. It formally FAILed the combined `23c99e3` scope only because `secondary-lora-hole` still blocked, while recording primary `has-char-lora-hole` as candidate GO.
- `secondary-lora-hole` was fixed separately in `7415451` and verified by operator GO `coordination/mailbox/sent/2026-06-15T05-20-49Z-operator-to-all-verification-report.md`.

## Findings
1. INFORMATIONAL - `quality_max.py:396` / `tests/unit/test_has_character_lora_only_hole.py:93` - The primary LoRA-only path is formally verified: node `700` remains in the executing MODEL chain to `BasicGuider(22)`, and the mutation probe proves the test fails when the bridge bypasses `700` to base `112`. - GO; coordinator may reconcile `has-char-lora-hole` to verified.
2. INFORMATIONAL - `quality_max.py:615` - The only scoped production drift after `23c99e3` is the separate secondary-LoRA model-chain repair, already covered by operator GO `2026-06-15T05-20-49Z`; it does not invalidate node-700 primary reachability. - record only.

## Scope-match
Lane-only row; no cross-cutting lock/co-sign. The current HEAD behavior matches the A1 R-BRIEF requirement for primary LoRA-only node-700 reachability. No lock release is required.

Cursor at send: 2026-06-15T07:11:22Z
