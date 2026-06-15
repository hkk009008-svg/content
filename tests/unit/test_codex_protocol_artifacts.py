"""Tests for Codex-side four-seat protocol transplant artifacts."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


def test_codex_hooks_are_parseable_and_delegate_to_wrappers():
    hooks = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))

    assert set(hooks["hooks"]) == {"SessionStart", "PreToolUse", "PostToolUse"}
    commands = [
        hook["command"]
        for groups in hooks["hooks"].values()
        for group in groups
        for hook in group["hooks"]
    ]

    assert any(".codex/hooks/session-smoke.sh" in command for command in commands)
    assert any(".codex/hooks/guard-git-index.sh" in command for command in commands)
    assert any(".codex/hooks/update-state.sh" in command for command in commands)


def test_codex_hook_wrappers_exist_and_bridge_codex_seat():
    hooks_dir = ROOT / ".codex" / "hooks"

    for name in ("session-smoke.sh", "guard-git-index.sh", "update-state.sh"):
        text = (hooks_dir / name).read_text(encoding="utf-8")
        assert ".claude/hooks" in text

    update_state = (hooks_dir / "update-state.sh").read_text(encoding="utf-8")
    assert "CODEX_SEAT" in update_state
    assert "CLAUDE_SEAT" in update_state


def test_codex_custom_agents_are_valid_toml_with_required_fields():
    agents_dir = ROOT / ".codex" / "agents"
    agent_files = sorted(agents_dir.glob("*.toml"))

    assert {path.name for path in agent_files} == {
        "lane-v-verifier.toml",
        "money-gate-reviewer.toml",
        "protocol-coordinator.toml",
        "protocol-director.toml",
        "protocol-operator.toml",
        "readiness-bridge.toml",
    }
    for path in agent_files:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert data["name"]
        assert data["description"]
        assert data["developer_instructions"]
        assert ".claude/skills/four-seat-protocol" not in data["developer_instructions"]


def test_protocol_coordinator_agent_uses_tight_reconcile_loop():
    agent = tomllib.loads(
        (ROOT / ".codex" / "agents" / "protocol-coordinator.toml").read_text(
            encoding="utf-8"
        )
    )
    instructions = agent["developer_instructions"]

    assert "seat_status.py coordinator --wave 2" in instructions
    assert "Do not consume mailbox cursors" in instructions
    assert "no-op status report" in instructions
    assert "one consolidated mailbox" in instructions
    assert "Capacity-max cycle default" in instructions
    assert "protocol-director" in instructions
    assert "protocol-operator" in instructions


def test_codex_protocol_skill_points_to_readiness_and_seat_commands():
    text = (ROOT / ".agents" / "skills" / "four-seat-protocol" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "name: four-seat-protocol" in text
    assert "scripts/continuation_readiness.py" in text
    assert "scripts/draft_handoff.py" in text
    assert "seat_status.py <seat> --wave 2" in text
    assert "coordination/bin/consume-events <seat>" in text
    assert "Never silently upgrade from bridge mode into a seat." in text
    assert "Capacity-Max Default Cycle" in text
    assert "protocol-director" in text
    assert "protocol-operator" in text


def test_codex_continuation_defines_subagent_cycle_default():
    text = (ROOT / "docs" / "protocol" / "codex" / "continuation.md").read_text(
        encoding="utf-8"
    )

    assert "Capacity-Max Default Workflow" in text
    assert "capacity-max loop" in text
    assert "scripts/draft_handoff.py" in text
    assert "protocol-director" in text
    assert "protocol-operator" in text
    assert "Readiness bridge mode is still read-only and never auto-spawns seats" in text


def test_seat_coordinator_skill_defines_noop_fast_path():
    text = (ROOT / ".agents" / "skills" / "seat-coordinator" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "seat_status.py coordinator --wave <N>" in text
    assert "No-op fast path" in text
    assert "do not send a new mailbox event" in text
    assert "ADR-027 means the gate now executes" in text
