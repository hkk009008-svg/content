"""
tests/unit/test_api_state_and_destructive.py — Regression tests for destructive
and state-machine endpoints in web_server.py (Tier 1 Batch B).
"""

from unittest.mock import MagicMock, patch

import pytest
from flask import json

from web_server import (
    app,
    _cores_lock,
    _pipelines_lock,
    _project_admin_in_flight,
    _progress_queues,
    _running_cores,
    _running_pipelines,
)


@pytest.fixture(autouse=True)
def clean_pipeline_state():
    """Clear project runtime registries before and after each test."""
    with _pipelines_lock:
        _running_pipelines.clear()
        _progress_queues.clear()
        _project_admin_in_flight.clear()
    with _cores_lock:
        _running_cores.clear()
    yield
    with _pipelines_lock:
        _running_pipelines.clear()
        _progress_queues.clear()
        _project_admin_in_flight.clear()
    with _cores_lock:
        _running_cores.clear()


@pytest.fixture()
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# DELETE /api/projects/<pid>
# ---------------------------------------------------------------------------

@patch("web_server.delete_project")
def test_api_delete_project_busy(mock_delete, client):
    """If a pipeline is running, delete is rejected."""
    pid = "test_pid"
    with _pipelines_lock:
        _running_pipelines[pid] = MagicMock()
    
    resp = client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 409
    assert resp.json.get("error") == f"Project '{pid}' is busy with an active generation run. Retry shortly."
    mock_delete.assert_not_called()


@patch("web_server.delete_project")
def test_api_delete_project_success(mock_delete, client):
    """A successful delete also evicts and closes cached runtime state."""
    pid = "test_pid"
    mock_delete.return_value = True
    cached_core = MagicMock()
    cached_bus = MagicMock()
    with _cores_lock:
        _running_cores[pid] = cached_core
    with _pipelines_lock:
        _progress_queues[pid] = cached_bus
    
    resp = client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json.get("deleted") is True
    mock_delete.assert_called_once_with(pid, timeout=pytest.approx(5.0, abs=10.0))  # HTTP_PROJECT_TIMEOUT is usually 5 or 15
    assert pid not in _running_cores
    assert pid not in _progress_queues
    cached_core.cost_tracker.close.assert_called_once_with()
    cached_bus.close.assert_called_once_with()


@patch("web_server.delete_project")
def test_api_delete_project_not_found(mock_delete, client):
    """If project does not exist, delete returns 404."""
    pid = "test_pid"
    mock_delete.return_value = False
    
    resp = client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 404
    assert resp.json.get("error") == "Project not found"
    mock_delete.assert_called_once()


@patch("web_server.load_project", return_value={"id": "test_pid"})
@patch("web_server.delete_project")
def test_api_delete_project_reservation_blocks_generation_start(
    mock_delete,
    _mock_load,
    client,
):
    """Generation cannot reserve a slot while deletion owns admin state."""
    nested_status = {}

    def delete_while_probing(_pid, *, timeout):
        with app.test_client() as other_client:
            nested = other_client.post("/api/projects/test_pid/generate")
        nested_status.update(status=nested.status_code, body=nested.get_json())
        return True

    mock_delete.side_effect = delete_while_probing

    response = client.delete("/api/projects/test_pid")

    assert response.status_code == 200
    assert nested_status["status"] == 409
    assert nested_status["body"]["code"] == "project_busy"
    assert "test_pid" not in _running_pipelines
    assert "test_pid" not in _project_admin_in_flight


@patch("web_server.threading.Thread")
@patch("web_server.delete_project")
@patch("web_server.load_project")
def test_api_generation_reserves_before_project_load_blocks_delete(
    mock_load,
    mock_delete,
    mock_thread,
    client,
):
    """A delete interleaving inside load_project cannot win then start stale."""
    nested_status = {}

    def load_while_probing_delete(_pid):
        with app.test_client() as other_client:
            nested = other_client.delete("/api/projects/test_pid")
        nested_status.update(status=nested.status_code, body=nested.get_json())
        return {"id": "test_pid"}

    mock_load.side_effect = load_while_probing_delete

    response = client.post("/api/projects/test_pid/generate")

    assert response.status_code == 200
    assert nested_status["status"] == 409
    assert nested_status["body"]["code"] == "project_busy"
    mock_delete.assert_not_called()
    assert _running_pipelines["test_pid"] is not None
    mock_thread.return_value.start.assert_called_once_with()


