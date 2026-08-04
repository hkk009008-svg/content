"""Deferred provider jobs halt motion without becoming shot failures."""

from __future__ import annotations

from unittest.mock import MagicMock

from cinema.context import PipelineContext
from cinema.phases.motion_render import MotionRenderPhase


def _project() -> dict:
    return {
        "id": "project-deferred",
        "global_settings": {},
        "scenes": [
            {
                "id": "scene-1",
                "shots": [
                    {"id": "shot-1"},
                    {"id": "shot-2"},
                    {"id": "shot-3"},
                ],
            }
        ],
    }


def test_deferred_job_halts_before_later_shots_without_failure_callback():
    generator = MagicMock()
    generator.generate_motion_take.return_value = {
        "success": False,
        "code": "provider_job_deferred",
        "error": "LTX job is still pending.",
        "deferred_job": {
            "engine": "LTX",
            "status": "pending",
            "reason": "poll_deadline_exceeded",
            "job_id": "job-123",
            "provider_status": "processing",
            "attempts": ["LTX"],
            "billed": False,
        },
    }
    on_failure = MagicMock()
    phase = MotionRenderPhase(
        shot_generator=generator,
        project=_project(),
        on_failure=on_failure,
    )

    result = phase.run(PipelineContext())

    assert result.ok is False
    assert "halted" in result.message.lower()
    generator.generate_motion_take.assert_called_once_with("scene-1", "shot-1")
    on_failure.assert_not_called()
    assert phase.deferred_job == {
        "code": "provider_job_deferred",
        "scene_id": "scene-1",
        "shot_id": "shot-1",
        "deferred_job": {
            "engine": "LTX",
            "status": "pending",
            "reason": "poll_deadline_exceeded",
            "job_id": "job-123",
            "provider_status": "processing",
            "attempts": ["LTX"],
            "billed": False,
        },
    }


def test_deferred_payload_is_allowlisted_bounded_and_json_safe():
    generator = MagicMock()
    generator.generate_motion_take.return_value = {
        "success": False,
        "code": "provider_job_deferred",
        "error": "private path /tmp/job-state.json and secret-fingerprint",
        "deferred_job": {
            "engine": "L" * 300,
            "status": "recovery_required",
            "reason": "output_invalid",
            "job_id": object(),
            "attempts": ["LTX", object(), "X" * 100] * 10,
            "billed": True,
            "state_path": "/private/job-state.json",
            "request_fingerprint": "secret-fingerprint",
            "detail": "raw provider detail",
        },
    }
    phase = MotionRenderPhase(shot_generator=generator, project=_project())

    result = phase.run(PipelineContext())

    assert result.ok is False
    assert "/tmp/job-state.json" not in result.message
    assert "secret-fingerprint" not in result.message
    public = phase.deferred_job["deferred_job"]
    assert len(public["engine"]) == 256
    assert len(public["attempts"]) <= 16
    assert all(isinstance(item, str) and len(item) <= 64 for item in public["attempts"])
    assert public["billed"] is True
    assert "job_id" not in public
    assert "state_path" not in public
    assert "request_fingerprint" not in public
    assert "detail" not in public
