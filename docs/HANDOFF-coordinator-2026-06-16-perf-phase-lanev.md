# HANDOFF - coordinator - 2026-06-16 perf-phase Lane V

READ FIRST AS coordinator. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

Timestamp: `2026-06-15T18:03:55Z` (`2026-06-16T03:03:55+0900` Asia/Seoul).

HEAD before writing this handoff:

```text
cfcd755f coord(route): reroute perf phase verification
454385cd coord(verify): request perf phase Lane V
6e8da868 fix(performance): gate capture before budget spend
c027e194 docs(handoff): director2 perf phase route
ee5c7363 fix(handoff): restore operator artifacts
```

Branch relation before this handoff:

```text
main vs origin/main: 11 ahead, 0 behind
```

Coordinator/all-scope mailbox events before this handoff: `150`.

## What Just Landed

Latest durable commits:

- `6e8da868 fix(performance): gate capture before budget spend`
  - Pair-B/director2 implementation for `perf-phase-no-gate`.
  - Adds performance-engine `API_COST_USD` entries, a pre-dispatch
    `would_exceed(engine)` gate in `generate_performance_take`, budget-abort
    handling in `PerformanceCapturePhase`, `PERFORMANCE_HALTED` progress, an
    R-BRIEF, doc/manual updates, and executable selectors.
- `454385cd coord(verify): request perf phase Lane V`
  - Director2 verify request to operator2 for `6e8da868`.
- `cfcd755f coord(route): reroute perf phase verification`
  - Coordinator capacity-max reroute after user request.
  - Operator2 is active owner for formal Lane V; director2 stands by for
    NITS/FAIL; Pair-A director/operator are no-op standby for product-oracle or
    Pair-A work.

No push was performed. Push remains user-gated.

## Coordinator Evidence

Coordinator status:

```text
seat_status.py coordinator --wave 2
HEAD cfcd755f coord(route): reroute perf phase verification
vs origin/main: 11 ahead, 0 behind
ALL-SCOPE EVENTS: 150
Coordinator is UNPINNED (no cursor); no mailbox was consumed.
```

Peer heartbeats in that status:

```text
director   ONLINE @ cfcd755f
director2  ONLINE @ cfcd755f
operator   ONLINE @ cfcd755f
operator2  ONLINE @ cfcd755f
```

Operator2 status:

```text
seat_status.py operator2 --wave 2
UNREAD: 2
  2026-06-15T17-48-46Z-director2-to-operator2-verify-request.md
  2026-06-15T17-52-06Z-coordinator-to-all-coordination.md
```

Locks:

```text
find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

Product-oracle artifact check:

```text
find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

Smoke:

```text
scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known smoke advisories remain:

- `176` `docs/PROGRAM-MANUAL.md` doc-anchor drifts.
- R2 invisible-green warnings in existing pin files.

## Wave 2 Gate

Fresh gate proof:

```text
scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 23
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, and finite lipsync.offset_frames
PYTEST summary: 15 failed, 55 passed
```

Important delta: `perf-phase-no-gate` is no longer a no-selector blocker. It is
still `open` until operator2 sends a formal GO/NITS/FAIL for `6e8da868`.

## Current Routing

- `operator2`: active. Consume the two unread events, verify
  `6e8da868 fix(performance): gate capture before budget spend`, and send one
  formal GO/NITS/FAIL report. Must read landed git diff, not dirty default
  index state.
- `director2`: standby. If operator2 sends NITS/FAIL, fix only the scoped
  `perf-phase-no-gate` issue and request re-verification. Do not start
  `lipsync-veto`, `web_server.py` HTTP batch, or checkpoint rows until this
  Lane V resolves.
- `director`: Pair-A implementation idle. Stand by for product-oracle
  identity/ArcFace review, Tier-A co-signs, or explicit Pair-A work.
- `operator`: Pair-A no-op standby. Do not verify Pair-B diffs.

## Operator2 Watch Items

Coordinator sidecar preflight found two questions operator2 must decide:

1. `cinema_pipeline.py` emits `PERFORMANCE_HALTED` when
   `performance_result.ok` is false, but may still continue into
   `PERFORMANCE_REVIEW` and motion because `pause()` is not cancellation.
2. The new precheck estimates only the resolved performance engine, while
   Mode-B driving synth can log separate Hedra/SadTalker spend. Decide whether
   this is accepted soft-cap behavior or a sibling budget gap.

## Operational Caution

The default git index is stale/noisy after concurrent seat commits and shows
delete/add or `MM` churn for files already landed in HEAD. The coordinator index
only had `coordination/mailbox/seen/operator2.txt` dirty before this handoff.
Use per-seat indexes and explicit pathspecs; do not clean up artifacts owned by
another seat unless the user explicitly authorizes it.

Coordinator did not edit production code, inventory status, locks, or cursors.

## Postscript: Seat Status After This Snapshot

After the coordinator snapshot above, all four seats wrote handoff/status
artifacts acknowledging the reroute:

- `operator2` handoff was committed as
  `5df710d8 docs(handoff): operator2 perf lanev pending`.
- `director`: `2026-06-15T18-04-42Z-director-to-all-status.md` and
  `docs/HANDOFF-director-2026-06-16-paira-idle-after-perf-reroute.md`; Pair-A
  remains implementation-idle and will not take Pair-B rows.
- `operator2`: `2026-06-15T18-05-18Z-operator2-to-all-status.md` and
  `docs/HANDOFF-operator2-2026-06-16-perf-phase-lanev-pending.md`; operator2
  consumed through `2026-06-15T17:52:06Z`, unread is now 0, and formal Lane V
  on `6e8da868` is still pending.
- `director2`: `2026-06-15T18-05-33Z-director2-to-all-status.md` and
  `docs/HANDOFF-director2-2026-06-16-perf-phase-lanev-standby.md`; director2
  remains standby for NITS/FAIL only.
- `operator`: `2026-06-15T18-05-41Z-operator-to-all-status.md` and
  `docs/HANDOFF-operator-2026-06-16-noop-after-perf-reroute.md`; Pair-A
  operator remains no-op standby.

These were status/handoff events only, **not** verification reports. No seat has
GO/NITS/FAILed `6e8da868` yet, so `perf-phase-no-gate` remains open until
operator2 sends the formal verification report.
