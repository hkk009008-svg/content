# R-BRIEF: spent-usd-reset-on-resume - resume must keep the budget gate honest

PRIORITY: MAJOR        LANE: B (video/assembly/audio)
CROSS-CUTTING: no
  -> No shared lock. The implementation stays out of `cinema/core.py`,
     `cinema/context.py`, `cinema/auto_approve.py`, and `web_server.py`.

## The Defect

`spent-usd-reset-on-resume` is a Wave 2 Pair-B checkpoint/money row. A resumed
pipeline gets a fresh `CostTracker` whose fast budget-gate accumulator starts at
`0.0`, while prior spend survives only in SQLite. `_restore_from_checkpoint()`
restores runstate fields but never rehydrates `CostTracker.spent_usd`, so
`would_exceed()` and `is_over_budget()` under-count after process restart.

## Rule #12 - Grep The Writes

TARGET SYMBOL: `CostTracker.spent_usd`, the in-memory accumulator read by the
budget gate.

`$ rg -n "self\\.spent_usd\\s*:|self\\.spent_usd\\s*=|self\\.spent_usd\\s*\\+=" cost_tracker.py`

```text
228:        self.spent_usd: float = 0.0
307:            self.spent_usd += cost_usd
```

Runtime write confirmed: `log()` increments the accumulator after persisting a
cost row. The resume gap is the constructor reset at line 228 with no later
restore-side write.

TARGET DURABLE SOURCE: `cost_log.cost_usd` rows scoped by project/video id.

`$ rg -n "SELECT .*SUM\\(cost_usd\\)|WHERE video_id|WHERE shot_id|get_video_cost|get_session_cost|get_shot_spent" cost_tracker.py cinema/review/controller.py cinema_pipeline.py`

```text
cinema/review/controller.py:332:                    shot["spent_usd"] = self._core.cost_tracker.get_shot_spent(
cost_tracker.py:483:    def get_shot_spent(self, shot_id: str) -> float:
cost_tracker.py:488:        veto checks.  Mirrors the get_session_cost COALESCE pattern to handle
cost_tracker.py:506:                "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM cost_log WHERE shot_id = ?",
cost_tracker.py:514:    def get_video_cost(self, video_id: str) -> dict:
cost_tracker.py:524:                "SELECT * FROM cost_log WHERE video_id = ?", (video_id,)
cost_tracker.py:558:    def get_session_cost(self, lookback_hours: float = 24.0) -> float:
cost_tracker.py:569:                "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM cost_log WHERE timestamp >= ?",
cost_tracker.py:576:        info = self.get_video_cost(video_id)
cinema_pipeline.py:916:            cost_summary = self.cost_tracker.get_video_cost(video_id)
```

Durable read patterns exist. This fix adds the missing project/video-scoped
rehydration helper rather than changing the `core.py` constructor.

## Rule #13 - Symmetric / Sibling Audit

SHARED STATE: budget-gate spend source of truth.

`$ rg -n "would_exceed\\(|is_over_budget\\(|spent_usd" cost_tracker.py cinema/shots/controller.py cinema/phases/motion_render.py cinema/review/controller.py phase_c_ffmpeg.py`

```text
phase_c_ffmpeg.py:104:        in cinema/shots/controller.py, ADR-022) calls cost_tracker.would_exceed()
phase_c_ffmpeg.py:107:        would_exceed() reads 0.0 and the gate silently admits them.
cost_tracker.py:23:``would_exceed(api_name)`` before an API call and ``is_over_budget()``
cost_tracker.py:30:``spent_usd`` accumulates in-process only; SQLite is the durable store,
cost_tracker.py:228:        self.spent_usd: float = 0.0
cost_tracker.py:302:            # spent_usd mirrors the persisted spend. Increment at this sole write
cost_tracker.py:307:            self.spent_usd += cost_usd
cost_tracker.py:443:    def would_exceed(self, api_name: str) -> bool:
cost_tracker.py:456:            spent = self.spent_usd
cost_tracker.py:462:    def is_over_budget(self) -> bool:
cost_tracker.py:474:            spent = self.spent_usd
cinema/review/controller.py:332:                    shot["spent_usd"] = self._core.cost_tracker.get_shot_spent(
cinema/phases/motion_render.py:124:                refused = bool(tracker.would_exceed("KLING_NATIVE"))
cinema/shots/controller.py:1518:        if self.cost_tracker.is_over_budget():
cinema/shots/controller.py:1671:        if self.cost_tracker.would_exceed(target_api):
```

Sibling disposition:

- `would_exceed()` and `is_over_budget()` already fail safe on non-finite
  `spent_usd`; do not change their semantics.
- `get_shot_spent()` already uses a durable SQLite SUM for per-shot gate
  injection; mirror its COALESCE/finite-safe shape for project/video rehydrate.
- `get_video_cost()` remains reporting-oriented and returns a breakdown dict;
  do not make checkpoint restore parse that report.
- `perf-phase-no-gate` is a separate missing pre-spend check in
  `generate_performance_take`; defer it to its own row.

## Full-Shape Pattern Reference

MIRROR: `CostTracker.get_shot_spent(shot_id)` at `cost_tracker.py:483`, including
the SQLite `COALESCE(SUM(cost_usd), 0.0)` query and finite-value guard.

MIRROR: `CheckpointStore._restore_from_checkpoint()` at
`cinema/checkpoint.py:163`, preserving its no-argument return contract
(`set[int]`) and best-effort resume behavior. The new spend rehydrate must not
turn a missing optional `cost_tracker` test stub into a crash.

## The Fix

Add `CostTracker.rehydrate_spent_usd_from_video(video_id) -> float`:

- Query durable `cost_log` rows with `WHERE video_id = ?`.
- Set `self.spent_usd` under `_conn_lock`.
- Return the restored total.
- Preserve fail-safe behavior for non-finite persisted totals by making gate
  reads fire rather than treating corrupt spend as zero.

Call that helper from `CheckpointStore._restore_from_checkpoint()` after state
restore, using the current project id. This intentionally avoids
`cinema/core.py`, so no cross-cutting lock is required.

Files expected:

- `cost_tracker.py`
- `cinema/checkpoint.py`
- `tests/unit/test_spent_usd_resume.py`
- `docs/REMEDIATION-INVENTORY.md`
- this brief

## Verification

Primary selector:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_spent_usd_resume.py -q
```

Expected after fix: `2 passed`.

Also run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_tracker.py tests/unit/test_spent_usd_resume.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
```

`wave_gate_check.py 2` is expected to remain UNMET for other open rows and the
missing product-oracle artifact, but `spent-usd-reset-on-resume` must no longer
be reported as "no executable xfail-pin selector".
