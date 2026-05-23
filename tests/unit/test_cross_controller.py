"""Cross-controller integration tests.

V1.1 #1 of REFACTOR_HANDOFF.md. Formalizes the verification template
from Lesson 8.17: exercise the controller call chains end-to-end with
a shared RunState + a host that satisfies all three ControllerHost
protocols.

Why this test exists
====================

Slice 2 (commit 11e5795) dropped ShotControllerMixin from
CinemaPipeline's base list. Public method delegates were added on
CinemaPipeline, but 2 private cross-mixin helpers (_find_take +
_mutate_shot) were NOT delegated. The result: every call chain
through ReviewControllerMixin.X -> self._find_take silently broke
with AttributeError on first invocation. The bug survived 8 commits
because:

  - The §0 smoke can't runtime-import cinema_pipeline.py on 3.9
    (PEP 604).
  - The Slice 2-I behavioral check used a StubHost with
    _resolve_take_path stubbed -- exercising ShotController in
    isolation, never the real cross-controller chain.
  - The Slice 2 structural AST checks verified delegate presence
    but not the call graph.

Caught in Phase 0.5 (f9c575c) by behavioral testing.

This file ensures that future composition slices can't ship a
similar silent break. Each test exercises a specific cross-controller
chain that the architecture relies on.

Test design
===========

Doesn't import cinema_pipeline.py (PEP 604 issue on Python 3.9).
Instead, constructs the three standalone controllers + a TestHost
that implements all three ControllerHost protocols by delegating
cross-controller calls between the controllers it holds. This
mirrors exactly what CinemaPipeline does at runtime.

Each test creates its own ``tempfile.TemporaryDirectory()`` for
file-system-touching state (checkpoint round-trip), so the file
runs without pytest fixtures.

Run with:
  pytest tests/unit/test_cross_controller.py -v
  # OR (no pytest needed):
  python tests/unit/test_cross_controller.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import threading
import time
import traceback

# Bootstrap sys.path for standalone invocation (python tests/integration/X.py).
# Pytest sets this up via tests/conftest.py; this branch covers the
# no-pytest case. Two dirs up from this file is the project root.
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from cinema.checkpoint import CheckpointStore
from cinema.lifecycle import NullLifecycle, ThreadedLifecycle
from cinema.review.controller import ReviewController, ReviewControllerHost
from cinema.runstate import RunState
from cinema.shots.controller import ShotController, ShotControllerHost


# ---------------------------------------------------------------------------
# Test fixtures (plain functions; no pytest dependency).
# ---------------------------------------------------------------------------


class FakeCore:
    """Stand-in for PipelineCore that avoids the heavy service construction.

    We can't construct a real PipelineCore on Python 3.9 because
    vbench_evaluator has PEP 604 in function defaults. This fake
    provides the surface ShotController + ReviewController + CheckpointStore
    need from core.
    """

    def __init__(self, project: dict, project_dir: str):
        self.project = project
        self.project_dir = project_dir
        self.temp_dir = project_dir
        self.export_dir = project_dir
        # Service stubs -- cross-controller chains don't invoke these.
        # If a future test needs to exercise continuity / director / vbench,
        # swap in a real or mock.
        self.continuity = None
        self.director = None
        self.vbench = None
        self.cost_tracker = None
        self.ensemble = None


class WiredHost:
    """Implements all three ControllerHost protocols.

    The cross-controller calls (ReviewController._resolve_take_path ->
    host._find_take -> ShotController._find_take) work because WiredHost
    holds references to all three controllers and forwards each call to
    the right one. This is the exact composition CinemaPipeline does
    at runtime, minus the orchestration loop.
    """

    def __init__(self, core: FakeCore, lifecycle, runstate: RunState):
        self._core = core
        self._lifecycle = lifecycle
        self._runstate = runstate
        # Three controllers, all sharing the same runstate.
        self._shot_ctrl = ShotController(core, lifecycle, self, runstate)
        self._review_ctrl = ReviewController(core, lifecycle, self, runstate)
        self._checkpoint = CheckpointStore(core, lifecycle, runstate)

    # -- ShotControllerHost surface --
    def _refresh_project_snapshot(self, timeout: float = 10):
        return None  # no-op for tests

    def _rebuild_review_clips(self, project=None):
        return self._review_ctrl._rebuild_review_clips(project)

    def _candidate_take(self, shot):
        return self._review_ctrl._candidate_take(shot)

    def _resolve_take_path(self, shot, take_id):
        return self._review_ctrl._resolve_take_path(shot, take_id)

    def _latest_take(self, shot, collection_name):
        return self._review_ctrl._latest_take(shot, collection_name)

    def _save_checkpoint(self, completed_scene_idx: int = -1):
        return self._checkpoint._save_checkpoint(completed_scene_idx)

    def _ensure_scene_audio(self, scene, characters):
        return None  # AudioPhase concern; not exercised here

    # -- ReviewControllerHost surface --
    def _find_take(self, shot, take_id):
        return self._shot_ctrl._find_take(shot, take_id)

    def _mutate_shot(self, shot_id, mutator, timeout: float = 10):
        return self._shot_ctrl._mutate_shot(shot_id, mutator, timeout)

    def resume(self):
        self._lifecycle.resume()


def _sample_project(tmpdir: str) -> dict:
    """Return a minimal but realistic project dict for the tests."""
    return {
        "id": "test_project",
        "global_settings": {},
        "scenes": [
            {
                "id": "sc1",
                "shots": [
                    {
                        "id": "sh1",
                        "plan_status": "approved",
                        "keyframe_takes": [
                            {
                                "id": "tk_kf_1", "kind": "keyframe",
                                "path": os.path.join(tmpdir, "kf1.jpg"),
                                "source_take_id": "", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "motion_takes": [
                            {
                                "id": "tk_m_1", "kind": "motion",
                                "path": os.path.join(tmpdir, "m1.mp4"),
                                "source_take_id": "tk_kf_1", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "postprocess_variants": [],
                        "approved_keyframe_take_id": "tk_kf_1",
                        "approved_final_take_id": "",
                    },
                    {
                        "id": "sh2",
                        "plan_status": "approved",
                        "keyframe_takes": [],
                        "motion_takes": [],
                        "postprocess_variants": [],
                        "approved_keyframe_take_id": "",
                        "approved_final_take_id": "",
                    },
                ],
            }
        ],
        "characters": [],
        "locations": [],
    }


def _make_setup(tmpdir: str, lifecycle=None):
    """Build (core, runstate, host) for a test in the given tmpdir."""
    # Touch take asset files so file-existence checks pass.
    open(os.path.join(tmpdir, "kf1.jpg"), "w").close()
    open(os.path.join(tmpdir, "m1.mp4"), "w").close()

    project = _sample_project(tmpdir)
    core = FakeCore(project, tmpdir)
    if lifecycle is None:
        lifecycle = NullLifecycle()
    runstate = RunState()
    host = WiredHost(core, lifecycle, runstate)
    return host, runstate, core, lifecycle


def _richer_project(tmpdir: str) -> dict:
    """A larger project dict for branch-coverage tests (approve_take,
    PERFORMANCE_REVIEW gate, postprocess chain walks).

    Distinct from _sample_project (which the original 10 wiring tests
    depend on -- mutating it would break them). Layout:

      sc1/
        sh1: keyframe approved, motion + postprocess chain (variant_b ->
             variant_a -> motion -> keyframe). Used for `final` approval
             walk-the-chain tests.
        sh2: keyframe approved, performance_engine = "ACT_ONE" with one
             performance take. Used for `performance` approval tests.
        sh3: performance_engine = "SKIP" -- the gate predicate's
             skip-bypass branch.
        sh4: no keyframe approved -- the gate predicate's "no keyframe"
             bypass branch.
        sh5: keyframe approved + performance_engine = "ACT_ONE" but NO
             approved_performance_take_id -- triggers the
             "needs unapproved" branch of PERFORMANCE_REVIEW.
        sh6: synthetic postprocess loop (loop_a.source = loop_b,
             loop_b.source = loop_a) for visited-set guard test.

    All shots have plan_status = "approved" so PLAN_REVIEW is satisfied
    by default; individual tests toggle other fields as needed.
    """
    return {
        "id": "richer_project",
        "global_settings": {},
        "scenes": [
            {
                "id": "sc1",
                "shots": [
                    {
                        "id": "sh1",
                        "plan_status": "approved",
                        "performance_engine": "SKIP",
                        "keyframe_takes": [
                            {
                                "id": "tk_kf_1", "kind": "keyframe",
                                "path": os.path.join(tmpdir, "kf1.jpg"),
                                "source_take_id": "", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "motion_takes": [
                            {
                                "id": "tk_m_1", "kind": "motion",
                                "path": os.path.join(tmpdir, "m1.mp4"),
                                "source_take_id": "tk_kf_1", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "postprocess_variants": [
                            {
                                "id": "tk_pv_a", "kind": "postprocess",
                                "path": os.path.join(tmpdir, "pv_a.mp4"),
                                "source_take_id": "tk_m_1", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                            {
                                "id": "tk_pv_b", "kind": "postprocess",
                                "path": os.path.join(tmpdir, "pv_b.mp4"),
                                "source_take_id": "tk_pv_a", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "performance_takes": [],
                        "approved_keyframe_take_id": "tk_kf_1",
                        "approved_performance_take_id": "",
                        "approved_motion_take_id": "",
                        "approved_final_take_id": "",
                    },
                    {
                        "id": "sh2",
                        "plan_status": "approved",
                        "performance_engine": "ACT_ONE",
                        "keyframe_takes": [
                            {
                                "id": "tk_kf_2", "kind": "keyframe",
                                "path": os.path.join(tmpdir, "kf2.jpg"),
                                "source_take_id": "", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "motion_takes": [],
                        "postprocess_variants": [],
                        "performance_takes": [
                            {
                                "id": "tk_perf_2", "kind": "performance",
                                "path": os.path.join(tmpdir, "perf2.mp4"),
                                "source_take_id": "tk_kf_2", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "approved_keyframe_take_id": "tk_kf_2",
                        "approved_performance_take_id": "tk_perf_2",
                        "approved_motion_take_id": "",
                        "approved_final_take_id": "",
                    },
                    {
                        "id": "sh3",
                        "plan_status": "approved",
                        "performance_engine": "SKIP",
                        "keyframe_takes": [
                            {
                                "id": "tk_kf_3", "kind": "keyframe",
                                "path": os.path.join(tmpdir, "kf3.jpg"),
                                "source_take_id": "", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "motion_takes": [],
                        "postprocess_variants": [],
                        "performance_takes": [],
                        "approved_keyframe_take_id": "tk_kf_3",
                        "approved_performance_take_id": "",
                        "approved_motion_take_id": "",
                        "approved_final_take_id": "",
                    },
                    {
                        "id": "sh4",
                        "plan_status": "approved",
                        "performance_engine": "ACT_ONE",
                        "keyframe_takes": [
                            {
                                "id": "tk_kf_4", "kind": "keyframe",
                                "path": os.path.join(tmpdir, "kf4.jpg"),
                                "source_take_id": "", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "motion_takes": [],
                        "postprocess_variants": [],
                        "performance_takes": [],
                        "approved_keyframe_take_id": "",   # NOT approved
                        "approved_performance_take_id": "",
                        "approved_motion_take_id": "",
                        "approved_final_take_id": "",
                    },
                    {
                        "id": "sh5",
                        "plan_status": "approved",
                        "performance_engine": "ACT_ONE",
                        "keyframe_takes": [
                            {
                                "id": "tk_kf_5", "kind": "keyframe",
                                "path": os.path.join(tmpdir, "kf5.jpg"),
                                "source_take_id": "", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "motion_takes": [],
                        "postprocess_variants": [],
                        "performance_takes": [
                            {
                                "id": "tk_perf_5", "kind": "performance",
                                "path": os.path.join(tmpdir, "perf5.mp4"),
                                "source_take_id": "tk_kf_5", "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "approved_keyframe_take_id": "tk_kf_5",
                        "approved_performance_take_id": "",  # needs review
                        "approved_motion_take_id": "",
                        "approved_final_take_id": "",
                    },
                    {
                        "id": "sh6",
                        "plan_status": "approved",
                        "performance_engine": "SKIP",
                        "keyframe_takes": [],
                        "motion_takes": [],
                        "postprocess_variants": [
                            {
                                # synthetic loop: loop_a.source -> loop_b
                                "id": "tk_loop_a", "kind": "postprocess",
                                "path": os.path.join(tmpdir, "loop_a.mp4"),
                                "source_take_id": "tk_loop_b",
                                "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                            {
                                # loop_b.source -> loop_a (closes the cycle)
                                "id": "tk_loop_b", "kind": "postprocess",
                                "path": os.path.join(tmpdir, "loop_b.mp4"),
                                "source_take_id": "tk_loop_a",
                                "status": "generated",
                                "created_at": "", "metadata": {},
                            },
                        ],
                        "performance_takes": [],
                        "approved_keyframe_take_id": "",
                        "approved_performance_take_id": "",
                        "approved_motion_take_id": "",
                        "approved_final_take_id": "",
                    },
                ],
            }
        ],
        "characters": [],
        "locations": [],
    }


def _empty_project() -> dict:
    """Minimal valid project with zero scenes (for empty-state branch
    coverage of _gate_satisfied + _project_gate_status)."""
    return {
        "id": "empty_project",
        "global_settings": {},
        "scenes": [],
        "characters": [],
        "locations": [],
    }


@contextlib.contextmanager
def _project_on_disk(tmpdir: str, project: dict):
    """Seed `project.json` under a tmpdir-scoped PROJECTS_DIR so the
    real ``mutate_project`` path (called by ShotController._mutate_shot)
    can load/save atomically without touching the repo's `projects/`.

    The real mutation path uses ``domain.project_manager.PROJECTS_DIR``
    as a module-level constant. We monkey-patch it for the duration of
    the test, then restore. The patch is also threaded through
    ``project_manager`` (the re-export shim) and ``cinema.shots.controller``
    (in case it cached the symbol -- it imports the function, not the
    constant, so this is belt-and-suspenders).
    """
    import domain.project_manager as dpm
    fake_root = os.path.join(tmpdir, "projects")
    os.makedirs(os.path.join(fake_root, project["id"]), exist_ok=True)
    project_file = os.path.join(fake_root, project["id"], "project.json")
    with open(project_file, "w", encoding="utf-8") as f:
        json.dump(project, f)

    original = dpm.PROJECTS_DIR
    dpm.PROJECTS_DIR = fake_root
    try:
        yield project_file
    finally:
        dpm.PROJECTS_DIR = original


def _make_richer_setup(tmpdir: str, lifecycle=None):
    """Like _make_setup, but with the _richer_project fixture and
    PROJECTS_DIR monkey-patched so approve_take's disk persistence
    targets tmpdir, not the repo.

    Returns (host, runstate, core, lifecycle, patch_ctx). Caller is
    responsible for entering patch_ctx (e.g. ``with patch_ctx:``).
    The asset files referenced by _richer_project are touched here so
    file-existence checks pass.
    """
    for asset in (
        "kf1.jpg", "kf2.jpg", "kf3.jpg", "kf4.jpg", "kf5.jpg",
        "m1.mp4", "perf2.mp4", "perf5.mp4",
        "pv_a.mp4", "pv_b.mp4",
        "loop_a.mp4", "loop_b.mp4",
    ):
        open(os.path.join(tmpdir, asset), "w").close()

    project = _richer_project(tmpdir)
    core = FakeCore(project, tmpdir)
    if lifecycle is None:
        lifecycle = NullLifecycle()
    runstate = RunState()
    host = WiredHost(core, lifecycle, runstate)
    patch_ctx = _project_on_disk(tmpdir, project)
    return host, runstate, core, lifecycle, patch_ctx


def _make_empty_setup(tmpdir: str, lifecycle=None):
    """Setup with the _empty_project fixture (no scenes). No disk
    persistence is needed because the empty-project tests never call
    approve_take or any mutation path."""
    project = _empty_project()
    core = FakeCore(project, tmpdir)
    if lifecycle is None:
        lifecycle = NullLifecycle()
    runstate = RunState()
    host = WiredHost(core, lifecycle, runstate)
    return host, runstate, core, lifecycle


# ---------------------------------------------------------------------------
# Tests. Each one creates its own tmpdir so they're independently runnable.
# ---------------------------------------------------------------------------


def test_review_resolve_take_path_reaches_shot_via_host():
    """ReviewController._resolve_take_path -> host._find_take -> ShotController._find_take.

    The Slice 2 regression chain. If _find_take isn't reachable via
    host, this raises AttributeError.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _ = _make_setup(tmpdir)
        shot = core.project["scenes"][0]["shots"][0]
        path = host._review_ctrl._resolve_take_path(shot, "tk_kf_1")
        assert path.endswith("kf1.jpg"), f"unexpected path: {path!r}"


