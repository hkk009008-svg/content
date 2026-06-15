# tests/unit/test_wave_gate_check.py
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("wgc", ROOT / "scripts" / "wave_gate_check.py")

INVENTORY = """\
# Remediation Inventory

| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |
|----|-----------|-----------|----------|----------|-----------|-------|-----------|------------|-------------|------|--------|----------|-------|
| budget-nan | money | cost_tracker.py:101 | CRITICAL | 1 | nan bypass | t | tests/unit/test_budget_nan_gate_xfail.py | B |  | 1 | verified | op2 |  |
| gate-nan | gates | auto_approve.py:120 | CRITICAL | 2 | nan veto | t | tests/unit/test_auto_approve_nangate_xfail.py | A | W1-auto_approve.py.lock | 1 | open | | |
| no-oracle | gates | core.py:7 | MAJOR | 2 | no oracle | t | test-infeasible | A | | 1 | open | | |
| med-open | gates | core.py:8 | MEDIUM | 3 | medium | t | tests/unit/test_medium_xfail.py | A | | 1 | open | | |
| p1 | x | core.py:9 | MINOR | 1 | x | t | tests/unit/test_p1_xfail.py | A | | 3 | provisional | | mid |
"""


def _load():
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _runner(exit_code=0, stdout="2 passed\n"):
    calls = []

    def run(selectors):
        calls.append(list(selectors))
        return {
            "args": ["python", "-m", "pytest", *selectors, "--runxfail", "-q"],
            "command": "python -m pytest ... --runxfail -q",
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": "",
        }

    run.calls = calls
    return run


def test_gate_executes_critical_major_selectors_and_ignores_status_for_verdict(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY.replace("| no-oracle |", "| med2 |").replace("test-infeasible", "tests/unit/test_major_xfail.py"))
    wgc = _load()
    runner = _runner(exit_code=0)

    report = wgc.gate_report(inv, wave=1, runner=runner)

    assert report["verdict"] == "MET"
    assert runner.calls == [[
        "tests/unit/test_budget_nan_gate_xfail.py",
        "tests/unit/test_auto_approve_nangate_xfail.py",
        "tests/unit/test_major_xfail.py",
    ]]
    assert report["counts"]["open"] == 3


def test_no_oracle_major_blocks_even_when_status_is_not_authoritative(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY)
    wgc = _load()
    runner = _runner(exit_code=0)

    report = wgc.gate_report(inv, wave=1, runner=runner)

    assert report["verdict"] == "UNMET"
    assert any(b["id"] == "no-oracle" for b in report["blockers"])
    assert runner.calls == [[
        "tests/unit/test_budget_nan_gate_xfail.py",
        "tests/unit/test_auto_approve_nangate_xfail.py",
    ]]


def test_pytest_failure_blocks_gate(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY.replace("| no-oracle |", "| med2 |").replace("test-infeasible", "tests/unit/test_major_xfail.py"))
    wgc = _load()
    runner = _runner(exit_code=1, stdout="FAILED tests/unit/test_major_xfail.py::test_bug\n")

    report = wgc.gate_report(inv, wave=1, runner=runner)

    assert report["verdict"] == "UNMET"
    assert report["pytest_blocking"] is True


def test_provisional_blocks_regardless_of_severity(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY)
    wgc = _load()
    runner = _runner(exit_code=0)

    rep = wgc.gate_report(inv, wave=3, runner=runner)

    assert rep["verdict"] == "UNMET"
    assert any(r["id"] == "p1" for r in rep["blockers"])


def test_medium_open_does_not_run_or_block(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY)
    wgc = _load()
    runner = _runner(exit_code=0)

    rep = wgc.gate_report(inv, wave=1, runner=runner)

    assert "tests/unit/test_medium_xfail.py" not in rep["selectors"]
    assert not any(r["id"] == "med-open" for r in rep["blockers"])


def test_empty_wave_is_met_without_pytest(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY)
    wgc = _load()
    runner = _runner(exit_code=1)

    rep = wgc.gate_report(inv, wave=99, runner=runner)

    assert rep["verdict"] == "MET"
    assert rep["blockers"] == []
    assert rep["counts"] == {}
    assert runner.calls == []


def test_selector_extraction_expands_shorthand_nodes():
    wgc = _load()

    selectors = wgc._selectors_from_pin(
        "tests/unit/test_phase_c_vision.py::TestValidateIdentityVision / "
        "::TestValidateIdentityVisionEncodeFailure; "
        "tests/unit/test_identity_validator.py::test_marker "
        "(notes ignored)"
    )

    assert selectors == [
        "tests/unit/test_phase_c_vision.py::TestValidateIdentityVision",
        "tests/unit/test_phase_c_vision.py::TestValidateIdentityVisionEncodeFailure",
        "tests/unit/test_identity_validator.py::test_marker",
    ]
