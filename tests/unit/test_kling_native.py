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
import types
from datetime import date
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
# generate_video — on_billed fires exactly at the provider's billed-URL
# boundary (money-gate 2026-07-11: a post-billing download failure must
# still be distinguishable from a pre-billing failure to the caller).
# ---------------------------------------------------------------------------

def test_generate_video_pre_billing_failure_does_not_call_on_billed(tmp_path):
    """No videos in the poll result => the provider never returned a video
    => never billed => on_billed must NOT fire."""
    api = _make_api()
    img_path = _real_png(tmp_path)
    out_path = str(tmp_path / "out.mp4")
    on_billed = MagicMock()

    with (
        patch.object(api, "create_image_to_video", return_value="task-no-video"),
        patch.object(api, "poll_task", return_value={"task_result": {"videos": []}}),
    ):
        result = api.generate_video(
            image_path=img_path,
            prompt="no video in result",
            output_path=out_path,
            on_billed=on_billed,
        )

    assert result is None
    on_billed.assert_not_called()


def test_generate_video_post_billing_download_failure_still_notes_billed(tmp_path):
    """RED->GREEN target: a download failure AFTER the provider returned a
    video URL must still fire on_billed. Pre-fix, download_video's failure
    fell into the blanket `except Exception: return None`, indistinguishable
    from a pre-billing failure and losing the spend to the caller's budget
    gate. on_billed must fire BEFORE the download attempt, not after.
    """
    api = _make_api()
    img_path = _real_png(tmp_path)
    out_path = str(tmp_path / "out.mp4")

    call_order: list[str] = []
    on_billed = MagicMock(side_effect=lambda: call_order.append("billed"))

    def _failing_download(*args, **kwargs):
        call_order.append("download")
        raise RuntimeError("simulated post-billing download failure")

    with (
        patch.object(api, "create_image_to_video", return_value="task-billed-fail"),
        patch.object(api, "poll_task", return_value={
            "task_result": {"videos": [{"url": "https://example.com/video.mp4"}]}
        }),
        patch.object(api, "download_video", side_effect=_failing_download),
    ):
        result = api.generate_video(
            image_path=img_path,
            prompt="billed then download fails",
            output_path=out_path,
            on_billed=on_billed,
        )

    assert result is None
    on_billed.assert_called_once()
    assert call_order == ["billed", "download"], (
        "on_billed must fire BEFORE the download attempt so a caller's spend "
        f"record is never lost to a post-billing download failure; got {call_order!r}"
    )


def test_generate_video_success_fires_on_billed_exactly_once(tmp_path):
    """The happy path also bills — on_billed must fire exactly once, before
    download, even when the download subsequently succeeds."""
    api = _make_api()
    img_path = _real_png(tmp_path)
    out_path = str(tmp_path / "out.mp4")
    on_billed = MagicMock()

    with (
        patch.object(api, "create_image_to_video", return_value="task-ok"),
        patch.object(api, "poll_task", return_value={
            "task_result": {"videos": [{"url": "https://example.com/video.mp4"}]}
        }),
        patch.object(api, "download_video", return_value=out_path),
    ):
        result = api.generate_video(
            image_path=img_path,
            prompt="success",
            output_path=out_path,
            on_billed=on_billed,
        )

    assert result == out_path
    on_billed.assert_called_once()


def test_generate_video_on_billed_exception_does_not_abort_download(tmp_path):
    """A broken accounting callback must never abort an otherwise-successful
    generation — the callback's own exception must be swallowed and logged,
    not allowed to propagate into the outer except and blank out a real
    video."""
    api = _make_api()
    img_path = _real_png(tmp_path)
    out_path = str(tmp_path / "out.mp4")

    def _bad_callback():
        raise RuntimeError("accounting hook bug")

    with (
        patch.object(api, "create_image_to_video", return_value="task-ok2"),
        patch.object(api, "poll_task", return_value={
            "task_result": {"videos": [{"url": "https://example.com/video.mp4"}]}
        }),
        patch.object(api, "download_video", return_value=out_path),
    ):
        result = api.generate_video(
            image_path=img_path,
            prompt="callback bug",
            output_path=out_path,
            on_billed=_bad_callback,
        )

    assert result == out_path, (
        "A broken on_billed callback must not abort an otherwise-successful download"
    )


