"""Checkpoint/resume regressions and R-VERIFY-TIER(B) pins found by the hardening-campaign
discovery bug-hunt (wf_13f9d2f6-f93, confirmed[18..23]).

BUG CLASS: CheckpointStore._save_checkpoint / _restore_from_checkpoint round-trip loses
or ignores state, so a resumed run either silently re-does paid work, loads the wrong
project without detecting it, or starts from an empty progress pointer despite a rich
checkpoint on disk.

CATALOG (cinema/checkpoint.py):
  confirmed[18] W2:MAJOR:ckpt-sceneidx-dead        :87,97,178
  confirmed[19] W2:MEDIUM:ckpt-shotaudio-loss       :87-115
  confirmed[20] W2:MEDIUM:ckpt-projectid-nocrosscheck :93
  confirmed[21] Wdefer:MINOR:ckpt-nan-json-token    :110
  confirmed[22] Wdefer:MINOR:ckpt-sceneclips-dead   :98,172
  confirmed[23] Wdefer:MINOR:ckpt-stage-notrestored :94-96

Fixed sites stay here as ordinary regression tests. Deferred sites remain
strict xfail pins until their production fixes land.
"""

from __future__ import annotations

import json
import math
import os
import types
import unittest.mock as mock

import pytest

# ---------------------------------------------------------------------------
# Helpers — build a minimal CheckpointStore from scratch without a real
# PipelineCore or LifecycleService (both are constructor params but only their
# attributes are accessed during save/restore).
# ---------------------------------------------------------------------------


def _make_store(tmp_path, runstate, project_id="proj-1"):
    """Return a CheckpointStore wired to *runstate* and *tmp_path*."""
    from cinema.checkpoint import CheckpointStore
    from cinema.runstate import RunState  # noqa: F401 (ensure importable)

    # Minimal core stub: only .project["id"] and .temp_dir are read.
    core = types.SimpleNamespace(
        project={"id": project_id, "scenes": []},
        temp_dir=str(tmp_path),
    )

    # Minimal lifecycle stub: only .report_progress is called.
    lifecycle = types.SimpleNamespace(
        report_progress=lambda *a, **k: None,
    )

    return CheckpointStore(core, lifecycle, runstate)


# ---------------------------------------------------------------------------
# confirmed[18] W2:MAJOR:ckpt-sceneidx-dead
# completed_scene_indices is saved/restored by the checkpoint layer and must be
# populated by the runtime completion hook so resume_info reports real progress
# and resume can skip already-completed scene work.
#
# This regression exercises the SAVE side of the runtime hook: call
# _save_checkpoint(completed_scene_idx=0), restore, and assert that the completed
# scene index survives.
# ---------------------------------------------------------------------------


def test_ckpt_sceneidx_populated_at_runtime(tmp_path):
    """completed_scene_indices must be non-empty after a scene completes so that
    a subsequent save/restore round-trip carries the right count to resume_info."""
    from cinema.runstate import RunState

    rs = RunState()
    store = _make_store(tmp_path, rs)

    # Simulate a scene completing through the checkpoint hook that pipeline
    # code can call after finishing scene index 0.

    store._save_checkpoint(completed_scene_idx=0)

    # Restore into a fresh runstate.
    rs2 = RunState()
    store2 = _make_store(tmp_path, rs2)
    store2._restore_from_checkpoint()

    assert len(rs2.completed_scene_indices) == 1, (
        "completed_scene_indices must survive a checkpoint round-trip "
        "after the scene-completion checkpoint hook records an index"
    )


# ---------------------------------------------------------------------------
# confirmed[19] W2:MEDIUM:ckpt-shotaudio-loss
# RunState.shot_audio (per-shot TTS cache, dict[str, str]) must be included in
# the checkpoint state so individual-shot TTS outputs can be reused after resume.
# ---------------------------------------------------------------------------


def test_ckpt_shotaudio_survives_round_trip(tmp_path):
    """shot_audio must survive a save/restore round-trip."""
    from cinema.runstate import RunState

    rs = RunState()
    rs.shot_audio = {"shot-1": "/audio/shot1.wav", "shot-2": "/audio/shot2.wav"}
    store = _make_store(tmp_path, rs)
    store._save_checkpoint()

    rs2 = RunState()
    store2 = _make_store(tmp_path, rs2)
    store2._restore_from_checkpoint()

    assert rs2.shot_audio == {"shot-1": "/audio/shot1.wav", "shot-2": "/audio/shot2.wav"}, (
        "shot_audio must survive a checkpoint round-trip"
    )


