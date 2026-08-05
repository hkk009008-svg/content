from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cost_tracker import CostTracker
from paid_provider import (
    PaidCallBudgetBlocked,
    PaidCallDeferred,
    PaidCallUnbilled,
    has_paid_attempt_authority,
    paid_attempt_id,
    request_fingerprint,
    run_durable_comfy_job,
    run_durable_fal_job,
    run_nonresumable_paid_call,
)


def test_paid_authority_requires_explicit_version_not_mocked_methods():
    assert has_paid_attempt_authority(MagicMock()) is False
    tracker = CostTracker(db_path=":memory:")
    try:
        assert has_paid_attempt_authority(tracker) is True
    finally:
        tracker.close()


@dataclass
class _Handle:
    request_id: str


class _FalClient:
    def __init__(self, statuses, *, result=None, submit_error=None, forbid_submit=False):
        self.statuses = list(statuses)
        self.result_value = result or {"video": {"url": "https://example.invalid/out.mp4"}}
        self.submit_error = submit_error
        self.forbid_submit = forbid_submit
        self.submit_calls = 0
        self.status_calls = 0

    def submit(self, application, arguments):
        self.submit_calls += 1
        if self.forbid_submit:
            raise AssertionError("restart must resume request_id, not submit")
        if self.submit_error:
            raise self.submit_error
        return _Handle("fal-request-1")

    def status(self, application, request_id, *, with_logs=False):
        self.status_calls += 1
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        return self.statuses[0]

    def result(self, application, request_id):
        return self.result_value


def _run(tracker, client, *, attempt="fal:test", cost=0.4, timeout=0):
    return run_durable_fal_job(
        client=client,
        application="fal-ai/example",
        arguments={"prompt": "not persisted"},
        attempt_id=attempt,
        engine="FAL_EXAMPLE",
        operation="test_generation",
        estimated_cost_usd=cost,
        request_fingerprint_value=request_fingerprint("safe-input"),
        cost_tracker=tracker,
        shot_id="shot-1",
        video_id="project-1",
        poll_timeout_s=timeout,
        poll_interval_s=0,
    )


def test_running_fal_request_resumes_after_restart_without_duplicate_submit(tmp_path):
    db = str(tmp_path / "fal-resume.db")
    first = CostTracker(db_path=db, budget_usd=2.0)
    try:
        with pytest.raises(PaidCallDeferred):
            _run(first, _FalClient([{"status": "IN_PROGRESS"}]))
        pending = first.get_paid_attempt("fal:test")
        assert pending["state"] == "accepted_unknown"
        assert pending["provider_job_id"] == "fal-request-1"
        assert pending["reserved_cost_usd"] == pytest.approx(0.4)
    finally:
        first.close()

    resumed_client = _FalClient(
        [{"status": "COMPLETED"}],
        result={"audio": {"url": "https://example.invalid/out.mp3"}},
        forbid_submit=True,
    )
    resumed = CostTracker(db_path=db, budget_usd=2.0)
    try:
        assert _run(resumed, resumed_client) == {
            "audio": {"url": "https://example.invalid/out.mp3"}
        }
        assert resumed_client.submit_calls == 0
        settled = resumed.get_paid_attempt("fal:test")
        assert settled["state"] == "succeeded"
        assert settled["provider_job_id"] == "fal-request-1"
        assert resumed.get_video_cost("project-1")["total_usd"] == pytest.approx(0.4)
    finally:
        resumed.close()


def test_lost_submit_acknowledgement_blocks_every_automatic_replay(tmp_path):
    db = str(tmp_path / "fal-lost-ack.db")
    tracker = CostTracker(db_path=db, budget_usd=2.0)
    try:
        with pytest.raises(PaidCallDeferred):
            _run(tracker, _FalClient([], submit_error=TimeoutError("lost response")))
        ambiguous = tracker.get_paid_attempt("fal:test")
        assert ambiguous["state"] == "accepted_unknown"
        assert ambiguous["provider_job_id"] == ""
    finally:
        tracker.close()

    restarted = CostTracker(db_path=db, budget_usd=2.0)
    client = _FalClient([], forbid_submit=True)
    try:
        with pytest.raises(PaidCallDeferred):
            _run(restarted, client)
        assert client.submit_calls == 0
        assert restarted.get_paid_attempt("fal:test")["state"] == "accepted_unknown"
    finally:
        restarted.close()


