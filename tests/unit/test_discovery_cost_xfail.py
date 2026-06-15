"""R-VERIFY-TIER(B) pins — cost-tracking defects confirmed by the hardening-campaign
discovery bug-hunt (logs/discovery-wf_13f9d2f6-f93.json, confirmed[4,5,7]).

BUG CLASS: API spend paths that should update the in-process ``spent_usd`` accumulator
(or look up costs with the correct key) silently record $0.00, undermining the budget
gate and cost visibility.

CATALOG:
  - confirmed[4] costtracker-perf-uncounted (cost_tracker.py — W1:CRITICAL): FIXED in
    Wave-1 Task 7.  ``log()`` (the sole write chokepoint that log_api/log_llm delegate
    to) now increments ``self.spent_usd``; ``record_api_call()``'s duplicate increment
    was removed; and the shared ``cost_tracker`` is threaded through
    ``performance/_router.dispatch`` into the 4 performance phases so per-shot spend
    lands on the accumulator the budget gate reads.  Live regression:
    tests/unit/test_costtracker_perf_uncounted_regression.py (the former two xfail pins
    flipped XPASS and were promoted there).

  - confirmed[5] lipsync-postproc-costkey (controller.py — W2:MAJOR): FIXED.
    The postprocess lip_sync branch now shares the motion path's
    ``LIPSYNC_<ENGINE>`` cost-key normalization, including ``LIPSYNC_DEFAULT``
    when cascade metadata omits an engine. Live regression:
    tests/unit/test_postprocess_audio_propagation.py::
    TestApplyCorrectionFlagPropagation::
    test_lip_sync_variant_records_namespaced_lipsync_cost. The former direct
    ``record_api_call("syncsov3")`` xfail was deleted because it did not exercise
    the controller call site.

  - confirmed[7] lipsync-precheck-cascade-gap (controller.py:1655 — W2:MEDIUM):
    ``would_exceed(target_api)`` checks only the video-API cost; the mandatory F1b
    lipsync cascade fires unconditionally afterwards and its cost (~$0.05-0.10/shot)
    is not accounted for.  A shot right below the cap passes the gate and then pushes
    cumulative spend over budget.  TEST-INFEASIBLE at unit level — the gate is embedded
    inside ``generate_motion_take()``, a ~400-line method with deep ShotController
    dependencies (SQLite project state, lifecycle FSM, ComfyUI worker pool, cascade
    runner).  No clean seam exists to exercise the gate logic in isolation without a
    full integration harness.  Documented for the epic; no pin.

When a defect is fixed its xfail flips to XPASS (strict=True) → delete that pin.
"""


# ---------------------------------------------------------------------------
# confirmed[4] — costtracker-perf-uncounted: FIXED in Wave-1 Task 7.
#   log()/log_api()/log_llm() now increment spent_usd at the log() chokepoint and
#   the shared cost_tracker is threaded through performance/_router.dispatch into
#   the 4 performance phases. The two former xfail pins (test_log_api_increments_
#   spent_usd / test_log_llm_increments_spent_usd) flipped XPASS and were promoted
#   to live regressions in tests/unit/test_costtracker_perf_uncounted_regression.py.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# confirmed[5] — postprocess lipsync cost key missing LIPSYNC_ prefix
#   FIXED. Live regression:
#   tests/unit/test_postprocess_audio_propagation.py::
#   TestApplyCorrectionFlagPropagation::
#   test_lip_sync_variant_records_namespaced_lipsync_cost.
# ---------------------------------------------------------------------------
