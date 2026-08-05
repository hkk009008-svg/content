# tests/unit/test_sora_native.py
"""Characterization tests for sora_native.SoraNativeAPI (offline, mocked SDK).
Locks in EXISTING behaviour — all tests must PASS.
Intentional behaviours are documented with # DOCUMENTED-INTENTIONAL tags.
"""
from __future__ import annotations

import sys
import tempfile
from io import BytesIO
from pathlib import Path

# Other test files (test_dialogue_routing, test_ensure_shot_audio, test_f1b_dialogue_lipsync)
# inject a lightweight stub module for 'sora_native' via sys.modules to satisfy
# import-time deps without the full SDK. When that stub is already in sys.modules
# at collection time, `from sora_native import SoraNativeAPI` would fail with
# "cannot import name 'SoraNativeAPI' from 'sora_native' (unknown location)".
# Remove the stub so our import always gets the real module.
sys.modules.pop("sora_native", None)

from unittest.mock import MagicMock, patch

import pytest

import sora_native
from sora_native import SoraNativeAPI


@pytest.fixture(autouse=True)
def _accept_mock_video_payloads(monkeypatch):
    """These SDK contract tests use sentinel bytes; container validation is
    covered independently in test_media_artifact_validation.py."""
    monkeypatch.setattr(sora_native, "validate_video_artifact", lambda _path: None)


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
    # DOCUMENTED-INTENTIONAL (G(sora)1): raises EnvironmentError instead of returning None — matches veo_native; caller catches it
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
# generate_video — invalid duration rejected before submission
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("duration", [0, 7, 16, 20])
def test_invalid_duration_rejected_before_submission(duration, monkeypatch, tmp_path):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(
        image_path=img_path,
        prompt="test",
        output_path=out,
        duration=duration,
    )

    assert result is None
    api.client.videos.create_and_poll.assert_not_called()
    api.client.videos.download_content.assert_not_called()


# ---------------------------------------------------------------------------
# generate_video — resolution param maps to correct API size (G(sora)2 fixed)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("resolution", ["1080p", "720p", "480p"])
def test_sora2_clamps_any_resolution_to_720p_landscape(resolution, monkeypatch, tmp_path):
    """sora-2 supports ONLY the 720p tier (1280x720 / 720x1280 per the API — 1080p and
    480p both 400). generate_video must clamp ANY requested resolution to 720p for sora-2,
    so the landscape size= is always '1280x720' (assembly normalize upscales to the project
    container at render). Caught live: the T9 preflight 400'd on size=1080x1920. Plan U6.
    """
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    video_mock = _make_video_mock(status="completed")
    api.client.videos.create_and_poll.return_value = video_mock
    api.client.videos.download_content.return_value = _make_download_content()

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    api.generate_video(image_path=img_path, prompt="test", output_path=out, resolution=resolution)

    actual_size = api.client.videos.create_and_poll.call_args.kwargs.get("size")
    assert actual_size == "1280x720", (
        f"sora-2 must clamp resolution={resolution!r} to the 720p tier (1280x720); got {actual_size!r}"
    )


def test_sora2_portrait_clamps_to_720x1280(monkeypatch, tmp_path):
    """sora-2 portrait (9:16): clamp to 720p AND transpose → size='720x1280' (a supported
    sora-2 size). Before the fix the code requested '1080x1920', which the live API rejects
    (T9 preflight FAIL). Assembly normalize upscales 720x1280 → 1080x1920 at render."""
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    video_mock = _make_video_mock(status="completed")
    api.client.videos.create_and_poll.return_value = video_mock
    api.client.videos.download_content.return_value = _make_download_content()

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    api.generate_video(image_path=img_path, prompt="test", output_path=out,
                       resolution="1080p", aspect_ratio="9:16")

    actual_size = api.client.videos.create_and_poll.call_args.kwargs.get("size")
    assert actual_size == "720x1280", (
        f"sora-2 portrait must be '720x1280' (clamped+transposed, a supported size); got {actual_size!r}"
    )