def test_review_candidate_take_walks_collections_via_host():
    """ReviewController._candidate_take falls through to host._find_take + _latest_take."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _ = _make_setup(tmpdir)
        shot = core.project["scenes"][0]["shots"][0]
        candidate = host._review_ctrl._candidate_take(shot)
        assert candidate is not None
        assert candidate["kind"] == "motion"
        assert candidate["id"] == "tk_m_1"


def test_review_rebuild_review_clips_full_chain():
    """_rebuild_review_clips internally calls _resolve_take_path +
    _candidate_take + _latest_take -- a triple host-chain exercise."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, runstate, _, _ = _make_setup(tmpdir)
        manifest = host._review_ctrl._rebuild_review_clips()
        assert "sh1" in manifest
        assert manifest["sh1"]["image"].endswith("kf1.jpg")
        assert manifest["sh1"]["video"].endswith("m1.mp4")
        assert runstate.review_clips == manifest


def test_runstate_shared_across_all_controllers():
    """V1.1 #5 invariant: mutating runstate via one controller is visible
    via every other consumer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, runstate, _, _ = _make_setup(tmpdir)
        host._shot_ctrl._runstate.shot_results["sh1"] = {"image": "/x.jpg"}
        assert host._review_ctrl._runstate.shot_results == {"sh1": {"image": "/x.jpg"}}
        assert host._checkpoint._runstate.shot_results == {"sh1": {"image": "/x.jpg"}}
        assert runstate.shot_results == {"sh1": {"image": "/x.jpg"}}


def test_update_progress_pointer_propagates():
    """RunState.update_progress_pointer mutates shared state; every
    controller sees the update."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, runstate, _, _ = _make_setup(tmpdir)
        host._shot_ctrl._runstate.update_progress_pointer("KEYFRAME", "sc1", "sh1")
        assert runstate.current_stage == "KEYFRAME"
        assert host._review_ctrl._runstate.current_scene_id == "sc1"
        assert host._checkpoint._runstate.current_shot_id == "sh1"


