# Codex Continuation Adapter

This is the short Codex adapter for the executable harness kernel in
`scripts/codex_protocol_model.py`. The active invariant is: durable shared state beats chat memory. Read git, mailbox bodies, cursors, locks, logs, gate evidence, and operator reports before trusting stale prose.

For folder ownership, use `docs/protocol/protocol-assembly-map.md`. For full
agent-neutral governance, use `docs/protocol/agents/`. This file only maps the
kernel onto Codex commands and runtime choices.

## Runtime modes

- Readiness bridge: default mode. Report current durable state and blockers.
  Do not consume cursors, send mailbox, claim locks, push, spend, edit
  inventory, or author production changes.
- Live seat: only when the user or parent prompt explicitly names `director`,
  `director2`, `operator`, or `operator2`. Work inside that seat's authority.
- Coordinator: only when explicitly asked to reconcile, route, gate, or operate
  cross-seat state. The coordinator is unpinned and never consumes a
  coordinator cursor.
- Subagent: bounded by the parent prompt. Subagents do not inherit live-seat or
  coordinator authority unless the prompt explicitly grants it.

## Live-Seat Behavior Sources

Concrete live-seat identity and canonical behavior source are separate.
Behavior source map: `director -> director2`, `director2 -> director2`, `operator -> operator`, `operator2 -> operator`.

Mailbox, cursor, heartbeat, event-addressing, and git-index operations use the concrete seat, not the behavior source.
For example, `CODEX_SEAT=director` uses director mailbox/cursor/index paths
while following the `director2` behavior source.

## Same-Seat Handoff First

On a fresh/transplanted instance, if the user or parent prompt names a live
seat or coordinator, locate the newest handoff from that same concrete role
before ordinary orientation:

- Live seat: newest `docs/HANDOFF-<concrete-seat>-*.md`.
- Coordinator: newest `docs/HANDOFF-coordinator-*.md`.

Use the concrete seat, not the behavior source. For example, `director` reads
`HANDOFF-director-*`, not `HANDOFF-director2-*`. If no same-seat handoff exists,
state that and continue with the first commands below.

## First Commands

Readiness bridge:

```bash
.venv/bin/python scripts/continuation_readiness.py
env -u GIT_INDEX_FILE git log --oneline -5
```

Live seat:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py <seat> --wave 2
env -u GIT_INDEX_FILE git log --oneline -5
```

Coordinator:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
env -u GIT_INDEX_FILE git log --oneline -5
.venv/bin/python scripts/wave_gate_check.py 2
.venv/bin/python scripts/ci_smoke.py
```

Use `<wave>` when the active wave is not 2:

```bash
.venv/bin/python scripts/wave_gate_check.py <wave>
```

## Mailbox-First Rule

mailbox-first decisions: always check mail before protocol decisions or
state-asserting writes. Counts are not enough: read the relevant
`coordination/mailbox/sent/*.md` bodies and let the newest binding event shape
the decision. Cursor consumption is a separate live-seat mutation:

```bash
coordination/bin/consume-events <seat>
```

Do not run that command from readiness bridge mode. Do not consume coordinator
mail.

## Side-Effect Gate

The kernel names `user-gated side effects`: push, lock-claim side effects, paid
API spend, and pod spend require explicit user consent. Use
`env -u GIT_INDEX_FILE` for ordinary git and pytest commands unless you are
deliberately maintaining a seat-local or scoped temporary index.

The coordinator may route and reconcile but does not author behavior-changing
production fixes. A verified inventory transition still needs an operator
`verification-report` GO plus executed evidence; a gate script is process
evidence, not row-correctness proof.

## Optional Tools

- `scripts/mailbox_monitor.py --once` or `--watch --interval 5`: read-only
  mailbox awareness without claiming a seat.
- `scripts/draft_handoff.py <seat> --wave 2 --smoke --output`: draft a
  handoff evidence scaffold; refresh live state before finalizing it.
- `scripts/protocol_effectiveness_report.py`: read-only diagnostics. It does
  not route work, consume mail, or decide inventory state.
- `.codex/agents/agentNN.toml`: optional guardrail extensions. They do not
  replace seat authority, mailbox cursor rules, or user-gated push.

## Subagents

Use project role agents only when the parent prompt asks for that role:
`protocol-director`, `protocol-operator`, `protocol-coordinator`,
`lane-v-verifier`, or `money-gate-reviewer`. Keep the parent responsible for
final synthesis and for any user-gated action.

## Seat Subagent Development

Core rule: seats retain authority; subagents own bounded work.

- Director/director2 may dispatch bounded implementer subagents for independent
  implementation slices, but the director seat still owns the brief,
  acceptance evidence, final synthesis, and verify-request.
- Operator/operator2 may dispatch read-only verifier helpers for diff
  inspection, focused reproduction, or edge-case review, but the operator seat
  still owns the GO/NITS/FAIL report.
- Coordinator may dispatch read-only reconciliation helpers for inventory,
  mailbox, lock, gate, or plan-readiness checks, but the coordinator still
  owns the consolidated route or no-op report.
- Required loop: implementer -> spec review -> quality review -> seat synthesis.
- Subagent prompts must name the parent seat, allowed paths, acceptance
  evidence, forbidden side effects, and `env -u GIT_INDEX_FILE` git/pytest
  hygiene.
- Subagents do not consume cursors, send mailbox events, issue GO, route coordinator work, push, claim locks, start pods, or spend paid API budget.
- Do not run parallel implementation subagents on shared files or behind the
  same push-gated lock.

## Verification Commands

Run the narrow command that proves the current claim:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
.venv/bin/python scripts/wave_gate_check.py <wave>
```

For a commit or handoff, also inspect scope:

```bash
env -u GIT_INDEX_FILE git status --short
env -u GIT_INDEX_FILE git diff --stat
```
