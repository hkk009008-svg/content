# HANDOFF - director2 - 2026-06-16 lipsync precheck WIP

READ FIRST AS `director2`. Trust git, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T20:10:40Z` (`2026-06-16T05:10:40+0900`
Asia/Seoul).

Current HEAD at final refresh:

```text
a43f6e40 coord(status): director no-op after reconcile route
f3754d7a coord(status): operator2 standby after reconcile route
5a7ef77b coord(cursor): operator consume reconcile no-op status
aa371016 coord(status): operator no-op after reconcile route
940e26d7 coord(cursor): operator2 consume coordinator route
7743da64 coord(reconcile): verify checkpoint rows
f2044ec2 coord(cursor): operator consume self status mail
3e5159a9 coord(status): operator standby after checkpoint mail
```

Branch relation from `seat_status.py director2 --wave 2`:

```text
branch main
a43f6e40 coord(status): director no-op after reconcile route
vs origin/main: 16 ahead, 0 behind
```

Final director2 mailbox state:

```text
cursor: 2026-06-15T20:04:46Z
UNREAD: 0
```

All peers were online at final refresh.

## User Interruption

User said `handoff` while the `lipsync-precheck-cascade-gap` implementation was
staged but not committed. I stopped the implementation flow and did not send an
operator2 verify-request.

## Current Worktree / Index

Implementation work is staged in the shared index, but no commit has been made.
Staged scope:

```text
M  cinema/shots/controller.py
M  coordination/mailbox/seen/director2.txt
A  docs/BRIEF-director2-2026-06-16-lipsync-precheck-cascade-gap.md
M  docs/PROGRAM-MANUAL.md
M  docs/REMEDIATION-INVENTORY.md
M  tests/unit/test_budget_pre_spend_gate.py
M  tests/unit/test_dialogue_routing.py
M  tests/unit/test_discovery_cost_xfail.py
M  tests/unit/test_f1b_dialogue_lipsync.py
```

Unrelated worktree residue preserved and not staged:

```text
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
```

This handoff file itself is newly written after the staged-scope capture.

## What The Staged WIP Does

Route source:

```text
coordination/mailbox/sent/2026-06-15T19-59-27Z-coordinator-to-all-coordination.md
```

Coordinator routed `director2` to the no-lock Pair-B row
`lipsync-precheck-cascade-gap`.

Staged implementation summary:

- Adds R-BRIEF `docs/BRIEF-director2-2026-06-16-lipsync-precheck-cascade-gap.md`.
- Adds executable regression:
  `tests/unit/test_budget_pre_spend_gate.py::TestPreSpendBudgetGate::test_dialogue_overlay_refuses_when_video_plus_lipsync_exceeds_budget`.
- Updates `cinema/shots/controller.py` so overlay-mode dialogue shots precheck
  resolved video API cost plus `LIPSYNC_DEFAULT` before dispatching video.
- Preserves existing single-call `would_exceed(target_api)` behavior when no
  required F1b lip-sync call exists.
- Updates adjacent MagicMock test harnesses to set
  `would_exceed_cost.return_value = False`, matching their intended
  budget-allows baseline.
- Updates `docs/REMEDIATION-INVENTORY.md` from `open/test-infeasible` to
  `fixed` pending operator2 GO.
- Updates stale commentary in `tests/unit/test_discovery_cost_xfail.py`.
- Fixes `docs/PROGRAM-MANUAL.md` anchor drift caused by controller line shifts.

No `auto_approve.py`, `web_server.py`, lock file, product-oracle artifact, pod
spend, paid API spend, or push action was touched.

## Verification Already Run

RED before production edit:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py::TestPreSpendBudgetGate::test_dialogue_overlay_refuses_when_video_plus_lipsync_exceeds_budget -q --tb=short
FAILED ... assert True is False
1 failed in 1.64s
```

GREEN after implementation:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py -q --tb=short
13 passed in 2.34s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_f1b_dialogue_lipsync.py::TestGenerateMotionTakeOverlayWiring tests/unit/test_dialogue_routing.py -q --tb=short
27 passed in 2.32s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py --fix docs/PROGRAM-MANUAL.md
FIXED ... cinema/shots/controller.py:2241 -> cinema/shots/controller.py:2272
Remaining anchors checked - no drift.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known smoke advisories remain:

- unknown mailbox kind `verify-addendum`
- two R2 invisible-green warnings in existing pin files

Wave gate after staged WIP:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 23, 'open': 6, 'fixed': 1}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Remaining failures are unrelated known blockers:

- `lipsync-veto` in `tests/unit/test_postprocess_audio_siblings_xfail.py`
- HTTP/web-server cluster in `tests/unit/test_discovery_web_server_xfail.py`
- missing committed `logs/product-oracle-*.json`

## Next Steps

1. Refresh live state again before acting:
   `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 2`
   and `env -u GIT_INDEX_FILE git log --oneline -5`.
2. Inspect staged diff, especially `cinema/shots/controller.py` and
   `tests/unit/test_budget_pre_spend_gate.py`.
3. If acceptable, commit the staged implementation with an explicit pathspec.
   Keep `docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md` out.
4. After the implementation commit exists, send operator2 a verify-request
   naming the exact commit, changed files, tests above, and residual risks.
5. Operator2 is already on standby for this exact row per
   `coordination/mailbox/sent/2026-06-15T20-04-46Z-operator2-to-all-status.md`.

Do not mark this row `verified`; it is only `fixed` until operator2 GO lands.
