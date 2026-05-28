"""Unit tests for F2b: storyboard batch mode wired into MotionRenderPhase.

Coverage:
  (a) flag ON + eligible scene (3 shots) → generate_storyboard called once,
      3 segments finalized, cost recorded exactly ONCE for the batch (NOT 3×).
  (b) flag OFF → per-shot path: generate_motion_take called per shot,
      generate_storyboard NOT called.
  (c) ineligible scene: 1 shot → per-shot path (not storyboard).
  (d) ineligible scene: 7 shots → per-shot path (not storyboard).
  (e) generate_storyboard returns None → fallback to per-shot path.
  (f) _get_storyboard_mode reads the correct nested key.

All tests are fully offline — no real APIs, no GPU.
"""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Module-level stub injection.
#
# Some other test files (e.g. test_dialogue_routing.py) inject a bare stub
# module for 'kling_native' (no KlingNativeAPI attribute) to avoid loading
# the heavy real module.  If that stub is already in sys.modules when our
# tests run, patch("kling_native.KlingNativeAPI") raises AttributeError.
#
# Fix: ensure KlingNativeAPI exists on the cached module before tests run.
# If the module isn't loaded at all, importing the real one here (or creating
# a minimal stub) ensures patch() can find the attribute.
# ---------------------------------------------------------------------------

def _ensure_kling_native_patchable():
    """Guarantee kling_native.KlingNativeAPI exists so patch() can find it."""
    mod = sys.modules.get("kling_native")
    if mod is None:
        # Module not yet imported — create a minimal stub.
        mod = types.ModuleType("kling_native")
        mod.KlingNativeAPI = MagicMock  # type: ignore[attr-defined]
        sys.modules["kling_native"] = mod
    elif not hasattr(mod, "KlingNativeAPI"):
        # Stub was registered without the class (by another test file).
        mod.KlingNativeAPI = MagicMock  # type: ignore[attr-defined]


_ensure_kling_native_patchable()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_lifecycle(cancelled: bool = False) -> MagicMock:
    lc = MagicMock()
    lc.is_cancelled.return_value = cancelled
    return MagicMock(lifecycle=lc)


def _make_shot(shot_id: str, kf_take_id: str = "kf_001", has_final: bool = False) -> dict:
    shot = {
        "id": shot_id,
        "approved_keyframe_take_id": kf_take_id,
        "characters_in_frame": [],
        "camera": "dolly_in",
        "prompt": f"Shot {shot_id} prompt",
        "duration": 5.0,
    }
    if has_final:
        shot["approved_final_take_id"] = "final_take_xxx"
    return shot


def _make_scene(scene_id: str, shots: list) -> dict:
    return {"id": scene_id, "shots": shots}


def _make_project(
    scenes: list,
    storyboard_mode: bool = False,
) -> dict:
    return {
        "id": "proj_test",
        "scenes": scenes,
        "global_settings": {
            "api_engines": {
                "KLING_NATIVE": {
                    "storyboard_mode": storyboard_mode,
                },
            },
        },
    }


def _make_gen_mock(
    kf_paths: dict | None = None,
    motion_take_success: bool = True,
):
    """Build a mock shot_generator (stands in for CinemaPipeline).

    kf_paths: {shot_id: path} — returned by _resolve_take_path.
    """
    kf_paths = kf_paths or {}

    gen = MagicMock()
    gen._resolve_take_path.side_effect = lambda shot, take_id: kf_paths.get(
        shot.get("id", ""), "/fake/kf.jpg"
    )

    # cost_tracker
    gen.cost_tracker = MagicMock()
    gen.cost_tracker.record_api_call = MagicMock()

    # _shot_ctrl — needs _take_output_path and _finalize_motion_take
    shot_ctrl = MagicMock()
    shot_ctrl._take_output_path.return_value = "/tmp/storyboard_scene_1.mp4"
    finalize_result = {"success": True, "take": {}, "video": "/tmp/seg.mp4", "identity_score": 0.0}
    shot_ctrl._finalize_motion_take.return_value = finalize_result
    gen._shot_ctrl = shot_ctrl

    # generate_motion_take (per-shot path)
    gen.generate_motion_take.return_value = {"success": motion_take_success}

    return gen