# ---------------------------------------------------------------------------
# generate_storyboard — one canonical provider-capped duration allocation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("shot_count", "expected_durations"),
    [
        (4, [5.0, 5.0, 4.0, 1.0]),
        (6, [5.0, 5.0, 2.0, 1.0, 1.0, 1.0]),
    ],
)
def test_storyboard_payload_stays_within_provider_cap_after_minimums(
    tmp_path,
    shot_count,
    expected_durations,
):
    """The 1s floor must not push a capped allocation back above 15s.

    The former adapter first capped the requested durations, then applied the
    one-second floor. Four 5s shots therefore described a 16s provider payload;
    six described 18s. Reserve each remaining minimum during allocation so the
    final provider payload and its declared total remain coherent.
    """
    from cinema.storyboard import allocate_storyboard_durations

    api = _make_api()
    img_path = _real_png(tmp_path)
    out_path = str(tmp_path / "storyboard.mp4")
    shots = [
        {"prompt": f"shot {index}", "duration": 5.0}
        for index in range(shot_count)
    ]

    with (
        patch.object(
            kling_native.requests,
            "post",
            return_value=_ok_post_response(),
        ) as mock_post,
        patch.object(
            api,
            "poll_task",
            return_value={
                "task_result": {
                    "videos": [{"url": "https://example.com/storyboard.mp4"}],
                },
            },
        ),
        patch.object(api, "download_video", return_value=out_path),
    ):
        result = api.generate_storyboard(
            image_path=img_path,
            shots=shots,
            output_path=out_path,
        )

    body = mock_post.call_args.kwargs["json"]
    payload_durations = [
        float(item["duration"])
        for item in body["multi_prompt"]
    ]
    assert result == out_path
    assert allocate_storyboard_durations(shots) == expected_durations
    assert payload_durations == expected_durations
    assert float(body["duration"]) == sum(expected_durations)
    assert sum(payload_durations) <= 15.0
    assert min(payload_durations) >= 1.0


# ---------------------------------------------------------------------------
# generate_storyboard — on_billed mirrors generate_video's billed-URL boundary
# ---------------------------------------------------------------------------

def test_generate_storyboard_post_billing_download_failure_still_notes_billed(tmp_path):
    """A download failure AFTER the provider returned a storyboard video URL
    must still fire on_billed, mirroring generate_video's contract — a
    billed-but-failed storyboard batch must not be invisible to the
    caller's cost accounting."""
    api = _make_api()
    img_path = _real_png(tmp_path)
    out_path = str(tmp_path / "storyboard.mp4")
    shots = [
        {"prompt": "shot one", "duration": 5.0},
        {"prompt": "shot two", "duration": 5.0},
    ]

    call_order: list[str] = []
    on_billed = MagicMock(side_effect=lambda: call_order.append("billed"))

    def _failing_download(*args, **kwargs):
        call_order.append("download")
        raise RuntimeError("simulated post-billing download failure")

    with (
        patch.object(kling_native.requests, "post", return_value=_ok_post_response()),
        patch.object(api, "poll_task", return_value={
            "task_result": {"videos": [{"url": "https://example.com/storyboard.mp4"}]},
        }),
        patch.object(api, "download_video", side_effect=_failing_download),
    ):
        result = api.generate_storyboard(
            image_path=img_path,
            shots=shots,
            output_path=out_path,
            on_billed=on_billed,
        )

    assert result is None
    on_billed.assert_called_once()
    assert call_order == ["billed", "download"], (
        "on_billed must fire BEFORE the download attempt; got "
        f"{call_order!r}"
    )


def test_generate_storyboard_pre_billing_failure_does_not_call_on_billed(tmp_path):
    """No videos in the poll result => never billed => on_billed must NOT
    fire."""
    api = _make_api()
    img_path = _real_png(tmp_path)
    out_path = str(tmp_path / "storyboard.mp4")
    shots = [{"prompt": "shot one", "duration": 5.0}]
    on_billed = MagicMock()

    with (
        patch.object(kling_native.requests, "post", return_value=_ok_post_response()),
        patch.object(api, "poll_task", return_value={"task_result": {"videos": []}}),
    ):
        result = api.generate_storyboard(
            image_path=img_path,
            shots=shots,
            output_path=out_path,
            on_billed=on_billed,
        )

    assert result is None
    on_billed.assert_not_called()


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (sys.float_info.max, [14.0, 1.0]),
        (-sys.float_info.max, [1.0, 5.0]),
    ],
)
def test_storyboard_allocator_clamps_finite_extremes_before_scaling(
    requested,
    expected,
):
    """Finite extremes must clamp, not overflow during tenths conversion."""
    from cinema.storyboard import allocate_storyboard_durations

    shots = [
        {"prompt": "extreme", "duration": requested},
        {"prompt": "normal", "duration": 5.0},
    ]

    assert allocate_storyboard_durations(shots) == expected


