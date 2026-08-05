"""Offline contract tests for the manual live-provider canary."""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from scripts import live_contract_canary as canary


ROOT = Path(__file__).resolve().parents[2]


def _base(target: str = "runway-act-two", budget: str = "0.15") -> dict[str, str]:
    return {
        canary.TARGET_ENV: target,
        canary.APPROVAL_ENV: canary.APPROVAL_PHRASE,
        canary.MAX_COST_ENV: budget,
    }


@pytest.mark.parametrize(
    ("target", "budget", "selector"),
    [
        ("runway-act-two", "0.15", "test_act_two_minimal_call_returns_mp4"),
        ("runway-act-two", "0.20", "test_act_two_minimal_call_returns_mp4"),
        ("runpod-pulid-production", "0.04", "test_production_pulid_round_trip"),
        ("runpod-pulid-production", "0.05", "test_production_pulid_round_trip"),
        (
            "runpod-liveportrait-performance",
            "0.03",
            "test_live_portrait_pod_round_trip",
        ),
        (
            "runpod-liveportrait-performance",
            "0.05",
            "test_live_portrait_pod_round_trip",
        ),
    ],
)
def test_input_contract_accepts_only_bounded_fixed_selectors(target, budget, selector):
    name, contract, parsed_budget = canary.validate_inputs(_base(target, budget))
    assert name == target
    assert selector in contract.test_selector
    assert parsed_budget == canary.Decimal(budget)


@pytest.mark.parametrize(
    "environment",
    [
        {},
        _base("none", "0.15"),
        {**_base(), canary.APPROVAL_ENV: "I APPROVE ONE LIVE CONTRACT CANARY "},
        _base(budget="0"),
        _base(budget="NaN"),
        _base(budget="Infinity"),
        _base(budget="0.14"),
        _base(budget="0.201"),
        _base("runpod-pulid-production", "0.03"),
        _base("runpod-pulid-production", "0.06"),
        _base("runpod-liveportrait-performance", "0.02"),
        _base("runpod-liveportrait-performance", "0.06"),
    ],
)
def test_input_contract_refuses_defaults_ambiguity_and_unsafe_budgets(environment):
    with pytest.raises(canary.CanaryPreflightError):
        canary.validate_inputs(environment)


def test_secret_contract_is_target_specific_and_does_not_echo_secret(capsys):
    environment = _base()
    name, target, _budget = canary.validate_inputs(environment)
    secret = "super-secret-value-that-must-not-be-printed"
    environment["RUNWAYML_API_SECRET"] = secret

    canary.validate_secrets(name, target, environment)
    assert secret not in capsys.readouterr().out

    with pytest.raises(canary.CanaryPreflightError) as error:
        canary.validate_secrets(name, target, _base())
    assert secret not in str(error.value)


@pytest.mark.parametrize(
    ("target_name", "budget", "url_env", "token_env"),
    [
        (
            "runpod-pulid-production",
            "0.04",
            "COMFYUI_SERVER_URL",
            "COMFYUI_API_KEY",
        ),
        (
            "runpod-liveportrait-performance",
            "0.03",
            "PERFORMANCE_COMFYUI_SERVER_URL",
            "PERFORMANCE_COMFYUI_API_KEY",
        ),
    ],
)
@pytest.mark.parametrize(
    "url",
    [
        "http://pod.example.test",
        "https://user:pass@pod.example.test",
        "https://pod.example.test/?token=secret",
        "https://pod.example.test/proxy-prefix",
        "https://127.0.0.1",
        "https://metadata.google.internal",
    ],
)
def test_runpod_secret_contract_rejects_unsafe_origins(
    target_name,
    budget,
    url_env,
    token_env,
    url,
):
    environment = _base(target_name, budget)
    environment.update({url_env: url, token_env: "x" * 32})
    name, target, _budget = canary.validate_inputs(environment)
    with pytest.raises(canary.CanaryPreflightError):
        canary.validate_secrets(name, target, environment)


def test_performance_target_cannot_fall_back_to_production_endpoint_secrets():
    environment = _base("runpod-liveportrait-performance", "0.03")
    environment.update(
        {
            "COMFYUI_SERVER_URL": "https://production.example.test",
            "COMFYUI_API_KEY": "p" * 32,
        }
    )
    name, target, _budget = canary.validate_inputs(environment)
    with pytest.raises(canary.CanaryPreflightError, match="PERFORMANCE_COMFYUI_SERVER_URL"):
        canary.validate_secrets(name, target, environment)


