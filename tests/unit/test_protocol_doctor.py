from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import protocol_doctor  # noqa: E402


def test_doctor_runs_read_only_protocol_bundle(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_run(cmd, cwd, timeout=120):
        calls.append(cmd)
        return protocol_doctor.CommandResult(cmd=cmd, returncode=0, stdout="OK", stderr="")

    monkeypatch.setattr(protocol_doctor, "run_command", fake_run)

    rc = protocol_doctor.main(["--root", str(tmp_path), "--wave", "4"])

    assert rc == 0
    assert [sys.executable, "scripts/check_coordination.py"] in calls
    assert [sys.executable, "scripts/protocol_capacity_board.py", "--wave", "4"] in calls
    assert [
        sys.executable,
        "-m",
        "pytest",
        "tests/unit/test_codex_protocol_model.py",
        "tests/unit/test_codex_protocol_artifacts.py",
        "tests/unit/test_protocol_capacity_board.py",
        "tests/unit/test_coordination_bin.py",
        "tests/unit/test_check_coordination.py",
        "-q",
    ] in calls
    assert [sys.executable, "scripts/ci_smoke.py"] in calls
    assert "PROTOCOL DOCTOR: PASS" in capsys.readouterr().out


def test_doctor_validates_route_when_passed(monkeypatch, tmp_path):
    route = tmp_path / "coordination/mailbox/sent/route.md"
    route.parent.mkdir(parents=True)
    route.write_text("task-board\n", encoding="utf-8")
    calls = []

    def fake_run(cmd, cwd, timeout=120):
        calls.append(cmd)
        return protocol_doctor.CommandResult(cmd=cmd, returncode=0, stdout="OK", stderr="")

    monkeypatch.setattr(protocol_doctor, "run_command", fake_run)

    rc = protocol_doctor.main(["--root", str(tmp_path), "--wave", "4", "--route", str(route)])

    assert rc == 0
    assert [
        sys.executable,
        "scripts/protocol_capacity_board.py",
        "--wave",
        "4",
        "--require-packets",
    ] in calls
    assert [
        sys.executable,
        "scripts/protocol_capacity_board.py",
        "--wave",
        "4",
        "--validate-route",
        str(route),
    ] in calls


def test_doctor_fails_on_first_failed_command(monkeypatch, tmp_path):
    def fake_run(cmd, cwd, timeout=120):
        return protocol_doctor.CommandResult(cmd=cmd, returncode=1, stdout="", stderr="bad")

    monkeypatch.setattr(protocol_doctor, "run_command", fake_run)

    rc = protocol_doctor.main(["--root", str(tmp_path), "--wave", "4"])

    assert rc == 1
