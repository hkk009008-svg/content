"""tests/unit/test_screening_endpoint.py -- S19 SCREENING endpoints.

Covers the two HTTP endpoints added in cycle-9 S19 (Surface B):

- POST /api/projects/<pid>/assemble/screen
- POST /api/projects/<pid>/screening/approve

Test matrix:

1. Both endpoints return 404 when CINEMA_SCREENING_STAGE flag is OFF.
2. /assemble/screen returns 404 when flag is ON but project is absent.
3. /assemble/screen returns 409 when flag is ON, project exists, but
   the assembled mp4 hasn't been produced yet.
4. /assemble/screen returns 200 + correct manifest shape when flag is
   ON, project exists, and the assembled mp4 is present.
5. /assemble/screen returns 409 project_busy when the project's
   pipeline is mid-run.
6. /screening/approve returns 404 when flag is OFF.
7. /screening/approve returns 404 when project absent.
8. /screening/approve returns 200 + sets the flag when called against
   a real project (patched mutate_project to verify the write).
9. /screening/approve does NOT busy-fence (gate-exit can't deadlock).
10. /screening/approve nudges lifecycle.signal_gate when a pipeline is
    running.

Uses Flask's test_client() with patched project_manager / module-state
references so no filesystem access (beyond the assembled-mp4 stub file
in #4) is required.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from web_server import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Flask test client with testing mode enabled."""
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


