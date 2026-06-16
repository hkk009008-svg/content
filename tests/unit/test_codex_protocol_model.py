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
    assert "CODEX_AUTHORITY_SCOPE=seat-owned" in text
    assert "CODEX_MAILBOX_POLICY=seat-read-consume-intentional" in text
    assert "CODEX_GIT_POLICY=per-seat-index-for-cursor-status" in text
    assert "CODEX_VERIFICATION_POLICY=request-operator-go" in text
    assert "CODEX_CONTEXT_SOURCES=seat-mailbox-owned-files-gate-evidence" in text
    assert "CODEX_OUTPUT_CONTRACT=seat-artifact-or-operator-request" in text
    assert "CODEX_DECISION_BOUNDARY=lane-owned-seat" in text
    assert "CODEX_NEXT_ACTION_POLICY=read-mail-then-act-or-report-idle" in text
    assert "CODEX_SIDE_EFFECT_POLICY=user-consent-required" in text
    assert "GIT_INDEX_FILE=/repo/.git/index-codex-director" in text
    assert "env does not authorize push, lock-claim side effects, paid API spend, or pod spend" in text


def test_runtime_env_contract_models_operator_and_specialist_authority() -> None:
    operator_text = model.render_runtime_env_contract(
        {
            "CODEX_SEAT": "operator2",
            "GIT_INDEX_FILE": "/repo/.git/index-codex-operator2",
        }
    )
    specialist_text = model.render_runtime_env_contract(
        {
            "CODEX_AGENT_MODE": "subagent",
            "CODEX_AGENT_ROLE": "lane-v-verifier",
        }
    )

    assert "CODEX_AGENT_ROLE=operator2" in operator_text
    assert "CODEX_VERIFICATION_POLICY=independent-go-nits-fail" in operator_text
    assert "CODEX_AUTHORITY_SCOPE=seat-owned" in operator_text

    assert "CODEX_AGENT_MODE=subagent" in specialist_text
    assert "CODEX_AGENT_ROLE=lane-v-verifier" in specialist_text
    assert "CODEX_MUTATION_SCOPE=read-only-verification" in specialist_text
    assert "CODEX_AUTHORITY_SCOPE=parent-scoped" in specialist_text
    assert "CODEX_MAILBOX_POLICY=parent-scoped" in specialist_text
    assert "CODEX_VERIFICATION_POLICY=read-only-review-no-go" in specialist_text
    assert "CODEX_CONTEXT_SOURCES=parent-prompt-plus-allowed-artifacts" in specialist_text
    assert "CODEX_OUTPUT_CONTRACT=bounded-findings-to-parent" in specialist_text
    assert "CODEX_DECISION_BOUNDARY=parent-scoped-no-seat-authority" in specialist_text
    assert "CODEX_NEXT_ACTION_POLICY=return-evidence-then-stop" in specialist_text


def test_runtime_env_contract_infers_mode_from_explicit_role() -> None:
    coordinator_text = model.render_runtime_env_contract(
        {
            "CODEX_AGENT_ROLE": "coordinator",
        }
    )
    verifier_text = model.render_runtime_env_contract(
        {
            "CODEX_AGENT_ROLE": "money-gate-reviewer",
        }
    )

    assert "CODEX_AGENT_MODE=coordinator" in coordinator_text
    assert "CODEX_CAPABILITY_MODE=capacity-max" in coordinator_text
    assert "CODEX_MUTATION_SCOPE=coordination-only" in coordinator_text
    assert "CODEX_AUTHORITY_SCOPE=all-scope-reconcile" in coordinator_text
    assert "CODEX_MAILBOX_POLICY=all-scope-read-no-consume" in coordinator_text
    assert "CODEX_VERIFICATION_POLICY=reconcile-operator-go-only" in coordinator_text
    assert "CODEX_CONTEXT_SOURCES=all-scope-mailbox-inventory-locks-gates" in coordinator_text
    assert "CODEX_OUTPUT_CONTRACT=capacity-board-or-single-route" in coordinator_text
    assert "CODEX_DECISION_BOUNDARY=all-scope-routing-no-production-fixes" in coordinator_text
    assert "CODEX_NEXT_ACTION_POLICY=build-board-reconcile-once" in coordinator_text

    assert "CODEX_AGENT_MODE=subagent" in verifier_text
    assert "CODEX_AGENT_ROLE=money-gate-reviewer" in verifier_text
    assert "CODEX_MUTATION_SCOPE=read-only-verification" in verifier_text
    assert "CODEX_VERIFICATION_POLICY=read-only-review-no-go" in verifier_text