def test_clamp_is_sora2_specific_other_models_unclamped(monkeypatch, tmp_path):
    """The 720p clamp is sora-2-SPECIFIC: a non-sora-2 model passes resolution through
    UNCHANGED (1080p → '1920x1080'). Guards against the clamp guard silently widening to
    other tiers without a test. NOTE: this asserts only that OUR clamp does not fire for
    other models — it does NOT claim sora-2-pro supports 1920x1080 at the API (separate,
    live concern; we have no sora-2-pro size whitelist to assert)."""
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    video_mock = _make_video_mock(status="completed")
    api.client.videos.create_and_poll.return_value = video_mock
    api.client.videos.download_content.return_value = _make_download_content()

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    api.generate_video(image_path=img_path, prompt="pro", output_path=out,
                       resolution="1080p", model="sora-2-pro", aspect_ratio="16:9")

    actual_size = api.client.videos.create_and_poll.call_args.kwargs.get("size")
    assert actual_size == "1920x1080", (
        f"non-sora-2 model must NOT be clamped (resolution passes through); got {actual_size!r}"
    )


def test_sora2_pro_rejects_invalid_480p_before_submission(monkeypatch, tmp_path):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")
    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(
        image_path=img_path,
        prompt="pro",
        output_path=out,
        resolution="480p",
        model="sora-2-pro",
    )

    assert result is None
    api.client.videos.create_and_poll.assert_not_called()


def test_unknown_sora_model_is_rejected_before_submission(monkeypatch, tmp_path):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")
    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(
        image_path=img_path,
        prompt="future",
        output_path=out,
        model="sora-future",
    )

    assert result is None
    api.client.videos.create_and_poll.assert_not_called()


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
    submitted_reference = (
        api.client.videos.create_and_poll.call_args.kwargs["input_reference"]
    )

    assert result == out
    with open(out, "rb") as f:
        assert f.read() == b"CHUNK1CHUNK2"
    api.client.videos.download_content.assert_called_once_with("vid-42")
    assert not submitted_reference.exists()


def test_invalid_download_is_not_published(monkeypatch, tmp_path):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = tmp_path / "out.mp4"
    out.write_bytes(b"known-good")
    api.client.videos.create_and_poll.return_value = _make_video_mock(status="completed")
    api.client.videos.download_content.return_value = _make_download_content()
    monkeypatch.setattr(
        sora_native,
        "validate_video_artifact",
        lambda _path: "invalid test container",
    )

    assert api.generate_video(img_path, "cinematic", str(out)) is None
    assert out.read_bytes() == b"known-good"


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
    submitted_reference = (
        api.client.videos.create_and_poll.call_args.kwargs["input_reference"]
    )

    assert result is None
    assert not submitted_reference.exists()


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
    submitted_reference = (
        api.client.videos.create_and_poll.call_args.kwargs["input_reference"]
    )

    assert result is None
    assert not submitted_reference.exists()


def test_download_exception_returns_none_and_cleans_temp(monkeypatch, tmp_path):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    api.client.videos.create_and_poll.return_value = _make_video_mock(
        status="completed"
    )
    api.client.videos.download_content.side_effect = RuntimeError(
        "download interrupted"
    )

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(image_path=img_path, prompt="test", output_path=out)
    submitted_reference = (
        api.client.videos.create_and_poll.call_args.kwargs["input_reference"]
    )

    assert result is None
    assert not submitted_reference.exists()


# ---------------------------------------------------------------------------
# generate_video — on_billed fires exactly at the provider's billed-URL
# boundary (money-gate 2026-07-11 class, extended to sora_native in slice M2:
# a post-billing download failure must still be distinguishable from a
# pre-billing failure to the caller). Mirrors kling_native.py's on_billed
# tests (commit 55c0797e).
# ---------------------------------------------------------------------------

