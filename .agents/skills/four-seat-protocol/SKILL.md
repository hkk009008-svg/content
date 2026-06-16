---
name: four-seat-protocol
description: Use in this repo when asked to continue, inspect, hand off, or operate the four-seat director/operator protocol from Codex; covers readiness bridge mode, seat orientation, mailbox rules, Wave gates, and Codex-specific mechanics. Do not use for ordinary feature work unless the user mentions a seat, mailbox, handoff, wave, continuation, readiness, or protocol.
---

# Four-Seat Protocol for Codex

This skill is the Codex runtime checklist for the Content repo's four-seat
director/operator process. The executable harness structure lives in
`scripts/codex_protocol_model.py`; the model-backed operating doc is
`docs/protocol/codex/continuation.md`.

Central invariant: durable shared state beats chat memory. Treat git commits,
committed files, mailbox bodies, `sent/` events, seen cursors, locks, logs,
gate evidence, and operator verification reports as protocol truth.

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

## Start-Session Inhabitance

A fresh Codex session should inhabit the Codex harness as a readiness bridge
unless the user or parent prompt names a live seat or coordinator. Start with
`.venv/bin/python scripts/continuation_readiness.py`, read the model-backed
Codex Harness Model section, and treat `agentNN.toml` files as guardrail
extensions only.

Bridge mode may report durable state and blockers, but it must not consume
cursors, send mailbox events, claim locks, push, spend, edit inventory, or
author production changes.

## Readiness Bridge Checklist

Run the project command:

```bash
.venv/bin/python scripts/continuation_readiness.py
```

Use `--smoke` when the user asks for execution readiness or before making a
verification-environment claim.

For active communication awareness without claiming a seat, run the read-only
mailbox monitor:

```bash
.venv/bin/python scripts/mailbox_monitor.py --once
.venv/bin/python scripts/mailbox_monitor.py --watch --interval 5
```

The monitor reports live unread counts, latest unread event per seat,
coordinator broadcast receipt splits, and heartbeat freshness. It never
consumes cursors, sends mailbox events, or substitutes for live-seat work.

The command is read-only. It reports:

- current HEAD and origin relation
- unread counts for `director`, `director2`, `operator`, `operator2`
- Wave gate state
- ADR-028 ceremony gate state
- environment/smoke status
- Codex harness model artifacts

Do not call `coordination/bin/consume-events` in readiness mode.

## Handoff Draft Checklist

When the user asks for a handoff or a clean-session transfer, the evidence
scaffold can be generated without mutating protocol state:

```bash
.venv/bin/python scripts/draft_handoff.py <seat> --wave 2 --smoke --output
```

This is only a draft. It automates git/mailbox/gate/smoke/lock evidence and a
clean-session prompt, but the current seat still owns the judgment fields and
must refresh live state before finalizing. The command must not be treated as
cursor consumption, a mailbox route, an operator GO, or a coordinator
reconciliation.

## Live Seat Checklist

