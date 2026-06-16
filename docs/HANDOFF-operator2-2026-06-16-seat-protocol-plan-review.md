# HANDOFF - operator2 - SEAT_PROTOCOL final-plan review

READ FIRST AS `coordinator` or `operator2`. Trust current git, mailbox bodies,
and committed protocol files over this planning response if they diverge.

## State At Review

Timestamp: `2026-06-16T05:07:14Z`.

This is an `operator2` planning response to
`coordination/mailbox/sent/2026-06-16T05-04-09Z-coordinator-to-all-coordination.md`.
It is not a production implementation, Lane V verification verdict, lock
claim, push, paid API/pod spend, or inventory transition.

Live evidence:

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2
HEAD: 0d578571 coord(relay): route seat protocol plan review
Origin relation: 5 ahead, 0 behind
operator2 unread before consume: 2
Unread files:
- 2026-06-16T04-19-21Z-coordinator-to-all-coordination.md
- 2026-06-16T05-04-09Z-coordinator-to-all-coordination.md
Wave 2 gate: MET counts={'verified': 30}; selector tail: 71 passed

$ env -u GIT_INDEX_FILE git log --oneline -5
0d578571 coord(relay): route seat protocol plan review
30fcb944 coord(protocol): add active mailbox monitor
326980d0 coord(protocol): guard live-seat handoff boundary
afdc2bb4 coord(status): operator relay ack
d6857582 coord(status): operator2 relay ack

$ GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-operator2 coordination/bin/consume-events operator2 --to 2026-06-16T05:04:09Z
cursor operator2: 2026-06-16T03:57:57Z -> 2026-06-16T05:04:09Z; unread now: 0

$ GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-operator2 git diff --cached --name-status
M	coordination/mailbox/seen/operator2.txt
```

Read inputs:

- `SEAT_PROTOCOL.md` untracked proposal.
- `scripts/codex_protocol_model.py`.
- `docs/protocol/codex/continuation.md`, especially Rotating Planning Relay,
  Active Communication Monitor, live-seat env, hooks, and evidence discipline.
- `.codex/hooks.json` and `.codex/hooks/{session-smoke,guard-git-index,update-state}.sh`.
- `scripts/mailbox_monitor.py`.

## Operator2 Plan Verdict

Plan verdict: `NITS`, not `FAIL`.

The proposal has the right direction if the final plan treats it as proposal
input: compact contracts, live proof first, executable guard emphasis,
read-only observability, and machine-checkable done evidence are all useful.
It is not ready to land as a root replacement or deletion/migration vehicle
without the nits below.

## Keep

1. Keep the six-field seat contract, but implement it as a renderer/resolver
   on top of current Codex runtime truth, especially `scripts/codex_protocol_model.py`.
2. Keep the live proof bundle idea, but compose existing evidence first:
   `seat_status.py`, `env -u GIT_INDEX_FILE git log`, mailbox bodies,
   `scripts/wave_gate_check.py`, `scripts/ci_smoke.py`, and receipt-split output.
3. Keep executable guards for staged scope, index hygiene, stale state, push
   authorization, coordinator overreach, cursor misuse, and subagent boundaries.
4. Keep a DONE/blocked summary emitter, provided it fact-fills from git and
   mailbox state after a stale-state refresh rather than relying on prose claims.
5. Keep the observability/watchboard direction; `scripts/mailbox_monitor.py`
   already implements part of this surface and should be extended or reused.

## Required Nits Before Implementation

1. Do not promote `SEAT_PROTOCOL.md` as the canonical root document in place.
   Write a reviewed spec under `docs/superpowers/specs/` or another agreed
   protocol-planning path, then migrate only after source-order and
   no-information-loss evidence exist.
2. Do not delete or archive existing per-seat/protocol notes from this plan
   alone. Current authority remains `AGENTS.md`, `ARCHITECTURE.md`,
   `docs/protocol/agents/`, `docs/protocol/codex/continuation.md`,
   `.agents/skills/`, committed mailbox state, and executable scripts.
3. Preserve the coordinator prohibition exactly: coordinator may route and
   observe but must not edit lane/product code. Any guard must block that as a
   real path rule, not just print advice.
4. Preserve operator independence exactly: operators do not author production
   fixes, do not verify their own work, and do not broaden planning responses
   into Lane V verdicts for nonexistent code.
5. Reject a blanket "all subagents are read-only" rule. Read-only verifier
   subagents stay read-only; explicitly spawned role agents may do bounded
   seat-authorized work when the parent prompt and protocol allow it.
6. Remove model-specific wording such as `GPT-5.5` from canonical repo policy.
   Keep the underlying design principle: compact contracts and executable
   checks reduce reasoning drift.
7. Treat `seat_banner.py`, `proof_bundle.py`, and `done_summary.py` as possible
   thin commands, not parallel sources of truth. They should import or compose
   existing model/status/monitor/handoff scripts where practical.
8. Guard-first tests must prove blocking behavior. A test that only checks a
   phrase appears in documentation is insufficient for G3/G4/G5/G6/G7/G8.

## Future Lane V Acceptance Checks

For a future implementation commit, `operator2` should require at least:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_codex_protocol_model.py \
  tests/unit/test_codex_protocol_artifacts.py \
  tests/unit/test_continuation_readiness.py \
  tests/unit/test_mailbox_monitor.py \
  tests/unit/test_four_seat_coordination.py \
  tests/unit/test_coordination_bin.py \
  tests/unit/test_check_coordination.py -q

env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
.venv/bin/python scripts/mailbox_monitor.py --once
.venv/bin/python scripts/continuation_readiness.py --smoke
```

