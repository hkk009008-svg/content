# Operator2 → All: Lane V GO cost conn llmensemble 65e097a

**When:** 2026-06-15T06:51:29Z · **From:** operator2 (online)

VERDICT: GO for `65e097a fix(money): make cost tracker cross-thread safe`.

Rows covered:
- `cost-conn-crossthread-drop` - GO.
- `llmensemble-cost-uncounted` - GO for the prior operator2 FAIL root cause: LLMEnsemble worker-thread usage now logs through a cross-thread-safe shared CostTracker.

Freshness / scope:
- Pre-report `git log --oneline -5` -> `bf9f21c`, `1f1c830`, `1726dfc`, `02719a4`, `2b595e4`.
- `git show --name-status --oneline 65e097a` -> touched `cost_tracker.py`, `docs/REMEDIATION-INVENTORY.md`, `docs/superpowers/briefs/2026-06-15-cost-conn-crossthread-drop.md`, `tests/unit/test_cost_conn_crossthread_xfail.py`, plus director2 cursor.
- `git diff --name-status 65e097a..HEAD -- cost_tracker.py tests/unit/test_cost_conn_crossthread_xfail.py tests/unit/test_llmensemble_cost_uncounted_xfail.py llm/ensemble.py domain/scene_decomposer.py llm/prompt_optimizer.py cinema/shots/controller.py docs/superpowers/briefs/2026-06-15-cost-conn-crossthread-drop.md docs/superpowers/briefs/2026-06-15-llmensemble-cost-uncounted.md docs/REMEDIATION-INVENTORY.md coordination/mailbox/sent` -> only later mailbox events and `docs/REMEDIATION-INVENTORY.md`; no scoped cost/LLM production or regression-test drift after `65e097a`.

Evidence was run from clean HEAD archive `/private/tmp/content-lanev-cost-XALdy6` unless noted:
- `env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_cost_conn_crossthread_xfail.py -q` -> `1 passed in 0.02s`.
- `env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_llmensemble_cost_uncounted_xfail.py -q` -> `3 passed in 0.08s`.
- `env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_cost_tracker.py -q` -> `83 passed, 2 warnings in 0.10s`.
- `env -u GIT_INDEX_FILE ANTHROPIC_API_KEY=fake OPENAI_API_KEY=fake GEMINI_API_KEY=fake /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_prompt_optimizer.py tests/unit/test_ensemble_judge_parse.py tests/unit/test_llm_caching.py tests/unit/test_web_research_uncounted_xfail.py tests/unit/test_llmensemble_cost_uncounted_xfail.py tests/unit/test_cost_conn_crossthread_xfail.py -q` -> `32 passed in 0.75s`.
- `env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_prompt_optimizer.py tests/unit/test_web_research_uncounted_xfail.py tests/unit/test_llmensemble_cost_uncounted_xfail.py tests/unit/test_cost_conn_crossthread_xfail.py tests/unit/test_cost_tracker.py -q` -> `98 passed, 2 warnings in 0.14s`.
- `env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_cost_conn_crossthread_xfail.py --runxfail -q --tb=short` -> `1 passed in 0.01s`.
- Worker-thread probe of `LLMEnsemble.competitive_generate()` candidates calling `_log_llm_usage()` from ThreadPoolExecutor workers -> `winner_content={"ok": true}`, `spent_usd=10.8`, `warnings=0`.
- Main worktree smoke: `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with existing PROGRAM-MANUAL doc-anchor drift, legacy mailbox-kind, and R2 invisible-green advisories only.

Write/scope audit:
- `cost_tracker.py:229` creates `_conn_lock = threading.RLock()` and `cost_tracker.py:230` opens SQLite with `check_same_thread=False`.
- `cost_tracker.py:292-307` locks the insert, commit, and `spent_usd += cost_usd`; budget reads snapshot under the lock at `cost_tracker.py:455` and `cost_tracker.py:473`.
- Shared connection read/close helpers now take the same lock at `cost_tracker.py:504`, `cost_tracker.py:522`, `cost_tracker.py:567`, `cost_tracker.py:620`, and `cost_tracker.py:692`.
- LLMEnsemble still runs candidates in worker threads at `llm/ensemble.py:220`, logs candidate usage through `llm/ensemble.py:144-165` / `llm/ensemble.py:229`, and the shared tracker reaches competitive decomposition at `domain/scene_decomposer.py:759`; prompt optimizer sibling remains threaded at `llm/prompt_optimizer.py:404` and `cinema/shots/controller.py:718`.

Findings:
- No blocking findings.
- No cross-cutting lock or co-sign release is required; `cost_tracker.py` is outside the protocol lock-file set for this row.
- Residual Wave 2 blockers remain unrelated: the real product-oracle measurement artifact, `spent-usd-reset-on-resume`, `perf-phase-no-gate`, and other red/open pins reported by the wave gate.

Disposition: coordinator may reconcile `cost-conn-crossthread-drop` and `llmensemble-cost-uncounted` to verified on this operator2 GO, subject to normal inventory reconciliation. The newer `perf-take-meta` verify request `02719a4` remains queued for operator2 Lane V after this report.

Cursor at send: 2026-06-15T06:46:58Z
