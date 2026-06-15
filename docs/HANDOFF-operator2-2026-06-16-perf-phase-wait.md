# Handoff - operator2 - 2026-06-16 perf-phase wait

READ FIRST AS operator2. Trust git and mailbox artifacts over this prose if
they diverge.

## State At Wrap

Timestamp: `2026-06-15T17:27:47Z` (`2026-06-16T02:27:47+0900` Asia/Seoul).

Latest HEAD observed before this handoff commit:

```text
a3131d12 docs(handoff): coordinator seat assignment wrap
4fd37fea coord(route): assign next wave2 seats
1c3a454e coord(inventory): verify spent resume row
c6c6350c coord(verify): operator2 GO spent resume
f7b99d9e coord(mailbox): correct download IO reconcile
```

Operator2 mailbox was consumed from `2026-06-15T15:30:32Z` through
`2026-06-15T17:19:41Z`; unread is now 0. The consumed events were:

- `2026-06-15T16-23-33Z-operator2-to-all-verification-report.md`:
  operator2 GO for `spent-usd-reset-on-resume` on `8b100459`.
- `2026-06-15T16-25-06Z-coordinator-to-all-coordination.md`:
  coordinator reconciled `spent-usd-reset-on-resume` to verified.
- `2026-06-15T17-19-41Z-coordinator-to-all-coordination.md`:
  coordinator assigned next seats after push/alignment.

No production code, inventory row, or lock was edited during this handoff.

## Current Routing

Operator2 is idle until director2 lands or explicitly routes a
`perf-phase-no-gate` verify request.

When that request lands:

- verify the actual diff, not chat prose;
- check the selector/non-vacuity story because this row was previously a
  no-selector blocker;
- send one GO/NITS/FAIL `verification-report` with executed evidence.

Do not verify Pair-A work by default. Do not spend pod or paid API budget for
product-oracle generation/measurement without user authorization.

## Gate And Locks

Latest seat-status evidence:

```text
seat_status.py operator2 --wave 2
HEAD 4fd37fea coord(route): assign next wave2 seats
UNREAD: 3 before consume; cursor after consume is 2026-06-15T17:19:41Z
Wave 2 gate: UNMET counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 20
remaining no-selector blocker: perf-phase-no-gate
product-oracle artifact still missing
pytest summary: 15 failed, 48 passed
```

Lock/product-oracle checks:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

## Dirty Tree Note

Before writing this handoff, the normal working tree was clean. The handoff
turn intentionally stages only:

- `coordination/mailbox/seen/operator2.txt`
- this handoff file
- the outgoing operator2 status mailbox event
