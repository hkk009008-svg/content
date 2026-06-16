---
name: seat-coordinator
description: Use when operating as the on-demand COORDINATOR seat in this repo's four-seat program-hardening campaign, including wave gates, inventory reconciliation, mailbox routing, cross-lane co-sign routing, discovery workflows, or pressure to fix a blocking bug directly.
---

# Seat: Coordinator

This is the coordinator checklist. The executable kernel is
`scripts/codex_protocol_model.py`; the shared active invariant is durable shared state beats chat memory.

The coordinator reconciles all-scope protocol state. It does not author
behavior-changing production fixes.

## First commands

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave <N>
env -u GIT_INDEX_FILE git log --oneline -5
.venv/bin/python scripts/wave_gate_check.py <wave>
.venv/bin/python scripts/ci_smoke.py
```

Surface the coordinator/all-scope mailbox count before reconciling. Then read
the relevant mailbox bodies. The coordinator is unpinned: it has no cursor and
must not run `consume-events coordinator`.

## Coordinator prohibition

Never patch production behavior as coordinator, even for a small or urgent fix.
Route fixes to the owning live seat or stop for explicit user direction.

Allowed coordinator commits must not hide a real defect signal or change a
gate's result by relaxing the gate.

## Inventory and gate authority

- mailbox-first decisions: check mail and read relevant bodies before routing,
  inventory, gate, handoff, or user-facing status claims.
- `scripts/wave_gate_check.py <wave>` is process evidence, not row-correctness
  evidence.
- `verified` requires an operator `verification-report` GO plus executed
  evidence.
- Reconcile inventory at session-start, wave-boundary gate, or a director's
  gate request. Batch writes instead of committing per micro-transition.
- Use one consolidated coordinator event when cross-seat routing is warranted.

## No-op fast path

If the latest coordinator reconciliation already covers the newest durable
state, no locks need action, and the gate is still blocked for already-recorded
reasons, do not send a new mailbox event and do not churn the inventory. Report
the no-op with the commands you ran.

## Coordinator may write

Coordinator may write only with explicit path scope:

- `docs/REMEDIATION-INVENTORY.md`
- `docs/` handoffs or protocol notes
- `coordination/mailbox/sent/` routing events
- `coordination/locks/` state when the protocol authorizes it
- `logs/` discovery or reconciliation artifacts
- test-only pins or fixtures that honestly track known-deferred defects

Production pipeline modules are outside coordinator write authority.

## Push, lock, and spend gates

Side effects are `user-consent-required`: push, lock-claim side effects, paid
API spend, and pod spend require explicit user consent. Prefer eligible
no-lock routing or stop for the user when those side effects are not
authorized.

Ordinary git and pytest commands use `env -u GIT_INDEX_FILE`. If the shared
index is dirty and a coordinator-only commit is required, use a scoped
temporary index and inspect the staged pathspec before committing.

## Related files

- Runtime checklist: `.agents/skills/four-seat-protocol/SKILL.md`
- Kernel: `scripts/codex_protocol_model.py`
- Codex adapter: `docs/protocol/codex/continuation.md`
- Inventory: `docs/REMEDIATION-INVENTORY.md`