def test_checkpoint_round_trip_via_runstate():
    """CheckpointStore writes runstate to disk; restore reads it back.
    Tests V1.1 #5's "all state in runstate" invariant + the existing
    checkpoint contract."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, runstate, _, _ = _make_setup(tmpdir)

        runstate.shot_results = {
            "sh1": {
                "image": os.path.join(tmpdir, "kf1.jpg"),
                "video": os.path.join(tmpdir, "m1.mp4"),
                "identity_score": 0.91,
                "status": "final_review",
                "take_id": "tk_m_1",
            }
        }
        runstate.current_stage = "MOTION"
        runstate.completed_scene_indices = {0}
        runstate.failed_shots = ["sh3_failed"]

        host._checkpoint._save_checkpoint()
        assert host._checkpoint.has_checkpoint()

        info = host._checkpoint.resume_info()
        assert info["resumable"] is True
        assert info["completed_scenes"] == 1
        assert info["shots_done"] == 1
        assert info["shots_failed"] == 1

        # Reset + restore
        runstate.shot_results = {}
        runstate.failed_shots = []
        runstate.completed_scene_indices = set()
        completed = host._checkpoint._restore_from_checkpoint()
        assert completed == {0}
        assert runstate.failed_shots == ["sh3_failed"]
        assert runstate.shot_results["sh1"]["identity_score"] == 0.91


def test_gate_satisfied_predicates_use_project_state():
    """ReviewController._gate_satisfied reads project dict; predicate
    iterates the same project ReviewController got from FakeCore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _ = _make_setup(tmpdir)
        # Initial state
        assert host._review_ctrl._gate_satisfied("PLAN_REVIEW") is True
        assert host._review_ctrl._gate_satisfied("KEYFRAME_REVIEW") is False  # sh2 missing
        assert host._review_ctrl._gate_satisfied("REVIEW") is False
        # Mutate -> picked up
        core.project["scenes"][0]["shots"][1]["approved_keyframe_take_id"] = "tk_kf_2"
        assert host._review_ctrl._gate_satisfied("KEYFRAME_REVIEW") is True


