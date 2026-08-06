"""Offline contract tests for the isolated Windows FLUX.2 LoRA candidate."""

from __future__ import annotations

import copy
import functools
import hashlib
import io
import json
import shutil
import struct
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "deploy" / "windows-flux2-lora"
JOB_ID = "0" * 32
RUNTIME_SHA = "6" * 64


def _load(name: str, path: Path):
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


contract = _load("contract", PACKAGE / "contract.py")
inference = _load("inference", PACKAGE / "inference.py")
train = _load("train", PACKAGE / "train.py")
benchmark = _load("windows_flux2_lora_benchmark", PACKAGE / "benchmark.py")
installer = _load("windows_flux2_lora_install", PACKAGE / "install.py")


def _png(index: int) -> bytes:
    from PIL import Image

    output = io.BytesIO()
    Image.new("RGB", (512, 512), (index, index * 2, index * 3)).save(
        output, format="PNG"
    )
    return output.getvalue()


def _api_manifest() -> dict:
    return {
        "schema_version": 1,
        "contract": contract.CANARY_CONTRACT,
        "candidate_sha256": hashlib.sha256(
            (PACKAGE / "candidate.json").read_bytes()
        ).hexdigest(),
        "consent": True,
        "references": [
            {
                "sha256": hashlib.sha256(_png(index)).hexdigest(),
                "caption": contract.FIXED_CAPTIONS[index - 1],
            }
            for index in range(1, 5)
        ],
    }


JOB_ID = hashlib.sha256(contract.canonical_utf8_json_bytes(_api_manifest())).hexdigest()[:32]


def _write_job(state_root: Path, *, mutate=None) -> dict:
    input_root = state_root / "jobs" / JOB_ID / "input"
    input_root.mkdir(parents=True)
    references = []
    for index in range(1, 5):
        stem = f"reference-{index:02d}"
        image = _png(index)
        caption = contract.FIXED_CAPTIONS[index - 1].encode()
        (input_root / f"{stem}.png").write_bytes(image)
        (input_root / f"{stem}.txt").write_bytes(caption)
        references.append(
            {
                "image": f"{stem}.png",
                "image_bytes": len(image),
                "image_sha256": hashlib.sha256(image).hexdigest(),
                "caption": f"{stem}.txt",
                "caption_bytes": len(caption),
                "caption_sha256": hashlib.sha256(caption).hexdigest(),
            }
        )
    reference_set_sha = hashlib.sha256(contract.canonical_json_bytes(references)).hexdigest()
    manifest = {
        "schema_version": 1,
        "job_id": JOB_ID,
        "trigger_token": "hkkperson",
        "consent": {
            "identity_owner_authorized": True,
            "training_use_authorized": True,
            "reference_set_sha256": reference_set_sha,
        },
        "references": references,
    }
    if mutate:
        mutate(manifest, input_root)
    (input_root / "job.json").write_bytes(contract.canonical_json_bytes(manifest))
    api_manifest = {
        "schema_version": 1,
        "contract": contract.CANARY_CONTRACT,
        "candidate_sha256": hashlib.sha256((PACKAGE / "candidate.json").read_bytes()).hexdigest(),
        "consent": True,
        "references": [
            {
                "sha256": reference["image_sha256"],
                "caption": (input_root / reference["caption"]).read_text(encoding="utf-8"),
            }
            for reference in references
        ],
    }
    (input_root.parent / "manifest.json").write_bytes(
        contract.canonical_utf8_json_bytes(api_manifest)
    )
    return manifest


def _metadata(payload: bytes) -> dict:
    sha = hashlib.sha256(payload).hexdigest()
    return contract.build_adapter_metadata(
        job_id=JOB_ID,
        adapter_bytes=len(payload),
        adapter_sha256=sha,
        input_manifest_sha256="1" * 64,
        config_sha256="2" * 64,
        package_sha256="3" * 64,
        inference_runtime_sha256=RUNTIME_SHA,
        tensor_count=160,
        pair_count=80,
        tensor_inventory_sha256=_lora_inventory_sha256(),
    )


def _lora_tensor_records() -> tuple[dict, list[dict], int]:
    tensors = {}
    inventory = []
    offset = 0
    for module, sides in sorted(contract.expected_lora_shapes().items()):
        for side in ("A", "B"):
            shape = list(sides[side])
            size = 2 * shape[0] * shape[1]
            name = f"{module}.lora_{side}.weight"
            tensors[name] = {
                "dtype": "BF16",
                "shape": shape,
                "data_offsets": [offset, offset + size],
            }
            inventory.append({"name": name, "dtype": "BF16", "shape": shape})
            offset += size
    return tensors, inventory, offset


def _lora_inventory_sha256() -> str:
    _tensors, inventory, _size = _lora_tensor_records()
    return hashlib.sha256(contract.canonical_json_bytes(inventory)).hexdigest()


@functools.lru_cache(maxsize=2)
def _tiny_lora(step: int | None = None) -> bytes:
    tensors, _inventory, data_bytes = _lora_tensor_records()
    if step is not None:
        tensors = {
            "__metadata__": {
                "training_info": json.dumps({"step": step, "epoch": 0})
            },
            **tensors,
        }
    header = json.dumps(tensors, separators=(",", ":")).encode()
    return struct.pack("<Q", len(header)) + header + bytes(data_bytes)


def _partial_lora() -> bytes:
    tensors = {
        "diffusion_model.single_blocks.0.linear1.lora_A.weight": {
            "dtype": "BF16",
            "shape": [16, 3072],
            "data_offsets": [0, 98_304],
        },
        "diffusion_model.single_blocks.0.linear1.lora_B.weight": {
            "dtype": "BF16",
            "shape": [27_648, 16],
            "data_offsets": [98_304, 983_040],
        },
    }
    header = json.dumps(tensors, separators=(",", ":")).encode()
    return struct.pack("<Q", len(header)) + header + bytes(983_040)


def _object_info(lora_name: str) -> dict:
    graph = inference.build_inference_workflow(
        metadata=_metadata(_tiny_lora()), prompt="hkkperson standing in a studio"
    )
    info = {node["class_type"]: {"input": {"required": {}}} for node in graph.values()}
    info["UNETLoader"]["input"]["required"] = {
        "unet_name": [[contract.DISTILLED_FILENAME]],
        "weight_dtype": [["default"]],
    }
    info["LoraLoaderModelOnly"]["input"]["required"] = {
        "model": ["MODEL"],
        "lora_name": [[lora_name]],
        "strength_model": ["FLOAT"],
    }
    info["CLIPLoader"]["input"]["required"] = {
        "clip_name": [[contract.TEXT_ENCODER_FILENAME]],
        "type": [["flux2"]],
    }
    info["VAELoader"]["input"]["required"] = {
        "vae_name": [[contract.INFERENCE_VAE_FILENAME]],
    }
    return info


def _resource() -> dict:
    return {
        "operating_system": "Windows",
        "architecture": "AMD64",
        "python": "3.12",
        "ram_bytes": 34_359_738_368,
        "free_disk_bytes": 42_949_672_960,
        "cuda_available": True,
        "torch_version": contract.TORCH_VERSION,
        "torchvision_version": contract.TORCHVISION_VERSION,
        "torchaudio_version": contract.TORCHAUDIO_VERSION,
        "cuda_version": "13.0",
        "runtime_imports_sha256": "3" * 64,
        "cuda_smoke_passed": True,
        "toolkit_import_smoke_passed": True,
        "gpu_name": "NVIDIA GeForce RTX 5070 Ti",
        "gpu_uuid": "GPU-01234567-89ab-cdef-0123-456789abcdef",
        "vram_mib": 16_303,
        "free_vram_mib": 14_500,
        "gpu_utilization_percent": 0,
        "compute_capability": "12.0",
        "packages_sha256": "4" * 64,
    }


