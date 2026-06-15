# Codex continuation protocol

This document is the Codex-side transplant of the repo's four-seat
director/operator process. It does not replace `AGENTS.md` or the
agent-agnostic protocol under `docs/protocol/agents/`; it maps that protocol
onto Codex-native surfaces.

## Codex surfaces

| Need | Codex surface |
|---|---|
| Durable repo rules | `AGENTS.md` |
| Reusable continuation workflow | `.agents/skills/four-seat-protocol/SKILL.md` |
| Explicit spawned role agents | `.codex/agents/*.toml` |
| Session lifecycle guardrails | `.codex/hooks.json` + `.codex/hooks/*.sh` |
| Read-only state report | `scripts/continuation_readiness.py` |
| Live seat orientation | `.agents/skills/four-seat-protocol/scripts/seat_status.py` |

The remaining `.claude/` script path is intentional for now: Codex wrappers
reuse the same tested shell/Python implementation instead of forking protocol
logic. Codex-facing instructions live in this file, `.agents/skills/`, and
`.codex/`.

## Mode selection

Default mode is **readiness bridge**. A Codex thread is not a director,
operator, or coordinator unless the user explicitly says so.

Readiness bridge:

- May run read-only orientation and summarize state.
- Must not consume mailbox cursors.
- Must not send mailbox events.
- Must not edit remediation inventory, handoffs, or presence.
- Must not claim director/operator ownership.

Live seat:

- Requires an explicit seat name: `director`, `director2`, `operator`, or
  `operator2`.
- Must surface unread count before processing mailbox events.
- May consume events only intentionally, knowing that cursor files are staged.
- Must follow the seat ownership rules in `docs/protocol/agents/`.

Coordinator:

- On-demand only.
- Starts with the coordinator seat-status command, not the generic readiness
  bridge.
- Reconciles and routes; it does not author production fixes.
- Has no cursor and must not run `consume-events`.
- Writes only for a real state transition, routing need, lock correction,
  wave-open/close artifact, or user-facing escalation; otherwise it reports a
  no-op with command evidence.
- Must not mark correctness verified without the required operator GO and
  executed evidence.

## Subagent-Driven Seat Cycle

When the user explicitly asks Codex to run **all seats**, complete **one more
cycle**, or otherwise coordinate multiple live seats, the default Codex
implementation is a coordinator-held subagent cycle:

1. The parent/coordinator context captures the shared baseline:
   `seat_status.py coordinator --wave 2`, `git log --oneline -5`,
   `scripts/wave_gate_check.py 2`, and `scripts/ci_smoke.py`.
2. The parent orients all four live seats with
   `.agents/skills/four-seat-protocol/scripts/seat_status.py <seat> --wave 2`
   and surfaces each unread count before any mailbox processing.
3. The parent spawns bounded role agents from `.codex/agents/`:
   `protocol-director` for `director` / `director2`, and
   `protocol-operator` for `operator` / `operator2`.
4. Each spawned seat prompt names the concrete seat, current HEAD, unread
   count, lane ownership, allowed write scope, and whether mailbox consumption
   is intentional for that seat.
5. Directors may brief, route, or implement within their lane; operators verify
   only actual landed diffs and emit GO/NITS/FAIL reports; idle seats return
   no-op evidence instead of inventing work.
6. The parent waits for the needed role results, then the coordinator reconciles
   inventory/locks/mailbox exactly once if a real transition occurred.

This default applies only after an explicit live-seat or all-seat instruction.
Readiness bridge mode never auto-spawns seats. Subagents do not relax the
director/operator boundary: a director still cannot verify its own work, an
operator still should not author production fixes, and the coordinator still
does not author production code.

If the next ordered row requires `coordination/bin/claim-lock`, remember that
the helper performs fetch/push. Push is user-gated; without explicit push
authorization, choose eligible no-lock work or stop for authorization rather
than claiming the lock.

## Seat-Local Subagent Workflow

All live seats may use Codex subagents as part of their normal workflow, but the
seat remains accountable for the result. A subagent report is evidence, not a
role handoff, mailbox cursor, operator GO, or coordinator reconciliation by
itself.

