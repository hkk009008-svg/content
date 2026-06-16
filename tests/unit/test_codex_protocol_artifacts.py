"""Tests for Codex-side four-seat protocol harness artifacts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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


def test_session_smoke_does_not_fallback_to_system_python(tmp_path):
    """Missing project venv should not run system python with missing deps."""
    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    shutil.copy2(ROOT / ".claude" / "hooks" / "session-smoke.sh", hooks_dir)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "python3-called"
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        f"#!/usr/bin/env bash\nprintf called > {marker}\nexit 99\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    result = subprocess.run(
        ["bash", str(hooks_dir / "session-smoke.sh")],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert not marker.exists()
    assert "project venv missing" in result.stdout


def test_codex_custom_agents_are_valid_toml_with_required_fields():
    agents_dir = ROOT / ".codex" / "agents"
    agent_files = sorted(agents_dir.glob("*.toml"))
    agent_names = {path.name for path in agent_files}

    required_agent_names = {
        "lane-v-verifier.toml",
        "money-gate-reviewer.toml",
        "protocol-coordinator.toml",
        "protocol-director.toml",
        "protocol-operator.toml",
        "readiness-bridge.toml",
    }
    assert required_agent_names <= agent_names
    extra_agent_names = agent_names - required_agent_names
    assert all(
        name.startswith("agent")
        and name.endswith(".toml")
        and len(name) == len("agent00.toml")
        and name[5:7].isdigit()
        for name in extra_agent_names
    )
    for path in agent_files:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert data["name"]
        assert data["description"]
        assert data["developer_instructions"]
        assert ".claude/skills/four-seat-protocol" not in data["developer_instructions"]
        instructions = data["developer_instructions"].lower()
        assert (
            "durable shared state" in instructions
            or "git commits and mailbox" in instructions
        )


def test_core_role_prompts_are_compact_kernel_adapters():
    expectations = {
        "protocol-coordinator.toml": {
            "mode": "Mode: explicit coordinator",
            "commands": (
                "seat_status.py coordinator --wave 2",
                "git log --oneline -5",
                "scripts/wave_gate_check.py 2",
                "scripts/ci_smoke.py",
            ),
            "mutation": "Allowed mutation: coordination/docs/logs only",
            "authority": "Coordinator may route and reconcile but not author production fixes.",
            "output": "Expected output: capacity board, single consolidated route, or no-op report.",
        },
        "protocol-director.toml": {
            "mode": "Mode: explicit concrete director seat",
            "commands": (
                "seat_status.py <seat> --wave 2",
                "git log --oneline -5",
            ),
            "mutation": "Allowed mutation: seat-owned docs/code within route",
            "authority": "Director does not issue operator GO.",
            "output": "Expected output: brief/fix/verify-request or blocked handoff.",
        },
        "protocol-operator.toml": {
            "mode": "Mode: explicit concrete operator seat",
            "commands": (
                "seat_status.py <seat> --wave 2",
                "git log --oneline -5",
            ),
            "mutation": (
                "Allowed mutation: verification report/cursor/docs only unless "
                "user overrides"
            ),
            "authority": "Operator does not author production fixes by default.",
            "output": "Expected output: GO/NITS/FAIL or no target report.",
        },
    }

    forbidden_terms = (
        "rotating planning relay",
        "proof bundle",
        "proof-bundle",
        "idle/no-op evidence",
        "no-op evidence",
        "capacity-max",
    )

    for name, expected in expectations.items():
        data = tomllib.loads(
            (ROOT / ".codex" / "agents" / name).read_text(encoding="utf-8")
        )
        text = data["developer_instructions"]
        normalized = text.lower()

        assert "scripts/codex_protocol_model.py" in text
        assert "durable shared state beats chat memory" in text
        assert "First commands" in text
        assert "Authority boundary" in text
        assert "Allowed mutation" in text
        assert "Expected output" in text
        assert "Always check mail" in text
        assert expected["mode"] in text
        assert expected["mutation"] in text
        assert expected["authority"] in text
        assert expected["output"] in text
        for command in expected["commands"]:
            assert command in text
        for term in forbidden_terms:
            assert term not in normalized


def test_codex_adapters_are_kernel_backed_and_do_not_require_default_ceremony():
    paths = [
        ROOT / "docs" / "protocol" / "codex" / "continuation.md",
        ROOT / ".agents" / "skills" / "four-seat-protocol" / "SKILL.md",
        ROOT / ".agents" / "skills" / "seat-coordinator" / "SKILL.md",
        ROOT / "AGENTS.md",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        normalized = text.lower()
        assert "scripts/codex_protocol_model.py" in text
        assert "durable shared state beats chat memory" in text
        assert "mailbox-first" in normalized or "check mail" in normalized
        for term in (
            "proof bundle",
            "proof-bundle",
            "rotating planning relay",
            "idle seats return no-op evidence",
            "every eligible seat",
            "no-op evidence",
            "capacity-max",
        ):
            assert term not in normalized


def test_codex_protocol_skill_points_to_runtime_checklists():
    text = (ROOT / ".agents" / "skills" / "four-seat-protocol" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "name: four-seat-protocol" in text
    assert "scripts/codex_protocol_model.py" in text
    assert "durable shared state beats chat memory" in text
    assert "Source order" in text
    assert "Mode selection" in text
    assert "Readiness bridge" in text
    assert "Live seat" in text
    assert "Coordinator" in text
    assert "scripts/continuation_readiness.py" in text
    assert "scripts/mailbox_monitor.py" in text
    assert "scripts/draft_handoff.py" in text
    assert "seat_status.py <seat> --wave 2" in text
    assert "coordination/bin/consume-events <seat>" in text
    assert "Never silently upgrade from bridge mode into a seat." in text
    assert "env -u GIT_INDEX_FILE" in text
    assert "Do not consume coordinator mail" in text
    assert "user-consent-required" in text
    assert "Codex-side transplant" not in text


def test_codex_continuation_is_compact_kernel_adapter():
    text = (ROOT / "docs" / "protocol" / "codex" / "continuation.md").read_text(
        encoding="utf-8"
    )

    assert "scripts/codex_protocol_model.py" in text
    assert "durable shared state beats chat memory" in text
    assert "Runtime modes" in text
    assert "Readiness bridge" in text
    assert "Live seat" in text
    assert "Coordinator" in text
    assert "scripts/continuation_readiness.py" in text
    assert "seat_status.py <seat> --wave 2" in text
    assert "seat_status.py coordinator --wave 2" in text
    assert "mailbox-first decisions" in text
    assert "user-gated side effects" in text
    assert "scripts/mailbox_monitor.py" in text
    assert "scripts/draft_handoff.py" in text
    assert "scripts/protocol_effectiveness_report.py" in text
    assert "protocol-director" in text
    assert "protocol-operator" in text
    assert "scripts/ci_smoke.py" in text
    assert "scripts/wave_gate_check.py <wave>" in text
    assert "Codex-side transplant" not in text


def test_protocol_assembly_map_doc_codifies_folder_intent():
    text = (ROOT / "docs" / "protocol" / "protocol-assembly-map.md").read_text(
        encoding="utf-8"
    )
    continuation = (ROOT / "docs" / "protocol" / "codex" / "continuation.md").read_text(
        encoding="utf-8"
    )

    assert "Protocol Assembly Map" in text
    assert "lowest folder that can own it without ambiguity" in text
    assert "docs/protocol/agents/" in text
    assert "docs/protocol/codex/continuation.md" in text
    assert ".agents/skills/" in text
    assert ".codex/agents/*.toml" in text
    assert "coordination/mailbox/sent/" in text
    assert "coordination/mailbox/seen/" in text
    assert "coordination/locks/" in text
    assert "docs/REMEDIATION-INVENTORY.md" in text
    assert "docs/superpowers/briefs/" in text
    assert "scripts/" in text
    assert "logs/" in text
    assert "tests/unit/" in text
    assert "docs/protocol/protocol-assembly-map.md" in continuation


def test_root_agents_file_points_codex_start_to_harness_model():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "scripts/codex_protocol_model.py" in text
    assert "inhabit the Codex harness" in text
    assert "agentNN.toml" in text


def test_readiness_bridge_agent_inhabits_harness_without_role_claim():
    text = (ROOT / ".codex" / "agents" / "readiness-bridge.toml").read_text(
        encoding="utf-8"
    )

    assert "inhabit the Codex harness" in text
    assert "scripts/continuation_readiness.py" in text
    assert "scripts/mailbox_monitor.py" in text
    assert "agentNN.toml" in text
    assert "A readiness bridge never upgrades itself silently." in text


def test_seat_coordinator_skill_defines_noop_fast_path():
    text = (ROOT / ".agents" / "skills" / "seat-coordinator" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "scripts/codex_protocol_model.py" in text
    assert "durable shared state beats chat memory" in text
    assert "seat_status.py coordinator --wave <N>" in text
    assert "No-op fast path" in text
    assert "do not send a new mailbox event" in text
    assert "scripts/wave_gate_check.py <wave>" in text
    assert "Coordinator may write" in text
    assert "user-consent-required" in text
