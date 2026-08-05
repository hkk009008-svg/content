"""Durable, cross-process queue for full-project generation runs.

The web process owns only a bounded set of worker threads.  Queue truth lives
in SQLite so an accepted request survives a process crash, and an expired
running lease is retried as a checkpoint resume instead of as a fresh run.
"""

from __future__ import annotations

import os
import re
import socket
import sqlite3
import stat
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import fcntl

from config.settings import settings


DEFAULT_DB_PATH = "data/pipeline_jobs.db"
DEFAULT_CONCURRENCY = 1
MAX_CONCURRENCY = 8
DEFAULT_LEASE_SECONDS = 30.0
DEFAULT_POLL_SECONDS = 0.25
_ACTIVE_STATES = ("queued", "running")
_TERMINAL_STATES = ("succeeded", "failed", "cancelled")
_WORKER_SESSION_RE = re.compile(r"^[0-9a-f]{32}$")


def pipeline_job_db_path(value: str | None = None) -> Path:
    """Resolve a durable filesystem path from ``PIPELINE_JOB_DB_PATH``.

    SQLite URI and in-memory forms are deliberately rejected: silently using
    either would defeat crash recovery.  Relative paths are rooted at the
    repository, not at an arbitrary process working directory.
    """

    raw = value if value is not None else settings.pipeline_job_db_path
    raw = str(raw).strip()
    if not raw:
        raise ValueError("PIPELINE_JOB_DB_PATH must not be empty")
    if "\x00" in raw or raw == ":memory:" or raw.startswith("file:"):
        raise ValueError("PIPELINE_JOB_DB_PATH must be a durable filesystem path")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    path = path.resolve(strict=False)
    if path.exists() and path.is_dir():
        raise ValueError("PIPELINE_JOB_DB_PATH must name a file, not a directory")
    return path


def pipeline_queue_concurrency(value: str | int | None = None) -> int:
    """Read and validate the global queue concurrency (one through eight)."""

    raw = value if value is not None else settings.pipeline_queue_concurrency
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("PIPELINE_QUEUE_CONCURRENCY must be an integer from 1 to 8") from exc
    if not 1 <= parsed <= MAX_CONCURRENCY:
        raise ValueError("PIPELINE_QUEUE_CONCURRENCY must be between 1 and 8")
    return parsed


def _utc_iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


_SECRETISH = re.compile(
    r"(?i)(api[_-]?key|token|secret|authorization|password)\s*[:=]\s*[^\s,;]+"
)
_SIGNED_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:x-amz-|x-goog-)?(?:signature|credential|security-token|"
    r"access-key-id|googleaccessid|key-pair-id)=)[^&#\s]+"
)


def safe_error_summary(exc: BaseException, limit: int = 500) -> str:
    """Return a bounded, single-line operator summary without credentials."""

    message = " ".join(str(exc).split())
    message = _SECRETISH.sub(r"\1=[redacted]", message)
    message = _SIGNED_QUERY_SECRET.sub(lambda match: f"{match.group(1)}[redacted]", message)
    summary = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
    return summary[:limit]


@dataclass(frozen=True)
class PipelineJob:
    job_id: str
    project_id: str
    state: str
    requested_resume: bool
    resume_required: bool
    created_at: float
    updated_at: float
    started_at: float | None
    finished_at: float | None
    attempt_count: int
    safe_error: str | None
    worker_id: str | None
    lease_expires_at: float | None
    heartbeat_at: float | None
    cancel_requested: bool

    @property
    def effective_resume(self) -> bool:
        return self.requested_resume or self.resume_required


