"""Crash-safe paid recovery on the active automatic motion dispatch path."""

from __future__ import annotations

from datetime import date
import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import fal_client
import phase_c_ffmpeg
from cinema.context import PipelineContext
from cost_tracker import CostTracker
from domain.provider_catalog import RuntimeSnapshot


FAL_MOTION_ENGINES = ("VEO", "KLING_3_0", "SEEDANCE", "LTX")


def _runtime(monkeypatch) -> None:
    runtime = RuntimeSnapshot(
        credentials={"fal_key"},
        modules={"fal_client"},
    )
    settings = SimpleNamespace(
        fal_key="offline-fal-key",
        ltx_api_key="",
        runwayml_api_secret="",
    )
    monkeypatch.setattr(phase_c_ffmpeg, "settings", settings)
    monkeypatch.setattr(phase_c_ffmpeg, "FAL_AVAILABLE", True)
    monkeypatch.setattr(phase_c_ffmpeg, "fal_client", fal_client, raising=False)
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        lambda: runtime,
    )
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_current_date",
        lambda: date(2026, 8, 5),
    )
    monkeypatch.setattr(phase_c_ffmpeg, "_accept_or_reject", lambda *_a: True)
    current_ltx_module = importlib.import_module("ltx_native")
    monkeypatch.setattr(current_ltx_module, "settings", settings)
    monkeypatch.setattr(current_ltx_module, "FAL_AVAILABLE", True)


def _generate(
    *,
    tracker: CostTracker,
    engine: str,
    image: str,
    output: str,
    cascade: dict,
):
    fallback = "SEEDANCE" if engine == "VEO" else "VEO"
    return phase_c_ffmpeg.generate_ai_video(
        image_path=image,
        camera_motion="tracking_shot",
        target_api="AUTO",
        output_mp4=output,
        shot_type="action",
        video_fallbacks=[engine, fallback],
        ctx=PipelineContext(
            global_settings={"aspect_ratio": "16:9", "cascade_retry_limit": 0}
        ),
        _cascade_out=cascade,
        cost_tracker=tracker,
        shot_id=f"shot-{engine.lower()}",
        video_id=f"project-{engine.lower()}",
    )


def _native_runtime(monkeypatch) -> None:
    runtime = RuntimeSnapshot(
        credentials={
            "kling_access_key",
            "kling_secret_key",
            "openai_api_key",
        },
        modules={"jwt", "openai"},
    )
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "settings",
        SimpleNamespace(
            fal_key="",
            ltx_api_key="",
            runwayml_api_secret="",
        ),
    )
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        lambda: runtime,
    )
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_current_date",
        lambda: date(2026, 8, 5),
    )
    monkeypatch.setattr(phase_c_ffmpeg, "_accept_or_reject", lambda *_a: True)


def _generate_native(
    *,
    tracker: CostTracker,
    engine: str,
    fallback: str,
    image: str,
    output: str,
    cascade: dict,
):
    return phase_c_ffmpeg.generate_ai_video(
        image_path=image,
        camera_motion="tracking_shot",
        target_api=engine,
        output_mp4=output,
        shot_type="medium",
        video_fallbacks=[fallback],
        ctx=PipelineContext(
            global_settings={"aspect_ratio": "16:9", "cascade_retry_limit": 0}
        ),
        _cascade_out=cascade,
        cost_tracker=tracker,
        shot_id=f"shot-{engine.lower()}",
        video_id=f"project-{engine.lower()}",
    )


