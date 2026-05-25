"""tests/unit/test_reassemble_endpoint.py -- S21 /assemble/re-assemble endpoint.

Covers the HTTP endpoint added in cycle-9 S21 (Surface B):

  POST /api/projects/<pid>/assemble/re-assemble

Test matrix:

1. Returns 404 when CINEMA_SCREENING_STAGE flag is OFF.
2. Returns 404 when project doesn't exist.
3. Returns 200 + skipped=true when only_if_changed=true AND no dirty
   shots; CinemaPipeline.assemble_approved_takes is NOT called.
4. Returns 200 + skipped=false + regenerated_shots populated when
   only_if_changed=true AND dirty shots exist; assemble_approved_takes
   IS called; needs_reassembly is cleared on success.
5. Returns 200 + always runs when only_if_changed=false even with no
   dirty shots.
6. Returns 409 reassembly_busy when a re-assembly is already in flight
   for the same project (re-entrancy guard).
7. Does NOT busy-fence on _running_pipelines (mirrors /screening/approve;
   re-assembly runs WHILE the pipeline waits at the SCREENING gate).
8. needs_reassembly is NOT cleared when assemble_approved_takes fails
   (so the operator can retry without re-iterating the same shots).

Uses Flask test_client() with patched CinemaPipeline / project_manager
so no real ffmpeg / filesystem mp4 work is required.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from web_server import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def flag_on():
    """CINEMA_SCREENING_STAGE=1 for the duration of the test."""
    with patch.dict(os.environ, {"CINEMA_SCREENING_STAGE": "1"}):
        yield


@pytest.fixture()
def flag_off():
    """CINEMA_SCREENING_STAGE cleared for the duration of the test."""
    env = {k: v for k, v in os.environ.items() if k != "CINEMA_SCREENING_STAGE"}
    with patch.dict(os.environ, env, clear=True):
        yield


def _make_project(
    pid: str = "proj-reassemble-test",
    dirty: list[str] | None = None,
    num_shots: int = 2,
) -> dict:
    """Minimal project dict with optional needs_reassembly populated."""
    shots = []
    for i in range(num_shots):
        shots.append({
            "id": f"shot_1_{i}",
            "approved_final_take_id": f"take_{i}",
            "motion_takes": [
                {"id": f"take_{i}", "kind": "motion",
                 "metadata": {"duration_s": 5.0}},
            ],
        })
    project: dict = {
        "id": pid,
        "name": "Test Reassemble Project",
        "scenes": [
            {
                "id": "scene_1",
                "shots": shots,
                "duration_seconds": 5.0,
            }
        ],
    }
    if dirty is not None:
        project["needs_reassembly"] = list(dirty)
    return project


def _patch_clean_in_flight():
    """Clean module-level _reassembly_in_flight set between tests."""
    from web_server import _reassembly_in_flight, _reassembly_lock
    with _reassembly_lock:
        _reassembly_in_flight.clear()


@pytest.fixture(autouse=True)
def _reset_in_flight():
    """Auto-reset _reassembly_in_flight before AND after each test so a
    test that left stale state doesn't poison the next one."""
    _patch_clean_in_flight()
    yield
    _patch_clean_in_flight()


# ---------------------------------------------------------------------------
# Flag-off + project-not-found paths
# ---------------------------------------------------------------------------


class TestFlagOff:
    def test_returns_404_when_flag_off(self, client, flag_off):
        resp = client.post("/api/projects/proj-x/assemble/re-assemble")
        assert resp.status_code == 404
        body = resp.get_json()
        assert "Screening stage not enabled" in body["error"]


class TestProjectNotFound:
    def test_returns_404_when_project_absent(self, client, flag_on):
        with patch("web_server.load_project", return_value=None):
            resp = client.post(
                "/api/projects/missing-pid/assemble/re-assemble",
                json={"only_if_changed": True},
            )
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "Project not found"


