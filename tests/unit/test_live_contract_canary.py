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
    assert workflow.count("deployments: write") == 1
    assert "\n  runway-fence:" not in workflow
    assert "python scripts/live_contract_canary.py verify-runway-fence" in workflow
    assert "CANARY_AUTHORITY_GITHUB_TOKEN" in workflow
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
    assert "sudo apt-get install --yes --no-install-recommends ffmpeg" in workflow
    assert (
        "inputs.target == 'runway-act-two' || "
        "inputs.target == 'runpod-liveportrait-performance'"
        in workflow
    )
    refs = re.findall(r"uses:\s+[^@\s]+@([^\s#]+)", workflow)
    assert refs and all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in refs)


def test_runway_canary_uses_owned_hash_verified_synthetic_media():
    source = Path("tests/integration/test_act_two_smoke.py").read_text()
    assert "testsrc2" not in source
    assert "raw.githubusercontent.com" not in source
    assert "97471b9377c817251c86dbb58982464d7586b6b3d800936683f900da668c0fb6" in source
    assert "hmac.compare_digest" in source
    assert "Image.blend" in source
    assert '"-frames:v", str(frame_count)' in source


def test_workflow_pins_the_audited_runway_sdk():
    workflow = Path(".github/workflows/live-contract-canary.yml").read_text()
    assert "'runwayml==4.14.0'" in workflow


def test_workflow_restores_and_retains_complete_runway_attempt_state():
    workflow = Path(".github/workflows/live-contract-canary.yml").read_text()
    assert "LIVE_CONTRACT_CANARY_LEDGER_PATH" in workflow
    assert "LIVE_CONTRACT_CANARY_FIXTURE_DIR" in workflow
    assert "actions/cache/restore@caa296126883cff596d87d8935842f9db880ef25" in workflow
    assert "actions/cache/save@caa296126883cff596d87d8935842f9db880ef25" in workflow
    assert "runway-act-two-ledger-v3-97471b93-" in workflow
    assert "restore-keys:" in workflow
    assert workflow.count("if: always() && inputs.target == 'runway-act-two'") == 2
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in workflow
    assert "path: ${{ runner.temp }}/live-contract-canary/" in workflow
    assert "if-no-files-found: warn" in workflow


def _github_fence_environment(tmp_path: Path) -> dict[str, str]:
    return {
        **_base(),
        "GITHUB_REPOSITORY": "owner/repository",
        canary.RUNWAY_AUTHORITY_TOKEN_ENV: "g" * 40,
        "GITHUB_SHA": "a" * 40,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ID": "1234",
        "GITHUB_RUN_ATTEMPT": "1",
    }


def _deployment(deployment_id: int = 42) -> dict:
    return {
        "id": deployment_id,
        "payload": {
            "schema_version": 1,
            "target": "runway-act-two",
            "logical_attempt": f"v3-{canary.RUNWAY_FIXTURE_SHA256[:8]}",
            "fixture_sha256": canary.RUNWAY_FIXTURE_SHA256,
            "owner_run_id": "1234",
            "owner_run_attempt": "1",
        },
    }


def test_runway_claim_is_created_only_at_the_provider_boundary(
    monkeypatch,
    tmp_path,
):
    environment = _github_fence_environment(tmp_path)
    calls = []
    list_calls = 0

    def fake_api(method, path, *, token, payload=None, accepted_statuses=(200,)):
        nonlocal list_calls
        calls.append((method, path, payload, accepted_statuses))
        assert token == "g" * 40
        if method == "GET" and "/deployments?" in path:
            list_calls += 1
            return (200, [] if list_calls == 1 else [_deployment()])
        if method == "GET" and "/statuses" in path:
            return 200, []
        assert method == "POST" and path.endswith("/deployments")
        return 201, _deployment()

    monkeypatch.setattr(canary, "_github_api_json", fake_api)
    assert canary.claim_runway_submission(environment) == 42
    create_payload = next(payload for method, _path, payload, _ in calls if method == "POST")
    assert create_payload["task"] == canary.RUNWAY_AUTHORITY_TASK
    assert create_payload["auto_merge"] is False
    assert create_payload["required_contexts"] == []


