"""Regression test — cost-spent-nan-poison fix (W2:CRITICAL).

Bug: cost_tracker.py log() line 287 had no math.isfinite guard on cost_usd.
A NaN cost poisoned self.spent_usd → NaN, making both budget gate methods
silently return False (NaN > budget is always False in IEEE 754):
  would_exceed(:431)   — (NaN + cost) > budget   -> False (gate dead)
  is_over_budget(:440) — NaN > budget             -> False (gate dead)

Fix (cost-spent-nan-poison, W2:CRITICAL, landed with this commit):
  1. log() coerces non-finite cost_usd to 0.0 + emits WARNING (fail-safe:
     gate stays ALIVE for real subsequent spend).
  2. would_exceed / is_over_budget guard non-finite self.spent_usd directly
     (defense-in-depth, Rule #13 symmetric-endpoint gap vs budget_usd guard).

Asymmetric-to-budget_usd: budget_usd is guarded at construction via
_finite_budget_or_block (ADR-026); spent_usd was the missing sibling.
"""

import math
import pytest
import warnings


def test_nan_cost_does_not_poison_budget_gate(tmp_path):
    """A NaN cost_usd must NOT disable the budget gate for subsequent real spend.

    Exercises the exact bug path:
      1. Construct a CostTracker with a $10.00 budget.
      2. Log a NaN cost via log_api() — this poisoned self.spent_usd pre-fix.
      3. Log $100.00 of real spend — well over the $10.00 cap.
      4. Assert is_over_budget() is True  (gate must still fire).
      5. Assert math.isfinite(tracker.spent_usd)  (accumulator stays finite).
    """
    from cost_tracker import CostTracker

    db = str(tmp_path / "cost.db")
    tracker = CostTracker(db_path=db, budget_usd=10.0)

    # Precondition: budget is set and accumulator starts clean.
    assert tracker.budget_usd == 10.0, "precondition: $10.00 budget must be active"
    assert tracker.spent_usd == 0.0, "precondition: accumulator must start at zero"

    # Step 2: inject the NaN cost — mirrors driving_video._cost_log when
    # duration_s is NaN (cost + 0.005 * float(NaN) = NaN).
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        tracker.log_api(
            provider="x",
            model="y",
            operation="z",
            cost_usd=float("nan"),
        )
    # The fix must emit a WARNING for the bad value.
    assert any("cost-spent-nan-poison" in str(w.message) or "Non-finite" in str(w.message)
               for w in caught), (
        "log() must emit a WARNING when cost_usd is non-finite "
        "(cost-spent-nan-poison coercion guard)"
    )

    # Step 3: log $100.00 of real spend — 10x over the $10.00 cap.
    tracker.log_api(
        provider="video",
        model="KLING_NATIVE",
        operation="video_generation",
        cost_usd=100.0,
    )

    # FIXED behaviour assertion 1: gate must detect the over-budget condition.
    assert tracker.is_over_budget() is True, (
        f"is_over_budget() returned False with spent_usd={tracker.spent_usd!r} "
        f"against a $10.00 cap — NaN cost poisoned the accumulator and disabled "
        "the budget gate (cost-spent-nan-poison)"
    )

    # FIXED behaviour assertion 2: accumulator must remain finite.
    assert math.isfinite(tracker.spent_usd), (
        f"spent_usd={tracker.spent_usd!r} is not finite — the NaN cost from "
        "log_api() was not coerced at the log() chokepoint (cost-spent-nan-poison)"
    )