# ---------------------------------------------------------------------------
# confirmed[20] W2:MEDIUM:ckpt-projectid-nocrosscheck
# project_id is saved and _restore_from_checkpoint must compare it to the
# current project. A checkpoint from project A must not silently restore into a
# run for project B.
#
# The FIXED behaviour: restoring a checkpoint whose project_id != the current
# project raises ValueError (or similar) before corrupting the runstate.
#
# Seam check: _restore_from_checkpoint accepts no arguments and reads project
# from self._core.project.  We can exercise the mismatch by creating a store
# whose core.project["id"] differs from what was saved.
# ---------------------------------------------------------------------------


def test_ckpt_projectid_crosscheck_on_restore(tmp_path):
    """Restoring a checkpoint whose project_id differs from the current project
    must raise rather than silently loading the mismatched state."""
    from cinema.runstate import RunState

    # Save a checkpoint for project-A.
    rs_a = RunState()
    rs_a.shot_results = {"shot-1": {"status": "done", "image": None, "video": None}}
    store_a = _make_store(tmp_path, rs_a, project_id="project-A")
    store_a._save_checkpoint()

    # Now try to restore that checkpoint while running project-B.
    rs_b = RunState()
    store_b = _make_store(tmp_path, rs_b, project_id="project-B")

    with pytest.raises((ValueError, RuntimeError, AssertionError)):
        store_b._restore_from_checkpoint()


# ---------------------------------------------------------------------------
# confirmed[21] Wdefer:MINOR:ckpt-nan-json-token
# json.dump(..., default=str) does NOT guard NaN/Infinity: Python's json module
# serialises float('nan') as the non-standard token `NaN` even with default=str
# because the default= hook is only called for types that are not natively
# serialisable (float IS natively handled, wrongly, before default fires).
# The resulting file fails strict JSON parsers and may corrupt the checkpoint.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Wdefer:MINOR:ckpt-nan-json-token cinema/checkpoint.py:110 "
        "json.dump(default=str) does NOT prevent NaN/Infinity from being written as "
        "non-standard JSON tokens (Python json bypasses default= for floats). "
        "Fix = use a custom encoder that maps nan/inf to null before serialisation; "
        "then this xpasses (strict)."
    ),
)
def test_ckpt_nan_not_written_as_nonstandard_token(tmp_path):
    """A checkpoint containing NaN in shot_results must serialise to valid JSON
    (no literal NaN/Infinity/nan token in the file)."""
    from cinema.runstate import RunState

    rs = RunState()
    # Inject a NaN identity score — realistic: ArcFace returns nan on failure.
    rs.shot_results = {"shot-1": {"status": "done", "identity_score": float("nan")}}
    store = _make_store(tmp_path, rs)
    store._save_checkpoint()

    ckpt_path = os.path.join(str(tmp_path), "pipeline_state.json")
    raw = open(ckpt_path, "r", encoding="utf-8").read()

    # Non-standard tokens that strict parsers reject.
    bad_tokens = ("NaN", "Infinity", "-Infinity", "nan", "inf", "-inf")
    found = [t for t in bad_tokens if t in raw]
    assert not found, (
        f"Checkpoint file contains non-standard JSON token(s) {found!r}; "
        "the file is not valid JSON and will be rejected by strict parsers on resume."
    )

    # Also verify the file round-trips through strict json.loads.
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        pytest.fail(f"Checkpoint is not valid JSON: {exc}")


