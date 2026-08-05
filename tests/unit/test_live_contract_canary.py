"""Offline contract tests for the manual live-provider canary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from scripts import live_contract_canary as canary


ROOT = Path(__file__).resolve().parents[2]


def _base(target: str = "runway-act-two", budget: str = "0.15") -> dict[str, str]:
    environment = {
        canary.TARGET_ENV: target,
        canary.APPROVAL_ENV: canary.APPROVAL_PHRASE,
        canary.MAX_COST_ENV: budget,
    }
    if target == "windows-liveportrait-performance":
        environment[canary.WINDOWS_RUNNER_AUTHORIZATION_ENV] = (
            canary.WINDOWS_RUNNER_AUTHORIZATION_PHRASE
        )
    return environment


def test_script_direct_invocation_resolves_repository_modules():
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    environment.update(_base())

    result = subprocess.run(
        [sys.executable, "-S", "scripts/live_contract_canary.py", "check-inputs"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "live-contract preflight passed" in result.stdout.lower()


@pytest.mark.parametrize(
    ("target", "budget", "selector"),
    [
        ("runway-act-two", "0.15", "test_act_two_minimal_call_returns_mp4"),
        ("runway-act-two", "0.20", "test_act_two_minimal_call_returns_mp4"),
        (
            "windows-liveportrait-performance",
            "0.00",
            "test_live_portrait_windows_round_trip",
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
        _base("windows-liveportrait-performance", "0.01"),
        _base("windows-liveportrait-performance", "-0.01"),
    ],
)
def test_input_contract_refuses_defaults_ambiguity_and_unsafe_budgets(environment):
    with pytest.raises(canary.CanaryPreflightError):
        canary.validate_inputs(environment)


def test_windows_input_contract_requires_ephemeral_jit_runner_confirmation():
    environment = _base("windows-liveportrait-performance", "0.00")
    environment.pop(canary.WINDOWS_RUNNER_AUTHORIZATION_ENV)
    with pytest.raises(canary.CanaryPreflightError, match="ephemeral JIT runner"):
        canary.validate_inputs(environment)

    cloud_environment = _base()
    cloud_environment[canary.WINDOWS_RUNNER_AUTHORIZATION_ENV] = (
        canary.WINDOWS_RUNNER_AUTHORIZATION_PHRASE
    )
    with pytest.raises(canary.CanaryPreflightError, match="only valid"):
        canary.validate_inputs(cloud_environment)


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
            "windows-liveportrait-performance",
            "0.00",
            "PERFORMANCE_COMFYUI_SERVER_URL",
            "PERFORMANCE_COMFYUI_API_KEY",
        ),
    ],
)
@pytest.mark.parametrize(
    "url",
    [
        "http://worker.example.test",
        "https://user:pass@worker.example.test",
        "https://worker.example.test/?token=secret",
        "https://worker.example.test/proxy-prefix",
        "https://127.0.0.1",
        "https://metadata.google.internal",
    ],
)
def test_worker_secret_contract_rejects_unsafe_origins(
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


def test_windows_target_requires_the_fixed_mac_loopback_tunnel():
    environment = _base("windows-liveportrait-performance", "0.00")
    environment.update(
        {
            "COMFYUI_SERVER_URL": "https://production.example.test",
            "COMFYUI_API_KEY": "p" * 32,
            "PERFORMANCE_COMFYUI_API_KEY": "w" * 32,
        }
    )
    name, target, _budget = canary.validate_inputs(environment)
    with pytest.raises(canary.CanaryPreflightError, match="fixed Mac loopback tunnel"):
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


def test_windows_runner_preserves_dedicated_and_image_worker_configuration(
    monkeypatch,
):
    environment = _base("windows-liveportrait-performance", "0.00")
    environment.update(
        {
            "COMFYUI_SERVER_URL": "https://production.example.test",
            "COMFYUI_API_KEY": "p" * 32,
            "PERFORMANCE_COMFYUI_SERVER_URL": canary.WINDOWS_LIVEPORTRAIT_ORIGIN,
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
        "windows-liveportrait-performance"
    ].test_selector
    assert seen["kwargs"]["env"]["COMFYUI_SERVER_URL"] == (
        "https://production.example.test"
    )
    assert seen["kwargs"]["env"]["COMFYUI_API_KEY"] == "p" * 32
    assert seen["kwargs"]["env"]["PERFORMANCE_COMFYUI_SERVER_URL"] == (
        canary.WINDOWS_LIVEPORTRAIT_ORIGIN
    )
    assert seen["kwargs"]["env"]["PERFORMANCE_COMFYUI_API_KEY"] == "k" * 32


def test_windows_probe_binds_exact_readiness_and_shipping_graph(monkeypatch):
    import comfyui_client
    import performance.worker_readiness as worker_readiness

    environment = _base("windows-liveportrait-performance", "0.00")
    environment.update(
        {
            "PERFORMANCE_COMFYUI_SERVER_URL": canary.WINDOWS_LIVEPORTRAIT_ORIGIN,
            "PERFORMANCE_COMFYUI_API_KEY": "w" * 32,
        }
    )
    object_info = json.loads(
        (ROOT / "tests/fixtures/liveportrait_object_info.json").read_text()
    )
    seen = {}
    real_validate = comfyui_client.ComfyUIClient._validate_workflow_contract

    def fake_require(settings_obj):
        seen["readiness"] = settings_obj
        return {"status": "ready", "role": "performance-liveportrait"}

    class Client:
        _validate_workflow_contract = staticmethod(real_validate)

        def __init__(self, origin, **kwargs):
            seen["client"] = (origin, kwargs)

        def get_system_stats(self):
            return {"system": {}, "devices": []}

        def get_object_info(self):
            return object_info

    monkeypatch.setattr(
        worker_readiness, "require_liveportrait_worker_ready", fake_require
    )
    monkeypatch.setattr(comfyui_client, "ComfyUIClient", Client)

    canary.probe_worker(environment)

    assert seen["readiness"].performance_comfyui_server_url == (
        canary.WINDOWS_LIVEPORTRAIT_ORIGIN
    )
    assert seen["client"] == (
        canary.WINDOWS_LIVEPORTRAIT_ORIGIN,
        {
            "auth_token": "w" * 32,
            "connect_timeout": 2.0,
            "read_timeout": 5.0,
        },
    )


def test_workflow_is_manual_only_default_inert_and_immutable():
    workflow = Path(".github/workflows/live-contract-canary.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "\n  push:" not in workflow
    assert "default: none" in workflow
    assert "default: '0'" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "\npermissions:\n  contents: read\n" in workflow
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "name: live-contract-canary" in workflow
    assert "timeout-minutes: 15" in workflow
    assert workflow.count("deployments: write") == 1
    assert "\n  runway-fence:" not in workflow
    assert "python scripts/live_contract_canary.py verify-runway-fence" in workflow
    assert "CANARY_AUTHORITY_GITHUB_TOKEN" in workflow
    assert "- windows-liveportrait-performance" in workflow
    assert (
        "runs-on: [self-hosted, macOS, content-liveportrait-ephemeral-jit]"
        in workflow
    )
    assert "windows_runner_authorization:" in workflow
    assert canary.WINDOWS_RUNNER_AUTHORIZATION_ENV in workflow
    windows_job = workflow.split(
        "  windows-liveportrait-canary:\n", 1
    )[1]
    windows_job_environment = windows_job.split("    env:\n", 1)[1].split(
        "    steps:\n", 1
    )[0]
    assert "PERFORMANCE_COMFYUI_API_KEY" not in windows_job_environment
    assert windows_job.count(
        "PERFORMANCE_COMFYUI_API_KEY: "
        "${{ secrets.PERFORMANCE_COMFYUI_API_KEY }}"
    ) == 3
    assert "CANARY_VENV: ${{ runner.temp }}/content-liveportrait-canary-venv" in (
        windows_job_environment
    )
    assert 'python -m venv --clear "$CANARY_VENV"' in windows_job
    assert "pip install --no-cache-dir --no-deps" in windows_job
    for requirement in (
        "pytest==8.4.2",
        "Pillow==11.3.0",
        "python-dotenv==1.2.1",
        "requests==2.32.5",
        "certifi==2026.2.25",
        "charset-normalizer==3.4.6",
        "idna==3.11",
        "urllib3==2.6.3",
        "iniconfig==2.3.0",
        "packaging==26.0",
        "pluggy==1.6.0",
        "Pygments==2.19.2",
    ):
        assert f"'{requirement}'" in windows_job
    assert "sudo apt-get install --yes --no-install-recommends ffmpeg" in workflow
    assert "PERFORMANCE_COMFYUI_SERVER_URL: http://127.0.0.1:18189" in workflow
    assert "python scripts/live_contract_canary.py probe-worker" in workflow
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
    assert "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f" in workflow
    assert "path: ${{ runner.temp }}/live-contract-canary/" in workflow
    assert "if-no-files-found: warn" in workflow
    live_job = workflow.split("  live-canary:\n", 1)[1]
    job_env = live_job.split("    env:\n", 1)[1].split("    steps:\n", 1)[0]
    assert "runner.temp" not in job_env


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
        "sha": "a" * 40,
        "payload": {
            "schema_version": 1,
            "target": "runway-act-two",
            "logical_attempt": f"v3-{canary.RUNWAY_FIXTURE_SHA256[:8]}",
            "fixture_sha256": canary.RUNWAY_FIXTURE_SHA256,
            "source_sha": "a" * 40,
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
    assert create_payload["payload"]["source_sha"] == "a" * 40


def test_runway_recovery_rejects_deployment_from_another_source_commit(
    monkeypatch,
    tmp_path,
):
    environment = {
        **_github_fence_environment(tmp_path),
        "GITHUB_SHA": "c" * 40,
    }

    def fake_api(method, path, *, token, payload=None, accepted_statuses=(200,)):
        if method == "GET" and "/deployments?" in path:
            return 200, [_deployment()]
        raise AssertionError("source drift must fail before deployment status lookup")

    monkeypatch.setattr(canary, "_github_api_json", fake_api)
    with pytest.raises(canary.CanaryPreflightError, match="source SHA drifted"):
        canary.verify_runway_fence(environment)


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


def test_terminal_runway_result_finalizes_deployment_status(monkeypatch, tmp_path):
    task_id = "d9f3cd8d-55c8-4a26-b2c4-b3ea0b0d7f9b"
    environment = _github_fence_environment(tmp_path)
    calls = []

    def fake_api(method, path, *, token, payload=None, accepted_statuses=(200,)):
        calls.append((method, path, payload))
        if method == "GET" and "/deployments?" in path:
            return 200, [_deployment()]
        if method == "GET":
            return 200, [
                {"state": "in_progress", "description": f"runway_task_id={task_id}"}
            ]
        return 201, {"id": 100}

    monkeypatch.setattr(canary, "_github_api_json", fake_api)
    canary.finalize_runway_deployment(environment, task_id, "succeeded")
    assert calls[-1][0] == "POST"
    assert calls[-1][2]["state"] == "success"
    assert calls[-1][2]["description"] == f"runway_task_id={task_id}"


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
        Path("tests/integration/test_live_portrait_smoke.py"),
    ):
        source = path.read_text()
        assert "pytest.fail(" in source
        assert "pytest.skip(" not in source


def test_liveportrait_fixture_encoder_normalizes_odd_h264_geometry(
    monkeypatch,
    tmp_path,
):
    """The hash-pinned 1254px sheet produces odd 627px panels."""
    from PIL import Image
    from tests.integration import test_live_portrait_smoke as smoke

    panels = [Image.new("RGB", (627, 627), color=(index, 0, 0)) for index in range(4)]
    monkeypatch.setattr(smoke, "_load_verified_expression_panels", lambda: panels)
    seen: dict[str, list[str]] = {}

    def fake_run(command, **_kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)
    smoke._make_test_driving_video(str(tmp_path / "driving.mp4"), frames=2)

    command = seen["command"]
    assert command[command.index("-vf") + 1] == "pad=ceil(iw/2)*2:ceil(ih/2)*2"
