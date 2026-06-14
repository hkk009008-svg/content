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

  - confirmed[5] lipsync-postproc-costkey (controller.py:2442-2446 — W2:MAJOR):
    the postprocess lip_sync branch passes the raw engine name (e.g. ``"syncsov3"``) to
    ``record_api_call()``.  ``API_COST_USD`` keys are namespaced ``LIPSYNC_<ENGINE>``
    (e.g. ``"LIPSYNC_SYNCSOV3"``), so the lookup returns 0.0 and records $0 cost.
    The generate-motion path at :1858 correctly prefixes ``f"LIPSYNC_{engine}"``.
    PINNED below.

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
import pytest


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
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="W2:MAJOR:lipsync-postproc-costkey controller.py:2442-2446: the postprocess "
    "lip_sync branch calls record_api_call(_ls_engine) where _ls_engine is the raw "
    "cascade engine name (e.g. 'syncsov3'). API_COST_USD keys are namespaced as "
    "LIPSYNC_<ENGINE> (e.g. 'LIPSYNC_SYNCSOV3'), so the lookup returns 0.0 and "
    "records $0 cost. The generate-motion path at :1858 correctly prefixes "
    "f'LIPSYNC_{engine}'. Fix: apply the same LIPSYNC_ prefix in the postprocess "
    "branch; then this xpasses (strict) and the pin is removed.",
)
def test_postprocess_lipsync_costkey_resolves_nonzero(tmp_path):
    """record_api_call with a LIPSYNC_-namespaced key must resolve a nonzero cost.

    The postprocess path at controller.py:2444 passes the raw engine name to
    record_api_call(), skipping the LIPSYNC_ prefix.  This test exercises
    record_api_call() directly, mirroring both the buggy call and the correct call,
    and asserts the FIXED behaviour: a priced LIPSYNC_* key must produce nonzero
    spend.
    """
    from cost_tracker import CostTracker, API_COST_USD

    db = str(tmp_path / "cost.db")
    tracker = CostTracker(db_path=db, budget_usd=10.0)

    # Confirm the table HAS a priced entry for the engine under the correct key.
    assert API_COST_USD.get("LIPSYNC_SYNCSOV3", 0.0) > 0.0, (
        "precondition: LIPSYNC_SYNCSOV3 must be priced in API_COST_USD"
    )
    # Confirm the bare engine name (the bug) resolves to 0.
    assert API_COST_USD.get("SYNCSOV3", 0.0) == 0.0, (
        "precondition: bare SYNCSOV3 must NOT be in API_COST_USD (that is the bug)"
    )

    # --- Reproduce the BUGGY postprocess call (bare engine name, no prefix) ---
    # At controller.py:2444 the cascade_metadata["engine"] is e.g. "syncsov3".
    buggy_engine = "syncsov3"
    tracker.record_api_call(buggy_engine, operation="lipsync")

    # The FIXED behaviour: after the fix, spent_usd reflects a real lipsync cost.
    # Current (buggy) behaviour: the unprefixed key resolves to $0.00, so
    # spent_usd stays 0.0 after the call -> XFAIL today.
    assert tracker.spent_usd > 0.0, (
        f"record_api_call({buggy_engine!r}) resolved to $0.00 because the "
        "LIPSYNC_ prefix is missing — postprocess lipsync cost is silently "
        "untracked (lipsync-postproc-costkey)"
    )
