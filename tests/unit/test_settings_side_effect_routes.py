"""Revision and cache contracts for settings-mutating POST routes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def client():
    import web_server

    web_server.app.config["TESTING"] = True
    with web_server._pipelines_lock:
        web_server._running_pipelines.clear()
        web_server._project_admin_in_flight.clear()
    with web_server._cores_lock:
        web_server._running_cores.clear()
    with web_server.app.test_client() as test_client:
        yield test_client
    with web_server._pipelines_lock:
        web_server._running_pipelines.clear()
        web_server._project_admin_in_flight.clear()
    with web_server._cores_lock:
        web_server._running_cores.clear()


def _make_project(tmp_path, monkeypatch) -> str:
    from domain import project_manager

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    return project_manager.create_project("style-rules-contract")["id"]


def _load(pid):
    from domain import project_manager

    return project_manager.load_project(pid)


def test_style_rules_bumps_revision_once_and_evicts_cached_core(
    client, tmp_path, monkeypatch
):
    import web_server

    pid = _make_project(tmp_path, monkeypatch)
    generated_rules = {"visual_language": "restrained handheld"}
    generate = MagicMock(return_value=generated_rules)
    monkeypatch.setattr(web_server, "generate_style_rules", generate)
    cached_core = MagicMock()
    with web_server._cores_lock:
        web_server._running_cores[pid] = cached_core

    response = client.post(
        f"/api/projects/{pid}/style-rules",
        json={
            "expected_revision": 0,
            "mood": "quiet tension",
            "use_web_research": False,
        },
    )

    assert response.status_code == 200
    assert response.get_json() == generated_rules
    generate.assert_called_once()
    persisted = _load(pid)
    assert persisted["global_settings"]["style_rules"] == generated_rules
    assert persisted["global_settings"]["revision"] == 1
    assert pid not in web_server._running_cores
    cached_core.cost_tracker.close.assert_called_once_with()


def test_style_rules_stale_revision_skips_generation_and_preserves_cache(
    client, tmp_path, monkeypatch
):
    import web_server

    pid = _make_project(tmp_path, monkeypatch)
    patched = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "music_mood": "hopeful"}},
    )
    assert patched.status_code == 200

    generate = MagicMock(return_value={"visual_language": "must not be used"})
    monkeypatch.setattr(web_server, "generate_style_rules", generate)
    cached_core = MagicMock()
    with web_server._cores_lock:
        web_server._running_cores[pid] = cached_core

    response = client.post(
        f"/api/projects/{pid}/style-rules",
        json={"expected_revision": 0, "use_web_research": False},
    )

    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == "settings_revision_conflict"
    assert body["current_revision"] == 1
    generate.assert_not_called()
    persisted = _load(pid)
    assert persisted["global_settings"]["revision"] == 1
    assert persisted["global_settings"].get("style_rules", {}) == {}
    assert web_server._running_cores[pid] is cached_core
    cached_core.cost_tracker.close.assert_not_called()


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({}, "revision_required"),
        ({"expected_revision": False}, "invalid_revision"),
        ({"expected_revision": 0.0}, "invalid_revision"),
    ],
)
def test_style_rules_requires_integer_expected_revision(
    client, tmp_path, monkeypatch, payload, code
):
    import web_server

    pid = _make_project(tmp_path, monkeypatch)
    generate = MagicMock()
    monkeypatch.setattr(web_server, "generate_style_rules", generate)

    response = client.post(f"/api/projects/{pid}/style-rules", json=payload)

    assert response.status_code == 400
    assert response.get_json()["code"] == code
    generate.assert_not_called()


def test_style_rules_returns_busy_without_calling_generator(
    client, tmp_path, monkeypatch
):
    import web_server

    pid = _make_project(tmp_path, monkeypatch)
    generate = MagicMock()
    monkeypatch.setattr(web_server, "generate_style_rules", generate)
    with web_server._pipelines_lock:
        web_server._running_pipelines[pid] = object()

    response = client.post(
        f"/api/projects/{pid}/style-rules",
        json={"expected_revision": 0},
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "project_busy"
    generate.assert_not_called()
