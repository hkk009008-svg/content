#!/usr/bin/env python3
"""One-shot execution probe and sequential FLUX.2 Klein capacity benchmark.

Every run verifies installed bytes and live ComfyUI schema before uploading the
committed fixed fixture.  Prompt submission is deliberately one-shot: an
ambiguous response is recorded as UNKNOWN and is never retried automatically.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parent
CAPABILITY = "image-flux2-klein"
FIXED_PROMPT = (
    "Studio product photograph of a small matte-black mechanical compass, "
    "neutral gray background, soft diffused key light, centered composition."
)
FIXED_SEED = 424242
FIXED_ASPECT_RATIO = "1:1"
BENCHMARK_REFERENCE_COUNTS = (1, 2, 10)
SAVE_NODE_ID = "23"
UPLOAD_SUBFOLDER = "content-flux2-klein"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_IMAGE_BYTES = 256 * 1024 * 1024
DEFAULT_EXECUTION_TIMEOUT_SECONDS = 1800.0
DEFAULT_POLL_INTERVAL_SECONDS = 2.0


class RuntimeContractError(RuntimeError):
    """A worker, execution, artifact, or evidence contract failed closed."""


class SubmissionUnknownError(RuntimeContractError):
    """The caller cannot prove whether ComfyUI accepted the one prompt."""


def _load_sibling(name: str, filename: str):
    path = ROOT / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeContractError(f"cannot load bound package tool {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeContractError(f"cannot read {label}") from exc
    if not isinstance(value, Mapping):
        raise RuntimeContractError(f"{label} must be a JSON object")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RuntimeContractError(f"cannot hash {path.name}") from exc
    return digest.hexdigest()


def _contract_digest(value: object) -> str:
    return _sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_bytes_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise RuntimeContractError(f"refusing to overwrite evidence artifact {path}") from exc


def _write_json_new(path: Path, payload: Mapping[str, Any]) -> None:
    _write_bytes_new(
        path, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(
                (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _bound_evidence_path(state_root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise RuntimeContractError("status evidence path is invalid")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise RuntimeContractError("status evidence path escapes the state root")
    state_root = state_root.resolve()
    path = state_root.joinpath(*parsed.parts).resolve(strict=False)
    if state_root not in path.parents or path.is_symlink() or not path.is_file():
        raise RuntimeContractError("status evidence path is missing or unsafe")
    return path


def load_runtime_status(
    state_root: Path,
    *,
    package_root: Path = ROOT,
    verify_evidence: bool = True,
) -> Mapping[str, Any]:
    """Validate the atomic gateway status and its immutable evidence chain."""

    state_root = state_root.resolve()
    status = _load_json(state_root / "status.json", "runtime status")
    state = status.get("state")
    expected_truth = {
        "not_installed": (False, False, "not_run", "candidate_execution_probe_not_run"),
        "needs_benchmark": (False, True, "not_run", "candidate_benchmark_not_run"),
        "ready": (True, True, "passed", None),
    }
    if (
        status.get("schema_version") != 1
        or status.get("capability") != CAPABILITY
        or state not in expected_truth
        or status.get("artifacts_installed") is not True
        or status.get("license_review_state") != "official_source_derivation_verified"
    ):
        raise RuntimeContractError("runtime status identity/state contract is invalid")
    startup_ready, execution_proven, benchmark_state, blocker = expected_truth[state]
    if (
        status.get("startup_ready") is not startup_ready
        or status.get("execution_proven") is not execution_proven
        or status.get("benchmark_state") != benchmark_state
        or status.get("blocker_code") != blocker
        or status.get("artifact_manifest_sha256")
        != _sha256_file(package_root / "models.json")
        or status.get("workflow_contract_sha256")
        != _sha256_file(package_root / "workflow.py")
    ):
        raise RuntimeContractError("runtime status truth/binding contract drifted")
    runtime_hash = status.get("runtime_contract_sha256")
    if state == "not_installed":
        if runtime_hash is not None:
            raise RuntimeContractError("pre-probe status overclaims a runtime binding")
    elif not isinstance(runtime_hash, str) or len(runtime_hash) != 64:
        raise RuntimeContractError("post-probe status lacks its runtime binding")

    evidence = status.get("evidence")
    if not isinstance(evidence, Mapping) or set(evidence) != {
        "install", "canary", "benchmark"
    }:
        raise RuntimeContractError("runtime status evidence inventory is invalid")
    required = {
        "not_installed": {"install"},
        "needs_benchmark": {"install", "canary"},
        "ready": {"install", "canary", "benchmark"},
    }[state]
    if any((key in required) != isinstance(evidence.get(key), Mapping) for key in evidence):
        raise RuntimeContractError("runtime status evidence presence contradicts state")
    if not verify_evidence:
        return status

    loaded: dict[str, Mapping[str, Any]] = {}
    expected_statuses = {
        "install": "installed_needs_execution_probe",
        "canary": "fixed_probe_passed",
        "benchmark": "benchmark_passed",
    }
    for key in required:
        record = evidence[key]
        if set(record) - {
            "path", "sha256", "run_id", "status", "workflow_sha256", "output_sha256"
        }:
            raise RuntimeContractError("runtime evidence record has unexpected fields")
        path = _bound_evidence_path(state_root, record.get("path"))
        if (
            not isinstance(record.get("sha256"), str)
            or _sha256_file(path) != record.get("sha256")
        ):
            raise RuntimeContractError("runtime evidence SHA-256 does not match")
        payload = _load_json(path, f"{key} evidence")
        if (
            payload.get("capability") != CAPABILITY
            or payload.get("run_id", payload.get("benchmark_id")) != record.get("run_id")
            or payload.get("status") != expected_statuses[key]
            or record.get("status") != expected_statuses[key]
        ):
            raise RuntimeContractError("runtime evidence identity/status does not match")
        loaded[key] = payload
    if state in {"needs_benchmark", "ready"}:
        canary = loaded["canary"]
        if (
            canary.get("runtime_contract_sha256") != runtime_hash
            or canary.get("workflow_sha256") != evidence["canary"].get("workflow_sha256")
            or not isinstance(canary.get("output"), Mapping)
            or canary["output"].get("sha256") != evidence["canary"].get("output_sha256")
        ):
            raise RuntimeContractError("canary evidence binding does not match status")
    if state == "ready":
        benchmark = loaded["benchmark"]
        if (
            benchmark.get("runtime_contract_sha256") != runtime_hash
            or benchmark.get("probe_evidence_sha256") != evidence["canary"].get("sha256")
            or benchmark.get("sequence") != [1, 2, 10]
            or benchmark.get("benchmark_state") != "passed"
        ):
            raise RuntimeContractError("benchmark evidence binding does not match status")
    return status


def _status_evidence_record(
    state_root: Path,
    evidence_path: Path,
    payload: Mapping[str, Any],
    *,
    include_output: bool = False,
) -> Mapping[str, Any]:
    state_root = state_root.resolve()
    evidence_path = evidence_path.resolve()
    if state_root not in evidence_path.parents:
        raise RuntimeContractError("evidence path escapes the state root")
    record: dict[str, Any] = {
        "path": str(evidence_path.relative_to(state_root)).replace("\\", "/"),
        "sha256": _sha256_file(evidence_path),
        "run_id": payload.get("run_id", payload.get("benchmark_id")),
        "status": payload.get("status"),
    }
    if include_output:
        output = payload.get("output")
        if not isinstance(output, Mapping):
            raise RuntimeContractError("canary evidence output is invalid")
        record.update(
            {
                "workflow_sha256": payload.get("workflow_sha256"),
                "output_sha256": output.get("sha256"),
            }
        )
    return record


def load_fixed_fixture(package_root: Path = ROOT) -> tuple[bytes, Mapping[str, Any]]:
    contract = _load_json(package_root / "fixtures" / "reference.json", "fixture contract")
    if contract.get("path") != "reference.png" or contract.get("encoding") != "base64":
        raise RuntimeContractError("fixed fixture contract drifted")
    payload_name = contract.get("payload")
    if payload_name != "reference.png.b64":
        raise RuntimeContractError("fixed fixture payload binding drifted")
    try:
        encoded = (package_root / "fixtures" / payload_name).read_text(encoding="ascii").strip()
        payload = base64.b64decode(encoded, validate=True)
    except (OSError, ValueError) as exc:
        raise RuntimeContractError("fixed fixture payload cannot be decoded") from exc
    if len(payload) != contract.get("expected_bytes") or _sha256_bytes(payload) != contract.get("sha256"):
        raise RuntimeContractError("fixed fixture failed exact byte/SHA-256 verification")
    _validate_decoded_image(payload, contract.get("decoded"), label="fixed fixture")
    return payload, contract


def _validate_decoded_image(
    payload: bytes, expected: object, *, label: str
) -> Mapping[str, Any]:
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise RuntimeContractError("Pillow is required for decoded-output validation") from exc
    if not isinstance(expected, Mapping):
        raise RuntimeContractError(f"{label} decoded-image contract is invalid")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            actual = {
                "format": image.format,
                "mode": image.mode,
                "width": image.width,
                "height": image.height,
            }
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise RuntimeContractError(f"{label} is not a fully decodable image") from exc
    for key in ("format", "mode", "width", "height"):
        if expected.get(key) is not None and actual[key] != expected.get(key):
            raise RuntimeContractError(f"{label} decoded {key} differs from contract")
    return actual


def _is_link_or_reparse(path: Path, metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    return path.is_symlink() or bool(reparse_flag and file_attributes & reparse_flag)


def _require_runtime_directory(path: Path, label: str) -> Path:
    """Resolve one explicit Comfy runtime root without following a root link."""

    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise RuntimeContractError(f"{label} is missing or inaccessible") from exc
    if not stat.S_ISDIR(metadata.st_mode) or _is_link_or_reparse(path, metadata):
        raise RuntimeContractError(f"{label} must be a real directory")
    return resolved


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _require_separate_runtime_roots(
    state_root: Path, input_root: Path, output_root: Path
) -> None:
    if any(
        _paths_overlap(left, right)
        for left, right in (
            (state_root, input_root),
            (state_root, output_root),
            (input_root, output_root),
        )
    ):
        raise RuntimeContractError(
            "candidate state and worker input/output roots must be separate directories"
        )


def prepare_runtime_context(
    *,
    comfy_root: Path,
    state_root: Path,
    input_root: Path,
    output_root: Path,
    package_root: Path = ROOT,
) -> Mapping[str, Any]:
    """Verify source package, install evidence, and every installed model byte."""

    preflight = _load_sibling(
        "windows_flux2_klein_bound_preflight_runtime", "preflight.py"
    )
    result = preflight.validate_package(package_root)
    if result.get("status") != "candidate_contract_valid":
        raise RuntimeContractError("static package preflight did not pass")
    installer = _load_sibling(
        "windows_flux2_klein_bound_install_runtime", "install.py"
    )
    resolved_root, model_root = installer.validate_comfy_root(comfy_root)
    resolved_state = _require_runtime_directory(state_root, "candidate state root")
    resolved_input = _require_runtime_directory(input_root, "worker input root")
    resolved_output = _require_runtime_directory(output_root, "worker output root")
    _require_separate_runtime_roots(resolved_state, resolved_input, resolved_output)
    manifest = _load_json(package_root / "models.json", "model manifest")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise RuntimeContractError("model artifact manifest is invalid")
    install_evidence_path = resolved_state / "install.json"
    install_evidence = _load_json(install_evidence_path, "install evidence")
    package_binding = installer._package_binding(package_root)
    if (
        install_evidence.get("capability") != CAPABILITY
        or install_evidence.get("status") != "installed_needs_execution_probe"
        or install_evidence.get("execution_proven") is not False
        or install_evidence.get("package") != package_binding
    ):
        raise RuntimeContractError("install evidence is missing, stale, or overclaims readiness")

    expected_records = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise RuntimeContractError("artifact record is invalid")
        destination = installer._safe_destination(model_root, artifact.get("destination"))
        try:
            installer._verify_file(destination, artifact, f"installed model {artifact.get('id')}")
        except Exception as exc:
            raise RuntimeContractError("installed model verification failed") from exc
        expected_records.append(
            {
                "id": artifact.get("id"),
                "destination": artifact.get("destination"),
                "expected_bytes": artifact.get("expected_bytes"),
                "sha256": artifact.get("sha256"),
            }
        )
    installed_records = install_evidence.get("artifacts")
    if not isinstance(installed_records, list) or [
        {key: record.get(key) for key in ("id", "destination", "expected_bytes", "sha256")}
        for record in installed_records
        if isinstance(record, Mapping)
    ] != expected_records:
        raise RuntimeContractError("install evidence artifact set drifted")
    fixture, fixture_contract = load_fixed_fixture(package_root)
    context_binding = {
        "package": package_binding,
        "install_evidence_sha256": _sha256_file(install_evidence_path),
        "artifacts": expected_records,
        "fixture": {
            "bytes": fixture_contract.get("expected_bytes"),
            "sha256": fixture_contract.get("sha256"),
        },
    }
    return {
        "comfy_root": resolved_root,
        "input_root": resolved_input,
        "output_root": resolved_output,
        "model_root": model_root,
        "state_root": resolved_state,
        "package_root": package_root.resolve(),
        "fixture": fixture,
        "fixture_contract": fixture_contract,
        "binding": context_binding,
        "runtime_contract_sha256": _contract_digest(context_binding),
    }


def _read_bounded(response: Any, maximum: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(1024 * 1024, maximum + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum:
            raise RuntimeContractError("worker response exceeded the byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


class ComfyClient:
    """Minimal bounded ComfyUI HTTP client with no automatic retries."""

    def __init__(
        self,
        endpoint: str,
        *,
        token: str | None = None,
        timeout: float = 30.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ):
        parsed = urllib.parse.urlsplit(endpoint.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeContractError("worker endpoint must be an absolute HTTP(S) URL")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise RuntimeContractError("worker endpoint may not include a path/query/fragment")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"} and not token:
            raise RuntimeContractError("non-loopback plaintext worker access requires authentication")
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.opener = opener
        self.endpoint_sha256 = _sha256_bytes(self.endpoint.encode("utf-8"))

    def _headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "Content-FLUX2-Klein/1"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if extra:
            headers.update(extra)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        maximum: int = MAX_JSON_BYTES,
    ) -> tuple[bytes, Mapping[str, str]]:
        request = urllib.request.Request(
            self.endpoint + path,
            data=data,
            headers=self._headers(headers),
            method=method,
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                body = _read_bounded(response, maximum)
                response_headers = dict(response.headers.items())
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            raise RuntimeContractError("worker request failed") from exc
        return body, response_headers

    def _json(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        data = None
        headers = None
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers = {"Content-Type": "application/json", "Content-Length": str(len(data))}
        body, _ = self._request(method, path, data=data, headers=headers)
        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeContractError("worker returned invalid JSON") from exc
        if not isinstance(value, Mapping):
            raise RuntimeContractError("worker JSON response is not an object")
        return value

    def get_object_info(self) -> Mapping[str, Any]:
        return self._json("GET", "/object_info")

    def get_queue(self) -> Mapping[str, Any]:
        return self._json("GET", "/queue")

    def get_system_stats(self) -> Mapping[str, Any]:
        return self._json("GET", "/system_stats")

    def upload_image(self, payload: bytes, filename: str) -> str:
        if not filename or any(character in filename for character in "/\\\x00"):
            raise RuntimeContractError("upload filename is unsafe")
        boundary = "----ContentFlux2Klein" + uuid.uuid4().hex
        pieces = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\nContent-Type: image/png\r\n\r\n".encode(),
            payload,
            f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\ninput\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"subfolder\"\r\n\r\n{UPLOAD_SUBFOLDER}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\nfalse\r\n".encode(),
            f"--{boundary}--\r\n".encode(),
        ]
        body = b"".join(pieces)
        raw, _ = self._request(
            "POST",
            "/upload/image",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
        )
        try:
            response = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeContractError("upload returned invalid JSON") from exc
        if not isinstance(response, Mapping) or response.get("type") != "input":
            raise RuntimeContractError("upload response did not prove an input image")
        name = response.get("name")
        subfolder = response.get("subfolder", "")
        if not isinstance(name, str) or not isinstance(subfolder, str):
            raise RuntimeContractError("upload response filename is invalid")
        remote = f"{subfolder}/{name}" if subfolder else name
        return _safe_remote_name(remote)

    def submit_once(self, workflow: Mapping[str, Any], client_id: str) -> str:
        try:
            response = self._json(
                "POST", "/prompt", {"prompt": workflow, "client_id": client_id}
            )
        except RuntimeContractError as exc:
            raise SubmissionUnknownError(
                "prompt submission is UNKNOWN; do not retry automatically"
            ) from exc
        prompt_id = response.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise SubmissionUnknownError(
                "prompt submission response is UNKNOWN; do not retry automatically"
            )
        return prompt_id

    def get_history(self, prompt_id: str) -> Mapping[str, Any]:
        encoded = urllib.parse.quote(prompt_id, safe="")
        return self._json("GET", f"/history/{encoded}")

    def download_output(self, output: Mapping[str, Any]) -> tuple[bytes, str]:
        filename = output.get("filename")
        subfolder = output.get("subfolder", "")
        output_type = output.get("type")
        if output_type != "output" or not isinstance(filename, str) or not isinstance(subfolder, str):
            raise RuntimeContractError("SaveImage output locator is invalid")
        if any(character in filename for character in "/\\\x00"):
            raise RuntimeContractError("SaveImage output filename is unsafe")
        _safe_remote_name(f"{subfolder}/{filename}" if subfolder else filename)
        query = urllib.parse.urlencode(
            {"filename": filename, "subfolder": subfolder, "type": output_type}
        )
        body, headers = self._request(
            "GET", f"/view?{query}", maximum=MAX_IMAGE_BYTES
        )
        content_type = headers.get("Content-Type", "").split(";", 1)[0].lower()
        if not content_type.startswith("image/"):
            raise RuntimeContractError("worker output is not an image response")
        if not body:
            raise RuntimeContractError("worker output image is empty")
        return body, content_type


def _safe_remote_name(value: str) -> str:
    if "\\" in value or "\x00" in value:
        raise RuntimeContractError("remote filename is unsafe")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.name:
        raise RuntimeContractError("remote filename escapes the input/output root")
    return str(path)


def _assert_empty_queue(queue: object) -> None:
    if not isinstance(queue, Mapping):
        raise RuntimeContractError("worker queue response is invalid")
    running = queue.get("queue_running")
    pending = queue.get("queue_pending")
    if not isinstance(running, list) or not isinstance(pending, list):
        raise RuntimeContractError("worker queue shape is invalid")
    if running or pending:
        raise RuntimeContractError("worker queue must be empty before a candidate run")


def _gpu_sample(stats: object, elapsed_seconds: float) -> Mapping[str, Any]:
    if not isinstance(stats, Mapping) or not isinstance(stats.get("devices"), list):
        raise RuntimeContractError("worker system_stats device list is invalid")
    candidates = []
    for device in stats["devices"]:
        if not isinstance(device, Mapping):
            continue
        device_type = str(device.get("type", "")).casefold()
        name = str(device.get("name", ""))
        if "cuda" in device_type or "nvidia" in name.casefold():
            candidates.append(device)
    if len(candidates) != 1:
        raise RuntimeContractError("worker must expose exactly one NVIDIA/CUDA device")
    device = candidates[0]

    def required_nonnegative(name: str) -> int:
        value = device.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RuntimeContractError(f"worker GPU field {name} is invalid")
        return value

    total = required_nonnegative("vram_total")
    free = required_nonnegative("vram_free")
    torch_total = required_nonnegative("torch_vram_total")
    torch_free = required_nonnegative("torch_vram_free")
    if total <= 0 or free > total or torch_free > torch_total or torch_total > total:
        raise RuntimeContractError("worker GPU memory counters are inconsistent")
    return {
        "elapsed_seconds": round(max(0.0, elapsed_seconds), 6),
        "device_index": device.get("index"),
        "device_type": device.get("type"),
        "device_name": name,
        "vram_total_bytes": total,
        "vram_free_bytes": free,
        "vram_used_bytes": total - free,
        "torch_vram_total_bytes": torch_total,
        "torch_vram_free_bytes": torch_free,
        "torch_vram_used_bytes": torch_total - torch_free,
    }


def _history_record(history: object, prompt_id: str) -> Mapping[str, Any] | None:
    if not isinstance(history, Mapping):
        raise RuntimeContractError("worker history response is invalid")
    record = history.get(prompt_id)
    if record is None:
        return None
    if not isinstance(record, Mapping):
        raise RuntimeContractError("worker history record is invalid")
    status = record.get("status")
    if not isinstance(status, Mapping):
        raise RuntimeContractError("worker history status is invalid")
    status_text = status.get("status_str")
    if status_text in {"error", "failed"}:
        raise RuntimeContractError("worker execution failed")
    if status.get("completed") is True:
        if status_text not in {"success", None}:
            raise RuntimeContractError("worker completed with a non-success status")
        return record
    return None


def _save_output_locator(record: Mapping[str, Any]) -> Mapping[str, Any]:
    outputs = record.get("outputs")
    node = outputs.get(SAVE_NODE_ID) if isinstance(outputs, Mapping) else None
    images = node.get("images") if isinstance(node, Mapping) else None
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], Mapping):
        raise RuntimeContractError("completed workflow lacks exactly one SaveImage output")
    output = images[0]
    # Validate before returning only the non-secret output locator.
    filename = output.get("filename")
    subfolder = output.get("subfolder", "")
    if output.get("type") != "output" or not isinstance(filename, str) or not isinstance(subfolder, str):
        raise RuntimeContractError("SaveImage output locator is invalid")
    _safe_remote_name(f"{subfolder}/{filename}" if subfolder else filename)
    return {"filename": filename, "subfolder": subfolder, "type": "output"}


def _gpu_summary(samples: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not samples:
        raise RuntimeContractError("execution has no GPU samples")
    identities = {
        (sample.get("device_index"), sample.get("device_name"), sample.get("vram_total_bytes"))
        for sample in samples
    }
    if len(identities) != 1:
        raise RuntimeContractError("GPU identity or capacity changed during execution")
    return {
        "sample_count": len(samples),
        "max_sample_interval_seconds": max(
            (float(right["elapsed_seconds"]) - float(left["elapsed_seconds"]))
            for left, right in zip(samples, samples[1:])
        ) if len(samples) > 1 else 0.0,
        "peak_vram_used_bytes": max(int(sample["vram_used_bytes"]) for sample in samples),
        "minimum_vram_free_bytes": min(int(sample["vram_free_bytes"]) for sample in samples),
        "peak_torch_vram_used_bytes": max(
            int(sample["torch_vram_used_bytes"]) for sample in samples
        ),
        "device": {
            "index": samples[0].get("device_index"),
            "type": samples[0].get("device_type"),
            "name": samples[0].get("device_name"),
            "vram_total_bytes": samples[0].get("vram_total_bytes"),
        },
    }


def _bound_runtime_file(root: Path, relative_name: str, label: str) -> Path:
    relative = PurePosixPath(_safe_remote_name(relative_name))
    candidate = root.joinpath(*relative.parts)
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise RuntimeContractError(
                f"{label} is missing from its configured root"
            ) from exc
        if _is_link_or_reparse(current, metadata):
            raise RuntimeContractError(f"{label} path contains a link or reparse point")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeContractError(f"{label} parent is not a directory")
    resolved = candidate.resolve(strict=True)
    if root not in resolved.parents:
        raise RuntimeContractError(f"{label} escapes its configured runtime root")
    return resolved


def _verified_runtime_file(
    root: Path, relative_name: str, expected_hash: str, label: str
) -> Path:
    candidate = _bound_runtime_file(root, relative_name, label)
    metadata = candidate.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeContractError(f"{label} must be an owned regular file")
    if _sha256_file(candidate) != expected_hash:
        raise RuntimeContractError(f"{label} hash does not match the owned artifact")
    return candidate


def _expected_upload_name(run_id: str, index: int) -> str:
    return f"{UPLOAD_SUBFOLDER}/{run_id}-reference-{index:02d}.png"


def _verify_owned_input(
    input_root: Path,
    remote_name: str,
    *,
    run_id: str,
    index: int,
    fixture_hash: str,
) -> Path:
    expected = _expected_upload_name(run_id, index)
    if remote_name != expected:
        raise RuntimeContractError("worker did not preserve the owned upload name")
    return _verified_runtime_file(
        input_root, remote_name, fixture_hash, f"owned input {index}"
    )


def _delete_verified_files(paths: Sequence[Path], label: str) -> None:
    for path in paths:
        try:
            path.unlink()
        except OSError as exc:
            raise RuntimeContractError(f"could not remove {label}") from exc
        if path.exists():
            raise RuntimeContractError(f"{label} remained after cleanup")


def _cleanup_owned_inputs(
    input_root: Path,
    names: Sequence[str],
    *,
    run_id: str,
    fixture_hash: str,
) -> Mapping[str, Any]:
    paths = [
        _verify_owned_input(
            input_root,
            name,
            run_id=run_id,
            index=index,
            fixture_hash=fixture_hash,
        )
        for index, name in enumerate(names, 1)
    ]
    _delete_verified_files(paths, "owned input")
    return {"state": "deleted", "count": len(paths)}


def _owned_output_name(
    locator: Mapping[str, Any], *, run_id: str, evidence_kind: str
) -> str:
    filename = locator.get("filename")
    subfolder = locator.get("subfolder", "")
    if not isinstance(filename, str) or subfolder != "":
        raise RuntimeContractError("owned output must remain in the output root")
    prefix = f"flux2-klein-{evidence_kind}-{run_id[:12]}"
    if not filename.startswith(prefix + "_") or not filename.lower().endswith(".png"):
        raise RuntimeContractError("worker output does not match the owned run prefix")
    return _safe_remote_name(filename)


def _cleanup_owned_output(
    output_root: Path,
    locator: Mapping[str, Any],
    *,
    run_id: str,
    evidence_kind: str,
    output_hash: str,
) -> Mapping[str, Any]:
    relative_name = _owned_output_name(
        locator, run_id=run_id, evidence_kind=evidence_kind
    )
    path = _verified_runtime_file(
        output_root, relative_name, output_hash, "owned output"
    )
    _delete_verified_files([path], "owned output")
    return {"state": "deleted", "count": 1}


def execute_case(
    *,
    client: Any,
    context: Mapping[str, Any],
    reference_count: int,
    evidence_kind: str,
    execution_timeout_seconds: float = DEFAULT_EXECUTION_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    workflow_builder: Callable[..., Mapping[str, Any]] | None = None,
    object_info_validator: Callable[[object], Mapping[str, Any]] | None = None,
    workflow_validator: Callable[[object, object], Mapping[str, Any]] | None = None,
) -> Mapping[str, Any]:
    """Run exactly one submitted graph and persist immutable decoded evidence."""

    if reference_count not in BENCHMARK_REFERENCE_COUNTS:
        raise RuntimeContractError("reference count must be one of 1, 2, or 10")
    if evidence_kind not in {"probe", "benchmark"}:
        raise RuntimeContractError("evidence kind is invalid")
    if workflow_builder is None or object_info_validator is None or workflow_validator is None:
        preflight = _load_sibling(
            "windows_flux2_klein_bound_preflight_execute", "preflight.py"
        )
        workflow = _load_sibling(
            "windows_flux2_klein_bound_workflow_execute", "workflow.py"
        )
        workflow_builder = workflow.build_flux2_klein_workflow
        object_info_validator = preflight.validate_object_info
        workflow_validator = preflight.validate_workflow

    run_id = uuid.uuid4().hex
    case_root = (
        Path(context["state_root"])
        / "evidence"
        / evidence_kind
        / run_id
    )
    phase = "pre_upload"
    prompt_id: str | None = None
    uploaded: list[str] = []
    start = clock()
    case_base: dict[str, Any] = {
        "schema_version": 1,
        "capability": CAPABILITY,
        "kind": evidence_kind,
        "run_id": run_id,
        "created_at": _utc_now(),
        "runtime_contract_sha256": context["runtime_contract_sha256"],
        "package": context["binding"]["package"],
        "artifact_contract": context["binding"]["artifacts"],
        "fixture": context["binding"]["fixture"],
        "reference_count": reference_count,
        "prompt": FIXED_PROMPT,
        "seed": FIXED_SEED,
        "aspect_ratio": FIXED_ASPECT_RATIO,
        "worker_endpoint_sha256": getattr(client, "endpoint_sha256", None),
        "execution_proven": False,
    }
    try:
        pre_object_info = client.get_object_info()
        object_info_validator(pre_object_info)
        _assert_empty_queue(client.get_queue())
        samples = [_gpu_sample(client.get_system_stats(), clock() - start)]

        fixture = context["fixture"]
        for index in range(reference_count):
            requested_name = f"{run_id}-reference-{index + 1:02d}.png"
            remote = client.upload_image(
                fixture, requested_name
            )
            if remote in uploaded:
                raise RuntimeContractError("worker returned duplicate upload filenames")
            _verify_owned_input(
                Path(context["input_root"]),
                remote,
                run_id=run_id,
                index=index + 1,
                fixture_hash=str(context["binding"]["fixture"]["sha256"]),
            )
            uploaded.append(remote)
        phase = "uploaded"

        live_object_info = client.get_object_info()
        object_info_validator(live_object_info)
        graph = workflow_builder(
            prompt=FIXED_PROMPT,
            reference_images=uploaded,
            seed=FIXED_SEED,
            aspect_ratio=FIXED_ASPECT_RATIO,
            filename_prefix=f"flux2-klein-{evidence_kind}-{run_id[:12]}",
        )
        workflow_result = workflow_validator(graph, live_object_info)
        if workflow_result.get("reference_count") != reference_count:
            raise RuntimeContractError("live workflow reference count drifted")
        graph_sha256 = _contract_digest(graph)
        _assert_empty_queue(client.get_queue())

        phase = "submitting"
        prompt_id = client.submit_once(graph, run_id)
        phase = "submitted"
        while True:
            elapsed = clock() - start
            if elapsed > execution_timeout_seconds:
                raise RuntimeContractError("submitted execution timed out; status is UNKNOWN")
            history = client.get_history(prompt_id)
            samples.append(_gpu_sample(client.get_system_stats(), elapsed))
            record = _history_record(history, prompt_id)
            if record is not None:
                break
            sleeper(poll_interval_seconds)
        latency = clock() - start
        output_locator = _save_output_locator(record)
        _owned_output_name(
            output_locator, run_id=run_id, evidence_kind=evidence_kind
        )
        output_payload, content_type = client.download_output(output_locator)
        expected_dimensions = {"width": 1024, "height": 1024}
        decoded = _validate_decoded_image(
            output_payload, expected_dimensions, label="generated output"
        )
        output_path = case_root / "output.png"
        _write_bytes_new(output_path, output_payload)
        output_hash = _sha256_bytes(output_payload)
        phase = "cleanup"
        input_cleanup = _cleanup_owned_inputs(
            Path(context["input_root"]),
            uploaded,
            run_id=run_id,
            fixture_hash=str(context["binding"]["fixture"]["sha256"]),
        )
        output_cleanup = _cleanup_owned_output(
            Path(context["output_root"]),
            output_locator,
            run_id=run_id,
            evidence_kind=evidence_kind,
            output_hash=output_hash,
        )
        evidence = {
            **case_base,
            "status": "fixed_probe_passed" if evidence_kind == "probe" else "benchmark_case_passed",
            "execution_proven": True,
            "workflow_sha256": graph_sha256,
            "workflow_node_count": workflow_result.get("node_count"),
            "prompt_id_sha256": _sha256_bytes(prompt_id.encode("utf-8")),
            "latency_seconds": round(latency, 6),
            "gpu": _gpu_summary(samples),
            "gpu_samples": samples,
            "output": {
                "path": "output.png",
                "bytes": len(output_payload),
                "sha256": output_hash,
                "content_type": content_type,
                "decoded": decoded,
            },
            "cleanup": {
                "inputs": input_cleanup,
                "output": output_cleanup,
            },
        }
        _write_json_new(case_root / "evidence.json", evidence)
        return {**evidence, "evidence_path": str(case_root / "evidence.json")}
    except Exception as exc:
        if phase == "cleanup":
            status = "post_execution_cleanup_failed"
        elif isinstance(exc, SubmissionUnknownError) or phase in {"submitting", "submitted"}:
            status = "submission_unknown"
        else:
            status = "failed_pre_submission"
        cleanup_failure: str | None = None
        if status == "failed_pre_submission" and uploaded:
            try:
                _cleanup_owned_inputs(
                    Path(context["input_root"]),
                    uploaded,
                    run_id=run_id,
                    fixture_hash=str(context["binding"]["fixture"]["sha256"]),
                )
            except RuntimeContractError as cleanup_exc:
                cleanup_failure = type(cleanup_exc).__name__
        failure = {
            **case_base,
            "status": status,
            "phase": phase,
            "blocker_code": (
                "flux2_submission_or_execution_unknown"
                if status == "submission_unknown"
                else (
                    "flux2_runtime_cleanup_failed"
                    if status == "post_execution_cleanup_failed"
                    else "flux2_probe_precondition_failed"
                )
            ),
            "error_type": type(exc).__name__,
        }
        if status == "post_execution_cleanup_failed":
            failure.update(
                {
                    "execution_proven": True,
                    "automatic_retry_allowed": False,
                    "prompt_id_sha256": _sha256_bytes(prompt_id.encode("utf-8")),
                    "output": {
                        "path": "output.png",
                        "bytes": len(output_payload),
                        "sha256": output_hash,
                        "content_type": content_type,
                        "decoded": decoded,
                    },
                }
            )
        if cleanup_failure is not None:
            failure["cleanup_error_type"] = cleanup_failure
        _write_json_new(case_root / "evidence.json", failure)
        if isinstance(exc, RuntimeContractError):
            raise
        raise RuntimeContractError("candidate execution failed closed") from exc


def run_probe(
    *,
    client: Any,
    context: Mapping[str, Any],
    **case_options: Any,
) -> Mapping[str, Any]:
    return execute_case(
        client=client,
        context=context,
        reference_count=1,
        evidence_kind="probe",
        **case_options,
    )


def publish_probe_status(
    *, context: Mapping[str, Any], probe_result: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Atomically promote installed evidence to needs_benchmark."""

    state_root = Path(context["state_root"])
    current = load_runtime_status(
        state_root, package_root=Path(context["package_root"])
    )
    if current.get("state") != "not_installed":
        raise RuntimeContractError("fixed probe can only promote the installed pre-probe state")
    if (
        probe_result.get("status") != "fixed_probe_passed"
        or probe_result.get("runtime_contract_sha256")
        != context["runtime_contract_sha256"]
    ):
        raise RuntimeContractError("fixed probe result cannot promote status")
    probe_path = Path(str(probe_result.get("evidence_path")))
    evidence = dict(current["evidence"])
    evidence["canary"] = _status_evidence_record(
        state_root, probe_path, probe_result, include_output=True
    )
    promoted = {
        **current,
        "state": "needs_benchmark",
        "startup_ready": False,
        "execution_proven": True,
        "benchmark_state": "not_run",
        "blocker_code": "candidate_benchmark_not_run",
        "runtime_contract_sha256": context["runtime_contract_sha256"],
        "updated_at": _utc_now(),
        "evidence": evidence,
    }
    _write_json_atomic(state_root / "status.json", promoted)
    return load_runtime_status(
        state_root, package_root=Path(context["package_root"])
    )


