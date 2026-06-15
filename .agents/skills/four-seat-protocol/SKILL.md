---
name: four-seat-protocol
description: Use in this repo when asked to continue, inspect, transplant, or operate the four-seat director/operator protocol from Codex; covers readiness bridge mode, seat orientation, mailbox rules, Wave gates, and Codex-specific mechanics. Do not use for ordinary feature work unless the user mentions a seat, mailbox, handoff, wave, continuation, readiness, or protocol.
---

# Four-Seat Protocol for Codex

This skill is the Codex-side entry point for the Content repo's four-seat
director/operator process. It ports the Claude-era protocol into Codex surfaces
without making Codex pretend to be Claude Code.

## Source Order

Use this order when artifacts disagree:

1. User direct instruction
2. Git commits and current filesystem
3. Mailbox events in `coordination/mailbox/sent/`
4. Handoffs and `STATE.md` cache
5. Defaults

`STATE.md` is local cache only. If it disagrees with git or mailbox files, git
and mailbox win.

## Pick the Mode

Default to **readiness bridge** unless the user explicitly names a live role.

- Readiness bridge: orient, report, and prepare. Do not consume cursors, send
  mailbox events, edit inventory, or claim director/operator work.
- Director seat: only when the user or parent prompt explicitly names
  `director` or `director2`.
- Operator seat: only when the user or parent prompt explicitly names
  `operator` or `operator2`.
- Coordinator: only when explicitly asked to reconcile or route across seats.

Never silently upgrade from bridge mode into a seat.

## Readiness Bridge Checklist

Run the project command:

```bash
.venv/bin/python scripts/continuation_readiness.py
```

Use `--smoke` when the user asks for execution readiness or before making a
verification-environment claim.

The command is read-only. It reports:

- current HEAD and origin relation
- unread counts for `director`, `director2`, `operator`, `operator2`
- Wave gate state
- ADR-028 ceremony gate state
- environment/smoke status
- Codex transplant artifacts

Do not call `coordination/bin/consume-events` in readiness mode.

## Live Seat Checklist

