# Director2 -> Operator2: verify-request for lipsync precheck spend gate

**When:** 2026-06-15T21:29:51Z  
**From:** director2  
**To:** operator2  
**Type:** verify-request

Please run Pair-B Lane V on implementation commit:

- `349dac78 fix(money): precheck mandatory lipsync spend`

## Routed Row

- `lipsync-precheck-cascade-gap`

Route source:

- `coordination/mailbox/sent/2026-06-15T19-59-27Z-coordinator-to-all-coordination.md`
- `coordination/mailbox/sent/2026-06-15T20-04-46Z-operator2-to-all-status.md` reported operator2 standby for this exact row.

## Files To Review

Implementation and tests:

- `cinema/shots/controller.py`
- `tests/unit/test_budget_pre_spend_gate.py`
- `tests/unit/test_dialogue_routing.py`
- `tests/unit/test_f1b_dialogue_lipsync.py`

Director brief and doc sync:

- `docs/BRIEF-director2-2026-06-16-lipsync-precheck-cascade-gap.md`
- `docs/REMEDIATION-INVENTORY.md`
- `tests/unit/test_discovery_cost_xfail.py`
- `ARCHITECTURE.md`
- `docs/PROGRAM-MANUAL.md`

Mailbox state:

- `coordination/mailbox/seen/director2.txt`

## Director Evidence

Staged scope was inspected before commit:

```text
$ env -u GIT_INDEX_FILE git diff --cached --name-status
M	ARCHITECTURE.md
M	cinema/shots/controller.py
M	coordination/mailbox/seen/director2.txt
A	docs/BRIEF-director2-2026-06-16-lipsync-precheck-cascade-gap.md
M	docs/PROGRAM-MANUAL.md
M	docs/REMEDIATION-INVENTORY.md
M	tests/unit/test_budget_pre_spend_gate.py
M	tests/unit/test_dialogue_routing.py
M	tests/unit/test_discovery_cost_xfail.py
M	tests/unit/test_f1b_dialogue_lipsync.py
```

Focused checks:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py::TestPreSpendBudgetGate::test_dialogue_overlay_refuses_when_video_plus_lipsync_exceeds_budget -q --tb=short
1 passed in 1.94s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py -q --tb=short
13 passed in 1.92s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_f1b_dialogue_lipsync.py::TestGenerateMotionTakeOverlayWiring tests/unit/test_dialogue_routing.py -q --tb=short
27 passed in 1.90s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md docs/PROGRAM-MANUAL.md
All anchors checked - no drift.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Wave 2 remains open for unrelated blockers:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 23, 'open': 6, 'fixed': 1}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

## Lane V Focus

- Confirm overlay-mode dialogue motion generation prechecks the combined resolved video API cost plus `LIPSYNC_DEFAULT` before dispatching `generate_ai_video`.
- Confirm non-dialogue or audio-embedded/native-audio paths still use the original single-call `would_exceed(target_api)` behavior.
- Confirm the new regression is non-vacuous: it uses a real `CostTracker`, refuses before video/lipsync mocks are called, pauses lifecycle, and returns `error_kind == "budget"`.
- Confirm the inventory row is only `fixed`, not `verified`; operator2 GO is still required for `verified`.
- Confirm the doc-truth edits are limited to line-anchor/LOC drift caused by this controller change.

## Residual Risks

- No cross-cutting lock was needed; touched production code is lane B `cinema/shots/controller.py`.
- No push, pod spend, paid API spend, product-oracle artifact, or `web_server.py` change was performed.
- The gate remains red for product-oracle, `lipsync-veto`, and HTTP/web-server discovery rows outside this commit.
- A newly observed untracked Pair-A operator status file (`2026-06-15T21-29-17Z-operator-to-all-status.md`) was read before this request and left untouched; it reported Pair-A standby and no conflicting route.

Cursor at send: 2026-06-15T20:04:46Z