@pytest.mark.parametrize("engine", FAL_MOTION_ENGINES)
def test_crash_after_fal_submit_resumes_request_id_without_duplicate_paid_work(
    monkeypatch, tmp_path, engine
):
    _runtime(monkeypatch)
    image = tmp_path / f"{engine.lower()}.png"
    image.write_bytes(b"keyframe")
    db = str(tmp_path / f"{engine.lower()}.db")
    submit_calls: list[str] = []

    monkeypatch.setattr(fal_client, "upload_file", lambda _path: "https://fal.invalid/input.png")

    def submit(application, _arguments):
        submit_calls.append(application)
        return SimpleNamespace(request_id=f"request-{engine.lower()}")

    monkeypatch.setattr(fal_client, "submit", submit)
    monkeypatch.setattr(
        fal_client,
        "status",
        lambda *_a, **_k: (_ for _ in ()).throw(KeyboardInterrupt("worker died")),
    )
    first_cascade: dict = {}
    first = CostTracker(db_path=db, budget_usd=20.0)
    try:
        with pytest.raises(KeyboardInterrupt, match="worker died"):
            _generate(
                tracker=first,
                engine=engine,
                image=str(image),
                output=str(tmp_path / "first.mp4"),
                cascade=first_cascade,
            )
        attempt = first.get_latest_paid_attempt(
            video_id=f"project-{engine.lower()}",
            shot_id=f"shot-{engine.lower()}",
            engine=engine,
            operation="motion_generation",
        )
        assert attempt["state"] == "running"
        assert attempt["provider_job_id"] == f"request-{engine.lower()}"
        assert first_cascade["attempt_history"] == [engine]
        # Recovery ownership must outrank automatic health avoidance. Without
        # the active-attempt pin, these failures would route restart to the next
        # provider and strand/duplicate the accepted request.
        for _ in range(3):
            first.record_provider_observation(
                provider="fal",
                engine=engine,
                operation="motion_generation",
                status="failed",
                latency_ms=1.0,
                video_id="historical-health",
            )
        assert first.get_provider_usage_analytics("")["by_engine"][engine][
            "health"
        ]["status"] == "unhealthy"
    finally:
        first.close()

    def duplicate_submit(*_a, **_k):
        raise AssertionError("restart submitted a second paid FAL job")

    monkeypatch.setattr(fal_client, "submit", duplicate_submit)
    monkeypatch.setattr(
        fal_client,
        "status",
        lambda *_a, **_k: {"status": "COMPLETED"},
    )
    monkeypatch.setattr(
        fal_client,
        "result",
        lambda *_a, **_k: {"video": {"url": "https://fal.invalid/result.mp4"}},
    )

    def download(_url, destination, **_kwargs):
        with open(destination, "wb") as handle:
            handle.write(b"video")
        return destination

    monkeypatch.setattr(phase_c_ffmpeg, "safe_download", download)
    resumed_output = tmp_path / "resumed.mp4"
    resumed_cascade: dict = {}
    resumed = CostTracker(db_path=db, budget_usd=20.0)
    try:
        assert _generate(
            tracker=resumed,
            engine=engine,
            image=str(image),
            output=str(resumed_output),
            cascade=resumed_cascade,
        ) == str(resumed_output)
        assert resumed_cascade["recovery_owner"]["engine"] == engine
        settled = resumed.get_latest_paid_attempt(
            video_id=f"project-{engine.lower()}",
            shot_id=f"shot-{engine.lower()}",
            engine=engine,
            operation="motion_generation",
        )
        assert settled["state"] == "succeeded"
        assert settled["provider_job_id"] == f"request-{engine.lower()}"
        assert resumed.get_video_cost(f"project-{engine.lower()}")["total_usd"] > 0
        assert len(submit_calls) == 1
    finally:
        resumed.close()


