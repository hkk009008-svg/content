"""Offline contract tests for the LTX 2.3 native/FAL adapter."""
from __future__ import annotations

import inspect
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# A few sibling tests install a deliberately tiny import stub.  This module
# owns the real adapter contract, so collection must import the real module.
sys.modules.pop("ltx_native", None)

import ltx_native
from ltx_native import LTXContractViolation, LTXJobPending, LTXVideoAPI


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"input-image"
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"input-image"
WEBP_BYTES = b"RIFF\x0c\x00\x00\x00WEBP" + b"input-image"
MP4_BYTES = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload=None,
        *,
        text: str = "",
        headers: dict | None = None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"status {self.status_code}",
                response=self,
            )


def _fake_settings(ltx_key: str = "", fal_key: str = "") -> MagicMock:
    configured = MagicMock()
    configured.ltx_api_key = ltx_key
    configured.fal_key = fal_key
    return configured


def _make_api(
    ltx_key: str = "",
    fal_key: str = "",
    mode: str | None = None,
) -> LTXVideoAPI:
    with patch(
        "ltx_native.settings",
        _fake_settings(ltx_key=ltx_key, fal_key=fal_key),
    ):
        api = LTXVideoAPI()
    if mode is not None:
        api.mode = mode
    return api


def _write_image(tmp_path: Path, data: bytes = PNG_BYTES) -> Path:
    image = tmp_path / "frame.any"
    image.write_bytes(data)
    return image


def _successful_download(monkeypatch, events: list[str] | None = None):
    def download(url, destination, **kwargs):
        if events is not None:
            events.append("download")
        Path(destination).write_bytes(MP4_BYTES)
        return destination

    monkeypatch.setattr(ltx_native, "safe_download", download)


def _seed_terminal_job_state(
    api: LTXVideoAPI,
    image: Path,
    output: Path,
    status: str,
) -> Path:
    request = {
        "prompt": "prompt",
        "model": "ltx-2-3-pro",
        "duration": 6,
        "resolution": "1920x1080",
        "generate_audio": False,
    }
    fingerprint = api._request_fingerprint(str(image), request)
    state_path = Path(api._job_state_path(str(output), fingerprint))
    api._write_job_state(
        str(state_path),
        {
            "schema_version": api.JOB_STATE_SCHEMA_VERSION,
            "provider": "ltx",
            "endpoint": "image-to-video",
            "job_id": "job-terminal",
            "request_fingerprint": fingerprint,
            "duration_s": 6,
            "status": status,
            "updated_at": 1.0,
        },
    )
    return state_path


def _install_native_http(
    monkeypatch,
    *,
    poll_payloads: list[dict] | None = None,
    required_headers: dict | None = None,
):
    calls: dict[str, list] = {"post": [], "put": [], "get": []}
    post_responses = iter(
        [
            FakeResponse(
                200,
                {
                    "upload_url": "https://uploads.example.test/signed",
                    "storage_uri": "ltx://uploads/input-1",
                    "expires_at": "2026-08-04T01:00:00Z",
                    "required_headers": required_headers or {},
                },
            ),
            FakeResponse(
                202,
                {
                    "id": "job-123",
                    "created_at": "2026-08-04T00:00:00Z",
                },
            ),
        ]
    )
    polls = iter(
        poll_payloads
        or [
            {"id": "job-123", "status": "processing"},
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            },
        ]
    )

    def fake_post(url, **kwargs):
        calls["post"].append((url, kwargs))
        return next(post_responses)

    def fake_put(url, **kwargs):
        calls["put"].append((url, kwargs))
        # Read while the adapter-owned file handle is open.
        calls["put_bytes"] = [kwargs["data"].read()]
        return FakeResponse(200)

    def fake_get(url, **kwargs):
        calls["get"].append((url, kwargs))
        return FakeResponse(200, next(polls))

    monkeypatch.setattr(ltx_native.requests, "post", fake_post)
    monkeypatch.setattr(ltx_native.requests, "put", fake_put)
    monkeypatch.setattr(ltx_native.requests, "get", fake_get)
    monkeypatch.setattr(LTXVideoAPI, "NATIVE_POLL_INTERVAL_S", 0)
    return calls


def test_init_modes_and_native_precedence(monkeypatch):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    assert _make_api().mode is None
    assert _make_api(fal_key="fal").mode == "fal"
    assert _make_api(ltx_key="ltx").mode == "native"
    assert _make_api(ltx_key="ltx", fal_key="fal").mode == "native"


def test_native_host_and_async_paths_are_current():
    assert LTXVideoAPI.NATIVE_BASE_URL == "https://api.ltx.io"
    assert LTXVideoAPI.NATIVE_UPLOAD_PATH == "/v1/upload"
    assert LTXVideoAPI.NATIVE_ASYNC_PATH == "/v2/image-to-video"


def test_default_and_supported_duration_contract():
    default = inspect.signature(LTXVideoAPI.generate_video).parameters["duration"].default
    assert default == 6
    assert LTXVideoAPI.DURATION_SECONDS == (6, 8, 10)
    assert LTXVideoAPI.nearest_supported_duration(4) == 6
    assert LTXVideoAPI.nearest_supported_duration(7) == 8
    assert LTXVideoAPI.nearest_supported_duration(9) == 10
    assert LTXVideoAPI.nearest_supported_duration(15) == 10


def test_phase_c_duration_enum_matches_adapter():
    import phase_c_ffmpeg

    assert phase_c_ffmpeg._LTX_DURATION_ENUM_S == LTXVideoAPI.DURATION_SECONDS


