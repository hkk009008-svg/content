"""tests/unit/test_pipeline_state_authority.py -- backend action authority.

Covers the additive fields ``GET /api/projects/<pid>/pipeline-state`` gained
in Slice 8a of the 2026-07-30 comprehensive-product-unification plan
(docs/superpowers/plans/2026-07-30-comprehensive-product-unification.md,
plan slice 8), extended by Slice 11c with checkpoint-availability and
review-gate action authority:

  running: bool               -- derived from the SAME _running_pipelines /
                                  _PIPELINE_PENDING registry that gates
                                  /generate, /cancel, /pause, /resume.
                                  Transport/SSE connectivity is never
                                  consulted.
  allowed_actions: list[str]  -- subset of {"start", "resume_checkpoint",
                                  "cancel", "pause", "resume"} legal for
                                  pid's CURRENT state, computed rather than
                                  hardcoded.
  checkpoint: dict            -- (Slice 11c, idle branch only) the same
                                  shape GET /checkpoint returns
                                  (cinema.services.checkpoint_info).

State matrix (deliberately kept in one file/test per the "assert against
DIFFERENT states" pin -- a hardcoded allowed_actions value cannot satisfy
all of them):

  idle                  -- pid absent from _running_pipelines,
                            no resumable checkpoint on disk -> running=False, ["start"]
  idle + checkpoint      -- pid absent, checkpoint_info(pid).resumable=True
                            (Slice 11c)                     -> running=False, ["start", "resume_checkpoint"]
  pending-start          -- _PIPELINE_PENDING sentinel present  -> running=True,  []
  running                -- real pipeline object, not paused,
                            NOT at a review-gate stage      -> running=True,  ["cancel", "pause"]
  running + review gate  -- real pipeline object, not paused,
                            current_stage in _GATE_STAGES
                            (Slice 11c)                     -> running=True,  ["cancel"]
  paused                 -- real pipeline object, paused         -> running=True,  ["cancel", "resume"]

Also locks:
  - the 404 "Project not found" shape is UNCHANGED (no running/
    allowed_actions key on it -- there is no pid-scoped authority to
    report for a project that does not exist);
  - every pre-existing response field (paused, cancelled, current_stage,
    current_scene_id, current_shot_id, shot_results, failed_shots,
    scenes_completed, gate_status) still round-trips untouched
    (additive-only, both on the live-pipeline branch and the disk-snapshot
    branch);
  - an unexpected registry-entry shape (bare ``object()``, mirroring the
    bare-sentinel tolerance already established by
    ``_pipeline_at_gate_stage``) does not crash the derivation.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

import pytest

import project_manager
from web_server import _PIPELINE_PENDING, _pipeline_action_authority, app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Flask test client with testing mode enabled (matches
    tests/unit/test_screening_endpoint.py / test_reassemble_endpoint.py)."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def real_project():
    """A real on-disk project under a disposable PROJECTS_DIR.

    Both ``web_server.load_project`` and ``cinema.services.load_project``
    are names bound (via separate ``from ... import load_project``
    statements) to the identical function in ``domain.project_manager``,
    which reads ``PROJECTS_DIR`` as a module global at call time. Patching
    that one global (the pattern already used in
    tests/unit/test_project_persistence.py::ProjectPersistenceBase) is the
    single point of truth both call paths agree on -- mocking
    ``load_project`` in each importing module separately would be two
    sources of truth for one project store.
    """
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch("domain.project_manager.PROJECTS_DIR", tmp):
            yield project_manager.create_project("Pipeline State Authority Test")


class _StubPipeline:
    """Minimal pipeline stub exposing exactly what api_pipeline_state
    touches: ``.paused`` (read by ``_pipeline_action_authority``),
    ``.current_stage`` (read by ``_pipeline_at_gate_stage`` -- Slice 11c),
    and ``.get_state()`` (the legacy response shape). Mirrors the
    ``RunningPipeline``/``StubPipeline`` shape already used in
    tests/unit/test_project_persistence.py.

    ``current_stage`` defaults to "SCENE" (not a review-gate stage) so
    every pre-11c call site that doesn't care about gate behavior is
    unaffected; ``get_state()`` echoes it back exactly as the real
    ``CinemaPipeline.get_state()`` does (``"current_stage": self.current_stage``),
    so a test that sets it also sees it round-trip through the HTTP body.
    """

    def __init__(self, paused: bool = False, cancelled: bool = False, current_stage: str = "SCENE"):
        self.paused = paused
        self.cancelled = cancelled
        self.current_stage = current_stage

    def get_state(self) -> dict:
        return {
            "paused": self.paused,
            "cancelled": self.cancelled,
            "current_stage": self.current_stage,
            "current_scene_id": "scene_1",
            "current_shot_id": "shot_1",
            "shot_results": {"shot_1": {"status": "in_progress"}},
            "failed_shots": [],
            "scenes_completed": 0,
            "gate_status": {
                "total_shots": 1,
                "plans_approved": 1,
                "keyframes_approved": 0,
                "motions_generated": 0,
                "finals_approved": 0,
            },
        }


def _write_checkpoint(pid: str, **state) -> None:
    """Write a real checkpoint file into ``pid``'s own ``temp/`` dir.

    Must be called while ``real_project``'s ``PROJECTS_DIR`` patch is
    still active (i.e. from inside a test that depends on that fixture).
    Mirrors the exact file ``CheckpointStore._save_checkpoint`` persists
    (``cinema/checkpoint.py``) closely enough for
    ``cinema.services.checkpoint_info`` -- the SAME reader production
    code uses -- to report ``resumable=True`` off of it.
    """
    from domain.project_manager import get_project_dir

    path = os.path.join(get_project_dir(pid), "temp", "pipeline_state.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)


# ---------------------------------------------------------------------------
# Direct unit tests of the derivation helper -- pure function, no Flask.
# ---------------------------------------------------------------------------

def test_idle_reports_start_only_and_not_running():
    from web_server import _running_pipelines

    pid = "proj-authority-idle-unit"
    assert pid not in _running_pipelines  # sanity: genuinely idle

    running, allowed = _pipeline_action_authority(pid)

    assert running is False
    assert allowed == ["start"]


def test_pending_start_sentinel_reports_running_with_no_legal_action(inject_pipeline):
    pid = "proj-authority-pending-unit"
    inject_pipeline(pid, _PIPELINE_PENDING)

    running, allowed = _pipeline_action_authority(pid)

    assert running is True
    assert allowed == []


def test_running_not_paused_reports_cancel_and_pause(inject_pipeline):
    pid = "proj-authority-running-unit"
    inject_pipeline(pid, _StubPipeline(paused=False))

    running, allowed = _pipeline_action_authority(pid)

    assert running is True
    assert allowed == ["cancel", "pause"]


def test_paused_reports_cancel_and_resume(inject_pipeline):
    pid = "proj-authority-paused-unit"
    inject_pipeline(pid, _StubPipeline(paused=True))

    running, allowed = _pipeline_action_authority(pid)

    assert running is True
    assert allowed == ["cancel", "resume"]


def test_registry_entry_without_paused_attribute_does_not_crash(inject_pipeline):
    """Defensive parity with _pipeline_at_gate_stage's bare object()
    tolerance -- an unrecognized registry-entry shape must not crash the
    derivation. Treated as "not paused" (the branch that offers
    cancel/pause rather than asserting an unverifiable resume)."""
    pid = "proj-authority-bare-object-unit"
    inject_pipeline(pid, object())

    running, allowed = _pipeline_action_authority(pid)

    assert running is True
    assert allowed == ["cancel", "pause"]


def test_idle_with_resumable_checkpoint_adds_resume_checkpoint_action():
    """Slice 11c: an idle pid with a resumable on-disk checkpoint reports
    BOTH "start" (fresh run) and "resume_checkpoint" (continues the
    checkpoint) -- the explicit resume-vs-new-run choice."""
    pid = "proj-authority-checkpoint-idle-unit"
    fake_checkpoint = {
        "resumable": True,
        "completed_scenes": 2,
        "total_scenes": 5,
        "stage": "MOTION",
        "shots_done": 3,
        "shots_failed": 1,
    }
    with mock.patch("web_server.checkpoint_info", return_value=fake_checkpoint) as mocked:
        running, allowed = _pipeline_action_authority(pid)
        mocked.assert_called_once_with(pid)

    assert running is False
    assert allowed == ["start", "resume_checkpoint"]


def test_idle_with_non_resumable_checkpoint_reports_start_only():
    """The idle branch always consults checkpoint_info; a non-resumable
    result (no checkpoint file, or none the reader could parse) must NOT
    add "resume_checkpoint" -- exercises the explicit False branch rather
    than relying on checkpoint_info never being called."""
    pid = "proj-authority-checkpoint-absent-unit"
    with mock.patch("web_server.checkpoint_info", return_value={"resumable": False}) as mocked:
        running, allowed = _pipeline_action_authority(pid)
        mocked.assert_called_once_with(pid)

    assert running is False
    assert allowed == ["start"]


def test_running_at_review_gate_reports_cancel_only(inject_pipeline):
    """Slice 11c: a running, unpaused pipeline parked at a review-gate
    stage withholds "pause" -- it would be a legal-but-inert action since
    ThreadedLifecycle.wait_for_gate never consults check_pause()."""
    pid = "proj-authority-gate-unit"
    inject_pipeline(pid, _StubPipeline(paused=False, current_stage="PLAN_REVIEW"))

    running, allowed = _pipeline_action_authority(pid)

    assert running is True
    assert allowed == ["cancel"]


@pytest.mark.parametrize("gate_stage", ["PLAN_REVIEW", "KEYFRAME_REVIEW", "PERFORMANCE_REVIEW", "REVIEW", "SCREENING"])
def test_every_gate_stage_withholds_pause(inject_pipeline, gate_stage):
    """All five _GATE_STAGES members -- not just one -- drop "pause"."""
    pid = f"proj-authority-gate-{gate_stage.lower()}"
    inject_pipeline(pid, _StubPipeline(paused=False, current_stage=gate_stage))

    running, allowed = _pipeline_action_authority(pid)

    assert running is True
    assert allowed == ["cancel"]


def test_paused_at_review_gate_still_reports_cancel_and_resume(inject_pipeline):
    """Paused takes priority over the gate check: a paused pipeline that
    also happens to be parked at a gate stage still offers "resume" (the
    lifecycle-level unpause), not the gate-stage's narrower ["cancel"]."""
    pid = "proj-authority-paused-at-gate-unit"
    inject_pipeline(pid, _StubPipeline(paused=True, current_stage="KEYFRAME_REVIEW"))

    running, allowed = _pipeline_action_authority(pid)

    assert running is True
    assert allowed == ["cancel", "resume"]


