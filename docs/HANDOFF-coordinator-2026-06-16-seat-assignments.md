# HANDOFF - coordinator - 2026-06-16 seat assignments

READ FIRST AS coordinator. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

Timestamp: `2026-06-15T17:26:57Z` (`2026-06-16T02:26:57+0900` Asia/Seoul).

HEAD before writing this handoff:

```text
4fd37fea coord(route): assign next wave2 seats
1c3a454e coord(inventory): verify spent resume row
c6c6350c coord(verify): operator2 GO spent resume
f7b99d9e coord(mailbox): correct download IO reconcile
2c2e1026 coord(verify): request spent resume Lane V
```

Branch relation before writing this handoff:

```text
## main...origin/main [ahead 1]
```

Working tree was otherwise clean.

## What Just Landed

Local commit ready to push:

- `4fd37fea coord(route): assign next wave2 seats`
  - Adds
    `coordination/mailbox/sent/2026-06-15T17-19-41Z-coordinator-to-all-coordination.md`.
  - Assigns `director2` the next no-lock Wave 2 gate blocker:
    `perf-phase-no-gate`.
  - Assigns `operator2` to wait for the `perf-phase-no-gate` verify request.
  - Assigns `director` and `operator` to consume updates and stay idle unless
    product-oracle identity/ArcFace review, Tier-A co-sign, Pair-A verification,
    or new user instruction lands.

No push was performed after this assignment. Push remains user-gated.

## Coordinator Evidence

Coordinator status:

```text
seat_status.py coordinator --wave 2
HEAD 4fd37fea coord(route): assign next wave2 seats
vs origin/main: 1 ahead, 0 behind
ALL-SCOPE EVENTS: 145
Coordinator is UNPINNED (no cursor); no mailbox was consumed.
```

Peer heartbeats in that status:

```text
director   ONLINE at 2026-06-15T17:26:51Z (4fd37fea)
director2  ONLINE at 2026-06-15T17:26:55Z (4fd37fea)
operator   ONLINE at 2026-06-15T17:26:57Z (4fd37fea)
operator2  STALE, last 2026-06-15T15:22:18Z (2c2ddd63)
```

Locks:

```text
find coordination/locks -maxdepth 1 -type f -print
coordination/locks/.gitkeep
```

Product-oracle artifact check:

```text
find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print
# no output
```

Smoke:

```text
scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known smoke advisories remain:

- `177` `docs/PROGRAM-MANUAL.md` doc-anchor drifts.
- R2 invisible-green warnings in existing pin files.

## Wave 2 Gate

Fresh gate proof:

```text
scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 20
BLOCKER [MAJOR/open] perf-phase-no-gate (cinema/shots/controller.py:1076): no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, and finite lipsync.offset_frames
PYTEST summary: 15 failed, 48 passed
```

The failing selector set is the already-known open-row set: postprocess audio
sibling, web-server HTTP cluster, checkpoint cluster, plus the no-selector and
product-oracle blockers above.

## Seat Routing

- `director`: consume unread all-scope updates, then idle for implementation.
  Stay available for product-oracle identity/ArcFace review, Tier-A co-signs, or
  a new Pair-A request. Do not take Pair-B rows.
- `operator`: consume unread all-scope updates, then no-op unless a Pair-A
  verify request or coordinator-routed product-oracle identity review lands.
- `director2`: consume unread updates, then own `perf-phase-no-gate`
  (`cinema/shots/controller.py:1076`). Start with an R-BRIEF that re-checks
  selector feasibility, Rule #12 write evidence for the performance paid-call
  path, and Rule #13 sibling audit against the motion-path pre-spend gate.
  Prefer an executable regression if honest; if still test-infeasible, surface
  the exact reason and user-exemption need.
- `operator2`: consume unread updates, then wait for director2's
  `perf-phase-no-gate` verify request. Verify the actual diff and the
  selector/non-vacuity story; send one GO/NITS/FAIL report.

## Queue After Current Assignment

- Product-oracle artifact remains mandatory for Wave 2 close. Do not spend pod
  or paid API budget for product-oracle generation/measurement without explicit
  user authorization.
- `lipsync-veto` and the `web_server.py` HTTP batch are lock-gated
  (`W2-auto_approve.py.lock`, `W2-web_server.py.lock`). Stop before
  `coordination/bin/claim-lock`; lock claiming/push remains user-gated.
- Non-lock checkpoint rows (`ckpt-sceneidx-dead`, `ckpt-shotaudio-loss`,
  `ckpt-projectid-nocrosscheck`) are available after the gate-blocking
  no-selector row is addressed, unless a newer coordinator route supersedes
  this.
