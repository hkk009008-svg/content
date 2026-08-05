#!/usr/bin/env python3
"""Validate, fetch, and verify the production ComfyUI model manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
import time
from typing import Any, Iterable
from urllib.request import Request, urlopen
import zipfile


CHUNK_BYTES = 8 * 1024 * 1024
MIN_FREE_HEADROOM = 1024 * 1024 * 1024
REQUIRED_LICENSE_FIELDS = {
    "declared_by_distributor",
    "upstream_terms",
    "review_note",
}


class ManifestError(ValueError):
    """The model manifest does not satisfy the fail-closed contract."""


class ArtifactError(RuntimeError):
    """A required artifact is absent, corrupt, or could not be fetched."""


def _non_placeholder(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if normalized.lower() in {"todo", "tbd", "unknown", "replace-me", "placeholder"}:
        raise ManifestError(f"{field} contains a placeholder value")
    return normalized


def safe_relative_path(value: Any, *, field: str) -> PurePosixPath:
    raw = _non_placeholder(value, field=field)
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ManifestError(f"{field} must be a traversal-free relative path")
    if any(part in {"", "."} for part in candidate.parts):
        raise ManifestError(f"{field} contains an invalid path component")
    return candidate


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read model manifest {path}: {exc}") from exc
    validate_manifest(payload)
    return payload


def validate_manifest(payload: Any) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ManifestError("model manifest schema_version must be 1")
    _non_placeholder(payload.get("resolved_at"), field="resolved_at")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ManifestError("artifacts must be a non-empty list")

    seen_ids: set[str] = set()
    seen_destinations: set[str] = set()
    for index, artifact in enumerate(artifacts):
        prefix = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            raise ManifestError(f"{prefix} must be an object")
        artifact_id = _non_placeholder(artifact.get("id"), field=f"{prefix}.id")
        if artifact_id in seen_ids:
            raise ManifestError(f"duplicate artifact id: {artifact_id}")
        seen_ids.add(artifact_id)
        if artifact.get("required") is not True:
            raise ManifestError(f"{prefix}.required must be true for this production image")
        if artifact.get("kind") not in {"file", "zip"}:
            raise ManifestError(f"{prefix}.kind must be 'file' or 'zip'")

        source = artifact.get("source")
        if not isinstance(source, dict):
            raise ManifestError(f"{prefix}.source must be an object")
        _non_placeholder(source.get("repository"), field=f"{prefix}.source.repository")
        _non_placeholder(source.get("revision"), field=f"{prefix}.source.revision")
        url = _non_placeholder(source.get("url"), field=f"{prefix}.source.url")
        if not url.startswith("https://"):
            raise ManifestError(f"{prefix}.source.url must use HTTPS")

        license_data = artifact.get("license")
        if not isinstance(license_data, dict):
            raise ManifestError(f"{prefix}.license must be an object")
        missing_license = REQUIRED_LICENSE_FIELDS.difference(license_data)
        if missing_license:
            raise ManifestError(
                f"{prefix}.license missing fields: {', '.join(sorted(missing_license))}"
            )
        for field in REQUIRED_LICENSE_FIELDS:
            _non_placeholder(license_data[field], field=f"{prefix}.license.{field}")

        expected_bytes = artifact.get("expected_bytes")
        if not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool) or expected_bytes <= 0:
            raise ManifestError(f"{prefix}.expected_bytes must be a positive integer")
        digest = _non_placeholder(artifact.get("sha256"), field=f"{prefix}.sha256")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ManifestError(f"{prefix}.sha256 must be 64 lowercase hex characters")

        destination = safe_relative_path(artifact.get("destination"), field=f"{prefix}.destination")
        destination_string = destination.as_posix()
        if destination_string in seen_destinations:
            raise ManifestError(f"duplicate artifact destination: {destination_string}")
        seen_destinations.add(destination_string)

        if artifact["kind"] == "zip":
            safe_relative_path(artifact.get("extract_to"), field=f"{prefix}.extract_to")
            members = artifact.get("required_members")
            if not isinstance(members, list) or not members:
                raise ManifestError(f"{prefix}.required_members must be a non-empty list")
            seen_members: set[str] = set()
            for member_index, member in enumerate(members):
                member_path = safe_relative_path(
                    member, field=f"{prefix}.required_members[{member_index}]"
                )
                if len(member_path.parts) != 1:
                    raise ManifestError(
                        f"{prefix}.required_members entries must be basenames"
                    )
                if member_path.name in seen_members:
                    raise ManifestError(f"{prefix}.required_members contains duplicates")
                seen_members.add(member_path.name)

        cache_data = artifact.get("huggingface_cache")
        if cache_data is not None:
            if artifact["kind"] != "file" or not isinstance(cache_data, dict):
                raise ManifestError(f"{prefix}.huggingface_cache must describe a file")
            repo_id = _non_placeholder(
                cache_data.get("repo_id"), field=f"{prefix}.huggingface_cache.repo_id"
            )
            if repo_id.count("/") != 1:
                raise ManifestError(f"{prefix}.huggingface_cache.repo_id must be owner/name")
            revision = _non_placeholder(
                cache_data.get("revision"), field=f"{prefix}.huggingface_cache.revision"
            )
            if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
                raise ManifestError(
                    f"{prefix}.huggingface_cache.revision must be a full commit SHA"
                )
            filename = safe_relative_path(
                cache_data.get("filename"), field=f"{prefix}.huggingface_cache.filename"
            )
            if len(filename.parts) != 1:
                raise ManifestError(f"{prefix}.huggingface_cache.filename must be a basename")


def hash_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def artifact_path(model_root: Path, artifact: dict[str, Any]) -> Path:
    relative = safe_relative_path(artifact["destination"], field="artifact.destination")
    return model_root.joinpath(*relative.parts)


def _verify_file(path: Path, artifact: dict[str, Any]) -> None:
    if path.is_symlink() or not path.is_file():
        raise ArtifactError(f"{artifact['id']}: required regular file missing: {path}")
    digest, size = hash_and_size(path)
    if size != artifact["expected_bytes"]:
        raise ArtifactError(
            f"{artifact['id']}: byte count {size} != {artifact['expected_bytes']}: {path}"
        )
    if digest != artifact["sha256"]:
        raise ArtifactError(
            f"{artifact['id']}: sha256 {digest} != {artifact['sha256']}: {path}"
        )


def _zip_member_map(archive: zipfile.ZipFile, required: Iterable[str]) -> dict[str, zipfile.ZipInfo]:
    wanted = set(required)
    found: dict[str, zipfile.ZipInfo] = {}
    for info in archive.infolist():
        pure = PurePosixPath(info.filename)
        if pure.is_absolute() or ".." in pure.parts:
            raise ArtifactError(f"unsafe path in verified zip: {info.filename}")
        if info.is_dir() or pure.name not in wanted:
            continue
        if pure.name in found:
            raise ArtifactError(f"duplicate required basename in zip: {pure.name}")
        found[pure.name] = info
    missing = wanted.difference(found)
    if missing:
        raise ArtifactError(f"required zip members missing: {', '.join(sorted(missing))}")
    return found


def _stream_digest(handle: Any) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := handle.read(CHUNK_BYTES):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _verify_zip_outputs(model_root: Path, artifact: dict[str, Any], archive_path: Path) -> None:
    extract_relative = safe_relative_path(artifact["extract_to"], field="artifact.extract_to")
    extract_root = model_root.joinpath(*extract_relative.parts)
    with zipfile.ZipFile(archive_path) as archive:
        mapping = _zip_member_map(archive, artifact["required_members"])
        for basename, info in mapping.items():
            output = extract_root / basename
            if output.is_symlink() or not output.is_file():
                raise ArtifactError(f"{artifact['id']}: extracted model missing: {output}")
            with archive.open(info) as source:
                expected_digest, expected_size = _stream_digest(source)
            actual_digest, actual_size = hash_and_size(output)
            if (actual_digest, actual_size) != (expected_digest, expected_size):
                raise ArtifactError(
                    f"{artifact['id']}: extracted model differs from verified archive: {output}"
                )


def _huggingface_cache_paths(
    model_root: Path, artifact: dict[str, Any]
) -> tuple[Path, Path, str]:
    cache_data = artifact["huggingface_cache"]
    repo_directory = "models--" + cache_data["repo_id"].replace("/", "--")
    cache_root = model_root / ".huggingface" / "hub" / repo_directory
    snapshot = cache_root / "snapshots" / cache_data["revision"] / cache_data["filename"]
    reference = cache_root / "refs" / "main"
    return snapshot, reference, cache_data["revision"]


def _ensure_huggingface_cache(model_root: Path, artifact: dict[str, Any]) -> None:
    if "huggingface_cache" not in artifact:
        return
    blob = artifact_path(model_root, artifact)
    snapshot, reference, revision = _huggingface_cache_paths(model_root, artifact)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    reference.parent.mkdir(parents=True, exist_ok=True)

    relative_target = os.path.relpath(blob, snapshot.parent)
    if snapshot.is_symlink():
        if os.readlink(snapshot) != relative_target:
            raise ArtifactError(f"{artifact['id']}: unexpected Hugging Face cache symlink")
    elif snapshot.exists():
        raise ArtifactError(f"{artifact['id']}: cache snapshot path is not a symlink")
    else:
        snapshot.symlink_to(relative_target)

    if reference.exists() or reference.is_symlink():
        if reference.is_symlink() or reference.read_text(encoding="utf-8").strip() != revision:
            raise ArtifactError(f"{artifact['id']}: unexpected Hugging Face main reference")
    else:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".main-", suffix=".partial",
            dir=reference.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(revision + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, reference)


def _verify_huggingface_cache(model_root: Path, artifact: dict[str, Any]) -> None:
    if "huggingface_cache" not in artifact:
        return
    blob = artifact_path(model_root, artifact)
    snapshot, reference, revision = _huggingface_cache_paths(model_root, artifact)
    if not snapshot.is_symlink() or snapshot.resolve(strict=True) != blob.resolve(strict=True):
        raise ArtifactError(f"{artifact['id']}: Hugging Face snapshot does not resolve to verified blob")
    if reference.is_symlink() or not reference.is_file():
        raise ArtifactError(f"{artifact['id']}: Hugging Face main reference missing")
    if reference.read_text(encoding="utf-8").strip() != revision:
        raise ArtifactError(f"{artifact['id']}: Hugging Face main reference is not pinned")


def verify_artifact(model_root: Path, artifact: dict[str, Any]) -> None:
    path = artifact_path(model_root, artifact)
    _verify_file(path, artifact)
    if artifact["kind"] == "zip":
        _verify_zip_outputs(model_root, artifact, path)
    _verify_huggingface_cache(model_root, artifact)


def verify_all(model_root: Path, manifest: dict[str, Any]) -> None:
    for artifact in manifest["artifacts"]:
        verify_artifact(model_root, artifact)
        print(f"verified {artifact['id']}", flush=True)


def _download_one(artifact: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        artifact["source"]["url"],
        headers={"User-Agent": "content-runpod-artifact-fetcher/1"},
    )
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{destination.name}.", suffix=".partial",
            dir=destination.parent, delete=False
        ) as output:
            temp_path = Path(output.name)
            digest = hashlib.sha256()
            size = 0
            last_report = 0
            with urlopen(request, timeout=120) as response:
                while chunk := response.read(CHUNK_BYTES):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                    if size - last_report >= 512 * 1024 * 1024:
                        print(f"fetching {artifact['id']}: {size} bytes", flush=True)
                        last_report = size
            output.flush()
            os.fsync(output.fileno())
        if size != artifact["expected_bytes"]:
            raise ArtifactError(
                f"{artifact['id']}: downloaded byte count {size} != {artifact['expected_bytes']}"
            )
        actual_digest = digest.hexdigest()
        if actual_digest != artifact["sha256"]:
            raise ArtifactError(
                f"{artifact['id']}: downloaded sha256 {actual_digest} != {artifact['sha256']}"
            )
        os.chmod(temp_path, 0o640)
        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _extract_zip(model_root: Path, artifact: dict[str, Any], archive_path: Path) -> None:
    extract_relative = safe_relative_path(artifact["extract_to"], field="artifact.extract_to")
    extract_root = model_root.joinpath(*extract_relative.parts)
    extract_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        mapping = _zip_member_map(archive, artifact["required_members"])
        for basename, info in mapping.items():
            destination = extract_root / basename
            temp_path: Path | None = None
            try:
                with archive.open(info) as source, tempfile.NamedTemporaryFile(
                    mode="wb", prefix=f".{basename}.", suffix=".partial",
                    dir=extract_root, delete=False
                ) as output:
                    temp_path = Path(output.name)
                    shutil.copyfileobj(source, output, length=CHUNK_BYTES)
                    output.flush()
                    os.fsync(output.fileno())
                os.chmod(temp_path, 0o640)
                os.replace(temp_path, destination)
                temp_path = None
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)


def _required_free_bytes(model_root: Path, manifest: dict[str, Any]) -> int:
    required = 0
    for artifact in manifest["artifacts"]:
        destination = artifact_path(model_root, artifact)
        if not destination.exists():
            required += artifact["expected_bytes"]
            if artifact["kind"] == "zip":
                required += artifact["expected_bytes"]
    return required


def fetch_all(model_root: Path, manifest: dict[str, Any]) -> None:
    model_root.mkdir(parents=True, exist_ok=True)
    required = _required_free_bytes(model_root, manifest)
    free = shutil.disk_usage(model_root).free
    if free < required + MIN_FREE_HEADROOM:
        raise ArtifactError(
            f"insufficient free storage: need at least {required + MIN_FREE_HEADROOM} bytes, have {free}"
        )

    for artifact in manifest["artifacts"]:
        destination = artifact_path(model_root, artifact)
        if destination.exists():
            # Never overwrite an existing mismatched model automatically.
            _verify_file(destination, artifact)
        else:
            print(f"fetching required artifact {artifact['id']}", flush=True)
            last_error: OSError | ArtifactError | None = None
            for attempt in range(1, 4):
                try:
                    _download_one(artifact, destination)
                    last_error = None
                    break
                except (OSError, ArtifactError) as exc:
                    last_error = exc
                    if attempt < 3:
                        print(
                            f"retrying {artifact['id']} after failed attempt {attempt}: {exc}",
                            file=sys.stderr,
                            flush=True,
                        )
                        time.sleep(attempt)
            if last_error is not None:
                raise last_error
        if artifact["kind"] == "zip":
            try:
                _verify_zip_outputs(model_root, artifact, destination)
            except ArtifactError:
                _extract_zip(model_root, artifact, destination)
        _ensure_huggingface_cache(model_root, artifact)
        verify_artifact(model_root, artifact)
        print(f"ready {artifact['id']}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, default=Path("/workspace/models"))
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--validate-only", action="store_true")
    action.add_argument("--check-only", action="store_true")
    action.add_argument("--download", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.validate_only:
            print("model manifest valid")
        elif args.check_only:
            verify_all(args.model_root, manifest)
        else:
            fetch_all(args.model_root, manifest)
    except (ManifestError, ArtifactError, OSError, zipfile.BadZipFile) as exc:
        print(f"model artifact validation failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
