# R-BRIEF: perf-phase-no-gate — budget precheck before performance capture

PRIORITY: MAJOR        LANE: B (video/assembly/audio)
CROSS-CUTTING: no (`cinema/shots/controller.py`, `cinema/phases/performance.py`, `cinema_pipeline.py`, `cost_tracker.py`; none are in the lock set `auto_approve.py`, `cinema/context.py`, `core.py`, `web_server.py`)

## Repair addendum after operator2 FAIL

Operator2 FAIL `2026-06-15T18-16-10Z-operator2-to-all-verification-report.md`
confirmed the engine-only precheck is insufficient for Mode B. The failing
path is:

1. `CostTracker.would_exceed("ACT_ONE")` can pass at `spent_usd=0.70`,
   `budget_usd=1.00`.
2. `synth_driving_face_from_audio(... cost_tracker=self.cost_tracker)` can then
   log paid Hedra/SadTalker driving spend.
3. `performance._router.dispatch(... cost_tracker=self.cost_tracker)` can then
   log Act-One spend, putting combined driving+engine spend over cap.

Repair shape: add a combined precheck before Mode-B synth that estimates the
main performance engine plus the expected Mode-B driving synth. Keep the
structured refusal shape already used by the prior fix:
`BUDGET_EXCEEDED`, `self._lifecycle.pause()`, and
`{"success": False, "error_kind": "budget"}` before synth or dispatch.

`PERFORMANCE_HALTED` continuation is intentional pause/review behavior for this
repair. It parks the run at `PERFORMANCE_REVIEW` so an operator can raise the
budget, upload/re-record/skip performance, or cancel. The refusal leaves no
paid performance take and no approved take, so the review gate is not
automatically satisfied by the budget halt. This repair does not turn a budget
halt into cancellation.

## The defect

`cinema/shots/controller.py:generate_performance_take` resolves a paid performance engine (`ACT_ONE`, `LIVE_PORTRAIT`, `VIGGLE`) and launches Mode-B driving synth plus `performance._router.dispatch(...)` without first asking the shared `CostTracker` whether the next performance spend would exceed the project budget.

The sibling motion path already refuses before launching paid video generation and returns `error_kind="budget"`. Performance capture lacked the equivalent guard, so near-cap runs could launch paid retargeting while the budget gate stayed silent.

## Rule #12 — grep-the-writes

TARGET SYMBOL: performance paid-call path writes to the shared budget accumulator.

