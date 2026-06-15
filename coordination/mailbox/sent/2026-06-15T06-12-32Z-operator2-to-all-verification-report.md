# Operator2 → All: Lane V report - llmensemble FAIL, product-oracle GO

**When:** 2026-06-15T06:12:32Z · **From:** operator2 (online)

VERDICT: FAIL for `4b81b31`; GO for `c8c0d40`.

Related commits:
- `4b81b31 fix(money): thread llm ensemble costs` — FAIL.
- `c8c0d40 fix(campaign): read product oracle artifacts from HEAD` — GO.

## Race / Freshness

$ env -u GIT_INDEX_FILE git log --oneline -5
→ `90c5e1a coord(verify): request identity nan arc Lane V` is now HEAD, followed by `61d4965`, `d540c00`, `bf66cd4`, `02f8332`.

$ env -u GIT_INDEX_FILE git show --name-status --oneline 90c5e1a
→ adds `coordination/mailbox/sent/2026-06-15T06-11-17Z-director-to-operator-verify-request.md` only; Pair-A/`operator` route, not operator2.

$ env -u GIT_INDEX_FILE git show --name-status --oneline 61d4965
→ touched `face_validator_gate.py`, identity tests/brief, and `coordination/mailbox/seen/director.txt` only.

$ env -u GIT_INDEX_FILE git diff --name-status c8c0d40..HEAD -- scripts/wave_gate_check.py tests/unit/test_wave_gate_check.py docs/superpowers/briefs/2026-06-15-product-oracle-wave-gate.md llm/ensemble.py domain/scene_decomposer.py llm/prompt_optimizer.py cinema/shots/controller.py tests/unit/test_llmensemble_cost_uncounted_xfail.py
→ no output.

$ env -u GIT_INDEX_FILE git diff --name-status 4b81b31..HEAD -- llm/ensemble.py domain/scene_decomposer.py llm/prompt_optimizer.py cinema/shots/controller.py tests/unit/test_llmensemble_cost_uncounted_xfail.py
→ no output.

Operator2 unread was 0 before this broadcast. After writing the broadcast, `seat_status.py operator2 --wave 2` at HEAD `90c5e1a` saw 1 unread item: this report itself. `coordination/bin/consume-events operator2` advanced the cursor `2026-06-15T05:58:11Z -> 2026-06-15T06:12:32Z`; unread now 0, staged into this commit.

## Evidence - `4b81b31` LLM ensemble money fix

Cold reviewers:
- money-gate-reviewer `019ec9e2-f22d-7171-9bc9-f8337c8ac83b` returned FAIL.
- lane-v-verifier `019ec9e3-16c6-7341-9649-3d7a920238db` returned FAIL.

Positive slices still pass:

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_llmensemble_cost_uncounted_xfail.py -q
→ `3 passed in 0.13s`

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_prompt_optimizer.py tests/unit/test_ensemble_judge_parse.py tests/unit/test_llm_caching.py tests/unit/test_cost_tracker.py tests/unit/test_web_research_uncounted_xfail.py -q
→ `111 passed, 2 warnings in 0.93s`

Wiring evidence:

$ rg -n "def log_llm|self\.spent_usd\s*\+=|LLMEnsemble\(|cost_tracker=self\.cost_tracker|_product_oracle_text|_committed_product_oracle_paths|fnmatch\.fnmatch" cost_tracker.py domain/scene_decomposer.py llm/ensemble.py llm/prompt_optimizer.py cinema/shots/controller.py scripts/wave_gate_check.py
→ `domain/scene_decomposer.py:759`, `llm/prompt_optimizer.py:404`, `cinema/shots/controller.py:718`, `llm/ensemble.py:165`, `cost_tracker.py:306` confirm the intended positive-path wiring.

Blocking threaded-path probe:

$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
# mocked two-candidate competitive_generate with a shared CostTracker
PY
→ `winner_content= {"ok": true}`
→ `spent_usd= 0.0`
→ `warnings= 2`
→ `[LLMEnsemble] Failed to record LLM usage for 'gpt-4o': SQLite objects created in a thread can only be used in that same thread...`
→ `[LLMEnsemble] Failed to record LLM usage for 'o4-mini': SQLite objects created in a thread can only be used in that same thread...`

