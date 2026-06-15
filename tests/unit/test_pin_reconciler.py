# tests/unit/test_pin_reconciler.py
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("pin_reconciler", ROOT / "scripts" / "pin_reconciler.py")

INVENTORY = """\
# Remediation Inventory

| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |
|----|-----------|-----------|----------|----------|-----------|-------|-----------|------------|-------------|------|--------|----------|-------|
| verified-clean | money | cost_tracker.py:101 | CRITICAL | 1 | fixed | t | tests/unit/test_clean_regression.py | B |  | 1 | verified | op2 |  |
| verified-stale | gates | auto_approve.py:120 | CRITICAL | 2 | stale | t | tests/unit/test_stale_xfail.py | A |  | 1 | verified | op1 | |
| open-row | gates | core.py:7 | MAJOR | 2 | open | t | tests/unit/test_open_xfail.py | A | | 1 | open | | |
| verified-missing | gates | core.py:8 | MAJOR | 2 | missing | t | test-infeasible | A | | 2 | verified | op1 | |
"""


def _load():
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reconciler_runs_only_verified_rows_normally(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY)
    reconciler = _load()
    calls = []

    def runner(selectors):
        calls.append(list(selectors))
        stdout = "1 xfailed\n" if "test_stale_xfail.py" in selectors[0] else "1 passed\n"
        return {
            "args": ["python", "-m", "pytest", *selectors, "-q"],
            "command": "python -m pytest ... -q",
            "exit_code": 0,
            "stdout": stdout,
            "stderr": "",
        }

    report = reconciler.reconcile_report(inv, wave=1, runner=runner)

    assert calls == [
        ["tests/unit/test_clean_regression.py"],
        ["tests/unit/test_stale_xfail.py"],
    ]
    assert [item["row"]["id"] for item in report["results"] if item["issue"]] == ["verified-stale"]
    assert report["missing"] == []


def test_reconciler_reports_verified_rows_without_executable_selectors(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY)
    reconciler = _load()

    report = reconciler.reconcile_report(inv, wave=2, runner=lambda selectors: {})

    assert [item["id"] for item in report["missing"]] == ["verified-missing"]
    assert report["issues"] == report["missing"]
