# Operator Handoff - Mode-B perf fix routed to operator2

Seat: `operator`
Written: 2026-06-16 KST
Latest HEAD observed before writing: `1b3509cf coord(verify): request mode-b budget Lane V`

## Current role

Operator is active monitor / standby. There is no Pair-A Lane V target,
NITS reread, Tier-A co-sign, or product-oracle review request for this seat.

The current live trigger is Pair-B:

- `04cc0c78 fix(performance): gate mode-b driving budget envelope` landed.
- `fb86ef4e docs(perf): sync mode-b budget gate notes` followed with docs/inventory sync.
- Director2 emitted the durable verify-request in
  `coordination/mailbox/sent/2026-06-15T18-34-02Z-director2-to-operator2-verify-request.md`.
- `operator2` is the correct verifier for this Pair-B repair.

Operator must not duplicate Pair-B Lane V by default. The useful action from
this seat is to preserve the route, keep the cursor current, and be ready for a
role-safe trigger.

## Consumed mailbox

Operator consumed unread events through `2026-06-15T18:30:29Z`.

Consumed events:

- `2026-06-15T18-29-08Z-operator2-to-all-status.md`
- `2026-06-15T18-30-29Z-director-to-all-status.md`

Those events confirmed the active-monitor board before the director2 fix landed:
director2 owned the `perf-phase-no-gate` repair, operator2 was standby for the
next committed fix plus verify-request, and Pair-A seats were monitor/support.

## Capacity board

| Seat | State | What / how / why |
|---|---|---|
| `director` | Active monitor / support | Pair-A still has no active implementation row. Director is ready for product-oracle identity/ArcFace review, Tier-A co-sign, or explicit Pair-A work. |
| `director2` | Repair landed | Landed `04cc0c78` for `perf-phase-no-gate`, then `fb86ef4e` docs/inventory sync, and committed the operator2 verify-request in `1b3509cf`. |
| `operator2` | Lane V owed now | Operator2 should consume the durable `2026-06-15T18-34-02Z-director2-to-operator2-verify-request.md` event and verify `04cc0c78` plus `fb86ef4e` against the brief/prior FAIL. |
| `operator` | Standby / no-op | Cursor is current through `18:30:29Z`; no Pair-A verification target exists. Do not duplicate Pair-B Lane V unless coordinator/user explicitly reroutes it. |

## Evidence

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
1b3509cf coord(verify): request mode-b budget Lane V
fb86ef4e docs(perf): sync mode-b budget gate notes
04cc0c78 fix(performance): gate mode-b driving budget envelope
b4c7d02f docs(handoff): director active monitor capacity
797eec50 docs(handoff): operator2 active monitor standby

$ coordination/bin/consume-events operator
cursor operator: 2026-06-15T18:26:14Z -> 2026-06-15T18:30:29Z; unread now: 0

$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2
HEAD fb86ef4e docs(perf): sync mode-b budget gate notes
UNREAD: 3 before `1b3509cf` landed; `1b3509cf` then committed the durable
verify-request at `2026-06-15T18-34-02Z-director2-to-operator2-verify-request.md`.

$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Wave 2 remains UNMET. The latest seat-status recompute reports 19 verified, 11
open, product-oracle artifact still missing, and the open-row selector suite at
15 failed / 57 passed. The prior Mode-B failure has dropped out; remaining
failures are unrelated postprocess, web-server, and checkpoint clusters.

## Next action

Primary next move: `operator2` consumes mail and runs Lane V / NITS reread for
`04cc0c78` plus `fb86ef4e` using the director2 verify-request.

Operator should resume only for:

- Pair-A verify request or NITS reread.
- Coordinator-routed product-oracle identity/ArcFace validation.
- Tier-A co-sign request.
- Explicit reroute of Pair-B verification to operator.
- Direct user instruction.

Subagents should be used when they materially improve coverage or speed, but
not to duplicate operator2's assigned verification or cross role boundaries.
