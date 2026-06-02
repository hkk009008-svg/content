# tests/unit/test_sora_native.py
"""Characterization tests for sora_native.SoraNativeAPI (offline, mocked SDK).
Locks in EXISTING behaviour — all tests must PASS.
Candidate bugs are asserted against ACTUAL behaviour with # CANDIDATE BUG tags.
"""
from __future__ import annotations

import sys

# Other test files (test_dialogue_routing, test_ensure_shot_audio, test_f1b_dialogue_lipsync)
# inject a lightweight stub module for 'sora_native' via sys.modules to satisfy
# import-time deps without the full SDK. When that stub is already in sys.modules
# at collection time, `from sora_native import SoraNativeAPI` would fail with
# "cannot import name 'SoraNativeAPI' from 'sora_native' (unknown location)".
# Remove the stub so our import always gets the real module.
sys.modules.pop("sora_native", None)

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sora_native
from sora_native import SoraNativeAPI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_settings(api_key: str = "sk-test-xxx") -> MagicMock:
    """Return a mock settings object with only the fields SoraNativeAPI reads."""
    s = MagicMock()
    s.openai_api_key = api_key
    return s


def _make_api(api_key: str = "sk-test-xxx") -> SoraNativeAPI:
    """Build a SoraNativeAPI with a fake OpenAI client so __init__ succeeds
    without touching the real SDK.

    settings is a frozen dataclass singleton — cannot monkeypatch attributes.
    Patch 'sora_native.settings' (the module-level name) with a MagicMock,
    and patch 'sora_native.openai.OpenAI' so no real network client is built.
    """
    fake_openai_client = MagicMock()
    with (
        patch("sora_native.settings", _fake_settings(api_key)),
        patch("sora_native.openai.OpenAI", return_value=fake_openai_client),
    ):
        api = SoraNativeAPI()
    # Replace the client with a clean mock so each test configures independently.
    api.client = MagicMock()
    return api


def _real_jpeg(tmp_path) -> str:
    """Write a minimal real JPEG so PIL.Image.open succeeds during the resize step."""
    from PIL import Image
    img = Image.new("RGB", (32, 18), color=(128, 0, 0))
    p = tmp_path / "start.jpg"
    img.save(str(p), format="JPEG")
    return str(p)


def _make_download_content(chunks: tuple[bytes, ...] = (b"VIDEOBYTES",)):
    """Return a mock whose `.response.iter_bytes()` yields `chunks`."""
    mock_content = MagicMock()
    mock_content.response.iter_bytes.return_value = iter(chunks)
    return mock_content


def _make_video_mock(status: str = "completed", video_id: str = "vid-1"):
    """Return a mock video object returned by `create_and_poll`."""
    v = MagicMock()
    v.status = status
    v.id = video_id
    # Make attribute chains (url, video.url, output.url) return None
    # so the dead download_url computation doesn't accidentally match.
    v.url = None
    v.video = MagicMock(url=None)
    v.output = MagicMock(url=None)
    return v


# ---------------------------------------------------------------------------
# __init__ — EnvironmentError on empty key
# ---------------------------------------------------------------------------

def test_init_raises_on_empty_key():
    """G(sora)1: __init__ raises EnvironmentError when OPENAI_API_KEY is empty.
    Asymmetric vs the rest of the API family (other clients return None on a bad
    key rather than raising at construction time).
    """
    # CANDIDATE BUG (G(sora)1): raises EnvironmentError instead of returning None
    with (
        patch("sora_native.settings", _fake_settings(api_key="")),
        patch("sora_native.openai.OpenAI"),
        pytest.raises(EnvironmentError),
    ):
        SoraNativeAPI()


def test_init_succeeds_with_valid_key():
    """Happy-path construction does not raise and sets self.client."""
    fake_client = MagicMock()
    with (
        patch("sora_native.settings", _fake_settings("sk-test-xxx")),
        patch("sora_native.openai.OpenAI", return_value=fake_client) as OpenAIMock,
    ):
        api = SoraNativeAPI()
    # The SDK client should be instantiated with the provided key.
    OpenAIMock.assert_called_once_with(api_key="sk-test-xxx")
    assert api.client is fake_client


# ---------------------------------------------------------------------------
# generate_video — missing image → None
# ---------------------------------------------------------------------------

def test_missing_image_returns_none(tmp_path):
    api = _make_api()
    result = api.generate_video(
        image_path=str(tmp_path / "nonexistent.jpg"),
        prompt="a walk",
        output_path=str(tmp_path / "out.mp4"),
    )
    assert result is None


# ---------------------------------------------------------------------------
# generate_video — invalid duration → clamped to 4
# ---------------------------------------------------------------------------

def test_invalid_duration_clamped_to_4(monkeypatch, tmp_path):
    """Invalid durations are silently clamped to 4; the clamped value is
    forwarded to create_and_poll as `seconds=4`."""
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    video_mock = _make_video_mock(status="completed")
    api.client.videos.create_and_poll.return_value = video_mock
    api.client.videos.download_content.return_value = _make_download_content()

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    api.generate_video(image_path=img_path, prompt="test", output_path=out, duration=7)

    call_kwargs = api.client.videos.create_and_poll.call_args
    assert call_kwargs.kwargs.get("seconds") == 4, (
        "Invalid duration should be clamped to 4"
    )