def test_runner_invokes_only_the_constant_selector(monkeypatch):
    environment = _base()
    environment["RUNWAYML_API_SECRET"] = "r" * 32
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(canary.subprocess, "run", fake_run)
    assert canary.run_canary(environment) == 0
    assert seen["command"][3] == canary.TARGETS["runway-act-two"].test_selector
    assert seen["command"][4:] == ["-m", "e2e", "--maxfail=1", "-q"]
    assert seen["kwargs"]["timeout"] == 720


def test_performance_runner_maps_only_selected_endpoint_into_application_config(
    monkeypatch,
):
    environment = _base("runpod-liveportrait-performance", "0.03")
    environment.update(
        {
            "COMFYUI_SERVER_URL": "https://production.example.test",
            "COMFYUI_API_KEY": "p" * 32,
            "PERFORMANCE_COMFYUI_SERVER_URL": "https://performance.example.test",
            "PERFORMANCE_COMFYUI_API_KEY": "k" * 32,
        }
    )
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(canary.subprocess, "run", fake_run)
    assert canary.run_canary(environment) == 0
    assert seen["command"][3] == canary.TARGETS[
        "runpod-liveportrait-performance"
    ].test_selector
    assert seen["kwargs"]["env"]["COMFYUI_SERVER_URL"] == (
        "https://performance.example.test"
    )
    assert seen["kwargs"]["env"]["COMFYUI_API_KEY"] == "k" * 32


@pytest.mark.parametrize(
    ("target_name", "budget", "url_env", "token_env", "required_nodes"),
    [
        (
            "runpod-pulid-production",
            "0.04",
            "COMFYUI_SERVER_URL",
            "COMFYUI_API_KEY",
            {
                node["class_type"]
                for node in json.loads((ROOT / "pulid.json").read_text()).values()
            },
        ),
        (
            "runpod-liveportrait-performance",
            "0.03",
            "PERFORMANCE_COMFYUI_SERVER_URL",
            "PERFORMANCE_COMFYUI_API_KEY",
            {
                "LoadImage",
                "VHS_LoadVideoPath",
                "LivePortraitProcess",
                "VHS_VideoCombine",
            },
        ),
    ],
)
def test_runpod_probe_checks_selected_gateway_auth_and_required_nodes(
    monkeypatch,
    target_name,
    budget,
    url_env,
    token_env,
    required_nodes,
):
    environment = _base(target_name, budget)
    environment.update({url_env: "https://pod.example.test", token_env: "k" * 32})
    calls = []
    responses = {
        "/health/ready": {"status": "ready"},
        "/system_stats": {"system": {}},
        "/object_info": {name: {} for name in required_nodes},
    }

    def fake_request(origin, path, *, token):
        calls.append((origin, path, token))
        return responses[path]

    monkeypatch.setattr(canary, "_request_runpod_json", fake_request)
    canary.probe_runpod(environment)
    assert calls == [
        ("https://pod.example.test", "/health/ready", None),
        ("https://pod.example.test", "/system_stats", "k" * 32),
        ("https://pod.example.test", "/object_info", "k" * 32),
    ]


def test_workflow_is_manual_only_default_inert_and_immutable():
    workflow = Path(".github/workflows/live-contract-canary.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "\n  push:" not in workflow
    assert "default: none" in workflow
    assert "default: '0'" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "\npermissions:\n  contents: read\n" in workflow
    assert "name: live-contract-canary" in workflow
    assert "timeout-minutes: 15" in workflow
    assert "- runpod-pulid-production" in workflow
    assert "- runpod-liveportrait-performance" in workflow
    assert (
        "inputs.target == 'runpod-pulid-production' && secrets.COMFYUI_SERVER_URL"
        in workflow
    )
    assert (
        "inputs.target == 'runpod-liveportrait-performance' "
        "&& secrets.PERFORMANCE_COMFYUI_SERVER_URL"
        in workflow
    )
    assert "secrets.PERFORMANCE_COMFYUI_SERVER_URL" in workflow
    assert "secrets.PERFORMANCE_COMFYUI_API_KEY" in workflow
    refs = re.findall(r"uses:\s+[^@\s]+@([^\s#]+)", workflow)
    assert refs and all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in refs)


def test_configured_live_tests_fail_instead_of_skipping_on_empty_result():
    for path in (
        Path("tests/integration/test_act_two_smoke.py"),
        Path("tests/integration/test_pulid_smoke.py"),
        Path("tests/integration/test_live_portrait_smoke.py"),
    ):
        source = path.read_text()
        assert "pytest.fail(" in source
        assert "pytest.skip(" not in source