def _validate_probe_evidence(path: Path, context: Mapping[str, Any]) -> Mapping[str, Any]:
    probe = _load_json(path, "fixed probe evidence")
    if (
        probe.get("capability") != CAPABILITY
        or probe.get("kind") != "probe"
        or probe.get("status") != "fixed_probe_passed"
        or probe.get("execution_proven") is not True
        or probe.get("reference_count") != 1
        or probe.get("runtime_contract_sha256") != context["runtime_contract_sha256"]
        or probe.get("fixture") != context["binding"]["fixture"]
    ):
        raise RuntimeContractError("fixed probe evidence is missing, failed, or stale")
    output = probe.get("output")
    if not isinstance(output, Mapping) or not isinstance(output.get("sha256"), str):
        raise RuntimeContractError("fixed probe decoded-output evidence is invalid")
    return probe


def run_benchmark(
    *,
    client: Any,
    context: Mapping[str, Any],
    probe_evidence_path: Path,
    case_runner: Callable[..., Mapping[str, Any]] = execute_case,
    **case_options: Any,
) -> Mapping[str, Any]:
    """Run 1, 2, then 10 references serially and bind all case evidence."""

    probe = _validate_probe_evidence(probe_evidence_path, context)
    benchmark_id = uuid.uuid4().hex
    benchmark_root = Path(context["state_root"]) / "evidence" / "benchmark-runs" / benchmark_id
    started_at = _utc_now()
    completed: list[Mapping[str, Any]] = []
    try:
        for reference_count in BENCHMARK_REFERENCE_COUNTS:
            case = case_runner(
                client=client,
                context=context,
                reference_count=reference_count,
                evidence_kind="benchmark",
                **case_options,
            )
            if case.get("status") != "benchmark_case_passed":
                raise RuntimeContractError("benchmark case did not pass")
            completed.append(case)
    except Exception as exc:
        failed = {
            "schema_version": 1,
            "capability": CAPABILITY,
            "kind": "benchmark_summary",
            "benchmark_id": benchmark_id,
            "created_at": started_at,
            "status": "benchmark_failed",
            "benchmark_state": "failed",
            "execution_proven": True,
            "runtime_contract_sha256": context["runtime_contract_sha256"],
            "sequence": list(BENCHMARK_REFERENCE_COUNTS),
            "completed_reference_counts": [case["reference_count"] for case in completed],
            "blocker_code": "flux2_local_capacity_benchmark_failed",
            "error_type": type(exc).__name__,
        }
        _write_json_new(benchmark_root / "evidence.json", failed)
        if isinstance(exc, RuntimeContractError):
            raise
        raise RuntimeContractError("capacity benchmark failed closed") from exc

    summaries = [
        {
            "reference_count": case["reference_count"],
            "latency_seconds": case["latency_seconds"],
            "workflow_sha256": case["workflow_sha256"],
            "output_sha256": case["output"]["sha256"],
            "peak_vram_used_bytes": case["gpu"]["peak_vram_used_bytes"],
            "minimum_vram_free_bytes": case["gpu"]["minimum_vram_free_bytes"],
            "evidence_sha256": _sha256_file(Path(case["evidence_path"])),
        }
        for case in completed
    ]
    evidence = {
        "schema_version": 1,
        "capability": CAPABILITY,
        "kind": "benchmark_summary",
        "benchmark_id": benchmark_id,
        "created_at": started_at,
        "completed_at": _utc_now(),
        "status": "benchmark_passed",
        "benchmark_state": "passed",
        "execution_proven": True,
        "startup_ready": False,
        "runtime_contract_sha256": context["runtime_contract_sha256"],
        "probe_evidence_sha256": _sha256_file(probe_evidence_path),
        "probe_output_sha256": probe["output"]["sha256"],
        "sequence": list(BENCHMARK_REFERENCE_COUNTS),
        "sequential_no_overlap": True,
        "pass_contract": (
            "Each 1/2/10-reference graph was submitted exactly once after an empty "
            "queue check, completed successfully, decoded to the fixed dimensions, "
            "and produced consistent bounded GPU telemetry. Latency has no hidden SLA."
        ),
        "cases": summaries,
    }
    _write_json_new(benchmark_root / "evidence.json", evidence)
    return {**evidence, "evidence_path": str(benchmark_root / "evidence.json")}