# ---------------------------------------------------------------------------
# (f) _get_storyboard_mode unit test
# ---------------------------------------------------------------------------

class TestGetStoryboardMode:
    def test_reads_nested_key(self):
        from cinema.phases.motion_render import _get_storyboard_mode
        project = _make_project([], storyboard_mode=True)
        assert _get_storyboard_mode(project) is True

    def test_defaults_false_when_missing(self):
        from cinema.phases.motion_render import _get_storyboard_mode
        assert _get_storyboard_mode({"global_settings": {}}) is False

    def test_defaults_false_when_no_global_settings(self):
        from cinema.phases.motion_render import _get_storyboard_mode
        assert _get_storyboard_mode({}) is False

    def test_defaults_false_when_no_api_engines(self):
        from cinema.phases.motion_render import _get_storyboard_mode
        project = {"global_settings": {"api_engines": {}}}
        assert _get_storyboard_mode(project) is False

    def test_defaults_false_when_no_kling_entry(self):
        from cinema.phases.motion_render import _get_storyboard_mode
        project = {"global_settings": {"api_engines": {"KLING_NATIVE": {}}}}
        assert _get_storyboard_mode(project) is False

    def test_explicit_false(self):
        from cinema.phases.motion_render import _get_storyboard_mode
        project = _make_project([], storyboard_mode=False)
        assert _get_storyboard_mode(project) is False


# ---------------------------------------------------------------------------
# (b) flag OFF → per-shot path only
# ---------------------------------------------------------------------------

class TestFlagOff:
    def test_per_shot_path_called_for_each_shot(self, tmp_path):
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [_make_shot("s1_0"), _make_shot("s1_1"), _make_shot("s1_2")]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=False)

        kf_paths = {s["id"]: str(tmp_path / f"{s['id']}.jpg") for s in shots}
        for p in kf_paths.values():
            open(p, "w").close()

        gen = _make_gen_mock(kf_paths=kf_paths)
        phase = MotionRenderPhase(shot_generator=gen, project=project)
        ctx = _make_lifecycle()

        result = phase.run(ctx)

        assert result.ok is True
        # generate_motion_take called once per shot
        assert gen.generate_motion_take.call_count == 3
        # generate_storyboard NEVER called
        gen._shot_ctrl._finalize_motion_take.assert_not_called()
        # No batch cost recorded
        # (cost_tracker.record_api_call may be called by generate_motion_take mocks,
        #  but generate_storyboard path's explicit cost recording must not have happened
        #  via the batch path — we verify by checking _shot_ctrl._finalize was not used)

    def test_generate_storyboard_not_called_flag_off(self, tmp_path):
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [_make_shot("s1_0"), _make_shot("s1_1")]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=False)

        gen = _make_gen_mock()
        phase = MotionRenderPhase(shot_generator=gen, project=project)
        ctx = _make_lifecycle()

        with patch("kling_native.KlingNativeAPI") as mock_kling_cls:
            phase.run(ctx)
            mock_kling_cls.assert_not_called()


# ---------------------------------------------------------------------------
# (c/d) ineligible scene counts (1 shot, 7 shots) → per-shot
# ---------------------------------------------------------------------------