@pytest.mark.parametrize("engine", FAL_MOTION_ENGINES)
def test_lost_submit_acknowledgement_blocks_fallback_and_every_replay(
    monkeypatch, tmp_path, engine
):
    _runtime(monkeypatch)
    image = tmp_path / f"ambiguous-{engine.lower()}.png"
    image.write_bytes(b"keyframe")
    db = str(tmp_path / f"ambiguous-{engine.lower()}.db")
    submit_count = 0
    monkeypatch.setattr(fal_client, "upload_file", lambda _path: "https://fal.invalid/input.png")

    def ambiguous_submit(*_a, **_k):
        nonlocal submit_count
        submit_count += 1
        raise TimeoutError("submit response lost")

    monkeypatch.setattr(fal_client, "submit", ambiguous_submit)
    first_cascade: dict = {}
    tracker = CostTracker(db_path=db, budget_usd=20.0)
    try:
        assert _generate(
            tracker=tracker,
            engine=engine,
            image=str(image),
            output=str(tmp_path / "ambiguous.mp4"),
            cascade=first_cascade,
        ) is None
        assert first_cascade["attempt_history"] == [engine]
        assert first_cascade["deferred_job"]["reason"] == "submission_outcome_unknown"
        attempt = tracker.get_latest_paid_attempt(
            video_id=f"project-{engine.lower()}",
            shot_id=f"shot-{engine.lower()}",
            engine=engine,
            operation="motion_generation",
        )
        assert attempt["state"] == "accepted_unknown"
        assert attempt["provider_job_id"] == ""
    finally:
        tracker.close()

    def duplicate_submit(*_a, **_k):
        raise AssertionError("ambiguous FAL submission was replayed")

    monkeypatch.setattr(fal_client, "submit", duplicate_submit)
    second_cascade: dict = {}
    restarted = CostTracker(db_path=db, budget_usd=20.0)
    try:
        assert _generate(
            tracker=restarted,
            engine=engine,
            image=str(image),
            output=str(tmp_path / "retry.mp4"),
            cascade=second_cascade,
        ) is None
        assert second_cascade["attempt_history"] == [engine]
        assert submit_count == 1
    finally:
        restarted.close()


def test_active_request_with_changed_inputs_blocks_resume_and_new_fallback(
    monkeypatch, tmp_path
):
    _runtime(monkeypatch)
    image = tmp_path / "changed.png"
    image.write_bytes(b"keyframe")
    db = str(tmp_path / "changed.db")
    monkeypatch.setattr(fal_client, "upload_file", lambda _path: "https://fal.invalid/input.png")
    monkeypatch.setattr(
        fal_client,
        "submit",
        lambda *_a, **_k: SimpleNamespace(request_id="request-changed"),
    )
    monkeypatch.setattr(
        fal_client,
        "status",
        lambda *_a, **_k: (_ for _ in ()).throw(KeyboardInterrupt("worker died")),
    )
    first = CostTracker(db_path=db, budget_usd=20.0)
    try:
        with pytest.raises(KeyboardInterrupt):
            _generate(
                tracker=first,
                engine="VEO",
                image=str(image),
                output=str(tmp_path / "first.mp4"),
                cascade={},
            )
    finally:
        first.close()

    def provider_tripwire(*_a, **_k):
        raise AssertionError("changed request touched an accepted provider job")

    monkeypatch.setattr(fal_client, "submit", provider_tripwire)
    monkeypatch.setattr(fal_client, "status", provider_tripwire)
    cascade: dict = {}
    restarted = CostTracker(db_path=db, budget_usd=20.0)
    try:
        assert phase_c_ffmpeg.generate_ai_video(
            image_path=str(image),
            camera_motion="pan_left",
            target_api="AUTO",
            output_mp4=str(tmp_path / "changed-retry.mp4"),
            shot_type="action",
            video_fallbacks=["VEO", "SEEDANCE"],
            ctx=PipelineContext(global_settings={"aspect_ratio": "16:9"}),
            _cascade_out=cascade,
            cost_tracker=restarted,
            shot_id="shot-veo",
            video_id="project-veo",
        ) is None
        assert cascade["attempt_history"] == ["VEO"]
        assert cascade["deferred_job"]["reason"] == "request_changed_during_recovery"
        assert restarted.get_latest_paid_attempt(
            video_id="project-veo",
            shot_id="shot-veo",
            engine="VEO",
            operation="motion_generation",
        )["state"] == "running"
    finally:
        restarted.close()


