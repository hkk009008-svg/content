"""Tests for the executable Codex protocol harness model."""

from __future__ import annotations

import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import codex_protocol_model as model  # noqa: E402


def test_render_mermaid_contains_required_harness_nodes() -> None:
    diagram = model.render_mermaid()

    assert "User principal" in diagram
    assert "Codex CLI harness" in diagram
    assert "Durable shared state" in diagram
    assert "Mailbox sent/ + seen cursors" in diagram
    assert "coordinator" in diagram


def test_render_live_loop_contains_operational_evidence_sources() -> None:
    loop = model.render_live_loop()

    assert "seat_status.py" in loop
    assert "git log" in loop
    assert "gate scripts" in loop
    assert "mailbox bodies" in loop
    assert "committed files" in loop
    assert "Push remains user-gated" in loop


def test_coordinator_invariants_pin_unpinned_cursor_and_single_route() -> None:
    summary = model.render_surface_summary()

    assert "never consume coordinator cursor" in summary
    assert "one coordinator-to-all route if needed" in summary


def test_agent_extension_modules_are_guardrails_not_role_replacements() -> None:
    assert model.is_agent_extension_name("agent01.toml")
    assert model.is_agent_extension_name("agent42.toml")
    assert not model.is_agent_extension_name("agent1.toml")
    assert not model.is_agent_extension_name("protocol-director.toml")

    summary = model.render_agent_extension_summary(
        ["protocol-director.toml", "agent04.toml", "agent01.toml"]
    )

    assert "agent guardrail extensions: agent01.toml, agent04.toml" in summary
    assert "extend the harness" in summary
    assert "do not replace built-in role agents" in summary
    assert "mailbox cursor rules" in summary


def test_render_start_session_inhabitance_contract() -> None:
    text = model.render_start_session_inhabitance(["agent02.toml", "protocol-director.toml"])

    assert "Next start session" in text
    assert "inhabit the Codex harness as readiness bridge" in text
    assert "scripts/continuation_readiness.py" in text
    assert "do not consume cursors" in text
    assert "core agent modules" in text
    assert "agent guardrail extensions: agent02.toml" in text
    assert "explicit seat or coordinator instruction" in text


def test_runtime_env_contract_infers_live_seat_and_user_gated_side_effects() -> None:
    text = model.render_runtime_env_contract(
        {
            "CODEX_SEAT": "director",
            "GIT_INDEX_FILE": "/repo/.git/index-codex-director",
        }
    )

    assert "Runtime env contract" in text
    assert "CODEX_AGENT_MODE=live-seat" in text
    assert "CODEX_AGENT_ROLE=director" in text
    assert "CODEX_SEAT=director" in text
    assert "CODEX_CAPABILITY_MODE=seat-local" in text
    assert "CODEX_MUTATION_SCOPE=seat-owned" in text
    assert "GIT_INDEX_FILE=/repo/.git/index-codex-director" in text
    assert "env does not authorize push, lock-claim side effects, paid API spend, or pod spend" in text


def test_runtime_env_contract_defaults_to_readiness_and_models_coordinator() -> None:
    readiness_text = model.render_runtime_env_contract({})
    coordinator_text = model.render_runtime_env_contract(
        {
            "CODEX_AGENT_MODE": "coordinator",
            "CODEX_AGENT_ROLE": "coordinator",
            "CODEX_CAPABILITY_MODE": "capacity-max",
        }
    )

    assert "CODEX_AGENT_MODE=readiness-bridge" in readiness_text
    assert "CODEX_AGENT_ROLE=readiness-bridge" in readiness_text
    assert "CODEX_CAPABILITY_MODE=read-only" in readiness_text
    assert "CODEX_MUTATION_SCOPE=none" in readiness_text
    assert "GIT_INDEX_FILE=(unset)" in readiness_text

    assert "CODEX_AGENT_MODE=coordinator" in coordinator_text
    assert "CODEX_AGENT_ROLE=coordinator" in coordinator_text
    assert "CODEX_CAPABILITY_MODE=capacity-max" in coordinator_text
    assert "CODEX_MUTATION_SCOPE=coordination-only" in coordinator_text
    assert "coordinator remains unpinned; no coordinator cursor is consumed" in coordinator_text


def test_render_protocol_assembly_map_places_portions_by_folder_intent() -> None:
    text = model.render_protocol_assembly_map()

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