class TestIneligibleScenes:
    def _run_scene(self, n_shots: int, tmp_path, storyboard_mode=True):
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [_make_shot(f"s1_{i}") for i in range(n_shots)]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=storyboard_mode)

        kf_paths = {s["id"]: str(tmp_path / f"{s['id']}.jpg") for s in shots}
        for p in kf_paths.values():
            open(p, "w").close()

        gen = _make_gen_mock(kf_paths=kf_paths)
        phase = MotionRenderPhase(shot_generator=gen, project=project)
        ctx = _make_lifecycle()
        return phase.run(ctx), gen

    def test_single_shot_uses_per_shot_path(self, tmp_path):
        result, gen = self._run_scene(1, tmp_path)
        assert result.ok is True
        assert gen.generate_motion_take.call_count == 1
        gen._shot_ctrl._finalize_motion_take.assert_not_called()

    def test_seven_shots_uses_per_shot_path(self, tmp_path):
        result, gen = self._run_scene(7, tmp_path)
        assert result.ok is True
        assert gen.generate_motion_take.call_count == 7
        gen._shot_ctrl._finalize_motion_take.assert_not_called()

    def test_two_shots_triggers_storyboard_path(self, tmp_path):
        """2 shots is inside the 2–6 range — storyboard path should be attempted."""
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [_make_shot("s1_0"), _make_shot("s1_1")]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=True)

        kf_paths = {s["id"]: str(tmp_path / f"{s['id']}.jpg") for s in shots}
        for p in kf_paths.values():
            open(p, "w").close()

        gen = _make_gen_mock(kf_paths=kf_paths)

        with patch("kling_native.KlingNativeAPI") as mock_kling_cls:
            mock_kling = MagicMock()
            mock_kling.generate_storyboard.return_value = str(tmp_path / "storyboard.mp4")
            open(str(tmp_path / "storyboard.mp4"), "w").close()
            mock_kling_cls.return_value = mock_kling

            with patch("phase_c_ffmpeg.split_video_into_segments") as mock_split:
                seg_paths = [str(tmp_path / f"seg_{i}.mp4") for i in range(2)]
                for p in seg_paths:
                    open(p, "w").close()
                mock_split.return_value = seg_paths

                phase = MotionRenderPhase(shot_generator=gen, project=project)
                ctx = _make_lifecycle()
                result = phase.run(ctx)

        # Storyboard was invoked
        mock_kling.generate_storyboard.assert_called_once()
        # Per-shot generate_motion_take was NOT called
        gen.generate_motion_take.assert_not_called()
        assert result.ok is True

    def test_six_shots_triggers_storyboard_path(self, tmp_path):
        """6 shots is the max eligible — storyboard path should be attempted."""
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [_make_shot(f"s1_{i}") for i in range(6)]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=True)

        kf_paths = {s["id"]: str(tmp_path / f"{s['id']}.jpg") for s in shots}
        for p in kf_paths.values():
            open(p, "w").close()

        gen = _make_gen_mock(kf_paths=kf_paths)

        with patch("kling_native.KlingNativeAPI") as mock_kling_cls:
            mock_kling = MagicMock()
            mock_kling.generate_storyboard.return_value = str(tmp_path / "storyboard.mp4")
            open(str(tmp_path / "storyboard.mp4"), "w").close()
            mock_kling_cls.return_value = mock_kling

            with patch("phase_c_ffmpeg.split_video_into_segments") as mock_split:
                seg_paths = [str(tmp_path / f"seg_{i}.mp4") for i in range(6)]
                for p in seg_paths:
                    open(p, "w").close()
                mock_split.return_value = seg_paths

                phase = MotionRenderPhase(shot_generator=gen, project=project)
                ctx = _make_lifecycle()
                result = phase.run(ctx)

        mock_kling.generate_storyboard.assert_called_once()
        gen.generate_motion_take.assert_not_called()
        assert result.ok is True


# ---------------------------------------------------------------------------
# (a) main storyboard happy path
# ---------------------------------------------------------------------------