def test_wait_for_gate_auto_resolves_on_predicate_satisfaction():
    """Phase 2 contract: _wait_for_gate uses lifecycle.wait_for_gate
    (predicate-poll). When predicate becomes True, gate unblocks
    without an explicit Resume click."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lifecycle = ThreadedLifecycle()
        host, _, core, _ = _make_setup(tmpdir, lifecycle=lifecycle)
        # Start with unapproved shot
        core.project["scenes"][0]["shots"][0]["plan_status"] = "pending"

        result_holder = {}
        def gate_worker():
            result_holder["out"] = host._review_ctrl._wait_for_gate("PLAN_REVIEW", "detail", 25)

        t = threading.Thread(target=gate_worker, daemon=True)
        t.start()
        time.sleep(0.2)
        assert t.is_alive(), "gate-wait should be blocking"

        # Approve all
        core.project["scenes"][0]["shots"][0]["plan_status"] = "approved"
        core.project["scenes"][0]["shots"][1]["plan_status"] = "approved"
        t.join(timeout=2.0)

        assert not t.is_alive(), "gate-wait did not return after predicate satisfied"
        assert result_holder["out"] is True


def test_wait_for_gate_returns_false_on_cancel():
    """lifecycle.cancel() causes wait_for_gate to return False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lifecycle = ThreadedLifecycle()
        host, _, core, _ = _make_setup(tmpdir, lifecycle=lifecycle)
        # Predicate won't satisfy on its own
        core.project["scenes"][0]["shots"][0]["plan_status"] = "pending"

        result_holder = {}
        def gate_worker():
            result_holder["out"] = host._review_ctrl._wait_for_gate("PLAN_REVIEW", "detail", 25)

        t = threading.Thread(target=gate_worker, daemon=True)
        t.start()
        time.sleep(0.2)
        lifecycle.cancel()
        t.join(timeout=2.0)

        assert not t.is_alive()
        assert result_holder["out"] is False


