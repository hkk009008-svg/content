"""Guarded local FLUX.2 Klein dispatch and atomic output publication."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from comfyui_client import ComfyUIError, ComfyUIClient
from config.settings import settings
from paid_provider import (
    file_fingerprint,
    has_paid_attempt_authority,
    paid_attempt_id,
    request_fingerprint,
    run_durable_comfy_job,
)
from performance.comfyui_endpoint import resolve_performance_comfyui
from performance.worker_readiness import (
    DEFAULT_DEPLOY_ROOT,
    DEFAULT_FLUX2_DEPLOY_ROOT,
    IMAGE_CAPABILITY,
    PerformanceWorkerUnavailable,
    expected_flux2_worker_contract,
    validate_flux2_gateway_readiness,
    validate_unified_gateway_capabilities,
)


MAX_REFERENCE_IMAGES = 4


@dataclass(frozen=True)
class Flux2KleinJobResult:
    prompt_id: str
    output: Mapping[str, Any]
    history: Mapping[str, Any]
    published_path: str


def _workflow_module(deploy_root: Path) -> ModuleType:
    contract = expected_flux2_worker_contract(deploy_root)
    path = deploy_root.resolve() / "workflow.py"
    name = f"content_flux2_klein_{contract.workflow_sha256}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PerformanceWorkerUnavailable(
            "The tracked FLUX.2 workflow builder cannot be loaded."
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "build_flux2_klein_workflow", None)):
        raise PerformanceWorkerUnavailable(
            "The tracked FLUX.2 workflow builder is unavailable."
        )
    if getattr(module, "MAX_REFERENCE_IMAGES", None) != MAX_REFERENCE_IMAGES:
        raise PerformanceWorkerUnavailable(
            "The tracked FLUX.2 reference-image limit has drifted."
        )
    return module


def build_flux2_klein_workflow(
    *,
    prompt: str,
    reference_images: Sequence[str],
    seed: int,
    aspect_ratio: str,
    filename_prefix: str = "flux2-klein",
    deploy_root: Path = DEFAULT_FLUX2_DEPLOY_ROOT,
) -> dict[str, dict[str, Any]]:
    """Build through the hash-bound candidate rather than a copied graph."""

    builder = _workflow_module(deploy_root).build_flux2_klein_workflow
    graph = builder(
        prompt=prompt,
        reference_images=reference_images,
        seed=seed,
        aspect_ratio=aspect_ratio,
        filename_prefix=filename_prefix,
    )
    if not isinstance(graph, dict):
        raise PerformanceWorkerUnavailable(
            "The tracked FLUX.2 workflow builder returned an invalid graph."
        )
    return graph


def flux2_required_node_classes(
    deploy_root: Path = DEFAULT_FLUX2_DEPLOY_ROOT,
) -> frozenset[str]:
    module = _workflow_module(deploy_root)
    classes = getattr(module, "REQUIRED_NODE_CLASSES", None)
    if not isinstance(classes, frozenset) or not all(
        isinstance(value, str) and value for value in classes
    ):
        raise PerformanceWorkerUnavailable(
            "The tracked FLUX.2 node contract is invalid."
        )
    return classes


def flux2_aspect_dimensions(
    aspect_ratio: str,
    deploy_root: Path = DEFAULT_FLUX2_DEPLOY_ROOT,
) -> tuple[int, int]:
    dimensions = getattr(_workflow_module(deploy_root), "ASPECT_DIMENSIONS", None)
    value = dimensions.get(aspect_ratio) if isinstance(dimensions, Mapping) else None
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or not all(isinstance(item, int) and item > 0 for item in value)
    ):
        raise ValueError("aspect_ratio is not supported by the FLUX.2 contract")
    return value


def _local_references(paths: Sequence[str]) -> tuple[list[str], list[str]]:
    if isinstance(paths, (str, bytes)) or not isinstance(paths, Sequence):
        raise ValueError("reference_image_paths must be a sequence")
    values = [str(value) for value in paths]
    if not 1 <= len(values) <= MAX_REFERENCE_IMAGES:
        raise ValueError(
            f"reference_image_paths must contain 1..{MAX_REFERENCE_IMAGES} items"
        )
    resolved: list[str] = []
    fingerprints: list[str] = []
    for value in values:
        path = Path(value)
        if not path.is_file() or path.is_symlink():
            raise ValueError("FLUX.2 references must be regular non-symlink files")
        canonical = str(path.resolve())
        if canonical in resolved:
            raise ValueError("FLUX.2 reference paths must be unique")
        resolved.append(canonical)
        fingerprints.append(file_fingerprint(canonical))
    return resolved, fingerprints


def _first_image_output(history: Mapping[str, Any], prompt_id: str) -> Mapping[str, Any]:
    record = history.get(prompt_id)
    outputs = record.get("outputs") if isinstance(record, Mapping) else None
    if not isinstance(outputs, Mapping):
        raise PerformanceWorkerUnavailable(
            "The durable FLUX.2 job completed without an image output."
        )
    for node_output in outputs.values():
        images = node_output.get("images") if isinstance(node_output, Mapping) else None
        if isinstance(images, list) and images and isinstance(images[0], Mapping):
            return dict(images[0])
    raise PerformanceWorkerUnavailable(
        "The durable FLUX.2 job completed without an image output."
    )


def run_flux2_klein_image_job(
    *,
    prompt: str,
    reference_image_paths: Sequence[str],
    output_path: str,
    seed: int,
    aspect_ratio: str,
    cost_tracker: Any,
    shot_id: str = "",
    video_id: str = "",
    request_id: str = "",
    filename_prefix: str = "flux2-klein",
    poll_timeout_s: float = 600.0,
    settings_obj: object = settings,
    client_factory=ComfyUIClient,
    performance_deploy_root: Path = DEFAULT_DEPLOY_ROOT,
    flux2_deploy_root: Path = DEFAULT_FLUX2_DEPLOY_ROOT,
) -> Flux2KleinJobResult:
    """Upload and execute only after an exact authenticated Ready proof.

    This is deliberately durable-only even though local API spend is zero: a
    restart must resume the accepted Comfy prompt ID instead of duplicating GPU
    work.
    """

    if not has_paid_attempt_authority(cost_tracker):
        raise TypeError("FLUX.2 local dispatch requires durable job authority")
    references, fingerprints = _local_references(reference_image_paths)
    destination = Path(output_path)
    if destination.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise ValueError("FLUX.2 output_path must be a JPEG or PNG path")
    if destination.is_symlink():
        raise ValueError("FLUX.2 output_path cannot be a symlink")
    expected_dimensions = flux2_aspect_dimensions(
        aspect_ratio, deploy_root=flux2_deploy_root
    )
    # Validate every graph argument before constructing a network client.
    build_flux2_klein_workflow(
        prompt=prompt,
        reference_images=[f"reference-{index}.png" for index in range(len(references))],
        seed=seed,
        aspect_ratio=aspect_ratio,
        filename_prefix=filename_prefix,
        deploy_root=flux2_deploy_root,
    )

    endpoint = resolve_performance_comfyui(settings_obj)
    if not endpoint.shared_endpoint or not endpoint.usable:
        raise PerformanceWorkerUnavailable(
            "FLUX.2 requires the authenticated shared GPU-worker contract."
        )
    client = client_factory(
        endpoint.server_url,
        auth_token=endpoint.api_key,
        connect_timeout=2.0,
        read_timeout=2.0,
    )
    try:
        unified = client.get_gateway_capabilities_readiness()
    except ComfyUIError as exc:
        raise PerformanceWorkerUnavailable(
            "The FLUX.2 worker readiness proof is unavailable."
        ) from exc
    validated = validate_unified_gateway_capabilities(
        unified,
        deploy_root=performance_deploy_root,
        flux2_deploy_root=flux2_deploy_root,
    )
    capabilities = validated["capabilities"]
    assert isinstance(capabilities, Mapping)
    validate_flux2_gateway_readiness(
        capabilities[IMAGE_CAPABILITY],
        deploy_root=flux2_deploy_root,
        require_ready=True,
    )

    # The first source-media side effect occurs only after the proof above.
    remote_names = [client.upload_image(path) for path in references]
    workflow = build_flux2_klein_workflow(
        prompt=prompt,
        reference_images=remote_names,
        seed=seed,
        aspect_ratio=aspect_ratio,
        filename_prefix=filename_prefix,
        deploy_root=flux2_deploy_root,
    )
    stable_request = request_fingerprint(
        "local-flux2-klein-v1",
        prompt,
        seed,
        aspect_ratio,
        filename_prefix,
        fingerprints,
        request_id,
    )
    history = run_durable_comfy_job(
        client=client,
        workflow=workflow,
        attempt_id=paid_attempt_id(
            "local-flux2-klein", video_id, shot_id, stable_request
        ),
        engine="FLUX2_KLEIN_LOCAL",
        provider="local_gpu",
        operation="keyframe_generation",
        estimated_cost_usd=0.0,
        request_fingerprint_value=stable_request,
        cost_tracker=cost_tracker,
        shot_id=shot_id,
        video_id=video_id,
        poll_timeout_s=float(poll_timeout_s),
        poll_interval_s=2.0,
    )
    if not isinstance(history, Mapping) or len(history) != 1:
        raise PerformanceWorkerUnavailable(
            "The durable FLUX.2 history record is invalid."
        )
    prompt_id = next(iter(history))
    if not isinstance(prompt_id, str) or not prompt_id:
        raise PerformanceWorkerUnavailable(
            "The durable FLUX.2 history has no prompt identity."
        )
    output = _first_image_output(history, prompt_id)
    published = client.download_image(
        output.get("filename"),
        output.get("subfolder", ""),
        output.get("type", "output"),
        str(destination),
        expected_dimensions=expected_dimensions,
    )
    return Flux2KleinJobResult(
        prompt_id=prompt_id,
        output=output,
        history=dict(history),
        published_path=published,
    )
