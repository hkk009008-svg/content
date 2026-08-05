#!/usr/bin/env python3
"""Online ComfyUI contract checks and a zero-provider-cost execution canary."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid


class StartupGuardError(RuntimeError):
    """The backend is alive but does not satisfy the production graph contract."""


def request_json(
    base_url: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 30,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(base_url.rstrip("/") + path, data=data, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise StartupGuardError(f"{path} returned HTTP {response.status}")
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                raise StartupGuardError(f"{path} returned {content_type}, not application/json")
            try:
                return json.load(response)
            except json.JSONDecodeError as exc:
                raise StartupGuardError(f"{path} returned invalid JSON") from exc
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise StartupGuardError(f"{path} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise StartupGuardError(f"{path} unavailable: {exc.reason}") from exc


def wait_for_backend(base_url: str, *, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            payload = request_json(base_url, "/system_stats", timeout=5)
            if isinstance(payload, dict) and isinstance(payload.get("system"), dict):
                return payload
            last_error = "system_stats JSON lacks the system object"
        except StartupGuardError as exc:
            last_error = str(exc)
        time.sleep(2)
    raise StartupGuardError(f"backend did not become alive within {timeout}s: {last_error}")


def required_workflow_nodes(workflow_path: Path) -> set[str]:
    try:
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StartupGuardError(f"cannot load workflow {workflow_path}: {exc}") from exc
    if not isinstance(workflow, dict) or not workflow:
        raise StartupGuardError("production workflow must be a non-empty object")
    result = {
        node["class_type"]
        for node in workflow.values()
        if isinstance(node, dict) and isinstance(node.get("class_type"), str)
    }
    if not result:
        raise StartupGuardError("production workflow contains no class_type values")
    return result


def _choice_values(object_info: dict[str, Any], node: str, input_name: str) -> set[str]:
    try:
        definition = object_info[node]["input"]["required"][input_name]
    except (KeyError, TypeError) as exc:
        raise StartupGuardError(f"{node}.{input_name} schema missing from /object_info") from exc
    if not isinstance(definition, list) or not definition or not isinstance(definition[0], list):
        raise StartupGuardError(f"{node}.{input_name} does not expose a choice list")
    return {value for value in definition[0] if isinstance(value, str)}


def verify_object_info(base_url: str, workflow_path: Path) -> dict[str, Any]:
    payload = request_json(base_url, "/object_info", timeout=120)
    if not isinstance(payload, dict):
        raise StartupGuardError("/object_info must return an object")
    required = required_workflow_nodes(workflow_path)
    missing = sorted(required.difference(payload))
    if missing:
        raise StartupGuardError("required node classes missing: " + ", ".join(missing))

    expected_choices = {
        ("UNETLoader", "unet_name"): "FLUX1/flux1-dev-fp8.safetensors",
        ("DualCLIPLoader", "clip_name1"): "t5xxl_fp8_e4m3fn.safetensors",
        ("DualCLIPLoader", "clip_name2"): "clip_l.safetensors",
        ("VAELoader", "vae_name"): "ae.safetensors",
        ("PulidFluxModelLoader", "pulid_file"): "pulid_flux_v0.9.1.safetensors",
        ("UpscaleModelLoader", "model_name"): "RealESRGAN_x4plus.pth",
    }
    for (node, input_name), expected in expected_choices.items():
        choices = _choice_values(payload, node, input_name)
        if expected not in choices:
            raise StartupGuardError(f"{node}.{input_name} does not expose {expected}")
    return payload


def run_execution_canary(base_url: str, *, timeout: float = 90) -> str:
    client_id = str(uuid.uuid4())
    prefix = "content-health-canary-" + client_id[:12]
    prompt = {
        "1": {
            "class_type": "EmptyImage",
            "inputs": {"width": 64, "height": 64, "batch_size": 1, "color": 0x203040},
        },
        "2": {
            "class_type": "PreviewImage",
            "inputs": {"images": ["1", 0], "filename_prefix": prefix},
        },
    }
    submitted = request_json(
        base_url,
        "/prompt",
        payload={"prompt": prompt, "client_id": client_id},
        timeout=30,
    )
    if not isinstance(submitted, dict) or not isinstance(submitted.get("prompt_id"), str):
        raise StartupGuardError("execution canary was not assigned a prompt_id")
    prompt_id = submitted["prompt_id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        history = request_json(base_url, f"/history/{prompt_id}", timeout=15)
        if not isinstance(history, dict):
            raise StartupGuardError("execution canary history is not an object")
        record = history.get(prompt_id)
        if isinstance(record, dict):
            status = record.get("status")
            if isinstance(status, dict) and status.get("status_str") == "error":
                raise StartupGuardError("execution canary reached terminal error")
            outputs = record.get("outputs")
            if isinstance(outputs, dict) and outputs:
                images = outputs.get("2", {}).get("images", [])
                if not isinstance(images, list) or len(images) != 1:
                    raise StartupGuardError("execution canary did not publish exactly one image")
                return prompt_id
        time.sleep(1)
    raise StartupGuardError(f"execution canary {prompt_id} did not finish within {timeout}s")


def verify_backend(base_url: str, workflow_path: Path, *, startup_timeout: float) -> dict[str, Any]:
    stats = wait_for_backend(base_url, timeout=startup_timeout)
    verify_object_info(base_url, workflow_path)
    canary_id = run_execution_canary(base_url)
    return {
        "status": "ready",
        "backend": base_url,
        "canary_prompt_id": canary_id,
        "system": stats.get("system", {}),
        "checked_at_unix": int(time.time()),
    }
