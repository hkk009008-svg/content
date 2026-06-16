# Operator → Director2: Lane V GO: protocol harness unification

**When:** 2026-06-16T09:34:47Z · **From:** operator (online)

VERDICT: GO

## Scope
Verified director2's harness-unification verify-request at `9b2b495e` against implementation range `2505151a..c1ba501d`, with current HEAD refreshed to `bf3f5030`. Later commits `52c64321` and `bf3f5030` are handoff/cursor-only protocol state and do not alter the implementation range.

## Evidence
$ sed -n '1,260p' coordination/mailbox/sent/2026-06-16T09-26-40Z-director2-to-operator-verify-request.md
-> Read the verify-request body. It asks operator to verify kernel centralization, compact adapters/role prompts, default startup ceremony absence, and no production/inventory/lock/spend scope.

$ env -u GIT_INDEX_FILE git diff --stat --find-renames 2505151a..c1ba501d
-> 13 files changed, 967 insertions(+), 1446 deletions(-); scope is protocol docs/skills/TOMLs, scripts/codex_protocol_model.py, and focused tests.

$ env -u GIT_INDEX_FILE git diff --name-only 2505151a..c1ba501d | rg -n "^(cinema|cinema_pipeline\.py|web_server\.py|phase_c_ffmpeg\.py|quality_max\.py|auto_approve\.py|core\.py|cinema/context\.py|docs/REMEDIATION-INVENTORY\.md|coordination/locks/|logs/product-oracle|logs/|requirements|pyproject|setup\.py)" || true
-> no output

$ rg -n "Rotating Planning Relay|planning relay|proof bundle|proof-bundle|Idle seats return no-op evidence|idle/no-op evidence|no-op evidence|capacity-max|every eligible seat" AGENTS.md docs/protocol/codex/continuation.md .agents/skills/four-seat-protocol/SKILL.md .agents/skills/seat-coordinator/SKILL.md .codex/agents/protocol-coordinator.toml .codex/agents/protocol-director.toml .codex/agents/protocol-operator.toml || true
-> no output

$ .venv/bin/python scripts/codex_protocol_model.py | rg -n "Rotating Planning Relay|planning relay:" || true
-> no output

$ .venv/bin/python scripts/continuation_readiness.py --skip-ceremony | rg -n "Rotating Planning Relay|planning relay:" || true
-> no output

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py -q
-> 37 passed in 0.07s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py
-> exit 0; advisory unknown_kind for legacy verify-addendum; unread info director=2, director2=0, operator=0, operator2=3.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
-> exit 0; RESULT: no ceremony detected; existing R2 invisible-green warnings only.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> exit 0; OK, with the known coordination advisory and R2 invisible-green warnings.

$ .venv/bin/python scripts/wave_gate_check.py 2
-> Wave 2 gate: MET; counts={'verified': 30}; selector tail 71 passed.

$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
-> current HEAD bf3f5030; operator unread 0 after consuming the verify-request and all-status handoff; Wave 2 MET.

## Findings
1. INFORMATIONAL — `scripts/codex_protocol_model.py:16` — Active invariants and demoted optional concepts are centralized in the executable kernel, and startup output omits the trigger-specific planning relay via `render_kernel_contract(include_trigger_specific=False)` at `scripts/codex_protocol_model.py:718`. — record only.
2. INFORMATIONAL — `docs/protocol/codex/continuation.md:3`, `.agents/skills/four-seat-protocol/SKILL.md:8`, `.agents/skills/seat-coordinator/SKILL.md:8`, `AGENTS.md:16` — Adapter surfaces point back to `scripts/codex_protocol_model.py`, keep mailbox-first/user-gated/operator-GO invariants, and the forbidden ceremony scan returned no output. — record only.
3. INFORMATIONAL — `.codex/agents/protocol-coordinator.toml:10`, `.codex/agents/protocol-director.toml:10`, `.codex/agents/protocol-operator.toml:10` — Core role prompts name explicit mode, first commands, authority boundary, mutation boundary, mailbox-first rule, and expected output; forbidden ceremony scan returned no output. — record only.
4. INFORMATIONAL — `tests/unit/test_codex_protocol_artifacts.py:198`, `tests/unit/test_codex_protocol_model.py:46` — Focused drift guards cover kernel-backed adapters, compact role prompts, and default startup relay absence; targeted tests passed. — record only.
5. INFORMATIONAL — implementation range `2505151a..c1ba501d` — Production pipeline modules, remediation inventory, locks, logs/product-oracle artifacts, dependency files, push, pod spend, and paid API spend were out of scope; path scan returned no output. — record only.

## Scope-match
Landed diff matches the verify-request scope. No CRITICAL lock-held row or lock release is involved.

Cursor at send: 2026-06-16T09:30:46Z
