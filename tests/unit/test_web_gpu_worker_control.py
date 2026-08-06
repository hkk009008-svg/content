from __future__ import annotations

import json
import plistlib
from pathlib import Path
import subprocess
import sys

from flask import Flask
import pytest

import web_gpu_worker_control as control


def _status(**overrides):
    value = {
        "schema_version": 1,
        "state": "stopped",
        "can_start": True,
        "gpu_busy": False,
        "gpu_used_mib": 1024,
        "gpu_utilization_percent": 0,
        "last_task_result": 0,
        "message": "The Windows worker is stopped and available.",
    }
    value.update(overrides)
    return value


def _app():
    app = Flask(__name__)
    app.register_blueprint(control.gpu_worker_control_api)
    return app


def _write_locked(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o600)


def _configured_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    known_hosts = home / ".ssh/known_hosts"
    tunnel_key = home / ".ssh/content_gpu_worker_ed25519"
    control_key = home / ".ssh/content_gpu_control_ed25519"
    for path in (known_hosts, tunnel_key, control_key):
        _write_locked(path)
    arguments = [
        "/usr/bin/ssh", "-F", "/dev/null", "-N", "-T",
        "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
        "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3", "-o", "TCPKeepAlive=yes",
        "-o", "GatewayPorts=no", "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-i", str(tunnel_key),
        "-L", "127.0.0.1:18189:127.0.0.1:8189",
        "worker-user@192.168.50.16",
    ]
    plist = home / "Library/LaunchAgents/com.content.liveportrait-tunnel.plist"
    _write_locked(plist, plistlib.dumps({"Label": control._LABEL, "ProgramArguments": arguments}))
    return home


def test_target_is_derived_only_from_locked_launch_agent(tmp_path: Path) -> None:
    target = control._load_target(_configured_home(tmp_path))
    argv = control._ssh_arguments("start", target)

    assert target.destination == "worker-user@192.168.50.16"
    assert argv[0] == "/usr/bin/ssh"
    assert argv[-2:] == ["worker-user@192.168.50.16", "start"]
    assert "ClearAllForwardings=yes" in argv
    assert "-L" not in argv
    assert "shell" not in " ".join(argv).lower()


def test_target_rejects_injected_ssh_option_and_permissive_key(tmp_path: Path) -> None:
    home = _configured_home(tmp_path)
    plist = home / "Library/LaunchAgents/com.content.liveportrait-tunnel.plist"
    payload = plistlib.loads(plist.read_bytes())
    payload["ProgramArguments"][-1:-1] = ["-o", "ProxyCommand=unsafe"]
    plist.write_bytes(plistlib.dumps(payload))
    plist.chmod(0o600)
    with pytest.raises(control.WorkerControlError, match="unapproved SSH option"):
        control._load_target(home)

    home = _configured_home(tmp_path / "second")
    (home / ".ssh/content_gpu_control_ed25519").chmod(0o644)
    with pytest.raises(control.WorkerControlError, match="mode 0600 or stricter"):
        control._load_target(home)


@pytest.mark.parametrize("mutation", ["omit", "duplicate"])
def test_target_requires_exactly_one_empty_ssh_configuration(
    tmp_path: Path,
    mutation: str,
) -> None:
    home = _configured_home(tmp_path)
    plist = home / "Library/LaunchAgents/com.content.liveportrait-tunnel.plist"
    payload = plistlib.loads(plist.read_bytes())
    arguments = payload["ProgramArguments"]
    config_index = arguments.index("-F")
    if mutation == "omit":
        del arguments[config_index : config_index + 2]
    else:
        arguments[config_index:config_index] = ["-F", "/dev/null"]
    plist.write_bytes(plistlib.dumps(payload))
    plist.chmod(0o600)

    with pytest.raises(
        control.WorkerControlError,
        match="may not inherit SSH configuration",
    ):
        control._load_target(home)


