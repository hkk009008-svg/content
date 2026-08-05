"""HTTP contract tests for durable spend and paid-attempt control."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import cost_tracker
import performance.runway_tasks
import pytest

import web_server


class _FakeTracker:
    def __init__(self, *, budget_usd=None):
        self.budget_usd = budget_usd
        self.closed = False
        self.attempt = {
            "attempt_id": "attempt-1",
            "provider": "runway",
            "engine": "RUNWAY_GEN4",
            "operation": "video_generation",
            "shot_id": "shot-1",
            "video_id": "project-1",
            "state": "accepted_unknown",
            "reserved_cost_usd": 0.75,
            "reconciled_cost_usd": 0.0,
            "billed": None,
            "provider_job_id": "task-123",
            "provider_status": "",
            "failure_code": "",
            "detail": "Submission outcome is unknown",
            "created_at": "2026-08-05T00:00:00+00:00",
            "updated_at": "2026-08-05T00:00:01+00:00",
            "active": True,
            "request_fingerprint": "must-not-leave-the-server",
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self):
        self.closed = True

    def get_video_cost(self, video_id):
        assert video_id == "project-1"
        return {"total_usd": 1.25}

    def get_paid_attempts_snapshot(self, video_id):
        assert video_id == "project-1"
        return {
            "attempts": [self.attempt],
            "active_reservation_usd": 0.75,
            "accepted_unknown_count": 1,
            "billed_failure_count": 0,
            "blocked_attempt_count": 0,
        }

    def get_paid_attempt(self, attempt_id):
        return self.attempt if attempt_id == self.attempt["attempt_id"] else None


@pytest.fixture(autouse=True)
def _clear_cached_cores():
    with web_server._cores_lock:
        previous = dict(web_server._running_cores)
        web_server._running_cores.clear()
    yield
    with web_server._cores_lock:
        web_server._running_cores.clear()
        web_server._running_cores.update(previous)


@pytest.fixture
def project():
    return {
        "id": "project-1",
        "global_settings": {"budget_limit_usd": 5.0},
    }


def test_cost_live_returns_authoritative_exposure_and_closes_owned_tracker(
    monkeypatch, project
):
    tracker = _FakeTracker()
    monkeypatch.setattr(web_server, "load_existing_project_readonly", lambda pid: project)
    monkeypatch.setattr(cost_tracker, "CostTracker", lambda **_kwargs: tracker)

    with web_server.app.test_client() as client:
        response = client.get("/api/projects/project-1/cost-live")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["charged_usd"] == 1.25
    assert payload["active_reservation_usd"] == 0.75
    assert payload["committed_usd"] == 2.0
    assert payload["budget_status"] == "active"
    assert payload["remaining_usd"] == 3.0
    assert payload["attempts"][0]["attempt_id"] == "attempt-1"
    assert "request_fingerprint" not in payload["attempts"][0]
    assert tracker.closed is True


def test_cost_live_does_not_create_storage_for_unknown_project(monkeypatch):
    constructor = Mock(side_effect=AssertionError("tracker must not be constructed"))
    monkeypatch.setattr(web_server, "load_existing_project_readonly", lambda pid: None)
    monkeypatch.setattr(cost_tracker, "CostTracker", constructor)

    with web_server.app.test_client() as client:
        response = client.get("/api/projects/missing/cost-live")

    assert response.status_code == 404
    constructor.assert_not_called()


def test_cost_live_reuses_cached_tracker_without_closing_it(monkeypatch, project):
    tracker = _FakeTracker()
    monkeypatch.setattr(web_server, "load_existing_project_readonly", lambda pid: project)
    with web_server._cores_lock:
        web_server._running_cores["project-1"] = SimpleNamespace(cost_tracker=tracker)

    with web_server.app.test_client() as client:
        response = client.get("/api/projects/project-1/cost-live")

    assert response.status_code == 200
    assert tracker.closed is False


def test_shutdown_closes_and_evicts_cached_trackers():
    first = _FakeTracker()
    second = _FakeTracker()
    with web_server._cores_lock:
        web_server._running_cores.update({
            "project-1": SimpleNamespace(cost_tracker=first),
            "project-2": SimpleNamespace(cost_tracker=second),
        })

    web_server._close_all_cached_cores()

    assert first.closed is True
    assert second.closed is True
    assert web_server._running_cores == {}


def test_cancel_is_project_scoped_and_returns_updated_authority(
    monkeypatch, project
):
    tracker = _FakeTracker()
    cancel = Mock(side_effect=lambda owned, attempt_id: {
        **owned.get_paid_attempt(attempt_id),
        "state": "cancel_requested",
    })
    monkeypatch.setattr(web_server, "load_existing_project_readonly", lambda pid: project)
    monkeypatch.setattr(cost_tracker, "CostTracker", lambda **_kwargs: tracker)
    monkeypatch.setattr(performance.runway_tasks, "cancel_runway_attempt", cancel)

    with web_server.app.test_client() as client:
        response = client.post(
            "/api/projects/project-1/paid-attempts/attempt-1/cancel",
            json={},
        )

    assert response.status_code == 202
    assert response.get_json()["cancellation"]["state"] == "cancel_requested"
    cancel.assert_called_once_with(tracker, "attempt-1")
    assert tracker.closed is True


def test_cancel_hides_cross_project_attempt(monkeypatch, project):
    tracker = _FakeTracker()
    tracker.attempt["video_id"] = "different-project"
    cancel = Mock()
    monkeypatch.setattr(web_server, "load_existing_project_readonly", lambda pid: project)
    monkeypatch.setattr(cost_tracker, "CostTracker", lambda **_kwargs: tracker)
    monkeypatch.setattr(performance.runway_tasks, "cancel_runway_attempt", cancel)

    with web_server.app.test_client() as client:
        response = client.post(
            "/api/projects/project-1/paid-attempts/attempt-1/cancel",
            json={},
        )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Paid attempt not found"}
    cancel.assert_not_called()
    assert tracker.closed is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, ("unlimited", None)),
        ("5.5", ("active", 5.5)),
        (float("nan"), ("invalid", None)),
        (-1, ("invalid", None)),
        (True, ("invalid", None)),
        ("typo", ("invalid", None)),
    ],
)
def test_budget_authority_is_fail_closed(raw, expected):
    assert web_server._project_budget_authority(
        {"global_settings": {"budget_limit_usd": raw}}
    ) == expected