def test_stale_fresh_output_cannot_bypass_attempt_two_remote_recheck(
    monkeypatch,
    tmp_path,
):
    environment = {
        **_github_fence_environment(tmp_path),
        "GITHUB_RUN_ATTEMPT": "2",
        "LIVE_CONTRACT_CANARY_FENCE_FRESH": "true",
        canary.RUNWAY_LEDGER_ENV: str(tmp_path / "missing.sqlite3"),
        canary.RUNWAY_FIXTURE_DIR_ENV: str(tmp_path / "fixture"),
    }

    def fake_api(method, path, *, token, payload=None, accepted_statuses=(200,)):
        if "/statuses" in path:
            return 200, []
        return 200, [_deployment()]

    monkeypatch.setattr(canary, "_github_api_json", fake_api)
    with pytest.raises(canary.CanaryPreflightError, match="duplicate submission blocked"):
        canary.verify_runway_fence(environment)


def test_remote_deployment_task_id_rehydrates_retrieval_only_ledger(
    monkeypatch,
    tmp_path,
):
    task_id = "d9f3cd8d-55c8-4a26-b2c4-b3ea0b0d7f9b"
    environment = {
        **_github_fence_environment(tmp_path),
        "GITHUB_RUN_ATTEMPT": "2",
        canary.RUNWAY_LEDGER_ENV: str(tmp_path / "authority.sqlite3"),
        canary.RUNWAY_FIXTURE_DIR_ENV: str(tmp_path / "fixture"),
    }

    def fake_api(method, path, *, token, payload=None, accepted_statuses=(200,)):
        if "/statuses" in path:
            return 200, [{"description": f"runway_task_id={task_id}"}]
        return 200, [_deployment()]

    monkeypatch.setattr(canary, "_github_api_json", fake_api)
    canary.verify_runway_fence(environment)

    from cost_tracker import CostTracker

    with CostTracker(db_path=environment[canary.RUNWAY_LEDGER_ENV]) as tracker:
        attempt = tracker.get_latest_paid_attempt(
            video_id="live-contract-canary",
            shot_id="runway-act-two-fixture-v1",
            engine="ACT_ONE",
            operation="performance_capture",
        )
    assert attempt["provider_job_id"] == task_id
    assert attempt["state"] == "running"


def test_accepted_runway_task_is_appended_as_deployment_status(
    monkeypatch,
):
    task_id = "d9f3cd8d-55c8-4a26-b2c4-b3ea0b0d7f9b"
    environment = {
        **_github_fence_environment(Path("/tmp")),
        canary.RUNWAY_AUTHORITY_TOKEN_ENV: "t" * 40,
    }
    calls = []

    def fake_api(method, path, *, token, payload=None, accepted_statuses=(200,)):
        calls.append((method, path, payload))
        if method == "GET" and "/deployments?" in path:
            return 200, [_deployment()]
        if method == "GET":
            return 200, []
        return 201, {"id": 99}

    monkeypatch.setattr(canary, "_github_api_json", fake_api)
    canary.checkpoint_runway_task(environment, task_id)
    assert calls[-1][0] == "POST"
    assert calls[-1][2]["description"] == f"runway_task_id={task_id}"
    assert calls[-1][2]["auto_inactive"] is False


def test_non_main_runway_authority_is_refused_before_remote_write(tmp_path):
    environment = {
        **_github_fence_environment(tmp_path),
        "GITHUB_REF": "refs/heads/feature/canary",
    }
    with pytest.raises(canary.CanaryPreflightError, match="restricted to main"):
        canary.claim_runway_submission(environment)


def test_conflicting_deployment_task_ids_fail_closed():
    statuses = [
        {"description": "runway_task_id=d9f3cd8d-55c8-4a26-b2c4-b3ea0b0d7f9b"},
        {"description": "runway_task_id=ad4fdc3e-3b76-45a0-9136-9f2ea15cb978"},
    ]
    with pytest.raises(canary.CanaryPreflightError, match="conflicting task IDs"):
        canary._deployment_task_id(statuses)


def test_configured_live_tests_fail_instead_of_skipping_on_empty_result():
    for path in (
        Path("tests/integration/test_act_two_smoke.py"),
        Path("tests/integration/test_pulid_smoke.py"),
        Path("tests/integration/test_live_portrait_smoke.py"),
    ):
        source = path.read_text()
        assert "pytest.fail(" in source
        assert "pytest.skip(" not in source
