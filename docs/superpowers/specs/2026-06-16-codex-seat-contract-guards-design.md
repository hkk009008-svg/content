# Codex Seat Contract Guards Design

*Date: 2026-06-16. Status: relay-reviewed design input for implementation planning.*

## 1. Purpose

This design converts the useful parts of the untracked `SEAT_PROTOCOL.md`
proposal into repo-owned protocol tooling without promoting that proposal as a
new root authority.

The goal is a compact, executable Codex seat contract:

- render the current role, objective, permissions, scope, verification, and done
  evidence before mutation;
- gather a live proof bundle from existing durable sources before decisions;
- enforce the highest-risk protocol failures with tested checks;
- emit a fact-filled done or blocked summary instead of relying on prose.

## 2. Source Order

The implementation must preserve the current source order:

1. user direct instruction;
2. git commits and current filesystem;
3. mailbox events in `coordination/mailbox/sent/`;
4. handoffs and `STATE.md` cache;
5. defaults.

The durable repo authority remains `AGENTS.md`, `ARCHITECTURE.md`,
`docs/protocol/agents/`, `docs/protocol/codex/continuation.md`,
`.agents/skills/`, committed mailbox state, and executable scripts. The root
`SEAT_PROTOCOL.md` file is proposal input only.

## 3. Adopted Concepts

Adopt these concepts from `SEAT_PROTOCOL.md`:

- six-field seat contract: `role`, `objective`, `permissions`, `scope`,
  `verification`, and `done`;
- live proof bundle before protocol decisions;
- tested checks for staged scope, git-index hygiene, stale state, unauthorized
  push, coordinator overreach, cursor misuse, and subagent boundary;
- read-only observability through `scripts/mailbox_monitor.py` and receipt
  split reporting;
- done/blocked summaries that fact-fill from git, mailbox, and command output.

## 4. Rejected Concepts

Do not adopt these parts:

- replacing `AGENTS.md`, existing protocol docs, or per-seat skills;
- deleting or archiving existing notes as part of the first implementation;
- flattening `director`/`director2` or `operator`/`operator2` where mailbox,
  cursor, heartbeat, lane, or verification authority is seat-specific;
- making all subagents globally read-only;
- broadening operator authority into production fixes;
- encoding model-brand policy wording as canonical repo guidance;
- reducing Codex live progress updates to silence.

## 5. Tooling Boundaries

`scripts/codex_protocol_model.py` remains the protocol brain for runtime role
inference, environment contract fields, side-effect policy, planning relay, and
assembly placement.

`scripts/seat_banner.py` will be a thin renderer over
`codex_protocol_model.infer_runtime_env`. It may accept explicit objective,
permission, scope, verification, and done arguments. It must not read mailbox
bodies, consume cursors, stage files, or become a separate authority layer.

`scripts/proof_bundle.py` will compose existing read-only sources:
`seat_status.py`, `git log`, selected mailbox bodies, `scripts/wave_gate_check.py`,
optional `scripts/ci_smoke.py`, and `scripts.mailbox_monitor.collect_monitor_state`.
It must not consume cursors or imply operator GO.

`scripts/protocol_guards.py` will hold reusable checks that hooks and CLIs can
call. The checks must be narrow and testable, and false positives should fail
with actionable output rather than silently modifying state.

`scripts/done_summary.py` will emit done or blocked evidence from durable facts.
Unknown values must be printed as `unknown` or `unverified`; the tool must not
invent proof.

## 6. Guard Expectations

The first implementation must include negative tests for each guard it claims:

| Guard | Bad path to block |
|---|---|
| mode/contract claim | mutating action with missing required contract fields |
| cursor misuse | cursor-only commit stages anything beyond `seen/<seat>.txt` |
| coordinator overreach | coordinator scope includes product or lane code |
| staged scope | staged paths exceed the declared scope |
| index hygiene | ordinary git/pytest runs under a seat-local index |
| stale state | finalization uses proof older than the configured age |
| push authorization | push path lacks explicit user/session authorization |
| subagent boundary | read-only verifier/specialist attempts mutation |

Allowed-path tests are required too, so normal seat work remains possible.

## 7. Verification

Implementation verification should start with focused protocol tests, then:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Run `scripts/wave_gate_check.py 2` only when the change touches wave/gate
surfaces or records a wave-state claim.

## 8. Non-Goals

This design does not implement product pipeline behavior, spend logic, pod
automation, lock claiming, inventory status changes, or Wave 3 media work.
Push remains user-gated.
