"""Tests for the executable Codex protocol harness model."""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import codex_protocol_model as model  # noqa: E402


def test_kernel_names_active_invariants_and_demoted_runtime_concepts() -> None:
    text = model.render_kernel_contract()

    assert "Active kernel invariants" in text
    assert "durable shared state beats chat memory" in text
    assert "mailbox-first decisions" in text
    assert "explicit mode" in text
    assert "user-gated side effects" in text
    assert "operator verification-report GO" in text
    assert "Demoted optional concepts" in text
    assert "capacity-max cycle: explicit coordinator tool" in text
    assert "no-op evidence: only after a seat was actually queried or oriented" in text
    assert "Rotating Planning Relay: optional rare cross-seat planning pattern" in text
    assert "proof-bundle language: use concrete evidence names" in text


def test_live_loop_uses_concrete_evidence_and_not_default_ceremony() -> None:
    loop = model.render_live_loop()

    assert "mailbox bodies" in loop
    assert "gate output" in loop
    assert "smoke output" in loop
    assert "diff scope" in loop
    assert "Use the Rotating Planning Relay" not in loop
    assert "no-op evidence so the coordinator knows" not in loop
    assert "proof bundle" not in loop.lower()


def test_main_output_keeps_optional_relay_out_of_startup_surface() -> None:
    stream = io.StringIO()

    with contextlib.redirect_stdout(stream):
        rc = model.main()

    output = stream.getvalue()
    assert rc == 0
    assert "## Kernel Contract" in output
    assert "Active kernel invariants" in output
    assert "Demoted optional concepts" in output
    assert "Rotating Planning Relay" not in output
    assert "planning relay:" not in output.lower()


def test_surface_summary_omits_trigger_specific_relay_doctrine() -> None:
    summary = model.render_surface_summary()

    assert "Rotating Planning Relay" not in summary
    assert "planning relay:" not in summary.lower()
    assert "Active kernel invariants" in summary
    assert "Demoted optional concepts" in summary


def test_render_mermaid_contains_required_harness_nodes() -> None:
    diagram = model.render_mermaid()

    assert "User principal" in diagram
    assert "Codex CLI harness" in diagram
    assert "Durable shared state" in diagram
    assert "Mailbox sent/ + seen cursors" in diagram
    assert "coordinator" in diagram


def test_render_live_loop_contains_operational_evidence_sources() -> None:
    loop = model.render_live_loop()

    assert "newest same-seat handoff" in loop
    assert "docs/HANDOFF-<concrete-seat>-*.md" in loop
    assert "seat_status.py" in loop
    assert "git log" in loop
    assert "Always check mail before protocol decisions" in loop
    assert "state-asserting writes" in loop
    assert "gate scripts" in loop
    assert "mailbox bodies" in loop
    assert "committed files" in loop
    assert "Push remains user-gated" in loop


def test_render_live_loop_codifies_cycle_end_handoff_before_transplant() -> None:
    loop = model.render_live_loop()

    assert "cycle reaches a real completion boundary" in loop
    assert "assigned tasks are complete" in loop
    assert "durable handoff before transplant or context switch" in loop
    assert "exact next trigger" in loop


def test_coordinator_invariants_pin_unpinned_cursor_and_single_route() -> None:
    summary = model.render_surface_summary()

    assert "never consume coordinator cursor" in summary
    assert "one coordinator-to-all route if needed" in summary


def test_capacity_board_gate_is_required_before_active_task_board_routes() -> None:
    loop = model.render_live_loop()
    summary = model.render_surface_summary()

    assert "scripts/protocol_capacity_board.py --wave <wave>" in loop
    assert "--validate-route coordination/mailbox/sent/<event>.md" in loop
    assert "active coordinator task-board route" in loop
    assert "capacity-board route validation" in summary


def test_live_seat_behavior_sources_preserve_concrete_identity() -> None:
    assert model.SEAT_BEHAVIOR_SOURCE == {
        "director": "director2",
        "director2": "director2",
        "operator": "operator",
        "operator2": "operator",
    }
    assert model.behavior_source_for_seat("director") == "director2"
    assert model.behavior_source_for_seat("director2") == "director2"
    assert model.behavior_source_for_seat("operator") == "operator"
    assert model.behavior_source_for_seat("operator2") == "operator"
    assert model.behavior_source_for_seat("coordinator") is None
    assert model.behavior_source_for_seat("not-a-seat") is None

    director_text = model.render_runtime_env_contract(
        {
            "CODEX_SEAT": "director",
            "GIT_INDEX_FILE": "/repo/.git/index-codex-director",
        }
    )
    operator2_text = model.render_runtime_env_contract(
        {
            "CODEX_SEAT": "operator2",
            "GIT_INDEX_FILE": "/repo/.git/index-codex-operator2",
        }
    )

    assert "CODEX_AGENT_ROLE=director" in director_text
    assert "CODEX_SEAT=director" in director_text
    assert "CODEX_BEHAVIOR_SOURCE=director2" in director_text
    assert "GIT_INDEX_FILE=/repo/.git/index-codex-director" in director_text

    assert "CODEX_AGENT_ROLE=operator2" in operator2_text
    assert "CODEX_SEAT=operator2" in operator2_text
    assert "CODEX_BEHAVIOR_SOURCE=operator" in operator2_text
    assert "GIT_INDEX_FILE=/repo/.git/index-codex-operator2" in operator2_text