class TestStoryboardHappyPath:
    def _run_storyboard(self, n_shots: int, tmp_path):
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [_make_shot(f"s1_{i}") for i in range(n_shots)]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=True)

        kf_paths = {s["id"]: str(tmp_path / f"{s['id']}.jpg") for s in shots}
        for p in kf_paths.values():
            open(p, "w").close()

        gen = _make_gen_mock(kf_paths=kf_paths)
        storyboard_path = str(tmp_path / "combined.mp4")
        seg_paths = [str(tmp_path / f"seg_{i}.mp4") for i in range(n_shots)]
        for p in seg_paths:
            open(p, "w").close()

        with patch("kling_native.KlingNativeAPI") as mock_kling_cls:
            mock_kling = MagicMock()
            mock_kling.generate_storyboard.return_value = storyboard_path
            open(storyboard_path, "w").close()
            mock_kling_cls.return_value = mock_kling

            with patch("phase_c_ffmpeg.split_video_into_segments") as mock_split:
                mock_split.return_value = seg_paths

                phase = MotionRenderPhase(shot_generator=gen, project=project)
                ctx = _make_lifecycle()
                result = phase.run(ctx)

        return result, gen, mock_kling, mock_split, seg_paths, storyboard_path

    def test_generate_storyboard_called_once(self, tmp_path):
        result, gen, mock_kling, mock_split, seg_paths, sb_path = self._run_storyboard(3, tmp_path)
        assert result.ok is True
        mock_kling.generate_storyboard.assert_called_once()

    def test_n_segments_finalized(self, tmp_path):
        n = 3
        result, gen, mock_kling, mock_split, seg_paths, sb_path = self._run_storyboard(n, tmp_path)
        assert gen._shot_ctrl._finalize_motion_take.call_count == n

    def test_cost_recorded_exactly_once_for_batch(self, tmp_path):
        """CRITICAL: cost must be recorded once for the batch, not per-segment."""
        result, gen, mock_kling, mock_split, seg_paths, sb_path = self._run_storyboard(3, tmp_path)

        # Batch cost recorded exactly once via cost_tracker.record_api_call
        batch_cost_calls = [
            c for c in gen.cost_tracker.record_api_call.call_args_list
            if c.args and c.args[0] == "KLING_NATIVE"
            and c.kwargs.get("operation") == "storyboard_generation"
        ]
        assert len(batch_cost_calls) == 1, (
            f"Expected exactly 1 batch cost record, got {len(batch_cost_calls)}. "
            f"All record_api_call invocations: {gen.cost_tracker.record_api_call.call_args_list}"
        )

    def test_finalize_called_with_record_cost_false(self, tmp_path):
        """Each per-segment finalize must pass record_cost=False to suppress N-counting."""
        result, gen, mock_kling, mock_split, seg_paths, sb_path = self._run_storyboard(3, tmp_path)

        for idx, c in enumerate(gen._shot_ctrl._finalize_motion_take.call_args_list):
            rc = c.kwargs.get("record_cost")
            assert rc is False, (
                f"_finalize_motion_take call {idx}: expected record_cost=False, got {rc!r}"
            )

    def test_generate_motion_take_not_called_for_storyboard_scene(self, tmp_path):
        result, gen, *_ = self._run_storyboard(3, tmp_path)
        gen.generate_motion_take.assert_not_called()

    def test_result_ok_and_counts(self, tmp_path):
        n = 3
        result, gen, *_ = self._run_storyboard(n, tmp_path)
        assert result.ok is True
        assert f"{n} new" in result.message

    def test_split_called_with_per_shot_durations(self, tmp_path):
        from cinema.phases.motion_render import MotionRenderPhase

        n = 3
        shots = [_make_shot(f"s1_{i}") for i in range(n)]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=True)

        kf_paths = {s["id"]: str(tmp_path / f"{s['id']}.jpg") for s in shots}
        for p in kf_paths.values():
            open(p, "w").close()

        gen = _make_gen_mock(kf_paths=kf_paths)
        storyboard_path = str(tmp_path / "combined.mp4")
        seg_paths = [str(tmp_path / f"seg_{i}.mp4") for i in range(n)]
        for p in seg_paths:
            open(p, "w").close()

        with patch("kling_native.KlingNativeAPI") as mock_kling_cls:
            mock_kling = MagicMock()
            mock_kling.generate_storyboard.return_value = storyboard_path
            open(storyboard_path, "w").close()
            mock_kling_cls.return_value = mock_kling

            with patch("phase_c_ffmpeg.split_video_into_segments") as mock_split:
                mock_split.return_value = seg_paths

                phase = MotionRenderPhase(shot_generator=gen, project=project)
                result = phase.run(_make_lifecycle())

        # split_video_into_segments must have been called with the per-shot durations
        mock_split.assert_called_once()
        _, split_kwargs = mock_split.call_args[0], mock_split.call_args[1]
        # The durations list (2nd positional arg) must have n entries
        call_args_pos = mock_split.call_args[0]
        call_args_kw = mock_split.call_args[1]
        durations_arg = call_args_kw.get("durations") or (call_args_pos[1] if len(call_args_pos) > 1 else None)
        assert durations_arg is not None
        assert len(durations_arg) == n


# ---------------------------------------------------------------------------
# (e) generate_storyboard returns None → fallback to per-shot
# ---------------------------------------------------------------------------

