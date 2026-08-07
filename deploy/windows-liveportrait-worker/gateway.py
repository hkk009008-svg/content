#!/usr/bin/env python3
"""Bearer-authenticated proxy for a loopback-only ComfyUI worker."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import struct
import time
import types
from typing import Any
from urllib.parse import urlsplit
import uuid

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
WORKER_ROLE = "performance-liveportrait"
CAPABILITY_SCHEMA_VERSION = 1
IMAGE_CAPABILITY = "image-flux2-klein"
IMAGE_BLOCKER_CODE = "candidate_artifacts_not_installed"
FLUX2_BENCHMARK_REFERENCE_COUNTS = (1, 2, 4)
LORA_SCHEMA_VERSION = 1
LORA_CANARY_CONTRACT = "flux2-klein-character-lora-canary-v1"
LORA_TRIGGER_TOKEN = "hkkperson"
LORA_REFERENCE_CAPTIONS = tuple(
    f"portrait photograph of hkkperson person, identity reference view {index}"
    for index in range(1, 5)
)
LORA_MAX_BLOB_BYTES = 20 * 1024 * 1024
LORA_MAX_JSON_BYTES = 8 * 1024
LORA_MAX_ADAPTER_BYTES = 1024 * 1024 * 1024
LORA_MIN_FREE_VRAM_BYTES = 13_500 * 1024 * 1024
LORA_BLOCKING_STATES = {
    "starting",
    "running",
    "benchmarking",
    "unknown",
    "interrupted",
}
LORA_ACTIVITY_TYPES = {"training", "benchmark", "prompt"}
LORA_RETRY_MODES = {"none", "initial", "checkpoint", "benchmark"}
LORA_PACKAGE_FILES = frozenset(
    {
        "README.md",
        "Install-Candidate.ps1",
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
LORA_STATES = LORA_BLOCKING_STATES | {
    "succeeded",
    "failed",
    "interrupted",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
# Exact reviewed source-package identity. These values intentionally remain
# static until a reviewed candidate update changes both the application-side
# validator and this gateway contract.
FLUX2_PACKAGE_FIELDS = {
    "capability": IMAGE_CAPABILITY,
    "candidate_manifest_sha256": "02f2cc195cf2537c220ae385ef012d038ff46d4f39f2b007280bb7ef2fdf95f7",
    "workflow_sha256": "f05cd319099ea0c07be6bf6bb8953cea345af154b4b23a86f08c06e180c30148",
    "model_manifest_sha256": "f35145f0fdc8d35a810b6905ccfc9358baa18d86c3abdfac23b373fd7e95018f",
    "revisions_manifest_sha256": "a2dd0f168cd711985bb041beb1ad6fa2ee0fe6536bb216805700fe573dd5e12f",
    "contract_digest": "97d59ef8400cf199737e1d7d9e4b417874c97d79f667079f323b5aad2490ad1a",
}
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class GatewayConfigError(ValueError):
    """The gateway cannot enforce the worker exposure contract."""


def validate_token(value: str) -> str:
    token = value.strip()
    if token.lower().startswith("bearer "):
        raise GatewayConfigError("COMFYUI_API_KEY must be the token only")
    if len(token) < 32:
        raise GatewayConfigError("COMFYUI_API_KEY must contain at least 32 characters")
    if token.lower() in {"changeme", "replace-me", "placeholder"}:
        raise GatewayConfigError("COMFYUI_API_KEY contains a placeholder")
    return token


def validate_upstream(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        raise GatewayConfigError("gateway upstream must be loopback HTTP")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise GatewayConfigError("gateway upstream contains forbidden URL data")
    return value.rstrip("/")


def validate_listen(value: str) -> str:
    if value not in {"127.0.0.1", "::1"}:
        raise GatewayConfigError("gateway listener must be loopback-only")
    return value


def filtered_headers(headers: Any, *, response: bool = False) -> dict[str, str]:
    blocked = set(HOP_BY_HOP) | {"host", "authorization"}
    if not response:
        blocked.add("content-length")
    return {key: value for key, value in headers.items() if key.lower() not in blocked}


def _canonical_json(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _json_without_duplicate_keys(raw: bytes) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(_canonical_json(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _atomic_bytes(path: Path, data: bytes) -> None:
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        with contextlib.suppress(OSError):
            temporary.chmod(0o400)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _private_directory(path: Path, *, create: bool = False) -> Path:
    if create:
        path.mkdir(parents=True, exist_ok=True)
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(path, "is_junction", lambda: False)()
        or not stat.S_ISDIR(info.st_mode)
    ):
        raise GatewayConfigError("LoRA state contains an unsafe directory")
    return path.resolve()


def _read_regular_file(path: Path, *, maximum: int) -> bytes:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("unsafe file")
    if before.st_size <= 0 or before.st_size > maximum:
        raise ValueError("invalid file size")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not os.path.samestat(before, opened):
            raise ValueError("file changed before open")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    finally:
        os.close(descriptor)
    after = path.lstat()
    if not os.path.samestat(opened, after) or len(data) != opened.st_size:
        raise ValueError("file changed while reading")
    if not data or len(data) > maximum:
        raise ValueError("invalid file size")
    return data


def _digest_regular_file(path: Path, *, maximum: int) -> tuple[str, int]:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("unsafe file")
    if before.st_size <= 0 or before.st_size > maximum:
        raise ValueError("invalid file size")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    total = 0
    try:
        opened = os.fstat(descriptor)
        if not os.path.samestat(before, opened):
            raise ValueError("file changed before open")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise ValueError("invalid file size")
            digest.update(chunk)
    finally:
        os.close(descriptor)
    after = path.lstat()
    if not os.path.samestat(opened, after) or total != opened.st_size:
        raise ValueError("file changed while reading")
    return digest.hexdigest(), total


def _validate_png(payload: bytes) -> None:
    if (
        len(payload) < 33
        or payload[:8] != b"\x89PNG\r\n\x1a\n"
        or payload[12:16] != b"IHDR"
    ):
        raise ValueError("invalid PNG")
    width, height = struct.unpack(">II", payload[16:24])
    if (
        not 256 <= width <= 8192
        or not 256 <= height <= 8192
        or width * height > 20_000_000
    ):
        raise ValueError("invalid PNG dimensions")


class AuthenticatedGateway:
    def __init__(
        self,
        *,
        upstream: str,
        token: str,
        sentinel: Path,
        revisions: Path,
        models: Path,
        probe_contract: Path,
        flux2_state_root: Path | None = None,
        lora_state_root: Path | None = None,
        lora_python: Path | None = None,
        lora_runner: Path | None = None,
        lora_comfy_root: Path | None = None,
        lora_candidate_sha256: str | None = None,
        lora_process_death_guaranteed: bool = False,
    ) -> None:
        self.upstream = validate_upstream(upstream)
        self.token = validate_token(token)
        self.sentinel = sentinel
        self.revisions = revisions
        self.models = models
        self.probe_contract = probe_contract
        self.flux2_state_root = flux2_state_root.resolve() if flux2_state_root else None
        self.session: ClientSession | None = None
        self._lora_lock = asyncio.Lock()
        self._lora_process: asyncio.subprocess.Process | None = None
        self._lora_watch_task: asyncio.Task[None] | None = None
        self._lora_state_invalid = False
        self._orphan_prompt_lease_sha256: str | None = None
        self._lora_contract: types.ModuleType | None = None
        self.lora_state_root: Path | None = None
        self.lora_python: Path | None = None
        self.lora_runner: Path | None = None
        self.lora_comfy_root: Path | None = None
        self.lora_candidate_sha256: str | None = None
        self.lora_program_files: Path | None = None
        self.lora_process_death_guaranteed = bool(lora_process_death_guaranteed)
        configured = (
            lora_state_root,
            lora_python,
            lora_runner,
            lora_comfy_root,
            lora_candidate_sha256,
        )
        if any(value is not None for value in configured):
            if any(value is None for value in configured):
                raise GatewayConfigError("LoRA gateway configuration is incomplete")
            assert lora_state_root is not None
            assert lora_python is not None
            assert lora_runner is not None
            assert lora_comfy_root is not None
            assert lora_candidate_sha256 is not None
            if not _SHA256_RE.fullmatch(lora_candidate_sha256):
                raise GatewayConfigError("LoRA candidate digest is invalid")
            if not lora_state_root.is_absolute() or not lora_comfy_root.is_absolute():
                raise GatewayConfigError("LoRA roots must be absolute")
            if (
                flux2_state_root is None
                or not flux2_state_root.is_absolute()
                or self.flux2_state_root is None
                or self.flux2_state_root.name != "ContentFlux2Klein"
            ):
                raise GatewayConfigError(
                    "LoRA training requires the fixed FLUX.2 installation root"
                )
            program_data = os.environ.get("PROGRAMDATA")
            if not program_data or not Path(program_data).is_absolute():
                raise GatewayConfigError("PROGRAMDATA is unavailable for LoRA state")
            program_files = os.environ.get("ProgramFiles")
            if not program_files or not Path(program_files).is_absolute():
                raise GatewayConfigError("ProgramFiles is unavailable for LoRA training")
            expected_state_root = (
                Path(program_data) / "Content" / "IdentityLab" / "flux2-lora"
            ).resolve()
            if lora_state_root.resolve() != expected_state_root:
                raise GatewayConfigError("LoRA state root drifted from the fixed package path")
            for executable in (lora_python, lora_runner):
                if not executable.is_absolute():
                    raise GatewayConfigError("LoRA executable paths must be absolute")
                info = executable.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    raise GatewayConfigError("LoRA executable path is unsafe")
            self.lora_state_root = _private_directory(lora_state_root, create=True)
            self.lora_python = lora_python.resolve()
            self.lora_runner = lora_runner.resolve()
            self.lora_comfy_root = _private_directory(lora_comfy_root, create=True)
            self.lora_candidate_sha256 = lora_candidate_sha256
            self.lora_program_files = Path(program_files).resolve()
            if self.lora_python != (
                self.lora_state_root / "runtime" / "venv" / "Scripts" / "python.exe"
            ) or self.lora_runner != self.lora_state_root / "package" / "train.py":
                raise GatewayConfigError("LoRA executable paths drifted from the installed package")
            for directory in (
                self.lora_state_root / "runtime",
                self.lora_state_root / "runtime" / "venv",
                self.lora_state_root / "runtime" / "venv" / "Scripts",
                self.lora_state_root / "package",
            ):
                _private_directory(directory)
            _private_directory(self.lora_state_root / "blobs", create=True)
            _private_directory(self.lora_state_root / "jobs", create=True)
            _private_directory(self.lora_state_root / "locks", create=True)
            _private_directory(self.lora_state_root / "tmp", create=True)
            self._validate_lora_package()

    async def start(self, _app: web.Application) -> None:
        if self.lora_state_root is not None:
            try:
                self._recover_lora_jobs()
            except (OSError, ValueError, GatewayConfigError):
                self._lora_state_invalid = True
        self.session = ClientSession(
            timeout=ClientTimeout(total=None, sock_connect=10, sock_read=None),
            auto_decompress=False,
            trust_env=False,
        )
        if self.lora_state_root is not None and not self._lora_state_invalid:
            try:
                await self._reconcile_orphan_prompt_activity(startup=True)
            except (OSError, ValueError, GatewayConfigError):
                self._lora_state_invalid = True

    async def stop(self, _app: web.Application) -> None:
        if self.session is not None:
            await self.session.close()

    @staticmethod
    def _lora_error(code: str, status: int) -> web.Response:
        return web.json_response({"error": code}, status=status)

    def _lora_configured(self) -> bool:
        return (
            self.lora_state_root is not None
            and self.lora_python is not None
            and self.lora_runner is not None
            and self.lora_comfy_root is not None
            and self.lora_candidate_sha256 is not None
            and not self._lora_state_invalid
        )

    def _validate_lora_package(self) -> str:
        if self.lora_runner is None or self.lora_candidate_sha256 is None:
            raise GatewayConfigError("LoRA package is not configured")
        package_root = _private_directory(self.lora_runner.parent)
        if self.lora_runner != package_root / "train.py":
            raise GatewayConfigError("LoRA runner is not the candidate train.py")
        actual: set[str] = set()
        for path in package_root.rglob("*"):
            relative = path.relative_to(package_root)
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(
                path, "is_junction", lambda: False
            )():
                raise GatewayConfigError("LoRA package contains a link")
            if stat.S_ISREG(info.st_mode):
                actual.add(relative.as_posix())
            else:
                raise GatewayConfigError("LoRA package contains an unexpected entry")
        if actual != LORA_PACKAGE_FILES:
            raise GatewayConfigError("LoRA package inventory drifted")
        candidate_bytes = _read_regular_file(
            package_root / "candidate.json", maximum=1024 * 1024
        )
        candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
        if not hmac.compare_digest(candidate_sha256, self.lora_candidate_sha256):
            raise GatewayConfigError("LoRA candidate digest drifted")
        try:
            candidate = _json_without_duplicate_keys(candidate_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise GatewayConfigError("LoRA candidate manifest is invalid") from exc
        if (
            not isinstance(candidate, dict)
            or set(candidate)
            != {
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
            }
            or type(candidate.get("schema_version")) is not int
            or candidate.get("schema_version") != 1
            or candidate.get("capability") != "identity-flux2-klein-lora"
            or candidate.get("candidate_state") != "not_installed"
        ):
            raise GatewayConfigError("LoRA candidate identity drifted")
        bindings = candidate.get("bindings")
        expected_bindings = LORA_PACKAGE_FILES - {"candidate.json"}
        if not isinstance(bindings, dict) or set(bindings) != expected_bindings:
            raise GatewayConfigError("LoRA package bindings drifted")
        for relative in expected_bindings:
            expected = bindings.get(relative)
            if (
                not isinstance(expected, str)
                or not _SHA256_RE.fullmatch(expected)
                or _digest_regular_file(
                    package_root / relative, maximum=16 * 1024 * 1024
                )[0]
                != expected
            ):
                raise GatewayConfigError("LoRA package file hash drifted")
        if self._lora_contract is None:
            contract_path = package_root / "contract.py"
            contract_source = _read_regular_file(
                contract_path, maximum=16 * 1024 * 1024
            )
            if not hmac.compare_digest(
                hashlib.sha256(contract_source).hexdigest(),
                str(bindings["contract.py"]),
            ):
                raise GatewayConfigError("LoRA contract changed while loading")
            module = types.ModuleType("_content_identity_lora_contract")
            module.__file__ = str(contract_path)
            module.__package__ = ""
            try:
                exec(
                    compile(contract_source, str(contract_path), "exec"),
                    module.__dict__,
                )
            except Exception as exc:
                raise GatewayConfigError("LoRA contract cannot be loaded") from exc
            self._lora_contract = module
        required = {
            "validate_package",
            "package_digest",
            "validate_gateway_admission",
            "validate_gateway_training_result",
            "validate_gateway_benchmark_result",
            "validate_lora_safetensors",
            "validate_adapter_file",
        }
        if any(not callable(getattr(self._lora_contract, name, None)) for name in required):
            raise GatewayConfigError("LoRA contract API is incomplete")
        try:
            self._lora_contract.validate_package(package_root)
            contract_digest = self._lora_contract.package_digest(package_root)
        except Exception as exc:
            raise GatewayConfigError("LoRA package contract rejected the install") from exc
        if not hmac.compare_digest(str(contract_digest), candidate_sha256):
            raise GatewayConfigError("LoRA package contract digest drifted")
        return candidate_sha256

    def _call_lora_contract(self, name: str, *args: object, **kwargs: object) -> dict[str, Any]:
        self._validate_lora_package()
        assert self._lora_contract is not None
        function = getattr(self._lora_contract, name)
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            raise ValueError(f"LoRA contract rejected {name}") from exc
        if not isinstance(result, dict):
            raise ValueError("LoRA contract returned an invalid projection")
        return result

    async def _limited_body(self, request: web.Request, maximum: int) -> bytes:
        length = request.content_length
        if length is not None and (length < 0 or length > maximum):
            raise OverflowError("request too large")
        chunks: list[bytes] = []
        total = 0
        async for chunk in request.content.iter_chunked(min(1024 * 1024, maximum + 1)):
            total += len(chunk)
            if total > maximum:
                raise OverflowError("request too large")
            chunks.append(bytes(chunk))
        return b"".join(chunks)

    def _lora_job_dir(self, job_id: str, *, required: bool) -> Path:
        if not _JOB_ID_RE.fullmatch(job_id) or self.lora_state_root is None:
            raise ValueError("invalid job")
        jobs = _private_directory(self.lora_state_root / "jobs")
        path = jobs / job_id
        if not path.exists():
            if required:
                raise FileNotFoundError(job_id)
            return path
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("unsafe job")
        if path.resolve().parent != jobs:
            raise ValueError("unsafe job")
        return path

    @staticmethod
    def _validate_lora_manifest(payload: object) -> dict[str, object]:
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version",
            "contract",
            "candidate_sha256",
            "consent",
            "references",
        }:
            raise ValueError("invalid manifest")
        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] != LORA_SCHEMA_VERSION
            or payload["contract"] != LORA_CANARY_CONTRACT
            or payload["consent"] is not True
            or not isinstance(payload["candidate_sha256"], str)
            or not _SHA256_RE.fullmatch(payload["candidate_sha256"])
        ):
            raise ValueError("invalid manifest")
        references = payload["references"]
        if not isinstance(references, list) or len(references) != 4:
            raise ValueError("invalid references")
        normalized: list[dict[str, str]] = []
        hashes: set[str] = set()
        for index, reference in enumerate(references):
            if not isinstance(reference, dict) or set(reference) != {"sha256", "caption"}:
                raise ValueError("invalid reference")
            digest = reference.get("sha256")
            caption = reference.get("caption")
            if (
                not isinstance(digest, str)
                or not _SHA256_RE.fullmatch(digest)
                or not isinstance(caption, str)
                or caption != LORA_REFERENCE_CAPTIONS[index]
                or digest in hashes
            ):
                raise ValueError("invalid reference")
            hashes.add(digest)
            normalized.append({"sha256": digest, "caption": caption})
        return {
            "schema_version": LORA_SCHEMA_VERSION,
            "contract": LORA_CANARY_CONTRACT,
            "candidate_sha256": payload["candidate_sha256"],
            "consent": True,
            "references": normalized,
        }

    def _load_lora_json(self, path: Path, *, maximum: int = LORA_MAX_JSON_BYTES) -> object:
        return _json_without_duplicate_keys(_read_regular_file(path, maximum=maximum))

    def _validate_lora_state(self, payload: object, job_id: str) -> dict[str, object]:
        keys = {
            "schema_version",
            "job_id",
            "contract",
            "candidate_sha256",
            "manifest_sha256",
            "state",
            "retriable",
            "retry_mode",
            "created_at_unix",
            "updated_at_unix",
            "started_at_unix",
            "completed_at_unix",
            "exit_code",
            "blocker_code",
            "attempt_index",
            "benchmark_attempt_index",
            "activity_lease_sha256",
            "execution_activity_lease_sha256",
            "benchmark_activity_lease_sha256",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("invalid state")
        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] != LORA_SCHEMA_VERSION
            or payload["job_id"] != job_id
            or payload["contract"] != LORA_CANARY_CONTRACT
            or payload["state"] not in LORA_STATES
            or type(payload["retriable"]) is not bool
            or payload["retry_mode"] not in LORA_RETRY_MODES
            or payload["retriable"] is not (payload["retry_mode"] != "none")
            or (
                payload["retry_mode"] != "none"
                and payload["state"] not in {"failed", "interrupted"}
            )
            or not isinstance(payload["candidate_sha256"], str)
            or not _SHA256_RE.fullmatch(payload["candidate_sha256"])
            or not isinstance(payload["manifest_sha256"], str)
            or not _SHA256_RE.fullmatch(payload["manifest_sha256"])
            or type(payload["created_at_unix"]) is not int
            or type(payload["updated_at_unix"]) is not int
            or type(payload["attempt_index"]) is not int
            or payload["attempt_index"] not in {1, 2}
            or type(payload["benchmark_attempt_index"]) is not int
            or payload["benchmark_attempt_index"] not in {0, 1, 2}
            or not isinstance(payload["blocker_code"], str)
            or (
                payload["activity_lease_sha256"] is not None
                and (
                    not isinstance(payload["activity_lease_sha256"], str)
                    or not _SHA256_RE.fullmatch(payload["activity_lease_sha256"])
                )
            )
            or not isinstance(payload["execution_activity_lease_sha256"], str)
            or not _SHA256_RE.fullmatch(payload["execution_activity_lease_sha256"])
            or (
                payload["benchmark_activity_lease_sha256"] is not None
                and (
                    not isinstance(
                        payload["benchmark_activity_lease_sha256"], str
                    )
                    or not _SHA256_RE.fullmatch(
                        payload["benchmark_activity_lease_sha256"]
                    )
                )
            )
        ):
            raise ValueError("invalid state")
        for key in ("started_at_unix", "completed_at_unix", "exit_code"):
            if payload[key] is not None and type(payload[key]) is not int:
                raise ValueError("invalid state")
        return dict(payload)

    def _load_lora_state(self, job_dir: Path) -> dict[str, object]:
        return self._validate_lora_state(
            self._load_lora_json(job_dir / "state.json"), job_dir.name
        )

    @staticmethod
    def _public_lora_state(state: dict[str, object]) -> dict[str, object]:
        return {
            key: state[key]
            for key in (
                "schema_version",
                "job_id",
                "contract",
                "candidate_sha256",
                "manifest_sha256",
                "state",
                "retriable",
                "retry_mode",
                "created_at_unix",
                "updated_at_unix",
                "started_at_unix",
                "completed_at_unix",
                "exit_code",
                "blocker_code",
            )
        }

    def _write_lora_state(self, job_dir: Path, state: dict[str, object]) -> None:
        checked = self._validate_lora_state(state, job_dir.name)
        _atomic_json(job_dir / "state.json", checked)

    def _lora_job_directories(self) -> list[Path]:
        if self.lora_state_root is None:
            return []
        jobs = _private_directory(self.lora_state_root / "jobs")
        result: list[Path] = []
        for path in jobs.iterdir():
            info = path.lstat()
            if (
                not _JOB_ID_RE.fullmatch(path.name)
                or stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
            ):
                raise ValueError("unsafe job state")
            result.append(path)
        return result

    def _blocking_lora_job(self, *, exclude: str | None = None) -> str | None:
        for job_dir in self._lora_job_directories():
            if job_dir.name == exclude:
                continue
            state = self._load_lora_state(job_dir)
            if state["state"] in LORA_BLOCKING_STATES:
                return job_dir.name
        return None

    def _try_acquire_lora_activity(self, activity: str, job_id: str) -> str | None:
        if (
            self.lora_state_root is None
            or activity not in LORA_ACTIVITY_TYPES
            or not _JOB_ID_RE.fullmatch(job_id)
        ):
            raise ValueError("invalid GPU activity lease")
        locks = _private_directory(self.lora_state_root / "locks")
        path = locks / "gateway-activity.lock"
        payload = _canonical_json(
            {
                "schema_version": 1,
                "capability": "identity-flux2-klein-lora",
                "activity": activity,
                "job_id": job_id,
                "owner_pid": os.getpid(),
                "nonce": uuid.uuid4().hex,
            }
        )
        try:
            with path.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            return None
        return hashlib.sha256(payload).hexdigest()

    def _release_lora_activity(self, expected_sha256: str) -> None:
        if self.lora_state_root is None or not _SHA256_RE.fullmatch(expected_sha256):
            raise ValueError("invalid GPU activity lease digest")
        path = _private_directory(self.lora_state_root / "locks") / "gateway-activity.lock"
        try:
            payload = _read_regular_file(path, maximum=LORA_MAX_JSON_BYTES)
        except FileNotFoundError:
            return
        if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), expected_sha256):
            raise ValueError("GPU activity lease ownership mismatch")
        path.unlink()

    def _require_owned_lora_activity(
        self, expected_sha256: str, activity: str, job_id: str
    ) -> None:
        if self.lora_state_root is None:
            raise ValueError("GPU activity lease is unavailable")
        payload = _read_regular_file(
            _private_directory(self.lora_state_root / "locks")
            / "gateway-activity.lock",
            maximum=LORA_MAX_JSON_BYTES,
        )
        record = _json_without_duplicate_keys(payload)
        if (
            hashlib.sha256(payload).hexdigest() != expected_sha256
            or not isinstance(record, dict)
            or payload != _canonical_json(record)
            or set(record)
            != {
                "schema_version",
                "capability",
                "activity",
                "job_id",
                "owner_pid",
                "nonce",
            }
            or type(record.get("schema_version")) is not int
            or record.get("schema_version") != 1
            or record.get("capability") != "identity-flux2-klein-lora"
            or record.get("activity") != activity
            or record.get("job_id") != job_id
            or type(record.get("owner_pid")) is not int
            or record.get("owner_pid") != os.getpid()
            or not _JOB_ID_RE.fullmatch(str(record.get("nonce")))
        ):
            raise ValueError("GPU activity lease binding mismatch")

    async def _reconcile_orphan_prompt_activity(
        self, *, startup: bool = False
    ) -> None:
        if self.lora_state_root is None:
            return
        path = _private_directory(self.lora_state_root / "locks") / "gateway-activity.lock"
        try:
            raw = _read_regular_file(path, maximum=LORA_MAX_JSON_BYTES)
        except FileNotFoundError:
            return
        record = _json_without_duplicate_keys(raw)
        if (
            not isinstance(record, dict)
            or raw != _canonical_json(record)
            or set(record)
            != {
                "schema_version",
                "capability",
                "activity",
                "job_id",
                "owner_pid",
                "nonce",
            }
            or type(record.get("schema_version")) is not int
            or record.get("schema_version") != 1
            or record.get("capability") != "identity-flux2-klein-lora"
            or not _JOB_ID_RE.fullmatch(str(record.get("job_id")))
            or not _JOB_ID_RE.fullmatch(str(record.get("nonce")))
        ):
            raise ValueError("GPU activity lease is malformed")
        if record.get("activity") != "prompt":
            return
        owner_pid = record.get("owner_pid")
        if type(owner_pid) is not int or owner_pid <= 0:
            raise ValueError("prompt activity lease owner is invalid")
        digest = hashlib.sha256(raw).hexdigest()
        if startup:
            self._orphan_prompt_lease_sha256 = digest
        elif owner_pid == os.getpid() and digest != self._orphan_prompt_lease_sha256:
            return
        if await self._comfy_queue_empty() is True:
            self._release_lora_activity(digest)
            self._orphan_prompt_lease_sha256 = None

    def _recover_lora_jobs(self) -> None:
        now = int(time.time())
        for job_dir in self._lora_job_directories():
            state = self._load_lora_state(job_dir)
            lease_sha256 = state["activity_lease_sha256"]
            active_state = str(state["state"])
            if active_state not in {"starting", "running", "benchmarking"}:
                if lease_sha256 is not None and state["state"] in {
                    "succeeded",
                    "failed",
                    "interrupted",
                }:
                    self._release_lora_activity(str(lease_sha256))
                    state["activity_lease_sha256"] = None
                    self._write_lora_state(job_dir, state)
                continue
            if lease_sha256 is None:
                raise ValueError("active job lacks its GPU activity lease")
            if not self.lora_process_death_guaranteed:
                state["state"] = "unknown"
                state["retriable"] = False
                state["retry_mode"] = "none"
                state["blocker_code"] = "process_state_unknown"
                state["updated_at_unix"] = now
                state["completed_at_unix"] = now
                state["exit_code"] = None
                self._write_lora_state(job_dir, state)
                continue

            release_lease = False
            if active_state == "benchmarking":
                try:
                    result = self._lora_benchmark_result(job_dir, state)
                except ValueError:
                    state["state"] = "unknown"
                    state["retriable"] = False
                    state["retry_mode"] = "none"
                    state["blocker_code"] = "benchmark_restart_outcome_unknown"
                else:
                    outcome = str(result["state"])
                    if outcome == "benchmark_passed":
                        state["state"] = "succeeded"
                        state["retriable"] = False
                        state["retry_mode"] = "none"
                        state["blocker_code"] = ""
                        release_lease = True
                    elif outcome == "benchmark_not_run":
                        retry = state["benchmark_attempt_index"] < 2
                        state["state"] = "failed"
                        state["retriable"] = retry
                        state["retry_mode"] = "benchmark" if retry else "none"
                        state["blocker_code"] = "gateway_restarted_before_benchmark_submission"
                        release_lease = True
                    elif outcome == "benchmark_failed":
                        state["state"] = "failed"
                        state["retriable"] = False
                        state["retry_mode"] = "none"
                        state["blocker_code"] = str(
                            result.get("blocker_code") or "benchmark_failed"
                        )
                        release_lease = True
                    else:
                        state["state"] = "unknown"
                        state["retriable"] = False
                        state["retry_mode"] = "none"
                        state["blocker_code"] = str(
                            result.get("blocker_code")
                            or "benchmark_restart_outcome_unknown"
                        )
            else:
                try:
                    result = self._lora_training_result(job_dir, state)
                except ValueError:
                    state["state"] = "unknown"
                    state["retriable"] = False
                    state["retry_mode"] = "none"
                    state["blocker_code"] = "training_restart_outcome_unknown"
                else:
                    outcome = str(result["state"])
                    retry_mode = str(result["retry_mode"])
                    if outcome == "training_passed":
                        self._finish_lora_training(job_dir, state)
                        state["state"] = "failed"
                        state["retriable"] = True
                        state["retry_mode"] = "benchmark"
                        state["blocker_code"] = "benchmark_not_started"
                        release_lease = True
                    elif outcome in {"not_started", "interrupted"}:
                        if state["attempt_index"] != 1:
                            retry_mode = "none"
                        state["state"] = "interrupted"
                        state["retriable"] = retry_mode != "none"
                        state["retry_mode"] = retry_mode
                        state["blocker_code"] = (
                            "gateway_restarted_before_training_start"
                            if retry_mode == "initial"
                            else "gateway_restarted_after_training_start"
                        )
                        release_lease = True
                    elif outcome == "training_failed":
                        state["state"] = "failed"
                        state["retriable"] = False
                        state["retry_mode"] = "none"
                        state["blocker_code"] = str(
                            result.get("blocker_code") or "training_failed"
                        )
                        release_lease = True
                    else:
                        state["state"] = "unknown"
                        state["retriable"] = False
                        state["retry_mode"] = "none"
                        state["blocker_code"] = str(
                            result.get("blocker_code")
                            or "training_restart_outcome_unknown"
                        )

            if release_lease:
                self._release_lora_activity(str(lease_sha256))
                state["activity_lease_sha256"] = None
            state["updated_at_unix"] = now
            state["completed_at_unix"] = now
            state["exit_code"] = None
            self._write_lora_state(job_dir, state)

    def _lora_training_result(
        self,
        job_dir: Path,
        state: dict[str, object],
        *,
        published: bool = False,
    ) -> dict[str, Any]:
        assert self.lora_state_root is not None
        result = self._call_lora_contract(
            "validate_gateway_training_result",
            self.lora_state_root,
            job_dir.name,
            expected_activity_lease_sha256=str(
                state["execution_activity_lease_sha256"]
            ),
            comfy_lora_root=self.lora_comfy_root if published else None,
        )
        if (
            result.get("job_id") != job_dir.name
            or result.get("candidate_sha256") != state["candidate_sha256"]
            or result.get("manifest_sha256") != state["manifest_sha256"]
            or result.get("state")
            not in {
                "not_started",
                "interrupted",
                "training_failed",
                "training_unknown",
                "training_passed",
            }
            or result.get("retry_mode")
            not in {"none", "initial", "checkpoint"}
        ):
            raise ValueError("training result projection mismatch")
        return result

    def _lora_benchmark_result(
        self, job_dir: Path, state: dict[str, object]
    ) -> dict[str, Any]:
        assert self.lora_state_root is not None
        benchmark_lease = state.get("benchmark_activity_lease_sha256")
        if not isinstance(benchmark_lease, str):
            raise ValueError("benchmark lease binding is absent")
        result = self._call_lora_contract(
            "validate_gateway_benchmark_result",
            self.lora_state_root,
            job_dir.name,
            expected_training_activity_lease_sha256=str(
                state["execution_activity_lease_sha256"]
            ),
            expected_benchmark_activity_lease_sha256=benchmark_lease,
            comfy_lora_root=self.lora_comfy_root,
        )
        if (
            result.get("job_id") != job_dir.name
            or result.get("candidate_sha256") != state["candidate_sha256"]
            or result.get("state")
            not in {
                "benchmark_not_run",
                "benchmark_failed",
                "benchmark_unknown",
                "benchmark_passed",
            }
            or result.get("retry_mode") not in {"none", "benchmark"}
        ):
            raise ValueError("benchmark result projection mismatch")
        return result

    async def _comfy_queue_empty(self) -> bool | None:
        if self.session is None:
            return None
        try:
            async with self.session.get(self.upstream + "/queue") as response:
                payload = await response.json() if response.status == 200 else None
        except Exception:
            return None
        if not isinstance(payload, dict) or set(payload) != {
            "queue_running",
            "queue_pending",
        }:
            return None
        running = payload.get("queue_running")
        pending = payload.get("queue_pending")
        if not isinstance(running, list) or not isinstance(pending, list):
            return None
        return not running and not pending

    async def _free_comfy_models(self) -> bool:
        if self.session is None:
            return False
        try:
            async with self.session.post(
                self.upstream + "/free",
                json={"unload_models": True, "free_memory": True},
                timeout=ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    return False
        except Exception:
            return False

        async def wait_until_released() -> bool:
            assert self.session is not None
            while True:
                try:
                    async with self.session.get(
                        self.upstream + "/system_stats",
                        timeout=ClientTimeout(total=2),
                    ) as response:
                        stats = await response.json() if response.status == 200 else None
                except Exception:
                    return False
                if not isinstance(stats, dict) or not isinstance(
                    stats.get("system"), dict
                ):
                    return False
                devices = stats.get("devices")
                if not isinstance(devices, list):
                    return False
                cuda = [
                    device
                    for device in devices
                    if isinstance(device, dict)
                    and device.get("type") == "cuda"
                    and device.get("index") == 0
                ]
                if len(cuda) != 1:
                    return False
                total = cuda[0].get("vram_total")
                free = cuda[0].get("vram_free")
                if (
                    type(total) is not int
                    or type(free) is not int
                    or total < 15_000 * 1024 * 1024
                    or free <= 0
                    or free > total
                ):
                    return False
                if await self._comfy_queue_empty() is not True:
                    return False
                if free >= LORA_MIN_FREE_VRAM_BYTES:
                    return True
                await asyncio.sleep(0.25)

        try:
            return await asyncio.wait_for(wait_until_released(), timeout=15)
        except TimeoutError:
            return False

    async def lora_put_blob(self, request: web.Request) -> web.Response:
        if not self._lora_configured():
            return self._lora_error("identity_lora_unavailable", 503)
        digest = request.match_info.get("sha256", "")
        if not _SHA256_RE.fullmatch(digest):
            return self._lora_error("invalid_blob_id", 404)
        if request.content_type != "application/octet-stream":
            return self._lora_error("unsupported_media_type", 415)
        try:
            body = await self._limited_body(request, LORA_MAX_BLOB_BYTES)
        except OverflowError:
            return self._lora_error("blob_too_large", 413)
        if not body or not hmac.compare_digest(hashlib.sha256(body).hexdigest(), digest):
            return self._lora_error("blob_digest_mismatch", 422)
        assert self.lora_state_root is not None
        async with self._lora_lock:
            try:
                blobs = _private_directory(self.lora_state_root / "blobs")
                destination = blobs / f"{digest}.blob"
                if destination.exists() or destination.is_symlink():
                    existing = _read_regular_file(
                        destination, maximum=LORA_MAX_BLOB_BYTES
                    )
                    if not hmac.compare_digest(hashlib.sha256(existing).hexdigest(), digest):
                        raise ValueError("stored blob mismatch")
                    state = "present"
                    size = len(existing)
                else:
                    _atomic_bytes(destination, body)
                    state = "stored"
                    size = len(body)
            except (OSError, ValueError, GatewayConfigError):
                self._lora_state_invalid = True
                return self._lora_error("identity_lora_state_invalid", 503)
        return web.json_response(
            {
                "schema_version": LORA_SCHEMA_VERSION,
                "sha256": digest,
                "size_bytes": size,
                "state": state,
            },
            status=201 if state == "stored" else 200,
        )

    async def _lora_manifest_request(
        self, request: web.Request
    ) -> tuple[dict[str, object] | None, web.Response | None]:
        if request.content_type != "application/json":
            return None, self._lora_error("unsupported_media_type", 415)
        try:
            raw = await self._limited_body(request, LORA_MAX_JSON_BYTES)
            payload = _json_without_duplicate_keys(raw)
            manifest = self._validate_lora_manifest(payload)
        except OverflowError:
            return None, self._lora_error("request_too_large", 413)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None, self._lora_error("invalid_manifest", 400)
        if manifest["candidate_sha256"] != self.lora_candidate_sha256:
            return None, self._lora_error("candidate_contract_mismatch", 409)
        return manifest, None

    def _read_lora_manifest(self, job_dir: Path) -> dict[str, object]:
        manifest = self._validate_lora_manifest(
            self._load_lora_json(job_dir / "manifest.json")
        )
        return manifest

    def _blob_bytes(self, digest: str) -> bytes:
        assert self.lora_state_root is not None
        blobs = _private_directory(self.lora_state_root / "blobs")
        path = blobs / f"{digest}.blob"
        data = _read_regular_file(path, maximum=LORA_MAX_BLOB_BYTES)
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), digest):
            raise ValueError("blob mismatch")
        return data

    def _create_lora_job_files(
        self,
        job_dir: Path,
        manifest: dict[str, object],
        manifest_sha256: str,
        references: list[bytes],
        activity_lease_sha256: str,
    ) -> dict[str, object]:
        job_dir.mkdir()
        inputs = _private_directory(job_dir / "input", create=True)
        reference_records = manifest["references"]
        assert isinstance(reference_records, list)
        input_references: list[dict[str, object]] = []
        for index, (record, data) in enumerate(zip(reference_records, references), 1):
            assert isinstance(record, dict)
            stem = f"reference-{index:02d}"
            image_name = f"{stem}.png"
            caption_name = f"{stem}.txt"
            caption = str(record["caption"]).encode("utf-8")
            _atomic_bytes(inputs / image_name, data)
            _atomic_bytes(inputs / caption_name, caption)
            input_references.append(
                {
                    "image": image_name,
                    "image_bytes": len(data),
                    "image_sha256": str(record["sha256"]),
                    "caption": caption_name,
                    "caption_bytes": len(caption),
                    "caption_sha256": hashlib.sha256(caption).hexdigest(),
                }
            )
        _atomic_json(job_dir / "manifest.json", manifest)
        reference_set_sha256 = hashlib.sha256(
            _canonical_json(input_references)
        ).hexdigest()
        _atomic_json(
            inputs / "job.json",
            {
                "schema_version": LORA_SCHEMA_VERSION,
                "job_id": job_dir.name,
                "trigger_token": LORA_TRIGGER_TOKEN,
                "consent": {
                    "identity_owner_authorized": True,
                    "training_use_authorized": True,
                    "reference_set_sha256": reference_set_sha256,
                },
                "references": input_references,
            },
        )
        now = int(time.time())
        state: dict[str, object] = {
            "schema_version": LORA_SCHEMA_VERSION,
            "job_id": job_dir.name,
            "contract": LORA_CANARY_CONTRACT,
            "candidate_sha256": self.lora_candidate_sha256,
            "manifest_sha256": manifest_sha256,
            "state": "starting",
            "retriable": False,
            "retry_mode": "none",
            "created_at_unix": now,
            "updated_at_unix": now,
            "started_at_unix": now,
            "completed_at_unix": None,
            "exit_code": None,
            "blocker_code": "",
            "attempt_index": 1,
            "benchmark_attempt_index": 0,
            "activity_lease_sha256": activity_lease_sha256,
            "execution_activity_lease_sha256": activity_lease_sha256,
            "benchmark_activity_lease_sha256": None,
        }
        self._write_lora_state(job_dir, state)
        return state

    def _lora_child_environment(self, activity_lease_sha256: str) -> dict[str, str]:
        assert self.lora_state_root is not None
        assert self.flux2_state_root is not None
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        temporary = str(self.lora_state_root / "tmp")
        return {
            "SystemRoot": system_root,
            "PROGRAMDATA": os.environ.get(
                "PROGRAMDATA", str(self.lora_state_root.parent)
            ),
            "ProgramFiles": str(self.lora_program_files),
            "LOCALAPPDATA": str(self.flux2_state_root.parent),
            "TEMP": temporary,
            "TMP": temporary,
            # matplotlib is a DIRECT_RUNTIME_IMPORTS entry and calls Path.home()
            # at import time to locate ~/.matplotlib. This allowlist deliberately
            # withholds USERPROFILE/HOME/HOMEDRIVE/HOMEPATH, so on Windows that
            # raises RuntimeError("Could not determine home directory") and kills
            # the runner inside contract.py's CUDA probe -- which reports it as a
            # CUDA failure, because the probe imports all 47 modules eagerly.
            #
            # MPLCONFIGDIR is matplotlib's documented escape hatch and is the
            # minimal fix: measured on the target host, all 47 imports succeed
            # with it set while Path.home() still raises, so the scrub is intact
            # and matplotlib is the only import-time home consumer.
            #
            # Must be NON-EMPTY and ABSOLUTE. matplotlib/__init__.py:520 tests
            # `if configdir:` (truthiness -- an empty string silently re-arms the
            # same crash) and :530 resolves a relative value against cwd, which
            # is set to the digest-pinned package directory.
            "MPLCONFIGDIR": str(self.lora_state_root / "mplconfig"),
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "CONTENT_LORA_ACTIVITY_LEASE_SHA256": activity_lease_sha256,
        }

    async def _launch_lora_job(
        self,
        job_dir: Path,
        state: dict[str, object],
        *,
        retry_mode: str = "none",
    ) -> dict[str, object]:
        assert self.lora_python is not None and self.lora_runner is not None
        assert self.lora_state_root is not None
        self._call_lora_contract(
            "validate_gateway_admission",
            self.lora_state_root,
            job_dir.name,
            self.lora_candidate_sha256,
        )
        activity_lease_sha256 = state.get("activity_lease_sha256")
        if not isinstance(activity_lease_sha256, str):
            raise ValueError("training activity lease is missing")
        self._require_owned_lora_activity(
            activity_lease_sha256, "training", job_dir.name
        )
        argv = [str(self.lora_python), str(self.lora_runner)]
        if retry_mode == "checkpoint":
            argv.append("--resume")
        elif retry_mode not in {"none", "initial"}:
            raise ValueError("invalid training retry mode")
        argv.append(job_dir.name)
        child_environment = self._lora_child_environment(activity_lease_sha256)
        log_root = _private_directory(job_dir / "gateway-logs", create=True)
        log_path = log_root / f"runner-{state['attempt_index']}.log"
        try:
            with log_path.open("xb") as runner_log:
                try:
                    process = await asyncio.create_subprocess_exec(
                        *argv,
                        cwd=str(self.lora_runner.parent),
                        stdin=asyncio.subprocess.DEVNULL,
                        stdout=runner_log,
                        stderr=runner_log,
                        close_fds=True,
                        env=child_environment,
                    )
                except Exception as exc:
                    diagnostic = (
                        f"gateway launch failed: {type(exc).__name__}: {exc}\n"
                    ).encode("utf-8", errors="replace")[:4096]
                    runner_log.write(diagnostic)
                    runner_log.flush()
                    raise
        except Exception:
            retry = state["attempt_index"] == 1
            state["state"] = "failed"
            state["retriable"] = retry
            state["retry_mode"] = "initial" if retry else "none"
            state["blocker_code"] = "trainer_launch_failed"
            state["updated_at_unix"] = int(time.time())
            state["completed_at_unix"] = int(time.time())
            state["exit_code"] = None
            self._release_lora_activity(activity_lease_sha256)
            state["activity_lease_sha256"] = None
            self._write_lora_state(job_dir, state)
            return state
        self._lora_process = process
        self._lora_watch_task = asyncio.create_task(
            self._watch_lora_job(job_dir, process)
        )
        state["state"] = "running"
        state["updated_at_unix"] = int(time.time())
        self._write_lora_state(job_dir, state)
        return state

    def _publish_lora_adapter(
        self, source: Path, metadata: dict[str, Any]
    ) -> tuple[str, int, str]:
        assert self.lora_comfy_root is not None
        destination_root = _private_directory(self.lora_comfy_root)
        adapter = metadata.get("adapter")
        if not isinstance(adapter, dict):
            raise ValueError("adapter metadata projection is missing")
        digest = adapter.get("sha256")
        size = adapter.get("bytes")
        name = adapter.get("filename")
        if (
            not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
            or type(size) is not int
            or size <= 0
            or name != f"identity-lora-{digest}.safetensors"
        ):
            raise ValueError("adapter projection is invalid")
        destination = destination_root / str(name)
        if destination.exists() or destination.is_symlink():
            self._call_lora_contract(
                "validate_adapter_file",
                destination,
                metadata,
                root=destination_root,
            )
            return digest, size, str(name)

        temporary = destination_root / f".{digest}.{uuid.uuid4().hex}.tmp"
        try:
            with source.open("rb") as reader, temporary.open("xb") as writer:
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    writer.write(chunk)
                writer.flush()
                os.fsync(writer.fileno())
            self._call_lora_contract(
                "validate_lora_safetensors", temporary, root=destination_root
            )
            if _digest_regular_file(
                temporary, maximum=LORA_MAX_ADAPTER_BYTES
            ) != (digest, size):
                raise ValueError("copied adapter changed")
            os.replace(temporary, destination)
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()
        self._call_lora_contract(
            "validate_adapter_file", destination, metadata, root=destination_root
        )
        return digest, size, str(name)

    def _finish_lora_training(
        self, job_dir: Path, state: dict[str, object]
    ) -> dict[str, Any]:
        result = self._lora_training_result(job_dir, state)
        if result["state"] != "training_passed":
            raise ValueError("training did not pass")
        source_value = result.get("adapter_path")
        metadata = result.get("metadata")
        if not isinstance(source_value, str) or not isinstance(metadata, dict):
            raise ValueError("training result cannot be published")
        self._publish_lora_adapter(Path(source_value), metadata)
        return self._lora_training_result(job_dir, state, published=True)

    async def _launch_lora_benchmark(
        self, job_dir: Path, state: dict[str, object]
    ) -> dict[str, object]:
        assert self.lora_python is not None and self.lora_runner is not None
        lease = state.get("activity_lease_sha256")
        if not isinstance(lease, str):
            raise ValueError("benchmark activity lease is missing")
        self._require_owned_lora_activity(lease, "benchmark", job_dir.name)
        self._finish_lora_training(job_dir, state)
        runner = self.lora_runner.parent / "benchmark.py"
        if not runner.is_file() or runner.is_symlink():
            raise ValueError("benchmark runner is unavailable")
        log_path = _private_directory(job_dir / "gateway-logs", create=True) / (
            f"benchmark-{state['benchmark_attempt_index']}.log"
        )
        try:
            with log_path.open("xb") as runner_log:
                try:
                    process = await asyncio.create_subprocess_exec(
                        str(self.lora_python),
                        str(runner),
                        job_dir.name,
                        cwd=str(self.lora_runner.parent),
                        stdin=asyncio.subprocess.DEVNULL,
                        stdout=runner_log,
                        stderr=runner_log,
                        close_fds=True,
                        env=self._lora_child_environment(lease),
                    )
                except Exception as exc:
                    diagnostic = (
                        f"gateway benchmark launch failed: {type(exc).__name__}: {exc}\n"
                    ).encode("utf-8", errors="replace")[:4096]
                    runner_log.write(diagnostic)
                    runner_log.flush()
                    raise
        except Exception:
            retry = state["benchmark_attempt_index"] == 1
            state["state"] = "failed"
            state["retriable"] = retry
            state["retry_mode"] = "benchmark" if retry else "none"
            state["blocker_code"] = "benchmark_launch_failed"
            state["updated_at_unix"] = int(time.time())
            state["completed_at_unix"] = int(time.time())
            state["exit_code"] = None
            self._release_lora_activity(lease)
            state["activity_lease_sha256"] = None
            self._write_lora_state(job_dir, state)
            return state
        self._lora_process = process
        self._lora_watch_task = asyncio.create_task(
            self._watch_lora_benchmark(job_dir, process)
        )
        state["state"] = "benchmarking"
        state["retriable"] = False
        state["retry_mode"] = "none"
        state["blocker_code"] = ""
        state["updated_at_unix"] = int(time.time())
        state["completed_at_unix"] = None
        self._write_lora_state(job_dir, state)
        return state

    async def _begin_lora_benchmark(
        self, job_dir: Path, state: dict[str, object]
    ) -> dict[str, object]:
        self._finish_lora_training(job_dir, state)
        training_lease = state.get("activity_lease_sha256")
        if not isinstance(training_lease, str):
            raise ValueError("training lease is missing")
        self._release_lora_activity(training_lease)
        state["activity_lease_sha256"] = None
        state["state"] = "failed"
        state["retriable"] = True
        state["retry_mode"] = "benchmark"
        state["blocker_code"] = "benchmark_not_started"
        state["updated_at_unix"] = int(time.time())
        state["completed_at_unix"] = int(time.time())
        state["exit_code"] = 0
        self._write_lora_state(job_dir, state)
        benchmark_lease = self._try_acquire_lora_activity(
            "benchmark", job_dir.name
        )
        if benchmark_lease is None:
            return state
        state["activity_lease_sha256"] = benchmark_lease
        state["benchmark_activity_lease_sha256"] = benchmark_lease
        state["benchmark_attempt_index"] = 1
        state["state"] = "benchmarking"
        state["retriable"] = False
        state["retry_mode"] = "none"
        state["blocker_code"] = ""
        state["completed_at_unix"] = None
        self._write_lora_state(job_dir, state)
        return await self._launch_lora_benchmark(job_dir, state)

    async def _watch_lora_benchmark(
        self, job_dir: Path, process: asyncio.subprocess.Process
    ) -> None:
        try:
            return_code = await process.wait()
        except asyncio.CancelledError:
            raise
        except Exception:
            return_code = None
        async with self._lora_lock:
            self._lora_process = None
            try:
                state = self._load_lora_state(job_dir)
                now = int(time.time())
                if return_code is None:
                    state["state"] = "unknown"
                    state["retriable"] = False
                    state["retry_mode"] = "none"
                    state["blocker_code"] = "benchmark_exit_unknown"
                    state["completed_at_unix"] = now
                    state["exit_code"] = None
                    self._write_lora_state(job_dir, state)
                    return
                result = self._lora_benchmark_result(job_dir, state)
                outcome = result["state"]
                retry_mode = result["retry_mode"]
                if return_code == 0 and outcome == "benchmark_passed":
                    state["state"] = "succeeded"
                    state["blocker_code"] = ""
                elif outcome == "benchmark_unknown":
                    state["state"] = "unknown"
                    state["blocker_code"] = str(
                        result.get("blocker_code") or "benchmark_outcome_unknown"
                    )
                else:
                    state["state"] = "failed"
                    state["retry_mode"] = (
                        "benchmark"
                        if retry_mode == "benchmark"
                        and state["benchmark_attempt_index"] == 1
                        else "none"
                    )
                    state["retriable"] = state["retry_mode"] == "benchmark"
                    state["blocker_code"] = str(
                        result.get("blocker_code") or "benchmark_failed"
                    )
                state["updated_at_unix"] = now
                state["completed_at_unix"] = now
                state["exit_code"] = return_code
                if state["state"] != "unknown":
                    lease = state.get("activity_lease_sha256")
                    if not isinstance(lease, str):
                        raise ValueError("completed benchmark lacks its lease")
                    self._release_lora_activity(lease)
                    state["activity_lease_sha256"] = None
                self._write_lora_state(job_dir, state)
            except (OSError, ValueError, GatewayConfigError):
                self._lora_state_invalid = True

    async def _watch_lora_job(
        self, job_dir: Path, process: asyncio.subprocess.Process
    ) -> None:
        try:
            return_code = await process.wait()
        except asyncio.CancelledError:
            raise
        except Exception:
            return_code = None
        async with self._lora_lock:
            self._lora_process = None
            try:
                state = self._load_lora_state(job_dir)
                now = int(time.time())
                if return_code is None:
                    state["state"] = "unknown"
                    state["retriable"] = False
                    state["retry_mode"] = "none"
                    state["blocker_code"] = "trainer_exit_unknown"
                    state["updated_at_unix"] = now
                    state["completed_at_unix"] = now
                    state["exit_code"] = None
                    self._write_lora_state(job_dir, state)
                    return
                try:
                    result = self._lora_training_result(job_dir, state)
                except ValueError:
                    started = job_dir / "evidence" / "started.json"
                    if started.is_symlink():
                        raise
                    retry_mode = (
                        "initial"
                        if not started.exists() and state["attempt_index"] == 1
                        else "none"
                    )
                    state["state"] = "failed"
                    state["retriable"] = retry_mode != "none"
                    state["retry_mode"] = retry_mode
                    state["blocker_code"] = "runner_preflight_failed"
                else:
                    outcome = result["state"]
                    retry_mode = str(result["retry_mode"])
                    if return_code == 0 and outcome == "training_passed":
                        await self._begin_lora_benchmark(job_dir, state)
                        return
                    if outcome == "training_unknown":
                        state["state"] = "unknown"
                        state["retriable"] = False
                        state["retry_mode"] = "none"
                    else:
                        state["state"] = "failed"
                        if state["attempt_index"] != 1:
                            retry_mode = "none"
                        state["retriable"] = retry_mode != "none"
                        state["retry_mode"] = retry_mode
                    state["blocker_code"] = str(
                        result.get("blocker_code") or outcome
                    )
                state["updated_at_unix"] = now
                state["completed_at_unix"] = now
                state["exit_code"] = return_code
                if state["state"] != "unknown":
                    lease = state.get("activity_lease_sha256")
                    if not isinstance(lease, str):
                        raise ValueError("completed training lacks its lease")
                    self._release_lora_activity(lease)
                    state["activity_lease_sha256"] = None
                self._write_lora_state(job_dir, state)
            except (OSError, ValueError, GatewayConfigError):
                self._lora_state_invalid = True

    async def lora_put_job(self, request: web.Request) -> web.Response:
        if not self._lora_configured():
            return self._lora_error("identity_lora_unavailable", 503)
        job_id = request.match_info.get("job_id", "")
        if not _JOB_ID_RE.fullmatch(job_id):
            return self._lora_error("invalid_job_id", 404)
        manifest, error = await self._lora_manifest_request(request)
        if error is not None:
            return error
        assert manifest is not None
        manifest_bytes = _canonical_json(manifest)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        if job_id != manifest_sha256[:32]:
            return self._lora_error("job_id_contract_mismatch", 409)
        async with self._lora_lock:
            activity_lease_sha256: str | None = None
            try:
                job_dir = self._lora_job_dir(job_id, required=False)
                if job_dir.exists():
                    existing_manifest = self._read_lora_manifest(job_dir)
                    if not hmac.compare_digest(
                        hashlib.sha256(_canonical_json(existing_manifest)).hexdigest(),
                        manifest_sha256,
                    ):
                        return self._lora_error("job_manifest_conflict", 409)
                    return web.json_response(
                        self._public_lora_state(self._load_lora_state(job_dir)),
                        status=200,
                    )
                self._validate_lora_package()
                if self._blocking_lora_job() is not None:
                    return self._lora_error("identity_lora_job_active", 409)
                await self._reconcile_orphan_prompt_activity()
                activity_lease_sha256 = self._try_acquire_lora_activity(
                    "training", job_id
                )
                if activity_lease_sha256 is None:
                    return self._lora_error("identity_lora_gpu_active", 409)
                queue_empty = await self._comfy_queue_empty()
                if queue_empty is None:
                    self._release_lora_activity(activity_lease_sha256)
                    activity_lease_sha256 = None
                    return self._lora_error("comfy_queue_unknown", 503)
                if not queue_empty:
                    self._release_lora_activity(activity_lease_sha256)
                    activity_lease_sha256 = None
                    return self._lora_error("comfy_queue_not_empty", 409)
                if not await self._free_comfy_models():
                    self._release_lora_activity(activity_lease_sha256)
                    activity_lease_sha256 = None
                    return self._lora_error("comfy_memory_release_failed", 503)
                reference_records = manifest["references"]
                assert isinstance(reference_records, list)
                references = [
                    self._blob_bytes(str(record["sha256"]))
                    for record in reference_records
                    if isinstance(record, dict)
                ]
                if len(references) != 4:
                    raise ValueError("invalid references")
                for reference in references:
                    _validate_png(reference)
                state = self._create_lora_job_files(
                    job_dir,
                    manifest,
                    manifest_sha256,
                    references,
                    activity_lease_sha256,
                )
                activity_lease_sha256 = None
                state = await self._launch_lora_job(job_dir, state)
            except FileNotFoundError:
                if activity_lease_sha256 is not None:
                    self._release_lora_activity(activity_lease_sha256)
                return self._lora_error("reference_blob_missing", 422)
            except FileExistsError:
                if activity_lease_sha256 is not None:
                    self._release_lora_activity(activity_lease_sha256)
                return self._lora_error("job_manifest_conflict", 409)
            except (OSError, ValueError, GatewayConfigError):
                if activity_lease_sha256 is not None:
                    with contextlib.suppress(OSError, ValueError, GatewayConfigError):
                        self._release_lora_activity(activity_lease_sha256)
                self._lora_state_invalid = True
                return self._lora_error("identity_lora_state_invalid", 503)
        status = 202 if state["state"] == "running" else 503
        return web.json_response(self._public_lora_state(state), status=status)

    async def lora_get_job(self, request: web.Request) -> web.Response:
        if not self._lora_configured():
            return self._lora_error("identity_lora_unavailable", 503)
        job_id = request.match_info.get("job_id", "")
        if not _JOB_ID_RE.fullmatch(job_id):
            return self._lora_error("invalid_job_id", 404)
        async with self._lora_lock:
            try:
                job_dir = self._lora_job_dir(job_id, required=True)
                state = self._load_lora_state(job_dir)
            except FileNotFoundError:
                return self._lora_error("identity_lora_job_not_found", 404)
            except (OSError, ValueError, GatewayConfigError):
                self._lora_state_invalid = True
                return self._lora_error("identity_lora_state_invalid", 503)
        return web.json_response(self._public_lora_state(state))

    async def _empty_json_request(self, request: web.Request) -> web.Response | None:
        if request.content_type != "application/json":
            return self._lora_error("unsupported_media_type", 415)
        try:
            raw = await self._limited_body(request, LORA_MAX_JSON_BYTES)
            payload = _json_without_duplicate_keys(raw)
        except OverflowError:
            return self._lora_error("request_too_large", 413)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return self._lora_error("invalid_request", 400)
        if payload != {}:
            return self._lora_error("invalid_request", 400)
        return None

    async def lora_resume_job(self, request: web.Request) -> web.Response:
        if not self._lora_configured():
            return self._lora_error("identity_lora_unavailable", 503)
        job_id = request.match_info.get("job_id", "")
        if not _JOB_ID_RE.fullmatch(job_id):
            return self._lora_error("invalid_job_id", 404)
        error = await self._empty_json_request(request)
        if error is not None:
            return error
        async with self._lora_lock:
            activity_lease_sha256: str | None = None
            try:
                job_dir = self._lora_job_dir(job_id, required=True)
                state = self._load_lora_state(job_dir)
                if state["state"] == "unknown":
                    return self._lora_error("identity_lora_job_unknown", 409)
                retry_mode = state["retry_mode"]
                if (
                    retry_mode != "benchmark"
                    and state["attempt_index"] > 1
                    and state["state"] != "benchmarking"
                ):
                    if state["state"] == "interrupted":
                        return self._lora_error(
                            "identity_lora_resume_not_available", 409
                        )
                    return web.json_response(
                        self._public_lora_state(state), status=200
                    )
                if (
                    retry_mode == "benchmark"
                    and state["benchmark_attempt_index"] > 1
                ):
                    return self._lora_error("identity_lora_resume_not_available", 409)
                if (
                    state["state"] not in {"failed", "interrupted"}
                    or state["retriable"] is not True
                    or retry_mode not in {"initial", "checkpoint", "benchmark"}
                    or not self.lora_process_death_guaranteed
                ):
                    return self._lora_error("identity_lora_job_not_resumable", 409)
                self._validate_lora_package()
                if self._blocking_lora_job(exclude=job_id) is not None:
                    return self._lora_error("identity_lora_job_active", 409)
                await self._reconcile_orphan_prompt_activity()
                activity_lease_sha256 = self._try_acquire_lora_activity(
                    "benchmark" if retry_mode == "benchmark" else "training",
                    job_id,
                )
                if activity_lease_sha256 is None:
                    return self._lora_error("identity_lora_gpu_active", 409)
                queue_empty = await self._comfy_queue_empty()
                if queue_empty is None:
                    self._release_lora_activity(activity_lease_sha256)
                    activity_lease_sha256 = None
                    return self._lora_error("comfy_queue_unknown", 503)
                if not queue_empty:
                    self._release_lora_activity(activity_lease_sha256)
                    activity_lease_sha256 = None
                    return self._lora_error("comfy_queue_not_empty", 409)
                if retry_mode != "benchmark" and not await self._free_comfy_models():
                    self._release_lora_activity(activity_lease_sha256)
                    activity_lease_sha256 = None
                    return self._lora_error("comfy_memory_release_failed", 503)
                now = int(time.time())
                state["state"] = (
                    "benchmarking" if retry_mode == "benchmark" else "starting"
                )
                state["updated_at_unix"] = now
                state["started_at_unix"] = now
                state["completed_at_unix"] = None
                state["exit_code"] = None
                state["blocker_code"] = ""
                if retry_mode == "benchmark":
                    state["benchmark_attempt_index"] += 1
                else:
                    state["attempt_index"] = 2
                state["retriable"] = False
                state["retry_mode"] = "none"
                state["activity_lease_sha256"] = activity_lease_sha256
                if retry_mode != "benchmark":
                    state["execution_activity_lease_sha256"] = activity_lease_sha256
                else:
                    state["benchmark_activity_lease_sha256"] = activity_lease_sha256
                self._write_lora_state(job_dir, state)
                activity_lease_sha256 = None
                if retry_mode == "benchmark":
                    state = await self._launch_lora_benchmark(job_dir, state)
                else:
                    state = await self._launch_lora_job(
                        job_dir, state, retry_mode=str(retry_mode)
                    )
            except FileNotFoundError:
                if activity_lease_sha256 is not None:
                    self._release_lora_activity(activity_lease_sha256)
                return self._lora_error("identity_lora_job_not_found", 404)
            except (OSError, ValueError, GatewayConfigError):
                if activity_lease_sha256 is not None:
                    with contextlib.suppress(OSError, ValueError, GatewayConfigError):
                        self._release_lora_activity(activity_lease_sha256)
                self._lora_state_invalid = True
                return self._lora_error("identity_lora_state_invalid", 503)
        status = 202 if state["state"] in {"running", "benchmarking"} else 503
        return web.json_response(self._public_lora_state(state), status=status)

    @staticmethod
    def _public_lora_evidence(
        state: dict[str, object],
        training: dict[str, Any],
        benchmark: dict[str, Any],
    ) -> dict[str, object]:
        adapter = training["adapter"]
        telemetry = training["training"]
        assert isinstance(adapter, dict)
        assert isinstance(telemetry, dict)
        return {
            "schema_version": LORA_SCHEMA_VERSION,
            "job_id": state["job_id"],
            "contract": LORA_CANARY_CONTRACT,
            "candidate_sha256": state["candidate_sha256"],
            "manifest_sha256": state["manifest_sha256"],
            "state": "succeeded",
            "adapter": {
                "sha256": adapter["sha256"],
                "size_bytes": adapter["bytes"],
                "comfy_name": adapter["filename"],
            },
            "training": {
                "steps": 500,
                "resolution": 512,
                "rank": 16,
                "seed": 0,
                "batch_size": 1,
                "elapsed_seconds": telemetry["elapsed_seconds"],
                "peak_vram_bytes": telemetry["peak_vram_bytes"],
            },
            "adapter_metadata": training["metadata"],
            "adapter_metadata_sha256": adapter["metadata_sha256"],
            "terminal_sha256": training["terminal_sha256"],
            "benchmark": {
                "proof_sha256": benchmark["proof_sha256"],
                "control": benchmark["control"],
                "lora": benchmark["lora"],
            },
        }

    async def lora_get_evidence(self, request: web.Request) -> web.Response:
        if not self._lora_configured():
            return self._lora_error("identity_lora_unavailable", 503)
        job_id = request.match_info.get("job_id", "")
        if not _JOB_ID_RE.fullmatch(job_id):
            return self._lora_error("invalid_job_id", 404)
        async with self._lora_lock:
            try:
                job_dir = self._lora_job_dir(job_id, required=True)
                state = self._load_lora_state(job_dir)
                if state["state"] != "succeeded":
                    return self._lora_error(
                        "identity_lora_evidence_not_available", 409
                    )
                training = self._lora_training_result(
                    job_dir, state, published=True
                )
                benchmark = self._lora_benchmark_result(job_dir, state)
                if (
                    training["state"] != "training_passed"
                    or benchmark["state"] != "benchmark_passed"
                ):
                    raise ValueError("successful job evidence is incomplete")
                evidence = self._public_lora_evidence(
                    state, training, benchmark
                )
            except FileNotFoundError:
                return self._lora_error("identity_lora_job_not_found", 404)
            except (OSError, ValueError, GatewayConfigError):
                self._lora_state_invalid = True
                return self._lora_error("identity_lora_state_invalid", 503)
        return web.json_response(evidence)

    async def lora_ready(self, _request: web.Request) -> web.Response:
        payload: dict[str, object] = {
            "schema_version": LORA_SCHEMA_VERSION,
            "contract": LORA_CANARY_CONTRACT,
            "candidate_sha256": self.lora_candidate_sha256 or "",
            "state": "blocked",
            "blocker_code": "gateway_not_configured",
            "job_submission_ready": False,
        }
        if not self._lora_configured():
            if self._lora_state_invalid:
                payload["blocker_code"] = "identity_lora_state_invalid"
            return web.json_response(payload, status=503)
        async with self._lora_lock:
            try:
                self._validate_lora_package()
                flux2 = self._flux2_status_record()
                runtime = flux2.get("runtime_contract_sha256")
                if (
                    flux2.get("state") != "ready"
                    or not isinstance(runtime, str)
                    or not _SHA256_RE.fullmatch(runtime)
                ):
                    payload["blocker_code"] = "base_flux2_not_ready"
                    return web.json_response(payload, status=503)
                states = []
                for job_dir in self._lora_job_directories():
                    state = self._load_lora_state(job_dir)
                    if state["candidate_sha256"] != self.lora_candidate_sha256:
                        continue
                    states.append(state)

                if any(state["state"] == "unknown" for state in states):
                    payload["blocker_code"] = "candidate_outcome_unknown"
                    return web.json_response(payload, status=503)
                if any(state["state"] == "benchmarking" for state in states):
                    payload["blocker_code"] = "candidate_inference_running"
                    return web.json_response(payload, status=503)
                if any(
                    state["state"] in {"starting", "running", "interrupted"}
                    for state in states
                ):
                    payload["blocker_code"] = "candidate_training_not_proven"
                    return web.json_response(payload, status=503)

                payload["job_submission_ready"] = True
                for state in states:
                    if state["state"] == "succeeded":
                        job_dir = self._lora_job_dir(str(state["job_id"]), required=True)
                        training = self._lora_training_result(
                            job_dir, state, published=True
                        )
                        benchmark = self._lora_benchmark_result(job_dir, state)
                        if (
                            training["state"] != "training_passed"
                            or benchmark["state"] != "benchmark_passed"
                            or training.get("runtime_contract_sha256") != runtime
                            or benchmark.get("runtime_contract_sha256") != runtime
                        ):
                            raise ValueError("ready evidence is stale")
                        payload["state"] = "ready"
                        payload["blocker_code"] = ""
                        return web.json_response(payload)
                if any(
                    state["retry_mode"] == "benchmark"
                    for state in states
                ):
                    payload["blocker_code"] = "candidate_inference_not_proven"
                elif any(
                    state["state"] == "failed"
                    and state["benchmark_attempt_index"] > 0
                    for state in states
                ):
                    payload["blocker_code"] = "candidate_inference_failed"
                elif any(state["state"] == "failed" for state in states):
                    payload["blocker_code"] = "candidate_training_failed"
                else:
                    payload["blocker_code"] = "candidate_training_not_proven"
                return web.json_response(payload, status=503)
            except (OSError, ValueError, GatewayConfigError):
                self._lora_state_invalid = True
                payload["blocker_code"] = "candidate_evidence_invalid"
                payload["job_submission_ready"] = False
                return web.json_response(payload, status=503)

    async def lora_not_found(self, _request: web.Request) -> web.Response:
        return self._lora_error("identity_lora_route_not_found", 404)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _expected_contract(self) -> dict[str, str] | None:
        try:
            probe = json.loads(self.probe_contract.read_text(encoding="utf-8"))
            workflow_value = probe.get("workflow") if isinstance(probe, dict) else None
            if not isinstance(workflow_value, str) or Path(workflow_value).is_absolute():
                return None
            probe_root = self.probe_contract.parent.resolve()
            workflow = (probe_root / workflow_value).resolve()
            if probe_root not in workflow.parents:
                return None
            workflow_hash = self._sha256(workflow)
            if probe.get("workflow_sha256") != workflow_hash:
                return None
            contract = {
                "model_manifest_sha256": self._sha256(self.models),
                "revisions_manifest_sha256": self._sha256(self.revisions),
                "role": WORKER_ROLE,
                "workflow_sha256": workflow_hash,
            }
        except (OSError, json.JSONDecodeError):
            return None
        contract["contract_digest"] = hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return contract

    def _ready_record(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.sentinel.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            not isinstance(payload, dict)
            or payload.get("status") != "ready"
            or payload.get("role") != WORKER_ROLE
            or payload.get("startup_ready") is not True
            or payload.get("execution_proven") is not True
        ):
            return None
        canary = payload.get("execution_canary")
        if not isinstance(canary, dict) or canary.get("state") != "passed":
            return None
        expected = self._expected_contract()
        if expected is None or any(payload.get(key) != value for key, value in expected.items()):
            return None
        return payload

    def _flux2_evidence_sha256(
        self,
        root: Path,
        record: object,
        *,
        expected_status: str,
    ) -> tuple[str, dict[str, Any]]:
        if not isinstance(record, dict):
            raise ValueError("missing evidence record")
        relative = record.get("path")
        expected_hash = record.get("sha256")
        run_id = record.get("run_id")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or not isinstance(run_id, str)
            or not run_id
            or record.get("status") != expected_status
        ):
            raise ValueError("invalid evidence record")
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file() or path.is_symlink():
            raise ValueError("unsafe evidence path")
        actual = self._sha256(path)
        if not hmac.compare_digest(actual, expected_hash):
            raise ValueError("evidence hash mismatch")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("capability") != IMAGE_CAPABILITY
            or payload.get("status") != expected_status
            or str(payload.get("run_id") or payload.get("benchmark_id") or "")
            != run_id
        ):
            raise ValueError("evidence payload mismatch")
        if expected_status == "fixed_probe_passed":
            output = payload.get("output")
            if (
                record.get("workflow_sha256") != payload.get("workflow_sha256")
                or not isinstance(output, dict)
                or record.get("output_sha256") != output.get("sha256")
            ):
                raise ValueError("canary evidence summary mismatch")
        return actual, payload

    def _flux2_status_record(self) -> dict[str, Any]:
        """Rehash private durable evidence and return only its safe projection."""

        base = {
            **FLUX2_PACKAGE_FIELDS,
            "state": "not_installed",
            "startup_ready": False,
            "execution_proven": False,
            "benchmark_state": "not_run",
            "blocker_code": IMAGE_BLOCKER_CODE,
            "artifacts_installed": False,
            "runtime_contract_sha256": "",
            "license_review_state": "official_sources_selected_derivation_pending",
            "execution_canary_state": "not_run",
            "execution_canary_sha256": "",
            "benchmark_sha256": "",
        }
        if self.flux2_state_root is None:
            return base
        root = self.flux2_state_root
        status_path = root / "status.json"
        if not status_path.is_file() or status_path.is_symlink():
            return base
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if (
                not isinstance(status, dict)
                or status.get("schema_version") != 1
                or status.get("capability") != IMAGE_CAPABILITY
                or status.get("artifact_manifest_sha256")
                != FLUX2_PACKAGE_FIELDS["model_manifest_sha256"]
                or status.get("workflow_contract_sha256")
                != FLUX2_PACKAGE_FIELDS["workflow_sha256"]
                or not isinstance(status.get("updated_at"), str)
            ):
                raise ValueError("status contract mismatch")
            state = status.get("state")
            if state not in {"not_installed", "needs_benchmark", "ready"}:
                raise ValueError("invalid state")
            runtime_hash = status.get("runtime_contract_sha256")
            if runtime_hash is None:
                runtime_hash = ""
            if not isinstance(runtime_hash, str) or (
                runtime_hash and len(runtime_hash) != 64
            ):
                raise ValueError("invalid runtime contract")
            evidence = status.get("evidence")
            if not isinstance(evidence, dict):
                raise ValueError("missing evidence map")
            install_hash, _install_payload = self._flux2_evidence_sha256(
                root,
                evidence.get("install"),
                expected_status="installed_needs_execution_probe",
            )
            del install_hash  # verified but intentionally not browser-visible
            canary_hash = ""
            benchmark_hash = ""
            canary_state = "not_run"
            if state in {"needs_benchmark", "ready"}:
                canary_hash, canary_payload = self._flux2_evidence_sha256(
                    root,
                    evidence.get("canary"),
                    expected_status="fixed_probe_passed",
                )
                if canary_payload.get("runtime_contract_sha256") != runtime_hash:
                    raise ValueError("canary runtime binding mismatch")
                canary_state = "passed"
            elif evidence.get("canary") is not None:
                raise ValueError("premature canary evidence")
            if state == "ready":
                benchmark_hash, benchmark_payload = self._flux2_evidence_sha256(
                    root,
                    evidence.get("benchmark"),
                    expected_status="benchmark_passed",
                )
                if (
                    benchmark_payload.get("runtime_contract_sha256") != runtime_hash
                    or benchmark_payload.get("probe_evidence_sha256") != canary_hash
                    or benchmark_payload.get("sequence")
                    != list(FLUX2_BENCHMARK_REFERENCE_COUNTS)
                    or benchmark_payload.get("benchmark_state") != "passed"
                ):
                    raise ValueError("benchmark evidence binding mismatch")
            elif evidence.get("benchmark") is not None:
                raise ValueError("premature benchmark evidence")

            expected = {
                "not_installed": {
                    "startup_ready": False,
                    "execution_proven": False,
                    "benchmark_state": "not_run",
                    "blocker_code": "candidate_execution_probe_not_run",
                },
                "needs_benchmark": {
                    "startup_ready": False,
                    "execution_proven": True,
                    "benchmark_state": "not_run",
                    "blocker_code": "candidate_benchmark_not_run",
                },
                "ready": {
                    "startup_ready": True,
                    "execution_proven": True,
                    "benchmark_state": "passed",
                    "blocker_code": None,
                },
            }[state]
            if any(status.get(key) != value for key, value in expected.items()):
                raise ValueError("state transition tuple mismatch")
            if (
                status.get("artifacts_installed") is not True
                or status.get("license_review_state")
                != "official_source_derivation_verified"
                or (
                    state == "not_installed" and runtime_hash != ""
                )
                or (
                    state in {"needs_benchmark", "ready"}
                    and len(runtime_hash) != 64
                )
            ):
                raise ValueError("installed evidence is incomplete")
            return {
                **FLUX2_PACKAGE_FIELDS,
                "state": state,
                "startup_ready": expected["startup_ready"],
                "execution_proven": expected["execution_proven"],
                "benchmark_state": expected["benchmark_state"],
                "blocker_code": expected["blocker_code"] or "",
                "artifacts_installed": True,
                "runtime_contract_sha256": runtime_hash,
                "license_review_state": "official_source_derivation_verified",
                "execution_canary_state": canary_state,
                "execution_canary_sha256": canary_hash,
                "benchmark_sha256": benchmark_hash,
            }
        except (OSError, json.JSONDecodeError, ValueError):
            return {
                **base,
                "state": "blocked",
                "benchmark_state": "unknown",
                "blocker_code": "candidate_status_evidence_invalid",
                "license_review_state": "review_required",
                "execution_canary_state": "unknown",
            }

    async def live(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "live", "role": WORKER_ROLE})

    async def ready(self, _request: web.Request) -> web.Response:
        record = self._ready_record()
        if record is None or self.session is None:
            return web.json_response(
                {
                    "status": "not_ready",
                    "role": WORKER_ROLE,
                    "startup_ready": False,
                    "execution_proven": False,
                },
                status=503,
            )
        try:
            async with self.session.get(self.upstream + "/system_stats") as response:
                payload = await response.json() if response.status == 200 else None
        except Exception:
            payload = None
        if not isinstance(payload, dict) or not isinstance(payload.get("system"), dict):
            return web.json_response(
                {
                    "status": "not_ready",
                    "role": WORKER_ROLE,
                    "startup_ready": False,
                    "execution_proven": False,
                },
                status=503,
            )
        return web.json_response(
            {
                "status": "ready",
                "role": WORKER_ROLE,
                "startup_ready": True,
                "execution_proven": True,
                "checked_at_unix": record.get("checked_at_unix"),
                "workflow_sha256": record.get("workflow_sha256"),
                "model_manifest_sha256": record.get("model_manifest_sha256"),
                "revisions_manifest_sha256": record.get("revisions_manifest_sha256"),
                "contract_digest": record.get("contract_digest"),
                "execution_canary_state": "passed",
            }
        )

    def _capability_record(self) -> dict[str, Any] | None:
        """Return the exact offline unified-worker contract.

        The accepted installation proves only LivePortrait execution. FLUX.2
        Klein is a separately hash-bound candidate and remains not installed;
        node reachability must never upgrade that state. This record is
        exposed only by the authenticated route. No retired image capability
        can be inferred from the performance worker's node inventory.
        """

        record = self._ready_record()
        if record is None:
            return None
        performance = {
            "role": WORKER_ROLE,
            "status": "ready",
            "startup_ready": True,
            "execution_proven": True,
            "execution_canary_state": "passed",
            "workflow_sha256": record.get("workflow_sha256"),
            "model_manifest_sha256": record.get("model_manifest_sha256"),
            "revisions_manifest_sha256": record.get("revisions_manifest_sha256"),
            "contract_digest": record.get("contract_digest"),
        }
        image = self._flux2_status_record()
        return {
            "schema_version": CAPABILITY_SCHEMA_VERSION,
            "status": "ready" if image.get("state") == "ready" else "partial",
            "capabilities": {
                WORKER_ROLE: performance,
                IMAGE_CAPABILITY: image,
            },
        }

    async def capabilities_ready(self, _request: web.Request) -> web.Response:
        """Return capability-bound readiness after bearer authentication."""

        payload = self._capability_record()
        if payload is None or self.session is None:
            return web.json_response(
                {
                    "schema_version": CAPABILITY_SCHEMA_VERSION,
                    "status": "not_ready",
                },
                status=503,
            )
        try:
            async with self.session.get(self.upstream + "/system_stats") as response:
                stats = await response.json() if response.status == 200 else None
        except Exception:
            stats = None
        if not isinstance(stats, dict) or not isinstance(stats.get("system"), dict):
            return web.json_response(
                {
                    "schema_version": CAPABILITY_SCHEMA_VERSION,
                    "status": "not_ready",
                },
                status=503,
            )
        return web.json_response(payload)

    def _authorized(self, request: web.Request) -> bool:
        return hmac.compare_digest(
            request.headers.get("Authorization", ""), f"Bearer {self.token}"
        )

    @web.middleware
    async def access_control(
        self, request: web.Request, handler: Any
    ) -> web.StreamResponse:
        if request.path in {"/health/live", "/health/ready"}:
            return await handler(request)
        if request.path.rstrip("/") == "/api/identity-lora/ready":
            if not self._authorized(request):
                return web.json_response(
                    {"error": "unauthorized"},
                    status=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if self._ready_record() is None:
                return web.json_response(
                    {
                        "schema_version": LORA_SCHEMA_VERSION,
                        "contract": LORA_CANARY_CONTRACT,
                        "candidate_sha256": self.lora_candidate_sha256 or "",
                        "state": "blocked",
                        "blocker_code": "backend_not_ready",
                        "job_submission_ready": False,
                    },
                    status=503,
                )
            return await handler(request)
        if self._ready_record() is None:
            return web.json_response({"error": "backend_not_ready"}, status=503)
        if not self._authorized(request):
            return web.json_response(
                {"error": "unauthorized"},
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await handler(request)

    async def proxy(self, request: web.Request) -> web.StreamResponse:
        if request.path.rstrip("/") == "/prompt":
            async with self._lora_lock:
                activity_lease_sha256: str | None = None
                try:
                    if self._blocking_lora_job() is not None:
                        return self._lora_error("identity_lora_job_active", 409)
                    if self.lora_state_root is not None:
                        await self._reconcile_orphan_prompt_activity()
                        activity_lease_sha256 = self._try_acquire_lora_activity(
                            "prompt", uuid.uuid4().hex
                        )
                        if activity_lease_sha256 is None:
                            return self._lora_error("identity_lora_gpu_active", 409)
                except (OSError, ValueError, GatewayConfigError):
                    self._lora_state_invalid = True
                    return self._lora_error("identity_lora_state_invalid", 503)
                response = await self._proxy_unlocked(request)
                if (
                    activity_lease_sha256 is not None
                    and response.headers.get("X-Content-Gateway-Outcome") != "unknown"
                ):
                    try:
                        self._release_lora_activity(activity_lease_sha256)
                    except (OSError, ValueError, GatewayConfigError):
                        self._lora_state_invalid = True
                return response
        return await self._proxy_unlocked(request)

    async def _proxy_unlocked(self, request: web.Request) -> web.StreamResponse:
        if self.session is None:
            return web.json_response({"error": "gateway_not_ready"}, status=503)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await self._proxy_websocket(request)
        try:
            async with self.session.request(
                request.method,
                self.upstream + str(request.rel_url),
                headers=filtered_headers(request.headers),
                data=request.content.iter_chunked(1024 * 1024),
                allow_redirects=False,
            ) as upstream:
                response = web.StreamResponse(
                    status=upstream.status,
                    reason=upstream.reason,
                    headers=filtered_headers(upstream.headers, response=True),
                )
                response.headers["X-Content-Gateway"] = "authenticated"
                await response.prepare(request)
                async for chunk in upstream.content.iter_chunked(1024 * 1024):
                    await response.write(chunk)
                await response.write_eof()
                return response
        except asyncio.CancelledError:
            raise
        except Exception:
            return web.json_response(
                {"error": "upstream_outcome_unknown"},
                status=502,
                headers={"X-Content-Gateway-Outcome": "unknown"},
            )

    async def _proxy_websocket(self, request: web.Request) -> web.WebSocketResponse:
        assert self.session is not None
        downstream = web.WebSocketResponse(heartbeat=30, max_msg_size=0)
        await downstream.prepare(request)
        upstream_url = self.upstream.replace("http://", "ws://", 1) + str(request.rel_url)
        try:
            async with self.session.ws_connect(
                upstream_url,
                headers=filtered_headers(request.headers),
                heartbeat=30,
                max_msg_size=0,
            ) as upstream:

                async def copy(source: Any, target: Any) -> None:
                    async for message in source:
                        if message.type == WSMsgType.TEXT:
                            await target.send_str(message.data)
                        elif message.type == WSMsgType.BINARY:
                            await target.send_bytes(message.data)
                        elif message.type in {
                            WSMsgType.CLOSE,
                            WSMsgType.CLOSED,
                            WSMsgType.ERROR,
                        }:
                            break

                tasks = {
                    asyncio.create_task(copy(downstream, upstream)),
                    asyncio.create_task(copy(upstream, downstream)),
                }
                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*done, *pending, return_exceptions=True)
        finally:
            await downstream.close()
        return downstream


def create_app(gateway: AuthenticatedGateway) -> web.Application:
    app = web.Application(middlewares=[gateway.access_control], client_max_size=1024**3)
    app.router.add_get("/health/live", gateway.live)
    app.router.add_get("/health/ready", gateway.ready)
    app.router.add_get("/api/capabilities/ready", gateway.capabilities_ready)
    app.router.add_get("/api/identity-lora/ready", gateway.lora_ready)
    app.router.add_put(
        r"/api/identity-lora/blobs/{sha256:[0-9a-f]{64}}", gateway.lora_put_blob
    )
    app.router.add_put(
        r"/api/identity-lora/jobs/{job_id:[0-9a-f]{32}}", gateway.lora_put_job
    )
    app.router.add_get(
        r"/api/identity-lora/jobs/{job_id:[0-9a-f]{32}}", gateway.lora_get_job
    )
    app.router.add_post(
        r"/api/identity-lora/jobs/{job_id:[0-9a-f]{32}}/resume",
        gateway.lora_resume_job,
    )
    app.router.add_get(
        r"/api/identity-lora/jobs/{job_id:[0-9a-f]{32}}/evidence",
        gateway.lora_get_evidence,
    )
    app.router.add_route("*", "/api/identity-lora/{tail:.*}", gateway.lora_not_found)
    app.router.add_route("*", "/{tail:.*}", gateway.proxy)
    app.on_startup.append(gateway.start)
    app.on_cleanup.append(gateway.stop)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8189)
    parser.add_argument("--upstream", default="http://127.0.0.1:8188")
    parser.add_argument("--sentinel", type=Path, required=True)
    parser.add_argument("--revisions", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--probe-contract", type=Path, required=True)
    parser.add_argument("--flux2-state-root", type=Path)
    parser.add_argument("--lora-state-root", type=Path)
    parser.add_argument("--lora-python", type=Path)
    parser.add_argument("--lora-runner", type=Path)
    parser.add_argument("--lora-comfy-root", type=Path)
    parser.add_argument("--lora-candidate-sha256")
    parser.add_argument("--lora-process-death-guaranteed", action="store_true")
    args = parser.parse_args()
    gateway = AuthenticatedGateway(
        upstream=args.upstream,
        token=os.environ.get("COMFYUI_API_KEY", ""),
        sentinel=args.sentinel,
        revisions=args.revisions,
        models=args.models,
        probe_contract=args.probe_contract,
        flux2_state_root=args.flux2_state_root,
        lora_state_root=args.lora_state_root,
        lora_python=args.lora_python,
        lora_runner=args.lora_runner,
        lora_comfy_root=args.lora_comfy_root,
        lora_candidate_sha256=args.lora_candidate_sha256,
        lora_process_death_guaranteed=args.lora_process_death_guaranteed,
    )
    web.run_app(
        create_app(gateway),
        host=validate_listen(args.listen),
        port=args.port,
        handle_signals=True,
        access_log_format='%a "%r" %s %b %Tf',
    )


if __name__ == "__main__":
    main()
