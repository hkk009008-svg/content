# tests/unit/test_kling_native.py
"""Characterization tests for kling_native.KlingNativeAPI (offline, mocked HTTP).

CONTRACT PINNED: Kling's image-to-video is KEYFRAME-DRIVEN.
The output aspect ratio comes from the input keyframe's dimensions, NOT from
any API parameter.  Unlike Veo/Sora/Runway, Kling's HTTP payload has NO
aspect/ratio/size/resolution key.  These tests lock that contract so a future
contributor who tries to "add a Kling aspect param" gets a failing test
reminding them that the mechanism is the keyframe + T7's backstop.

All tests are fully offline — no real network, no GPU.
"""
from __future__ import annotations

import sys

# test_f2b_storyboard_mode.py (and others) may inject a lightweight stub for
# 'kling_native' into sys.modules that lacks the real KlingNativeAPI
# implementation.  Remove it so our import always gets the real module.
sys.modules.pop("kling_native", None)

import dataclasses
import os
from unittest.mock import MagicMock, call, patch

import pytest

import kling_native
from kling_native import KlingNativeAPI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A ≥32-byte HS256 secret keeps jwt.encode from emitting InsecureKeyLengthWarning
# (the real keys are long; the short "sk-test" dummy tripped the warning on 5 tests).
_TEST_SECRET = "sk-test" + "x" * 25  # 32 chars


def _patched_settings(access_key: str = "ak-test", secret_key: str = _TEST_SECRET):
    """Return a settings replacement with Kling credentials set.

    settings is a frozen dataclass singleton — we must replace the whole
    module-level name rather than mutating individual attributes.
    `dataclasses.replace` clones it with overridden fields.
    """
    return dataclasses.replace(
        kling_native.settings,
        kling_access_key=access_key,
        kling_secret_key=secret_key,
    )


def _make_api(access_key: str = "ak-test", secret_key: str = _TEST_SECRET) -> KlingNativeAPI:
    """Construct a KlingNativeAPI with patched settings.

    TC-7 pattern B: patch the module-level 'settings' BEFORE __init__ runs,
    because __init__:33-43 reads settings.kling_access_key / .kling_secret_key
    and calls _generate_token() (jwt.encode) during construction.
    """
    with patch.object(kling_native, "settings", _patched_settings(access_key, secret_key)):
        api = KlingNativeAPI()
    return api


def _real_png(tmp_path) -> str:
    """Write a minimal real PNG so open(image_path,'rb') succeeds."""
    p = tmp_path / "keyframe.png"
    # Minimal 1×1 PNG bytes (valid PNG header + IDAT)
    import base64
    _TINY_PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    p.write_bytes(_TINY_PNG)
    return str(p)