def test_render_planning_relay_codifies_rotating_baton_and_coordinator_start() -> None:
    relay = model.render_planning_relay()

    assert "Rotating Planning Relay" in relay
    assert "important cross-seat plan" in relay
    assert "starter is step 1" in relay
    assert "director -> operator -> director2 -> operator2" in relay
    assert "wraps after operator2 back to director" in relay
    assert "exactly four live-seat turns" in relay
    assert "coordinator-started plan" in relay
    assert "coordinator -> all four seats -> coordinator" in relay
    assert "one consolidated coordinator-to-all task board" in relay
    assert "no production work, verification verdict, lock, push, or inventory change is implied" in relay


def test_render_seat_subagent_development_codifies_all_seat_boundaries() -> None:
    text = model.render_seat_subagent_development()

    assert "Seat Subagent Development" in text
    assert "seats retain authority; subagents own bounded work" in text
    assert "director/director2: dispatch bounded implementer subagents" in text
    assert "operator/operator2: use read-only verifier helpers" in text
    assert "coordinator: use read-only reconciliation helpers" in text
    assert "Live seats and coordinator may choose bounded subagents at seat discretion" in text
    assert "does not require a separate user request for delegation" in text
    assert "Default behavior: every live seat and coordinator actively considers bounded subagents" in text
    assert "uses them when they add independent signal, capacity, or fresh verification" in text
    assert "Direct work remains acceptable for small, tightly coupled, or authority-sensitive work" in text
    assert "implementer -> spec review -> quality review -> seat synthesis" in text
    assert "no mailbox cursor, mailbox event, operator GO, coordinator route, push, lock, pod spend, or paid API spend" in text


def test_render_pair_operating_contract_codifies_efficient_pair_loop() -> None:
    text = model.render_pair_operating_contract()

    assert "Pair Operating Contract" in text
    assert "director -> operator is the fast path" in text
    assert "mailbox artifact, not chat" in text
    assert "Director sends one verify-request" in text
    assert "Operator waits for a fresh verify-request or shipping commit" in text
    assert "no duplicate Lane V" in text
    assert "No receipt/status churn" in text
    assert "first commit to land wins" in text
    assert "exact next trigger" in text
    assert "operator verification-report GO" in text


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
    assert "same-kind handoff first" in text
    assert "docs/HANDOFF-<seat-or-coordinator>-*.md" in text
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
    assert "CODEX_BEHAVIOR_SOURCE=director2" in text
    assert "fresh/transplanted live seat first finds the newest same-seat handoff" in text
    assert "env does not authorize push, lock-claim side effects, paid API spend, or pod spend" in text


def test_render_seat_contract_includes_six_fields_and_source_order() -> None:
    text = model.render_seat_contract(
        {
            "CODEX_SEAT": "director2",
            "GIT_INDEX_FILE": "/repo/.git/index-codex-director2",
        },
        objective="draft R-BRIEF",
        permissions="edit=yes commit=yes push=no spend=no lock=no",
        scope="docs/superpowers/briefs/example.md",
        verification="pytest tests/unit/test_example.py -q",
        done="HEAD changed-files unread verification push next-trigger",
    )

    assert "S-ROLE: live-seat / director2" in text
    assert "S-OBJ: draft R-BRIEF" in text
    assert "S-PERM: edit=yes commit=yes push=no spend=no lock=no" in text
    assert "S-SCOPE: docs/superpowers/briefs/example.md" in text
    assert "S-VERIFY: pytest tests/unit/test_example.py -q" in text
    assert "S-DONE: HEAD changed-files unread verification push next-trigger" in text
    assert "source order: user > git > mailbox > handoff > defaults" in text


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
    assert "CODEX_BEHAVIOR_SOURCE=operator" in operator_text

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
    assert "CODEX_BEHAVIOR_SOURCE=(none)" in specialist_text


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


def test_runtime_env_contract_accepts_coordinator_seat_compatibility_alias() -> None:
    text = model.render_runtime_env_contract(
        {
            "CODEX_SEAT": "coordinator",
            "GIT_INDEX_FILE": "/repo/.git/index-codex-coordinator",
        }
    )

    assert "CODEX_AGENT_MODE=coordinator" in text
    assert "CODEX_AGENT_ROLE=coordinator" in text
    assert "CODEX_SEAT=coordinator" in text
    assert "CODEX_CAPABILITY_MODE=capacity-max" in text
    assert "CODEX_MUTATION_SCOPE=coordination-only" in text
    assert "CODEX_AUTHORITY_SCOPE=all-scope-reconcile" in text
    assert "CODEX_MAILBOX_POLICY=all-scope-read-no-consume" in text
    assert "CODEX_GIT_POLICY=env-u-git-index-or-temp-index" in text
    assert "CODEX_VERIFICATION_POLICY=reconcile-operator-go-only" in text
    assert "CODEX_CONTEXT_SOURCES=all-scope-mailbox-inventory-locks-gates" in text
    assert "CODEX_OUTPUT_CONTRACT=capacity-board-or-single-route" in text
    assert "CODEX_DECISION_BOUNDARY=all-scope-routing-no-production-fixes" in text
    assert "CODEX_NEXT_ACTION_POLICY=build-board-reconcile-once" in text
    assert "GIT_INDEX_FILE=/repo/.git/index-codex-coordinator" in text
    assert "CODEX_SEAT=coordinator is a compatibility spelling" in text
    assert "coordinator remains unpinned; no coordinator cursor is consumed" in text
    assert "(ignored: coordinator)" not in text


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
    assert "CODEX_BEHAVIOR_SOURCE=director2" in out
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
