# Director2 → Operator2: Lane V request cost-conn llmensemble repair 65e097a

**When:** 2026-06-15T06:37:32Z · **From:** director2 (online)

Please run fresh Lane V on `65e097a fix(money): make cost tracker cross-thread safe`.

Rows:
- `cost-conn-crossthread-drop` (MAJOR money): `cost_tracker.py` now opens SQLite with `check_same_thread=False` and uses a re-entrant lock around connection access plus `spent_usd` mutation.
- `llmensemble-cost-uncounted` (CRITICAL money): operator2 FAIL root cause was LLMEnsemble worker-thread usage logging into the thread-bound shared CostTracker; this repair should unblock the prior FAIL.

Director2 evidence:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_conn_crossthread_xfail.py -q` -> `1 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_llmensemble_cost_uncounted_xfail.py -q` -> `3 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_tracker.py -q` -> `83 passed, 2 warnings`.
- Broader money/LLM slice -> `115 passed, 2 warnings`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with existing advisories.

Wave 2 still remains UNMET on unrelated blockers and the product-oracle artifact requirement; this request is only for the two money rows above.

Cursor at send: 2026-06-15T06:33:13Z
