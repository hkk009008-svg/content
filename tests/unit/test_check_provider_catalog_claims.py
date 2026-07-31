"""Tests for scripts/check_provider_catalog_claims.py.

Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_provider_catalog_claims.py -q

Pins the exact provider-lifecycle facts Slice 14a verified and wrote into
config/prompts/pipeline_context.md and the ai-video-gen SKILL.md (GEMINI_OMNI
repaired/routable, SORA_2 fully retired, RUNWAY_ACT_ONE retired/migrated to
Act-Two, VIGGLE KNOWN_BROKEN, LTX duration restricted to {6, 8, 10}s). Each
regression test mutates a real CatalogEntry (via dataclasses.replace, so the
mutation is a genuine, structurally valid CatalogEntry — not a bare mock)
and confirms the checker fails loud instead of staying silently green.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_provider_catalog_claims import check  # noqa: E402

from domain.provider_catalog import (  # noqa: E402
    CATALOG,
    Lifecycle,
    ParameterConstraint,
    ProductSupport,
)


def test_real_catalog_is_clean():
    """Integration pin: the real CATALOG matches every claim this slice wrote."""
    assert check(REPO_ROOT) == []


def test_missing_entry_is_reported(monkeypatch):
    reduced = {k: v for k, v in CATALOG.items() if k != "GEMINI_OMNI"}
    monkeypatch.setattr(
        "domain.provider_catalog.CATALOG", reduced, raising=True
    )
    messages = check(REPO_ROOT)
    assert any("GEMINI_OMNI is missing from CATALOG" in m for m in messages)


def test_gemini_omni_regression_to_broken_is_reported(monkeypatch):
    entry = CATALOG["GEMINI_OMNI"]
    broken = dataclasses.replace(
        entry,
        product_support=ProductSupport.KNOWN_BROKEN,
        selectable=False,
        dispatchable=False,
        spendable=False,
        runtime_options=(),
    )
    patched = dict(CATALOG)
    patched["GEMINI_OMNI"] = broken
    monkeypatch.setattr("domain.provider_catalog.CATALOG", patched, raising=True)
    messages = check(REPO_ROOT)
    assert any("GEMINI_OMNI" in m for m in messages)


def test_sora_2_un_retirement_is_reported(monkeypatch):
    # Flip only the two fields the checker inspects. selectable/dispatchable/
    # spendable are left at their real (False) values — flipping those too
    # would need a real runtime_options tuple to satisfy CatalogEntry's own
    # "dispatchable entries need a runtime option" invariant, which is
    # orthogonal to what this checker verifies.
    entry = CATALOG["SORA_2"]
    revived = dataclasses.replace(
        entry,
        lifecycle=Lifecycle.ACTIVE,
        product_support=ProductSupport.SUPPORTED,
    )
    patched = dict(CATALOG)
    patched["SORA_2"] = revived
    monkeypatch.setattr("domain.provider_catalog.CATALOG", patched, raising=True)
    messages = check(REPO_ROOT)
    assert any("SORA_2" in m and "RETIRED/UNSUPPORTED" in m for m in messages)


def test_runway_act_one_un_retirement_is_reported(monkeypatch):
    entry = CATALOG["RUNWAY_ACT_ONE"]
    revived = dataclasses.replace(
        entry,
        lifecycle=Lifecycle.ACTIVE,
        product_support=ProductSupport.SUPPORTED,
    )
    patched = dict(CATALOG)
    patched["RUNWAY_ACT_ONE"] = revived
    monkeypatch.setattr("domain.provider_catalog.CATALOG", patched, raising=True)
    messages = check(REPO_ROOT)
    assert any("RUNWAY_ACT_ONE" in m for m in messages)


def test_viggle_repair_is_reported(monkeypatch):
    entry = CATALOG["VIGGLE"]
    repaired = dataclasses.replace(
        entry,
        product_support=ProductSupport.SUPPORTED,
    )
    patched = dict(CATALOG)
    patched["VIGGLE"] = repaired
    monkeypatch.setattr("domain.provider_catalog.CATALOG", patched, raising=True)
    messages = check(REPO_ROOT)
    assert any("VIGGLE" in m and "KNOWN_BROKEN" in m for m in messages)


def test_ltx_duration_widening_is_reported(monkeypatch):
    entry = CATALOG["LTX"]
    widened_params = tuple(
        p for p in entry.parameters if p.name != "duration"
    ) + (ParameterConstraint("duration", allowed_values=(4, 6, 8, 10, 12)),)
    widened = dataclasses.replace(entry, parameters=widened_params)
    patched = dict(CATALOG)
    patched["LTX"] = widened
    monkeypatch.setattr("domain.provider_catalog.CATALOG", patched, raising=True)
    messages = check(REPO_ROOT)
    assert any("LTX duration" in m and "6, 8, 10" in m for m in messages)


def test_ltx_duration_shrinking_is_also_reported(monkeypatch):
    """A narrower set is just as much a drift from the documented {6,8,10} as
    a wider one — the check must not special-case "only additions"."""
    entry = CATALOG["LTX"]
    narrowed_params = tuple(
        p for p in entry.parameters if p.name != "duration"
    ) + (ParameterConstraint("duration", allowed_values=(6, 8)),)
    narrowed = dataclasses.replace(entry, parameters=narrowed_params)
    patched = dict(CATALOG)
    patched["LTX"] = narrowed
    monkeypatch.setattr("domain.provider_catalog.CATALOG", patched, raising=True)
    messages = check(REPO_ROOT)
    assert any("LTX duration" in m for m in messages)
