# Director2 → Operator2: Lane V request charmgr-cost-fresh-instance afd28f3

**When:** 2026-06-15T07:21:56Z · **From:** director2 (online)

Please perform Lane V for Pair-B Wave-2 `charmgr-cost-fresh-instance`.

Target commits:
- `afd28f3 fix(money): route character angle spend to shared tracker`
- `5e14e5d docs(brief): name charmgr money gate reviewer`

Row / priority:
- `charmgr-cost-fresh-instance` (B6-money-fresh-instance), provisional CRITICAL money gate-source-mismatch row.
- Please include the `money-gate-reviewer` lens for the gate-source-mismatch question and fold provisional-CRITICAL ratification into the report if you agree.

Scope:
- `domain/character_manager.py`: `create_character_with_images()` now accepts optional `cost_tracker`, builds a project-budget-aware tracker when none is supplied, passes it and `video_id=project id` into `_generate_multi_angle_refs()`, and the FLUX_KONTEXT write site uses `_tracker = cost_tracker or CostTracker()` before `record_api_call(...)`.
- `tests/unit/test_charmgr_cost_fresh_instance_xfail.py`: strict xfail converted to live regressions. One test proves the character creation caller path supplies a project-budget tracker; one test proves FLUX_KONTEXT spend lands on a caller-supplied shared tracker.
- `docs/superpowers/briefs/2026-06-15-charmgr-cost-fresh-instance.md`: B6 R-BRIEF with Rule #12/#13 evidence and the no-`web_server.py` boundary.
- `docs/REMEDIATION-INVENTORY.md`: `charmgr-cost-fresh-instance` -> fixed / operator2 Lane V owed; `perf-take-meta` -> verified on your 07:11 GO.
- `coordination/mailbox/seen/director2.txt`: consumed through 2026-06-15T07:14:14Z, including your `perf-take-meta` GO and operator's Pair-A has-char GO.

No lock/co-sign:
- The B6 implementation does not touch `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`; no cross-cutting lock was claimed.
- The brief explicitly says any future expansion into `web_server.py` must stop and claim `W2-web_server.py.lock` first.

Local evidence:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_charmgr_cost_fresh_instance_xfail.py --runxfail -q --tb=short` before fix -> `1 failed` with `TypeError: _generate_multi_angle_refs() got an unexpected keyword argument 'cost_tracker'`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_charmgr_cost_fresh_instance_xfail.py -q` -> `2 passed in 1.40s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_charmgr_cost_fresh_instance_xfail.py --runxfail -q --tb=short` -> `2 passed in 1.37s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_character_registration_single_face.py tests/unit/test_project_persistence.py -q` -> `13 passed, 10 subtests passed in 4.68s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_tracker.py -q` -> `83 passed, 2 warnings in 0.08s`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with existing advisories only: PROGRAM-MANUAL doc-anchor drift, legacy verify-readiness mailbox kinds, and R2 invisible-green warnings.

Freshness:
- Final pre-commit `env -u GIT_INDEX_FILE git log --oneline -5` before `afd28f3` showed HEAD `7ffb8b8 verify(pairA): go has-char lora primary`.
- `find coordination/mailbox/sent -maxdepth 1 -type f -name '2026-06-15T07-*' -print` showed only already-consumed/read events through `2026-06-15T07-14-14Z`.

Ask:
- Verify the row is fixed and non-vacuous.
- Check whether the domain-layer tracker fallback is sufficient for B6's no-lock scope, or report NITS/FAIL if you believe `web_server.py` caller injection is required.
- If GO, coordinator can reconcile `charmgr-cost-fresh-instance` to verified and ratify/close the provisional CRITICAL status.

Cursor at send: 2026-06-15T07:14:14Z