# ---------------------------------------------------------------------------
# generate_video — resolution param is IGNORED (G(sora)2)
# ---------------------------------------------------------------------------

def test_resolution_param_ignored_hardcoded_size(monkeypatch, tmp_path):
    """G(sora)2: the `resolution` parameter is silently ignored.
    `create_and_poll` is always called with size='1280x720' regardless of
    what the caller passes for `resolution`.
    """
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    video_mock = _make_video_mock(status="completed")
    api.client.videos.create_and_poll.return_value = video_mock
    api.client.videos.download_content.return_value = _make_download_content()

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    # Request 1080p — the API docstring says this is supported, code ignores it.
    api.generate_video(image_path=img_path, prompt="test", output_path=out, resolution="1080p")

    call_kwargs = api.client.videos.create_and_poll.call_args
    actual_size = call_kwargs.kwargs.get("size")
    # CANDIDATE BUG (G(sora)2): resolution param is ignored; size is always '1280x720'
    assert actual_size == "1280x720", (
        f"Expected hardcoded size '1280x720', got {actual_size!r}"
    )


# ---------------------------------------------------------------------------
# generate_video — happy path writes bytes, returns output_path
# ---------------------------------------------------------------------------

def test_happy_path_writes_output(monkeypatch, tmp_path):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    video_mock = _make_video_mock(status="completed", video_id="vid-42")
    api.client.videos.create_and_poll.return_value = video_mock
    api.client.videos.download_content.return_value = _make_download_content(
        (b"CHUNK1", b"CHUNK2")
    )

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(image_path=img_path, prompt="cinematic", output_path=out)

    assert result == out
    with open(out, "rb") as f:
        assert f.read() == b"CHUNK1CHUNK2"
    api.client.videos.download_content.assert_called_once_with("vid-42")


# ---------------------------------------------------------------------------
# generate_video — non-completed status → None
# ---------------------------------------------------------------------------

def test_non_completed_status_returns_none(monkeypatch, tmp_path):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    video_mock = _make_video_mock(status="failed")
    api.client.videos.create_and_poll.return_value = video_mock

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(image_path=img_path, prompt="test", output_path=out)
    assert result is None


# ---------------------------------------------------------------------------
# generate_video — SDK exception → None
# ---------------------------------------------------------------------------

def test_sdk_exception_returns_none(monkeypatch, tmp_path):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    api.client.videos.create_and_poll.side_effect = RuntimeError("quota exceeded")

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(image_path=img_path, prompt="test", output_path=out)
    assert result is None


# ---------------------------------------------------------------------------
# generate_video — driving video: used when file exists
# ---------------------------------------------------------------------------

def test_driving_video_used_when_exists(monkeypatch, tmp_path):
    """When `driving_video_path` is set AND the file exists, it is passed as
    `input_reference` to `create_and_poll` instead of the resized still."""
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    driving = tmp_path / "driving.mp4"
    driving.write_bytes(b"fakevideo")
    out = str(tmp_path / "out.mp4")

    video_mock = _make_video_mock(status="completed")
    api.client.videos.create_and_poll.return_value = video_mock
    api.client.videos.download_content.return_value = _make_download_content()

    existing = {img_path, str(driving)}
    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p in existing)

    api.generate_video(
        image_path=img_path,
        prompt="motion",
        output_path=out,
        driving_video_path=str(driving),
    )

    call_kwargs = api.client.videos.create_and_poll.call_args
    assert call_kwargs.kwargs.get("input_reference") == Path(str(driving))


# ---------------------------------------------------------------------------
# generate_video — driving video: ignored when file missing
# ---------------------------------------------------------------------------

def test_driving_video_ignored_when_missing(monkeypatch, tmp_path):
    """When `driving_video_path` is set but the file does NOT exist, the still
    frame (temp resized JPEG) is used as `input_reference` instead."""
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")
    missing_driving = str(tmp_path / "missing_driving.mp4")

    video_mock = _make_video_mock(status="completed")
    api.client.videos.create_and_poll.return_value = video_mock
    api.client.videos.download_content.return_value = _make_download_content()

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    api.generate_video(
        image_path=img_path,
        prompt="motion",
        output_path=out,
        driving_video_path=missing_driving,
    )

    call_kwargs = api.client.videos.create_and_poll.call_args
    actual_ref = call_kwargs.kwargs.get("input_reference")
    # input_reference must NOT be the missing driving video path
    assert actual_ref != Path(missing_driving)
    # It should be a Path to a temp .jpg (the resized still frame)
    assert isinstance(actual_ref, Path)
    assert actual_ref.suffix == ".jpg"


# ---------------------------------------------------------------------------
# generate_video — valid duration values pass through unchanged
# ---------------------------------------------------------------------------

def test_valid_duration_passes_through(monkeypatch, tmp_path):
    """Each valid duration (4, 8, 12, 16, 20) is forwarded as `seconds=<dur>`."""
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    for dur in (4, 8, 12, 16, 20):
        api.client.videos.create_and_poll.reset_mock()
        video_mock = _make_video_mock(status="completed")
        api.client.videos.create_and_poll.return_value = video_mock
        api.client.videos.download_content.return_value = _make_download_content()

        api.generate_video(image_path=img_path, prompt="t", output_path=out, duration=dur)

        call_kwargs = api.client.videos.create_and_poll.call_args
        assert call_kwargs.kwargs.get("seconds") == dur, f"duration={dur} should pass through as seconds={dur}"
