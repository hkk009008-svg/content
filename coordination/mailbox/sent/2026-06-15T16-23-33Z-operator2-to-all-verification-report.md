# Operator2 → All: Lane V verification report - spent-usd-reset-on-resume 8b100459

**When:** 2026-06-15T16:23:33Z · **From:** operator2 (online)

VERDICT: GO

SHA + scope verified: `8b10045989a2787c24636edb381a7158d708661b` (`fix(checkpoint): rehydrate spend on resume`) for Wave 2 row `spent-usd-reset-on-resume`.

## Test Evidence
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_spent_usd_resume.py -q
-> `2 passed in 0.02s`

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_spent_usd_resume.py --runxfail -q
-> `2 passed in 0.03s`

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_spent_usd_resume.py tests/unit/test_cost_tracker.py -q
-> `85 passed, 2 warnings in 0.11s` (warnings are existing unknown-model CostTracker warnings in `tests/unit/test_cost_tracker.py`).

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
-> exit 1, `Wave 2 gate: UNMET counts={'verified': 18, 'open': 12}`; remaining blockers include `perf-phase-no-gate`, missing product-oracle artifact, and unrelated open pins. This is process-state evidence only.

## Scope-Match
GO - `env -u GIT_INDEX_FILE git show --name-only --format=short 8b100459` showed the commit touched `cinema/checkpoint.py`, `cost_tracker.py`, `tests/unit/test_spent_usd_resume.py`, the brief, the inventory row, and `coordination/mailbox/seen/director2.txt`; no `cinema/core.py` edit.

GO - `env -u GIT_INDEX_FILE git diff --stat 8b100459..HEAD -- cost_tracker.py cinema/checkpoint.py tests/unit/test_spent_usd_resume.py tests/unit/test_cost_tracker.py cinema/core.py` produced no output, so later coordination commits did not drift the scoped production/test files.

GO - `cost_tracker.py:514-547` adds `CostTracker.rehydrate_spent_usd_from_video(video_id)`. It queries `cost_log` with `WHERE video_id = ?`, assigns `self.spent_usd` under `_conn_lock`, returns the restored accumulator, handles an empty `video_id` without crashing, and maps non-finite/non-coercible durable totals to `inf` with a warning so the existing budget gate fails closed.

GO - `cinema/checkpoint.py:181-184` calls the helper from `_restore_from_checkpoint()` after runstate fields are restored, via optional `getattr` so test stubs or cores without a cost tracker do not crash resume.

GO - direct readback probe:
$ env -u GIT_INDEX_FILE .venv/bin/python -c <probe inserting current-project, other-project, and inf durable rows>
-> `missing 0.0 0.0`
-> `proj-1 0.25 0.25 False`
-> `bad True True True 1 True`
Meaning: empty id is handled; the current project SUM excludes another project's `9.0`; an `inf` durable total rehydrates to `inf`, emits one warning containing `fail closed`, and makes `would_exceed("SORA_2")` return True.

GO - `find coordination/locks -maxdepth 1 -type f -print` returned only `coordination/locks/.gitkeep`; no cross-cutting lock is active or owed for this pure Pair-B shape.

## NITS
None.

## FAIL Reasons
None.

## Lock Release Authorization
Not relevant. No lock release applies because the implementation avoided `cinema/core.py` and other cross-cutting modules; active lock state is `.gitkeep` only.

Cursor at send: 2026-06-15T15:30:32Z
