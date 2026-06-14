"""Operator-1 post-commit verification of nan-gate commits 7b4d377 + bf1034a.

PROVENANCE: independent implementer!=verifier pass (workflow wf_25dce560-524).
The two commits themselves PASS verification (all 8 guards mutation-proven
load-bearing; all 35 new tests coupled/non-vacuous; 167 targeted + 2425 full-suite
green). But the Rule#13 completeness sweep surfaced sibling sites of the SAME
non-finite hazard class that the commits' audit boundary did NOT extend to.

These are NOT regressions in 7b4d377/bf1034a — they are pre-existing class-siblings
the audit (wf_cc849e2d) scoped out. Pinned strict=True so CI tracks them and
XPASS-flags the fix landing (R-VERIFY-TIER(B): a confirmed-but-unfixed defect ships
a strict-xfail pin in the confirming session). Fix disposition = director-1's
cross-lane nan-gate hardening epic.

A third confirmed sibling — phase_c_assembly.py:346 (img2img_denoise -> node 17
denoise, identical clamp-luck; + a continuity_options=null AttributeError) — is
Pair-B lane AND test-infeasible without extracting a helper from the inline
generate_ai_broll body; reported cross-pair (do NOT pin in someone else's lane with
a vacuous abstract test).
"""
from __future__ import annotations

import math

import pytest


def test_nan_pulid_weight_must_not_reach_node_100():
    """Regression (W1:CRITICAL:pulid-nan-node100, FIXED): a non-finite PuLID
    node-100 weight/start_at/end_at must never be written.

    STRENGTHENED beyond the original weight-only pin to also assert start_at/end_at
    (the pin-blind siblings at quality_max.py:564-565 operator-1 flagged): a
    weight-only fix would XPASS the old single-assert pin while leaving those two
    open. _inject_identity now wraps all three node-100 writes in _finite_or
    (mirroring nodes 700/701), so each non-finite value falls back to its per-input
    default (0.85 / 0.0 / 0.90). Reachable via controller.py pulid_weight_override
    (continuity config, no overlay chokepoint) -> params -> node 100."""
    from quality_max import _inject_identity

    wf = {"100": {"inputs": {}}, "700": {"inputs": {}}}
    params = {"pulid_weight": float("nan"), "pulid_start_at": float("nan"),
              "pulid_end_at": float("nan"), "lora_strength_model": 0.8,
              "lora_strength_clip": 0.8}
    _inject_identity(wf, "alice.safetensors", None, params, True,
                     char_lora_strength=0.5)
    node100 = wf["100"]["inputs"]
    for key in ("weight", "start_at", "end_at"):
        assert math.isfinite(node100[key]), (
            f"node 100 PuLID {key} {node100[key]!r} is non-finite "
            f"(non-finite reached the PuLID node — _finite_or guard missing/reverted)"
        )


@pytest.mark.xfail(
    strict=True,
    reason="OP1-VERIFY sibling of bf1034a: get_workflow_params crashes with "
    "AttributeError when continuity_options is JSON null. settings.get("
    "'continuity_options', {}) returns None (not the {} default — the key is "
    "present-but-null), then None.get('img2img_denoise') raises "
    "(workflow_selector.py:515). The sibling site quality_max.py:1041 already has "
    "the isinstance(_co, dict) guard this block lacks. Pair-A; fold into the epic.",
)
def test_null_continuity_options_must_not_crash_param_resolution():
    """A JSON-null continuity_options must not crash param resolution; the
    img2img overlay should simply be skipped, leaving the template default.
    Currently xfails (AttributeError); XPASSes when the dict-guard is added."""
    from workflow_selector import get_workflow_params

    p = get_workflow_params("portrait", settings={"continuity_options": None})
    assert isinstance(p, dict) and p, "expected template params, got a crash/empty"
