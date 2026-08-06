"""Local FLUX.2 Klein character-LoRA training and inference seam."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence

from comfyui_client import ComfyUIError, ComfyUIClient
from config.settings import settings
from identity.lora_training import (
    LoraTrainingClient,
    LoraTrainingEvidence,
    build_lora_training_plan,
    current_lora_candidate_sha256,
    fixed_character_token,
)
from identity.protocols import LORA_BENCHMARK_PROMPT
from paid_provider import (
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
    validate_flux2_gateway_readiness,
    validate_unified_gateway_capabilities,
)


LORA_DEPLOY_ROOT = (
    Path(__file__).resolve().parent.parent / "deploy" / "windows-flux2-lora"
)
_MODULE_LOCK = threading.Lock()


@dataclass(frozen=True)
class Flux2LoraJobResult:
    prompt_id: str
    output: Mapping[str, Any]
    history: Mapping[str, Any]
    published_path: str


def _load_module(name: str, path: Path) -> ModuleType:
    try:
        source = path.read_bytes()
        code = compile(source, str(path), "exec")
    except (OSError, SyntaxError) as exc:
        raise PerformanceWorkerUnavailable("The tracked LoRA candidate cannot be loaded.")
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    exec(code, module.__dict__)
    return module


def _lora_modules(
    deploy_root: Path = LORA_DEPLOY_ROOT,
) -> tuple[ModuleType, ModuleType]:
    """Load the hyphenated Windows package without copying its graph contract."""

    try:
        root = deploy_root.resolve(strict=True)
    except OSError as exc:
        raise PerformanceWorkerUnavailable(
            "The tracked LoRA candidate package is unavailable."
        ) from exc
    with _MODULE_LOCK:
        contract = _load_module("content_flux2_lora_contract", root / "contract.py")
        try:
            contract.validate_package(root)
            candidate_sha256 = contract.package_digest(root)
        except Exception as exc:
            raise PerformanceWorkerUnavailable(
                "The tracked LoRA candidate package failed its binding contract."
            ) from exc
        prior = sys.modules.get("contract")
        sys.modules["contract"] = contract
        try:
            inference = _load_module(
                f"content_flux2_lora_inference_{candidate_sha256}",
                root / "inference.py",
            )
        finally:
            if prior is None:
                sys.modules.pop("contract", None)
            else:
                sys.modules["contract"] = prior
    inference_functions = (
        "build_control_workflow",
        "build_inference_workflow",
        "validate_control_workflow",
        "validate_inference_workflow",
    )
    if not callable(getattr(contract, "validate_adapter_metadata", None)) or not all(
        callable(getattr(inference, name, None)) for name in inference_functions
    ):
        raise PerformanceWorkerUnavailable(
            "The tracked LoRA inference contract is incomplete."
        )
    return contract, inference


def _shared_endpoint(settings_obj: object) -> Any:
    endpoint = resolve_performance_comfyui(settings_obj)
    if not endpoint.shared_endpoint or not endpoint.usable:
        raise PerformanceWorkerUnavailable(
            "Character LoRA requires the authenticated shared GPU-worker contract."
        )
    return endpoint


def train_character_lora(
    *,
    reference_paths: Sequence[str | Path],
    project_id: str,
    character_id: str,
    allow_interrupted_resume: bool = False,
    settings_obj: object = settings,
    client_factory: Callable[..., LoraTrainingClient] = LoraTrainingClient,
) -> LoraTrainingEvidence:
    """Reconcile one deterministic four-reference training job."""

    fixed_character_token(project_id, character_id)
    if type(allow_interrupted_resume) is not bool:
        raise ValueError("allow_interrupted_resume must be a boolean")
    endpoint = _shared_endpoint(settings_obj)
    client = client_factory(endpoint.server_url, endpoint.api_key)
    candidate_sha256 = current_lora_candidate_sha256()
    readiness = client.get_readiness(candidate_sha256)
    plan = build_lora_training_plan(reference_paths, consent=True)
    if not readiness.job_submission_ready and client.get_job(plan.job_id) is None:
        raise PerformanceWorkerUnavailable(
            f"Character LoRA is blocked: {readiness.blocker_code}"
        )
    return client.ensure_training(
        plan,
        allow_interrupted_resume=allow_interrupted_resume,
    )


def _first_lora_output(
    history: Mapping[str, Any], prompt_id: str
) -> Mapping[str, Any]:
    record = history.get(prompt_id)
    outputs = record.get("outputs") if isinstance(record, Mapping) else None
    save_output = outputs.get("14") if isinstance(outputs, Mapping) else None
    images = save_output.get("images") if isinstance(save_output, Mapping) else None
    if (
        not isinstance(images, list)
        or len(images) != 1
        or not isinstance(images[0], Mapping)
    ):
        raise PerformanceWorkerUnavailable(
            "The durable LoRA job completed without exactly one image output."
        )
    return dict(images[0])


def _prove_worker_ready(
    client: Any,
    *,
    performance_deploy_root: Path,
    flux2_deploy_root: Path,
) -> None:
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
    if not isinstance(capabilities, Mapping):
        raise PerformanceWorkerUnavailable(
            "The FLUX.2 worker capability proof is invalid."
        )
    validate_flux2_gateway_readiness(
        capabilities[IMAGE_CAPABILITY],
        deploy_root=flux2_deploy_root,
        require_ready=True,
    )


def run_flux2_lora_image_job(
    *,
    prompt: str,
    mode: str,
    evidence: LoraTrainingEvidence,
    output_path: str,
    cost_tracker: Any,
    shot_id: str = "",
    video_id: str = "",
    request_id: str = "",
    poll_timeout_s: float = 600.0,
    settings_obj: object = settings,
    client_factory: Callable[..., Any] = ComfyUIClient,
    lora_client_factory: Callable[..., LoraTrainingClient] = LoraTrainingClient,
    durable_runner: Callable[..., Mapping[str, Any]] = run_durable_comfy_job,
    module_loader: Callable[[Path], tuple[ModuleType, ModuleType]] = _lora_modules,
    performance_deploy_root: Path = DEFAULT_DEPLOY_ROOT,
    flux2_deploy_root: Path = DEFAULT_FLUX2_DEPLOY_ROOT,
    lora_deploy_root: Path = LORA_DEPLOY_ROOT,
) -> Flux2LoraJobResult:
    """Run one hash-bound control or adapter arm under durable job authority."""

    if not has_paid_attempt_authority(cost_tracker):
        raise TypeError("FLUX.2 LoRA dispatch requires durable job authority")
    if mode not in {"control", "adapter"}:
        raise ValueError("mode must be control or adapter")
    if prompt != LORA_BENCHMARK_PROMPT:
        raise ValueError("LoRA comparison uses the fixed benchmark prompt")
    if (
        isinstance(poll_timeout_s, bool)
        or not isinstance(poll_timeout_s, (int, float))
        or not math.isfinite(float(poll_timeout_s))
        or poll_timeout_s <= 0
    ):
        raise ValueError("poll_timeout_s must be finite and positive")
    destination = Path(output_path)
    if destination.suffix.lower() != ".png" or destination.is_symlink():
        raise ValueError("LoRA output_path must be a non-symlink PNG path")

    contract, inference = module_loader(lora_deploy_root)
    try:
        candidate_sha256 = str(contract.package_digest(lora_deploy_root))
        metadata = contract.validate_adapter_metadata(evidence.adapter_metadata)
    except Exception as exc:
        raise PerformanceWorkerUnavailable(
            "The LoRA adapter evidence failed the tracked package contract."
        ) from exc
    metadata_sha256 = hashlib.sha256(
        (
            json.dumps(
                metadata,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    if (
        candidate_sha256 != current_lora_candidate_sha256()
        or evidence.job_id != metadata.get("job_id")
        or evidence.adapter_sha256 != metadata.get("adapter", {}).get("sha256")
        or evidence.adapter_size_bytes != metadata.get("adapter", {}).get("bytes")
        or evidence.comfy_name != metadata.get("adapter", {}).get("filename")
        or evidence.raw.get("candidate_sha256") != candidate_sha256
        or evidence.raw.get("adapter_metadata") != metadata
        or evidence.raw.get("adapter_metadata_sha256") != metadata_sha256
        or evidence.adapter_metadata_sha256 != metadata_sha256
        or metadata.get("training", {}).get("package_sha256") != candidate_sha256
    ):
        raise PerformanceWorkerUnavailable(
            "The LoRA adapter evidence is not bound to the current candidate."
        )

    builder = (
        inference.build_control_workflow
        if mode == "control"
        else inference.build_inference_workflow
    )
    validator = (
        inference.validate_control_workflow
        if mode == "control"
        else inference.validate_inference_workflow
    )
    workflow = builder(metadata=metadata, prompt=prompt)

    endpoint = _shared_endpoint(settings_obj)
    client = client_factory(
        endpoint.server_url,
        auth_token=endpoint.api_key,
        connect_timeout=2.0,
        read_timeout=2.0,
    )
    _prove_worker_ready(
        client,
        performance_deploy_root=performance_deploy_root,
        flux2_deploy_root=flux2_deploy_root,
    )
    lora_readiness = lora_client_factory(
        endpoint.server_url, endpoint.api_key
    ).get_readiness(candidate_sha256)
    if lora_readiness.state != "ready":
        raise PerformanceWorkerUnavailable(
            f"Character LoRA is blocked: {lora_readiness.blocker_code}"
        )
    try:
        object_info = client.get_object_info()
        validator(workflow, metadata, object_info)
    except Exception as exc:
        raise PerformanceWorkerUnavailable(
            "The installed worker does not match the LoRA inference graph."
        ) from exc

    stable_request = request_fingerprint(
        "local-flux2-klein-lora-v1",
        mode,
        prompt,
        evidence.job_id,
        evidence.adapter_sha256,
        evidence.adapter_metadata_sha256,
        candidate_sha256,
        workflow,
        request_id,
    )
    history = durable_runner(
        client=client,
        workflow=workflow,
        attempt_id=paid_attempt_id(
            "local-flux2-klein-lora", video_id, shot_id, stable_request
        ),
        engine="FLUX2_KLEIN_LORA_LOCAL",
        provider="local_gpu",
        operation="identity_inference",
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
            "The durable LoRA history record is invalid."
        )
    prompt_id = next(iter(history))
    if not isinstance(prompt_id, str) or not prompt_id:
        raise PerformanceWorkerUnavailable(
            "The durable LoRA history has no prompt identity."
        )
    output = _first_lora_output(history, prompt_id)
    published = client.download_image(
        output.get("filename"),
        output.get("subfolder", ""),
        output.get("type", "output"),
        str(destination),
        expected_dimensions=(1024, 1024),
    )
    return Flux2LoraJobResult(
        prompt_id=prompt_id,
        output=output,
        history=dict(history),
        published_path=published,
    )