- `coordinator`: holds the shared baseline, spawns `protocol-director` and
  `protocol-operator` for all-seat cycles, and may run read-only
  `lane-v-verifier` / `money-gate-reviewer` workflows at wave-boundary or
  discovery triggers. The coordinator still does not author production fixes.
- `director` / `director2`: may use subagents for bounded exploration,
  sibling-audit help, implementation shards, or specialist pre-review. The
  director still owns the R-BRIEF, lock/co-sign decisions, final dispatch
  shape, and verify-request; subagents cannot replace the operator GO.
- `operator` / `operator2`: should use read-only verifier subagents for
  cold-context Lane V where useful, especially `lane-v-verifier` for ordinary
  diffs and `money-gate-reviewer` for spend/budget-gate diffs. The operator
  still reads the actual diff, synthesizes the final GO/NITS/FAIL, sends the
  `verification-report`, and handles lock-release atomicity on GO.

Subagent prompts must name the concrete seat, current HEAD, unread count, lane
scope, allowed write set, mailbox consumption decision, and expected output.
Never run two implementation subagents in parallel on shared files. Idle seats
return no-op evidence instead of inventing work.

## Read-only continuation command

For Codex app or ad-hoc Codex threads:

```bash
.venv/bin/python scripts/continuation_readiness.py
```

For execution-readiness checks:

```bash
.venv/bin/python scripts/continuation_readiness.py --smoke
```

This command reports git, mailbox unread counts, Wave state, ADR-028 ceremony
state, environment status, and installed Codex transplant artifacts. It exits
successfully as a report command even when Wave or ceremony gates are red.

## Live-seat launch

For CLI seats in one shared working tree:

```bash
cd /Users/hyungkoookkim/Content
export CODEX_SEAT=<director|director2|operator|operator2>
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-codex-$CODEX_SEAT"
[ -f "$GIT_INDEX_FILE" ] || git read-tree HEAD
codex
```

Inside the session, start with:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py "$CODEX_SEAT" --wave 2
git log --oneline -5
```

For an explicit coordinator session, start with:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
git log --oneline -5
.venv/bin/python scripts/wave_gate_check.py 2
.venv/bin/python scripts/ci_smoke.py
```

If the seat must process mailbox events:

```bash
coordination/bin/consume-events "$CODEX_SEAT"
```

`consume-events` mutates and stages `coordination/mailbox/seen/<seat>.txt`.
Never run it in readiness bridge mode.
Never run it for the coordinator; the coordinator is unpinned and reconciles
from all-time coordinator/all mailbox evidence at the §6f triggers.

## Codex hooks

`.codex/hooks.json` registers Codex lifecycle hooks:

- `SessionStart`: delegates to the R-START smoke tripwire.
- `PreToolUse` on `Bash`: delegates to the git-index guard.
- `PostToolUse` on `Bash|apply_patch|Edit|Write`: delegates to the state and
  heartbeat updater.

The wrappers bridge `CODEX_SEAT` to the legacy `CLAUDE_SEAT` variable used by
the shared hook implementation. Codex may require `/hooks` review/trust before
repo-local hooks run.

## Custom agents

Project custom agents live under `.codex/agents/`:

- `readiness-bridge`: read-only orientation; never upgrades itself into a seat.
- `protocol-director`: explicit `director`/`director2` work.
- `protocol-operator`: explicit `operator`/`operator2` work.
- `protocol-coordinator`: explicit cross-seat reconciliation.
- `lane-v-verifier`: read-only independent Lane V verification.
- `money-gate-reviewer`: read-only reviewer for budget/cost-gate diffs.

Use them only when the parent asks for subagents or role-specific delegation.
Codex does not spawn subagents automatically in readiness bridge mode. For an
explicit live-seat or all-seat cycle, the parent/coordinator should use the
subagent-driven seat cycle above as the default implementation.

## Evidence discipline

- `scripts/wave_gate_check.py` reports process state; it is not a correctness
  proof.
- A `verified` transition requires the protocol's operator
  `verification-report` GO plus executed evidence.
- Measurement-backed verdicts require committed instruments and citable
  `logs/` artifacts.
- For state-asserting writes, run `git log --oneline -5` immediately before
  the write and again immediately before commit.