def test_host_satisfies_runtime_checkable_protocols():
    """V1.1 #3 invariant: WiredHost passes isinstance against
    @runtime_checkable host protocols. If a future protocol method
    gets added but WiredHost forgets to implement it, this fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _ = _make_setup(tmpdir)
        assert isinstance(host, ShotControllerHost)
        assert isinstance(host, ReviewControllerHost)
        # CheckpointStoreHost was deleted in V1.1 #5 (no host needed).


# ---------------------------------------------------------------------------
# _gate_satisfied branch coverage (Session 2 audited gap list)
# ---------------------------------------------------------------------------
#
# The controller's _gate_satisfied has six branches:
#   1. empty scenes -> False (no shots)
#   2. PLAN_REVIEW -> all plan_status == "approved"
#   3. KEYFRAME_REVIEW -> all approved_keyframe_take_id set
#   4. PERFORMANCE_REVIEW -> per-shot: SKIP engine OR no approved keyframe
#                            OR approved_performance_take_id set
#   5. REVIEW -> all approved_final_take_id set
#   6. unknown gate -> False
#
# The existing test_gate_satisfied_predicates_use_project_state covers
# branches 2, 3, 5 partially. These add coverage for branches 1, 4, 6
# plus deeper coverage of the others.


def test_gate_satisfied_empty_project_returns_false():
    """Branch: no shots in any scene -> False for every gate.

    Guards the `if not shots: return False` early-exit at
    cinema/review/controller.py:205-206. Without this, the `all(...)`
    over an empty iterable would vacuously return True.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _ = _make_empty_setup(tmpdir)
        assert host._review_ctrl._gate_satisfied("PLAN_REVIEW") is False
        assert host._review_ctrl._gate_satisfied("KEYFRAME_REVIEW") is False
        assert host._review_ctrl._gate_satisfied("PERFORMANCE_REVIEW") is False
        assert host._review_ctrl._gate_satisfied("REVIEW") is False


def test_gate_satisfied_plan_review_all_approved():
    """PLAN_REVIEW branch: every shot's plan_status == 'approved'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            # _richer_project ships every shot at plan_status="approved"
            assert host._review_ctrl._gate_satisfied("PLAN_REVIEW") is True


def test_gate_satisfied_plan_review_one_unapproved():
    """PLAN_REVIEW branch: a single un-approved shot flips the gate."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            core.project["scenes"][0]["shots"][2]["plan_status"] = "pending_review"
            assert host._review_ctrl._gate_satisfied("PLAN_REVIEW") is False


def test_gate_satisfied_performance_all_skip():
    """PERFORMANCE_REVIEW: when every shot has SKIP engine, gate opens
    immediately. Mirrors cinema_pipeline.py:768-773's all_skipped bypass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            # Force every shot to SKIP regardless of its other state
            for shot in core.project["scenes"][0]["shots"]:
                shot["performance_engine"] = "SKIP"
            assert host._review_ctrl._gate_satisfied("PERFORMANCE_REVIEW") is True


def test_gate_satisfied_performance_all_approved():
    """PERFORMANCE_REVIEW: all non-SKIP shots have an
    approved_performance_take_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            # Approve performance on every non-SKIP shot. SKIP shots pass
            # via the SKIP branch; "no keyframe approved" shots pass via
            # that branch. So set approvals on the rest.
            for shot in core.project["scenes"][0]["shots"]:
                engine = (shot.get("performance_engine") or "").upper()
                if engine == "SKIP":
                    continue
                if not shot.get("approved_keyframe_take_id"):
                    continue
                if not shot.get("approved_performance_take_id"):
                    shot["approved_performance_take_id"] = (
                        shot["performance_takes"][0]["id"]
                        if shot["performance_takes"]
                        else "fake_perf_id"
                    )
            assert host._review_ctrl._gate_satisfied("PERFORMANCE_REVIEW") is True


def test_gate_satisfied_performance_mixed_skip_approved_nokeyframe():
    """PERFORMANCE_REVIEW: every shot satisfies via a different branch.

    _richer_project ships:
      sh1: SKIP                                  -> branch 1
      sh2: ACT_ONE + approved_performance_take   -> branch 3
      sh3: SKIP                                  -> branch 1
      sh4: no approved keyframe                  -> branch 2
      sh5: ACT_ONE + keyframe approved, NO perf  -> FAILS (gap)
      sh6: SKIP                                  -> branch 1

    With sh5 left as-is, gate is False. Fix sh5 by setting
    approved_performance_take_id, then gate is True. This test sets
    sh5's approval to verify the mixed-branch path opens the gate.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            shots = core.project["scenes"][0]["shots"]
            shots[4]["approved_performance_take_id"] = "tk_perf_5"
            assert host._review_ctrl._gate_satisfied("PERFORMANCE_REVIEW") is True


def test_gate_satisfied_performance_one_needs_unapproved():
    """PERFORMANCE_REVIEW: a single shot needs a performance AND lacks
    approval -> gate stays False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            # sh5 ships in _richer_project as exactly this state:
            # ACT_ONE engine + keyframe approved + perf take exists +
            # approved_performance_take_id == "". All other shots are
            # already satisfied via SKIP or no-keyframe branches.
            assert host._review_ctrl._gate_satisfied("PERFORMANCE_REVIEW") is False


