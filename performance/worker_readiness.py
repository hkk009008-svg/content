"""Role- and capability-bound readiness for the local GPU worker."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from comfyui_client import ComfyUIError, ComfyUIClient
from config.settings import settings
from performance.comfyui_endpoint import resolve_performance_comfyui
from performance.live_portrait_workflow import build_live_portrait_workflow


WORKER_ROLE = "performance-liveportrait"
FLUX2_CAPABILITY = "image-flux2-klein"
# Shared-gateway image capability key.
IMAGE_CAPABILITY = FLUX2_CAPABILITY
CAPABILITY_SCHEMA_VERSION = 1
FLUX2_OPERATOR_STATES = frozenset(
    {"not_installed", "needs_benchmark", "ready", "blocked", "offline"}
)
FLUX2_NOT_INSTALLED_BLOCKER = "candidate_artifacts_not_installed"
FLUX2_PROBE_BLOCKER = "candidate_execution_probe_not_run"
FLUX2_BENCHMARK_BLOCKER = "candidate_benchmark_not_run"
REQUIRED_UNIFIED_CAPABILITIES = frozenset({WORKER_ROLE, IMAGE_CAPABILITY})
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEPLOY_ROOT = _REPOSITORY_ROOT / "deploy" / "windows-liveportrait-worker"
DEFAULT_FLUX2_DEPLOY_ROOT = _REPOSITORY_ROOT / "deploy" / "windows-flux2-klein"
_HEX_DIGEST_LENGTH = 64


class PerformanceWorkerUnavailable(RuntimeError):
    """The explicit local route cannot safely accept source media or work."""


@dataclass(frozen=True)
class PerformanceWorkerContract:
    role: str
    workflow_sha256: str
    model_manifest_sha256: str
    revisions_manifest_sha256: str
    contract_digest: str

    def gateway_fields(self) -> dict[str, str]:
        return {
            "role": self.role,
            "workflow_sha256": self.workflow_sha256,
            "model_manifest_sha256": self.model_manifest_sha256,
            "revisions_manifest_sha256": self.revisions_manifest_sha256,
            "contract_digest": self.contract_digest,
        }


@dataclass(frozen=True)
class Flux2WorkerContract:
    capability: str
    candidate_manifest_sha256: str
    workflow_sha256: str
    model_manifest_sha256: str
    revisions_manifest_sha256: str
    contract_digest: str

    def gateway_fields(self) -> dict[str, str]:
        return {
            "capability": self.capability,
            "candidate_manifest_sha256": self.candidate_manifest_sha256,
            "workflow_sha256": self.workflow_sha256,
            "model_manifest_sha256": self.model_manifest_sha256,
            "revisions_manifest_sha256": self.revisions_manifest_sha256,
            "contract_digest": self.contract_digest,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _HEX_DIGEST_LENGTH
        and all(char in "0123456789abcdef" for char in value)
    )


def _safe_workflow_path(deploy_root: Path) -> Path:
    probe_root = (deploy_root / "probes").resolve()
    contract_path = probe_root / "probe.json"
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PerformanceWorkerUnavailable(
            "The tracked performance-worker probe contract is unavailable."
        ) from exc
    workflow_value = payload.get("workflow") if isinstance(payload, Mapping) else None
    if not isinstance(workflow_value, str) or not workflow_value:
        raise PerformanceWorkerUnavailable(
            "The tracked performance-worker workflow binding is invalid."
        )
    workflow = (probe_root / workflow_value).resolve()
    if probe_root not in workflow.parents or not workflow.is_file():
        raise PerformanceWorkerUnavailable(
            "The tracked performance-worker workflow binding is invalid."
        )
    try:
        graph = json.loads(workflow.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PerformanceWorkerUnavailable(
            "The tracked performance-worker workflow is invalid."
        ) from exc
    expected_graph = build_live_portrait_workflow(
        "source-face.jpg", "driving-expression.mp4", 1 / 25
    )
    if graph != expected_graph:
        raise PerformanceWorkerUnavailable(
            "The worker probe graph has drifted from the shipping LivePortrait builder."
        )
    return workflow


@lru_cache(maxsize=4)
def expected_performance_worker_contract(
    deploy_root: Path = DEFAULT_DEPLOY_ROOT,
) -> PerformanceWorkerContract:
    root = deploy_root.resolve()
    try:
        workflow_hash = _sha256(_safe_workflow_path(root))
        model_hash = _sha256(root / "models.json")
        revisions_hash = _sha256(root / "revisions.json")
    except OSError as exc:
        raise PerformanceWorkerUnavailable(
            "The tracked performance-worker manifests are unavailable."
        ) from exc
    contract_payload = {
        "model_manifest_sha256": model_hash,
        "revisions_manifest_sha256": revisions_hash,
        "role": WORKER_ROLE,
        "workflow_sha256": workflow_hash,
    }
    contract_digest = hashlib.sha256(
        json.dumps(contract_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return PerformanceWorkerContract(
        role=WORKER_ROLE,
        workflow_sha256=workflow_hash,
        model_manifest_sha256=model_hash,
        revisions_manifest_sha256=revisions_hash,
        contract_digest=contract_digest,
    )


def expected_flux2_worker_contract(
    deploy_root: Path = DEFAULT_FLUX2_DEPLOY_ROOT,
) -> Flux2WorkerContract:
    """Hash the complete tracked candidate before trusting its core fields.

    ``candidate.json`` binds every shipping candidate file.  Validating every
    binding here means a gateway cannot become compatible merely by echoing a
    status string or one model filename.
    """

    root = deploy_root.resolve()
    candidate_path = root / "candidate.json"
    try:
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PerformanceWorkerUnavailable(
            "The tracked FLUX.2 candidate contract is unavailable."
        ) from exc
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("schema_version") != 1
        or candidate.get("capability") != FLUX2_CAPABILITY
    ):
        raise PerformanceWorkerUnavailable(
            "The tracked FLUX.2 candidate schema is invalid."
        )
    bindings = candidate.get("bindings")
    if not isinstance(bindings, Mapping) or not bindings:
        raise PerformanceWorkerUnavailable(
            "The tracked FLUX.2 candidate has no package bindings."
        )
    hashes: dict[str, str] = {}
    for raw_name, expected_hash in bindings.items():
        if (
            not isinstance(raw_name, str)
            or not isinstance(expected_hash, str)
            or not _is_sha256(expected_hash)
        ):
            raise PerformanceWorkerUnavailable(
                "The tracked FLUX.2 candidate package binding is invalid."
            )
        path = (root / raw_name).resolve()
        if root not in path.parents or not path.is_file():
            raise PerformanceWorkerUnavailable(
                "The tracked FLUX.2 candidate package binding is unavailable."
            )
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise PerformanceWorkerUnavailable(
                "The tracked FLUX.2 candidate package binding has drifted."
            )
        hashes[raw_name] = actual_hash
    required = {"workflow.py", "models.json", "revisions.json"}
    if not required.issubset(hashes):
        raise PerformanceWorkerUnavailable(
            "The tracked FLUX.2 candidate core bindings are incomplete."
        )
    fields = {
        "candidate_manifest_sha256": _sha256(candidate_path),
        "capability": FLUX2_CAPABILITY,
        "model_manifest_sha256": hashes["models.json"],
        "revisions_manifest_sha256": hashes["revisions.json"],
        "workflow_sha256": hashes["workflow.py"],
    }
    digest = hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return Flux2WorkerContract(contract_digest=digest, **fields)


def validate_performance_gateway_readiness(
    payload: object,
    *,
    deploy_root: Path = DEFAULT_DEPLOY_ROOT,
) -> Mapping[str, Any]:
    """Reject generic, stale, wrong-role, or execution-unproven readiness."""

    if not isinstance(payload, Mapping):
        raise PerformanceWorkerUnavailable(
            "The performance worker returned an invalid readiness record."
        )
    if (
        payload.get("status") != "ready"
        or payload.get("startup_ready") is not True
        or payload.get("execution_proven") is not True
        or payload.get("execution_canary_state") != "passed"
    ):
        raise PerformanceWorkerUnavailable(
            "The performance worker has not passed its execution readiness proof."
        )
    expected = expected_performance_worker_contract(deploy_root)
    for field, expected_value in expected.gateway_fields().items():
        actual = payload.get(field)
        if (
            not isinstance(actual, str)
            or len(actual) != (_HEX_DIGEST_LENGTH if field != "role" else len(WORKER_ROLE))
            or actual != expected_value
        ):
            raise PerformanceWorkerUnavailable(
                "The performance worker does not match the tracked role and artifact contract."
            )
    return payload


def validate_flux2_gateway_readiness(
    payload: object,
    *,
    deploy_root: Path = DEFAULT_FLUX2_DEPLOY_ROOT,
    require_ready: bool = False,
) -> Mapping[str, Any]:
    """Validate one exact FLUX.2 capability record and its state evidence."""

    if not isinstance(payload, Mapping):
        raise PerformanceWorkerUnavailable(
            "The FLUX.2 worker returned an invalid capability record."
        )
    expected = expected_flux2_worker_contract(deploy_root)
    for field, expected_value in expected.gateway_fields().items():
        actual = payload.get(field)
        if not isinstance(actual, str) or actual != expected_value:
            raise PerformanceWorkerUnavailable(
                "The FLUX.2 worker does not match the tracked candidate package contract."
            )

    state = payload.get("state")
    if state not in FLUX2_OPERATOR_STATES or state == "offline":
        # Offline is an application projection for a failed bounded transport;
        # a reachable gateway cannot self-assert it.
        raise PerformanceWorkerUnavailable(
            "The FLUX.2 worker returned an invalid operator state."
        )
    startup_ready = payload.get("startup_ready")
    execution_proven = payload.get("execution_proven")
    benchmark_state = payload.get("benchmark_state")
    blocker_code = payload.get("blocker_code")
    license_state = payload.get("license_review_state")
    canary_state = payload.get("execution_canary_state")
    canary_hash = payload.get("execution_canary_sha256")
    benchmark_hash = payload.get("benchmark_sha256")
    artifacts_installed = payload.get("artifacts_installed")
    runtime_hash = payload.get("runtime_contract_sha256")
    if not all(
        isinstance(value, str)
        for value in (
            benchmark_state,
            blocker_code,
            license_state,
            canary_state,
            canary_hash,
            benchmark_hash,
            runtime_hash,
        )
    ) or not isinstance(artifacts_installed, bool):
        raise PerformanceWorkerUnavailable(
            "The FLUX.2 worker readiness evidence is incomplete."
        )

    if state == "not_installed":
        source_only = (
            startup_ready is False
            and execution_proven is False
            and benchmark_state == "not_run"
            and blocker_code == FLUX2_NOT_INSTALLED_BLOCKER
            and license_state == "official_sources_selected_derivation_pending"
            and artifacts_installed is False
            and runtime_hash == ""
            and canary_state == "not_run"
            and canary_hash == ""
            and benchmark_hash == ""
        )
        installed_needs_probe = (
            startup_ready is False
            and execution_proven is False
            and benchmark_state == "not_run"
            and blocker_code == FLUX2_PROBE_BLOCKER
            and license_state == "official_source_derivation_verified"
            and artifacts_installed is True
            and runtime_hash == ""
            and canary_state == "not_run"
            and canary_hash == ""
            and benchmark_hash == ""
        )
        valid_state = source_only or installed_needs_probe
    elif state == "needs_benchmark":
        valid_state = (
            startup_ready is False
            and execution_proven is True
            and benchmark_state == "not_run"
            and blocker_code == FLUX2_BENCHMARK_BLOCKER
            and license_state == "official_source_derivation_verified"
            and artifacts_installed is True
            and _is_sha256(runtime_hash)
            and canary_state == "passed"
            and _is_sha256(canary_hash)
            and benchmark_hash == ""
        )
    elif state == "ready":
        valid_state = (
            startup_ready is True
            and execution_proven is True
            and benchmark_state == "passed"
            and blocker_code == ""
            and license_state == "official_source_derivation_verified"
            and artifacts_installed is True
            and _is_sha256(runtime_hash)
            and canary_state == "passed"
            and _is_sha256(canary_hash)
            and _is_sha256(benchmark_hash)
        )
    else:  # blocked
        valid_state = (
            startup_ready is False
            and execution_proven is False
            and benchmark_state in {"not_run", "failed", "unknown"}
            and bool(blocker_code)
            and (runtime_hash == "" or _is_sha256(runtime_hash))
            and canary_state in {"not_run", "failed", "unknown"}
            and (canary_hash == "" or _is_sha256(canary_hash))
            and (benchmark_hash == "" or _is_sha256(benchmark_hash))
        )
    if not valid_state:
        raise PerformanceWorkerUnavailable(
            "The FLUX.2 worker state does not match its required readiness evidence."
        )
    if require_ready and state != "ready":
        raise PerformanceWorkerUnavailable(
            f"The FLUX.2 worker is {state} and cannot accept media."
        )
    return payload


def validate_unified_gateway_capabilities(
    payload: object,
    *,
    deploy_root: Path = DEFAULT_DEPLOY_ROOT,
    flux2_deploy_root: Path = DEFAULT_FLUX2_DEPLOY_ROOT,
) -> Mapping[str, Any]:
    """Validate the exact LivePortrait + FLUX.2 shared-worker contract."""

    if not isinstance(payload, Mapping):
        raise PerformanceWorkerUnavailable(
            "The shared GPU worker returned an invalid capability record."
        )
    if payload.get("schema_version") != CAPABILITY_SCHEMA_VERSION:
        raise PerformanceWorkerUnavailable(
            "The shared GPU worker capability schema or aggregate state is invalid."
        )
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, Mapping):
        raise PerformanceWorkerUnavailable(
            "The shared GPU worker returned no capability map."
        )
    actual_capabilities = frozenset(capabilities)
    if actual_capabilities != REQUIRED_UNIFIED_CAPABILITIES:
        raise PerformanceWorkerUnavailable(
            "The shared GPU worker capability set does not match the required contract."
        )

    performance = capabilities.get(WORKER_ROLE)
    validate_performance_gateway_readiness(performance, deploy_root=deploy_root)

    image = capabilities.get(IMAGE_CAPABILITY)
    validated_image = validate_flux2_gateway_readiness(
        image, deploy_root=flux2_deploy_root
    )
    expected_aggregate = "ready" if validated_image.get("state") == "ready" else "partial"
    if payload.get("status") != expected_aggregate:
        raise PerformanceWorkerUnavailable(
            "The shared GPU worker capability aggregate state is invalid."
        )
    return payload


def performance_capability_from_unified(
    payload: object,
    *,
    deploy_root: Path = DEFAULT_DEPLOY_ROOT,
    flux2_deploy_root: Path = DEFAULT_FLUX2_DEPLOY_ROOT,
) -> Mapping[str, Any]:
    """Return the validated LivePortrait member of one unified contract."""

    validated = validate_unified_gateway_capabilities(
        payload,
        deploy_root=deploy_root,
        flux2_deploy_root=flux2_deploy_root,
    )
    capabilities = validated["capabilities"]
    assert isinstance(capabilities, Mapping)  # established by validation above
    performance = capabilities[WORKER_ROLE]
    assert isinstance(performance, Mapping)
    return performance


def require_flux2_worker_ready(
    settings_obj: object = settings,
    *,
    client_factory=ComfyUIClient,
    deploy_root: Path = DEFAULT_DEPLOY_ROOT,
    flux2_deploy_root: Path = DEFAULT_FLUX2_DEPLOY_ROOT,
) -> Mapping[str, Any]:
    """Run one authenticated zero-media proof before any FLUX.2 upload."""

    endpoint = resolve_performance_comfyui(settings_obj)
    if not endpoint.shared_endpoint:
        raise PerformanceWorkerUnavailable(
            "The image worker does not use the shared capability contract."
        )
    if not endpoint.usable:
        raise PerformanceWorkerUnavailable(
            "The shared GPU worker configuration is not safe to use."
        )
    try:
        client = client_factory(
            endpoint.server_url,
            auth_token=endpoint.api_key,
            connect_timeout=2.0,
            read_timeout=2.0,
        )
        payload = client.get_gateway_capabilities_readiness()
    except ComfyUIError as exc:
        raise PerformanceWorkerUnavailable(
            "The shared image worker has not passed its guarded capability proof."
        ) from exc
    except Exception as exc:
        raise PerformanceWorkerUnavailable(
            "The shared image worker readiness check failed safely."
        ) from exc

    validated = validate_unified_gateway_capabilities(
        payload,
        deploy_root=deploy_root,
        flux2_deploy_root=flux2_deploy_root,
    )
    capabilities = validated["capabilities"]
    assert isinstance(capabilities, Mapping)
    image = capabilities[IMAGE_CAPABILITY]
    assert isinstance(image, Mapping)
    return validate_flux2_gateway_readiness(
        image,
        deploy_root=flux2_deploy_root,
        require_ready=True,
    )


def require_liveportrait_worker_ready(
    settings_obj: object = settings,
    *,
    client_factory=ComfyUIClient,
    deploy_root: Path = DEFAULT_DEPLOY_ROOT,
    flux2_deploy_root: Path = DEFAULT_FLUX2_DEPLOY_ROOT,
) -> Mapping[str, Any]:
    """Perform a bounded, zero-media check before any explicit local dispatch."""

    endpoint = resolve_performance_comfyui(settings_obj)
    if not endpoint.configured:
        raise PerformanceWorkerUnavailable(
            "The dedicated performance worker is not configured."
        )
    if not endpoint.usable:
        raise PerformanceWorkerUnavailable(
            "The dedicated performance worker configuration is not safe to use."
        )
    try:
        client = client_factory(
            endpoint.server_url,
            auth_token=endpoint.api_key,
            connect_timeout=2.0,
            read_timeout=2.0,
        )
        if endpoint.requires_capability_proof:
            payload = client.get_gateway_capabilities_readiness()
        else:
            payload = client.get_gateway_readiness()
    except ComfyUIError as exc:
        raise PerformanceWorkerUnavailable(
            "The dedicated performance worker is reachable only after its guarded startup proof passes."
        ) from exc
    except Exception as exc:
        raise PerformanceWorkerUnavailable(
            "The dedicated performance worker readiness check failed safely."
        ) from exc
    if endpoint.requires_capability_proof:
        return performance_capability_from_unified(
            payload,
            deploy_root=deploy_root,
            flux2_deploy_root=flux2_deploy_root,
        )
    return validate_performance_gateway_readiness(payload, deploy_root=deploy_root)
