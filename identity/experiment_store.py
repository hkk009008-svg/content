"""Durable state for the fixed native-reference and character-LoRA comparison."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from identity.protocols import SUPPORTED_PROTOCOL_ID, protocol_cell_specs


DEFAULT_DB_PATH = "data/identity_experiments.db"
MAX_LIST_LIMIT = 100
_ACTIVE_STATES = ("queued", "running", "unknown")
_STATES = ("queued", "running", "succeeded", "failed", "blocked", "unknown", "cancelled")
_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_REQUEST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class IdentityExperimentError(RuntimeError):
    pass


class IdentityExperimentValidationError(IdentityExperimentError):
    pass


class IdentityExperimentConflict(IdentityExperimentError):
    pass


class IdentityExperimentNotFound(IdentityExperimentError):
    pass


class IdentityExperimentPathError(IdentityExperimentError):
    pass


class IdentityExperimentIntegrityError(IdentityExperimentError):
    pass


@dataclass(frozen=True)
class CreateResult:
    experiment: dict[str, Any]
    created: bool
    disposition: str


def identity_experiment_db_path(value: str | os.PathLike[str] | None = None) -> Path:
    raw = os.fspath(value) if value is not None else os.environ.get(
        "IDENTITY_EXPERIMENT_DB_PATH", DEFAULT_DB_PATH
    )
    raw = raw.strip()
    if not raw or raw == ":memory:" or raw.startswith("file:") or "\x00" in raw:
        raise IdentityExperimentPathError(
            "IDENTITY_EXPERIMENT_DB_PATH must be a durable filesystem path"
        )
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path.resolve(strict=False)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def identity_reference_fingerprint(references: Iterable[Mapping[str, Any]]) -> str:
    """Bind consent to the ordered roles and exact bytes selected for training."""

    selected = [
        {
            "role": str(reference["role"]),
            "sha256": str(reference["sha256"]),
            "size_bytes": int(reference["size_bytes"]),
        }
        for reference in references
    ]
    return _fingerprint(selected)


def _bounded_text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise IdentityExperimentValidationError(f"{label} must be a string")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise IdentityExperimentValidationError(
            f"{label} must contain 1 through {maximum} characters"
        )
    return normalized


def _safe_error(value: object) -> str:
    text = " ".join(str(value or "Identity comparison failed").split())
    return text[:500]


class IdentityExperimentStore:
    def __init__(self, db_path: str | os.PathLike[str] | None = None):
        self.path = identity_experiment_db_path(db_path)
        try:
            mode = self.path.lstat().st_mode
        except FileNotFoundError:
            mode = None
        if mode is not None and stat.S_ISLNK(mode):
            raise IdentityExperimentPathError("Identity Lab database cannot be a symlink")
        if mode is not None and not stat.S_ISREG(mode):
            raise IdentityExperimentPathError("Identity Lab database must be a file")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def runner_lock_path(self) -> Path:
        return self.path.with_name(f".{self.path.name}.runner.lock")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS identity_experiments (
                    experiment_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    method TEXT NOT NULL CHECK (method = 'native_flux2'),
                    protocol_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    input_fingerprint TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    aspect_ratio TEXT NOT NULL,
                    references_json TEXT NOT NULL,
                    cells_json TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN ('queued', 'running', 'succeeded', 'failed',
                                  'blocked', 'unknown', 'cancelled')
                    ),
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                        CHECK (cancel_requested IN (0, 1)),
                    lora_consent INTEGER NOT NULL DEFAULT 0
                        CHECK (lora_consent IN (0, 1)),
                    safe_error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_request
                    ON identity_experiments(project_id, request_id);
                CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_active_project
                    ON identity_experiments(project_id)
                    WHERE state IN ('queued', 'running', 'unknown');
                CREATE INDEX IF NOT EXISTS ix_identity_claim
                    ON identity_experiments(state, created_at, experiment_id);
                CREATE INDEX IF NOT EXISTS ix_identity_project_history
                    ON identity_experiments(project_id, created_at DESC, experiment_id DESC);
                """
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(identity_experiments)")
            }
            if "lora_consent" not in columns:
                connection.execute(
                    """ALTER TABLE identity_experiments
                       ADD COLUMN lora_consent INTEGER NOT NULL DEFAULT 0
                       CHECK (lora_consent IN (0, 1))"""
                )

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["references"] = json.loads(value.pop("references_json"))
        value["cells"] = json.loads(value.pop("cells_json"))
        value["cancel_requested"] = bool(value["cancel_requested"])
        value["lora_consent"] = bool(value.get("lora_consent", 0))
        return value

    @staticmethod
    def _public(value: Mapping[str, Any]) -> dict[str, Any]:
        references = [
            {
                "role": reference["role"],
                "sha256": reference["sha256"],
                "size_bytes": reference["size_bytes"],
            }
            for reference in value["references"]
        ]
        return {
            "experiment_id": value["experiment_id"],
            "project_id": value["project_id"],
            "character_id": value["character_id"],
            "method": (
                "identity_comparison" if value["lora_consent"] else value["method"]
            ),
            "protocol_id": value["protocol_id"],
            "request_id": value["request_id"],
            "prompt": value["prompt"],
            "aspect_ratio": value["aspect_ratio"],
            "state": value["state"],
            "cancel_requested": bool(value["cancel_requested"]),
            "lora_consent": bool(value["lora_consent"]),
            "safe_error": value["safe_error"],
            "created_at": value["created_at"],
            "updated_at": value["updated_at"],
            "references": references,
            "reference_count": len(references),
            "reference_fingerprint": identity_reference_fingerprint(references),
            "cells": [dict(cell) for cell in value["cells"]],
        }

    @staticmethod
    def _reference_snapshot(
        project_root: Path,
        subject_paths: Iterable[tuple[str, str]],
        experiment_id: str,
    ) -> list[dict[str, Any]]:
        try:
            root = project_root.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise IdentityExperimentPathError("project root is unavailable") from exc
        lab_root = root / ".identity_lab"
        experiments_root = lab_root / "experiments"
        for directory in (lab_root, experiments_root):
            try:
                mode = directory.lstat().st_mode
            except FileNotFoundError:
                directory.mkdir(mode=0o700)
            else:
                if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                    raise IdentityExperimentPathError(
                        "Identity Lab storage must be a project-owned directory"
                    )
        snapshot_root = experiments_root / experiment_id / "inputs"
        try:
            snapshot_root.mkdir(mode=0o700, parents=True, exist_ok=False)
        except OSError as exc:
            raise IdentityExperimentPathError(
                "Identity Lab reference snapshot could not be created"
            ) from exc

        snapshots: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        seen_hashes: set[str] = set()
        for raw_role, raw_path in subject_paths:
            role = _bounded_text(raw_role, "reference role", maximum=32)
            path = Path(raw_path)
            try:
                mode = path.lstat().st_mode
                resolved = path.resolve(strict=True)
                resolved.relative_to(root)
            except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
                raise IdentityExperimentPathError(
                    "approved reference is unavailable or outside the project"
                ) from exc
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise IdentityExperimentPathError("approved references must be regular files")
            canonical = str(resolved)
            if canonical in seen_paths:
                continue
            before = resolved.stat()
            content = resolved.read_bytes()
            after = resolved.stat()
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
            ):
                raise IdentityExperimentIntegrityError(
                    "approved reference changed while it was read"
                )
            digest = hashlib.sha256(content).hexdigest()
            if digest in seen_hashes:
                raise IdentityExperimentValidationError(
                    "approved references must contain four distinct images"
                )
            seen_paths.add(canonical)
            seen_hashes.add(digest)
            suffix = resolved.suffix.lower()
            if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
                suffix = ".image"
            snapshot_path = snapshot_root / f"reference-{len(snapshots) + 1}{suffix}"
            try:
                with snapshot_path.open("xb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                snapshot_path.chmod(0o400)
            except OSError as exc:
                raise IdentityExperimentPathError(
                    "Identity Lab reference snapshot could not be written"
                ) from exc
            snapshots.append(
                {
                    "role": role,
                    "path": str(snapshot_path),
                    "sha256": digest,
                    "size_bytes": len(content),
                }
            )
        if len(snapshots) != 4:
            raise IdentityExperimentValidationError(
                "Native FLUX.2 comparison requires four approved references"
            )
        return snapshots

    def create_experiment(
        self,
        *,
        project_id: str,
        character_id: str,
        request_id: str,
        prompt: str,
        aspect_ratio: str,
        protocol_id: str,
        lora_consent: bool,
        project_root: str | os.PathLike[str],
        subject_paths: Iterable[tuple[str, str]],
        expected_reference_fingerprint: str | None = None,
    ) -> CreateResult:
        project_id = _bounded_text(project_id, "project_id", maximum=128)
        character_id = _bounded_text(character_id, "character_id", maximum=128)
        if not isinstance(request_id, str) or not _REQUEST_RE.fullmatch(request_id):
            raise IdentityExperimentValidationError(
                "request_id must be 8 through 128 safe characters"
            )
        prompt = _bounded_text(prompt, "prompt", maximum=1000)
        aspect_ratio = _bounded_text(aspect_ratio, "aspect_ratio", maximum=16)
        if protocol_id != SUPPORTED_PROTOCOL_ID:
            raise IdentityExperimentValidationError("unsupported identity protocol")
        if lora_consent is not True:
            raise IdentityExperimentValidationError(
                "character LoRA training requires explicit consent"
            )
        experiment_id = uuid.uuid4().hex
        try:
            resolved_project_root = Path(project_root).resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise IdentityExperimentPathError("project root is unavailable") from exc
        snapshot_parent = (
            resolved_project_root / ".identity_lab" / "experiments" / experiment_id
        )
        try:
            references = self._reference_snapshot(
                resolved_project_root, subject_paths, experiment_id
            )
            if expected_reference_fingerprint is not None:
                if (
                    not isinstance(expected_reference_fingerprint, str)
                    or not _SHA_RE.fullmatch(expected_reference_fingerprint)
                    or identity_reference_fingerprint(references)
                    != expected_reference_fingerprint
                ):
                    raise IdentityExperimentIntegrityError(
                        "approved identity references changed after consent"
                    )
        except Exception:
            shutil.rmtree(snapshot_parent, ignore_errors=True)
            raise
        cells = [
            {
                "cell_key": spec.cell_key,
                "method": spec.method,
                "label": spec.label,
                "reference_count": spec.reference_count,
                "seed": spec.seed,
                "attempt_index": 0,
                "explicit_resume": False,
                "state": "pending",
                "prompt_id": None,
                "output_path": None,
                "output_sha256": None,
                "latency_ms": None,
                "identity_score": None,
                "identity_verdict": "unknown",
                "safe_error": "",
            }
            for spec in protocol_cell_specs(protocol_id)
        ]
        binding = {
            "project_id": project_id,
            "character_id": character_id,
            "method": "identity_comparison",
            "lora_consent": True,
            "protocol_id": protocol_id,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "references": [
                {key: reference[key] for key in ("role", "sha256", "size_bytes")}
                for reference in references
            ],
        }
        input_fingerprint = _fingerprint(binding)
        now = time.time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM identity_experiments WHERE project_id = ? AND request_id = ?",
                (project_id, request_id),
            ).fetchone()
            if existing is not None:
                value = self._decode(existing)
                if value["input_fingerprint"] != input_fingerprint:
                    raise IdentityExperimentConflict(
                        "request_id was already used with different inputs"
                    )
                connection.commit()
                shutil.rmtree(snapshot_parent, ignore_errors=True)
                return CreateResult(self._public(value), False, "replayed")
            active = connection.execute(
                """SELECT experiment_id FROM identity_experiments
                     WHERE project_id = ? AND state IN ('queued', 'running', 'unknown')
                     LIMIT 1""",
                (project_id,),
            ).fetchone()
            if active is not None:
                raise IdentityExperimentConflict(
                    "project already has an active identity experiment"
                )
            connection.execute(
                """
                INSERT INTO identity_experiments (
                    experiment_id, project_id, character_id, method, protocol_id,
                    request_id, input_fingerprint, prompt, aspect_ratio,
                    references_json, cells_json, state, lora_consent,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'native_flux2', ?, ?, ?, ?, ?, ?, ?, 'queued', 1, ?, ?)
                """,
                (
                    experiment_id,
                    project_id,
                    character_id,
                    protocol_id,
                    request_id,
                    input_fingerprint,
                    prompt,
                    aspect_ratio,
                    _canonical_json(references),
                    _canonical_json(cells),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM identity_experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            connection.commit()
            assert row is not None
            return CreateResult(self._public(self._decode(row)), True, "created")
        except Exception:
            connection.rollback()
            shutil.rmtree(snapshot_parent, ignore_errors=True)
            raise
        finally:
            connection.close()

    def get_internal(self, experiment_id: str) -> dict[str, Any] | None:
        if not isinstance(experiment_id, str) or not _ID_RE.fullmatch(experiment_id):
            return None
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM identity_experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
        return self._decode(row) if row is not None else None

    def get_experiment(self, project_id: str, experiment_id: str) -> dict[str, Any] | None:
        if not isinstance(experiment_id, str) or not _ID_RE.fullmatch(experiment_id):
            return None
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM identity_experiments WHERE project_id = ? AND experiment_id = ?",
                (project_id, experiment_id),
            ).fetchone()
        return self._public(self._decode(row)) if row is not None else None

    def list_experiments(self, project_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not 1 <= limit <= MAX_LIST_LIMIT:
            raise IdentityExperimentValidationError(
                f"limit must be between 1 and {MAX_LIST_LIMIT}"
            )
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT * FROM identity_experiments WHERE project_id = ?
                   ORDER BY created_at DESC, experiment_id DESC LIMIT ?""",
                (project_id, limit),
            ).fetchall()
        return [self._public(self._decode(row)) for row in rows]

    def claim_next(self) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM identity_experiments WHERE state = 'queued'
                   ORDER BY created_at, experiment_id LIMIT 1"""
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            now = time.time()
            connection.execute(
                """UPDATE identity_experiments
                      SET state = 'running', updated_at = ?, safe_error = ''
                    WHERE experiment_id = ? AND state = 'queued'""",
                (now, row["experiment_id"]),
            )
            claimed = connection.execute(
                "SELECT * FROM identity_experiments WHERE experiment_id = ?",
                (row["experiment_id"],),
            ).fetchone()
            connection.commit()
            return self._decode(claimed) if claimed is not None else None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def recover_running(self) -> int:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT * FROM identity_experiments WHERE state = 'running'"
            ).fetchall()
            now = time.time()
            for row in rows:
                value = self._decode(row)
                cells = value["cells"]
                for cell in cells:
                    if cell["state"] == "running":
                        cell["state"] = "pending"
                        cell["safe_error"] = "Interrupted run recovered"
                connection.execute(
                    """UPDATE identity_experiments
                          SET state = 'queued', cells_json = ?, updated_at = ?,
                              safe_error = 'Interrupted run recovered'
                        WHERE experiment_id = ? AND state = 'running'""",
                    (_canonical_json(cells), now, value["experiment_id"]),
                )
            connection.commit()
            return len(rows)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _mutate_cells(self, experiment_id: str, mutate) -> dict[str, Any]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM identity_experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            if row is None:
                raise IdentityExperimentNotFound("identity experiment not found")
            value = self._decode(row)
            mutate(value)
            value["updated_at"] = time.time()
            connection.execute(
                """UPDATE identity_experiments
                      SET state = ?, cells_json = ?, cancel_requested = ?,
                          safe_error = ?, updated_at = ?
                    WHERE experiment_id = ?""",
                (
                    value["state"],
                    _canonical_json(value["cells"]),
                    int(bool(value["cancel_requested"])),
                    value["safe_error"],
                    value["updated_at"],
                    experiment_id,
                ),
            )
            connection.commit()
            return value
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _cell(value: Mapping[str, Any], cell_key: str) -> dict[str, Any]:
        for cell in value["cells"]:
            if cell["cell_key"] == cell_key:
                return cell
        raise IdentityExperimentValidationError("identity comparison cell not found")

    def mark_cell_running(self, experiment_id: str, cell_key: str) -> None:
        def mutate(value: dict[str, Any]) -> None:
            if value["state"] != "running":
                raise IdentityExperimentConflict("identity experiment is not running")
            cell = self._cell(value, cell_key)
            if cell["state"] != "pending":
                raise IdentityExperimentConflict("identity comparison cell is not pending")
            cell["state"] = "running"
            cell["safe_error"] = ""

        self._mutate_cells(experiment_id, mutate)

    def complete_cell(
        self,
        experiment_id: str,
        cell_key: str,
        *,
        prompt_id: str,
        output_path: str,
        output_sha256: str,
        latency_ms: int,
        identity_score: float | None,
        identity_verdict: str,
    ) -> None:
        if not isinstance(prompt_id, str) or not prompt_id:
            raise IdentityExperimentValidationError("prompt_id is required")
        if not isinstance(output_path, str) or not output_path:
            raise IdentityExperimentValidationError("output_path is required")
        if not isinstance(output_sha256, str) or not _SHA_RE.fullmatch(output_sha256):
            raise IdentityExperimentValidationError("output_sha256 is invalid")
        if type(latency_ms) is not int or latency_ms < 0:
            raise IdentityExperimentValidationError("latency_ms is invalid")
        if identity_score is not None and (
            isinstance(identity_score, bool)
            or not isinstance(identity_score, (int, float))
            or not 0.0 <= float(identity_score) <= 1.0
        ):
            raise IdentityExperimentValidationError("identity_score is invalid")
        if identity_verdict not in {"passed", "failed", "unknown"}:
            raise IdentityExperimentValidationError("identity_verdict is invalid")

        def mutate(value: dict[str, Any]) -> None:
            cell = self._cell(value, cell_key)
            if value["state"] != "running" or cell["state"] != "running":
                raise IdentityExperimentConflict("identity comparison cell is not running")
            cell.update(
                {
                    "state": "succeeded",
                    "prompt_id": prompt_id,
                    "output_path": output_path,
                    "output_sha256": output_sha256,
                    "latency_ms": latency_ms,
                    "identity_score": None if identity_score is None else float(identity_score),
                    "identity_verdict": identity_verdict,
                    "safe_error": "",
                }
            )

        self._mutate_cells(experiment_id, mutate)

    def block_cell(
        self,
        experiment_id: str,
        cell_key: str,
        *,
        state: str,
        safe_error: str,
    ) -> None:
        if state not in {"failed", "blocked", "unknown"}:
            raise IdentityExperimentValidationError("invalid blocked cell state")

        def mutate(value: dict[str, Any]) -> None:
            cell = self._cell(value, cell_key)
            if cell["state"] not in {"pending", "running"}:
                raise IdentityExperimentConflict("identity comparison cell is terminal")
            detail = _safe_error(safe_error)
            cell["state"] = state
            cell["safe_error"] = detail
            value["state"] = state
            value["safe_error"] = detail

        self._mutate_cells(experiment_id, mutate)

    def finish_succeeded(self, experiment_id: str) -> None:
        def mutate(value: dict[str, Any]) -> None:
            if not value["cells"] or any(
                cell["state"] != "succeeded" for cell in value["cells"]
            ):
                raise IdentityExperimentConflict("identity comparison is incomplete")
            value["state"] = "succeeded"
            value["safe_error"] = ""

        self._mutate_cells(experiment_id, mutate)

    def finish_cancelled(self, experiment_id: str) -> None:
        def mutate(value: dict[str, Any]) -> None:
            for cell in value["cells"]:
                if cell["state"] in {"pending", "running"}:
                    cell["state"] = "cancelled"
            value["state"] = "cancelled"
            value["cancel_requested"] = True

        self._mutate_cells(experiment_id, mutate)

    def cancel(self, project_id: str, experiment_id: str) -> dict[str, Any] | None:
        current = self.get_experiment(project_id, experiment_id)
        if current is None:
            return None
        if current["state"] == "queued":
            self.finish_cancelled(experiment_id)
        elif current["state"] == "running":
            with closing(self._connect()) as connection:
                connection.execute(
                    """UPDATE identity_experiments
                          SET cancel_requested = 1, updated_at = ?
                        WHERE project_id = ? AND experiment_id = ? AND state = 'running'""",
                    (time.time(), project_id, experiment_id),
                )
        return self.get_experiment(project_id, experiment_id)

    def requeue(self, project_id: str, experiment_id: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM identity_experiments
                     WHERE project_id = ? AND experiment_id = ?""",
                (project_id, experiment_id),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            value = self._decode(row)
            if value["state"] not in {"failed", "blocked", "unknown"}:
                raise IdentityExperimentConflict("identity experiment cannot be resumed")
            active = connection.execute(
                """SELECT experiment_id FROM identity_experiments
                     WHERE project_id = ? AND experiment_id <> ?
                       AND state IN ('queued', 'running', 'unknown')
                     LIMIT 1""",
                (project_id, experiment_id),
            ).fetchone()
            if active is not None:
                raise IdentityExperimentConflict(
                    "project already has an active identity experiment"
                )
            for cell in value["cells"]:
                if cell["state"] != "succeeded":
                    if cell["state"] == "failed":
                        cell["attempt_index"] = int(cell.get("attempt_index", 0)) + 1
                    cell["explicit_resume"] = True
                    cell["state"] = "pending"
                    cell["safe_error"] = ""
            value["state"] = "queued"
            value["cancel_requested"] = False
            value["safe_error"] = ""
            value["updated_at"] = time.time()
            connection.execute(
                """UPDATE identity_experiments
                      SET state = 'queued', cells_json = ?, cancel_requested = 0,
                          safe_error = '', updated_at = ?
                    WHERE project_id = ? AND experiment_id = ?""",
                (
                    _canonical_json(value["cells"]),
                    value["updated_at"],
                    project_id,
                    experiment_id,
                ),
            )
            connection.commit()
            return self._public(value)
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise IdentityExperimentConflict(
                "project already has an active identity experiment"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def cancel_requested(self, experiment_id: str) -> bool:
        value = self.get_internal(experiment_id)
        return bool(value and value["cancel_requested"])

    def has_active_project(self, project_id: str) -> bool:
        placeholders = ",".join("?" for _ in _ACTIVE_STATES)
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"SELECT 1 FROM identity_experiments WHERE project_id = ? AND state IN ({placeholders}) LIMIT 1",
                (project_id, *_ACTIVE_STATES),
            ).fetchone()
        return row is not None

    def has_active_character(self, project_id: str, character_id: str) -> bool:
        placeholders = ",".join("?" for _ in _ACTIVE_STATES)
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"""SELECT 1 FROM identity_experiments
                      WHERE project_id = ? AND character_id = ?
                        AND state IN ({placeholders}) LIMIT 1""",
                (project_id, character_id, *_ACTIVE_STATES),
            ).fetchone()
        return row is not None
