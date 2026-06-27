"""
tests/unit/test_api_state_and_destructive.py — Regression tests for destructive
and state-machine endpoints in web_server.py (Tier 1 Batch B).
"""

from unittest.mock import MagicMock, patch

import pytest
from flask import json

from web_server import app, _running_pipelines, _pipelines_lock


@pytest.fixture(autouse=True)
def clean_pipeline_state():
    """Clear _running_pipelines before and after each test."""
    with _pipelines_lock:
        _running_pipelines.clear()
    yield
    with _pipelines_lock:
        _running_pipelines.clear()


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
    """If no pipeline is running and project exists, delete succeeds."""
    pid = "test_pid"
    mock_delete.return_value = True
    
    resp = client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json.get("deleted") is True
    mock_delete.assert_called_once_with(pid, timeout=pytest.approx(5.0, abs=10.0))  # HTTP_PROJECT_TIMEOUT is usually 5 or 15


@patch("web_server.delete_project")
def test_api_delete_project_not_found(mock_delete, client):
    """If project does not exist, delete returns 404."""
    pid = "test_pid"
    mock_delete.return_value = False
    
    resp = client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 404
    assert resp.json.get("error") == "Project not found"
    mock_delete.assert_called_once()


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
