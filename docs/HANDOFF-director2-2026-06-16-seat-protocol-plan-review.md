# HANDOFF - director2 - 2026-06-16 - SEAT_PROTOCOL plan review

READ FIRST AS `director2` or coordinator. Trust git, mailbox artifacts, and
the executable protocol tools over this prose if they diverge.

## Seat And Scope

Seat: `director2` / Pair-B director.

Assignment consumed from:

- `coordination/mailbox/sent/2026-06-16T03-57-57Z-operator2-to-all-status.md`
- `coordination/mailbox/sent/2026-06-16T04-19-21Z-coordinator-to-all-coordination.md`
- `coordination/mailbox/sent/2026-06-16T05-04-09Z-coordinator-to-all-coordination.md`

Cursor advanced:

```text
director2: 2026-06-16T03:47:24Z -> 2026-06-16T05:04:09Z
```

This is a planning response only. It is not production implementation, not a
verification verdict, not a lock claim, not a push, not pod/API spend, and not
an inventory transition.

Allowed write set for this response:

- `docs/HANDOFF-director2-2026-06-16-seat-protocol-plan-review.md`
- `coordination/mailbox/seen/director2.txt`
- the matching `director2` mailbox status event

## Live Evidence Checked

```text
$ CODEX_SEAT=director2 env -u GIT_INDEX_FILE .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 2
HEAD 0d578571 coord(relay): route seat protocol plan review
vs origin/main: 5 ahead, 0 behind
UNREAD: 3
Wave 2 gate: MET counts={'verified': 30}
selector tail: 71 passed in 2.84s
```

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
0d578571 coord(relay): route seat protocol plan review
30fcb944 coord(protocol): add active mailbox monitor
326980d0 coord(protocol): guard live-seat handoff boundary
afdc2bb4 coord(status): operator relay ack
d6857582 coord(status): operator2 relay ack
```

```text
$ rg -n "seat_banner|proof_bundle|done_summary|receipt_split" scripts tests docs .codex .agents coordination -g '!coordination/mailbox/sent/**'
tests/unit/test_mailbox_monitor.py:73:def test_latest_coordinator_broadcast_receipt_split_is_cursor_based(tmp_path: Path) -> None:
```

```text
$ env -u GIT_INDEX_FILE git diff --cached --name-status
M       coordination/mailbox/seen/director2.txt

