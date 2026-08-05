"""Durable, searchable structured traces for the local production controller.

Stdout remains the deployment log stream.  This module adds a bounded SQLite
index so operators can search project/shot/provider events from the UI without
granting filesystem access or exposing raw exception payloads.
"""

from __future__ import annotations

import atexit
import json
import logging
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Mapping

from config.settings import settings


TRACE_SCHEMA_VERSION = 1
DEFAULT_TRACE_DB_PATH = "data/telemetry.db"
DEFAULT_RETENTION_DAYS = 30
DEFAULT_MAX_EVENTS = 50_000
MAX_SEARCH_LIMIT = 200
PRUNE_EVERY_EVENTS = 500

_trace_id: ContextVar[str] = ContextVar("cinema_trace_id", default="")
_project_id: ContextVar[str] = ContextVar("cinema_project_id", default="")
_handlers: set["SQLiteTraceHandler"] = set()
_handlers_lock = threading.Lock()

_PUBLIC_EXTRA_FIELDS = frozenset({
    "attempt_id", "code", "cost_usd", "detail", "engine", "latency_ms",
    "percent", "provider", "provider_status", "scene_id", "shot_id",
    "stage", "state", "status", "take_id", "video_id",
})
_SECRET_KEY_RE = re.compile(
    r"(?i)(?:^|_)(?:authorization|proxy_authorization|api_?key|access_?key|"
    r"access_?token|refresh_?token|id_?token|client_?secret|private_?key|"
    r"token|secret|password|credentials?)$"
)
_LABELED_SECRET_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])((?:[\"']?(?:[A-Za-z0-9]+[-_])*"
    r"(?:api[-_]?key|access[-_]?key|access[-_]?token|refresh[-_]?token|"
    r"id[-_]?token|client[-_]?secret|private[-_]?key)|[\"']?"
    r"(?:authorization|proxy[-_ ]authorization|token|secret|password|"
    r"credentials?))[\"']?\s*[:=]\s*)"
    r"(?:bearer\s+)?(?:\"[^\"]*\"|'[^']*'|[^\s,;&#}\]]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SIGNED_QUERY_RE = re.compile(
    r"(?i)([?&](?:x-amz-|x-goog-)?(?:signature|credential|security-token|"
    r"access-key-id|googleaccessid|key-pair-id)=)[^&#\s]+"
)


def _redact_text(value: object, *, limit: int = 4_096) -> str:
    """Bound and redact credential-shaped values before durable storage/UI."""

    text = str(value)
    text = _LABELED_SECRET_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _SIGNED_QUERY_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    return text[:limit]


def _sanitize_public_value(value: object, *, depth: int = 0) -> object:
    """Return bounded JSON-safe public data with nested secrets removed."""

    if depth >= 5:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return _redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for index, (raw_key, child) in enumerate(value.items()):
            if index >= 100:
                break
            key = str(raw_key)[:128]
            normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            if _SECRET_KEY_RE.search(normalized):
                continue
            result[key] = _sanitize_public_value(child, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize_public_value(child, depth=depth + 1) for child in value[:100]]
    return _redact_text(value)


def new_trace_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def trace_context(*, trace_id: str = "", project_id: str = "") -> Iterator[str]:
    """Bind correlation fields for logs emitted in the current execution context."""
    resolved_trace_id = trace_id or new_trace_id()
    trace_token: Token[str] = _trace_id.set(resolved_trace_id)
    project_token: Token[str] = _project_id.set(str(project_id or ""))
    try:
        yield resolved_trace_id
    finally:
        _project_id.reset(project_token)
        _trace_id.reset(trace_token)


def current_trace_id() -> str:
    return _trace_id.get()


def current_project_id() -> str:
    return _project_id.get()


def _bounded_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return min(maximum, max(minimum, parsed))


def trace_db_path() -> str:
    value = settings.cinema_trace_db_path.strip()
    return value or DEFAULT_TRACE_DB_PATH


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if db_path != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    if db_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trace_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_version INTEGER NOT NULL,
            ts TEXT NOT NULL,
            level TEXT NOT NULL,
            logger TEXT NOT NULL,
            message TEXT NOT NULL,
            trace_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            scene_id TEXT NOT NULL,
            shot_id TEXT NOT NULL,
            engine TEXT NOT NULL,
            public_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trace_project_event "
        "ON trace_events(project_id, event_id DESC)"
    )
    conn.commit()
    return conn


def _project_from_record(record: logging.LogRecord) -> str:
    # A route/job trace context is the isolation authority.  Record extras are
    # often provider metadata and must not move an event into another project's
    # searchable partition.
    bound = current_project_id()
    if bound:
        return bound[:128]
    for field in ("project_id", "pid", "video_id"):
        value = getattr(record, field, None)
        if isinstance(value, str) and value:
            return value[:128]
    return ""


def _public_record_fields(record: logging.LogRecord) -> dict[str, object]:
    public: dict[str, object] = {}
    for field in _PUBLIC_EXTRA_FIELDS:
        if not hasattr(record, field):
            continue
        value = _sanitize_public_value(getattr(record, field))
        try:
            encoded = json.dumps(value, default=str)
        except (TypeError, ValueError):
            continue
        if len(encoded) <= 4_096:
            public[field] = value
    return public


class SQLiteTraceHandler(logging.Handler):
    """Synchronous bounded trace index; logging failures never reach callers."""

    def __init__(
        self,
        db_path: str | None = None,
        *,
        level: int = logging.INFO,
        retention_days: int | None = None,
        max_events: int | None = None,
    ):
        super().__init__(level=level)
        self.db_path = db_path or trace_db_path()
        self.retention_days = _bounded_int(
            settings.cinema_trace_retention_days
            if retention_days is None
            else retention_days,
            DEFAULT_RETENTION_DAYS,
            minimum=1,
            maximum=365,
        )
        self.max_events = _bounded_int(
            settings.cinema_trace_max_events if max_events is None else max_events,
            DEFAULT_MAX_EVENTS,
            minimum=1_000,
            maximum=1_000_000,
        )
        self._lock = threading.RLock()
        self._closed = False
        self._conn = _connect(self.db_path)
        self._prune()
        self._events_since_prune = 0
        with _handlers_lock:
            _handlers.add(self)

    def _prune(self) -> None:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        ).isoformat()
        with self._lock:
            self._conn.execute("DELETE FROM trace_events WHERE ts < ?", (cutoff,))
            count = int(self._conn.execute("SELECT COUNT(*) FROM trace_events").fetchone()[0])
            excess = count - self.max_events
            if excess > 0:
                self._conn.execute(
                    "DELETE FROM trace_events WHERE event_id IN ("
                    "SELECT event_id FROM trace_events ORDER BY event_id ASC LIMIT ?)",
                    (excess,),
                )
            self._conn.commit()

    def emit(self, record: logging.LogRecord) -> None:
        if self._closed:
            return
        try:
            public = _public_record_fields(record)
            project_id = _project_from_record(record)
            trace_id = str(getattr(record, "trace_id", "") or current_trace_id())[:128]
            ts = datetime.fromtimestamp(record.created, timezone.utc).isoformat()
            with self._lock:
                self._conn.execute(
                    """
                    INSERT INTO trace_events (
                        schema_version, ts, level, logger, message, trace_id,
                        project_id, scene_id, shot_id, engine, public_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        TRACE_SCHEMA_VERSION,
                        ts,
                        record.levelname[:16],
                        record.name[:256],
                        _redact_text(record.getMessage()),
                        trace_id,
                        project_id,
                        str(public.get("scene_id") or "")[:128],
                        str(public.get("shot_id") or "")[:128],
                        str(public.get("engine") or "")[:128],
                        json.dumps(public, ensure_ascii=False, default=str),
                    ),
                )
                self._conn.commit()
                self._events_since_prune += 1
                if self._events_since_prune >= PRUNE_EVERY_EVENTS:
                    self._prune()
                    self._events_since_prune = 0
        except Exception:
            # Logging must never change production control flow. Avoid
            # handleError(), which could recurse through this handler.
            return

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._conn.close()
        with _handlers_lock:
            _handlers.discard(self)
        super().close()


def close_trace_handlers() -> None:
    with _handlers_lock:
        handlers = list(_handlers)
    for handler in handlers:
        handler.close()


atexit.register(close_trace_handlers)


def search_traces(
    project_id: str,
    *,
    query: str = "",
    level: str = "",
    trace_id: str = "",
    before_event_id: int | None = None,
    limit: int = 50,
    db_path: str | None = None,
) -> dict[str, object]:
    """Return a bounded project-scoped page of UI-safe trace events."""
    limit = max(1, min(MAX_SEARCH_LIMIT, int(limit)))
    clauses = ["project_id = ?"]
    args: list[object] = [project_id]
    if query:
        clauses.append("(message LIKE ? OR public_json LIKE ?)")
        pattern = f"%{query[:200]}%"
        args.extend((pattern, pattern))
    if level:
        clauses.append("level = ?")
        args.append(level[:16].upper())
    if trace_id:
        clauses.append("trace_id = ?")
        args.append(trace_id[:128])
    if before_event_id is not None:
        clauses.append("event_id < ?")
        args.append(int(before_event_id))
    args.append(limit + 1)

    conn = _connect(db_path or trace_db_path())
    try:
        rows = conn.execute(
            "SELECT * FROM trace_events WHERE " + " AND ".join(clauses)
            + " ORDER BY event_id DESC LIMIT ?",
            tuple(args),
        ).fetchall()
    finally:
        conn.close()
    has_more = len(rows) > limit
    rows = rows[:limit]
    events = []
    for row in rows:
        try:
            fields = json.loads(row["public_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            fields = {}
        events.append({
            "event_id": row["event_id"],
            "ts": row["ts"],
            "level": row["level"],
            "logger": row["logger"],
            "message": _redact_text(row["message"]),
            "trace_id": row["trace_id"],
            "project_id": row["project_id"],
            "scene_id": row["scene_id"],
            "shot_id": row["shot_id"],
            "engine": row["engine"],
            "fields": (
                _sanitize_public_value(fields) if isinstance(fields, Mapping) else {}
            ),
        })
    return {
        "events": events,
        "has_more": has_more,
        "next_before_event_id": events[-1]["event_id"] if has_more and events else None,
    }
