"""
tests/unit/test_api_gate_endpoints.py
Regression tests for generation and approval gate endpoints.

Tier 1 HTTP endpoints batch C.
"""

from unittest.mock import MagicMock, patch

import pytest

from web_server import app
from project_manager import ProjectLockError


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _fake_project(pid="proj_1"):
    return {
        "id": pid,
        "scenes": [
            {
                "id": "scene_1",
                "shots": [
                    {"id": "shot_1"}
                ]
            }
        ]
    }


class TestApiGenerateKeyframe:
    """Tests for api_generate_keyframe (trigger, errors)."""

    def test_success(self, client):
        mock_pipeline = MagicMock()
        mock_pipeline.generate_keyframe_take.return_value = {"success": True, "take": {"id": "t1"}}
        with patch("web_server.load_project", return_value=_fake_project()), \
             patch("web_server._locate_shot", return_value=(_fake_project()["scenes"][0], _fake_project()["scenes"][0]["shots"][0])), \
             patch("web_server._get_stage_pipeline", return_value=mock_pipeline):
            resp = client.post("/api/projects/proj_1/shots/shot_1/keyframes/generate", json={"positive_prompt": "test"})
            assert resp.status_code == 200
            assert resp.json["success"] is True
            mock_pipeline.generate_keyframe_take.assert_called_once_with(
                "scene_1", "shot_1", positive_prompt="test", negative_prompt=None
            )

    def test_error_prevents_stranding(self, client):
        """Failure must return 409 so the operator is not stranded without feedback."""
        mock_pipeline = MagicMock()
        mock_pipeline.generate_keyframe_take.return_value = {"success": False, "error": "API failed"}
        with patch("web_server.load_project", return_value=_fake_project()), \
             patch("web_server._locate_shot", return_value=(_fake_project()["scenes"][0], _fake_project()["scenes"][0]["shots"][0])), \
             patch("web_server._get_stage_pipeline", return_value=mock_pipeline):
            resp = client.post("/api/projects/proj_1/shots/shot_1/keyframes/generate", json={})
            assert resp.status_code == 409
            assert resp.json["error"] == "API failed"

    def test_pipeline_value_error_returns_404(self, client):
        """Pipeline initialization failures (missing project) return 404."""
        with patch("web_server.load_project", return_value=_fake_project()), \
             patch("web_server._locate_shot", return_value=(_fake_project()["scenes"][0], _fake_project()["scenes"][0]["shots"][0])), \
             patch("web_server._get_stage_pipeline", side_effect=ValueError("No project")):
            resp = client.post("/api/projects/proj_1/shots/shot_1/keyframes/generate", json={})
            assert resp.status_code == 404

    def test_project_not_found(self, client):
        with patch("web_server.load_project", return_value=None):
            resp = client.post("/api/projects/proj_1/shots/shot_1/keyframes/generate", json={})
            assert resp.status_code == 404

    def test_shot_not_found(self, client):
        with patch("web_server.load_project", return_value=_fake_project()), \
             patch("web_server._locate_shot", return_value=(None, None)):
            resp = client.post("/api/projects/proj_1/shots/shot_1/keyframes/generate", json={})
            assert resp.status_code == 404


class TestApiGenerateMotion:
    """Tests for api_generate_motion (trigger, concurrency, budget guards)."""

    def test_success(self, client):
        mock_pipeline = MagicMock()
        mock_pipeline.generate_motion_take.return_value = {"success": True, "take": {"id": "m1"}}
        with patch("web_server.load_project", return_value=_fake_project()), \
             patch("web_server._locate_shot", return_value=(_fake_project()["scenes"][0], _fake_project()["scenes"][0]["shots"][0])), \
             patch("web_server._get_stage_pipeline", return_value=mock_pipeline):
            resp = client.post("/api/projects/proj_1/shots/shot_1/motion/generate")
            assert resp.status_code == 200
            assert resp.json["success"] is True
            mock_pipeline.generate_motion_take.assert_called_once_with("scene_1", "shot_1")

    def test_budget_guard_failure(self, client):
        """A budget guard failure returned from the pipeline returns 409."""
        mock_pipeline = MagicMock()
        mock_pipeline.generate_motion_take.return_value = {"success": False, "error": "Budget exceeded"}
        with patch("web_server.load_project", return_value=_fake_project()), \
             patch("web_server._locate_shot", return_value=(_fake_project()["scenes"][0], _fake_project()["scenes"][0]["shots"][0])), \
             patch("web_server._get_stage_pipeline", return_value=mock_pipeline):
            resp = client.post("/api/projects/proj_1/shots/shot_1/motion/generate")
            assert resp.status_code == 409
            assert resp.json["error"] == "Budget exceeded"

    def test_concurrency_project_locked(self, client):
        """The endpoint is protected by @_project_lock_guard. Concurrent accesses return 409 project_locked."""
        with patch("web_server.load_project", side_effect=ProjectLockError("proj_1", 10)):
            resp = client.post("/api/projects/proj_1/shots/shot_1/motion/generate")
            assert resp.status_code == 409
            assert resp.json["code"] == "project_locked"


class TestApiApproveFinalTake:
    """Tests for api_approve_final_take (gate transition)."""

    def test_success(self, client):
        """Gate transition succeeds and cascades into assembly/screening."""
        mock_pipeline = MagicMock()
        mock_pipeline.approve_take.return_value = {"success": True}
        with patch("web_server._get_stage_pipeline", return_value=mock_pipeline):
            resp = client.post("/api/projects/proj_1/shots/shot_1/final/t1/approve")
            assert resp.status_code == 200
            assert resp.json["success"] is True
            mock_pipeline.approve_take.assert_called_once_with("shot_1", "t1", "final")

    def test_error_returns_409(self, client):
        """Approval error (e.g. invalid take) returns 409."""
        mock_pipeline = MagicMock()
        mock_pipeline.approve_take.return_value = {"error": "Invalid take"}
        with patch("web_server._get_stage_pipeline", return_value=mock_pipeline):
            resp = client.post("/api/projects/proj_1/shots/shot_1/final/t1/approve")
            assert resp.status_code == 409
            assert resp.json["error"] == "Invalid take"

    def test_value_error_returns_404(self, client):
        """Missing project during pipeline resolution returns 404."""
        with patch("web_server._get_stage_pipeline", side_effect=ValueError("Not found")):
            resp = client.post("/api/projects/proj_1/shots/shot_1/final/t1/approve")
            assert resp.status_code == 404

    def test_concurrency_project_locked(self, client):
        """The approval endpoint is protected by @_project_lock_guard."""
        with patch("web_server._get_stage_pipeline", side_effect=ProjectLockError("proj_1", 10)):
            resp = client.post("/api/projects/proj_1/shots/shot_1/final/t1/approve")
            assert resp.status_code == 409
            assert resp.json["code"] == "project_locked"