@pytest.mark.parametrize("mode", ["native", "fal"])
def test_invalid_duration_is_rejected_before_network(monkeypatch, tmp_path, mode):
    api = _make_api(ltx_key="ltx", fal_key="fal", mode=mode)
    image = _write_image(tmp_path)
    post = MagicMock()
    subscribe = MagicMock()
    monkeypatch.setattr(ltx_native.requests, "post", post)
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe)

    with pytest.raises(LTXContractViolation):
        api.generate_video(
            str(image),
            "prompt",
            str(tmp_path / "out.mp4"),
            duration=4,
        )

    post.assert_not_called()
    subscribe.assert_not_called()


@pytest.mark.parametrize("prompt", ["", "   ", "x" * 5001, None])
def test_invalid_prompt_is_rejected_before_network(monkeypatch, tmp_path, prompt):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    post = MagicMock()
    monkeypatch.setattr(ltx_native.requests, "post", post)

    with pytest.raises(LTXContractViolation):
        api.generate_video(
            str(image),
            prompt,
            str(tmp_path / "out.mp4"),
        )

    post.assert_not_called()


def test_no_key_returns_none_without_reading_input(tmp_path):
    api = _make_api()
    assert api.generate_video(
        str(tmp_path / "missing.png"),
        "prompt",
        str(tmp_path / "out.mp4"),
    ) is None


@pytest.mark.parametrize(
    ("image_bytes", "expected_mime"),
    [
        (PNG_BYTES, "image/png"),
        (JPEG_BYTES, "image/jpeg"),
        (WEBP_BYTES, "image/webp"),
    ],
)
def test_signed_upload_uses_mime_from_bytes(
    monkeypatch,
    tmp_path,
    image_bytes,
    expected_mime,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path, image_bytes)
    calls = _install_native_http(
        monkeypatch,
        poll_payloads=[
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            }
        ],
    )
    _successful_download(monkeypatch)

    assert api.generate_video(
        str(image),
        "prompt",
        str(tmp_path / "out.mp4"),
    ) == str(tmp_path / "out.mp4")

    upload_url, upload_kwargs = calls["put"][0]
    assert upload_url == "https://uploads.example.test/signed"
    assert upload_kwargs["headers"]["Content-Type"] == expected_mime
    assert upload_kwargs["allow_redirects"] is False
    assert calls["put_bytes"] == [image_bytes]


def test_signed_upload_preserves_provider_required_headers(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    calls = _install_native_http(
        monkeypatch,
        required_headers={
            "x-goog-content-length-range": "1,15728640",
            "content-type": "image/png",
        },
        poll_payloads=[
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            }
        ],
    )
    _successful_download(monkeypatch)

    api.generate_video(str(image), "prompt", str(tmp_path / "out.mp4"))

    headers = calls["put"][0][1]["headers"]
    assert headers == {
        "x-goog-content-length-range": "1,15728640",
        "content-type": "image/png",
    }


def test_upload_ticket_mime_mismatch_fails_before_put(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path, PNG_BYTES)
    put = MagicMock()
    monkeypatch.setattr(
        ltx_native.requests,
        "post",
        MagicMock(
            return_value=FakeResponse(
                200,
                {
                    "upload_url": "https://uploads.example.test/signed",
                    "storage_uri": "ltx://uploads/input-1",
                    "required_headers": {"Content-Type": "image/jpeg"},
                },
            )
        ),
    )
    monkeypatch.setattr(ltx_native.requests, "put", put)

    assert api.generate_video(
        str(image), "prompt", str(tmp_path / "out.mp4")
    ) is None
    put.assert_not_called()


def test_native_flow_uses_ltx_upload_not_fal_and_submits_ltx_uri(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx", fal_key="fal")
    image = _write_image(tmp_path)
    fal_upload = MagicMock(side_effect=AssertionError("native path touched FAL upload"))
    monkeypatch.setattr(ltx_native.fal_client, "upload_file", fal_upload)
    calls = _install_native_http(monkeypatch)
    _successful_download(monkeypatch)

    result = api.generate_video(
        str(image),
        "cinematic",
        str(tmp_path / "out.mp4"),
        duration=8,
        resolution="1080p",
        camera_motion="dolly_in",
    )

    assert result == str(tmp_path / "out.mp4")
    fal_upload.assert_not_called()
    assert [item[0] for item in calls["post"]] == [
        "https://api.ltx.io/v1/upload",
        "https://api.ltx.io/v2/image-to-video",
    ]
    submit = calls["post"][1][1]
    assert submit["json"] == {
        "image_uri": "ltx://uploads/input-1",
        "prompt": "cinematic. Camera: dolly in.",
        "model": "ltx-2-3-pro",
        "duration": 8,
        "resolution": "1920x1080",
        "generate_audio": False,
    }
    assert submit["allow_redirects"] is False


def test_job_id_is_persisted_before_first_poll(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    events: list[str] = []
    _install_native_http(
        monkeypatch,
        poll_payloads=[
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            }
        ],
    )
    _successful_download(monkeypatch)
    real_write = LTXVideoAPI._write_job_state.__func__

    def recording_write(cls, path, state):
        events.append(f"persist:{state['status']}")
        return real_write(cls, path, state)

    def recording_get(url, **kwargs):
        events.append("poll")
        return FakeResponse(
            200,
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            },
        )

    monkeypatch.setattr(
        LTXVideoAPI,
        "_write_job_state",
        classmethod(recording_write),
    )
    monkeypatch.setattr(ltx_native.requests, "get", recording_get)

    api.generate_video(str(image), "prompt", str(tmp_path / "out.mp4"))

    assert events[:2] == ["persist:submitted", "poll"]
    state_files = list(tmp_path.glob(".ltx-image-to-video-*.job.json"))
    assert len(state_files) == 1
    state = json.loads(state_files[0].read_text())
    assert state["job_id"] == "job-123"
    assert state["request_fingerprint"]
    assert state["status"] == "completed"