def test_allowed_actions_differ_across_all_four_states(inject_pipeline):
    """The mutation pin required by the slice brief: assert exact expected
    values against DIFFERENT real states in one test, so a hardcoded
    ``return True, ["cancel", "pause"]`` (or any other constant) cannot
    satisfy every branch."""
    idle_pid = "proj-authority-matrix-idle"
    pending_pid = "proj-authority-matrix-pending"
    running_pid = "proj-authority-matrix-running"
    paused_pid = "proj-authority-matrix-paused"

    inject_pipeline(pending_pid, _PIPELINE_PENDING)
    inject_pipeline(running_pid, _StubPipeline(paused=False))
    inject_pipeline(paused_pid, _StubPipeline(paused=True))

    idle_result = _pipeline_action_authority(idle_pid)
    pending_result = _pipeline_action_authority(pending_pid)
    running_result = _pipeline_action_authority(running_pid)
    paused_result = _pipeline_action_authority(paused_pid)

    assert idle_result == (False, ["start"])
    assert pending_result == (True, [])
    assert running_result == (True, ["cancel", "pause"])
    assert paused_result == (True, ["cancel", "resume"])

    # Pairwise distinctness: proves the four calls above are not all
    # collapsing to the same constant return value.
    all_results = [idle_result, pending_result, running_result, paused_result]
    for i in range(len(all_results)):
        for j in range(i + 1, len(all_results)):
            assert all_results[i] != all_results[j], (
                f"states at index {i} and {j} produced identical "
                f"(running, allowed_actions) -- allowed_actions looks "
                f"hardcoded rather than derived"
            )


