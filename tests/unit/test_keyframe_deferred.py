"""Durable keyframe-provider recovery and duplicate-submit guards."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cinema.phases.keyframe_render import KeyframeRenderPhase
from cinema.runstate import RunState
from cinema.services import state_snapshot
from cinema.shots.controller import ShotController
from phase_c_assembly import ImageGenResult


def _controller():
    shot = {
        "id": "shot_1",
        "plan_status": "approved",
        "characters_in_frame": [],
        "camera": "medium_shot",
        "target_api": "AUTO",
    }
    scene = {
        "id": "scene_1",
        "title": "Scene",
        "action": "Action",
        "location_id": None,
        "shots": [shot],
    }
    project = {
        "id": "proj_keyframe_deferred",
        "scenes": [scene],
        "characters": [],
        "objects": [],
        "locations": [],
        "global_settings": {},
    }
    core = SimpleNamespace(
        project=project,
        project_dir="/tmp/proj_keyframe_deferred",
        continuity=MagicMock(),
        cost_tracker=MagicMock(),
    )
    core.continuity.enhance_shot_prompt.return_value = {
        "prompt": "base prompt",
        "continuity_config": {"multi_angle_refs": []},
    }
    core.cost_tracker.would_exceed.return_value = False
    core.cost_tracker.spent_usd = 0.0
    core.cost_tracker.budget_usd = None
    lifecycle = MagicMock()
    lifecycle.report_progress.return_value = None
    host = MagicMock()
    host._refresh_project_snapshot.return_value = project
    controller = ShotController(core, lifecycle, host, RunState())
    controller._resolve_previous_approved_keyframe = MagicMock(return_value="")
    controller._take_output_path = MagicMock(return_value="/missing/keyframe.jpg")

    def _mutate_shot(shot_id, mutator, timeout=10):
        assert shot_id == shot["id"]
        return mutator(scene, shot).value

    controller._mutate_shot = _mutate_shot
    return controller, project, shot


def test_unknown_comfyui_state_persists_and_blocks_duplicate_submission():
    controller, _project, shot = _controller()
    provider_calls = []

    def _unknown_provider(*args, **kwargs):
        provider_calls.append(kwargs)
        kwargs["_recovery_out"].update({
            "engine": "COMFYUI_PULID",
            "status": "recovery_required",
            "provider_status": "job_state_unknown",
            "reason": "Reconcile ComfyUI before retrying.",
            "job_id": "prompt-123",
            "_billed_rejects": ("GEMINI_IMAGE",),
        })
        return None

    with patch("cinema.shots.controller.generate_ai_broll", _unknown_provider):
        first = controller.generate_keyframe_take("scene_1", "shot_1")
        second = controller.generate_keyframe_take("scene_1", "shot_1")

    assert first["error_kind"] == "deferred"
    assert first["code"] == "keyframe_job_deferred"
    assert first["deferred_job"]["job_id"] == "prompt-123"
    assert "attempt_id" not in first["deferred_job"]
    assert second["error_kind"] == "deferred"
    assert len(provider_calls) == 1
    assert shot["deferred_keyframe_job"]["provider_status"] == "job_state_unknown"
    assert "_billed_rejects" not in shot["deferred_keyframe_job"]
    controller.cost_tracker.record_api_call.assert_called_once_with(
        "GEMINI_IMAGE",
        operation="image_generation_rejected",
        shot_id="shot_1",
        video_id="proj_keyframe_deferred",
    )


def test_operator_resolution_clears_marker_and_appends_audit_diagnostic():
    controller, _project, shot = _controller()
    shot["deferred_keyframe_job"] = {
        "engine": "COMFYUI_PULID",
        "status": "recovery_required",
        "provider_status": "job_state_unknown",
        "job_id": "prompt-123",
    }

    result = controller.resolve_deferred_keyframe_job("shot_1")

    assert result["success"] is True
    assert "deferred_keyframe_job" not in shot
    assert shot["diagnostics"][-1]["kind"] == "keyframe_recovery_resolved"
    assert shot["diagnostics"][-1]["job_id"] == "prompt-123"


def test_manual_resolution_rejects_a_still_active_request_window():
    controller, _project, shot = _controller()
    shot["deferred_keyframe_job"] = {
        "engine": "KEYFRAME_PIPELINE",
        "status": "recovery_required",
        "provider_status": "submission_claimed",
        "attempt_id": "take_active",
        "resolve_after": "2999-01-01T00:00:00+00:00",
    }

    result = controller.resolve_deferred_keyframe_job("shot_1")

    assert result["success"] is False
    assert result["code"] == "keyframe_attempt_active"
    assert shot["deferred_keyframe_job"]["attempt_id"] == "take_active"


def test_late_completion_cannot_clear_or_publish_over_a_newer_attempt(tmp_path):
    controller, _project, shot = _controller()
    output = tmp_path / "late.jpg"
    controller._take_output_path = MagicMock(return_value=str(output))

    def _late_provider(*args, **kwargs):
        # Simulate a request that exceeded its active window: the operator
        # reconciles it and a newer request claims the shot just before the
        # old provider response arrives.
        shot["deferred_keyframe_job"]["resolve_after"] = (
            "2000-01-01T00:00:00+00:00"
        )
        assert controller.resolve_deferred_keyframe_job("shot_1")["success"] is True
        newer = {
            "engine": "KEYFRAME_PIPELINE",
            "status": "recovery_required",
            "provider_status": "submission_claimed",
            "attempt_id": "take_newer",
            "resolve_after": "2999-01-01T00:00:00+00:00",
        }
        assert controller._claim_deferred_keyframe_job("shot_1", newer)["claimed"] is True
        output.write_bytes(b"image")
        return ImageGenResult(str(output), "COMFYUI_PULID")

    with patch("cinema.shots.controller.generate_ai_broll", _late_provider):
        result = controller.generate_keyframe_take("scene_1", "shot_1")

    assert result["success"] is False
    assert result["error_kind"] == "deferred"
    assert shot["deferred_keyframe_job"]["attempt_id"] == "take_newer"
    assert shot.get("keyframe_takes", []) == []


def test_completed_missing_output_records_winner_and_billed_reject():
    controller, _project, shot = _controller()

    with patch(
        "cinema.shots.controller.generate_ai_broll",
        return_value=ImageGenResult(
            "/missing/keyframe.jpg",
            "FLUX_KONTEXT",
            ("GEMINI_IMAGE",),
        ),
    ):
        result = controller.generate_keyframe_take("scene_1", "shot_1")

    assert result["error_kind"] == "deferred"
    assert shot["deferred_keyframe_job"]["provider_status"] == "output_missing"
    calls = controller.cost_tracker.record_api_call.call_args_list
    assert [call.args[0] for call in calls] == ["FLUX_KONTEXT", "GEMINI_IMAGE"]
    assert [call.kwargs["operation"] for call in calls] == [
        "keyframe_generation",
        "image_generation_rejected",
    ]


def test_terminal_generation_failure_records_billed_reject_without_deferring():
    controller, _project, shot = _controller()

    def _failed_provider(*args, **kwargs):
        kwargs["_recovery_out"]["_billed_rejects"] = ("GEMINI_IMAGE",)
        return None

    with patch("cinema.shots.controller.generate_ai_broll", _failed_provider):
        result = controller.generate_keyframe_take("scene_1", "shot_1")

    assert result == {"success": False, "error": "Image generation failed"}
    assert "deferred_keyframe_job" not in shot
    controller.cost_tracker.record_api_call.assert_called_once_with(
        "GEMINI_IMAGE",
        operation="image_generation_rejected",
        shot_id="shot_1",
        video_id="proj_keyframe_deferred",
    )


def test_idle_state_routes_persisted_recovery_back_to_keyframe_review(monkeypatch):
    _controller_instance, project, shot = _controller()
    shot["deferred_keyframe_job"] = {
        "engine": "COMFYUI_PULID",
        "status": "recovery_required",
        "provider_status": "job_state_unknown",
    }
    monkeypatch.setattr("cinema.services.load_project", lambda project_id: project)

    state = state_snapshot(project["id"])

    assert state["current_stage"] == "KEYFRAME_REVIEW"
    assert state["current_scene_id"] == "scene_1"
    assert state["current_shot_id"] == "shot_1"


def test_identity_validation_exception_cannot_hide_completed_provider_spend(tmp_path):
    controller, _project, _shot = _controller()
    output = tmp_path / "generated.jpg"
    controller._take_output_path = MagicMock(return_value=str(output))
    controller._core.continuity.enhance_shot_prompt.return_value = {
        "prompt": "base prompt",
        "continuity_config": {"primary_reference": "/reference/face.jpg"},
    }

    def _provider(*args, **kwargs):
        output.write_bytes(b"image")
        return ImageGenResult(str(output), "GEMINI_IMAGE")

    validator = MagicMock()
    validator.validate_image.side_effect = RuntimeError("validator crashed")
    with patch("cinema.shots.controller.generate_ai_broll", _provider), \
         patch("phase_c_vision._get_shared_validator", return_value=validator):
        with pytest.raises(RuntimeError, match="validator crashed"):
            controller.generate_keyframe_take("scene_1", "shot_1")

    controller.cost_tracker.record_api_call.assert_called_once_with(
        "GEMINI_IMAGE",
        operation="keyframe_generation",
        shot_id="shot_1",
        video_id="proj_keyframe_deferred",
    )


def test_keyframe_phase_stops_deferred_without_recording_shot_failure():
    generator = MagicMock()
    generator.generate_keyframe_take.return_value = {
        "success": False,
        "error_kind": "deferred",
        "error": "provider outcome unresolved",
    }
    failures = []
    phase = KeyframeRenderPhase(
        shot_generator=generator,
        project={
            "scenes": [{
                "id": "scene_1",
                "shots": [
                    {"id": "shot_1"},
                    {"id": "shot_2"},
                ],
            }],
        },
        on_failure=lambda *args: failures.append(args),
    )
    ctx = SimpleNamespace(lifecycle=SimpleNamespace(is_cancelled=lambda: False))

    result = phase.run(ctx)

    assert result.ok is False
    assert "recovery required" in result.message
    assert generator.generate_keyframe_take.call_count == 1
    assert failures == []
