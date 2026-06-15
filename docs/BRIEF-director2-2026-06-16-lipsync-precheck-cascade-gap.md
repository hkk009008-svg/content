# R-BRIEF: lipsync-precheck-cascade-gap - precheck mandatory lip-sync spend

PRIORITY: MEDIUM        LANE: B (video/assembly/audio)
CROSS-CUTTING: no
LOCK: none; scoped to `cinema/shots/controller.py` and focused tests.

## The Defect

`generate_motion_take()` prechecks only the resolved video API cost before it
dispatches video generation. For overlay-mode dialogue shots, the F1b block then
runs a mandatory lip-sync pass and records a separate `LIPSYNC_*` cost. A shot
near the budget cap can therefore pass the pre-spend gate, dispatch paid video,
then push cumulative spend over budget when the required lip-sync call is
recorded.

Current routed source: `coordination/mailbox/sent/2026-06-15T19-59-27Z-coordinator-to-all-coordination.md`.

## Rule #12 - Grep The Writes

TARGET SYMBOL: `CostTracker.spent_usd` and the motion-path lip-sync cost write.

```text
$ rg -n "self\.spent_usd\s*=|self\.spent_usd\s*\+=" cost_tracker.py
313:            self.spent_usd += cost_usd
550:                self.spent_usd = 0.0
570:            self.spent_usd = spent

$ rg -n "record_api_call\(|_lipsync_cost_api_key|LIPSYNC_|would_exceed_cost\(|would_exceed\(" cinema/shots/controller.py cinema/phases cost_tracker.py tests/unit/test_budget_pre_spend_gate.py
cost_tracker.py:94:    "LIPSYNC_SYNCSOV3":    0.05,   # sync.so v3 overlay (best generalist) via FAL
cost_tracker.py:102:    "LIPSYNC_DEFAULT":     0.05,   # fallback when the cascade reports no engine name
cost_tracker.py:449:    def would_exceed(self, api_name: str) -> bool:
cost_tracker.py:468:    def would_exceed_cost(self, estimated_cost_usd: float) -> bool:
cinema/shots/controller.py:214:def _lipsync_cost_api_key(engine: object) -> str:
cinema/shots/controller.py:1050:            would_exceed_budget = self.cost_tracker.would_exceed_cost(estimated_cost)
cinema/shots/controller.py:1059:            would_exceed_budget = self.cost_tracker.would_exceed(engine)
cinema/shots/controller.py:1720:        if self.cost_tracker.would_exceed(target_api):
cinema/shots/controller.py:1922:                            self.cost_tracker.record_api_call(
cinema/shots/controller.py:1923:                                _lipsync_cost_api_key(_ls_engine), operation="lipsync",
```

Runtime write confirmed: successful F1b lip-sync calls record a namespaced
`LIPSYNC_*` API call, and `CostTracker.log()` increments `spent_usd` at the
single accumulator write chokepoint.

## Rule #13 - Symmetric / Sibling Audit

SHARED FENCE/FLAG/STATE: pre-spend budget gate before paid dispatch.

Sibling gates checked:

- `cinema/shots/controller.py:1050` uses `would_exceed_cost(estimated_cost)`
  when performance Mode-B may launch two paid calls.
- `cinema/shots/controller.py:1059` uses `would_exceed(engine)` when only the
  performance engine cost is known.
- `cinema/shots/controller.py:1720` currently uses `would_exceed(target_api)`
  for motion generation, missing the mandatory F1b lip-sync envelope.
- `cinema/phases/motion_render.py:124` gates the storyboard batch launch with
  `would_exceed("KLING_NATIVE")`; the per-shot motion path remains responsible
  for dialogue/lip-sync spend.
- `cost_tracker.py:468` already provides `would_exceed_cost()` for caller
  computed multi-call envelopes.

Fold: mirror the Mode-B pattern in `generate_motion_take()` only when the
resolved motion take structurally requires F1b lip-sync. Defer fallback cascade
winner price variance; the existing motion gate already documents that primary
API estimates are approximate.

## Full-Shape Pattern Reference

MIRROR: `cinema/shots/controller.py:1046-1077` performance Mode-B pre-spend
gate.

Full shape to preserve:

- compute a local estimated multi-call envelope before any paid dispatch;
- use `CostTracker.would_exceed_cost(estimated_cost)` for multi-call envelope
  checks;
- on refusal, emit `BUDGET_EXCEEDED`, pause lifecycle, and return
  `{"success": False, "error_kind": "budget"}` before dispatching the paid API;
- keep the single-call `would_exceed(engine)` path where no extra required call
  exists.

## The Fix

Add a small motion-path estimate before `generate_ai_video()`:

- base estimate = `API_COST_USD[target_api]`;
- if the shot has dialogue and the resolved primary engine will not be tagged
  `audio_embedded` for the current voice mode, add `API_COST_USD["LIPSYNC_DEFAULT"]`;
- use `would_exceed_cost()` and a budget refusal message for that combined
  envelope;
- otherwise preserve the existing `would_exceed(target_api)` behavior.

Expected files:

- `cinema/shots/controller.py`
- `tests/unit/test_budget_pre_spend_gate.py`
- this brief

No `auto_approve.py`, `web_server.py`, lock file, pod spend, paid API spend, or
product-oracle artifact change is in scope.

## Verification The Operator/CI Will Run

RED first:

```text
.venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py::TestPreSpendBudgetGate::test_dialogue_overlay_refuses_when_video_plus_lipsync_exceeds_budget -q --tb=short
```

Expected RED on current code: the video API mock is called and the result is not
a structured budget refusal, because only video cost is prechecked.

GREEN:

```text
.venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py::TestPreSpendBudgetGate::test_dialogue_overlay_refuses_when_video_plus_lipsync_exceeds_budget -q --tb=short
.venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py -q --tb=short
```

The existing Wave 2 gate will remain UNMET for product-oracle and unrelated
HTTP/postprocess rows.
