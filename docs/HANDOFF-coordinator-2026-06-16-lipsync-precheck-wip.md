# HANDOFF - coordinator - 2026-06-16 lipsync precheck WIP

READ FIRST AS coordinator. Trust git, mailbox artifacts, and current source over
this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T20:15:39Z` (`2026-06-16T05:15:39+0900` Asia/Seoul).

Coordinator is unpinned. No coordinator cursor exists and no coordinator cursor
was consumed.

Baseline immediately before this coordinator handoff commit:

```text
1c63cd56 docs(handoff): director reconcile route handoff
c2338cb0 docs(handoff): operator reconcile route standby
130a5e23 docs(handoff): operator2 lipsync standby
a43f6e40 coord(status): director no-op after reconcile route
f3754d7a coord(status): operator2 standby after reconcile route
5a7ef77b coord(cursor): operator consume reconcile no-op status
aa371016 coord(status): operator no-op after reconcile route
940e26d7 coord(cursor): operator2 consume coordinator route
```

Branch relation from final live coordinator status after the coordinator handoff
commit:

```text
main vs origin/main: 20 ahead, 0 behind
```

## Mailbox / Seat State

Fresh coordinator status:

```text
ALL-SCOPE EVENTS: 173
latest visible all-scope events:
- 2026-06-15T19-59-27Z-coordinator-to-all-coordination.md
- 2026-06-15T20-01-25Z-director-to-all-status.md
- 2026-06-15T20-04-00Z-operator-to-all-status.md
- 2026-06-15T20-04-46Z-operator2-to-all-status.md
```

All four peer heartbeats were online during the final live coordinator refresh.
Recent seat handoff commits landed in quick succession: operator2 `130a5e23`,
operator `c2338cb0`, and director `1c63cd56`.

Seat cursors / unread from live status:

```text
director   cursor 2026-06-15T20:04:46Z  unread 0
director2  cursor 2026-06-15T20:04:46Z  unread 0
operator   cursor 2026-06-15T20:04:00Z  unread 1
operator2  cursor 2026-06-15T20:04:46Z  unread 0
```

Unread operator item is status/no-op mail only, not a new verify request:

- operator unread: `2026-06-15T20-04-46Z-operator2-to-all-status.md`.

Latest seat mail interpretation:

- `director`: consumed the coordinator reconcile route, found no Pair-A,
  product-oracle, or Tier-A trigger, and remains active monitor.
- `operator`: consumed the coordinator reconcile route plus director status,
  found no Pair-A Lane V target, committed a standby handoff at `c2338cb0`, and
  remains Pair-A verifier standby.
- `operator2`: consumed the coordinator route, confirmed checkpoint Lane V is
  complete/reconciled, committed a standby handoff at `130a5e23`, and remains
  Pair-B Lane V standby until director2 sends a committed fix and verify-request
  for `lipsync-precheck-cascade-gap`.
- `director2`: has no unread mail and has active staged WIP for
  `lipsync-precheck-cascade-gap`.

## Coordinator Commit Just Completed

Coordinator reconciliation landed at:

```text
7743da64 coord(reconcile): verify checkpoint rows
```

It moved these Wave 2 rows to `verified` in
`docs/REMEDIATION-INVENTORY.md`, citing operator2 GO
`coordination/mailbox/sent/2026-06-15T19-46-45Z-operator2-to-all-verification-report.md`:

- `ckpt-sceneidx-dead`
- `ckpt-shotaudio-loss`
- `ckpt-projectid-nocrosscheck`

The coordinator also sent:

```text
coordination/mailbox/sent/2026-06-15T19-59-27Z-coordinator-to-all-coordination.md
```

That route made `lipsync-precheck-cascade-gap` the next no-lock Pair-B task for
director2 and operator2 Lane V standby.

## Active Non-Coordinator WIP

The shared index has staged director2 WIP. This coordinator handoff does not own
or review it.

```text
$ env -u GIT_INDEX_FILE git diff --cached --stat
 cinema/shots/controller.py                         |  41 ++++-
 coordination/mailbox/seen/director2.txt            |   2 +-
 ...tor2-2026-06-16-lipsync-precheck-cascade-gap.md | 122 +++++++++++++++
 ...FF-director2-2026-06-16-lipsync-precheck-wip.md | 165 +++++++++++++++++++++
 docs/PROGRAM-MANUAL.md                             |   2 +-
 docs/REMEDIATION-INVENTORY.md                      |   2 +-
 tests/unit/test_budget_pre_spend_gate.py           |  54 +++++++
 tests/unit/test_dialogue_routing.py                |   1 +
 tests/unit/test_discovery_cost_xfail.py            |  14 +-
 tests/unit/test_f1b_dialogue_lipsync.py            |   1 +
 10 files changed, 388 insertions(+), 16 deletions(-)
