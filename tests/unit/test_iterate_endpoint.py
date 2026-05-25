"""
tests/unit/test_iterate_endpoint.py — S16 iteration endpoint + ShotController.regenerate_with_intent.

Covers:
1. Happy path: regenerate_with_intent routes to generate_keyframe_take with
   correct kwargs (parent_take_id, intent_override, revised_prompt populated).
2. Feature-flag off: _directorial_iteration_enabled() returns False when env var absent.
3. Feature-flag on: _directorial_iteration_enabled() returns True with each truthy value.

Tests do NOT require live LLM keys — intent_translator is fully mocked.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

from domain.models import DirectorialIntent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_intent(prose="tighten the framing", target_stage="keyframe") -> DirectorialIntent:
    return DirectorialIntent(prose=prose, target_stage=target_stage)


def _make_minimal_project(scene_id="scene_1", shot_id="shot_1_0") -> dict:
    """Minimal project dict with one scene + one shot + one keyframe_take."""
    return {
        "id": "proj_test",
        "scenes": [
            {
                "id": scene_id,
                "title": "Test Scene",
                "action": "Characters walk into frame.",
                "shots": [
                    {
                        "id": shot_id,
                        "prompt": "Wide shot of the protagonist",
                        "plan_status": "approved",
                        "approved_keyframe_take_id": "take_parent",
                        "keyframe_takes": [
                            {
                                "id": "take_parent",
                                "kind": "keyframe",
                                "path": "/fake/path.jpg",
                                "metadata": {"prompt": "Wide shot of the protagonist"},
                            }
                        ],
                    }
                ],
            }
        ],
        "global_settings": {},
    }


# ---------------------------------------------------------------------------
# Feature flag tests
# ---------------------------------------------------------------------------

class TestDirectorialIterationFlag:
    """_directorial_iteration_enabled() respects env var."""

    def test_flag_off_by_default(self):
        from cinema.shots.controller import _directorial_iteration_enabled
        env = {k: v for k, v in os.environ.items() if k != "CINEMA_DIRECTORIAL_ITERATION"}
        with patch.dict(os.environ, env, clear=True):
            assert _directorial_iteration_enabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "YES"])
    def test_flag_on_truthy_values(self, value):
        from cinema.shots.controller import _directorial_iteration_enabled
        with patch.dict(os.environ, {"CINEMA_DIRECTORIAL_ITERATION": value}):
            assert _directorial_iteration_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "", "off"])
    def test_flag_off_falsy_values(self, value):
        from cinema.shots.controller import _directorial_iteration_enabled
        with patch.dict(os.environ, {"CINEMA_DIRECTORIAL_ITERATION": value}):
            assert _directorial_iteration_enabled() is False


# ---------------------------------------------------------------------------
# ShotController.regenerate_with_intent happy path
# ---------------------------------------------------------------------------

class TestRegenerateWithIntentHappyPath:
    """regenerate_with_intent routes correctly and populates TakeRecord fields."""

    def _build_controller(self, project: dict):
        """Build a minimal ShotController with stubbed host + dependencies."""
        from cinema.shots.controller import ShotController

        host = MagicMock()
        host._refresh_project_snapshot.return_value = project
        host._rebuild_review_clips.return_value = None
        host._save_checkpoint.return_value = None
        host._resolve_take_path.return_value = "/fake/path.jpg"

        # Lifecycle and runstate stubs
        lifecycle = MagicMock()
        runstate = MagicMock()
        runstate.shot_results = {}

        # PipelineCore stub — only needs project / project_dir / cost_tracker
        # (cost_tracker is a property that proxies to core.cost_tracker)
        core = MagicMock()
        core.project = project
        core.project_dir = "/tmp/fake_project"
        core.continuity = MagicMock()
        mock_cost_tracker = MagicMock()
        mock_cost_tracker.is_over_budget.return_value = False
        core.cost_tracker = mock_cost_tracker

        ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
        return ctrl

    def test_keyframe_iteration_calls_generate_keyframe_take(self):
        """intent.target_stage='keyframe' → generate_keyframe_take called with intent kwargs."""
        project = _make_minimal_project()
        ctrl = self._build_controller(project)
        intent = _make_intent(prose="bring the camera closer", target_stage="keyframe")

        # Mock the full translated output from intent_translator
        mock_translated = {
            "revised_prompt": "Close-up of the protagonist",
            "params_delta": {"guidance_scale": 8.5},
            "anchor_refs": [],
        }

        # Mock generate_keyframe_take to avoid full pipeline execution
        expected_take = {"id": "take_new", "kind": "keyframe", "parent_take_id": "take_parent"}
        ctrl.generate_keyframe_take = MagicMock(
            return_value={"success": True, "take": expected_take}
        )
        ctrl._mutate_shot = MagicMock(return_value=expected_take)

        with patch("llm.director.intent_translator", return_value=mock_translated):
            result = ctrl.regenerate_with_intent(
                "scene_1", "shot_1_0", "take_parent", intent
            )

        assert result["success"] is True

        # Verify generate_keyframe_take was called with the right iteration kwargs
        ctrl.generate_keyframe_take.assert_called_once()
        call_kwargs = ctrl.generate_keyframe_take.call_args
        assert call_kwargs.kwargs.get("intent_override") is intent
        assert call_kwargs.kwargs.get("parent_take_id") == "take_parent"
        assert call_kwargs.kwargs.get("revised_prompt") == "Close-up of the protagonist"
        assert call_kwargs.kwargs.get("positive_prompt") == "Close-up of the protagonist"

    def test_missing_take_returns_error(self):
        """Requesting a non-existent take_id returns success=False."""
        project = _make_minimal_project()
        ctrl = self._build_controller(project)
        intent = _make_intent()

        with patch("llm.director.intent_translator", return_value={
            "revised_prompt": "x", "params_delta": {}, "anchor_refs": [],
        }):
            result = ctrl.regenerate_with_intent(
                "scene_1", "shot_1_0", "take_NONEXISTENT", intent
            )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_performance_iteration_calls_generate_performance_take(self):
        """intent.target_stage='performance' → generate_performance_take called with intent kwargs.

        Per code-quality reviewer M-3: covers the performance routing path that was
        absent from the original happy-path test (which only exercised keyframe).
        """
        project = _make_minimal_project()
        ctrl = self._build_controller(project)
        intent = _make_intent(prose="soften the line delivery", target_stage="performance")

        mock_translated = {
            "revised_prompt": "Subtler emotional delivery",
            "params_delta": {"warmth": 0.3},
            "anchor_refs": [],
        }
        expected_take = {"id": "take_perf_new", "kind": "performance", "parent_take_id": "take_parent"}
        ctrl.generate_performance_take = MagicMock(
            return_value={"success": True, "take": expected_take}
        )
        # Stub _mutate_shot so the second-trip metadata stash doesn't blow up
        # against the MagicMock host (controller-level test isolation).
        ctrl._mutate_shot = MagicMock(return_value=expected_take)

        with patch("llm.director.intent_translator", return_value=mock_translated):
            result = ctrl.regenerate_with_intent(
                "scene_1", "shot_1_0", "take_parent", intent
            )

        assert result["success"] is True

        ctrl.generate_performance_take.assert_called_once()
        call_kwargs = ctrl.generate_performance_take.call_args
        assert call_kwargs.kwargs.get("intent_override") is intent
        assert call_kwargs.kwargs.get("parent_take_id") == "take_parent"
        assert call_kwargs.kwargs.get("revised_prompt") == "Subtler emotional delivery"
        # generate_performance_take does NOT take positive_prompt (signature is
        # (scene_id, shot_id) plus the keyword-only iteration kwargs); verify
        # we didn't accidentally pass one.
        assert "positive_prompt" not in call_kwargs.kwargs

    def test_motion_iteration_calls_generate_motion_take(self):
        """intent.target_stage='motion' → generate_motion_take called with intent kwargs.

        Per code-quality reviewer M-3: covers the motion routing path.
        """
        project = _make_minimal_project()
        ctrl = self._build_controller(project)
        intent = _make_intent(prose="add a subtle dolly-in", target_stage="motion")

        mock_translated = {
            "revised_prompt": "Slow dolly-in toward protagonist",
            "params_delta": {"camera_speed": 0.4},
            "anchor_refs": [],
        }
        expected_take = {"id": "take_motion_new", "kind": "motion", "parent_take_id": "take_parent"}
        ctrl.generate_motion_take = MagicMock(
            return_value={"success": True, "take": expected_take}
        )
        ctrl._mutate_shot = MagicMock(return_value=expected_take)

        with patch("llm.director.intent_translator", return_value=mock_translated):
            result = ctrl.regenerate_with_intent(
                "scene_1", "shot_1_0", "take_parent", intent
            )

        assert result["success"] is True

        ctrl.generate_motion_take.assert_called_once()
        call_kwargs = ctrl.generate_motion_take.call_args
        assert call_kwargs.kwargs.get("intent_override") is intent
        assert call_kwargs.kwargs.get("parent_take_id") == "take_parent"
        assert call_kwargs.kwargs.get("revised_prompt") == "Slow dolly-in toward protagonist"
        assert "positive_prompt" not in call_kwargs.kwargs

    def test_approved_shots_includes_all_three_approval_kinds(self):
        """Lane V #6 F1 regression: scene_context["approved_shots"] must include
        shots approved via keyframe, motion, OR performance gates.

        The S18 F2 fold expanded the filter to performance-approved shots, but
        Lane V #6 caught that the implementation checked `performance_take_id`
        (a Pydantic default, never written) instead of `approved_performance_take_id`
        (the actual runtime field). This test locks the F2 fold semantic — if a
        future change reverts to the wrong field name, the `match_shot` verb's
        cross-shot reference pool silently shrinks. See:
          - cinema/shots/controller.py:1179-1186 (the filter)
          - coordination/mailbox/sent/2026-05-25T18-20-57Z-operator-to-director-verification-report.md (F1)
        """
        project = {
            "id": "proj_f4",
            "scenes": [
                {
                    "id": "scene_1",
                    "title": "Mixed approvals",
                    "action": "Several shots with different approval kinds.",
                    "shots": [
                        # Shot A — performance-only approved (the F1 target case)
                        {
                            "id": "shot_perf_only",
                            "prompt": "Performance shot",
                            "approved_performance_take_id": "take_perf_approved",
                            "performance_takes": [
                                {"id": "take_perf_approved", "kind": "performance"}
                            ],
                        },
                        # Shot B — keyframe-only approved
                        {
                            "id": "shot_kf_only",
                            "prompt": "Keyframe shot",
                            "approved_keyframe_take_id": "take_kf_approved",
                            "keyframe_takes": [
                                {"id": "take_kf_approved", "kind": "keyframe"}
                            ],
                        },
                        # Shot C — motion-only approved
                        {
                            "id": "shot_motion_only",
                            "prompt": "Motion shot",
                            "approved_motion_take_id": "take_motion_approved",
                            "motion_takes": [
                                {"id": "take_motion_approved", "kind": "motion"}
                            ],
                        },
                        # Shot D — the iteration target (also keyframe-approved
                        # so it has a parent take to iterate from)
                        {
                            "id": "shot_iter_target",
                            "prompt": "Iteration target",
                            "approved_keyframe_take_id": "take_iter_parent",
                            "keyframe_takes": [
                                {
                                    "id": "take_iter_parent",
                                    "kind": "keyframe",
                                    "metadata": {"prompt": "Iteration target"},
                                }
                            ],
                        },
                    ],
                }
            ],
            "global_settings": {},
        }
        ctrl = self._build_controller(project)
        intent = _make_intent(prose="match shot_perf_only", target_stage="keyframe")
        ctrl.generate_keyframe_take = MagicMock(
            return_value={"success": True, "take": {"id": "take_new", "kind": "keyframe"}}
        )
        ctrl._mutate_shot = MagicMock()

        captured = {}

        def _capture_scene_context(intent_arg, take_context, scene_context, *, project=None):
            captured["scene_context"] = scene_context
            return {"revised_prompt": "x", "params_delta": {}, "anchor_refs": []}

        with patch("llm.director.intent_translator", side_effect=_capture_scene_context):
            ctrl.regenerate_with_intent(
                "scene_1", "shot_iter_target", "take_iter_parent", intent
            )

        approved_ids = {s["id"] for s in captured["scene_context"]["approved_shots"]}
        # All three approval kinds must be represented. The iteration target
        # itself is also keyframe-approved so it appears too — 4 shots total.
        assert "shot_perf_only" in approved_ids, (
            "F1 regression: performance-only-approved shot missing from approved_shots — "
            "check that the filter uses `approved_performance_take_id`, not bare "
            "`performance_take_id` (which is never written to runtime shot dicts)."
        )
        assert "shot_kf_only" in approved_ids
        assert "shot_motion_only" in approved_ids
        assert "shot_iter_target" in approved_ids


# ---------------------------------------------------------------------------
# S21 (cycle-9 Surface B): dirty-shot tracking during SCREENING
# ---------------------------------------------------------------------------


class TestRegenerateWithIntentDirtyTracking:
    """When iterate fires DURING SCREENING, regenerate_with_intent must add
    the shot_id to project.needs_reassembly via mark_shot_needs_reassembly.

    Per S21 brief: dirty-tracking is the signal the re-assemble endpoint
    uses to short-circuit on `only_if_changed=true`. The insertion site is
    inside regenerate_with_intent (after the successful generate_*_take
    call), gated on the live runstate.current_stage == "SCREENING".
    """

    def _build_controller(self, project: dict, current_stage: str = ""):
        """Build a ShotController whose runstate has the given current_stage."""
        from cinema.shots.controller import ShotController

        host = MagicMock()
        host._refresh_project_snapshot.return_value = project
        host._rebuild_review_clips.return_value = None
        host._save_checkpoint.return_value = None
        host._resolve_take_path.return_value = "/fake/path.jpg"

        lifecycle = MagicMock()
        runstate = MagicMock()
        runstate.shot_results = {}
        runstate.current_stage = current_stage  # critical for S21 trigger

        core = MagicMock()
        core.project = project
        core.project_dir = "/tmp/fake_project"
        core.continuity = MagicMock()
        mock_cost_tracker = MagicMock()
        mock_cost_tracker.is_over_budget.return_value = False
        core.cost_tracker = mock_cost_tracker

        return ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)

    def test_iterate_during_screening_marks_shot_dirty(self):
        """current_stage == 'SCREENING' + successful iterate -> mark_shot_needs_reassembly called."""
        project = _make_minimal_project()
        ctrl = self._build_controller(project, current_stage="SCREENING")
        intent = _make_intent()

        expected_take = {"id": "take_new", "kind": "keyframe", "parent_take_id": "take_parent"}
        ctrl.generate_keyframe_take = MagicMock(
            return_value={"success": True, "take": expected_take}
        )
        ctrl._mutate_shot = MagicMock(return_value=expected_take)

        with patch("llm.director.intent_translator", return_value={
            "revised_prompt": "x", "params_delta": {}, "anchor_refs": [],
        }), patch("cinema.screening.mark_shot_needs_reassembly") as mock_mark:
            ctrl.regenerate_with_intent(
                "scene_1", "shot_1_0", "take_parent", intent,
                project_id="proj_test",
            )

        mock_mark.assert_called_once_with("proj_test", "shot_1_0")

    def test_iterate_outside_screening_does_not_mark_dirty(self):
        """current_stage != 'SCREENING' -> mark_shot_needs_reassembly NOT called."""
        project = _make_minimal_project()
        ctrl = self._build_controller(project, current_stage="KEYFRAME_REVIEW")
        intent = _make_intent()

        expected_take = {"id": "take_new", "kind": "keyframe"}
        ctrl.generate_keyframe_take = MagicMock(
            return_value={"success": True, "take": expected_take}
        )
        ctrl._mutate_shot = MagicMock(return_value=expected_take)

        with patch("llm.director.intent_translator", return_value={
            "revised_prompt": "x", "params_delta": {}, "anchor_refs": [],
        }), patch("cinema.screening.mark_shot_needs_reassembly") as mock_mark:
            ctrl.regenerate_with_intent(
                "scene_1", "shot_1_0", "take_parent", intent,
                project_id="proj_test",
            )

        mock_mark.assert_not_called()

    def test_iterate_failure_does_not_mark_dirty(self):
        """A FAILED iterate (success=False) must NOT mark the shot dirty —
        otherwise the operator's re-assemble would skip a take that was
        never actually changed."""
        project = _make_minimal_project()
        ctrl = self._build_controller(project, current_stage="SCREENING")
        intent = _make_intent()

        ctrl.generate_keyframe_take = MagicMock(
            return_value={"success": False, "error": "downstream failure"}
        )

        with patch("llm.director.intent_translator", return_value={
            "revised_prompt": "x", "params_delta": {}, "anchor_refs": [],
        }), patch("cinema.screening.mark_shot_needs_reassembly") as mock_mark:
            ctrl.regenerate_with_intent(
                "scene_1", "shot_1_0", "take_parent", intent,
                project_id="proj_test",
            )

        mock_mark.assert_not_called()

    def test_iterate_without_project_id_skips_dirty_tracking(self):
        """project_id='' (no scope) -> dirty-tracking is a no-op.
        This is the legacy call path; without project_id we can't safely
        mutate any project's needs_reassembly list."""
        project = _make_minimal_project()
        ctrl = self._build_controller(project, current_stage="SCREENING")
        intent = _make_intent()

        expected_take = {"id": "take_new", "kind": "keyframe"}
        ctrl.generate_keyframe_take = MagicMock(
            return_value={"success": True, "take": expected_take}
        )
        ctrl._mutate_shot = MagicMock(return_value=expected_take)

        with patch("llm.director.intent_translator", return_value={
            "revised_prompt": "x", "params_delta": {}, "anchor_refs": [],
        }), patch("cinema.screening.mark_shot_needs_reassembly") as mock_mark:
            ctrl.regenerate_with_intent(
                "scene_1", "shot_1_0", "take_parent", intent,
                # project_id defaults to "" — legacy callers
            )

        mock_mark.assert_not_called()

    def test_dirty_tracking_failure_does_not_break_iterate(self):
        """If mark_shot_needs_reassembly raises (e.g. project file
        evaporated mid-iterate), the iterate response must still surface
        success=True with the new take. Best-effort semantics."""
        project = _make_minimal_project()
        ctrl = self._build_controller(project, current_stage="SCREENING")
        intent = _make_intent()

        expected_take = {"id": "take_new", "kind": "keyframe"}
        ctrl.generate_keyframe_take = MagicMock(
            return_value={"success": True, "take": expected_take}
        )
        ctrl._mutate_shot = MagicMock(return_value=expected_take)

        with patch("llm.director.intent_translator", return_value={
            "revised_prompt": "x", "params_delta": {}, "anchor_refs": [],
        }), patch("cinema.screening.mark_shot_needs_reassembly",
                  side_effect=RuntimeError("simulated mutate failure")):
            result = ctrl.regenerate_with_intent(
                "scene_1", "shot_1_0", "take_parent", intent,
                project_id="proj_test",
            )

        # iterate succeeded -- the dirty-tracking failure is swallowed.
        assert result["success"] is True
        assert result["take"]["id"] == "take_new"
