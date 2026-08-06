"""Project-scoped API for the executable Identity Lab comparison."""

from __future__ import annotations

import hashlib
import logging
import re
import stat
import threading
from functools import wraps
from pathlib import Path
from typing import Any, Mapping

from flask import Blueprint, jsonify, request

from config.settings import settings
from domain.character_manager import get_identity_reference_paths
from domain.project_manager import (
    ProjectLockError,
    get_project_dir,
    is_safe_project_id,
    load_existing_project_readonly,
)
from identity.experiment_store import (
    MAX_LIST_LIMIT,
    IdentityExperimentConflict,
    IdentityExperimentError,
    IdentityExperimentIntegrityError,
    IdentityExperimentPathError,
    IdentityExperimentStore,
    IdentityExperimentValidationError,
    identity_reference_fingerprint,
)
from identity.native_comparison import (
    IdentityExperimentDispatcher,
    run_identity_experiment,
)
from identity.lora_training import (
    LoraTrainingClient,
    LoraTrainingError,
    current_lora_candidate_sha256,
)
from identity.protocols import BENCHMARK_PROMPT, METHOD_CATALOG, SUPPORTED_PROTOCOL_ID
from performance.comfyui_endpoint import resolve_performance_comfyui
from pipeline_jobs import safe_error_summary
from web_project_operation_lock import project_operation_lock


logger = logging.getLogger(__name__)
identity_experiment_api = Blueprint("identity_experiment_api", __name__)