def _ok_post_response() -> MagicMock:
    """Return a mock requests.Response for a successful create_image_to_video call."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"code": 0, "data": {"task_id": "task-t1"}}
    return resp


# ---------------------------------------------------------------------------
# __init__ — raises ValueError on missing credentials
# ---------------------------------------------------------------------------

def test_init_raises_on_missing_credentials():
    """KlingNativeAPI raises ValueError when either key is empty."""
    with (
        patch.object(kling_native, "settings", _patched_settings(access_key="")),
        pytest.raises(ValueError, match="KLING_ACCESS_KEY"),
    ):
        KlingNativeAPI()


def test_init_raises_on_missing_secret():
    """KlingNativeAPI raises ValueError when secret_key is empty."""
    with (
        patch.object(kling_native, "settings", _patched_settings(secret_key="")),
        pytest.raises(ValueError, match="KLING_SECRET_KEY"),
    ):
        KlingNativeAPI()


def test_init_succeeds_with_valid_keys():
    """Happy-path construction does not raise and sets access_key/secret_key."""
    api = _make_api()
    assert api.access_key == "ak-test"
    assert api.secret_key == _TEST_SECRET
    assert api._token is not None  # _generate_token() was called


# ---------------------------------------------------------------------------
# PRIMARY CONTRACT: create_image_to_video sends NO aspect/ratio/size key
# ---------------------------------------------------------------------------

def test_no_aspect_key_in_i2v_payload(tmp_path):
    """CONTRACT: Kling i2v HTTP body contains no aspect/ratio/size/resolution key.

    This is the core portrait-safety contract: Kling determines output aspect
    from the keyframe dimensions, not from an API parameter.  Phase-3 portrait
    relies on T7's backstop (keyframe is already 9:16) — no parameter wiring
    is needed or correct.

    If this test fails after a code change, that change attempted to add an
    aspect/size/resolution key to the Kling i2v payload.  Review whether Kling's
    API actually supports it before proceeding; as of 2026-06-08, it does not.
    """
    ASPECT_KEYS = {"aspect_ratio", "ratio", "size", "resolution", "aspect"}

    api = _make_api()
    img_path = _real_png(tmp_path)

    with patch.object(kling_native, "requests") as mock_requests:
        mock_requests.post.return_value = _ok_post_response()

        task_id = api.create_image_to_video(
            image_path=img_path,
            prompt="a person walks forward",
        )

    assert task_id == "task-t1"

    # Grab the JSON body sent to requests.post (prod always passes it as a kwarg)
    body = mock_requests.post.call_args.kwargs["json"]

    # The body must be non-empty (sanity: proves the assertion below is non-vacuous)
    assert body, f"Expected a non-empty JSON body; got: {body!r}"

    # The expected keys ARE present in the body
    for expected_key in ("model_name", "image", "prompt", "duration", "mode", "cfg_scale"):
        assert expected_key in body, (
            f"Expected key {expected_key!r} missing from Kling i2v body: {set(body)}"
        )

    # CONTRACT: none of the aspect/ratio/size keys are present
    present_aspect_keys = ASPECT_KEYS & set(body)
    assert not present_aspect_keys, (
        f"Kling i2v payload MUST NOT contain aspect/ratio/size keys "
        f"(keyframe dimensions drive output aspect; T7 backstop ensures portrait keyframe is 9:16). "
        f"Found unexpected keys: {present_aspect_keys!r}. "
        f"Full body keys: {set(body)!r}"
    )


def test_i2v_payload_with_optional_params_still_no_aspect_key(tmp_path):
    """CONTRACT holds even when optional params (face_consistency, image_references) are passed.

    Verifies no aspect key is introduced through optional code paths.
    """
    ASPECT_KEYS = {"aspect_ratio", "ratio", "size", "resolution", "aspect"}

    api = _make_api()
    img_path = _real_png(tmp_path)
    # Create a subdirectory so _real_png can write into it
    ref_dir = tmp_path / "ref"
    ref_dir.mkdir()
    ref_path = _real_png(ref_dir)

    with patch.object(kling_native, "requests") as mock_requests:
        mock_requests.post.return_value = _ok_post_response()

        task_id = api.create_image_to_video(
            image_path=img_path,
            prompt="character smiles",
            face_consistency=True,
            image_references=[ref_path],
        )

    assert task_id == "task-t1"
    body = mock_requests.post.call_args.kwargs["json"]

    # face_consistency and image_reference may be present — that's fine
    assert body.get("face_consistency") is True
    assert "image_reference" in body

    # CONTRACT still holds
    present_aspect_keys = ASPECT_KEYS & set(body)
    assert not present_aspect_keys, (
        f"Optional params must not introduce aspect/ratio/size keys. "
        f"Found: {present_aspect_keys!r}"
    )


# ---------------------------------------------------------------------------
# missing image raises FileNotFoundError
# ---------------------------------------------------------------------------

def test_missing_image_raises(tmp_path):
    """create_image_to_video raises FileNotFoundError when image_path doesn't exist."""
    api = _make_api()
    with pytest.raises(FileNotFoundError, match="Source image not found"):
        api.create_image_to_video(
            image_path=str(tmp_path / "nonexistent.png"),
            prompt="test",
        )


# ---------------------------------------------------------------------------
# DELEGATION: generate_video routes through create_image_to_video
# ---------------------------------------------------------------------------

def test_generate_video_delegates_to_create_image_to_video(tmp_path):
    """generate_video calls create_image_to_video (which builds the no-aspect payload).

    This pins the cascade: phase_c_ffmpeg.py → generate_video → create_image_to_video.
    The no-aspect-key contract applies to ALL Kling video generation because it
    flows through create_image_to_video.
    """
    api = _make_api()
    img_path = _real_png(tmp_path)
    out_path = str(tmp_path / "out.mp4")

    # Patch create_image_to_video, poll_task, download_video to keep this lightweight
    with (
        patch.object(api, "create_image_to_video", return_value="task-del-1") as mock_create,
        patch.object(api, "poll_task", return_value={
            "task_result": {"videos": [{"url": "https://example.com/video.mp4"}]}
        }),
        patch.object(api, "download_video", return_value=out_path),
    ):
        result = api.generate_video(
            image_path=img_path,
            prompt="delegation test",
            output_path=out_path,
        )

    assert result == out_path
    mock_create.assert_called_once()
    # Confirm image_path and prompt were forwarded correctly
    create_args = mock_create.call_args
    assert create_args.args[0] == img_path or create_args.kwargs.get("image_path") == img_path
    assert "delegation test" in (create_args.args[1:] + tuple(create_args.kwargs.values()))


