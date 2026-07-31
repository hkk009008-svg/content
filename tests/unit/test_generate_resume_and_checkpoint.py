"""tests/unit/test_generate_resume_and_checkpoint.py -- Slice 11c.

Covers the two backend surfaces ``_pipeline_action_authority`` /
``GET /pipeline-state`` (tests/unit/test_pipeline_state_authority.py) does
NOT reach on its own:

  1. ``POST /generate``'s ``resume`` body flag actually threads through to
     ``CinemaPipeline.generate(resume=...)`` -- proving "start" (the
     default) never silently resumes, and "resume_checkpoint" (explicit
     ``{"resume": true}``) never silently discards the checkpoint by
     dropping the flag somewhere between the HTTP body and the pipeline
     call. This is the CONTRACT ``_pipeline_action_authority``'s two idle
     actions rely on; it was previously untested end-to-end (only the
     concurrency SENTINEL behavior was covered, in
     tests/unit/test_web_server_concurrency.py).
  2. ``POST /generate``'s already-running conflict returns 409 with
     machine-readable refresh guidance (``code``/``retryable``), the same
     shape ``_project_conflict_response`` already uses for
     ``project_busy`` elsewhere in web_server.py -- exercised for BOTH a
     stale "start" and a stale "resume_checkpoint" click, since both
     dispatch through this one endpoint.
  3. ``GET /checkpoint`` (previously had ZERO test coverage anywhere in
     the suite) -- project-not-found, no-checkpoint, and
     checkpoint-present shapes.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from unittest import mock

import pytest

import project_manager
from web_server import _PIPELINE_PENDING, _running_pipelines, app


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def real_project():
    """A real on-disk project under a disposable PROJECTS_DIR -- same
    pattern as tests/unit/test_pipeline_state_authority.py::real_project."""
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch("domain.project_manager.PROJECTS_DIR", tmp):
            yield project_manager.create_project("Generate Resume Test")


def _write_checkpoint(pid: str, **state) -> None:
    """Write a real checkpoint file into pid's own temp/ dir. Must run
    while real_project's PROJECTS_DIR patch is still active."""
    from domain.project_manager import get_project_dir

    path = os.path.join(get_project_dir(pid), "temp", "pipeline_state.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)


class _RecordingFakePipeline:
    """Records the exact ``resume`` kwarg api_generate's background
    thread calls ``.generate(resume=...)`` with, then signals ``done`` so
    the test can synchronize on the REAL threading.Thread web_server
    launches (no need to inspect internals or poll)."""

    def __init__(self, calls: list, done: threading.Event):
        self._calls = calls
        self._done = done

    def __call__(self, _pid, core=None, progress_callback=None):
        return self

    def generate(self, resume: bool = False) -> str:
        self._calls.append(resume)
        self._done.set()
        return "done"

    def cancel(self) -> None:
        pass


# ---------------------------------------------------------------------------
# POST /generate -- the resume flag actually threads through
# ---------------------------------------------------------------------------

def test_generate_with_no_body_threads_resume_false(client, real_project):
    """"start": an unqualified POST (no body at all, matching today's
    AppShell "Generate" button) must reach the pipeline with
    resume=False -- it must NOT silently continue a stale checkpoint."""
    pid = real_project["id"]
    calls: list = []
    done = threading.Event()
    fake = _RecordingFakePipeline(calls, done)

    with mock.patch("web_server.CinemaPipeline", fake), \
         mock.patch("web_server._get_or_build_core", return_value=mock.MagicMock()):
        resp = client.post(f"/api/projects/{pid}/generate")

        assert resp.status_code == 200
        assert resp.get_json()["resume"] is False
        assert done.wait(timeout=3.0), "background thread never reached generate()"

    assert calls == [False]


def test_generate_with_resume_false_body_threads_resume_false(client, real_project):
    """Explicit {"resume": false} (the "start new" choice when a
    checkpoint exists) behaves identically to an absent body."""
    pid = real_project["id"]
    calls: list = []
    done = threading.Event()
    fake = _RecordingFakePipeline(calls, done)

    with mock.patch("web_server.CinemaPipeline", fake), \
         mock.patch("web_server._get_or_build_core", return_value=mock.MagicMock()):
        resp = client.post(f"/api/projects/{pid}/generate", json={"resume": False})

        assert resp.status_code == 200
        assert done.wait(timeout=3.0), "background thread never reached generate()"

    assert calls == [False]


def test_generate_with_resume_true_body_threads_resume_true(client, real_project):
    """"resume_checkpoint": {"resume": true} must reach the pipeline as
    resume=True -- it must NOT silently discard the on-disk checkpoint by
    dropping the flag anywhere between the HTTP body and the pipeline
    call this endpoint is the ONLY dispatch point for."""
    pid = real_project["id"]
    calls: list = []
    done = threading.Event()
    fake = _RecordingFakePipeline(calls, done)

    with mock.patch("web_server.CinemaPipeline", fake), \
         mock.patch("web_server._get_or_build_core", return_value=mock.MagicMock()):
        resp = client.post(f"/api/projects/{pid}/generate", json={"resume": True})

        assert resp.status_code == 200
        assert resp.get_json()["resume"] is True
        assert done.wait(timeout=3.0), "background thread never reached generate()"

    assert calls == [True]


# ---------------------------------------------------------------------------
# POST /generate -- stale start/resume_checkpoint conflicts return 409
# with machine-readable refresh guidance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", [None, {"resume": False}, {"resume": True}])
def test_generate_conflict_when_already_running_returns_409_with_refresh_guidance(
    client, real_project, inject_pipeline, body,
):
    """A stale click of EITHER "start" or "resume_checkpoint" (both
    dispatch through this one route) while the pid is already running
    must 409 with the same code/retryable/error shape
    _project_conflict_response gives project_busy elsewhere -- so the
    typed frontend client's existing 409 handling (web/src/lib/api.ts)
    applies uniformly, and the caller knows to refresh rather than
    assume the click had no effect."""
    pid = real_project["id"]
    inject_pipeline(pid, mock.MagicMock())

    kwargs = {"json": body} if body is not None else {}
    resp = client.post(f"/api/projects/{pid}/generate", **kwargs)

    assert resp.status_code == 409
    resp_body = resp.get_json()
    assert resp_body["code"] == "generation_in_progress"
    assert resp_body["retryable"] is True
    assert isinstance(resp_body["error"], str) and resp_body["error"]


def test_generate_conflict_does_not_replace_the_pending_sentinel(client, real_project):
    """A stale request racing the brief _PIPELINE_PENDING construction
    window also 409s (not a 500/AttributeError) and leaves the sentinel
    in place -- the busy-check runs before any pipeline object access."""
    pid = real_project["id"]
    with mock.patch.dict(_running_pipelines, {pid: _PIPELINE_PENDING}):
        resp = client.post(f"/api/projects/{pid}/generate", json={"resume": True})

    assert resp.status_code == 409
    assert resp.get_json()["code"] == "generation_in_progress"


# ---------------------------------------------------------------------------
# GET /checkpoint -- previously had zero test coverage
# ---------------------------------------------------------------------------

def test_checkpoint_route_project_not_found(client):
    resp = client.get("/api/projects/proj-checkpoint-does-not-exist/checkpoint")

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Project not found"}


def test_checkpoint_route_no_checkpoint_file(client, real_project):
    pid = real_project["id"]

    resp = client.get(f"/api/projects/{pid}/checkpoint")

    assert resp.status_code == 200
    assert resp.get_json() == {"resumable": False}


def test_checkpoint_route_with_resumable_checkpoint(client, real_project):
    pid = real_project["id"]
    _write_checkpoint(
        pid,
        completed_scene_indices=[0],
        current_stage="KEYFRAME",
        shot_results={"shot_1": {"status": "complete"}},
        failed_shots=[],
    )

    resp = client.get(f"/api/projects/{pid}/checkpoint")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "resumable": True,
        "completed_scenes": 1,
        "total_scenes": 0,
        "stage": "KEYFRAME",
        "shots_done": 1,
        "shots_failed": 0,
    }


def test_checkpoint_route_matches_pipeline_state_checkpoint_key(client, real_project):
    """GET /checkpoint and the "checkpoint" key GET /pipeline-state
    threads onto its idle branch (Slice 11c) must never disagree -- both
    read the identical cinema.services.checkpoint_info(pid)."""
    pid = real_project["id"]
    _write_checkpoint(
        pid,
        completed_scene_indices=[0, 1, 2],
        current_stage="REVIEW",
        shot_results={},
        failed_shots=[],
    )

    checkpoint_resp = client.get(f"/api/projects/{pid}/checkpoint")
    state_resp = client.get(f"/api/projects/{pid}/pipeline-state")

    assert checkpoint_resp.get_json() == state_resp.get_json()["checkpoint"]
