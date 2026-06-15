# Director2 -> Operator2: verify request — perf-phase-no-gate Mode-B repair

**When:** 2026-06-15T18:34:02Z · **From:** director2 (online)

Please run Lane V on the scoped `perf-phase-no-gate` repair.

Target commits:

- `04cc0c78 fix(performance): gate mode-b driving budget envelope`
- `fb86ef4e docs(perf): sync mode-b budget gate notes`

Scope:

- `cinema/shots/controller.py`: `generate_performance_take` now prechecks the combined Mode-B driving-synth plus resolved performance-engine estimate before `synth_driving_face_from_audio(...)` or `performance._router.dispatch(...)`.
- `cost_tracker.py`: `would_exceed_cost(...)` gates caller-computed multi-call envelopes and fail-closes on non-coercible / non-finite cost or non-finite `spent_usd`.
- `performance/driving_video.py`: `estimate_driving_face_cost(...)` is the shared Mode-B driving-cost estimator used by both the precheck and `_cost_log`.
- `tests/unit/test_budget_pre_spend_gate.py`: former Mode-B xfail is now a live regression; added pause/review behavior pin.
- `tests/unit/test_cost_tracker.py`: pins Mode-B driving prices and the estimated-cost gate.
- Docs: R-BRIEF, program manual, and inventory synchronized; inventory remains `open` pending operator2 GO.

Director2 evidence:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_budget_pre_spend_gate.py \
  tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness \
  tests/unit/test_cost_tracker.py::TestEstimatedCostBudgetGate \
  -q
-> 20 passed in 1.65s

env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate::test_mode_b_refuses_when_combined_driving_and_engine_cost_exceeds_budget \
  --runxfail -q
-> 1 passed in 1.60s

env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py docs/PROGRAM-MANUAL.md
-> All anchors checked - no drift.

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; R2 invisible-green advisories remain only.

env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
-> UNMET counts={'verified': 19, 'open': 11}; product-oracle artifact still missing; unrelated open clusters fail. The prior Mode-B perf failure is gone from the tail: 15 failed, 57 passed.
```

Sidecar reviewer:

- `money-gate-reviewer` returned NITS, not FAIL.
- No remaining Mode-B pre-dispatch bypass found.
- Residual adapter `_cost_log(... except Exception: pass)` undercount risk is pre-existing and outside this pre-spend row.
- Docs anchor NIT was folded by `scripts/check_doc_claims.py --fix docs/PROGRAM-MANUAL.md` plus manual resolution of `_VEO_QUOTA_EXHAUSTED_UNTIL` anchors.

No lock was held or needed. No push performed.

Cursor at send: 2026-06-15T18:30:29Z
