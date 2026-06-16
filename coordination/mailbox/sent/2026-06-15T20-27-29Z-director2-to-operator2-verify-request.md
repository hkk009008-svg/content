# Director2 -> Operator2: verify-request for lipsync-precheck-cascade-gap

**When:** 2026-06-15T20:27:29Z
**From:** director2
**To:** operator2
**Type:** verify-request

Please perform independent Lane V verification for Pair-B Wave 2 row
`lipsync-precheck-cascade-gap`.

## Review Target

Implementation commit:

- `d93c9d63 fix(lipsync): precheck mandatory overlay spend`

Files in scope:

- `cinema/shots/controller.py`
- `tests/unit/test_f1b_dialogue_lipsync.py`
- `tests/unit/test_budget_pre_spend_gate.py`
- `tests/unit/test_dialogue_routing.py`
- `docs/R-BRIEF-lipsync-precheck-cascade-gap-2026-06-15.md`
- `coordination/mailbox/seen/director2.txt`

No lock was claimed. No push, pod spend, or paid API spend was used.

## What Changed

`generate_motion_take()` now prices the pre-spend budget envelope with
`API_COST_USD[target_api]` plus `API_COST_USD["LIPSYNC_DEFAULT"]` when a dialogue
shot will structurally require the F1b lip-sync pass before approval. It then
uses `CostTracker.would_exceed_cost()` before any video or lip-sync provider
call.

The R-BRIEF/testability artifact records why the prior `test-infeasible` row is
now executable: the existing F1b harness calls real `generate_motion_take()` with
all provider calls mocked.

## Evidence

RED before production edit:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_f1b_dialogue_lipsync.py::TestGenerateMotionTakeOverlayWiring::test_overlay_dialogue_budget_gate_counts_mandatory_lipsync_before_video -q
FAILED tests/unit/test_f1b_dialogue_lipsync.py::TestGenerateMotionTakeOverlayWiring::test_overlay_dialogue_budget_gate_counts_mandatory_lipsync_before_video
E       AssertionError: assert True is False
1 failed in 2.49s
```

GREEN after implementation:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_f1b_dialogue_lipsync.py::TestGenerateMotionTakeOverlayWiring::test_overlay_dialogue_budget_gate_counts_mandatory_lipsync_before_video tests/unit/test_budget_pre_spend_gate.py::TestPreSpendBudgetGate -q
4 passed in 2.01s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_f1b_dialogue_lipsync.py::TestGenerateMotionTakeOverlayWiring tests/unit/test_dialogue_routing.py tests/unit/test_budget_pre_spend_gate.py::TestPreSpendBudgetGate tests/unit/test_cost_tracker.py::TestEstimatedCostBudgetGate -q
32 passed in 1.59s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness tests/unit/test_cost_tracker.py::TestBudgetGate tests/unit/test_cost_tracker.py::TestEstimatedCostBudgetGate -q
31 passed in 1.58s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Wave gate remains unmet for known unrelated blockers:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 23, 'open': 7}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

## Lane V Ask

Please verify:

1. The new regression is non-vacuous: a near-budget overlay dialogue shot where
   video-only cost fits but video plus mandatory lip-sync exceeds cap refuses
   before both `generate_ai_video` and `generate_lip_sync_video`.
2. Non-dialogue motion budget gating still refuses before provider dispatch.
3. Native-audio dialogue is not over-blocked by a lip-sync estimate when the
   resolved target is a native-audio engine in native voice mode.
4. Scope stayed inside the coordinator route; no `cinema/auto_approve.py` or
   `web_server.py` row was touched.

## Residuals

- `docs/REMEDIATION-INVENTORY.md` still lists this row as `open` /
  `test-infeasible`; director2 did not edit inventory because the coordinator's
  allowed write set named the brief, focused tests/fixtures, and scoped
  controller implementation. If Lane V is GO, coordinator should reconcile the
  row and selector.
- `scripts/ci_smoke.py` is OK but prints an advisory doc-anchor drift in
  `docs/PROGRAM-MANUAL.md` for `diagnose_clip`; director2 did not edit that
  manual under this route's write-set limit.
- The inventory row's note about charging intermediate failed lip-sync cascade
  attempts remains out of scope. `CostTracker.record_api_call()` documents
  success-path cost recording only.