def _make_project(pid: str = "proj-screen-test", num_shots: int = 2) -> dict:
    """Minimal project dict with N approved shots in one scene."""
    shots = []
    for i in range(num_shots):
        shots.append({
            "id": f"shot_1_{i}",
            "approved_final_take_id": f"take_{i}",
            "motion_takes": [
                {"id": f"take_{i}", "kind": "motion",
                 "metadata": {"duration_s": 3.0}},
            ],
        })
    return {
        "id": pid,
        "name": "Test Screening Project",
        "scenes": [
            {
                "id": "scene_1",
                "shots": shots,
                "duration_seconds": 3.0,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Flag-off paths
# ---------------------------------------------------------------------------


class TestFlagOffReturns404:
    def test_assemble_screen_flag_off(self, client, flag_off):
        resp = client.post("/api/projects/proj-x/assemble/screen")
        assert resp.status_code == 404
        body = resp.get_json()
        assert "Screening stage not enabled" in body["error"]

    def test_screening_approve_flag_off(self, client, flag_off):
        resp = client.post("/api/projects/proj-x/screening/approve")
        assert resp.status_code == 404
        body = resp.get_json()
        assert "Screening stage not enabled" in body["error"]


# ---------------------------------------------------------------------------
# /assemble/screen happy & error paths
# ---------------------------------------------------------------------------


class TestAssembleScreenEndpoint:
    def test_project_not_found_returns_404(self, client, flag_on):
        with patch("web_server.load_project", return_value=None):
            resp = client.post("/api/projects/missing-pid/assemble/screen")
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "Project not found"

    def test_busy_project_returns_409_project_busy(self, client, flag_on):
        # Simulate active pipeline by injecting an entry into _running_pipelines.
        from web_server import _running_pipelines
        pid = "proj-busy"
        sentinel = object()
        _running_pipelines[pid] = sentinel
        try:
            resp = client.post(f"/api/projects/{pid}/assemble/screen")
        finally:
            _running_pipelines.pop(pid, None)
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["code"] == "project_busy"

    def test_assembled_mp4_missing_returns_409(self, client, flag_on):
        project = _make_project()
        # Point get_project_dir at a tmpdir where final_cinema.mp4 doesn't exist.
        with tempfile.TemporaryDirectory() as tmpd:
            with patch("web_server.load_project", return_value=project), \
                 patch("domain.project_manager.get_project_dir", return_value=tmpd):
                resp = client.post(f"/api/projects/{project['id']}/assemble/screen")
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["success"] is False
        assert "not found" in body["error"]

    def test_happy_path_returns_manifest(self, client, flag_on):
        project = _make_project(num_shots=2)
        with tempfile.TemporaryDirectory() as tmpd:
            export_dir = os.path.join(tmpd, "exports")
            os.makedirs(export_dir, exist_ok=True)
            mp4_path = os.path.join(export_dir, "final_cinema.mp4")
            # Stub the mp4 file -- contents don't matter for the endpoint.
            with open(mp4_path, "wb") as f:
                f.write(b"\x00" * 16)

            with patch("web_server.load_project", return_value=project), \
                 patch("domain.project_manager.get_project_dir", return_value=tmpd):
                resp = client.post(f"/api/projects/{project['id']}/assemble/screen")

        assert resp.status_code == 200, resp.data
        body = resp.get_json()
        assert body["success"] is True
        assert body["assembled_mp4_path"].endswith("final_cinema.mp4")
        manifest = body["timeline_manifest"]
        assert len(manifest) == 2
        # Per-take duration_s=3.0 wins over scene fallback 3.0 (same in this fixture);
        # cumulative timing: 0->3, 3->6.
        assert manifest[0]["start_s"] == 0.0
        assert manifest[0]["end_s"] == 3.0
        assert manifest[1]["start_s"] == 3.0
        assert manifest[1]["end_s"] == 6.0
        for entry in manifest:
            assert set(entry.keys()) == {
                "shot_id", "scene_id", "start_s", "end_s",
                "approved_take_id", "take_count",
            }


# ---------------------------------------------------------------------------
# /screening/approve happy & error paths
# ---------------------------------------------------------------------------


class TestScreeningApproveEndpoint:
    def test_project_not_found_returns_404(self, client, flag_on):
        with patch("project_manager.mutate_project", return_value=None):
            resp = client.post("/api/projects/missing-pid/screening/approve")
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "Project not found"

    def test_happy_path_sets_flag_and_returns_200(self, client, flag_on):
        # Use a real-like fake mutate that returns the mutator's MutationResult value.
        project_state = {"id": "proj-approve"}

        def fake_mutate(pid, mutator_fn, timeout=10, snapshot=None):
            result = mutator_fn(project_state)
            from project_manager import MutationResult
            if isinstance(result, MutationResult):
                return result.value
            return result

        with patch("project_manager.mutate_project", side_effect=fake_mutate):
            resp = client.post("/api/projects/proj-approve/screening/approve")

        assert resp.status_code == 200, resp.data
        body = resp.get_json()
        assert body["success"] is True
        assert body["screening_approved"] is True
        assert project_state.get("screening_approved") is True

    def test_does_not_busy_fence(self, client, flag_on):
        # If /screening/approve busy-fenced, a pipeline polling the SCREENING
        # gate could never get approved -- deadlock. Verify the endpoint
        # ignores _running_pipelines membership.
        from web_server import _running_pipelines
        pid = "proj-busy-approve"
        _running_pipelines[pid] = object()
        try:
            with patch("project_manager.mutate_project", return_value={
                "success": True, "screening_approved": True,
            }):
                resp = client.post(f"/api/projects/{pid}/screening/approve")
        finally:
            _running_pipelines.pop(pid, None)
        # 200, NOT 409 project_busy.
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True

    def test_signals_running_pipeline_gate_when_present(self, client, flag_on):
        # Inject a fake pipeline whose lifecycle has signal_gate; verify
        # that the endpoint calls it after the mutation lands.
        from web_server import _running_pipelines

        fake_lifecycle = MagicMock()
        fake_pipeline = MagicMock()
        fake_pipeline.lifecycle = fake_lifecycle

        pid = "proj-signal"
        _running_pipelines[pid] = fake_pipeline
        try:
            with patch("project_manager.mutate_project", return_value={
                "success": True, "screening_approved": True,
            }):
                resp = client.post(f"/api/projects/{pid}/screening/approve")
        finally:
            _running_pipelines.pop(pid, None)

        assert resp.status_code == 200
        fake_lifecycle.signal_gate.assert_called_once_with("SCREENING")

    def test_no_signal_when_no_pipeline_running(self, client, flag_on):
        # A project with no live pipeline (operator approved before the
        # pipeline reached SCREENING) is a silent no-op for signal_gate.
        # The mutation still applies; the endpoint returns 200.
        with patch("project_manager.mutate_project", return_value={
            "success": True, "screening_approved": True,
        }):
            resp = client.post("/api/projects/proj-cold/screening/approve")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["screening_approved"] is True

    def test_signal_gate_exception_is_swallowed(self, client, flag_on):
        # Older lifecycle implementations (NullLifecycle) may not expose
        # signal_gate -- AttributeError must NOT crash the endpoint.
        from web_server import _running_pipelines

        fake_pipeline = MagicMock()
        # Replace lifecycle with an object that raises AttributeError for signal_gate.
        bad_lifecycle = object()  # no signal_gate attribute
        fake_pipeline.lifecycle = bad_lifecycle

        pid = "proj-no-signal-method"
        _running_pipelines[pid] = fake_pipeline
        try:
            with patch("project_manager.mutate_project", return_value={
                "success": True, "screening_approved": True,
            }):
                resp = client.post(f"/api/projects/{pid}/screening/approve")
        finally:
            _running_pipelines.pop(pid, None)

        # Still 200 -- the AttributeError is the documented no-op fallback.
        assert resp.status_code == 200