def test_runtime_env_contract_codifies_side_effect_policy() -> None:
    text = model.render_runtime_env_contract(
        {
            "CODEX_SEAT": "operator",
            "GIT_INDEX_FILE": "/repo/.git/index-codex-operator",
        }
    )

    assert "CODEX_SIDE_EFFECT_POLICY=user-consent-required" in text
    assert "push, lock-claim side effects, paid API spend, and pod spend" in text


def test_runtime_env_contract_defaults_to_readiness_and_models_coordinator() -> None:
    readiness_text = model.render_runtime_env_contract({})
    coordinator_text = model.render_runtime_env_contract(
        {
            "CODEX_AGENT_MODE": "coordinator",
            "CODEX_AGENT_ROLE": "coordinator",
            "CODEX_CAPABILITY_MODE": "capacity-max",
            "CODEX_SEAT": "director2",
        }
    )

    assert "CODEX_AGENT_MODE=readiness-bridge" in readiness_text
    assert "CODEX_AGENT_ROLE=readiness-bridge" in readiness_text
    assert "CODEX_CAPABILITY_MODE=read-only" in readiness_text
    assert "CODEX_MUTATION_SCOPE=none" in readiness_text
    assert "CODEX_AUTHORITY_SCOPE=report-only" in readiness_text
    assert "CODEX_MAILBOX_POLICY=read-only-no-consume" in readiness_text
    assert "CODEX_GIT_POLICY=env-u-git-index-read-only" in readiness_text
    assert "CODEX_VERIFICATION_POLICY=report-evidence-only" in readiness_text
    assert "CODEX_CONTEXT_SOURCES=repo-docs-mailbox-gates-readonly" in readiness_text
    assert "CODEX_OUTPUT_CONTRACT=readiness-report-and-blockers" in readiness_text
    assert "CODEX_DECISION_BOUNDARY=no-seat-authority" in readiness_text
    assert "CODEX_NEXT_ACTION_POLICY=report-then-stop-or-request-role" in readiness_text
    assert "CODEX_SIDE_EFFECT_POLICY=user-consent-required" in readiness_text
    assert "GIT_INDEX_FILE=(unset)" in readiness_text

    assert "CODEX_AGENT_MODE=coordinator" in coordinator_text
    assert "CODEX_AGENT_ROLE=coordinator" in coordinator_text
    assert "CODEX_SEAT=(ignored: director2)" in coordinator_text
    assert "CODEX_CAPABILITY_MODE=capacity-max" in coordinator_text
    assert "CODEX_MUTATION_SCOPE=coordination-only" in coordinator_text
    assert "CODEX_AUTHORITY_SCOPE=all-scope-reconcile" in coordinator_text
    assert "CODEX_MAILBOX_POLICY=all-scope-read-no-consume" in coordinator_text
    assert "CODEX_GIT_POLICY=env-u-git-index-or-temp-index" in coordinator_text
    assert "CODEX_VERIFICATION_POLICY=reconcile-operator-go-only" in coordinator_text
    assert "CODEX_CONTEXT_SOURCES=all-scope-mailbox-inventory-locks-gates" in coordinator_text
    assert "CODEX_OUTPUT_CONTRACT=capacity-board-or-single-route" in coordinator_text
    assert "CODEX_DECISION_BOUNDARY=all-scope-routing-no-production-fixes" in coordinator_text
    assert "CODEX_NEXT_ACTION_POLICY=build-board-reconcile-once" in coordinator_text
    assert "coordinator remains unpinned; no coordinator cursor is consumed" in coordinator_text


def test_main_renders_current_environment(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CODEX_SEAT", "director2")
    monkeypatch.setenv("GIT_INDEX_FILE", "/repo/.git/index-codex-director2")

    assert model.main() == 0

    out = capsys.readouterr().out
    assert "CODEX_AGENT_MODE=live-seat" in out
    assert "CODEX_AGENT_ROLE=director2" in out
    assert "CODEX_AUTHORITY_SCOPE=seat-owned" in out
    assert "CODEX_VERIFICATION_POLICY=request-operator-go" in out
    assert "GIT_INDEX_FILE=/repo/.git/index-codex-director2" in out


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
