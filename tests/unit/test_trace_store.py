"""Durable central trace index and safe project-scoped search."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing

from cinema.trace_store import SQLiteTraceHandler, search_traces, trace_context


def _logger_with(handler: SQLiteTraceHandler) -> logging.Logger:
    logger = logging.getLogger(f"trace-test-{id(handler)}")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger


def test_trace_handler_correlates_and_searches_project_events(tmp_path):
    db = str(tmp_path / "traces.db")
    handler = SQLiteTraceHandler(db)
    logger = _logger_with(handler)
    try:
        with trace_context(trace_id="trace-123", project_id="project-1"):
            logger.info(
                "Runway task entered recovery",
                extra={
                    "engine": "RUNWAY_GEN4",
                    "shot_id": "shot-1",
                    "attempt_id": "attempt-1",
                    "provider_status": "RUNNING",
                    "api_key": "must-never-be-indexed",
                },
            )

        result = search_traces("project-1", query="recovery", db_path=db)
    finally:
        handler.close()

    assert result["has_more"] is False
    event = result["events"][0]
    assert event["trace_id"] == "trace-123"
    assert event["project_id"] == "project-1"
    assert event["engine"] == "RUNWAY_GEN4"
    assert event["shot_id"] == "shot-1"
    assert event["fields"]["attempt_id"] == "attempt-1"
    assert "api_key" not in event["fields"]
    assert "must-never-be-indexed" not in str(event)


def test_search_is_project_scoped_and_supports_bounded_paging(tmp_path):
    db = str(tmp_path / "traces.db")
    handler = SQLiteTraceHandler(db)
    logger = _logger_with(handler)
    try:
        for index in range(4):
            with trace_context(trace_id=f"trace-{index}", project_id="project-1"):
                logger.warning("provider warning %s", index, extra={"engine": "LTX"})
        with trace_context(trace_id="other", project_id="project-2"):
            logger.error("must stay private to project 2")

        first = search_traces("project-1", level="warning", limit=2, db_path=db)
        second = search_traces(
            "project-1",
            level="WARNING",
            before_event_id=first["next_before_event_id"],
            limit=2,
            db_path=db,
        )
    finally:
        handler.close()

    assert len(first["events"]) == 2
    assert first["has_more"] is True
    assert len(second["events"]) == 2
    assert all(event["project_id"] == "project-1" for event in first["events"] + second["events"])


def test_bound_project_context_cannot_be_overridden_by_record_extras(tmp_path):
    db = str(tmp_path / "traces.db")
    handler = SQLiteTraceHandler(db)
    logger = _logger_with(handler)
    try:
        with trace_context(project_id="outer-project"):
            logger.info("inner", extra={"video_id": "actual-project"})
        outer = search_traces("outer-project", db_path=db)
        attempted_override = search_traces("actual-project", db_path=db)
    finally:
        handler.close()

    assert len(outer["events"]) == 1
    assert attempted_override["events"] == []


def test_long_running_handler_periodically_enforces_event_bound(tmp_path):
    db = str(tmp_path / "traces.db")
    handler = SQLiteTraceHandler(db, max_events=1000)
    logger = _logger_with(handler)
    try:
        with trace_context(project_id="project-1"):
            for index in range(1500):
                logger.info("bounded trace %d", index)
    finally:
        handler.close()

    # sqlite3.Connection's context manager commits/rolls back but does not
    # close the descriptor; ``closing`` makes this resource assertion exact.
    with closing(sqlite3.connect(db)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM trace_events").fetchone()[0]
        oldest = connection.execute("SELECT MIN(event_id) FROM trace_events").fetchone()[0]
    assert count == 1000
    assert oldest == 501


def test_trace_storage_and_search_redact_credentials_in_messages_and_fields(tmp_path):
    db = str(tmp_path / "traces.db")
    handler = SQLiteTraceHandler(db)
    logger = _logger_with(handler)
    try:
        with trace_context(project_id="project-1"):
            logger.error(
                "request failed Authorization: Bearer super-secret-token "
                "https://cdn.example/file?Signature=signed-url-secret&Expires=123 "
                'JSON={"openai_api_key":"sk-json-secret","client_secret":"oauth-secret"} '
                "query=https://api.example.test?a=1&access_token=url-secret&ok=2",
                extra={
                    "detail": {
                        "api_key": "nested-secret",
                        "provider_access_token": "nested-access-secret",
                        "oauth_client_secret": "nested-client-secret",
                        "reason": "token=also-secret provider refused",
                    }
                },
            )
        result = search_traces("project-1", db_path=db)
    finally:
        handler.close()

    event = result["events"][0]
    rendered = str(event)
    assert "super-secret-token" not in rendered
    assert "nested-secret" not in rendered
    assert "also-secret" not in rendered
    assert "signed-url-secret" not in rendered
    assert "sk-json-secret" not in rendered
    assert "oauth-secret" not in rendered
    assert "url-secret" not in rendered
    assert "nested-access-secret" not in rendered
    assert "nested-client-secret" not in rendered
    assert "REDACTED" in rendered
    with closing(sqlite3.connect(db)) as connection:
        raw = " ".join(
            str(value)
            for value in connection.execute(
                "SELECT message, public_json FROM trace_events"
            ).fetchone()
        )
    assert "super-secret-token" not in raw
    assert "nested-secret" not in raw
    assert "also-secret" not in raw
    assert "signed-url-secret" not in raw
    assert "sk-json-secret" not in raw
    assert "oauth-secret" not in raw
    assert "url-secret" not in raw
    assert "nested-access-secret" not in raw
    assert "nested-client-secret" not in raw
