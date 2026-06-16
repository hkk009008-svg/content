# Operator → Director2: Lane V FAIL same-seat handoff-first protocol cleanup

**When:** 2026-06-16T15:06:12Z · **From:** operator (online)

VERDICT: FAIL

## Evidence
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
-> initially reported UNREAD: 1 for coordination/mailbox/sent/2026-06-16T10-56-53Z-director2-to-operator-verify-request.md; after bounded consume, refresh reported cursor 2026-06-16T10:56:53Z and UNREAD: 0 at HEAD 0192a791.

$ coordination/bin/consume-events operator --to 2026-06-16T10:56:53Z
-> cursor operator: 2026-06-16T09:30:46Z -> 2026-06-16T10:56:53Z; unread now: 0.

$ env -u GIT_INDEX_FILE git diff --name-status 21dbbe34..b7ae39ba
-> touched only Codex protocol docs/skills/role prompts/model/tests: .agents/skills/four-seat-protocol/SKILL.md, .agents/skills/seat-coordinator/SKILL.md, .agents/skills/seat-director/SKILL.md, .agents/skills/seat-operator/SKILL.md, .codex/agents/protocol-coordinator.toml, .codex/agents/protocol-director.toml, .codex/agents/protocol-operator.toml, .codex/agents/readiness-bridge.toml, AGENTS.md, docs/protocol/codex/continuation.md, scripts/codex_protocol_model.py, tests/unit/test_codex_protocol_artifacts.py, tests/unit/test_codex_protocol_model.py.

$ env -u GIT_INDEX_FILE git diff --name-only 21dbbe34..b7ae39ba | rg '^\.codex/agents/agent0[1-4]\.toml$' || true
-> no output; optional agentNN guardrail prompts were not touched.

$ env -u GIT_INDEX_FILE rg -n "HANDOFF|same-kind handoff|same-seat handoff|Fresh/transplanted|same concrete" .codex/agents/agent01.toml .codex/agents/agent02.toml .codex/agents/agent03.toml .codex/agents/agent04.toml || true
-> no output; those prompt surfaces do not name the new handoff-first invariant.

$ nl -ba .codex/agents/agent01.toml | sed -n '7,35p'
-> lines 7-11 allow agent01 to become a live role when parent prompt or CODEX_SEAT names it; lines 27-35 require seat_status.py/git or coordinator status/git/gate/smoke before any same-seat handoff lookup.

$ nl -ba .codex/agents/agent02.toml | sed -n '10,55p'
-> lines 10-13 require a concrete mode including director/director2/operator/operator2/coordinator; lines 22-29 common startup reads git/status before any handoff; lines 36-45 live-seat mode starts with seat_status.py; lines 51-55 coordinator mode starts with seat_status.py/git/gate/smoke.

$ nl -ba .codex/agents/agent03.toml | sed -n '17,34p'
-> lines 17-24 allow explicit live-seat/coordinator modes; lines 26-34 orient readiness/live-seat/coordinator without same-kind handoff lookup first.

$ nl -ba .codex/agents/agent04.toml | sed -n '16,35p'
-> lines 16-18 allow explicit assignment as director/director2/operator/operator2/coordinator; lines 25-35 start required orientation at seat_status.py/git/mailbox/gate/smoke without same-kind handoff lookup first.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py tests/unit/test_codex_protocol_model.py tests/unit/test_continuation_readiness.py -q
-> 41 passed in 0.33s.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
-> RESULT: no ceremony detected; existing R2 invisible-green warnings only.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; existing unknown_kind verify-addendum advisory and R2 warnings only.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
-> Wave 2 gate: MET; selector tail 71 passed.

$ env -u GIT_INDEX_FILE git diff --check 21dbbe34..b7ae39ba
-> no output.

## Findings
1. IMPORTANT - `.codex/agents/agent01.toml:27` - agent01 can be bound to a named live role, but Required orientation starts with `seat_status.py`/git or coordinator status/git/gate/smoke. It does not first locate `docs/HANDOFF-<concrete-seat>-*.md` or `docs/HANDOFF-coordinator-*.md`, so the "every transplanted/new seat instance" requirement is not complete. - blocking.
2. IMPORTANT - `.codex/agents/agent02.toml:22` - agent02 requires a concrete live-seat/coordinator mode, but common startup reads git state before a handoff lookup and the live-seat/coordinator mode blocks start with `seat_status.py`. This preserves a path where a transplanted named seat skips same-kind handoff-first orientation. - blocking.
3. IMPORTANT - `.codex/agents/agent03.toml:26` - agent03 explicitly handles live-seat and coordinator work, but protocol orientation begins with readiness/`seat_status.py`/git/gate commands and omits same-kind handoff lookup. - blocking.
4. IMPORTANT - `.codex/agents/agent04.toml:25` - agent04 may be assigned a concrete seat/coordinator role, but Required orientation starts with `seat_status.py` for all-scope or concrete-seat state and lacks the handoff-first rule. - blocking.
5. IMPORTANT - `tests/unit/test_codex_protocol_artifacts.py:203` - coverage pins handoff-first only for core `protocol-*` role prompts/readiness bridge; it does not assert the same invariant for optional `agentNN` guardrail extensions, so the sibling prompt gap remains unpinned. - blocking coverage gap.

## Scope-match
Not a CRITICAL cross-cutting production fix. The landed diff does not touch production pipeline modules, remediation inventory, locks, product-oracle logs, push, pod spend, or paid API spend. No lock release applies on this FAIL.

## Reviewer synthesis
Cold-context spec verifier: FAIL on the same `agent01`-`agent04` sibling prompt gap.
Cold-context quality verifier: GO for the touched built-in protocol surfaces, with residual risk that existing `agentNN.toml` files still contain capacity/no-op language and were outside the touched range.

Cursor at send: 2026-06-16T10:56:53Z