def test_active_reservation_makes_next_real_fal_attempt_fail_atomic_budget_gate(tmp_path):
    tracker = CostTracker(db_path=str(tmp_path / "fal-budget.db"), budget_usd=0.7)
    try:
        with pytest.raises(PaidCallDeferred):
            _run(tracker, _FalClient([{"status": "IN_PROGRESS"}]), cost=0.4)
        with pytest.raises(PaidCallBudgetBlocked):
            _run(
                tracker,
                _FalClient([{"status": "COMPLETED"}]),
                attempt="fal:second",
                cost=0.4,
            )
        assert tracker.get_paid_attempt("fal:second")["state"] == "blocked_budget"
        assert tracker.get_paid_attempts_snapshot("project-1")["active_reservation_usd"] == pytest.approx(0.4)
    finally:
        tracker.close()


def test_succeeded_request_can_redownload_without_new_submit_or_double_charge(tmp_path):
    tracker = CostTracker(db_path=str(tmp_path / "fal-redownload.db"), budget_usd=2.0)
    try:
        first = _FalClient([{"status": "COMPLETED"}])
        assert _run(tracker, first)
        second = _FalClient([], forbid_submit=True)
        assert _run(tracker, second)
        assert second.submit_calls == 0
        assert tracker.get_video_cost("project-1")["total_usd"] == pytest.approx(0.4)
    finally:
        tracker.close()


@pytest.mark.parametrize(
    ("status", "expected_state", "expected_cost", "exception_type"),
    [
        (
            {"status": "FAILED", "error": "input rejected", "billed": False},
            "failed_unbilled",
            0.0,
            PaidCallUnbilled,
        ),
        (
            {"status": "FAILED", "error": "safety", "billed": True},
            "failed_billed",
            0.4,
            PaidCallDeferred,
        ),
        (
            {"status": "CANCELLED", "billed": False},
            "cancelled",
            0.0,
            PaidCallUnbilled,
        ),
    ],
)
def test_fal_terminal_failure_uses_only_explicit_billing_evidence(
    tmp_path, status, expected_state, expected_cost, exception_type
):
    tracker = CostTracker(db_path=str(tmp_path / f"{expected_state}.db"), budget_usd=2.0)
    try:
        with pytest.raises(exception_type):
            _run(tracker, _FalClient([status]))
        attempt = tracker.get_paid_attempt("fal:test")
        assert attempt["state"] == expected_state
        assert attempt["provider_job_id"] == "fal-request-1"
        assert tracker.get_video_cost("project-1")["total_usd"] == pytest.approx(
            expected_cost
        )
    finally:
        tracker.close()


def test_fal_terminal_failure_without_billing_evidence_stays_accepted_unknown(
    tmp_path,
):
    tracker = CostTracker(db_path=str(tmp_path / "unknown-terminal.db"), budget_usd=2.0)
    try:
        with pytest.raises(PaidCallDeferred):
            _run(
                tracker,
                _FalClient([{"status": "FAILED", "error": "provider failed"}]),
            )
        attempt = tracker.get_paid_attempt("fal:test")
        assert attempt["state"] == "accepted_unknown"
        assert attempt["provider_job_id"] == "fal-request-1"
        assert tracker.get_video_cost("project-1")["total_usd"] == 0.0
    finally:
        tracker.close()


def test_attempt_ids_are_stable_and_do_not_embed_sensitive_inputs():
    attempt = paid_attempt_id("lipsync", "private prompt", {"seed": 7})
    assert attempt == paid_attempt_id("lipsync", "private prompt", {"seed": 7})
    assert "private prompt" not in attempt
    assert len(attempt) < 128


class _ComfyClient:
    def __init__(self, *, wait_error=None, forbid_queue=False):
        self.wait_error = wait_error
        self.forbid_queue = forbid_queue
        self.queue_calls = 0

    def queue_prompt(self, workflow):
        self.queue_calls += 1
        if self.forbid_queue:
            raise AssertionError("restart must resume prompt_id, not queue again")
        return "prompt-1"

    def wait_for_completion(self, prompt_id, *, timeout, poll_interval):
        if self.wait_error:
            raise self.wait_error
        return {
            prompt_id: {
                "outputs": {"30": {"videos": [{"filename": "out.mp4"}]}}
            }
        }