```text
$ rg -n "cost_tracker=self\.cost_tracker|from performance\._router import dispatch|result_path = dispatch\(|synth_driving_face_from_audio\(" cinema/shots/controller.py
731:                        cost_tracker=self.cost_tracker,
1095:                synth_result = synth_driving_face_from_audio(
1101:                    cost_tracker=self.cost_tracker,
1139:            from performance._router import dispatch
1140:            result_path = dispatch(
1149:                cost_tracker=self.cost_tracker,

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

Additional repair evidence for the Mode-B driving price write:

```text
$ rg -n "def estimate_driving_face_cost|def _cost_log|cost_tracker\\.log_api|cost_usd=estimate_driving_face_cost|def would_exceed|def would_exceed_cost|spent \\+ cost|spent \\+ estimated" performance/driving_video.py cost_tracker.py
cost_tracker.py:449:    def would_exceed(self, api_name: str) -> bool:
cost_tracker.py:466:        return (spent + cost) > self.budget_usd
cost_tracker.py:468:    def would_exceed_cost(self, estimated_cost_usd: float) -> bool:
cost_tracker.py:484:        return (spent + cost) > self.budget_usd
performance/driving_video.py:37:def estimate_driving_face_cost(provider: str, duration_s: float) -> float:
performance/driving_video.py:50:def _cost_log(provider: str, duration_s: float, shot_id: str, video_id: str, cost_tracker=None) -> None:
performance/driving_video.py:56:            cost_usd=estimate_driving_face_cost(provider, duration_s),
```

## Rule #13 — symmetric / sibling audit

SHARED FENCE/FLAG/STATE: pre-spend budget gate and structured budget refusal.

```text
$ rg -n "would_exceed\(|BUDGET_EXCEEDED|error_kind.*budget|self\._lifecycle\.pause" cinema/shots/controller.py cinema/phases -g '*.py'
cinema/shots/controller.py:1050:            would_exceed_budget = self.cost_tracker.would_exceed_cost(estimated_cost)
cinema/shots/controller.py:1059:            would_exceed_budget = self.cost_tracker.would_exceed(engine)
cinema/shots/controller.py:1069:                "BUDGET_EXCEEDED",
cinema/shots/controller.py:1079:            self._lifecycle.pause()
cinema/shots/controller.py:1083:                "error_kind": "budget",
cinema/shots/controller.py:1569:                "BUDGET_EXCEEDED",
cinema/shots/controller.py:1578:            self._lifecycle.pause()
cinema/shots/controller.py:1720:        if self.cost_tracker.would_exceed(target_api):
cinema/shots/controller.py:1722:                "BUDGET_EXCEEDED",
cinema/shots/controller.py:1732:            self._lifecycle.pause()
cinema/shots/controller.py:1739:                "error_kind": "budget",
cinema/phases/performance.py:81:                elif result.get("error_kind") == "budget":
cinema/phases/motion_render.py:120:        # BUDGET_EXCEEDED and aborts the phase — single abort mechanism.
cinema/phases/motion_render.py:124:                refused = bool(tracker.would_exceed("KLING_NATIVE"))
cinema/phases/motion_render.py:442:                elif result.get("error_kind") == "budget":
```

Sibling folded: performance capture now mirrors motion by returning `error_kind="budget"`, emitting `BUDGET_EXCEEDED`, pausing lifecycle, stopping the phase loop on structured budget refusal, and emitting `PERFORMANCE_HALTED` instead of `PERFORMANCE_DONE`.

Additional sibling found and folded: `CostTracker.would_exceed(engine)` would be vacuous without `API_COST_USD` entries for the performance engines, so `ACT_ONE`, `LIVE_PORTRAIT`, and `VIGGLE` are priced with the same 5-second estimates used by the adapter `_cost_log` methods.

Repair sibling folded: the same pre-spend fence must cover the Mode-B driving
write-path because it uses the same shared `CostTracker` accumulator before
main dispatch. The combined precheck uses the existing structured budget refusal
and phase abort; no lock is involved, and the inventory row stays open pending
operator2 GO.

## Full-shape pattern reference

MIRROR: `generate_motion_take` pre-spend guard in `cinema/shots/controller.py`:
signature unchanged; gate runs after engine resolution and before paid dispatch; refusal emits `BUDGET_EXCEEDED`, calls `self._lifecycle.pause()`, returns `{"success": False, "error_kind": "budget"}`; `MotionRenderPhase` stops its loop on that structured error.

Performance-specific adaptation: the guard runs after routing and hard precondition checks but before Mode-B driving synth and main performance dispatch.

## The fix

- Add performance-engine cost estimates to `API_COST_USD`.
- Add `self.cost_tracker.would_exceed(engine)` in `generate_performance_take` before paid performance work.
- Add a combined Mode-B precheck before `synth_driving_face_from_audio` that
  prices expected driving synth plus the resolved performance engine.
- Stop `PerformanceCapturePhase` on `error_kind="budget"`.
- Emit `PERFORMANCE_HALTED` for an aborted performance phase.
- Replace the stale `test-infeasible` row with executable offline regressions.

## Verification the operator/CI will run

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate \
  tests/unit/test_budget_pre_spend_gate.py::TestPerformancePhaseBudgetAbort \
  tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness::test_performance_capture_engines_priced_in_api_cost_usd \
  tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness::test_mode_b_driving_providers_priced_in_api_cost_usd \
  -q

env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness -q

env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate::test_mode_b_refuses_when_combined_driving_and_engine_cost_exceeds_budget \
  --runxfail -q
```
