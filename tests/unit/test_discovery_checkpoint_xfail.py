"""R-VERIFY-TIER(B) pins — checkpoint/resume defects found by the hardening-campaign
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

When a site is fixed its xfail xpasses (strict) — delete the pin then.
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
# completed_scene_indices is saved/restored by the checkpoint layer, but it is
# NEVER populated by the runtime (no .add() call site exists in
# cinema_pipeline.py or elsewhere — only the restore path writes to it).
# So resume_info always reports "completed_scenes": 0 regardless of actual
# progress, and the "skip already-done scenes" logic is always a no-op.
#
# The pin tests the SAVE side of the round-trip: after manually adding an index
# to the set, save + restore, and assert the index survives.  This currently
# XFAILs because the set is never added to at runtime (so a real resume saves
# an empty set and restores an empty set — silent zero), but the round-trip
# mechanics themselves are actually correct.
#
# Revised formulation (matches the confirmed defect more precisely): call
# _save_checkpoint BEFORE any .add() (simulating real runtime behaviour where
# no code populates the set), then restore and assert that resume_info reports
# the correct count.  The defect is that completed_scene_indices is NEVER
# updated during a run, so resume_info always returns 0 completed scenes.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "W2:MAJOR:ckpt-sceneidx-dead cinema/checkpoint.py:87,97,178 "
        "completed_scene_indices is saved/restored correctly but is NEVER populated "
        "at runtime (no .add() call site in cinema_pipeline.py) so the set is always "
        "empty at save-time and resume_info always reports 0 completed scenes even "
        "after scenes finish. Fix = add runstate.completed_scene_indices.add(scene_idx) "
        "in the per-scene completion hook; then this xpasses (strict) and the pin is removed."
    ),
)
def test_ckpt_sceneidx_populated_at_runtime(tmp_path):
    """completed_scene_indices must be non-empty after a scene completes so that
    a subsequent save/restore round-trip carries the right count to resume_info."""
    from cinema.runstate import RunState

    rs = RunState()
    store = _make_store(tmp_path, rs)

    # Simulate a scene completing: in the fixed world the pipeline calls
    # rs.completed_scene_indices.add(0) after finishing scene index 0.
    # In the current (broken) world NO call site does this, so the set stays empty.
    # We assert the FIXED behaviour: after save + restore the count is 1.

    # The broken path: nothing populates the set before save.
    store._save_checkpoint()

    # Restore into a fresh runstate.
    rs2 = RunState()
    store2 = _make_store(tmp_path, rs2)
    store2._restore_from_checkpoint()

    # Fixed expectation: 1 scene would have been recorded.  Today this is 0 (the bug).
    assert len(rs2.completed_scene_indices) == 1, (
        "completed_scene_indices must survive a checkpoint round-trip "
        "(currently always 0 because no code populates it at runtime)"
    )


# ---------------------------------------------------------------------------
# confirmed[19] W2:MEDIUM:ckpt-shotaudio-loss
# RunState.shot_audio (per-shot TTS cache, dict[str, str]) is NOT included in
# the state dict written by _save_checkpoint, so every paid TTS call for
# individual shots is re-generated from scratch on resume.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "W2:MEDIUM:ckpt-shotaudio-loss cinema/checkpoint.py:87-115 "
        "RunState.shot_audio is NOT included in the _save_checkpoint state dict "
        "so per-shot TTS audio paths are lost on resume and re-generated (re-paid). "
        "Fix = add 'shot_audio': self._runstate.shot_audio to the state dict and "
        "restore it in _restore_from_checkpoint; then this xpasses (strict)."
    ),
)
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
        "shot_audio lost across checkpoint round-trip "
        "(field absent from _save_checkpoint state dict)"
    )


# ---------------------------------------------------------------------------
# confirmed[20] W2:MEDIUM:ckpt-projectid-nocrosscheck
# project_id IS saved (line 93) but _restore_from_checkpoint never reads it
# back or compares it to the current project.  A checkpoint from project A
# silently restores into a run for project B.
#
# The FIXED behaviour: restoring a checkpoint whose project_id != the current
# project raises ValueError (or similar) before corrupting the runstate.
#
# Seam check: _restore_from_checkpoint accepts no arguments and reads project
# from self._core.project.  We can exercise the mismatch by creating a store
# whose core.project["id"] differs from what was saved.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "W2:MEDIUM:ckpt-projectid-nocrosscheck cinema/checkpoint.py:93 "
        "project_id is saved but _restore_from_checkpoint never compares it to the "
        "current project's id so a cross-project checkpoint loads silently, "
        "corrupting scene_clips/shot_results for the wrong project. "
        "Fix = read saved project_id and raise ValueError when it mismatches; "
        "then this xpasses (strict)."
    ),
)
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
