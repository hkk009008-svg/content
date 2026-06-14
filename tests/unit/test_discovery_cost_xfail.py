"""R-VERIFY-TIER(B) pins — cost-tracking defects confirmed by the hardening-campaign
discovery bug-hunt (logs/discovery-wf_13f9d2f6-f93.json, confirmed[4,5,7]).

BUG CLASS: API spend paths that should update the in-process ``spent_usd`` accumulator
(or look up costs with the correct key) silently record $0.00, undermining the budget
gate and cost visibility.

CATALOG:
  - confirmed[4] costtracker-perf-uncounted (cost_tracker.py:282,303 — W1:CRITICAL):
    ``log_api()`` and ``log_llm()`` write SQLite but do NOT increment ``self.spent_usd``;
    only ``record_api_call()`` does (:367).  Performance / image phases that call
    ``log_api()`` directly bypass the in-memory accumulator — budget gate sees $0 even
    after real spend, allowing unlimited over-run.  PINNED below.

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
# confirmed[4] — log_api / log_llm do not increment spent_usd
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="W1:CRITICAL:costtracker-perf-uncounted cost_tracker.py:282,303: log_api() "
    "writes to SQLite via self.log() but never does self.spent_usd += cost_usd "
    "(only record_api_call() does at :367). Performance/image phases that call "
    "log_api() directly leave spent_usd=0 so the budget gate always passes, "
    "allowing unbounded spend. Fix: increment spent_usd inside log_api (and "
    "log_llm); then this xpasses (strict) and the pin is removed.",
)
def test_log_api_increments_spent_usd(tmp_path):
    """log_api() must update spent_usd so the budget gate sees real spend."""
    from cost_tracker import CostTracker

    db = str(tmp_path / "cost.db")
    tracker = CostTracker(db_path=db, budget_usd=10.0)

    assert tracker.spent_usd == 0.0, "precondition: starts at zero"

    tracker.log_api(
        provider="comfyui",
        model="COMFYUI_PULID",
        operation="image_generation",
        cost_usd=0.04,
    )

    # The FIXED behaviour: log_api increments the in-process accumulator.
    # Current (buggy) behaviour: spent_usd stays 0.0 -> XFAIL today.
    assert tracker.spent_usd > 0.0, (
        "log_api() recorded SQLite cost but spent_usd remained 0.0 — "
        "the budget gate is blind to this spend (costtracker-perf-uncounted)"
    )


@pytest.mark.xfail(
    strict=True,
    reason="W1:CRITICAL:costtracker-perf-uncounted cost_tracker.py:303: log_llm() "
    "writes to SQLite via self.log() but never does self.spent_usd += cost_usd "
    "(only record_api_call() does at :367). LLM phases that call log_llm() directly "
    "leave spent_usd=0 so the budget gate always passes, allowing unbounded spend. "
    "Fix: increment spent_usd inside log_llm; then this xpasses (strict) and the "
    "pin is removed.",
)
def test_log_llm_increments_spent_usd(tmp_path):
    """log_llm() must update spent_usd so the budget gate sees real LLM spend."""
    from cost_tracker import CostTracker

    db = str(tmp_path / "cost.db")
    tracker = CostTracker(db_path=db, budget_usd=10.0)

    assert tracker.spent_usd == 0.0, "precondition: starts at zero"

    # claude-sonnet-4-6 is in PRICING: $3.00/M input, $15.00/M output
    # 100k input tokens -> $0.30; cost_usd > 0 if accumulated correctly.
    tracker.log_llm(
        model="claude-sonnet-4-6",
        operation="script_generation",
        input_tokens=100_000,
        output_tokens=1_000,
    )

    # The FIXED behaviour: log_llm increments the in-process accumulator.
    # Current (buggy) behaviour: spent_usd stays 0.0 -> XFAIL today.
    assert tracker.spent_usd > 0.0, (
        "log_llm() recorded SQLite cost but spent_usd remained 0.0 — "
        "the budget gate is blind to this LLM spend (costtracker-perf-uncounted)"
    )


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
