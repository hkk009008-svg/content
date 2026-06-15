# Coordinator Handoff - Authorized Wave 2 Route

Generated: 2026-06-15T23:11:27Z / 2026-06-16T08:11:27+0900

## Mode

This is a narrow coordinator state-transfer handoff. No production code,
inventory row, lock file, product-oracle artifact, or mailbox cursor was edited
by this coordinator handoff.

## Live Baseline

- HEAD after final pre-commit refresh:
  `90153a28 docs(handoff): refresh operator2 route handoff head`.
- Branch relation: `main...origin/main [ahead 25, behind 8]`.
- Coordinator/all mailbox scope: 179 all-scope events; coordinator is unpinned
  and has no cursor.
- Latest coordinator route:
  `coordination/mailbox/sent/2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`.
- Route commit: `875c1ab2 coord(route): authorized wave2 product oracle and locks`.
- User-principal authorization is recorded in that route event: lock-claim/push
  for Wave 2 `lipsync-veto` and HTTP rows, plus product-oracle
  write/pod/paid-API spend as needed.
- Newer handoff-only commits after the route:
  `f68a0d7b docs(handoff): refresh director authorized route`,
  `e5f1a798 docs(handoff): operator2 standby for authorized wave2 route`, and
  `63e83f9f docs(handoff): operator product oracle checker route`, then
  `90153a28 docs(handoff): refresh operator2 route handoff head`.

## Gate Proof

`scripts/wave_gate_check.py 2` remains UNMET:

- counts: `{'verified': 24, 'open': 6}`
- gate rows: 21
- executable selectors: 24
- blocker: no committed `logs/product-oracle-*.json` with
  `artifact_kind=product-oracle`, `wave=2`, finite `arcface.arc_score`, and
  finite `lipsync.offset_frames`
- executed selector tail: 9 failed, 58 passed
- failing cluster: `lipsync-veto` plus HTTP/web-server rows

`scripts/ci_smoke.py` passed:

- R1 xfail strictness: PASS
- R2 invisible-green: WARN on existing advisory risks
- R3 gate executes pins: PASS
- R4 CI runs runxfail: PASS
- result: OK

## Receipt Split

Fresh `seat_status.py <seat> --wave 2` after the final refresh:

- `director`: cursor `2026-06-15T22:59:40Z`, unread 1
  (`2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`). Director has
  a newer handoff commit, `f68a0d7b`, but the cursor still shows the route
  unread.
- `operator`: cursor `2026-06-15T23:07:16Z`, unread 0. Operator consumed the
  route and committed `63e83f9f`, positioning the seat as product-oracle
  checker / Pair-A standby.
- `director2`: cursor `2026-06-15T22:59:40Z`, unread 1
  (`2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`).
- `operator2`: cursor `2026-06-15T22:59:40Z`, unread 1
  (`2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`). Operator2 has
  newer standby handoff commits, `e5f1a798` and `90153a28`, but the cursor
  still shows the route unread.

All four peer heartbeats were online during the handoff refresh.

## Route Board To Preserve

The route event assigns:

- `director2`: implement Pair-B Wave 2 blockers after safe lock claim:
  `lipsync-veto` in `cinema/auto_approve.py`, then the HTTP cluster in
  `web_server.py`. Claim-lock helper is authorized but dangerous in the dirty
  shared tree because it can `git reset --hard @{u}` on push rejection.
- `operator2`: verify director2 landed commits only. On GO, manually stage the
  verification-report event and lock deletion in the same commit; do not use
  `coordination/bin/release-lock` for a GO path.
- `director`: produce or report the Wave 2 product-oracle artifact. Allowed
  write set is `logs/product-oracle-*.json`, measurement helper/script/test/docs
  if needed, and mailbox/status artifacts. No production code under this route.
- `operator`: independently check a landed product-oracle artifact. Do not
  duplicate Pair-B Lane V.

## Current Open Wave 2 Work

Active blockers:

- `lipsync-veto` - `cinema/auto_approve.py`, lock `W2-auto_approve.py.lock`
- `http-clearperf-silent200` - `web_server.py`, lock `W2-web_server.py.lock`
- `http-drivingvid-orphan` - `web_server.py`, lock `W2-web_server.py.lock`
- `http-addchar-float-unguarded` - `web_server.py`, lock `W2-web_server.py.lock`
- `http-null-json-body` - `web_server.py`, lock `W2-web_server.py.lock`
- `http-styleboard-false201` - `web_server.py`, lock `W2-web_server.py.lock`
- product-oracle artifact - `logs/product-oracle-*.json`

`coordination/locks/` contained only `.gitkeep`; no active lock file existed at
handoff prep. `find logs -maxdepth 1 -type f -name 'product-oracle-*.json'`
returned no output.

## Dirty Worktree / Index Cautions

At handoff prep, shared status still had unrelated WIP:

- modified protocol-effectiveness / continuation files:
  `.agents/skills/four-seat-protocol/SKILL.md`,
  `docs/protocol/codex/continuation.md`,
  `scripts/continuation_readiness.py`,
  `tests/unit/test_codex_protocol_artifacts.py`,
  `tests/unit/test_continuation_readiness.py`
- untracked handoff/tooling files including `scripts/draft_handoff.py`,
  `scripts/protocol_effectiveness_report.py`, and related tests

Do not run push/lock helpers from this dirty shared tree unless WIP is protected
or the seat is operating in a safe isolated/clean state.

## Next Coordinator Startup

Run, in order:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
env -u GIT_INDEX_FILE git log --oneline -8
.venv/bin/python scripts/wave_gate_check.py 2
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 2
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2
```

Then read any mailbox events after
`2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`. If no new
implementation, product-oracle artifact, lock transition, or operator GO has
landed, do not send another coordinator route. If a row is fixed and has the
required operator GO, reconcile inventory and lock state exactly once.
