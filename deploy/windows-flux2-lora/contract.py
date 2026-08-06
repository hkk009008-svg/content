"""Fail-closed contract for the isolated FLUX.2 Klein character-LoRA canary."""

from __future__ import annotations

import hashlib
import copy
import io
import json
import math
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import ctypes
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CAPABILITY = "identity-flux2-klein-lora"
TRIGGER_TOKEN = "hkkperson"
CANARY_CONTRACT = "flux2-klein-character-lora-canary-v1"
BENCHMARK_CONTRACT = "flux2-klein-character-lora-inference-benchmark-v1"
BENCHMARK_PROMPT = (
    "hkkperson cinematic studio portrait, neutral expression, soft key light, "
    "plain charcoal background, photorealistic"
)
TOOLKIT_COMMIT = "1e1418b22cf4373ec2b90b64ea3b343b031175ff"
BASE_REPOSITORY = "black-forest-labs/FLUX.2-klein-base-4B"
BASE_REVISION = "a3b4f4849157f664bdbc776fd7453c2783562f4d"
BASE_FILENAME = "flux-2-klein-base-4b.safetensors"
BASE_BYTES = 7_751_105_712
BASE_SHA256 = "9c5fed22b76baea749d88fc2abe3ad53245e7b21a0d353a762665eea00043b92"
VAE_REPOSITORY = "ai-toolkit/flux2_vae"
VAE_REVISION = "3f679cf232e6d91d28396522d9502c31e8f7ccbe"
VAE_FILENAME = "ae.safetensors"
VAE_BYTES = 336_211_292
VAE_SHA256 = "868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3"
DISTILLED_FILENAME = "flux-2-klein-4b-fp8.safetensors"
DISTILLED_REVISION = "5b4408e59397a4a37ccb46afe426d8ed86379441"
DISTILLED_BYTES = 4_070_624_520
DISTILLED_SHA256 = "97ed34fe0567e436200f2faee3939b88f2b5d99f8af2a4dc16532c4245c0ccb6"
TEXT_ENCODER_FILENAME = "qwen_3_4b.safetensors"
INFERENCE_VAE_FILENAME = "flux2-klein-vae-bf16.safetensors"
INFERENCE_VAE_BYTES = 168_120_878
INFERENCE_VAE_SHA256 = "ca70d2202afe6415bdbcb8793ba8cd99fd159cfe6192381504d6c4d3036e0f04"
REPOSITORY_INFERENCE_PACKAGE_ROOT = ROOT.parent / "windows-flux2-klein"
INFERENCE_PACKAGE_BINDINGS = {
    "candidate.json": "02f2cc195cf2537c220ae385ef012d038ff46d4f39f2b007280bb7ef2fdf95f7",
    "models.json": "f35145f0fdc8d35a810b6905ccfc9358baa18d86c3abdfac23b373fd7e95018f",
    "runtime.py": "17c81a8128ec6ee897f9ea98dd6fe38f6209332cb38390d65dc6c6d053c5d01d",
    "workflow.py": "f05cd319099ea0c07be6bf6bb8953cea345af154b4b23a86f08c06e180c30148",
}
EXPECTED_PACKAGE_FILES = frozenset(
    {
        "Install-Candidate.ps1",
        "README.md",
        "Benchmark-Candidate.ps1",
        "benchmark.py",
        "candidate.json",
        "contract.py",
        "inference.py",
        "install.py",
        "preflight.py",
        "requirements.in",
        "requirements.lock",
        "train.py",
    }
)
REFERENCE_NAMES = tuple(f"reference-{index:02d}" for index in range(1, 5))
FIXED_CAPTIONS = tuple(
    f"portrait photograph of hkkperson person, identity reference view {index}"
    for index in range(1, 5)
)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
JOB_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
PROMPT_ID_RE = re.compile(r"[0-9a-f-]{32,36}\Z")
TOKEN_RE = re.compile(r"[a-z][a-z0-9]{5,31}\Z")
ADAPTER_RE = re.compile(r"identity-lora-([0-9a-f]{64})\.safetensors\Z")
QWEN_REVISION = "1cfa9a7208912126459214e8b04321603b3df60c"
QWEN_REQUIRED_FILES = frozenset(
    {
        "config.json",
        "generation_config.json",
        "merges.txt",
        "model-00001-of-00003.safetensors",
        "model-00002-of-00003.safetensors",
        "model-00003-of-00003.safetensors",
        "model.safetensors.index.json",
        "tokenizer_config.json",
        "vocab.json",
    }
)
QWEN_FILE_RECORDS = {
    "config.json": (
        726,
        "8ba006f74fecfaaeb392872a60f4a480e7ec9860153d2e1b769ec81f9a147f8a",
    ),
    "generation_config.json": (
        239,
        "2325da0f15bb848e018c5ae071b7943332e9f871d6b60e2ed22ca97d4cb993d2",
    ),
    "merges.txt": (
        1_671_853,
        "8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5",
    ),
    "model-00001-of-00003.safetensors": (
        3_957_900_840,
        "328a91d3122359d5547f9d79521205bc0a46e1f79a792dfe650e99fc2d651223",
    ),
    "model-00002-of-00003.safetensors": (
        3_987_450_520,
        "6cd087b316306a68c562436b5492edbcf6e16c6dba3a1308279caa5a58e21ca5",
    ),
    "model-00003-of-00003.safetensors": (
        99_630_640,
        "e4bf436957184f4eeb86a80e9db394503f1f56446b2e6b7edeac5b81470f4ca1",
    ),
    "model.safetensors.index.json": (
        32_819,
        "6dc0981b8829fead746441f68f38f24c5ca4a3a66351f652c26c6df0efc43ab2",
    ),
    "tokenizer_config.json": (
        9_732,
        "d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101",
    ),
    "vocab.json": (
        2_776_833,
        "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910",
    ),
}
QWEN_TREE_SHA256 = "d4dbd58159f555388d7d382f84afd079cc0f3a0c3d3d30a6a209fc5f66d21ef0"
ACTIVITY_LEASE_ENV = "CONTENT_LORA_ACTIVITY_LEASE_SHA256"
MAX_IMAGE_PIXELS = 20_000_000
TORCH_VERSION = "2.13.0+cu130"
TORCHVISION_VERSION = "0.28.0+cu130"
TORCHAUDIO_VERSION = "2.11.0+cu130"
CUDA_VERSION = "13.0"
DIRECT_RUNTIME_IMPORTS = {
    "setuptools": "setuptools",
    "pip": "pip",
    "wheel": "wheel",
    "torch": "torch",
    "torchvision": "torchvision",
    "torchaudio": "torchaudio",
    "torchao": "torchao",
    "safetensors": "safetensors",
    "diffusers": "diffusers",
    "transformers": "transformers",
    "lycoris-lora": "lycoris",
    "flatten-json": "flatten_json",
    "pyyaml": "yaml",
    "oyaml": "oyaml",
    "tensorboard": "tensorboard",
    "kornia": "kornia",
    "invisible-watermark": "imwatermark",
    "einops": "einops",
    "accelerate": "accelerate",
    "toml": "toml",
    "albumentations": "albumentations",
    "albucore": "albucore",
    "pydantic": "pydantic",
    "omegaconf": "omegaconf",
    "open-clip-torch": "open_clip",
    "timm": "timm",
    "prodigyopt": "prodigyopt",
    "controlnet-aux": "controlnet_aux",
    "python-dotenv": "dotenv",
    "bitsandbytes": "bitsandbytes",
    "hf-transfer": "hf_transfer",
    "lpips": "lpips",
    "pytorch-fid": "pytorch_fid",
    "optimum-quanto": "optimum.quanto",
    "sentencepiece": "sentencepiece",
    "huggingface-hub": "huggingface_hub",
    "peft": "peft",
    "gradio": "gradio",
    "python-slugify": "slugify",
    "opencv-python": "cv2",
    "pytorch-wavelets": "pytorch_wavelets",
    "matplotlib": "matplotlib",
    "av": "av",
    "torchcodec": "torchcodec",
    "librosa": "librosa",
    "mutagen": "mutagen",
    "scipy": "scipy",
    "pillow": "PIL",
}


class ContractError(RuntimeError):
    """Candidate input, environment, output, or evidence is not trustworthy."""


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def canonical_utf8_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _regular_file_identity(path: Path, *, root: Path | None = None) -> os.stat_result:
    if root is not None:
        try:
            root_info = root.lstat()
            relative = path.relative_to(root)
        except (OSError, ValueError) as exc:
            raise ContractError(f"required file is outside its owned root: {path.name}") from exc
        if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
            raise ContractError("owned root is not a real directory")
        cursor = root
        for part in relative.parts[:-1]:
            cursor = cursor / part
            try:
                parent_info = cursor.lstat()
            except OSError as exc:
                raise ContractError(f"required parent is unavailable: {cursor.name}") from exc
            if stat.S_ISLNK(parent_info.st_mode) or not stat.S_ISDIR(parent_info.st_mode):
                raise ContractError(f"required parent is not a real directory: {cursor.name}")
    try:
        before = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"required regular file is unavailable: {path.name}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ContractError(f"required path is not a regular file: {path.name}")
    if root is not None:
        try:
            resolved.relative_to(root.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise ContractError(f"required file escapes its owned root: {path.name}") from exc
    return before


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        stat.S_ISREG(right.st_mode)
        and not stat.S_ISLNK(right.st_mode)
        and left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
    )


def _regular_bytes(
    path: Path, *, root: Path | None = None, maximum_bytes: int = 32 * 1024 * 1024
) -> bytes:
    before = _regular_file_identity(path, root=root)
    if before.st_size > maximum_bytes:
        raise ContractError(f"required file exceeds its fixed read bound: {path.name}")
    try:
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise ContractError(f"required file changed while reading: {path.name}") from exc
    if (
        not _same_file_identity(before, after)
        or len(payload) != before.st_size
    ):
        raise ContractError(f"required file changed while reading: {path.name}")
    return payload


def file_record(path: Path, *, root: Path | None = None) -> dict[str, object]:
    before = _regular_file_identity(path, root=root)
    digest = hashlib.sha256()
    total = 0
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not _same_file_identity(before, opened):
                raise ContractError(f"required file changed while opening: {path.name}")
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
                total += len(chunk)
            finished = os.fstat(handle.fileno())
    except ContractError:
        raise
    except OSError as exc:
        raise ContractError(f"required file changed while reading: {path.name}") from exc
    try:
        after = path.lstat()
    except OSError as exc:
        raise ContractError(f"required file changed while reading: {path.name}") from exc
    if (
        not _same_file_identity(before, finished)
        or not _same_file_identity(before, after)
        or total != before.st_size
    ):
        raise ContractError(f"required file changed while reading: {path.name}")
    return {"bytes": total, "sha256": digest.hexdigest()}


def regular_file_tail(
    path: Path, *, root: Path | None = None, maximum_bytes: int = 262_144
) -> bytes:
    if type(maximum_bytes) is not int or maximum_bytes <= 0:
        raise ContractError("file-tail byte bound is invalid")
    before = _regular_file_identity(path, root=root)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not _same_file_identity(before, opened):
                raise ContractError(f"required file changed while opening: {path.name}")
            handle.seek(max(0, before.st_size - maximum_bytes))
            payload = handle.read(maximum_bytes)
            finished = os.fstat(handle.fileno())
    except ContractError:
        raise
    except OSError as exc:
        raise ContractError(f"required file changed while reading: {path.name}") from exc
    try:
        after = path.lstat()
    except OSError as exc:
        raise ContractError(f"required file changed while reading: {path.name}") from exc
    if (
        not _same_file_identity(before, finished)
        or not _same_file_identity(before, after)
        or len(payload) > maximum_bytes
    ):
        raise ContractError(f"required file changed while reading: {path.name}")
    return payload


