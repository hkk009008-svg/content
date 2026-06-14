# tests/unit/test_wave_gate_check.py
import importlib.util, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("wgc", ROOT / "scripts" / "wave_gate_check.py")

INVENTORY = """\
# Remediation Inventory

| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |
|----|-----------|-----------|----------|----------|-----------|-------|-----------|------------|-------------|------|--------|----------|-------|
| budget-nan | money | core.py:101 | CRITICAL | 1 | nan bypass | t | tests/x.py | B |  | 1 | verified | op2 |  |
| gate-nan | gates | auto_approve.py:120 | CRITICAL | 2 | nan veto | t | tests/y.py | A | W1-auto_approve.py.lock | 1 | open | | |
| audio-zero | audio | audio/effects.py:230 | MAJOR | 1 | no tests | t | tests/z.py | B | | 2 | verified | op2 | |
"""

def _load():
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def test_unmet_when_open_critical(tmp_path):
    inv = tmp_path / "INV.md"; inv.write_text(INVENTORY)
    wgc = _load()
    report = wgc.gate_report(inv, wave=1)
    assert report["verdict"] == "UNMET"
    assert any(r["id"] == "gate-nan" for r in report["blockers"])

def test_met_when_all_verified(tmp_path):
    inv = tmp_path / "INV.md"; inv.write_text(INVENTORY)
    wgc = _load()
    report = wgc.gate_report(inv, wave=2)   # only audio-zero, verified
    assert report["verdict"] == "MET"
    assert report["blockers"] == []

def test_provisional_blocks_regardless_of_severity(tmp_path):
    # Wave 3 has no seeded rows, so a lone MINOR provisional cleanly isolates the
    # provisional-check (Wave 1 was already UNMET from its open CRITICAL).
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY + "| p1 | x | core.py:9 | MINOR | 1 | x | t | tests/p.py | A | | 3 | provisional | | mid |\n")
    wgc = _load()
    rep = wgc.gate_report(inv, wave=3)
    assert rep["verdict"] == "UNMET" and any(r["id"] == "p1" for r in rep["blockers"])

def test_medium_open_does_not_block(tmp_path):
    """MEDIUM/MINOR open rows must NOT trigger UNMET — only CRITICAL/MAJOR-not-verified or provisional do."""
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY + "| med-1 | x | core.py:5 | MEDIUM | 3 | x | t | tests/m.py | A | | 1 | open | | |\n")
    wgc = _load()
    rep = wgc.gate_report(inv, wave=1)
    # Wave 1 already has gate-nan (CRITICAL/open) blocking; med-1 must NOT be an additional blocker.
    assert not any(r["id"] == "med-1" for r in rep["blockers"])

def test_empty_wave_is_met(tmp_path):
    """A wave with no rows must return MET (Task 4 Step 2 relies on empty-inventory -> MET)."""
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY)  # waves 1 and 2 only — wave 99 is absent
    wgc = _load()
    rep = wgc.gate_report(inv, wave=99)
    assert rep["verdict"] == "MET"
    assert rep["blockers"] == []
    assert rep["counts"] == {}
