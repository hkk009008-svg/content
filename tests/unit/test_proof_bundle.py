from __future__ import annotations

import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import proof_bundle  # noqa: E402


def test_build_commands_uses_env_u_git_index_for_git_and_gate(tmp_path: Path) -> None:
    commands = proof_bundle.build_commands(tmp_path, seat="coordinator", wave=2, smoke=True)

    rendered = [" ".join(command) for command in commands]
    assert any("seat_status.py coordinator --wave 2" in command for command in rendered)
    assert any(command.startswith("env -u GIT_INDEX_FILE git log") for command in rendered)
    assert any("scripts/wave_gate_check.py 2" in command for command in rendered)
    assert any("scripts/ci_smoke.py" in command for command in rendered)


def test_collect_mailbox_bodies_limits_to_unread_files(tmp_path: Path) -> None:
    sent = tmp_path / "coordination" / "mailbox" / "sent"
    sent.mkdir(parents=True)
    event = sent / "2026-06-16T05-04-09Z-coordinator-to-all-coordination.md"
    event.write_text("# Coordinator\n\nbody\n", encoding="utf-8")

    bodies = proof_bundle.collect_mailbox_bodies(tmp_path, [event.name], limit=1)

    assert bodies == [(event.name, "# Coordinator\n\nbody\n")]


def test_main_renders_commands_monitor_and_mailbox_bodies(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    sent = tmp_path / "coordination" / "mailbox" / "sent"
    sent.mkdir(parents=True)
    event = sent / "2026-06-16T05-04-09Z-coordinator-to-all-coordination.md"
    event.write_text("# Coordinator\n\nroute body\n", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run_command(command: list[str], root: Path) -> tuple[int, str]:
        calls.append(command)
        return 0, f"output for {' '.join(command[:3])}\n"

    def fake_collect_monitor_state(root: Path, *, now=None, stale_min: int = 15) -> dict:
        assert root == tmp_path
        assert stale_min == 7
        return {"fake": "state"}

    monkeypatch.setattr(proof_bundle, "run_command", fake_run_command)
    monkeypatch.setattr(proof_bundle, "collect_monitor_state", fake_collect_monitor_state)
    monkeypatch.setattr(proof_bundle, "render_snapshot", lambda state: "MONITOR SNAPSHOT\n")

    rc = proof_bundle.main(
        [
            "--root",
            str(tmp_path),
            "--seat",
            "director2",
            "--wave",
            "2",
            "--smoke",
            "--mailbox",
            event.name,
            "--stale-min",
            "7",
        ]
    )

    output = capsys.readouterr().out
    assert rc == 0
    assert any("seat_status.py" in " ".join(command) for command in calls)
    assert "MONITOR SNAPSHOT" in output
    assert "# Coordinator\n\nroute body\n" in output
    assert "read-only; no cursor consumption; no mailbox send" in output


def test_main_returns_first_nonzero_command_status(tmp_path: Path, monkeypatch) -> None:
    def fake_run_command(command: list[str], root: Path) -> tuple[int, str]:
        if command[:3] == ["env", "-u", "GIT_INDEX_FILE"]:
            return 3, "gate failed\n"
        return 0, "ok\n"

    monkeypatch.setattr(proof_bundle, "run_command", fake_run_command)
    monkeypatch.setattr(proof_bundle, "collect_monitor_state", lambda root, **kw: {})
    monkeypatch.setattr(proof_bundle, "render_snapshot", lambda state: "")

    assert proof_bundle.main(["--root", str(tmp_path), "--seat", "operator2"]) == 3