def _json_object(path: Path, *, root: Path | None = None) -> Mapping[str, Any]:
    try:
        payload = json.loads(
            _regular_bytes(path, root=root), object_pairs_hook=_reject_duplicate_json
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid JSON object: {path.name}") from exc
    if not isinstance(payload, Mapping):
        raise ContractError(f"JSON value is not an object: {path.name}")
    return payload


def read_json_object(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    return dict(_json_object(path, root=root))


def validate_package(root: Path = ROOT) -> Mapping[str, Any]:
    root = root.resolve(strict=True)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if actual != EXPECTED_PACKAGE_FILES:
        raise ContractError("candidate package file inventory drifted")
    candidate = _json_object(root / "candidate.json", root=root)
    if set(candidate) != {
        "schema_version",
        "capability",
        "candidate_state",
        "readiness",
        "storage",
        "training",
        "resources",
        "upstreams",
        "inference",
        "bindings",
    }:
        raise ContractError("candidate manifest fields drifted")
    if (
        candidate.get("schema_version") != 1
        or candidate.get("capability") != "identity-flux2-klein-lora"
        or candidate.get("candidate_state") != "not_installed"
    ):
        raise ContractError("candidate identity or state drifted")
    if candidate.get("readiness") != {
        "state": "not_installed",
        "startup_ready": False,
        "execution_proven": False,
        "training_canary": "not_run",
        "inference_canary": "not_run",
        "blocker_code": "candidate_runtime_not_installed",
    }:
        raise ContractError("candidate readiness is not fail-closed")
    if candidate.get("storage") != {
        "root": "%PROGRAMDATA%/Content/IdentityLab/flux2-lora",
        "package": "package",
        "accepted_input": "jobs/<32-lowercase-hex-job-id>/input",
        "runtime": "runtime",
        "evidence": "jobs/<32-lowercase-hex-job-id>/evidence",
    }:
        raise ContractError("candidate storage contract drifted")
    expected_training = {
        "reference_count": 4,
        "caption_count": 4,
        "trigger_token": TRIGGER_TOKEN,
        "resolution": [512],
        "buckets": True,
        "batch_size": 1,
        "rank": 16,
        "alpha": 16,
        "dtype": "bf16",
        "quantize": True,
        "quantize_te": True,
        "low_vram": True,
        "gradient_checkpointing": True,
        "cache_latents_to_disk": True,
        "optimizer": "adamw8bit",
        "seed": 0,
        "steps": 500,
    }
    if candidate.get("training") != expected_training:
        raise ContractError("training contract drifted")
    if candidate.get("resources") != {
        "operating_system": "Windows",
        "architecture": "AMD64",
        "python": "3.12",
        "gpu_name_contains": "RTX 5070 Ti",
        "minimum_ram_bytes": 34_359_738_368,
        "minimum_free_disk_bytes": 42_949_672_960,
        "minimum_vram_mib": 15_000,
        "minimum_free_vram_mib": 13_500,
        "maximum_gpu_utilization_percent": 5,
    }:
        raise ContractError("candidate resource contract drifted")
    upstreams = candidate.get("upstreams")
    if not isinstance(upstreams, Mapping) or set(upstreams) != {
        "ai_toolkit",
        "training_base",
        "training_vae",
        "inference_base",
        "qwen",
    }:
        raise ContractError("upstream manifest is missing")
    toolkit = upstreams.get("ai_toolkit")
    base = upstreams.get("training_base")
    if not isinstance(toolkit, Mapping) or not isinstance(base, Mapping):
        raise ContractError("pinned toolkit or training base is missing")
    if toolkit != {
        "repository": "https://github.com/ostris/ai-toolkit.git",
        "commit": TOOLKIT_COMMIT,
        "launcher": "run.py",
        "requirements_lock_sha256": file_record(
            root / "requirements.lock", root=root
        )["sha256"],
        "license": "MIT",
    }:
        raise ContractError("AI Toolkit pin drifted")
    if base != {
        "repository": BASE_REPOSITORY,
        "revision": BASE_REVISION,
        "transformer": BASE_FILENAME,
        "expected_bytes": BASE_BYTES,
        "sha256": BASE_SHA256,
        "license": "Apache-2.0",
    }:
        raise ContractError("training base pin drifted")
    vae = upstreams.get("training_vae")
    qwen = upstreams.get("qwen")
    if vae != {
        "repository": VAE_REPOSITORY,
        "revision": VAE_REVISION,
        "file": VAE_FILENAME,
        "expected_bytes": VAE_BYTES,
        "sha256": VAE_SHA256,
    }:
        raise ContractError("training VAE pin drifted")
    if qwen != {
        "repository": "Qwen/Qwen3-4B",
        "revision": QWEN_REVISION,
        "tree_sha256": QWEN_TREE_SHA256,
        "files": [
            {"path": relative, "expected_bytes": QWEN_FILE_RECORDS[relative][0], "sha256": QWEN_FILE_RECORDS[relative][1]}
            for relative in sorted(QWEN_REQUIRED_FILES)
        ],
    }:
        raise ContractError("Qwen offline-cache pin drifted")
    if upstreams.get("inference_base") != {
        "repository": "black-forest-labs/FLUX.2-klein-4b-fp8",
        "revision": DISTILLED_REVISION,
        "file": DISTILLED_FILENAME,
        "expected_bytes": DISTILLED_BYTES,
        "sha256": DISTILLED_SHA256,
        "license": "Apache-2.0",
    }:
        raise ContractError("distilled inference-base pin drifted")
    if candidate.get("inference") != {
        "node": "LoraLoaderModelOnly",
        "reference_count": 0,
        "seed": 0,
        "steps": 4,
        "sampler": "euler",
        "cfg": 1.0,
        "width": 1024,
        "height": 1024,
        "strength_model": 1.0,
    }:
        raise ContractError("candidate inference contract drifted")
    bindings = candidate.get("bindings")
    if not isinstance(bindings, Mapping) or set(bindings) != EXPECTED_PACKAGE_FILES - {
        "candidate.json"
    }:
        raise ContractError("candidate file bindings are incomplete")
    for relative, expected in bindings.items():
        if not isinstance(expected, str) or not HEX64.fullmatch(expected):
            raise ContractError("candidate file binding is malformed")
        if file_record(root / relative, root=root)["sha256"] != expected:
            raise ContractError(f"candidate file hash drifted: {relative}")
    return candidate


def canonical_job_id(value: object) -> str:
    if not isinstance(value, str) or not JOB_ID_RE.fullmatch(value):
        raise ContractError("job id must be exactly 32 lowercase hexadecimal characters")
    return value


def windows_state_root() -> Path:
    if os.name != "nt" or platform.system() != "Windows":
        raise ContractError("the training entrypoint is Windows-only")
    program_data = os.environ.get("PROGRAMDATA")
    if not program_data:
        raise ContractError("PROGRAMDATA is unavailable")
    base = Path(program_data)
    if not base.is_absolute():
        raise ContractError("PROGRAMDATA is not an absolute path")
    return base / "Content" / "IdentityLab" / "flux2-lora"


def inference_state_root() -> Path:
    if os.name != "nt" or platform.system() != "Windows":
        raise ContractError("the inference runtime is Windows-only")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data or not Path(local_app_data).is_absolute():
        raise ContractError("LOCALAPPDATA is unavailable or not absolute")
    return Path(local_app_data) / "ContentFlux2Klein"


def validate_inference_runtime() -> dict[str, str]:
    """Bind LoRA use to the separately proven, ready FLUX.2 runtime."""

    package_root = (
        ROOT.parent / "inference-package"
        if ROOT.name == "package" and ROOT.parent.name == "flux2-lora"
        else REPOSITORY_INFERENCE_PACKAGE_ROOT
    ).resolve(strict=True)
    for relative, expected_sha256 in INFERENCE_PACKAGE_BINDINGS.items():
        if file_record(package_root / relative, root=package_root)["sha256"] != expected_sha256:
            raise ContractError(f"pinned inference package drifted: {relative}")
    runtime_path = package_root / "runtime.py"
    namespace: dict[str, Any] = {
        "__name__": "content_bound_flux2_klein_runtime",
        "__file__": str(runtime_path),
    }
    try:
        exec(compile(_regular_bytes(runtime_path, root=package_root), str(runtime_path), "exec"), namespace)
        loader = namespace.get("load_runtime_status")
        if not callable(loader):
            raise ContractError("pinned inference runtime loader is missing")
        state_root = inference_state_root()
        status = loader(state_root, package_root=package_root, verify_evidence=True)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError("pinned inference runtime is not proven ready") from exc
    runtime_sha = status.get("runtime_contract_sha256") if isinstance(status, Mapping) else None
    if (
        not isinstance(status, Mapping)
        or status.get("state") != "ready"
        or status.get("startup_ready") is not True
        or status.get("execution_proven") is not True
        or status.get("benchmark_state") != "passed"
        or not isinstance(runtime_sha, str)
        or not HEX64.fullmatch(runtime_sha)
    ):
        raise ContractError("pinned inference runtime is not proven ready")
    return {
        "runtime_contract_sha256": runtime_sha,
        "status_sha256": str(file_record(state_root / "status.json", root=state_root)["sha256"]),
        "package_candidate_sha256": INFERENCE_PACKAGE_BINDINGS["candidate.json"],
    }


def job_paths(state_root: Path, job_id: object) -> dict[str, Path]:
    canonical = canonical_job_id(job_id)
    root = state_root.resolve()
    job = root / "jobs" / canonical
    return {
        "root": root,
        "job": job,
        "input": job / "input",
        "manifest": job / "input" / "job.json",
        "api_manifest": job / "manifest.json",
        "config": job / "work" / "train.yaml",
        "output": job / "output",
        "adapter": job / "adapter",
        "evidence": job / "evidence",
        "runtime": root / "runtime",
        "toolkit": root / "runtime" / "ai-toolkit",
        "python": root / "runtime" / "venv" / "Scripts" / "python.exe",
        "models": root / "runtime" / "models",
        "hf_home": root / "runtime" / "hf-home",
        "runtime_receipt": root / "runtime" / "runtime-receipt.json",
        "model_receipt": root / "runtime" / "model-receipt.json",
        "lock": root / "locks" / "gpu-training.lock",
        "activity_lock": root / "locks" / "gateway-activity.lock",
    }


def validate_gateway_activity_lease(
    paths: Mapping[str, Path], job_id: str, *, activity: str
) -> str:
    if activity not in {"training", "benchmark"}:
        raise ContractError("gateway activity kind is invalid")
    expected_sha256 = os.environ.get(ACTIVITY_LEASE_ENV)
    if not isinstance(expected_sha256, str) or not HEX64.fullmatch(expected_sha256):
        raise ContractError("gateway activity authority is absent")
    lease = _json_object(paths["activity_lock"], root=paths["root"])
    if set(lease) != {
        "schema_version",
        "capability",
        "activity",
        "job_id",
        "owner_pid",
        "nonce",
    } or lease != {
        **lease,
        "schema_version": 1,
        "capability": CAPABILITY,
        "activity": activity,
        "job_id": canonical_job_id(job_id),
    }:
        raise ContractError("gateway activity lease is malformed")
    if (
        type(lease.get("owner_pid")) is not int
        or lease["owner_pid"] <= 0
        or not isinstance(lease.get("nonce"), str)
        or not re.fullmatch(r"[0-9a-f]{32}", lease["nonce"])
        or file_record(paths["activity_lock"], root=paths["root"])["sha256"]
        != expected_sha256
    ):
        raise ContractError("gateway activity lease binding failed")
    return expected_sha256


def validate_gateway_training_activity_lease(
    paths: Mapping[str, Path], job_id: str
) -> str:
    return validate_gateway_activity_lease(paths, job_id, activity="training")


def _png_dimensions(payload: bytes) -> tuple[int, int]:
    if not 1 <= len(payload) <= 20 * 1024 * 1024:
        raise ContractError("training reference byte size is outside the fixed bounds")
    try:
        from PIL import Image

        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            width, height = image.size
            if image.format != "PNG" or image.mode not in {"RGB", "RGBA"}:
                raise ContractError("each training reference must be an RGB/RGBA PNG")
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError("each training reference must fully decode as PNG") from exc
    if (
        not 256 <= width <= 8192
        or not 256 <= height <= 8192
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise ContractError("training reference dimensions are outside the fixed bounds")
    return width, height


def benchmark_png_pixel_sha256(payload: bytes) -> str:
    if not 1 <= len(payload) <= 50 * 1024 * 1024:
        raise ContractError("benchmark output byte size is outside the fixed bounds")
    try:
        from PIL import Image

        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
        with Image.open(io.BytesIO(payload)) as image:
            if image.format != "PNG" or image.size != (1024, 1024):
                raise ContractError("benchmark output is not a 1024x1024 PNG")
            image.load()
            pixels = image.convert("RGB").tobytes()
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError("benchmark output cannot be fully decoded") from exc
    digest = hashlib.sha256()
    digest.update(b"RGB\x00")
    digest.update(struct.pack(">II", 1024, 1024))
    digest.update(pixels)
    return digest.hexdigest()


def validate_input_manifest(state_root: Path, job_id: object) -> dict[str, Any]:
    paths = job_paths(state_root, job_id)
    expected_input_names = {"job.json"} | {
        f"{name}{suffix}"
        for name in REFERENCE_NAMES
        for suffix in (".png", ".txt")
    }
    try:
        entries = list(paths["input"].iterdir())
    except OSError as exc:
        raise ContractError("training input directory is unavailable") from exc
    if {entry.name for entry in entries} != expected_input_names:
        raise ContractError("training input tree contains an unmanifested path")
    for entry in entries:
        info = entry.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ContractError("training input tree contains a non-regular path")
    manifest_bytes = _regular_bytes(paths["manifest"], root=paths["input"])
    try:
        manifest = json.loads(
            manifest_bytes, object_pairs_hook=_reject_duplicate_json
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("input manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, Mapping):
        raise ContractError("input manifest is not an object")
    if set(manifest) != {
        "schema_version",
        "job_id",
        "trigger_token",
        "consent",
        "references",
    }:
        raise ContractError("input manifest fields drifted")
    if manifest.get("schema_version") != 1 or manifest.get("job_id") != canonical_job_id(job_id):
        raise ContractError("input manifest identity drifted")
    token = manifest.get("trigger_token")
    if token != TRIGGER_TOKEN or not TOKEN_RE.fullmatch(str(token)):
        raise ContractError("input trigger token drifted")
    references = manifest.get("references")
    if not isinstance(references, Sequence) or isinstance(references, (str, bytes)) or len(references) != 4:
        raise ContractError("exactly four references are required")
    validated: list[dict[str, Any]] = []
    image_hashes: set[str] = set()
    caption_hashes: set[str] = set()
    caption_values: set[str] = set()
    caption_casefolds: set[str] = set()
    api_references: list[dict[str, str]] = []
    for expected_name, expected_caption, raw in zip(
        REFERENCE_NAMES, FIXED_CAPTIONS, references, strict=True
    ):
        if not isinstance(raw, Mapping) or set(raw) != {
            "image",
            "image_bytes",
            "image_sha256",
            "caption",
            "caption_bytes",
            "caption_sha256",
        }:
            raise ContractError("reference manifest fields drifted")
        image_relative = f"{expected_name}.png"
        caption_relative = f"{expected_name}.txt"
        if raw.get("image") != image_relative or raw.get("caption") != caption_relative:
            raise ContractError("reference paths are not the fixed server-owned paths")
        image_payload = _regular_bytes(paths["input"] / image_relative, root=paths["input"])
        caption_payload = _regular_bytes(paths["input"] / caption_relative, root=paths["input"])
        image_sha = sha256_bytes(image_payload)
        caption_sha = sha256_bytes(caption_payload)
        if raw.get("image_bytes") != len(image_payload) or raw.get("image_sha256") != image_sha:
            raise ContractError("reference image hash binding failed")
        if raw.get("caption_bytes") != len(caption_payload) or raw.get("caption_sha256") != caption_sha:
            raise ContractError("reference caption hash binding failed")
        _png_dimensions(image_payload)
        try:
            caption = caption_payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError("captions must be UTF-8") from exc
        if (
            not 1 <= len(caption) <= 512
            or caption != caption.strip()
            or "\n" in caption
            or "\r" in caption
            or "\x00" in caption
            or not all(character.isprintable() for character in caption)
            or caption != expected_caption
        ):
            raise ContractError("caption is malformed or lacks the fixed trigger token")
        if (
            image_sha in image_hashes
            or caption_sha in caption_hashes
            or caption in caption_values
            or caption.casefold() in caption_casefolds
        ):
            raise ContractError("duplicate training reference or caption")
        image_hashes.add(image_sha)
        caption_hashes.add(caption_sha)
        caption_values.add(caption)
        caption_casefolds.add(caption.casefold())
        api_references.append({"sha256": image_sha, "caption": caption})
        validated.append(
            {
                "image": image_relative,
                "image_bytes": len(image_payload),
                "image_sha256": image_sha,
                "caption": caption_relative,
                "caption_bytes": len(caption_payload),
                "caption_sha256": caption_sha,
            }
        )
    reference_set_sha = sha256_bytes(canonical_json_bytes(validated))
    if manifest.get("consent") != {
        "identity_owner_authorized": True,
        "training_use_authorized": True,
        "reference_set_sha256": reference_set_sha,
    }:
        raise ContractError("consent is absent or not bound to this reference set")
    normalized = {
        "schema_version": 1,
        "job_id": canonical_job_id(job_id),
        "trigger_token": TRIGGER_TOKEN,
        "consent": dict(manifest["consent"]),
        "references": validated,
    }
    canonical = canonical_json_bytes(normalized)
    if canonical != manifest_bytes:
        raise ContractError("input manifest is not canonical")
    return {
        "manifest": normalized,
        "sha256": sha256_bytes(canonical),
        "api_references": api_references,
    }


def validate_api_manifest(
    state_root: Path,
    job_id: object,
    *,
    input_result: Mapping[str, Any],
    candidate_sha256: str,
) -> dict[str, Any]:
    paths = job_paths(state_root, job_id)
    try:
        raw = _regular_bytes(paths["api_manifest"], root=paths["job"])
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("API admission manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, Mapping) or set(manifest) != {
        "schema_version",
        "contract",
        "candidate_sha256",
        "consent",
        "references",
    }:
        raise ContractError("API admission manifest fields drifted")
    expected = {
        "schema_version": 1,
        "contract": CANARY_CONTRACT,
        "candidate_sha256": candidate_sha256,
        "consent": True,
        "references": input_result.get("api_references"),
    }
    if manifest != expected or raw != canonical_utf8_json_bytes(expected):
        raise ContractError("API admission manifest does not bind the staged inputs")
    if canonical_job_id(job_id) != sha256_bytes(raw)[:32]:
        raise ContractError("job id is not derived from the canonical API manifest")
    return {
        "manifest": expected,
        "sha256": sha256_bytes(raw),
        "contract": CANARY_CONTRACT,
        "candidate_sha256": candidate_sha256,
    }


def build_training_config(state_root: Path, job_id: object) -> dict[str, Any]:
    paths = job_paths(state_root, job_id)
    name = "identity_lora_" + canonical_job_id(job_id)
    return {
        "job": "extension",
        "config": {
            "name": name,
            "process": [
                {
                    "type": "sd_trainer",
                    "training_folder": str(paths["output"]),
                    "device": "cuda:0",
                    "training_seed": 0,
                    "trigger_word": TRIGGER_TOKEN,
                    "network": {
                        "type": "lora",
                        "linear": 16,
                        "linear_alpha": 16,
                        "transformer_only": True,
                    },
                    "save": {
                        "dtype": "bf16",
                        "save_format": "safetensors",
                        "save_every": 100,
                        "max_step_saves_to_keep": 1,
                        "push_to_hub": False,
                    },
                    "datasets": [
                        {
                            "folder_path": str(paths["input"]),
                            "caption_ext": "txt",
                            "caption_dropout_rate": 0.0,
                            "shuffle_tokens": False,
                            "resolution": [512],
                            "buckets": True,
                            "cache_latents": False,
                            "cache_latents_to_disk": True,
                            "num_repeats": 1,
                        }
                    ],
                    "train": {
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
                    },
                    "model": {
                        "name_or_path": str(paths["models"] / BASE_FILENAME),
                        "arch": "flux2_klein_4b",
                        "vae_path": str(paths["models"] / VAE_FILENAME),
                        "quantize": True,
                        "quantize_te": True,
                        "qtype": "qfloat8",
                        "qtype_te": "qfloat8",
                        "low_vram": True,
                    },
                }
            ],
        },
        "meta": {"name": "[name]", "version": "1.0"},
    }


def validate_resource_snapshot(snapshot: Mapping[str, Any]) -> None:
    expected_fields = {
        "operating_system",
        "architecture",
        "python",
        "ram_bytes",
        "free_disk_bytes",
        "cuda_available",
        "torch_version",
        "torchvision_version",
        "torchaudio_version",
        "cuda_version",
        "runtime_imports_sha256",
        "cuda_smoke_passed",
        "toolkit_import_smoke_passed",
        "gpu_name",
        "gpu_uuid",
        "vram_mib",
        "free_vram_mib",
        "gpu_utilization_percent",
        "compute_capability",
        "packages_sha256",
    }
    if set(snapshot) != expected_fields:
        raise ContractError("resource snapshot fields drifted")
    if snapshot.get("operating_system") != "Windows" or snapshot.get("architecture") != "AMD64":
        raise ContractError("training requires Windows AMD64")
    if snapshot.get("python") != "3.12":
        raise ContractError("training requires CPython 3.12")
    numeric_gates = (
        ("ram_bytes", 34_359_738_368),
        ("free_disk_bytes", 42_949_672_960),
        ("vram_mib", 15_000),
        ("free_vram_mib", 13_500),
    )
    for field, minimum in numeric_gates:
        value = snapshot.get(field)
        if type(value) is not int or value < minimum:
            raise ContractError(f"resource gate failed: {field}")
    if snapshot.get("free_vram_mib") > snapshot.get("vram_mib"):
        raise ContractError("GPU memory telemetry is contradictory")
    utilization = snapshot.get("gpu_utilization_percent")
    if type(utilization) is not int or not 0 <= utilization <= 5:
        raise ContractError("GPU is not idle enough for the training canary")
    if snapshot.get("cuda_available") is not True or "RTX 5070 Ti" not in str(snapshot.get("gpu_name")):
        raise ContractError("required CUDA RTX 5070 Ti is unavailable")
    if not re.fullmatch(r"GPU-[0-9a-fA-F-]{16,}", str(snapshot.get("gpu_uuid"))):
        raise ContractError("GPU UUID is missing or malformed")
    if not re.fullmatch(r"\d+\.\d+", str(snapshot.get("compute_capability"))):
        raise ContractError("GPU compute capability is missing")
    if snapshot.get("torch_version") != TORCH_VERSION:
        raise ContractError("torch version drifted from the pinned runtime")
    if snapshot.get("torchvision_version") != TORCHVISION_VERSION:
        raise ContractError("torchvision version drifted from the pinned runtime")
    if snapshot.get("torchaudio_version") != TORCHAUDIO_VERSION:
        raise ContractError("torchaudio version drifted from the pinned runtime")
    if snapshot.get("cuda_version") != CUDA_VERSION:
        raise ContractError("CUDA version drifted from the pinned runtime")
    if snapshot.get("cuda_smoke_passed") is not True:
        raise ContractError("CUDA runtime smoke did not pass")
    if snapshot.get("toolkit_import_smoke_passed") is not True:
        raise ContractError("AI Toolkit import smoke did not pass")
    if not HEX64.fullmatch(str(snapshot.get("runtime_imports_sha256"))):
        raise ContractError("direct runtime import proof is missing")
    if not HEX64.fullmatch(str(snapshot.get("packages_sha256"))):
        raise ContractError("installed dependency digest is missing")


def validate_runtime_receipts(state_root: Path, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    paths = job_paths(state_root, "0" * 32)
    runtime = _json_object(paths["runtime_receipt"], root=paths["runtime"])
    model = _json_object(paths["model_receipt"], root=paths["runtime"])
    if set(runtime) != {
        "schema_version",
        "toolkit_commit",
        "python",
        "packages_sha256",
        "dependency_lock_sha256",
        "qwen",
    }:
        raise ContractError("runtime receipt fields drifted")
    if (
        runtime.get("schema_version") != 1
        or runtime.get("toolkit_commit") != TOOLKIT_COMMIT
        or runtime.get("python") != "3.12"
        or runtime.get("packages_sha256") != snapshot.get("packages_sha256")
        or runtime.get("dependency_lock_sha256")
        != file_record(ROOT / "requirements.lock", root=ROOT)["sha256"]
    ):
        raise ContractError("runtime dependency receipt does not match the live environment")
    qwen = runtime.get("qwen")
    if not isinstance(qwen, Mapping) or set(qwen) != {
        "repository",
        "revision",
        "tree_sha256",
        "files",
    }:
        raise ContractError("Qwen offline-cache receipt is incomplete")
    if (
        qwen.get("repository") != "Qwen/Qwen3-4B"
        or qwen.get("revision") != QWEN_REVISION
        or qwen.get("tree_sha256") != QWEN_TREE_SHA256
    ):
        raise ContractError("Qwen offline-cache receipt is invalid")
    files = qwen.get("files")
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
        raise ContractError("Qwen offline-cache file receipt is invalid")
    received: dict[str, dict[str, object]] = {}
    for record in files:
        if not isinstance(record, Mapping) or set(record) != {"path", "bytes", "sha256"}:
            raise ContractError("Qwen offline-cache file receipt is invalid")
        relative = record.get("path")
        if not isinstance(relative, str) or relative not in QWEN_REQUIRED_FILES or relative in received:
            raise ContractError("Qwen offline-cache file inventory drifted")
        received[relative] = {
            "bytes": record.get("bytes"),
            "sha256": record.get("sha256"),
        }
    if set(received) != QWEN_REQUIRED_FILES:
        raise ContractError("Qwen offline-cache file inventory drifted")
    for relative, (expected_bytes, expected_sha) in QWEN_FILE_RECORDS.items():
        if received[relative] != {"bytes": expected_bytes, "sha256": expected_sha}:
            raise ContractError("Qwen offline-cache file pin drifted")
    snapshot_root = (
        paths["hf_home"]
        / "hub"
        / "models--Qwen--Qwen3-4B"
        / "snapshots"
        / QWEN_REVISION
    )
    actual_records: list[dict[str, object]] = []
    for relative in sorted(QWEN_REQUIRED_FILES):
        record = file_record(snapshot_root / relative, root=paths["hf_home"])
        if record != received[relative]:
            raise ContractError(f"Qwen offline-cache file drifted: {relative}")
        actual_records.append({"path": relative, **record})
    if sha256_bytes(canonical_json_bytes(actual_records)) != QWEN_TREE_SHA256:
        raise ContractError("Qwen offline-cache tree digest drifted")
    ref = paths["hf_home"] / "hub" / "models--Qwen--Qwen3-4B" / "refs" / "main"
    try:
        cached_revision = _regular_bytes(ref, root=paths["hf_home"]).decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ContractError("Qwen cache ref is not ASCII") from exc
    if cached_revision != QWEN_REVISION:
        raise ContractError("Qwen cache main ref is not pinned")
    if set(model) != {"schema_version", "training_base", "training_vae"}:
        raise ContractError("model receipt fields drifted")
    if model.get("training_base") != {
        "repository": BASE_REPOSITORY,
        "revision": BASE_REVISION,
        "file": BASE_FILENAME,
        "expected_bytes": BASE_BYTES,
        "sha256": BASE_SHA256,
    }:
        raise ContractError("training-base receipt drifted")
    if model.get("training_vae") != {
        "repository": VAE_REPOSITORY,
        "revision": VAE_REVISION,
        "file": VAE_FILENAME,
        "expected_bytes": VAE_BYTES,
        "sha256": VAE_SHA256,
    }:
        raise ContractError("training-VAE receipt drifted")
    for filename, size, digest in (
        (BASE_FILENAME, BASE_BYTES, BASE_SHA256),
        (VAE_FILENAME, VAE_BYTES, VAE_SHA256),
    ):
        record = file_record(paths["models"] / filename, root=paths["models"])
        if record != {"bytes": size, "sha256": digest}:
            raise ContractError(f"installed model drifted: {filename}")
    return {
        "runtime_receipt_sha256": file_record(paths["runtime_receipt"], root=paths["runtime"])["sha256"],
        "model_receipt_sha256": file_record(paths["model_receipt"], root=paths["runtime"])["sha256"],
    }


def _memory_bytes_windows() -> int:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("memory_load", ctypes.c_ulong),
            ("total_physical", ctypes.c_ulonglong),
            ("available_physical", ctypes.c_ulonglong),
            ("total_page_file", ctypes.c_ulonglong),
            ("available_page_file", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong),
            ("available_virtual", ctypes.c_ulonglong),
            ("available_extended_virtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    try:
        success = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    except (AttributeError, OSError) as exc:
        raise ContractError("Windows RAM telemetry is unavailable") from exc
    if not success:
        raise ContractError("Windows RAM telemetry failed")
    return int(status.total_physical)


def _toolkit_clean_commit(paths: Mapping[str, Path]) -> str:
    program_files = os.environ.get("ProgramFiles")
    if not program_files:
        raise ContractError("ProgramFiles is unavailable")
    git = Path(program_files) / "Git" / "cmd" / "git.exe"
    if not git.is_file():
        raise ContractError("fixed Git executable is unavailable")
    commands = (
        ["rev-parse", "HEAD"],
        ["status", "--porcelain", "--untracked-files=all"],
    )
    outputs: list[str] = []
    for arguments in commands:
        result = subprocess.run(
            [str(git), "-C", str(paths["toolkit"]), *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            raise ContractError("AI Toolkit checkout cannot be verified")
        outputs.append(result.stdout.strip())
    if outputs != [TOOLKIT_COMMIT, ""]:
        raise ContractError("AI Toolkit checkout revision or worktree drifted")
    _regular_bytes(paths["toolkit"] / "run.py", root=paths["toolkit"])
    return TOOLKIT_COMMIT


def collect_resource_snapshot(state_root: Path) -> dict[str, Any]:
    """Measure the fixed Windows runtime without accepting paths or commands."""

    if os.name != "nt" or platform.system() != "Windows" or platform.machine() != "AMD64":
        raise ContractError("resource preflight requires Windows AMD64")
    paths = job_paths(state_root, "0" * 32)
    try:
        fixed_python = paths["python"].resolve(strict=True)
    except OSError as exc:
        raise ContractError("fixed training venv is unavailable") from exc
    if Path(sys.executable).resolve() != fixed_python:
        raise ContractError("resource preflight is not running in the fixed training venv")
    _toolkit_clean_commit(paths)
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    nvidia_smi = Path(system_root) / "System32" / "nvidia-smi.exe"
    if not nvidia_smi.is_file():
        raise ContractError("fixed NVIDIA telemetry executable is unavailable")
    result = subprocess.run(
        [
            str(nvidia_smi),
            "--query-gpu=name,uuid,memory.total,memory.free,utilization.gpu,compute_cap",
            "--format=csv,noheader,nounits",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
        timeout=30,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0 or len(lines) != 1:
        raise ContractError("exactly one NVIDIA GPU is required")
    fields = [value.strip() for value in lines[0].split(",")]
    if len(fields) != 6:
        raise ContractError("NVIDIA telemetry shape drifted")
    import_map = json.dumps(list(DIRECT_RUNTIME_IMPORTS.items()), separators=(",", ":"))
    probe = (
        "import hashlib,importlib,importlib.metadata,json,re;"
        f"pairs=json.loads({import_map!r});"
        "loaded={n:importlib.import_module(v) for n,v in pairs};"
        "torch=loaded['torch'];"
        "direct=sorted([n,importlib.metadata.version(n),v] for n,v in pairs);"
        "p=sorted((re.sub(r'[-_.]+','-',d.metadata.get('Name','').lower()),d.version) for d in importlib.metadata.distributions());"
        "b=(json.dumps(p,separators=(',',':'))+'\\n').encode();"
        "d=(json.dumps(direct,separators=(',',':'))+'\\n').encode();"
        "boxes=torch.tensor([[0.,0.,1.,1.]],device='cuda');"
        "scores=torch.tensor([1.],device='cuda');"
        "keep=loaded['torchvision'].ops.nms(boxes,scores,0.5);"
        "audio=loaded['torchaudio'].functional.resample(torch.zeros((1,16)),8000,16000);"
        "torch.cuda.synchronize();"
        "print(json.dumps({'torch_version':torch.__version__,"
        "'torchvision_version':loaded['torchvision'].__version__,"
        "'torchaudio_version':loaded['torchaudio'].__version__,"
        "'cuda_version':torch.version.cuda,'cuda_available':torch.cuda.is_available(),"
        "'gpu_name':torch.cuda.get_device_name(0) if torch.cuda.is_available() else '',"
        "'compute_capability':'.'.join(map(str,torch.cuda.get_device_capability(0))) if torch.cuda.is_available() else '',"
        "'runtime_imports_sha256':hashlib.sha256(d).hexdigest(),"
        "'cuda_smoke_passed':bool(keep.numel()==1 and audio.shape[-1]>16),"
        "'packages_sha256':hashlib.sha256(b).hexdigest()}))"
    )
    python_result = subprocess.run(
        [str(paths["python"]), "-I", "-c", probe],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
        timeout=180,
    )
    try:
        runtime = json.loads(python_result.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError("CUDA runtime probe did not return JSON") from exc
    if python_result.returncode != 0 or not isinstance(runtime, Mapping):
        raise ContractError("CUDA runtime probe failed")
    toolkit_smoke = subprocess.run(
        [str(paths["python"]), str(paths["toolkit"] / "run.py"), "--help"],
        cwd=paths["toolkit"],
        env=fixed_child_environment(paths),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
        timeout=180,
    )
    if (
        toolkit_smoke.returncode != 0
        or len(toolkit_smoke.stdout) + len(toolkit_smoke.stderr) > 1_048_576
        or "config_file_list" not in toolkit_smoke.stdout + toolkit_smoke.stderr
    ):
        raise ContractError("AI Toolkit import smoke failed")
    name, gpu_uuid, vram, free_vram, utilization, compute = fields
    if runtime.get("gpu_name") != name:
        raise ContractError("CUDA and NVIDIA telemetry identify different GPUs")
    try:
        snapshot = {
            "operating_system": "Windows",
            "architecture": "AMD64",
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "ram_bytes": _memory_bytes_windows(),
            "free_disk_bytes": shutil.disk_usage(state_root).free,
            "cuda_available": runtime.get("cuda_available"),
            "torch_version": runtime.get("torch_version"),
            "torchvision_version": runtime.get("torchvision_version"),
            "torchaudio_version": runtime.get("torchaudio_version"),
            "cuda_version": runtime.get("cuda_version"),
            "runtime_imports_sha256": runtime.get("runtime_imports_sha256"),
            "cuda_smoke_passed": runtime.get("cuda_smoke_passed"),
            "toolkit_import_smoke_passed": True,
            "gpu_name": name,
            "gpu_uuid": gpu_uuid,
            "vram_mib": int(vram),
            "free_vram_mib": int(free_vram),
            "gpu_utilization_percent": int(utilization),
            "compute_capability": compute,
            "packages_sha256": runtime.get("packages_sha256"),
        }
    except (OSError, ValueError) as exc:
        raise ContractError("resource telemetry cannot be parsed") from exc
    if snapshot["compute_capability"] != runtime.get("compute_capability"):
        raise ContractError("CUDA and NVIDIA telemetry report different compute capability")
    validate_resource_snapshot(snapshot)
    return snapshot


def sample_gpu_memory_used_bytes() -> int:
    """Read one bounded RTX memory sample from the fixed driver binary."""

    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    nvidia_smi = Path(system_root) / "System32" / "nvidia-smi.exe"
    if os.name != "nt" or not nvidia_smi.is_file():
        raise ContractError("fixed NVIDIA telemetry executable is unavailable")
    result = subprocess.run(
        [
            str(nvidia_smi),
            "--query-gpu=memory.used",
            "--format=csv,noheader,nounits",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
        timeout=10,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0 or len(lines) != 1:
        raise ContractError("GPU memory telemetry is incomplete")
    try:
        used_mib = int(lines[0])
    except ValueError as exc:
        raise ContractError("GPU memory telemetry is malformed") from exc
    if used_mib < 0:
        raise ContractError("GPU memory telemetry is malformed")
    return used_mib * 1024 * 1024


def adapter_filename(sha256: object) -> str:
    if not isinstance(sha256, str) or not HEX64.fullmatch(sha256):
        raise ContractError("adapter SHA-256 is malformed")
    return f"identity-lora-{sha256}.safetensors"


def validate_terminal_evidence(record: dict[str, object]) -> None:
    if set(record) != {
        "schema_version",
        "capability",
        "job_id",
        "state",
        "attempt",
        "resumed",
        "blocker_code",
        "return_code",
        "elapsed_seconds",
        "elapsed_scope",
        "peak_vram_bytes",
        "telemetry_complete",
        "contract",
        "candidate_sha256",
        "manifest_sha256",
        "package_sha256",
        "input_manifest_sha256",
        "config_sha256",
        "log_sha256",
        "adapter",
        "resume_checkpoint_sha256",
        "inference_runtime_sha256",
        "activity_lease_sha256",
    }:
        raise ContractError("terminal evidence fields drifted")
    if (
        record.get("schema_version") != 1
        or record.get("capability") != CAPABILITY
        or record.get("contract") != "flux2-klein-character-lora-canary-v1"
        or record.get("elapsed_scope") != "current_process_attempt"
    ):
        raise ContractError("terminal evidence identity drifted")
    canonical_job_id(record.get("job_id"))
    attempt = record.get("attempt")
    if type(attempt) is not int or attempt not in {1, 2} or record.get("resumed") is not (attempt == 2):
        raise ContractError("terminal attempt metadata is invalid")
    elapsed = record.get("elapsed_seconds")
    peak = record.get("peak_vram_bytes")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed <= 0
        or type(peak) is not int
        or peak <= 0
    ):
        raise ContractError("terminal telemetry must be measured and strictly positive")
    if type(record.get("telemetry_complete")) is not bool:
        raise ContractError("terminal telemetry completeness is invalid")
    for field in (
        "candidate_sha256",
        "manifest_sha256",
        "package_sha256",
        "input_manifest_sha256",
        "config_sha256",
        "inference_runtime_sha256",
        "activity_lease_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(record.get(field))):
            raise ContractError("terminal evidence digest is malformed")
    if record.get("candidate_sha256") != record.get("package_sha256"):
        raise ContractError("terminal candidate/package binding disagrees")
    for field in ("log_sha256", "resume_checkpoint_sha256"):
        value = record.get(field)
        if value is not None and not re.fullmatch(r"[0-9a-f]{64}", str(value)):
            raise ContractError("terminal optional digest is malformed")
    return_code = record.get("return_code")
    if return_code is not None and type(return_code) is not int:
        raise ContractError("terminal return code is invalid")
    state = record.get("state")
    adapter = record.get("adapter")
    blocker = record.get("blocker_code")
    if state == "training_passed":
        if return_code != 0 or blocker is not None or record.get("telemetry_complete") is not True:
            raise ContractError("passing terminal evidence contradicts its state")
        if not isinstance(adapter, dict) or set(adapter) != {
            "filename",
            "bytes",
            "sha256",
            "metadata_filename",
            "metadata_sha256",
            "tensor_count",
            "pair_count",
            "tensor_inventory_sha256",
        }:
            raise ContractError("passing terminal adapter evidence is incomplete")
        sha = adapter.get("sha256")
        if (
            adapter.get("filename") != adapter_filename(sha)
            or adapter.get("metadata_filename") != f"{adapter_filename(sha)}.json"
            or type(adapter.get("bytes")) is not int
            or adapter.get("bytes") <= 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(adapter.get("metadata_sha256")))
            or adapter.get("tensor_count") != 160
            or adapter.get("pair_count") != 80
            or not re.fullmatch(
                r"[0-9a-f]{64}", str(adapter.get("tensor_inventory_sha256"))
            )
        ):
            raise ContractError("passing terminal adapter evidence is invalid")
    elif state in {"failed", "unknown"}:
        if adapter is not None or not isinstance(blocker, str) or not blocker:
            raise ContractError("non-passing terminal evidence contradicts its state")
        if state == "unknown" and return_code is not None:
            raise ContractError("unknown terminal cannot claim a return code")
    else:
        raise ContractError("terminal state is invalid")




def build_inference_workflow(
    *, metadata: Mapping[str, Any], prompt: str
) -> dict[str, dict[str, Any]]:
    """Build the fixed seed-0, four-step, 1:1 core-node LoRA graph."""

    normalized = validate_adapter_metadata(metadata)
    if (
        not isinstance(prompt, str)
        or not 1 <= len(prompt.strip()) <= 4096
        or prompt != prompt.strip()
        or prompt.split().count(TRIGGER_TOKEN) != 1
        or "\x00" in prompt
    ):
        raise ContractError("inference prompt must contain the fixed trigger token exactly once")
    lora_name = normalized["adapter"]["filename"]
    prefix = "identity-lora-" + normalized["adapter"]["sha256"][:16]
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": DISTILLED_FILENAME, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"model": ["1", 0], "lora_name": lora_name, "strength_model": 1.0},
        },
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": TEXT_ENCODER_FILENAME, "type": "flux2", "device": "default"},
        },
        "4": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": INFERENCE_VAE_FILENAME},
        },
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": 1024, "height": 1024}},
        "10": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "11": {
            "class_type": "CFGGuider",
            "inputs": {"model": ["2", 0], "positive": ["5", 0], "negative": ["6", 0], "cfg": 1.0},
        },
        "12": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {"noise": ["7", 0], "guider": ["11", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["10", 0]},
        },
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
        "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": prefix}},
    }


def build_control_workflow(
    *, metadata: Mapping[str, Any], prompt: str
) -> dict[str, dict[str, Any]]:
    """Build the exact text-only arm paired with the LoRA canary."""

    normalized = validate_adapter_metadata(metadata)
    graph = copy.deepcopy(build_inference_workflow(metadata=normalized, prompt=prompt))
    del graph["2"]
    graph["11"]["inputs"]["model"] = ["1", 0]
    graph["14"]["inputs"]["filename_prefix"] = (
        "identity-control-" + normalized["adapter"]["sha256"][:16]
    )
    return graph


def _combo(spec: object) -> tuple[str, ...] | None:
    if not isinstance(spec, list) or not spec:
        return None
    choices = spec[0]
    if isinstance(choices, list) and all(isinstance(value, str) for value in choices):
        return tuple(choices)
    return None


def validate_inference_workflow(
    graph: Mapping[str, Any], metadata: Mapping[str, Any], object_info: Mapping[str, Any]
) -> dict[str, object]:
    normalized = validate_adapter_metadata(metadata)
    if not isinstance(graph, Mapping) or graph.get("5", {}).get("class_type") != "CLIPTextEncode":
        raise ContractError("inference graph is malformed")
    prompt = graph["5"].get("inputs", {}).get("text")
    if graph != build_inference_workflow(metadata=normalized, prompt=prompt):
        raise ContractError("inference graph drifted from the fixed contract")
    _validate_object_info(graph, normalized, object_info, include_lora=True)
    return {"status": "static_inference_preflight_passed", "node_count": len(graph), "reference_count": 0, "execution_proven": False}


def _validate_object_info(
    graph: Mapping[str, Any],
    metadata: Mapping[str, Any],
    object_info: Mapping[str, Any],
    *,
    include_lora: bool,
) -> None:
    required = {node["class_type"] for node in graph.values()}
    if not required <= set(object_info):
        raise ContractError("required core inference node is missing")
    expected_choices = {
        ("UNETLoader", "unet_name"): DISTILLED_FILENAME,
        ("CLIPLoader", "clip_name"): TEXT_ENCODER_FILENAME,
        ("CLIPLoader", "type"): "flux2",
        ("VAELoader", "vae_name"): INFERENCE_VAE_FILENAME,
    }
    if include_lora:
        expected_choices[("LoraLoaderModelOnly", "lora_name")] = metadata["adapter"]["filename"]
    for (class_name, field), expected in expected_choices.items():
        raw = object_info.get(class_name)
        if not isinstance(raw, Mapping):
            raise ContractError(f"object_info is missing {class_name}")
        inputs = raw.get("input")
        if not isinstance(inputs, Mapping):
            raise ContractError(f"object_info input schema is missing for {class_name}")
        spec = None
        for section in ("required", "optional"):
            values = inputs.get(section)
            if isinstance(values, Mapping) and field in values:
                spec = values[field]
        choices = _combo(spec)
        if choices is None or expected not in choices:
            raise ContractError(f"object_info rejects fixed {class_name}.{field}")
    if include_lora:
        loader = object_info["LoraLoaderModelOnly"].get("input", {}).get("required", {})
        if set(loader) != {"model", "lora_name", "strength_model"}:
            raise ContractError("LoraLoaderModelOnly input schema drifted")
        if loader.get("model", [None])[0] != "MODEL" or loader.get("strength_model", [None])[0] != "FLOAT":
            raise ContractError("LoraLoaderModelOnly types drifted")


def validate_control_workflow(
    graph: Mapping[str, Any], metadata: Mapping[str, Any], object_info: Mapping[str, Any]
) -> dict[str, object]:
    normalized = validate_adapter_metadata(metadata)
    if not isinstance(graph, Mapping) or graph.get("5", {}).get("class_type") != "CLIPTextEncode":
        raise ContractError("control graph is malformed")
    prompt = graph["5"].get("inputs", {}).get("text")
    if graph != build_control_workflow(metadata=normalized, prompt=prompt):
        raise ContractError("control graph drifted from the fixed contract")
    _validate_object_info(graph, normalized, object_info, include_lora=False)
    return {"status": "static_control_preflight_passed", "node_count": len(graph), "reference_count": 0, "execution_proven": False}


def validate_benchmark_proof(proof: Mapping[str, Any]) -> dict[str, Any]:
    if set(proof) != {
        "schema_version",
        "capability",
        "contract",
        "state",
        "job_id",
        "candidate_sha256",
        "manifest_sha256",
        "training_terminal_sha256",
        "runtime_contract_sha256",
        "benchmark_activity_lease_sha256",
        "adapter",
        "prompt_sha256",
        "object_info_sha256",
        "settings",
        "sequence",
        "arms",
        "causality",
    }:
        raise ContractError("inference benchmark proof fields drifted")
    if (
        proof.get("schema_version") != 1
        or proof.get("capability") != CAPABILITY
        or proof.get("contract") != BENCHMARK_CONTRACT
        or proof.get("state") != "passed"
        or proof.get("sequence") != ["control", "lora"]
        or proof.get("settings")
        != {"reference_count": 0, "seed": 0, "steps": 4, "sampler": "euler", "cfg": 1.0, "width": 1024, "height": 1024}
        or proof.get("prompt_sha256") != sha256_bytes(BENCHMARK_PROMPT.encode("utf-8"))
    ):
        raise ContractError("inference benchmark proof identity drifted")
    canonical_job_id(proof.get("job_id"))
    for field in (
        "candidate_sha256",
        "manifest_sha256",
        "training_terminal_sha256",
        "runtime_contract_sha256",
        "benchmark_activity_lease_sha256",
        "object_info_sha256",
    ):
        if not HEX64.fullmatch(str(proof.get(field))):
            raise ContractError("inference benchmark proof digest is malformed")
    adapter = proof.get("adapter")
    if not isinstance(adapter, Mapping) or set(adapter) != {
        "filename",
        "sha256",
        "metadata_filename",
        "metadata_sha256",
        "tensor_count",
        "pair_count",
        "tensor_inventory_sha256",
    }:
        raise ContractError("inference benchmark adapter binding is incomplete")
    if adapter.get("filename") != adapter_filename(adapter.get("sha256")):
        raise ContractError("inference benchmark adapter filename is not content-addressed")
    for field in ("sha256", "metadata_sha256"):
        if not HEX64.fullmatch(str(adapter.get(field))):
            raise ContractError("inference benchmark adapter digest is malformed")
    if adapter.get("metadata_filename") != f"{adapter.get('filename')}.json":
        raise ContractError("inference benchmark adapter metadata path drifted")
    if (
        adapter.get("tensor_count") != 160
        or adapter.get("pair_count") != 80
        or not HEX64.fullmatch(str(adapter.get("tensor_inventory_sha256")))
    ):
        raise ContractError("inference benchmark adapter inventory drifted")
    arms = proof.get("arms")
    if not isinstance(arms, list) or len(arms) != 2:
        raise ContractError("inference benchmark arms are incomplete")
    pixel_hashes: list[str] = []
    for expected_arm, arm in zip(("control", "lora"), arms, strict=True):
        if not isinstance(arm, Mapping) or set(arm) != {
            "arm",
            "prompt_id",
            "workflow_sha256",
            "output_file",
            "output_bytes",
            "output_sha256",
            "pixel_sha256",
            "latency_seconds",
            "peak_vram_bytes",
        }:
            raise ContractError("inference benchmark arm fields drifted")
        if arm.get("arm") != expected_arm or not PROMPT_ID_RE.fullmatch(str(arm.get("prompt_id"))):
            raise ContractError("inference benchmark arm identity drifted")
        if arm.get("output_file") != f"{expected_arm}.png":
            raise ContractError("inference benchmark output path drifted")
        if type(arm.get("output_bytes")) is not int or arm.get("output_bytes") <= 0:
            raise ContractError("inference benchmark output byte count is invalid")
        if type(arm.get("peak_vram_bytes")) is not int or arm.get("peak_vram_bytes") <= 0:
            raise ContractError("inference benchmark VRAM telemetry is invalid")
        latency = arm.get("latency_seconds")
        if isinstance(latency, bool) or not isinstance(latency, (int, float)) or not math.isfinite(latency) or latency <= 0:
            raise ContractError("inference benchmark latency telemetry is invalid")
        for field in ("workflow_sha256", "output_sha256", "pixel_sha256"):
            if not HEX64.fullmatch(str(arm.get(field))):
                raise ContractError("inference benchmark arm digest is malformed")
        pixel_hashes.append(str(arm["pixel_sha256"]))
    if proof.get("causality") != {"pixel_hashes_differ": True} or len(set(pixel_hashes)) != 2:
        raise ContractError("LoRA causality was not demonstrated")
    return dict(proof)




def build_adapter_metadata(
    *,
    job_id: str,
    adapter_bytes: int,
    adapter_sha256: str,
    input_manifest_sha256: str,
    config_sha256: str,
    package_sha256: str,
    inference_runtime_sha256: str,
    tensor_count: int,
    pair_count: int,
    tensor_inventory_sha256: str,
) -> dict[str, Any]:
    canonical_job_id(job_id)
    for digest in (
        adapter_sha256,
        input_manifest_sha256,
        config_sha256,
        package_sha256,
        inference_runtime_sha256,
        tensor_inventory_sha256,
    ):
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise ContractError("adapter metadata digest is malformed")
    if isinstance(adapter_bytes, bool) or not isinstance(adapter_bytes, int) or adapter_bytes <= 0:
        raise ContractError("adapter byte count is invalid")
    if tensor_count != 160 or pair_count != 80:
        raise ContractError("adapter tensor inventory count is invalid")
    return {
        "schema_version": 1,
        "state": "training_passed",
        "job_id": job_id,
        "adapter": {
            "filename": adapter_filename(adapter_sha256),
            "bytes": adapter_bytes,
            "sha256": adapter_sha256,
            "tensor_count": tensor_count,
            "pair_count": pair_count,
            "tensor_inventory_sha256": tensor_inventory_sha256,
        },
        "training": {
            "toolkit_commit": TOOLKIT_COMMIT,
            "base_repository": BASE_REPOSITORY,
            "base_revision": BASE_REVISION,
            "base_sha256": BASE_SHA256,
            "arch": "flux2_klein_4b",
            "trigger_token": TRIGGER_TOKEN,
            "rank": 16,
            "alpha": 16,
            "dtype": "bf16",
            "seed": 0,
            "steps": 500,
            "input_manifest_sha256": input_manifest_sha256,
            "config_sha256": config_sha256,
            "package_sha256": package_sha256,
        },
        "inference": {
            "loader": "LoraLoaderModelOnly",
            "base_revision": DISTILLED_REVISION,
            "base_sha256": DISTILLED_SHA256,
            "strength_model": 1.0,
            "reference_count": 0,
            "seed": 0,
            "steps": 4,
            "runtime_contract_sha256": inference_runtime_sha256,
        },
    }


def validate_adapter_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    if set(metadata) != {"schema_version", "state", "job_id", "adapter", "training", "inference"}:
        raise ContractError("adapter metadata fields drifted")
    job_id = canonical_job_id(metadata.get("job_id"))
    adapter = metadata.get("adapter")
    training = metadata.get("training")
    inference = metadata.get("inference")
    if not all(isinstance(value, Mapping) for value in (adapter, training, inference)):
        raise ContractError("adapter compatibility metadata is incomplete")
    sha = adapter.get("sha256")
    expected = build_adapter_metadata(
        job_id=job_id,
        adapter_bytes=adapter.get("bytes"),
        adapter_sha256=sha,
        input_manifest_sha256=training.get("input_manifest_sha256"),
        config_sha256=training.get("config_sha256"),
        package_sha256=training.get("package_sha256"),
        inference_runtime_sha256=inference.get("runtime_contract_sha256"),
        tensor_count=adapter.get("tensor_count"),
        pair_count=adapter.get("pair_count"),
        tensor_inventory_sha256=adapter.get("tensor_inventory_sha256"),
    )
    if metadata != expected:
        raise ContractError("adapter compatibility metadata does not match the candidate")
    return expected


def _reject_duplicate_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("safetensors header contains a duplicate key")
        result[key] = value
    return result


def _safetensors_snapshot(
    path: Path, *, root: Path
) -> tuple[Mapping[str, Any], int, int, dict[str, object]]:
    before = _regular_file_identity(path, root=root)
    if before.st_size < 10:
        raise ContractError("adapter is not a safetensors file")
    digest = hashlib.sha256()
    total = 0
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not _same_file_identity(before, opened):
                raise ContractError("adapter changed while opening")
            prefix = handle.read(8)
            if len(prefix) != 8:
                raise ContractError("adapter is not a safetensors file")
            digest.update(prefix)
            total += len(prefix)
            header_bytes = struct.unpack("<Q", prefix)[0]
            if (
                not 2 <= header_bytes <= 16 * 1024 * 1024
                or 8 + header_bytes > before.st_size
            ):
                raise ContractError("adapter safetensors header length is invalid")
            raw_header = handle.read(header_bytes)
            if len(raw_header) != header_bytes:
                raise ContractError("adapter safetensors header is truncated")
            digest.update(raw_header)
            total += len(raw_header)
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
                total += len(chunk)
            finished = os.fstat(handle.fileno())
    except ContractError:
        raise
    except OSError as exc:
        raise ContractError("adapter safetensors header cannot be read") from exc
    try:
        after = path.lstat()
    except OSError as exc:
        raise ContractError("adapter changed while reading its header") from exc
    if (
        not _same_file_identity(before, finished)
        or not _same_file_identity(before, after)
        or total != before.st_size
    ):
        raise ContractError("adapter changed while reading")
    try:
        header = json.loads(raw_header, object_pairs_hook=_reject_duplicate_json)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("adapter safetensors header is invalid") from exc
    if not isinstance(header, Mapping):
        raise ContractError("adapter safetensors header is not an object")
    return (
        header,
        before.st_size,
        header_bytes,
        {"bytes": total, "sha256": digest.hexdigest()},
    )


def expected_lora_shapes() -> dict[str, dict[str, tuple[int, int]]]:
    double_shapes = {
        "img_attn.qkv": ((16, 3072), (9216, 16)),
        "img_attn.proj": ((16, 3072), (3072, 16)),
        "img_mlp.0": ((16, 3072), (18432, 16)),
        "img_mlp.2": ((16, 9216), (3072, 16)),
        "txt_attn.qkv": ((16, 3072), (9216, 16)),
        "txt_attn.proj": ((16, 3072), (3072, 16)),
        "txt_mlp.0": ((16, 3072), (18432, 16)),
        "txt_mlp.2": ((16, 9216), (3072, 16)),
    }
    result: dict[str, dict[str, tuple[int, int]]] = {}
    for index in range(5):
        for module, (shape_a, shape_b) in double_shapes.items():
            result[f"diffusion_model.double_blocks.{index}.{module}"] = {
                "A": shape_a,
                "B": shape_b,
            }
    for index in range(20):
        result[f"diffusion_model.single_blocks.{index}.linear1"] = {
            "A": (16, 3072),
            "B": (27648, 16),
        }
        result[f"diffusion_model.single_blocks.{index}.linear2"] = {
            "A": (16, 12288),
            "B": (3072, 16),
        }
    return result


def _validate_lora_snapshot(
    path: Path, *, root: Path
) -> tuple[dict[str, object], dict[str, object], Mapping[str, Any]]:
    header, total_bytes, header_bytes, record = _safetensors_snapshot(path, root=root)
    tensors = {key: value for key, value in header.items() if key != "__metadata__"}
    expected = expected_lora_shapes()
    expected_names = {
        f"{module}.lora_{side}.weight"
        for module in expected
        for side in ("A", "B")
    }
    if set(tensors) != expected_names:
        raise ContractError("adapter tensor inventory is not the exact FLUX.2 Klein LoRA")
    data_bytes = total_bytes - 8 - header_bytes
    intervals: list[tuple[int, int]] = []
    inventory: list[dict[str, object]] = []
    for name in sorted(tensors):
        raw = tensors[name]
        if not isinstance(raw, Mapping) or set(raw) != {
            "dtype",
            "shape",
            "data_offsets",
        }:
            raise ContractError("adapter tensor metadata is malformed")
        module, side = name.rsplit(".lora_", 1)
        side = side.removesuffix(".weight")
        dtype = raw.get("dtype")
        shape = raw.get("shape")
        offsets = raw.get("data_offsets")
        if (
            dtype != "BF16"
            or not isinstance(shape, list)
            or tuple(shape) != expected[module][side]
            or not isinstance(offsets, list)
            or len(offsets) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in offsets)
        ):
            raise ContractError("adapter tensor type, shape, or offset is invalid")
        start, end = offsets
        expected_bytes = 2 * shape[0] * shape[1]
        if not 0 <= start < end <= data_bytes or end - start != expected_bytes:
            raise ContractError("adapter tensor payload bounds are invalid")
        intervals.append((start, end))
        inventory.append({"name": name, "dtype": dtype, "shape": shape})
    cursor = 0
    for start, end in sorted(intervals):
        if start != cursor:
            raise ContractError("adapter tensor payload is not contiguous")
        cursor = end
    if cursor != data_bytes:
        raise ContractError("adapter tensor payload is not contiguous")
    inventory_record = {
        "tensor_count": 160,
        "pair_count": 80,
        "tensor_inventory_sha256": sha256_bytes(canonical_json_bytes(inventory)),
    }
    return inventory_record, record, header


def validate_lora_safetensors(path: Path, *, root: Path) -> dict[str, object]:
    inventory, _record, _header = _validate_lora_snapshot(path, root=root)
    return inventory


def validate_resume_checkpoint(
    path: Path, *, root: Path, job_id: str
) -> dict[str, object]:
    canonical_job_id(job_id)
    _inventory, record, header = _validate_lora_snapshot(path, root=root)
    metadata = header.get("__metadata__")
    if not isinstance(metadata, Mapping):
        raise ContractError("resume checkpoint has no training metadata")
    training_info = metadata.get("training_info")
    if isinstance(training_info, str):
        try:
            training_info = json.loads(training_info)
        except json.JSONDecodeError as exc:
            raise ContractError("resume checkpoint training metadata is invalid") from exc
    if not isinstance(training_info, Mapping):
        raise ContractError("resume checkpoint training metadata is invalid")
    step = training_info.get("step")
    if isinstance(step, bool) or not isinstance(step, int) or step not in {100, 200, 300, 400}:
        raise ContractError("resume checkpoint step is outside the fixed continuation points")
    expected_name = f"identity_lora_{job_id}_{step:09d}.safetensors"
    if path.name != expected_name:
        raise ContractError("resume checkpoint filename and metadata disagree")
    return {"step": step, **record, "filename": path.name}


def validate_adapter_file(path: Path, metadata: Mapping[str, Any], *, root: Path) -> dict[str, object]:
    normalized = validate_adapter_metadata(metadata)
    adapter = normalized["adapter"]
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ContractError("adapter file escapes its owned root") from exc
    if relative != adapter["filename"] or not ADAPTER_RE.fullmatch(relative):
        raise ContractError("adapter filename is not content-addressed")
    inventory, record, _header = _validate_lora_snapshot(path, root=root)
    if inventory != {
        "tensor_count": adapter["tensor_count"],
        "pair_count": adapter["pair_count"],
        "tensor_inventory_sha256": adapter["tensor_inventory_sha256"],
    }:
        raise ContractError("adapter tensor inventory does not match compatibility metadata")
    if record != {"bytes": adapter["bytes"], "sha256": adapter["sha256"]}:
        raise ContractError("adapter bytes do not match compatibility metadata")
    return record


def validate_gateway_admission(
    state_root: Path, job_id: object, candidate_sha256: str
) -> dict[str, Any]:
    validate_package(ROOT)
    job_id = canonical_job_id(job_id)
    actual_candidate = package_digest(ROOT)
    if candidate_sha256 != actual_candidate:
        raise ContractError("gateway candidate binding is stale")
    input_result = validate_input_manifest(state_root, job_id)
    api = validate_api_manifest(
        state_root,
        job_id,
        input_result=input_result,
        candidate_sha256=actual_candidate,
    )
    return {
        "job_id": job_id,
        "candidate_sha256": actual_candidate,
        "input_manifest_sha256": input_result["sha256"],
        "manifest_sha256": api["sha256"],
        "references": input_result["api_references"],
    }


def validate_gateway_training_result(
    state_root: Path,
    job_id: object,
    *,
    expected_activity_lease_sha256: str,
    comfy_lora_root: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(expected_activity_lease_sha256, str) or not HEX64.fullmatch(
        expected_activity_lease_sha256
    ):
        raise ContractError("expected training activity lease is malformed")
    admission = validate_gateway_admission(
        state_root, job_id, package_digest(ROOT)
    )
    job_id = admission["job_id"]
    paths = job_paths(state_root, job_id)
    runtime = validate_inference_runtime()
    terminal_path = paths["evidence"] / "terminal.json"
    started_path = paths["evidence"] / "started.json"
    resume_started_path = paths["evidence"] / "resume-started.json"

    def present(path: Path) -> bool:
        return path.exists() or path.is_symlink()

    def started_record() -> dict[str, Any]:
        started = read_json_object(started_path, root=paths["evidence"])
        if set(started) != {
            "schema_version",
            "job_id",
            "state",
            "attempt",
            "admission_sha256",
            "lease_sha256",
            "activity_lease_sha256",
        } or started != {
            **started,
            "schema_version": 1,
            "job_id": job_id,
            "state": "started",
            "attempt": 1,
        }:
            raise ContractError("initial started evidence is malformed")
        for field in ("admission_sha256", "lease_sha256", "activity_lease_sha256"):
            if not HEX64.fullmatch(str(started.get(field))):
                raise ContractError("initial started evidence digest is malformed")
        return started

    def resume_started_record() -> dict[str, Any]:
        resumed = read_json_object(resume_started_path, root=paths["evidence"])
        if (
            resumed.get("schema_version") != 1
            or resumed.get("job_id") != job_id
            or resumed.get("state") != "started"
            or resumed.get("attempt") != 2
            or resumed.get("activity_lease_sha256")
            != expected_activity_lease_sha256
            or not HEX64.fullmatch(str(resumed.get("lease_sha256")))
        ):
            raise ContractError("resume-started evidence is malformed")
        return resumed

    if not present(terminal_path):
        if not present(started_path):
            if present(resume_started_path):
                raise ContractError("resume evidence exists without an initial start")
            return {
                **admission,
                "state": "not_started",
                "blocker_code": "training_not_started",
                "retry_mode": "initial",
            }
        started = started_record()
        second_attempt = present(resume_started_path)
        resumed = resume_started_record() if second_attempt else None
        if not second_attempt and (
            started["activity_lease_sha256"] != expected_activity_lease_sha256
        ):
            raise ContractError("initial started activity lease binding is stale")
        if present(paths["lock"]):
            lock = read_json_object(paths["lock"], root=paths["root"])
            expected_lease_sha256 = (
                resumed["lease_sha256"] if resumed is not None else started["lease_sha256"]
            )
            if (
                set(lock) != {"schema_version", "job_id", "pid", "nonce"}
                or lock.get("schema_version") != 1
                or lock.get("job_id") != job_id
                or type(lock.get("pid")) is not int
                or lock["pid"] <= 0
                or not re.fullmatch(r"[0-9a-f]{32}", str(lock.get("nonce")))
                or file_record(paths["lock"], root=paths["root"])["sha256"]
                != expected_lease_sha256
            ):
                raise ContractError("interrupted training lease is malformed")
            lease_bound = True
        else:
            lease_bound = False
        checkpoint: dict[str, object] | None = None
        save_root = paths["output"] / f"identity_lora_{job_id}"
        if save_root.is_dir() and not save_root.is_symlink():
            safetensors = list(save_root.glob("*.safetensors"))
            optimizer = save_root / "optimizer.pt"
            if len(safetensors) == 1 and optimizer.is_file() and not optimizer.is_symlink():
                checkpoint = validate_resume_checkpoint(
                    safetensors[0], root=save_root, job_id=job_id
                )
                if file_record(optimizer, root=save_root)["bytes"] < 1024:
                    raise ContractError("resume optimizer state is incomplete")
        retry_mode = (
            "checkpoint"
            if checkpoint is not None and lease_bound and not second_attempt
            else "none"
        )
        return {
            **admission,
            "state": "interrupted",
            "blocker_code": (
                "training_interrupted"
                if retry_mode == "checkpoint"
                else "resume_not_available"
            ),
            "retry_mode": retry_mode,
            "checkpoint": checkpoint,
        }

    terminal = read_json_object(terminal_path, root=paths["evidence"])
    validate_terminal_evidence(terminal)
    if not present(started_path):
        raise ContractError("terminal evidence has no initial start")
    started = started_record()
    if terminal.get("attempt") == 2:
        if not present(resume_started_path):
            raise ContractError("resumed terminal has no resume-started evidence")
        resume_started_record()
    elif present(resume_started_path):
        raise ContractError("initial terminal conflicts with resume-started evidence")
    elif started["activity_lease_sha256"] != expected_activity_lease_sha256:
        raise ContractError("initial started activity lease binding is stale")
    if (
        terminal.get("job_id") != job_id
        or terminal.get("candidate_sha256") != admission["candidate_sha256"]
        or terminal.get("manifest_sha256") != admission["manifest_sha256"]
        or terminal.get("input_manifest_sha256")
        != admission["input_manifest_sha256"]
        or terminal.get("inference_runtime_sha256")
        != runtime["runtime_contract_sha256"]
        or terminal.get("activity_lease_sha256")
        != expected_activity_lease_sha256
    ):
        raise ContractError("training terminal binding is stale")
    config_record = file_record(paths["config"], root=paths["job"])
    if config_record["sha256"] != terminal.get("config_sha256"):
        raise ContractError("training configuration binding failed")
    terminal_sha = file_record(terminal_path, root=paths["evidence"])["sha256"]
    training_projection = {
        "attempt": terminal["attempt"],
        "resumed": terminal["resumed"],
        "elapsed_seconds": terminal["elapsed_seconds"],
        "peak_vram_bytes": terminal["peak_vram_bytes"],
    }
    if terminal["state"] != "training_passed":
        return {
            **admission,
            "state": (
                "training_unknown"
                if terminal["state"] == "unknown"
                else "training_failed"
            ),
            "blocker_code": terminal["blocker_code"],
            "retry_mode": "none",
            "terminal_sha256": terminal_sha,
            "runtime_contract_sha256": runtime["runtime_contract_sha256"],
            "activity_lease_sha256": expected_activity_lease_sha256,
            "training": training_projection,
        }

    adapter = terminal.get("adapter")
    if not isinstance(adapter, Mapping):
        raise ContractError("passing training terminal has no adapter")
    metadata_path = paths["adapter"] / str(adapter.get("metadata_filename"))
    metadata_record = file_record(metadata_path, root=paths["adapter"])
    if metadata_record["sha256"] != adapter.get("metadata_sha256"):
        raise ContractError("adapter metadata hash binding failed")
    metadata = validate_adapter_metadata(
        read_json_object(metadata_path, root=paths["adapter"])
    )
    if (
        adapter
        != {
            **metadata["adapter"],
            "metadata_filename": metadata_path.name,
            "metadata_sha256": metadata_record["sha256"],
        }
        or metadata["inference"]["runtime_contract_sha256"]
        != runtime["runtime_contract_sha256"]
    ):
        raise ContractError("adapter metadata and terminal disagree")
    adapter_path = paths["adapter"] / str(adapter["filename"])
    adapter_record = validate_adapter_file(
        adapter_path, metadata, root=paths["adapter"]
    )
    if comfy_lora_root is not None:
        published = comfy_lora_root / str(adapter["filename"])
        if file_record(published, root=comfy_lora_root) != adapter_record:
            raise ContractError("published ComfyUI adapter drifted")
    return {
        **admission,
        "state": "training_passed",
        "blocker_code": None,
        "retry_mode": "none",
        "terminal_sha256": terminal_sha,
        "runtime_contract_sha256": runtime["runtime_contract_sha256"],
        "activity_lease_sha256": expected_activity_lease_sha256,
        "training": training_projection,
        "adapter_path": str(adapter_path.resolve(strict=True)),
        "adapter": dict(adapter),
        "metadata": metadata,
    }


def validate_gateway_benchmark_result(
    state_root: Path,
    job_id: object,
    *,
    expected_training_activity_lease_sha256: str,
    expected_benchmark_activity_lease_sha256: str,
    comfy_lora_root: Path | None = None,
) -> dict[str, Any]:
    training = validate_gateway_training_result(
        state_root,
        job_id,
        expected_activity_lease_sha256=expected_training_activity_lease_sha256,
        comfy_lora_root=comfy_lora_root,
    )
    if not HEX64.fullmatch(str(expected_benchmark_activity_lease_sha256)):
        raise ContractError("expected benchmark activity lease is malformed")
    if training["state"] != "training_passed":
        return {
            "job_id": training["job_id"],
            "state": "benchmark_not_run",
            "candidate_sha256": training["candidate_sha256"],
            "blocker_code": "training_not_passed",
            "retry_mode": "none",
        }
    paths = job_paths(state_root, training["job_id"])
    proof_path = paths["evidence"] / "inference-benchmark.json"
    failed_path = paths["evidence"] / "inference-benchmark-failed.json"
    unknown_path = paths["evidence"] / "inference-benchmark-unknown.json"
    attempt_path = paths["evidence"] / "inference-benchmark-attempt.json"
    markers = [
        path
        for path in (proof_path, failed_path, unknown_path)
        if path.exists() or path.is_symlink()
    ]
    benchmark_root = paths["job"] / "benchmark"
    if not markers:
        if attempt_path.exists() or attempt_path.is_symlink() or benchmark_root.exists() or benchmark_root.is_symlink():
            raise ContractError("benchmark preflight artifacts require reconciliation")
        return {
            "job_id": training["job_id"],
            "state": "benchmark_not_run",
            "candidate_sha256": training["candidate_sha256"],
            "blocker_code": "benchmark_not_run",
            "retry_mode": "benchmark",
        }
    if len(markers) != 1:
        raise ContractError("benchmark terminal markers conflict")

    if markers[0] != proof_path:
        marker = read_json_object(markers[0], root=paths["evidence"])
        common = {
            "schema_version": 1,
            "contract": BENCHMARK_CONTRACT,
            "job_id": training["job_id"],
            "benchmark_activity_lease_sha256": expected_benchmark_activity_lease_sha256,
        }
        if markers[0] == unknown_path:
            expected_fields = set(common) | {"state", "blocker_code", "attempt_sha256"}
            expected_values = {
                **common,
                "state": "unknown",
                "blocker_code": "inference_benchmark_outcome_unknown",
            }
            state = "benchmark_unknown"
        else:
            blocker = marker.get("blocker_code")
            extra = (
                {
                    "control_output_sha256",
                    "lora_output_sha256",
                    "control_pixel_sha256",
                    "lora_pixel_sha256",
                }
                if blocker == "lora_causality_not_demonstrated"
                else set()
            )
            expected_fields = set(common) | {"state", "blocker_code", "attempt_sha256"} | extra
            expected_values = {**common, "state": "failed"}
            if blocker not in {
                "lora_causality_not_demonstrated",
                "inference_benchmark_preflight_failed",
            }:
                raise ContractError("benchmark failure blocker is invalid")
            if blocker == "lora_causality_not_demonstrated" and (
                not all(
                    HEX64.fullmatch(str(marker.get(field)))
                    for field in extra
                )
                or marker["control_pixel_sha256"]
                != marker["lora_pixel_sha256"]
            ):
                raise ContractError("benchmark causality failure marker is malformed")
            state = "benchmark_failed"
        if set(marker) != expected_fields or marker != {**marker, **expected_values}:
            raise ContractError("benchmark terminal marker is malformed")
        attempt_record = file_record(attempt_path, root=paths["evidence"])
        if marker.get("attempt_sha256") != attempt_record["sha256"]:
            raise ContractError("benchmark attempt binding failed")
        return {
            "job_id": training["job_id"],
            "state": state,
            "candidate_sha256": training["candidate_sha256"],
            "blocker_code": marker["blocker_code"],
            "retry_mode": "none",
            "benchmark_activity_lease_sha256": expected_benchmark_activity_lease_sha256,
            "marker_sha256": file_record(markers[0], root=paths["evidence"])["sha256"],
        }

    proof = validate_benchmark_proof(
        read_json_object(proof_path, root=paths["evidence"])
    )
    if (
        proof["job_id"] != training["job_id"]
        or proof["candidate_sha256"] != training["candidate_sha256"]
        or proof["manifest_sha256"] != training["manifest_sha256"]
        or proof["training_terminal_sha256"] != training["terminal_sha256"]
        or proof["runtime_contract_sha256"]
        != training["runtime_contract_sha256"]
        or proof["benchmark_activity_lease_sha256"]
        != expected_benchmark_activity_lease_sha256
        or proof["adapter"]
        != {
            key: training["adapter"][key]
            for key in (
                "filename",
                "sha256",
                "metadata_filename",
                "metadata_sha256",
                "tensor_count",
                "pair_count",
                "tensor_inventory_sha256",
            )
        }
    ):
        raise ContractError("benchmark proof and training result disagree")
    object_info_path = benchmark_root / "object-info.json"
    control_path = benchmark_root / "control-workflow.json"
    lora_path = benchmark_root / "lora-workflow.json"
    if file_record(object_info_path, root=benchmark_root)["sha256"] != proof[
        "object_info_sha256"
    ]:
        raise ContractError("benchmark object-info artifact drifted")
    object_info = read_json_object(object_info_path, root=benchmark_root)
    control = read_json_object(control_path, root=benchmark_root)
    lora = read_json_object(lora_path, root=benchmark_root)
    if (
        file_record(control_path, root=benchmark_root)["sha256"]
        != proof["arms"][0]["workflow_sha256"]
        or file_record(lora_path, root=benchmark_root)["sha256"]
        != proof["arms"][1]["workflow_sha256"]
    ):
        raise ContractError("benchmark workflow artifact drifted")
    validate_control_workflow(control, training["metadata"], object_info)
    validate_inference_workflow(lora, training["metadata"], object_info)
    for arm in proof["arms"]:
        output_path = benchmark_root / arm["output_file"]
        output = _regular_bytes(
            output_path,
            root=benchmark_root,
            maximum_bytes=50 * 1024 * 1024,
        )
        if (
            {"bytes": len(output), "sha256": sha256_bytes(output)}
            != {
                "bytes": arm["output_bytes"],
                "sha256": arm["output_sha256"],
            }
            or benchmark_png_pixel_sha256(output) != arm["pixel_sha256"]
        ):
            raise ContractError("benchmark PNG artifact drifted")
    return {
        "job_id": training["job_id"],
        "state": "benchmark_passed",
        "blocker_code": None,
        "retry_mode": "none",
        "candidate_sha256": training["candidate_sha256"],
        "runtime_contract_sha256": training["runtime_contract_sha256"],
        "training_activity_lease_sha256": expected_training_activity_lease_sha256,
        "benchmark_activity_lease_sha256": expected_benchmark_activity_lease_sha256,
        "adapter": training["adapter"],
        "proof_sha256": file_record(proof_path, root=paths["evidence"])["sha256"],
        "control": dict(proof["arms"][0]),
        "lora": dict(proof["arms"][1]),
    }


def write_json_new(
    path: Path,
    payload: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> str:
    if root is None:
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        try:
            root_info = root.lstat()
            relative_parent = path.parent.relative_to(root)
        except (OSError, ValueError) as exc:
            raise ContractError("evidence path is outside its owned root") from exc
        if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
            raise ContractError("owned root is not a real directory")
        cursor = root
        for part in relative_parent.parts:
            cursor = cursor / part
            try:
                cursor.mkdir()
            except FileExistsError:
                pass
            try:
                info = cursor.lstat()
            except OSError as exc:
                raise ContractError("owned evidence directory is unavailable") from exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise ContractError("owned evidence directory is not a real directory")
    data = canonical_json_bytes(payload)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        raise ContractError(f"refusing to overwrite immutable evidence: {path.name}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return sha256_bytes(data)


def write_bytes_new(path: Path, data: bytes, *, root: Path) -> str:
    if not isinstance(data, bytes) or not data:
        raise ContractError("immutable artifact bytes are empty")
    try:
        root_info = root.lstat()
        relative_parent = path.parent.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ContractError("artifact path is outside its owned root") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise ContractError("owned root is not a real directory")
    cursor = root
    for part in relative_parent.parts:
        cursor = cursor / part
        try:
            cursor.mkdir()
        except FileExistsError:
            pass
        info = cursor.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ContractError("owned artifact directory is not a real directory")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        raise ContractError(f"refusing to overwrite immutable artifact: {path.name}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return sha256_bytes(data)


def package_digest(root: Path = ROOT) -> str:
    validate_package(root)
    return str(file_record(root / "candidate.json", root=root)["sha256"])


def fixed_child_environment(paths: Mapping[str, Path]) -> dict[str, str]:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    temp = os.environ.get("TEMP", str(paths["root"] / "tmp"))
    return {
        "SystemRoot": system_root,
        "TEMP": temp,
        "TMP": temp,
        "PATH": str(paths["python"].parent) + os.pathsep + str(Path(system_root) / "System32"),
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "SEED": "0",
        "HF_HOME": str(paths["hf_home"]),
        "HF_HUB_CACHE": str(paths["hf_home"] / "hub"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "WANDB_MODE": "disabled",
        "WANDB_DISABLED": "true",
        "TOKENIZERS_PARALLELISM": "false",
    }


def toolkit_command(paths: Mapping[str, Path]) -> list[str]:
    return [
        str(paths["python"]),
        str(paths["toolkit"] / "run.py"),
        str(paths["config"]),
    ]


def classify_failure(return_code: int, output: str) -> str:
    if return_code == 0:
        raise ContractError("a successful process cannot be classified as a failure")
    lowered = output.lower()
    if any(marker in lowered for marker in ("cuda out of memory", "outofmemoryerror", "cublas_status_alloc_failed")):
        return "training_oom"
    return "training_failed"