$ env -u GIT_INDEX_FILE git diff --name-status
M       coordination/mailbox/seen/director.txt
M       coordination/mailbox/seen/operator2.txt
```

The unstaged `director` and `operator2` cursor changes are other-seat state in
the shared tree. They must remain outside this director2 commit unless those
seats explicitly route them.

Late pre-commit refresh read these newer planning responses:

- `coordination/mailbox/sent/2026-06-16T05-07-44Z-director-to-all-status.md`
- `coordination/mailbox/sent/2026-06-16T05-08-16Z-operator2-to-all-status.md`
- `coordination/mailbox/sent/2026-06-16T05-08-23Z-operator-to-all-status.md`

They reinforce the same boundary: use `SEAT_PROTOCOL.md` as proposal input,
preserve existing authority order, build thin tools over existing protocol
truth, and require guard-first tests before implementation. No director2 route
change is needed.

## Recommendation

Do not promote root `SEAT_PROTOCOL.md` directly as canonical policy. Treat it
as proposal input and convert the adopted subset into a reviewed spec under
`docs/superpowers/specs/`, then implement tools and update authoritative docs
only after tests prove the behavior.

The final plan should keep one protocol brain:

- `scripts/codex_protocol_model.py` remains the source for role/mode inference,
  runtime environment fields, side-effect policy, planning relay rules, and
  protocol assembly placement.
- `docs/protocol/codex/continuation.md` remains the Codex-facing operating
  manual generated from or synced with that model-backed shape.
- `.agents/skills/four-seat-protocol/SKILL.md` remains the live runtime
  checklist.
- `.codex/hooks.json` and wrapper hooks remain enforcement entrypoints, not
  policy prose.

## Module Boundaries

Recommended boundary for `seat_banner.py`:

- Thin CLI/view over `codex_protocol_model.infer_runtime_env`.
- Accept explicit `--objective`, `--scope`, `--verify`, `--done`, and
  permission flags rather than inventing them from chat.
- Print the six-field contract and return nonzero only when invoked with an
  explicit `--require-complete` or mutating-action mode.
- Do not read mailbox bodies, consume cursors, stage files, or duplicate
  `seat_status.py`.

Recommended boundary for `proof_bundle.py`:

- Read-only composer, not an authority replacement.
- Inputs: `--seat`, `--wave`, optional `--smoke`, optional `--json`, optional
  mailbox body limit.
- Compose existing sources: `seat_status.py`, `env -u GIT_INDEX_FILE git log`,
  unread mailbox body excerpts, `scripts/wave_gate_check.py`, optional
  `scripts/ci_smoke.py`, and `mailbox_monitor.collect_monitor_state`.
- Emit the exact commands it ran and return nonzero only for command failure,
  not for "this seat has unread work."
- Never consume cursors and never claim an operator GO.

Recommended receipt-split boundary:

- Prefer extending `scripts/mailbox_monitor.py` with a `--broadcast latest|<id>`
  filter or a tiny wrapper importing `collect_monitor_state`.
- Do not create a second parser for mailbox filenames. The monitor already owns
  event parsing and cursor-based receipt state.

Recommended `done_summary.py` boundary:

- Build after `proof_bundle.py`.
- Fact-fill HEAD, changed files, mailbox delta, verification commands, push
  status, blockers, and exact next trigger.
- If a field cannot be proven from git/mailbox/log evidence, print `unknown`
  or `unverified`; do not infer.
- It is a summary emitter, not a verifier and not a coordinator reconciliation.

Recommended guard boundary:

- Put reusable guard logic in `scripts/` with focused unit tests.
- Keep `.codex/hooks/*.sh` as wrappers around shared checks, matching the
  current `guard-git-index.sh` / `session-smoke.sh` / `update-state.sh` shape.
- Extend the existing G6 git-index guard rather than duplicate it.
- Add G5 staged-scope and G8 push-authorization as precise checks with
  fail-open parsing where false positives would halt the fleet.

## Build Order

1. Write the reviewed spec under `docs/superpowers/specs/`. Include the adopted
   six-field contract, proof-bundle contract, guard list, and source-order map.
   Do not delete/archive existing notes in the same move.
2. Add tests for any new fields exported from `codex_protocol_model.py`.
3. Build `scripts/seat_banner.py` with tests against env combinations:
   readiness, live `director2`, coordinator alias, subagent/verifier role, and
   incomplete contract handling.
4. Build `scripts/proof_bundle.py` with temp-repo fixtures proving it is
   read-only, includes mailbox bodies, and can report receipt split via the
   monitor without consuming cursors.
5. Add the receipt-split filter to `mailbox_monitor.py` only if the proof
   bundle needs more than the current latest-broadcast summary.
6. Add guard tests before guard wiring: staged-scope, hook-safe index seeding,
   push authorization, stale-state age, coordinator no-production-write
   boundary, and cursor misuse.
7. Wire hooks after tests are green. Keep push, lock, pod, and paid API side
   effects user-gated.
8. Add `done_summary.py` and the blocked-handoff emitter after the proof bundle
   provides stable machine-readable facts.
9. Update docs and skills narrowly after tools exist; keep
   `docs/protocol/protocol-assembly-map.md` coherent with any new files.

## Caveats

- The role abstraction `director == director2` and `operator == operator2` is
  useful for prompts, but do not flatten seat identity in mailbox, cursor, or
  heartbeat artifacts. Those files are per-seat truth.
- Do not make all subagents globally read-only. Verifier/specialist subagents
  stay read-only; explicitly spawned role agents can do bounded parent-scoped
  work when the parent and protocol allow it.
- Do not encode model-brand wording such as "GPT-5.5 extra thinking" into
  canonical repo policy. Keep the durable principle: compact contracts plus
  executable guards reduce drift.
- Do not downgrade live Codex user updates into silence. Durable artifacts are
  protocol truth, but Codex still owes concise progress updates while working.
- Do not rely on a local pre-push hook alone for G8 unless the installer path is
  explicit. A Codex PreToolUse push guard or script-level push wrapper is more
  likely to be active in this harness.

## Verification Recommendation For Eventual Implementation

Minimum focused checks for the implementation branch:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_codex_protocol_model.py \
  tests/unit/test_mailbox_monitor.py \
  tests/unit/test_continuation_readiness.py \
  tests/unit/test_coordination_bin.py \
  tests/unit/test_check_coordination.py \
  -q
```

Add new tests before new behavior:

- `tests/unit/test_seat_banner.py`
- `tests/unit/test_proof_bundle.py`
- `tests/unit/test_protocol_guards.py` or focused guard-specific files
- hook tests for any `.codex/hooks` wrapper changes

Final branch checks:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Run `scripts/wave_gate_check.py 2` only if the implementation touches wave/gate
surfaces or makes a wave-state claim.

## Next Trigger

Coordinator should reconcile after all four planning responses land. If the
coordinator accepts this boundary, the next route should be a spec-first task
board, not direct implementation from root `SEAT_PROTOCOL.md`.

Push remains user-gated. No lock, pod spend, paid API spend, inventory edit, or
production implementation was performed in this director2 response.