@pytest.mark.parametrize(
    ("terminal_status", "billed", "expects_fallback"),
    [
        ("FAILED", False, True),
        ("CANCELLED", False, True),
        ("FAILED", True, False),
    ],
)
def test_automatic_motion_fallback_requires_explicit_unbilled_terminal_truth(
    monkeypatch, tmp_path, terminal_status, billed, expects_fallback
):
    _runtime(monkeypatch)
    image = tmp_path / "terminal.png"
    image.write_bytes(b"keyframe")
    submit_calls: list[str] = []
    monkeypatch.setattr(fal_client, "upload_file", lambda _path: "https://fal.invalid/input.png")

    def submit(application, _arguments):
        submit_calls.append(application)
        return SimpleNamespace(request_id=f"terminal-{len(submit_calls)}")

    def status(_application, request_id, **_kwargs):
        if request_id == "terminal-1":
            return {
                "status": terminal_status,
                "error": "provider terminal",
                "billed": billed,
            }
        return {"status": "COMPLETED"}

    monkeypatch.setattr(fal_client, "submit", submit)
    monkeypatch.setattr(fal_client, "status", status)
    monkeypatch.setattr(
        fal_client,
        "result",
        lambda *_a, **_k: {"video": {"url": "https://fal.invalid/result.mp4"}},
    )

    def download(_url, destination, **_kwargs):
        with open(destination, "wb") as handle:
            handle.write(b"video")
        return destination

    monkeypatch.setattr(phase_c_ffmpeg, "safe_download", download)
    cascade: dict = {}
    output = tmp_path / "terminal.mp4"
    with CostTracker(
        db_path=str(tmp_path / f"terminal-{terminal_status}-{billed}.db"),
        budget_usd=20.0,
    ) as tracker:
        result = phase_c_ffmpeg.generate_ai_video(
            image_path=str(image),
            camera_motion="tracking_shot",
            target_api="AUTO",
            output_mp4=str(output),
            shot_type="action",
            video_fallbacks=["VEO", "SEEDANCE"],
            ctx=PipelineContext(global_settings={"aspect_ratio": "16:9"}),
            _cascade_out=cascade,
            cost_tracker=tracker,
            shot_id="shot-terminal",
            video_id="project-terminal",
        )
        first = tracker.get_latest_paid_attempt(
            video_id="project-terminal",
            shot_id="shot-terminal",
            engine="VEO",
            operation="motion_generation",
        )
        if expects_fallback:
            assert result == str(output)
            assert cascade["attempt_history"] == ["VEO", "SEEDANCE"]
            assert len(submit_calls) == 2
            assert first["state"] in {"failed_unbilled", "cancelled"}
        else:
            assert result is None
            assert cascade["attempt_history"] == ["VEO"]
            assert len(submit_calls) == 1
            assert first["state"] == "failed_billed"


