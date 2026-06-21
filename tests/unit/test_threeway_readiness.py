"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_readiness.py -q"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import threeway_readiness as readiness  # noqa: E402


def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


def _git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        env=_env(),
    )


def _new_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.test")
    _git(repo, "config", "user.name", "T")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def _write_minimal_tree(repo: Path) -> None:
    (repo / "threeway").mkdir()
    (repo / "threeway" / "__init__.py").write_text("", encoding="utf-8")
    for name in ("keys_bootstrap.py", "refstore.py", "gate.py", "cutover.py"):
        (repo / "threeway" / name).write_text("# placeholder\n", encoding="utf-8")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "threeway_readiness.py").write_text("# placeholder\n", encoding="utf-8")
    (repo / "coordination" / "threeway" / "keys").mkdir(parents=True)
    (repo / "coordination" / "threeway" / "events").mkdir(parents=True)
    (repo / "coordination" / "mailbox" / "sent").mkdir(parents=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "STATE.md").write_text("state\n", encoding="utf-8")


def test_check_readiness_reports_ready_not_live_without_writes(tmp_path):
    repo = _new_repo(tmp_path)
    _write_minimal_tree(repo)
    protected_files = [
        repo / "STATE.md",
        repo / ".github" / "workflows" / "ci.yml",
        repo / "coordination" / "threeway" / "keys" / "README.md",
        repo / "coordination" / "mailbox" / "sent" / "existing.md",
    ]
    protected_files[1].write_text("ci\n", encoding="utf-8")
    protected_files[2].write_text("keys\n", encoding="utf-8")
    protected_files[3].write_text("mail\n", encoding="utf-8")
    before_refs = _git(repo, "for-each-ref", "refs/threeway", "--format=%(refname) %(objectname)").stdout
    before = {p: p.read_text(encoding="utf-8") for p in protected_files}

    report = readiness.check_readiness(repo)

    assert report["mode"] == "ready-not-live"
    assert report["status"] == "BLOCKED"
    assert report["authority_flip_active"] is False
    assert any(b["id"] == "production-registry-missing" for b in report["blockers"])
    roster = next(c for c in report["checks"] if c["id"] == "key-roster-support")
    assert roster["status"] == "pass"
    assert {"chief-gemini", "chief-chatgpt"}.issubset(set(roster["details"]["seats"]))
    registry = next(c for c in report["checks"] if c["id"] == "production-registry")
    assert "chief-gemini" in registry["details"]["missing"]
    ref_bus = next(c for c in report["checks"] if c["id"] == "ref-bus-state")
    assert ref_bus["details"]["events_ref_present"] is False
    assert "authority flip: inactive" in report["summary"]
    assert before_refs == _git(repo, "for-each-ref", "refs/threeway", "--format=%(refname) %(objectname)").stdout
    assert before == {p: p.read_text(encoding="utf-8") for p in protected_files}


def test_check_readiness_degrades_missing_runtime_placeholders(tmp_path):
    repo = _new_repo(tmp_path)
    (repo / "threeway").mkdir()
    (repo / "threeway" / "keys_bootstrap.py").write_text("# placeholder\n", encoding="utf-8")

    report = readiness.check_readiness(repo)

    runtime = next(c for c in report["checks"] if c["id"] == "runtime-placeholders")
    assert runtime["status"] == "blocker"
    assert "scripts/threeway_readiness.py" in runtime["details"]["missing"]
    assert "threeway/refstore.py" in runtime["details"]["missing"]
    assert any(b["id"] == "runtime-placeholders-missing" for b in report["blockers"])


def test_json_state_line_and_hook_summary_outputs(tmp_path, monkeypatch, capsys):
    repo = _new_repo(tmp_path)
    _write_minimal_tree(repo)
    monkeypatch.setattr(readiness, "repo_root", lambda: repo)

    assert readiness.main(["--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mode"] == "ready-not-live"
    assert data["status"] == "BLOCKED"
    assert isinstance(data["checks"], list)
    assert isinstance(data["blockers"], list)

    assert readiness.main(["--state-line"]) == 0
    state_line = capsys.readouterr().out.strip()
    assert state_line.startswith("threeway: ready-not-live")
    assert "authority_flip=inactive" in state_line
    assert "blockers=" in state_line
    assert "\n" not in state_line

    assert readiness.main(["--hook-summary"]) == 0
    hook_summary = capsys.readouterr().out.strip()
    assert hook_summary.startswith("threeway ready-not-live:")
    assert "no authority flip" in hook_summary
    assert "hook failed open" not in hook_summary


def test_hook_summary_fails_open_on_unexpected_error(monkeypatch, capsys):
    monkeypatch.setattr(readiness, "check_readiness", lambda root: (_ for _ in ()).throw(RuntimeError("boom")))

    assert readiness.main(["--hook-summary"]) == 0
    out = capsys.readouterr().out.strip()
    assert "threeway ready-not-live: hook failed open" in out
    assert "boom" in out