class TestStoryboardFallback:
    def test_none_result_falls_back_to_per_shot(self, tmp_path):
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [_make_shot("s1_0"), _make_shot("s1_1"), _make_shot("s1_2")]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=True)

        kf_paths = {s["id"]: str(tmp_path / f"{s['id']}.jpg") for s in shots}
        for p in kf_paths.values():
            open(p, "w").close()

        gen = _make_gen_mock(kf_paths=kf_paths)

        with patch("kling_native.KlingNativeAPI") as mock_kling_cls:
            mock_kling = MagicMock()
            mock_kling.generate_storyboard.return_value = None  # simulate failure
            mock_kling_cls.return_value = mock_kling

            phase = MotionRenderPhase(shot_generator=gen, project=project)
            ctx = _make_lifecycle()
            result = phase.run(ctx)

        # Must have fallen back to per-shot
        assert gen.generate_motion_take.call_count == 3
        assert result.ok is True

    def test_none_result_does_not_record_batch_cost(self, tmp_path):
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [_make_shot("s1_0"), _make_shot("s1_1")]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=True)

        kf_paths = {s["id"]: str(tmp_path / f"{s['id']}.jpg") for s in shots}
        for p in kf_paths.values():
            open(p, "w").close()

        gen = _make_gen_mock(kf_paths=kf_paths)

        with patch("kling_native.KlingNativeAPI") as mock_kling_cls:
            mock_kling = MagicMock()
            mock_kling.generate_storyboard.return_value = None
            mock_kling_cls.return_value = mock_kling

            phase = MotionRenderPhase(shot_generator=gen, project=project)
            result = phase.run(_make_lifecycle())

        # No batch cost should have been recorded
        batch_cost_calls = [
            c for c in gen.cost_tracker.record_api_call.call_args_list
            if c.kwargs.get("operation") == "storyboard_generation"
        ]
        assert len(batch_cost_calls) == 0

    def test_split_failure_falls_back_to_per_shot(self, tmp_path):
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [_make_shot("s1_0"), _make_shot("s1_1")]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=True)

        kf_paths = {s["id"]: str(tmp_path / f"{s['id']}.jpg") for s in shots}
        for p in kf_paths.values():
            open(p, "w").close()

        gen = _make_gen_mock(kf_paths=kf_paths)
        storyboard_path = str(tmp_path / "combined.mp4")
        open(storyboard_path, "w").close()

        with patch("kling_native.KlingNativeAPI") as mock_kling_cls:
            mock_kling = MagicMock()
            mock_kling.generate_storyboard.return_value = storyboard_path
            mock_kling_cls.return_value = mock_kling

            with patch("phase_c_ffmpeg.split_video_into_segments", side_effect=RuntimeError("ffmpeg fail")):
                phase = MotionRenderPhase(shot_generator=gen, project=project)
                result = phase.run(_make_lifecycle())

        # Must have fallen back to per-shot
        assert gen.generate_motion_take.call_count == 2
        assert result.ok is True

    def test_missing_keyframe_skips_storyboard(self, tmp_path):
        """Scene with a shot missing a keyframe → ineligible for storyboard."""
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [
            _make_shot("s1_0"),
            # shot s1_1 has no keyframe take id
            {"id": "s1_1", "characters_in_frame": [], "camera": "dolly_in"},
        ]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=True)

        kf_paths = {"s1_0": str(tmp_path / "s1_0.jpg")}
        open(kf_paths["s1_0"], "w").close()

        gen = _make_gen_mock(kf_paths=kf_paths)

        with patch("kling_native.KlingNativeAPI") as mock_kling_cls:
            phase = MotionRenderPhase(shot_generator=gen, project=project)
            result = phase.run(_make_lifecycle())
            # Storyboard was never attempted
            mock_kling_cls.assert_not_called()

        # Fell back to per-shot
        assert gen.generate_motion_take.call_count == 2


# ---------------------------------------------------------------------------
# Existing behavior preserved: pre-approved shots are skipped
# ---------------------------------------------------------------------------

