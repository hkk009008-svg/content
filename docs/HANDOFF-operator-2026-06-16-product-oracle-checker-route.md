# Operator handoff - product-oracle checker route

READ FIRST AS `operator`. Trust git and live mailbox state over this prose if
they diverge.

## State At Handoff

Timestamp: `2026-06-15T23:09:40Z` UTC (`2026-06-16T08:09:40+0900` KST).

Seat: `operator` / Pair-A operator.

Current HEAD at live refresh:

```text
f68a0d7b docs(handoff): refresh director authorized route
d7e98a46 docs(handoff): director protocol notices consumed
875c1ab2 coord(route): authorized wave2 product oracle and locks
148a81df coord(cursor): director consume protocol notice
ef1c56b8 coord(status): operator fold self-broadcast cursor
d029a00a coord(cursor): operator2 consume standby notices
```

Branch relation from `seat_status.py operator --wave 2`:

```text
main vs origin/main: 22 ahead, 8 behind
```

## Mailbox / Cursor

Initial live recompute before consumption:

```text
cursor: 2026-06-15T22:59:40Z
UNREAD: 1
  - 2026-06-15T23-07-16Z-coordinator-to-all-coordination.md
```

I read the unread coordinator route and consumed the operator cursor:

```text
$ coordination/bin/consume-events operator
cursor operator: 2026-06-15T22:59:40Z -> 2026-06-15T23:07:16Z; unread now: 0
```

Fresh operator status after consumption:

```text
HEAD: f68a0d7b docs(handoff): refresh director authorized route
cursor: 2026-06-15T23:07:16Z
UNREAD: 0
```

## Current Operator Assignment

Coordinator route:
`coordination/mailbox/sent/2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`.

User authorization is now recorded for the side effects named in that route:
lock-claim/push for Wave 2 `lipsync-veto` and HTTP rows, plus
product-oracle artifact write/pod/paid-API spend as needed.

Operator-specific task:

- Stand by for `director` to land a committed `logs/product-oracle-*.json`
  artifact.
- After the artifact lands, independently check that it is committed, finite,
  and accepted by `scripts/wave_gate_check.py 2` for the product-oracle portion.
- Expected artifact contract: `artifact_kind="product-oracle"`, `wave=2`,
  finite `arcface.arc_score`, and finite `lipsync.offset_frames`.
- Allowed operator write set: verification/status mailbox event and operator
  cursor only. No production code.
- Do not duplicate Pair-B Lane V. `operator2` owns verification of
  director2's `lipsync-veto` / HTTP implementation commits.

No product-oracle artifact has landed yet:

```text
$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

## Seat Board

- `director`: route recipient for the product-oracle artifact. Latest peer
  status before this handoff saw the coordinator route unread for that seat;
  `f68a0d7b` is a director handoff refresh, not an operator GO.
- `operator`: consumed through the coordinator route to
  `2026-06-15T23:07:16Z`; unread 0; product-oracle checker standby.
- `director2`: route recipient for Pair-B locks/implementation. The route
  allows `lipsync-veto` and HTTP cluster work after safe lock claim.
- `operator2`: Pair-B Lane V standby for real director2 verify requests.

Locks at handoff evidence time:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

## Gate / Verification Evidence

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md - kind 'verify-addendum' not in KNOWN_KINDS
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Wave 2 gate from `seat_status.py operator --wave 2`:

```text
Wave 2 gate: UNMET  counts={'verified': 24, 'open': 6}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, and finite lipsync.offset_frames
PYTEST summary: 9 failed, 58 passed
```

Open inventory rows at handoff evidence time:

```text
ckpt-nan-json-token
ckpt-sceneclips-dead
ckpt-stage-notrestored
http-addchar-float-unguarded
http-clearperf-silent200
http-drivingvid-orphan
http-null-json-body
http-styleboard-false201
identity-arcface-embselect
lipsync-veto
```

## Dirty Worktree / Ownership

Shared worktree has unrelated protocol-effectiveness and handoff WIP. Preserve
it; do not broad-stage from the operator seat.

```text
M .agents/skills/four-seat-protocol/SKILL.md
M docs/protocol/codex/continuation.md
M scripts/continuation_readiness.py
M tests/unit/test_codex_protocol_artifacts.py
M tests/unit/test_continuation_readiness.py
?? docs/HANDOFF-coordinator-2026-06-16-automated-handoff-tool-transplant.md
?? docs/HANDOFF-director-2026-06-16-lipsync-reconciled-product-oracle-open.md
?? docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
?? docs/HANDOFF-operator-2026-06-16-lipsync-precheck-reconciled.md
?? scripts/draft_handoff.py
?? scripts/protocol_effectiveness_report.py
?? tests/unit/test_draft_handoff.py
?? tests/unit/test_protocol_effectiveness_report.py
```

## Next Operator

1. Start with:
   `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2`.
2. If `director` has landed a `logs/product-oracle-*.json`, verify the exact
   committed artifact contract and run `scripts/wave_gate_check.py 2` to confirm
   the product-oracle blocker is satisfied or identify the remaining mismatch.
3. Emit a status/verification mailbox event only after that concrete artifact
   check. If no artifact has landed, remain standby.
4. Do not claim locks or verify Pair-B implementation commits from this seat;
   those are routed to `director2` / `operator2`.
5. Use `env -u GIT_INDEX_FILE` for ordinary git/pytest commands and preserve
   the unrelated dirty WIP.
