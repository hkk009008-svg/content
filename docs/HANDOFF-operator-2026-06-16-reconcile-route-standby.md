# Operator handoff - reconcile route standby

READ FIRST AS `operator`. Trust git and live mailbox state over this prose if
they diverge.

## State At Handoff

Timestamp: `2026-06-15T20:13:46Z` (`2026-06-16T05:13:46+0900`
Asia/Seoul).

Seat: `operator` / Pair-A operator.

Current HEAD at live refresh:

```text
130a5e23 docs(handoff): operator2 lipsync standby
a43f6e40 coord(status): director no-op after reconcile route
f3754d7a coord(status): operator2 standby after reconcile route
5a7ef77b coord(cursor): operator consume reconcile no-op status
aa371016 coord(status): operator no-op after reconcile route
940e26d7 coord(cursor): operator2 consume coordinator route
```

Branch relation from `seat_status.py operator --wave 2`:

```text
main vs origin/main: 17 ahead, 0 behind
```

## Mailbox / Cursor

Fresh operator status:

```text
cursor: 2026-06-15T20:04:00Z
UNREAD: 1
  - 2026-06-15T20-04-46Z-operator2-to-all-status.md
```

I read the unread event. It reports that `operator2` is Pair-B Lane V standby
after checkpoint reconciliation, and that there is no committed director2 fix or
verify-request yet for `lipsync-precheck-cascade-gap`.

I did not consume the operator cursor during this handoff. If the next operator
chooses to advance it after re-reading the event, the target is:

```text
coordination/bin/consume-events operator --to 2026-06-15T20:04:46Z
```

## Current Operator Posture

No Pair-A Lane V target is active.

- Checkpoint repair has operator2 GO and is coordinator-reconciled in
  `7743da64 coord(reconcile): verify checkpoint rows`.
- The latest committed statuses after reconciliation are no-op/standby events,
  not Pair-A shipping `fix` / `feat` / `refactor` diffs.
- The newest committed verify-request remains
  `coordination/mailbox/sent/2026-06-15T19-38-54Z-director2-to-operator2-verify-request.md`
  for the already-GO checkpoint repair; no newer verify-request exists in
  `coordination/mailbox/sent/`.
- `operator2` status says director2's current `lipsync-precheck-cascade-gap`
  work is brief/testability WIP, not a committed fix ready for Lane V.

Operator should stay Pair-A verifier standby for a real Pair-A verify-request,
Tier-A co-sign verification, product-oracle support, or coordinator-routed
Pair-A work.

## Active Other-Seat WIP

The shared index is intentionally dirty with director2-owned Pair-B work. Do not
broad-stage or commit it from the operator seat.

```text
M  cinema/shots/controller.py
M  coordination/mailbox/seen/director2.txt
A  docs/BRIEF-director2-2026-06-16-lipsync-precheck-cascade-gap.md
A  docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
M  docs/PROGRAM-MANUAL.md
M  docs/REMEDIATION-INVENTORY.md
M  tests/unit/test_budget_pre_spend_gate.py
M  tests/unit/test_dialogue_routing.py
M  tests/unit/test_discovery_cost_xfail.py
M  tests/unit/test_f1b_dialogue_lipsync.py
```

There are also untracked handoff drafts:

```text
docs/HANDOFF-coordinator-2026-06-16-lipsync-precheck-wip.md
docs/HANDOFF-director-2026-06-16-reconcile-route-active-monitor.md
docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
```

The old operator draft predates checkpoint reconciliation and should not be
treated as the current operator handoff without refreshing it. The coordinator
and director handoff drafts are not operator-owned.

## Gate / Verification Evidence

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md - kind 'verify-addendum' not in KNOWN_KINDS
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Wave 2 gate:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 23, 'open': 6, 'fixed': 1}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Locks:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

Product-oracle artifact check:

```text
$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

## Next Operator

1. Start with:
   `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2`.
2. Re-read any unread operator/all mail before deciding whether to consume the
   cursor.
3. Do not verify director2's `lipsync-precheck-cascade-gap` WIP unless a
   committed fix and verify-request land for the operator seat or Pair-A scope.
   Current routed verifier for that Pair-B row is `operator2`.
4. Preserve other-seat WIP in the shared index. Use the operator seat index or a
   scoped temporary index for any operator-only handoff/cursor commit.
5. Do not push or claim locks unless the user-principal explicitly authorizes
   push/lock side effects.
