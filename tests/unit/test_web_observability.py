"""Project-scoped provider analytics and central trace API contracts."""

from __future__ import annotations

import logging

from flask import Flask

import cinema.trace_store as trace_store
from cinema.trace_store import SQLiteTraceHandler, trace_context
import web_observability


class _FakeTracker:
    calls: list[tuple[str, int]] = []

    def __init__(self, *, budget_usd=None):
        self.budget_usd = budget_usd

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get_provider_usage_analytics(self, video_id="", terminal_limit=200):
        self.calls.append((video_id, terminal_limit))
        return {
            "scope_video_id": video_id,
            "terminal_limit": terminal_limit,
            "by_engine": {},
            "by_provider": {"runway": {"key": "runway"}},
        }


def _app(monkeypatch, project=None):
    app = Flask(__name__)
    app.register_blueprint(web_observability.observability_api)
    monkeypatch.setattr(
        web_observability,
        "load_existing_project_readonly",
        lambda pid: project if pid == "project-1" else None,
    )
    return app


def test_provider_analytics_threads_project_and_routing_scope(monkeypatch):
    _FakeTracker.calls = []
    monkeypatch.setattr(web_observability, "CostTracker", _FakeTracker)
    app = _app(monkeypatch, {"id": "project-1", "global_settings": {"budget_limit_usd": 10}})

    with app.test_client() as client:
        project = client.get("/api/projects/project-1/provider-analytics?limit=25")
        routing = client.get("/api/projects/project-1/provider-analytics?scope=routing")

    assert project.status_code == 200
    assert len(project.headers["X-Trace-ID"]) == 32
    assert project.get_json()["scope"] == "project"
    assert routing.status_code == 200
    assert routing.get_json()["scope"] == "routing"
    assert _FakeTracker.calls == [("project-1", 25), ("", 200)]


def test_observability_rejects_bad_scope_bounds_and_missing_projects(monkeypatch):
    monkeypatch.setattr(web_observability, "CostTracker", _FakeTracker)
    app = _app(monkeypatch, {"id": "project-1", "global_settings": {}})

    with app.test_client() as client:
        assert client.get("/api/projects/project-1/provider-analytics?scope=all").status_code == 400
        assert client.get("/api/projects/project-1/provider-analytics?limit=0").status_code == 400
        assert client.get("/api/projects/project-1/traces?level=DEBUG").status_code == 400
        assert client.get("/api/projects/project-1/traces?before=nope").status_code == 400
        assert client.get("/api/projects/missing/traces").status_code == 404
        assert client.get("/api/projects/../traces").status_code == 400


def test_trace_api_is_searchable_and_project_scoped(monkeypatch, tmp_path):
    db = str(tmp_path / "telemetry.db")
    # Settings are intentionally loaded once at process startup.  Point the
    # trace-store accessor at this test database instead of mutating the
    # environment after the settings singleton has already been imported.
    monkeypatch.setattr(trace_store, "trace_db_path", lambda: db)
    app = _app(monkeypatch, {"id": "project-1", "global_settings": {}})
    handler = SQLiteTraceHandler(db)
    logger = logging.getLogger("web-observability-test")
    previous_handlers = logger.handlers[:]
    previous_propagate = logger.propagate
    previous_level = logger.level
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        with trace_context(trace_id="job-123", project_id="project-1"):
            logger.warning("Runway recovery required", extra={"engine": "RUNWAY_GEN4"})
        with trace_context(trace_id="private", project_id="project-2"):
            logger.error("Other project secret")

        with app.test_client() as client:
            response = client.get(
                "/api/projects/project-1/traces?q=recovery&level=WARNING&trace_id=job-123"
            )
    finally:
        handler.close()
        logger.handlers = previous_handlers
        logger.propagate = previous_propagate
        logger.setLevel(previous_level)

    assert response.status_code == 200
    events = response.get_json()["events"]
    assert len(events) == 1
    assert events[0]["project_id"] == "project-1"
    assert events[0]["message"] == "Runway recovery required"
    assert "Other project secret" not in str(response.get_json())
