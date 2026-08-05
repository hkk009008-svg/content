"""Crash/resume contracts for paid performance and upscale adapters.

All provider traffic is faked.  These tests exercise the real SQLite paid-
attempt authority to prove provider IDs survive a tracker/process restart,
fresh local output paths do not create replacement jobs, and cost analytics
receive exactly one reconciled terminal row.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from cost_tracker import API_COST_USD, CostTracker
import lip_sync
import performance.live_portrait as live_portrait
import performance.viggle as viggle


def _media_inputs(tmp_path: Path) -> tuple[str, str]:
    keyframe = tmp_path / "keyframe.png"
    driving = tmp_path / "driving.mp4"
    keyframe.write_bytes(b"keyframe-bytes")
    driving.write_bytes(b"driving-video-bytes")
    return str(keyframe), str(driving)


class _RecoverableComfy:
    def __init__(self, *, wait_error: Exception | None = None, forbid_queue: bool = False):
        self.wait_error = wait_error
        self.forbid_queue = forbid_queue
        self.queue_calls = 0

    def upload_image(self, path: str) -> str:
        return f"remote-{Path(path).name}"

    def queue_prompt(self, _workflow: dict) -> str:
        self.queue_calls += 1
        if self.forbid_queue:
            raise AssertionError("recovery must resume prompt_id, not queue again")
        return "live-prompt-1"

    def wait_for_completion(self, prompt_id: str, *, timeout: float, poll_interval: float):
        if self.wait_error is not None:
            raise self.wait_error
        return {
            prompt_id: {
                "outputs": {
                    "30": {
                        "videos": [
                            {
                                "filename": "live.mp4",
                                "subfolder": "",
                                "type": "output",
                            }
                        ]
                    }
                }
            }
        }


def test_live_portrait_resumes_prompt_after_restart_without_double_charge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    keyframe, driving = _media_inputs(tmp_path)
    db_path = str(tmp_path / "live-paid.db")
    first_client = _RecoverableComfy(wait_error=TimeoutError("worker stopped"))
    second_client = _RecoverableComfy(forbid_queue=True)
    clients = [first_client, second_client]

    monkeypatch.setattr(
        live_portrait,
        "settings",
        SimpleNamespace(
            comfyui_server_url="http://private-pod:8189",
            comfyui_api_key="secret",
        ),
    )
    monkeypatch.setattr(
        live_portrait,
        "RunPodComfyUI",
        lambda *_args, **_kwargs: clients.pop(0),
    )

    def _download(_url: str, destination: str, **_kwargs) -> str:
        Path(destination).write_bytes(b"live-output")
        return destination

    monkeypatch.setattr(live_portrait, "safe_download", _download)

    first = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        assert live_portrait.generate_live_portrait_performance(
            keyframe,
            driving,
            str(tmp_path / "take-a.mp4"),
            duration_s=5.0,
            shot_id="shot-1",
            video_id="project-1",
            cost_tracker=first,
        ) is None
        pending = first.get_latest_paid_attempt(
            video_id="project-1",
            shot_id="shot-1",
            engine="LIVE_PORTRAIT",
            operation="performance_capture",
        )
        assert pending is not None
        assert pending["state"] == "accepted_unknown"
        assert pending["provider_job_id"] == "live-prompt-1"
        assert first.get_video_cost("project-1")["total_usd"] == 0.0
    finally:
        first.close()

    resumed = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        second_output = str(tmp_path / "take-b.mp4")
        assert live_portrait.generate_live_portrait_performance(
            keyframe,
            driving,
            second_output,
            duration_s=5.0,
            shot_id="shot-1",
            video_id="project-1",
            cost_tracker=resumed,
        ) == second_output
        assert second_client.queue_calls == 0
        settled = resumed.get_latest_paid_attempt(
            video_id="project-1",
            shot_id="shot-1",
            engine="LIVE_PORTRAIT",
            operation="performance_capture",
        )
        assert settled is not None and settled["state"] == "succeeded"
        assert resumed.get_video_cost("project-1")["total_usd"] == pytest.approx(0.04)
        analytics = resumed.get_provider_usage_analytics("project-1")
        assert analytics["by_engine"]["LIVE_PORTRAIT"]["succeeded"] == 1
        assert analytics["by_engine"]["LIVE_PORTRAIT"]["charged_cost_usd"] == pytest.approx(0.04)
    finally:
        resumed.close()


class _Response:
    def __init__(self, status_code: int, body: dict | None = None, *, text: str = ""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self) -> dict:
        return self._body


def _viggle_settings() -> SimpleNamespace:
    return SimpleNamespace(viggle_api_key="offline-key")


def test_viggle_persists_render_id_and_resumes_fresh_take_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    keyframe, driving = _media_inputs(tmp_path)
    db_path = str(tmp_path / "viggle-paid.db")
    post_calls = []

    def _post(*_args, **_kwargs):
        post_calls.append(True)
        return _Response(202, {"status": "queued", "id": "viggle-render-1"})

    monkeypatch.setattr(viggle, "settings", _viggle_settings())
    monkeypatch.setattr(requests, "post", _post)
    monkeypatch.setattr(
        requests,
        "get",
        lambda *_args, **_kwargs: _Response(
            200,
            {"status": "ready", "video_url": "https://cdn.invalid/viggle.mp4"},
        ),
    )

    def _download(_url: str, destination: str, **_kwargs) -> str:
        Path(destination).write_bytes(b"viggle-output")
        return destination

    monkeypatch.setattr(viggle, "safe_download", _download)
    monkeypatch.setattr(viggle, "_POLL_INTERVAL_S", 0)

    first = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        assert viggle.generate_viggle_performance(
            keyframe,
            driving,
            str(tmp_path / "take-a.mp4"),
            shot_id="shot-1",
            video_id="project-1",
            poll_timeout_s=0,
            cost_tracker=first,
        ) is None
        pending = first.get_latest_paid_attempt(
            video_id="project-1",
            shot_id="shot-1",
            engine="VIGGLE",
            operation="performance_capture",
        )
        assert pending is not None
        assert pending["state"] == "accepted_unknown"
        assert pending["provider_job_id"] == "viggle-render-1"
    finally:
        first.close()

    monkeypatch.setattr(
        requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("recovery must not submit a second Viggle render")
        ),
    )
    resumed = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        second_output = str(tmp_path / "take-b.mp4")
        assert viggle.generate_viggle_performance(
            keyframe,
            driving,
            second_output,
            shot_id="shot-1",
            video_id="project-1",
            poll_timeout_s=1,
            cost_tracker=resumed,
        ) == second_output
        assert len(post_calls) == 1
        assert resumed.get_video_cost("project-1")["total_usd"] == pytest.approx(0.20)
        analytics = resumed.get_provider_usage_analytics("project-1")
        assert analytics["by_engine"]["VIGGLE"]["succeeded"] == 1
        assert analytics["by_provider"]["viggle"]["charged_cost_usd"] == pytest.approx(0.20)
    finally:
        resumed.close()


def test_viggle_lost_submit_ack_never_reposts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    keyframe, driving = _media_inputs(tmp_path)
    db_path = str(tmp_path / "viggle-lost-ack.db")
    calls = 0

    def _lost_ack(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise requests.exceptions.Timeout("response lost")

    monkeypatch.setattr(viggle, "settings", _viggle_settings())
    monkeypatch.setattr(requests, "post", _lost_ack)
    first = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        assert viggle.generate_viggle_performance(
            keyframe,
            driving,
            str(tmp_path / "take-a.mp4"),
            shot_id="shot-1",
            video_id="project-1",
            cost_tracker=first,
        ) is None
        pending = first.get_latest_paid_attempt(
            video_id="project-1",
            shot_id="shot-1",
            engine="VIGGLE",
            operation="performance_capture",
        )
        assert pending is not None
        assert pending["state"] == "accepted_unknown"
        assert pending["provider_job_id"] == ""
    finally:
        first.close()

    resumed = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        assert viggle.generate_viggle_performance(
            keyframe,
            driving,
            str(tmp_path / "take-b.mp4"),
            shot_id="shot-1",
            video_id="project-1",
            cost_tracker=resumed,
        ) is None
        assert calls == 1
    finally:
        resumed.close()


class _FalHandle:
    request_id = "seedvr-request-1"


def test_seedvr2_resumes_request_id_and_appears_in_analytics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    db_path = str(tmp_path / "seedvr-paid.db")
    submit_calls = []
    status = {"value": "IN_PROGRESS"}

    monkeypatch.setattr(lip_sync, "FAL_AVAILABLE", True)
    monkeypatch.setattr(lip_sync, "ENV_SETTINGS", SimpleNamespace(fal_key="offline"))
    monkeypatch.setattr(lip_sync, "FAL_TIMEOUT_VIDEO_S", 0)
    monkeypatch.setattr(lip_sync, "_seedvr2_estimated_cost", lambda *_args: 0.25)
    monkeypatch.setattr(lip_sync.fal_client, "upload_file", lambda _path: "https://upload.invalid/source")
    monkeypatch.setattr(
        lip_sync.fal_client,
        "submit",
        lambda *_args, **_kwargs: submit_calls.append(True) or _FalHandle(),
    )
    monkeypatch.setattr(
        lip_sync.fal_client,
        "status",
        lambda *_args, **_kwargs: {"status": status["value"]},
    )
    monkeypatch.setattr(
        lip_sync.fal_client,
        "result",
        lambda *_args, **_kwargs: {
            "video": {"url": "https://cdn.invalid/seedvr.mp4"},
            "seed": 123,
        },
    )
    monkeypatch.setattr(
        lip_sync.fal_client,
        "subscribe",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("shared tracker must use durable queue API")
        ),
    )

    def _download(_url: str, destination: str, **_kwargs) -> str:
        Path(destination).write_bytes(b"seedvr-output")
        return destination

    monkeypatch.setattr(lip_sync, "safe_download", _download)
    monkeypatch.setattr(lip_sync, "_remux_source_audio_in_place", lambda *_args, **_kwargs: True)

    first = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        assert lip_sync.upscale_video_seedvr2(
            str(source),
            str(tmp_path / "take-a.mp4"),
            cost_tracker=first,
            shot_id="shot-1",
            video_id="project-1",
        ) is None
        pending = first.get_latest_paid_attempt(
            video_id="project-1",
            shot_id="shot-1",
            engine="FAL_SEEDVR2",
            operation="video_upscale",
        )
        assert pending is not None
        assert pending["provider_job_id"] == "seedvr-request-1"
        assert pending["state"] == "accepted_unknown"
    finally:
        first.close()

    status["value"] = "COMPLETED"
    monkeypatch.setattr(
        lip_sync.fal_client,
        "submit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("recovery must not submit a second SeedVR2 job")
        ),
    )
    resumed = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        second_output = str(tmp_path / "take-b.mp4")
        assert lip_sync.upscale_video_seedvr2(
            str(source),
            second_output,
            cost_tracker=resumed,
            shot_id="shot-1",
            video_id="project-1",
        ) == second_output
        assert len(submit_calls) == 1
        assert resumed.get_video_cost("project-1")["total_usd"] == pytest.approx(0.25)
        analytics = resumed.get_provider_usage_analytics("project-1")
        assert analytics["by_engine"]["FAL_SEEDVR2"]["succeeded"] == 1
        assert analytics["by_provider"]["fal"]["charged_cost_usd"] == pytest.approx(0.25)
    finally:
        resumed.close()


def test_seedvr2_cost_uses_published_megapixel_frame_formula(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lip_sync, "_seedvr2_frame_count", lambda _path: 121)
    assert lip_sync._seedvr2_estimated_cost("video.mp4", "1080p") == pytest.approx(
        0.250906
    )
    assert API_COST_USD["FAL_SEEDVR2"] == pytest.approx(0.25)
