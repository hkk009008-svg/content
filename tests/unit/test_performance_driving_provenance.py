from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cinema.shots.controller import ShotController


@pytest.mark.parametrize("source_mode", ["upload", "tts_auto"])
def test_accepted_performance_take_persists_exact_project_relative_driving_input(
    tmp_path, source_mode
):
    keyframe = tmp_path / "inputs" / "keyframe.jpg"
    audio = tmp_path / "inputs" / "dialogue.mp3"
    uploaded_driving = tmp_path / "inputs" / "operator-driving.mp4"
    keyframe.parent.mkdir(parents=True)
    keyframe.write_bytes(b"keyframe")
    audio.write_bytes(b"audio")
    if source_mode == "upload":
        uploaded_driving.write_bytes(b"operator-driving")

    shot = {
        "id": "shot_1",
        "prompt": "A medium dialogue performance",
        "plan_status": "approved",
        "shot_type": "medium",
        "dialogue": "Hold the line.",
        "characters_in_frame": ["char_1"],
        "approved_keyframe_take_id": "kf_1",
    }
    if source_mode == "upload":
        shot["driving_video_path"] = str(uploaded_driving)
    scene = {
        "id": "scene_1",
        "duration_seconds": 5.0,
        "characters_present": ["char_1"],
        "shots": [shot],
    }
    project = {
        "id": "project_1",
        "characters": [{"id": "char_1", "name": "Actor"}],
        "global_settings": {},
        "scenes": [scene],
    }

    tracker = MagicMock()
    tracker.would_exceed.return_value = False
    tracker.would_exceed_cost.return_value = False
    tracker.spent_usd = 0.0
    tracker.budget_usd = 5.0
    lifecycle = SimpleNamespace(
        report_progress=MagicMock(),
        pause=MagicMock(),
    )
    runstate = SimpleNamespace(update_progress_pointer=MagicMock())
    host = SimpleNamespace(
        _refresh_project_snapshot=lambda: project,
        _resolve_take_path=lambda *_args: str(keyframe),
        _ensure_scene_audio=lambda *_args: str(audio),
        _save_checkpoint=MagicMock(),
        _runstate=runstate,
    )
    core = SimpleNamespace(
        project=project,
        project_dir=str(tmp_path),
        continuity=MagicMock(),
        cost_tracker=tracker,
    )
    controller = ShotController(core, lifecycle, host, runstate)

    def mutate(_shot_id, mutator):
        return mutator(scene, shot).value

    controller._mutate_shot = mutate
    synthesized_path = tmp_path / "shots" / "shot_1" / "outputs" / "driving_kf_1.mp4"

    def synth(**kwargs):
        assert kwargs["output_mp4"] == str(synthesized_path)
        synthesized_path.write_bytes(b"mode-b-driving")
        return str(synthesized_path), "sadtalker"

    dispatched_driving = []

    def dispatch(_engine, **kwargs):
        dispatched_driving.append(kwargs["driving_video_path"])
        output = kwargs["output_mp4"]
        with open(output, "wb") as handle:
            handle.write(b"performance")
        return output

    with (
        patch("performance.driving_video.synth_driving_face_from_audio", side_effect=synth) as synth_call,
        patch("performance._router.dispatch", side_effect=dispatch),
        patch("performance.identity_gate.validate_performance_take", return_value=None),
    ):
        result = controller.generate_performance_take("scene_1", "shot_1")

    assert result["success"] is True
    take = result["take"]
    expected_absolute = (
        str(uploaded_driving) if source_mode == "upload" else str(synthesized_path)
    )
    assert dispatched_driving == [expected_absolute]
    assert take["metadata"]["driving_video_path"] == str(
        expected_absolute.removeprefix(str(tmp_path) + "/")
    )
    assert not take["metadata"]["driving_video_path"].startswith("/")
    if source_mode == "upload":
        synth_call.assert_not_called()
        assert take["metadata"]["driving_provider"] is None
    else:
        synth_call.assert_called_once()
        assert take["metadata"]["driving_provider"] == "sadtalker"