def test_gate_satisfied_keyframe_review_all_approved():
    """KEYFRAME_REVIEW branch: every shot has approved_keyframe_take_id
    set (truthy non-empty string).

    The existing test_gate_satisfied_predicates_use_project_state hits
    this branch on a 2-shot project. This version uses _richer_project
    (6 shots, more varied state) and stamps every shot to verify the
    `all(...)` over a larger collection lights up correctly. It also
    documents that the predicate is a truthiness check, not an existence-
    in-keyframe_takes lookup -- a stale ID after a delete still satisfies."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            for shot in core.project["scenes"][0]["shots"]:
                shot["approved_keyframe_take_id"] = "any_truthy_id"
            assert host._review_ctrl._gate_satisfied("KEYFRAME_REVIEW") is True


def test_gate_satisfied_review_all_approved():
    """REVIEW branch: every shot has approved_final_take_id set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            # Stamp every shot with a final approval (the value doesn't
            # have to be a real take_id -- the gate just checks truthiness).
            for shot in core.project["scenes"][0]["shots"]:
                shot["approved_final_take_id"] = "stamped_final"
            assert host._review_ctrl._gate_satisfied("REVIEW") is True


def test_gate_satisfied_unknown_gate_returns_false():
    """Fall-through: any gate name not in the {PLAN_REVIEW,
    KEYFRAME_REVIEW, PERFORMANCE_REVIEW, REVIEW} set -> False.

    Guards the trailing `return False` at controller.py:225 -- a typo
    in the orchestrator's gate name would otherwise hang the pipeline
    waiting for a predicate that's never True. Here the predicate is
    deterministically False so callers fail fast (or, in the case of
    _wait_for_gate, they'd block forever -- but the test isolates the
    return value, not the wait loop)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            assert host._review_ctrl._gate_satisfied("KEYFRAME_RVEIEW") is False
            assert host._review_ctrl._gate_satisfied("") is False
            assert host._review_ctrl._gate_satisfied("MOTION") is False


# ---------------------------------------------------------------------------
# approve_take branch coverage (Session 2 audited gap list)
# ---------------------------------------------------------------------------
#
# approve_take has four approval_kind arms:
#   - "keyframe"    : take must live in keyframe_takes
#   - "performance" : take must live in performance_takes
#   - "final"       : take must NOT be a keyframe; if motion, set
#                     approved_motion_take_id; if postprocess, walk
#                     source_take_id chain to find the motion ancestor
#   - else          : return "Unsupported approval kind '{kind}'"
#
# Plus two outer error branches:
#   - shot_id not found        : _mutate_shot returns None -> "Shot not found"
#   - take_id not in shot      : _find_take returns (None, None) -> "Take not found"


def test_approve_take_keyframe_in_keyframe_takes_sets_field():
    """Happy path: approving a keyframe-collection take with kind=keyframe
    sets shot.approved_keyframe_take_id and reports success."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            # Reset sh1's keyframe approval so we can verify the write
            core.project["scenes"][0]["shots"][0]["approved_keyframe_take_id"] = ""
            # ALSO clear on disk so mutate_project's load reads cleared state
            project_file = os.path.join(tmpdir, "projects", "richer_project", "project.json")
            with open(project_file, "r", encoding="utf-8") as f:
                disk = json.load(f)
            disk["scenes"][0]["shots"][0]["approved_keyframe_take_id"] = ""
            with open(project_file, "w", encoding="utf-8") as f:
                json.dump(disk, f)

            result = host._review_ctrl.approve_take("sh1", "tk_kf_1", "keyframe")
            assert "error" not in result, f"unexpected error: {result}"
            assert result["approval_kind"] == "keyframe"
            assert result["take_id"] == "tk_kf_1"
            # In-memory snapshot was synced by mutate_project
            assert core.project["scenes"][0]["shots"][0]["approved_keyframe_take_id"] == "tk_kf_1"


def test_approve_take_keyframe_in_motion_takes_errors_not_keyframe():
    """Error: approving a motion-collection take with kind=keyframe
    returns 'Take is not a keyframe'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            result = host._review_ctrl.approve_take("sh1", "tk_m_1", "keyframe")
            assert result.get("error") == "Take is not a keyframe"


def test_approve_take_performance_in_performance_takes_sets_field():
    """Happy path: approving a performance-collection take with
    kind=performance sets approved_performance_take_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            result = host._review_ctrl.approve_take("sh2", "tk_perf_2", "performance")
            assert "error" not in result, f"unexpected error: {result}"
            assert core.project["scenes"][0]["shots"][1]["approved_performance_take_id"] == "tk_perf_2"


def test_approve_take_performance_in_keyframe_takes_errors_not_performance():
    """Error: approving a keyframe-collection take with kind=performance
    returns 'Take is not a performance'.

    This branch IS reachable today because the take is in keyframe_takes
    (which _find_take does iterate), so collection_name resolves to
    'keyframe_takes' (not 'performance_takes'), triggering the error
    return."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            result = host._review_ctrl.approve_take("sh2", "tk_kf_2", "performance")
            assert result.get("error") == "Take is not a performance"


def test_approve_take_final_motion_sets_both_motion_and_final():
    """Happy path: approving a motion-collection take with kind=final
    sets BOTH approved_motion_take_id (== take_id) AND
    approved_final_take_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            result = host._review_ctrl.approve_take("sh1", "tk_m_1", "final")
            assert "error" not in result, f"unexpected error: {result}"
            sh1 = core.project["scenes"][0]["shots"][0]
            assert sh1["approved_motion_take_id"] == "tk_m_1"
            assert sh1["approved_final_take_id"] == "tk_m_1"


