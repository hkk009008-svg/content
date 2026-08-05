#!/usr/bin/env python3
"""Offline, fail-closed validation for the FLUX.2 Klein candidate package."""

from __future__ import annotations

import base64
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
HEX_LENGTH = 64
EXPECTED_BOUND_FILES = frozenset(
    {
        "Benchmark-Candidate.ps1",
        "Install-Candidate.ps1",
        "PROVENANCE.md",
        "Probe-Candidate.ps1",
        "README.md",
        "fixtures/object_info.json",
        "fixtures/reference.json",
        "fixtures/reference.png.b64",
        "install.py",
        "merge_qwen_encoder.py",
        "models.json",
        "preflight.py",
        "revisions.json",
        "runtime.py",
        "workflow.py",
    }
)
EXPECTED_FIXTURE = {
    "path": "reference.png",
    "encoding": "base64",
    "payload": "reference.png.b64",
    "expected_bytes": 173,
    "sha256": "cd91b55001d19f88023fe80098c6919baeb99a62d4a65ba2d2339e9ca217bca8",
    "media_type": "image/png",
    "decoded": {
        "format": "PNG",
        "mode": "RGB",
        "width": 64,
        "height": 64,
    },
}


class CandidateContractError(RuntimeError):
    """The static candidate contract is incomplete, stale, or malformed."""


@dataclass(frozen=True)
class NodeContract:
    required: Mapping[str, str]
    optional: Mapping[str, str]
    outputs: tuple[str, ...]


NODE_CONTRACTS: dict[str, NodeContract] = {
    "UNETLoader": NodeContract(
        {"unet_name": "COMBO", "weight_dtype": "COMBO"}, {}, ("MODEL",)
    ),
    "CLIPLoader": NodeContract(
        {"clip_name": "COMBO", "type": "COMBO"},
        {"device": "COMBO"},
        ("CLIP",),
    ),
    "VAELoader": NodeContract({"vae_name": "COMBO"}, {}, ("VAE",)),
    "CLIPTextEncode": NodeContract(
        {"text": "STRING", "clip": "CLIP"}, {}, ("CONDITIONING",)
    ),
    "ConditioningZeroOut": NodeContract(
        {"conditioning": "CONDITIONING"}, {}, ("CONDITIONING",)
    ),
    "LoadImage": NodeContract({"image": "COMBO"}, {}, ("IMAGE", "MASK")),
    "ImageScaleToTotalPixels": NodeContract(
        {
            "image": "IMAGE",
            "upscale_method": "COMBO",
            "megapixels": "FLOAT",
            "resolution_steps": "INT",
        },
        {},
        ("IMAGE",),
    ),
    "VAEEncode": NodeContract(
        {"pixels": "IMAGE", "vae": "VAE"}, {}, ("LATENT",)
    ),
    "ReferenceLatent": NodeContract(
        {"conditioning": "CONDITIONING"}, {"latent": "LATENT"}, ("CONDITIONING",)
    ),
    "CFGGuider": NodeContract(
        {
            "model": "MODEL",
            "positive": "CONDITIONING",
            "negative": "CONDITIONING",
            "cfg": "FLOAT",
        },
        {},
        ("GUIDER",),
    ),
    "RandomNoise": NodeContract({"noise_seed": "INT"}, {}, ("NOISE",)),
    "KSamplerSelect": NodeContract(
        {"sampler_name": "COMBO"}, {}, ("SAMPLER",)
    ),
    "Flux2Scheduler": NodeContract(
        {"steps": "INT", "width": "INT", "height": "INT"}, {}, ("SIGMAS",)
    ),
    "EmptyFlux2LatentImage": NodeContract(
        {"width": "INT", "height": "INT", "batch_size": "INT"},
        {},
        ("LATENT",),
    ),
    "SamplerCustomAdvanced": NodeContract(
        {
            "noise": "NOISE",
            "guider": "GUIDER",
            "sampler": "SAMPLER",
            "sigmas": "SIGMAS",
            "latent_image": "LATENT",
        },
        {},
        ("LATENT", "LATENT"),
    ),
    "VAEDecode": NodeContract(
        {"samples": "LATENT", "vae": "VAE"}, {}, ("IMAGE",)
    ),
    "SaveImage": NodeContract(
        {"images": "IMAGE", "filename_prefix": "STRING"}, {}, ("IMAGE",)
    ),
}