# ---------------------------------------------------------------------------
# POST /api/projects/<pid>/pause and /resume
# ---------------------------------------------------------------------------

def test_api_pause_success(client):
    """Pause works when a pipeline is running."""
    pid = "test_pid"
    fake_pipeline = MagicMock()
    with _pipelines_lock:
        _running_pipelines[pid] = fake_pipeline
        
    resp = client.post(f"/api/projects/{pid}/pause")
    assert resp.status_code == 200
    assert resp.json.get("paused") is True
    fake_pipeline.pause.assert_called_once()


def test_api_pause_not_found(client):
    """Pause returns 404 if no pipeline is running."""
    pid = "test_pid"
    resp = client.post(f"/api/projects/{pid}/pause")
    assert resp.status_code == 404
    assert resp.json.get("error") == "No generation in progress"


def test_api_resume_success(client):
    """Resume works when a pipeline is running."""
    pid = "test_pid"
    fake_pipeline = MagicMock()
    with _pipelines_lock:
        _running_pipelines[pid] = fake_pipeline
        
    resp = client.post(f"/api/projects/{pid}/resume")
    assert resp.status_code == 200
    assert resp.json.get("resumed") is True
    fake_pipeline.resume.assert_called_once()


def test_api_resume_not_found(client):
    """Resume returns 404 if no pipeline is running."""
    pid = "test_pid"
    resp = client.post(f"/api/projects/{pid}/resume")
    assert resp.status_code == 404
    assert resp.json.get("error") == "No generation in progress"


# ---------------------------------------------------------------------------
# POST /api/projects/<pid>/shots/<shot_id>/restart
# ---------------------------------------------------------------------------

@patch("web_server.mutate_project")
def test_api_restart_shot_project_not_found(mock_mutate, client):
    """If project doesn't exist, restart returns 404."""
    pid = "test_pid"
    shot_id = "s1"
    mock_mutate.return_value = None
    
    resp = client.post(f"/api/projects/{pid}/shots/{shot_id}/restart")
    assert resp.status_code == 404
    assert resp.json.get("error") == "Project not found"


@patch("web_server.mutate_project")
def test_api_restart_shot_shot_not_found(mock_mutate, client):
    """If shot doesn't exist, restart returns 404."""
    pid = "test_pid"
    shot_id = "s1"
    mock_mutate.return_value = False
    
    resp = client.post(f"/api/projects/{pid}/shots/{shot_id}/restart")
    assert resp.status_code == 404
    assert resp.json.get("error") == "Shot not found"


@patch("web_server.mutate_project")
def test_api_restart_shot_with_running_pipeline(mock_mutate, client):
    """If pipeline is running, it delegates restart_shot to it."""
    pid = "test_pid"
    shot_id = "s1"
    scene_id = "scene1"
    mock_mutate.return_value = scene_id
    
    fake_pipeline = MagicMock()
    fake_pipeline.restart_shot.return_value = {"success": True}
    with _pipelines_lock:
        _running_pipelines[pid] = fake_pipeline
        
    resp = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/restart",
        json={"positive_prompt": "new", "negative_prompt": "bad"}
    )
    
    assert resp.status_code == 200
    assert resp.json.get("success") is True
    fake_pipeline.restart_shot.assert_called_once_with(scene_id, shot_id, "new", "bad")


@patch("web_server._get_or_build_core")
@patch("web_server.CinemaPipeline")
@patch("web_server.mutate_project")
def test_api_restart_shot_without_running_pipeline(mock_mutate, mock_pipeline_class, mock_get_core, client):
    """If no pipeline is running, it creates a temporary one to delegate."""
    pid = "test_pid"
    shot_id = "s1"
    scene_id = "scene1"
    mock_mutate.return_value = scene_id
    
    fake_pipeline_instance = MagicMock()
    fake_pipeline_instance.restart_shot.return_value = {"success": True, "restarted": True}
    mock_pipeline_class.return_value = fake_pipeline_instance
    
    resp = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/restart",
        json={"positive_prompt": "new"}
    )
    
    assert resp.status_code == 200
    assert resp.json.get("restarted") is True
    fake_pipeline_instance.restart_shot.assert_called_once_with(scene_id, shot_id, "new", None)
    mock_pipeline_class.assert_called_once()