def test_approve_take_final_postprocess_walks_chain_to_motion():
    """Happy path: approving a postprocess-collection take with
    kind=final walks source_take_id back to the motion ancestor.

    _richer_project sh1 has chain: tk_pv_b -> tk_pv_a -> tk_m_1
    (motion). Approving tk_pv_b as final should set
    approved_motion_take_id = 'tk_m_1' and
    approved_final_take_id = 'tk_pv_b'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            result = host._review_ctrl.approve_take("sh1", "tk_pv_b", "final")
            assert "error" not in result, f"unexpected error: {result}"
            sh1 = core.project["scenes"][0]["shots"][0]
            assert sh1["approved_motion_take_id"] == "tk_m_1", (
                f"chain walk should land on tk_m_1; got {sh1['approved_motion_take_id']!r}"
            )
            assert sh1["approved_final_take_id"] == "tk_pv_b"


def test_approve_take_final_keyframe_errors():
    """Error: approving a keyframe-collection take with kind=final
    returns 'Keyframes cannot be approved as final takes'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            result = host._review_ctrl.approve_take("sh1", "tk_kf_1", "final")
            assert result.get("error") == "Keyframes cannot be approved as final takes"


def test_approve_take_unknown_kind_errors():
    """Error: any approval_kind outside {keyframe, performance, final}
    returns 'Unsupported approval kind ...'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            result = host._review_ctrl.approve_take("sh1", "tk_m_1", "draft")
            assert result.get("error") == "Unsupported approval kind 'draft'"


def test_approve_take_unknown_shot_id_returns_shot_not_found():
    """Outer error: shot_id not in any scene -> _mutate_shot returns
    None -> approve_take returns 'Shot not found'.

    Guards approve_take's tail at controller.py:335:
        return result or {"error": "Shot not found"}
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            result = host._review_ctrl.approve_take(
                "sh_does_not_exist", "tk_m_1", "final"
            )
            assert result.get("error") == "Shot not found"


def test_approve_take_unknown_take_id_returns_take_not_found():
    """Outer error: shot exists but take_id doesn't -> _find_take
    returns (None, None) -> approve_take returns 'Take not found'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            result = host._review_ctrl.approve_take("sh1", "tk_phantom", "final")
            assert result.get("error") == "Take not found"


# ---------------------------------------------------------------------------
# _project_gate_status branch coverage (Session 2 audited gap list)
# ---------------------------------------------------------------------------


def test_project_gate_status_returns_all_five_counts_for_fixture():
    """_project_gate_status returns a dict with the 5 documented count
    keys, populated from the project state.

    For _richer_project:
      - total_shots: 6 (sh1..sh6)
      - plans_approved: 6 (all default plan_status='approved')
      - keyframes_approved: 4 (sh1, sh2, sh3, sh5 have approved_keyframe_take_id)
      - performance_approved: 1 (only sh2)
      - motions_generated: 1 (only sh1 has a motion take)
      - finals_approved: 0
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            status = host._review_ctrl._project_gate_status()
            assert status == {
                "total_shots": 6,
                "plans_approved": 6,
                "keyframes_approved": 4,
                "performance_approved": 1,
                "motions_generated": 1,
                "finals_approved": 0,
            }


def test_project_gate_status_empty_project_all_zero():
    """Empty project -> every count is 0 (no scenes -> no shots ->
    sum() over empty generator)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, _, _ = _make_empty_setup(tmpdir)
        status = host._review_ctrl._project_gate_status()
        assert status == {
            "total_shots": 0,
            "plans_approved": 0,
            "keyframes_approved": 0,
            "performance_approved": 0,
            "motions_generated": 0,
            "finals_approved": 0,
        }


# ---------------------------------------------------------------------------
# _candidate_take branch coverage (Session 2 audited gap list)
# ---------------------------------------------------------------------------
#
# The existing test_review_candidate_take_walks_collections_via_host
# exercises the motion-takes fall-through. These three add:
#   - the approved_final_take_id short-circuit at the top
#   - postprocess_variants preferred over motion_takes
#   - the keyframe_takes fall-through when no motion exists


def test_candidate_take_returns_approved_final_take_when_set():
    """First branch of _candidate_take (controller.py:173-176): if the
    shot has approved_final_take_id, return that take (looked up via
    host._find_take) regardless of what's in any of the collections."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            shot = core.project["scenes"][0]["shots"][0]
            # Mark tk_m_1 as the approved final
            shot["approved_final_take_id"] = "tk_m_1"
            candidate = host._review_ctrl._candidate_take(shot)
            assert candidate is not None
            assert candidate["id"] == "tk_m_1"
            assert candidate["kind"] == "motion"


def test_candidate_take_falls_through_to_postprocess_variants():
    """Fall-through priority (controller.py:177): postprocess_variants
    is checked BEFORE motion_takes. With both present, _latest_take of
    postprocess_variants wins.

    _richer_project sh1 has postprocess_variants = [tk_pv_a, tk_pv_b];
    _latest_take returns the last entry, so tk_pv_b is the candidate.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            shot = core.project["scenes"][0]["shots"][0]
            assert not shot.get("approved_final_take_id"), (
                "fixture invariant: sh1 must NOT have an approved final "
                "or the short-circuit branch fires instead"
            )
            candidate = host._review_ctrl._candidate_take(shot)
            assert candidate is not None
            assert candidate["id"] == "tk_pv_b"
            assert candidate["kind"] == "postprocess"


def test_candidate_take_falls_through_to_keyframe_when_no_motion():
    """Fall-through last resort (controller.py:177): if neither
    postprocess_variants nor motion_takes exists, the keyframe is
    returned.

    _richer_project sh2 has only keyframe_takes + performance_takes
    (no motion, no postprocess). _candidate_take's loop should reach
    keyframe_takes and return tk_kf_2. Performance_takes is NOT in the
    loop's tuple, so it's intentionally ignored at this layer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            shot = core.project["scenes"][0]["shots"][1]  # sh2
            # Verify no approved final (short-circuit must not fire)
            assert not shot.get("approved_final_take_id")
            candidate = host._review_ctrl._candidate_take(shot)
            assert candidate is not None
            assert candidate["id"] == "tk_kf_2"
            assert candidate["kind"] == "keyframe"


