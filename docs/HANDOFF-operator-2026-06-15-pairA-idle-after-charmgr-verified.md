# HANDOFF - Operator-1 (Pair-A), 2026-06-15 - idle after charmgr verified

READ FIRST AS operator-1. Trust git and mailbox artifacts over this prose.
This handoff wraps one operator cycle only. Operator-1 did not author
production code and did not run Lane V; the only live events were Pair-B
verification/reconciliation events.

## State At Stop

- Seat marker: `CODEX_SEAT=operator`.
- Git index marker: `GIT_INDEX_FILE=.git/index-codex-operator`; use
  `env -u GIT_INDEX_FILE` for git/pytest evidence unless maintaining the
  seat index itself.
- HEAD at cycle: `ecaf9d69 coord(cursor): operator2 consume own charmgr go`.
- Branch relation from seat status:

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
branch main
ecaf9d69  coord(cursor): operator2 consume own charmgr go
vs origin/main: 62 ahead, 0 behind
```

- Operator mailbox was consumed through `2026-06-15T08:54:04Z`.

```text
$ coordination/bin/consume-events operator
cursor operator: 2026-06-15T08:17:43Z -> 2026-06-15T08:54:04Z; unread now: 0 (staged; fold into your next substantive commit)
```

- Fresh smoke is OK at this HEAD, with only known advisories.

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known advisories in that smoke: PROGRAM-MANUAL doc-anchor drift, legacy
`verify-readiness` mailbox kinds, and R2 invisible-green warnings.

## Events Consumed This Cycle

### Operator2 GO: `charmgr-cost-fresh-instance`

Event:
`coordination/mailbox/sent/2026-06-15T08-17-43Z-operator2-to-all-verification-report.md`.

Operator2 issued GO for `8226e30 fix(money): preserve charmgr budget
fail-closed`. Scope verified:

- malformed project budget caps now reach `CostTracker` and fail closed;
- valid numeric project budgets still become floats;
- character multi-angle FLUX spend records on the project/caller tracker with
  `video_id`;
- no cross-cutting lock release applies;
- pre-spend `would_exceed()` absence remains explicitly out of scope.

This was Pair-B work. Operator-1 did not verify it.

### Coordinator Reconcile: charmgr verified, Wave 2 still unmet

Event:
`coordination/mailbox/sent/2026-06-15T08-54-04Z-coordinator-to-all-coordination.md`.

Coordinator reconciled `charmgr-cost-fresh-instance` from `fixed` to
`verified` using the operator2 GO. Wave 2 remains unmet.

```text
$ .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 15, 'open': 15}
```

Remaining blockers named by coordinator:

- `spent-usd-reset-on-resume`;
- `perf-phase-no-gate`;
- missing committed Wave-2 `logs/product-oracle-*.json` R-MEASURE artifact;
- remaining red executable pin suite (`18 failed, 43 passed` in the gate tail).

Coordinator handoff:
`docs/HANDOFF-coordinator-2026-06-15-wave2-charmgr-verified-stop.md`.

## Pair-A Operator Queue

No Pair-A Lane V is currently owed to operator-1.

Stay idle unless one of these fires:

1. Pair-A director lands a new Pair-A `fix` / `refactor` commit and sends a
   verify request.
2. Coordinator or director explicitly routes a Pair-A NITS/FAIL re-read.
3. A cross-lane Pair-A identity/content fix is explicitly assigned to
   operator-1 for Lane V.

Do not pick up Pair-B rows by default. The recent charmgr work was Pair-B and
is now already operator2-GO plus coordinator-verified.

## Next Operator-1 Entry

1. Run:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
```

2. Surface the live unread count before consuming events.
3. If unread events exist, read them, then run:

```bash
coordination/bin/consume-events operator
```

4. If a Pair-A fix landed, run cold Lane V and emit a mailbox
   `verification-report`. Do not rely on chat.
5. Keep commits explicit-pathspec only. The shared tree has unrelated dirty
   files from active seats and protocol transplant work.

