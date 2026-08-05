"""Crash/restart and money-boundary evidence for PixVerse face swap.

Provider traffic is fully faked.  These tests exercise the real SQLite
paid-attempt ledger through ``phase_c_vision.face_swap_video_frames`` so the
production adapter, rather than a test-only abstraction, proves request-ID
resume, no duplicate paid submission, fail-closed ambiguity, and atomic budget
admission.
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from config.settings import settings as real_settings
from cost_tracker import API_COST_USD, CostTracker
from paid_provider import PaidCallDeferred
import phase_c_vision


class _FalClient:
    def __init__(
        self,
        *,
        status: str = "COMPLETED",
        result: dict | None = None,
        request_id: str = "pixverse-request-1",
        status_payload: dict | None = None,
        submit_error: Exception | None = None,
        forbid_submit: bool = False,
    ):
        self.status_value = status
        self.result_value = result or {
            "video": {"url": "https://example.invalid/pixverse.mp4"}
        }
        self.request_id = request_id
        self.status_payload = status_payload
        self.submit_error = submit_error
        self.forbid_submit = forbid_submit
        self.submit_calls = 0
        self.upload_calls = 0

    def upload_file(self, path: str) -> str:
        self.upload_calls += 1
        return f"https://uploads.invalid/{Path(path).name}"

    def submit(self, application: str, arguments: dict):
        self.submit_calls += 1
        if self.forbid_submit:
            raise AssertionError("recovery must never submit a replacement job")
        if self.submit_error is not None:
            raise self.submit_error
        assert application == "fal-ai/pixverse/swap"
        assert arguments["mode"] == "person"
        assert arguments["resolution"] == "720p"
        assert arguments["duration"] == "5"
        assert arguments["original_sound_switch"] is False
        assert "image_url" in arguments
        assert "swap_image_url" not in arguments
        return SimpleNamespace(request_id=self.request_id)

    def status(self, application: str, request_id: str, *, with_logs: bool = False):
        assert application == "fal-ai/pixverse/swap"
        assert request_id == self.request_id
        assert with_logs is True
        return dict(self.status_payload or {"status": self.status_value})

    def result(self, application: str, request_id: str):
        assert application == "fal-ai/pixverse/swap"
        assert request_id == self.request_id
        return self.result_value


def _inputs(tmp_path: Path) -> tuple[str, str]:
    video = tmp_path / "source.mp4"
    reference = tmp_path / "identity.jpg"
    video.write_bytes(b"stable-source-video")
    reference.write_bytes(b"stable-identity-reference")
    return str(video), str(reference)


def _fal_settings():
    from dataclasses import replace

    return replace(real_settings, fal_key="test-fal-key")


def _download(_url: str, destination: str, **_kwargs) -> str:
    Path(destination).write_bytes(b"pixverse-output")
    return destination


def test_pixverse_resumes_request_id_after_restart_without_duplicate_charge(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="phase_c_vision")
    video, reference = _inputs(tmp_path)
    db_path = str(tmp_path / "paid.db")
    first_client = _FalClient(status="IN_PROGRESS")
    first = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        with patch.object(phase_c_vision, "settings", _fal_settings()), \
             patch.object(phase_c_vision, "FAL_TIMEOUT_VIDEO_S", 0), \
             patch.dict(sys.modules, {"fal_client": first_client}), \
             patch("subprocess.run") as local_run, \
             pytest.raises(PaidCallDeferred):
            phase_c_vision.face_swap_video_frames(
                video,
                reference,
                str(tmp_path / "first-output.mp4"),
                cost_tracker=first,
                shot_id="shot-1",
                video_id="project-1",
            )
        local_run.assert_not_called()
        pending = first.get_latest_paid_attempt(
            video_id="project-1",
            shot_id="shot-1",
            engine="FAL_PIXVERSE_SWAP",
            operation="face_swap",
        )
        assert pending["state"] == "accepted_unknown"
        assert pending["provider_job_id"] == "pixverse-request-1"
        assert pending["reserved_cost_usd"] == pytest.approx(
            API_COST_USD["FAL_PIXVERSE_SWAP"]
        )
        assert first.get_video_cost("project-1")["total_usd"] == 0.0
    finally:
        first.close()

    resumed_client = _FalClient(forbid_submit=True)
    resumed = CostTracker(db_path=db_path, budget_usd=1.0)
    cascade: dict = {}
    try:
        second_output = str(tmp_path / "different-output.mp4")
        with patch.object(phase_c_vision, "settings", _fal_settings()), \
             patch.dict(sys.modules, {"fal_client": resumed_client}), \
             patch.object(phase_c_vision, "safe_download", _download), \
             patch("lip_sync._remux_source_audio_in_place", return_value=True), \
             patch("subprocess.run") as local_run:
            result = phase_c_vision.face_swap_video_frames(
                video,
                reference,
                second_output,
                cost_tracker=resumed,
                shot_id="shot-1",
                video_id="project-1",
                _cascade_out=cascade,
            )
        assert result == second_output
        assert Path(second_output).read_bytes() == b"pixverse-output"
        assert resumed_client.submit_calls == 0
        local_run.assert_not_called()

        settled = resumed.get_latest_paid_attempt(
            video_id="project-1",
            shot_id="shot-1",
            engine="FAL_PIXVERSE_SWAP",
            operation="face_swap",
        )
        assert settled["state"] == "succeeded"
        assert settled["provider_job_id"] == "pixverse-request-1"
        assert resumed.get_video_cost("project-1")["total_usd"] == pytest.approx(
            API_COST_USD["FAL_PIXVERSE_SWAP"]
        )
        analytics = resumed.get_provider_usage_analytics("project-1")
        metric = analytics["by_engine"]["FAL_PIXVERSE_SWAP"]
        assert metric["succeeded"] == 1
        assert metric["charged_cost_usd"] == pytest.approx(
            API_COST_USD["FAL_PIXVERSE_SWAP"]
        )
        assert cascade["engine"] == "FAL_PIXVERSE_SWAP"
        assert cascade["model"] == "fal-ai/pixverse/swap"
        assert cascade["provider_job_id"] == "pixverse-request-1"
        assert cascade["paid_cost_recorded"] is True
        completion = next(
            record
            for record in caplog.records
            if record.getMessage() == "PixVerse face-swap completed"
        )
        assert completion.provider == "fal"
        assert completion.engine == "FAL_PIXVERSE_SWAP"
        assert completion.shot_id == "shot-1"
        assert completion.video_id == "project-1"
        assert completion.attempt_id.startswith("fal-pixverse-swap:")
    finally:
        resumed.close()


def test_lost_submit_ack_never_replays_or_falls_back_after_restart(
    tmp_path: Path,
) -> None:
    video, reference = _inputs(tmp_path)
    db_path = str(tmp_path / "ambiguous.db")
    first_client = _FalClient(submit_error=TimeoutError("ack lost"))
    first = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        with patch.object(phase_c_vision, "settings", _fal_settings()), \
             patch.dict(sys.modules, {"fal_client": first_client}), \
             patch("subprocess.run") as local_run, \
             pytest.raises(PaidCallDeferred):
            phase_c_vision.face_swap_video_frames(
                video,
                reference,
                str(tmp_path / "first.mp4"),
                cost_tracker=first,
                shot_id="shot-1",
                video_id="project-1",
            )
        local_run.assert_not_called()
        ambiguous = first.get_latest_paid_attempt(
            video_id="project-1",
            shot_id="shot-1",
            engine="FAL_PIXVERSE_SWAP",
            operation="face_swap",
        )
        assert ambiguous["state"] == "accepted_unknown"
        assert ambiguous["provider_job_id"] == ""
    finally:
        first.close()

    restarted_client = _FalClient(forbid_submit=True)
    restarted = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        with patch.object(phase_c_vision, "settings", _fal_settings()), \
             patch.dict(sys.modules, {"fal_client": restarted_client}), \
             patch("subprocess.run") as local_run, \
             pytest.raises(PaidCallDeferred):
            phase_c_vision.face_swap_video_frames(
                video,
                reference,
                str(tmp_path / "second.mp4"),
                cost_tracker=restarted,
                shot_id="shot-1",
                video_id="project-1",
            )
        assert restarted_client.submit_calls == 0
        local_run.assert_not_called()
        assert restarted.get_video_cost("project-1")["total_usd"] == 0.0
        assert restarted.get_paid_attempts_snapshot("project-1")[
            "accepted_unknown_count"
        ] == 1
    finally:
        restarted.close()


def test_atomic_budget_refusal_never_submits_and_allows_local_facefusion(
    tmp_path: Path,
) -> None:
    video, reference = _inputs(tmp_path)
    output = tmp_path / "local.mp4"
    client = _FalClient(forbid_submit=True)
    tracker = CostTracker(
        db_path=str(tmp_path / "budget.db"),
        budget_usd=API_COST_USD["FAL_PIXVERSE_SWAP"] - 0.01,
    )
    cascade: dict = {}

    def _local_run(_command, **_kwargs):
        output.write_bytes(b"facefusion-output")
        return SimpleNamespace(returncode=0)

    try:
        with patch.object(phase_c_vision, "settings", _fal_settings()), \
             patch.dict(sys.modules, {"fal_client": client}), \
             patch("subprocess.run", side_effect=_local_run) as local_run, \
             patch("lip_sync._remux_source_audio_in_place", return_value=True):
            result = phase_c_vision.face_swap_video_frames(
                video,
                reference,
                str(output),
                cost_tracker=tracker,
                shot_id="shot-budget",
                video_id="project-budget",
                _cascade_out=cascade,
            )

        assert result == str(output)
        assert output.read_bytes() == b"facefusion-output"
        assert client.submit_calls == 0
        local_run.assert_called_once()
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-budget",
            shot_id="shot-budget",
            engine="FAL_PIXVERSE_SWAP",
            operation="face_swap",
        )
        assert attempt["state"] == "blocked_budget"
        assert tracker.get_video_cost("project-budget")["total_usd"] == 0.0
        assert cascade["engine"] == "FACEFUSION_LOCAL"
        assert cascade["provider"] == "local"
        assert cascade["paid_attempt"]["state"] == "blocked_budget"
    finally:
        tracker.close()


def test_explicit_terminal_unbilled_failure_reconciles_then_allows_local(
    tmp_path: Path,
) -> None:
    video, reference = _inputs(tmp_path)
    output = tmp_path / "unbilled-local.mp4"
    client = _FalClient(
        status_payload={
            "status": "FAILED",
            "error": "provider rejected input",
            "error_type": "input_rejected",
            "billed": False,
        },
        request_id="pixverse-unbilled",
    )
    tracker = CostTracker(db_path=str(tmp_path / "unbilled.db"), budget_usd=1.0)

    def _local_run(_command, **_kwargs):
        output.write_bytes(b"safe-local-output")
        return SimpleNamespace(returncode=0)

    try:
        with patch.object(phase_c_vision, "settings", _fal_settings()), \
             patch.dict(sys.modules, {"fal_client": client}), \
             patch("subprocess.run", side_effect=_local_run) as local_run, \
             patch("lip_sync._remux_source_audio_in_place", return_value=True):
            result = phase_c_vision.face_swap_video_frames(
                video,
                reference,
                str(output),
                cost_tracker=tracker,
                shot_id="shot-unbilled",
                video_id="project-unbilled",
            )

        assert result == str(output)
        assert client.submit_calls == 1
        local_run.assert_called_once()
        settled = tracker.get_latest_paid_attempt(
            video_id="project-unbilled",
            shot_id="shot-unbilled",
            engine="FAL_PIXVERSE_SWAP",
            operation="face_swap",
        )
        assert settled["state"] == "failed_unbilled"
        assert settled["provider_job_id"] == "pixverse-unbilled"
        assert settled["reconciled_cost_usd"] == 0.0
        assert tracker.get_video_cost("project-unbilled")["total_usd"] == 0.0
    finally:
        tracker.close()