def test_generate_video_default_poll_timeout_is_300s(tmp_path):
    """generate_video defaults the poll timeout to 300s.

    Kling image-to-video jobs run ~178-195s; the prior 180s default timed out
    flakily on the slow tail (T9 portrait preflight run-2 hit a KLING timeout at
    180s after taking 178s on run-1). 300s gives operational headroom while still
    bounding a genuinely-stuck job. Callers may still override via timeout=...
    """
    api = _make_api()
    img_path = _real_png(tmp_path)
    out_path = str(tmp_path / "out.mp4")

    with (
        patch.object(api, "create_image_to_video", return_value="task-timeout-1"),
        patch.object(api, "poll_task", return_value={
            "task_result": {"videos": [{"url": "https://example.com/video.mp4"}]}
        }) as mock_poll,
        patch.object(api, "download_video", return_value=out_path),
    ):
        api.generate_video(
            image_path=img_path,
            prompt="timeout default test",
            output_path=out_path,
        )

    # No explicit timeout kwarg → the default must be 300s.
    assert mock_poll.call_args.kwargs.get("timeout") == 300, (
        f"Expected default poll timeout 300s; got {mock_poll.call_args.kwargs.get('timeout')}"
    )


def test_generate_video_timeout_override_reaches_poll_task(tmp_path):
    """An explicit timeout= override must reach poll_task — not strand in **kwargs.

    create_image_to_video has a fixed signature (no **kwargs, no timeout param), so
    generate_video must pop timeout from kwargs BEFORE calling
    create_image_to_video(**kwargs). Otherwise a timeout= override lands in that call,
    raises TypeError, is swallowed by the bare except, and generate_video silently
    returns None — the opposite of an honored override.

    autospec=True makes the create_image_to_video mock enforce the real signature so
    this test actually exercises the bug (a plain MagicMock accepts any kwarg and
    would hide it).
    """
    api = _make_api()
    img_path = _real_png(tmp_path)
    out_path = str(tmp_path / "out.mp4")

    with (
        patch.object(api, "create_image_to_video", autospec=True, return_value="task-override-1"),
        patch.object(api, "poll_task", return_value={
            "task_result": {"videos": [{"url": "https://example.com/video.mp4"}]}
        }) as mock_poll,
        patch.object(api, "download_video", return_value=out_path),
    ):
        result = api.generate_video(
            image_path=img_path,
            prompt="timeout override test",
            output_path=out_path,
            timeout=600,
        )

    # The override must have reached poll_task, not stranded in create_image_to_video's kwargs.
    assert result == out_path, (
        "generate_video returned None — a timeout= override reached "
        "create_image_to_video(**kwargs) and raised TypeError (pop must precede create)"
    )
    assert mock_poll.call_args.kwargs.get("timeout") == 600, (
        f"Expected override timeout=600 to reach poll_task; got {mock_poll.call_args.kwargs.get('timeout')}"
    )


# ---------------------------------------------------------------------------
# poll_task — characterization (kling_native.py:170; backoff [3,5,8,12,15] at :190,226-229)
#
# poll_task loops: time.sleep(interval) FIRST, then requests.get(...).  So the
# number of recorded sleeps == the number of polls.  The first sleep uses
# initial_interval (default 3); thereafter `interval` is driven by
# backoff_schedule = [3, 5, 8, 12, 15], advancing the index by one each
# non-terminal poll until it pins at the last element (15) — it never exceeds
# 15.  With the default initial_interval==schedule[0]==3, the observed sleep
# sequence is 3, 5, 8, 12, 15, 15, 15, ... which matches the docstring intent at
# :175 ("3s -> 5s -> 8s -> 12s -> 15s (capped)").
#
# All HTTP and waiting is mocked: kling_native.time.sleep (record args, no real
# wait) and kling_native.requests.get (scripted {"code":0,"data":{...}} dicts).
# ---------------------------------------------------------------------------

def _poll_resp(status, *, code=0, msg=None) -> MagicMock:
    """Return a mock requests.Response for a single poll_task GET.

    Shapes the body as Kling does: {"code": <int>, "data": {"task_status": ...}}.
    raise_for_status() is a no-op (HTTP 200). When msg is given it is attached as
    task_status_msg (the failure-reason field poll_task surfaces).
    """
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    data = {"task_status": status}
    if msg is not None:
        data["task_status_msg"] = msg
    resp.json.return_value = {"code": code, "data": data}
    return resp