def test_slice_11c_states_distinct_from_the_slice_8a_four(inject_pipeline):
    """Same mutation-pin shape as test_allowed_actions_differ_across_all_four_states,
    extended with the two Slice 11c states (idle+checkpoint,
    running+review-gate) -- proves they are each their OWN distinct
    result, not accidentally collapsing onto one of the original four."""
    idle_pid = "proj-authority-matrix11c-idle"
    checkpoint_pid = "proj-authority-matrix11c-checkpoint"
    running_pid = "proj-authority-matrix11c-running"
    gate_pid = "proj-authority-matrix11c-gate"
    paused_pid = "proj-authority-matrix11c-paused"

    inject_pipeline(running_pid, _StubPipeline(paused=False))
    inject_pipeline(gate_pid, _StubPipeline(paused=False, current_stage="REVIEW"))
    inject_pipeline(paused_pid, _StubPipeline(paused=True))

    idle_result = _pipeline_action_authority(idle_pid)
    with mock.patch("web_server.checkpoint_info", return_value={"resumable": True}):
        checkpoint_result = _pipeline_action_authority(checkpoint_pid)
    running_result = _pipeline_action_authority(running_pid)
    gate_result = _pipeline_action_authority(gate_pid)
    paused_result = _pipeline_action_authority(paused_pid)

    assert idle_result == (False, ["start"])
    assert checkpoint_result == (False, ["start", "resume_checkpoint"])
    assert running_result == (True, ["cancel", "pause"])
    assert gate_result == (True, ["cancel"])
    assert paused_result == (True, ["cancel", "resume"])

    all_results = [idle_result, checkpoint_result, running_result, gate_result, paused_result]
    for i in range(len(all_results)):
        for j in range(i + 1, len(all_results)):
            assert all_results[i] != all_results[j], (
                f"states at index {i} and {j} produced identical "
                f"(running, allowed_actions) -- a Slice 11c state looks "
                f"collapsed onto a pre-existing one"
            )


