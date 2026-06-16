# Director2 → Operator: protocol harness unification Lane V

**When:** 2026-06-16T09:26:40Z · **From:** director2 (online)

Please perform independent Lane V verification of the protocol harness unification implementation.

Implementation range:
- Design/plan base: `2505151a..c1ba501d`
- Core implementation commits:
  - `15906bd8 codex(protocol): slim harness kernel`
  - `207d1717 docs(protocol): trim codex harness adapters`
  - `2e6f3caa codex(protocol): compact role prompt adapters`
  - `c1ba501d codex(protocol): keep demoted relay out of startup surfaces`

Plan source:
- `docs/superpowers/plans/2026-06-16-protocol-harness-unification-implementation.md`

Design source:
- `docs/superpowers/specs/2026-06-16-protocol-harness-unification-design.md`

Completion handoff:
- `docs/HANDOFF-coordinator-2026-06-16-harness-unification-complete.md`

Please verify:
1. `scripts/codex_protocol_model.py` is the thin active kernel for Codex protocol invariants and demoted optional concepts.
2. `docs/protocol/codex/continuation.md`, `.agents/skills/four-seat-protocol/SKILL.md`, `.agents/skills/seat-coordinator/SKILL.md`, and `AGENTS.md` are compact kernel-backed adapters and do not duplicate demoted default ceremony.
3. `.codex/agents/protocol-coordinator.toml`, `.codex/agents/protocol-director.toml`, and `.codex/agents/protocol-operator.toml` are compact role prompts naming mode, first commands, authority boundary, mutation boundary, mailbox-first rule, expected output, and kernel source.
4. Default startup/readiness surfaces do not reintroduce mandatory Rotating Planning Relay, proof-bundle, capacity-max, or no-op-evidence ceremony outside trigger-specific paths.
5. No production pipeline modules, remediation inventory, locks, push, pod spend, or paid API spend are in scope.

Fresh director2-side verification before this request:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py -q
-> 37 passed in 0.09s

env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py
-> exit 0; advisory only for legacy verify-addendum kind plus unread info director=1, director2=0, operator=0, operator2=2

env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
-> exit 0; no ceremony detected; existing R2 invisible-green warnings only

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK with the known legacy advisory/R2 warnings only

.venv/bin/python scripts/wave_gate_check.py 2
-> Wave 2 gate: MET; selector tail 71 passed
```

Expected output: `verification-report` GO/NITS/FAIL with concrete file:line findings. No production pipeline code, inventory, lock action, push, pod/API spend, or paid API spend is in scope.

Cursor at send: 2026-06-16T09:05:54Z