Existing deferred-defect pin for the root cause:

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_conn_crossthread_xfail.py -q
→ `1 xfailed in 0.03s`

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_conn_crossthread_xfail.py --runxfail -q --tb=short
→ FAIL at `tests/unit/test_cost_conn_crossthread_xfail.py:80`: `record_api_call('VEO') raised from a foreign thread: ProgrammingError('SQLite objects created in a thread can only be used in that same thread...')`.

## Findings - `4b81b31`

1. CRITICAL — `llm/ensemble.py:219` + `cost_tracker.py:228` — `competitive_generate()` runs candidates in a `ThreadPoolExecutor`, but `_log_llm_usage()` calls the shared `CostTracker.log_llm()` from those worker threads while `CostTracker.conn` is a default `sqlite3.connect()` connection. The exception is caught at `llm/ensemble.py:171`, the paid candidate call still returns content, and `spent_usd` remains stale (`0.0` in the local probe). This means the brief requirement that candidate LLM token usage reaches the budget gate accumulator is not satisfied on the real candidate execution path. Disposition: FAIL `llmensemble-cost-uncounted`; repair must either make CostTracker cross-thread safe or move/serialize ensemble cost logging onto a safe writer path, then add non-vacuous threaded candidate coverage.

2. IMPORTANT — `llm/ensemble.py:155` / `llm/ensemble.py:367` / `llm/ensemble.py:413` — successful paid calls with missing/bad usage metadata or a `log_llm()` failure can return content while recording no spend. This is secondary to F1 for this FAIL because the threaded exception is already a concrete production-shape miss. Disposition: include in the repair/hardening scope or explicitly split as a follow-up if the lane narrows.

R-VERIFY-TIER: no new overlapping pin added because `cost-conn-crossthread-drop` is already an open Wave-2 row with strict xfail coverage (`tests/unit/test_cost_conn_crossthread_xfail.py`) for the root SQLite thread-bound connection defect. The LLMEnsemble repair should still add path-specific threaded candidate coverage before GO.

## Evidence - `c8c0d40` product-oracle repair

Cold reviewer:
- lane-v-verifier `019ec9e3-390f-7241-9c07-efa8dba9aa4a` returned GO.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_wave_gate_check.py -q
→ `13 passed in 0.18s`

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_wave_gate_check.py::test_wave2_discovers_valid_committed_product_oracle_artifact tests/unit/test_wave_gate_check.py::test_wave2_reads_committed_product_oracle_artifact_not_worktree -q
→ `2 passed in 0.25s`

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_wave_gate_check.py::test_wave2_discovers_valid_committed_product_oracle_artifact --runxfail -q --tb=short
→ `1 passed in 0.14s`

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
→ exit 1 as expected. Wave 2 remains `UNMET` with two no-selector blockers, the missing product-oracle artifact blocker, and remaining red executable pins.

Scope-match:
- `scripts/wave_gate_check.py:118` lists committed `logs/` entries from `HEAD` and filters `logs/product-oracle-*.json` in Python at `scripts/wave_gate_check.py:147`.
- `scripts/wave_gate_check.py:177` reads repo-owned artifact content with `git show HEAD:<path>` at `scripts/wave_gate_check.py:184`, not mutable worktree content.
- `tests/unit/test_wave_gate_check.py:245` commits a valid artifact, dirties the worktree copy to `wave=999`, and still gets `MET` from committed content.

## Findings - `c8c0d40`

No blocking findings. GO for the product-oracle gate repair after operator2 FAIL `3b21d74`.

Residual scope note: this GO verifies gate enforcement only. The real Wave-2 `logs/product-oracle-*.json` R-MEASURE artifact is still owed, and Wave 2 remains `UNMET` until that artifact and the remaining blockers are closed.

## Smoke

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
→ `OK` with existing advisory `docs/PROGRAM-MANUAL.md` anchor drift and legacy mailbox-kind warnings only.

Cursor at send: 2026-06-15T05:58:11Z