def _adapter_record(payload: bytes) -> dict[str, object]:
    sha = hashlib.sha256(payload).hexdigest()
    filename = contract.adapter_filename(sha)
    return {
        "filename": filename,
        "bytes": len(payload),
        "sha256": sha,
        "metadata_filename": f"{filename}.json",
        "metadata_sha256": "5" * 64,
        "tensor_count": 160,
        "pair_count": 80,
        "tensor_inventory_sha256": _lora_inventory_sha256(),
    }


def _terminal_record(
    *, candidate_sha: str = "a" * 64, manifest_sha: str = "b" * 64
) -> dict[str, object]:
    return train._terminal(
        job_id=JOB_ID,
        state="training_passed",
        attempt=1,
        blocker_code=None,
        return_code=0,
        elapsed_seconds=12.5,
        peak_vram_bytes=15_000_000_000,
        telemetry_complete=True,
        package_sha256=candidate_sha,
        manifest_sha256=manifest_sha,
        input_manifest_sha256="c" * 64,
        config_sha256="d" * 64,
        log_sha256="e" * 64,
        adapter=_adapter_record(_tiny_lora()),
        resume_checkpoint_sha256=None,
        inference_runtime_sha256=RUNTIME_SHA,
        activity_lease_sha256="7" * 64,
    )


def _real_png(index: int, *, prompt_metadata: str | None = None) -> bytes:
    from PIL import Image, PngImagePlugin

    output = io.BytesIO()
    pnginfo = None
    if prompt_metadata is not None:
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("prompt", prompt_metadata)
    Image.new("RGB", (1024, 1024), (index, index * 2, index * 3)).save(
        output, format="PNG", pnginfo=pnginfo
    )
    return output.getvalue()


def _prepare_started_job(
    state_root: Path,
    *,
    activity_lease_sha256: str = "7" * 64,
    bind_live_training_lock: bool = False,
) -> dict[str, object]:
    _write_job(state_root)
    candidate_sha = contract.package_digest(PACKAGE)
    admitted = contract.validate_input_manifest(state_root, JOB_ID)
    api_manifest = contract.validate_api_manifest(
        state_root,
        JOB_ID,
        input_result=admitted,
        candidate_sha256=candidate_sha,
    )
    paths = contract.job_paths(state_root, JOB_ID)
    config_sha = contract.write_json_new(
        paths["config"],
        contract.build_training_config(state_root, JOB_ID),
        root=paths["root"],
    )
    lease_sha = "8" * 64
    if bind_live_training_lock:
        lease_sha = contract.write_json_new(
            paths["lock"],
            {
                "schema_version": 1,
                "job_id": JOB_ID,
                "pid": 1234,
                "nonce": "a" * 32,
            },
            root=paths["root"],
        )
    contract.write_json_new(
        paths["evidence"] / "started.json",
        {
            "schema_version": 1,
            "job_id": JOB_ID,
            "state": "started",
            "attempt": 1,
            "admission_sha256": "9" * 64,
            "lease_sha256": lease_sha,
            "activity_lease_sha256": activity_lease_sha256,
        },
        root=paths["root"],
    )
    return {
        "paths": paths,
        "candidate_sha": candidate_sha,
        "admitted": admitted,
        "api_manifest": api_manifest,
        "config_sha": config_sha,
    }


def _prepare_terminal_job(
    state_root: Path,
    *,
    state: str = "training_passed",
    attempt: int = 1,
    initial_activity_lease_sha256: str = "7" * 64,
    current_activity_lease_sha256: str = "7" * 64,
) -> dict[str, object]:
    prepared = _prepare_started_job(
        state_root,
        activity_lease_sha256=initial_activity_lease_sha256,
    )
    paths = prepared["paths"]
    assert isinstance(paths, dict)
    if attempt == 2:
        contract.write_json_new(
            paths["evidence"] / "resume-started.json",
            {
                "schema_version": 1,
                "job_id": JOB_ID,
                "state": "started",
                "attempt": 2,
                "lease_sha256": "4" * 64,
                "activity_lease_sha256": current_activity_lease_sha256,
            },
            root=paths["root"],
        )

    candidate_sha = prepared["candidate_sha"]
    admitted = prepared["admitted"]
    api_manifest = prepared["api_manifest"]
    config_sha = prepared["config_sha"]
    assert isinstance(candidate_sha, str)
    assert isinstance(admitted, dict)
    assert isinstance(api_manifest, dict)
    assert isinstance(config_sha, str)

    metadata = None
    adapter_record = None
    if state == "training_passed":
        payload = _tiny_lora()
        metadata = contract.build_adapter_metadata(
            job_id=JOB_ID,
            adapter_bytes=len(payload),
            adapter_sha256=hashlib.sha256(payload).hexdigest(),
            input_manifest_sha256=admitted["sha256"],
            config_sha256=config_sha,
            package_sha256=candidate_sha,
            inference_runtime_sha256=RUNTIME_SHA,
            tensor_count=160,
            pair_count=80,
            tensor_inventory_sha256=_lora_inventory_sha256(),
        )
        paths["adapter"].mkdir(parents=True)
        adapter_path = paths["adapter"] / metadata["adapter"]["filename"]
        adapter_path.write_bytes(payload)
        metadata_path = paths["adapter"] / f"{adapter_path.name}.json"
        metadata_sha = contract.write_json_new(
            metadata_path, metadata, root=paths["root"]
        )
        adapter_record = {
            **metadata["adapter"],
            "metadata_filename": metadata_path.name,
            "metadata_sha256": metadata_sha,
        }

    blockers = {
        "training_passed": None,
        "failed": "training_failed",
        "unknown": "training_outcome_ambiguous",
    }
    terminal = train._terminal(
        job_id=JOB_ID,
        state=state,
        attempt=attempt,
        blocker_code=blockers[state],
        return_code={"training_passed": 0, "failed": 1, "unknown": None}[state],
        elapsed_seconds=12.5,
        peak_vram_bytes=15_000_000_000,
        telemetry_complete=state != "unknown",
        package_sha256=candidate_sha,
        manifest_sha256=api_manifest["sha256"],
        input_manifest_sha256=admitted["sha256"],
        config_sha256=config_sha,
        log_sha256="e" * 64,
        adapter=adapter_record,
        resume_checkpoint_sha256="4" * 64 if attempt == 2 else None,
        inference_runtime_sha256=RUNTIME_SHA,
        activity_lease_sha256=current_activity_lease_sha256,
    )
    contract.write_json_new(
        paths["evidence"] / "terminal.json", terminal, root=paths["root"]
    )
    return {**prepared, "metadata": metadata, "terminal": terminal}


def _prepare_benchmark_job(state_root: Path) -> dict:
    prepared = _prepare_terminal_job(state_root)
    metadata = prepared["metadata"]
    assert isinstance(metadata, dict)
    return metadata


