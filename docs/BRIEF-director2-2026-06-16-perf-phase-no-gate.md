# R-BRIEF: perf-phase-no-gate — budget precheck before performance capture

PRIORITY: MAJOR        LANE: B (video/assembly/audio)
CROSS-CUTTING: no (`cinema/shots/controller.py`, `cinema/phases/performance.py`, `cinema_pipeline.py`, `cost_tracker.py`; none are in the lock set `auto_approve.py`, `cinema/context.py`, `core.py`, `web_server.py`)

## The defect

`cinema/shots/controller.py:generate_performance_take` resolves a paid performance engine (`ACT_ONE`, `LIVE_PORTRAIT`, `VIGGLE`) and launches Mode-B driving synth plus `performance._router.dispatch(...)` without first asking the shared `CostTracker` whether the next performance spend would exceed the project budget.

The sibling motion path already refuses before launching paid video generation and returns `error_kind="budget"`. Performance capture lacked the equivalent guard, so near-cap runs could launch paid retargeting while the budget gate stayed silent.

## Rule #12 — grep-the-writes

TARGET SYMBOL: performance paid-call path writes to the shared budget accumulator.

```text
$ rg -n "cost_tracker=self\.cost_tracker|from performance\._router import dispatch|result_path = dispatch\(|synth_driving_face_from_audio\(" cinema/shots/controller.py
731:                        cost_tracker=self.cost_tracker,
1070:                synth_result = synth_driving_face_from_audio(
1076:                    cost_tracker=self.cost_tracker,
1114:            from performance._router import dispatch
1115:            result_path = dispatch(
1124:                cost_tracker=self.cost_tracker,

$ rg -n "def _cost_log|cost_tracker\.log_api|cost_tracker\.record_api_call|CostTracker\(" performance -g '*.py'
performance/act_one.py:29:def _cost_log(operation: str, duration_s: float, shot_id: str = "", video_id: str = "", cost_tracker=None) -> None:
performance/act_one.py:34:        (cost_tracker or CostTracker()).log_api(
performance/live_portrait.py:27:def _cost_log(duration_s: float, shot_id: str = "", video_id: str = "", cost_tracker=None) -> None:
performance/live_portrait.py:31:        (cost_tracker or CostTracker()).log_api(
performance/driving_video.py:33:def _cost_log(provider: str, duration_s: float, shot_id: str, video_id: str, cost_tracker=None) -> None:
performance/driving_video.py:37:        (cost_tracker or CostTracker()).log_api(
performance/viggle.py:26:def _cost_log(shot_id: str = "", video_id: str = "", cost_tracker=None) -> None:
performance/viggle.py:30:        (cost_tracker or CostTracker()).log_api(
```

Runtime write is confirmed: controller passes `self.cost_tracker` into both Mode-B driving synth and main dispatch; each performance adapter writes through `_cost_log(...).log_api(...)`.

## Rule #13 — symmetric / sibling audit

SHARED FENCE/FLAG/STATE: pre-spend budget gate and structured budget refusal.

```text
$ rg -n "would_exceed\(|BUDGET_EXCEEDED|error_kind.*budget|self\._lifecycle\.pause" cinema/shots/controller.py cinema/phases -g '*.py'
cinema/shots/controller.py:1039:        if self.cost_tracker.would_exceed(engine):
cinema/shots/controller.py:1041:                "BUDGET_EXCEEDED",
cinema/shots/controller.py:1052:            self._lifecycle.pause()
cinema/shots/controller.py:1056:                "error_kind": "budget",
cinema/shots/controller.py:1544:                "BUDGET_EXCEEDED",
cinema/shots/controller.py:1553:            self._lifecycle.pause()
cinema/shots/controller.py:1695:        if self.cost_tracker.would_exceed(target_api):
cinema/shots/controller.py:1697:                "BUDGET_EXCEEDED",
cinema/shots/controller.py:1707:            self._lifecycle.pause()
cinema/shots/controller.py:1714:                "error_kind": "budget",
cinema/phases/performance.py:81:                elif result.get("error_kind") == "budget":
cinema/phases/motion_render.py:120:        # BUDGET_EXCEEDED and aborts the phase — single abort mechanism.
cinema/phases/motion_render.py:124:                refused = bool(tracker.would_exceed("KLING_NATIVE"))
cinema/phases/motion_render.py:442:                elif result.get("error_kind") == "budget":
```

Sibling folded: performance capture now mirrors motion by returning `error_kind="budget"`, emitting `BUDGET_EXCEEDED`, pausing lifecycle, stopping the phase loop on structured budget refusal, and emitting `PERFORMANCE_HALTED` instead of `PERFORMANCE_DONE`.

Additional sibling found and folded: `CostTracker.would_exceed(engine)` would be vacuous without `API_COST_USD` entries for the performance engines, so `ACT_ONE`, `LIVE_PORTRAIT`, and `VIGGLE` are priced with the same 5-second estimates used by the adapter `_cost_log` methods.

## Full-shape pattern reference

MIRROR: `generate_motion_take` pre-spend guard in `cinema/shots/controller.py`:
signature unchanged; gate runs after engine resolution and before paid dispatch; refusal emits `BUDGET_EXCEEDED`, calls `self._lifecycle.pause()`, returns `{"success": False, "error_kind": "budget"}`; `MotionRenderPhase` stops its loop on that structured error.

Performance-specific adaptation: the guard runs after routing and hard precondition checks but before Mode-B driving synth and main performance dispatch.

## The fix

- Add performance-engine cost estimates to `API_COST_USD`.
- Add `self.cost_tracker.would_exceed(engine)` in `generate_performance_take` before paid performance work.
- Stop `PerformanceCapturePhase` on `error_kind="budget"`.
- Emit `PERFORMANCE_HALTED` for an aborted performance phase.
- Replace the stale `test-infeasible` row with executable offline regressions.

## Verification the operator/CI will run

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate \
  tests/unit/test_budget_pre_spend_gate.py::TestPerformancePhaseBudgetAbort \
  tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness::test_performance_capture_engines_priced_in_api_cost_usd \
  -q

env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness -q
```
