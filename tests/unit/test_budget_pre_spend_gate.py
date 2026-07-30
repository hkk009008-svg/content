"""Pre-spend budget gate on generate_motion_take (P0-2 wiring of NF-2).

``CostTracker`` has promised pre-call gating since the module was written
("Call ``would_exceed(api_name)`` before an API call" — cost_tracker.py
module docstring); motion generation now uses the multi-call
``would_exceed_cost()`` helper so mandatory attached work can be included in
the same pre-spend envelope. These tests pin the wiring: when the estimated
cost of the resolved
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
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from domain.provider_catalog import RuntimeSnapshot


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

# Guarantee kling_native.KlingNativeAPI exists so patch() can find it
# (mirrors test_f2b_storyboard_mode._ensure_kling_native_patchable — another
# test file may have registered the stub without the class).
if not hasattr(sys.modules["kling_native"], "KlingNativeAPI"):
    sys.modules["kling_native"].KlingNativeAPI = MagicMock  # type: ignore[attr-defined]


_PRE_SORA_SUNSET = date(2026, 9, 23)


def _kling_native_runtime() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        credentials={"kling_access_key", "kling_secret_key"},
        modules={"jwt"},
    )


def _veo_native_runtime() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        credentials={"google_api_key"},
        modules={"google.genai"},
    )


class TestPreSpendBudgetGate:
    """generate_motion_take refuses to spend when the estimated envelope exceeds budget."""

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
        cost_tracker.would_exceed_cost.return_value = False
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
            patch(
                "cinema.shots.controller._video_policy_runtime_snapshot",
                return_value=_kling_native_runtime(),
            ),
            patch(
                "cinema.shots.controller._video_policy_current_date",
                return_value=_PRE_SORA_SUNSET,
            ),
        ):
            result = ctrl.generate_motion_take("scene_1", "shot_1_0")

        assert result.get("success") is False
        assert "budget" in result.get("error", "").lower()
        # Structured kind — the phase loop keys its abort on this, not on
        # parsing the human-facing error string.
        assert result.get("error_kind") == "budget"
        gen_vid.assert_not_called()
        lifecycle.pause.assert_called_once()
        cost_tracker.would_exceed.assert_called_once_with("KLING_NATIVE")
        cost_tracker.would_exceed_cost.assert_not_called()
        # The refusal must be visible to the UI: a BUDGET_EXCEEDED progress
        # event is emitted (ctrl.progress proxies lifecycle.report_progress).
        events = [c.args[0] for c in lifecycle.report_progress.call_args_list if c.args]
        assert "BUDGET_EXCEEDED" in events

    def test_auto_shot_gate_uses_resolved_engine(self, tmp_path):
        """Anti-mutation pin: the gate must price the RESOLVED engine, not the
        raw 'AUTO' sentinel (API_COST_USD.get('AUTO') is 0.0 — estimating it
        would silently disable the pre-spend estimate for AUTO shots)."""
        project = self._make_project(target_api="AUTO")
        ctrl, host, lifecycle, cost_tracker = self._build_controller(project, tmp_path)
        cost_tracker.would_exceed.return_value = True
        cost_tracker.spent_usd = 0.80
        cost_tracker.budget_usd = 1.00

        gen_vid = MagicMock()
        with (
            patch("cinema.shots.controller.generate_ai_video", gen_vid),
            patch("workflow_selector.classify_shot_type", return_value="medium"),
            patch(
                "cinema.shots.controller._video_policy_runtime_snapshot",
                return_value=RuntimeSnapshot(
                    credentials={"google_api_key"},
                    modules={"google.genai"},
                ),
            ),
            patch(
                "cinema.shots.controller._video_policy_current_date",
                return_value=date(2026, 9, 23),
            ),
        ):
            result = ctrl.generate_motion_take("scene_1", "shot_1_0")

        assert result.get("success") is False
        # The template is a historical order seed; its known-broken Gemini
        # head is filtered, leaving the injected ready Veo engine.
        resolved = "VEO_NATIVE"
        assert resolved != "AUTO"
        cost_tracker.would_exceed.assert_called_once_with(resolved)
        cost_tracker.would_exceed_cost.assert_not_called()

    def test_dialogue_overlay_refuses_when_video_plus_lipsync_exceeds_budget(self, tmp_path):
        """Dialogue overlay shots must precheck video plus mandatory F1b lipsync."""
        from cost_tracker import CostTracker

        project = self._make_project(target_api="AUTO")
        project["global_settings"]["dialogue_voice_mode"] = "overlay"
        shot = project["scenes"][0]["shots"][0]
        shot["optimizer_cache"] = {
            "spec": {
                "purpose": "dialogue_close_up",
                "suggested_video_api": "VEO_NATIVE",
            }
        }

        ctrl, host, lifecycle, _mock_tracker = self._build_controller(project, tmp_path)
        tracker = CostTracker(db_path=str(tmp_path / "cost.db"), budget_usd=1.00)
        tracker.spent_usd = 0.67
        ctrl._core.cost_tracker = tracker

        audio_file = str(tmp_path / "shot_tts.mp3")
        open(audio_file, "wb").write(b"fake_audio")
        host._ensure_shot_audio.return_value = audio_file
        ref_image_file = str(tmp_path / "ref_char1.jpg")
        open(ref_image_file, "wb").write(b"fake_jpg")
        veo_clip = str(tmp_path / "veo_clip.mp4")
        open(veo_clip, "wb").write(b"fake_veo")
        ls_clip = str(tmp_path / "ls_clip.mp4")
        open(ls_clip, "wb").write(b"fake_ls")
        ctrl._finalize_motion_take = MagicMock(
            return_value={"success": True, "take": {}, "video": ls_clip, "identity_score": 0.0}
        )

        gen_vid = MagicMock(return_value=veo_clip)
        gen_ls = MagicMock(return_value=ls_clip)
        with (
            patch("cinema.shots.controller.generate_ai_video", gen_vid),
            patch("cinema.shots.controller.generate_lip_sync_video", gen_ls),
            patch("lip_sync.generate_lip_sync_video", gen_ls),
            patch("lip_sync.validate_lipsync_quality", return_value=0.91),
            patch("cinema.shots.controller.get_reference_image", return_value=ref_image_file),
            patch("cinema.shots.controller._probe_duration", return_value=3.5),
            patch("workflow_selector.classify_shot_type", return_value="medium"),
            patch(
                "cinema.shots.controller._video_policy_runtime_snapshot",
                return_value=_veo_native_runtime(),
            ),
            patch(
                "cinema.shots.controller._video_policy_current_date",
                return_value=_PRE_SORA_SUNSET,
            ),
        ):
            result = ctrl.generate_motion_take("scene_1", "shot_1_0")

        assert result.get("success") is False
        assert result.get("error_kind") == "budget"
        gen_vid.assert_not_called()
        gen_ls.assert_not_called()
        lifecycle.pause.assert_called_once()
        events = [c.args[0] for c in lifecycle.report_progress.call_args_list if c.args]
        assert "BUDGET_EXCEEDED" in events

    def test_proceeds_when_within_budget(self, tmp_path):
        """Control: would_exceed False → generation proceeds, no pause."""
        project = self._make_project(target_api="KLING_NATIVE")
        ctrl, host, lifecycle, cost_tracker = self._build_controller(project, tmp_path)
        cost_tracker.would_exceed_cost.return_value = False

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
            patch(
                "cinema.shots.controller._video_policy_runtime_snapshot",
                return_value=_kling_native_runtime(),
            ),
            patch(
                "cinema.shots.controller._video_policy_current_date",
                return_value=_PRE_SORA_SUNSET,
            ),
        ):
            result = ctrl.generate_motion_take("scene_1", "shot_1_0")

        assert result.get("success") is True
        lifecycle.pause.assert_not_called()
        # P1-3 (NF-3): the MOTION progress event carries the engine being
        # tried — the operator's #1 blindness during 8-minute motion waits.
        motion_events = [
            c for c in lifecycle.report_progress.call_args_list
            if c.args and c.args[0] == "MOTION"
        ]
        assert motion_events, "expected a MOTION progress event"
        assert motion_events[0].kwargs.get("engine") == "KLING_NATIVE"

    @pytest.mark.parametrize(
        ("target_api", "snapshot", "expected_reason"),
        [
            ("SORA_2", RuntimeSnapshot(), "retired"),
            ("SORA_NATIVE", RuntimeSnapshot(), "runtime_unavailable"),
        ],
    )
    def test_legacy_explicit_target_fails_before_any_spend_or_take_effect(
        self,
        tmp_path,
        target_api,
        snapshot,
        expected_reason,
    ):
        """A stored explicit target is fenced before budget, TTS, progress, or take I/O."""

        project = self._make_project(target_api=target_api)
        ctrl, host, lifecycle, cost_tracker = self._build_controller(project, tmp_path)
        bomb = AssertionError("downstream effect escaped target policy fence")
        cost_tracker.would_exceed.side_effect = bomb
        cost_tracker.would_exceed_cost.side_effect = bomb
        lifecycle.report_progress.side_effect = bomb
        ctrl._take_output_path.side_effect = bomb
        ctrl._core.continuity.enhance_shot_prompt.side_effect = bomb
        host._ensure_shot_audio.side_effect = bomb
        host._ensure_scene_audio.side_effect = bomb
        generate = MagicMock(side_effect=bomb)
        make_take_mock = MagicMock(side_effect=bomb)

        with (
            patch("cinema.shots.controller.generate_ai_video", generate),
            patch("cinema.shots.controller.make_take", make_take_mock),
            patch("workflow_selector.classify_shot_type", return_value="medium"),
            patch(
                "cinema.shots.controller._video_policy_runtime_snapshot",
                return_value=snapshot,
            ),
            patch(
                "cinema.shots.controller._video_policy_current_date",
                return_value=date(2026, 9, 23),
            ),
        ):
            result = ctrl.generate_motion_take("scene_1", "shot_1_0")

        assert result == {
            "success": False,
            "error": "Target video engine is unavailable",
            "error_kind": "target_api_policy",
            "code": "target_api_unavailable",
            "target_api": target_api,
            "reason": expected_reason,
            "retryable": False,
            "rejections": [
                {"key": target_api, "reason": expected_reason},
            ],
        }
        generate.assert_not_called()
        make_take_mock.assert_not_called()

    @pytest.mark.parametrize(
        ("target_api", "settings", "expected_reason"),
        [
            (
                "SEEDANCE",
                {"api_engines": {"SEEDANCE": {"enabled": False}}},
                "project_disabled",
            ),
            ("LTX", {"aspect_ratio": "9:16"}, "aspect_incompatible"),
        ],
    )
    def test_project_and_aspect_policy_fail_before_budget(
        self,
        tmp_path,
        target_api,
        settings,
        expected_reason,
    ):
        project = self._make_project(target_api=target_api)
        project["global_settings"].update(settings)
        ctrl, host, lifecycle, cost_tracker = self._build_controller(project, tmp_path)
        cost_tracker.would_exceed.side_effect = AssertionError(
            "budget gate must not run for a policy-rejected target"
        )
        generate = MagicMock()

        with (
            patch("cinema.shots.controller.generate_ai_video", generate),
            patch("workflow_selector.classify_shot_type", return_value="medium"),
            patch(
                "cinema.shots.controller._video_policy_runtime_snapshot",
                return_value=RuntimeSnapshot(
                    credentials={"fal_key"},
                    modules={"fal_client"},
                ),
            ),
            patch(
                "cinema.shots.controller._video_policy_current_date",
                return_value=date(2026, 9, 23),
            ),
        ):
            result = ctrl.generate_motion_take("scene_1", "shot_1_0")

        assert result["error_kind"] == "target_api_policy"
        assert result["reason"] == expected_reason
        assert result["rejections"] == [
            {"key": target_api, "reason": expected_reason},
        ]
        generate.assert_not_called()
        lifecycle.report_progress.assert_not_called()

    def test_auto_empty_runtime_fails_before_budget_and_preserves_rejections(
        self,
        tmp_path,
    ):
        project = self._make_project(target_api="AUTO")
        ctrl, host, lifecycle, cost_tracker = self._build_controller(project, tmp_path)
        cost_tracker.would_exceed.side_effect = AssertionError(
            "empty AUTO chain must fail before budget"
        )
        generate = MagicMock()

        with (
            patch("cinema.shots.controller.generate_ai_video", generate),
            patch("workflow_selector.classify_shot_type", return_value="medium"),
            patch(
                "cinema.shots.controller._video_policy_runtime_snapshot",
                return_value=RuntimeSnapshot(),
            ),
            patch(
                "cinema.shots.controller._video_policy_current_date",
                return_value=date(2026, 9, 23),
            ),
        ):
            result = ctrl.generate_motion_take("scene_1", "shot_1_0")

        assert result["error_kind"] == "target_api_policy"
        assert result["target_api"] == "AUTO"
        assert result["retryable"] is False
        assert result["reason"] == "unsupported"
        assert result["rejections"][0] == {
            "key": "GEMINI_OMNI",
            "reason": "unsupported",
        }
        assert not any(
            rejection["key"] == "SORA_2"
            for rejection in result["rejections"]
        )
        generate.assert_not_called()
        lifecycle.report_progress.assert_not_called()

    def test_auto_filtered_chain_preserves_suggestion_order_and_dedupes(
        self,
        tmp_path,
    ):
        project = self._make_project(target_api="AUTO")
        project["scenes"][0]["shots"][0]["optimizer_cache"] = {
            "spec": {
                "purpose": "action_motion",
                "suggested_video_api": "LTX",
            }
        }
        ctrl, host, lifecycle, cost_tracker = self._build_controller(project, tmp_path)
        clip = str(tmp_path / "clip.mp4")
        open(clip, "wb").write(b"fake_mp4")
        captured_take = {}

        def _finalize(scene, shot, take, video_path, **kwargs):
            captured_take.update(take)
            return {
                "success": True,
                "take": dict(take),
                "video": video_path,
                "identity_score": 0.0,
            }

        ctrl._finalize_motion_take = MagicMock(side_effect=_finalize)
        generate = MagicMock(return_value=clip)
        snapshot = RuntimeSnapshot(
            credentials={"fal_key"},
            modules={"fal_client"},
        )

        with (
            patch("cinema.shots.controller.generate_ai_video", generate),
            patch("workflow_selector.classify_shot_type", return_value="medium"),
            patch(
                "cinema.shots.controller._video_policy_runtime_snapshot",
                return_value=snapshot,
            ),
            patch(
                "cinema.shots.controller._video_policy_current_date",
                return_value=date(2026, 9, 23),
            ),
        ):
            result = ctrl.generate_motion_take("scene_1", "shot_1_0")

        assert result["success"] is True
        kwargs = generate.call_args.kwargs
        assert generate.call_args.args[2] == "AUTO"
        assert kwargs["video_fallbacks"] == [
            "LTX",
            "KLING_3_0",
            "SEEDANCE",
        ]
        assert "_policy_snapshot" not in kwargs
        assert "_policy_allow_primary_fallback" not in kwargs
        assert cost_tracker.would_exceed.call_args.args == ("LTX",)
        assert captured_take["cascade_metadata"]["policy_rejections"][0] == {
            "key": "GEMINI_OMNI",
            "reason": "unsupported",
        }


class TestBudgetPhaseAbort:
    """Phase-level behavior when the per-take gate refuses for budget.

    Without the abort, a budget-exhausted run marches through every remaining
    shot — each refused (no spend) but each mislabeled as a SHOT_FAILED via
    on_failure — and then proceeds to the next stage. The abort stops the
    phase at the first budget refusal; ordinary failures keep today's
    continue-and-record behavior.
    """

    _BUDGET_REFUSAL = {
        "success": False,
        "error": "Budget cap reached — motion generation not started",
        "error_kind": "budget",
    }

    def _make_ctx(self):
        lc = MagicMock()
        lc.is_cancelled.return_value = False
        ctx = MagicMock(lifecycle=lc)
        ctx.get.side_effect = lambda k, d=None: ({} if k == "global_settings" else d)
        return ctx

    def _make_project(self, n_shots=3, storyboard_mode=False):
        shots = [
            {
                "id": f"s1_{i}",
                "approved_keyframe_take_id": "kf_001",
                "prompt": f"shot {i}",
                "duration": 5.0,
            }
            for i in range(n_shots)
        ]
        return {
            "id": "proj_budget_abort",
            "scenes": [{"id": "scene_1", "shots": shots}],
            "global_settings": {
                "api_engines": {"KLING_NATIVE": {"storyboard_mode": storyboard_mode}},
            },
        }

    def _make_gen(self, tmp_path, take_result):
        kf = str(tmp_path / "kf.jpg")
        open(kf, "wb").write(b"fake_jpg")
        gen = MagicMock()
        gen._resolve_take_path.return_value = kf
        gen.cost_tracker = MagicMock()
        gen.cost_tracker.would_exceed.return_value = False
        gen.generate_motion_take.return_value = take_result
        return gen

    def test_per_shot_loop_aborts_on_budget_refusal(self, tmp_path):
        from cinema.phases.motion_render import MotionRenderPhase

        gen = self._make_gen(tmp_path, self._BUDGET_REFUSAL)
        on_failure = MagicMock()
        phase = MotionRenderPhase(
            shot_generator=gen, project=self._make_project(), on_failure=on_failure,
        )
        result = phase.run(self._make_ctx())

        assert gen.generate_motion_take.call_count == 1
        on_failure.assert_not_called()  # budget stop is not a shot failure
        assert result.ok is False
        assert "budget" in result.message.lower()

    def test_per_shot_loop_continues_on_ordinary_failure(self, tmp_path):
        """Control: failures without error_kind keep the record-and-continue path."""
        from cinema.phases.motion_render import MotionRenderPhase

        gen = self._make_gen(tmp_path, {"success": False, "error": "boom"})
        on_failure = MagicMock()
        phase = MotionRenderPhase(
            shot_generator=gen, project=self._make_project(), on_failure=on_failure,
        )
        result = phase.run(self._make_ctx())

        assert gen.generate_motion_take.call_count == 3
        assert on_failure.call_count == 3
        assert result.ok is True

    def test_storyboard_batch_refused_when_would_exceed(self, tmp_path):
        """F2b: the batch launch is pre-spend-gated too — would_exceed refuses
        BEFORE KlingNativeAPI is constructed; the scene falls through to the
        per-shot path, whose own gate then aborts the phase."""
        from cinema.phases.motion_render import MotionRenderPhase

        gen = self._make_gen(tmp_path, self._BUDGET_REFUSAL)
        gen.cost_tracker.would_exceed.return_value = True
        phase = MotionRenderPhase(
            shot_generator=gen, project=self._make_project(storyboard_mode=True),
        )
        with (
            patch(
                "cinema.phases.motion_render._storyboard_policy_runtime_snapshot",
                return_value=_kling_native_runtime(),
            ),
            patch(
                "cinema.phases.motion_render._storyboard_policy_current_date",
                return_value=_PRE_SORA_SUNSET,
            ),
            patch("kling_native.KlingNativeAPI") as mock_kling_cls,
        ):
            result = phase.run(self._make_ctx())
            mock_kling_cls.assert_not_called()

        assert gen.generate_motion_take.call_count == 1
        assert result.ok is False
        assert "budget" in result.message.lower()


class TestPerformancePreSpendBudgetGate:
    """generate_performance_take refuses paid retargeting before dispatch."""

    def _build_controller(self, project: dict, tmp_path):
        from cinema.shots.controller import ShotController

        keyframe_path = str(tmp_path / "keyframe.jpg")
        open(keyframe_path, "wb").write(b"fake_jpg")

        host = MagicMock()
        host._refresh_project_snapshot.return_value = project
        host._resolve_take_path.return_value = keyframe_path
        host._ensure_scene_audio.return_value = ""
        host._save_checkpoint.return_value = None

        lifecycle = MagicMock()
        lifecycle.report_progress.return_value = None
        runstate = MagicMock()
        runstate.update_progress_pointer.return_value = None

        core = MagicMock()
        core.project = project
        core.project_dir = str(tmp_path)
        core.continuity = MagicMock()
        cost_tracker = MagicMock()
        cost_tracker.is_over_budget.return_value = False
        cost_tracker.would_exceed.return_value = False
        cost_tracker.spent_usd = 0.80
        cost_tracker.budget_usd = 1.00
        core.cost_tracker = cost_tracker

        ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
        ctrl._take_output_path = MagicMock(
            side_effect=lambda shot_id, take_id, ext: str(tmp_path / f"{take_id}{ext}")
        )
        ctrl._mutate_shot = MagicMock(side_effect=lambda shot_id, mutator: {"id": "perf_take"})
        return ctrl, lifecycle, cost_tracker

    def _make_project(self, tmp_path):
        driving = tmp_path / "drive.mp4"
        driving.write_bytes(b"fake_mp4")
        return {
            "id": "proj_perf_budget_gate_test",
            "characters": [{"id": "char_1", "name": "Alice"}],
            "global_settings": {},
            "scenes": [{
                "id": "scene_1",
                "title": "Scene",
                "duration_seconds": 5.0,
                "characters_present": ["char_1"],
                "shots": [{
                    "id": "shot_1_0",
                    "prompt": "Action shot",
                    "plan_status": "approved",
                    "shot_type": "action",
                    "characters_in_frame": ["char_1"],
                    "approved_keyframe_take_id": "kf_t1",
                    "driving_video_path": str(driving),
                }],
            }],
        }

    def test_refuses_performance_dispatch_when_would_exceed(self, tmp_path):
        project = self._make_project(tmp_path)
        ctrl, lifecycle, cost_tracker = self._build_controller(project, tmp_path)
        cost_tracker.would_exceed.return_value = True

        dispatch = MagicMock()
        with patch("performance._router.dispatch", dispatch):
            result = ctrl.generate_performance_take("scene_1", "shot_1_0")

        assert result.get("success") is False
        assert result.get("error_kind") == "budget"
        assert result.get("engine") == "VIGGLE"
        dispatch.assert_not_called()
        lifecycle.pause.assert_called_once()
        cost_tracker.would_exceed.assert_called_once_with("VIGGLE")
        events = [c.args[0] for c in lifecycle.report_progress.call_args_list if c.args]
        assert "BUDGET_EXCEEDED" in events

    def test_proceeds_when_performance_budget_allows(self, tmp_path):
        project = self._make_project(tmp_path)
        ctrl, lifecycle, cost_tracker = self._build_controller(project, tmp_path)
        cost_tracker.would_exceed.return_value = False

        def _dispatch(*args, **kwargs):
            output = kwargs["output_mp4"]
            open(output, "wb").write(b"fake_mp4")
            return output

        with (
            patch("performance._router.dispatch", side_effect=_dispatch) as dispatch,
            patch("performance.identity_gate.validate_performance_take", return_value=None),
        ):
            result = ctrl.generate_performance_take("scene_1", "shot_1_0")

        assert result.get("success") is True
        dispatch.assert_called_once()
        lifecycle.pause.assert_not_called()
        cost_tracker.would_exceed.assert_called_once_with("VIGGLE")

    def test_mode_b_refuses_when_combined_driving_and_engine_cost_exceeds_budget(self, tmp_path):
        """Correct behavior: refuse before Mode-B synth when combined spend exceeds cap."""
        from cost_tracker import CostTracker

        audio = tmp_path / "scene.mp3"
        audio.write_bytes(b"fake_mp3")
        driving = tmp_path / "driving.mp4"

        project = {
            "id": "proj_perf_mode_b_budget_gap",
            "characters": [{"id": "char_1", "name": "Alice"}],
            "global_settings": {},
            "scenes": [{
                "id": "scene_1",
                "title": "Scene",
                "duration_seconds": 5.0,
                "characters_present": ["char_1"],
                "shots": [{
                    "id": "shot_1_0",
                    "prompt": "Medium dialogue shot",
                    "plan_status": "approved",
                    "shot_type": "medium",
                    "characters_in_frame": ["char_1"],
                    "dialogue": "hello there",
                    "approved_keyframe_take_id": "kf_t1",
                }],
            }],
        }
        ctrl, lifecycle, _mock_tracker = self._build_controller(project, tmp_path)
        ctrl._host._ensure_scene_audio.return_value = str(audio)
        tracker = CostTracker(db_path=str(tmp_path / "cost.db"), budget_usd=1.00)
        # WS4: Hedra removed from Mode-B (2026-07-18) — the pre-spend gate's
        # driving-cost estimate now uses the sole surviving engine (sadtalker,
        # $0.02 base + $0.005/s), so 0.71 spent is the smallest bump that still
        # pushes ACT_ONE (0.25) + sadtalker driving (0.045 @ 5s) = 0.295 over
        # the $1.00 cap (0.71 + 0.295 = 1.005 > 1.00).
        tracker.spent_usd = 0.71
        ctrl._core.cost_tracker = tracker

        def _synth(**kwargs):
            driving.write_bytes(b"fake_driving")
            tracker.log_api(
                provider="sadtalker",
                model="driving_face",
                operation="performance_capture_driving",
                cost_usd=0.045,  # matches estimate_driving_face_cost('sadtalker', 5s)
            )
            return str(driving), "sadtalker"

        def _dispatch(*args, **kwargs):
            output = kwargs["output_mp4"]
            open(output, "wb").write(b"fake_mp4")
            tracker.log_api(
                provider="runway",
                model="act_one",
                operation="performance_capture",
                cost_usd=0.25,
            )
            return output

        try:
            with (
                patch("performance.driving_video.synth_driving_face_from_audio", side_effect=_synth) as synth,
                patch("performance._router.dispatch", side_effect=_dispatch) as dispatch,
                patch("performance.identity_gate.validate_performance_take", return_value=None),
            ):
                result = ctrl.generate_performance_take("scene_1", "shot_1_0")

            assert result.get("success") is False
            assert result.get("error_kind") == "budget"
            synth.assert_not_called()
            dispatch.assert_not_called()
            lifecycle.pause.assert_called_once()
            assert tracker.spent_usd == pytest.approx(0.71)
            assert not driving.exists()
        finally:
            tracker.close()

    def test_mode_b_budget_pause_parks_at_performance_review_not_cancel(self):
        """Budget refusal pauses the run; review/cancel remains operator-owned."""
        from cinema.lifecycle import ThreadedLifecycle

        lifecycle = ThreadedLifecycle()

        lifecycle.pause()

        assert lifecycle.is_paused() is True
        assert lifecycle.is_cancelled() is False
        assert lifecycle.wait_for_gate(
            "PERFORMANCE_REVIEW",
            lambda: True,
            poll_interval=0.01,
        ) is True


class TestPerformancePhaseBudgetAbort:
    """PerformanceCapturePhase stops at a structured budget refusal."""

    _BUDGET_REFUSAL = {
        "success": False,
        "error": "Budget cap reached — performance capture not started",
        "error_kind": "budget",
    }

    def _make_ctx(self):
        lc = MagicMock()
        lc.is_cancelled.return_value = False
        return MagicMock(lifecycle=lc)

    def _make_project(self, n_shots=3):
        shots = [
            {"id": f"s1_{i}", "approved_keyframe_take_id": "kf_001"}
            for i in range(n_shots)
        ]
        return {"id": "proj_perf_budget_abort", "scenes": [{"id": "scene_1", "shots": shots}]}

    def test_performance_loop_aborts_on_budget_refusal(self):
        from cinema.phases.performance import PerformanceCapturePhase

        gen = MagicMock()
        gen.generate_performance_take.return_value = self._BUDGET_REFUSAL
        on_failure = MagicMock()
        phase = PerformanceCapturePhase(
            shot_generator=gen, project=self._make_project(), on_failure=on_failure,
        )

        result = phase.run(self._make_ctx())

        assert gen.generate_performance_take.call_count == 1
        on_failure.assert_not_called()
        assert result.ok is False
        assert "budget" in result.message.lower()

    def test_performance_loop_continues_on_ordinary_failure(self):
        from cinema.phases.performance import PerformanceCapturePhase

        gen = MagicMock()
        gen.generate_performance_take.return_value = {"success": False, "error": "boom"}
        on_failure = MagicMock()
        phase = PerformanceCapturePhase(
            shot_generator=gen, project=self._make_project(), on_failure=on_failure,
        )

        result = phase.run(self._make_ctx())

        assert gen.generate_performance_take.call_count == 3
        assert on_failure.call_count == 3
        assert result.ok is True


class TestKeyframePreSpendBudgetGate:
    """generate_keyframe_take refuses to spend when the estimated image-gen
    cost would push spend past the budget cap (FOLLOW-UP (a) Site 1).

    generate_ai_broll's backend cascade is PRIORITY-0 Gemini (GEMINI_IMAGE)
    whenever character_image (== primary_reference) is truthy
    (phase_c_assembly.py); otherwise the cascade's next entry point is the
    ComfyUI PuLID path (COMFYUI_PULID). Harness mirrors
    _build_controller_for_lora_strength() in test_char_lora_strength_thread.py
    (lightweight seam to generate_ai_broll — no real project-dir disk I/O).
    """

    def _build_controller(self, primary_reference=None):
        from cinema.shots.controller import ShotController

        char_id = "char_1"
        shot = {
            "id": "shot_1_0",
            "plan_status": "approved",
            "characters_in_frame": [char_id],
            "camera": "medium_shot",
            "target_api": "AUTO",
        }
        scene = {
            "id": "scene_1",
            "title": "T",
            "action": "A",
            "location_id": None,
            "shots": [shot],
        }
        project = {
            "id": "proj_kf_budget_gate",
            "scenes": [scene],
            "characters": [{"id": char_id, "name": "Alice"}],
            "objects": [],
            "locations": [],
            "global_settings": {},
        }

        host = MagicMock()
        host._refresh_project_snapshot.return_value = project
        lifecycle = MagicMock()
        lifecycle.report_progress.return_value = None
        runstate = MagicMock()
        runstate.shot_results = {}
        runstate.update_progress_pointer.return_value = None

        continuity_config = {"multi_angle_refs": []}
        if primary_reference is not None:
            continuity_config["primary_reference"] = primary_reference

        core = MagicMock()
        core.project = project
        core.project_dir = "/tmp/fake_kf_budget_project"
        core.continuity = MagicMock()
        core.continuity.enhance_shot_prompt.return_value = {
            "prompt": "base prompt",
            "continuity_config": continuity_config,
        }
        cost_tracker = MagicMock()
        cost_tracker.is_over_budget.return_value = False
        cost_tracker.would_exceed.return_value = False
        cost_tracker.spent_usd = 0.0
        cost_tracker.budget_usd = None
        core.cost_tracker = cost_tracker

        ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
        # Lightweight seam (mirrors test_char_lora_strength_thread.py): a
        # nonexistent output path means generate_ai_broll's own return value
        # never needs to be a real ImageGenResult — os.path.exists(img_path)
        # fails right after the call, which is fine for these tests (they
        # only assert on whether/how generate_ai_broll was invoked).
        ctrl._take_output_path = MagicMock(return_value="/nonexistent/keyframe.jpg")
        ctrl._resolve_previous_approved_keyframe = MagicMock(return_value="")
        ctrl._mutate_shot = MagicMock()
        return ctrl, lifecycle, cost_tracker

    def test_refuses_generation_when_would_exceed_with_primary_reference(self):
        """GEMINI_IMAGE branch: primary_reference set -> gate prices GEMINI_IMAGE."""
        ctrl, lifecycle, cost_tracker = self._build_controller(primary_reference="/fake/ref.jpg")
        cost_tracker.would_exceed.return_value = True
        # The gate formats these as floats — must be real numbers, not MagicMock.
        cost_tracker.spent_usd = 0.80
        cost_tracker.budget_usd = 1.00

        gen_broll = MagicMock()
        with patch("cinema.shots.controller.generate_ai_broll", gen_broll):
            result = ctrl.generate_keyframe_take("scene_1", "shot_1_0")

        assert result.get("success") is False
        assert "budget" in result.get("error", "").lower()
        # Structured kind — the keyframe phase loop keys its abort on this,
        # not on parsing the human-facing error string.
        assert result.get("error_kind") == "budget"
        gen_broll.assert_not_called()
        lifecycle.pause.assert_called_once()
        cost_tracker.would_exceed.assert_called_once_with("GEMINI_IMAGE")
        # The refusal must be visible to the UI: a BUDGET_EXCEEDED progress
        # event is emitted (ctrl.progress proxies lifecycle.report_progress).
        events = [c.args[0] for c in lifecycle.report_progress.call_args_list if c.args]
        assert "BUDGET_EXCEEDED" in events

    def test_refuses_generation_uses_comfyui_pulid_estimate_when_no_primary_ref(self):
        """Anti-mutation pin: absent primary_reference must price COMFYUI_PULID,
        not silently fall back to GEMINI_IMAGE (or an unpriced 0.0 estimate)."""
        ctrl, lifecycle, cost_tracker = self._build_controller(primary_reference=None)
        cost_tracker.would_exceed.return_value = True
        cost_tracker.spent_usd = 0.80
        cost_tracker.budget_usd = 1.00

        gen_broll = MagicMock()
        with patch("cinema.shots.controller.generate_ai_broll", gen_broll):
            result = ctrl.generate_keyframe_take("scene_1", "shot_1_0")

        assert result.get("success") is False
        assert result.get("error_kind") == "budget"
        gen_broll.assert_not_called()
        cost_tracker.would_exceed.assert_called_once_with("COMFYUI_PULID")
        lifecycle.pause.assert_called_once()

    def test_proceeds_when_within_budget(self):
        """Control: would_exceed False -> generation proceeds, no pause."""
        ctrl, lifecycle, cost_tracker = self._build_controller(primary_reference="/fake/ref.jpg")
        cost_tracker.would_exceed.return_value = False

        gen_broll = MagicMock()
        with patch("cinema.shots.controller.generate_ai_broll", gen_broll):
            ctrl.generate_keyframe_take("scene_1", "shot_1_0")

        gen_broll.assert_called_once()
        lifecycle.pause.assert_not_called()
        cost_tracker.would_exceed.assert_called_once_with("GEMINI_IMAGE")


class TestKeyframePhaseBudgetAbort:
    """Phase-level behavior when the per-take gate refuses for budget
    (FOLLOW-UP (a) Site 2). Mirrors TestBudgetPhaseAbort /
    TestPerformancePhaseBudgetAbort for KeyframeRenderPhase.
    """

    _BUDGET_REFUSAL = {
        "success": False,
        "error": "Budget cap reached — keyframe generation not started",
        "error_kind": "budget",
    }

    def _make_ctx(self):
        lc = MagicMock()
        lc.is_cancelled.return_value = False
        return MagicMock(lifecycle=lc)

    def _make_project(self, n_shots=3):
        shots = [{"id": f"s1_{i}", "prompt": f"shot {i}"} for i in range(n_shots)]
        return {"id": "proj_kf_budget_abort", "scenes": [{"id": "scene_1", "shots": shots}]}

    def test_per_shot_loop_aborts_on_budget_refusal(self):
        from cinema.phases.keyframe_render import KeyframeRenderPhase

        gen = MagicMock()
        gen.generate_keyframe_take.return_value = self._BUDGET_REFUSAL
        on_failure = MagicMock()
        phase = KeyframeRenderPhase(
            shot_generator=gen, project=self._make_project(), on_failure=on_failure,
        )
        result = phase.run(self._make_ctx())

        assert gen.generate_keyframe_take.call_count == 1
        on_failure.assert_not_called()  # budget stop is not a shot failure
        assert result.ok is False
        assert "budget" in result.message.lower()

    def test_per_shot_loop_continues_on_ordinary_failure(self):
        """Control: failures without error_kind keep the record-and-continue path."""
        from cinema.phases.keyframe_render import KeyframeRenderPhase

        gen = MagicMock()
        gen.generate_keyframe_take.return_value = {"success": False, "error": "boom"}
        on_failure = MagicMock()
        phase = KeyframeRenderPhase(
            shot_generator=gen, project=self._make_project(), on_failure=on_failure,
        )
        result = phase.run(self._make_ctx())

        assert gen.generate_keyframe_take.call_count == 3
        assert on_failure.call_count == 3
        assert result.ok is True