def _prepare_interrupted_job(
    state_root: Path, *, checkpoint: bool, second_attempt: bool
) -> None:
    prepared = _prepare_started_job(
        state_root,
        activity_lease_sha256="1" * 64 if second_attempt else "7" * 64,
        bind_live_training_lock=not second_attempt,
    )
    paths = prepared["paths"]
    assert isinstance(paths, dict)
    if second_attempt:
        lease_sha = contract.write_json_new(
            paths["lock"],
            {
                "schema_version": 1,
                "job_id": JOB_ID,
                "pid": 5678,
                "nonce": "b" * 32,
            },
            root=paths["root"],
        )
        contract.write_json_new(
            paths["evidence"] / "resume-started.json",
            {
                "schema_version": 1,
                "job_id": JOB_ID,
                "state": "started",
                "attempt": 2,
                "lease_sha256": lease_sha,
                "activity_lease_sha256": "7" * 64,
            },
            root=paths["root"],
        )
    if checkpoint:
        save_root = paths["output"] / f"identity_lora_{JOB_ID}"
        save_root.mkdir(parents=True)
        checkpoint_path = (
            save_root / f"identity_lora_{JOB_ID}_000000200.safetensors"
        )
        checkpoint_path.write_bytes(_tiny_lora(step=200))
        (save_root / "optimizer.pt").write_bytes(bytes(1024))


def _benchmark_api(metadata: dict, *, identical_pixels: bool = False):
    info = _object_info(metadata["adapter"]["filename"])
    submitted = []
    histories = {}
    control_png = _real_png(
        1, prompt_metadata="control graph" if identical_pixels else None
    )
    lora_png = (
        _real_png(1, prompt_metadata="lora graph")
        if identical_pixels
        else _real_png(2)
    )

    def api_json(method, path, payload=None):
        if method == "GET" and path == "/queue":
            return {"queue_running": [], "queue_pending": []}
        if method == "GET" and path == "/object_info":
            return info
        if method == "POST" and path == "/prompt":
            graph = payload["prompt"]
            submitted.append(graph)
            prompt_id = str(len(submitted)) * 32
            prefix = graph["14"]["inputs"]["filename_prefix"]
            histories[prompt_id] = {
                prompt_id: {
                    "status": {"status_str": "success"},
                    "outputs": {
                        "14": {
                            "images": [
                                {
                                    "filename": f"{prefix}_00001_.png",
                                    "subfolder": "",
                                    "type": "output",
                                }
                            ]
                        }
                    },
                }
            }
            return {"prompt_id": prompt_id}
        if method == "GET" and path.startswith("/history/"):
            return histories[path.rsplit("/", 1)[-1]]
        raise AssertionError((method, path, payload))

    def api_bytes(path):
        return control_png if "identity-control-" in path else lora_png

    ticks = [0.0]

    def clock():
        ticks[0] += 0.25
        return ticks[0]

    return submitted, api_json, api_bytes, clock


@pytest.fixture
def proven_inference_runtime(monkeypatch):
    def runtime():
        return {
            "runtime_contract_sha256": RUNTIME_SHA,
            "status_sha256": "8" * 64,
            "package_candidate_sha256": contract.INFERENCE_PACKAGE_BINDINGS[
                "candidate.json"
            ],
        }

    monkeypatch.setattr(benchmark, "validate_inference_runtime", runtime)
    monkeypatch.setattr(contract, "validate_inference_runtime", runtime)


def test_package_manifest_is_hash_bound_and_truthfully_not_ready():
    candidate = contract.validate_package(PACKAGE)

    assert candidate["candidate_state"] == "not_installed"
    assert candidate["readiness"] == {
        "state": "not_installed",
        "startup_ready": False,
        "execution_proven": False,
        "training_canary": "not_run",
        "inference_canary": "not_run",
        "blocker_code": "candidate_runtime_not_installed",
    }
    assert candidate["upstreams"]["ai_toolkit"]["commit"] == contract.TOOLKIT_COMMIT
    assert candidate["upstreams"]["training_base"] == {
        "repository": contract.BASE_REPOSITORY,
        "revision": contract.BASE_REVISION,
        "transformer": contract.BASE_FILENAME,
        "expected_bytes": contract.BASE_BYTES,
        "sha256": contract.BASE_SHA256,
        "license": "Apache-2.0",
    }
    assert candidate["upstreams"]["qwen"]["revision"] == contract.QWEN_REVISION


def test_every_direct_runtime_requirement_has_an_installed_venv_import_probe():
    direct = set()
    for raw in (PACKAGE / "requirements.in").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        name = line.split("@", 1)[0].split("==", 1)[0].strip()
        direct.add(name.lower().replace("_", "-"))

    assert set(contract.DIRECT_RUNTIME_IMPORTS) == direct
    assert contract.DIRECT_RUNTIME_IMPORTS["torch"] == "torch"
    assert contract.DIRECT_RUNTIME_IMPORTS["torchvision"] == "torchvision"
    assert contract.DIRECT_RUNTIME_IMPORTS["torchaudio"] == "torchaudio"


def test_package_hash_drift_fails_closed(tmp_path):
    copied = tmp_path / "candidate"
    shutil.copytree(PACKAGE, copied, ignore=shutil.ignore_patterns("__pycache__"))
    (copied / "README.md").write_text("drift", encoding="utf-8")

    with pytest.raises(contract.ContractError, match="hash drifted"):
        contract.validate_package(copied)


def test_package_rejects_executable_bytecode_cache(tmp_path):
    copied = tmp_path / "candidate"
    shutil.copytree(PACKAGE, copied)
    cache = copied / "__pycache__"
    cache.mkdir()
    (cache / "contract.cpython-312.pyc").write_bytes(b"crafted")

    with pytest.raises(contract.ContractError, match="inventory drifted"):
        contract.validate_package(copied)


@pytest.mark.parametrize(
    "value",
    [
        "01234567-89ab-cdef-0123-456789abcdef",
        "0123456789ABCDEF0123456789ABCDEF",
        "../0123456789abcdef0123456789abcd",
        "0" * 31,
        "0" * 33,
    ],
)
def test_only_exact_server_job_id_shape_is_accepted(value):
    with pytest.raises(contract.ContractError):
        contract.canonical_job_id(value)


def test_fixed_training_config_contains_the_complete_500_step_canary(tmp_path):
    process = contract.build_training_config(tmp_path, JOB_ID)["config"]["process"][0]

    assert process["type"] == "sd_trainer"
    assert process["device"] == "cuda:0"
    assert process["training_seed"] == 0
    assert process["trigger_word"] == "hkkperson"
    assert process["network"] == {
        "type": "lora",
        "linear": 16,
        "linear_alpha": 16,
        "transformer_only": True,
    }
    assert process["datasets"] == [
        {
            "folder_path": str(tmp_path / "jobs" / JOB_ID / "input"),
            "caption_ext": "txt",
            "caption_dropout_rate": 0.0,
            "shuffle_tokens": False,
            "resolution": [512],
            "buckets": True,
            "cache_latents": False,
            "cache_latents_to_disk": True,
            "num_repeats": 1,
        }
    ]
    assert process["train"] == {
        "batch_size": 1,
        "steps": 500,
        "gradient_accumulation": 1,
        "train_unet": True,
        "train_text_encoder": False,
        "gradient_checkpointing": True,
        "noise_scheduler": "flowmatch",
        "timestep_type": "sigmoid",
        "content_or_style": "balanced",
        "optimizer": "adamw8bit",
        "optimizer_params": {"weight_decay": 1e-5},
        "lr": 1e-4,
        "lr_scheduler": "constant",
        "max_grad_norm": 1.0,
        "dtype": "bf16",
        "disable_sampling": True,
        "skip_first_sample": True,
        "cache_text_embeddings": True,
        "unload_text_encoder": True,
        "ema_config": {"use_ema": False},
    }
    assert process["model"] == {
        "name_or_path": str(tmp_path / "runtime" / "models" / contract.BASE_FILENAME),
        "arch": "flux2_klein_4b",
        "vae_path": str(tmp_path / "runtime" / "models" / contract.VAE_FILENAME),
        "quantize": True,
        "quantize_te": True,
        "qtype": "qfloat8",
        "qtype_te": "qfloat8",
        "low_vram": True,
    }
    assert process["save"] == {
        "dtype": "bf16",
        "save_format": "safetensors",
        "save_every": 100,
        "max_step_saves_to_keep": 1,
        "push_to_hub": False,
    }