For a real seat, run:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py <seat> --wave 2
env -u GIT_INDEX_FILE git log --oneline -5
```

Then surface the unread count in the first user-facing response before
processing events. Always read the unread mailbox files before deciding the
seat is idle, routed, blocked, or ready to verify. Cursor consumption is a
separate intentional mutation. If the live seat intentionally consumes mail:

```bash
coordination/bin/consume-events <seat>
```

Consumption mutates and stages the cursor. That is correct only for live-seat
work, never for bridge mode.

Mailbox discipline:

- Do not decide from unread counts alone. Open the relevant unread
  `coordination/mailbox/sent/*.md` files and let the newest binding mail shape
  the seat decision.
- Coordinator is unpinned: read coordinator/all mailbox state, but never run
  `consume-events coordinator`.
- If a live seat consumes mail after `HEAD` advanced, inspect the active
  seat-local staged scope before committing. A stale per-seat index can stage
  bogus deletions for files introduced by newer commits. Refresh that index to
  `HEAD` and re-stage only the intended cursor file before a cursor-only commit
  when there is no other intentional staged work. If there is intentional staged
  work, reconcile the mixed index deliberately and preserve owned paths.
- The expected staged scope for a mailbox-only consume is exactly
  `M coordination/mailbox/seen/<seat>.txt`.

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
- Treat optional `.codex/agents/agentNN.toml` files as self-codified
  guardrail extensions: working, synergistic modules that may add seat-local
  heuristics or situational-awareness loops, but never replace the built-in
  role agents, seat authority, mailbox cursor rules, or user-gated push.
- If `GIT_INDEX_FILE` is set, prefix git and pytest shell commands with
  `env -u GIT_INDEX_FILE` unless the task is explicitly about maintaining the
  active per-seat index.
- Use explicit pathspecs for staging and commits when committing is requested.

## Runtime Env Contract

Codex instances should describe their current part in the whole through this
runtime environment contract. `scripts/codex_protocol_model.py` is the
executable source, and `scripts/continuation_readiness.py` prints the inferred
values.

- `CODEX_AGENT_MODE`: `readiness-bridge`, `live-seat`, `coordinator`, or
  `subagent`. If unset, Codex defaults to readiness bridge unless `CODEX_SEAT`
  names a live protocol role.
- `CODEX_AGENT_ROLE`: the inhabited part, such as `readiness-bridge`,
  `director`, `director2`, `operator`, `operator2`, `coordinator`,
  `lane-v-verifier`, or `money-gate-reviewer`.
- `CODEX_SEAT`: `director`, `director2`, `operator`, or `operator2` for a live
  seat. `CODEX_SEAT=coordinator` is a compatibility spelling for coordinator
  mode; coordinator remains unpinned and no coordinator cursor is consumed.
- `CODEX_CAPABILITY_MODE`: `read-only`, `seat-local`, `capacity-max`, or
  `parent-scoped`.
- `CODEX_MUTATION_SCOPE`: `none`, `seat-owned`, `coordination-only`,
  `read-only-verification`, or `parent-scoped`.
- `CODEX_AUTHORITY_SCOPE`: `report-only`, `seat-owned`,
  `all-scope-reconcile`, or `parent-scoped`.
- `CODEX_MAILBOX_POLICY`: `read-only-no-consume`,
  `seat-read-consume-intentional`, `all-scope-read-no-consume`, or
  `parent-scoped`.
- `CODEX_GIT_POLICY`: `env-u-git-index-read-only`,
  `per-seat-index-for-cursor-status`, `env-u-git-index-or-temp-index`, or
  `env-u-git-index-parent-scoped`.
- `CODEX_VERIFICATION_POLICY`: `report-evidence-only`,
  `request-operator-go`, `independent-go-nits-fail`,
  `reconcile-operator-go-only`, `read-only-review-no-go`, or
  `parent-scoped-no-go`.
- `CODEX_CONTEXT_SOURCES`: `repo-docs-mailbox-gates-readonly`,
  `seat-mailbox-owned-files-gate-evidence`,
  `all-scope-mailbox-inventory-locks-gates`, or
  `parent-prompt-plus-allowed-artifacts`.
- `CODEX_OUTPUT_CONTRACT`: `readiness-report-and-blockers`,
  `seat-artifact-or-operator-request`, `capacity-board-or-single-route`, or
  `bounded-findings-to-parent`.
- `CODEX_DECISION_BOUNDARY`: `no-seat-authority`, `lane-owned-seat`,
  `all-scope-routing-no-production-fixes`, or
  `parent-scoped-no-seat-authority`.
- `CODEX_NEXT_ACTION_POLICY`: `report-then-stop-or-request-role`,
  `read-mail-then-act-or-report-idle`, `build-board-reconcile-once`, or
  `return-evidence-then-stop`.
- `CODEX_SIDE_EFFECT_POLICY`: `user-consent-required`; push, lock-claim side
  effects, paid API spend, and pod spend remain user-gated outside env.
- `GIT_INDEX_FILE`: per-seat or coordinator-local index path; ordinary
  git/pytest still follows `CODEX_GIT_POLICY`.

Default mappings:

- no env -> `CODEX_AGENT_MODE=readiness-bridge`,
  `CODEX_AGENT_ROLE=readiness-bridge`, `CODEX_CAPABILITY_MODE=read-only`,
  `CODEX_MUTATION_SCOPE=none`, `CODEX_AUTHORITY_SCOPE=report-only`,
  `CODEX_MAILBOX_POLICY=read-only-no-consume`,
  `CODEX_GIT_POLICY=env-u-git-index-read-only`,
  `CODEX_VERIFICATION_POLICY=report-evidence-only`,
  `CODEX_CONTEXT_SOURCES=repo-docs-mailbox-gates-readonly`,
  `CODEX_OUTPUT_CONTRACT=readiness-report-and-blockers`,
  `CODEX_DECISION_BOUNDARY=no-seat-authority`,
  `CODEX_NEXT_ACTION_POLICY=report-then-stop-or-request-role`,
  `CODEX_SIDE_EFFECT_POLICY=user-consent-required`
- `CODEX_SEAT=<seat>` -> `CODEX_AGENT_MODE=live-seat`,
  `CODEX_AGENT_ROLE=<seat>`, `CODEX_CAPABILITY_MODE=seat-local`,
  `CODEX_MUTATION_SCOPE=seat-owned`, `CODEX_AUTHORITY_SCOPE=seat-owned`,
  `CODEX_MAILBOX_POLICY=seat-read-consume-intentional`,
  `CODEX_GIT_POLICY=per-seat-index-for-cursor-status`,
  `CODEX_VERIFICATION_POLICY=request-operator-go` for director seats or
  `independent-go-nits-fail` for operator seats,
  `CODEX_CONTEXT_SOURCES=seat-mailbox-owned-files-gate-evidence`,
  `CODEX_OUTPUT_CONTRACT=seat-artifact-or-operator-request`,
  `CODEX_DECISION_BOUNDARY=lane-owned-seat`,
  `CODEX_NEXT_ACTION_POLICY=read-mail-then-act-or-report-idle`,
  `CODEX_SIDE_EFFECT_POLICY=user-consent-required`
- `CODEX_SEAT=coordinator` -> compatibility spelling for coordinator mode:
  `CODEX_AGENT_MODE=coordinator`, `CODEX_AGENT_ROLE=coordinator`,
  `CODEX_CAPABILITY_MODE=capacity-max`,
  `CODEX_MUTATION_SCOPE=coordination-only`,
  `CODEX_AUTHORITY_SCOPE=all-scope-reconcile`,
  `CODEX_MAILBOX_POLICY=all-scope-read-no-consume`,
  `CODEX_GIT_POLICY=env-u-git-index-or-temp-index`,
  `CODEX_VERIFICATION_POLICY=reconcile-operator-go-only`,
  `CODEX_CONTEXT_SOURCES=all-scope-mailbox-inventory-locks-gates`,
  `CODEX_OUTPUT_CONTRACT=capacity-board-or-single-route`,
  `CODEX_DECISION_BOUNDARY=all-scope-routing-no-production-fixes`,
  `CODEX_NEXT_ACTION_POLICY=build-board-reconcile-once`,
  `CODEX_SIDE_EFFECT_POLICY=user-consent-required`
- coordinator -> `CODEX_AGENT_MODE=coordinator`,
  `CODEX_AGENT_ROLE=coordinator`, `CODEX_CAPABILITY_MODE=capacity-max`,
  `CODEX_MUTATION_SCOPE=coordination-only`,
  `CODEX_AUTHORITY_SCOPE=all-scope-reconcile`,
  `CODEX_MAILBOX_POLICY=all-scope-read-no-consume`,
  `CODEX_GIT_POLICY=env-u-git-index-or-temp-index`,
  `CODEX_VERIFICATION_POLICY=reconcile-operator-go-only`,
  `CODEX_CONTEXT_SOURCES=all-scope-mailbox-inventory-locks-gates`,
  `CODEX_OUTPUT_CONTRACT=capacity-board-or-single-route`,
  `CODEX_DECISION_BOUNDARY=all-scope-routing-no-production-fixes`,
  `CODEX_NEXT_ACTION_POLICY=build-board-reconcile-once`,
  `CODEX_SIDE_EFFECT_POLICY=user-consent-required`

Canonical coordinator launch should set `CODEX_AGENT_MODE=coordinator` and
`CODEX_AGENT_ROLE=coordinator` with `CODEX_SEAT` unset. Compatibility launchers
may set `CODEX_SEAT=coordinator` plus `index-codex-coordinator`; the executable
model treats it as coordinator mode, not a consumable live-seat cursor. If a
different stale seat env remains during coordinator mode, the executable model
reports it as ignored.

`CODEX_AGENT_ROLE` can infer `coordinator`, `live-seat`, or `subagent` mode
when `CODEX_AGENT_MODE` is unset, but launchers should still set both for
clarity.

`CODEX_SIDE_EFFECT_POLICY=user-consent-required` is global: env describes the
process part, but never authorizes push, lock-claim side effects, paid API
spend, or pod spend.

## Codex Live-Protocol Rules

- Read live mailbox state before any handoff, routing event, inventory/gate
  claim, or state-asserting protocol write. For coordinator work, use
  `seat_status.py coordinator --wave <N>` plus recent
  `coordination/mailbox/sent/` entries; never consume coordinator mail. For
  live seats, read unread mail by default; consume cursors only when
  intentionally advancing live-seat state.
- Refresh live state again before finalizing a handoff or commit when other
  seats are active. Mailbox counts and HEADs can change while a handoff is being
  written.
- Cross-seat coordinator routing should be one consolidated
  `coordinator-to-all` event unless a direct route is explicitly required. Name
  each seat's task, unread/cursor context, lock/push/spend status, allowed write
  set, and expected output.
- After sending a consolidated task-board event, verify receipt with
  `seat_status.py <seat> --wave <N>` for each live seat. Receipt evidence only
  proves mailbox/cursor state; it does not prove assigned work is complete.
- If the shared index is dirty but a coordinator-only docs/mailbox/log commit
  is needed, use a scoped temporary index:
  `env -u GIT_INDEX_FILE GIT_INDEX_FILE=<temp-index> git ...`. Inspect staged
  scope under that index before committing. If the committed path later appears
  as a stale `D/??` pair in the shared index, refresh only that path.
- When push, pod spend, paid API spend, or lock-claim side effects are not
  user-authorized, route eligible no-lock work first or stop for authorization.
- A bare `handoff` request means a narrow state-transfer artifact from live
  evidence, not new implementation, verification, inventory churn, or mailbox
  noise.
- When a full coordinator/live-seat cycle reaches a real completion boundary
  and the assigned tasks are complete, the last active Codex seat or coordinator
  writes a durable handoff before transplant or context switch. Refresh live
  git/mailbox/gate/smoke state, record what was consumed or routed, preserve
  dirty-tree caveats, and name the exact next trigger.
- When a protocol observation would improve capacity, efficacy, or efficiency,
  preserve it as durable memory if the user has authorized memory updates; if it
  is broadly reusable, codify it in the relevant protocol docs/rules log with
  evidence.

## Capacity-Max Default Cycle

When the user explicitly enters a live seat, asks a coordinator to continue, or
asks Codex to advance a cycle, use the capacity-max workflow by default unless
the user asks for a narrower single-seat/read-only pass.

1. The parent/coordinator captures the shared baseline:
   `seat_status.py coordinator --wave 2`, `env -u GIT_INDEX_FILE git log --oneline -5`,
   `scripts/wave_gate_check.py 2`, and `scripts/ci_smoke.py`.
2. Build a capacity board from mailbox deltas, inventory rows, active locks,
   gate output, and landed-but-unverified diffs. Assign each seat one of:
   implementation/briefing, co-sign/product-oracle review, Lane V verification,
   routing-only, or idle/no-op. Read the relevant mailbox bodies, not only the
   unread counts, before assigning work.
3. Orient `director`, `director2`, `operator`, and `operator2` with
   `.agents/skills/four-seat-protocol/scripts/seat_status.py <seat> --wave 2`;
   surface each unread count before mailbox processing, then read live-seat
   mail. Consume cursors only when intentionally advancing live-seat state.
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
8. If the cycle reached a real completion boundary and assigned tasks are
   complete, the last active seat or coordinator writes the durable handoff
   before transplant/context switch. It refreshes live state, records what was
   consumed or routed, preserves dirty-tree caveats, and names the exact next
   trigger.

This default does not apply to readiness bridge mode. A bridge reports state
and stops. If a candidate row requires `coordination/bin/claim-lock`, remember
that the helper fetches and pushes; push is user-gated, so choose eligible
no-lock work or stop for authorization when push has not been granted.

## Rotating Planning Relay

Use the **Rotating Planning Relay** when an important cross-seat plan needs
all-seat review before work is distributed. The fixed cyclic order is
`director -> operator -> director2 -> operator2`. The starter is step 1; the
baton follows that order, wrapping after `operator2` back to
`director`, until exactly four live-seat turns have occurred. The final live
seat sends the result to coordinator/all-scope for reconciliation.

coordinator-started plan case: `coordinator -> all four seats -> coordinator`.
The coordinator fans out the planning question to all seats, reads responses
back from all seats, and then distributes one consolidated `coordinator-to-all`
task board.

Relay mailbox events are planning evidence only. No production work,
verification verdict, lock, push, or inventory change is implied unless a later
coordinator task board explicitly routes that action.

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

## Coordinator Broadcast Receipt

After a coordinator sends a consolidated `coordinator-to-all` routing notice,
do not assume every seat has consumed or acted on it. A follow-up coordinator
check should:

1. Read the latest coordinator/all mailbox event.
2. Re-run `seat_status.py <seat> --wave 2` for all four live seats.
3. Compare each seat cursor and unread set against the latest coordinator
   broadcast.
4. Report any receipt split explicitly. Receipt evidence proves only that mail
   landed or remains unread; it does not prove assigned work is complete.

If the latest coordinator reconciliation covers the newest evidence, no locks
need action, and the gate remains red for already-recorded blockers, use the
no-op fast path instead of sending another mailbox event.

## Protocol Learning

When a live protocol observation would improve future capacity, efficacy, or
efficiency, preserve it as durable memory if the user has authorized memory
updates. If the observation is broadly reusable, codify it in the relevant
protocol docs or skill instructions with current evidence and provenance. Prefer
reusable lessons over transient snapshots such as exact unread counts or
time-specific blockers.

## Codex Launch Pattern

For CLI-based live seats, launch Codex from the shared working tree with a seat
marker and per-seat index:

```bash
cd /Users/hyungkoookkim/Content
export CODEX_AGENT_MODE=live-seat
export CODEX_SEAT=<director|director2|operator|operator2>
export CODEX_AGENT_ROLE="$CODEX_SEAT"
export CODEX_CAPABILITY_MODE=seat-local
export CODEX_MUTATION_SCOPE=seat-owned
export CODEX_AUTHORITY_SCOPE=seat-owned
export CODEX_MAILBOX_POLICY=seat-read-consume-intentional
export CODEX_GIT_POLICY=per-seat-index-for-cursor-status
export CODEX_SIDE_EFFECT_POLICY=user-consent-required
export CODEX_CONTEXT_SOURCES=seat-mailbox-owned-files-gate-evidence
export CODEX_OUTPUT_CONTRACT=seat-artifact-or-operator-request
export CODEX_DECISION_BOUNDARY=lane-owned-seat
export CODEX_NEXT_ACTION_POLICY=read-mail-then-act-or-report-idle
case "$CODEX_SEAT" in
  director|director2) export CODEX_VERIFICATION_POLICY=request-operator-go ;;
  operator|operator2) export CODEX_VERIFICATION_POLICY=independent-go-nits-fail ;;
esac
CODEX_GIT_DIR="$(env -u GIT_INDEX_FILE git rev-parse --absolute-git-dir)"
export GIT_INDEX_FILE="$CODEX_GIT_DIR/index-codex-$CODEX_SEAT"
[ -f "$GIT_INDEX_FILE" ] || env -u GIT_INDEX_FILE git read-tree --index-output="$GIT_INDEX_FILE" HEAD
codex
```

For canonical coordinator launch, leave `CODEX_SEAT` unset and name the
coordinator part explicitly:

```bash
cd /Users/hyungkoookkim/Content
unset CODEX_SEAT GIT_INDEX_FILE
export CODEX_AGENT_MODE=coordinator
export CODEX_AGENT_ROLE=coordinator
export CODEX_CAPABILITY_MODE=capacity-max
export CODEX_MUTATION_SCOPE=coordination-only
export CODEX_AUTHORITY_SCOPE=all-scope-reconcile
export CODEX_MAILBOX_POLICY=all-scope-read-no-consume
export CODEX_GIT_POLICY=env-u-git-index-or-temp-index
export CODEX_VERIFICATION_POLICY=reconcile-operator-go-only
export CODEX_CONTEXT_SOURCES=all-scope-mailbox-inventory-locks-gates
export CODEX_OUTPUT_CONTRACT=capacity-board-or-single-route
export CODEX_DECISION_BOUNDARY=all-scope-routing-no-production-fixes
export CODEX_NEXT_ACTION_POLICY=build-board-reconcile-once
export CODEX_SIDE_EFFECT_POLICY=user-consent-required
codex
```

Compatibility launchers may use `CODEX_SEAT=coordinator` plus a
coordinator-local index; this infers the same coordinator contract while still
forbidding coordinator cursor consumption:

```bash
cd /Users/hyungkoookkim/Content
export CODEX_SEAT=coordinator
CODEX_GIT_DIR="$(env -u GIT_INDEX_FILE git rev-parse --absolute-git-dir)"
export GIT_INDEX_FILE="$CODEX_GIT_DIR/index-codex-coordinator"
[ -f "$GIT_INDEX_FILE" ] || env -u GIT_INDEX_FILE git read-tree --index-output="$GIT_INDEX_FILE" HEAD
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
- `scripts/draft_handoff.py` is a review scaffold, not live truth; rerun
  `seat_status.py` and read mailbox bodies before acting from it.
- For state-asserting docs or commits, run
  `env -u GIT_INDEX_FILE git log --oneline -5` immediately before writing and
  again immediately before commit.

## Related Files

- Codex continuation doc: `docs/protocol/codex/continuation.md`
- Codex harness model: `scripts/codex_protocol_model.py`
- Readiness report: `scripts/continuation_readiness.py`
- Handoff draft: `scripts/draft_handoff.py`
- Seat status: `.agents/skills/four-seat-protocol/scripts/seat_status.py`
- Coordination rules: `coordination/README.md`
- Agent-neutral protocol: `docs/protocol/agents/`