# ---------------------------------------------------------------------------
# HTTP-level: GET /pipeline-state threads running/allowed_actions into the
# real JSON response, additive to every pre-existing field.
# ---------------------------------------------------------------------------

def test_http_idle_project_reports_start_only_and_keeps_legacy_fields(client, real_project):
    pid = real_project["id"]

    resp = client.get(f"/api/projects/{pid}/pipeline-state")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {
        "paused": False,
        "cancelled": False,
        "current_stage": "",
        "current_scene_id": "",
        "current_shot_id": "",
        "shot_results": {},
        "failed_shots": [],
        "scenes_completed": 0,
        "gate_status": {
            "total_shots": 0,
            "plans_approved": 0,
            "keyframes_approved": 0,
            "motions_generated": 0,
            "finals_approved": 0,
        },
        "running": False,
        "allowed_actions": ["start"],
        # Slice 11c: additive on the idle branch -- no checkpoint file
        # exists yet for a freshly created project.
        "checkpoint": {"resumable": False},
    }


def test_http_completed_project_reports_start_only_no_lingering_resume(client, real_project):
    """Slice 11c: the "completed" state in the plan's action-matrix
    acceptance criterion. A run that finishes successfully clears its own
    checkpoint (CheckpointStore._clear_checkpoint, called immediately
    before the terminal COMPLETE progress event in cinema_pipeline.py) --
    simulated here by writing then removing the checkpoint file, exactly
    what that call does. A completed project must report allowed_actions
    identical to a project that never ran: no lingering "resume_checkpoint"
    zombie action once there is truly nothing left to resume."""
    pid = real_project["id"]
    _write_checkpoint(pid, completed_scene_indices=[0, 1, 2], current_stage="COMPLETE")
    from domain.project_manager import get_project_dir
    checkpoint_path = os.path.join(get_project_dir(pid), "temp", "pipeline_state.json")
    assert os.path.exists(checkpoint_path)  # sanity: the write above landed
    os.remove(checkpoint_path)  # the exact effect of _clear_checkpoint()

    resp = client.get(f"/api/projects/{pid}/pipeline-state")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["allowed_actions"] == ["start"]
    assert "resume_checkpoint" not in body["allowed_actions"]
    assert body["checkpoint"] == {"resumable": False}


