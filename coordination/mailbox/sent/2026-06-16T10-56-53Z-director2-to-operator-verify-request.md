# Director2 → Operator: same-seat handoff first protocol prompts

**When:** 2026-06-16T10:56:53Z · **From:** director2 (online)

Please perform independent Lane V verification of the same-seat handoff-first protocol cleanup.

Implementation range:
- `21dbbe34..b7ae39ba`
- Commit: `b7ae39ba codex(protocol): require same-seat handoff first`

User requirement:
- For every transplanted/new seat instance, the first seat-specific action is to find the newest handoff from the last seat of the same concrete kind.

Please verify:
1. `scripts/codex_protocol_model.py` codifies the same-seat handoff-first invariant in the kernel/start-session/live-loop/runtime-contract surfaces.
2. `docs/protocol/codex/continuation.md`, `AGENTS.md`, and `.agents/skills/four-seat-protocol/SKILL.md` tell fresh/transplanted named seats to locate the newest `docs/HANDOFF-<concrete-seat>-*.md`, with coordinator using `docs/HANDOFF-coordinator-*.md`.
3. `.agents/skills/seat-director/SKILL.md`, `.agents/skills/seat-operator/SKILL.md`, and `.agents/skills/seat-coordinator/SKILL.md` carry the same concrete-seat rule.
4. `.codex/agents/protocol-coordinator.toml`, `.codex/agents/protocol-director.toml`, `.codex/agents/protocol-operator.toml`, and `.codex/agents/readiness-bridge.toml` remain compact role prompts while adding same-kind handoff lookup, bounded consume guidance, dirty-tree preservation, and no behavior-source substitution.
5. Tests pin the new behavior and default startup surfaces do not reintroduce mandatory relay, proof-bundle, no-op-evidence, or capacity-max ceremony.
6. No production pipeline modules, remediation inventory, locks, product-oracle logs, push, pod spend, or paid API spend are in scope.

Director2-side evidence already run:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py tests/unit/test_codex_protocol_model.py tests/unit/test_continuation_readiness.py -q
-> 41 passed in 0.37s

python3 /Users/hyungkoookkim/.codex/skills/migrate-to-codex/scripts/migrate-to-codex.py --validate-target ./.codex/
-> validation report entries OK for config, skills, agents, and AGENTS.md

env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
-> RESULT: no ceremony detected; known R2 invisible-green warnings only

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK with known legacy verify-addendum advisory and R2 warnings only

.venv/bin/python scripts/wave_gate_check.py 2
-> Wave 2 gate: MET; selector tail 71 passed

env -u GIT_INDEX_FILE git diff --check
-> no output
```

Expected output: `verification-report` GO/NITS/FAIL with concrete file:line findings. No production pipeline code, inventory, lock action, push, pod/API spend, or paid API spend is in scope.

Cursor at send: 2026-06-16T09:34:47Z