def test_pre_billing_failure_does_not_call_on_billed(monkeypatch, tmp_path):
    """A non-completed status => the provider never delivered a video =>
    never billed => on_billed must NOT fire."""
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")
    on_billed = MagicMock()

    api.client.videos.create_and_poll.return_value = _make_video_mock(status="failed")
    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(
        image_path=img_path, prompt="test", output_path=out, on_billed=on_billed
    )

    assert result is None
    on_billed.assert_not_called()


def test_post_billing_download_failure_still_notes_billed(monkeypatch, tmp_path):
    """RED->GREEN target: a download failure AFTER the provider reported the
    generation completed must still fire on_billed. Pre-fix, download_content's
    failure fell into the blanket `except Exception: return None`,
    indistinguishable from a pre-billing failure and losing the spend to the
    caller's budget gate. on_billed must fire BEFORE the download attempt.
    """
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    call_order: list[str] = []
    on_billed = MagicMock(side_effect=lambda: call_order.append("billed"))

    api.client.videos.create_and_poll.return_value = _make_video_mock(status="completed")

    def _failing_download(*args, **kwargs):
        call_order.append("download")
        raise RuntimeError("simulated post-billing download failure")

    api.client.videos.download_content.side_effect = _failing_download
    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(
        image_path=img_path, prompt="test", output_path=out, on_billed=on_billed
    )

    assert result is None
    on_billed.assert_called_once()
    assert call_order == ["billed", "download"], (
        "on_billed must fire BEFORE the download attempt so a caller's spend "
        f"record is never lost to a post-billing download failure; got {call_order!r}"
    )


def test_success_fires_on_billed_exactly_once(monkeypatch, tmp_path):
    """The happy path also bills — on_billed must fire exactly once, before
    download, even when the download subsequently succeeds."""
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")
    on_billed = MagicMock()

    api.client.videos.create_and_poll.return_value = _make_video_mock(status="completed")
    api.client.videos.download_content.return_value = _make_download_content()
    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(
        image_path=img_path, prompt="test", output_path=out, on_billed=on_billed
    )

    assert result == out
    on_billed.assert_called_once()


def test_on_billed_exception_does_not_abort_download(monkeypatch, tmp_path):
    """A broken accounting callback must never abort an otherwise-successful
    generation — the callback's own exception must be swallowed and logged,
    not allowed to propagate into the outer except and blank out a real
    video."""
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    def _bad_callback():
        raise RuntimeError("accounting hook bug")

    api.client.videos.create_and_poll.return_value = _make_video_mock(status="completed")
    api.client.videos.download_content.return_value = _make_download_content()
    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(
        image_path=img_path, prompt="test", output_path=out, on_billed=_bad_callback
    )

    assert result == out, (
        "A broken on_billed callback must not abort an otherwise-successful download"
    )


# ---------------------------------------------------------------------------
# generate_video — driving video rejected before submission
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("driving_exists", [False, True])
def test_driving_video_rejected_before_preprocessing_or_submission(
    driving_exists, tmp_path
):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    driving = tmp_path / "driving.mp4"
    if driving_exists:
        driving.write_bytes(b"operator-owned")

    with (
        patch(
            "PIL.Image.open",
            side_effect=AssertionError("rejected driving input must bypass PIL"),
        ) as image_open,
        patch(
            "sora_native.tempfile.NamedTemporaryFile",
            side_effect=AssertionError(
                "rejected driving input must bypass temp files"
            ),
        ) as named_temp,
    ):
        result = api.generate_video(
            image_path=img_path,
            prompt="motion",
            output_path=str(tmp_path / "out.mp4"),
            driving_video_path=str(driving),
        )

    assert result is None
    image_open.assert_not_called()
    named_temp.assert_not_called()
    api.client.videos.create_and_poll.assert_not_called()
    api.client.videos.download_content.assert_not_called()
    if driving_exists:
        assert driving.read_bytes() == b"operator-owned"


