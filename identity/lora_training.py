"""Bounded client contract for the local FLUX.2 character-LoRA canary."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import stat
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageOps, UnidentifiedImageError


LORA_CONTRACT = "flux2-klein-character-lora-canary-v1"
MAX_BLOB_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_IMAGE_PIXELS = 20_000_000
LORA_CANDIDATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "deploy"
    / "windows-flux2-lora"
    / "candidate.json"
)
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_COMFY_NAME = re.compile(r"^[A-Za-z0-9._/-]{1,180}$")
_TERMINAL_STATES = frozenset({"succeeded", "failed", "unknown", "interrupted"})
_ACTIVE_STATES = frozenset({"starting", "running", "benchmarking"})
_JOB_STATES = _ACTIVE_STATES | _TERMINAL_STATES
_RETRY_MODES = frozenset({"none", "initial", "checkpoint", "benchmark"})
_JOB_STATE_FIELDS = frozenset(
    {
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
    }
)


class LoraTrainingError(RuntimeError):
    pass


class LoraTrainingConflict(LoraTrainingError):
    pass


class LoraTrainingStateUnknown(LoraTrainingError):
    def __init__(self, job_id: str, message: str = "LoRA training state is unknown"):
        super().__init__(message)
        self.job_id = job_id


@dataclass(frozen=True)
class LoraTrainingPlan:
    job_id: str
    manifest: dict[str, Any]
    sources: tuple[tuple[bytes, str], ...]


@dataclass(frozen=True)
class LoraTrainingEvidence:
    job_id: str
    adapter_sha256: str
    adapter_size_bytes: int
    comfy_name: str
    elapsed_seconds: float
    peak_vram_bytes: int
    adapter_metadata: Mapping[str, Any]
    adapter_metadata_sha256: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class LoraReadiness:
    state: str
    blocker_code: str
    candidate_sha256: str
    job_submission_ready: bool


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _regular_bytes(path_value: str | Path, *, maximum: int) -> bytes:
    path = Path(path_value)
    try:
        before = path.lstat()
    except (FileNotFoundError, OSError, RuntimeError) as exc:
        raise ValueError("LoRA references must be available regular files") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("LoRA references must be available regular files")
    if before.st_size <= 0 or before.st_size > maximum:
        raise ValueError("LoRA input size is outside the fixed canary limit")
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or opened.st_size != before.st_size
        ):
            raise ValueError("LoRA input changed while it was admitted")
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = -1
            content = handle.read(maximum + 1)
            finished = os.fstat(handle.fileno())
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError("LoRA references must be available regular files") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        after = path.lstat()
    except OSError as exc:
        raise ValueError("LoRA input changed while it was admitted") from exc
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    ) != (
        finished.st_dev,
        finished.st_ino,
        finished.st_size,
        finished.st_mtime_ns,
    ) or len(content) != before.st_size or len(content) > maximum:
        raise ValueError("LoRA input changed while it was admitted")
    return content


def _source(path_value: str | Path) -> tuple[bytes, str]:
    content = _regular_bytes(path_value, maximum=MAX_BLOB_BYTES)
    try:
        with Image.open(BytesIO(content)) as opened:
            width, height = opened.size
            if (
                not 256 <= width <= 8192
                or not 256 <= height <= 8192
                or width * height > MAX_IMAGE_PIXELS
            ):
                raise ValueError("LoRA reference dimensions are outside the fixed bounds")
            normalized = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = normalized.size
            if (
                not 256 <= width <= 8192
                or not 256 <= height <= 8192
                or width * height > MAX_IMAGE_PIXELS
            ):
                raise ValueError("LoRA reference dimensions are outside the fixed bounds")
            output = BytesIO()
            normalized.save(output, format="PNG", optimize=False, compress_level=9)
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        if isinstance(exc, ValueError) and "dimensions" in str(exc):
            raise
        raise ValueError("LoRA references must be decodable images") from exc
    payload = output.getvalue()
    if not payload or len(payload) > MAX_BLOB_BYTES:
        raise ValueError("Normalized LoRA reference is outside the fixed canary limit")
    return payload, hashlib.sha256(payload).hexdigest()


def current_lora_candidate_sha256() -> str:
    payload = _regular_bytes(LORA_CANDIDATE_PATH, maximum=1024 * 1024)
    return hashlib.sha256(payload).hexdigest()


def build_lora_training_plan(
    reference_paths: Sequence[str | Path],
    *,
    consent: bool,
) -> LoraTrainingPlan:
    """Bind exactly four local references to the one supported canary."""

    if consent is not True:
        raise ValueError("LoRA training requires explicit reference-image consent")
    if isinstance(reference_paths, (str, bytes)) or len(reference_paths) != 4:
        raise ValueError("LoRA training requires exactly four references")
    normalized_captions = fixed_character_captions("hkkperson")

    sources: list[tuple[bytes, str]] = []
    references: list[dict[str, str]] = []
    for path_value, caption in zip(reference_paths, normalized_captions, strict=True):
        payload, digest = _source(path_value)
        sources.append((payload, digest))
        references.append({"sha256": digest, "caption": caption})
    if len({digest for _payload, digest in sources}) != 4:
        raise ValueError("LoRA references must have distinct content")
    manifest = {
        "schema_version": 1,
        "contract": LORA_CONTRACT,
        "candidate_sha256": current_lora_candidate_sha256(),
        "consent": True,
        "references": references,
    }
    job_id = hashlib.sha256(_canonical_json(manifest)).hexdigest()[:32]
    return LoraTrainingPlan(job_id, manifest, tuple(sources))


def fixed_character_token(project_id: str, character_id: str) -> str:
    if not project_id or not character_id:
        raise ValueError("project and character identity are required")
    return "hkkperson"


def fixed_character_captions(token: str) -> tuple[str, ...]:
    if token != "hkkperson":
        raise ValueError("invalid fixed identity token")
    return tuple(
        f"portrait photograph of {token} person, identity reference view {index}"
        for index in range(1, 5)
    )


class LoraTrainingClient:
    """Submit once, then reconcile only by the deterministic planned ID."""

    def __init__(
        self,
        server_url: str,
        token: str,
        *,
        session: requests.Session | None = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
    ) -> None:
        parsed = urlsplit(server_url.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("LoRA gateway URL must be an absolute HTTP(S) endpoint")
        if parsed.scheme == "http":
            host = (parsed.hostname or "").lower()
            try:
                loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                raise ValueError("Plaintext LoRA gateway URLs must use a loopback host")
        normalized_token = token.strip()
        if len(normalized_token) < 32 or normalized_token.lower().startswith("bearer "):
            raise ValueError("LoRA gateway requires the token value only")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value <= 0
            for value in (connect_timeout, read_timeout)
        ):
            raise ValueError("LoRA gateway timeouts must be finite and positive")
        self.server_url = server_url.strip().rstrip("/")
        self.token = normalized_token
        self.session = session or requests.Session()
        self.timeout = (float(connect_timeout), float(read_timeout))

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @staticmethod
    def _manifest_sha256(plan: LoraTrainingPlan) -> str:
        return hashlib.sha256(_canonical_json(plan.manifest)).hexdigest()

    @classmethod
    def _validate_plan_binding(
        cls, payload: Mapping[str, Any], plan: LoraTrainingPlan
    ) -> None:
        if (
            type(payload.get("schema_version")) is not int
            or payload.get("schema_version") != 1
            or payload.get("job_id") != plan.job_id
            or payload.get("contract") != LORA_CONTRACT
            or payload.get("candidate_sha256") != plan.manifest["candidate_sha256"]
            or payload.get("manifest_sha256") != cls._manifest_sha256(plan)
        ):
            raise LoraTrainingError("LoRA gateway state does not match the planned job")

    @classmethod
    def _validate_job_state(
        cls, payload: Mapping[str, Any], plan: LoraTrainingPlan
    ) -> None:
        cls._validate_plan_binding(payload, plan)
        state = payload.get("state")
        retry_mode = payload.get("retry_mode")
        retriable = payload.get("retriable")
        if (
            set(payload) != _JOB_STATE_FIELDS
            or state not in _JOB_STATES
            or retry_mode not in _RETRY_MODES
            or type(retriable) is not bool
            or retriable is not (retry_mode != "none")
            or (retry_mode != "none" and state not in {"failed", "interrupted"})
            or type(payload.get("created_at_unix")) is not int
            or type(payload.get("updated_at_unix")) is not int
            or not isinstance(payload.get("blocker_code"), str)
            or any(
                payload.get(key) is not None and type(payload.get(key)) is not int
                for key in ("started_at_unix", "completed_at_unix", "exit_code")
            )
        ):
            raise LoraTrainingError("LoRA gateway returned an invalid job state")

    @classmethod
    def _validate_plan(cls, plan: LoraTrainingPlan) -> None:
        if (
            not isinstance(plan.manifest, Mapping)
            or set(plan.manifest)
            != {
                "schema_version",
                "contract",
                "candidate_sha256",
                "consent",
                "references",
            }
            or type(plan.manifest.get("schema_version")) is not int
            or plan.manifest.get("schema_version") != 1
            or plan.manifest.get("contract") != LORA_CONTRACT
            or plan.manifest.get("candidate_sha256")
            != current_lora_candidate_sha256()
            or plan.manifest.get("consent") is not True
            or hashlib.sha256(_canonical_json(plan.manifest)).hexdigest()[:32]
            != plan.job_id
            or not _HEX32.fullmatch(plan.job_id)
        ):
            raise LoraTrainingError("LoRA training plan manifest changed after admission")
        references = plan.manifest.get("references")
        if (
            not isinstance(references, list)
            or len(references) != 4
            or len(plan.sources) != 4
        ):
            raise LoraTrainingError("LoRA training plan references changed after admission")
        expected_captions = fixed_character_captions("hkkperson")
        for index, (reference, (payload, digest)) in enumerate(
            zip(references, plan.sources, strict=True)
        ):
            if (
                not isinstance(reference, Mapping)
                or set(reference) != {"sha256", "caption"}
                or reference.get("sha256") != digest
                or reference.get("caption") != expected_captions[index]
                or hashlib.sha256(payload).hexdigest() != digest
                or not payload
                or len(payload) > MAX_BLOB_BYTES
            ):
                raise LoraTrainingError("LoRA training plan references changed after admission")
        if len({digest for _payload, digest in plan.sources}) != 4:
            raise LoraTrainingError("LoRA training plan references changed after admission")

    @staticmethod
    def _payload(response: requests.Response) -> Mapping[str, Any]:
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise LoraTrainingError("LoRA gateway response is too large")
        try:
            value = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise LoraTrainingError("LoRA gateway returned invalid JSON") from exc
        if not isinstance(value, Mapping):
            raise LoraTrainingError("LoRA gateway returned an invalid object")
        return value

    def get_readiness(self, expected_candidate_sha256: str) -> LoraReadiness:
        if not _SHA256.fullmatch(expected_candidate_sha256):
            raise ValueError("invalid LoRA candidate digest")
        try:
            response = self.session.get(
                f"{self.server_url}/api/identity-lora/ready",
                headers=self._headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LoraTrainingError("LoRA gateway readiness is unreachable") from exc
        payload = self._payload(response)
        if (
            response.status_code not in {200, 503}
            or set(payload)
            != {
                "schema_version",
                "contract",
                "candidate_sha256",
                "state",
                "blocker_code",
                "job_submission_ready",
            }
            or type(payload.get("schema_version")) is not int
            or payload.get("schema_version") != 1
            or payload.get("contract") != LORA_CONTRACT
            or payload.get("candidate_sha256") != expected_candidate_sha256
            or payload.get("state") not in {"ready", "blocked"}
            or (payload.get("state") == "ready") != (response.status_code == 200)
            or not isinstance(payload.get("blocker_code"), str)
            or type(payload.get("job_submission_ready")) is not bool
            or (payload.get("state") == "ready" and payload.get("blocker_code") != "")
            or (payload.get("state") == "blocked" and not payload.get("blocker_code"))
            or (payload.get("state") == "ready" and payload.get("job_submission_ready") is not True)
        ):
            raise LoraTrainingError("LoRA gateway readiness contract is invalid")
        return LoraReadiness(
            state=str(payload["state"]),
            blocker_code=str(payload["blocker_code"]),
            candidate_sha256=expected_candidate_sha256,
            job_submission_ready=bool(payload["job_submission_ready"]),
        )

    def get_job(self, job_id: str) -> Mapping[str, Any] | None:
        if not _HEX32.fullmatch(job_id):
            raise ValueError("invalid LoRA job ID")
        try:
            response = self.session.get(
                f"{self.server_url}/api/identity-lora/jobs/{job_id}",
                headers=self._headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LoraTrainingStateUnknown(job_id) from exc
        if response.status_code == 404:
            return None
        payload = self._payload(response)
        if response.status_code != 200:
            raise LoraTrainingError(str(payload.get("error") or "LoRA status failed"))
        if payload.get("job_id") != job_id or payload.get("contract") != LORA_CONTRACT:
            raise LoraTrainingError("LoRA status does not match the planned job")
        return payload

    def _put_blob(self, content: bytes, expected_sha256: str, job_id: str) -> None:
        if len(content) > MAX_BLOB_BYTES or hashlib.sha256(content).hexdigest() != expected_sha256:
            raise LoraTrainingError("LoRA reference bytes do not match the planned upload")
        try:
            response = self.session.put(
                f"{self.server_url}/api/identity-lora/blobs/{expected_sha256}",
                headers={**self._headers, "Content-Type": "application/octet-stream"},
                data=content,
                timeout=(self.timeout[0], max(self.timeout[1], 120.0)),
            )
        except requests.RequestException as exc:
            raise LoraTrainingStateUnknown(
                job_id, "LoRA reference upload outcome is unknown"
            ) from exc
        payload = self._payload(response)
        if response.status_code not in {200, 201}:
            raise LoraTrainingError(str(payload.get("error") or "LoRA reference upload failed"))
        if payload.get("sha256") != expected_sha256 or payload.get("size_bytes") != len(content):
            raise LoraTrainingError("LoRA gateway did not confirm the uploaded reference")

    def _put_job(self, plan: LoraTrainingPlan) -> Mapping[str, Any]:
        try:
            response = self.session.put(
                f"{self.server_url}/api/identity-lora/jobs/{plan.job_id}",
                headers={**self._headers, "Content-Type": "application/json"},
                data=_canonical_json(plan.manifest),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LoraTrainingStateUnknown(
                plan.job_id, "LoRA training submission outcome is unknown"
            ) from exc
        payload = self._payload(response)
        if response.status_code == 409:
            raise LoraTrainingConflict(str(payload.get("error") or "LoRA job conflict"))
        if response.status_code == 503 and payload.get("state") == "unknown":
            self._validate_job_state(payload, plan)
            raise LoraTrainingStateUnknown(
                plan.job_id, "LoRA training launch outcome is unknown"
            )
        if response.status_code not in {200, 202}:
            raise LoraTrainingError(str(payload.get("error") or "LoRA training submission failed"))
        self._validate_job_state(payload, plan)
        return payload

    def _resume(self, plan: LoraTrainingPlan) -> Mapping[str, Any]:
        job_id = plan.job_id
        try:
            response = self.session.post(
                f"{self.server_url}/api/identity-lora/jobs/{job_id}/resume",
                headers={**self._headers, "Content-Type": "application/json"},
                data=b"{}",
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LoraTrainingStateUnknown(
                job_id, "LoRA training resume outcome is unknown"
            ) from exc
        payload = self._payload(response)
        if response.status_code == 409:
            raise LoraTrainingConflict(str(payload.get("error") or "LoRA resume conflict"))
        if response.status_code == 503 and payload.get("state") == "unknown":
            self._validate_job_state(payload, plan)
            raise LoraTrainingStateUnknown(
                job_id, "LoRA training resume outcome is unknown"
            )
        if response.status_code != 202:
            raise LoraTrainingError(str(payload.get("error") or "LoRA resume failed"))
        self._validate_job_state(payload, plan)
        return payload

    def _evidence(self, plan: LoraTrainingPlan) -> LoraTrainingEvidence:
        job_id = plan.job_id
        try:
            response = self.session.get(
                f"{self.server_url}/api/identity-lora/jobs/{job_id}/evidence",
                headers=self._headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LoraTrainingStateUnknown(job_id) from exc
        payload = self._payload(response)
        if response.status_code != 200:
            raise LoraTrainingError(str(payload.get("error") or "LoRA evidence unavailable"))
        self._validate_plan_binding(payload, plan)
        if (
            type(payload.get("schema_version")) is not int
            or payload.get("schema_version") != 1
            or payload.get("job_id") != job_id
            or payload.get("contract") != LORA_CONTRACT
            or payload.get("state") != "succeeded"
        ):
            raise LoraTrainingError("LoRA evidence does not match the completed job")
        adapter = payload.get("adapter")
        training = payload.get("training")
        metadata = payload.get("adapter_metadata")
        metadata_sha256 = payload.get("adapter_metadata_sha256")
        if (
            not isinstance(adapter, Mapping)
            or not isinstance(training, Mapping)
            or not isinstance(metadata, Mapping)
            or not isinstance(metadata_sha256, str)
            or not _SHA256.fullmatch(metadata_sha256)
        ):
            raise LoraTrainingError("LoRA evidence is incomplete")
        digest = adapter.get("sha256")
        size = adapter.get("size_bytes")
        comfy_name = adapter.get("comfy_name")
        if (
            not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
            or type(size) is not int
            or size <= 0
            or not isinstance(comfy_name, str)
            or not _SAFE_COMFY_NAME.fullmatch(comfy_name)
            or comfy_name != f"identity-lora-{digest}.safetensors"
        ):
            raise LoraTrainingError("LoRA adapter evidence is invalid")
        metadata_adapter = metadata.get("adapter")
        metadata_training = metadata.get("training")
        if (
            type(metadata.get("schema_version")) is not int
            or metadata.get("schema_version") != 1
            or metadata.get("state") != "training_passed"
            or metadata.get("job_id") != job_id
            or not isinstance(metadata_adapter, Mapping)
            or metadata_adapter.get("filename") != comfy_name
            or metadata_adapter.get("bytes") != size
            or metadata_adapter.get("sha256") != digest
            or not isinstance(metadata_training, Mapping)
            or metadata_training.get("package_sha256")
            != plan.manifest["candidate_sha256"]
            or hashlib.sha256(_canonical_json(metadata)).hexdigest()
            != metadata_sha256
        ):
            raise LoraTrainingError("LoRA adapter metadata is not bound to this job")
        expected_training = {
            "steps": 500,
            "resolution": 512,
            "rank": 16,
            "seed": 0,
            "batch_size": 1,
        }
        if any(
            type(training.get(key)) is not int or training.get(key) != value
            for key, value in expected_training.items()
        ):
            raise LoraTrainingError("LoRA training evidence differs from the fixed canary")
        elapsed = training.get("elapsed_seconds")
        peak_vram = training.get("peak_vram_bytes")
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or not math.isfinite(float(elapsed))
            or elapsed <= 0
            or type(peak_vram) is not int
            or peak_vram <= 0
        ):
            raise LoraTrainingError("LoRA telemetry evidence is invalid")
        return LoraTrainingEvidence(
            job_id=job_id,
            adapter_sha256=digest,
            adapter_size_bytes=size,
            comfy_name=comfy_name,
            elapsed_seconds=float(elapsed),
            peak_vram_bytes=peak_vram,
            adapter_metadata=dict(metadata),
            adapter_metadata_sha256=metadata_sha256,
            raw=payload,
        )

    def ensure_training(
        self,
        plan: LoraTrainingPlan,
        *,
        allow_interrupted_resume: bool = False,
        timeout_s: float = 4 * 60 * 60,
        poll_seconds: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> LoraTrainingEvidence:
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value <= 0
            for value in (timeout_s, poll_seconds)
        ):
            raise ValueError("LoRA training wait bounds must be finite and positive")
        self._validate_plan(plan)
        status = self.get_job(plan.job_id)
        if status is not None:
            self._validate_job_state(status, plan)
        if status is None:
            for payload, digest in plan.sources:
                self._put_blob(payload, digest, plan.job_id)
            status = self._put_job(plan)
        state = status.get("state")
        if state in {"failed", "interrupted"} and status.get("retriable") is True:
            if not allow_interrupted_resume:
                raise LoraTrainingStateUnknown(
                    plan.job_id,
                    "LoRA training or benchmark requires an explicit same-job resume",
                )
            status = self._resume(plan)
            state = status.get("state")
        deadline = time.monotonic() + float(timeout_s)
        while state not in _TERMINAL_STATES:
            if state not in _ACTIVE_STATES:
                raise LoraTrainingError("LoRA gateway returned an invalid job state")
            if time.monotonic() >= deadline:
                raise LoraTrainingStateUnknown(
                    plan.job_id, "LoRA training exceeded the bounded wait; it was not resubmitted"
                )
            sleep(float(poll_seconds))
            refreshed = self.get_job(plan.job_id)
            if refreshed is None:
                raise LoraTrainingStateUnknown(plan.job_id)
            self._validate_job_state(refreshed, plan)
            status = refreshed
            state = status.get("state")
        if state == "succeeded":
            return self._evidence(plan)
        if state in {"unknown", "interrupted"}:
            raise LoraTrainingStateUnknown(plan.job_id)
        raise LoraTrainingError(
            str(status.get("blocker_code") or "LoRA training failed")
        )