def test_four_reference_manifest_and_consent_binding_pass(tmp_path):
    expected = _write_job(tmp_path)

    result = contract.validate_input_manifest(tmp_path, JOB_ID)

    assert result["manifest"] == expected
    assert result["sha256"] == hashlib.sha256(contract.canonical_json_bytes(expected)).hexdigest()
    candidate_sha = hashlib.sha256((PACKAGE / "candidate.json").read_bytes()).hexdigest()
    api = contract.validate_api_manifest(
        tmp_path,
        JOB_ID,
        input_result=result,
        candidate_sha256=candidate_sha,
    )
    assert api["contract"] == contract.CANARY_CONTRACT
    assert api["candidate_sha256"] == candidate_sha


def test_input_manifest_requires_exact_canonical_bytes(tmp_path):
    manifest = _write_job(tmp_path)
    path = tmp_path / "jobs" / JOB_ID / "input" / "job.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(contract.ContractError, match="not canonical"):
        contract.validate_input_manifest(tmp_path, JOB_ID)


def test_reference_must_fully_decode_as_png(tmp_path):
    manifest = _write_job(tmp_path)
    input_root = tmp_path / "jobs" / JOB_ID / "input"
    invalid = b"\x89PNG\r\n\x1a\n" + bytes(64)
    (input_root / "reference-01.png").write_bytes(invalid)
    manifest["references"][0]["image_bytes"] = len(invalid)
    manifest["references"][0]["image_sha256"] = hashlib.sha256(invalid).hexdigest()
    (input_root / "job.json").write_bytes(contract.canonical_json_bytes(manifest))

    with pytest.raises(contract.ContractError, match="fully decode"):
        contract.validate_input_manifest(tmp_path, JOB_ID)


def test_reference_pixel_count_matches_gateway_decode_bound():
    from PIL import Image

    output = io.BytesIO()
    Image.new("RGB", (5000, 5000), (1, 2, 3)).save(output, format="PNG")

    with pytest.raises(contract.ContractError, match="dimensions"):
        contract._png_dimensions(output.getvalue())


def test_api_manifest_must_bind_exact_image_hashes_and_captions(tmp_path):
    _write_job(tmp_path)
    input_result = contract.validate_input_manifest(tmp_path, JOB_ID)
    path = tmp_path / "jobs" / JOB_ID / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["references"][0]["caption"] = "hkkperson changed caption"
    path.write_bytes(contract.canonical_utf8_json_bytes(manifest))

    with pytest.raises(contract.ContractError, match="does not bind"):
        contract.validate_api_manifest(
            tmp_path,
            JOB_ID,
            input_result=input_result,
            candidate_sha256=hashlib.sha256((PACKAGE / "candidate.json").read_bytes()).hexdigest(),
        )


def test_api_manifest_rejects_an_alternate_valid_shape_job_id(tmp_path):
    _write_job(tmp_path)
    input_result = contract.validate_input_manifest(tmp_path, JOB_ID)
    alternate = "f" * 32
    shutil.copytree(
        tmp_path / "jobs" / JOB_ID,
        tmp_path / "jobs" / alternate,
    )

    with pytest.raises(contract.ContractError, match="job id is not derived"):
        contract.validate_api_manifest(
            tmp_path,
            alternate,
            input_result=input_result,
            candidate_sha256=hashlib.sha256(
                (PACKAGE / "candidate.json").read_bytes()
            ).hexdigest(),
        )


@pytest.mark.parametrize("failure", ["duplicate_image", "duplicate_caption", "bad_caption", "consent", "count"])
def test_bad_dataset_or_consent_fails_closed(tmp_path, failure):
    def mutate(manifest, input_root):
        if failure == "duplicate_image":
            duplicate = (input_root / "reference-01.png").read_bytes()
            (input_root / "reference-02.png").write_bytes(duplicate)
            manifest["references"][1]["image_bytes"] = len(duplicate)
            manifest["references"][1]["image_sha256"] = hashlib.sha256(duplicate).hexdigest()
        elif failure == "duplicate_caption":
            duplicate = (input_root / "reference-01.txt").read_bytes()
            (input_root / "reference-02.txt").write_bytes(duplicate)
            manifest["references"][1]["caption_bytes"] = len(duplicate)
            manifest["references"][1]["caption_sha256"] = hashlib.sha256(duplicate).hexdigest()
        elif failure == "bad_caption":
            bad = b"portrait without token"
            (input_root / "reference-01.txt").write_bytes(bad)
            manifest["references"][0]["caption_bytes"] = len(bad)
            manifest["references"][0]["caption_sha256"] = hashlib.sha256(bad).hexdigest()
        elif failure == "consent":
            manifest["consent"]["training_use_authorized"] = False
        else:
            manifest["references"].pop()

    _write_job(tmp_path, mutate=mutate)

    with pytest.raises(contract.ContractError):
        contract.validate_input_manifest(tmp_path, JOB_ID)


def test_reference_symlink_is_rejected(tmp_path):
    _write_job(tmp_path)
    input_root = tmp_path / "jobs" / JOB_ID / "input"
    source = input_root / "reference-01.png"
    moved = tmp_path / "owned.png"
    source.rename(moved)
    source.symlink_to(moved)

    with pytest.raises(contract.ContractError, match="non-regular"):
        contract.validate_input_manifest(tmp_path, JOB_ID)


@pytest.mark.parametrize("extra", ["extra.png", "extra.jpg", "nested"])
def test_unmanifested_training_input_is_rejected(tmp_path, extra):
    _write_job(tmp_path)
    input_root = tmp_path / "jobs" / JOB_ID / "input"
    path = input_root / extra
    if extra == "nested":
        path.mkdir()
        (path / "hidden.png").write_bytes(_png(9))
    else:
        path.write_bytes(_png(9))

    with pytest.raises(contract.ContractError, match="unmanifested"):
        contract.validate_input_manifest(tmp_path, JOB_ID)


