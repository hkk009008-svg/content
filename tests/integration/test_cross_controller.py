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
  pytest tests/integration/test_cross_controller.py -v
  # OR (no pytest needed):
  python tests/integration/test_cross_controller.py
"""

from __future__ import annotations

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
        self.quality_tracker = None
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
