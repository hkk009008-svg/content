"""Project-scoped artifact history and deterministic client-package API."""

from __future__ import annotations

import logging
import hashlib
import os
import re
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from cinema.artifact_versions import (
    ArtifactIntegrityError,
    ArtifactLockError,
    ArtifactPathError,
    ArtifactValidationError,
    ArtifactVersionStore,
    ClientPackageBuilder,
    DISTRIBUTION_CLIENT,
)
from project_manager import is_safe_project_id, load_existing_project_readonly


logger = logging.getLogger(__name__)
artifact_api = Blueprint("artifact_api", __name__)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PUBLIC_ARTIFACT_FIELDS = (
    "artifact_id",
    "sequence",
    "version",
    "logical_name",
    "sha256",
    "byte_size",
    "media_type",
    "provider",
    "model",
    "seed",
    "parameters",
    "source_hashes",
    "dependency_hashes",
    "distribution_class",
    "reproducibility",
    "created_at",
)


def _project_or_error(pid: str):
    if not is_safe_project_id(pid):
        return None, (jsonify({"error": "Invalid project_id"}), 400)
    project = load_existing_project_readonly(pid)
    if not project:
        return None, (jsonify({"error": "Project not found"}), 404)
    return project, None


def _public_record(record: dict) -> dict:
    return {field: record.get(field) for field in _PUBLIC_ARTIFACT_FIELDS}


def _artifact_error_response(exc: Exception):
    if isinstance(exc, ArtifactLockError):
        return jsonify({"error": "Artifact ledger is busy", "retryable": True}), 423
    if isinstance(exc, ArtifactIntegrityError):
        return jsonify({"error": "Artifact integrity verification failed"}), 409
    if isinstance(exc, (ArtifactValidationError, ArtifactPathError)):
        return jsonify({"error": str(exc)}), 400
    logger.exception("artifact API failed")
    return jsonify({"error": "Artifact operation failed"}), 500


def _query_int(name: str, default: int, minimum: int, maximum: int):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default, None
    try:
        value = int(raw)
    except (TypeError, ValueError, OverflowError):
        return None, (jsonify({"error": f"{name} must be an integer"}), 400)
    if not minimum <= value <= maximum:
        return None, (
            jsonify({"error": f"{name} must be between {minimum} and {maximum}"}),
            400,
        )
    return value, None


@artifact_api.get("/api/projects/<pid>/artifacts")
def api_artifact_history(pid: str):
    """Return verified current artifacts and a bounded newest-first history."""
    _project, error = _project_or_error(pid)
    if error is not None:
        return error
    limit, error = _query_int("limit", 50, 1, 200)
    if error is not None:
        return error
    before, error = _query_int("before", 2**63 - 1, 1, 2**63 - 1)
    if error is not None:
        return error
    try:
        store = ArtifactVersionStore.for_project(pid)
        history = [record for record in reversed(store.history()) if record["sequence"] < before]
        page = history[: limit + 1]
        has_more = len(page) > limit
        page = page[:limit]
        current = store.current_records()
        return jsonify({
            "current": [_public_record(record) for record in current],
            "records": [_public_record(record) for record in page],
            "has_more": has_more,
            "next_before_sequence": page[-1]["sequence"] if has_more and page else None,
        })
    except Exception as exc:
        return _artifact_error_response(exc)


def _adopt_existing_final_export(store: ArtifactVersionStore) -> None:
    """Give a pre-ledger final export an honest output-hash-only record."""
    if store.current_records(distribution_class=DISTRIBUTION_CLIENT):
        return
    final_path = store.project_root / "exports" / "final_cinema.mp4"
    if not final_path.is_file():
        return
    store.record_artifact(
        "final/master",
        final_path,
        media_type="video/mp4",
        model="legacy-final-export",
        distribution_class=DISTRIBUTION_CLIENT,
    )


@artifact_api.post("/api/projects/<pid>/deliverables/package")
def api_build_client_package(pid: str):
    """Build the current deterministic client ZIP and return its download URL."""
    _project, error = _project_or_error(pid)
    if error is not None:
        return error
    if request.is_json:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "JSON object required"}), 400
    else:
        body = {}
    artifact_ids = body.get("artifact_ids")
    if artifact_ids is not None:
        if (
            not isinstance(artifact_ids, list)
            or not artifact_ids
            or len(artifact_ids) > 200
            or any(not isinstance(item, str) or not item for item in artifact_ids)
        ):
            return jsonify({"error": "artifact_ids must be a non-empty list of at most 200 IDs"}), 400
    try:
        store = ArtifactVersionStore.for_project(pid)
        if artifact_ids is None:
            _adopt_existing_final_export(store)
        else:
            owned_ids = {record["artifact_id"] for record in store.history()}
            if any(artifact_id not in owned_ids for artifact_id in artifact_ids):
                # Unknown and cross-project IDs are deliberately indistinguishable.
                return jsonify({"error": "Artifact not found"}), 404
        package_name = f"{pid}-deliverables"
        result = ClientPackageBuilder(store).build(
            package_name,
            artifact_ids=artifact_ids,
        )
        payload = result.to_dict()
        payload.pop("path", None)
        payload.update({
            "filename": Path(result.path).name,
            "download_url": (
                f"/api/projects/{pid}/deliverables/package/download?sha256={result.sha256}"
            ),
        })
        logger.info(
            "Client deliverables packaged",
            extra={"pid": pid, "status": "succeeded", "artifact_count": len(result.artifact_ids)},
        )
        return jsonify(payload), 201
    except Exception as exc:
        return _artifact_error_response(exc)


@artifact_api.get("/api/projects/<pid>/deliverables/package/download")
def api_download_client_package(pid: str):
    """Stream the same content-addressed package descriptor we verify."""
    _project, error = _project_or_error(pid)
    if error is not None:
        return error
    expected_hash = request.args.get("sha256", "")
    if not _SHA256_RE.fullmatch(expected_hash):
        return jsonify({"error": "sha256 must be a lowercase SHA-256 digest"}), 400
    try:
        store = ArtifactVersionStore.for_project(pid)
        package_name = f"{pid}-deliverables-{expected_hash}.zip"
        package_path = store.project_root / "exports" / "client_packages" / package_name
        if not package_path.exists():
            return jsonify({"error": "Client package not found"}), 404

        fd, _relative, before = store._open_owned_file(package_path)
        handle = os.fdopen(fd, "rb")
        digest = hashlib.sha256()
        total = 0
        try:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
            after = os.fstat(handle.fileno())
            if (
                not store._same_file_observation(before, after)
                or total != after.st_size
                or digest.hexdigest() != expected_hash
            ):
                handle.close()
                return jsonify({"error": "Client package hash no longer matches"}), 409
            handle.seek(0)
        except BaseException:
            handle.close()
            raise

        response = send_file(
            handle,
            mimetype="application/zip",
            as_attachment=True,
            download_name=package_name,
            conditional=False,
            etag=False,
        )
        response.call_on_close(handle.close)
        return response
    except Exception as exc:
        return _artifact_error_response(exc)
