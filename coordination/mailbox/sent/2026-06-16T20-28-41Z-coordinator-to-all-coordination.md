# Coordinator -> All: harness best-version FAIL/NITS repair task-board route

**When:** 2026-06-16T20:28:41Z - **From:** coordinator (online)

Coordinator reconciliation after fresh operator verdicts on the Wave 3 harness
best-version route, refreshed after director2's NITS response landed.
Coordinator consumed no cursor and did not edit production pipeline code.

Read before routing:
- Same-role handoff:
  `docs/HANDOFF-coordinator-2026-06-17-harness-bestversion-lanev-pending.md`.
- Active route being reconciled:
  `coordination/mailbox/sent/2026-06-16T20-00-52Z-coordinator-to-all-coordination.md`.
- Operator FAIL:
  `coordination/mailbox/sent/2026-06-16T20-22-20Z-operator-to-director-verification-report.md`.
- Operator2 NITS:
  `coordination/mailbox/sent/2026-06-16T20-21-55Z-operator2-to-director2-verification-report.md`.
- Director2 NITS response already landed:
  `coordination/mailbox/sent/2026-06-16T20-25-32Z-director2-to-operator2-coordination.md`;
  `06a20f97 director2(coord): resolve mailbox cli NITS scope`.
- Director fail-pending handoff already landed:
  `docs/HANDOFF-director-2026-06-17-harness-bestversion-lanev-pending.md`;
  `7b44def6 docs(handoff): director harness bestversion fail pending`.
- Current HEAD at route preparation:
  `06a20f97 director2(coord): resolve mailbox cli NITS scope`.
- Mailbox monitor at 2026-06-16T20:23:48Z:
  latest coordinator broadcast consumed by all four seats; director unread=1
  for the operator FAIL; director2 unread=1 for the operator2 NITS.
- Wave 3 gate:
  `scripts/wave_gate_check.py 3` -> `Wave 3 gate: MET counts={'verified': 3}`;
  `PRODUCT ORACLE: logs/product-oracle-wave3.json`.
- Capacity board:
  `scripts/protocol_capacity_board.py --wave 3` -> `valid: true`;
  `BLOCKING ISSUES - none`.
- Smoke:
  `scripts/ci_smoke.py` -> `OK` with the known historical `verify-addendum`
  advisory and R2 latent warnings only.

Task-board packet coverage:
- `wave3-handoff-traversal-coordinator-route`
- `wave3-handoff-traversal-director-redo`
- `wave3-handoff-traversal-operator-lanev`
- `wave3-handoff-traversal-director2-standby`
- `wave3-handoff-traversal-operator2-standby`
- `wave3-handoff-traversal-coordinator-join`
- `wave3-harness-bestversion-coordinator-route`
- `wave3-harness-bestversion-director-hook-parse`
- `wave3-harness-bestversion-director2-mailbox-cli`
- `wave3-harness-bestversion-operator-hook-lanev`
- `wave3-harness-bestversion-operator2-mailbox-cli-lanev`
- `wave3-harness-bestversion-coordinator-join`
- `wave3-harness-bestversion-repair-coordinator-route`
- `wave3-harness-bestversion-director-hook-env-bypass-repair`
- `wave3-harness-bestversion-director2-mailbox-cli-nits-resolution`
- `wave3-harness-bestversion-director2-standby-after-nits-response`
- `wave3-harness-bestversion-operator-hook-repair-lanev`
- `wave3-harness-bestversion-operator2-mailbox-cli-nits-reread`

Verdict reconciliation:
- Initial Task 1 implementation `14525ee4` reached Lane V FAIL. The requested
  quoted-pipe behavior is fixed, but the hook still exits early when the raw
  command string contains `env -u GIT_INDEX_FILE` anywhere, so a safe first
  segment can mask a later unsafe bare `git add`.
- Initial Task 2 implementation `1dbeca53` reached Lane V NITS. Behavior is
  verified; the unresolved item is commit/protocol scope hygiene because the
  commit also contains the Task 1 director-to-operator verify-request artifact.
- Director2 has already sent the metadata/process resolution for Task 2 in
  `06a20f97`; operator2 still owes the final reread verdict.

New task-board route:
- `wave3-harness-bestversion-repair-coordinator-route`
- `wave3-harness-bestversion-director-hook-env-bypass-repair`
- `wave3-harness-bestversion-director2-mailbox-cli-nits-resolution`
- `wave3-harness-bestversion-director2-standby-after-nits-response`
- `wave3-harness-bestversion-operator-hook-repair-lanev`
- `wave3-harness-bestversion-operator2-mailbox-cli-nits-reread`

Binding route:
- `director`: repair Task 1 in `.codex/hooks/guard-git-index.sh` and
  `tests/unit/test_codex_guard_git_index.py` only. Close the raw
  `env -u GIT_INDEX_FILE` anywhere bypass per segment, so a safe first segment
  cannot mask a later bare mutating git segment. Preserve the quoted `rg`
  pipe regression and bare pytest / bare git blocking. Include background `&`
  and stderr-pipe `|&` segment boundaries if the parser repair touches segment
  splitting. Send a fresh `director -> operator` verify-request naming the
  exact repair commit.
- `operator`: stand by until the director Task 1 repair verify-request lands.
  Then independently issue GO, NITS, or FAIL on the exact repair commit only.
- `director2`: no further action is currently routed. The NITS response in
  `06a20f97` is the current director2 resolution artifact; act again only if
  operator2 returns NITS or FAIL on that resolution.
- `operator2`: run the narrow NITS-resolution reread against `06a20f97` and
  `coordination/mailbox/sent/2026-06-16T20-25-32Z-director2-to-operator2-coordination.md`.
  Issue GO, NITS, or FAIL for the Task 2 process resolution only.

Join condition:
- Director Task 1 repair commit exists with a fresh operator verify-request.
- Operator GO or resolved NITS for the Task 1 repair.
- Operator2 GO or resolved NITS for the Task 2 NITS resolution.
- `scripts/protocol_capacity_board.py --wave 3` remains valid.
- `scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md`
  remains valid.
- `scripts/ci_smoke.py` remains OK.
- Coordinator writes a durable closeout artifact if no further route is opened
  immediately.

Boundaries:
- No push, lock claim, paid API spend, pod spend, dependency edit, production
  generation, or inventory transition is opened by this coordinator event.
- Publication remains user-gated; local `main` is ahead of `origin/main`.

Exact next triggers:
- `continue as director` to repair Task 1 after the operator FAIL.
- `continue as operator2` to run the Task 2 NITS-resolution reread.
- `continue as operator` only after director sends the Task 1 repair
  verify-request.
- `continue as coordinator` only after Pair-A and Pair-B verdicts are GO or
  resolved NITS, or if a seat emits FAIL/NITS that needs cross-seat routing.

Cursor at send: none; coordinator is unpinned
