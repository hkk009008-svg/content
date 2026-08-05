from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from pathlib import Path
import shutil
import subprocess

import pytest

from cinema.shots.controller import ShotController
from performance.driving_clip import (
    DrivingClipError,
    prepare_bounded_driving_clip as _real_prepare_bounded_clip,
)


@pytest.fixture(autouse=True)
def _stub_bounded_driving_clip(monkeypatch):
    """Keep controller unit tests focused while preserving path separation."""

    def _prepare(source_path, *, project_root, duration_s):
        target = Path(project_root) / "performance_inputs" / "bounded" / (
            f"test-{int(float(duration_s) * 25)}f.mp4"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(source_path).read_bytes())
        return str(target)

    monkeypatch.setattr(
        "performance.driving_clip.prepare_bounded_driving_clip",
        _prepare,
    )


def test_accepted_performance_take_persists_exact_project_relative_driving_input(
    tmp_path,
):
    keyframe = tmp_path / "inputs" / "keyframe.jpg"
    audio = tmp_path / "inputs" / "dialogue.mp3"
    uploaded_driving = tmp_path / "inputs" / "operator-driving.mp4"
    keyframe.parent.mkdir(parents=True)
    keyframe.write_bytes(b"keyframe")
    audio.write_bytes(b"audio")
    uploaded_driving.write_bytes(b"operator-driving")

    shot = {
        "id": "shot_1",
        "prompt": "A medium dialogue performance",
        "plan_status": "approved",
        "shot_type": "medium",
        "dialogue": "Hold the line.",
        "characters_in_frame": ["char_1"],
        "approved_keyframe_take_id": "kf_1",
        "driving_video_path": str(uploaded_driving),
    }
    scene = {
        "id": "scene_1",
        "duration_seconds": 20.0,
        "characters_present": ["char_1"],
        "shots": [shot, {"id": "shot_2"}, {"id": "shot_3"}, {"id": "shot_4"}],
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
    dispatched_driving = []
    dispatched_duration = []

    def dispatch(_engine, **kwargs):
        dispatched_driving.append(kwargs["driving_video_path"])
        dispatched_duration.append(kwargs["duration_s"])
        output = kwargs["output_mp4"]
        with open(output, "wb") as handle:
            handle.write(b"performance")
        return output

    with (
        patch("performance._router.dispatch", side_effect=dispatch),
        patch("performance.identity_gate.validate_performance_take", return_value=None),
    ):
        result = controller.generate_performance_take("scene_1", "shot_1")

    assert result["success"] is True
    take = result["take"]
    expected_absolute = str(uploaded_driving)
    expected_dispatched = str(
        tmp_path / "performance_inputs" / "bounded" / "test-125f.mp4"
    )
    assert dispatched_driving == [expected_dispatched]
    assert dispatched_duration == [5.0]
    assert take["metadata"]["driving_video_path"] == str(
        expected_absolute.removeprefix(str(tmp_path) + "/")
    )
    assert take["metadata"]["dispatched_driving_video_path"] == str(
        Path(expected_dispatched).relative_to(tmp_path)
    )
    assert not take["metadata"]["driving_video_path"].startswith("/")
    assert take["metadata"]["driving_source"] == "upload"
    assert take["metadata"]["scene_duration_s"] == 20.0
    assert take["metadata"]["scene_shot_count"] == 4
    assert take["metadata"]["duration_s"] == 5.0
    assert take["metadata"]["duration_capped"] is False
    assert "driving_provider" not in take["metadata"]
    assert shot.get("approved_performance_take_id", "") == ""
    assert any(
        call.args[0] == "PERFORMANCE_REVIEW_REQUIRED"
        for call in lifecycle.report_progress.call_args_list
    )


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
    assert tracker.get_latest_paid_attempt.call_count == 2
    tracker.get_latest_paid_attempt.assert_called_with(
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


@pytest.mark.parametrize("dispatch_mode", ["none", "missing_file", "raises"])
def test_liveportrait_runtime_failure_without_durable_attempt_fails_closed(
    tmp_path, dispatch_mode
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
    tracker.get_latest_paid_attempt.return_value = None
    tracker.spent_usd = 0.0
    tracker.budget_usd = 5.0
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
        side_effect=AssertionError("local execution failure must not become SKIP")
    )

    def fail_dispatch(_engine, **kwargs):
        if dispatch_mode == "none":
            return None
        if dispatch_mode == "missing_file":
            return kwargs["output_mp4"]
        raise RuntimeError("simulated local worker failure")

    with (
        patch(
            "domain.performance.route_performance_engine",
            return_value="LIVE_PORTRAIT",
        ) as route,
        patch(
            "performance.worker_readiness.require_liveportrait_worker_ready"
        ) as require_ready,
        patch("performance._router.dispatch", side_effect=fail_dispatch) as dispatch,
    ):
        result = controller.generate_performance_take("scene_1", "shot_1")

    assert result["success"] is False
    assert result["error_kind"] == "worker_execution"
    assert result["code"] == "local_performance_failed"
    assert result["engine"] == "LIVE_PORTRAIT"
    assert "performance_engine" not in shot
    assert "performance_takes" not in shot
    controller._mutate_shot.assert_not_called()
    route.assert_called_once_with(shot, scene)
    require_ready.assert_called_once_with()
    dispatch.assert_called_once()
    assert dispatch.call_args.args == ("LIVE_PORTRAIT",)
    assert tracker.get_latest_paid_attempt.call_count == 2
    events = [call.args[0] for call in lifecycle.report_progress.call_args_list]
    assert "PERFORMANCE_BLOCKED" in events
    assert "PERFORMANCE_SKIPPED" not in events


def test_missing_driving_upload_blocks_before_audio_or_dispatch(tmp_path):
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
    tracker.spent_usd = 0.0
    tracker.budget_usd = 1.0
    lifecycle = SimpleNamespace(report_progress=MagicMock(), pause=MagicMock())
    runstate = SimpleNamespace(update_progress_pointer=MagicMock())
    host = SimpleNamespace(
        _refresh_project_snapshot=lambda: project,
        _resolve_take_path=lambda *_args: str(keyframe),
        _ensure_scene_audio=MagicMock(
            side_effect=AssertionError("missing driving input must block before paid audio")
        ),
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
        side_effect=AssertionError("missing input must not become SKIP")
    )

    with patch("performance._router.dispatch") as dispatch:
        result = controller.generate_performance_take("scene_1", "shot_1")

    assert result["success"] is False
    assert result["error_kind"] == "input_required"
    assert result["code"] == "driving_video_required"
    assert result["engine"] == "ACT_ONE"
    dispatch.assert_not_called()
    lifecycle.pause.assert_not_called()
    assert "performance_engine" not in shot


def _review_action_controller(tmp_path, *, paid_attempt=None):
    keyframe = tmp_path / "keyframe.jpg"
    audio = tmp_path / "dialogue.mp3"
    driving = tmp_path / "driving.mp4"
    keyframe.write_bytes(b"keyframe")
    audio.write_bytes(b"audio")
    driving.write_bytes(b"driving")
    historical_take = {
        "id": "performance-old",
        "kind": "performance",
        "path": "shots/performance-old.mp4",
        "metadata": {"engine": "ACT_ONE", "driving_video_path": "driving.mp4"},
    }
    shot = {
        "id": "shot_1",
        "plan_status": "approved",
        "shot_type": "medium",
        "dialogue": "Perform this line.",
        "characters_in_frame": ["char_1"],
        "approved_keyframe_take_id": "kf_1",
        "driving_video_path": str(driving),
        "performance_takes": [historical_take],
        "approved_performance_take_id": historical_take["id"],
        "performance_engine": "ACT_ONE",
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
    tracker.get_latest_paid_attempt.return_value = paid_attempt
    tracker.spent_usd = 0.0
    tracker.budget_usd = 5.0
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
    return controller, lifecycle, tracker, project, scene, shot, historical_take


def test_performance_duration_uses_scene_allocation_and_eight_second_cap():
    from cinema.shots.controller import (
        MAX_PERFORMANCE_TAKE_DURATION_S,
        performance_take_duration_details,
        performance_take_duration_s,
    )

    assert performance_take_duration_s({
        "duration_seconds": 30,
        "shots": [{"id": str(index)} for index in range(5)],
    }) == 6.0
    assert performance_take_duration_s({
        "duration_seconds": 120,
        "shots": [{"id": "only"}],
    }) == MAX_PERFORMANCE_TAKE_DURATION_S == 8.0
    assert performance_take_duration_details({
        "duration_seconds": "20",
        "shots": [{"id": "one"}, {"id": "two"}],
    }) == (8.0, 20.0, 2)
    with pytest.raises(ValueError, match="greater than zero"):
        performance_take_duration_s({"duration_seconds": 0, "shots": [{"id": "x"}]})
    with pytest.raises(ValueError, match="shot count is invalid"):
        performance_take_duration_s({"duration_seconds": 10, "shots": [], "num_shots": "bad"})


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="requires ffmpeg and ffprobe",
)
def test_bounded_clip_is_a_retained_physical_eight_second_provider_input(tmp_path):
    source = tmp_path / "performance_inputs" / "source.mp4"
    source.parent.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
            "color=c=blue:s=128x128:r=30", "-t", "10", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", str(source),
        ],
        check=True,
        timeout=30,
    )

    bounded = _real_prepare_bounded_clip(
        str(source), project_root=str(tmp_path), duration_s=8.0,
    )
    repeated = _real_prepare_bounded_clip(
        str(source), project_root=str(tmp_path), duration_s=8.0,
    )
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", bounded,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert bounded != str(source)
    assert repeated == bounded
    assert Path(bounded).is_file()
    assert float(probe.stdout.strip()) <= 8.04

    source_alias = source.with_name("source-alias.mp4")
    source_alias.symlink_to(source)
    with pytest.raises(DrivingClipError, match="non-symlink"):
        _real_prepare_bounded_clip(
            str(source_alias), project_root=str(tmp_path), duration_s=8.0,
        )


