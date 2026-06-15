# R-BRIEF: lipsync-precheck-cascade-gap - budget precheck misses mandatory lip-sync spend

PRIORITY: MEDIUM        LANE: B (video/assembly/audio)
CROSS-CUTTING: no. This touches `cinema/shots/controller.py`, not one of
`auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`; no
shared lock applies.

## The Defect

`docs/REMEDIATION-INVENTORY.md:53` records `lipsync-precheck-cascade-gap`:
`cinema/shots/controller.py:1655`, Wave 2 open, Pair-B, no lock. The row says
`test-infeasible`, but current test harnesses can exercise real
`ShotController.generate_motion_take()` offline with provider calls mocked.

Runtime shape:

- `generate_motion_take()` resolves `target_api` and runs the pre-spend gate at
  `cinema/shots/controller.py:1712-1740`.
- The existing gate checks only `self.cost_tracker.would_exceed(target_api)`.
- For dialogue overlay shots, the F1b block at
  `cinema/shots/controller.py:1848-1927` then runs mandatory lip-sync and records
  a `LIPSYNC_*` cost after the video spend has already been admitted.
- A near-budget shot can therefore pass the video-only precheck and overrun when
  the mandatory lip-sync call is made.

## Testability Result

Executable regression is feasible without paid API or pod spend. The existing
offline harness in `tests/unit/test_f1b_dialogue_lipsync.py` calls real
`generate_motion_take()` while patching `generate_ai_video`,
`generate_lip_sync_video`, `validate_lipsync_quality`, reference-image lookup,
duration probing, and shot type classification. A focused regression can assert
that a near-budget dialogue overlay shot refuses before either mocked provider
call.

Evidence:

```text
$ rg -n "class TestGenerateMotionTakeOverlayWiring|patch\\(\"cinema\\.shots\\.controller\\.generate_ai_video\"|patch\\(\"cinema\\.shots\\.controller\\.generate_lip_sync_video\"" tests/unit/test_f1b_dialogue_lipsync.py
594:class TestGenerateMotionTakeOverlayWiring:
792:            patch("cinema.shots.controller.generate_ai_video", return_value=veo_clip) as mock_gen_vid,
793:            patch("cinema.shots.controller.generate_lip_sync_video", return_value=ls_clip) as mock_gen_ls_ctrl,
```

## Rule #12 - grep-the-writes

TARGET SYMBOL: `CostTracker.spent_usd`, read by `would_exceed()` /
`would_exceed_cost()` and written when generation costs are recorded.

```text
$ rg -n "record_api_call\\(|self\\.spent_usd\\s*\\+=|self\\.spent_usd\\s*=" --glob '*.py' .
./cost_tracker.py:313:            self.spent_usd += cost_usd
./cost_tracker.py:388:    def record_api_call(
./cost_tracker.py:550:                self.spent_usd = 0.0
./cost_tracker.py:570:            self.spent_usd = spent
./cinema/shots/controller.py:1553:                self.cost_tracker.record_api_call(
./cinema/shots/controller.py:1922:                            self.cost_tracker.record_api_call(
```

The production write chokepoint for recorded API spend is
`cost_tracker.py:313`. The motion video spend records at
`cinema/shots/controller.py:1553`, and the mandatory F1b lip-sync spend records
at `cinema/shots/controller.py:1922`.

TARGET SYMBOL: lip-sync price estimate for the pre-spend envelope.

```text
$ rg -n "LIPSYNC_DEFAULT|LIPSYNC_" cost_tracker.py cinema/shots/controller.py
cost_tracker.py:94:    "LIPSYNC_SYNCSOV3":    0.05,
cost_tracker.py:95:    "LIPSYNC_MUSETALK":    0.02,
cost_tracker.py:96:    "LIPSYNC_LATENTSYNC":  0.03,
cost_tracker.py:97:    "LIPSYNC_SYNCV2":      0.10,
cost_tracker.py:98:    "LIPSYNC_HEDRA":       0.10,
cost_tracker.py:99:    "LIPSYNC_KLING":       0.05,
cost_tracker.py:100:    "LIPSYNC_OMNIHUMAN":   0.10,
cost_tracker.py:101:    "LIPSYNC_AURORA":      0.05,
cost_tracker.py:102:    "LIPSYNC_DEFAULT":     0.05,
cinema/shots/controller.py:214:def _lipsync_cost_api_key(engine: object) -> str:
cinema/shots/controller.py:1922:                            self.cost_tracker.record_api_call(
```

