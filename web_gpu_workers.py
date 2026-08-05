"""Safe, read-only GPU worker readiness for the local operator UI.

Reachability, API compatibility, and guarded production readiness are separate
states.  Endpoint URLs and bearer tokens stay server-side; the browser receives
only an allowlisted status projection.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from flask import Blueprint, jsonify

from comfyui_client import (
    ComfyUIReadinessError,
    ComfyUITransportError,
    ComfyUIClient,
)
from config.settings import settings
from domain.flux2_candidate import flux2_candidate_status
from performance.comfyui_endpoint import resolve_performance_comfyui
from performance.flux2_klein import flux2_required_node_classes
from performance.live_portrait_workflow import LIVE_PORTRAIT_REQUIRED_NODE_CLASSES
from performance.worker_readiness import (
    IMAGE_CAPABILITY,
    PerformanceWorkerUnavailable,
    WORKER_ROLE,
    validate_unified_gateway_capabilities,
    validate_performance_gateway_readiness,
)


logger = logging.getLogger(__name__)
gpu_workers_api = Blueprint("gpu_workers_api", __name__)

_PERFORMANCE_NODE_CLASSES = LIVE_PORTRAIT_REQUIRED_NODE_CLASSES


@dataclass(frozen=True)
class _WorkerSpec:
    role: str
    label: str
    server_url: str
    api_key: str
    dedicated: bool
    shared_endpoint: bool
    required_node_classes: frozenset[str]
    configuration_error: str = ""


@dataclass(frozen=True)
class _GatewayProbe:
    state: str
    capability: Mapping[str, Any] | None = None


def _worker_specs(settings_obj: object = settings) -> tuple[_WorkerSpec, ...]:
    performance = resolve_performance_comfyui(settings_obj)
    shared_error = performance.configuration_error if performance.shared_endpoint else ""
    try:
        image_nodes = flux2_required_node_classes()
    except PerformanceWorkerUnavailable:
        image_nodes = frozenset()
    return (
        _WorkerSpec(
            role="image",
            label="Local image worker (FLUX.2 Klein 4B)",
            server_url=(getattr(settings_obj, "comfyui_server_url", "") or "").strip().rstrip("/"),
            api_key=(getattr(settings_obj, "comfyui_api_key", "") or "").strip(),
            dedicated=not performance.shared_endpoint,
            shared_endpoint=performance.shared_endpoint,
            required_node_classes=image_nodes,
            configuration_error=shared_error,
        ),
        _WorkerSpec(
            role="performance",
            label="Performance worker (LivePortrait)",
            server_url=performance.server_url,
            api_key=performance.api_key,
            dedicated=performance.dedicated,
            shared_endpoint=performance.shared_endpoint,
            required_node_classes=_PERFORMANCE_NODE_CLASSES,
            configuration_error=performance.configuration_error,
        ),
    )


def _base_status(spec: _WorkerSpec) -> dict[str, Any]:
    return {
        "role": spec.role,
        "label": spec.label,
        "configured": bool(spec.server_url),
        "dedicated": spec.dedicated,
        "state": "unconfigured",
        "message": "No worker endpoint is configured for this role.",
    }


def _is_loopback_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.hostname.lower() == "localhost":
            return True
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        return False


def _valid_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def _safe_text(value: object, *, maximum: int = 120) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(char for char in value if char.isprintable()).strip()[:maximum]


def _gib(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return round(float(value) / (1024**3), 2)


def _add_device_projection(status: dict[str, Any], stats: Mapping[str, Any]) -> None:
    devices = stats.get("devices")
    if not isinstance(devices, list):
        return
    device = next((item for item in devices if isinstance(item, Mapping)), None)
    if device is None:
        return
    name = _safe_text(device.get("name"))
    if name:
        status["gpu_name"] = name
    total = _gib(device.get("vram_total"))
    free = _gib(device.get("vram_free"))
    if total is not None:
        status["vram_total_gib"] = total
    if free is not None:
        status["vram_free_gib"] = free


def _gateway_readiness(client: ComfyUIClient, spec: _WorkerSpec) -> _GatewayProbe:
    try:
        if spec.shared_endpoint:
            payload = client.get_gateway_capabilities_readiness()
            try:
                validated = validate_unified_gateway_capabilities(payload)
            except PerformanceWorkerUnavailable:
                return _GatewayProbe("incompatible")
            capabilities = validated["capabilities"]
            assert isinstance(capabilities, Mapping)
            capability_name = WORKER_ROLE if spec.role == "performance" else IMAGE_CAPABILITY
            capability = capabilities[capability_name]
            assert isinstance(capability, Mapping)
            if spec.role == "performance":
                return _GatewayProbe("ready", capability)
            state = capability.get("state")
            return _GatewayProbe(str(state), capability)
        payload = client.get_gateway_readiness()
        if spec.role == "performance":
            try:
                validate_performance_gateway_readiness(payload)
            except PerformanceWorkerUnavailable:
                return _GatewayProbe("incompatible")
        return _GatewayProbe("ready")
    except ComfyUITransportError as exc:
        if exc.status_code == 404:
            return _GatewayProbe("absent")
        if exc.status_code == 503:
            return _GatewayProbe("not_ready")
        raise


def _probe_worker(spec: _WorkerSpec, settings_obj: object = settings) -> dict[str, Any]:
    status = _base_status(spec)
    if spec.role == "image":
        candidate = flux2_candidate_status(settings_obj)
        if candidate.state == "blocked":
            status.update(
                state="blocked",
                blocker_code=candidate.blocker_code,
                message=candidate.reason,
            )
            return status
        if not spec.server_url:
            status.update(
                state=candidate.state,
                blocker_code=candidate.blocker_code,
                benchmark_state=candidate.benchmark_state,
                startup_ready=candidate.startup_ready,
                execution_proven=candidate.execution_proven,
                message=candidate.reason,
            )
            return status
        if not spec.shared_endpoint:
            status.update(
                state="blocked",
                blocker_code="shared_capability_contract_required",
                message=(
                    "FLUX.2 requires the authenticated shared worker contract; "
                    "a generic or legacy image endpoint is not eligible."
                ),
            )
            return status
    if not spec.server_url:
        return status
    if spec.configuration_error:
        state = "blocked" if spec.role == "image" else "incompatible"
        if spec.configuration_error == "invalid_token":
            status.update(
                state="blocked" if spec.role == "image" else "unauthorized",
                blocker_code="worker_authentication_required" if spec.role == "image" else None,
                message="A random bearer API key of at least 32 characters is required.",
            )
        elif spec.configuration_error == "insecure_transport":
            status.update(
                state=state,
                blocker_code="insecure_worker_transport" if spec.role == "image" else None,
                message="Plain HTTP is allowed only through a loopback tunnel.",
            )
        elif spec.configuration_error == "shared_credentials":
            status.update(
                state="blocked" if spec.role == "image" else "unauthorized",
                blocker_code="shared_worker_credentials_mismatch" if spec.role == "image" else None,
                message="A shared worker must use one matching bearer credential for both roles.",
            )
        else:
            status.update(
                state=state,
                blocker_code="worker_configuration_invalid" if spec.role == "image" else None,
                message="The configured worker endpoint is not a valid dedicated gateway URL.",
            )
        if status.get("blocker_code") is None:
            status.pop("blocker_code", None)
        return status
    if not _valid_http_url(spec.server_url):
        status.update(
            state="blocked" if spec.role == "image" else "incompatible",
            blocker_code="worker_endpoint_invalid" if spec.role == "image" else None,
            message="The configured worker endpoint is not a valid HTTP(S) URL.",
        )
        if status.get("blocker_code") is None:
            status.pop("blocker_code", None)
        return status
    if not _is_loopback_url(spec.server_url) and not spec.api_key:
        status.update(
            state="blocked" if spec.role == "image" else "unauthorized",
            blocker_code="worker_authentication_required" if spec.role == "image" else None,
            message="A bearer API key is required for a non-loopback worker.",
        )
        if status.get("blocker_code") is None:
            status.pop("blocker_code", None)
        return status

    client = ComfyUIClient(
        spec.server_url,
        auth_token=spec.api_key,
        connect_timeout=2.0,
        read_timeout=2.0,
    )
    try:
        gateway = _gateway_readiness(client, spec)
        try:
            stats = client.get_system_stats()
        except ComfyUITransportError as exc:
            if gateway.state == "not_ready" and exc.status_code == 503:
                if spec.role == "image":
                    status.update(
                        state="blocked",
                        blocker_code="candidate_startup_not_ready",
                        message="The FLUX.2 gateway answered, but its guarded startup contract is not ready.",
                    )
                else:
                    status.update(
                        state="reachable",
                        message="The guarded worker answered, but its startup contract is not ready.",
                    )
                return status
            raise

        _add_device_projection(status, stats)
        queue = client.get_queue()
        status["running"] = len(queue["queue_running"])
        status["pending"] = len(queue["queue_pending"])

        if gateway.state == "incompatible":
            status.update(
                state="blocked" if spec.role == "image" else "incompatible",
                blocker_code="candidate_contract_mismatch" if spec.role == "image" else None,
                message=(
                    "The gateway does not match the tracked unified capability contract."
                    if spec.shared_endpoint
                    else "The gateway does not match the tracked performance-worker contract."
                ),
            )
            if status.get("blocker_code") is None:
                status.pop("blocker_code", None)
            return status

        if spec.role == "image" and gateway.state != "ready":
            capability = gateway.capability or {}
            status.update(
                state=gateway.state,
                startup_ready=capability.get("startup_ready", False),
                execution_proven=capability.get("execution_proven", False),
                benchmark_state=capability.get("benchmark_state", "unknown"),
                blocker_code=capability.get("blocker_code", "candidate_not_ready"),
            )
            for field in (
                "candidate_manifest_sha256",
                "workflow_sha256",
                "model_manifest_sha256",
                "revisions_manifest_sha256",
                "contract_digest",
            ):
                value = capability.get(field)
                if isinstance(value, str):
                    status[field] = value
            messages = {
                "not_installed": (
                    "The hash-bound FLUX.2 Klein candidate is not installed; "
                    "no image run is available."
                ),
                "needs_benchmark": (
                    "FLUX.2 execution passed, but the required local benchmark "
                    "has not passed."
                ),
                "blocked": (
                    "FLUX.2 is blocked by its policy, manifest, model, or "
                    "execution evidence contract."
                ),
            }
            status["message"] = messages.get(
                gateway.state, "FLUX.2 is not ready for local image work."
            )
            return status

        object_info = client.get_object_info()
        missing = sorted(spec.required_node_classes.difference(object_info))

        if not spec.required_node_classes:
            status.update(
                state="blocked" if spec.role == "image" else "incompatible",
                blocker_code="candidate_node_contract_unavailable" if spec.role == "image" else None,
                message="The application has no valid workflow contract for this worker role.",
            )
            if status.get("blocker_code") is None:
                status.pop("blocker_code", None)
        elif missing:
            status.update(
                state="blocked" if spec.role == "image" else "incompatible",
                blocker_code="candidate_node_contract_mismatch" if spec.role == "image" else None,
                message="The worker is reachable but its required node contract is incomplete.",
                missing_node_classes=missing,
            )
            if status.get("blocker_code") is None:
                status.pop("blocker_code", None)
        elif gateway.state == "ready":
            if spec.role == "performance":
                status.update(
                    state="ready",
                    message=(
                        "Technical readiness passed: the guarded startup, node, "
                        "model-file, and execution contracts match. Commercial-use "
                        "licensing remains a separate human review."
                    ),
                )
            else:
                capability = gateway.capability or {}
                status.update(
                    state="ready",
                    startup_ready=True,
                    execution_proven=True,
                    benchmark_state="passed",
                    blocker_code="",
                    message=(
                        "FLUX.2 Klein passed the exact package, execution, benchmark, "
                        "and live core-node contracts."
                    ),
                )
                for field in (
                    "candidate_manifest_sha256",
                    "workflow_sha256",
                    "model_manifest_sha256",
                    "revisions_manifest_sha256",
                    "contract_digest",
                ):
                    value = capability.get(field)
                    if isinstance(value, str):
                        status[field] = value
        elif gateway.state == "not_ready":
            status.update(
                state="reachable",
                message="The API contract matches, but the guarded startup contract is not ready.",
            )
        else:
            status.update(
                state="reachable",
                message="The API contract matches, but guarded startup readiness is unavailable.",
            )
        return status
    except ComfyUITransportError as exc:
        if spec.role == "image":
            if exc.status_code in {401, 403}:
                status.update(
                    state="blocked",
                    blocker_code="worker_authentication_failed",
                    message="The worker rejected the configured bearer credential.",
                )
            elif exc.status_code is None or exc.status_code == 429 or exc.status_code >= 500:
                status.update(
                    state="offline",
                    blocker_code="worker_offline",
                    message="The authenticated FLUX.2 worker is currently offline.",
                )
            else:
                status.update(
                    state="blocked",
                    blocker_code="candidate_contract_mismatch",
                    message="The endpoint does not implement the exact FLUX.2 worker contract.",
                )
            return status
        if exc.status_code in {401, 403}:
            status.update(
                state="unauthorized",
                message="The worker rejected the configured bearer credential.",
            )
        elif exc.status_code is not None and (
            exc.status_code == 429 or exc.status_code >= 500
        ):
            status.update(
                state="offline",
                message="The worker returned an unavailable response to its health probe.",
            )
        elif exc.status_code is not None:
            status.update(
                state="incompatible",
                message="The endpoint answered but does not implement the required ComfyUI API.",
            )
        else:
            status.update(
                state="offline",
                message="The worker did not answer before the bounded health timeout.",
            )
        return status
    except ComfyUIReadinessError:
        status.update(
            state="blocked" if spec.role == "image" else "incompatible",
            blocker_code="candidate_contract_mismatch" if spec.role == "image" else None,
            message="The worker answered with an invalid ComfyUI readiness contract.",
        )
        if status.get("blocker_code") is None:
            status.pop("blocker_code", None)
        return status
    except Exception:
        logger.exception("GPU worker status probe failed", extra={"role": spec.role})
        status.update(
            state="offline",
            message="The worker health probe failed safely.",
        )
        return status


@gpu_workers_api.get("/api/runtime/gpu-workers")
def api_gpu_workers():
    """Return only safe role readiness; never endpoint or credential data."""

    workers = [_probe_worker(spec, settings) for spec in _worker_specs(settings)]
    return jsonify({
        "workers": workers,
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })
