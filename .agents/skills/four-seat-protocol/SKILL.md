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

## Related files

- Kernel: `scripts/codex_protocol_model.py`
- Codex adapter: `docs/protocol/codex/continuation.md`
- Seat status: `.agents/skills/four-seat-protocol/scripts/seat_status.py`
- Root process layer: `AGENTS.md`
- Folder intent: `docs/protocol/protocol-assembly-map.md`
- Agent-neutral protocol: `docs/protocol/agents/`
