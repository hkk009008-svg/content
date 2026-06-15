# HANDOFF - director2 - 2026-06-16 - perf-phase Lane V standby

READ FIRST AS `director2`. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## Current State

Seat: `director2` / Pair-B director.

Current HEAD:

```text
f9616565 docs(handoff): update coordinator perf lanev wrap
5df710d8 docs(handoff): operator2 perf lanev pending
9d7828ca docs(handoff): coordinator perf lanev wrap
cfcd755f coord(route): reroute perf phase verification
454385cd coord(verify): request perf phase Lane V
6e8da868 fix(performance): gate capture before budget spend
c027e194 docs(handoff): director2 perf phase route
ee5c7363 fix(handoff): restore operator artifacts
```

`seat_status.py director2 --wave 2` after consuming the coordinator reroute and
post-reroute status events:

```text
HEAD f9616565 docs(handoff): update coordinator perf lanev wrap
vs origin/main: 14 ahead, 0 behind
director2 unread: 0
cursor: 2026-06-15T18:05:41Z
peers: director/operator/operator2 ONLINE
```

Consumed for this handoff:

- `2026-06-15T17-52-06Z-coordinator-to-all-coordination.md`
- `2026-06-15T18-04-42Z-director-to-all-status.md`
- `2026-06-15T18-05-18Z-operator2-to-all-status.md`
- `2026-06-15T18-05-33Z-director2-to-all-status.md`
- `2026-06-15T18-05-41Z-operator-to-all-status.md`

Cursor advanced:

```text
director2: 2026-06-15T17:29:15Z -> 2026-06-15T17:52:06Z
director2: 2026-06-15T17:52:06Z -> 2026-06-15T18:05:41Z
```

## What Landed

`perf-phase-no-gate` implementation landed:

- Implementation: `6e8da868 fix(performance): gate capture before budget spend`
- Verify request: `454385cd coord(verify): request perf phase Lane V`
- Coordinator reroute: `cfcd755f coord(route): reroute perf phase verification`
- Coordinator handoff: `9d7828ca docs(handoff): coordinator perf lanev wrap`
- Operator2 pending handoff: `5df710d8 docs(handoff): operator2 perf lanev pending`
- Coordinator wrap update: `f9616565 docs(handoff): update coordinator perf lanev wrap`
- R-BRIEF: `docs/BRIEF-director2-2026-06-16-perf-phase-no-gate.md`

Implementation scope:

- `cost_tracker.py`: nonzero `API_COST_USD` entries for `ACT_ONE`,
  `LIVE_PORTRAIT`, and `VIGGLE`.
- `cinema/shots/controller.py`: `generate_performance_take` now calls
  `self.cost_tracker.would_exceed(engine)` after routing/preconditions and
  before Mode-B driving synth or `performance._router.dispatch`.
- `cinema/phases/performance.py`: `error_kind="budget"` stops the performance
  phase loop and does not call `on_failure`.
- `cinema_pipeline.py`: aborted performance phase emits `PERFORMANCE_HALTED`
  instead of `PERFORMANCE_DONE`.
- Tests and docs: executable selectors replaced the stale `test-infeasible`
  inventory row; budget manual stale prose was fixed; `ARCHITECTURE.md`
  `_assemble_final` anchor was synced.

## Current Assignment

The coordinator's latest route is controlling:

- `director2`: **stand by for operator2's formal Lane V result**.
- Do not start `lipsync-veto`, the `web_server.py` HTTP batch, checkpoint rows,
  or product-oracle work from this seat.
- If operator2 sends NITS/FAIL, fix only the scoped `perf-phase-no-gate` issue
  and request re-verification.
- No lock is held or needed for the current row. Lock claiming/push remains
  user-gated.

Operator2 was explicitly assigned to consume
`2026-06-15T17-48-46Z-director2-to-operator2-verify-request.md` and verify
target commit `6e8da868`.

Operator2 must decide two coordinator-called risks:

1. Whether `PERFORMANCE_HALTED` can still allow the pipeline to continue into
   `PERFORMANCE_REVIEW` and motion because `pause()` is not cancellation.
2. Whether the precheck's resolved-engine estimate is accepted soft-cap
   behavior despite possible separate Mode-B Hedra/SadTalker driving-synth
   spend, or is a sibling gap.

Director2 should not pre-answer those as verified; operator2 owns the GO/NITS/FAIL.

## Verification Evidence

Director2 local evidence for `6e8da868`:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate \
  tests/unit/test_budget_pre_spend_gate.py::TestPerformancePhaseBudgetAbort \
  tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness::test_performance_capture_engines_priced_in_api_cost_usd \
  -q
-> 7 passed in 1.59s

env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_budget_pre_spend_gate.py \
  tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness \
  -q
-> 15 passed in 1.51s

env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_costtracker_perf_uncounted_regression.py \
  tests/unit/test_budget_pre_spend_gate.py \
  tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness \
  -q
-> 22 passed in 1.56s

env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_spent_usd_resume.py \
  tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate \
  tests/unit/test_budget_pre_spend_gate.py::TestPerformancePhaseBudgetAbort \
  tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness::test_performance_capture_engines_priced_in_api_cost_usd \
  -q
-> 9 passed in 1.58s
```

Fresh handoff checks:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; existing advisory warnings only:
   176 docs/PROGRAM-MANUAL.md anchors and R2 invisible-green warnings.

env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
-> UNMET counts={'verified': 19, 'open': 11}; executable selectors=23.
   Product-oracle artifact still missing; unrelated open pin clusters still fail.

find coordination/locks -maxdepth 1 -type f -print | sort
-> coordination/locks/.gitkeep

find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
-> no output
```

Important: Wave gate output no longer lists `perf-phase-no-gate` as a
no-selector blocker. That row still remains `open` until operator2's formal GO.

## Dirty Tree / Index Warning

Use the per-seat index and explicit pathspecs.

At handoff time, the `director2` index saw cursor dirt from multiple seats:

```text
 M coordination/mailbox/seen/director.txt
 M coordination/mailbox/seen/director2.txt
 M coordination/mailbox/seen/operator.txt
 M coordination/mailbox/seen/operator2.txt
?? coordination/mailbox/sent/2026-06-15T18-04-42Z-director-to-all-status.md
?? coordination/mailbox/sent/2026-06-15T18-05-18Z-operator2-to-all-status.md
?? coordination/mailbox/sent/2026-06-15T18-05-33Z-director2-to-all-status.md
?? coordination/mailbox/sent/2026-06-15T18-05-41Z-operator-to-all-status.md
?? docs/HANDOFF-director-2026-06-16-paira-idle-after-perf-reroute.md
?? docs/HANDOFF-director2-2026-06-16-perf-phase-lanev-standby.md
?? docs/HANDOFF-operator-2026-06-16-noop-after-perf-reroute.md
?? docs/HANDOFF-operator2-2026-06-16-perf-phase-lanev-pending.md
```

Only `coordination/mailbox/seen/director2.txt`, this handoff, and the matching
director2 status event belong in the director2 handoff commit. The other cursor
changes and default-index staged/deleted/untracked churn are other-seat/default
index artifacts; do not clean them up from director2 unless explicitly routed.

## Next Director2 Action

Wait for operator2's `verification-report` on `6e8da868`.

If GO:

- Leave inventory reconciliation to the coordinator unless explicitly routed.
- Continue to avoid product-oracle paid/pod work without authorization.

If NITS/FAIL:

- Fix only the scoped `perf-phase-no-gate` problem.
- Run focused tests.
- Send a re-verify request to operator2.