class TestPreApprovedShotsSkipped:
    def test_approved_shots_not_regenerated(self, tmp_path):
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [
            _make_shot("s1_0", has_final=True),   # already approved
            _make_shot("s1_1"),                    # needs generation
        ]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=False)

        gen = _make_gen_mock()
        phase = MotionRenderPhase(shot_generator=gen, project=project)
        result = phase.run(_make_lifecycle())

        assert result.ok is True
        # Only the unapproved shot should have been processed
        assert gen.generate_motion_take.call_count == 1
        assert "1 pre-finalized" in result.message

    def test_approved_shot_excluded_from_storyboard_count(self, tmp_path):
        """With 1 approved + 1 unapproved = 1 unapproved → ineligible for storyboard."""
        from cinema.phases.motion_render import MotionRenderPhase

        shots = [
            _make_shot("s1_0", has_final=True),
            _make_shot("s1_1"),
        ]
        scene = _make_scene("scene_1", shots)
        project = _make_project([scene], storyboard_mode=True)

        kf_paths = {"s1_1": str(tmp_path / "s1_1.jpg")}
        open(kf_paths["s1_1"], "w").close()

        gen = _make_gen_mock(kf_paths=kf_paths)

        with patch("kling_native.KlingNativeAPI") as mock_kling_cls:
            phase = MotionRenderPhase(shot_generator=gen, project=project)
            result = phase.run(_make_lifecycle())
            # Storyboard path requires 2–6 unapproved; only 1 here → not attempted
            mock_kling_cls.assert_not_called()

        assert gen.generate_motion_take.call_count == 1


# ---------------------------------------------------------------------------
# record_cost=False param on _finalize_motion_take (controller unit test)
# ---------------------------------------------------------------------------

class TestRecordCostParam:
    """Verify the record_cost param on ShotController._finalize_motion_take."""

    def _setup_ctrl(self, tmp_path):
        from cinema.shots.controller import ShotController
        from domain.project_manager import make_take

        project = {
            "id": "proj_rcp",
            "scenes": [{"id": "sc1", "shots": [{"id": "sh1", "characters_in_frame": []}]}],
            "global_settings": {},
        }

        host = MagicMock()
        host._refresh_project_snapshot.return_value = project
        host._rebuild_review_clips.return_value = None
        host._save_checkpoint.return_value = None

        lifecycle = MagicMock()
        runstate = MagicMock()
        runstate.shot_results = {}

        core = MagicMock()
        core.project = project
        core.project_dir = str(tmp_path)
        core.continuity = MagicMock()
        mock_cost = MagicMock()
        mock_cost.is_over_budget.return_value = False
        core.cost_tracker = mock_cost

        ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)

        scene = project["scenes"][0]
        shot = scene["shots"][0]

        def _fake_mutate(shot_id, mutator, timeout=10):
            from cinema.shots.controller import MutationResult
            fake = {"motion_takes": []}
            result = mutator(scene, fake)
            return result.value

        ctrl._mutate_shot = MagicMock(side_effect=_fake_mutate)

        take = make_take("motion", source_take_id="kf_001", metadata={"scene_id": "sc1", "shot_id": "sh1", "target_api": "KLING_NATIVE", "shot_type": "medium"})
        vid = tmp_path / "vid.mp4"
        vid.write_bytes(b"fake")

        return ctrl, scene, shot, take, str(vid)

    def test_record_cost_true_calls_cost_tracker(self, tmp_path):
        ctrl, scene, shot, take, vid = self._setup_ctrl(tmp_path)
        ctrl._finalize_motion_take(
            scene, shot, take, vid,
            source_image="/f/kf.jpg",
            target_api="KLING_NATIVE",
            cc={}, settings={}, resolved_shot_type="medium",
            record_cost=True,
        )
        ctrl.cost_tracker.record_api_call.assert_called_once()

    def test_record_cost_false_skips_cost_tracker(self, tmp_path):
        ctrl, scene, shot, take, vid = self._setup_ctrl(tmp_path)
        ctrl._finalize_motion_take(
            scene, shot, take, vid,
            source_image="/f/kf.jpg",
            target_api="KLING_NATIVE",
            cc={}, settings={}, resolved_shot_type="medium",
            record_cost=False,
        )
        ctrl.cost_tracker.record_api_call.assert_not_called()

    def test_default_record_cost_true(self, tmp_path):
        """record_cost defaults to True — existing callers are unaffected."""
        ctrl, scene, shot, take, vid = self._setup_ctrl(tmp_path)
        ctrl._finalize_motion_take(
            scene, shot, take, vid,
            source_image="/f/kf.jpg",
            target_api="KLING_NATIVE",
            cc={}, settings={}, resolved_shot_type="medium",
            # record_cost omitted — default True
        )
        ctrl.cost_tracker.record_api_call.assert_called_once()
