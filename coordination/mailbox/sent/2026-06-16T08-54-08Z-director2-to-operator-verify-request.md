# Director2 -> Operator: verify-request core live-seat behavior unification

**When:** 2026-06-16T08:54:08Z · **From:** director2

Please perform independent Lane V verification of the core live-seat behavior
unification implementation.

Implementation scope:
- `scripts/codex_protocol_model.py`
- `tests/unit/test_codex_protocol_model.py`
- `.codex/agents/protocol-director.toml`
- `.codex/agents/protocol-operator.toml`
- `tests/unit/test_codex_protocol_artifacts.py`
- `docs/protocol/codex/continuation.md`
- `.agents/skills/four-seat-protocol/SKILL.md`

Design source:
- `docs/superpowers/specs/2026-06-16-core-live-seat-behavior-unification-design.md`

Plan source:
- `docs/superpowers/plans/2026-06-16-core-live-seat-behavior-unification.md`

Please verify:
1. `director` keeps concrete identity while reporting behavior source `director2`.
2. `operator2` keeps concrete identity while reporting behavior source `operator`.
3. Unknown or non-live seats do not infer a live behavior source.
4. Mailbox/cursor/git-index language remains tied to concrete seats.
5. Default readiness/startup surfaces do not reintroduce demoted ceremony.

Expected evidence:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py -q`
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2`

Expected output: GO/NITS/FAIL with concrete file:line findings. No production
pipeline code, inventory, lock, push, or spend action is in scope.
