"""§4 nan-gate completeness — a NEW major site found by director2's §4 verify.

director2's authoritative verify of operator2's §4 nan-gate (a812ee4,
wf_99bc3ff7-fe4) ran an independent completeness sweep BEYOND the 5 §4A sites
and the 6 already-pinned auto_approve sites. It surfaced a third *shape* of the
NaN-defeats-a-gate bug class, in the budget-enforcement path — confirmed by
direct read + a behavioral probe (R-EVIDENCE).

THE BUG (major — unbounded spend):
  - cinema/core.py:99-104 reads ``budget_limit_usd`` and does ``float(budget_usd)``
    inside a try/except (TypeError, ValueError). ``float(nan)`` SUCCEEDS, so a NaN
    survives the cast (the §4A bug class — float(NaN) does not raise).
  - cost_tracker.py:170 stores it: ``self.budget_usd = budget_usd if budget_usd
    else None``. ``bool(nan) is True``, so NaN is STORED (not coerced to None).
  - CostTracker.would_exceed (:368) ``(spent + cost) > self.budget_usd`` and
    is_over_budget (:377) ``self.spent_usd > self.budget_usd`` both compare against
    NaN, which is ALWAYS False — so every pre-generation check passes and the
    post-generation halt never fires. A NaN budget DISABLES all spend enforcement
    for the whole session while masquerading as a set cap (budget_usd is not None).

This directly contradicts the cost_tracker.py:167-169 philosophy ("negatives block
all spend (fail-safe) rather than coercing to unlimited (fail-open on a typo)") — a
NaN is a typo/garbage value, yet it fails OPEN to unlimited.

DISPOSITION (mirrors operator2's handling of their 6 auto_approve sites): SURFACED
+ xfail(strict)-PINNED, NOT edited (R-VERIFY-TIER B). Budget enforcement is
cross-cutting (coordinator/Cat-B lane, last touched by 89e386d), so the fix +
its DIRECTION are a cross-lane call:
  OPEN DESIGN QUESTION (surface, do not silently decide): should a NaN budget be
  (a) fail-safe BLOCK (consistent with the negative-value philosophy above), or
  (b) coerced to None = unlimited (consistent with the falsy->None convention)?
  These diverge. Recommend folding into the consolidated "auto_approve + lipsync +
  nan-gate hardening" epic with a Pair-A/coordinator co-sign, using the shared
  cinema.context._finite_or landed in a812ee4.

This pin is fix-AGNOSTIC: it only asserts NaN is not STORED as a live budget, which
holds for either resolution. It flips to a strict CI error when the bug is fixed.
"""
import math

import pytest

from cost_tracker import CostTracker


@pytest.mark.xfail(
    strict=True,
    reason="§4 completeness (major): a NaN budget_limit_usd survives float() (cinema/core.py:101) "
    "and bool(nan)=True stores it (cost_tracker.py:170), so would_exceed/is_over_budget compare "
    "against NaN -> always False -> unbounded spend, masquerading as a set cap. Fix (direction is "
    "an open design call: fail-safe block vs None=unlimited) coerces NaN off the live-budget slot; "
    "this then xpasses (strict) and the pin is removed.",
)
def test_nan_budget_is_not_stored_as_a_live_cap():
    """A NaN budget must not be stored verbatim — that silently bypasses both gates."""
    tracker = CostTracker(budget_usd=float("nan"))
    assert not (
        isinstance(tracker.budget_usd, float) and math.isnan(tracker.budget_usd)
    ), (
        "NaN budget stored verbatim -> would_exceed/is_over_budget compare against NaN "
        "(always False) -> unbounded spend for the whole session (§4 completeness defect)"
    )
