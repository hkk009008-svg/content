#!/usr/bin/env python3
"""Fail-closed installer for the pinned FLUX.2 Klein Windows candidate.

The installer is intentionally separate from candidate readiness.  It verifies
the static package, downloads only commit-pinned official artifacts, performs
the deterministic Qwen shard merge, and publishes exact model bytes without
overwriting an existing model.  Successful installation still requires the
fixed execution probe and capacity benchmark before the capability can be
advertised as ready.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO


ROOT = Path(__file__).resolve().parent
CHUNK_SIZE = 8 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 120
ALLOWED_MODEL_DIRECTORIES = frozenset(
    {"diffusion_models", "text_encoders", "vae"}
)


class InstallContractError(RuntimeError):
    """Installation was refused because an exact safety contract failed."""


def _load_sibling(name: str, filename: str):
    path = ROOT / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise InstallContractError(f"cannot load bound package tool {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallContractError(f"cannot read JSON contract {path.name}") from exc
    if not isinstance(value, Mapping):
        raise InstallContractError(f"JSON contract {path.name} is not an object")
    return value


def _sha256_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
                size += len(chunk)
                digest.update(chunk)
    except OSError as exc:
        raise InstallContractError(f"cannot hash {path}") from exc
    return digest.hexdigest(), size


def _expected(record: Mapping[str, Any]) -> tuple[int, str]:
    expected_bytes = record.get("expected_bytes")
    expected_hash = record.get("sha256")
    if (
        isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or expected_bytes <= 0
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
        or any(character not in "0123456789abcdef" for character in expected_hash)
    ):
        raise InstallContractError("artifact byte/hash gate is invalid")
    return expected_bytes, expected_hash


def _verify_file(path: Path, record: Mapping[str, Any], label: str) -> None:
    expected_bytes, expected_hash = _expected(record)
    if not path.is_file() or path.is_symlink():
        raise InstallContractError(f"{label} is missing or is not a regular file")
    actual_hash, actual_bytes = _sha256_size(path)
    if actual_bytes != expected_bytes or actual_hash != expected_hash:
        raise InstallContractError(f"{label} failed exact byte/SHA-256 verification")


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse)


def _require_real_existing_tree(path: Path, label: str) -> Path:
    if not path.exists() or not path.is_dir() or _is_link_or_reparse(path):
        raise InstallContractError(f"{label} must be an existing real directory")
    resolved = path.resolve()
    current = path
    while True:
        if _is_link_or_reparse(current):
            raise InstallContractError(f"{label} may not traverse a link or junction")
        if current.parent == current:
            break
        current = current.parent
    return resolved


def validate_comfy_root(comfy_root: Path) -> tuple[Path, Path]:
    """Resolve an existing ComfyUI checkout and its real model directory."""

    root = _require_real_existing_tree(comfy_root, "ComfyUI root")
    main = root / "main.py"
    if not main.is_file() or _is_link_or_reparse(main):
        raise InstallContractError("ComfyUI root is missing a real main.py")
    model_root = _require_real_existing_tree(root / "models", "ComfyUI models root")
    if root not in model_root.parents:
        raise InstallContractError("ComfyUI models root escapes the checkout")
    return root, model_root


def _safe_destination(model_root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative:
        raise InstallContractError("model destination is missing")
    parsed = PurePosixPath(relative)
    if (
        parsed.is_absolute()
        or ".." in parsed.parts
        or len(parsed.parts) != 2
        or parsed.parts[0] not in ALLOWED_MODEL_DIRECTORIES
        or any("\x00" in part or "\\" in part for part in parsed.parts)
    ):
        raise InstallContractError("model destination is outside approved directories")
    destination = model_root.joinpath(*parsed.parts)
    resolved_parent = destination.parent.resolve(strict=False)
    if model_root != resolved_parent and model_root not in resolved_parent.parents:
        raise InstallContractError("model destination escapes the models root")
    if destination.parent.exists() and _is_link_or_reparse(destination.parent):
        raise InstallContractError("model destination directory may not be a link")
    return destination


class ExclusiveInstallLock(AbstractContextManager["ExclusiveInstallLock"]):
    def __init__(self, state_root: Path):
        self.path = state_root / "install.lock"
        self.fd: int | None = None

    def __enter__(self) -> "ExclusiveInstallLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(
                self.fd,
                json.dumps({"pid": os.getpid(), "created_at": _utc_now()}).encode(
                    "utf-8"
                ),
            )
            os.fsync(self.fd)
        except FileExistsError as exc:
            raise InstallContractError(
                f"another install may be active; inspect and remove stale lock: {self.path}"
            ) from exc
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.path.unlink(missing_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_download_url(url: object) -> str:
    if not isinstance(url, str):
        raise InstallContractError("download URL is missing")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "huggingface.co":
        raise InstallContractError("only pinned HTTPS huggingface.co sources are allowed")
    if not parsed.path.startswith("/black-forest-labs/") or "/resolve/" not in parsed.path:
        raise InstallContractError("download URL is not a pinned BFL resolve path")
    return url


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if status is None and hasattr(response, "getcode"):
        status = response.getcode()
    return int(status or 200)


def download_verified(
    record: Mapping[str, Any],
    destination: Path,
    *,
    opener: Callable[..., BinaryIO] = urllib.request.urlopen,
    timeout: int = DOWNLOAD_TIMEOUT_SECONDS,
) -> Mapping[str, Any]:
    """Download/resume one exact source into an owned cache path."""

    expected_bytes, expected_hash = _expected(record)
    url = _validate_download_url(record.get("url"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        _verify_file(destination, record, "cached source")
        return {"status": "cache_reused", "bytes": expected_bytes, "sha256": expected_hash}
    partial = destination.with_name(destination.name + ".partial")
    offset = partial.stat().st_size if partial.exists() else 0
    if partial.exists() and (partial.is_symlink() or not partial.is_file()):
        raise InstallContractError("download partial is not an owned regular file")
    if offset > expected_bytes:
        partial.unlink()
        offset = 0

    headers = {"Accept-Encoding": "identity", "User-Agent": "Content-FLUX2-Klein/1"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        response = opener(request, timeout=timeout)
        status = _response_status(response)
        if offset and status == 206:
            content_range = response.headers.get("Content-Range", "")
            if not content_range.startswith(f"bytes {offset}-"):
                raise InstallContractError("resumed download Content-Range is invalid")
            mode = "ab"
        elif status == 200:
            offset = 0
            mode = "wb"
        else:
            raise InstallContractError(f"download returned unexpected HTTP status {status}")
        written = offset
        with response, partial.open(mode) as handle:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > expected_bytes:
                    raise InstallContractError("download exceeded the pinned byte count")
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    except InstallContractError:
        if partial.exists() and partial.stat().st_size > expected_bytes:
            partial.unlink()
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise InstallContractError("verified source download failed; partial retained") from exc

    _verify_file(partial, record, "downloaded source")
    try:
        os.link(partial, destination)
    except FileExistsError as exc:
        raise InstallContractError("download cache destination appeared concurrently") from exc
    except OSError as exc:
        raise InstallContractError("filesystem cannot atomically publish verified cache") from exc
    partial.unlink()
    return {"status": "downloaded", "bytes": expected_bytes, "sha256": expected_hash}


def _source_records(artifact: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    source = artifact.get("source")
    if not isinstance(source, Mapping):
        raise InstallContractError("artifact source contract is missing")
    if source.get("type") == "deterministic_official_shard_merge":
        index = source.get("index")
        inputs = source.get("inputs")
        if not isinstance(index, Mapping) or not isinstance(inputs, list) or not inputs:
            raise InstallContractError("Qwen source records are invalid")
        if not all(isinstance(item, Mapping) for item in inputs):
            raise InstallContractError("Qwen source input record is invalid")
        return [index, *inputs]
    return [
        {
            **source,
            "expected_bytes": artifact.get("expected_bytes"),
            "sha256": artifact.get("sha256"),
        }
    ]


def _safe_cache_source(source_root: Path, record: Mapping[str, Any]) -> Path:
    relative = record.get("path")
    if not isinstance(relative, str):
        raise InstallContractError("source path is missing")
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or ".." in parsed.parts or any("\\" in part for part in parsed.parts):
        raise InstallContractError("source path escapes the official cache")
    destination = source_root.joinpath(*parsed.parts)
    if source_root != destination.parent.resolve(strict=False) and source_root not in destination.parent.resolve(strict=False).parents:
        raise InstallContractError("source cache path escapes its root")
    return destination


def prepare_verified_sources(
    manifest: Mapping[str, Any],
    cache_root: Path,
    *,
    downloader: Callable[[Mapping[str, Any], Path], Mapping[str, Any]] = download_verified,
    merge_tool: Callable[[Path, Path, Path], Mapping[str, Any]] | None = None,
    manifest_path: Path = ROOT / "models.json",
) -> tuple[dict[str, Path], list[Mapping[str, Any]], Mapping[str, Any]]:
    """Fetch exact direct sources and derive the exact Qwen output."""

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise InstallContractError("expected exactly three candidate artifacts")
    source_root = (cache_root / "official").resolve()
    source_root.mkdir(parents=True, exist_ok=True)
    results: dict[str, Path] = {}
    transfers: list[Mapping[str, Any]] = []
    merge_evidence: Mapping[str, Any] = {"status": "not_required"}

    for artifact in artifacts:
        if not isinstance(artifact, Mapping) or not isinstance(artifact.get("id"), str):
            raise InstallContractError("artifact manifest record is invalid")
        artifact_id = artifact["id"]
        source = artifact.get("source")
        if not isinstance(source, Mapping):
            raise InstallContractError("artifact source record is invalid")
        records = _source_records(artifact)
        for record in records:
            cache_path = _safe_cache_source(source_root, record)
            result = downloader(record, cache_path)
            transfers.append(
                {
                    "artifact_id": artifact_id,
                    "source_path": record.get("path"),
                    "status": result.get("status"),
                    "bytes": record.get("expected_bytes"),
                    "sha256": record.get("sha256"),
                }
            )
        if source.get("type") == "deterministic_official_shard_merge":
            derived = cache_root / "derived" / Path(str(artifact.get("destination"))).name
            if derived.exists():
                _verify_file(derived, artifact, "cached derived Qwen encoder")
                merge_evidence = {
                    "status": "verified_derivation_cache_reused",
                    "output_bytes": artifact.get("expected_bytes"),
                    "output_sha256": artifact.get("sha256"),
                    "tensor_count": source.get("derivation", {}).get("expected_tensor_count"),
                }
            else:
                if merge_tool is None:
                    merge_module = _load_sibling(
                        "windows_flux2_klein_bound_merge", "merge_qwen_encoder.py"
                    )
                    merge_tool = merge_module.merge_from_manifest
                derived.parent.mkdir(parents=True, exist_ok=True)
                merge_evidence = merge_tool(manifest_path, source_root, derived)
                _verify_file(derived, artifact, "derived Qwen encoder")
            results[artifact_id] = derived
        else:
            results[artifact_id] = _safe_cache_source(source_root, records[0])
            _verify_file(results[artifact_id], artifact, f"source for {artifact_id}")
    return results, transfers, merge_evidence


def _inspect_destinations(
    model_root: Path, artifacts: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Path], set[str]]:
    destinations: dict[str, Path] = {}
    reusable: set[str] = set()
    for artifact in artifacts:
        artifact_id = artifact.get("id")
        if not isinstance(artifact_id, str) or artifact_id in destinations:
            raise InstallContractError("artifact identifiers are invalid or duplicated")
        destination = _safe_destination(model_root, artifact.get("destination"))
        destinations[artifact_id] = destination
        if destination.exists():
            _verify_file(destination, artifact, f"existing model {artifact_id}")
            reusable.add(artifact_id)
    return destinations, reusable


def _publish_verified(source: Path, destination: Path, record: Mapping[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _is_link_or_reparse(destination.parent):
        raise InstallContractError("model destination directory became a link")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".partial",
            dir=destination.parent,
            delete=False,
        ) as target, source.open("rb") as origin:
            temporary_name = target.name
            shutil.copyfileobj(origin, target, CHUNK_SIZE)
            target.flush()
            os.fsync(target.fileno())
        temporary = Path(temporary_name)
        _verify_file(temporary, record, "staged model")
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise InstallContractError("refusing to overwrite a model that appeared concurrently") from exc
        except OSError as exc:
            raise InstallContractError("filesystem cannot atomically publish a verified model") from exc
        temporary.unlink()
        temporary_name = None
        _verify_file(destination, record, "published model")
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _unlink_owned_exact(path: Path, record: Mapping[str, Any]) -> None:
    try:
        _verify_file(path, record, "rollback model")
    except InstallContractError:
        return
    path.unlink(missing_ok=True)


def _package_binding(package_root: Path) -> Mapping[str, Any]:
    candidate = _load_json(package_root / "candidate.json")
    bindings = candidate.get("bindings")
    if not isinstance(bindings, Mapping):
        raise InstallContractError("candidate package bindings are missing")
    return {
        "candidate_sha256": _sha256_size(package_root / "candidate.json")[0],
        "bound_files": dict(sorted(bindings.items())),
    }


def _write_json_new(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise InstallContractError(f"refusing to overwrite evidence {path}") from exc


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install_candidate(
    *,
    comfy_root: Path,
    state_root: Path,
    package_root: Path = ROOT,
    downloader: Callable[[Mapping[str, Any], Path], Mapping[str, Any]] = download_verified,
    merge_tool: Callable[[Path, Path, Path], Mapping[str, Any]] | None = None,
    package_validator: Callable[[Path], Mapping[str, Any]] | None = None,
) -> Mapping[str, Any]:
    """Install the exact candidate and write non-promoting durable evidence."""

    if package_validator is None:
        preflight_module = _load_sibling(
            "windows_flux2_klein_bound_preflight_install", "preflight.py"
        )
        package_validator = preflight_module.validate_package
    package_result = package_validator(package_root)
    if package_result.get("status") != "candidate_contract_valid":
        raise InstallContractError("static candidate package did not validate")
    root, model_root = validate_comfy_root(comfy_root)
    manifest_path = package_root / "models.json"
    manifest = _load_json(manifest_path)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise InstallContractError("model manifest artifacts are invalid")

    state_root = state_root.resolve()
    if state_root == root or root in state_root.parents:
        raise InstallContractError("installer state/cache must remain outside ComfyUI")
    state_root.mkdir(parents=True, exist_ok=True)
    _require_real_existing_tree(state_root, "installer state root")

    # Inspect every final target before the first possible network operation.
    _inspect_destinations(model_root, artifacts)
    with ExclusiveInstallLock(state_root):
        destinations, reusable = _inspect_destinations(model_root, artifacts)
        sources, transfers, merge_evidence = prepare_verified_sources(
            manifest,
            state_root / "cache",
            downloader=downloader,
            merge_tool=merge_tool,
            manifest_path=manifest_path,
        )
        installed_now: list[tuple[Path, Mapping[str, Any]]] = []
        try:
            for artifact in artifacts:
                artifact_id = artifact["id"]
                if artifact_id in reusable:
                    continue
                _publish_verified(sources[artifact_id], destinations[artifact_id], artifact)
                installed_now.append((destinations[artifact_id], artifact))
            # Re-audit all destinations after the complete publish set.
            for artifact in artifacts:
                _verify_file(
                    destinations[artifact["id"]], artifact, f"installed model {artifact['id']}"
                )

        except Exception:
            for path, artifact in reversed(installed_now):
                _unlink_owned_exact(path, artifact)
            raise

        # Evidence failure does not remove already verified models. A rerun can
        # safely reuse them and repair status without redownloading paid bytes.
        run_id = f"{int(time.time())}-{uuid.uuid4().hex}"
        evidence: Mapping[str, Any] = {
            "schema_version": 1,
            "capability": "image-flux2-klein",
            "run_id": run_id,
            "created_at": _utc_now(),
            "status": "installed_needs_execution_probe",
            "startup_ready": False,
            "execution_proven": False,
            "benchmark_state": "not_run",
            "license_review": {
                "state": "official_source_derivation_verified",
                "qwen_output_sha256": merge_evidence.get("output_sha256"),
            },
            "package": _package_binding(package_root),
            "artifacts": [
                {
                    "id": artifact["id"],
                    "destination": artifact["destination"],
                    "expected_bytes": artifact["expected_bytes"],
                    "sha256": artifact["sha256"],
                    "install_action": (
                        "verified_existing" if artifact["id"] in reusable else "installed"
                    ),
                }
                for artifact in artifacts
            ],
            "source_transfers": transfers,
            "qwen_derivation": dict(merge_evidence),
        }
        history_path = state_root / "evidence" / "install" / run_id / "evidence.json"
        _write_json_new(history_path, evidence)
        history_relative = str(history_path.relative_to(state_root)).replace("\\", "/")
        latest = dict(evidence)
        latest["history_evidence"] = history_relative
        _write_json_atomic(state_root / "install.json", latest)
        status = {
            "schema_version": 1,
            "capability": "image-flux2-klein",
            "state": "not_installed",
            "startup_ready": False,
            "execution_proven": False,
            "benchmark_state": "not_run",
            "blocker_code": "candidate_execution_probe_not_run",
            "artifacts_installed": True,
            "license_review_state": "official_source_derivation_verified",
            "runtime_contract_sha256": None,
            "artifact_manifest_sha256": _sha256_size(manifest_path)[0],
            "workflow_contract_sha256": _sha256_size(package_root / "workflow.py")[0],
            "updated_at": _utc_now(),
            "evidence": {
                "install": {
                    "path": history_relative,
                    "sha256": _sha256_size(history_path)[0],
                    "run_id": run_id,
                    "status": "installed_needs_execution_probe",
                },
                "canary": None,
                "benchmark": None,
            },
        }
        _write_json_atomic(state_root / "status.json", status)
    return latest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    return parser


if __name__ == "__main__":
    arguments = _parser().parse_args()
    print(
        json.dumps(
            install_candidate(
                comfy_root=arguments.comfy_root,
                state_root=arguments.state_root,
            ),
            sort_keys=True,
        )
    )
