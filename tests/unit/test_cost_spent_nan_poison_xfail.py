"""R-VERIFY-TIER(B) pin — cost-spent-nan-poison (NEW, money; sibling of budget-nan on
the SPEND side).

Found by operator2 during Task-7 (costtracker-perf-uncounted) verification.

BUG: cost_tracker.py log() (line 287) does ``self.spent_usd += cost_usd`` with NO
math.isfinite guard.  A non-finite cost_usd (e.g. produced by
driving_video._cost_log via ``cost + 0.005 * float(duration_s)`` when duration_s is
NaN) poisons the in-process accumulator: 0.0 + NaN = NaN.  Both budget-gate methods
then silently disable enforcement because ``NaN > budget`` is always False in IEEE
754:

    would_exceed (:431)   — (NaN + cost) > budget   -> False  (gate silently passes)
    is_over_budget (:440) — NaN > budget             -> False  (gate silently passes)

Confirmed consequence: $100 of real spend recorded after the poison call yields
``is_over_budget() == False`` against a $10.00 cap, so the pipeline never stops.
Asymmetric to budget_usd, which IS guarded (_finite_budget_or_block, ADR-026) —
a Rule #13 symmetric-endpoint gap. PRE-EXISTING (record_api_call could always
poison) but Task-7 widened the entry points (log_api/log_llm now reach log()).

FIX (not yet landed): coerce non-finite cost to 0.0 and emit a WARNING at the
``log()`` chokepoint (fail-safe: keep the gate alive while flagging the bad value).
When the fix lands, ``spent_usd`` stays finite, ``is_over_budget()`` returns True
after the $100 real spend, and this xfail flips XPASS (strict=True) -> remove pin.
"""

import math
import pytest


@pytest.mark.xfail(
    strict=True,
    reason=(
        "cost-spent-nan-poison cost_tracker.py:287: log() does self.spent_usd += cost_usd "
        "with no math.isfinite guard; a NaN cost_usd poisons the accumulator so "
        "is_over_budget() always returns False (NaN > budget is False in IEEE 754). "
        "Fix: coerce non-finite cost->0.0 + WARNING at the log() chokepoint; "
        "then is_over_budget() returns True after real over-cap spend (xpass -> remove pin)."
    ),
)
def test_nan_cost_does_not_poison_budget_gate(tmp_path):
    """A NaN cost_usd must NOT disable the budget gate for subsequent real spend.

    Exercises the exact bug path:
      1. Construct a CostTracker with a $10.00 budget.
      2. Log a NaN cost via log_api() — this poisons self.spent_usd today.
      3. Log $100.00 of real spend — well over the $10.00 cap.
      4. Assert is_over_budget() is True  (FIXED behaviour: gate must still fire).
      5. Assert math.isfinite(tracker.spent_usd)  (FIXED behaviour: accumulator stays finite).

    Today (unfixed): step 2 sets spent_usd = NaN; step 4 returns False -> XFAIL.
    After fix: NaN is coerced to 0.0 at log(); spent_usd = 100.0 after step 3;
    is_over_budget() returns True -> XPASS.
    """
    from cost_tracker import CostTracker

    db = str(tmp_path / "cost.db")
    tracker = CostTracker(db_path=db, budget_usd=10.0)

    # Precondition: budget is set and accumulator starts clean.
    assert tracker.budget_usd == 10.0, "precondition: $10.00 budget must be active"
    assert tracker.spent_usd == 0.0, "precondition: accumulator must start at zero"

    # Step 2: inject the NaN cost — mirrors driving_video._cost_log when
    # duration_s is NaN (cost + 0.005 * float(NaN) = NaN).
    tracker.log_api(
        provider="x",
        model="y",
        operation="z",
        cost_usd=float("nan"),
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
