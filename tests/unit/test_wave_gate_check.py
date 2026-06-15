# tests/unit/test_wave_gate_check.py
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

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

WAVE2_INVENTORY = """\
# Remediation Inventory

| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |
|----|-----------|-----------|----------|----------|-----------|-------|-----------|------------|-------------|------|--------|----------|-------|
| wave2-budget | money | cost_tracker.py:101 | CRITICAL | 1 | nan bypass | t | tests/unit/test_budget_nan_gate_xfail.py | B |  | 2 | verified | op2 |  |
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

def _write_product_oracle(tmp_path, *, wave=2, payload=None):
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    path = logs / f"product-oracle-wave{wave}.json"
    if payload is None:
        payload = {
            "artifact_kind": "product-oracle",
            "wave": wave,
            "instrument": "scripts/measure_lipsync_offset.py",
            "arcface": {"arc_score": 0.84},
            "lipsync": {"offset_frames": 1.5},
        }
    path.write_text(json.dumps(payload))
    return path


def _git(cwd, *args):
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


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


def test_wave1_does_not_require_product_oracle_artifact(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY.replace("| no-oracle |", "| med2 |").replace("test-infeasible", "tests/unit/test_major_xfail.py"))
    wgc = _load()
    runner = _runner(exit_code=0)

    report = wgc.gate_report(inv, wave=1, runner=runner, product_oracle_paths=[])

    assert report["verdict"] == "MET"
    assert report["product_oracle_blockers"] == []


def test_wave2_requires_product_oracle_artifact_even_when_pins_pass(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(WAVE2_INVENTORY)
    wgc = _load()
    runner = _runner(exit_code=0)

    report = wgc.gate_report(inv, wave=2, runner=runner, product_oracle_paths=[])

    assert report["verdict"] == "UNMET"
    assert report["product_oracles"]["valid"] == []
    assert report["product_oracle_blockers"]
    assert "logs/product-oracle-*.json" in report["product_oracle_blockers"][0]


def test_wave2_accepts_valid_product_oracle_artifact(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(WAVE2_INVENTORY)
    artifact = _write_product_oracle(tmp_path, wave=2)
    wgc = _load()
    runner = _runner(exit_code=0)

    report = wgc.gate_report(inv, wave=2, runner=runner, product_oracle_paths=[artifact])

    assert report["verdict"] == "MET"
    assert report["product_oracle_blockers"] == []
    assert report["product_oracles"]["valid"] == [str(artifact)]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "product-oracle-head-path-discovery: committed logs/product-oracle-*.json "
        "artifacts are not discovered from HEAD"
    ),
)
def test_wave2_discovers_valid_committed_product_oracle_artifact(tmp_path, monkeypatch):
    inv = tmp_path / "INV.md"
    inv.write_text(WAVE2_INVENTORY)
    artifact = _write_product_oracle(tmp_path, wave=2)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "operator2@example.invalid")
    _git(tmp_path, "config", "user.name", "operator2 regression pin")
    _git(tmp_path, "add", str(artifact.relative_to(tmp_path)))
    _git(tmp_path, "commit", "-q", "-m", "valid committed product oracle")
    wgc = _load()
    monkeypatch.setattr(wgc, "_REPO_ROOT", tmp_path)
    runner = _runner(exit_code=0)

    report = wgc.gate_report(inv, wave=2, runner=runner)

    assert report["verdict"] == "MET"
    assert report["product_oracle_blockers"] == []
    assert report["product_oracles"]["valid"] == ["logs/product-oracle-wave2.json"]


def test_wave2_rejects_malformed_product_oracle_artifact(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(WAVE2_INVENTORY)
    artifact = _write_product_oracle(
        tmp_path,
        wave=2,
        payload={
            "artifact_kind": "product-oracle",
            "wave": 2,
            "arcface": {"arc_score": 0.84},
        },
    )
    wgc = _load()
    runner = _runner(exit_code=0)

    report = wgc.gate_report(inv, wave=2, runner=runner, product_oracle_paths=[artifact])

    assert report["verdict"] == "UNMET"
    assert any("lipsync.offset_frames" in issue for issue in report["product_oracles"]["invalid"])