def test_kling_native_lost_submit_ack_blocks_fallback_and_restart(
    monkeypatch, tmp_path
):
    import kling_native

    _native_runtime(monkeypatch)
    monkeypatch.setattr(
        kling_native,
        "settings",
        SimpleNamespace(
            kling_access_key="ak-offline",
            kling_secret_key="offline-secret-for-tests-32-bytes+",
        ),
    )
    image = tmp_path / "kling-ambiguous.png"
    image.write_bytes(b"keyframe")
    db = str(tmp_path / "kling-ambiguous.db")
    submit_count = 0

    def ambiguous_post(*_args, **_kwargs):
        nonlocal submit_count
        submit_count += 1
        raise TimeoutError("Kling submit acknowledgement lost")

    monkeypatch.setattr(kling_native.requests, "post", ambiguous_post)
    first_cascade: dict = {}
    with CostTracker(db_path=db, budget_usd=20.0) as first:
        assert _generate_native(
            tracker=first,
            engine="KLING_NATIVE",
            fallback="SORA_NATIVE",
            image=str(image),
            output=str(tmp_path / "kling-ambiguous.mp4"),
            cascade=first_cascade,
        ) is None
        attempt = first.get_latest_paid_attempt(
            video_id="project-kling_native",
            shot_id="shot-kling_native",
            engine="KLING_NATIVE",
            operation="motion_generation",
        )
        assert attempt["state"] == "accepted_unknown"
        assert attempt["provider_job_id"] == ""
        assert first_cascade["attempt_history"] == ["KLING_NATIVE"]
        assert first_cascade["deferred_job"]["reason"] == "submission_outcome_unknown"

    def duplicate_post(*_args, **_kwargs):
        raise AssertionError("ambiguous Kling submission was replayed")

    monkeypatch.setattr(kling_native.requests, "post", duplicate_post)
    restarted_cascade: dict = {}
    with CostTracker(db_path=db, budget_usd=20.0) as restarted:
        assert _generate_native(
            tracker=restarted,
            engine="KLING_NATIVE",
            fallback="SORA_NATIVE",
            image=str(image),
            output=str(tmp_path / "kling-restart.mp4"),
            cascade=restarted_cascade,
        ) is None
        assert restarted_cascade["recovery_owner"]["engine"] == "KLING_NATIVE"
        assert restarted_cascade["attempt_history"] == ["KLING_NATIVE"]
        assert submit_count == 1


def test_kling_native_acknowledged_task_resumes_exact_id_without_resubmit(
    monkeypatch, tmp_path
):
    import kling_native

    _native_runtime(monkeypatch)
    monkeypatch.setattr(
        kling_native,
        "settings",
        SimpleNamespace(
            kling_access_key="ak-offline",
            kling_secret_key="offline-secret-for-tests-32-bytes+",
        ),
    )
    image = tmp_path / "kling-resume.png"
    image.write_bytes(b"keyframe")
    db = str(tmp_path / "kling-resume.db")
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "code": 0,
        "data": {"task_id": "kling-task-durable-1"},
    }
    post_count = 0

    def acknowledged_post(*_args, **_kwargs):
        nonlocal post_count
        post_count += 1
        return response

    monkeypatch.setattr(kling_native.requests, "post", acknowledged_post)
    monkeypatch.setattr(
        kling_native.KlingNativeAPI,
        "poll_task",
        lambda *_a, **_k: (_ for _ in ()).throw(
            KeyboardInterrupt("worker stopped after Kling acknowledgement")
        ),
    )
    with CostTracker(db_path=db, budget_usd=20.0) as first:
        with pytest.raises(KeyboardInterrupt, match="Kling acknowledgement"):
            _generate_native(
                tracker=first,
                engine="KLING_NATIVE",
                fallback="SORA_NATIVE",
                image=str(image),
                output=str(tmp_path / "kling-first.mp4"),
                cascade={},
            )
        active = first.get_latest_paid_attempt(
            video_id="project-kling_native",
            shot_id="shot-kling_native",
            engine="KLING_NATIVE",
            operation="motion_generation",
        )
        assert active["state"] == "running"
        assert active["provider_job_id"] == "kling-task-durable-1"

    def duplicate_post(*_args, **_kwargs):
        raise AssertionError("Kling exact-ID recovery submitted a replacement job")

    monkeypatch.setattr(kling_native.requests, "post", duplicate_post)
    polled_ids: list[str] = []

    def completed_poll(_self, task_id, **_kwargs):
        polled_ids.append(task_id)
        return {
            "task_result": {
                "videos": [{"url": "https://kling.invalid/video.mp4"}],
            },
        }

    def download(_self, _url, output_path):
        with open(output_path, "wb") as handle:
            handle.write(b"video")
        return output_path

    monkeypatch.setattr(kling_native.KlingNativeAPI, "poll_task", completed_poll)
    monkeypatch.setattr(kling_native.KlingNativeAPI, "download_video", download)
    resumed_cascade: dict = {}
    resumed_output = tmp_path / "kling-resumed.mp4"
    with CostTracker(db_path=db, budget_usd=20.0) as resumed:
        assert _generate_native(
            tracker=resumed,
            engine="KLING_NATIVE",
            fallback="SORA_NATIVE",
            image=str(image),
            output=str(resumed_output),
            cascade=resumed_cascade,
        ) == str(resumed_output)
        settled = resumed.get_latest_paid_attempt(
            video_id="project-kling_native",
            shot_id="shot-kling_native",
            engine="KLING_NATIVE",
            operation="motion_generation",
        )
        assert settled["state"] == "succeeded"
        assert settled["provider_job_id"] == "kling-task-durable-1"
        assert resumed_cascade["recovery_owner"]["engine"] == "KLING_NATIVE"
        assert polled_ids == ["kling-task-durable-1"]
        assert post_count == 1