EXPECTED_ARTIFACTS = {
    "flux2-klein-4b-distilled-fp8": (
        4070624520,
        "97ed34fe0567e436200f2faee3939b88f2b5d99f8af2a4dc16532c4245c0ccb6",
        "diffusion_models/flux-2-klein-4b-fp8.safetensors",
    ),
    "qwen3-4b-text-encoder": (
        8044982048,
        "e37269b7ca1301ad72a92627ce95432ab5aad5f89143a06055886aad3419d12f",
        "text_encoders/qwen_3_4b.safetensors",
    ),
    "flux2-vae": (
        168120878,
        "ca70d2202afe6415bdbcb8793ba8cd99fd159cfe6192381504d6c4d3036e0f04",
        "vae/flux2-klein-vae-bf16.safetensors",
    ),
}

EXPECTED_MODEL_SOURCE_REVISIONS = {
    "flux2-klein-4b-distilled-fp8": (
        "black-forest-labs/FLUX.2-klein-4b-fp8",
        "5b4408e59397a4a37ccb46afe426d8ed86379441",
    ),
    "qwen3-4b-text-encoder": (
        "black-forest-labs/FLUX.2-klein-4B",
        "5e67da950fce4a097bc150c22958a05716994cea",
    ),
    "flux2-vae": (
        "black-forest-labs/FLUX.2-klein-4B",
        "5e67da950fce4a097bc150c22958a05716994cea",
    ),
}

EXPECTED_QWEN_SOURCE_FILES = {
    "text_encoder/model.safetensors.index.json": (
        32855,
        "06b3d5319b6d76d1a4a2433419180016cfd54ed62d086a5e6567a809f8c82634",
    ),
    "text_encoder/model-00001-of-00002.safetensors": (
        4967215360,
        "8c0506e7f4936fa7e26183a4fd8da4e2bdbc5990ba64ae441f965d51228f36ea",
    ),
    "text_encoder/model-00002-of-00002.safetensors": (
        3077766632,
        "82f2bd839378541b0557bfabaf37c7d3d637071fdcb73302dedd7cf61162ce07",
    ),
}