def test_remote_output_is_strictly_projected(monkeypatch, tmp_path: Path) -> None:
    home = _configured_home(tmp_path)
    load_target = control._load_target
    monkeypatch.setattr(control, "_load_target", lambda: load_target(home))
    output = _status()
    output["endpoint"] = "do-not-project"
    monkeypatch.setattr(
        control,
        "_run_ssh",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(output).encode("utf-8"),
        ),
    )

    projected = control._remote_control("status")
    assert projected == _status()
    assert "endpoint" not in projected


def test_remote_process_output_is_hard_capped() -> None:
    with pytest.raises(control.WorkerControlError, match="failed closed"):
        control._run_capped_process(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 5000)"],
            timeout=5,
            output_limit=4096,
        )

    completed = control._run_capped_process(
        [
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('private' * 10000); sys.stdout.write('ok')",
        ],
        timeout=5,
        output_limit=4096,
    )
    assert completed.returncode == 0
    assert completed.stdout == b"ok"


def test_status_returns_token_without_authority_details(monkeypatch) -> None:
    monkeypatch.setattr(control, "_remote_control", lambda action: _status())
    with _app().test_client() as client:
        response = client.get("/api/runtime/gpu-worker-control")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state"] == "stopped"
    assert payload["control_token"] == control._CONTROL_TOKEN
    assert response.headers["Cache-Control"] == "no-store"
    assert "192.168" not in str(payload)
    assert "ssh" not in str(payload).lower()


def test_start_is_same_origin_token_bound_fixed_and_idempotent(monkeypatch) -> None:
    actions = []

    def remote(action):
        actions.append(action)
        if action == "start":
            return _status(state="starting", can_start=False, message="Launch requested.")
        return _status()

    monkeypatch.setattr(control, "_remote_control", remote)
    headers = {
        "Origin": "http://localhost",
        "Sec-Fetch-Site": "same-origin",
        "X-Content-Control-Token": control._CONTROL_TOKEN,
    }
    with _app().test_client() as client:
        response = client.post(
            "/api/runtime/gpu-worker-control/start", json={}, headers=headers
        )

    assert response.status_code == 202
    assert response.get_json()["state"] == "starting"
    assert actions == ["status", "start"]


@pytest.mark.parametrize(
    ("json_body", "headers", "remote_addr", "status"),
    [
        ({}, {"Origin": "http://localhost"}, "127.0.0.1", 403),
        ({"task": "anything"}, {"Origin": "http://localhost", "X-Content-Control-Token": control._CONTROL_TOKEN}, "127.0.0.1", 400),
        ({}, {"Origin": "https://evil.example", "X-Content-Control-Token": control._CONTROL_TOKEN}, "127.0.0.1", 403),
        ({}, {"Origin": "http://localhost", "X-Content-Control-Token": control._CONTROL_TOKEN}, "192.168.50.8", 403),
    ],
)
def test_start_rejects_missing_authority_fields_and_nonlocal_requests(
    monkeypatch, json_body, headers, remote_addr, status
) -> None:
    monkeypatch.setattr(
        control,
        "_remote_control",
        lambda action: pytest.fail("remote control must not run"),
    )
    with _app().test_client() as client:
        response = client.post(
            "/api/runtime/gpu-worker-control/start",
            json=json_body,
            headers=headers,
            environ_overrides={"REMOTE_ADDR": remote_addr},
        )
    assert response.status_code == status


def test_busy_gpu_blocks_start_without_mutation(monkeypatch) -> None:
    actions = []

    def remote(action):
        actions.append(action)
        return _status(
            can_start=False,
            gpu_busy=True,
            message="The Windows GPU is busy.",
        )

    monkeypatch.setattr(control, "_remote_control", remote)
    with _app().test_client() as client:
        response = client.post(
            "/api/runtime/gpu-worker-control/start",
            json={},
            headers={
                "Origin": "http://localhost",
                "X-Content-Control-Token": control._CONTROL_TOKEN,
            },
        )
    assert response.status_code == 409
    assert actions == ["status"]
    assert response.get_json()["error"] == "The Windows GPU is busy."


def test_no_remote_stop_route_exists() -> None:
    with _app().test_client() as client:
        assert client.post("/api/runtime/gpu-worker-control/stop", json={}).status_code == 404
