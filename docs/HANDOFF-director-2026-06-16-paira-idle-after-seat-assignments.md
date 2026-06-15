# HANDOFF - Director (Pair-A), 2026-06-16 - idle after seat assignments

READ FIRST AS NEXT PAIR-A DIRECTOR. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

- Seat: `director` / Pair-A image, identity, realism.
- Write timestamp: `2026-06-15T17:29:15Z` (`2026-06-16T02:29:15+0900`
  Asia/Seoul).
- Durable HEAD observed before writing: `a3131d12 docs(handoff): coordinator
  seat assignment wrap`.
- Branch from live seat status: `main`, 2 ahead / 0 behind origin.
- Director mailbox cursor after final self-status consumption:
  `2026-06-15T17:29:15Z`; unread now 0.
- Active locks: `coordination/locks/.gitkeep` only.
- Wave 2 remains `UNMET`: `verified=19`, `open=11`.
- No committed `logs/product-oracle-*.json` artifact exists.
- Smoke returned `OK` with existing advisories only.
- Pair-A has no active Wave 2 implementation row. The only open Pair-A row is
  deferred/test-infeasible: `identity-arcface-embselect`.
- No production code, remediation inventory status, or locks were edited by this
  director handoff.
- Push remains user-gated.

Evidence:

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2
HEAD a3131d12 docs(handoff): coordinator seat assignment wrap
vs origin/main: 2 ahead, 0 behind
mailbox cursor: 2026-06-15T17:19:41Z
UNREAD: 3
Wave 2 gate: UNMET counts={'verified': 19, 'open': 11}

$ export CODEX_SEAT=director
$ export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-codex-$CODEX_SEAT"
$ coordination/bin/consume-events director
cursor director: 2026-06-15T17:19:41Z -> 2026-06-15T17:28:37Z; unread now: 0 (staged; fold into your next substantive commit)

$ coordination/bin/consume-events director
cursor director: 2026-06-15T17:28:37Z -> 2026-06-15T17:29:15Z; unread now: 0 (staged; fold into your next substantive commit)

$ env -u GIT_INDEX_FILE git log --oneline -5
a3131d12 docs(handoff): coordinator seat assignment wrap
4fd37fea coord(route): assign next wave2 seats
1c3a454e coord(inventory): verify spent resume row
c6c6350c coord(verify): operator2 GO spent resume
f7b99d9e coord(mailbox): correct download IO reconcile

$ .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected -- every relied-on green is backed by execution.
OK

$ .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 20
BLOCKER [MAJOR/open] perf-phase-no-gate (cinema/shots/controller.py:1076): no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, and finite lipsync.offset_frames
PYTEST summary: 15 failed, 48 passed

$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output

$ rg -n '^\\| [^|]+ \\| [^|]+ \\| [^|]+ \\| [^|]+ \\| [^|]* \\| [^|]+ \\| [^|]+ \\| [^|]+ \\| A \\| [^|]* \\| (2|defer) \\| open|^\\| [^|]+ \\| [^|]+ \\| [^|]+ \\| [^|]+ \\| [^|]* \\| [^|]+ \\| [^|]+ \\| [^|]+ \\| B \\| [^|]* \\| 2 \\| open' docs/REMEDIATION-INVENTORY.md
43:lipsync-veto ... lane-owner B ... wave 2 ... open
53:lipsync-precheck-cascade-gap ... lane-owner B ... wave 2 ... open
56:http-clearperf-silent200 ... lane-owner B ... wave 2 ... open
57:http-drivingvid-orphan ... lane-owner B ... wave 2 ... open
59:http-addchar-float-unguarded ... lane-owner B ... wave 2 ... open
60:http-null-json-body ... lane-owner B ... wave 2 ... open
61:http-styleboard-false201 ... lane-owner B ... wave 2 ... open
62:ckpt-sceneidx-dead ... lane-owner B ... wave 2 ... open
63:ckpt-shotaudio-loss ... lane-owner B ... wave 2 ... open
64:ckpt-projectid-nocrosscheck ... lane-owner B ... wave 2 ... open
69:identity-arcface-embselect ... lane-owner A ... wave defer ... open
75:perf-phase-no-gate ... lane-owner B ... wave 2 ... open
```

Known smoke advisories remain: `docs/PROGRAM-MANUAL.md` doc-anchor drift and
two R2 invisible-green warnings.

## Mailbox Consumed

Initial unread at resume was 5:

- `2026-06-15T15-20-34Z-operator2-to-all-verification-report.md`
- `2026-06-15T15-25-12Z-coordinator-to-all-coordination.md`
- `2026-06-15T16-23-33Z-operator2-to-all-verification-report.md`
- `2026-06-15T16-25-06Z-coordinator-to-all-coordination.md`
- `2026-06-15T17-19-41Z-coordinator-to-all-coordination.md`

Those events establish:

- `download-urllib-notimeout` is verified and reconciled.
- `spent-usd-reset-on-resume` is verified and reconciled.
- Coordinator assigned `director2` the next active Pair-B task:
  `perf-phase-no-gate`.
- Coordinator assigned `director` to consume updates and stay idle unless
  product-oracle identity/ArcFace review, Tier-A co-sign, Pair-A verification,
  or a new user instruction lands.

Late unread during handoff was 3:

- `2026-06-15T17-28-15Z-operator-to-all-status.md`
- `2026-06-15T17-28-21Z-operator2-to-all-status.md`
- `2026-06-15T17-28-37Z-director2-to-all-status.md`

Those are no-op/waiting handoffs. They do not change Pair-A routing. Director
cursor was advanced to `2026-06-15T17:28:37Z`.

After writing the `director -> all` status event, director consumed that own
broadcast as well. Final cursor is `2026-06-15T17:29:15Z`, unread 0.

## Current Pair-A Routing

Pair-A director remains idle/readiness-only unless one of these arrives:

- Product-oracle artifact needing identity / GhostFaceNet / ArcFace-result
  review.
- Tier-A co-sign request from Pair-B/director2 or coordinator.
- New or reactivated Pair-A row.
- User-principal direct instruction changing seat ownership.

Do not claim Pair-B implementation work from this seat. `perf-phase-no-gate`
belongs to `director2`; `operator2` is waiting to verify that actual diff and
selector/non-vacuity story.

## Current Wave 2 Blockers

Wave 2 cannot close yet:

- `perf-phase-no-gate` has no executable selector and remains open.
- The committed Wave 2 product-oracle artifact is missing.
- Executable red pins remain in postprocess lipsync sibling coverage,
  web-server HTTP cluster, and checkpoint cluster.

Do not declare the wave green from status-column movement alone.

## Dirty Tree Notes

Other seats wrote cursor/status handoffs while this handoff was being prepared.
Do not revert or normalize them from the Pair-A director seat. This handoff
intentionally adds only:

- `docs/HANDOFF-director-2026-06-16-paira-idle-after-seat-assignments.md`
- `coordination/mailbox/sent/2026-06-15T17-29-15Z-director-to-all-status.md`
- `coordination/mailbox/seen/director.txt`
