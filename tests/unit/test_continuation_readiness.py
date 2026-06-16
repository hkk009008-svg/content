"""Tests for scripts/continuation_readiness.py."""

from __future__ import annotations

import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import continuation_readiness as readiness  # noqa: E402


def test_render_mailbox_reports_all_four_seats(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        readiness,
        "collect_mailbox",
        lambda root: {
            "mailbox_director_unread": 3,
            "mailbox_director_cursor": "2026-06-14T19:58:23Z",
            "mailbox_director2_unread": 3,
            "mailbox_director2_cursor": "2026-06-14T19:58:23Z",
            "mailbox_operator_unread": 3,
            "mailbox_operator_cursor": "2026-06-14T19:58:23Z",
            "mailbox_operator2_unread": 2,
            "mailbox_operator2_cursor": "2026-06-14T20:16:05Z",
        },
    )

    readiness.render_mailbox(tmp_path)

    out = capsys.readouterr().out
    assert "mode: read-only; cursors are not consumed" in out
    assert "director " in out
    assert "director2" in out
    assert "operator " in out
    assert "operator2" in out
    assert "consume-events intentionally" in out


def test_main_identifies_readiness_bridge_role(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(readiness, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(readiness, "render_codex", lambda root: None)
    monkeypatch.setattr(readiness, "render_git", lambda root, commits: None)
    monkeypatch.setattr(readiness, "render_mailbox", lambda root: None)
    monkeypatch.setattr(readiness, "render_wave", lambda root, wave: None)
    monkeypatch.setattr(readiness, "render_ceremony", lambda root: None)
    monkeypatch.setattr(readiness, "render_environment", lambda root, smoke: None)

    rc = readiness.main(["--skip-ceremony"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "Continuation Readiness Bridge" in out
    assert "no seat claim, cursor consumption, mailbox send, or inventory edit" in out


def test_render_codex_reports_harness_model_artifacts(tmp_path, monkeypatch, capsys):
    for key in (
        "CODEX_AGENT_MODE",
        "CODEX_AGENT_ROLE",
        "CODEX_SEAT",
        "CODEX_CAPABILITY_MODE",
        "CODEX_MUTATION_SCOPE",
        "GIT_INDEX_FILE",
    ):
        monkeypatch.delenv(key, raising=False)

    skill = tmp_path / ".agents" / "skills" / "four-seat-protocol"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: four-seat-protocol\n---\n", encoding="utf-8")
    codex_agents = tmp_path / ".codex" / "agents"
    codex_agents.mkdir(parents=True)
    (tmp_path / ".codex" / "hooks.json").write_text("{}", encoding="utf-8")
    (codex_agents / "readiness-bridge.toml").write_text("name='readiness-bridge'\n", encoding="utf-8")
    (codex_agents / "agent01.toml").write_text("name='agent01'\n", encoding="utf-8")

    readiness.render_codex(tmp_path)

    out = capsys.readouterr().out
    assert "Codex Harness Model" in out
    assert "source: scripts/codex_protocol_model.py" in out
    assert "skill: present" in out
    assert "hooks: present" in out
    assert "durable shared state" in out
    assert "Mailbox sent/ + seen cursors" in out
    assert "agent guardrail extensions: agent01.toml" in out
    assert "do not replace built-in role agents" in out
    assert "Next start session" in out
    assert "Runtime env contract" in out
    assert "CODEX_AGENT_MODE=readiness-bridge" in out
    assert "CODEX_AGENT_ROLE=readiness-bridge" in out
    assert "CODEX_CAPABILITY_MODE=read-only" in out
    assert "CODEX_MUTATION_SCOPE=none" in out
    assert "inhabit the Codex harness as readiness bridge" in out
    assert "explicit seat or coordinator instruction" in out
    assert "readiness-bridge.toml" in out
    assert "CODEX_SEAT=<seat>" in out
    assert "scripts/draft_handoff.py <seat> --wave 2 --output" in out
