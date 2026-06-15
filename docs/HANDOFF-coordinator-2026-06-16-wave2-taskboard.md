# HANDOFF - coordinator - 2026-06-16 Wave 2 task board

READ FIRST AS coordinator. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

Timestamp: `2026-06-15T19:04:22Z`
(`2026-06-16T04:04:22+0900` Asia/Seoul).

HEAD before writing this handoff:

```text
e6205050 coord(route): notify wave2 seat tasks
8da10dc2 coord(handoff): verify mode-b budget gate
38e892e3 coord(verify): operator2 go mode-b budget gate
9128d90d docs(handoff): operator route mode-b lanev
1b3509cf coord(verify): request mode-b budget Lane V
```

Branch state from coordinator status:

```text
main vs origin/main: 32 ahead, 0 behind
```

Coordinator/all-scope mailbox count:

```text
seat_status.py coordinator --wave 2
ALL-SCOPE EVENTS: 164
latest event: 2026-06-15T18-58-49Z-coordinator-to-all-coordination.md
```

Coordinator is unpinned. No coordinator cursor exists and no cursor was
consumed.

## What Just Landed

Latest durable commit:

- `e6205050 coord(route): notify wave2 seat tasks`
  - Adds
    `coordination/mailbox/sent/2026-06-15T18-58-49Z-coordinator-to-all-coordination.md`.
  - Tells every seat its current task from live mailbox, lock, and Wave 2 gate
    state.
  - Routes director2 to the no-lock Pair-B checkpoint cluster:
    `ckpt-sceneidx-dead`, `ckpt-shotaudio-loss`,
    `ckpt-projectid-nocrosscheck`.
  - Routes operator2 to stand by for Lane V after director2 lands the checkpoint
    repair and sends a verify request.
  - Routes director to active monitor for product-oracle identity/ArcFace review,
    Tier-A co-signs, or Pair-A work.
  - Routes operator to consume stale unread mail and remain Pair-A verifier
    standby.

No push was performed. Push remains user-gated.

## Live Seat Mail State

Fresh per-seat status after the task-board commit:

```text
director  UNREAD: 0
operator  UNREAD: 3
  - 2026-06-15T18-42-44Z-operator2-to-all-verification-report.md
  - 2026-06-15T18-45-12Z-coordinator-to-all-coordination.md
  - 2026-06-15T18-58-49Z-coordinator-to-all-coordination.md
director2 UNREAD: 1
  - 2026-06-15T18-58-49Z-coordinator-to-all-coordination.md
operator2 UNREAD: 1
  - 2026-06-15T18-58-49Z-coordinator-to-all-coordination.md
```

Peer heartbeats in coordinator status were all ONLINE on `e6205050`:

```text
director   ONLINE
director2  ONLINE
operator   ONLINE
operator2  ONLINE
```

## Gate Proof

Smoke:

```text
scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known smoke advisories remain:

```text
R2 invisible-green WARN
tests/unit/test_discovery_identity_xfail.py:193 skip() in a pin file
tests/unit/test_lane_silent_gate_siblings_xfail.py:64 importorskip('cv2')
```

Wave 2 gate:

```text
scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 20, 'open': 10}
gate rows: 21; executable selectors: 24
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json
artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score,
and finite lipsync.offset_frames
15 failed, 57 passed
exit 1
```

Locks and product-oracle artifact:

```text
find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

## Open Wave 2 Rows

Current open Wave 2 rows from `docs/REMEDIATION-INVENTORY.md`:

- `lipsync-veto` (`cinema/auto_approve.py:502`, lane B, lock
  `W2-auto_approve.py.lock`, pin
  `tests/unit/test_postprocess_audio_siblings_xfail.py`)
- `lipsync-precheck-cascade-gap` (`cinema/shots/controller.py:1655`, lane B,
  no lock, pin `test-infeasible`)
- `http-clearperf-silent200` (`web_server.py:972`, lane B, lock
  `W2-web_server.py.lock`, pin `tests/unit/test_discovery_web_server_xfail.py`)
- `http-drivingvid-orphan` (`web_server.py:909`, lane B, lock
  `W2-web_server.py.lock`, pin `tests/unit/test_discovery_web_server_xfail.py`)
- `http-addchar-float-unguarded` (`web_server.py:567`, lane B, lock
  `W2-web_server.py.lock`, pin `tests/unit/test_discovery_web_server_xfail.py`)
- `http-null-json-body` (`web_server.py:1966`, lane B, lock
  `W2-web_server.py.lock`, pin `tests/unit/test_discovery_web_server_xfail.py`)
- `http-styleboard-false201` (`web_server.py:984`, lane B, lock
  `W2-web_server.py.lock`, pin `tests/unit/test_discovery_web_server_xfail.py`)
- `ckpt-sceneidx-dead` (`cinema/checkpoint.py:87`, lane B, no lock, pin
  `tests/unit/test_discovery_checkpoint_xfail.py`)
- `ckpt-shotaudio-loss` (`cinema/checkpoint.py:87`, lane B, no lock, pin
  `tests/unit/test_discovery_checkpoint_xfail.py`)
- `ckpt-projectid-nocrosscheck` (`cinema/checkpoint.py:93`, lane B, no lock,
  pin `tests/unit/test_discovery_checkpoint_xfail.py`)

## Working Tree / Index Warning

The shared index/worktree remains dirty from existing seat state. Before writing
this handoff, `env -u GIT_INDEX_FILE git diff --cached --name-status` showed
pre-existing staged modifications/deletions across production files, seen
cursors, recent mailbox files, and handoff docs. Do not treat that staged scope
as coordinator-owned work.

Important recurring fix: ordinary git/pytest commands should use
`env -u GIT_INDEX_FILE`. If a scoped coordinator docs/mailbox commit is needed
while the shared index is dirty, use a temporary index:

```text
env -u GIT_INDEX_FILE GIT_INDEX_FILE=.git/index-codex-coordinator-commit-tmp git ...
```

Inspect staged scope before commit and refresh only the committed path in the
shared index if the shared index shows a bogus `D/??` pair afterward.

## Next Coordinator Moves

1. Read mailbox first. Start with
   `.agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2`
   and recent `coordination/mailbox/sent/` entries.
2. Do not consume a coordinator cursor; coordinator is unpinned.
3. Do not send a duplicate routing event unless there is a real transition:
   operator GO/NITS/FAIL, lock correction, product-oracle artifact, wave gate
   change, new user authorization, or a route that supersedes the current
   task board.
4. Preserve the current assignment unless newer mail/commits supersede it:
   director2 owns the no-lock checkpoint cluster; operator2 verifies after a
   committed fix and verify request; director/operator remain role-safe
   monitors.
5. Do not claim `W2-web_server.py.lock` or `W2-auto_approve.py.lock` unless
   push/lock side effects are explicitly authorized by the user-principal.
6. Do not author production fixes as coordinator.
