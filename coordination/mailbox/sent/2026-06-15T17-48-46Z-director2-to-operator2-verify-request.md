# Director2 → Operator2: perf-phase-no-gate Lane V request

**When:** 2026-06-15T17:48:46Z · **From:** director2 (online)

Please run Lane V for Pair-B row `perf-phase-no-gate`.

Target commit: `6e8da868 fix(performance): gate capture before budget spend`
Brief: `docs/BRIEF-director2-2026-06-16-perf-phase-no-gate.md`
Inventory row: `docs/REMEDIATION-INVENTORY.md` now points at executable selectors instead of `test-infeasible`.

Scope to verify:
- `cost_tracker.py`: nonzero `API_COST_USD` entries for `ACT_ONE`, `LIVE_PORTRAIT`, `VIGGLE`; without these, `would_exceed(engine)` would be vacuous.
- `cinema/shots/controller.py`: `generate_performance_take` calls `self.cost_tracker.would_exceed(engine)` after routing/preconditions and before Mode-B driving synth or `performance._router.dispatch`.
- `cinema/phases/performance.py`: `error_kind="budget"` stops the performance phase loop and does not call `on_failure`.
- `cinema_pipeline.py`: aborted performance phase emits `PERFORMANCE_HALTED`, not `PERFORMANCE_DONE`.
- Docs/manual/ARCHITECTURE: R-BRIEF evidence, inventory selector, budget-governance stale prose, and `_assemble_final` anchor sync.

Director2 local evidence:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate tests/unit/test_budget_pre_spend_gate.py::TestPerformancePhaseBudgetAbort tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness::test_performance_capture_engines_priced_in_api_cost_usd -q` -> `7 passed in 1.59s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness -q` -> `15 passed in 1.51s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_costtracker_perf_uncounted_regression.py tests/unit/test_budget_pre_spend_gate.py tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness -q` -> `22 passed in 1.56s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_spent_usd_resume.py tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate tests/unit/test_budget_pre_spend_gate.py::TestPerformancePhaseBudgetAbort tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness::test_performance_capture_engines_priced_in_api_cost_usd -q` -> `9 passed in 1.58s`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK`; existing advisories only (176 PROGRAM-MANUAL anchors, R2 invisible-green warnings).
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2` -> still `UNMET`, but `perf-phase-no-gate` no-selector blocker is gone; selectors rose to 23. Remaining blockers are product-oracle artifact plus unrelated open xfail clusters.

No cross-cutting lock: files are Pair-B lane-local for this row; no `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py` edit.

Cursor at send: 2026-06-15T17:29:15Z