def test_still_reference_preserves_lanczos_resize_and_jpeg_quality_90(tmp_path):
    """The submitted still must match the existing LANCZOS/JPEG-q90 transform."""
    from PIL import Image

    api = _make_api()
    source = tmp_path / "pattern.png"
    with Image.new("RGB", (5, 3)) as source_image:
        source_image.putdata(
            [
                (
                    (x * 47 + y * 11) % 256,
                    (x * 13 + y * 71) % 256,
                    (x * 89 + y * 7) % 256,
                )
                for y in range(3)
                for x in range(5)
            ]
        )
        source_image.save(source, format="PNG")

    captured: dict[str, object] = {}
    video_mock = _make_video_mock(status="completed")

    def capture_reference(**kwargs):
        reference = kwargs["input_reference"]
        captured["reference"] = reference
        captured["bytes"] = reference.read_bytes()
        with Image.open(reference) as submitted:
            captured["size"] = submitted.size
            captured["format"] = submitted.format
        return video_mock

    api.client.videos.create_and_poll.side_effect = capture_reference
    api.client.videos.download_content.return_value = _make_download_content()

    result = api.generate_video(
        image_path=str(source),
        prompt="motion",
        output_path=str(tmp_path / "out.mp4"),
        model="sora-2-pro",
        resolution="720p",
    )

    expected_bytes = BytesIO()
    with Image.open(source) as source_image:
        expected_image = source_image.resize((1280, 720), Image.LANCZOS)
        try:
            expected_image.save(expected_bytes, format="JPEG", quality=90)
        finally:
            expected_image.close()

    assert result == str(tmp_path / "out.mp4")
    assert captured["size"] == (1280, 720)
    assert captured["format"] == "JPEG"
    assert captured["bytes"] == expected_bytes.getvalue()
    assert not captured["reference"].exists()


def test_partial_preprocessing_failure_cleans_created_temp(monkeypatch, tmp_path):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    created_temp_paths: list[Path] = []
    real_named_temp = tempfile.NamedTemporaryFile

    def record_named_temp(*args, **kwargs):
        temp_file = real_named_temp(*args, **kwargs)
        created_temp_paths.append(Path(temp_file.name))
        return temp_file

    monkeypatch.setattr(
        sora_native.tempfile, "NamedTemporaryFile", record_named_temp
    )

    with patch(
        "PIL.Image.Image.save",
        side_effect=RuntimeError("resized still write failed"),
    ):
        result = api.generate_video(
            image_path=img_path,
            prompt="motion",
            output_path=str(tmp_path / "out.mp4"),
        )

    assert result is None
    assert len(created_temp_paths) == 1
    assert not created_temp_paths[0].exists()
    api.client.videos.create_and_poll.assert_not_called()


# ---------------------------------------------------------------------------
# generate_video — valid duration values pass through unchanged
# ---------------------------------------------------------------------------

def test_valid_duration_passes_through(monkeypatch, tmp_path):
    """Each current API duration is forwarded unchanged."""
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    for dur in (4, 8, 12):
        api.client.videos.create_and_poll.reset_mock()
        video_mock = _make_video_mock(status="completed")
        api.client.videos.create_and_poll.return_value = video_mock
        api.client.videos.download_content.return_value = _make_download_content()

        api.generate_video(image_path=img_path, prompt="t", output_path=out, duration=dur)

        call_kwargs = api.client.videos.create_and_poll.call_args
        assert call_kwargs.kwargs.get("seconds") == dur, f"duration={dur} should pass through as seconds={dur}"


# ---------------------------------------------------------------------------
# generate_video — portrait aspect swaps size (Task 4)
# ---------------------------------------------------------------------------