def test_sora_native_ambiguous_create_and_poll_blocks_fallback_and_restart(
    monkeypatch, tmp_path
):
    import sora_native
    from PIL import Image

    _native_runtime(monkeypatch)
    monkeypatch.setattr(
        sora_native,
        "settings",
        SimpleNamespace(openai_api_key="sk-offline"),
    )
    image = tmp_path / "sora-ambiguous.jpg"
    with Image.new("RGB", (32, 18), color=(16, 32, 64)) as source:
        source.save(image, format="JPEG")
    db = str(tmp_path / "sora-ambiguous.db")
    client = MagicMock()
    client.videos.create_and_poll.side_effect = TimeoutError(
        "Sora composite call outcome lost"
    )
    constructor_count = 0

    def make_client(*_args, **_kwargs):
        nonlocal constructor_count
        constructor_count += 1
        return client

    monkeypatch.setattr(sora_native.openai, "OpenAI", make_client)
    first_cascade: dict = {}
    with CostTracker(db_path=db, budget_usd=20.0) as first:
        assert _generate_native(
            tracker=first,
            engine="SORA_NATIVE",
            fallback="KLING_NATIVE",
            image=str(image),
            output=str(tmp_path / "sora-ambiguous.mp4"),
            cascade=first_cascade,
        ) is None
        attempt = first.get_latest_paid_attempt(
            video_id="project-sora_native",
            shot_id="shot-sora_native",
            engine="SORA_NATIVE",
            operation="motion_generation",
        )
        assert attempt["state"] == "accepted_unknown"
        assert first_cascade["attempt_history"] == ["SORA_NATIVE"]
        assert first_cascade["deferred_job"]["reason"] == "submission_outcome_unknown"

    def duplicate_constructor(*_args, **_kwargs):
        raise AssertionError("ambiguous Sora submission was replayed")

    monkeypatch.setattr(sora_native.openai, "OpenAI", duplicate_constructor)
    restarted_cascade: dict = {}
    with CostTracker(db_path=db, budget_usd=20.0) as restarted:
        assert _generate_native(
            tracker=restarted,
            engine="SORA_NATIVE",
            fallback="KLING_NATIVE",
            image=str(image),
            output=str(tmp_path / "sora-restart.mp4"),
            cascade=restarted_cascade,
        ) is None
        assert restarted_cascade["recovery_owner"]["engine"] == "SORA_NATIVE"
        assert restarted_cascade["attempt_history"] == ["SORA_NATIVE"]
        assert constructor_count == 1


