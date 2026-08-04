"""Exclusive direct-stage leases protect cached project runtime state."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import web_server
from web_server import app


@pytest.fixture(autouse=True)
def clean_runtime_state():
    with web_server._pipelines_lock:
        web_server._running_pipelines.clear()
        web_server._progress_queues.clear()
        web_server._project_admin_in_flight.clear()
        web_server._project_stage_in_flight.clear()
    with web_server._cores_lock:
        web_server._running_cores.clear()
    yield
    with web_server._pipelines_lock:
        web_server._running_pipelines.clear()
        web_server._progress_queues.clear()
        web_server._project_admin_in_flight.clear()
        web_server._project_stage_in_flight.clear()
    with web_server._cores_lock:
        web_server._running_cores.clear()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def _project(pid: str) -> dict:
    return {
        "id": pid,
        "name": "Stage lease test",
        "global_settings": {},
        "scenes": [
            {"id": "scene-1", "shots": [{"id": "shot-1"}]},
        ],
        "characters": [],
        "locations": [],
    }


def test_direct_motion_lease_blocks_settings_delete_generation_and_core_eviction(
    client,
):
    pid = "stage-lease-project"
    project = _project(pid)
    cached_core = MagicMock()
    with web_server._cores_lock:
        web_server._running_cores[pid] = cached_core

    nested: dict[str, object] = {}
    stage_pipeline = MagicMock()

    def generate_while_probing_admin(_scene_id, _shot_id):
        assert pid in web_server._project_stage_in_flight
        with app.test_client() as other_client:
            settings = other_client.patch(
                f"/api/projects/{pid}",
                json={
                    "global_settings": {
                        "revision": 0,
                        "music_mood": "hopeful",
                    }
                },
            )
            delete = other_client.delete(f"/api/projects/{pid}")
            generation = other_client.post(f"/api/projects/{pid}/generate")
        nested.update(
            settings=(settings.status_code, settings.get_json()),
            delete=(delete.status_code, delete.get_json()),
            generation=(generation.status_code, generation.get_json()),
        )
        assert web_server._running_cores[pid] is cached_core
        cached_core.cost_tracker.close.assert_not_called()
        return {"success": True, "take": {"id": "motion-1"}}

    stage_pipeline.generate_motion_take.side_effect = generate_while_probing_admin

    with (
        patch("web_server.load_project", return_value=project),
        patch("web_server._get_stage_pipeline", return_value=stage_pipeline),
        patch("web_server.delete_project", return_value=True) as delete_project,
    ):
        response = client.post(
            f"/api/projects/{pid}/shots/shot-1/motion/generate"
        )

        assert response.status_code == 200
        for status, body in nested.values():
            assert status == 409
            assert body["code"] == "project_busy"
            assert "direct stage operation" in body["error"]
        delete_project.assert_not_called()
        assert pid not in web_server._project_stage_in_flight
        assert pid not in web_server._running_pipelines

        # Once the stage call releases its lease, destructive administration
        # may proceed and is then responsible for retiring the cached core.
        deleted = client.delete(f"/api/projects/{pid}")

    assert deleted.status_code == 200
    assert pid not in web_server._running_cores
    cached_core.cost_tracker.close.assert_called_once_with()
    delete_project.assert_called_once_with(pid, timeout=web_server.HTTP_PROJECT_TIMEOUT)


def test_concurrent_direct_motion_is_rejected_before_second_provider_call(client):
    pid = "stage-lease-duplicate"
    project = _project(pid)
    nested: dict[str, object] = {}
    stage_pipeline = MagicMock()

    def first_motion(_scene_id, _shot_id):
        with app.test_client() as other_client:
            duplicate = other_client.post(
                f"/api/projects/{pid}/shots/shot-1/motion/generate"
            )
        nested.update(status=duplicate.status_code, body=duplicate.get_json())
        return {"success": True}

    stage_pipeline.generate_motion_take.side_effect = first_motion
    with (
        patch("web_server.load_project", return_value=project),
        patch("web_server._get_stage_pipeline", return_value=stage_pipeline),
    ):
        response = client.post(
            f"/api/projects/{pid}/shots/shot-1/motion/generate"
        )

    assert response.status_code == 200
    assert nested["status"] == 409
    assert nested["body"]["code"] == "project_busy"
    stage_pipeline.generate_motion_take.assert_called_once_with("scene-1", "shot-1")
    assert pid not in web_server._project_stage_in_flight


def test_stage_lease_releases_when_provider_raises(client):
    pid = "stage-lease-exception"
    project = _project(pid)
    stage_pipeline = MagicMock()
    stage_pipeline.generate_motion_take.side_effect = RuntimeError("provider exploded")

    with (
        patch("web_server.load_project", return_value=project),
        patch("web_server._get_stage_pipeline", return_value=stage_pipeline),
        pytest.raises(RuntimeError, match="provider exploded"),
    ):
        client.post(f"/api/projects/{pid}/shots/shot-1/motion/generate")

    assert pid not in web_server._project_stage_in_flight
    assert web_server._reserve_project_admin(pid) is True
    web_server._release_project_admin(pid)


def test_pending_pipeline_constructor_blocks_direct_stage_without_core_build(client):
    pid = "stage-lease-pending"
    with web_server._pipelines_lock:
        web_server._running_pipelines[pid] = web_server._PIPELINE_PENDING

    with patch("web_server._get_stage_pipeline") as get_stage_pipeline:
        response = client.post(
            f"/api/projects/{pid}/shots/shot-1/final/take-1/approve"
        )

    assert response.status_code == 409
    assert response.get_json()["code"] == "project_busy"
    get_stage_pipeline.assert_not_called()
    assert pid not in web_server._project_stage_in_flight
