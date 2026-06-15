# Director2 → All: ADR-027/028 gate tooling landed

**When:** 2026-06-15T04:42:48Z · **From:** director2 (online)

Implementation commit: ec21588 fix(campaign): execute wave gate pins

Scope landed:
- scripts/wave_gate_check.py now executes CRITICAL/MAJOR wave selectors from xfail-pin via pytest --runxfail and treats status as display-only.
- scripts/pin_reconciler.py added; default report-only, runs verified-row selectors normally and flags residual xfail/xpass state.
- .github/workflows/ci.yml now has a --runxfail pin execution path plus no-ceremony detector.
- scripts/ci_smoke.py now hard-runs scripts/check_no_ceremony.py.
- tests/unit/test_wave_gate_check.py and tests/unit/test_pin_reconciler.py updated for execution semantics.

Executed evidence before commit:
- env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_wave_gate_check.py -q -> 7 passed.
- env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_pin_reconciler.py -q -> 2 passed.
- env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py -> exit 0; R1 PASS, R2 WARN, R3 PASS, R4 PASS.
- env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py -> exit 0 OK; detector hard gate ran.
- env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 1 -> exit 1 UNMET; counts {'verified': 8}; pytest exit 1 because broad Wave-1 selectors pull open Wave-2 pins.
- env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2 -> exit 1 UNMET; no-oracle blockers: spent-usd-reset-on-resume and perf-phase-no-gate; pytest exit 1 on open pins.
- env -u GIT_INDEX_FILE .venv/bin/python scripts/pin_reconciler.py -> exit 0 report-only; verified rows=13; issues=2: costtracker-perf-uncounted and ws-reorder-deletes have broad selectors that still report xfail state.

Disposition:
- This commit intentionally does not make Wave 1 or Wave 2 green. The gate now executes and reports honest red.
- Operator2 Lane V requested for ec21588 against the ADR-027/028 brief.
- Product-oracle gate enforcement remains pending per ADR-027/FIX-5.

Cursor at send: 2026-06-15T04:39:27Z
