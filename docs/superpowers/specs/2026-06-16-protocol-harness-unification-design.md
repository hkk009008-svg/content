# Protocol Harness Unification Design

## Goal

Eliminate ceremony and theatrical protocol behavior by keeping only proven,
enforceable, or ambiguity-reducing parts of the Codex harness and four-seat
protocol, then unify the remaining behavior into one predictable operating
model.

## Proof Standard

A protocol rule stays in active startup/runtime instructions only if it meets
at least one of these criteria:

1. It has executable enforcement through a script, test, hook, or gate.
2. It has repeated incident evidence showing that it prevented real process
   failure.
3. It is a small operational invariant that directly reduces ambiguity.

Anything else is removed from active instructions, folded into a single
canonical source, or archived as historical context.

## Current Evidence

Verified live repository state before this design:

```text
$ env -u GIT_INDEX_FILE git log --oneline -8
eff19ee8 codex(protocol): require mailbox-first decisions
5900bcc2 operator2(cursor): consume status replies
74776093 director2(status): reply to coordinator state ping
7caa0460 director(status): reply to coordinator state ping
34e1d1c0 operator2(status): report current no-op state
de673b66 codex(protocol): surface cycle handoff in harness
40e438e7 docs(protocol): require cycle handoff before transplant
b2a9b0b1 coord(query): ping seats for current state
```

```text
$ wc -l AGENTS.md docs/protocol/codex/continuation.md .agents/skills/four-seat-protocol/SKILL.md .agents/skills/seat-coordinator/SKILL.md scripts/codex_protocol_model.py .codex/agents/protocol-coordinator.toml .codex/agents/protocol-director.toml .codex/agents/protocol-operator.toml scripts/continuation_readiness.py scripts/mailbox_monitor.py scripts/draft_handoff.py scripts/protocol_effectiveness_report.py scripts/check_no_ceremony.py scripts/check_coordination.py
     313 AGENTS.md
     581 docs/protocol/codex/continuation.md
     521 .agents/skills/four-seat-protocol/SKILL.md
     193 .agents/skills/seat-coordinator/SKILL.md
     628 scripts/codex_protocol_model.py
      67 .codex/agents/protocol-coordinator.toml
      61 .codex/agents/protocol-director.toml
      64 .codex/agents/protocol-operator.toml
     183 scripts/continuation_readiness.py
     325 scripts/mailbox_monitor.py
     353 scripts/draft_handoff.py
     951 scripts/protocol_effectiveness_report.py
     192 scripts/check_no_ceremony.py
     321 scripts/check_coordination.py
    4753 total
```

The current active Codex protocol is spread across root policy, Codex docs,
skills, role prompts, scripts, and tests. The duplication itself is now a risk:
agents can follow one surface while missing a stricter or newer rule elsewhere.

## Selected Approach

Use a thin kernel plus checked adapter surfaces.

The executable kernel is `scripts/codex_protocol_model.py`. It owns the
canonical role model, source order, permission boundaries, side-effect gates,
and required live-loop invariants. Other surfaces become adapters:

- `AGENTS.md`: short repo-root policy and links to the kernel/adapter docs.
- `docs/protocol/codex/continuation.md`: Codex-specific operating manual
  generated from, or checked against, the kernel.
- `.agents/skills/four-seat-protocol/SKILL.md`: runtime checklist, not a
  duplicate manual.
- `.agents/skills/seat-coordinator/SKILL.md`: coordinator-specific checklist,
  focused on inventory/gate/routing authority.
- `.codex/agents/*.toml`: minimal role prompts that name mode, permissions,
  first commands, and expected output.
- Scripts under `scripts/`: executable evidence producers and checkers.

## Core Kernel

The active kernel keeps these proven behaviors:

- Durable state beats chat memory: use git, mailbox bodies, cursors, locks,
  logs, gates, and operator reports before stale prose or chat.
- Mailbox-first decisions: check mail and read relevant bodies before protocol
  decisions or state-asserting writes.
