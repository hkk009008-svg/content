"""
tests/unit/test_api_gate_endpoints.py
Regression tests for generation and approval gate endpoints.

Tier 1 HTTP endpoints batch C.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

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
             patch("web_server._get_running_pipeline", return_value=SimpleNamespace(current_stage="KEYFRAME_REVIEW")), \
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
             patch("web_server._get_running_pipeline", return_value=SimpleNamespace(current_stage="KEYFRAME_REVIEW")), \
             patch("web_server._get_stage_pipeline", return_value=mock_pipeline):
            resp = client.post("/api/projects/proj_1/shots/shot_1/keyframes/generate", json={})
            assert resp.status_code == 409
            assert resp.json["error"] == "API failed"

    def test_pipeline_value_error_returns_404(self, client):
        """Pipeline initialization failures (missing project) return 404."""
        with patch("web_server.load_project", return_value=_fake_project()), \
             patch("web_server._locate_shot", return_value=(_fake_project()["scenes"][0], _fake_project()["scenes"][0]["shots"][0])), \
             patch("web_server._get_running_pipeline", return_value=SimpleNamespace(current_stage="KEYFRAME_REVIEW")), \
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

    def test_generation_is_blocked_during_performance_review(self, client):
        project = _fake_project()
        with patch("web_server.load_project", return_value=project), \
             patch("web_server._get_running_pipeline", return_value=SimpleNamespace(current_stage="PERFORMANCE_REVIEW")), \
             patch("web_server._get_stage_pipeline") as pipeline:
            response = client.post(
                "/api/projects/proj_1/shots/shot_1/keyframes/generate",
                json={},
            )

        assert response.status_code == 409
        assert response.json["code"] == "wrong_pipeline_stage"
        assert response.json["required_stage"] == "KEYFRAME_REVIEW"
        pipeline.assert_not_called()


class TestApiResolveKeyframeRecovery:
    def test_requires_exact_explicit_confirmation(self, client):
        resp = client.post(
            "/api/projects/proj_1/shots/shot_1/keyframes/recovery/resolve",
            json={"confirmed": True, "force": True},
        )
        assert resp.status_code == 400
        assert "confirmation" in resp.json["error"].lower()

    def test_resolves_through_pipeline(self, client):
        mock_pipeline = MagicMock()
        mock_pipeline.resolve_deferred_keyframe_job.return_value = {
            "success": True,
            "resolved": True,
        }
        project = _fake_project()
        shot = project["scenes"][0]["shots"][0]
        with patch("web_server.load_project", return_value=project), \
             patch("web_server._locate_shot", return_value=(project["scenes"][0], shot)), \
             patch("web_server._get_stage_pipeline", return_value=mock_pipeline):
            resp = client.post(
                "/api/projects/proj_1/shots/shot_1/keyframes/recovery/resolve",
                json={"confirmed": True},
            )

        assert resp.status_code == 200
        assert resp.json["resolved"] is True
        mock_pipeline.resolve_deferred_keyframe_job.assert_called_once_with("shot_1")


class TestApiGenerateMotion:
    """Tests for api_generate_motion (trigger, concurrency, budget guards)."""

    def test_success(self, client):
        mock_pipeline = MagicMock()
        mock_pipeline.generate_motion_take.return_value = {"success": True, "take": {"id": "m1"}}
        with patch("web_server.load_project", return_value=_fake_project()), \
             patch("web_server._locate_shot", return_value=(_fake_project()["scenes"][0], _fake_project()["scenes"][0]["shots"][0])), \
             patch("web_server._get_running_pipeline", return_value=SimpleNamespace(current_stage="REVIEW")), \
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
             patch("web_server._get_running_pipeline", return_value=SimpleNamespace(current_stage="REVIEW")), \
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

    @pytest.mark.parametrize("stage", ["", "PERFORMANCE_REVIEW", "KEYFRAME_REVIEW"])
    def test_requires_exact_final_review_stage(self, client, stage):
        with patch("web_server.load_project", return_value=_fake_project()), \
             patch("web_server._get_running_pipeline", return_value=SimpleNamespace(current_stage=stage)), \
             patch("web_server._get_stage_pipeline") as pipeline:
            response = client.post(
                "/api/projects/proj_1/shots/shot_1/motion/generate"
            )

        assert response.status_code == 409
        assert response.json["code"] == "wrong_pipeline_stage"
        assert response.json["required_stage"] == "REVIEW"
        pipeline.assert_not_called()


class TestApiPerformanceReviewActions:
    @pytest.mark.parametrize(
        "body",
        [None, {}, {"request_id": "bad"}, {"request_id": "A" * 32}, {"request_id": "1" * 32, "extra": True}],
    )
    def test_generate_requires_exact_client_request_id(self, client, body):
        response = client.post(
            "/api/projects/proj_1/shots/shot_1/performance/generate",
            json=body,
        )

        assert response.status_code == 400
        assert response.json["code"] == "invalid_performance_request_id"

    def test_performance_approval_requires_exact_performance_review(self, client):
        with patch(
            "web_server._get_running_pipeline",
            return_value=SimpleNamespace(current_stage="REVIEW"),
        ), patch("web_server._get_stage_pipeline") as pipeline:
            response = client.post(
                "/api/projects/proj_1/shots/shot_1/performance/take-1/approve"
            )

        assert response.status_code == 409
        assert response.json["code"] == "wrong_pipeline_stage"
        pipeline.assert_not_called()

    def test_performance_approval_reaches_controller_at_exact_stage(self, client):
        pipeline = MagicMock()
        pipeline.approve_take.return_value = {
            "shot_id": "shot_1",
            "take_id": "take-1",
            "approval_kind": "performance",
        }
        with patch(
            "web_server._get_running_pipeline",
            return_value=SimpleNamespace(current_stage="PERFORMANCE_REVIEW"),
        ), patch("web_server._get_stage_pipeline", return_value=pipeline):
            response = client.post(
                "/api/projects/proj_1/shots/shot_1/performance/take-1/approve"
            )

        assert response.status_code == 200
        pipeline.approve_take.assert_called_once_with(
            "shot_1", "take-1", "performance"
        )

    def test_generate_and_retry_use_the_real_performance_controller(self, client):
        project = _fake_project()
        scene = project["scenes"][0]
        shot = scene["shots"][0]
        pipeline = MagicMock()
        pipeline.generate_performance_take.side_effect = [
            {"success": True, "take": {"id": "performance-1"}},
            {"success": True, "take": {"id": "performance-2"}},
        ]
        with patch("web_server.load_project", return_value=project), \
             patch("web_server._locate_shot", return_value=(scene, shot)), \
             patch("web_server._get_running_pipeline", return_value=SimpleNamespace(current_stage="PERFORMANCE_REVIEW")), \
             patch("web_server._get_stage_pipeline", return_value=pipeline):
            first = client.post(
                "/api/projects/proj_1/shots/shot_1/performance/generate",
                json={"request_id": "1" * 32},
            )
            retry = client.post(
                "/api/projects/proj_1/shots/shot_1/performance/generate",
                json={"request_id": "2" * 32},
            )

        assert first.status_code == 200
        assert retry.status_code == 200
        assert [first.json["take"]["id"], retry.json["take"]["id"]] == [
            "performance-1",
            "performance-2",
        ]
        assert pipeline.generate_performance_take.call_args_list == [
            call(
                "scene_1", "shot_1", operator_requested=True,
                operator_request_id="1" * 32,
            ),
            call(
                "scene_1", "shot_1", operator_requested=True,
                operator_request_id="2" * 32,
            ),
        ]

    def test_generate_failure_is_non_2xx_and_preserves_error(self, client):
        project = _fake_project()
        pipeline = MagicMock()
        pipeline.generate_performance_take.return_value = {
            "success": False,
            "error": "Driving video required",
            "code": "driving_video_required",
        }
        with patch("web_server.load_project", return_value=project), \
             patch("web_server._get_running_pipeline", return_value=SimpleNamespace(current_stage="PERFORMANCE_REVIEW")), \
             patch("web_server._get_stage_pipeline", return_value=pipeline):
            response = client.post(
                "/api/projects/proj_1/shots/shot_1/performance/generate",
                json={"request_id": "3" * 32},
            )

        assert response.status_code == 409
        assert response.json["error"] == "Driving video required"

    @pytest.mark.parametrize("body", [None, {}, {"confirmed": False}, {"confirmed": True, "force": True}])
    def test_skip_requires_exact_explicit_confirmation(self, client, body):
        response = client.post(
            "/api/projects/proj_1/shots/shot_1/performance/skip",
            json=body,
        )
        assert response.status_code == 400
        assert "confirmation" in response.json["error"].lower()

    @pytest.mark.parametrize(
        "reason",
        ["", "   ", "x" * 241, "line one\nline two", "control\x7fbyte"],
    )
    def test_skip_rejects_missing_oversized_or_control_character_reason(
        self, client, reason
    ):
        response = client.post(
            "/api/projects/proj_1/shots/shot_1/performance/skip",
            json={"confirmed": True, "reason": reason},
        )

        assert response.status_code == 400
        assert response.json["code"] == "invalid_performance_skip_reason"

    @pytest.mark.parametrize("stage", ["", "KEYFRAME_REVIEW", "REVIEW"])
    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("performance/generate", {"request_id": "4" * 32}),
            (
                "performance/skip",
                {"confirmed": True, "reason": "Operator chose ordinary motion"},
            ),
        ],
    )
    def test_actions_fail_closed_outside_exact_performance_review(
        self, client, stage, path, body
    ):
        project = _fake_project()
        with patch("web_server.load_project", return_value=project), \
             patch("web_server._get_running_pipeline", return_value=SimpleNamespace(current_stage=stage)), \
             patch("web_server._get_stage_pipeline") as pipeline:
            response = client.post(
                f"/api/projects/proj_1/shots/shot_1/{path}",
                json=body,
            )

        assert response.status_code == 409
        assert response.json["code"] == "wrong_pipeline_stage"
        assert response.json["required_stage"] == "PERFORMANCE_REVIEW"
        assert response.json["current_stage"] == stage
        pipeline.assert_not_called()

    def test_skip_success_and_authority_failure_are_truthful(self, client):
        project = _fake_project()
        pipeline = MagicMock()
        pipeline.skip_performance_take.side_effect = [
            {"success": True, "skipped": True, "engine": "SKIP"},
            {
                "success": False,
                "error": "Provider work is accepted_unknown",
                "code": "provider_job_deferred",
            },
        ]
        with patch("web_server.load_project", return_value=project), \
             patch("web_server._get_running_pipeline", return_value=SimpleNamespace(current_stage="PERFORMANCE_REVIEW")), \
             patch("web_server._get_stage_pipeline", return_value=pipeline):
            success = client.post(
                "/api/projects/proj_1/shots/shot_1/performance/skip",
                json={"confirmed": True, "reason": "The acting reference is unusable"},
            )
            blocked = client.post(
                "/api/projects/proj_1/shots/shot_1/performance/skip",
                json={"confirmed": True, "reason": "The acting reference is unusable"},
            )

        assert success.status_code == 200
        assert success.json["skipped"] is True
        assert blocked.status_code == 409
        assert blocked.json["code"] == "provider_job_deferred"
        assert pipeline.skip_performance_take.call_count == 2
        assert pipeline.skip_performance_take.call_args_list == [
            call("scene_1", "shot_1", reason="The acting reference is unusable"),
            call("scene_1", "shot_1", reason="The acting reference is unusable"),
        ]


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