```

Staged inventory currently marks:

```text
lipsync-precheck-cascade-gap ... wave 2 ... fixed ... awaiting operator2 Lane V GO
```

The staged director2 brief is:

```text
docs/BRIEF-director2-2026-06-16-lipsync-precheck-cascade-gap.md
```

It records a no-lock Pair-B repair scoped to `cinema/shots/controller.py` and
focused tests. Let director2 finish/commit this work and send operator2 a
verify-request before any coordinator `verified` transition.

Also present but not coordinator-owned:

```text
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
D  docs/HANDOFF-director-2026-06-16-reconcile-route-active-monitor.md
?? docs/HANDOFF-director-2026-06-16-reconcile-route-active-monitor.md
```

Operator's latest committed status says the checkpoint-context draft is stale
relative to current checkpoint reconciliation; preserve it unless operating as
the operator seat or explicitly asked to clean it. The director active-monitor
handoff shows a stale `D/??` pair from a seat-local/temp-index commit; do not
stage or refresh it from the coordinator seat unless explicitly asked.

## Gate / Smoke / Artifacts

Fresh smoke:

```text
$ .venv/bin/python scripts/ci_smoke.py
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md - kind 'verify-addendum' not in KNOWN_KINDS
R1 xfail-strictness ....... PASS
R2 invisible-green ........ WARN
R3 gate-executes-pins ..... PASS
R4 ci-runs-runxfail ....... PASS
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Fresh Wave 2 gate from the current working tree/index state:

```text
$ .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 23, 'open': 6, 'fixed': 1}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

The fixed row is the staged director2 `lipsync-precheck-cascade-gap` WIP, not an
operator-verified row.

Product-oracle artifact:

```text
$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

Locks:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

No lock is held. Push, lock-claim/push side effects, pod spend, and paid API
spend remain unauthorized.

## Remaining Wave 2 Board

Current working tree inventory reports:

```text
lipsync-veto                 open   lock W2-auto_approve.py.lock
lipsync-precheck-cascade-gap fixed  no lock; awaiting operator2 GO
http-clearperf-silent200     open   lock W2-web_server.py.lock
http-drivingvid-orphan       open   lock W2-web_server.py.lock
http-addchar-float-unguarded open   lock W2-web_server.py.lock
http-null-json-body          open   lock W2-web_server.py.lock
http-styleboard-false201     open   lock W2-web_server.py.lock
```

Wave 2 also still needs a committed `logs/product-oracle-*.json` artifact with
finite ArcFace and lip-sync metrics before close.

## Next Coordinator Moves

1. Refresh live state first:
   `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2`,
   `env -u GIT_INDEX_FILE git log --oneline -8`,
   `.venv/bin/python scripts/wave_gate_check.py 2`, and
   `.venv/bin/python scripts/ci_smoke.py`.
2. Do not touch or commit the staged director2 WIP as coordinator. Wait for
   director2 to commit and send an operator2 verify-request, or for the
   user-principal to redirect ownership.
3. After a real operator2 GO for `lipsync-precheck-cascade-gap`, reconcile that
   row from `fixed` to `verified` if the current evidence still matches.
4. Do not start or route lock-gated `auto_approve.py` / `web_server.py` work
   unless push/lock side effects are explicitly authorized.
5. Do not invent another coordinator mailbox event unless new evidence creates a
   real state transition, routing need, lock correction, wave-boundary action, or
   user-facing escalation.
6. Push only on explicit user authorization.
