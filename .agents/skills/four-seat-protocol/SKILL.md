---
name: four-seat-protocol
description: Use in this repo when asked to continue, inspect, hand off, or operate the four-seat director/operator protocol from Codex; covers readiness bridge mode, seat orientation, mailbox rules, Wave gates, and Codex-specific mechanics. Do not use for ordinary feature work unless the user mentions a seat, mailbox, handoff, wave, continuation, readiness, or protocol.
---

# Four-Seat Protocol for Codex

This is the Codex runtime checklist for the Content repo's four-seat protocol.
The executable kernel is `scripts/codex_protocol_model.py`; the short operating
adapter is `docs/protocol/codex/continuation.md`.

Central invariant: durable shared state beats chat memory. Read git commits,
current files, mailbox bodies, cursors, locks, logs, gate evidence, and
operator reports before trusting chat or stale summaries.

## Source order

1. User direct instruction
2. Git commits and current filesystem
3. Mailbox events in `coordination/mailbox/sent/`
4. Handoffs and `STATE.md` cache
5. Defaults

When artifacts disagree, current git and mailbox bodies win over stale prose.

## Mode selection

- Readiness bridge: default mode. Orient and report only.
- Live seat: only when the user or parent prompt explicitly names `director`,
  `director2`, `operator`, or `operator2`.
- Coordinator: only when explicitly asked to reconcile, route, gate, or operate
  cross-seat state.
- Subagent: bounded by the parent prompt and its allowed mutation scope.

Never silently upgrade from bridge mode into a seat.

## Live-seat behavior sources

Concrete live-seat identity and canonical behavior source are separate.
Behavior source map: `director -> director2`, `director2 -> director2`, `operator -> operator`, `operator2 -> operator`.

Mailbox, cursor, heartbeat, event-addressing, and git-index operations use the concrete seat, not the behavior source.
For example, `CODEX_SEAT=operator2` uses operator2 mailbox/cursor/index paths
while following the `operator` behavior source.

## Same-seat handoff first

On a fresh/transplanted instance, if the user or parent prompt names a live
seat or coordinator, first locate the newest handoff from that same concrete
role before ordinary orientation:

- Live seat: newest `docs/HANDOFF-<concrete-seat>-*.md`.
- Coordinator: newest `docs/HANDOFF-coordinator-*.md`.

Use the concrete seat, not the behavior source. If no same-seat handoff exists,
say so and continue with the relevant checklist.

## Readiness bridge checklist

```bash
.venv/bin/python scripts/continuation_readiness.py
env -u GIT_INDEX_FILE git log --oneline -5
```

The bridge may report durable state and blockers. It must not consume cursors,
send mailbox events, edit inventory, claim locks, push, spend, or author
production changes.

Optional read-only awareness:

```bash
.venv/bin/python scripts/mailbox_monitor.py --once
.venv/bin/python scripts/mailbox_monitor.py --watch --interval 5
```

Optional handoff scaffold:

```bash
.venv/bin/python scripts/draft_handoff.py <seat> --wave 2 --smoke --output
```

Refresh live state before finalizing any handoff.

## Live seat checklist

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py <seat> --wave 2
env -u GIT_INDEX_FILE git log --oneline -5
```

Always check mail before protocol decisions or state-asserting writes. Read the
relevant mailbox bodies; do not decide from unread counts alone.

If the live seat intentionally consumes mail:

```bash
coordination/bin/consume-events <seat>
```

That command mutates and stages `coordination/mailbox/seen/<seat>.txt`. Inspect
staged scope before committing cursor-only state.

## Coordinator checklist

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
env -u GIT_INDEX_FILE git log --oneline -5
.venv/bin/python scripts/wave_gate_check.py 2
.venv/bin/python scripts/ci_smoke.py
```

Before committing an active coordinator task-board route:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave <wave>
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave <wave> --validate-route coordination/mailbox/sent/<event>.md
```

Coordinator is unpinned. Read all-scope coordinator mail. Do not consume coordinator mail and do not run `consume-events coordinator`.

The coordinator may reconcile inventory, locks, gate state, mailbox routing,
and handoff state. It may not author behavior-changing production fixes.

## Mailbox and cursor rules

- mailbox-first decisions: check mail and read relevant bodies before protocol
  decisions or state-asserting writes.
- A mailbox-only consume should stage only
  `M coordination/mailbox/seen/<seat>.txt`.
- If `HEAD` advanced, refresh stale seat-local index state before committing a
  cursor-only update.
- Use one consolidated coordinator route when cross-seat routing is warranted.
- Receipt checks are coordination evidence only; they do not prove assigned
  work is complete.

## Git index rule

Use `env -u GIT_INDEX_FILE` for ordinary git and pytest commands. Use a
seat-local or scoped temporary index only when deliberately maintaining cursor,
status, docs, or coordinator-only state.

Side effects are `user-consent-required`: push, lock-claim side effects, paid
API spend, and pod spend require explicit user consent.

## Seat Subagent Development

Core rule: seats retain authority; subagents own bounded work.
Live seats and coordinator may choose bounded subagents at seat discretion; this does not require a separate user request for delegation.

- Director seats (`director`, `director2`) may use bounded implementer
  subagents for independent implementation slices, then require spec review,
  quality review, and director-seat synthesis before any verify-request.
- Operator seats (`operator`, `operator2`) may use read-only verifier helpers
  for diff inspection, focused reproduction, or edge-case review, but the
  operator seat still issues GO/NITS/FAIL.
- Coordinator may use read-only reconciliation helpers for inventory, mailbox,
  lock, gate, or plan-readiness checks, but the coordinator still owns the
  consolidated route or no-op report.
- Required loop: implementer -> spec review -> quality review -> seat synthesis.
- Give subagents only the parent prompt, allowed paths, acceptance evidence,
  forbidden side effects, and `env -u GIT_INDEX_FILE` git/pytest hygiene.
- Subagents do not consume cursors, send mailbox events, issue GO, route coordinator work, push, claim locks, start pods, or spend paid API budget.
- Do not run parallel implementation subagents on shared files or behind the
  same push-gated lock.

## Related files

- Kernel: `scripts/codex_protocol_model.py`
- Codex adapter: `docs/protocol/codex/continuation.md`
- Seat status: `.agents/skills/four-seat-protocol/scripts/seat_status.py`
- Root process layer: `AGENTS.md`
- Folder intent: `docs/protocol/protocol-assembly-map.md`
- Agent-neutral protocol: `docs/protocol/agents/`