# ---------------------------------------------------------------------------
# _resolve_motion_source visited-set guard (Session 2 audited gap list)
# ---------------------------------------------------------------------------


def test_resolve_motion_source_visited_set_breaks_synthetic_loop():
    """A synthetic postprocess cycle (tk_loop_a.source -> tk_loop_b,
    tk_loop_b.source -> tk_loop_a) must NOT hang _resolve_motion_source.

    Walked behavior (per controller.py:297-309):
      iter 1: current=tk_loop_b, visited={tk_loop_b}, postprocess
              -> source=tk_loop_a, current=tk_loop_a
      iter 2: current=tk_loop_a, visited={tk_loop_a, tk_loop_b}, postprocess
              -> source=tk_loop_b, current=tk_loop_b
      iter 3: current=tk_loop_b -- id IS in visited -> loop exit
              -> return ""

    Because the walk never reaches motion_takes, the returned
    motion_take_id is "" and the `if motion_take_id:` guard at
    controller.py:327 skips the approved_motion_take_id assignment.
    approved_final_take_id IS still set (always-writes path at line 329).

    This is the safety net for malformed postprocess chains. Without
    the visited set, this would infinite-loop and timeout the
    operator's approve click."""
    with tempfile.TemporaryDirectory() as tmpdir:
        host, _, core, _, patch_ctx = _make_richer_setup(tmpdir)
        with patch_ctx:
            # Approve via final on the looping variant; must return quickly
            t0 = time.monotonic()
            result = host._review_ctrl.approve_take("sh6", "tk_loop_b", "final")
            elapsed = time.monotonic() - t0

            assert elapsed < 2.0, f"approve_take hung; elapsed={elapsed:.2f}s"
            assert "error" not in result, f"unexpected error: {result}"

            sh6 = core.project["scenes"][0]["shots"][5]
            # Final IS recorded (always-writes path)
            assert sh6["approved_final_take_id"] == "tk_loop_b"
            # Motion NOT recorded (resolver returned "")
            assert sh6["approved_motion_take_id"] == "", (
                "visited-set guard should leave approved_motion_take_id "
                "empty since the chain never reaches motion_takes; got "
                f"{sh6['approved_motion_take_id']!r}"
            )


# ---------------------------------------------------------------------------
# Standalone runner (no pytest needed).
# ---------------------------------------------------------------------------


_TESTS = [
    test_review_resolve_take_path_reaches_shot_via_host,
    test_review_candidate_take_walks_collections_via_host,
    test_review_rebuild_review_clips_full_chain,
    test_runstate_shared_across_all_controllers,
    test_update_progress_pointer_propagates,
    test_checkpoint_round_trip_via_runstate,
    test_gate_satisfied_predicates_use_project_state,
    test_wait_for_gate_auto_resolves_on_predicate_satisfaction,
    test_wait_for_gate_returns_false_on_cancel,
    test_host_satisfies_runtime_checkable_protocols,
    # Session 2 -- _gate_satisfied branch coverage
    test_gate_satisfied_empty_project_returns_false,
    test_gate_satisfied_plan_review_all_approved,
    test_gate_satisfied_plan_review_one_unapproved,
    test_gate_satisfied_performance_all_skip,
    test_gate_satisfied_performance_all_approved,
    test_gate_satisfied_performance_mixed_skip_approved_nokeyframe,
    test_gate_satisfied_performance_one_needs_unapproved,
    test_gate_satisfied_keyframe_review_all_approved,
    test_gate_satisfied_review_all_approved,
    test_gate_satisfied_unknown_gate_returns_false,
    # Session 2 -- approve_take branch coverage
    test_approve_take_keyframe_in_keyframe_takes_sets_field,
    test_approve_take_keyframe_in_motion_takes_errors_not_keyframe,
    test_approve_take_performance_in_performance_takes_sets_field,
    test_approve_take_performance_in_keyframe_takes_errors_not_performance,
    test_approve_take_final_motion_sets_both_motion_and_final,
    test_approve_take_final_postprocess_walks_chain_to_motion,
    test_approve_take_final_keyframe_errors,
    test_approve_take_unknown_kind_errors,
    test_approve_take_unknown_shot_id_returns_shot_not_found,
    test_approve_take_unknown_take_id_returns_take_not_found,
    # Session 2 -- _project_gate_status branch coverage
    test_project_gate_status_returns_all_five_counts_for_fixture,
    test_project_gate_status_empty_project_all_zero,
    # Session 2 -- _candidate_take branch coverage
    test_candidate_take_returns_approved_final_take_when_set,
    test_candidate_take_falls_through_to_postprocess_variants,
    test_candidate_take_falls_through_to_keyframe_when_no_motion,
    # Session 2 -- _resolve_motion_source visited-set guard
    test_resolve_motion_source_visited_set_breaks_synthetic_loop,
]


def main() -> int:
    passed = failed = 0
    for fn in _TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
            failed += 1
    print()
    print(f"=== {passed}/{passed + failed} passed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
