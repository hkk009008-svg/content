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
