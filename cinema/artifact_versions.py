"""Immutable artifact provenance and deterministic client-package services.

The generation pipeline writes mutable media files into a project's runtime
tree.  This module records immutable *observations* of those files: content
hashes plus the provider/recipe evidence available when the file was accepted.
It deliberately does not claim that a cloud provider can reproduce identical
bytes.  A recorded hash proves which bytes were accepted; it is not a promise
that replaying a provider request will produce them again.

The ledger lives inside the project directory at ``.artifact_versions/``. One
write-once JSON document is created per record and chained to its predecessor;
accepted bytes are copied into an immutable content-addressed object store.
Readers verify the complete chain before returning data. Client packages are
built only from retained objects whose records are explicitly classified as
client deliverables and whose publication path was below ``exports/``.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from filelock import FileLock, Timeout


LEDGER_SCHEMA_VERSION = 1
PACKAGE_SCHEMA_VERSION = 1

_LOGICAL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_MIME_RE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")

DISTRIBUTION_INTERNAL = "internal"
DISTRIBUTION_CLIENT = "client_deliverable"
_DISTRIBUTION_CLASSES = {DISTRIBUTION_INTERNAL, DISTRIBUTION_CLIENT}

_CLIENT_EXTENSIONS = {
    ".flac",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".srt",
    ".txt",
    ".vtt",
    ".wav",
    ".webm",
    ".webp",
}
_CLIENT_MIME_TYPES = {
    "application/pdf",
    "application/x-subrip",
    "text/plain",
    "text/vtt",
}
_FORBIDDEN_CLIENT_SEGMENTS = {
    ".artifact_versions",
    "cache",
    "checkpoints",
    "client_packages",
    "internal",
    "logs",
    "runtime",
    "temp",
    "tmp",
}
_FORBIDDEN_CLIENT_STEMS = {
    ".env",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "password",
    "private_key",
    "secret",
    "secrets",
    "token",
}
_FORBIDDEN_CLIENT_SUFFIXES = {
    ".db",
    ".env",
    ".key",
    ".pem",
    ".sqlite",
    ".sqlite3",
}
_SENSITIVE_PARAMETER_KEYS = {
    "access_key",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "password",
    "private_key",
    "secret",
    "token",
}
_SENSITIVE_PARAMETER_KEY_RE = re.compile(
    r"(?:^|_)(?:authorization|bearer|password|secret|token|credential|"
    r"credentials|api_key|access_key|private_key|client_secret)(?:_|$)"
)
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class ArtifactVersionError(RuntimeError):
    """Base class for artifact-ledger failures."""


class ArtifactValidationError(ArtifactVersionError, ValueError):
    """Caller supplied invalid metadata or a non-deliverable selection."""


class ArtifactPathError(ArtifactVersionError, ValueError):
    """An artifact or package path is outside its project-owned boundary."""


class ArtifactIntegrityError(ArtifactVersionError):
    """Recorded ledger or artifact bytes no longer match their hashes."""


class ArtifactLockError(ArtifactVersionError):
    """The project artifact ledger could not be locked in time."""


@dataclass(frozen=True)
class FileObservation:
    """Stable observation of one regular project-owned file."""

    relative_path: str
    sha256: str
    byte_size: int


@dataclass(frozen=True)
class ClientPackageResult:
    """Result of an atomically published deterministic client package."""

    path: str
    sha256: str
    byte_size: int
    artifact_ids: tuple[str, ...]
    entry_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "artifact_ids": list(self.artifact_ids),
            "entry_count": self.entry_count,
        }


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ArtifactValidationError("metadata must be finite JSON data") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _assert_plain_directory(path: Path, *, create: bool) -> None:
    """Create or validate a private directory without accepting a symlink."""

    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if not create:
            raise
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            mode = path.lstat().st_mode
        else:
            _fsync_directory(path.parent)
            return
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ArtifactPathError(f"artifact state path is not a plain directory: {path.name}")


def _normalise_logical_name(value: object) -> str:
    if not isinstance(value, str) or not _LOGICAL_NAME_RE.fullmatch(value):
        raise ArtifactValidationError("logical_name must be a bounded portable name")
    parts = value.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ArtifactValidationError("logical_name cannot contain traversal components")
    return value


def _normalise_optional_text(field: str, value: object, *, limit: int = 256) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ArtifactValidationError(f"{field} must be a non-empty bounded string or null")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ArtifactValidationError(f"{field} cannot contain control characters")
    return value


def _normalise_hashes(field: str, values: Mapping[str, str] | None) -> dict[str, str]:
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise ArtifactValidationError(f"{field} must be an object of SHA-256 values")
    result: dict[str, str] = {}
    for raw_name, raw_hash in values.items():
        name = _normalise_optional_text(f"{field} key", raw_name, limit=512)
        if name is None or not isinstance(raw_hash, str) or not _SHA256_RE.fullmatch(raw_hash):
            raise ArtifactValidationError(f"{field} values must be SHA-256 hex digests")
        result[name] = raw_hash.lower()
    return dict(sorted(result.items()))


def _normalise_parameter_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _is_sensitive_parameter_key(value: str) -> bool:
    """Recognize provider-prefixed credential keys after normalization."""

    normalized = _normalise_parameter_key(value)
    return (
        normalized in _SENSITIVE_PARAMETER_KEYS
        or normalized == "key"
        or normalized.endswith("_key")
        or _SENSITIVE_PARAMETER_KEY_RE.search(normalized) is not None
    )


def _reject_sensitive_parameter_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ArtifactValidationError("parameter object keys must be strings")
            if _is_sensitive_parameter_key(key):
                raise ArtifactValidationError("parameters cannot contain credential-bearing keys")
            _reject_sensitive_parameter_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_sensitive_parameter_keys(child)


def _normalise_parameters(parameters: Mapping[str, Any] | None) -> dict[str, Any]:
    if parameters is None:
        return {}
    if not isinstance(parameters, Mapping):
        raise ArtifactValidationError("parameters must be a JSON object")
    _reject_sensitive_parameter_keys(parameters)
    # Canonical encode/decode both validates the JSON shape and returns a deep
    # copy so callers cannot mutate a record after its fingerprint is computed.
    return json.loads(_canonical_json(parameters).decode("utf-8"))


def _normalise_seed(seed: object) -> int | str | None:
    if seed is None:
        return None
    if isinstance(seed, bool) or not isinstance(seed, (int, str)):
        raise ArtifactValidationError("seed must be an integer, string, or null")
    if isinstance(seed, str):
        return _normalise_optional_text("seed", seed, limit=256)
    return seed


def _normalise_media_type(media_type: object, relative_path: str) -> str:
    if media_type is None:
        guessed, _ = mimetypes.guess_type(relative_path)
        return (guessed or "application/octet-stream").lower()
    if not isinstance(media_type, str):
        raise ArtifactValidationError("media_type must be a MIME type string")
    value = media_type.strip().lower()
    if not _MIME_RE.fullmatch(value):
        raise ArtifactValidationError("media_type must be a simple MIME type without parameters")
    return value


def _reproducibility(
    provider: str | None,
    model: str | None,
    parameters: Mapping[str, Any],
    seed: object,
    source_hashes: Mapping[str, str],
    dependency_hashes: Mapping[str, str],
) -> dict[str, Any]:
    """Return a conservative status; no status asserts bit-exact replay."""

    if provider is not None:
        return {
            "status": "provider_replay_only",
            "bit_exact": False,
            "note": (
                "Provider, model, recipe, and accepted output are recorded when known; "
                "provider nondeterminism or version drift can change replayed bytes."
            ),
        }
    if model is not None and parameters and seed is not None and (source_hashes or dependency_hashes):
        return {
            "status": "recipe_captured",
            "bit_exact": False,
            "note": "Recipe evidence is captured; byte-identical replay has not been asserted.",
        }
    return {
        "status": "output_hash_only",
        "bit_exact": False,
        "note": "The accepted output bytes are verifiable; reproduction evidence is incomplete.",
    }


class ArtifactVersionStore:
    """Concurrent-safe, project-scoped immutable artifact version ledger."""

    def __init__(
        self,
        project_id: str,
        project_root: str | os.PathLike[str],
        *,
        lock_timeout: float = 10.0,
    ) -> None:
        if not isinstance(project_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", project_id
        ):
            raise ArtifactValidationError("project_id must be one safe path component")
        root = Path(project_root)
        try:
            root_mode = root.lstat().st_mode
        except FileNotFoundError as exc:
            raise ArtifactPathError("project root does not exist") from exc
        if stat.S_ISLNK(root_mode):
            raise ArtifactPathError("project root cannot be a symlink")
        if not stat.S_ISDIR(root_mode):
            raise ArtifactPathError("project root is not a directory")
        try:
            resolved_root = root.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ArtifactPathError("project root does not exist") from exc

        self.project_id = project_id
        self.project_root = resolved_root
        self.lock_timeout = lock_timeout
        self._state_dir = resolved_root / ".artifact_versions"
        self._records_dir = self._state_dir / "records"
        self._objects_dir = self._state_dir / "objects"
        self._lock_path = self._state_dir / "ledger.lock"

    @classmethod
    def for_project(cls, project_id: str, *, lock_timeout: float = 10.0) -> "ArtifactVersionStore":
        """Resolve the canonical project root without creating a missing project."""

        from domain.project_manager import get_project_dir

        return cls(project_id, get_project_dir(project_id), lock_timeout=lock_timeout)

    def _prepare_state(self) -> None:
        _assert_plain_directory(self._state_dir, create=True)
        _assert_plain_directory(self._records_dir, create=True)
        _assert_plain_directory(self._objects_dir, create=True)
        try:
            if stat.S_ISLNK(self._lock_path.lstat().st_mode):
                raise ArtifactPathError("artifact ledger lock cannot be a symlink")
        except FileNotFoundError:
            pass

    def _lock(self) -> FileLock:
        self._prepare_state()
        return FileLock(str(self._lock_path), timeout=self.lock_timeout, mode=0o600)

    def _state_is_present(self) -> bool:
        """Return whether a readable ledger exists, without creating state."""

        try:
            state_mode = self._state_dir.lstat().st_mode
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(state_mode) or not stat.S_ISDIR(state_mode):
            raise ArtifactPathError("artifact state path is not a plain directory")
        try:
            records_mode = self._records_dir.lstat().st_mode
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(records_mode) or not stat.S_ISDIR(records_mode):
            raise ArtifactPathError("artifact records path is not a plain directory")
        try:
            objects_mode = self._objects_dir.lstat().st_mode
        except FileNotFoundError:
            raise ArtifactIntegrityError("artifact object store is missing")
        if stat.S_ISLNK(objects_mode) or not stat.S_ISDIR(objects_mode):
            raise ArtifactPathError("artifact objects path is not a plain directory")
        return True

    def _resolve_owned_file(self, value: str | os.PathLike[str]) -> Path:
        raw = Path(os.fspath(value))
        if not raw.is_absolute() and any(part in {"", ".", ".."} for part in raw.parts):
            raise ArtifactPathError("artifact path cannot contain traversal components")
        candidate = raw if raw.is_absolute() else self.project_root / raw
        try:
            resolved = candidate.resolve(strict=True)
            relative = resolved.relative_to(self.project_root)
        except (FileNotFoundError, RuntimeError) as exc:
            raise ArtifactPathError("artifact path does not resolve to an existing project file") from exc
        except ValueError as exc:
            raise ArtifactPathError("artifact path escapes the project root") from exc
        if not relative.parts:
            raise ArtifactPathError("artifact path must name a file")
        if relative.parts[0] == ".artifact_versions":
            raise ArtifactPathError("artifact state files cannot be registered as outputs")
        return resolved

    def _open_owned_file(self, value: str | os.PathLike[str]) -> tuple[int, str, os.stat_result]:
        resolved = self._resolve_owned_file(value)
        relative = resolved.relative_to(self.project_root).as_posix()
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(resolved, flags)
        except OSError as exc:
            raise ArtifactPathError("artifact could not be opened safely") from exc
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            raise ArtifactPathError("artifact must be a regular file")
        return fd, relative, info

    @staticmethod
    def _same_file_observation(before: os.stat_result, after: os.stat_result) -> bool:
        return (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )

    def observe_file(self, value: str | os.PathLike[str]) -> FileObservation:
        """Hash one project-owned regular file and reject mid-read mutation."""

        fd, relative, before = self._open_owned_file(value)
        digest = hashlib.sha256()
        total = 0
        try:
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        if not self._same_file_observation(before, after) or total != after.st_size:
            raise ArtifactIntegrityError("artifact changed while it was being hashed")
        return FileObservation(relative, digest.hexdigest(), total)

    def _observe_object(self, sha256: str) -> FileObservation:
        """Verify one retained object without following a replacement symlink."""

        if not _SHA256_RE.fullmatch(sha256):
            raise ArtifactIntegrityError("artifact record has an invalid object digest")
        path = self._objects_dir / sha256.lower()
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError as exc:
            raise ArtifactIntegrityError("retained artifact object is missing") from exc
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise ArtifactIntegrityError("retained artifact object is not a plain file")
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise ArtifactIntegrityError("retained artifact object cannot be opened") from exc
        digest = hashlib.sha256()
        total = 0
        try:
            before = os.fstat(fd)
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        if not self._same_file_observation(before, after) or total != after.st_size:
            raise ArtifactIntegrityError("retained artifact object changed while verified")
        observed = digest.hexdigest()
        if observed != sha256.lower():
            raise ArtifactIntegrityError("retained artifact object hash mismatch")
        return FileObservation(
            f".artifact_versions/objects/{sha256.lower()}",
            observed,
            total,
        )

    def _ensure_object(self, observed: FileObservation) -> FileObservation:
        """Durably retain accepted bytes in the content-addressed object store."""

        target = self._objects_dir / observed.sha256
        if target.exists():
            retained = self._observe_object(observed.sha256)
            if retained.byte_size != observed.byte_size:
                raise ArtifactIntegrityError("retained artifact object size mismatch")
            return retained

        source_fd, relative, before = self._open_owned_file(observed.relative_path)
        if relative != observed.relative_path:
            os.close(source_fd)
            raise ArtifactIntegrityError("artifact publication path changed before retention")
        try:
            output_fd, temp_name = tempfile.mkstemp(
                prefix=f".{observed.sha256}-",
                suffix=".tmp",
                dir=self._objects_dir,
            )
        except BaseException:
            os.close(source_fd)
            raise
        temp_path = Path(temp_name)
        digest = hashlib.sha256()
        total = 0
        try:
            with os.fdopen(output_fd, "wb") as output:
                while True:
                    chunk = os.read(source_fd, 1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            after = os.fstat(source_fd)
            if not self._same_file_observation(before, after):
                raise ArtifactIntegrityError("artifact changed while its version was retained")
            if (
                digest.hexdigest() != observed.sha256
                or total != observed.byte_size
                or total != after.st_size
            ):
                raise ArtifactIntegrityError("retained bytes do not match the accepted artifact")
            os.chmod(temp_path, 0o400)
            try:
                os.link(temp_path, target)
            except FileExistsError:
                # Defensive for a second process that retained the same hash.
                pass
            else:
                os.chmod(target, 0o400)
                _fsync_directory(self._objects_dir)
        finally:
            os.close(source_fd)
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

        retained = self._observe_object(observed.sha256)
        if retained.byte_size != observed.byte_size:
            raise ArtifactIntegrityError("retained artifact object size mismatch")
        return retained

    def _open_retained_object(
        self,
        record: Mapping[str, Any],
    ) -> tuple[int, str, os.stat_result]:
        """Open the immutable object named by a verified ledger record."""

        sha256 = record.get("sha256")
        if not isinstance(sha256, str) or not _SHA256_RE.fullmatch(sha256):
            raise ArtifactIntegrityError("artifact record has an invalid object digest")
        sha256 = sha256.lower()
        expected_path = f".artifact_versions/objects/{sha256}"
        if record.get("object_path") != expected_path:
            raise ArtifactIntegrityError("artifact record has a non-canonical object path")
        path = self._objects_dir / sha256
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError as exc:
            raise ArtifactIntegrityError("retained artifact object is missing") from exc
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise ArtifactIntegrityError("retained artifact object is not a plain file")
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise ArtifactIntegrityError("retained artifact object cannot be opened") from exc
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            raise ArtifactIntegrityError("retained artifact object is not a regular file")
        return fd, expected_path, info

    @staticmethod
    def _record_hash(record: Mapping[str, Any]) -> str:
        payload = {key: value for key, value in record.items() if key != "record_hash"}
        return _sha256_bytes(_canonical_json(payload))

    def _load_records_unlocked(self) -> list[dict[str, Any]]:
        if not self._records_dir.exists():
            return []
        records: list[dict[str, Any]] = []
        previous_hash: str | None = None
        expected_sequence = 1
        for path in sorted(self._records_dir.glob("record-*.json")):
            expected_name = f"record-{expected_sequence:012d}.json"
            if path.name != expected_name:
                raise ArtifactIntegrityError("artifact ledger sequence is missing or non-canonical")
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ArtifactIntegrityError(f"artifact ledger record is unreadable: {path.name}") from exc
            if not isinstance(data, dict):
                raise ArtifactIntegrityError(f"artifact ledger record is not an object: {path.name}")
            if data.get("schema_version") != LEDGER_SCHEMA_VERSION:
                raise ArtifactIntegrityError(f"unsupported artifact ledger schema in {path.name}")
            if data.get("sequence") != expected_sequence:
                raise ArtifactIntegrityError(f"artifact ledger sequence mismatch in {path.name}")
            if data.get("previous_record_hash") != previous_hash:
                raise ArtifactIntegrityError(f"artifact ledger chain mismatch in {path.name}")
            observed_hash = data.get("record_hash")
            if not isinstance(observed_hash, str) or observed_hash != self._record_hash(data):
                raise ArtifactIntegrityError(f"artifact ledger hash mismatch in {path.name}")
            records.append(data)
            previous_hash = observed_hash
            expected_sequence += 1
        return records

    def _atomic_create_record(self, sequence: int, record: Mapping[str, Any]) -> None:
        target = self._records_dir / f"record-{sequence:012d}.json"
        if target.exists():
            raise ArtifactIntegrityError("artifact ledger target already exists")
        payload = _canonical_json(record) + b"\n"
        fd, temp_name = tempfile.mkstemp(prefix=".record-", suffix=".tmp", dir=self._records_dir)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            # A same-directory hard link publishes the complete bytes without
            # ever overwriting an immutable record name.  Once linked, keep a
            # complete target even if a later chmod/fsync reports an error; a
            # caller retry will discover the valid record idempotently.
            os.link(temp_path, target)
            os.chmod(target, 0o400)
            _fsync_directory(self._records_dir)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def record_artifact(
        self,
        logical_name: str,
        path: str | os.PathLike[str],
        *,
        media_type: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        parameters: Mapping[str, Any] | None = None,
        seed: int | str | None = None,
        source_hashes: Mapping[str, str] | None = None,
        dependency_hashes: Mapping[str, str] | None = None,
        distribution_class: str = DISTRIBUTION_INTERNAL,
    ) -> dict[str, Any]:
        """Append an immutable version, or return the identical current record.

        Idempotency is content-and-recipe based for the current logical
        artifact.  Repeating the exact call does not consume a new sequence;
        changing bytes or any provenance field does.
        """

        name = _normalise_logical_name(logical_name)
        observed = self.observe_file(path)
        provider_value = _normalise_optional_text("provider", provider)
        model_value = _normalise_optional_text("model", model)
        params = _normalise_parameters(parameters)
        seed_value = _normalise_seed(seed)
        sources = _normalise_hashes("source_hashes", source_hashes)
        dependencies = _normalise_hashes("dependency_hashes", dependency_hashes)
        if distribution_class not in _DISTRIBUTION_CLASSES:
            raise ArtifactValidationError("distribution_class is not supported")
        mime = _normalise_media_type(media_type, observed.relative_path)
        reproduction = _reproducibility(
            provider_value,
            model_value,
            params,
            seed_value,
            sources,
            dependencies,
        )
        identity = {
            "logical_name": name,
            "sha256": observed.sha256,
            "byte_size": observed.byte_size,
            "media_type": mime,
            "path": observed.relative_path,
            "object_path": f".artifact_versions/objects/{observed.sha256}",
            "provider": provider_value,
            "model": model_value,
            "parameters": params,
            "seed": seed_value,
            "source_hashes": sources,
            "dependency_hashes": dependencies,
            "distribution_class": distribution_class,
            "reproducibility": reproduction,
        }
        fingerprint = _sha256_bytes(_canonical_json(identity))

        try:
            with self._lock():
                locked_observation = self.observe_file(observed.relative_path)
                if locked_observation != observed:
                    raise ArtifactIntegrityError(
                        "artifact changed before its ledger record was published"
                    )
                retained = self._ensure_object(observed)
                if retained.relative_path != identity["object_path"]:
                    raise ArtifactIntegrityError("artifact object path is not canonical")
                records = self._load_records_unlocked()
                current = next(
                    (record for record in reversed(records) if record.get("logical_name") == name),
                    None,
                )
                if current is not None and current.get("fingerprint") == fingerprint:
                    return json.loads(json.dumps(current))

                sequence = len(records) + 1
                version = 1 + sum(record.get("logical_name") == name for record in records)
                created_at = (
                    datetime.now(timezone.utc)
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z")
                )
                record: dict[str, Any] = {
                    "schema_version": LEDGER_SCHEMA_VERSION,
                    "artifact_id": f"av-{sequence:012d}-{observed.sha256[:12]}",
                    "sequence": sequence,
                    "version": version,
                    **identity,
                    "fingerprint": fingerprint,
                    "created_at": created_at,
                    "previous_record_hash": records[-1]["record_hash"] if records else None,
                }
                record["record_hash"] = self._record_hash(record)
                self._atomic_create_record(sequence, record)
                return json.loads(json.dumps(record))
        except Timeout as exc:
            raise ArtifactLockError("artifact ledger is busy; retry shortly") from exc

    def history(self, logical_name: str | None = None) -> list[dict[str, Any]]:
        """Return verified chronological history, optionally for one name."""

        name = _normalise_logical_name(logical_name) if logical_name is not None else None
        # Record files are publish-once and atomically linked into place, so a
        # lock-free reader sees either the prior complete prefix or the next
        # complete record.  This also keeps GET/history calls read-only.
        records = self._load_records_unlocked() if self._state_is_present() else []
        if name is not None:
            records = [record for record in records if record.get("logical_name") == name]
        return json.loads(json.dumps(records))

    def current(self, logical_name: str) -> dict[str, Any] | None:
        records = self.history(logical_name)
        return records[-1] if records else None

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        if not isinstance(artifact_id, str) or not artifact_id:
            raise ArtifactValidationError("artifact_id must be a non-empty string")
        return next((record for record in self.history() if record.get("artifact_id") == artifact_id), None)

    def current_records(self, *, distribution_class: str | None = None) -> list[dict[str, Any]]:
        if distribution_class is not None and distribution_class not in _DISTRIBUTION_CLASSES:
            raise ArtifactValidationError("distribution_class is not supported")
        latest: dict[str, dict[str, Any]] = {}
        for record in self.history():
            latest[record["logical_name"]] = record
        records = list(latest.values())
        if distribution_class is not None:
            records = [record for record in records if record["distribution_class"] == distribution_class]
        return sorted(records, key=lambda record: (record["logical_name"], record["sequence"]))

    def verify_artifact(self, artifact_id: str) -> bool:
        record = self.get(artifact_id)
        if record is None:
            raise ArtifactValidationError("artifact_id is not present in this project ledger")
        expected_path = f".artifact_versions/objects/{record['sha256']}"
        if record.get("object_path") != expected_path:
            raise ArtifactIntegrityError("artifact record has a non-canonical object path")
        observed = self._observe_object(record["sha256"])
        return observed.sha256 == record["sha256"] and observed.byte_size == record["byte_size"]


class ClientPackageBuilder:
    """Build deterministic, allowlisted ZIP deliverables for one project."""

    def __init__(self, store: ArtifactVersionStore) -> None:
        self.store = store

    @staticmethod
    def _validate_client_record(record: Mapping[str, Any]) -> str:
        if record.get("distribution_class") != DISTRIBUTION_CLIENT:
            raise ArtifactValidationError("client packages accept only client_deliverable records")
        raw_path = record.get("path")
        if not isinstance(raw_path, str):
            raise ArtifactValidationError("artifact record has no canonical project path")
        path = PurePosixPath(raw_path)
        parts = path.parts
        if not parts or parts[0] != "exports" or len(parts) < 2:
            raise ArtifactValidationError("client deliverables must be stored below exports/")
        lowered = [part.lower() for part in parts]
        if any(part.startswith(".") for part in parts):
            raise ArtifactValidationError("hidden files cannot be client deliverables")
        if any(part in _FORBIDDEN_CLIENT_SEGMENTS for part in lowered):
            raise ArtifactValidationError("runtime or internal paths cannot be client deliverables")
        suffix = path.suffix.lower()
        if suffix in _FORBIDDEN_CLIENT_SUFFIXES or suffix not in _CLIENT_EXTENSIONS:
            raise ArtifactValidationError("artifact extension is not allowlisted for client delivery")
        stem = path.stem.lower()
        if stem in _FORBIDDEN_CLIENT_STEMS:
            raise ArtifactValidationError("credential-like files cannot be client deliverables")
        media_type = record.get("media_type")
        if not isinstance(media_type, str) or not (
            media_type.startswith(("audio/", "image/", "video/"))
            or media_type in _CLIENT_MIME_TYPES
        ):
            raise ArtifactValidationError("artifact media type is not allowlisted for client delivery")
        return PurePosixPath("deliverables", *parts[1:]).as_posix()

    @staticmethod
    def _zip_info(name: str) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
        info.compress_type = zipfile.ZIP_STORED
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        info.flag_bits |= 0x800
        return info

    def _select_records(
        self,
        artifact_ids: Sequence[str] | None,
    ) -> list[tuple[str, dict[str, Any]]]:
        if artifact_ids is None:
            records = self.store.current_records(distribution_class=DISTRIBUTION_CLIENT)
        else:
            if isinstance(artifact_ids, (str, bytes)):
                raise ArtifactValidationError("artifact_ids must be a sequence of IDs")
            requested = list(artifact_ids)
            if not requested or any(not isinstance(item, str) or not item for item in requested):
                raise ArtifactValidationError("artifact_ids must contain non-empty IDs")
            if len(set(requested)) != len(requested):
                raise ArtifactValidationError("artifact_ids cannot contain duplicates")
            by_id = {record["artifact_id"]: record for record in self.store.history()}
            missing = [item for item in requested if item not in by_id]
            if missing:
                raise ArtifactValidationError("one or more artifact IDs are not project-owned")
            records = [by_id[item] for item in requested]
        if not records:
            raise ArtifactValidationError("no client deliverables are available")

        selected = [(self._validate_client_record(record), record) for record in records]
        selected.sort(key=lambda item: (item[0], item[1]["artifact_id"]))
        archive_paths = [item[0] for item in selected]
        if len(set(archive_paths)) != len(archive_paths):
            raise ArtifactValidationError("selected artifacts collide at the same client path")
        return selected

    def _stream_verified_artifact(
        self,
        archive: zipfile.ZipFile,
        archive_path: str,
        record: Mapping[str, Any],
    ) -> None:
        fd, relative, before = self.store._open_retained_object(record)
        if relative != record.get("object_path"):
            os.close(fd)
            raise ArtifactIntegrityError("artifact object path is not canonical")
        digest = hashlib.sha256()
        total = 0
        try:
            with archive.open(self._zip_info(archive_path), "w") as output:
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        if not self.store._same_file_observation(before, after):
            raise ArtifactIntegrityError("retained artifact changed while the client package was built")
        if digest.hexdigest() != record["sha256"] or total != record["byte_size"]:
            raise ArtifactIntegrityError("retained artifact bytes do not match the immutable ledger")

    def build(
        self,
        package_name: str,
        *,
        artifact_ids: Sequence[str] | None = None,
    ) -> ClientPackageResult:
        """Atomically publish a deterministic ZIP from verified deliverables."""

        if not isinstance(package_name, str) or not _PACKAGE_NAME_RE.fullmatch(package_name):
            raise ArtifactValidationError("package_name must be a safe filename stem")
        selected = self._select_records(artifact_ids)

        manifest_entries = [
            {
                "archive_path": archive_path,
                "artifact_id": record["artifact_id"],
                "logical_name": record["logical_name"],
                "version": record["version"],
                "sha256": record["sha256"],
                "byte_size": record["byte_size"],
                "media_type": record["media_type"],
                "provider": record["provider"],
                "model": record["model"],
                "seed": record["seed"],
                "source_hashes": record["source_hashes"],
                "dependency_hashes": record["dependency_hashes"],
                "provenance_sha256": _sha256_bytes(_canonical_json({
                    "parameters": record["parameters"],
                    "seed": record["seed"],
                    "source_hashes": record["source_hashes"],
                    "dependency_hashes": record["dependency_hashes"],
                })),
                "reproducibility": record["reproducibility"],
            }
            for archive_path, record in selected
        ]
        manifest = {
            "schema_version": PACKAGE_SCHEMA_VERSION,
            "project_id": self.store.project_id,
            "artifacts": manifest_entries,
        }
        manifest_bytes = _canonical_json(manifest) + b"\n"
        checksums = [f"{_sha256_bytes(manifest_bytes)}  MANIFEST.json"]
        checksums.extend(
            f"{record['sha256']}  {archive_path}" for archive_path, record in selected
        )
        checksum_bytes = ("\n".join(checksums) + "\n").encode("utf-8")

        exports_dir = self.store.project_root / "exports"
        if exports_dir.exists():
            _assert_plain_directory(exports_dir, create=False)
        else:
            _assert_plain_directory(exports_dir, create=True)
        packages_dir = exports_dir / "client_packages"
        _assert_plain_directory(packages_dir, create=True)
        lock_path = packages_dir / f".{package_name}.lock"
        try:
            try:
                if stat.S_ISLNK(lock_path.lstat().st_mode):
                    raise ArtifactPathError("client package lock cannot be a symlink")
            except FileNotFoundError:
                pass
            with FileLock(
                str(lock_path),
                timeout=self.store.lock_timeout,
                mode=0o600,
            ):
                fd, temp_name = tempfile.mkstemp(
                    prefix=f".{package_name}-",
                    suffix=".tmp",
                    dir=packages_dir,
                )
                temp_path = Path(temp_name)
                try:
                    with os.fdopen(fd, "w+b") as handle:
                        with zipfile.ZipFile(
                            handle,
                            mode="w",
                            compression=zipfile.ZIP_STORED,
                            allowZip64=True,
                        ) as archive:
                            archive.writestr(self._zip_info("MANIFEST.json"), manifest_bytes)
                            archive.writestr(self._zip_info("SHA256SUMS.txt"), checksum_bytes)
                            for archive_path, record in selected:
                                self._stream_verified_artifact(archive, archive_path, record)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.chmod(temp_path, 0o600)

                    # Publish by content hash, never by replacing a shared
                    # fixed filename.  A download URL therefore continues to
                    # name exactly the bytes that were verified when it was
                    # created, even while another build runs concurrently.
                    temp_observation = self.store.observe_file(temp_path)
                    output_path = packages_dir / (
                        f"{package_name}-{temp_observation.sha256}.zip"
                    )
                    try:
                        os.link(temp_path, output_path)
                    except FileExistsError:
                        # Deterministic rebuilds converge on the same path.
                        # The observation below rejects a planted symlink or
                        # any existing file whose bytes do not match.
                        pass
                    else:
                        os.chmod(output_path, 0o600)
                        _fsync_directory(packages_dir)
                    temp_path.unlink()
                except BaseException:
                    try:
                        temp_path.unlink()
                    except FileNotFoundError:
                        pass
                    raise

                observation = self.store.observe_file(output_path)
                if (
                    observation.sha256 != temp_observation.sha256
                    or observation.byte_size != temp_observation.byte_size
                ):
                    raise ArtifactIntegrityError(
                        "published client package does not match the verified build"
                    )
                return ClientPackageResult(
                    path=str(output_path),
                    sha256=observation.sha256,
                    byte_size=observation.byte_size,
                    artifact_ids=tuple(record["artifact_id"] for _, record in selected),
                    entry_count=2 + len(selected),
                )
        except Timeout as exc:
            raise ArtifactLockError("client package is busy; retry shortly") from exc


__all__ = [
    "ArtifactIntegrityError",
    "ArtifactLockError",
    "ArtifactPathError",
    "ArtifactValidationError",
    "ArtifactVersionError",
    "ArtifactVersionStore",
    "ClientPackageBuilder",
    "ClientPackageResult",
    "DISTRIBUTION_CLIENT",
    "DISTRIBUTION_INTERNAL",
    "FileObservation",
]
