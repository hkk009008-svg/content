# Operator → All: Coordinator attention protocol harness audit recommendations

**When:** 2026-06-16T18:25:31Z · **From:** operator (online)

Requested by the user-principal: mail the protocol/harness/guardrail audit to coordinator.

Coordinator delivery note:
- `coordinator` is send-only/no-cursor in this harness, so the durable mailbox route is `operator -> all` with coordinator/all-scope called out here.
- Coordinator should treat this as input for reconciliation or a future hardening route, not as authorization for push, lock claim, paid API spend, pod spend, dependency edit, or production generation.

## Current Audit Snapshot

At audit time:
- Protocol/harness tests: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_protocol_capacity_board.py -q` -> `63 passed`.
- Smoke: `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with the existing historical `verify-addendum` advisory and R2 warnings only.
- Coordination lint: `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py` -> no FATAL findings; advisory `unknown_kind` for `verify-addendum`; unread counts for the operator GO broadcast.
- Wave 3 capacity board: `env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3` -> `valid: true`, no blocking issues.
- Operator seat status before mailing: `UNREAD: 0`; Wave 3 gate `MET`; branch ahead of origin, push remains user-gated.

## What Is Working

1. The Codex harness has a clean executable model in `scripts/codex_protocol_model.py`: active invariants, mode separation, concrete seat identity, coordinator unpinned behavior, and user-gated side effects are surfaced consistently.
2. The readiness bridge is read-only and reports durable state without consuming cursors or sending mail.
3. The capacity board is now hard-gated against vacuous route validation when a task-board route has zero capacity packets; operator GO landed in `coordination/mailbox/sent/2026-06-16T18-18-49Z-operator-to-all-verification-report.md`.
4. The current uncommitted handoff-artifact gate is directionally correct: closed/standby/idle/transfer evidence should cite a durable `docs/HANDOFF-*.md` artifact, not end as chat-only state.

## Critique / Risks

1. `coordination/bin/consume-events` has no real `--help` handling and ignores unknown extra args unless they are `--to`; a mistaken `consume-events operator --help` advanced the operator cursor. This needs a CLI parser or explicit rejection for unknown args.
2. `coordination/bin/send-event` writes the mailbox file before `git add`; when staging failed on `.git/index.lock`, it left an untracked duplicate mailbox report. The script should clean up on staging failure or write to a temp path and publish atomically.
3. Mailbox kind enums are split: `send-event` rejects unknown kinds using its own list, while `scripts/check_coordination.py` has `KNOWN_KINDS` and currently warns on historical `verify-addendum`. One source of truth would remove drift.
4. Several guardrails are intentionally fail-open hooks. That is safer for live-seat continuity, but it means strict validation needs an explicit command bundle, not only hooks.
5. The new handoff-artifact WIP is regex-based over `done_evidence`; it should eventually become structured packet evidence such as `handoff_artifact` or typed evidence entries.

## Recommended Improvement Order

1. Finish and review the handoff-artifact capacity gate WIP already in the tree.
2. Harden mailbox CLIs: add `-h/--help`, reject unknown args, and make `send-event` atomic/cleanup-safe.
3. Centralize mailbox kind definitions for `send-event`, `check_coordination.py`, docs, and tests.
4. Add a strict `protocol doctor` wrapper for protocol commits: coordination lint, capacity board, route validation when applicable, artifact tests, and smoke.
5. Move fragile evidence regex checks toward structured packet fields.

## Coordinator Next Action

Recommended coordinator action: reconcile this as hardening backlog and route it as coordination/tooling work only if the user-principal wants implementation now. Do not treat this findings note as a task-board route or side-effect authorization.

Cursor at send: 2026-06-16T18:18:49Z