def test_invalid_scene_duration_returns_structured_failure_before_dispatch(tmp_path):
    controller, lifecycle, _tracker, _project, scene, _shot, _take = (
        _review_action_controller(tmp_path)
    )
    scene["duration_seconds"] = "not-a-duration"

    with patch("performance._router.dispatch") as dispatch:
        result = controller.generate_performance_take("scene_1", "shot_1")

    assert result["success"] is False
    assert result["code"] == "performance_duration_invalid"
    assert result["error_kind"] == "duration"
    dispatch.assert_not_called()
    assert any(
        call.args[0] == "PERFORMANCE_BLOCKED"
        for call in lifecycle.report_progress.call_args_list
    )


def test_relative_driving_path_cannot_escape_current_project_before_paid_work(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    controller, lifecycle, _tracker, _project, _scene, shot, _take = (
        _review_action_controller(project_root)
    )
    escaped = tmp_path / "escaped-driving.mp4"
    escaped.write_bytes(b"outside-project")
    shot["driving_video_path"] = "../escaped-driving.mp4"
    controller._host._ensure_scene_audio = MagicMock(
        side_effect=AssertionError("unsafe input must fail before audio work")
    )

    with patch("performance._router.dispatch") as dispatch:
        result = controller.generate_performance_take("scene_1", "shot_1")

    assert result["success"] is False
    assert result["code"] == "driving_video_outside_project"
    assert result["error_kind"] == "input_provenance"
    controller._host._ensure_scene_audio.assert_not_called()
    dispatch.assert_not_called()
    assert any(
        call.args[0] == "PERFORMANCE_BLOCKED"
        for call in lifecycle.report_progress.call_args_list
    )


@pytest.mark.parametrize("engine", ["ACT_ONE", "VIGGLE"])
def test_provider_no_output_never_silently_mutates_to_skip(tmp_path, engine):
    controller, lifecycle, tracker, _project, scene, shot, _take = (
        _review_action_controller(tmp_path)
    )
    controller._mutate_shot = MagicMock(
        side_effect=AssertionError("provider failure must not become SKIP")
    )

    with (
        patch("domain.performance.route_performance_engine", return_value=engine),
        patch("performance._router.dispatch", return_value=None),
    ):
        result = controller.generate_performance_take("scene_1", "shot_1")

    assert result == {
        "success": False,
        "error": f"{engine} produced no valid performance output",
        "error_kind": "provider_execution",
        "code": "performance_capture_failed",
        "engine": engine,
    }
    controller._mutate_shot.assert_not_called()
    assert shot["performance_engine"] == "ACT_ONE"
    events = [call.args[0] for call in lifecycle.report_progress.call_args_list]
    assert "PERFORMANCE_BLOCKED" in events
    assert "PERFORMANCE_SKIPPED" not in events
    assert tracker.get_latest_paid_attempt.call_count >= 1


def test_explicit_skip_preserves_history_and_clears_active_performance(tmp_path):
    controller, lifecycle, _tracker, _project, scene, shot, historical_take = (
        _review_action_controller(tmp_path)
    )

    def mutate(_shot_id, mutator):
        return mutator(scene, shot).value

    controller._mutate_shot = mutate
    result = controller.skip_performance_take(
        "scene_1", "shot_1", reason="The acting reference is unusable"
    )

    assert result["success"] is True
    assert result["skipped"] is True
    assert shot["performance_engine"] == "SKIP"
    assert shot["approved_performance_take_id"] == ""
    assert shot["performance_takes"] == [historical_take]
    assert shot["performance_skip"]["decision_source"] == "operator"
    assert shot["performance_skip"]["reason"] == "The acting reference is unusable"
    assert shot["performance_skip"]["operator_reason"] == "The acting reference is unusable"
    assert shot["performance_skip_history"][-1] == shot["performance_skip"]
    assert shot["performance_review_history"][-1] == shot["performance_skip"]
    assert any(
        call.args[0] == "PERFORMANCE_SKIPPED"
        for call in lifecycle.report_progress.call_args_list
    )


@pytest.mark.parametrize("reason", ["", "x" * 241, "hidden\nline"])
def test_explicit_skip_rejects_invalid_reason_before_state_or_authority(
    tmp_path, reason
):
    controller, _lifecycle, tracker, _project, _scene, _shot, _take = (
        _review_action_controller(tmp_path)
    )
    controller._mutate_shot = MagicMock()

    result = controller.skip_performance_take(
        "scene_1", "shot_1", reason=reason
    )

    assert result["success"] is False
    assert result["code"] == "invalid_performance_skip_reason"
    controller._mutate_shot.assert_not_called()
    tracker.get_latest_paid_attempt.assert_not_called()


def test_explicit_skip_fails_closed_while_provider_attempt_is_ambiguous(tmp_path):
    controller, _lifecycle, _tracker, _project, _scene, shot, _take = (
        _review_action_controller(
            tmp_path,
            paid_attempt={
                "attempt_id": "attempt-1",
                "state": "accepted_unknown",
                "provider_job_id": "job-1",
            },
        )
    )
    controller._mutate_shot = MagicMock(
        side_effect=AssertionError("ambiguous provider work must block skip")
    )

    result = controller.skip_performance_take(
        "scene_1", "shot_1", reason="Provider work did not reconcile"
    )

    assert result["success"] is False
    assert result["code"] == "provider_job_deferred"
    assert result["paid_attempt"]["state"] == "accepted_unknown"
    controller._mutate_shot.assert_not_called()
    assert shot["approved_performance_take_id"] == "performance-old"


def _attempt(*, attempt_id, engine, state, provider_job_id=""):
    return {
        "attempt_id": attempt_id,
        "video_id": "project_1",
        "shot_id": "shot_1",
        "engine": engine,
        "operation": "performance_capture",
        "state": state,
        "provider_job_id": provider_job_id,
    }


class _BrokenSnapshotTracker:
    """Production-shaped authority whose durable snapshot read fails."""

    def __init__(self, delegate):
        self._delegate = delegate

    def get_paid_attempts_snapshot(self, _video_id=""):
        raise RuntimeError("simulated paid-attempt store failure")

    def __getattr__(self, name):
        return getattr(self._delegate, name)


def test_snapshot_failure_blocks_generation_and_skip_without_route_fallback(tmp_path):
    controller, _lifecycle, tracker, _project, _scene, _shot, _take = (
        _review_action_controller(tmp_path)
    )
    tracker.get_latest_paid_attempt.return_value = _attempt(
        attempt_id="old-viggle-active",
        engine="VIGGLE",
        state="accepted_unknown",
        provider_job_id="old-viggle-job",
    )
    controller._core.cost_tracker = _BrokenSnapshotTracker(tracker)
    controller._mutate_shot = MagicMock(
        side_effect=AssertionError("unavailable authority must not mutate state")
    )

    with patch("performance._router.dispatch") as dispatch:
        generation = controller.generate_performance_take("scene_1", "shot_1")
        skipped = controller.skip_performance_take(
            "scene_1", "shot_1", reason="Use ordinary motion instead",
        )

    assert generation["success"] is False
    assert generation["code"] == "performance_authority_unavailable"
    assert skipped["success"] is False
    assert skipped["code"] == "performance_authority_unavailable"
    tracker.get_latest_paid_attempt.assert_not_called()
    controller._mutate_shot.assert_not_called()
    dispatch.assert_not_called()


def test_non_operator_same_engine_active_attempt_blocks_new_dispatch(tmp_path):
    controller, _lifecycle, tracker, _project, _scene, _shot, _take = (
        _review_action_controller(tmp_path)
    )
    tracker.get_paid_attempts_snapshot.return_value = {
        "attempts": [
            _attempt(
                attempt_id="act-two-active",
                engine="ACT_ONE",
                state="accepted_unknown",
                provider_job_id="act-two-job",
            )
        ]
    }

    with patch("performance._router.dispatch") as dispatch:
        result = controller.generate_performance_take("scene_1", "shot_1")

    assert result["success"] is False
    assert result["code"] == "provider_job_deferred"
    assert result["paid_attempt"]["attempt_id"] == "act-two-active"
    dispatch.assert_not_called()


def test_same_operator_request_cannot_cross_driving_input_revision(tmp_path):
    from paid_provider import file_fingerprint

    controller, _lifecycle, tracker, _project, scene, shot, _take = (
        _review_action_controller(tmp_path)
    )
    tracker.get_paid_attempts_snapshot.return_value = {"attempts": []}
    old_driving = str(shot["driving_video_path"])
    request_id = "e" * 32
    shot["performance_generation_request"] = {
        "request_id": request_id,
        "status": "deferred",
        "engine": "ACT_ONE",
        "driving_video_revision": old_driving,
        "driving_video_fingerprint": file_fingerprint(old_driving),
    }
    replacement = tmp_path / "replacement-driving.mp4"
    replacement.write_bytes(b"different-driving-input")
    shot["driving_video_path"] = str(replacement)

    with patch("performance._router.dispatch") as dispatch:
        result = controller.generate_performance_take(
            "scene_1",
            "shot_1",
            operator_requested=True,
            operator_request_id=request_id,
        )

    assert result["success"] is False
    assert result["code"] == "performance_request_input_mismatch"
    assert result["request"]["driving_video_revision"] == old_driving
    dispatch.assert_not_called()


def test_succeeded_skip_request_is_not_replayed_after_input_replacement(tmp_path):
    from paid_provider import file_fingerprint

    controller, _lifecycle, tracker, _project, scene, shot, _take = (
        _review_action_controller(tmp_path)
    )
    tracker.get_paid_attempts_snapshot.return_value = {"attempts": []}
    tracker.get_latest_paid_attempt.return_value = None
    old_driving = str(shot["driving_video_path"])
    request_id = "9" * 32
    shot["performance_engine"] = "SKIP"
    shot["performance_skip"] = {
        "id": "operator-skip-old-input",
        "action": "skip",
        "reason": "operator",
        "decision_source": "operator",
        "operator_reason": "Use ordinary motion.",
        "created_at": "2026-08-05T00:00:00+00:00",
        "routed_engine": "ACT_ONE",
        "driving_video_path": old_driving,
    }
    shot["performance_generation_request"] = {
        "request_id": request_id,
        "status": "succeeded",
        "engine": "SKIP",
        "take_id": "",
        "driving_video_revision": old_driving,
        "driving_video_fingerprint": file_fingerprint(old_driving),
    }
    replacement = tmp_path / "replacement-after-skip.mp4"
    replacement.write_bytes(b"replacement-after-skip")
    shot["driving_video_path"] = str(replacement)

    def mutate(_shot_id, mutator):
        return mutator(scene, shot).value

    controller._mutate_shot = mutate

    with patch("performance._router.dispatch") as dispatch:
        result = controller.generate_performance_take(
            "scene_1",
            "shot_1",
            operator_requested=True,
            operator_request_id=request_id,
        )

    assert result["success"] is False
    assert result["code"] == "performance_request_input_mismatch"
    dispatch.assert_not_called()


def test_skip_checks_attempts_from_previous_routes(tmp_path):
    controller, _lifecycle, tracker, _project, _scene, _shot, _take = (
        _review_action_controller(tmp_path)
    )
    tracker.get_paid_attempts_snapshot.return_value = {
        "attempts": [
            _attempt(
                attempt_id="viggle-active",
                engine="VIGGLE",
                state="accepted_unknown",
                provider_job_id="viggle-job",
            )
        ]
    }
    controller._mutate_shot = MagicMock(
        side_effect=AssertionError("old-route provider work must block skip")
    )

    result = controller.skip_performance_take(
        "scene_1", "shot_1", reason="Use ordinary motion instead"
    )

    assert result["success"] is False
    assert result["code"] == "provider_job_deferred"
    assert result["engine"] == "VIGGLE"
    controller._mutate_shot.assert_not_called()


def test_succeeded_attempt_requires_exact_take_binding_before_skip(tmp_path):
    controller, _lifecycle, tracker, _project, _scene, shot, historical_take = (
        _review_action_controller(tmp_path)
    )
    tracker.get_paid_attempts_snapshot.return_value = {
        "attempts": [
            _attempt(
                attempt_id="newer-act-two",
                engine="ACT_ONE",
                state="succeeded",
                provider_job_id="newer-job",
            )
        ]
    }
    controller._mutate_shot = MagicMock(
        side_effect=AssertionError("engine-only history must not reconcile a paid job")
    )

    result = controller.skip_performance_take(
        "scene_1", "shot_1", reason="Use ordinary motion instead"
    )

    assert result["success"] is False
    assert result["code"] == "provider_job_deferred"
    assert historical_take["metadata"]["engine"] == "ACT_ONE"
    assert "paid_attempt_id" not in historical_take["metadata"]
    assert shot["approved_performance_take_id"] == "performance-old"


def test_provider_job_id_binding_cannot_cross_provider_routes(tmp_path):
    controller, _lifecycle, tracker, _project, _scene, _shot, historical_take = (
        _review_action_controller(tmp_path)
    )
    historical_take["metadata"]["provider_job_id"] = "shared-looking-id"
    tracker.get_paid_attempts_snapshot.return_value = {
        "attempts": [
            _attempt(
                attempt_id="viggle-success",
                engine="VIGGLE",
                state="succeeded",
                provider_job_id="shared-looking-id",
            )
        ]
    }
    controller._mutate_shot = MagicMock(
        side_effect=AssertionError("cross-provider job IDs must not reconcile")
    )

    result = controller.skip_performance_take(
        "scene_1", "shot_1", reason="Use ordinary motion instead"
    )

    assert result["success"] is False
    assert result["code"] == "provider_job_deferred"
    assert result["engine"] == "VIGGLE"


def test_exact_paid_attempt_binding_allows_skip_after_success(tmp_path):
    controller, _lifecycle, tracker, _project, scene, shot, historical_take = (
        _review_action_controller(tmp_path)
    )
    historical_take["metadata"]["paid_attempt_id"] = "act-two-success"
    tracker.get_paid_attempts_snapshot.return_value = {
        "attempts": [
            _attempt(
                attempt_id="act-two-success",
                engine="ACT_ONE",
                state="succeeded",
                provider_job_id="act-two-job",
            )
        ]
    }

    def mutate(_shot_id, mutator):
        return mutator(scene, shot).value

    controller._mutate_shot = mutate
    result = controller.skip_performance_take(
        "scene_1", "shot_1", reason="Use ordinary motion instead"
    )

    assert result["success"] is True
    assert shot["performance_engine"] == "SKIP"


def test_same_operator_request_replays_completed_take_without_second_dispatch(tmp_path):
    controller, _lifecycle, tracker, _project, scene, shot, _take = (
        _review_action_controller(tmp_path)
    )
    tracker.get_paid_attempts_snapshot.return_value = {"attempts": []}
    tracker.get_latest_paid_attempt.return_value = {
        **_attempt(
            attempt_id="request-bound-attempt",
            engine="ACT_ONE",
            state="succeeded",
            provider_job_id="request-bound-job",
        ),
        "request_fingerprint": "fingerprint",
    }

    def mutate(_shot_id, mutator):
        return mutator(scene, shot).value

    controller._mutate_shot = mutate

    def dispatch(_engine, **kwargs):
        Path(kwargs["output_mp4"]).write_bytes(b"performance")
        return kwargs["output_mp4"]

    request_id = "a" * 32
    with (
        patch("performance._router.dispatch", side_effect=dispatch) as dispatch_mock,
        patch("performance.identity_gate.validate_performance_take", return_value=None),
    ):
        first = controller.generate_performance_take(
            "scene_1", "shot_1", operator_requested=True,
            operator_request_id=request_id,
        )
        second = controller.generate_performance_take(
            "scene_1", "shot_1", operator_requested=True,
            operator_request_id=request_id,
        )

    assert first["success"] is True
    assert second["success"] is True
    assert second["replayed"] is True
    assert second["take"]["id"] == first["take"]["id"]
    assert dispatch_mock.call_count == 1
    assert len(shot["performance_takes"]) == 2  # historical + one new candidate
    assert shot["performance_generation_request"]["status"] == "succeeded"
    assert first["take"]["metadata"]["paid_attempt_id"] == "request-bound-attempt"


def test_different_operator_request_cannot_bypass_active_action(tmp_path):
    controller, _lifecycle, tracker, _project, _scene, shot, _take = (
        _review_action_controller(tmp_path)
    )
    tracker.get_paid_attempts_snapshot.return_value = {"attempts": []}
    shot["performance_generation_request"] = {
        "request_id": "b" * 32,
        "status": "dispatching",
        "engine": "ACT_ONE",
    }

    with patch("performance._router.dispatch") as dispatch:
        result = controller.generate_performance_take(
            "scene_1", "shot_1", operator_requested=True,
            operator_request_id="c" * 32,
        )

    assert result["success"] is False
    assert result["code"] == "performance_request_active"
    dispatch.assert_not_called()


def test_input_replacement_during_dispatch_retains_only_a_stale_historical_take(tmp_path):
    controller, _lifecycle, tracker, _project, scene, shot, _take = (
        _review_action_controller(tmp_path)
    )
    tracker.get_paid_attempts_snapshot.return_value = {"attempts": []}
    tracker.get_latest_paid_attempt.return_value = None

    def mutate(_shot_id, mutator):
        return mutator(scene, shot).value

    controller._mutate_shot = mutate

    def dispatch(_engine, **kwargs):
        Path(kwargs["output_mp4"]).write_bytes(b"performance")
        shot["driving_video_path"] = "performance_inputs/new-driving.mp4"
        shot["performance_engine"] = "VIGGLE"
        shot["approved_performance_take_id"] = ""
        return kwargs["output_mp4"]

    request_id = "d" * 32
    with (
        patch("performance._router.dispatch", side_effect=dispatch) as dispatch_mock,
        patch("performance.identity_gate.validate_performance_take", return_value=0.99),
    ):
        result = controller.generate_performance_take(
            "scene_1", "shot_1", operator_requested=True,
            operator_request_id=request_id,
        )
        replay = controller.generate_performance_take(
            "scene_1", "shot_1", operator_requested=True,
            operator_request_id=request_id,
        )

    assert result["success"] is True
    assert result["input_revision_stale"] is True
    assert result["take"]["metadata"]["input_revision_stale"] is True
    assert replay["success"] is True
    assert replay["replayed"] is True
    assert replay["input_revision_stale"] is True
    assert replay["take"]["id"] == result["take"]["id"]
    assert dispatch_mock.call_count == 1
    assert shot["approved_performance_take_id"] == ""
    assert shot["performance_engine"] == "VIGGLE"