- Explicit mode: readiness bridge, live seat, coordinator, and subagent are
  distinct; never silently upgrade mode.
- Coordinator is unpinned: it reads all-scope mail and never consumes a
  coordinator cursor.
- Ordinary git and pytest commands use `env -u GIT_INDEX_FILE` unless the task
  is deliberately maintaining a seat index.
- Push, lock-claim side effects, paid API spend, and pod spend are user-gated.
- Coordinator does not author production fixes.
- `verified` requires an operator `verification-report` GO plus executed
  evidence; `wave_gate_check.py` is process evidence, not correctness proof.
- Active routing uses one consolidated coordinator event when cross-seat
  awareness is needed.

These stay because they are either executable, repeatedly incident-backed, or
small ambiguity-reducing invariants.

## Demoted Or Removed From Active Runtime

These concepts should not remain as mandatory startup/runtime doctrine unless a
specific trigger requires them:

- Capacity-max cycle: keep as an explicit coordinator tool for active
  multi-seat work. Do not make every status check spawn or simulate all seats.
- No-op evidence: keep only when a seat was actually queried or oriented. Do
  not require idle seats to produce artifacts just to prove idleness.
- Rotating Planning Relay: demote to an optional planning pattern for rare
  cross-seat design choices. It should not appear in default startup paths.
- Protocol-effectiveness report: keep as read-only diagnostics. It should not
  route work, consume mail, edit inventory, or act as a required ceremony.
- Proof-bundle language: replace with concrete evidence names: status, git log,
  mailbox bodies, gate output, smoke output, and diff scope.
- Handoff ceremony: keep narrow handoffs only at real transfer boundaries or
  when explicitly requested.

## Unified Operating Model

Each live Codex agent should be able to answer four questions quickly:

1. What mode am I in?
2. What durable state must I read before acting?
3. What am I allowed to mutate?
4. What evidence proves the work or report?

The kernel should expose these answers as structured data and rendered text.
Adapters should repeat only the minimum necessary command checklist.

## Enforcement

Add or tighten tests so drift becomes visible:

- Kernel tests assert the active invariants appear in rendered live-loop,
  runtime-contract, and start-session text.
- Artifact tests assert role TOMLs and Codex docs refer to the kernel and do
  not carry independent copies of deprecated mandatory workflows.
- Coordination checks keep enforcing anti-theater handoff and verification
  rules.
- Ceremony checks remain focused on executable verification, not on ordinary
  protocol wording.

The tests should forbid reintroducing mandatory ceremony phrases such as
required no-op evidence for all idle seats, mandatory Rotating Planning Relay,
or proof-bundle-as-a-thing, except in historical/archive paths or explicitly
optional sections.

## Migration Shape

Implementation should be incremental and commit in small scopes:

1. Strengthen the executable kernel with the slim invariant set and demotion
   metadata.
2. Update tests to define the allowed active protocol vocabulary.
3. Trim `docs/protocol/codex/continuation.md` into a Codex adapter.
4. Trim `.agents/skills/four-seat-protocol/SKILL.md` and
   `.agents/skills/seat-coordinator/SKILL.md` into checklists.
5. Trim `.codex/agents/protocol-*.toml` into role launch prompts.
6. Update `AGENTS.md` to point at the unified model without duplicating it.
7. Run focused artifact/model tests, then `scripts/ci_smoke.py`.

No production pipeline behavior changes are in scope.

## Acceptance Criteria

- A new Codex agent can identify mode, read requirements, mutation boundary,
  and completion evidence from one kernel-backed path.
- Active startup/runtime instructions are shorter and do not duplicate long
  doctrine across surfaces.
- Proven safety rules remain present and tested.
- Optional or diagnostic tools are clearly labeled optional and trigger-based.
- Existing smoke and focused protocol artifact tests pass.
- No production modules are modified.

## Implementation Decisions

- Adapter docs will be checked against the kernel rather than generated in the
  first pass. This reduces migration risk while still making drift visible.
- Historical protocol docs will be left untouched in the first pass. Tests may
  exclude archive/historical paths instead of rewriting old records.
