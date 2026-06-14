"""budget-nan (Wave-1 CRITICAL, ADR-026) — a non-finite budget cap must fail-safe BLOCK.

THE BUG (originally a strict-xfail pin; director2's §4 verify, a812ee4 /
wf_99bc3ff7-fe4):
  - cinema/core.py:99-104 reads ``budget_limit_usd`` and ``float(budget_usd)``
    SUCCEEDS on NaN/inf (the §4A bug class — ``float(NaN)`` does not raise).
  - cost_tracker.py stored it verbatim: ``self.budget_usd = budget_usd if
    budget_usd else None``; ``bool(nan) is True`` so a NaN was KEPT, not None.
  - ``would_exceed`` / ``is_over_budget`` then compare against NaN, which is
    ALWAYS False — so every pre-generation check passes and the post-generation
    halt never fires. A NaN budget DISABLED all spend enforcement for the whole
    session while masquerading as a set cap. ``+inf`` is the same shape (reads
    as limitless).

THE FIX (Wave-1 Task 6, 2026-06-14, ADR-026 — user-endorsed fail-safe BLOCK):
  cost_tracker.py coerces a non-finite (NaN/inf) or non-coercible budget cap to
  a blocking sentinel, mapping corruption onto the existing kept-negatives-block
  fail-safe (cost_tracker.__init__). ``None`` / ``0`` / ``0.0`` stay "no cap";
  finite values (incl. negatives) are unchanged.

This is now a LIVE REGRESSION (the strict-xfail pin was removed when the fix
flipped it). It asserts both that NaN is not stored verbatim AND that the gate
actually BLOCKS on a non-finite cap — the original bare "not stored as NaN"
assertion was fix-agnostic and would have passed a policy-VIOLATING
``None=unlimited`` coercion too, so the block-behavior assertions lock in the
user-endorsed policy.
"""
import math

import pytest

from cost_tracker import CostTracker


def _tracker(budget_usd):
    """A hermetic CostTracker (in-memory DB; no data/experiments.db side effect)."""
    return CostTracker(db_path=":memory:", budget_usd=budget_usd)


def test_nan_budget_is_not_stored_as_a_live_cap():
    """A NaN budget must not be stored verbatim — that silently bypasses both gates."""
    tracker = _tracker(float("nan"))
    assert not (
        isinstance(tracker.budget_usd, float) and math.isnan(tracker.budget_usd)
    ), (
        "NaN budget stored verbatim -> would_exceed/is_over_budget compare against NaN "
        "(always False) -> unbounded spend for the whole session (§4 completeness defect)"
    )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_budget_blocks_spend(bad):
    """A non-finite cap is corruption -> fail-safe BLOCK (ADR-026), never unlimited.

    Uses ``UNKNOWN_API`` so the cost-table lookup returns 0.0 — the gate logic
    (spent vs budget) is exercised independent of the API_COST_USD price table.
    """
    tracker = _tracker(bad)
    assert tracker.would_exceed("UNKNOWN_API") is True, (
        f"non-finite budget {bad!r} must block would_exceed pre-spend (fail-safe)"
    )
    tracker.spent_usd = 0.01
    assert tracker.is_over_budget() is True, (
        f"non-finite budget {bad!r} must trip is_over_budget after any spend"
    )


def test_none_budget_is_unlimited():
    """None = no cap (unchanged regression)."""
    tracker = _tracker(None)
    assert tracker.budget_usd is None
    assert tracker.would_exceed("UNKNOWN_API") is False
    tracker.spent_usd = 10_000.0
    assert tracker.is_over_budget() is False


@pytest.mark.parametrize("falsy", [0, 0.0])
def test_zero_budget_is_unlimited(falsy):
    """0 / 0.0 = the project-settings 'unlimited' sentinel (NF-2, unchanged)."""
    tracker = _tracker(falsy)
    assert tracker.budget_usd is None
    assert tracker.would_exceed("UNKNOWN_API") is False


def test_finite_budget_enforced_normally():
    """A normal finite cap gates as before (no regression)."""
    tracker = _tracker(10.0)
    assert tracker.budget_usd == 10.0
    assert tracker.would_exceed("UNKNOWN_API") is False   # spent 0 + cost 0 > 10 -> False
    tracker.spent_usd = 10.5
    assert tracker.would_exceed("UNKNOWN_API") is True     # 10.5 > 10 -> True
    assert tracker.is_over_budget() is True


def test_negative_budget_still_blocks():
    """A negative cap is the EXISTING fail-safe block (kept deliberately) — unchanged."""
    tracker = _tracker(-1.0)
    assert tracker.budget_usd == -1.0
    assert tracker.would_exceed("UNKNOWN_API") is True    # 0 > -1 -> True
    assert tracker.is_over_budget() is True                # 0 > -1 -> True


def test_garbage_string_budget_blocks():
    """A non-coercible cap reaching the constructor directly blocks (chokepoint defense).

    core.py pre-handles non-numeric strings upstream (-> None); this guards the
    direct/fresh-instance construction paths so garbage can't silently disable
    the gate there either.
    """
    tracker = _tracker("not-a-number")
    assert tracker.would_exceed("UNKNOWN_API") is True
