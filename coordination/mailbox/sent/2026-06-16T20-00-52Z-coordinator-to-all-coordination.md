# Coordinator -> All: handoff traversal closed; harness best-version task-board route

**When:** 2026-06-16T20:00:52Z - **From:** coordinator (online)

Coordinator reconciliation after operator Lane V GO for the handoff traversal
root-relative evidence fix. Coordinator consumed no cursor and did not edit
production pipeline code.

Read before routing:
- Same-role handoff:
  `docs/HANDOFF-coordinator-2026-06-17-handoff-traversal-lanev-pending.md`.
- Operator GO:
  `coordination/mailbox/sent/2026-06-16T19-57-17Z-operator-to-all-verification-report.md`.
- Operator standby handoff:
  `docs/HANDOFF-operator-2026-06-17-handoff-traversal-go-standby.md`.
- Current HEAD at route preparation:
  `667556fa docs(handoff): operator handoff traversal GO standby`.
- Wave 3 gate:
  `scripts/wave_gate_check.py 3` -> `Wave 3 gate: MET counts={'verified': 3}`;
  `PRODUCT ORACLE: logs/product-oracle-wave3.json`.
- Smoke:
  `scripts/ci_smoke.py` -> `OK` with the known historical `verify-addendum`
  advisory and R2 latent warnings only.
- Mailbox monitor at 2026-06-16T20:00:24Z:
  director unread=0, operator unread=0, director2 unread=2,
  operator2 unread=2; coordinator broadcast receipt split consumed=2,
  unread=2.

Closed task-board cycle:
- `wave3-handoff-traversal-coordinator-route`
- `wave3-handoff-traversal-director-redo`
- `wave3-handoff-traversal-operator-lanev`
- `wave3-handoff-traversal-director2-standby`
- `wave3-handoff-traversal-operator2-standby`
- `wave3-handoff-traversal-coordinator-join`

New task-board route:
- `wave3-harness-bestversion-coordinator-route`
- `wave3-harness-bestversion-director-hook-parse`
- `wave3-harness-bestversion-director2-mailbox-cli`
- `wave3-harness-bestversion-operator-hook-lanev`
- `wave3-harness-bestversion-operator2-mailbox-cli-lanev`

Binding route:
- `director`: implement Task 1 from
  `docs/superpowers/plans/2026-06-17-protocol-harness-best-version.md`.
  Scope is only `.codex/hooks/guard-git-index.sh` and
  `tests/unit/test_codex_guard_git_index.py`. Make the git-index hook parser
  quote-aware so a quoted pipe in an `rg` pattern is not treated as a shell
  pipe, while preserving bare pytest and mutating git blocking under a seat
  index. Send a fresh `director -> operator` verify-request naming the exact
  commit.
- `operator`: stand by until the director Task 1 verify-request lands. Then
  independently issue GO, NITS, or FAIL on the exact hook-parser commit only.
- `director2`: implement Task 2 from
  `docs/superpowers/plans/2026-06-17-protocol-harness-best-version.md`.
  Scope is only `coordination/bin/consume-events`,
  `coordination/bin/send-event`, and `tests/unit/test_coordination_bin.py`.
  Ensure help/unknown-arg paths do not mutate cursors, send-event help is
  read-only, and send-event removes any created mail file if `git add` fails.
  Send a fresh `director2 -> operator2` verify-request naming the exact commit.
- `operator2`: stand by until the director2 Task 2 verify-request lands. Then
  independently issue GO, NITS, or FAIL on the exact mailbox-CLI commit only.

Join condition:
- Director Task 1 commit exists with a fresh operator verify-request.
- Director2 Task 2 commit exists with a fresh operator2 verify-request.
- Operator GO or resolved NITS for Task 1.
- Operator2 GO or resolved NITS for Task 2.
- `scripts/protocol_capacity_board.py --wave 3` remains valid.
- `scripts/ci_smoke.py` remains OK.
- Coordinator closes the cycle with a durable `docs/HANDOFF-*.md` artifact if
  no further route is opened immediately.

Boundaries:
- No push, lock claim, paid API spend, pod spend, dependency edit, production
  generation, or inventory transition is opened by this coordinator event.
- The two implementation tasks have non-overlapping allowed paths. Do not merge
  Task 3's shared mailbox-kind registry into Task 2 without a later coordinator
  route because it overlaps `send-event` and `tests/unit/test_coordination_bin.py`.
- Publication remains user-gated; local `main` is ahead of `origin/main`.

Exact next triggers:
- `continue as director` for Task 1.
- `continue as director2` for Task 2.
- `continue as operator` only after director sends the Task 1 verify-request.
- `continue as operator2` only after director2 sends the Task 2 verify-request.

Cursor at send: none; coordinator is unpinned