def test_adapter_metadata_and_binary_are_strict_and_content_addressed(tmp_path):
    payload = _tiny_lora()
    metadata = _metadata(payload)
    adapter = tmp_path / metadata["adapter"]["filename"]
    adapter.write_bytes(payload)

    assert contract.validate_adapter_metadata(metadata) == metadata
    assert contract.validate_adapter_file(adapter, metadata, root=tmp_path) == {
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    assert contract.validate_lora_safetensors(adapter, root=tmp_path) == {
        "tensor_count": 160,
        "pair_count": 80,
        "tensor_inventory_sha256": _lora_inventory_sha256(),
    }

    drifted = copy.deepcopy(metadata)
    drifted["training"]["base_revision"] = "0" * 40
    with pytest.raises(contract.ContractError, match="does not match"):
        contract.validate_adapter_metadata(drifted)


def test_non_safetensors_adapter_is_rejected_even_when_hash_matches(tmp_path):
    payload = b"not a safetensors adapter"
    metadata = _metadata(payload)
    adapter = tmp_path / metadata["adapter"]["filename"]
    adapter.write_bytes(payload)

    with pytest.raises(contract.ContractError, match="safetensors"):
        contract.validate_adapter_file(adapter, metadata, root=tmp_path)


def test_partial_or_extra_namespace_lora_is_rejected(tmp_path):
    adapter = tmp_path / "partial.safetensors"
    adapter.write_bytes(_partial_lora())

    with pytest.raises(contract.ContractError, match="exact FLUX.2 Klein"):
        contract.validate_lora_safetensors(adapter, root=tmp_path)


def test_resume_checkpoint_requires_exact_same_job_step_and_metadata(tmp_path):
    checkpoint = tmp_path / f"identity_lora_{JOB_ID}_000000200.safetensors"
    checkpoint.write_bytes(_tiny_lora(step=200))

    result = contract.validate_resume_checkpoint(
        checkpoint, root=tmp_path, job_id=JOB_ID
    )

    assert result["step"] == 200
    assert result["filename"] == checkpoint.name
    wrong = tmp_path / f"identity_lora_{JOB_ID}_000000500.safetensors"
    wrong.write_bytes(_tiny_lora(step=500))
    with pytest.raises(contract.ContractError, match="continuation points"):
        contract.validate_resume_checkpoint(wrong, root=tmp_path, job_id=JOB_ID)


def test_adapter_and_checkpoint_each_use_one_file_snapshot(tmp_path, monkeypatch):
    payload = _tiny_lora()
    metadata = _metadata(payload)
    adapter = tmp_path / metadata["adapter"]["filename"]
    adapter.write_bytes(payload)
    checkpoint = tmp_path / f"identity_lora_{JOB_ID}_000000200.safetensors"
    checkpoint.write_bytes(_tiny_lora(step=200))

    real_open = contract.os.open
    opened: list[Path] = []

    def counted_open(path, flags, *args, **kwargs):
        opened.append(Path(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(contract.os, "open", counted_open)

    contract.validate_adapter_file(adapter, metadata, root=tmp_path)
    assert opened.count(adapter) == 1

    opened.clear()
    contract.validate_resume_checkpoint(checkpoint, root=tmp_path, job_id=JOB_ID)
    assert opened.count(checkpoint) == 1


def test_completed_toolkit_output_keeps_final_adapter_and_step_400_resume_state(
    tmp_path,
):
    paths = contract.job_paths(tmp_path, JOB_ID)
    save_root = paths["output"] / f"identity_lora_{JOB_ID}"
    save_root.mkdir(parents=True)
    final = save_root / f"identity_lora_{JOB_ID}.safetensors"
    final.write_bytes(_tiny_lora())
    (save_root / f"identity_lora_{JOB_ID}_000000400.safetensors").write_bytes(
        _tiny_lora(step=400)
    )
    (save_root / "optimizer.pt").write_bytes(bytes(1024))

    assert train._final_adapter(paths, JOB_ID) == final

    (save_root / f"identity_lora_{JOB_ID}_000000300.safetensors").write_bytes(
        _tiny_lora(step=300)
    )
    with pytest.raises(contract.ContractError, match="final adapter and exact"):
        train._final_adapter(paths, JOB_ID)


def test_resume_recovers_only_a_dead_hash_bound_same_job_lease(tmp_path):
    paths = contract.job_paths(tmp_path, JOB_ID)
    _record, lease_sha = train._acquire_lock(paths, JOB_ID)
    started = {"lease_sha256": lease_sha}

    train._recover_dead_lease(
        paths, JOB_ID, started, process_alive=lambda _pid: False
    )
    assert not paths["lock"].exists()

    _record, lease_sha = train._acquire_lock(paths, JOB_ID)
    with pytest.raises(contract.ContractError, match="still alive"):
        train._recover_dead_lease(
            paths,
            JOB_ID,
            {"lease_sha256": lease_sha},
            process_alive=lambda _pid: True,
        )
    assert paths["lock"].exists()


def test_initial_retry_reclaims_prestart_evidence_bound_to_old_activity_lease(
    tmp_path,
):
    _write_job(tmp_path)
    paths = contract.job_paths(tmp_path, JOB_ID)
    config_sha = contract.write_json_new(
        paths["config"],
        contract.build_training_config(tmp_path, JOB_ID),
        root=paths["root"],
    )
    old_activity_lease = "1" * 64
    new_activity_lease = "2" * 64
    admission = {
        "schema_version": 1,
        "job_id": JOB_ID,
        "input_manifest_sha256": "3" * 64,
        "config_sha256": config_sha,
        "package_sha256": "4" * 64,
        "contract": "flux2-klein-character-lora-canary-v1",
        "candidate_sha256": "4" * 64,
        "manifest_sha256": "5" * 64,
        "runtime_receipt_sha256": "6" * 64,
        "model_receipt_sha256": "7" * 64,
        "resource_preflight": {},
        "inference_runtime": {},
        "activity_lease_sha256": old_activity_lease,
    }
    admission_path = paths["evidence"] / "admission.json"
    contract.write_json_new(admission_path, admission, root=paths["root"])

    train._reset_unstarted_partial_evidence(
        paths,
        JOB_ID,
        activity_lease_sha256=new_activity_lease,
    )

    assert old_activity_lease != new_activity_lease
    assert not admission_path.exists()
    assert not paths["config"].exists()


def test_gateway_training_activity_lease_is_required_and_hash_bound(
    tmp_path, monkeypatch
):
    tmp_path.mkdir(exist_ok=True)
    paths = contract.job_paths(tmp_path, JOB_ID)
    lease = {
        "schema_version": 1,
        "capability": "identity-flux2-klein-lora",
        "activity": "training",
        "job_id": JOB_ID,
        "owner_pid": 1234,
        "nonce": "9" * 32,
    }
    lease_sha = contract.write_json_new(
        paths["activity_lock"], lease, root=paths["root"]
    )
    monkeypatch.delenv(contract.ACTIVITY_LEASE_ENV, raising=False)
    with pytest.raises(contract.ContractError, match="authority is absent"):
        contract.validate_gateway_training_activity_lease(paths, JOB_ID)
    monkeypatch.setenv(contract.ACTIVITY_LEASE_ENV, "0" * 64)
    with pytest.raises(contract.ContractError, match="binding failed"):
        contract.validate_gateway_training_activity_lease(paths, JOB_ID)
    monkeypatch.setenv(contract.ACTIVITY_LEASE_ENV, lease_sha)
    assert contract.validate_gateway_training_activity_lease(paths, JOB_ID) == lease_sha


def test_train_run_blocks_without_gateway_lease_before_runtime_or_toolkit(
    tmp_path, monkeypatch
):
    tmp_path.mkdir(exist_ok=True)
    called = []
    monkeypatch.setattr(train, "validate_package", lambda _root: {})
    monkeypatch.setattr(train, "windows_state_root", lambda: tmp_path)
    monkeypatch.setattr(
        train,
        "validate_inference_runtime",
        lambda: called.append("runtime"),
    )
    monkeypatch.setattr(
        train,
        "_run_toolkit",
        lambda *_args, **_kwargs: called.append("toolkit"),
    )
    monkeypatch.delenv(contract.ACTIVITY_LEASE_ENV, raising=False)

    with pytest.raises(contract.ContractError, match="authority is absent"):
        train.run(JOB_ID)
    assert called == []


def test_terminal_schema_binds_manifest_candidate_and_measured_attempt_fields():
    adapter_sha = "f" * 64
    adapter = {
        "filename": contract.adapter_filename(adapter_sha),
        "bytes": 123,
        "sha256": adapter_sha,
        "metadata_filename": f"{contract.adapter_filename(adapter_sha)}.json",
        "metadata_sha256": "2" * 64,
        "tensor_count": 160,
        "pair_count": 80,
        "tensor_inventory_sha256": _lora_inventory_sha256(),
    }
    record = train._terminal(
        job_id=JOB_ID,
        state="training_passed",
        attempt=2,
        blocker_code=None,
        return_code=0,
        elapsed_seconds=12.3456789,
        peak_vram_bytes=15_000_000_000,
        telemetry_complete=True,
        package_sha256="a" * 64,
        manifest_sha256="b" * 64,
        input_manifest_sha256="c" * 64,
        config_sha256="d" * 64,
        log_sha256="e" * 64,
        adapter=adapter,
        resume_checkpoint_sha256="1" * 64,
        inference_runtime_sha256=RUNTIME_SHA,
        activity_lease_sha256="7" * 64,
    )

    assert record == {
        "schema_version": 1,
        "capability": "identity-flux2-klein-lora",
        "job_id": JOB_ID,
        "state": "training_passed",
        "attempt": 2,
        "resumed": True,
        "blocker_code": None,
        "return_code": 0,
        "elapsed_seconds": 12.345679,
        "elapsed_scope": "current_process_attempt",
        "peak_vram_bytes": 15_000_000_000,
        "telemetry_complete": True,
        "contract": contract.CANARY_CONTRACT,
        "candidate_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "package_sha256": "a" * 64,
        "input_manifest_sha256": "c" * 64,
        "config_sha256": "d" * 64,
        "log_sha256": "e" * 64,
        "adapter": adapter,
        "resume_checkpoint_sha256": "1" * 64,
        "inference_runtime_sha256": RUNTIME_SHA,
        "activity_lease_sha256": "7" * 64,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("elapsed_seconds", 0),
        ("elapsed_seconds", False),
        ("peak_vram_bytes", 0),
        ("peak_vram_bytes", True),
    ],
)
def test_terminal_rejects_unmeasured_or_boolean_telemetry(field, value):
    record = _terminal_record()
    record[field] = value

    with pytest.raises(contract.ContractError, match="strictly positive"):
        train.validate_terminal_evidence(record)


def test_zero_reference_inference_graph_is_fixed_and_lora_is_after_unet():
    metadata = _metadata(_tiny_lora())
    graph = inference.build_inference_workflow(
        metadata=metadata, prompt="hkkperson standing in a studio"
    )

    assert graph["1"]["class_type"] == "UNETLoader"
    assert graph["2"] == {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {
            "model": ["1", 0],
            "lora_name": metadata["adapter"]["filename"],
            "strength_model": 1.0,
        },
    }
    assert graph["7"]["inputs"] == {"noise_seed": 0}
    assert graph["8"]["inputs"] == {"sampler_name": "euler"}
    assert graph["9"]["inputs"] == {"steps": 4, "width": 1024, "height": 1024}
    assert graph["10"]["inputs"] == {"width": 1024, "height": 1024, "batch_size": 1}
    assert graph["11"]["inputs"]["model"] == ["2", 0]
    assert graph["11"]["inputs"]["cfg"] == 1.0
    assert not {"LoadImage", "ReferenceLatent"} & {node["class_type"] for node in graph.values()}
    result = inference.validate_inference_workflow(
        graph, metadata, _object_info(metadata["adapter"]["filename"])
    )
    assert result == {
        "status": "static_inference_preflight_passed",
        "node_count": 14,
        "reference_count": 0,
        "execution_proven": False,
    }


def test_control_graph_changes_only_lora_attachment_and_output_prefix():
    metadata = _metadata(_tiny_lora())
    prompt = "hkkperson standing in a studio"
    control = inference.build_control_workflow(metadata=metadata, prompt=prompt)
    lora = inference.build_inference_workflow(metadata=metadata, prompt=prompt)

    assert "2" not in control
    assert control["11"]["inputs"]["model"] == ["1", 0]
    assert lora["11"]["inputs"]["model"] == ["2", 0]
    for node_id in ("5", "7", "8", "9", "10"):
        assert control[node_id] == lora[node_id]
    result = inference.validate_control_workflow(
        control, metadata, _object_info(metadata["adapter"]["filename"])
    )
    assert result == {
        "status": "static_control_preflight_passed",
        "node_count": 13,
        "reference_count": 0,
        "execution_proven": False,
    }


def test_inference_rejects_node_or_adapter_choice_drift():
    metadata = _metadata(_tiny_lora())
    graph = inference.build_inference_workflow(
        metadata=metadata, prompt="hkkperson standing in a studio"
    )
    graph["11"]["inputs"]["cfg"] = 1.1
    with pytest.raises(contract.ContractError, match="graph drifted"):
        inference.validate_inference_workflow(
            graph, metadata, _object_info(metadata["adapter"]["filename"])
        )
    clean = inference.build_inference_workflow(
        metadata=metadata, prompt="hkkperson standing in a studio"
    )
    with pytest.raises(contract.ContractError, match="rejects fixed"):
        inference.validate_inference_workflow(clean, metadata, _object_info("wrong.safetensors"))


def test_benchmark_runs_control_then_lora_and_binds_downloaded_outputs(
    tmp_path, monkeypatch, proven_inference_runtime
):
    metadata = _prepare_benchmark_job(tmp_path)
    paths = contract.job_paths(tmp_path, JOB_ID)
    benchmark_lease_sha = contract.write_json_new(
        paths["activity_lock"],
        {
            "schema_version": 1,
            "capability": contract.CAPABILITY,
            "activity": "benchmark",
            "job_id": JOB_ID,
            "owner_pid": 1234,
            "nonce": "a" * 32,
        },
        root=paths["root"],
    )
    monkeypatch.setenv(contract.ACTIVITY_LEASE_ENV, benchmark_lease_sha)
    submitted, api_json, api_bytes, clock = _benchmark_api(metadata)

    proof = benchmark.run_benchmark(
        tmp_path,
        JOB_ID,
        api_json=api_json,
        api_bytes=api_bytes,
        gpu_sample=lambda: 1024,
        clock=clock,
        sleeper=lambda _seconds: None,
    )

    assert proof["sequence"] == ["control", "lora"]
    assert [arm["arm"] for arm in proof["arms"]] == ["control", "lora"]
    assert proof["arms"][0]["output_sha256"] != proof["arms"][1]["output_sha256"]
    assert proof["arms"][0]["pixel_sha256"] != proof["arms"][1]["pixel_sha256"]
    assert proof["causality"] == {"pixel_hashes_differ": True}
    assert all(arm["latency_seconds"] > 0 for arm in proof["arms"])
    assert all(arm["peak_vram_bytes"] > 0 for arm in proof["arms"])
    assert "2" not in submitted[0]
    assert submitted[0]["11"]["inputs"]["model"] == ["1", 0]
    assert submitted[1]["11"]["inputs"]["model"] == ["2", 0]
    assert benchmark.validate_benchmark_proof(proof) == proof
    assert proof["runtime_contract_sha256"] == RUNTIME_SHA
    assert proof["benchmark_activity_lease_sha256"] == benchmark_lease_sha
    assert paths["activity_lock"].exists()
    for arm in proof["arms"]:
        output = tmp_path / "jobs" / JOB_ID / "benchmark" / arm["output_file"]
        assert hashlib.sha256(output.read_bytes()).hexdigest() == arm["output_sha256"]
    benchmark_root = tmp_path / "jobs" / JOB_ID / "benchmark"
    assert hashlib.sha256((benchmark_root / "object-info.json").read_bytes()).hexdigest() == proof["object_info_sha256"]
    assert hashlib.sha256((benchmark_root / "control-workflow.json").read_bytes()).hexdigest() == proof["arms"][0]["workflow_sha256"]
    assert hashlib.sha256((benchmark_root / "lora-workflow.json").read_bytes()).hexdigest() == proof["arms"][1]["workflow_sha256"]

    training = contract.validate_gateway_training_result(
        tmp_path,
        JOB_ID,
        expected_activity_lease_sha256="7" * 64,
    )
    assert training["state"] == "training_passed"
    assert training["retry_mode"] == "none"
    assert training["training"] == {
        "attempt": 1,
        "resumed": False,
        "elapsed_seconds": 12.5,
        "peak_vram_bytes": 15_000_000_000,
    }
    validated = contract.validate_gateway_benchmark_result(
        tmp_path,
        JOB_ID,
        expected_training_activity_lease_sha256="7" * 64,
        expected_benchmark_activity_lease_sha256=proof[
            "benchmark_activity_lease_sha256"
        ],
    )
    assert validated["state"] == "benchmark_passed"
    assert validated["retry_mode"] == "none"


def test_gateway_training_result_marks_clean_absence_as_initial_retry(
    tmp_path, proven_inference_runtime
):
    _write_job(tmp_path)

    result = contract.validate_gateway_training_result(
        tmp_path,
        JOB_ID,
        expected_activity_lease_sha256="7" * 64,
    )

    assert result["state"] == "not_started"
    assert result["blocker_code"] == "training_not_started"
    assert result["retry_mode"] == "initial"


@pytest.mark.parametrize(
    "checkpoint,second_attempt,expected_blocker,expected_retry",
    [
        (True, False, "training_interrupted", "checkpoint"),
        (False, False, "resume_not_available", "none"),
        (True, True, "resume_not_available", "none"),
    ],
)
def test_gateway_training_result_classifies_interrupted_attempts_exactly(
    tmp_path,
    proven_inference_runtime,
    checkpoint,
    second_attempt,
    expected_blocker,
    expected_retry,
):
    _prepare_interrupted_job(
        tmp_path, checkpoint=checkpoint, second_attempt=second_attempt
    )

    result = contract.validate_gateway_training_result(
        tmp_path,
        JOB_ID,
        expected_activity_lease_sha256="7" * 64,
    )

    assert result["state"] == "interrupted"
    assert result["blocker_code"] == expected_blocker
    assert result["retry_mode"] == expected_retry
    assert (result["checkpoint"] is not None) is checkpoint


@pytest.mark.parametrize(
    "terminal_state,expected_state,expected_blocker",
    [
        ("failed", "training_failed", "training_failed"),
        ("unknown", "training_unknown", "training_outcome_ambiguous"),
    ],
)
def test_gateway_training_result_preserves_terminal_failure_truth(
    tmp_path,
    proven_inference_runtime,
    terminal_state,
    expected_state,
    expected_blocker,
):
    _prepare_terminal_job(tmp_path, state=terminal_state)

    result = contract.validate_gateway_training_result(
        tmp_path,
        JOB_ID,
        expected_activity_lease_sha256="7" * 64,
    )

    assert result["state"] == expected_state
    assert result["blocker_code"] == expected_blocker
    assert result["retry_mode"] == "none"


def test_gateway_training_result_accepts_resumed_success_with_new_activity_lease(
    tmp_path, proven_inference_runtime
):
    _prepare_terminal_job(
        tmp_path,
        attempt=2,
        initial_activity_lease_sha256="1" * 64,
        current_activity_lease_sha256="7" * 64,
    )

    result = contract.validate_gateway_training_result(
        tmp_path,
        JOB_ID,
        expected_activity_lease_sha256="7" * 64,
    )

    assert result["state"] == "training_passed"
    assert result["retry_mode"] == "none"
    assert result["training"]["attempt"] == 2
    assert result["training"]["resumed"] is True


def test_gateway_benchmark_result_marks_clean_absence_as_one_benchmark_retry(
    tmp_path, proven_inference_runtime
):
    _prepare_benchmark_job(tmp_path)

    result = contract.validate_gateway_benchmark_result(
        tmp_path,
        JOB_ID,
        expected_training_activity_lease_sha256="7" * 64,
        expected_benchmark_activity_lease_sha256="4" * 64,
    )

    assert result["state"] == "benchmark_not_run"
    assert result["blocker_code"] == "benchmark_not_run"
    assert result["retry_mode"] == "benchmark"


def test_benchmark_identical_pixels_with_different_png_metadata_fail_causality(
    tmp_path, proven_inference_runtime
):
    metadata = _prepare_benchmark_job(tmp_path)
    _submitted, api_json, api_bytes, clock = _benchmark_api(
        metadata, identical_pixels=True
    )

    with pytest.raises(contract.ContractError, match="causality was not demonstrated"):
        benchmark.run_benchmark(
            tmp_path,
            JOB_ID,
            api_json=api_json,
            api_bytes=api_bytes,
            gpu_sample=lambda: 1024,
            clock=clock,
            sleeper=lambda _seconds: None,
        )

    evidence = tmp_path / "jobs" / JOB_ID / "evidence"
    failure = json.loads((evidence / "inference-benchmark-failed.json").read_text())
    assert failure["state"] == "failed"
    assert failure["blocker_code"] == "lora_causality_not_demonstrated"
    assert failure["control_output_sha256"] != failure["lora_output_sha256"]
    assert failure["control_pixel_sha256"] == failure["lora_pixel_sha256"]
    assert not (evidence / "inference-benchmark.json").exists()
    assert not contract.job_paths(tmp_path, JOB_ID)["activity_lock"].exists()
    result = contract.validate_gateway_benchmark_result(
        tmp_path,
        JOB_ID,
        expected_training_activity_lease_sha256="7" * 64,
        expected_benchmark_activity_lease_sha256=failure[
            "benchmark_activity_lease_sha256"
        ],
    )
    assert result["state"] == "benchmark_failed"
    assert result["blocker_code"] == "lora_causality_not_demonstrated"
    assert result["retry_mode"] == "none"


def test_benchmark_activity_lease_excludes_gateway_training_or_prompt(
    tmp_path, proven_inference_runtime
):
    metadata = _prepare_benchmark_job(tmp_path)
    _submitted, api_json, api_bytes, clock = _benchmark_api(metadata)
    paths = contract.job_paths(tmp_path, JOB_ID)
    foreign = {
        "schema_version": 1,
        "capability": "identity-flux2-klein-lora",
        "activity": "prompt",
        "job_id": "f" * 32,
        "owner_pid": 999,
        "nonce": "9" * 32,
    }
    contract.write_json_new(paths["activity_lock"], foreign, root=paths["root"])

    with pytest.raises(contract.ContractError, match="refusing to overwrite"):
        benchmark.run_benchmark(
            tmp_path,
            JOB_ID,
            api_json=api_json,
            api_bytes=api_bytes,
            gpu_sample=lambda: 1024,
            clock=clock,
            sleeper=lambda _seconds: None,
        )

    assert json.loads(paths["activity_lock"].read_text()) == foreign


def test_ambiguous_benchmark_retains_owned_activity_lease(
    tmp_path, proven_inference_runtime
):
    metadata = _prepare_benchmark_job(tmp_path)
    _submitted, normal_api, api_bytes, clock = _benchmark_api(metadata)

    def ambiguous_api(method, path, payload=None):
        if method == "POST" and path == "/prompt":
            raise OSError("connection lost after send")
        return normal_api(method, path, payload)

    with pytest.raises(contract.ContractError, match="outcome is unknown"):
        benchmark.run_benchmark(
            tmp_path,
            JOB_ID,
            api_json=ambiguous_api,
            api_bytes=api_bytes,
            gpu_sample=lambda: 1024,
            clock=clock,
            sleeper=lambda _seconds: None,
        )

    paths = contract.job_paths(tmp_path, JOB_ID)
    lease = json.loads(paths["activity_lock"].read_text())
    assert lease["activity"] == "benchmark"
    assert lease["job_id"] == JOB_ID
    unknown_path = paths["evidence"] / "inference-benchmark-unknown.json"
    assert unknown_path.is_file()
    unknown = json.loads(unknown_path.read_text())
    result = contract.validate_gateway_benchmark_result(
        tmp_path,
        JOB_ID,
        expected_training_activity_lease_sha256="7" * 64,
        expected_benchmark_activity_lease_sha256=unknown[
            "benchmark_activity_lease_sha256"
        ],
    )
    assert result["state"] == "benchmark_unknown"
    assert result["blocker_code"] == "inference_benchmark_outcome_unknown"
    assert result["retry_mode"] == "none"


def test_pre_submission_schema_drift_releases_benchmark_lease(
    tmp_path, proven_inference_runtime
):
    metadata = _prepare_benchmark_job(tmp_path)
    submitted, normal_api, api_bytes, clock = _benchmark_api(metadata)
    object_info_calls = [0]

    def drifting_api(method, path, payload=None):
        if method == "GET" and path == "/object_info":
            object_info_calls[0] += 1
            value = normal_api(method, path, payload)
            if object_info_calls[0] == 2:
                value = copy.deepcopy(value)
                value["UNETLoader"]["input"]["required"]["unet_name"] = [["drift"]]
            return value
        return normal_api(method, path, payload)

    with pytest.raises(contract.ContractError, match="schema changed"):
        benchmark.run_benchmark(
            tmp_path,
            JOB_ID,
            api_json=drifting_api,
            api_bytes=api_bytes,
            gpu_sample=lambda: 1024,
            clock=clock,
            sleeper=lambda _seconds: None,
        )

    paths = contract.job_paths(tmp_path, JOB_ID)
    assert submitted == []
    assert not paths["activity_lock"].exists()
    assert not (paths["evidence"] / "inference-benchmark-unknown.json").exists()
    assert not (paths["evidence"] / "inference-benchmark-attempt.json").exists()
    assert not (paths["job"] / "benchmark").exists()


def test_benchmark_requires_an_idle_queue():
    with pytest.raises(contract.ContractError, match="must be idle"):
        benchmark._require_idle({"queue_running": [[1]], "queue_pending": []})


@pytest.mark.parametrize(
    "field,value",
    [
        ("ram_bytes", 34_359_738_367),
        ("free_disk_bytes", 42_949_672_959),
        ("cuda_available", False),
        ("gpu_name", "NVIDIA GeForce RTX 4090"),
        ("vram_mib", 14_999),
        ("free_vram_mib", 13_499),
        ("gpu_utilization_percent", 6),
        ("packages_sha256", "bad"),
    ],
)
def test_resource_gates_fail_closed(field, value):
    snapshot = _resource()
    snapshot[field] = value

    with pytest.raises(contract.ContractError):
        contract.validate_resource_snapshot(snapshot)


def test_fully_free_vram_is_valid_but_free_above_total_is_not():
    snapshot = _resource()
    snapshot["free_vram_mib"] = snapshot["vram_mib"]
    contract.validate_resource_snapshot(snapshot)

    snapshot["free_vram_mib"] += 1
    with pytest.raises(contract.ContractError, match="telemetry is contradictory"):
        contract.validate_resource_snapshot(snapshot)


def test_resource_contract_and_offline_child_environment_pass(tmp_path):
    snapshot = _resource()
    contract.validate_resource_snapshot(snapshot)
    paths = contract.job_paths(tmp_path, JOB_ID)

    assert contract.toolkit_command(paths) == [
        str(tmp_path / "runtime" / "venv" / "Scripts" / "python.exe"),
        str(tmp_path / "runtime" / "ai-toolkit" / "run.py"),
        str(tmp_path / "jobs" / JOB_ID / "work" / "train.yaml"),
    ]
    environment = contract.fixed_child_environment(paths)
    assert environment["SEED"] == "0"
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert environment["HF_DATASETS_OFFLINE"] == "1"
    assert environment["WANDB_MODE"] == "disabled"
    assert "http" not in " ".join(contract.toolkit_command(paths)).lower()


def test_installer_resource_preflight_runs_inside_the_fixed_venv(
    tmp_path, monkeypatch
):
    state_root = tmp_path / "state"
    package_root = state_root / "package"
    python = state_root / "runtime" / "venv" / "Scripts" / "python.exe"
    package_root.mkdir(parents=True)
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    snapshot = _resource()
    seen = {}

    class Result:
        returncode = 0
        stdout = json.dumps(snapshot)
        stderr = ""

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(installer.subprocess, "run", fake_run)

    assert installer._collect_fixed_venv_resource_snapshot(
        python, state_root, package_root
    ) == snapshot
    assert seen["command"][0] == str(python)
    assert seen["command"][1:4] == ["-I", "-B", "-c"]
    assert seen["command"][-2:] == [
        str(package_root.resolve()),
        str(state_root.resolve()),
    ]


def test_atomic_evidence_refuses_overwrite(tmp_path):
    path = tmp_path / "evidence" / "record.json"
    first = {"state": "started"}
    assert contract.write_json_new(path, first) == hashlib.sha256(
        contract.canonical_json_bytes(first)
    ).hexdigest()

    with pytest.raises(contract.ContractError, match="overwrite"):
        contract.write_json_new(path, {"state": "different"})
    assert json.loads(path.read_text()) == first


def test_toolkit_log_tail_read_is_bounded(tmp_path):
    path = tmp_path / "toolkit.log"
    path.write_bytes(b"a" * 1_000_000 + b"terminal-marker")

    tail = contract.regular_file_tail(path, root=tmp_path, maximum_bytes=1024)

    assert len(tail) == 1024
    assert tail.endswith(b"terminal-marker")


@pytest.mark.parametrize(
    "message,expected",
    [
        ("CUDA out of memory", "training_oom"),
        ("torch.OutOfMemoryError: allocation", "training_oom"),
        ("unexpected trainer exit", "training_failed"),
    ],
)
def test_training_failure_classification_is_bounded(message, expected):
    assert contract.classify_failure(1, message) == expected
