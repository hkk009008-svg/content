"""tests/unit/test_pipeline_state_authority.py -- Slice 8a backend action authority.

Covers the additive fields ``GET /api/projects/<pid>/pipeline-state`` gained
in Slice 8a of the 2026-07-30 comprehensive-product-unification plan
(docs/superpowers/plans/2026-07-30-comprehensive-product-unification.md,
plan slice 8):

  running: bool               -- derived from the SAME _running_pipelines /
                                  _PIPELINE_PENDING registry that gates
                                  /generate, /cancel, /pause, /resume.
                                  Transport/SSE connectivity is never
                                  consulted.
  allowed_actions: list[str]  -- subset of {"start", "cancel", "pause",
                                  "resume"} legal for pid's CURRENT state,
                                  computed rather than hardcoded.

State matrix (deliberately kept in one file/test per the "assert against
DIFFERENT states" pin -- a hardcoded allowed_actions value cannot satisfy
all four):

  idle          -- pid absent from _running_pipelines -> running=False, ["start"]
  pending-start -- _PIPELINE_PENDING sentinel present  -> running=True,  []
  running       -- real pipeline object, not paused    -> running=True,  ["cancel", "pause"]
  paused        -- real pipeline object, paused         -> running=True,  ["cancel", "resume"]

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
    touches: ``.paused`` (read by ``_pipeline_action_authority``) and
    ``.get_state()`` (the legacy response shape). Mirrors the
    ``RunningPipeline``/``StubPipeline`` shape already used in
    tests/unit/test_project_persistence.py.
    """

    def __init__(self, paused: bool = False, cancelled: bool = False):
        self.paused = paused
        self.cancelled = cancelled

    def get_state(self) -> dict:
        return {
            "paused": self.paused,
            "cancelled": self.cancelled,
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
        }


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
    }


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