`LIPSYNC_DEFAULT` is the existing fallback cost key used when cascade metadata
does not name the winner.

## Rule #13 - Symmetric / Sibling Audit

SHARED FENCE/FLAG/STATE: pre-spend budget gates for paid multi-call envelopes.

```text
$ rg -n "would_exceed_cost|would_exceed\\(" cost_tracker.py cinema/shots/controller.py tests/unit/test_budget_pre_spend_gate.py
cost_tracker.py:449:    def would_exceed(self, api_name: str) -> bool:
cost_tracker.py:468:    def would_exceed_cost(self, estimated_cost_usd: float) -> bool:
cinema/shots/controller.py:1049:            estimated_cost = API_COST_USD.get(engine.upper(), 0.0) + driving_cost
cinema/shots/controller.py:1050:            would_exceed_budget = self.cost_tracker.would_exceed_cost(estimated_cost)
cinema/shots/controller.py:1059:            would_exceed_budget = self.cost_tracker.would_exceed(engine)
cinema/shots/controller.py:1720:        if self.cost_tracker.would_exceed(target_api):
tests/unit/test_budget_pre_spend_gate.py:127:    def test_refuses_generation_when_would_exceed(self, tmp_path):
```

Sibling pattern: `generate_performance_take()` computes an envelope and uses
`would_exceed_cost(estimated_cost)` before dispatch when Mode-B driving synth is
structurally attached to performance capture (`controller.py:1041-1059`).
Motion dialogue overlay should mirror that pattern: compute video cost plus a
conservative `LIPSYNC_DEFAULT` when F1b is structurally required, then call
`would_exceed_cost()` before video dispatch.

Deferred sibling: the inventory row also notes intermediate failed lip-sync
cascade engine charges are untracked. `CostTracker.record_api_call()` documents
"Only call on the success path"; charging failed cascade attempts is a separate
policy and instrumentation change outside this scoped MEDIUM fix.

## Full-Shape Pattern Reference

Mirror `generate_performance_take()` at `cinema/shots/controller.py:1041-1067`:

- import `API_COST_USD` only at the gate site;
- compute a caller-owned `estimated_cost`;
- call `self.cost_tracker.would_exceed_cost(estimated_cost)`;
- on refusal, emit `BUDGET_EXCEEDED`, pause lifecycle, and return
  `{"success": False, "error_kind": "budget"}` before any paid provider call.

No HTTP endpoint or project-scoped route is involved; R-PID is N/A.

## The Fix

Scoped implementation in `cinema/shots/controller.py`:

- Replace the motion pre-spend check's single `would_exceed(target_api)` call
  with a combined estimate using `API_COST_USD[target_api]`.
- Add `API_COST_USD["LIPSYNC_DEFAULT"]` when the shot has dialogue and the
  resolved path will require the F1b lip-sync pass before approval.
- Keep the existing structured budget refusal shape and pre-provider-call
  placement.

Expected test changes:

- Add a focused regression in `tests/unit/test_f1b_dialogue_lipsync.py` proving
  the near-budget overlay path refuses before both video and lip-sync mocks.
- Update the existing motion budget precheck tests to assert the combined-cost
  helper shape without weakening their no-provider-call assertions.

## Verification the Operator/CI Will Run

Focused:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_f1b_dialogue_lipsync.py::TestGenerateMotionTakeOverlayWiring::test_overlay_dialogue_budget_gate_counts_mandatory_lipsync_before_video \
  tests/unit/test_budget_pre_spend_gate.py::TestPreSpendBudgetGate \
  -q
```

Smoke:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Residual Wave 2 gate blockers remain product-oracle absence and unrelated open
HTTP/auto-approve rows unless coordinator later reconciles this row after
operator2 GO.
