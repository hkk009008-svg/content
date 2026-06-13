"""Unit tests for auto-RIFE wiring in ShotController._finalize_motion_take (W1 §5.2).

Before this change, `_finalize_motion_take` never auto-applied frame
interpolation: `assess_motion_quality` only produced a *recommendation* inside
the manual `diagnose_clip` path, and `generate_rife_interpolation` was reachable
only via an explicit `action == "rife"` enhancement dispatch. The pipeline header
and the ai-video-gen skill both falsely claimed auto-RIFE was in-flow.

This wires a best-effort auto-RIFE pass into the finalize step:
  - reads `global_settings.auto_rife_smoothness_threshold` (default 0.4)
  - when threshold > 0, runs `assess_motion_quality` and records `smoothness_score`
  - when smoothness_score < threshold, calls `generate_rife_interpolation`,
    rebinds `take["path"]` to the interpolated output, sets `auto_rife_applied`,
    and records the `FAL_RIFE` cost
  - never raises — a RIFE failure leaves the original take intact

All tests are fully offline — no real APIs, no GPU. `assess_motion_quality` and
`generate_rife_interpolation` are patched at their resolved symbols.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _ensure_kling_native_patchable():
    """Guarantee kling_native.KlingNativeAPI exists (some sibling test files inject
    a bare stub module without the class)."""
    mod = sys.modules.get("kling_native")
    if mod is None:
        mod = types.ModuleType("kling_native")
        mod.KlingNativeAPI = MagicMock  # type: ignore[attr-defined]
        sys.modules["kling_native"] = mod
    elif not hasattr(mod, "KlingNativeAPI"):
        mod.KlingNativeAPI = MagicMock  # type: ignore[attr-defined]


_ensure_kling_native_patchable()


def _setup_ctrl(tmp_path):
    """Construct a REAL ShotController over a minimal project with a fake mutate.

    Mirrors test_f2b_storyboard_mode.TestRecordCostParam._setup_ctrl so the
    auto-RIFE behaviour is exercised through the real _finalize_motion_take flow
    (identity validation → provenance → auto-RIFE → persist) rather than a stub.
    """
    from cinema.shots.controller import ShotController, MutationResult
    from domain.project_manager import make_take

    project = {
        "id": "proj_rife",
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

    stored = {}

    def _fake_mutate(shot_id, mutator, timeout=10):
        fake = {"motion_takes": []}
        result = mutator(scene, fake)
        stored["project_shot"] = fake
        return result.value

    ctrl._mutate_shot = MagicMock(side_effect=_fake_mutate)

    take = make_take(
        "motion",
        source_take_id="kf_001",
        metadata={"scene_id": "sc1", "shot_id": "sh1", "target_api": "KLING_NATIVE", "shot_type": "medium"},
    )
    vid = tmp_path / "vid.mp4"
    vid.write_bytes(b"fake-original")

    return ctrl, scene, shot, take, str(vid), stored


def _finalize(ctrl, scene, shot, take, vid, settings):
    return ctrl._finalize_motion_take(
        scene, shot, take, vid,
        source_image="/f/kf.jpg",
        target_api="KLING_NATIVE",
        cc={}, settings=settings, resolved_shot_type="medium",
        record_cost=False,
    )


class TestAutoRifeFires:
    def test_auto_rife_fires_below_threshold(self, tmp_path):
        """smoothness 0.2 < threshold 0.4 → RIFE runs, take rebinds, cost recorded."""
        ctrl, scene, shot, take, vid, stored = _setup_ctrl(tmp_path)

        rife_out = tmp_path / "interpolated.mp4"
        rife_out.write_bytes(b"fake-rife")

        mq = {"smoothness_score": 0.2, "artifact_frames": [], "frozen_ratio": 0.0, "recommendation": "interpolate"}
        with patch("phase_c_ffmpeg.assess_motion_quality", return_value=mq) as m_assess, \
             patch("cinema.shots.controller.generate_rife_interpolation", return_value=str(rife_out)) as m_rife:
            result = _finalize(ctrl, scene, shot, take, vid, {"auto_rife_smoothness_threshold": 0.4})

        assert result["success"] is True
        m_assess.assert_called_once()
        m_rife.assert_called_once()
        # take path rebound to the interpolated output, and generated_video too
        assert take["path"] == str(rife_out)
        assert result["video"] == str(rife_out)
        assert stored["project_shot"]["generated_video"] == str(rife_out)
        # metadata reflects the decision
        assert take["metadata"]["auto_rife_applied"] is True
        assert take["metadata"]["smoothness_score"] == pytest.approx(0.2)
        # FAL_RIFE cost recorded
        rife_cost_calls = [
            c for c in ctrl.cost_tracker.record_api_call.call_args_list
            if c.args and c.args[0] == "FAL_RIFE"
        ]
        assert len(rife_cost_calls) == 1


class TestAutoRifeSkipped:
    def test_auto_rife_skipped_above_threshold(self, tmp_path):
        """smoothness 0.8 >= threshold 0.4 → RIFE NOT called, original kept."""
        ctrl, scene, shot, take, vid, stored = _setup_ctrl(tmp_path)
        mq = {"smoothness_score": 0.8, "artifact_frames": [], "frozen_ratio": 0.0, "recommendation": "accept"}
        with patch("phase_c_ffmpeg.assess_motion_quality", return_value=mq), \
             patch("cinema.shots.controller.generate_rife_interpolation") as m_rife:
            result = _finalize(ctrl, scene, shot, take, vid, {"auto_rife_smoothness_threshold": 0.4})

        m_rife.assert_not_called()
        assert take["path"] == vid
        assert result["video"] == vid
        # smoothness still recorded for the director UI
        assert take["metadata"]["smoothness_score"] == pytest.approx(0.8)
        assert "auto_rife_applied" not in take["metadata"]

    def test_auto_rife_disabled_when_threshold_zero(self, tmp_path):
        """threshold 0 → assessment is not even run (feature off)."""
        ctrl, scene, shot, take, vid, stored = _setup_ctrl(tmp_path)
        with patch("phase_c_ffmpeg.assess_motion_quality") as m_assess, \
             patch("cinema.shots.controller.generate_rife_interpolation") as m_rife:
            result = _finalize(ctrl, scene, shot, take, vid, {"auto_rife_smoothness_threshold": 0})

        m_assess.assert_not_called()
        m_rife.assert_not_called()
        assert take["path"] == vid
        assert "smoothness_score" not in take["metadata"]

    def test_auto_rife_default_threshold_runs_assessment(self, tmp_path):
        """No explicit setting → default threshold 0.4 is applied (assessment runs)."""
        ctrl, scene, shot, take, vid, stored = _setup_ctrl(tmp_path)
        mq = {"smoothness_score": 0.9, "artifact_frames": [], "frozen_ratio": 0.0, "recommendation": "accept"}
        with patch("phase_c_ffmpeg.assess_motion_quality", return_value=mq) as m_assess, \
             patch("cinema.shots.controller.generate_rife_interpolation") as m_rife:
            _finalize(ctrl, scene, shot, take, vid, {})  # no auto_rife key

        m_assess.assert_called_once()
        m_rife.assert_not_called()  # 0.9 is smooth


class TestAutoRifeBestEffort:
    def test_auto_rife_never_fails_take_on_rife_exception(self, tmp_path):
        """RIFE raising must not lose the take — original path is kept, success True."""
        ctrl, scene, shot, take, vid, stored = _setup_ctrl(tmp_path)
        mq = {"smoothness_score": 0.1, "artifact_frames": [], "frozen_ratio": 0.0, "recommendation": "interpolate"}
        with patch("phase_c_ffmpeg.assess_motion_quality", return_value=mq), \
             patch("cinema.shots.controller.generate_rife_interpolation", side_effect=RuntimeError("rife boom")):
            result = _finalize(ctrl, scene, shot, take, vid, {"auto_rife_smoothness_threshold": 0.4})

        assert result["success"] is True
        assert take["path"] == vid
        assert result["video"] == vid
        assert "auto_rife_applied" not in take["metadata"]

    def test_auto_rife_skipped_for_regenerate_recommendation(self, tmp_path):
        """A 'regenerate' assessment (broken / frozen / unassessable clip — what
        assess_motion_quality returns for short or unreadable videos) must NOT be
        sent to RIFE even though its smoothness_score (0.0) is below threshold:
        interpolation cannot repair a broken clip, and firing a real cloud RIFE
        call on every fake-video unit test would defeat offline testing."""
        ctrl, scene, shot, take, vid, stored = _setup_ctrl(tmp_path)
        mq = {"smoothness_score": 0.0, "artifact_frames": [], "frozen_ratio": 1.0, "recommendation": "regenerate"}
        with patch("phase_c_ffmpeg.assess_motion_quality", return_value=mq), \
             patch("cinema.shots.controller.generate_rife_interpolation") as m_rife:
            result = _finalize(ctrl, scene, shot, take, vid, {"auto_rife_smoothness_threshold": 0.4})

        m_rife.assert_not_called()
        assert take["path"] == vid
        assert take["metadata"]["smoothness_score"] == pytest.approx(0.0)
        assert "auto_rife_applied" not in take["metadata"]

    def test_auto_rife_keeps_original_when_rife_returns_none(self, tmp_path):
        """generate_rife_interpolation returning None (e.g. FAL unconfigured) → original kept."""
        ctrl, scene, shot, take, vid, stored = _setup_ctrl(tmp_path)
        mq = {"smoothness_score": 0.1, "artifact_frames": [], "frozen_ratio": 0.0, "recommendation": "interpolate"}
        with patch("phase_c_ffmpeg.assess_motion_quality", return_value=mq), \
             patch("cinema.shots.controller.generate_rife_interpolation", return_value=None):
            result = _finalize(ctrl, scene, shot, take, vid, {"auto_rife_smoothness_threshold": 0.4})

        assert result["success"] is True
        assert take["path"] == vid
        assert "auto_rife_applied" not in take["metadata"]


class TestAutoRifeCostKey:
    def test_fal_rife_priced_in_api_cost_usd(self):
        from cost_tracker import API_COST_USD
        assert "FAL_RIFE" in API_COST_USD
        assert API_COST_USD["FAL_RIFE"] > 0
