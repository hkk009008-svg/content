"""Regression test — shot-spent-usd-never-written (C-1) bridge fix.

ROW: shot-spent-usd-never-written (C-1, W2:CRITICAL)
BUG: the per-shot budget veto _shot_over_budget (cinema/auto_approve.py:608)
     reads shot_state.get("spent_usd", 0). No production code ever wrote
     "spent_usd" into any shot dict (only test fixtures), so the veto was
     structurally DEAD (always saw $0.00).

     The CostTracker DID persist per-call spend tagged with shot_id in the
     cost_log SQLite table, but there was no CostTracker.get_shot_spent(shot_id)
     bridge to read it back, and nothing injected that SUM into shot_state
     before check_gate.

FIX (this commit):
  Part 1 — BRIDGE (cost_tracker.py): CostTracker.get_shot_spent(shot_id) -> float
    = SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_log WHERE shot_id = ?
    Returns 0.0 for unknown/empty shot_id; coerces non-finite SQLite values to
    0.0 (defense-in-depth, cost-spent-nan-poison symmetric guard).
  Part 2 — INJECTION (cinema/review/controller.py): caller-injection before
    check_gate() at the SINGLE production call site (controller.py:324).
    shot_state["spent_usd"] = self._core.cost_tracker.get_shot_spent(shot["id"])
    No auto_approve.py edit needed; cost_tracker is reachable via self._core.

This test covers the bridge METHOD unit (the testable unit of the fix).
The gate-loop injection end-to-end is integration-level (needs a full
ShotController harness — test-infeasible, cf. perf-phase-no-gate).
"""
import pytest


def test_cost_tracker_get_shot_spent_sums_per_shot(tmp_path):
    """CostTracker.get_shot_spent(shot_id) returns the per-shot SQLite SUM.

    Real spend is logged against two distinct shot_ids; the test asserts
    get_shot_spent returns the per-shot SUM for one (cross-shot isolation
    proves it is not just summing everything).
    """
    from cost_tracker import CostTracker

    tracker = CostTracker(db_path=str(tmp_path / "cost.db"), budget_usd=100.0)
    # Real per-shot spend: $4 + $6 = $10 on shot_001; $99 on a DIFFERENT shot.
    tracker.log_api(provider="kling", model="KLING", operation="gen", cost_usd=4.0, shot_id="shot_001")
    tracker.log_api(provider="google", model="VEO", operation="gen", cost_usd=6.0, shot_id="shot_001")
    tracker.log_api(provider="ltx", model="LTX", operation="gen", cost_usd=99.0, shot_id="shot_002")

    # Bridge must exist.
    assert hasattr(CostTracker, "get_shot_spent"), (
        "CostTracker.get_shot_spent(shot_id) bridge is missing — the per-shot "
        "budget veto reads shot_state['spent_usd'] which is never written "
        "(shot-spent-usd-never-written, C-1)"
    )
    got = tracker.get_shot_spent("shot_001")
    assert got == pytest.approx(10.0), (
        f"get_shot_spent('shot_001')={got!r}, expected 10.0 (the per-shot SUM); "
        "shot_002's $99 must not leak in"
    )

    # Cross-shot isolation: shot_002 must not bleed into shot_001.
    got_002 = tracker.get_shot_spent("shot_002")
    assert got_002 == pytest.approx(99.0), (
        f"get_shot_spent('shot_002')={got_002!r}, expected 99.0"
    )

    # Unknown shot_id must return 0.0 (not raise).
    got_unknown = tracker.get_shot_spent("shot_999")
    assert got_unknown == 0.0, (
        f"get_shot_spent for unknown shot_id returned {got_unknown!r}, expected 0.0"
    )

    # Empty shot_id must return 0.0 (guard against bare queries).
    got_empty = tracker.get_shot_spent("")
    assert got_empty == 0.0, (
        f"get_shot_spent('') returned {got_empty!r}, expected 0.0"
    )
