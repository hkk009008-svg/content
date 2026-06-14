"""Discovery-run debt pins — W1:CRITICAL auto_approve inf/NaN bypass family.

Surfaced by the program-hardening Phase-0 discovery workflow
(logs/discovery-wf_13f9d2f6-f93.json, confirmed[0] + confirmed[1]),
independently confirmed by two refuter agents in the same workflow.

## confirmed[0] — id=aa-inf-scorebypass
Target: cinema/auto_approve.py:424,445,456,468
  (_best_take_composite, _best_take_identity, _best_take_motion_score,
  _best_take_lipsync)

A metadata score of ``float('inf')`` (valid in Python's json.load which
defaults to allow_nan=True) passes through every ``float()`` cast and every
``max()`` call unchanged, leaving ``best = inf``.  All four gate predicates
are of the form ``best < threshold``; ``inf < 0.97`` (or ``< 0.85`` / ``< 0.7``
/ ``< 0.8``) is always False, so NO veto fires and auto_approved=True is
returned regardless of actual quality.

Pinned via the IMAGE gate (composite=inf) because it is the cleanest
single-score repro: only one score field drives the predicate, so no
second field needs to be set to inf to bypass a second independent rule
(contrast: motion gate has two independent score rules — identity_score
AND motion_fidelity/motion_score — both must be inf to bypass both).

## confirmed[1] — id=aa-budget-nan-veto
Target: cinema/auto_approve.py:584-595 (_shot_over_budget)

If ``shot_state['spent_usd']`` is NaN (written by json.load from a project
file containing the bare token NaN), the budget-overrun veto is silently
skipped.  ``nan or 0`` keeps NaN (NaN is truthy in Python, so the or-0
idiom does NOT coerce it to 0), and ``float(nan) > multiplier * budget``
evaluates to False under IEEE 754 NaN semantics, so the function returns
False — "not over budget" — regardless of the intended spend.

WHY NOT FIXED THIS SESSION: the fix is a one-chokepoint _finite_or guard
in the affected helpers (same pattern as the NaN-threshold family pinned in
test_auto_approve_nangate_xfail.py, which targets the threshold *read* path
rather than the score *accumulation* path).  Cross-lane scope audit is
owed before editing; CI pins it here so the next session's CI, not an ad-hoc
agent, detects when the guard lands.

Each pin is ``xfail(strict=True)`` so CI flags it as XPASS the moment the
guard is added — prompting removal of the case (or a reason update).
"""
from __future__ import annotations

import pytest

from cinema.auto_approve import (
    AutoApproveConfig,
    check_gate,
    _shot_over_budget,
)


def _config_image_composite_only(**overrides) -> AutoApproveConfig:
    """AutoApproveConfig that exercises only the image-composite score rule.

    Disables the cascade-fallback veto so the test can confirm the composite
    threshold bypass in isolation (a take with composite=inf has no
    cascade_metadata.fallback=True, so that rule would not fire anyway, but
    disabling it makes the intent explicit).
    """
    return AutoApproveConfig(
        image_veto_on_fallback=False,
        final_require_human_if_upstream_auto=False,
        **overrides,
    )


# ---------------------------------------------------------------------------
# confirmed[0] — aa-inf-scorebypass
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "W1:CRITICAL:aa-inf-scorebypass (discovery wf_13f9d2f6-f93 confirmed[0]): "
        "a take with composite=inf causes _best_take_composite to return inf; "
        "inf < threshold is always False so the image-composite veto never fires "
        "and check_gate returns auto_approved=True. "
        "Fix: add math.isfinite guard in _best_take_composite (and the three sibling "
        "helpers) so inf scores are treated as invalid and the gate rejects them."
    ),
)
def test_inf_composite_score_must_not_auto_approve():
    """A take with composite=inf must NOT pass the image gate (auto_approved must be False).

    Demonstrates the ``inf < threshold`` bypass: ``_best_take_composite``
    returns inf, ``inf < 0.97`` is False, so NO veto fires today.
    The CORRECT behavior (what the fix will produce) is auto_approved=False
    (the inf score is invalid and must be treated as a gate failure).
    Today the bug is live, so this test XFAIL (auto_approved is True, not False).
    """
    inf_take = {"metadata": {"composite": float("inf")}}
    config = _config_image_composite_only()

    result = check_gate(
        "image",
        shot_state={},
        project={},
        takes=[inf_take],
        config=config,
    )

    # CORRECT behavior: inf is not a valid quality score; the gate must veto.
    assert not result.auto_approved, (
        "inf composite score bypassed the image gate "
        "(inf < threshold is always False — no veto fired)"
    )


# ---------------------------------------------------------------------------
# confirmed[1] — aa-budget-nan-veto
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "W1:CRITICAL:aa-budget-nan-veto (discovery wf_13f9d2f6-f93 confirmed[1]): "
        "_shot_over_budget uses `spent = shot_state.get('spent_usd', 0) or 0`; "
        "NaN is truthy so `nan or 0` returns nan, and `float(nan) > threshold` is "
        "always False under IEEE 754, so the budget veto silently returns False even "
        "when spent_usd is NaN. "
        "Fix: replace the or-0 idiom with math.isfinite(spent) or _finite_or so NaN "
        "spent_usd is detected and the veto fires (returns True)."
    ),
)
def test_nan_spent_usd_must_fire_budget_veto():
    """A NaN spent_usd must cause _shot_over_budget to return True (veto fires).

    The ``or 0`` idiom at auto_approve.py:594 does NOT coerce NaN because NaN
    is truthy; ``float(nan) > multiplier * budget`` is then always False per
    IEEE 754.  The CORRECT behavior (what the fix will produce) is True —
    an invalid spend value must fail-closed (veto fires, manual review required).
    Today the bug is live: _shot_over_budget returns False, so this test XFAIL.

    Project shape: 2 shots, budget $100 total -> $50 per shot.
    spent_usd = NaN, multiplier = 1.5 -> threshold = $75.
    NaN > $75 is False (bug); should be True (fix: NaN is invalid, treat as veto).
    """
    shot_state = {"spent_usd": float("nan")}
    project = {
        "global_settings": {"budget_limit_usd": 100.0},
        "scenes": [{"shots": [shot_state, {}]}],
    }

    result = _shot_over_budget(shot_state, project, multiplier=1.5)

    # CORRECT behavior: NaN spend is invalid; fail-closed means the veto fires.
    assert result is True, (
        "NaN spent_usd silently bypassed the budget veto "
        "(`nan or 0` keeps nan; `nan > threshold` is always False)"
    )
