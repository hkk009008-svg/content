"""R-VERIFY-TIER(B) debt pins — NOVEL NaN-gate family in cinema/auto_approve.py.

Surfaced by operator2's independent §4 completeness sweep (wf_2ca5b0ae-e26) and
CONFIRMED by direct read.  These are NOT in director2's PM7 §4A brief — the brief's
manual sweep found the *threshold-comparison* sites (``score < floor``) but missed
this *rule-registration* family: each numeric auto-approve threshold is read via
``AutoApproveConfig.from_project`` → ``_get`` (a bare ``raw.get`` with NO float
coercion, auto_approve.py:118-119) and then gates rule registration with
``if config.<field> > 0:``.  A NaN field makes ``nan > 0`` False, so the veto rule
is **never registered** and the gate silently passes everything:

  - image_min_composite (auto_approve.py:287)      -> every keyframe auto-approved, no composite check
  - image_max_spent_multiplier (:326)              -> over-budget veto disabled -> unbounded per-shot spend
  - motion_min_identity (:346)                     -> every motion take passes identity unconditionally
  - motion_min_motion_score (:360)                 -> motion-quality veto disabled
  - final_min_lipsync (:388/:390)                  -> final-gate lipsync check disabled

A 6th variant — image_min_composite_fallback (:285) — is a *predicate-threshold*
corruption rather than a rule drop (a valid image_min_composite registers the rule,
but a NaN fallback makes ``best_composite < nan`` False for fallback-engine takes);
it is fixed by the SAME chokepoint and is not separately pinned here.

WHY NOT FIXED THIS SESSION (lane discipline): auto_approve.py is a SHARED subsystem
whose image/identity gates (image_min_composite, motion_min_identity) are Pair-A's
domain (recent history: tier-aware composite default 8cf0f07, identity-score fallback
c917bc1).  Per the §3 precedent (operator2 surfaced auto-approve siblings rather than
unilaterally editing them) and Rule #23 (a Pair-B fix here would change which sites
Pair-A touches -> Tier A co-sign), operator2 SURFACES this family (verification-report
to director2 + cross-lane to Pair-A) and pins it for CI instead of editing Pair-A's
gates.  RECOMMENDED FIX (one chokepoint): a ``_get_finite(key, default)`` in
``from_project`` = ``_finite_or(raw.get(key, default), default)`` over the 6 numeric
fields, using the shared ``cinema.context._finite_or`` operator2 landed this session.

Each pin is ``xfail(strict=True)`` so CI — not the next session's agents —
re-verifies, and the pin flips to a HARD failure the moment the gate is fixed
(prompting removal of that case).
"""
from __future__ import annotations

import pytest

from cinema.auto_approve import (
    AutoApproveConfig,
    _rules_for_image,
    _rules_for_motion,
    _rules_for_final,
)


def _config_with_auto_approve(**auto_approve_overrides) -> AutoApproveConfig:
    """Build an AutoApproveConfig from a project carrying the given nan/inf
    auto_approve sub-keys (the realistic on-disk shape: project.json
    global_settings.auto_approve.<key>)."""
    return AutoApproveConfig.from_project(
        {"global_settings": {"auto_approve": auto_approve_overrides}}
    )


_GATE_RULES = {
    "image": _rules_for_image,
    "motion": _rules_for_motion,
    "final": _rules_for_final,
}

# (setting_key, gate, expected_rule_name)
_NAN_GATE_CASES = [
    ("image_min_composite", "image", "image_composite_below_threshold"),
    ("image_max_spent_multiplier", "image", "image_over_budget"),
    ("motion_min_identity", "motion", "motion_identity_below_threshold"),
    ("motion_min_motion_score", "motion", "motion_score_below_threshold"),
    ("final_min_lipsync", "final", "final_lipsync_below_threshold"),
]


@pytest.mark.xfail(
    strict=True,
    reason="NOVEL §4 sweep family (wf_2ca5b0ae-e26): a NaN auto_approve threshold "
    "makes `if config.<field> > 0` False so the veto rule is never registered and "
    "the gate silently passes everything. Fix = finite-guard the numeric reads in "
    "AutoApproveConfig.from_project via cinema.context._finite_or. Cross-lane "
    "(Pair-A image/identity domain) -> director2 + Pair-A disposition owed.",
)
@pytest.mark.parametrize("setting_key,gate,rule_name", _NAN_GATE_CASES)
def test_nan_threshold_still_registers_veto_rule(setting_key, gate, rule_name):
    """A NaN on an auto-approve numeric threshold must NOT drop its veto rule."""
    cfg = _config_with_auto_approve(**{setting_key: float("nan")})
    rules = _GATE_RULES[gate](cfg)
    rule_names = {r.name for r in rules}
    assert rule_name in rule_names, (
        f"NaN {setting_key} dropped veto rule {rule_name!r} "
        f"(nan > 0 is False) -> auto-approve gate silently disabled"
    )
