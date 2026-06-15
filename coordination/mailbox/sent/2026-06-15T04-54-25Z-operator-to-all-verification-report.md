# Operator → All: Lane V GO - 7bfb44c coherence invalid result guard

**When:** 2026-06-15T04:54:25Z · **From:** operator (online)

Verdict: GO for `coherence-caller-valid-ignored` in `7bfb44c fix(coherence): ignore invalid caller scores`.

Scope verified from executed evidence:
- `cinema/shots/controller.py` now guards invalid coherence results at the `diagnose_clip` caller with `getattr(coh, "valid", True) is False`.
- Invalid results log WARNING, set `coherence_error`, omit `coherence` / `color_drift` score writes, omit score-driven `color_grade` / `regenerate` recommendations, and set `coh = None` before the deep advisory call.
- Valid coherence behavior remains in the `else` path and still writes scores/recommendations when appropriate.
- No unrelated sibling row is folded; analyzer-side `coherence-silent` remains distinct from this caller-side row.

Local operator evidence:
- `env -u GIT_INDEX_FILE git show --stat --oneline 7bfb44c` -> `7bfb44c fix(coherence): ignore invalid caller scores`; touched `cinema/shots/controller.py`, `docs/REMEDIATION-INVENTORY.md`, `tests/unit/test_nan_gate_pairb.py`; 68 insertions, 23 deletions.
- `env -u GIT_INDEX_FILE git diff --name-status 7bfb44c..HEAD -- cinema/shots/controller.py tests/unit/test_nan_gate_pairb.py` -> no production/test drift after `7bfb44c`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate -q` -> `4 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate::test_invalid_coherence_result_is_not_recorded_as_clean_score --runxfail -q` -> `1 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_nan_gate_pairb.py -q` -> `19 passed`.
- `nl -ba cinema/shots/controller.py | sed -n '2240,2325p'` -> invalid branch at lines 2267-2278; valid score/recommendation path at lines 2279-2289; deep call passes `coherence_result=coh` at line 2324.
- `nl -ba tests/unit/test_nan_gate_pairb.py | sed -n '210,320p'` -> invalid-result assertions at lines 227-258 and deep advisory `coherence_result is None` assertion at lines 260-297.

Independent Lane V evidence:
- Verifier Copernicus: GO; focused class `4 passed`; former pin under `--runxfail` `1 passed`; production/test drift check empty; verified invalid branch, valid branch, deep advisory nulling, and sibling row separation.
- Verifier Kuhn: GO; focused class `4 passed`; former pin under `--runxfail` `1 passed`; full module `19 passed`; production/test scope not drifted; NIT only that inventory prose mentions a prior co-sign SHA while behavior/tests verify `7bfb44c` as the actual fix.

Pre-report gate evidence:
- `env -u GIT_INDEX_FILE git log --oneline -5` at report time -> `a9161a9`, `fd0919b`, `2f9e3f0`, `b97b978`, `f306582`.
- `env -u GIT_INDEX_FILE .venv/bin/python .claude/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2 --smoke` -> exit 0; operator `UNREAD: 0`; Wave 2 `UNMET`; counts `{'fixed': 2, 'open': 22, 'verified': 6}`; smoke OK.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> exit 0 OK; ceremony check R1 PASS, R2 WARN, R3 PASS, R4 PASS.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2` -> exit 1; Wave 2 `UNMET`; blockers without executable selectors remain `spent-usd-reset-on-resume` and `perf-phase-no-gate`; 23 open pin failures remain outside this coherence row.
- Smoke initially failed on a stale `ARCHITECTURE.md` doc anchor for `_inject_secondary_faceswap`; operator fixed the one-line anchor `quality_max.py:665 -> quality_max.py:674`, then `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md` -> `All anchors checked — no drift`, and `scripts/ci_smoke.py` returned OK.

NITS: none blocking. Kuhn's inventory-prose SHA clarity note is non-blocking and does not affect behavior or test evidence.
FAIL reasons: none.

Disposition: `coherence-caller-valid-ignored` may move from fixed to verified on operator evidence. Wave 2 remains red.

Cursor at send: 2026-06-15T04:48:58Z
