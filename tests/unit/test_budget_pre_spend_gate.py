"""Pre-spend budget gate on generate_motion_take (P0-2 wiring of NF-2).

``CostTracker.would_exceed`` has promised pre-call gating since the module
was written ("Call ``would_exceed(api_name)`` before an API call" —
cost_tracker.py module docstring) but had zero production callers; only the
post-fact ``is_over_budget()`` gate at _finalize_motion_take step 9 was
wired. These tests pin the wiring: when the estimated cost of the resolved
target_api would push spend past the cap, generate_motion_take must refuse
to launch the generation, pause the lifecycle, and report failure — BEFORE
any video API is called.

All tests are fully offline — the video generator is patched and, in the
gated case, must NOT be invoked.

Harness mirrors TestAutoRoutingDecisions in test_dialogue_routing.py.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers — minimal stubs so we can import domain modules without the
# full project's optional runtime deps (torch, cv2, …)
# ---------------------------------------------------------------------------

def _stub_module(name: str, **attrs):
    """Create a trivial stub module and inject it into sys.modules."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Stub heavy deps that are imported at module load in phase_c_ffmpeg / controller
for _dep in [
    "veo_native", "kling_native", "sora_native", "ltx_native",
    "runway_native", "runway_gen4", "fal_proxy",
    "kling_3_0", "sora_2", "veo_fal",
]:
    if _dep not in sys.modules:
        _stub_module(_dep)


class TestPreSpendBudgetGate:
    """generate_motion_take refuses to spend when would_exceed(target_api)."""

    def _build_controller(self, project: dict, tmp_path):
        """Build a minimal ShotController with mocked host + core.

        Returns (ctrl, host, lifecycle, cost_tracker) so tests can assert on
        the lifecycle and tracker mocks directly.
        """
        from cinema.shots.controller import ShotController

        host = MagicMock()
        host._refresh_project_snapshot.return_value = project
        host._rebuild_review_clips.return_value = {}
        host._save_checkpoint.return_value = None
        keyframe_path = str(tmp_path / "keyframe.jpg")
        open(keyframe_path, "wb").write(b"fake_jpg")
        host._resolve_take_path.return_value = keyframe_path
        host._ensure_shot_audio.return_value = None
        host._ensure_scene_audio.return_value = None

        lifecycle = MagicMock()
        lifecycle.report_progress.return_value = None
        runstate = MagicMock()
        runstate.shot_results = {}
        runstate.update_progress_pointer.return_value = None

        core = MagicMock()
        core.project = project
        core.project_dir = str(tmp_path)
        core.continuity = MagicMock()
        core.continuity.enhance_shot_prompt.return_value = {
            "continuity_config": {"primary_character": "char_1", "multi_angle_refs": []}
        }
        cost_tracker = MagicMock()
        cost_tracker.is_over_budget.return_value = False
        cost_tracker.would_exceed.return_value = False
        cost_tracker.spent_usd = 0.0
        cost_tracker.budget_usd = None
        core.cost_tracker = cost_tracker

        ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
        ctrl._take_output_path = MagicMock(
            side_effect=lambda shot_id, take_id, ext: str(tmp_path / f"{take_id}{ext}")
        )
        return ctrl, host, lifecycle, cost_tracker

    def _make_project(self, *, target_api="KLING_NATIVE"):
        """Minimal project with one approved, keyframed, non-dialogue shot."""
        return {
            "id": "proj_budget_gate_test",
            "characters": [{"id": "char_1", "name": "Alice"}],
            "global_settings": {},
            "scenes": [{
                "id": "scene_1",
                "title": "Scene",
                "action": "Action.",
                "characters_present": ["char_1"],
                "shots": [{
                    "id": "shot_1_0",
                    "prompt": "A shot",
                    "plan_status": "approved",
                    "target_api": target_api,
                    "camera": "static",
                    "characters_in_frame": ["char_1"],
                    "approved_keyframe_take_id": "kf_t1",
                }],
            }],
        }

    def test_refuses_generation_when_would_exceed(self, tmp_path):
        """Gate fires: no video API call, lifecycle paused, failure returned."""
        project = self._make_project(target_api="KLING_NATIVE")
        ctrl, host, lifecycle, cost_tracker = self._build_controller(project, tmp_path)
        cost_tracker.would_exceed.return_value = True
        # The gate formats these as floats — must be real numbers, not MagicMock.
        cost_tracker.spent_usd = 0.80
        cost_tracker.budget_usd = 1.00

        gen_vid = MagicMock()
        with (
            patch("cinema.shots.controller.generate_ai_video", gen_vid),
            patch("workflow_selector.classify_shot_type", return_value="medium"),
        ):
            result = ctrl.generate_motion_take("scene_1", "shot_1_0")

        assert result.get("success") is False
        assert "budget" in result.get("error", "").lower()
        gen_vid.assert_not_called()
        lifecycle.pause.assert_called_once()
        cost_tracker.would_exceed.assert_called_once_with("KLING_NATIVE")

    def test_proceeds_when_within_budget(self, tmp_path):
        """Control: would_exceed False → generation proceeds, no pause."""
        project = self._make_project(target_api="KLING_NATIVE")
        ctrl, host, lifecycle, cost_tracker = self._build_controller(project, tmp_path)
        cost_tracker.would_exceed.return_value = False

        clip = str(tmp_path / "clip.mp4")
        open(clip, "wb").write(b"fake_mp4")
        ctrl._finalize_motion_take = MagicMock(
            side_effect=lambda scene, shot, take, video_path, **kw: {
                "success": True, "take": dict(take), "video": video_path,
                "identity_score": 0.0,
            }
        )
        with (
            patch("cinema.shots.controller.generate_ai_video", return_value=clip),
            patch("workflow_selector.classify_shot_type", return_value="medium"),
        ):
            result = ctrl.generate_motion_take("scene_1", "shot_1_0")

        assert result.get("success") is True
        lifecycle.pause.assert_not_called()