_HEX_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_CREATE_FIELDS = frozenset(
    {"request_id", "character_id", "lora_consent", "reference_fingerprint"}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_reserve_project_mutation = lambda _pid: True
_release_project_mutation = lambda _pid: None
_project_mutation_timeout = 2.0
_dispatcher: IdentityExperimentDispatcher | None = None
_dispatcher_lock = threading.Lock()


def _lora_method_card() -> dict[str, Any]:
    base = next(
        dict(value) for value in METHOD_CATALOG if value["method"] == "flux2_character_lora"
    )
    endpoint = resolve_performance_comfyui(settings)
    if not endpoint.shared_endpoint or not endpoint.usable:
        return base
    try:
        candidate_sha256 = current_lora_candidate_sha256()
        readiness = LoraTrainingClient(
            endpoint.server_url,
            endpoint.api_key,
            connect_timeout=1.0,
            read_timeout=2.0,
        ).get_readiness(candidate_sha256)
    except (OSError, ValueError, LoraTrainingError):
        return {
            **base,
            "reason": "The current LoRA gateway proof is unavailable.",
            "blocker_code": "lora_readiness_unavailable",
        }
    if readiness.state != "ready":
        if (
            readiness.job_submission_ready
            and readiness.blocker_code == "candidate_training_not_proven"
        ):
            return {
                **base,
                "state": "canary",
                "reason": (
                    "The first authorized run will train the fixed LoRA and automatically "
                    "prove its text-only/adapter benchmark before inference."
                ),
                "blocker_code": readiness.blocker_code,
                "candidate_sha256": readiness.candidate_sha256,
            }
        reason = {
            "candidate_training_not_proven": (
                "The pinned trainer has not passed its Windows training canary."
            ),
            "candidate_training_failed": (
                "The fixed Windows LoRA training canary failed."
            ),
            "candidate_inference_not_proven": (
                "Training passed, but the text-only versus LoRA inference benchmark has not."
            ),
            "candidate_inference_running": (
                "The fixed text-only versus LoRA inference benchmark is still running."
            ),
            "candidate_inference_failed": (
                "The text-only versus LoRA benchmark did not demonstrate a LoRA effect."
            ),
            "candidate_outcome_unknown": (
                "The LoRA training or benchmark outcome is UNKNOWN and must be reconciled."
            ),
            "candidate_evidence_invalid": (
                "The current LoRA training or benchmark evidence is invalid."
            ),
            "gateway_not_configured": (
                "The Windows worker is not configured for character LoRA."
            ),
            "identity_lora_state_invalid": (
                "The Windows LoRA job state failed its integrity contract."
            ),
            "base_flux2_not_ready": (
                "The pinned base FLUX.2 worker is not ready."
            ),
            "backend_not_ready": (
                "The shared Windows GPU backend is not ready."
            ),
        }.get(readiness.blocker_code, "The current LoRA candidate is not ready.")
        return {**base, "reason": reason, "blocker_code": readiness.blocker_code}
    return {
        **base,
        "state": "available",
        "reason": "Runs a fixed text-only control and character-LoRA arm after native 1/2/4.",
        "blocker_code": "",
        "candidate_sha256": readiness.candidate_sha256,
    }


def _method_catalog() -> list[dict[str, Any]]:
    return [
        _lora_method_card() if value["method"] == "flux2_character_lora" else dict(value)
        for value in METHOD_CATALOG
    ]


def configure_identity_project_guard(reserve, release, *, timeout: float = 2.0) -> None:
    global _reserve_project_mutation, _release_project_mutation, _project_mutation_timeout
    _reserve_project_mutation = reserve
    _release_project_mutation = release
    _project_mutation_timeout = float(timeout)


def _project_mutation_guard(fn):
    @wraps(fn)
    def wrapper(pid: str, *args, **kwargs):
        try:
            with project_operation_lock(pid, timeout=_project_mutation_timeout):
                if not _reserve_project_mutation(pid):
                    return jsonify({"error": "Project is busy", "code": "project_busy"}), 409
                try:
                    return fn(pid, *args, **kwargs)
                finally:
                    _release_project_mutation(pid)
        except ProjectLockError as exc:
            return jsonify({"error": str(exc), "code": "project_locked"}), 409

    return wrapper


def _store() -> IdentityExperimentStore:
    return IdentityExperimentStore(settings.identity_experiment_db_path)


def identity_project_has_active_experiment(project_id: str) -> bool:
    return _store().has_active_project(project_id)


def identity_character_has_active_experiment(project_id: str, character_id: str) -> bool:
    return _store().has_active_character(project_id, character_id)


def _project_or_error(pid: str):
    if not is_safe_project_id(pid):
        return None, (jsonify({"error": "Invalid project_id"}), 400)
    project = load_existing_project_readonly(pid)
    if not project:
        return None, (jsonify({"error": "Project not found"}), 404)
    return project, None


def _json_object(*, allowed: frozenset[str], required: frozenset[str] = frozenset()):
    if not request.is_json:
        return None, (jsonify({"error": "JSON object required"}), 400)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, (jsonify({"error": "JSON object required"}), 400)
    if set(body) - allowed:
        return None, (jsonify({"error": "Request contains unsupported fields"}), 400)
    if required - set(body):
        return None, (jsonify({"error": "Request is missing required fields"}), 400)
    return body, None


def _character(project: Mapping[str, Any], character_id: object) -> Mapping[str, Any] | None:
    if not isinstance(character_id, str):
        return None
    for value in project.get("characters", []):
        if isinstance(value, Mapping) and value.get("id") == character_id:
            return value
    return None


def _error_response(exc: Exception):
    if isinstance(exc, IdentityExperimentConflict):
        return jsonify({"error": str(exc)}), 409
    if isinstance(exc, IdentityExperimentValidationError):
        status = 409 if "reference" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    if isinstance(exc, (IdentityExperimentIntegrityError, IdentityExperimentPathError)):
        return jsonify({"error": str(exc)}), 409
    logger.error(
        "Identity Lab operation failed",
        extra={"stage": "identity_lab", "state": "failed", "code": "internal_error"},
    )
    return jsonify({"error": "Identity Lab operation failed"}), 500


def _block_unexpected_runner_error(
    store: IdentityExperimentStore,
    experiment: Mapping[str, Any],
    exc: Exception,
) -> None:
    current = store.get_internal(str(experiment["experiment_id"]))
    if current is None or current["state"] != "running":
        return
    cell = next(
        (value for value in current["cells"] if value["state"] == "running"),
        None,
    )
    if cell is None:
        cell = next(
            (value for value in current["cells"] if value["state"] == "pending"),
            None,
        )
        if cell is not None:
            store.mark_cell_running(current["experiment_id"], cell["cell_key"])
    if cell is not None:
        store.block_cell(
            current["experiment_id"],
            cell["cell_key"],
            # This outer boundary cannot prove whether the fixed request was
            # dispatched. Preserve the same-experiment reconciliation path and
            # fence replacement work.
            state="unknown",
            safe_error=safe_error_summary(exc),
        )


def _run_claimed(store: IdentityExperimentStore, experiment: Mapping[str, Any]) -> None:
    try:
        run_identity_experiment(
            store,
            experiment,
            project_root=Path(get_project_dir(str(experiment["project_id"]))),
        )
    except Exception as exc:
        logger.exception("Identity comparison runner failed before a cell result was recorded")
        _block_unexpected_runner_error(store, experiment, exc)


def _wake_dispatcher() -> None:
    global _dispatcher
    with _dispatcher_lock:
        if _dispatcher is None:
            _dispatcher = IdentityExperimentDispatcher(_store(), _run_claimed)
        dispatcher = _dispatcher
    # A process that previously lost the cross-process runner lock has a dead
    # daemon thread. Let the next request try the lock again after the owner
    # exits instead of leaving this process permanently unable to drain work.
    dispatcher.start()
    dispatcher.wake()


def _reference_selection(
    project: Mapping[str, Any], project_id: str, character_id: str
) -> tuple[list[tuple[str, str]], list[dict[str, Any]], str]:
    root = Path(get_project_dir(project_id)).resolve(strict=True)
    subject_paths = get_identity_reference_paths(
        dict(project), character_id, SUPPORTED_PROTOCOL_ID
    )
    if len(subject_paths) != 4:
        raise IdentityExperimentValidationError(
            "Native FLUX.2 comparison requires four approved references"
        )
    descriptors: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for role, raw_path in subject_paths:
        path = Path(raw_path)
        try:
            before = path.lstat()
            resolved = path.resolve(strict=True)
            relative = resolved.relative_to(root)
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            raise IdentityExperimentPathError(
                "approved reference is unavailable or outside the project"
            ) from exc
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise IdentityExperimentPathError("approved references must be regular files")
        content = resolved.read_bytes()
        after = path.lstat()
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
        ) or path.resolve(strict=True) != resolved:
            raise IdentityExperimentIntegrityError(
                "approved identity reference changed during consent review"
            )
        digest = hashlib.sha256(content).hexdigest()
        if digest in seen_hashes:
            raise IdentityExperimentValidationError(
                "approved references must contain four distinct images"
            )
        seen_hashes.add(digest)
        descriptors.append(
            {
                "role": " ".join(str(role).split()),
                "sha256": digest,
                "size_bytes": len(content),
                "media_path": relative.as_posix(),
            }
        )
    return subject_paths, descriptors, identity_reference_fingerprint(descriptors)


