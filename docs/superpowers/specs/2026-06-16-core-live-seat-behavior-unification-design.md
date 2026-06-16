# Core Live-Seat Behavior Unification Design

Date: 2026-06-16
Status: approved design, awaiting implementation plan

## Context

The Content repo currently has four concrete live protocol seats:
`director`, `director2`, `operator`, and `operator2`. These concrete identities
are load-bearing because mailbox cursors, mailbox addressing, seat-local git
indexes, and live status tooling refer to them by name.

Verified context before writing this spec:

```text
$ env -u GIT_INDEX_FILE git status --short --branch
## main...origin/main [ahead 11]

$ env -u GIT_INDEX_FILE git log --oneline -5
9f7f2530 operator(cursor): consume status echo
937bc691 director(cursor): consume status replies
b5b49f35 operator(status): reply to coordinator ping
a22caf4a docs(handoff): harness unification completion
c1ba501d codex(protocol): keep demoted relay out of startup surfaces
```

The core role prompts are already paired by role:

- `.codex/agents/protocol-director.toml` covers explicit `director` and
  `director2` work.
- `.codex/agents/protocol-operator.toml` covers explicit `operator` and
  `operator2` work.
- `scripts/codex_protocol_model.py` is the executable kernel for seat lists,
  runtime env contracts, and protocol surfaces.

The user-approved intent is: keep the behavior of `operator` and `director2`,
remove divergent behavior from `director` and `operator2`, then apply
`director2` behavior to `director` and `operator` behavior to `operator2`.

## Goal

Unify core live-seat behavior so that:

- `director2` is the canonical behavior source for director-seat work.
- `operator` is the canonical behavior source for operator-seat work.
- `director` remains a concrete seat identity but uses the `director2`
  behavior source.
- `operator2` remains a concrete seat identity but uses the `operator`
  behavior source.

This is behavior unification, not identity deletion.

## Non-Goals

- Do not remove `director` or `operator2` from `SEATS`, mailbox tooling, status
  tooling, or the protocol model.
- Do not copy or rewrite mailbox history.
- Do not copy cursor files across seats.
- Do not copy seat-local git indexes across seats.
- Do not change lock ownership history or committed handoff history.
- Do not modify production pipeline behavior.
- Do not reintroduce default capacity-max, no-op, proof-bundle, or planning
  relay ceremony into startup surfaces.

## Design

Add an explicit behavior-source mapping to the protocol kernel:

```python
SEAT_BEHAVIOR_SOURCE = {
    "director": "director2",
    "director2": "director2",
    "operator": "operator",
    "operator2": "operator",
}
```

The concrete seat remains the runtime identity:

- `CODEX_SEAT=director` still reads and may intentionally consume
  `coordination/mailbox/seen/director.txt`.
- `CODEX_SEAT=director` still uses `.git/index-codex-director` for deliberate
  seat cursor/status work.
- `CODEX_SEAT=operator2` still reads and may intentionally consume
  `coordination/mailbox/seen/operator2.txt`.
- `CODEX_SEAT=operator2` still uses `.git/index-codex-operator2` for deliberate
  seat cursor/status work.

The behavior source controls the role contract text, prompts, and expectations:

- `director` and `director2` share the same director behavior source:
  mailbox-first orientation, director-owned briefs/fixes/co-signs,
  verify-request handoff, no self-issued operator GO, and operator GO required
  where the protocol demands it.
- `operator` and `operator2` share the same operator behavior source:
  independent Lane V verification, GO/NITS/FAIL reporting, cursor/report/docs
  write scope by default, and no production fixes unless the user explicitly
  overrides.

## Affected Surfaces

Implementation should touch only protocol/harness surfaces:

- `scripts/codex_protocol_model.py`: define the behavior-source mapping and
  expose helper/rendered text that names both concrete identity and behavior
  source.
- `tests/unit/test_codex_protocol_model.py`: pin the mapping and ensure runtime
  env contracts keep concrete seat identity while reporting canonical behavior.
- `.codex/agents/protocol-director.toml`: describe director seats as using the
  canonical `director2` behavior contract while preserving concrete seat
  identity.
- `.codex/agents/protocol-operator.toml`: describe operator seats as using the
  canonical `operator` behavior contract while preserving concrete seat
  identity.
- `tests/unit/test_codex_protocol_artifacts.py`: pin the role-prompt language.
- `docs/protocol/codex/continuation.md`: document identity preservation plus
  behavior-source unification.
- `.agents/skills/four-seat-protocol/SKILL.md`: mirror the operational rule for
  Codex live seats.

Optional documentation updates may include `AGENTS.md` only if the root process
layer would otherwise remain ambiguous.

## Error Handling And Safety

If a caller asks for an unknown seat, the protocol model should retain the
current unknown-seat behavior and not infer a behavior source.

If a concrete seat and behavior source differ, all mailbox, cursor, git-index,
heartbeat, and event-addressing operations must use the concrete seat, not the
source seat.

If a future doc or prompt says to copy a seat, the implementation should clarify
that copying means behavior contract reuse only. Durable state remains
seat-local.

## Testing

Focused tests should prove:

- `director` maps to behavior source `director2`.
- `director2` maps to behavior source `director2`.
- `operator` maps to behavior source `operator`.
- `operator2` maps to behavior source `operator`.
- `render_runtime_env_contract({"CODEX_SEAT": "director", ...})` keeps
  `CODEX_AGENT_ROLE=director`, `CODEX_SEAT=director`, and the director index
  path while naming `director2` as the behavior source.
- `render_runtime_env_contract({"CODEX_SEAT": "operator2", ...})` keeps
  `CODEX_AGENT_ROLE=operator2`, `CODEX_SEAT=operator2`, and the operator2 index
  path while naming `operator` as the behavior source.
- The role prompt artifact tests require the new canonical behavior language.
- Default startup/readiness surfaces still omit demoted ceremony terms.

Verification commands for the implementation plan:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
```

## Acceptance Criteria

- The four concrete live seats remain present and addressable.
- The protocol model exposes a single canonical behavior source for each live
  seat.
- `director` no longer has divergent director behavior from `director2`.
- `operator2` no longer has divergent operator behavior from `operator`.
- Concrete seat identity remains visible in runtime contract output and live
  commands.
- No mailbox cursor, lock, git-index, or production-pipeline state is copied
  across seats.
- Tests and docs make the identity-vs-behavior distinction hard to miss.