class PipelineJobStore:
    """Short-connection SQLite store with transactional claim semantics."""

    def __init__(self, db_path: str | os.PathLike[str] | None = None):
        self.path = pipeline_job_db_path(None if db_path is None else str(db_path))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.path), timeout=5.0, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @property
    def worker_fence_dir(self) -> Path:
        """Private same-filesystem directory for process-liveness fences."""

        return self.path.parent / f".{self.path.name}.worker-fences"

    def worker_fence_path(self, session_token: str, *, create_dir: bool = False) -> Path:
        if not isinstance(session_token, str) or not _WORKER_SESSION_RE.fullmatch(
            session_token
        ):
            raise ValueError("worker session token must be 32 lowercase hex characters")
        directory = self.worker_fence_dir
        if create_dir:
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError:
                pass
        try:
            mode = directory.lstat().st_mode
        except FileNotFoundError:
            if create_dir:
                raise RuntimeError("worker fence directory could not be created")
            return directory / f"{session_token}.lock"
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise RuntimeError("pipeline worker fence path is not a plain directory")
        return directory / f"{session_token}.lock"

    @staticmethod
    def _worker_session_token(worker_id: object) -> str | None:
        if not isinstance(worker_id, str):
            return None
        parts = worker_id.rsplit(":", 2)
        if len(parts) != 3 or not _WORKER_SESSION_RE.fullmatch(parts[1]):
            return None
        return parts[1]

    def _worker_fence_state(self, worker_id: object) -> bool | None:
        """Return True while owner lives, False when stopped, None if unverifiable."""

        token = self._worker_session_token(worker_id)
        if token is None:
            return None
        try:
            path = self.worker_fence_path(token)
            mode = path.lstat().st_mode
        except (FileNotFoundError, OSError, RuntimeError, ValueError):
            return None
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            return None
        flags = os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError:
            return None
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            except OSError:
                return None
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                return False
        finally:
            os.close(descriptor)

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pipeline_jobs (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')
                    ),
                    requested_resume INTEGER NOT NULL CHECK (requested_resume IN (0, 1)),
                    resume_required INTEGER NOT NULL DEFAULT 0 CHECK (resume_required IN (0, 1)),
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                    safe_error TEXT,
                    worker_id TEXT,
                    lease_expires_at REAL,
                    heartbeat_at REAL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1))
                );
                CREATE UNIQUE INDEX IF NOT EXISTS uq_pipeline_jobs_active_project
                    ON pipeline_jobs(project_id)
                    WHERE state IN ('queued', 'running');
                CREATE INDEX IF NOT EXISTS ix_pipeline_jobs_claim
                    ON pipeline_jobs(state, created_at, job_id);
                CREATE INDEX IF NOT EXISTS ix_pipeline_jobs_project_history
                    ON pipeline_jobs(project_id, created_at DESC, job_id DESC);
                """
            )

    @staticmethod
    def _row(row: sqlite3.Row | None) -> PipelineJob | None:
        if row is None:
            return None
        return PipelineJob(
            job_id=row["job_id"],
            project_id=row["project_id"],
            state=row["state"],
            requested_resume=bool(row["requested_resume"]),
            resume_required=bool(row["resume_required"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            attempt_count=int(row["attempt_count"]),
            safe_error=row["safe_error"],
            worker_id=row["worker_id"],
            lease_expires_at=row["lease_expires_at"],
            heartbeat_at=row["heartbeat_at"],
            cancel_requested=bool(row["cancel_requested"]),
        )

    def _recover_expired(self, connection: sqlite3.Connection, now: float) -> int:
        """Recover only after the prior process fence proves it has stopped.

        A timestamp alone cannot fence paid work: a live worker may miss a DB
        heartbeat while blocked in a provider request.  Reclaiming it would let
        a second worker overlap the same run.  Every dispatcher therefore holds
        a POSIX lock for its process lifetime.  Expiry makes a job *eligible*
        for inspection; the row is requeued only when that exact owner lock is
        provably no longer held.
        """

        expired = connection.execute(
            """
            SELECT job_id, worker_id, cancel_requested
              FROM pipeline_jobs
             WHERE state = 'running'
               AND lease_expires_at IS NOT NULL
               AND lease_expires_at <= ?
             ORDER BY created_at, job_id
            """,
            (now,),
        ).fetchall()
        recovered = 0
        for row in expired:
            fence_state = self._worker_fence_state(row["worker_id"])
            if fence_state is not False:
                detail = (
                    "Worker heartbeat expired but owner fence remains active; "
                    "automatic recovery is waiting for a safe stop"
                    if fence_state is True
                    else "Worker heartbeat expired but owner fence is unverifiable; "
                    "automatic recovery is blocked"
                )
                connection.execute(
                    """UPDATE pipeline_jobs SET safe_error = ?, updated_at = ?
                         WHERE job_id = ? AND state = 'running'""",
                    (detail, now, row["job_id"]),
                )
                continue
            if bool(row["cancel_requested"]):
                cursor = connection.execute(
                    """
                    UPDATE pipeline_jobs
                       SET state = 'cancelled', updated_at = ?, finished_at = ?,
                           worker_id = NULL, lease_expires_at = NULL,
                           heartbeat_at = NULL
                     WHERE job_id = ? AND state = 'running'
                    """,
                    (now, now, row["job_id"]),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE pipeline_jobs
                       SET state = 'queued', resume_required = 1, updated_at = ?,
                           worker_id = NULL, lease_expires_at = NULL,
                           heartbeat_at = NULL,
                           safe_error = 'Stopped worker recovered; checkpoint resume required'
                     WHERE job_id = ? AND state = 'running'
                    """,
                    (now, row["job_id"]),
                )
            recovered += int(cursor.rowcount)
        return recovered

    def recover_expired(self, *, now: float | None = None) -> int:
        timestamp = time.time() if now is None else now
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            count = self._recover_expired(connection, timestamp)
            connection.commit()
            return count
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def enqueue(self, project_id: str, *, resume: bool) -> tuple[PipelineJob, bool]:
        """Create one active job per project, or return the existing one."""

        now = time.time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._recover_expired(connection, now)
            existing = connection.execute(
                """SELECT * FROM pipeline_jobs
                     WHERE project_id = ? AND state IN ('queued', 'running')
                     ORDER BY created_at, job_id LIMIT 1""",
                (project_id,),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._row(existing), False  # type: ignore[return-value]
            job_id = uuid.uuid4().hex
            connection.execute(
                """
                INSERT INTO pipeline_jobs (
                    job_id, project_id, state, requested_resume,
                    resume_required, created_at, updated_at
                ) VALUES (?, ?, 'queued', ?, 0, ?, ?)
                """,
                (job_id, project_id, int(resume), now, now),
            )
            row = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            connection.commit()
            return self._row(row), True  # type: ignore[return-value]
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def claim(
        self,
        worker_id: str,
        *,
        max_concurrency: int,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        now: float | None = None,
    ) -> PipelineJob | None:
        """Atomically claim the oldest job while enforcing a global cap."""

        if not 1 <= max_concurrency <= MAX_CONCURRENCY:
            raise ValueError("max_concurrency must be between 1 and 8")
        timestamp = time.time() if now is None else now
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._recover_expired(connection, timestamp)
            running = connection.execute(
                "SELECT COUNT(*) FROM pipeline_jobs WHERE state = 'running'"
            ).fetchone()[0]
            if int(running) >= max_concurrency:
                connection.commit()
                return None
            candidate = connection.execute(
                """SELECT job_id FROM pipeline_jobs
                     WHERE state = 'queued'
                     ORDER BY created_at, job_id LIMIT 1"""
            ).fetchone()
            if candidate is None:
                connection.commit()
                return None
            job_id = candidate["job_id"]
            connection.execute(
                """
                UPDATE pipeline_jobs
                   SET state = 'running',
                       updated_at = ?,
                       started_at = COALESCE(started_at, ?),
                       attempt_count = attempt_count + 1,
                       worker_id = ?,
                       heartbeat_at = ?,
                       lease_expires_at = ?,
                       safe_error = NULL
                 WHERE job_id = ? AND state = 'queued'
                """,
                (
                    timestamp,
                    timestamp,
                    worker_id,
                    timestamp,
                    timestamp + lease_seconds,
                    job_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            connection.commit()
            return self._row(row)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        now: float | None = None,
    ) -> bool | None:
        """Renew a worker lease and return cancellation intent if still owned."""

        timestamp = time.time() if now is None else now
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                UPDATE pipeline_jobs
                   SET heartbeat_at = ?, lease_expires_at = ?, updated_at = ?
                 WHERE job_id = ? AND state = 'running' AND worker_id = ?
                """,
                (
                    timestamp,
                    timestamp + lease_seconds,
                    timestamp,
                    job_id,
                    worker_id,
                ),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT cancel_requested FROM pipeline_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            return bool(row[0])

    def finish(
        self,
        job_id: str,
        worker_id: str,
        *,
        state: str,
        safe_error: str | None = None,
        now: float | None = None,
    ) -> PipelineJob | None:
        if state not in _TERMINAL_STATES:
            raise ValueError("finish state must be succeeded, failed, or cancelled")
        timestamp = time.time() if now is None else now
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """SELECT cancel_requested FROM pipeline_jobs
                     WHERE job_id = ? AND state = 'running' AND worker_id = ?""",
                (job_id, worker_id),
            ).fetchone()
            if current is None:
                connection.commit()
                return None
            final_state = "cancelled" if bool(current[0]) else state
            connection.execute(
                """
                UPDATE pipeline_jobs
                   SET state = ?, updated_at = ?, finished_at = ?,
                       safe_error = ?, worker_id = NULL,
                       lease_expires_at = NULL, heartbeat_at = NULL
                 WHERE job_id = ? AND state = 'running' AND worker_id = ?
                """,
                (final_state, timestamp, timestamp, safe_error, job_id, worker_id),
            )
            row = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            connection.commit()
            return self._row(row)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def cancel_project(self, project_id: str) -> PipelineJob | None:
        """Cancel before claim, or durably request cancellation while running."""

        now = time.time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._recover_expired(connection, now)
            row = connection.execute(
                """SELECT * FROM pipeline_jobs
                     WHERE project_id = ? AND state IN ('queued', 'running')
                     ORDER BY created_at, job_id LIMIT 1""",
                (project_id,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            if row["state"] == "queued":
                connection.execute(
                    """
                    UPDATE pipeline_jobs
                       SET state = 'cancelled', cancel_requested = 1,
                           updated_at = ?, finished_at = ?
                     WHERE job_id = ? AND state = 'queued'
                    """,
                    (now, now, row["job_id"]),
                )
            else:
                connection.execute(
                    """UPDATE pipeline_jobs
                          SET cancel_requested = 1, updated_at = ?
                        WHERE job_id = ? AND state = 'running'""",
                    (now, row["job_id"]),
                )
            updated = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE job_id = ?", (row["job_id"],)
            ).fetchone()
            connection.commit()
            return self._row(updated)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def abandon_unverifiable(
        self,
        project_id: str,
        job_id: str,
        *,
        now: float | None = None,
    ) -> tuple[PipelineJob | None, str]:
        """Explicitly close only an expired job whose owner cannot be proved.

        This is intentionally narrower than cancellation.  It never unlocks
        a current lease, a live owner fence, or a safely recoverable stopped
        owner.  The operator must use the exact project/job identity and the
        HTTP boundary separately requires an acknowledgement that paid work
        may still exist outside local evidence.
        """

        if not isinstance(project_id, str) or not project_id:
            raise ValueError("project_id must be a non-empty string")
        if not isinstance(job_id, str) or not _WORKER_SESSION_RE.fullmatch(job_id):
            raise ValueError("job_id must be 32 lowercase hexadecimal characters")
        timestamp = time.time() if now is None else now
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            # First take any ordinary safe recovery path.  This ensures the
            # exceptional action is never offered for a provably stopped
            # worker that should resume from its checkpoint.
            self._recover_expired(connection, timestamp)
            row = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE project_id = ? AND job_id = ?",
                (project_id, job_id),
            ).fetchone()
            if row is None:
                connection.commit()
                return None, "not_found"
            if row["state"] != "running":
                connection.commit()
                return self._row(row), "not_running"
            lease_expires_at = row["lease_expires_at"]
            if lease_expires_at is None or float(lease_expires_at) > timestamp:
                connection.commit()
                return self._row(row), "lease_active"
            fence_state = self._worker_fence_state(row["worker_id"])
            if fence_state is True:
                connection.commit()
                return self._row(row), "owner_live"
            if fence_state is False:
                connection.commit()
                return self._row(row), "owner_stopped"

            message = (
                "Operator abandoned expired job after acknowledging an "
                "unverifiable owner fence; checkpoint review is required "
                "before starting new paid work"
            )
            connection.execute(
                """
                UPDATE pipeline_jobs
                   SET state = 'cancelled', cancel_requested = 1,
                       updated_at = ?, finished_at = ?, safe_error = ?,
                       worker_id = NULL, lease_expires_at = NULL,
                       heartbeat_at = NULL
                 WHERE project_id = ? AND job_id = ? AND state = 'running'
                """,
                (timestamp, timestamp, message, project_id, job_id),
            )
            updated = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            connection.commit()
            return self._row(updated), "abandoned"
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, job_id: str) -> PipelineJob | None:
        with closing(self._connect()) as connection:
            return self._row(
                connection.execute(
                    "SELECT * FROM pipeline_jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
            )

    def project_job(self, project_id: str, *, active_only: bool = False) -> PipelineJob | None:
        where = "AND state IN ('queued', 'running')" if active_only else ""
        order = (
            "CASE WHEN state IN ('queued', 'running') THEN 0 ELSE 1 END, "
            "created_at DESC, job_id DESC"
        )
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"""SELECT * FROM pipeline_jobs WHERE project_id = ? {where}
                      ORDER BY {order} LIMIT 1""",
                (project_id,),
            ).fetchone()
            return self._row(row)

    def public_snapshot(self, job: PipelineJob | None) -> dict | None:
        if job is None:
            return None
        position: int | None = None
        if job.state == "queued":
            with closing(self._connect()) as connection:
                position = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) + 1 FROM pipeline_jobs
                         WHERE state = 'queued'
                           AND (created_at < ? OR (created_at = ? AND job_id < ?))
                        """,
                        (job.created_at, job.created_at, job.job_id),
                    ).fetchone()[0]
                )
        elif job.state == "running":
            position = 0
        operator_action: str | None = None
        if (
            job.state == "running"
            and job.lease_expires_at is not None
            and job.lease_expires_at <= time.time()
            and self._worker_fence_state(job.worker_id) is None
        ):
            operator_action = "abandon_unverifiable"
        return {
            "job_id": job.job_id,
            "project_id": job.project_id,
            "state": job.state,
            "position": position,
            "requested_resume": job.requested_resume,
            "resume_required": job.resume_required,
            "effective_resume": job.effective_resume,
            "attempt_count": job.attempt_count,
            "created_at": _utc_iso(job.created_at),
            "updated_at": _utc_iso(job.updated_at),
            "started_at": _utc_iso(job.started_at),
            "finished_at": _utc_iso(job.finished_at),
            "lease_expires_at": _utc_iso(job.lease_expires_at),
            "cancel_requested": job.cancel_requested,
            "error": job.safe_error,
            "operator_action": operator_action,
        }

    def project_snapshot(self, project_id: str, *, active_only: bool = False) -> dict | None:
        return self.public_snapshot(self.project_job(project_id, active_only=active_only))

    def close(self) -> None:
        """Compatibility hook; methods own and close every connection."""


