# HANDOFF - director2 - 2026-06-16 - perf-phase route queued

READ FIRST AS `director2`. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Seat: `director2` / Pair-B director.

Current durable HEAD before this handoff commit:

```text
ee5c7363 fix(handoff): restore operator artifacts
6197e897 docs(handoff): finalize director cursor
8392eb29 docs(handoff): operator idle after seat assignments
7999e47d docs(handoff): director idle after seat assignments
44949239 docs(handoff): operator2 perf phase wait
a3131d12 docs(handoff): coordinator seat assignment wrap
4fd37fea coord(route): assign next wave2 seats
1c3a454e coord(inventory): verify spent resume row
c6c6350c coord(verify): operator2 GO spent resume
f7b99d9e coord(mailbox): correct download IO reconcile
2c2e1026 coord(verify): request spent resume Lane V
58063bf7 coord(cursor): consume download IO reconcile
8b100459 fix(checkpoint): rehydrate spend on resume
84242298 coord(verify): operator2 GO download IO
```

`seat_status.py director2 --wave 2` reported before the coordinator handoff
commit landed:

```text
HEAD 4fd37fea coord(route): assign next wave2 seats
vs origin/main: 1 ahead, 0 behind
director2 unread before consume: 3
```

Consumed events:

- `2026-06-15T16-23-33Z-operator2-to-all-verification-report.md`
- `2026-06-15T16-25-06Z-coordinator-to-all-coordination.md`
- `2026-06-15T17-19-41Z-coordinator-to-all-coordination.md`

Cursor advanced for the assignment events:

```text
director2: 2026-06-15T15:25:12Z -> 2026-06-15T17:19:41Z
```

During final pre-commit checks, a Pair-A director no-op handoff arrived:
`2026-06-15T17-29-15Z-director-to-all-status.md`, and a Pair-A operator no-op
handoff was also confirmed:
`2026-06-15T17-28-15Z-operator-to-all-status.md`. They were read, did not
change the `director2` route, and the final `director2` cursor was advanced to:

```text
2026-06-15T17:29:15Z
```

## What Changed Before Handoff

`spent-usd-reset-on-resume` is now verified:

- Implementation: `8b100459 fix(checkpoint): rehydrate spend on resume`
- Operator2 GO: `c6c6350c coord(verify): operator2 GO spent resume`
- Coordinator inventory reconciliation: `1c3a454e coord(inventory): verify spent resume row`

`download-urllib-notimeout` is also verified and reconciled. The latest
coordinator route is `4fd37fea coord(route): assign next wave2 seats`.

## Current Assignment

The coordinator assigned `director2` the next active Pair-B lane task:

```text
perf-phase-no-gate
file: cinema/shots/controller.py:1076
status: Wave 2 open MAJOR, remaining no-selector blocker
```

Required next shape:

- Start with an R-BRIEF.
- Re-check the no-selector / test-feasibility problem.
- Produce Rule #12 write evidence for the performance paid-call path.
- Produce Rule #13 sibling audit against the existing motion-path pre-spend
  gate.
- Prefer an honest executable regression.
- If it truly remains test-infeasible, surface the exact reason and the
  user-exemption need before relying on prose.
- After landing a fix or truthful selector artifact, request operator2 Lane V.

This row is Pair-B lane work unless evidence proves a cross-cutting file is
needed. Do not claim a lock just because the row is important.

## Wave State

Fresh gate:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 20
BLOCKER [MAJOR/open] perf-phase-no-gate (cinema/shots/controller.py:1076): no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: missing committed logs/product-oracle-*.json with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, finite lipsync.offset_frames
PYTEST summary: 15 failed, 48 passed
```

Known remaining unrelated failing pin clusters include `lipsync-veto`, the
`web_server.py` HTTP batch, and the checkpoint cluster.

## Smoke

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Existing advisories remain:

- 177 `docs/PROGRAM-MANUAL.md` doc-anchor drifts.
- R2 invisible-green warnings in existing pin files.

## Locks / Push

No lock is currently active per the coordinator assignment event:

```text
coordination/locks/ -> only .gitkeep
```

Stop before `coordination/bin/claim-lock` for `lipsync-veto` or any
`web_server.py` HTTP batch. Lock claiming and push remain user-gated.

Do not spend pod or paid API budget for the product-oracle artifact without
user authorization.

## Dirty Tree Warning

Before this handoff write, `git status --short` showed other-seat dirt:

```text
 M coordination/mailbox/seen/director.txt
 M coordination/mailbox/seen/operator.txt
 M coordination/mailbox/seen/operator2.txt
?? docs/HANDOFF-coordinator-2026-06-16-seat-assignments.md
```

During the handoff write, peer handoff artifacts also appeared for operator and
operator2. Operator2's handoff was committed as `44949239`; Pair-A handoff
commits then landed as `7999e47d`, `8392eb29`, `6197e897`, and `ee5c7363`. Any
remaining Pair-A index/worktree entries are not director2 work and should remain
outside the director2 commit unless explicitly routed.

This handoff should commit only:

- `docs/HANDOFF-director2-2026-06-16-perf-phase-route.md`
- `coordination/mailbox/seen/director2.txt`
- the matching `director2` status event

Use explicit pathspecs.
