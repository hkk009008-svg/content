"""C-1 pin — shot-spent-usd-never-written (CRITICAL, money-loss).

ROW: shot-spent-usd-never-written
FILE: cinema/auto_approve.py:627 (read site) + cost_tracker.py (missing bridge)
BUG: the per-shot budget veto _shot_over_budget reads shot_state.get("spent_usd", 0).
     NO production code writes "spent_usd" into any shot dict, so the veto always
     sees $0.00 and is structurally DEAD. The CostTracker DOES persist per-call
     spend tagged with shot_id (cost_log.shot_id column), but there is no
     CostTracker.get_shot_spent(shot_id) bridge to read it back, and nothing
     injects that SUM into shot_state before check_gate.

FIX (not landed, director2/Pair-B owns): add
     CostTracker.get_shot_spent(shot_id) -> float = SQLite SUM(cost_usd) WHERE
     shot_id=?, then inject it into shot_state in the gate loop
     (cinema/review/controller.py) before check_gate. This pin covers the
     bridge METHOD (the testable unit of the fix); the gate-loop injection that
     makes the veto actually fire end-to-end is integration-level (needs a full
     ShotController harness — tracked test-infeasible, cf. perf-phase-no-gate).

WHY NON-VACUOUS + FLIP-CORRECT: real spend is logged against two distinct
     shot_ids; the test asserts get_shot_spent returns the per-shot SUM for one
     (cross-shot isolation proves it is not just summing everything). Today the
     method does not exist -> the call raises AttributeError -> XFAIL. When the
     bridge lands, get_shot_spent returns the SUM -> XPASS (strict) -> remove pin.
"""
import pytest


@pytest.mark.xfail(
    strict=True,
    reason=(
        "C-1:CRITICAL:shot-spent-usd-never-written cinema/auto_approve.py:627 + "
        "cost_tracker.py: the per-shot veto reads shot_state['spent_usd'] which no "
        "production code writes, so it is dead; the bridge "
        "CostTracker.get_shot_spent(shot_id) = SQLite SUM(cost_usd) WHERE shot_id=? "
        "does not exist. Fix = add get_shot_spent + inject into shot_state before "
        "check_gate; then this xpasses and the pin is removed."
    ),
)
def test_cost_tracker_get_shot_spent_sums_per_shot(tmp_path):
    """CostTracker.get_shot_spent(shot_id) must return the per-shot SQLite SUM.

    FIXED behaviour: spend logged against a shot_id is retrievable per-shot so
    the gate loop can bridge it into shot_state and the per-shot veto can fire.

    Today (buggy): the method does not exist -> AttributeError -> XFAIL.
    """
    from cost_tracker import CostTracker

    tracker = CostTracker(db_path=str(tmp_path / "cost.db"), budget_usd=100.0)
    # Real per-shot spend: $4 + $6 = $10 on shot_001; $99 on a DIFFERENT shot.
    tracker.log_api(provider="kling", model="KLING", operation="gen", cost_usd=4.0, shot_id="shot_001")
    tracker.log_api(provider="google", model="VEO", operation="gen", cost_usd=6.0, shot_id="shot_001")
    tracker.log_api(provider="ltx", model="LTX", operation="gen", cost_usd=99.0, shot_id="shot_002")

    # FIXED behaviour: the bridge returns the per-shot SUM (cross-shot isolated).
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
