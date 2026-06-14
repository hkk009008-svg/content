"""Wave-1 regressions — nan-gate sibling sites of 7b4d377 + bf1034a (now FIXED).

PROVENANCE: surfaced by operator-1's independent implementer!=verifier sweep
(workflow wf_25dce560-524) of nan-gate commits 7b4d377 + bf1034a. Those commits
themselves PASSED verification (8 guards mutation-proven; 35 tests coupled). The
Rule#13 completeness sweep then surfaced sibling sites of the SAME non-finite hazard
class outside their audit boundary, pinned strict=True (R-VERIFY-TIER(B): a
confirmed-but-unfixed defect ships a strict-xfail pin in the confirming session).

Both Pair-A siblings were FIXED in Wave-1 of the program-hardening campaign and the
strict-xfail pins removed -> these are now LIVE regressions (they go RED if the guard
is reverted), strengthened beyond the original single-assert pins where noted:
  - pulid-nan-node100     -> quality_max.py node-100 weight/start_at/end_at _finite_or
  - null-continuity-crash -> workflow_selector.py:515 dict-guard

A third confirmed sibling (phase_c_assembly img2img clamp-luck) is Pair-B lane and was
addressed separately in that lane.
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


def test_null_continuity_options_must_not_crash_param_resolution():
    """Regression (W1:CRITICAL:null-continuity-crash, FIXED): a JSON-null
    continuity_options must not crash param resolution; the img2img overlay is
    simply skipped, leaving the template default. get_workflow_params now dict-guards
    the continuity_options read (workflow_selector.py:515), mirroring the sibling
    guard at quality_max.py:1044. Was `AttributeError: 'NoneType'.get` before the fix
    (settings.get('continuity_options', {}) returns None on present-but-null)."""
    from workflow_selector import get_workflow_params

    p = get_workflow_params("portrait", settings={"continuity_options": None})
    assert isinstance(p, dict) and p, "expected template params, got a crash/empty"
