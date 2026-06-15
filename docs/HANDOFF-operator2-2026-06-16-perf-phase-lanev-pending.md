# Handoff - operator2 - 2026-06-16 perf-phase Lane V pending

READ FIRST AS operator2. Trust git and mailbox artifacts over this prose if
they diverge.

## State At Wrap

Timestamp: `2026-06-15T18:04:31Z` (`2026-06-16T03:04:31+0900` Asia/Seoul).

Latest HEAD observed before this handoff:

```text
cfcd755f coord(route): reroute perf phase verification
454385cd coord(verify): request perf phase Lane V
6e8da868 fix(performance): gate capture before budget spend
c027e194 docs(handoff): director2 perf phase route
ee5c7363 fix(handoff): restore operator artifacts
```

Operator2 mailbox was consumed from `2026-06-15T17:29:15Z` through
`2026-06-15T17:52:06Z`; unread is now 0. The consumed events were:

- `2026-06-15T17-48-46Z-director2-to-operator2-verify-request.md`:
  director2 requested Lane V for Pair-B row `perf-phase-no-gate`, target
  commit `6e8da868 fix(performance): gate capture before budget spend`.
- `2026-06-15T17-52-06Z-coordinator-to-all-coordination.md`:
  coordinator confirmed operator2 is active now and must run formal Lane V;
  `perf-phase-no-gate` stays open until an operator2 verification report lands.

This handoff did not verify the target commit. It records the pending assignment
because the user asked for handoff before a full Lane V pass.

## Pending Operator2 Work

Run formal Lane V on:

```text
6e8da868 fix(performance): gate capture before budget spend
```

Required source-of-truth reads:

- `git show 6e8da868`
- `docs/BRIEF-director2-2026-06-16-perf-phase-no-gate.md`
- `coordination/mailbox/sent/2026-06-15T17-48-46Z-director2-to-operator2-verify-request.md`
- `coordination/mailbox/sent/2026-06-15T17-52-06Z-coordinator-to-all-coordination.md`

Verify the requested scope:

- `cost_tracker.py`: `API_COST_USD` prices `ACT_ONE`, `LIVE_PORTRAIT`, and
  `VIGGLE`, so `would_exceed(engine)` is not vacuous.
- `cinema/shots/controller.py`: `generate_performance_take` calls
  `self.cost_tracker.would_exceed(engine)` after routing/preconditions and
  before Mode-B driving synth or `performance._router.dispatch`.
- `cinema/phases/performance.py`: `error_kind="budget"` halts the performance
  phase loop and does not call `on_failure`.
- `cinema_pipeline.py`: aborted performance emits `PERFORMANCE_HALTED`, not
  `PERFORMANCE_DONE`.
- Docs/manual/architecture/inventory: brief evidence, executable selectors,
  budget-governance prose, and `_assemble_final` anchor sync.

Explicit coordinator risk checks:

- Decide whether `PERFORMANCE_HALTED` still continues into
  `PERFORMANCE_REVIEW`/motion because `pause()` is not cancellation.
- Decide whether prechecking only the resolved performance engine is acceptable
  soft-cap behavior when Mode-B driving synth can log separate Hedra/SadTalker
  spend, or whether it is a sibling budget gap.

Send one `verification-report` GO/NITS/FAIL with executed evidence. Do not use
director evidence as the operator verdict.

## Gate And Locks

Latest `seat_status.py operator2 --wave 2` evidence:

```text
HEAD cfcd755f coord(route): reroute perf phase verification
UNREAD: 2 before consume; cursor after consume is 2026-06-15T17:52:06Z
Wave 2 gate: UNMET counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 23
perf-phase-no-gate no-selector blocker is gone
remaining product-oracle blocker: missing committed logs/product-oracle-*.json
pytest summary: 15 failed, 55 passed
```

No lock is held for this row. Do not claim `W2-auto_approve.py.lock` or
`W2-web_server.py.lock`; lock claiming/push remains user-gated.

## Dirty Tree Note

The default git index has other-seat and stale-index churn after concurrent
commits. For this handoff turn, operator2 intentionally touched only:

- `coordination/mailbox/seen/operator2.txt`
- this handoff file
- the outgoing operator2 status mailbox event

Use the per-seat index and explicit pathspecs for any follow-up commit.