def validate_benchmark_status_prerequisite(
    *, context: Mapping[str, Any], probe_evidence_path: Path
) -> Mapping[str, Any]:
    state_root = Path(context["state_root"])
    current = load_runtime_status(
        state_root, package_root=Path(context["package_root"])
    )
    canary = current.get("evidence", {}).get("canary")
    if (
        current.get("state") != "needs_benchmark"
        or current.get("runtime_contract_sha256")
        != context["runtime_contract_sha256"]
        or not isinstance(canary, Mapping)
        or _sha256_file(probe_evidence_path) != canary.get("sha256")
    ):
        raise RuntimeContractError("atomic status does not authorize this benchmark")
    return current


def publish_benchmark_status(
    *,
    context: Mapping[str, Any],
    probe_evidence_path: Path,
    benchmark_result: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Atomically publish ready only from exact canary+1/2/10 evidence."""

    current = validate_benchmark_status_prerequisite(
        context=context, probe_evidence_path=probe_evidence_path
    )
    if (
        benchmark_result.get("status") != "benchmark_passed"
        or benchmark_result.get("benchmark_state") != "passed"
        or benchmark_result.get("runtime_contract_sha256")
        != context["runtime_contract_sha256"]
        or benchmark_result.get("sequence") != [1, 2, 10]
    ):
        raise RuntimeContractError("benchmark result cannot promote status")
    state_root = Path(context["state_root"])
    benchmark_path = Path(str(benchmark_result.get("evidence_path")))
    evidence = dict(current["evidence"])
    evidence["benchmark"] = _status_evidence_record(
        state_root, benchmark_path, benchmark_result
    )
    promoted = {
        **current,
        "state": "ready",
        "startup_ready": True,
        "execution_proven": True,
        "benchmark_state": "passed",
        "blocker_code": None,
        "updated_at": _utc_now(),
        "evidence": evidence,
    }
    _write_json_atomic(state_root / "status.json", promoted)
    return load_runtime_status(
        state_root, package_root=Path(context["package_root"])
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("probe", "benchmark"))
    parser.add_argument("--comfy-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8188")
    parser.add_argument("--token-env", default="CONTENT_COMFY_TOKEN")
    parser.add_argument("--probe-evidence", type=Path)
    parser.add_argument(
        "--execution-timeout-seconds",
        type=float,
        default=DEFAULT_EXECUTION_TIMEOUT_SECONDS,
    )
    return parser


if __name__ == "__main__":
    arguments = _parser().parse_args()
    token = os.environ.get(arguments.token_env) or None
    runtime_context = prepare_runtime_context(
        comfy_root=arguments.comfy_root,
        state_root=arguments.state_root,
        input_root=arguments.input_root,
        output_root=arguments.output_root,
    )
    runtime_client = ComfyClient(arguments.endpoint, token=token)
    options = {"execution_timeout_seconds": arguments.execution_timeout_seconds}
    if arguments.mode == "probe":
        current_status = load_runtime_status(
            Path(runtime_context["state_root"]),
            package_root=Path(runtime_context["package_root"]),
        )
        if current_status.get("state") != "not_installed":
            raise SystemExit("atomic status does not authorize another fixed probe")
        result = run_probe(client=runtime_client, context=runtime_context, **options)
        published_status = publish_probe_status(
            context=runtime_context, probe_result=result
        )
    else:
        if arguments.probe_evidence is None:
            raise SystemExit("--probe-evidence is required for benchmark mode")
        validate_benchmark_status_prerequisite(
            context=runtime_context,
            probe_evidence_path=arguments.probe_evidence,
        )
        result = run_benchmark(
            client=runtime_client,
            context=runtime_context,
            probe_evidence_path=arguments.probe_evidence,
            **options,
        )
        published_status = publish_benchmark_status(
            context=runtime_context,
            probe_evidence_path=arguments.probe_evidence,
            benchmark_result=result,
        )
    print(
        json.dumps(
            {
                "result": result,
                "runtime_status": {
                    key: published_status.get(key)
                    for key in (
                        "capability",
                        "state",
                        "startup_ready",
                        "execution_proven",
                        "benchmark_state",
                        "blocker_code",
                    )
                },
            },
            sort_keys=True,
        )
    )