def test_http_idle_project_with_resumable_checkpoint_reports_resume_checkpoint(client, real_project):
    """Slice 11c: the "failed" state in the plan's action-matrix acceptance
    criterion -- a prior run crashed/errored (web_server.py's run_pipeline
    catches the exception, publishes ERROR, and pops the pid from
    _running_pipelines WITHOUT ever calling _clear_checkpoint, unlike the
    success path) or was cancelled/killed mid-way, leaving a real on-disk
    checkpoint behind (written the same shape
    CheckpointStore._save_checkpoint persists). That flips
    "resume_checkpoint" into allowed_actions and threads the SAME summary
    GET /checkpoint reports onto pipeline-state's "checkpoint" key -- the
    explicit resume-vs-new-run choice, end to end through the real HTTP
    route."""
    pid = real_project["id"]
    _write_checkpoint(
        pid,
        completed_scene_indices=[0, 1],
        current_stage="MOTION",
        shot_results={
            "shot_1": {"status": "complete"},
            "shot_2": {"status": "failed"},
        },
        failed_shots=["shot_2"],
    )

    resp = client.get(f"/api/projects/{pid}/pipeline-state")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["running"] is False
    assert body["allowed_actions"] == ["start", "resume_checkpoint"]
    assert body["checkpoint"] == {
        "resumable": True,
        "completed_scenes": 2,
        # real_project has no scenes yet -- total_scenes reads the
        # project's OWN scene count, independent of the checkpoint file.
        "total_scenes": 0,
        "stage": "MOTION",
        "shots_done": 1,
        "shots_failed": 1,
    }
    # Legacy disk-snapshot fields are untouched by the checkpoint file --
    # state_snapshot() never reads temp/pipeline_state.json.
    assert body["current_stage"] == ""
    assert body["paused"] is False

    # GET /checkpoint (the standalone route) reports the identical shape.
    checkpoint_resp = client.get(f"/api/projects/{pid}/checkpoint")
    assert checkpoint_resp.get_json() == body["checkpoint"]


def test_http_running_at_review_gate_reports_cancel_only(client, real_project, inject_pipeline):
    """Slice 11c: the HTTP body's own current_stage confirms which gate
    the pipeline is parked at, while allowed_actions withholds "pause"."""
    pid = real_project["id"]
    inject_pipeline(pid, _StubPipeline(paused=False, current_stage="KEYFRAME_REVIEW"))

    resp = client.get(f"/api/projects/{pid}/pipeline-state")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["running"] is True
    assert body["allowed_actions"] == ["cancel"]
    assert body["current_stage"] == "KEYFRAME_REVIEW"
    # Live-pipeline branch never gets a "checkpoint" key (Slice 11c scopes
    # it to the disk-snapshot/idle branch only).
    assert "checkpoint" not in body


def test_http_pending_start_reports_running_true_no_actions(client, real_project, inject_pipeline):
    pid = real_project["id"]
    inject_pipeline(pid, _PIPELINE_PENDING)

    resp = client.get(f"/api/projects/{pid}/pipeline-state")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["running"] is True
    assert body["allowed_actions"] == []
    # Falls through to the disk-snapshot branch (no real pipeline object
    # registered yet) -- legacy fields still present and untouched.
    assert body["paused"] is False
    assert body["cancelled"] is False
    assert "gate_status" in body


def test_http_running_pipeline_reports_cancel_and_pause(client, real_project, inject_pipeline):
    pid = real_project["id"]
    inject_pipeline(pid, _StubPipeline(paused=False))

    resp = client.get(f"/api/projects/{pid}/pipeline-state")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {
        "paused": False,
        "cancelled": False,
        "current_stage": "SCENE",
        "current_scene_id": "scene_1",
        "current_shot_id": "shot_1",
        "shot_results": {"shot_1": {"status": "in_progress"}},
        "failed_shots": [],
        "scenes_completed": 0,
        "gate_status": {
            "total_shots": 1,
            "plans_approved": 1,
            "keyframes_approved": 0,
            "motions_generated": 0,
            "finals_approved": 0,
        },
        "running": True,
        "allowed_actions": ["cancel", "pause"],
    }


def test_http_paused_pipeline_reports_cancel_and_resume(client, real_project, inject_pipeline):
    pid = real_project["id"]
    inject_pipeline(pid, _StubPipeline(paused=True))

    resp = client.get(f"/api/projects/{pid}/pipeline-state")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["running"] is True
    assert body["allowed_actions"] == ["cancel", "resume"]
    assert body["paused"] is True  # legacy field, untouched by the new keys


def test_http_404_shape_unchanged_for_unknown_project(client):
    """The 404 path is explicitly out of scope for the new fields -- no
    running/allowed_actions key belongs on a response for a project that
    does not exist."""
    resp = client.get("/api/projects/proj-does-not-exist-authority/pipeline-state")

    assert resp.status_code == 404
    assert resp.get_json() == {
        "error": "Project not found",
        "paused": False,
        "cancelled": False,
    }
