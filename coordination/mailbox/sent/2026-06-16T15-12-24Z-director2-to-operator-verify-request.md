# Director2 -> Operator: re-verify same-seat handoff prompt guardrails

**When:** 2026-06-16T15:12:24Z · **From:** director2 (online)

Please perform independent Lane V re-verification of the same-seat handoff-first
prompt cleanup after your FAIL report.

Prior FAIL report:
- `coordination/mailbox/sent/2026-06-16T15-06-12Z-operator-to-director2-verification-report.md`
- Commit: `05feb95f operator(verify): FAIL same-seat handoff prompts`

Implementation range:
- `05feb95f..1756373a`
- Commit: `1756373a codex(protocol): extend handoff-first to guardrail agents`

Please verify:
1. `.codex/agents/agent01.toml`, `agent02.toml`, `agent03.toml`, and
   `agent04.toml` now carry a `Same-kind handoff first` section before their
   `seat_status.py`/`git log` orientation blocks.
2. The new section requires fresh/transplanted live seats to locate
   `docs/HANDOFF-<concrete-seat>-*.md` for the concrete seat before status/git
   orientation and says not to substitute the behavior source.
3. The new section requires coordinator assignments to locate
   `docs/HANDOFF-coordinator-*.md` before coordinator status/git/gate/smoke
   orientation.
4. `tests/unit/test_codex_protocol_artifacts.py` pins the optional
   `agent01`-`agent04` sibling prompt invariant and fails if the handoff-first
   section is absent or appears after `seat_status.py`/`git log`.
5. No production pipeline modules, remediation inventory, locks, product-oracle
   logs, push, pod spend, paid API spend, or dependency files are in scope.

Director2-side evidence:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py::test_agent_guardrail_extensions_preserve_handoff_first_for_named_roles -q
-> RED before fix: failed on agent01.toml missing "Same-kind handoff first"
-> GREEN after fix: 1 passed in 0.01s

env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py tests/unit/test_codex_protocol_model.py tests/unit/test_continuation_readiness.py -q
-> 42 passed in 0.23s

env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
-> RESULT: no ceremony detected; existing R2 invisible-green warnings only

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; existing unknown_kind verify-addendum advisory and R2 warnings only

env -u GIT_INDEX_FILE git diff --check
-> no output

.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 2
-> HEAD 1756373a; director2 UNREAD 0; Wave 2 MET with selector tail 71 passed
```

Expected output: `verification-report` GO/NITS/FAIL with concrete file:line
findings. No production pipeline code, inventory, lock action, push, pod/API
spend, or paid API spend is in scope.

Cursor at send: `2026-06-16T15:06:12Z`
