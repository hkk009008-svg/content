"""Project-scoped observability API shared by the local operator UI.

The routes in this blueprint expose only aggregate provider evidence and the
allowlisted trace projection. They never return provider request payloads,
credentials, exception tracebacks, or records belonging to another project.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from flask import Blueprint, g, jsonify, request

from cost_tracker import CostTracker
from cinema.trace_store import MAX_SEARCH_LIMIT, search_traces, trace_context
from project_manager import is_safe_project_id, load_existing_project_readonly


logger = logging.getLogger(__name__)
observability_api = Blueprint("observability_api", __name__)

_TRACE_LEVELS = frozenset({"INFO", "WARNING", "ERROR", "CRITICAL"})


@observability_api.before_app_request
def _bind_request_trace():
    """Give each API request a server-created correlation ID.

    Client-supplied trace identifiers are deliberately ignored. This prevents
    one caller from forging correlation with a different request or queued job.
    """
    if not request.path.startswith("/api/"):
        return None
    pid = (request.view_args or {}).get("pid")
    project_id = pid if isinstance(pid, str) and is_safe_project_id(pid) else ""
    manager = trace_context(project_id=project_id)
    g._cinema_trace_context = manager
    g.cinema_trace_id = manager.__enter__()
    return None


@observability_api.after_app_request
def _finish_request_trace(response):
    trace_id = getattr(g, "cinema_trace_id", "")
    if trace_id:
        response.headers["X-Trace-ID"] = trace_id
        logger.info(
            "HTTP request completed",
            extra={"status": response.status_code, "code": request.method.lower()},
        )
    return response


@observability_api.teardown_app_request
def _release_request_trace(_error):
    manager = getattr(g, "_cinema_trace_context", None)
    if manager is not None:
        manager.__exit__(None, None, None)


def _project_or_error(pid: str):
    if not is_safe_project_id(pid):
        return None, (jsonify({"error": "Invalid project_id"}), 400)
    project = load_existing_project_readonly(pid)
    if not project:
        return None, (jsonify({"error": "Project not found"}), 404)
    return project, None


def _bounded_query_int(
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> tuple[int | None, tuple | None]:
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


def _project_budget(project: Mapping[str, object]):
    settings = project.get("global_settings")
    return settings.get("budget_limit_usd") if isinstance(settings, Mapping) else None


@observability_api.get("/api/projects/<pid>/provider-analytics")
def api_provider_analytics(pid: str):
    """Return durable provider metrics for this project or AUTO routing history."""
    project, error = _project_or_error(pid)
    if error is not None:
        return error

    scope = request.args.get("scope", "project")
    if scope not in {"project", "routing"}:
        return jsonify({"error": "scope must be project or routing"}), 400
    terminal_limit, error = _bounded_query_int(
        "limit", default=200, minimum=1, maximum=1000
    )
    if error is not None:
        return error

    try:
        with CostTracker(budget_usd=_project_budget(project)) as tracker:
            snapshot = tracker.get_provider_usage_analytics(
                video_id=pid if scope == "project" else "",
                terminal_limit=terminal_limit,
            )
        snapshot["scope"] = scope
        return jsonify(snapshot)
    except Exception:
        logger.exception("provider analytics query failed", extra={"pid": pid})
        return jsonify({"error": "Provider analytics query failed"}), 500


@observability_api.get("/api/projects/<pid>/traces")
def api_project_traces(pid: str):
    """Search one project's bounded, allowlisted central trace index."""
    _project, error = _project_or_error(pid)
    if error is not None:
        return error

    query = request.args.get("q", "")
    trace_id = request.args.get("trace_id", "")
    level = request.args.get("level", "").upper()
    if len(query) > 200:
        return jsonify({"error": "q must be at most 200 characters"}), 400
    if len(trace_id) > 128:
        return jsonify({"error": "trace_id must be at most 128 characters"}), 400
    if level and level not in _TRACE_LEVELS:
        return jsonify({"error": "level must be INFO, WARNING, ERROR, or CRITICAL"}), 400

    limit, error = _bounded_query_int(
        "limit", default=50, minimum=1, maximum=MAX_SEARCH_LIMIT
    )
    if error is not None:
        return error
    before: int | None = None
    if request.args.get("before") not in {None, ""}:
        before, error = _bounded_query_int(
            "before", default=0, minimum=1, maximum=2**63 - 1
        )
        if error is not None:
            return error

    try:
        return jsonify(search_traces(
            pid,
            query=query,
            level=level,
            trace_id=trace_id,
            before_event_id=before,
            limit=limit,
        ))
    except Exception:
        logger.exception("trace search failed", extra={"pid": pid})
        return jsonify({"error": "Trace search failed"}), 500