def _run_comfy(tracker, client):
    return run_durable_comfy_job(
        client=client,
        workflow={"1": {"class_type": "Test", "inputs": {}}},
        attempt_id="comfy:test",
        engine="PERFORMANCE_DRIVING_SADTALKER",
        operation="performance_capture_driving",
        estimated_cost_usd=0.045,
        request_fingerprint_value=request_fingerprint("audio", "frame"),
        cost_tracker=tracker,
        shot_id="shot-1",
        video_id="project-1",
        poll_timeout_s=1,
        poll_interval_s=0.1,
    )


def test_comfy_prompt_id_resumes_after_worker_restart(tmp_path):
    db = str(tmp_path / "comfy-resume.db")
    first = CostTracker(db_path=db, budget_usd=1.0)
    try:
        with pytest.raises(PaidCallDeferred):
            _run_comfy(first, _ComfyClient(wait_error=TimeoutError("worker died")))
        pending = first.get_paid_attempt("comfy:test")
        assert pending["provider_job_id"] == "prompt-1"
        assert pending["state"] == "accepted_unknown"
    finally:
        first.close()

    resumed = CostTracker(db_path=db, budget_usd=1.0)
    client = _ComfyClient(forbid_queue=True)
    try:
        assert _run_comfy(resumed, client)["prompt-1"]["outputs"]
        assert client.queue_calls == 0
        assert resumed.get_paid_attempt("comfy:test")["state"] == "succeeded"
        assert resumed.get_video_cost("project-1")["total_usd"] == pytest.approx(0.045)
    finally:
        resumed.close()


def test_provider_without_idempotency_never_replays_ambiguous_call(tmp_path):
    tracker = CostTracker(db_path=str(tmp_path / "no-id.db"), budget_usd=1.0)
    calls = 0

    def ambiguous():
        nonlocal calls
        calls += 1
        raise TimeoutError("response lost after request body")

    kwargs = dict(
        attempt_id="no-id:test",
        provider="google",
        engine="GEMINI_IMAGE",
        operation="image_generation",
        estimated_cost_usd=0.067,
        request_fingerprint_value=request_fingerprint("image-inputs"),
        cost_tracker=tracker,
        video_id="project-1",
    )
    try:
        with pytest.raises(PaidCallDeferred):
            run_nonresumable_paid_call(call=ambiguous, **kwargs)
        with pytest.raises(PaidCallDeferred):
            run_nonresumable_paid_call(call=ambiguous, **kwargs)
        assert calls == 1
        assert tracker.get_paid_attempt("no-id:test")["state"] == "accepted_unknown"
    finally:
        tracker.close()


def test_nonresumable_result_is_not_reconciled_before_durable_retention(tmp_path):
    tracker = CostTracker(db_path=str(tmp_path / "retention.db"), budget_usd=1.0)
    try:
        with pytest.raises(PaidCallDeferred, match="durable output retention"):
            run_nonresumable_paid_call(
                call=lambda: {"path": "provider-output"},
                attempt_id="no-id:retention",
                provider="google",
                engine="GEMINI_IMAGE",
                operation="image_generation",
                estimated_cost_usd=0.067,
                request_fingerprint_value=request_fingerprint("image-inputs"),
                cost_tracker=tracker,
                video_id="project-1",
                on_completed=MagicMock(
                    side_effect=OSError("artifact ledger unavailable")
                ),
            )
        attempt = tracker.get_paid_attempt("no-id:retention")
        assert attempt["state"] == "accepted_unknown"
        assert tracker.get_video_cost("project-1")["total_usd"] == 0.0
    finally:
        tracker.close()


def test_real_fal_image_fallback_uses_request_id_ledger(monkeypatch, tmp_path):
    import fal_client
    import phase_c_assembly as assembly

    output = tmp_path / "frame.jpg"
    submissions = []
    monkeypatch.setattr(
        assembly,
        "settings",
        SimpleNamespace(fal_key="offline", comfyui_server_url=""),
    )
    monkeypatch.setattr(
        fal_client,
        "submit",
        lambda application, arguments: submissions.append(application) or _Handle("image-request"),
    )
    monkeypatch.setattr(
        fal_client,
        "status",
        lambda *_a, **_k: {"status": "COMPLETED"},
    )
    monkeypatch.setattr(
        fal_client,
        "result",
        lambda *_a, **_k: {"images": [{"url": "https://example.invalid/frame.jpg"}]},
    )

    def download(_url, destination):
        output.write_bytes(b"jpeg")
        return destination

    monkeypatch.setattr(assembly, "_download_generated_jpeg", download)
    recovery = {}
    with CostTracker(db_path=str(tmp_path / "image.db"), budget_usd=1.0) as tracker:
        result = assembly._fal_flux_fallback(
            "cinematic frame",
            str(output),
            seed=7,
            cost_tracker=tracker,
            shot_id="shot-image",
            video_id="project-image",
            _recovery_out=recovery,
        )
        assert result.api_name == "FLUX_PRO"
        assert submissions == ["fal-ai/flux-pro/v1.1-ultra"]
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-image",
            shot_id="shot-image",
            engine="FLUX_PRO",
            operation="keyframe_generation",
        )
        assert attempt["state"] == "succeeded"
        assert attempt["provider_job_id"] == "image-request"
        assert tracker.get_video_cost("project-image")["total_usd"] == pytest.approx(0.05)
        assert recovery["_winner_paid_cost_recorded"] is True