# ---------------------------------------------------------------------------
# only_if_changed semantics
# ---------------------------------------------------------------------------


class TestOnlyIfChangedShortCircuit:
    def test_skipped_when_no_dirty_and_only_if_changed_true(self, client, flag_on):
        project = _make_project(dirty=[])
        with patch("web_server.load_project", return_value=project), \
             patch("web_server.CinemaPipeline") as mock_pipeline:
            resp = client.post(
                f"/api/projects/{project['id']}/assemble/re-assemble",
                json={"only_if_changed": True},
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["skipped"] is True
        assert body["regenerated_shots"] == []
        assert "cost_estimate_seconds" in body
        # The expensive pipeline must NOT have been constructed/invoked.
        mock_pipeline.assert_not_called()

    def test_missing_only_if_changed_defaults_to_true(self, client, flag_on):
        # Default behavior: only_if_changed=true. With no dirty shots, skip.
        project = _make_project(dirty=[])
        with patch("web_server.load_project", return_value=project), \
             patch("web_server.CinemaPipeline") as mock_pipeline:
            # No JSON body at all
            resp = client.post(f"/api/projects/{project['id']}/assemble/re-assemble")
        assert resp.status_code == 200
        assert resp.get_json()["skipped"] is True
        mock_pipeline.assert_not_called()


class TestDirtyShotsTriggerReassembly:
    def test_runs_when_dirty_and_only_if_changed_true(self, client, flag_on):
        project = _make_project(dirty=["shot_1_0", "shot_1_1"])
        new_path = "/fake/exports/final_cinema.mp4"

        # Patch CinemaPipeline so we can verify it was constructed +
        # assemble_approved_takes() was called.
        mock_pipeline_inst = MagicMock()
        mock_pipeline_inst.assemble_approved_takes.return_value = {
            "success": True, "final_path": new_path,
        }
        clear_called: dict[str, bool] = {"called": False}

        def fake_clear(pid):
            clear_called["called"] = True
            return {"success": True, "needs_reassembly": []}

        with patch("web_server.load_project", return_value=project), \
             patch("web_server.CinemaPipeline", return_value=mock_pipeline_inst), \
             patch("web_server._get_or_build_core", return_value=MagicMock()), \
             patch("cinema.screening.clear_needs_reassembly", side_effect=fake_clear):
            resp = client.post(
                f"/api/projects/{project['id']}/assemble/re-assemble",
                json={"only_if_changed": True},
            )

        assert resp.status_code == 200, resp.data
        body = resp.get_json()
        assert body["success"] is True
        assert body["skipped"] is False
        assert body["new_assembled_path"] == new_path
        assert body["regenerated_shots"] == ["shot_1_0", "shot_1_1"]
        assert "cost_estimate_seconds" in body
        mock_pipeline_inst.assemble_approved_takes.assert_called_once()
        # Dirty-tracking is cleared after successful reassembly.
        assert clear_called["called"] is True

    def test_forces_run_when_only_if_changed_false(self, client, flag_on):
        # Empty dirty list, but only_if_changed=false forces a full rerun.
        project = _make_project(dirty=[])
        mock_pipeline_inst = MagicMock()
        mock_pipeline_inst.assemble_approved_takes.return_value = {
            "success": True, "final_path": "/fake/final.mp4",
        }
        with patch("web_server.load_project", return_value=project), \
             patch("web_server.CinemaPipeline", return_value=mock_pipeline_inst), \
             patch("web_server._get_or_build_core", return_value=MagicMock()), \
             patch("cinema.screening.clear_needs_reassembly",
                   return_value={"success": True, "needs_reassembly": []}):
            resp = client.post(
                f"/api/projects/{project['id']}/assemble/re-assemble",
                json={"only_if_changed": False},
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["skipped"] is False
        assert body["regenerated_shots"] == []  # nothing was dirty, but we still ran
        mock_pipeline_inst.assemble_approved_takes.assert_called_once()


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


class TestReassemblyFailure:
    def test_failed_assembly_returns_409_and_preserves_dirty(self, client, flag_on):
        # When assemble_approved_takes returns success=False, the endpoint
        # must NOT clear needs_reassembly -- the operator should be able to
        # retry without re-iterating the same shots.
        project = _make_project(dirty=["shot_1_0"])
        mock_pipeline_inst = MagicMock()
        mock_pipeline_inst.assemble_approved_takes.return_value = {
            "success": False, "error": "Approved take files are missing for: shot_xyz",
        }
        clear_called: dict[str, bool] = {"called": False}

        def fake_clear(pid):
            clear_called["called"] = True
            return {"success": True}

        with patch("web_server.load_project", return_value=project), \
             patch("web_server.CinemaPipeline", return_value=mock_pipeline_inst), \
             patch("web_server._get_or_build_core", return_value=MagicMock()), \
             patch("cinema.screening.clear_needs_reassembly", side_effect=fake_clear):
            resp = client.post(
                f"/api/projects/{project['id']}/assemble/re-assemble",
                json={"only_if_changed": True},
            )

        assert resp.status_code == 409
        body = resp.get_json()
        assert body["success"] is False
        assert "missing" in body["error"]
        # Critical: dirty-tracking preserved so the operator can retry.
        assert clear_called["called"] is False
        # The list of dirty shots is surfaced in the failure response so
        # the UI can still render "shot_1_0 will be regenerated when you
        # retry."
        assert body["regenerated_shots"] == ["shot_1_0"]


# ---------------------------------------------------------------------------
# Re-entrancy guard
# ---------------------------------------------------------------------------


class TestReassemblyInFlightGuard:
    def test_returns_409_reassembly_busy_when_already_running(self, client, flag_on):
        from web_server import _reassembly_in_flight, _reassembly_lock
        pid = "proj-reassembly-busy"

        # Simulate an in-flight re-assembly by pre-populating the guard set.
        with _reassembly_lock:
            _reassembly_in_flight.add(pid)
        try:
            resp = client.post(
                f"/api/projects/{pid}/assemble/re-assemble",
                json={"only_if_changed": True},
            )
        finally:
            with _reassembly_lock:
                _reassembly_in_flight.discard(pid)

        assert resp.status_code == 409
        body = resp.get_json()
        assert body["code"] == "reassembly_busy"
        assert body["retryable"] is True

    def test_in_flight_cleared_after_success(self, client, flag_on):
        # After a successful re-assembly, the pid must be removed from
        # _reassembly_in_flight so the operator can run a second re-assemble.
        from web_server import _reassembly_in_flight
        project = _make_project(dirty=["shot_1_0"])
        mock_pipeline_inst = MagicMock()
        mock_pipeline_inst.assemble_approved_takes.return_value = {
            "success": True, "final_path": "/fake/final.mp4",
        }
        with patch("web_server.load_project", return_value=project), \
             patch("web_server.CinemaPipeline", return_value=mock_pipeline_inst), \
             patch("web_server._get_or_build_core", return_value=MagicMock()), \
             patch("cinema.screening.clear_needs_reassembly",
                   return_value={"success": True}):
            client.post(f"/api/projects/{project['id']}/assemble/re-assemble",
                        json={"only_if_changed": True})
        # Endpoint's finally: must have cleared the in-flight marker.
        assert project["id"] not in _reassembly_in_flight

    def test_in_flight_cleared_after_failure(self, client, flag_on):
        # Same property must hold after a FAILURE -- otherwise a single
        # failed re-assembly would lock out the project forever.
        from web_server import _reassembly_in_flight
        project = _make_project(dirty=["shot_1_0"])
        mock_pipeline_inst = MagicMock()
        mock_pipeline_inst.assemble_approved_takes.return_value = {
            "success": False, "error": "missing files",
        }
        with patch("web_server.load_project", return_value=project), \
             patch("web_server.CinemaPipeline", return_value=mock_pipeline_inst), \
             patch("web_server._get_or_build_core", return_value=MagicMock()):
            client.post(f"/api/projects/{project['id']}/assemble/re-assemble",
                        json={"only_if_changed": True})
        assert project["id"] not in _reassembly_in_flight


# ---------------------------------------------------------------------------
# Busy-fence bypass (mirrors /screening/approve)
# ---------------------------------------------------------------------------


class TestDoesNotBusyFence:
    def test_runs_even_when_project_busy_in_running_pipelines(self, client, flag_on):
        # The SCREENING gate-waiter occupies _running_pipelines. If
        # re-assemble called _reject_if_project_busy, the operator could
        # never re-assemble during SCREENING -- the gate would never open.
        # Verify the endpoint ignores _running_pipelines membership.
        from web_server import _running_pipelines
        pid = "proj-busy-reassemble"
        _running_pipelines[pid] = object()  # sentinel; not None, not _PIPELINE_PENDING
        try:
            project = _make_project(pid=pid, dirty=["shot_1_0"])
            mock_pipeline_inst = MagicMock()
            mock_pipeline_inst.assemble_approved_takes.return_value = {
                "success": True, "final_path": "/fake/final.mp4",
            }
            with patch("web_server.load_project", return_value=project), \
                 patch("web_server.CinemaPipeline", return_value=mock_pipeline_inst), \
                 patch("web_server._get_or_build_core", return_value=MagicMock()), \
                 patch("cinema.screening.clear_needs_reassembly",
                       return_value={"success": True}):
                resp = client.post(
                    f"/api/projects/{pid}/assemble/re-assemble",
                    json={"only_if_changed": True},
                )
        finally:
            _running_pipelines.pop(pid, None)

        # 200, NOT 409 project_busy. The mp4 work would actually run if
        # CinemaPipeline weren't mocked.
        assert resp.status_code == 200, resp.data
        body = resp.get_json()
        assert body["success"] is True
        mock_pipeline_inst.assemble_approved_takes.assert_called_once()


# ---------------------------------------------------------------------------
# Response shape sanity
# ---------------------------------------------------------------------------


class TestResponseShape:
    def test_success_response_has_all_expected_keys(self, client, flag_on):
        project = _make_project(dirty=["shot_1_0"])
        mock_pipeline_inst = MagicMock()
        mock_pipeline_inst.assemble_approved_takes.return_value = {
            "success": True, "final_path": "/fake/final.mp4",
        }
        with patch("web_server.load_project", return_value=project), \
             patch("web_server.CinemaPipeline", return_value=mock_pipeline_inst), \
             patch("web_server._get_or_build_core", return_value=MagicMock()), \
             patch("cinema.screening.clear_needs_reassembly",
                   return_value={"success": True}):
            resp = client.post(
                f"/api/projects/{project['id']}/assemble/re-assemble",
                json={"only_if_changed": True},
            )
        body = resp.get_json()
        # Required keys per proposal §"Endpoints" + S21 brief.
        for key in (
            "success", "new_assembled_path", "regenerated_shots",
            "cost_estimate_seconds", "skipped",
        ):
            assert key in body, f"Missing key '{key}' in response"

    def test_skipped_response_has_all_expected_keys(self, client, flag_on):
        project = _make_project(dirty=[])
        with patch("web_server.load_project", return_value=project):
            resp = client.post(
                f"/api/projects/{project['id']}/assemble/re-assemble",
                json={"only_if_changed": True},
            )
        body = resp.get_json()
        for key in (
            "success", "new_assembled_path", "regenerated_shots",
            "cost_estimate_seconds", "skipped",
        ):
            assert key in body, f"Missing key '{key}' in skipped response"
        assert body["skipped"] is True
        assert body["new_assembled_path"] == ""