def test_portrait_swaps_size_and_resize(monkeypatch, tmp_path):
    """Task 4 / T-portrait-1: aspect_ratio='9:16' causes size to be transposed.

    sora-2 clamps to the 720p tier (T9-fix), so a 1080p portrait request becomes
    '720x1280' (clamp 1080p→720p='1280x720', then portrait_swap transposes to
    '720x1280' — a supported sora-2 size). One portrait_swap call drives both the
    API size= and the PIL resize target.
    """
    from PIL import Image

    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    video_mock = _make_video_mock(status="completed")
    captured: dict[str, object] = {}

    def capture_reference(**kwargs):
        reference = kwargs["input_reference"]
        captured["reference"] = reference
        with Image.open(reference) as submitted:
            captured["resize"] = submitted.size
        return video_mock

    api.client.videos.create_and_poll.side_effect = capture_reference
    api.client.videos.download_content.return_value = _make_download_content()

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    api.generate_video(
        image_path=img_path,
        prompt="portrait test",
        output_path=out,
        resolution="1080p",
        aspect_ratio="9:16",
    )

    call_kwargs = api.client.videos.create_and_poll.call_args
    actual_size = call_kwargs.kwargs.get("size")
    assert actual_size == "720x1280", (
        f"portrait should map to the clamped+transposed size='720x1280'; got {actual_size!r}"
    )
    assert captured["resize"] == (720, 1280)
    assert not captured["reference"].exists()


def test_landscape_size_unchanged(monkeypatch, tmp_path):
    """Task 4 / T-portrait-2 (refute): aspect_ratio='16:9' is NOT transposed.

    portrait_swap is a no-op for landscape; with the sora-2 720p clamp (T9-fix) a
    1080p landscape request maps to '1280x720' (clamped, not transposed) — a
    supported sora-2 size. Proves the orientation is preserved for landscape.
    """
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = str(tmp_path / "out.mp4")

    video_mock = _make_video_mock(status="completed")
    api.client.videos.create_and_poll.return_value = video_mock
    api.client.videos.download_content.return_value = _make_download_content()

    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    api.generate_video(
        image_path=img_path,
        prompt="landscape test",
        output_path=out,
        resolution="1080p",
        aspect_ratio="16:9",
    )

    call_kwargs = api.client.videos.create_and_poll.call_args
    actual_size = call_kwargs.kwargs.get("size")
    assert actual_size == "1280x720", (
        f"landscape should map to the clamped (not transposed) size='1280x720'; got {actual_size!r}"
    )


def test_midstream_download_preserves_existing_output(monkeypatch, tmp_path):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = tmp_path / "out.mp4"
    out.write_bytes(b"known-good")

    api.client.videos.create_and_poll.return_value = _make_video_mock(
        status="completed"
    )

    def failing_chunks():
        yield b"partial"
        raise RuntimeError("stream broke")

    mock_content = MagicMock()
    mock_content.response.iter_bytes.return_value = failing_chunks()
    api.client.videos.download_content.return_value = mock_content
    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(
        image_path=img_path,
        prompt="test",
        output_path=str(out),
    )

    assert result is None
    assert out.read_bytes() == b"known-good"
    assert list(tmp_path.glob(".sora-download-*.tmp")) == []


def test_download_over_hard_cap_preserves_existing_output(monkeypatch, tmp_path):
    api = _make_api()
    img_path = _real_jpeg(tmp_path)
    out = tmp_path / "out.mp4"
    out.write_bytes(b"known-good")

    api.client.videos.create_and_poll.return_value = _make_video_mock(
        status="completed"
    )
    api.client.videos.download_content.return_value = _make_download_content(
        (b"12345", b"6789")
    )
    monkeypatch.setattr(sora_native, "SORA_MAX_VIDEO_BYTES", 8)
    monkeypatch.setattr(sora_native.os.path, "exists", lambda p: p == img_path)

    result = api.generate_video(
        image_path=img_path,
        prompt="test",
        output_path=str(out),
    )

    assert result is None
    assert out.read_bytes() == b"known-good"
    assert list(tmp_path.glob(".safe-download-*.tmp")) == []