EXPECTED_DIRECT_SOURCE_PATHS = {
    "flux2-klein-4b-distilled-fp8": "flux-2-klein-4b-fp8.safetensors",
    "flux2-vae": "vae/diffusion_pytorch_model.safetensors",
}


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateContractError(f"cannot read JSON contract {path.name}") from exc
    if not isinstance(payload, Mapping):
        raise CandidateContractError(f"JSON contract {path.name} is not an object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CandidateContractError(f"bound file is unavailable: {path.name}") from exc
    return digest.hexdigest()


def _pinned_huggingface_url(source: Mapping[str, Any], path: object) -> str:
    repository = source.get("repository")
    revision = source.get("revision")
    if not all(isinstance(value, str) and value for value in (repository, revision, path)):
        return ""
    return f"{repository}/resolve/{revision}/{path}?download=true"


def _load_workflow_builder(root: Path):
    """Compile the exact bound source without accepting cached bytecode."""

    workflow_path = root / "workflow.py"
    namespace: dict[str, Any] = {
        "__name__": "windows_flux2_klein_bound_workflow",
        "__file__": str(workflow_path),
    }
    try:
        code = compile(workflow_path.read_bytes(), str(workflow_path), "exec")
        exec(code, namespace)
    except Exception as exc:  # pragma: no cover - exact import failures vary
        raise CandidateContractError("bound workflow builder cannot be imported") from exc
    builder = namespace.get("build_flux2_klein_workflow")
    if not callable(builder):
        raise CandidateContractError("bound workflow builder entry point is missing")
    return builder


def _spec_type(spec: object) -> str:
    if not isinstance(spec, (list, tuple)) or not spec:
        return ""
    value = spec[0]
    if isinstance(value, str):
        if value == "COMBO" and _combo_choices(spec) is None:
            return ""
        return value
    if _combo_choices(spec) is not None:
        return "COMBO"
    return ""


def _combo_choices(spec: object) -> tuple[str, ...] | None:
    """Parse only the two reviewed single-select COMBO schema encodings."""

    if not isinstance(spec, (list, tuple)):
        return None
    choices: object
    if (
        len(spec) in (1, 2)
        and isinstance(spec[0], (list, tuple))
        and (
            len(spec) == 1
            or (
                isinstance(spec[1], Mapping)
                and (
                    "multiselect" not in spec[1]
                    or spec[1].get("multiselect") is False
                )
            )
        )
    ):
        choices = spec[0]
    elif (
        len(spec) == 2
        and spec[0] == "COMBO"
        and isinstance(spec[1], Mapping)
        and set(spec[1]) == {"multiselect", "options"}
        and spec[1].get("multiselect") is False
    ):
        choices = spec[1].get("options")
    else:
        return None
    if (
        not isinstance(choices, (list, tuple))
        or any(not isinstance(choice, str) or not choice for choice in choices)
        or len(set(choices)) != len(choices)
    ):
        return None
    return tuple(choices)


def _spec_choices(spec: object) -> tuple[object, ...]:
    choices = _combo_choices(spec)
    return choices if choices is not None else ()


def _safe_load_image_name(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
    ):
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def validate_object_info(object_info: object) -> Mapping[str, Any]:
    """Require exact input locations/types and output types for every core node."""

    if not isinstance(object_info, Mapping):
        raise CandidateContractError("object_info must be an object")
    errors: list[str] = []
    for class_name, expected in NODE_CONTRACTS.items():
        raw = object_info.get(class_name)
        if not isinstance(raw, Mapping):
            errors.append(f"missing core class {class_name}")
            continue
        input_info = raw.get("input")
        if not isinstance(input_info, Mapping):
            errors.append(f"{class_name}: input schema is missing")
            continue
        required = input_info.get("required")
        optional = input_info.get("optional", {})
        if not isinstance(required, Mapping) or not isinstance(optional, Mapping):
            errors.append(f"{class_name}: required/optional schema is invalid")
            continue
        for name, expected_type in expected.required.items():
            actual_type = _spec_type(required.get(name))
            if actual_type != expected_type:
                errors.append(
                    f"{class_name}.{name}: required {expected_type}, got {actual_type or 'missing'}"
                )
        for name, expected_type in expected.optional.items():
            actual_type = _spec_type(optional.get(name))
            if actual_type != expected_type:
                errors.append(
                    f"{class_name}.{name}: optional {expected_type}, got {actual_type or 'missing'}"
                )
        outputs = raw.get("output")
        if not isinstance(outputs, (list, tuple)) or tuple(outputs) != expected.outputs:
            errors.append(f"{class_name}: output contract drifted")

    choice_requirements = {
        ("UNETLoader", "unet_name"): "flux-2-klein-4b-fp8.safetensors",
        ("UNETLoader", "weight_dtype"): "default",
        ("CLIPLoader", "clip_name"): "qwen_3_4b.safetensors",
        ("CLIPLoader", "type"): "flux2",
        ("CLIPLoader", "device"): "default",
        ("VAELoader", "vae_name"): "flux2-klein-vae-bf16.safetensors",
        ("KSamplerSelect", "sampler_name"): "euler",
        ("ImageScaleToTotalPixels", "upscale_method"): "nearest-exact",
    }
    for (class_name, input_name), required_choice in choice_requirements.items():
        raw = object_info.get(class_name, {})
        input_info = raw.get("input", {}) if isinstance(raw, Mapping) else {}
        required = input_info.get("required", {}) if isinstance(input_info, Mapping) else {}
        optional = input_info.get("optional", {}) if isinstance(input_info, Mapping) else {}
        spec = (
            required.get(input_name, optional.get(input_name))
            if isinstance(required, Mapping) and isinstance(optional, Mapping)
            else None
        )
        if required_choice not in _spec_choices(spec):
            errors.append(f"{class_name}.{input_name}: {required_choice!r} unavailable")
    if errors:
        raise CandidateContractError("object_info preflight failed: " + "; ".join(errors))
    return object_info


def _is_link(value: object) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
        and value[1] >= 0
    )


def _has_dependency_cycle(workflow: Mapping[str, Any]) -> bool:
    dependencies: dict[str, tuple[str, ...]] = {}
    for node_id, node in workflow.items():
        inputs = node.get("inputs", {}) if isinstance(node, Mapping) else {}
        dependencies[node_id] = (
            tuple(
                value[0]
                for value in inputs.values()
                if _is_link(value) and value[0] in workflow
            )
            if isinstance(inputs, Mapping)
            else ()
        )

    state: dict[str, int] = {}

    def visit(node_id: str) -> bool:
        marker = state.get(node_id, 0)
        if marker == 1:
            return True
        if marker == 2:
            return False
        state[node_id] = 1
        if any(visit(dependency) for dependency in dependencies[node_id]):
            return True
        state[node_id] = 2
        return False

    return any(
        visit(node_id)
        for node_id in dependencies
        if state.get(node_id, 0) == 0
    )


