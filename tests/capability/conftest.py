"""Shared fixtures + tier-marker registration for the capability suite.

Tiers:
  offline — deterministic, mocked, $0, always in CI (default for logic tests)
  live    — needs real API/GPU/ComfyUI creds; skipif-gated; costs money
  e2e     — the one paid golden run; opt-in via CAPABILITY_E2E=1
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pytest

from _scorecard import Scorecard


def pytest_configure(config):
    config.addinivalue_line("markers", "offline: deterministic capability test, no network/GPU/spend")
    config.addinivalue_line("markers", "live: capability test needing real API/GPU/ComfyUI; skipif-gated")
    config.addinivalue_line("markers", "e2e: full paid golden-run capability test; opt-in via CAPABILITY_E2E=1")
    config._capability_scorecard = Scorecard()


@pytest.fixture
def capability_record(request):
    """Record a capability result; dimension inferred from the test's subpackage."""
    sc = request.config._capability_scorecard
    parts = request.node.nodeid.split("/")
    dimension = parts[2] if len(parts) > 3 and parts[1] == "capability" else "framework"

    def _record(*, claim_id, passed, tier="offline", measured=None, bar=None, detail=""):
        sc.record(dimension=dimension, claim_id=claim_id, tier=tier,
                  passed=passed, measured=measured, bar=bar, detail=detail)
    return _record


@pytest.fixture
def synthetic_image(tmp_path):
    """A deterministic 256x256 RGB png (no real person)."""
    cv2 = pytest.importorskip("cv2")
    arr = np.full((256, 256, 3), 127, dtype=np.uint8)
    arr[64:192, 96:160] = 200
    p = tmp_path / "synthetic.png"
    cv2.imwrite(str(p), arr)
    return str(p)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    sc = getattr(config, "_capability_scorecard", None)
    if sc is None or not sc.entries:
        return
    terminalreporter.write_sep("=", "CAPABILITY SCORECARD")
    terminalreporter.write_line(sc.render_markdown())