def test_exclusive_submission_claim_is_durable_before_generation_post(
    monkeypatch,
    tmp_path,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    observed_claim: dict = {}

    monkeypatch.setattr(api, "_native_upload", lambda _path: "ltx://uploads/input-1")

    def submit(_payload):
        state_path = next(tmp_path.glob(".ltx-image-to-video-*.job.json"))
        observed_claim.update(json.loads(state_path.read_text(encoding="utf-8")))
        return "job-claim-1", "2026-08-04T00:00:00Z"

    monkeypatch.setattr(api, "_submit_native_job", submit)
    monkeypatch.setattr(
        api,
        "_poll_native_job",
        lambda *_args: {"status": "failed", "error": {"message": "terminal"}},
    )

    assert api.generate_video(
        str(image),
        "prompt",
        str(tmp_path / "out.mp4"),
        duration=8,
    ) is None

    assert observed_claim["status"] == "submission_claimed"
    assert observed_claim["duration_s"] == 8
    assert observed_claim["request_fingerprint"] == api.last_request_fingerprint
    assert "job_id" not in observed_claim
    assert api.last_job_id == "job-claim-1"
    assert api.last_duration_s == 8


def test_concurrent_identical_requests_cross_generation_post_once(
    monkeypatch,
    tmp_path,
):
    first = _make_api(ltx_key="ltx")
    second = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    submit_entered = threading.Event()
    release_submit = threading.Event()
    submit_count = 0
    submit_count_lock = threading.Lock()

    for api in (first, second):
        monkeypatch.setattr(
            api,
            "_native_upload",
            lambda _path: "ltx://uploads/input-1",
        )
        monkeypatch.setattr(
            api,
            "_poll_native_job",
            lambda *_args: {"status": "failed", "error": {"message": "terminal"}},
        )

    def submit(_payload):
        nonlocal submit_count
        with submit_count_lock:
            submit_count += 1
        submit_entered.set()
        assert release_submit.wait(timeout=5)
        return "job-concurrent", "2026-08-04T00:00:00Z"

    monkeypatch.setattr(first, "_submit_native_job", submit)
    monkeypatch.setattr(
        second,
        "_submit_native_job",
        MagicMock(side_effect=AssertionError("duplicate generation POST")),
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        winner = pool.submit(
            first.generate_video,
            str(image),
            "prompt",
            str(tmp_path / "first.mp4"),
        )
        assert submit_entered.wait(timeout=5)
        try:
            with pytest.raises(LTXJobPending) as pending:
                second.generate_video(
                    str(image),
                    "prompt",
                    str(tmp_path / "second.mp4"),
                )
            assert pending.value.reason == "submit_outcome_unknown"
            assert pending.value.provider_status == "submission_claimed"
            assert pending.value.duration_s == 6
        finally:
            release_submit.set()
        assert winner.result(timeout=5) is None

    assert submit_count == 1
    second._submit_native_job.assert_not_called()


@pytest.mark.parametrize("terminal_status", ["failed", "expired"])
def test_terminal_sidecar_allows_one_fresh_submission(
    terminal_status,
    monkeypatch,
    tmp_path,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    output = tmp_path / "out.mp4"
    state_path = _seed_terminal_job_state(
        api,
        image,
        output,
        terminal_status,
    )
    monkeypatch.setattr(api, "_native_upload", lambda _path: "ltx://uploads/retry")
    submit = MagicMock(return_value=("job-retry", "2026-08-05T00:00:00Z"))
    monkeypatch.setattr(api, "_submit_native_job", submit)
    poll = MagicMock(
        return_value={"status": "failed", "error": {"message": "terminal"}}
    )
    monkeypatch.setattr(api, "_poll_native_job", poll)

    assert api.generate_video(str(image), "prompt", str(output)) is None

    submit.assert_called_once()
    assert poll.call_args.args[0] == "job-retry"
    replacement = json.loads(state_path.read_text(encoding="utf-8"))
    assert replacement["job_id"] == "job-retry"
    assert replacement["status"] == "submitted"


def test_concurrent_terminal_retries_cross_generation_post_once(
    monkeypatch,
    tmp_path,
):
    first = _make_api(ltx_key="ltx")
    second = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    output = tmp_path / "out.mp4"
    _seed_terminal_job_state(first, image, output, "failed")
    submit_entered = threading.Event()
    release_submit = threading.Event()

    for api in (first, second):
        monkeypatch.setattr(
            api,
            "_native_upload",
            lambda _path: "ltx://uploads/retry",
        )
    monkeypatch.setattr(
        first,
        "_poll_native_job",
        lambda *_args: {"status": "failed", "error": {"message": "terminal"}},
    )

    def submit(_payload):
        submit_entered.set()
        assert release_submit.wait(timeout=5)
        return "job-retry", "2026-08-05T00:00:00Z"

    monkeypatch.setattr(first, "_submit_native_job", submit)
    duplicate_submit = MagicMock(
        side_effect=AssertionError("duplicate generation POST")
    )
    monkeypatch.setattr(second, "_submit_native_job", duplicate_submit)

    with ThreadPoolExecutor(max_workers=1) as pool:
        winner = pool.submit(
            first.generate_video,
            str(image),
            "prompt",
            str(output),
        )
        assert submit_entered.wait(timeout=5)
        try:
            with pytest.raises(LTXJobPending) as pending:
                second.generate_video(str(image), "prompt", str(output))
            assert pending.value.reason == "submit_outcome_unknown"
            assert pending.value.provider_status == "submission_claimed"
        finally:
            release_submit.set()
        assert winner.result(timeout=5) is None

    duplicate_submit.assert_not_called()


def test_abandoned_submission_claim_blocks_upload_and_resubmit(
    monkeypatch,
    tmp_path,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    request = {
        "prompt": "prompt",
        "model": "ltx-2-3-pro",
        "duration": 6,
        "resolution": "1920x1080",
        "generate_audio": False,
    }
    fingerprint = api._request_fingerprint(str(image), request)
    state_path = api._job_state_path(str(tmp_path / "out.mp4"), fingerprint)
    api._claim_submission_state(state_path, fingerprint, 6)
    upload = MagicMock(side_effect=AssertionError("claim retry uploaded"))
    submit = MagicMock(side_effect=AssertionError("claim retry submitted"))
    monkeypatch.setattr(api, "_native_upload", upload)
    monkeypatch.setattr(api, "_submit_native_job", submit)

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(str(image), "prompt", str(tmp_path / "out.mp4"))

    assert pending.value.reason == "submit_outcome_unknown"
    assert pending.value.provider_status == "submission_claimed"
    assert pending.value.duration_s == 6
    upload.assert_not_called()
    submit.assert_not_called()


def test_known_job_id_recovers_claim_left_by_accepted_state_write_failure(
    monkeypatch,
    tmp_path,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    output = tmp_path / "out.mp4"
    monkeypatch.setattr(api, "_native_upload", lambda _path: "ltx://uploads/input-1")
    monkeypatch.setattr(
        api,
        "_submit_native_job",
        lambda _payload: ("job-known-after-post", "2026-08-04T00:00:00Z"),
    )
    real_write = LTXVideoAPI._write_job_state.__func__

    def fail_accepted_state_write(cls, path, state):
        if state.get("status") == "submitted":
            raise OSError("accepted state disk write failed")
        return real_write(cls, path, state)

    monkeypatch.setattr(
        LTXVideoAPI,
        "_write_job_state",
        classmethod(fail_accepted_state_write),
    )

    with pytest.raises(LTXJobPending) as deferred:
        api.generate_video(str(image), "prompt", str(output), duration=8)

    assert deferred.value.reason == "accepted_job_local_error"
    assert deferred.value.job_id == "job-known-after-post"
    assert deferred.value.duration_s == 8
    fingerprint = deferred.value.request_fingerprint
    state_path = Path(deferred.value.state_path)
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == (
        "submission_claimed"
    )

    monkeypatch.setattr(
        LTXVideoAPI,
        "_write_job_state",
        classmethod(real_write),
    )
    upload = MagicMock(side_effect=AssertionError("known job recovery uploaded"))
    submit = MagicMock(side_effect=AssertionError("known job recovery submitted"))
    monkeypatch.setattr(api, "_native_upload", upload)
    monkeypatch.setattr(api, "_submit_native_job", submit)
    monkeypatch.setattr(
        api,
        "_poll_native_job",
        lambda job_id, *_args: {
            "id": job_id,
            "status": "completed",
            "result": {"video_url": "https://cdn.example.test/output.mp4"},
        },
    )
    _successful_download(monkeypatch)

    assert api.generate_video(
        str(image),
        "prompt",
        str(output),
        duration=8,
        expected_job_id="job-known-after-post",
        expected_request_fingerprint=fingerprint,
    ) == str(output)
    assert api.last_job_id == "job-known-after-post"
    upload.assert_not_called()
    submit.assert_not_called()


def test_pending_job_is_resumed_without_upload_or_resubmit(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    _install_native_http(
        monkeypatch,
        poll_payloads=[{"id": "job-123", "status": "processing"}],
    )
    monkeypatch.setattr(LTXVideoAPI, "NATIVE_MAX_POLLS", 1)
    _successful_download(monkeypatch)

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(str(image), "prompt", str(tmp_path / "first.mp4"))
    assert pending.value.reason == "poll_window_exhausted"
    assert pending.value.status == "pending"
    assert pending.value.job_id == "job-123"

    post = MagicMock(side_effect=AssertionError("resume submitted a new job"))
    put = MagicMock(side_effect=AssertionError("resume uploaded input again"))
    get = MagicMock(
        return_value=FakeResponse(
            200,
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            },
        )
    )
    monkeypatch.setattr(ltx_native.requests, "post", post)
    monkeypatch.setattr(ltx_native.requests, "put", put)
    monkeypatch.setattr(ltx_native.requests, "get", get)

    second_output = tmp_path / "second.mp4"
    assert api.generate_video(
        str(image), "prompt", str(second_output)
    ) == str(second_output)
    post.assert_not_called()
    put.assert_not_called()
    assert get.call_args.args[0].endswith("/v2/image-to-video/job-123")


def test_changed_request_does_not_resume_prior_job(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    first_calls = _install_native_http(
        monkeypatch,
        poll_payloads=[{"id": "job-123", "status": "processing"}],
    )
    monkeypatch.setattr(LTXVideoAPI, "NATIVE_MAX_POLLS", 1)
    _successful_download(monkeypatch)
    with pytest.raises(LTXJobPending):
        api.generate_video(str(image), "first prompt", str(tmp_path / "one.mp4"))
    assert len(first_calls["post"]) == 2

    second_calls = _install_native_http(
        monkeypatch,
        poll_payloads=[
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            }
        ],
    )
    api.generate_video(str(image), "different prompt", str(tmp_path / "two.mp4"))
    assert len(second_calls["post"]) == 2
    assert len(list(tmp_path.glob(".ltx-image-to-video-*.job.json"))) == 2


def test_expected_fingerprint_mismatch_blocks_before_upload_or_submit(
    monkeypatch,
    tmp_path,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    upload = MagicMock(side_effect=AssertionError("changed request uploaded"))
    submit = MagicMock(side_effect=AssertionError("changed request submitted"))
    monkeypatch.setattr(api, "_native_upload", upload)
    monkeypatch.setattr(api, "_submit_native_job", submit)

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(
            str(image),
            "current prompt",
            str(tmp_path / "out.mp4"),
            duration=10,
            expected_job_id="job-original",
            expected_request_fingerprint="f" * 64,
        )

    assert pending.value.reason == "request_changed"
    assert pending.value.status == "recovery_required"
    assert pending.value.job_id == "job-original"
    assert pending.value.request_fingerprint == "f" * 64
    assert pending.value.duration_s == 10
    assert api.last_duration_s == 10
    upload.assert_not_called()
    submit.assert_not_called()


def test_expected_binding_requires_existing_state_before_upload(
    monkeypatch,
    tmp_path,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    request = {
        "prompt": "prompt",
        "model": "ltx-2-3-pro",
        "duration": 6,
        "resolution": "1920x1080",
        "generate_audio": False,
    }
    fingerprint = api._request_fingerprint(str(image), request)
    upload = MagicMock(side_effect=AssertionError("missing state uploaded"))
    monkeypatch.setattr(api, "_native_upload", upload)

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(
            str(image),
            "prompt",
            str(tmp_path / "out.mp4"),
            expected_job_id="job-123",
            expected_request_fingerprint=fingerprint,
        )

    assert pending.value.reason == "job_state_missing"
    assert pending.value.job_id == "job-123"
    assert pending.value.duration_s == 6
    upload.assert_not_called()


def test_expected_job_id_mismatch_blocks_poll_and_submit(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    request = {
        "prompt": "prompt",
        "model": "ltx-2-3-pro",
        "duration": 6,
        "resolution": "1920x1080",
        "generate_audio": False,
    }
    fingerprint = api._request_fingerprint(str(image), request)
    state_path = api._job_state_path(str(tmp_path / "out.mp4"), fingerprint)
    api._write_job_state(
        state_path,
        {
            "schema_version": api.JOB_STATE_SCHEMA_VERSION,
            "provider": "ltx",
            "endpoint": "image-to-video",
            "job_id": "job-actual",
            "request_fingerprint": fingerprint,
            "duration_s": 6,
            "status": "processing",
        },
    )
    upload = MagicMock(side_effect=AssertionError("job mismatch uploaded"))
    poll = MagicMock(side_effect=AssertionError("job mismatch polled"))
    monkeypatch.setattr(api, "_native_upload", upload)
    monkeypatch.setattr(api, "_poll_native_job", poll)

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(
            str(image),
            "prompt",
            str(tmp_path / "out.mp4"),
            expected_job_id="job-expected",
            expected_request_fingerprint=fingerprint,
        )

    assert pending.value.reason == "job_id_mismatch"
    assert pending.value.job_id == "job-expected"
    assert pending.value.duration_s == 6
    upload.assert_not_called()
    poll.assert_not_called()


def test_exact_expected_binding_resumes_and_surfaces_job_metadata(
    monkeypatch,
    tmp_path,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    output = tmp_path / "out.mp4"
    request = {
        "prompt": "prompt",
        "model": "ltx-2-3-pro",
        "duration": 8,
        "resolution": "1920x1080",
        "generate_audio": False,
    }
    fingerprint = api._request_fingerprint(str(image), request)
    state_path = api._job_state_path(str(output), fingerprint)
    api._write_job_state(
        state_path,
        {
            "schema_version": api.JOB_STATE_SCHEMA_VERSION,
            "provider": "ltx",
            "endpoint": "image-to-video",
            "job_id": "job-resume",
            "request_fingerprint": fingerprint,
            "duration_s": 8,
            "status": "processing",
        },
    )
    monkeypatch.setattr(
        api,
        "_native_upload",
        MagicMock(side_effect=AssertionError("exact resume uploaded")),
    )
    monkeypatch.setattr(
        api,
        "_submit_native_job",
        MagicMock(side_effect=AssertionError("exact resume submitted")),
    )
    monkeypatch.setattr(
        api,
        "_poll_native_job",
        lambda *_args: {
            "status": "completed",
            "result": {"video_url": "https://cdn.example.test/output.mp4"},
        },
    )
    _successful_download(monkeypatch)

    assert api.generate_video(
        str(image),
        "prompt",
        str(output),
        duration=8,
        expected_job_id="job-resume",
        expected_request_fingerprint=fingerprint,
    ) == str(output)
    assert api.last_job_id == "job-resume"
    assert api.last_request_fingerprint == fingerprint
    assert api.last_duration_s == 8


def test_polling_is_bounded_and_retains_processing_state(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    calls = _install_native_http(
        monkeypatch,
        poll_payloads=[
            {"id": "job-123", "status": "pending"},
            {"id": "job-123", "status": "processing"},
            {"id": "job-123", "status": "processing"},
        ],
    )
    monkeypatch.setattr(LTXVideoAPI, "NATIVE_MAX_POLLS", 3)
    monkeypatch.setattr(LTXVideoAPI, "NATIVE_POLL_INTERVAL_S", 5)
    sleep = MagicMock()
    monkeypatch.setattr(ltx_native.time, "sleep", sleep)

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(str(image), "prompt", str(tmp_path / "out.mp4"))
    assert pending.value.reason == "poll_window_exhausted"
    assert pending.value.provider_status == "processing"
    assert len(calls["get"]) == 3
    assert sleep.call_count == 2
    state_file = next(tmp_path.glob(".ltx-image-to-video-*.job.json"))
    assert json.loads(state_file.read_text())["status"] == "processing"


def test_accepted_job_poll_protocol_error_requires_recovery_not_fal(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx", fal_key="fal")
    image = _write_image(tmp_path)
    _install_native_http(monkeypatch)
    monkeypatch.setattr(
        ltx_native.requests,
        "get",
        lambda *a, **k: FakeResponse(
            200,
            {"id": "job-123", "status": "provider-added-unknown-state"},
        ),
    )
    fal = MagicMock()
    monkeypatch.setattr(api, "_fal_generate", fal)

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(str(image), "prompt", str(tmp_path / "out.mp4"))

    assert pending.value.reason == "accepted_job_error"
    assert pending.value.status == "recovery_required"
    assert pending.value.job_id == "job-123"
    assert pending.value.provider_status == "submitted"
    fal.assert_not_called()


@pytest.mark.parametrize(
    "transient",
    [
        requests.ConnectionError("connection reset"),
        FakeResponse(503, {"error": {"message": "busy"}}),
    ],
    ids=["network", "http-503"],
)
def test_transient_poll_failure_retries_same_persisted_job(
    monkeypatch,
    tmp_path,
    transient,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    calls = _install_native_http(
        monkeypatch,
        poll_payloads=[
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            }
        ],
    )
    poll_events = iter(
        [
            transient,
            FakeResponse(
                200,
                {
                    "id": "job-123",
                    "status": "completed",
                    "result": {"video_url": "https://cdn.example.test/output.mp4"},
                },
            ),
        ]
    )

    def get(url, **kwargs):
        calls["get"].append((url, kwargs))
        event = next(poll_events)
        if isinstance(event, BaseException):
            raise event
        return event

    monkeypatch.setattr(ltx_native.requests, "get", get)
    monkeypatch.setattr(LTXVideoAPI, "NATIVE_MAX_POLLS", 2)
    sleep = MagicMock()
    monkeypatch.setattr(ltx_native.time, "sleep", sleep)
    _successful_download(monkeypatch)

    assert api.generate_video(
        str(image), "prompt", str(tmp_path / "out.mp4")
    ) == str(tmp_path / "out.mp4")
    assert len(calls["post"]) == 2
    assert len(calls["get"]) == 2
    sleep.assert_called_once()


def test_ambiguous_poll_404_preserves_and_retries_accepted_job(
    monkeypatch,
    tmp_path,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    calls = _install_native_http(
        monkeypatch,
        poll_payloads=[
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            },
        ],
    )
    poll_events = iter(
        [
            FakeResponse(404),
            FakeResponse(
                200,
                {
                    "id": "job-123",
                    "status": "completed",
                    "result": {"video_url": "https://cdn.example.test/output.mp4"},
                },
            ),
        ]
    )

    def get(url, **kwargs):
        calls["get"].append((url, kwargs))
        return next(poll_events)

    monkeypatch.setattr(ltx_native.requests, "get", get)
    monkeypatch.setattr(LTXVideoAPI, "NATIVE_MAX_POLLS", 2)
    sleep = MagicMock()
    monkeypatch.setattr(ltx_native.time, "sleep", sleep)
    _successful_download(monkeypatch)

    output = tmp_path / "out.mp4"
    assert api.generate_video(str(image), "prompt", str(output)) == str(output)
    assert len(calls["post"]) == 2
    assert len(calls["get"]) == 2
    sleep.assert_called_once()
    state_path = next(tmp_path.glob(".ltx-image-to-video-*.job.json"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["job_id"] == "job-123"
    assert state["status"] == "completed"


def test_terminal_failed_job_does_not_fallback_to_fal(monkeypatch, tmp_path):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx", fal_key="fal")
    image = _write_image(tmp_path)
    _install_native_http(
        monkeypatch,
        poll_payloads=[
            {
                "id": "job-123",
                "status": "failed",
                "error": {"type": "content_filtered_error", "message": "blocked"},
            }
        ],
    )
    fal = MagicMock()
    monkeypatch.setattr(api, "_fal_generate", fal)

    assert api.generate_video(
        str(image), "prompt", str(tmp_path / "out.mp4")
    ) is None
    fal.assert_not_called()
    state_file = next(tmp_path.glob(".ltx-image-to-video-*.job.json"))
    state = json.loads(state_file.read_text())
    assert state["status"] == "failed"
    assert state["error"]["type"] == "content_filtered_error"


def test_ambiguous_submit_failure_never_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx", fal_key="fal")
    image = _write_image(tmp_path)
    post_responses = iter(
        [
            FakeResponse(
                200,
                {
                    "upload_url": "https://uploads.example.test/signed",
                    "storage_uri": "ltx://uploads/input-1",
                    "required_headers": {},
                },
            ),
            requests.ConnectionError("response lost after POST"),
        ]
    )

    def post(*args, **kwargs):
        response = next(post_responses)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(ltx_native.requests, "post", post)
    monkeypatch.setattr(ltx_native.requests, "put", lambda *a, **k: FakeResponse(200))
    fal = MagicMock()
    monkeypatch.setattr(api, "_fal_generate", fal)

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(str(image), "prompt", str(tmp_path / "out.mp4"))
    assert pending.value.reason == "submit_outcome_unknown"
    assert pending.value.status == "recovery_required"
    assert pending.value.job_id is None
    fal.assert_not_called()
    marker = next(tmp_path.glob(".ltx-image-to-video-*.job.json"))
    assert json.loads(marker.read_text(encoding="utf-8"))["status"] == (
        "submission_unknown"
    )

    post_again = MagicMock(side_effect=AssertionError("ambiguous submit repeated"))
    monkeypatch.setattr(ltx_native.requests, "post", post_again)
    with pytest.raises(LTXJobPending) as resumed:
        api.generate_video(str(image), "prompt", str(tmp_path / "out.mp4"))
    assert resumed.value.reason == "submit_outcome_unknown"
    post_again.assert_not_called()


def test_invalid_submitted_job_id_blocks_resubmit_and_is_not_polled(
    monkeypatch,
    tmp_path,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    responses = iter(
        [
            FakeResponse(
                200,
                {
                    "upload_url": "https://uploads.example.test/signed",
                    "storage_uri": "ltx://uploads/input-1",
                    "required_headers": {},
                },
            ),
            FakeResponse(202, {"id": "../other-endpoint", "created_at": "now"}),
        ]
    )
    monkeypatch.setattr(ltx_native.requests, "post", lambda *a, **k: next(responses))
    monkeypatch.setattr(ltx_native.requests, "put", lambda *a, **k: FakeResponse(200))
    get = MagicMock()
    monkeypatch.setattr(ltx_native.requests, "get", get)

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(str(image), "prompt", str(tmp_path / "out.mp4"))
    assert pending.value.reason == "submit_outcome_unknown"
    get.assert_not_called()
    state_files = list(tmp_path.glob(".ltx-image-to-video-*.job.json"))
    assert len(state_files) == 1
    state = json.loads(state_files[0].read_text(encoding="utf-8"))
    assert state["status"] == "submission_unknown"
    assert "job_id" not in state


def test_unreadable_job_sidecar_blocks_duplicate_submit(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    request = {
        "prompt": "prompt",
        "model": "ltx-2-3-pro",
        "duration": 6,
        "resolution": "1920x1080",
        "generate_audio": False,
    }
    fingerprint = api._request_fingerprint(str(image), request)
    state_path = Path(api._job_state_path(str(tmp_path / "out.mp4"), fingerprint))
    state_path.write_text("{not-json", encoding="utf-8")
    post = MagicMock(side_effect=AssertionError("corrupt recovery state resubmitted"))
    monkeypatch.setattr(ltx_native.requests, "post", post)

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(str(image), "prompt", str(tmp_path / "out.mp4"))

    assert pending.value.reason == "job_state_unreadable"
    assert pending.value.status == "recovery_required"
    assert pending.value.state_path == str(state_path)
    post.assert_not_called()


def test_pre_submission_upload_failure_can_use_configured_fal(monkeypatch, tmp_path):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx", fal_key="fal")
    image = _write_image(tmp_path)
    monkeypatch.setattr(
        ltx_native.requests,
        "post",
        MagicMock(side_effect=requests.ConnectionError("upload ticket unavailable")),
    )
    fal = MagicMock(return_value=str(tmp_path / "out.mp4"))
    monkeypatch.setattr(api, "_fal_generate", fal)

    assert api.generate_video(
        str(image), "prompt", str(tmp_path / "out.mp4")
    ) == str(tmp_path / "out.mp4")
    fal.assert_called_once()


@pytest.mark.parametrize(
    "bad_bytes",
    [b"", b"GIF89a", b"not-an-image"],
)
def test_invalid_input_image_fails_locally_without_network_or_fal(
    monkeypatch,
    tmp_path,
    bad_bytes,
):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx", fal_key="fal")
    image = _write_image(tmp_path, bad_bytes)
    post = MagicMock()
    fal = MagicMock()
    monkeypatch.setattr(ltx_native.requests, "post", post)
    monkeypatch.setattr(api, "_fal_generate", fal)

    assert api.generate_video(
        str(image), "prompt", str(tmp_path / "out.mp4")
    ) is None
    post.assert_not_called()
    fal.assert_not_called()


def test_oversized_input_fails_before_network(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path, PNG_BYTES)
    monkeypatch.setattr(LTXVideoAPI, "INPUT_IMAGE_MAX_BYTES", 1)
    post = MagicMock()
    monkeypatch.setattr(ltx_native.requests, "post", post)

    assert api.generate_video(
        str(image), "prompt", str(tmp_path / "out.mp4")
    ) is None
    post.assert_not_called()


def test_completed_output_bills_before_download(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    _install_native_http(
        monkeypatch,
        poll_payloads=[
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            }
        ],
    )
    events: list[str] = []
    _successful_download(monkeypatch, events)

    assert api.generate_video(
        str(image),
        "prompt",
        str(tmp_path / "out.mp4"),
        on_billed=lambda: events.append("billed"),
    ) == str(tmp_path / "out.mp4")
    assert events == ["billed", "download"]


def test_download_failure_still_bills_and_preserves_existing_output(
    monkeypatch,
    tmp_path,
):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    output = tmp_path / "out.mp4"
    output.write_bytes(MP4_BYTES)
    _install_native_http(
        monkeypatch,
        poll_payloads=[
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            }
        ],
    )
    billed = MagicMock()
    monkeypatch.setattr(ltx_native, "safe_download", MagicMock(return_value=None))

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(str(image), "prompt", str(output), on_billed=billed)
    assert pending.value.reason == "completed_output_invalid"
    assert pending.value.provider_status == "completed"
    billed.assert_called_once()
    assert output.read_bytes() == MP4_BYTES


def test_billing_callback_exception_does_not_abort_publication(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    _install_native_http(
        monkeypatch,
        poll_payloads=[
            {
                "id": "job-123",
                "status": "completed",
                "result": {"video_url": "https://cdn.example.test/output.mp4"},
            }
        ],
    )
    _successful_download(monkeypatch)

    def broken_callback():
        raise RuntimeError("accounting hook failed")

    assert api.generate_video(
        str(image),
        "prompt",
        str(tmp_path / "out.mp4"),
        on_billed=broken_callback,
    ) == str(tmp_path / "out.mp4")


def test_completed_job_without_video_url_fails_without_billing(monkeypatch, tmp_path):
    api = _make_api(ltx_key="ltx")
    image = _write_image(tmp_path)
    _install_native_http(
        monkeypatch,
        poll_payloads=[
            {"id": "job-123", "status": "completed", "result": {}},
        ],
    )
    billed = MagicMock()

    with pytest.raises(LTXJobPending) as pending:
        api.generate_video(
            str(image),
            "prompt",
            str(tmp_path / "out.mp4"),
            on_billed=billed,
        )
    assert pending.value.reason == "completed_output_missing"
    assert pending.value.provider_status == "completed"
    billed.assert_not_called()


def test_download_requests_strict_mp4_mime_and_container_validation(monkeypatch):
    captured = {}

    def download(url, destination, **kwargs):
        captured.update(kwargs)
        return destination

    monkeypatch.setattr(ltx_native, "safe_download", download)

    assert LTXVideoAPI._download_video(
        "https://cdn.example.test/output.mp4", "out.mp4"
    ) == "out.mp4"
    assert captured["allowed_content_types"] == ("video/mp4",)
    assert captured["content_validator"] == ltx_native.validate_video_artifact


def test_fal_payload_and_validated_download(monkeypatch, tmp_path):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(fal_key="fal")
    image = _write_image(tmp_path)
    monkeypatch.setattr(
        ltx_native.fal_client,
        "upload_file",
        MagicMock(return_value="https://fal.example.test/input.png"),
    )
    subscribe = MagicMock(
        return_value={"video": {"url": "https://fal.example.test/output.mp4"}}
    )
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe)
    download = MagicMock(return_value=str(tmp_path / "out.mp4"))
    monkeypatch.setattr(api, "_download_video", download)

    assert api.generate_video(
        str(image),
        "prompt",
        str(tmp_path / "out.mp4"),
        duration=8,
        resolution="720p",
        camera_motion="dolly_in",
    ) == str(tmp_path / "out.mp4")

    arguments = subscribe.call_args.kwargs["arguments"]
    assert subscribe.call_args.args[0] == "fal-ai/ltx-2.3/image-to-video"
    assert arguments == {
        "prompt": "prompt. Camera: dolly in.",
        "image_url": "https://fal.example.test/input.png",
        "duration": 8,
        "resolution": "1080p",
        "generate_audio": False,
    }
    assert "width" not in arguments
    assert "height" not in arguments
    assert "num_frames" not in arguments
    download.assert_called_once_with(
        "https://fal.example.test/output.mp4",
        str(tmp_path / "out.mp4"),
    )


def test_fal_no_video_url_is_prebilling_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(fal_key="fal")
    image = _write_image(tmp_path)
    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "url")
    monkeypatch.setattr(
        ltx_native.fal_client,
        "subscribe",
        MagicMock(return_value={"video": {}}),
    )
    billed = MagicMock()

    assert api.generate_video(
        str(image),
        "prompt",
        str(tmp_path / "out.mp4"),
        on_billed=billed,
    ) is None
    billed.assert_not_called()


def test_fal_download_failure_still_bills(monkeypatch, tmp_path):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(fal_key="fal")
    image = _write_image(tmp_path)
    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "url")
    monkeypatch.setattr(
        ltx_native.fal_client,
        "subscribe",
        MagicMock(return_value={"video": {"url": "https://cdn/output.mp4"}}),
    )
    monkeypatch.setattr(api, "_download_video", MagicMock(return_value=None))
    billed = MagicMock()

    assert api.generate_video(
        str(image),
        "prompt",
        str(tmp_path / "out.mp4"),
        on_billed=billed,
    ) is None
    billed.assert_called_once()


def test_job_state_write_is_atomic_and_leaves_no_temp(monkeypatch, tmp_path):
    state_path = tmp_path / ".ltx-job.json"
    state_path.write_text('{"old":true}\n')
    real_replace = ltx_native.os.replace
    observations = []

    def observing_replace(source, destination):
        observations.append(
            (Path(source).read_text(), Path(destination).read_text())
        )
        real_replace(source, destination)

    monkeypatch.setattr(ltx_native.os, "replace", observing_replace)
    LTXVideoAPI._write_job_state(
        str(state_path),
        {
            "schema_version": 1,
            "job_id": "job-123",
            "status": "submitted",
        },
    )

    assert observations[0][1] == '{"old":true}\n'
    assert json.loads(state_path.read_text())["job_id"] == "job-123"
    assert list(tmp_path.glob("..ltx-job.json.*.tmp")) == []
