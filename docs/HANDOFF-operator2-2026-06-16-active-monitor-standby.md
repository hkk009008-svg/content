# Operator2 Handoff - active monitor / standby

Seat: `operator2`
Written: 2026-06-16 KST
Latest HEAD observed before writing: `45e53bbc coord(cursor): operator consume monitor updates`

## Current role

Operator2 is active monitor / standby, not currently verifying.

Why:
- Coordinator routed the `perf-phase-no-gate` FAIL repair to `director2`.
- Operator2 owns the next Pair-B verification only after director2 lands the scoped fix and sends a verify-request.
- No operator2 GO/NITS/FAIL should be issued against uncommitted working-tree changes.

## Consumed mailbox

Operator2 consumed unread events through `2026-06-15T18:26:14Z`.

Consumed events:
- `2026-06-15T18-25-34Z-director-to-all-status.md`
- `2026-06-15T18-26-14Z-operator-to-all-status.md`

The consumed events confirm the same capacity board:

| Seat | State | What / how / why |
|---|---|---|
| `director` | Active monitor / support only | Pair-A has no active implementation row, verify request, Tier-A co-sign, or product-oracle artifact. Director is watching for product-oracle identity/ArcFace review, Tier-A co-sign, Pair-A work, or direct user instruction. |
| `director2` | Active repair | Coordinator assigned the `perf-phase-no-gate` repair after operator2 FAIL. Scope is Mode-B driving-synthesis + performance-engine budget envelope, intentional `PERFORMANCE_HALTED` behavior, strict pin conversion, and touched docs only as needed. |
| `operator2` | Standby for re-verification | Operator2 issued the formal FAIL and is reserved for the next committed director2 fix plus verify-request. |
| `operator` | Standby / no-op | Pair-A operator has no Pair-A Lane V, NITS reread, co-sign, or product-oracle request and should not duplicate Pair-B verification. |

## Observed working tree

There is visible in-flight repair work in the shared working tree, apparently for `perf-phase-no-gate`.

Observed scoped changes include:
- `cinema/shots/controller.py`: combined pre-spend check for Mode-B driving synth plus performance engine before either paid call can launch.
- `cost_tracker.py`: new `would_exceed_cost(estimated_cost_usd)` helper and Mode-B driving cost entries.
- `performance/driving_video.py`: `estimate_driving_face_cost(...)` helper used by both estimate and cost logging.
- `tests/unit/test_budget_pre_spend_gate.py`: Mode-B strict xfail appears converted to a live regression.

Operator2 did not verify this work because it is not yet a committed director2 fix with a verify-request. Treat it as in-progress director2 work.

## Evidence

```text
$ env -u GIT_INDEX_FILE git log --oneline -8
45e53bbc coord(cursor): operator consume monitor updates
1a158cec docs(handoff): operator active monitor baseline
14676d2f docs(handoff): operator standby after pairb route
6feb5397 docs(handoff): operator2 standby after perf fail route
84bf0177 coord(route): route perf phase fail repair
1fa92cd0 coord(verify): operator2 fail perf phase gate
7da87435 docs(handoff): operator perf reroute standby
ccb344b5 docs(handoff): director perf reroute standby

$ coordination/bin/consume-events operator2
cursor operator2: 2026-06-15T18:23:03Z -> 2026-06-15T18:26:14Z; unread now: 0

$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 24
PRODUCT ORACLE BLOCKER: missing Wave 2 product-oracle artifact
PYTEST summary: 15 failed, 56 passed
```

## Next operator2 action

Stay standby and monitor.

When director2 lands the scoped repair and sends a verify-request:
1. Read the committed diff with `git show <sha>`.
2. Confirm the diff matches the routed repair scope.
3. Run the focused Mode-B budget selectors plus nearby cost/budget slices.
4. Decide GO/NITS/FAIL via a mailbox `verification-report`.

Do not update `docs/REMEDIATION-INVENTORY.md` directly while coordinator is live unless explicitly routed.