@pytest.mark.parametrize("engine", ["LIVE_PORTRAIT", "VIGGLE"])
@pytest.mark.parametrize(
    ("attempt_state", "expected_kind"),
    [("succeeded", "deferred"), ("blocked_budget", "budget")],
)
def test_missing_local_output_preserves_durable_performance_authority(
    tmp_path, engine, attempt_state, expected_kind
):
    keyframe = tmp_path / "keyframe.jpg"
    audio = tmp_path / "dialogue.mp3"
    driving = tmp_path / "driving.mp4"
    keyframe.write_bytes(b"keyframe")
    audio.write_bytes(b"audio")
    driving.write_bytes(b"driving")
    shot = {
        "id": "shot_1",
        "plan_status": "approved",
        "shot_type": "medium",
        "dialogue": "Perform this line.",
        "characters_in_frame": ["char_1"],
        "approved_keyframe_take_id": "kf_1",
        "driving_video_path": str(driving),
    }
    scene = {
        "id": "scene_1",
        "duration_seconds": 5.0,
        "characters_present": ["char_1"],
        "shots": [shot],
    }
    project = {
        "id": "project_1",
        "characters": [{"id": "char_1", "name": "Actor"}],
        "global_settings": {},
        "scenes": [scene],
    }
    tracker = MagicMock()
    tracker.would_exceed.return_value = False
    tracker.spent_usd = 0.0
    tracker.budget_usd = 5.0
    tracker.get_latest_paid_attempt.return_value = {
        "attempt_id": f"{engine.lower()}-attempt",
        "state": attempt_state,
        "provider_job_id": f"{engine.lower()}-job",
    }
    lifecycle = SimpleNamespace(report_progress=MagicMock(), pause=MagicMock())
    runstate = SimpleNamespace(update_progress_pointer=MagicMock())
    host = SimpleNamespace(
        _refresh_project_snapshot=lambda: project,
        _resolve_take_path=lambda *_args: str(keyframe),
        _ensure_scene_audio=lambda *_args: str(audio),
        _save_checkpoint=MagicMock(),
        _runstate=runstate,
    )
    core = SimpleNamespace(
        project=project,
        project_dir=str(tmp_path),
        continuity=MagicMock(),
        cost_tracker=tracker,
    )
    controller = ShotController(core, lifecycle, host, runstate)
    controller._mutate_shot = MagicMock(
        side_effect=AssertionError("durable task must not be converted to SKIP")
    )

    with (
        patch("domain.performance.route_performance_engine", return_value=engine),
        patch("performance._router.dispatch", return_value=None),
    ):
        result = controller.generate_performance_take("scene_1", "shot_1")

    assert result["success"] is False
    assert result["error_kind"] == expected_kind
    assert result["engine"] == engine
    assert result["paid_attempt"]["state"] == attempt_state
    tracker.get_latest_paid_attempt.assert_called_once_with(
        video_id="project_1",
        shot_id="shot_1",
        engine=engine,
        operation="performance_capture",
    )
    assert "performance_engine" not in shot
    if attempt_state == "blocked_budget":
        lifecycle.pause.assert_called_once()
    else:
        lifecycle.pause.assert_not_called()


def test_mode_b_atomic_budget_refusal_cannot_fall_through_to_performance(
    tmp_path,
):
    keyframe = tmp_path / "keyframe.jpg"
    audio = tmp_path / "dialogue.mp3"
    keyframe.write_bytes(b"keyframe")
    audio.write_bytes(b"audio")
    shot = {
        "id": "shot_1",
        "plan_status": "approved",
        "shot_type": "medium",
        "dialogue": "Perform this line.",
        "characters_in_frame": ["char_1"],
        "approved_keyframe_take_id": "kf_1",
    }
    scene = {
        "id": "scene_1",
        "duration_seconds": 5.0,
        "characters_present": ["char_1"],
        "shots": [shot],
    }
    project = {
        "id": "project_1",
        "characters": [{"id": "char_1", "name": "Actor"}],
        "global_settings": {},
        "scenes": [scene],
    }
    tracker = MagicMock()
    tracker.would_exceed_cost.return_value = False
    tracker.spent_usd = 1.0
    tracker.budget_usd = 1.0
    tracker.get_latest_paid_attempt.return_value = {
        "attempt_id": "mode-b-budget",
        "state": "blocked_budget",
    }
    lifecycle = SimpleNamespace(report_progress=MagicMock(), pause=MagicMock())
    runstate = SimpleNamespace(update_progress_pointer=MagicMock())
    host = SimpleNamespace(
        _refresh_project_snapshot=lambda: project,
        _resolve_take_path=lambda *_args: str(keyframe),
        _ensure_scene_audio=lambda *_args: str(audio),
        _save_checkpoint=MagicMock(),
        _runstate=runstate,
    )
    core = SimpleNamespace(
        project=project,
        project_dir=str(tmp_path),
        continuity=MagicMock(),
        cost_tracker=tracker,
    )
    controller = ShotController(core, lifecycle, host, runstate)
    controller._mutate_shot = MagicMock(
        side_effect=AssertionError("budget refusal must not become SKIP")
    )

    with (
        patch("performance.driving_video.synth_driving_face_from_audio", return_value=None),
        patch("performance._router.dispatch") as dispatch,
    ):
        result = controller.generate_performance_take("scene_1", "shot_1")

    assert result["success"] is False
    assert result["error_kind"] == "budget"
    assert result["engine"] == "PERFORMANCE_DRIVING_SADTALKER"
    dispatch.assert_not_called()
    lifecycle.pause.assert_called_once()
    assert "performance_engine" not in shot
