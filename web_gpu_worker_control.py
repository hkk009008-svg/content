"""Narrow, local-only launch control for the guarded Windows GPU worker.

The browser can request one fixed action. SSH authority, destination, task
name, and command remain server-owned, and the dedicated key is constrained by
a Windows forced-command entry even if this application layer is bypassed.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
import plistlib
import re
import selectors
import secrets
import stat
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from flask import Blueprint, Response, jsonify, request


gpu_worker_control_api = Blueprint("gpu_worker_control_api", __name__)

_LABEL = "com.content.liveportrait-tunnel"
_CONTROL_KEY_NAME = "content_gpu_control_ed25519"
_CONTROL_HEADER = "X-Content-Control-Token"
_CONTROL_TOKEN = secrets.token_urlsafe(32)
_ACTION_LOCK = threading.Lock()
_DESTINATION = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]{0,31})@([0-9.]+)$")
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_STATES = {"unavailable", "stopped", "starting", "running", "failed", "unknown"}


class WorkerControlError(RuntimeError):
    """The fixed worker-control contract could not be satisfied."""


@dataclass(frozen=True)
class _ControlTarget:
    destination: str
    known_hosts: Path
    identity_file: Path


def _locked_regular_file(path: Path, label: str) -> Path:
    try:
        details = path.lstat()
    except OSError as exc:
        raise WorkerControlError(f"{label} is missing") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise WorkerControlError(f"{label} must be a regular non-link file")
    if details.st_uid != os.geteuid() or stat.S_IMODE(details.st_mode) not in {0o400, 0o600}:
        raise WorkerControlError(f"{label} must be owned by this user and mode 0600 or stricter")
    return path.resolve(strict=True)


def _load_target(home: Path | None = None) -> _ControlTarget:
    user_home = (home or Path.home()).expanduser().resolve(strict=True)
    plist_path = _locked_regular_file(
        user_home / "Library/LaunchAgents" / f"{_LABEL}.plist",
        "worker tunnel LaunchAgent",
    )
    try:
        payload = plistlib.loads(plist_path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        raise WorkerControlError("worker tunnel LaunchAgent is invalid") from exc
    if payload.get("Label") != _LABEL:
        raise WorkerControlError("worker tunnel LaunchAgent label does not match")
    arguments = payload.get("ProgramArguments")
    if not isinstance(arguments, list) or not all(isinstance(value, str) for value in arguments):
        raise WorkerControlError("worker tunnel arguments are invalid")
    if not arguments or arguments[0] != "/usr/bin/ssh":
        raise WorkerControlError("worker tunnel must use the system SSH client")

    allowed_switches = {"-N", "-T"}
    required_switches: set[str] = set()
    required_options = {
        "BatchMode=yes",
        "IdentitiesOnly=yes",
        "ExitOnForwardFailure=yes",
        "ServerAliveInterval=15",
        "ServerAliveCountMax=3",
        "TCPKeepAlive=yes",
        "GatewayPorts=no",
        "StrictHostKeyChecking=yes",
    }
    seen_options: set[str] = set()
    known_hosts: Path | None = None
    config_file_seen = False
    forward_seen = False
    tunnel_identity_seen = False
    index = 1
    while index < len(arguments) - 1:
        argument = arguments[index]
        if argument in allowed_switches:
            if argument in required_switches:
                raise WorkerControlError("worker tunnel contains duplicate switches")
            required_switches.add(argument)
            index += 1
            continue
        if argument not in {"-F", "-o", "-i", "-L"} or index + 1 >= len(arguments) - 1:
            raise WorkerControlError("worker tunnel contains an unapproved SSH argument")
        value = arguments[index + 1]
        if argument == "-F":
            if config_file_seen or value != "/dev/null":
                raise WorkerControlError("worker tunnel may not inherit SSH configuration")
            config_file_seen = True
        elif argument == "-o":
            if value.startswith("UserKnownHostsFile="):
                if known_hosts is not None:
                    raise WorkerControlError("worker tunnel contains duplicate host-key files")
                raw = Path(value.split("=", 1)[1]).expanduser()
                if not raw.is_absolute():
                    raise WorkerControlError("worker host-key file must be absolute")
                known_hosts = _locked_regular_file(raw, "worker known_hosts")
            elif value in required_options:
                if value in seen_options:
                    raise WorkerControlError("worker tunnel contains duplicate SSH options")
                seen_options.add(value)
            else:
                raise WorkerControlError("worker tunnel contains an unapproved SSH option")
        elif argument == "-i":
            if tunnel_identity_seen:
                raise WorkerControlError("worker tunnel contains duplicate identities")
            raw_identity = Path(value).expanduser()
            if not raw_identity.is_absolute():
                raise WorkerControlError("worker tunnel identity must be absolute")
            _locked_regular_file(raw_identity, "worker tunnel identity")
            tunnel_identity_seen = True
        elif argument == "-L":
            if forward_seen or value != "127.0.0.1:18189:127.0.0.1:8189":
                raise WorkerControlError("worker tunnel forwarding contract does not match")
            forward_seen = True
        index += 2

    if required_switches != allowed_switches or seen_options != required_options:
        raise WorkerControlError("worker tunnel is missing required SSH protections")
    if not config_file_seen:
        raise WorkerControlError("worker tunnel may not inherit SSH configuration")
    if known_hosts is None or not forward_seen or not tunnel_identity_seen:
        raise WorkerControlError("worker tunnel is incomplete")

    destination = arguments[-1]
    matched = _DESTINATION.fullmatch(destination)
    if matched is None:
        raise WorkerControlError("worker destination is invalid")
    try:
        address = ipaddress.ip_address(matched.group(2))
    except ValueError as exc:
        raise WorkerControlError("worker destination is invalid") from exc
    if address.version != 4 or not any(address in network for network in _PRIVATE_NETWORKS):
        raise WorkerControlError("worker destination must be one private IPv4 address")

    identity = _locked_regular_file(
        user_home / ".ssh" / _CONTROL_KEY_NAME,
        "worker control identity",
    )
    return _ControlTarget(destination=destination, known_hosts=known_hosts, identity_file=identity)


def _ssh_arguments(action: str, target: _ControlTarget) -> list[str]:
    if action not in {"status", "start"}:
        raise WorkerControlError("worker control action is not allowlisted")
    return [
        "/usr/bin/ssh",
        "-F",
        "/dev/null",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "PermitLocalCommand=no",
        "-o",
        "RequestTTY=no",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={target.known_hosts}",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "ConnectionAttempts=1",
        "-i",
        str(target.identity_file),
        target.destination,
        action,
    ]


def _validated_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise WorkerControlError("worker control returned an invalid schema")
    state = value.get("state")
    if state not in _STATES:
        raise WorkerControlError("worker control returned an invalid state")
    if not isinstance(value.get("can_start"), bool) or not isinstance(value.get("gpu_busy"), bool):
        raise WorkerControlError("worker control returned invalid booleans")
    message = value.get("message")
    if not isinstance(message, str) or not message.strip() or len(message) > 180:
        raise WorkerControlError("worker control returned an invalid message")
    projected: dict[str, Any] = {
        "schema_version": 1,
        "state": state,
        "can_start": value["can_start"],
        "gpu_busy": value["gpu_busy"],
        "message": "".join(char for char in message if char.isprintable()).strip(),
    }
    for name in ("gpu_used_mib", "gpu_utilization_percent", "last_task_result"):
        candidate = value.get(name)
        if candidate is None:
            continue
        if isinstance(candidate, bool) or not isinstance(candidate, int):
            raise WorkerControlError(f"worker control returned invalid {name}")
        projected[name] = candidate
    return projected


def _run_capped_process(
    arguments: list[str],
    *,
    timeout: float = 10,
    output_limit: int = 4096,
) -> subprocess.CompletedProcess[bytes]:
    """Run one fixed command without buffering unbounded remote output."""

    try:
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    except OSError as exc:
        raise WorkerControlError("worker control did not answer") from exc
    if process.stdout is None:  # pragma: no cover - guaranteed by PIPE
        process.kill()
        process.wait()
        raise WorkerControlError("worker control did not answer")

    output = bytearray()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WorkerControlError("worker control did not answer")
            if not selector.select(remaining):
                raise WorkerControlError("worker control did not answer")
            chunk = os.read(process.stdout.fileno(), min(4096, output_limit + 1 - len(output)))
            if not chunk:
                try:
                    returncode = process.wait(timeout=max(0.01, deadline - time.monotonic()))
                except subprocess.TimeoutExpired as exc:
                    raise WorkerControlError("worker control did not answer") from exc
                return subprocess.CompletedProcess(arguments, returncode, bytes(output), None)
            output.extend(chunk)
            if len(output) > output_limit:
                raise WorkerControlError("worker control failed closed")
    finally:
        selector.close()
        process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait()


def _run_ssh(arguments: list[str]) -> subprocess.CompletedProcess[bytes]:
    return _run_capped_process(arguments)


def _remote_control(action: str) -> dict[str, Any]:
    target = _load_target()
    completed = _run_ssh(_ssh_arguments(action, target))
    if completed.returncode != 0:
        raise WorkerControlError("worker control failed closed")
    try:
        parsed = json.loads(completed.stdout.decode("utf-8").strip())
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise WorkerControlError("worker control returned invalid JSON") from exc
    return _validated_payload(parsed)


def _checked_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _response(payload: dict[str, Any], status: int = 200) -> Response:
    body = jsonify({**payload, "checked_at": _checked_at()})
    body.status_code = status
    body.headers["Cache-Control"] = "no-store"
    return body


def _unavailable(message: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state": "unavailable",
        "can_start": False,
        "gpu_busy": True,
        "message": message,
    }


def _loopback(value: str | None) -> bool:
    if not value:
        return False
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return value.lower() == "localhost"


def _request_is_local_ui() -> bool:
    if not _loopback(request.remote_addr):
        return False
    host = urlsplit(f"//{request.host}").hostname
    if not _loopback(host):
        return False
    origin = request.headers.get("Origin")
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not _loopback(parsed.hostname):
            return False
    fetch_site = request.headers.get("Sec-Fetch-Site")
    return fetch_site in {None, "none", "same-origin", "same-site"}


@gpu_worker_control_api.get("/api/runtime/gpu-worker-control")
def gpu_worker_control_status() -> Response:
    if not _request_is_local_ui():
        return _response({"error": "Worker launch status is local-only."}, 403)
    try:
        payload = _remote_control("status")
    except WorkerControlError:
        payload = _unavailable("Windows worker launch control is unavailable.")
    return _response({**payload, "control_token": _CONTROL_TOKEN})


@gpu_worker_control_api.post("/api/runtime/gpu-worker-control/start")
def gpu_worker_control_start() -> Response:
    if not _request_is_local_ui():
        return _response({"error": "Worker launch is allowed only from the local Content UI."}, 403)
    supplied = request.headers.get(_CONTROL_HEADER, "")
    if not hmac.compare_digest(supplied, _CONTROL_TOKEN):
        return _response({"error": "Worker launch control token is invalid."}, 403)
    body = request.get_json(silent=True) if request.is_json else None
    if body != {}:
        return _response({"error": "Worker launch accepts only an empty JSON object."}, 400)
    if not _ACTION_LOCK.acquire(blocking=False):
        return _response({"error": "A Windows worker launch request is already in progress."}, 409)
    try:
        try:
            current = _remote_control("status")
        except WorkerControlError:
            return _response({"error": "Windows worker launch control is unavailable."}, 503)
        if current["state"] in {"running", "starting"}:
            return _response(current)
        if current["state"] != "stopped" or not current["can_start"]:
            return _response({"error": current["message"], "control": current}, 409)
        try:
            started = _remote_control("start")
        except WorkerControlError:
            return _response({"error": "Windows worker launch failed closed."}, 503)
        if started["state"] not in {"running", "starting"}:
            return _response({"error": started["message"], "control": started}, 409)
        return _response(started, 202)
    finally:
        _ACTION_LOCK.release()