def test_poll_task_succeed_returns_data_dict():
    """status 'succeed' -> poll_task returns the inner `data` dict verbatim."""
    api = _make_api()
    succeed_data = {
        "task_status": "succeed",
        "task_result": {"videos": [{"url": "https://example.com/v.mp4"}]},
    }
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"code": 0, "data": succeed_data}

    with (
        patch.object(kling_native.time, "sleep") as mock_sleep,
        patch.object(kling_native.requests, "get", return_value=resp),
    ):
        result = api.poll_task("task-ok")

    assert result == succeed_data
    # The FIRST sleep uses initial_interval (default 3), before the schedule advances.
    assert mock_sleep.call_args_list[0].args[0] == 3


def test_poll_task_backoff_plateaus_at_15():
    """BACKOFF PLATEAU: intervals climb 3,5,8,12,15 then stay pinned at 15.

    Scripts several non-terminal ('processing'/'unknown') polls before 'succeed'.
    Because each loop sleeps once then polls once, the recorded sleep sequence is
    one-per-poll. It must climb through the schedule [3,5,8,12,15] and then
    PLATEAU at 15 — never exceeding 15 no matter how many extra polls occur.
    """
    # 7 non-terminal polls + 1 succeed = 8 polls = 8 recorded sleeps.
    responses = [
        _poll_resp("processing"),
        _poll_resp("processing"),
        _poll_resp("processing"),
        _poll_resp("processing"),
        _poll_resp("processing"),
        _poll_resp("unknown"),
        _poll_resp("unknown"),
        _poll_resp("succeed"),
    ]

    api = _make_api()
    with (
        patch.object(kling_native.time, "sleep") as mock_sleep,
        patch.object(kling_native.requests, "get", side_effect=responses),
    ):
        api.poll_task("task-backoff")

    intervals = [c.args[0] for c in mock_sleep.call_args_list]

    # At least the first five intervals climb exactly through the schedule.
    assert intervals[:5] == [3, 5, 8, 12, 15], (
        f"Expected backoff to climb [3,5,8,12,15]; got {intervals!r}"
    )
    # Every subsequent interval plateaus at 15 — and never exceeds it.
    assert all(i == 15 for i in intervals[5:]), (
        f"Expected intervals after the 5th to stay pinned at 15; got {intervals!r}"
    )
    assert max(intervals) == 15, f"No interval may exceed 15; got {intervals!r}"
    # Full pinned sequence for this exact script (8 polls).
    assert intervals == [3, 5, 8, 12, 15, 15, 15, 15], (
        f"Unexpected sleep sequence: {intervals!r}"
    )


def test_poll_task_failed_raises_runtimeerror_with_reason():
    """status 'failed' -> RuntimeError whose message includes task_status_msg."""
    api = _make_api()
    failed = _poll_resp("failed", msg="content moderation block")

    with (
        patch.object(kling_native.time, "sleep"),
        patch.object(kling_native.requests, "get", return_value=failed),
        pytest.raises(RuntimeError, match="content moderation block"),
    ):
        api.poll_task("task-fail")


def test_poll_task_nonzero_result_code_raises_runtimeerror():
    """result code != 0 -> RuntimeError (message carries the offending code)."""
    api = _make_api()
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"code": 1207, "message": "task not found"}

    with (
        patch.object(kling_native.time, "sleep"),
        patch.object(kling_native.requests, "get", return_value=resp),
        pytest.raises(RuntimeError, match="1207"),
    ):
        api.poll_task("task-bad-code")


def test_poll_task_never_completes_raises_timeouterror():
    """A status that never reaches a terminal state -> TimeoutError.

    sleep is mocked (no real wait); poll_task tracks elapsed by summing the
    intervals it 'slept', so a small timeout is reached deterministically after
    a few loops. With timeout=10 the intervals are 3 (elapsed 3) -> 5 (elapsed 8)
    -> 8 (elapsed 16 >= 10), so it bails on the 3rd iteration with TimeoutError.
    """
    api = _make_api()
    stuck = _poll_resp("processing")  # returned for every call

    with (
        patch.object(kling_native.time, "sleep") as mock_sleep,
        patch.object(kling_native.requests, "get", return_value=stuck),
        pytest.raises(TimeoutError, match="timed out"),
    ):
        api.poll_task("task-stuck", timeout=10)

    # Sanity: it actually entered the poll loop (didn't bail before sleeping).
    assert mock_sleep.call_count >= 1
    # And it never slept longer than the cap while spinning.
    assert max(c.args[0] for c in mock_sleep.call_args_list) <= 15