class JobExecutionContext:
    """Cancellation bridge shared between dispatcher heartbeat and handler."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancel_requested = False
        self._lease_lost = False
        self._cancel_callback: Callable[[], None] | None = None

    @property
    def cancel_requested(self) -> bool:
        with self._lock:
            return self._cancel_requested

    @property
    def lease_lost(self) -> bool:
        with self._lock:
            return self._lease_lost

    def set_cancel_callback(self, callback: Callable[[], None]) -> None:
        call_now = False
        with self._lock:
            self._cancel_callback = callback
            call_now = self._cancel_requested
        if call_now:
            callback()

    def request_cancel(self) -> None:
        callback: Callable[[], None] | None
        with self._lock:
            self._cancel_requested = True
            callback = self._cancel_callback
        if callback is not None:
            callback()

    def mark_lease_lost(self) -> None:
        callback: Callable[[], None] | None
        with self._lock:
            self._lease_lost = True
            self._cancel_requested = True
            callback = self._cancel_callback
        if callback is not None:
            callback()


class PipelineJobDispatcher:
    """Fixed-size worker pool with one bounded lease-heartbeat thread."""

    def __init__(
        self,
        store: PipelineJobStore,
        handler: Callable[[PipelineJob, JobExecutionContext], None],
        *,
        concurrency: int | None = None,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
    ) -> None:
        self.store = store
        self.handler = handler
        self.concurrency = pipeline_queue_concurrency(concurrency)
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        self.lease_seconds = float(lease_seconds)
        self.poll_seconds = float(poll_seconds)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._started = False
        self._threads: list[threading.Thread] = []
        self._active: dict[str, tuple[str, JobExecutionContext]] = {}
        self._session_token = uuid.uuid4().hex
        self._worker_prefix = (
            f"{socket.gethostname()}:{os.getpid()}:{self._session_token}"
        )
        self._session_fence_fd: int | None = None

    def _acquire_session_fence(self) -> None:
        if self._session_fence_fd is not None:
            return
        path = self.store.worker_fence_path(self._session_token, create_dir=True)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise RuntimeError("pipeline worker fence is not a regular file")
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(descriptor, 0)
            os.write(
                descriptor,
                f"host={socket.gethostname()} pid={os.getpid()} session={self._session_token}\n".encode(),
            )
            os.fsync(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        self._session_fence_fd = descriptor

    def _release_session_fence_if_stopped(self) -> None:
        with self._lock:
            if any(thread.is_alive() for thread in self._threads):
                return
            descriptor = self._session_fence_fd
            self._session_fence_fd = None
        if descriptor is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    @property
    def started(self) -> bool:
        with self._lock:
            return self._started

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._acquire_session_fence()
            self._started = True
            for index in range(self.concurrency):
                worker = threading.Thread(
                    target=self._worker_loop,
                    args=(f"{self._worker_prefix}:{index}",),
                    name=f"pipeline-queue-worker-{index}",
                    daemon=True,
                )
                self._threads.append(worker)
            heartbeat = threading.Thread(
                target=self._heartbeat_loop,
                name="pipeline-queue-heartbeat",
                daemon=True,
            )
            self._threads.append(heartbeat)
            threads = list(self._threads)
        for thread in threads:
            thread.start()

    def wake(self) -> None:
        self._wake.set()

    def stop(self, *, wait: bool = True, timeout: float = 5.0) -> None:
        """Stop claiming; leave active leases recoverable after shutdown."""

        self._stop.set()
        self._wake.set()
        with self._lock:
            contexts = [context for _, context in self._active.values()]
            threads = list(self._threads)
        for context in contexts:
            context.request_cancel()
        if wait:
            deadline = time.monotonic() + max(0.0, timeout)
            for thread in threads:
                thread.join(max(0.0, deadline - time.monotonic()))
            self._release_session_fence_if_stopped()

    def _worker_loop(self, worker_id: str) -> None:
        while not self._stop.is_set():
            try:
                job = self.store.claim(
                    worker_id,
                    max_concurrency=self.concurrency,
                    lease_seconds=self.lease_seconds,
                )
            except Exception:
                self._stop.wait(self.poll_seconds)
                continue
            if job is None:
                self._wake.wait(self.poll_seconds)
                self._wake.clear()
                continue
            if self._stop.is_set():
                # Claimed concurrently with shutdown: leave the lease intact
                # for the next process instead of starting provider work.
                return

            context = JobExecutionContext()
            with self._lock:
                self._active[job.job_id] = (worker_id, context)
            terminal = "succeeded"
            error_summary = None
            try:
                if job.cancel_requested:
                    context.request_cancel()
                self.handler(job, context)
                if context.cancel_requested:
                    terminal = "cancelled"
            except Exception as exc:
                terminal = "cancelled" if context.cancel_requested else "failed"
                error_summary = None if terminal == "cancelled" else safe_error_summary(exc)
            finally:
                with self._lock:
                    self._active.pop(job.job_id, None)
                # A normal shutdown intentionally leaves this row running.
                # Its lease then expires and the next process claims it as a
                # checkpoint resume; shutdown must never manufacture success.
                if not self._stop.is_set():
                    self.store.finish(
                        job.job_id,
                        worker_id,
                        state=terminal,
                        safe_error=error_summary,
                    )
                self._wake.set()

    def _heartbeat_loop(self) -> None:
        interval = min(max(self.lease_seconds / 3.0, 0.1), 5.0)
        while not self._stop.wait(interval):
            with self._lock:
                active = list(self._active.items())
            for job_id, (worker_id, context) in active:
                try:
                    cancel_requested = self.store.heartbeat(
                        job_id,
                        worker_id,
                        lease_seconds=self.lease_seconds,
                    )
                except Exception:
                    # Losing durable ownership is a safety event.  Cancel the
                    # local pipeline immediately; the process fence prevents a
                    # replacement worker from starting until this process has
                    # actually stopped.
                    context.mark_lease_lost()
                    continue
                if cancel_requested is None:
                    context.mark_lease_lost()
                elif cancel_requested:
                    context.request_cancel()
