# tests/unit/test_seed_inventory.py
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("seed", ROOT / "scripts" / "seed_inventory.py")

def _load():
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def test_finds_strict_xfail(tmp_path):
    t = tmp_path / "tests"; t.mkdir()
    (t / "test_a.py").write_text(
        'import pytest\n'
        '@pytest.mark.xfail(strict=True, reason="W1:CRITICAL:budget-nan core.py:101 nan bypass")\n'
        'def test_budget(): assert False\n'
    )
    pins = _load().find_xfail_pins(t)
    assert len(pins) == 1
    p = pins[0]
    assert p["strict"] is True
    assert p["test_file"].endswith("test_a.py")
    assert "budget-nan" in p["reason"]

def test_ignores_nonstrict_and_plain(tmp_path):
    t = tmp_path / "tests"; t.mkdir()
    (t / "test_b.py").write_text(
        'import pytest\n'
        '@pytest.mark.xfail(reason="flaky")\n'
        'def test_x(): pass\n'
    )
    pins = _load().find_xfail_pins(t)
    assert pins[0]["strict"] is False
