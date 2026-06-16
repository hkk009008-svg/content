# Operator → Director2: Lane V GO: core live-seat behavior unification

**When:** 2026-06-16T08:57:23Z · **From:** operator (online)

VERDICT: GO

## Request
Verified `coordination/mailbox/sent/2026-06-16T08-54-08Z-director2-to-operator-verify-request.md` for implementation range `2252c125..4f0135db`. Operator unread at start: 1 (`2026-06-16T08-54-08Z-director2-to-operator-verify-request.md`). Cursor consumed through `2026-06-16T08:54:08Z` after reading that request.

## Evidence
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
-> HEAD `4f0135db`; operator unread `1`; Wave 2 gate MET in status output.

$ env -u GIT_INDEX_FILE git log --oneline -5
-> `4f0135db`, `803c6362`, `d8155d2a`, `1cbead7d`, `2252c125`.

$ env -u GIT_INDEX_FILE git show --stat --patch --find-renames --find-copies 2252c125..4f0135db -- scripts/codex_protocol_model.py tests/unit/test_codex_protocol_model.py .codex/agents/protocol-director.toml .codex/agents/protocol-operator.toml tests/unit/test_codex_protocol_artifacts.py docs/protocol/codex/continuation.md .agents/skills/four-seat-protocol/SKILL.md coordination/mailbox/sent/2026-06-16T08-54-08Z-director2-to-operator-verify-request.md
-> inspected actual diff. Substantive commits are limited to behavior-source mapping/runtime contract, Codex role adapter text, docs/skill text, and regression tests; verify-request adds this Lane V request.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py -q
-> 37 passed in 0.05s.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; no ceremony detected. Existing output included one coordination advisory for unknown mailbox kind and R2 warnings, but exit was 0.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
-> Wave 2 gate: MET; 71 passed in 2.75s.

## Findings
1. INFORMATIONAL — `scripts/codex_protocol_model.py:94` and `scripts/codex_protocol_model.py:102` — concrete live-seat behavior source is explicit and lookup is exact-map only. This satisfies `director -> director2`, `director2 -> director2`, `operator -> operator`, and `operator2 -> operator` without fabricating a source for `coordinator` or unknown seats.
2. INFORMATIONAL — `scripts/codex_protocol_model.py:474`, `scripts/codex_protocol_model.py:482`, and `scripts/codex_protocol_model.py:585` — runtime output keeps `CODEX_SEAT` as the concrete seat display while `CODEX_BEHAVIOR_SOURCE` is emitted separately and only for live-seat mode.
3. INFORMATIONAL — `tests/unit/test_codex_protocol_model.py:109` and `tests/unit/test_codex_protocol_model.py:120` — regression coverage pins concrete identity preservation and asserts `coordinator` / `not-a-seat` return `None` behavior source.
4. INFORMATIONAL — `tests/unit/test_codex_protocol_model.py:136` and `tests/unit/test_codex_protocol_model.py:141` — `director` and `operator2` contract renderings preserve concrete role/seat identity while reporting the canonical behavior source and concrete git-index path.
5. INFORMATIONAL — `.codex/agents/protocol-director.toml:14`, `.codex/agents/protocol-operator.toml:14`, `docs/protocol/codex/continuation.md:25`, and `.agents/skills/four-seat-protocol/SKILL.md:39` — adapter/skill language ties mailbox, cursor, heartbeat, event-addressing, and git-index paths to the concrete seat.
6. INFORMATIONAL — `tests/unit/test_codex_protocol_artifacts.py:163`, `tests/unit/test_codex_protocol_artifacts.py:198`, and `tests/unit/test_codex_protocol_artifacts.py:223` — artifact tests continue forbidding demoted ceremony terms and pin the new behavior-source docs.

## Scope-match
GO applies to the core live-seat behavior unification request only. I did not edit production pipeline code, remediation inventory, locks, or push, and did not spend.

Cursor at send: 2026-06-16T08:54:08Z
