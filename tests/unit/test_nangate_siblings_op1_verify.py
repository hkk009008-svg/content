"""Wave-1 regressions — nan-gate sibling sites of 7b4d377 + bf1034a (now FIXED).

PROVENANCE: surfaced by operator-1's independent implementer!=verifier sweep
(workflow wf_25dce560-524) of nan-gate commits 7b4d377 + bf1034a. Those commits
themselves PASSED verification (8 guards mutation-proven; 35 tests coupled). The
Rule#13 completeness sweep then surfaced sibling sites of the SAME non-finite hazard
class outside their audit boundary, pinned strict=True (R-VERIFY-TIER(B): a
confirmed-but-unfixed defect ships a strict-xfail pin in the confirming session).

Both Pair-A siblings were FIXED in Wave-1 of the program-hardening campaign and the
strict-xfail pins removed -> these were LIVE regressions (they go RED if the guard
is reverted), strengthened beyond the original single-assert pins where noted:
  - pulid-nan-node100     -> quality_max.py node-100 weight/start_at/end_at _finite_or
    (RETIRED WS1 Task 4 — quality_max.py deleted, no production replacement; the
    regression test for it is retired alongside it, see below)
  - null-continuity-crash -> workflow_selector.py:515 dict-guard (still live)

A third confirmed sibling (phase_c_assembly img2img clamp-luck) is Pair-B lane and was
addressed separately in that lane.
"""
from __future__ import annotations

import pytest


def test_null_continuity_options_must_not_crash_param_resolution():
    """Regression (W1:CRITICAL:null-continuity-crash, FIXED): a JSON-null
    continuity_options must not crash param resolution; the img2img overlay is
    simply skipped, leaving the template default. get_workflow_params now dict-guards
    the continuity_options read (workflow_selector.py:515). Was
    `AttributeError: 'NoneType'.get` before the fix (settings.get('continuity_options',
    {}) returns None on present-but-null)."""
    from workflow_selector import get_workflow_params

    p = get_workflow_params("portrait", settings={"continuity_options": None})
    assert isinstance(p, dict) and p, "expected template params, got a crash/empty"