def _character_rows(project: Mapping[str, Any], project_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for value in project.get("characters", []):
        if not isinstance(value, Mapping) or not isinstance(value.get("id"), str):
            continue
        character_id = value["id"]
        try:
            _paths, references, fingerprint = _reference_selection(
                project, project_id, character_id
            )
            count = len(references)
        except Exception:
            count = 0
            references = []
            fingerprint = ""
        eligible = count == 4
        rows.append(
            {
                "character_id": character_id,
                "name": str(value.get("name") or character_id),
                "eligible": eligible,
                "reference_count": count,
                "reference_fingerprint": fingerprint,
                "references": references,
                "reason": "" if eligible else "Add four distinct approved reference images.",
            }
        )
    return rows


@identity_experiment_api.get("/api/projects/<pid>/identity-experiments")
def api_list_identity_experiments(pid: str):
    project, error = _project_or_error(pid)
    if error is not None:
        return error
    try:
        limit = int(request.args.get("limit", "50"))
    except (TypeError, ValueError, OverflowError):
        return jsonify({"error": "limit must be an integer"}), 400
    if not 1 <= limit <= MAX_LIST_LIMIT:
        return jsonify({"error": f"limit must be between 1 and {MAX_LIST_LIMIT}"}), 400
    try:
        experiments = _store().list_experiments(pid, limit=limit)
        _wake_dispatcher()
        return jsonify(
            {
                "experiments": experiments,
                "methods": _method_catalog(),
                "characters": _character_rows(project, pid),
                "prompt": BENCHMARK_PROMPT,
            }
        )
    except Exception as exc:
        return _error_response(exc)


@identity_experiment_api.post("/api/projects/<pid>/identity-experiments")
@_project_mutation_guard
def api_create_identity_experiment(pid: str):
    project, error = _project_or_error(pid)
    if error is not None:
        return error
    body, error = _json_object(allowed=_CREATE_FIELDS, required=_CREATE_FIELDS)
    if error is not None:
        return error
    assert body is not None and project is not None
    character = _character(project, body.get("character_id"))
    if character is None:
        return jsonify({"error": "Character not found"}), 404
    if body.get("lora_consent") is not True:
        return jsonify({"error": "Character LoRA training consent is required"}), 400
    submitted_fingerprint = body.get("reference_fingerprint")
    if not isinstance(submitted_fingerprint, str) or not _SHA256_RE.fullmatch(
        submitted_fingerprint
    ):
        return jsonify({"error": "Review and confirm the selected identity references"}), 400
    lora_method = _lora_method_card()
    if lora_method["state"] not in {"available", "canary"}:
        return jsonify(
            {
                "error": lora_method["reason"],
                "code": lora_method.get("blocker_code", "lora_not_ready"),
            }
        ), 409
    aspect_ratio = str((project.get("global_settings") or {}).get("aspect_ratio") or "16:9")
    try:
        references, _descriptors, current_fingerprint = _reference_selection(
            project, pid, str(character["id"])
        )
        if current_fingerprint != submitted_fingerprint:
            raise IdentityExperimentIntegrityError(
                "Selected identity references changed. Review and confirm them again."
            )
        result = _store().create_experiment(
            project_id=pid,
            character_id=str(character["id"]),
            request_id=body.get("request_id"),
            prompt=BENCHMARK_PROMPT,
            aspect_ratio=aspect_ratio,
            protocol_id=SUPPORTED_PROTOCOL_ID,
            lora_consent=True,
            project_root=Path(get_project_dir(pid)),
            subject_paths=references,
            expected_reference_fingerprint=submitted_fingerprint,
        )
        _wake_dispatcher()
        payload = dict(result.experiment)
        payload.update({"created": result.created, "disposition": result.disposition})
        return jsonify(payload), 202 if result.created else 200
    except IdentityExperimentError as exc:
        return _error_response(exc)
    except Exception as exc:
        return _error_response(exc)


@identity_experiment_api.get(
    "/api/projects/<pid>/identity-experiments/<experiment_id>"
)
def api_get_identity_experiment(pid: str, experiment_id: str):
    _project, error = _project_or_error(pid)
    if error is not None:
        return error
    if not _HEX_ID_RE.fullmatch(experiment_id):
        return jsonify({"error": "Identity experiment not found"}), 404
    detail = _store().get_experiment(pid, experiment_id)
    if detail is None:
        return jsonify({"error": "Identity experiment not found"}), 404
    if detail["state"] in {"queued", "running"}:
        _wake_dispatcher()
    return jsonify(detail)


@identity_experiment_api.post(
    "/api/projects/<pid>/identity-experiments/<experiment_id>/cancel"
)
@_project_mutation_guard
def api_cancel_identity_experiment(pid: str, experiment_id: str):
    _project, error = _project_or_error(pid)
    if error is not None:
        return error
    body, error = _json_object(allowed=frozenset())
    if error is not None:
        return error
    assert body == {}
    detail = _store().cancel(pid, experiment_id)
    if detail is None:
        return jsonify({"error": "Identity experiment not found"}), 404
    return jsonify(detail)


@identity_experiment_api.post(
    "/api/projects/<pid>/identity-experiments/<experiment_id>/resume"
)
@_project_mutation_guard
def api_resume_identity_experiment(pid: str, experiment_id: str):
    _project, error = _project_or_error(pid)
    if error is not None:
        return error
    body, error = _json_object(allowed=frozenset())
    if error is not None:
        return error
    assert body == {}
    try:
        detail = _store().requeue(pid, experiment_id)
    except IdentityExperimentConflict as exc:
        return _error_response(exc)
    if detail is None:
        return jsonify({"error": "Identity experiment not found"}), 404
    _wake_dispatcher()
    return jsonify(detail), 202