For a real seat, run:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py <seat> --wave 2
git log --oneline -5
```

Then surface the unread count in the first user-facing response before
processing events. Consume intentionally only after that:

```bash
coordination/bin/consume-events <seat>
```

Consumption mutates and stages the cursor. That is correct only for live-seat
work, never for bridge mode.

## Codex Mechanics

- Use Codex tools and terms: `update_plan`, subagents, skills, `apply_patch`,
  project `.codex/agents`, and `.codex/hooks.json`.
- Do not use Claude-only tool names (`Agent`, `TaskCreate`, `AskUserQuestion`)
  in Codex instructions.
- When dispatching Codex subagents, use the project custom agents under
  `.codex/agents/` only when the parent explicitly asks for that role.
- Use `lane-v-verifier` for read-only Lane V verification and
  `money-gate-reviewer` for read-only budget/cost-gate review when those
  verifier roles are explicitly requested.
- Keep main context responsible for decisions and final synthesis; use
  subagents for bounded exploration, verification, or role-specific work.
- If `GIT_INDEX_FILE` is set, prefix git and pytest shell commands with
  `env -u GIT_INDEX_FILE` unless the task is explicitly about maintaining the
  active per-seat index.
- Use explicit pathspecs for staging and commits when committing is requested.

## Capacity-Max Default Cycle

When the user explicitly enters a live seat, asks a coordinator to continue, or
asks Codex to advance a cycle, use the capacity-max workflow by default unless
the user asks for a narrower single-seat/read-only pass.

1. The parent/coordinator captures the shared baseline:
   `seat_status.py coordinator --wave 2`, `git log --oneline -5`,
   `scripts/wave_gate_check.py 2`, and `scripts/ci_smoke.py`.
2. Build a capacity board from mailbox deltas, inventory rows, active locks,
   gate output, and landed-but-unverified diffs. Assign each seat one of:
   implementation/briefing, co-sign/product-oracle review, Lane V verification,
   routing-only, or idle/no-op.
3. Orient `director`, `director2`, `operator`, and `operator2` with
   `.agents/skills/four-seat-protocol/scripts/seat_status.py <seat> --wave 2`;
   surface each unread count before any mailbox processing.
4. Spawn bounded role agents from `.codex/agents/` for every live seat in the
   cycle: `protocol-director` for director seats and `protocol-operator` for
   operator seats. Idle seats return no-op evidence so the coordinator knows
   the slot was checked.
5. The prompt must name the concrete seat, current HEAD, unread count, lane
   scope, mailbox consumption decision, allowed write set, lock/push status,
   and expected output. Directors may use bounded subagents for lane evidence,
   implementation shards, or pre-review; operators may use read-only verifier
   sidecars while still owning the final GO/NITS/FAIL.
6. Run implementation in parallel only when files/locks are disjoint. Never run
   two implementation agents on shared files or behind the same push-gated lock.
   Pull operator verification forward for already-landed diffs.
7. The coordinator reconciles once after role results: inventory, locks, gate
   evidence, and one consolidated mailbox event only when a real state
   transition or routing need exists.

This default does not apply to readiness bridge mode. A bridge reports state
and stops. If a candidate row requires `coordination/bin/claim-lock`, remember
that the helper fetches and pushes; push is user-gated, so choose eligible
no-lock work or stop for authorization when push has not been granted.

## Seat-Local Subagent Adoption

Subagents are now part of every live seat's normal Codex workflow. They increase
capacity, but they never move authority across role boundaries.

- Coordinator: uses `protocol-director` / `protocol-operator` as the default
  capacity mechanism for live cycles, and read-only `lane-v-verifier` /
  `money-gate-reviewer` only at coordinator-appropriate discovery,
  confirmation, provenance-gap, or wave-boundary triggers.
- Directors (`director`, `director2`): may use subagents for bounded
  exploration, Rule #12/#13 evidence gathering, implementation shards, and
  specialist pre-review. The director still owns the R-BRIEF, lock/co-sign
  gates, dispatch decision, and verify-request.
- Operators (`operator`, `operator2`): may use read-only subagents for cold
  context Lane V and specialist review. The operator still reads the real diff,
  decides GO/NITS/FAIL, sends the `verification-report`, and performs any
  same-commit lock release.

Every subagent prompt must include the concrete seat, HEAD, unread count, lane
scope, allowed write set, mailbox consumption decision, and expected output.
Never run two implementation subagents in parallel on shared files. Idle seats
return no-op evidence rather than inventing work.

## Codex Launch Pattern

For CLI-based live seats, launch Codex from the shared working tree with a seat
marker and per-seat index:

```bash
cd /Users/hyungkoookkim/Content
export CODEX_SEAT=<director|director2|operator|operator2>
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-codex-$CODEX_SEAT"
[ -f "$GIT_INDEX_FILE" ] || git read-tree HEAD
codex
```

The checked-in `.codex/hooks.json` delegates to the existing state, heartbeat,
smoke, and git-index guard scripts. Codex may require `/hooks` review/trust
before project hooks run.

## Verification Rules

- `scripts/wave_gate_check.py` is process state, not correctness proof.
- A future `verified` transition requires the operator `verification-report`
  GO required by the protocol plus executed evidence.
- Measurement-backed GO/NO-GO numbers require committed instruments and
  `logs/` artifacts.
- For state-asserting docs or commits, run `git log --oneline -5` immediately
  before writing and again immediately before commit.

## Related Files

- Codex continuation doc: `docs/protocol/codex/continuation.md`
- Readiness report: `scripts/continuation_readiness.py`
- Seat status: `.agents/skills/four-seat-protocol/scripts/seat_status.py`
- Coordination rules: `coordination/README.md`
- Agent-neutral protocol: `docs/protocol/agents/`