def test_completed_fal_image_with_bad_artifact_does_not_start_next_paid_fallback(
    monkeypatch, tmp_path
):
    import fal_client
    import phase_c_assembly as assembly

    submissions = []
    monkeypatch.setattr(
        assembly,
        "settings",
        SimpleNamespace(fal_key="offline", comfyui_server_url=""),
    )
    monkeypatch.setattr(
        fal_client,
        "submit",
        lambda application, arguments: submissions.append(application) or _Handle("bad-image-request"),
    )
    monkeypatch.setattr(fal_client, "status", lambda *_a, **_k: {"status": "COMPLETED"})
    monkeypatch.setattr(
        fal_client,
        "result",
        lambda *_a, **_k: {"images": [{"url": "https://example.invalid/bad.jpg"}]},
    )
    monkeypatch.setattr(assembly, "_download_generated_jpeg", lambda *_a, **_k: None)
    recovery = {}
    with CostTracker(db_path=str(tmp_path / "bad-image.db"), budget_usd=1.0) as tracker:
        assert assembly._fal_flux_fallback(
            "cinematic frame",
            str(tmp_path / "bad.jpg"),
            cost_tracker=tracker,
            shot_id="shot-image",
            video_id="project-image",
            _recovery_out=recovery,
        ) is None
        assert submissions == ["fal-ai/flux-pro/v1.1-ultra"]
        assert recovery["provider_status"] == "artifact_unavailable"


def test_real_lipsync_overlay_records_each_fal_request_without_winner_double_charge(
    monkeypatch, tmp_path
):
    import lip_sync

    video = tmp_path / "base.mp4"
    audio = tmp_path / "line.wav"
    output = tmp_path / "synced.mp4"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    submissions = []
    monkeypatch.setattr(lip_sync, "FAL_AVAILABLE", True)
    monkeypatch.setattr(lip_sync, "ENV_SETTINGS", SimpleNamespace(fal_key="offline"))
    monkeypatch.setattr(
        lip_sync,
        "check_overlay_prerequisites",
        lambda *_a, **_k: lip_sync.PrerequisiteResult(True, "overlay", [], []),
    )
    monkeypatch.setattr(lip_sync.fal_client, "upload_file", lambda path: f"uploaded:{path}")
    monkeypatch.setattr(
        lip_sync.fal_client,
        "submit",
        lambda application, arguments: submissions.append(application) or _Handle("lip-request"),
    )
    monkeypatch.setattr(
        lip_sync.fal_client,
        "status",
        lambda *_a, **_k: {"status": "COMPLETED"},
    )
    monkeypatch.setattr(
        lip_sync.fal_client,
        "result",
        lambda *_a, **_k: {"video": {"url": "https://example.invalid/lip.mp4"}},
    )

    def download(_url, destination, **_kwargs):
        with open(destination, "wb") as handle:
            handle.write(b"video-out")
        return destination

    monkeypatch.setattr(lip_sync, "safe_download", download)
    cascade = {}
    with CostTracker(db_path=str(tmp_path / "lipsync.db"), budget_usd=2.0) as tracker:
        assert lip_sync.lipsync_overlay(
            str(video),
            str(audio),
            str(output),
            settings={"lipsync_quality_validation": False},
            _cascade_out=cascade,
            cost_tracker=tracker,
            shot_id="shot-lip",
            video_id="project-lip",
        ) == str(output)
        assert submissions == ["fal-ai/sync-lipsync/v3"]
        assert cascade["paid_cost_recorded"] is True
        assert tracker.get_video_cost("project-lip")["total_usd"] == pytest.approx(0.67)

        # UI retry allocates a fresh take/output path. The logical provider
        # request is unchanged, so retrieve the completed request instead of
        # POSTing a second paid job.
        retry_output = tmp_path / "synced-retry.mp4"
        assert lip_sync.lipsync_overlay(
            str(video),
            str(audio),
            str(retry_output),
            settings={"lipsync_quality_validation": False},
            cost_tracker=tracker,
            shot_id="shot-lip",
            video_id="project-lip",
        ) == str(retry_output)
        assert submissions == ["fal-ai/sync-lipsync/v3"]
        assert tracker.get_video_cost("project-lip")["total_usd"] == pytest.approx(0.67)