# ---------------------------------------------------------------------------
# confirmed[22] Wdefer:MINOR:ckpt-sceneclips-dead
# scene_clips IS saved and restored (lines 98, 172) but _build_scene_packages
# (cinema_pipeline.py:713) starts with `self.scene_clips = {}` unconditionally,
# so the restored dict is always thrown away before it can be used.
#
# The pin exercises the checkpoint layer: scene_clips must survive save/restore.
# The unconditional reset in _build_scene_packages is a pipeline-level defect
# that lives outside checkpoint.py, but the round-trip mechanics must be correct
# for the fix to be useful.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Wdefer:MINOR:ckpt-sceneclips-dead cinema/checkpoint.py:98,172 "
        "scene_clips is saved and restored by CheckpointStore BUT "
        "_build_scene_packages (cinema_pipeline.py:713) unconditionally resets "
        "self.scene_clips = {} so the restored value is always discarded before it "
        "can be used to skip already-assembled scenes. "
        "Fix = guard the reset behind a skip-if-already-restored flag or skip scenes "
        "whose clips are already present in the restored dict; then this xpasses (strict)."
    ),
)
def test_ckpt_sceneclips_restored_value_survives_build(tmp_path):
    """scene_clips restored from a checkpoint must not be silently discarded.

    We cannot easily call _build_scene_packages in a unit test (it walks
    real on-disk paths), so this pin exercises the round-trip contract directly:
    scene_clips set on the runstate must be the same object after restore.
    The xfail is anchored to the confirmed defect that the pipeline DISCARDS this
    restored value (pipeline:713), not to a checkpoint serialisation bug.
    """
    from cinema.runstate import RunState

    rs = RunState()
    rs.scene_clips = {"scene-1": ["/clips/s1c1.mp4", "/clips/s1c2.mp4"]}
    store = _make_store(tmp_path, rs)
    store._save_checkpoint()

    rs2 = RunState()
    store2 = _make_store(tmp_path, rs2)
    store2._restore_from_checkpoint()

    # Round-trip must succeed at the checkpoint layer.
    assert rs2.scene_clips == {"scene-1": ["/clips/s1c1.mp4", "/clips/s1c2.mp4"]}, (
        "scene_clips lost across checkpoint round-trip"
    )

    # The deeper defect: _build_scene_packages resets scene_clips unconditionally,
    # so even a perfect restore is thrown away. The fixed pipeline must check whether
    # scene_clips is already populated for a scene before rebuilding it. We document
    # this here as the actual production-reachable consequence; the assertion above
    # catches any regression in the checkpoint layer itself.
    # (Assert the FIXED pipeline behaviour: restored clips are not discarded.)
    from cinema_pipeline import CinemaPipeline  # type: ignore[import]

    # Verify the defect at source: line 713 resets unconditionally.
    import inspect
    src = inspect.getsource(CinemaPipeline._build_scene_packages)
    # In the fixed world this line would be gone or gated.
    assert "self.scene_clips = {}" not in src, (
        "_build_scene_packages unconditionally resets scene_clips (pipeline:713), "
        "discarding any value restored from checkpoint — this is the confirmed defect"
    )


# ---------------------------------------------------------------------------
# confirmed[23] Wdefer:MINOR:ckpt-stage-notrestored
# current_stage, current_scene_id, current_shot_id are saved (lines 94-96)
# but _restore_from_checkpoint does NOT write them back into the runstate.
# After a resume the progress pointer triple is always ("", "", "") regardless
# of where the pipeline was interrupted.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Wdefer:MINOR:ckpt-stage-notrestored cinema/checkpoint.py:94-96 "
        "current_stage / current_scene_id / current_shot_id are saved but NOT "
        "restored in _restore_from_checkpoint so the progress pointer triple is "
        "always ('', '', '') after a resume, breaking stage-aware resume logic and "
        "UI status display. "
        "Fix = add the three assignments in _restore_from_checkpoint; "
        "then this xpasses (strict)."
    ),
)
def test_ckpt_stage_progress_pointer_restored(tmp_path):
    """current_stage/current_scene_id/current_shot_id must survive a round-trip."""
    from cinema.runstate import RunState

    rs = RunState()
    rs.current_stage = "MOTION"
    rs.current_scene_id = "scene-2"
    rs.current_shot_id = "shot-5"
    store = _make_store(tmp_path, rs)
    store._save_checkpoint()

    rs2 = RunState()
    store2 = _make_store(tmp_path, rs2)
    store2._restore_from_checkpoint()

    assert rs2.current_stage == "MOTION", (
        f"current_stage not restored (got {rs2.current_stage!r})"
    )
    assert rs2.current_scene_id == "scene-2", (
        f"current_scene_id not restored (got {rs2.current_scene_id!r})"
    )
    assert rs2.current_shot_id == "shot-5", (
        f"current_shot_id not restored (got {rs2.current_shot_id!r})"
    )