If the implementation adds new hook/wrapper behavior, also require focused
tests for `.codex/hooks/*` or the shared `.claude/hooks/*` behavior it delegates
to. If it adds a push guard, the acceptance must include a negative test proving
an unauthorized push path exits non-zero. If it adds coordinator or cursor
guards, the acceptance must include negative tests proving out-of-role writes
and unintended cursor consumption are blocked.

Before any commit in that implementation, the implementing seat should show:

```text
env -u GIT_INDEX_FILE git status --short
GIT_INDEX_FILE=<seat-or-temp-index> git diff --cached --name-status
```

Expected future implementation scope should be protocol tooling/docs/tests only
unless a later coordinator task board explicitly authorizes a production lane
change.

## Next Trigger

Coordinator should reconcile after all four seat planning responses land and
then issue one consolidated final implementation plan or task board. No
`operator2` Lane V target exists until a real implementation commit and
verify-request land.

## Pre-Commit Refresh

Before committing this response, `operator2` refreshed live state again:

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2
HEAD: 9336c2ac coord(status): director seat protocol plan review
operator2 cursor: 2026-06-16T05:04:09Z
UNREAD: 4
- 2026-06-16T05-07-44Z-director-to-all-status.md
- 2026-06-16T05-08-16Z-operator2-to-all-status.md
- 2026-06-16T05-08-23Z-operator-to-all-status.md
- 2026-06-16T05-09-14Z-director2-to-all-status.md
Wave 2 gate: MET counts={'verified': 30}; selector tail: 71 passed
```

I read the `director`, `operator`, and `director2` status bodies for
stale-state awareness. They converge with this response: keep the useful
contract/proof/guard shape, but require reviewed spec placement, source-order
preservation, executable negative tests, thin wrappers over current protocol
truth, and no authority broadening before implementation. I did not consume
these newer events in this commit; the next `operator2` turn should surface the
live unread count first and then decide whether to consume.

Verification run for this planning/status commit:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py
ADVISORY unknown_kind mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md
INFO unread director: 3 unread event(s)
INFO unread director2: 4 unread event(s)
INFO unread operator: 1 unread event(s)
INFO unread operator2: 4 unread event(s)

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Push remains user-gated. No push, lock, pod spend, paid API spend, production
code edit, inventory change, or Lane V verdict was performed here.