def test_lipsync_overlay_recovery_key_does_not_depend_on_new_take_output(
    monkeypatch, tmp_path
):
    import lip_sync
    import paid_provider

    video = tmp_path / "base.mp4"
    audio = tmp_path / "line.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    attempt_ids = []
    monkeypatch.setattr(lip_sync, "FAL_AVAILABLE", True)
    monkeypatch.setattr(lip_sync, "ENV_SETTINGS", SimpleNamespace(fal_key="offline"))
    monkeypatch.setattr(
        lip_sync,
        "check_overlay_prerequisites",
        lambda *_a, **_k: lip_sync.PrerequisiteResult(True, "overlay", [], []),
    )
    monkeypatch.setattr(lip_sync.fal_client, "upload_file", lambda path: f"uploaded:{path}")

    def durable(**kwargs):
        attempt_ids.append(kwargs["attempt_id"])
        return {"video": {"url": "https://example.invalid/lip.mp4"}}

    monkeypatch.setattr(paid_provider, "run_durable_fal_job", durable)

    def download(_url, destination, **_kwargs):
        with open(destination, "wb") as handle:
            handle.write(b"video-out")
        return destination

    monkeypatch.setattr(lip_sync, "safe_download", download)
    with CostTracker(db_path=str(tmp_path / "overlay-key.db"), budget_usd=2.0) as tracker:
        for name in ("take-a.mp4", "take-b.mp4"):
            assert lip_sync.lipsync_overlay(
                str(video),
                str(audio),
                str(tmp_path / name),
                settings={"lipsync_quality_validation": False},
                cost_tracker=tracker,
                shot_id="shot-lip",
                video_id="project-lip",
            ) == str(tmp_path / name)

    assert len(attempt_ids) == 2
    assert attempt_ids[0] == attempt_ids[1]


def test_lipsync_generation_recovery_key_does_not_depend_on_new_take_output(
    monkeypatch, tmp_path
):
    import lip_sync
    import paid_provider

    image = tmp_path / "actor.jpg"
    audio = tmp_path / "line.wav"
    image.write_bytes(b"image")
    audio.write_bytes(b"audio")
    attempt_ids = []
    monkeypatch.setattr(lip_sync, "FAL_AVAILABLE", True)
    monkeypatch.setattr(lip_sync, "ENV_SETTINGS", SimpleNamespace(fal_key="offline"))
    monkeypatch.setattr(
        lip_sync,
        "check_generation_prerequisites",
        lambda *_a, **_k: lip_sync.PrerequisiteResult(True, "generation", [], []),
    )
    monkeypatch.setattr(lip_sync.fal_client, "upload_file", lambda path: f"uploaded:{path}")

    def durable(**kwargs):
        attempt_ids.append(kwargs["attempt_id"])
        return {
            "video": {"url": "https://example.invalid/lip.mp4"},
            "duration": 1.0,
        }

    monkeypatch.setattr(paid_provider, "run_durable_fal_job", durable)

    def download(_url, destination, **_kwargs):
        with open(destination, "wb") as handle:
            handle.write(b"video-out")
        return destination

    monkeypatch.setattr(lip_sync, "safe_download", download)
    with CostTracker(db_path=str(tmp_path / "generation-key.db"), budget_usd=2.0) as tracker:
        for name in ("take-a.mp4", "take-b.mp4"):
            assert lip_sync.lipsync_generation(
                str(image),
                str(audio),
                str(tmp_path / name),
                settings={"lipsync_quality_validation": False},
                cost_tracker=tracker,
                shot_id="shot-lip",
                video_id="project-lip",
            ) == str(tmp_path / name)

    assert len(attempt_ids) == 2
    assert attempt_ids[0] == attempt_ids[1]