def test_fal_svd_crash_resumes_request_id_without_duplicate_submit(
    monkeypatch, tmp_path
):
    _runtime(monkeypatch)
    image = tmp_path / "svd.png"
    image.write_bytes(b"keyframe")
    db = str(tmp_path / "svd.db")
    submit_count = 0
    monkeypatch.setattr(
        fal_client,
        "upload_file",
        lambda _path: "https://fal.invalid/input.png",
    )

    def submit(application, _arguments):
        nonlocal submit_count
        submit_count += 1
        assert application == "fal-ai/fast-svd"
        return SimpleNamespace(request_id="svd-request-durable-1")

    monkeypatch.setattr(fal_client, "submit", submit)
    monkeypatch.setattr(
        fal_client,
        "status",
        lambda *_a, **_k: (_ for _ in ()).throw(
            KeyboardInterrupt("worker stopped after FAL SVD submit")
        ),
    )

    def generate(tracker, output, cascade):
        return phase_c_ffmpeg.generate_ai_video(
            image_path=str(image),
            camera_motion="subtle_motion",
            target_api="FAL_SVD",
            output_mp4=str(output),
            shot_type="medium",
            ctx=PipelineContext(global_settings={"aspect_ratio": "16:9"}),
            _cascade_out=cascade,
            cost_tracker=tracker,
            shot_id="shot-svd",
            video_id="project-svd",
        )

    with CostTracker(db_path=db, budget_usd=20.0) as first:
        with pytest.raises(KeyboardInterrupt, match="FAL SVD submit"):
            generate(first, tmp_path / "svd-first.mp4", {})
        active = first.get_latest_paid_attempt(
            video_id="project-svd",
            shot_id="shot-svd",
            engine="FAL_SVD",
            operation="motion_generation",
        )
        assert active["state"] == "running"
        assert active["provider_job_id"] == "svd-request-durable-1"

    def duplicate_submit(*_args, **_kwargs):
        raise AssertionError("FAL SVD recovery submitted a replacement job")

    monkeypatch.setattr(fal_client, "submit", duplicate_submit)
    monkeypatch.setattr(
        fal_client,
        "status",
        lambda *_a, **_k: {"status": "COMPLETED"},
    )
    monkeypatch.setattr(
        fal_client,
        "result",
        lambda *_a, **_k: {"video": {"url": "https://fal.invalid/svd.mp4"}},
    )

    def download(_url, destination, **_kwargs):
        with open(destination, "wb") as handle:
            handle.write(b"video")
        return destination

    monkeypatch.setattr(phase_c_ffmpeg, "safe_download", download)
    resumed_cascade: dict = {}
    resumed_output = tmp_path / "svd-resumed.mp4"
    with CostTracker(db_path=db, budget_usd=20.0) as resumed:
        assert generate(resumed, resumed_output, resumed_cascade) == str(resumed_output)
        settled = resumed.get_latest_paid_attempt(
            video_id="project-svd",
            shot_id="shot-svd",
            engine="FAL_SVD",
            operation="motion_generation",
        )
        assert settled["state"] == "succeeded"
        assert settled["provider_job_id"] == "svd-request-durable-1"
        assert resumed_cascade["recovery_owner"]["engine"] == "FAL_SVD"
        assert submit_count == 1


def test_kling_legacy_compatibility_path_never_subscribes_twice(
    monkeypatch, tmp_path
):
    _runtime(monkeypatch)
    image = tmp_path / "kling.png"
    image.write_bytes(b"keyframe")
    subscribe_calls = 0
    monkeypatch.setattr(fal_client, "upload_file", lambda _path: "https://fal.invalid/input.png")

    def fail_once(*_a, **_k):
        nonlocal subscribe_calls
        subscribe_calls += 1
        raise TimeoutError("legacy compatibility call failed")

    monkeypatch.setattr(fal_client, "subscribe", fail_once)
    assert phase_c_ffmpeg.generate_ai_video(
        image_path=str(image),
        camera_motion="tracking_shot",
        target_api="KLING_3_0",
        output_mp4=str(tmp_path / "kling.mp4"),
        shot_type="action",
        video_fallbacks=["KLING_3_0"],
        ctx=PipelineContext(
            global_settings={"aspect_ratio": "16:9", "cascade_retry_limit": 0}
        ),
    ) is None
    assert subscribe_calls == 1
