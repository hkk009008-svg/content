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