def validate_workflow(
    workflow: object, object_info: object
) -> Mapping[str, Any]:
    """Validate a candidate graph without contacting a worker or uploading media."""

    schemas = validate_object_info(object_info)
    if not isinstance(workflow, Mapping) or not workflow:
        raise CandidateContractError("workflow must be a non-empty flat object")
    errors: list[str] = []
    counts: Counter[str] = Counter()
    for node_id, node in workflow.items():
        if not isinstance(node_id, str) or not isinstance(node, Mapping):
            errors.append(f"node {node_id!r}: invalid flat API node")
            continue
        class_name = node.get("class_type")
        contract = NODE_CONTRACTS.get(class_name) if isinstance(class_name, str) else None
        if contract is None:
            errors.append(f"node {node_id}: unapproved class {class_name!r}")
            continue
        counts[class_name] += 1
        inputs = node.get("inputs")
        if not isinstance(inputs, Mapping):
            errors.append(f"node {node_id} ({class_name}): inputs missing")
            continue
        allowed = set(contract.required) | set(contract.optional)
        missing = sorted(set(contract.required) - set(inputs))
        unknown = sorted(set(inputs) - allowed)
        if missing:
            errors.append(f"node {node_id} ({class_name}): missing {missing}")
        if unknown:
            errors.append(f"node {node_id} ({class_name}): unknown {unknown}")
        raw_schema = schemas[class_name]
        schema_inputs = raw_schema["input"]
        required_schema = schema_inputs["required"]
        optional_schema = schema_inputs.get("optional", {})
        for name, value in inputs.items():
            expected_type = contract.required.get(name, contract.optional.get(name))
            if _is_link(value):
                origin_id, output_index = value
                origin = workflow.get(origin_id)
                if not isinstance(origin, Mapping):
                    errors.append(f"node {node_id}.{name}: missing origin {origin_id}")
                    continue
                origin_class = origin.get("class_type")
                origin_contract = NODE_CONTRACTS.get(origin_class)
                if origin_contract is None or output_index >= len(origin_contract.outputs):
                    errors.append(f"node {node_id}.{name}: invalid origin output")
                elif origin_contract.outputs[output_index] != expected_type:
                    errors.append(f"node {node_id}.{name}: link type mismatch")
                continue
            if expected_type == "STRING" and not isinstance(value, str):
                errors.append(f"node {node_id}.{name}: expected STRING")
            elif expected_type == "INT" and (
                isinstance(value, bool) or not isinstance(value, int)
            ):
                errors.append(f"node {node_id}.{name}: expected INT")
            elif expected_type == "FLOAT" and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                errors.append(f"node {node_id}.{name}: expected FLOAT")
            spec = required_schema.get(name, optional_schema.get(name))
            choices = _spec_choices(spec)
            if class_name == "LoadImage" and name == "image":
                if not _safe_load_image_name(value):
                    errors.append(
                        f"node {node_id}.{name}: unsafe relative POSIX filename"
                    )
            elif choices and value not in choices:
                errors.append(f"node {node_id}.{name}: value is not installed/allowed")

    if _has_dependency_cycle(workflow):
        errors.append("candidate graph contains a dependency cycle")

    singleton_classes = set(NODE_CONTRACTS) - {
        "LoadImage",
        "ImageScaleToTotalPixels",
        "VAEEncode",
        "ReferenceLatent",
    }
    for class_name in singleton_classes:
        if counts[class_name] != 1:
            errors.append(f"workflow requires exactly one {class_name}")
    references = counts["LoadImage"]
    if not 1 <= references <= 10:
        errors.append("workflow requires 1..10 reference images")
    if counts["ImageScaleToTotalPixels"] != references or counts["VAEEncode"] != references:
        errors.append("each reference requires one scale and VAE encode node")
    if counts["ReferenceLatent"] != references * 2:
        errors.append("each reference must bind both positive and negative conditioning")

    def inputs_for(node_id: str) -> Mapping[str, Any]:
        node = workflow.get(node_id)
        return node.get("inputs", {}) if isinstance(node, Mapping) else {}

    expected_node_ids = {str(index) for index in range(1, 10)} | {
        "20",
        "21",
        "22",
        "23",
    }
    for index in range(references):
        base = 100 + index * 10
        expected_node_ids.update(str(base + offset) for offset in range(5))
    if set(workflow) != expected_node_ids:
        errors.append("candidate graph node identifiers drifted")

    if inputs_for("1") != {
        "unet_name": "flux-2-klein-4b-fp8.safetensors",
        "weight_dtype": "default",
    }:
        errors.append("diffusion model binding drifted")
    if inputs_for("2") != {
        "clip_name": "qwen_3_4b.safetensors",
        "type": "flux2",
        "device": "default",
    }:
        errors.append("text encoder binding drifted")
    if inputs_for("3") != {"vae_name": "flux2-klein-vae-bf16.safetensors"}:
        errors.append("VAE binding drifted")
    if inputs_for("7").get("sampler_name") != "euler":
        errors.append("sampler must remain euler")
    scheduler = inputs_for("8")
    latent = inputs_for("9")
    if scheduler.get("steps") != 4:
        errors.append("distilled scheduler must remain four steps")
    if latent.get("batch_size") != 1:
        errors.append("candidate batch size must remain one")
    if (scheduler.get("width"), scheduler.get("height")) != (
        latent.get("width"),
        latent.get("height"),
    ):
        errors.append("scheduler and latent dimensions differ")
    approved_dimensions = {
        (1024, 1024),
        (832, 1248),
        (1248, 832),
        (864, 1152),
        (1152, 864),
        (720, 1280),
        (1280, 720),
        (1568, 672),
    }
    if (scheduler.get("width"), scheduler.get("height")) not in approved_dimensions:
        errors.append("output aspect is not in the fixed candidate contract")
    if inputs_for("20").get("cfg") != 1.0:
        errors.append("distilled CFG must remain 1.0")

    if inputs_for("4").get("clip") != ["2", 0]:
        errors.append("prompt encoder link drifted")
    if inputs_for("5") != {"conditioning": ["4", 0]}:
        errors.append("negative conditioning link drifted")
    seed = inputs_for("6").get("noise_seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**64:
        errors.append("noise seed must remain unsigned 64-bit")

    positive: list[object] = ["4", 0]
    negative: list[object] = ["5", 0]
    for index in range(references):
        base = 100 + index * 10
        load_id = str(base)
        scale_id = str(base + 1)
        encode_id = str(base + 2)
        positive_id = str(base + 3)
        negative_id = str(base + 4)
        reference_name = inputs_for(load_id).get("image")
        if not isinstance(reference_name, str) or not reference_name:
            errors.append(f"reference {index + 1} filename is missing")
        if inputs_for(scale_id) != {
            "image": [load_id, 0],
            "upscale_method": "nearest-exact",
            "megapixels": 1.0,
            "resolution_steps": 16,
        }:
            errors.append(f"reference {index + 1} scale contract drifted")
        if inputs_for(encode_id) != {
            "pixels": [scale_id, 0],
            "vae": ["3", 0],
        }:
            errors.append(f"reference {index + 1} VAE encode contract drifted")
        if inputs_for(positive_id) != {
            "conditioning": positive,
            "latent": [encode_id, 0],
        }:
            errors.append(f"reference {index + 1} positive chain drifted")
        if inputs_for(negative_id) != {
            "conditioning": negative,
            "latent": [encode_id, 0],
        }:
            errors.append(f"reference {index + 1} negative chain drifted")
        positive = [positive_id, 0]
        negative = [negative_id, 0]

    guider = inputs_for("20")
    if (
        guider.get("model") != ["1", 0]
        or guider.get("positive") != positive
        or guider.get("negative") != negative
    ):
        errors.append("guider reference-chain binding drifted")
    if inputs_for("21") != {
        "noise": ["6", 0],
        "guider": ["20", 0],
        "sampler": ["7", 0],
        "sigmas": ["8", 0],
        "latent_image": ["9", 0],
    }:
        errors.append("sampler input binding drifted")
    if inputs_for("22") != {"samples": ["21", 0], "vae": ["3", 0]}:
        errors.append("decode binding drifted")
    output = inputs_for("23")
    if output.get("images") != ["22", 0] or not isinstance(
        output.get("filename_prefix"), str
    ) or not output.get("filename_prefix"):
        errors.append("output binding drifted")

    if errors:
        raise CandidateContractError("workflow preflight failed: " + "; ".join(errors))
    return {
        "status": "static_preflight_passed",
        "node_count": len(workflow),
        "reference_count": references,
        "execution_proven": False,
    }


def validate_package(root: Path = ROOT) -> Mapping[str, Any]:
    """Validate manifests and bindings while preserving not-ready truth."""

    candidate = _load_json(root / "candidate.json")
    models = _load_json(root / "models.json")
    revisions = _load_json(root / "revisions.json")
    object_info = _load_json(root / "fixtures" / "object_info.json")
    if (
        candidate.get("capability") != "image-flux2-klein"
        or candidate.get("candidate_state") != "not_installed"
    ):
        raise CandidateContractError("candidate state must remain not_installed")
    readiness = candidate.get("readiness")
    if not isinstance(readiness, Mapping) or (
        readiness.get("state") != "not_installed"
        or readiness.get("startup_ready") is not False
        or readiness.get("execution_proven") is not False
        or readiness.get("benchmark_state") != "not_run"
    ):
        raise CandidateContractError("candidate readiness overclaims execution")
    license_review = candidate.get("license_review")
    if not isinstance(license_review, Mapping) or dict(license_review) != {
        "state": "official_sources_selected_derivation_pending",
        "blocker_code": "qwen_official_shard_derivation_not_verified",
    }:
        raise CandidateContractError("candidate license/derivation blocker drifted")
    bindings = candidate.get("bindings")
    if not isinstance(bindings, Mapping):
        raise CandidateContractError("candidate bindings are missing")
    if set(bindings) != EXPECTED_BOUND_FILES:
        raise CandidateContractError("candidate binding inventory is incomplete or unexpected")
    for relative, expected_hash in bindings.items():
        if (
            not isinstance(relative, str)
            or not isinstance(expected_hash, str)
            or len(expected_hash) != HEX_LENGTH
        ):
            raise CandidateContractError("candidate binding is not a SHA-256 record")
        path = (root / relative).resolve()
        if root.resolve() not in path.parents or _sha256(path) != expected_hash:
            raise CandidateContractError(f"candidate binding mismatch: {relative}")

    fixture_contract = _load_json(root / "fixtures" / "reference.json")
    if {key: fixture_contract.get(key) for key in EXPECTED_FIXTURE} != EXPECTED_FIXTURE:
        raise CandidateContractError("fixed execution fixture contract drifted")
    try:
        fixture = base64.b64decode(
            (root / "fixtures" / "reference.png.b64")
            .read_text(encoding="ascii")
            .strip(),
            validate=True,
        )
    except (OSError, ValueError) as exc:
        raise CandidateContractError("fixed execution fixture cannot be decoded") from exc
    if (
        len(fixture) != EXPECTED_FIXTURE["expected_bytes"]
        or hashlib.sha256(fixture).hexdigest() != EXPECTED_FIXTURE["sha256"]
        or not fixture.startswith(b"\x89PNG\r\n\x1a\n")
    ):
        raise CandidateContractError("fixed execution fixture bytes drifted")

    artifacts = models.get("artifacts")
    if not isinstance(artifacts, list):
        raise CandidateContractError("model artifact manifest is invalid")
    actual_artifacts: dict[str, tuple[object, object, object]] = {}
    actual_source_revisions: dict[str, tuple[object, object]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, Mapping) or not isinstance(artifact.get("id"), str):
            raise CandidateContractError("model artifact record is invalid")
        actual_artifacts[artifact["id"]] = (
            artifact.get("expected_bytes"),
            artifact.get("sha256"),
            artifact.get("destination"),
        )
        source = artifact.get("source")
        if not isinstance(source, Mapping):
            raise CandidateContractError("model source provenance is missing")
        repository = source.get("repository")
        repository_id = (
            repository.removeprefix("https://huggingface.co/")
            if isinstance(repository, str)
            else repository
        )
        actual_source_revisions[artifact["id"]] = (
            repository_id,
            source.get("revision"),
        )
        direct_path = EXPECTED_DIRECT_SOURCE_PATHS.get(artifact["id"])
        if direct_path is not None and (
            source.get("path") != direct_path
            or source.get("url") != _pinned_huggingface_url(source, direct_path)
        ):
            raise CandidateContractError("direct official model source path drifted")
        license_record = artifact.get("license")
        if not isinstance(license_record, Mapping) or not isinstance(
            license_record.get("review_state"), str
        ):
            raise CandidateContractError("model license provenance is missing")
        if license_record.get("source_declaration") != "Apache-2.0":
            raise CandidateContractError("model source license declaration drifted")
    if actual_artifacts != EXPECTED_ARTIFACTS:
        raise CandidateContractError("model artifact pins do not match the reviewed set")
    if actual_source_revisions != EXPECTED_MODEL_SOURCE_REVISIONS:
        raise CandidateContractError("model source revision pins drifted")

    qwen = next(
        artifact for artifact in artifacts if artifact.get("id") == "qwen3-4b-text-encoder"
    )
    qwen_source = qwen["source"]
    qwen_derivation = qwen_source.get("derivation")
    qwen_index = qwen_source.get("index")
    qwen_inputs = qwen_source.get("inputs")
    if (
        qwen_source.get("type") != "deterministic_official_shard_merge"
        or not isinstance(qwen_derivation, Mapping)
        or dict(qwen_derivation) != {
            "script": "merge_qwen_encoder.py",
            "tensor_order": "lexicographic_tensor_name",
            "metadata": None,
            "expected_tensor_count": 398,
            "expected_header_bytes": 45848,
            "execution_state": "not_executed",
        }
        or qwen.get("license", {}).get("review_state")
        != "official_source_derivation_not_execution_proven"
    ):
        raise CandidateContractError("Qwen official-source derivation truth drifted")
    if not isinstance(qwen_index, Mapping) or not isinstance(qwen_inputs, list):
        raise CandidateContractError("Qwen official-source file pins are missing")
    qwen_records = [qwen_index, *qwen_inputs]
    actual_qwen_source_files = {
        record.get("path"): (record.get("expected_bytes"), record.get("sha256"))
        for record in qwen_records
        if isinstance(record, Mapping)
    }
    if actual_qwen_source_files != EXPECTED_QWEN_SOURCE_FILES:
        raise CandidateContractError("Qwen official-source file pins drifted")
    if any(
        record.get("url") != _pinned_huggingface_url(qwen_source, record.get("path"))
        for record in qwen_records
        if isinstance(record, Mapping)
    ):
        raise CandidateContractError("Qwen official-source URL pins drifted")
    vae = next(artifact for artifact in artifacts if artifact.get("id") == "flux2-vae")
    if (
        vae["source"].get("type") != "direct_official_artifact"
        or vae.get("license", {}).get("review_state")
        != "official_source_and_static_compatibility_verified"
    ):
        raise CandidateContractError("VAE official-source provenance truth drifted")

    components = revisions.get("components")
    if not isinstance(components, list):
        raise CandidateContractError("revision manifest is invalid")
    component_commits = {
        component.get("id"): component.get("commit")
        for component in components
        if isinstance(component, Mapping)
    }
    if component_commits != {
        "comfyui": "b1693ecba9f5b65f8c80ab36b195ab963ec92413",
        "official-workflow-template": "6c038ced23eb9d4de675b14aa854b616a6a7cd16",
    }:
        raise CandidateContractError("source revision pins drifted")
    validate_object_info(object_info)
    builder = _load_workflow_builder(root)
    graph_results: dict[str, Mapping[str, Any]] = {}
    for reference_count in (1, 2, 10):
        reference_images = [
            f"reference-{index}.png" for index in range(1, reference_count + 1)
        ]
        try:
            graph = builder(
                prompt="fixed offline candidate contract probe",
                reference_images=reference_images,
                seed=424242,
                aspect_ratio="16:9",
                filename_prefix="flux2-klein-contract-probe",
            )
        except Exception as exc:
            raise CandidateContractError(
                f"workflow builder failed for {reference_count} references"
            ) from exc
        result = validate_workflow(graph, object_info)
        if result.get("reference_count") != reference_count:
            raise CandidateContractError(
                f"workflow builder reference count drifted for {reference_count} inputs"
            )
        graph_results[str(reference_count)] = result
    return {
        "status": "candidate_contract_valid",
        "capability": "image-flux2-klein",
        "readiness_state": "not_installed",
        "execution_proven": False,
        "artifact_count": len(artifacts),
        "core_class_count": len(NODE_CONTRACTS),
        "validated_reference_counts": sorted(int(key) for key in graph_results),
    }


if __name__ == "__main__":
    print(json.dumps(validate_package(), sort_keys=True))