@pytest.mark.parametrize("requested", [10**1000, -(10**1000)])
def test_storyboard_allocator_rejects_integer_outside_float_range(requested):
    """An oversized JSON integer is invalid input, not an uncaught overflow."""
    from cinema.storyboard import allocate_storyboard_durations

    with pytest.raises(ValueError, match="finite number"):
        allocate_storyboard_durations(
            [
                {"prompt": "oversized", "duration": requested},
                {"prompt": "normal", "duration": 5.0},
            ]
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


# ---------------------------------------------------------------------------
# phase_c_ffmpeg wiring — the legacy KLING_NATIVE cascade branch must pass
# its own on_billed hook into generate_video, so a post-billing failure
# still reaches _cascade_out["billed_attempts"] (money-gate 2026-07-11: this
# is what controller._record_billed_rejects reads to bill a rejected/failed
# attempt that the provider had already charged for).
# ---------------------------------------------------------------------------

def _kling_native_runtime_snapshot():
    from domain.provider_catalog import RuntimeSnapshot

    return RuntimeSnapshot(
        credentials={"kling_access_key", "kling_secret_key"},
        modules={"jwt"},
    )


def test_phase_c_ffmpeg_kling_native_branch_notes_billed_on_post_billing_failure(
    monkeypatch, tmp_path
):
    """RED->GREEN target for defect #3: the legacy KLING_NATIVE branch in
    phase_c_ffmpeg._execute_admitted_video_chain must note a billed attempt
    even when kling.generate_video billed the provider and then still
    returned None (e.g. a download failure after the video URL arrived).

    Drives phase_c_ffmpeg.generate_ai_video directly (its public
    _cascade_out param) with no fallback candidates and cascade_retry_limit=0
    so the cascade terminates immediately after the single KLING_NATIVE
    attempt, and inspects the resulting billed_attempts list.
    """
    import phase_c_ffmpeg
    from cinema.context import PipelineContext

    output = str(tmp_path / "winner.mp4")

    kling_instance = MagicMock()

    def _billed_then_fail(**kwargs):
        kwargs["on_billed"]()
        return None

    kling_instance.generate_video.side_effect = _billed_then_fail
    kling_module = types.ModuleType("kling_native")
    kling_module.KlingNativeAPI = MagicMock(return_value=kling_instance)
    monkeypatch.setitem(sys.modules, "kling_native", kling_module)
    monkeypatch.setattr(phase_c_ffmpeg, "_load_fal_client", lambda: None)
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        _kling_native_runtime_snapshot,
    )
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_current_date",
        lambda: date(2026, 9, 23),
    )

    cascade: dict = {}
    ctx = PipelineContext(
        global_settings={"aspect_ratio": "16:9", "cascade_retry_limit": 0}
    )
    result = phase_c_ffmpeg.generate_ai_video(
        "frame.png",
        "static",
        "KLING_NATIVE",
        output,
        video_fallbacks=["KLING_NATIVE"],
        shot_type="medium",
        ctx=ctx,
        _cascade_out=cascade,
    )

    assert result is None
    kling_module.KlingNativeAPI.assert_called_once_with()
    assert cascade.get("billed_attempts") == ["KLING_NATIVE"], (
        "A billed-but-failed KLING_NATIVE attempt must be noted in "
        f"_cascade_out['billed_attempts']; got {cascade!r}"
    )


def test_phase_c_ffmpeg_kling_native_branch_billed_and_succeeded_notes_billed_once(
    monkeypatch, tmp_path
):
    """RED->GREEN idempotency-guard target: the REAL provider success shape
    fires the `on_billed` hook (the provider returned a playable video) AND
    ALSO returns a truthy result from that SAME kling.generate_video call.
    That reaches BOTH billing sites in the KLING_NATIVE branch of
    phase_c_ffmpeg._execute_admitted_video_chain — the `on_billed` hook
    (`_note_kling_billed`) itself, and the post-`if result:` compat call a
    few lines later — so only the `_kling_billed_noted` idempotency guard
    keeps `billed_attempts` appended exactly once instead of twice. A double
    append would corrupt controller._record_billed_rejects' winner-subtraction
    (it assumes each real attempt contributes at most one entry). No prior
    test drove both sites from a single call: the companion
    post-billing-failure test above invokes on_billed but returns None (hook
    site only, cascades away before the `if result:` compat call can fire).

    Uses a landscape ctx (aspect_ratio="16:9") so `_accept_or_reject` is a
    no-op (always True) and never needs to probe the (non-real) output file.
    """
    import phase_c_ffmpeg
    from cinema.context import PipelineContext

    output = str(tmp_path / "winner.mp4")

    kling_instance = MagicMock()

    def _billed_then_succeed(**kwargs):
        kwargs["on_billed"]()
        return kwargs["output_path"]

    kling_instance.generate_video.side_effect = _billed_then_succeed
    kling_module = types.ModuleType("kling_native")
    kling_module.KlingNativeAPI = MagicMock(return_value=kling_instance)
    monkeypatch.setitem(sys.modules, "kling_native", kling_module)
    monkeypatch.setattr(phase_c_ffmpeg, "_load_fal_client", lambda: None)
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        _kling_native_runtime_snapshot,
    )
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_current_date",
        lambda: date(2026, 9, 23),
    )

    cascade: dict = {}
    ctx = PipelineContext(
        global_settings={"aspect_ratio": "16:9", "cascade_retry_limit": 0}
    )
    result = phase_c_ffmpeg.generate_ai_video(
        "frame.png",
        "static",
        "KLING_NATIVE",
        output,
        video_fallbacks=["KLING_NATIVE"],
        shot_type="medium",
        ctx=ctx,
        _cascade_out=cascade,
    )

    assert result == output
    kling_module.KlingNativeAPI.assert_called_once_with()
    assert cascade.get("billed_attempts") == ["KLING_NATIVE"], (
        "A double append (one from the on_billed hook, one from the "
        "post-result compat call) would corrupt "
        "controller._record_billed_rejects' winner-subtraction; got "
        f"{cascade!r}"
    )
