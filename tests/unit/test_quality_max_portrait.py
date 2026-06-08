"""Tests for _inject_aspect: max-tier native 9:16 latent + 4K portrait final.

Portrait Phase 2 — quality_max._inject_aspect transposes node 102
(EmptyLatentImage 1024x576) and node 950 (ImageScale 3840x2160) via
cinema/aspect.py::portrait_swap when aspect_ratio="9:16". Landscape / None →
no-op. Called after _inject_post_passes so both paths inherit correct dims.
"""
from __future__ import annotations

import pytest

from quality_max import _load_max_workflow, _inject_aspect, _inject_post_passes


def test_inject_aspect_portrait_transposes_node102_and_950():
    """9:16 → node 102 (EmptyLatentImage) transposes 1024x576 → 576x1024,
    node 950 (ImageScale final) transposes 3840x2160 → 2160x3840."""
    wf = _load_max_workflow()
    _inject_aspect(wf, "9:16")
    assert (wf["102"]["inputs"]["width"], wf["102"]["inputs"]["height"]) == (576, 1024)
    assert (wf["950"]["inputs"]["width"], wf["950"]["inputs"]["height"]) == (2160, 3840)


def test_inject_aspect_landscape_unchanged():
    """16:9 → no transposition; template dims are preserved."""
    wf = _load_max_workflow()
    _inject_aspect(wf, "16:9")
    assert (wf["102"]["inputs"]["width"], wf["102"]["inputs"]["height"]) == (1024, 576)
    assert (wf["950"]["inputs"]["width"], wf["950"]["inputs"]["height"]) == (3840, 2160)


def test_inject_aspect_none_is_noop():
    """None aspect_ratio → no-op (no ctx defaults to landscape)."""
    wf = _load_max_workflow()
    _inject_aspect(wf, None)
    assert (wf["102"]["inputs"]["width"], wf["102"]["inputs"]["height"]) == (1024, 576)


def test_inject_aspect_after_post_passes_uses_final_resolution():
    """Order contract: _inject_post_passes sets node 950 dims from
    params["final_resolution"]; _inject_aspect then transposes whatever
    post_passes set (NOT just the template default). A non-default
    final_resolution gives the ordering contract teeth — if _inject_aspect
    ran BEFORE post_passes, node 950 would read the template 3840x2160 and
    the assertion below (1080x1920) would fail."""
    wf = _load_max_workflow()
    _inject_post_passes(wf, params={"final_resolution": (1920, 1080)}, available=set())
    # post_passes set node 950 → 1920x1080 (landscape, non-default)
    assert (wf["950"]["inputs"]["width"], wf["950"]["inputs"]["height"]) == (1920, 1080)
    _inject_aspect(wf, "9:16")
    # _inject_aspect transposes what post_passes set → 1080x1920
    assert (wf["950"]["inputs"]["width"], wf["950"]["inputs"]["height"]) == (1080, 1920)
