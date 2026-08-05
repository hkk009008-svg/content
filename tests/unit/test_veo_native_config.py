"""Unit tests for veo_native config-threading fix (spec/plan 2026-05-29).

Covers the three confirmed bugs in veo_native.generate_video():
1. reference_images/reference_video passed as top-level kwargs to generate_videos
   (the SDK rejects them -> TypeError). They must go INTO the config
   (reference_images, wrapped) / via the top-level `video=` param.
2. generate_audio dropped (never set on the config).
3. duration/resolution dropped (never set on the config).

All tests are offline — no Vertex, no network, no spend.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, mock_open

import pytest

from google.genai import types

# Sibling unit tests (e.g. test_dialogue_routing) stub `veo_native` into
# sys.modules at import time (heavy-dep avoidance via _stub_module), and pytest
# collects them first (alphabetical). This module needs the REAL implementation,
# so drop any stub before importing — the real veo_native imports cleanly
# (google-genai is installed).
sys.modules.pop("veo_native", None)

import veo_native  # noqa: E402
from veo_native import (  # noqa: E402
    _parse_duration_seconds,
    _build_generate_videos_config,
    VeoNativeAPI,
    VeoNativeJobDeferred,
    veo_native_audio_available,
)


@pytest.fixture(autouse=True)
def _accept_mock_video_payloads(monkeypatch):
    """These SDK contract tests use sentinel bytes; ffprobe validation has a
    dedicated artifact-validation suite."""
    monkeypatch.setattr(veo_native, "validate_video_artifact", lambda _path: None)


def _veo_settings(*, project="", location="us-central1", api_key=""):
    return SimpleNamespace(
        google_cloud_project=project,
        google_cloud_location=location,
        google_api_key=api_key,
    )


def test_init_uses_vertex_only_with_explicit_project():
    client = MagicMock()
    with (
        patch(
            "veo_native.settings",
            _veo_settings(project="explicit-project", api_key="developer-key"),
        ),
        patch("veo_native.google_adc_available", return_value=True),
        patch("veo_native.genai.Client", return_value=client) as client_factory,
    ):
        api = VeoNativeAPI()

    client_factory.assert_called_once_with(
        vertexai=True,
        project="explicit-project",
        location="us-central1",
    )
    assert api.client is client
    assert api._backend == "vertex"
    assert api._model == "veo-3.1-generate-001"
    assert api.supports_native_audio is True


def test_init_uses_developer_api_when_only_api_key_is_configured():
    client = MagicMock()
    with (
        patch("veo_native.settings", _veo_settings(api_key="developer-key")),
        patch("veo_native.genai.Client", return_value=client) as client_factory,
    ):
        api = VeoNativeAPI()

    client_factory.assert_called_once_with(api_key="developer-key")
    assert api.client is client
    assert api._backend == "gemini"
    assert api._model == "veo-3.1-generate-preview"
    assert api.supports_native_audio is False


def test_init_falls_back_to_developer_api_when_project_has_no_adc():
    client = MagicMock()
    with (
        patch(
            "veo_native.settings",
            _veo_settings(project="explicit-project", api_key="developer-key"),
        ),
        patch("veo_native.google_adc_available", return_value=False),
        patch("veo_native.genai.Client", return_value=client) as client_factory,
    ):
        api = VeoNativeAPI()

    client_factory.assert_called_once_with(api_key="developer-key")
    assert api.client is client
    assert api._backend == "gemini"
    assert api.supports_native_audio is False


def test_init_project_without_adc_or_api_key_fails_before_client():
    with (
        patch("veo_native.settings", _veo_settings(project="explicit-project")),
        patch("veo_native.google_adc_available", return_value=False),
        patch("veo_native.genai.Client") as client_factory,
        pytest.raises(EnvironmentError, match="Application Default Credentials"),
    ):
        VeoNativeAPI()

    client_factory.assert_not_called()


def test_native_audio_capability_requires_project_and_adc():
    with (
        patch("veo_native.settings", _veo_settings(project="project")),
        patch("veo_native.google_adc_available", return_value=True),
    ):
        assert veo_native_audio_available() is True

    with (
        patch("veo_native.settings", _veo_settings(api_key="key")),
        patch("veo_native.google_adc_available", return_value=False),
    ):
        assert veo_native_audio_available() is False


def test_init_without_credentials_fails_before_client_construction():
    with (
        patch("veo_native.settings", _veo_settings()),
        patch("veo_native.genai.Client") as client_factory,
        pytest.raises(EnvironmentError, match="GOOGLE_CLOUD_PROJECT"),
    ):
        VeoNativeAPI()

    client_factory.assert_not_called()


# ---------------------------------------------------------------------------
# Task 1 — _parse_duration_seconds
# ---------------------------------------------------------------------------
def test_parses_normal_duration():
    assert _parse_duration_seconds("8s") == 8
    assert _parse_duration_seconds("5s") == 5
    assert _parse_duration_seconds("6s") == 6


def test_malformed_duration_defaults_to_8():
    # A formatting edge must not fail generation (spec §4.1 contract).
    assert _parse_duration_seconds("8") == 8          # missing 's'
    assert _parse_duration_seconds("") == 8
    assert _parse_duration_seconds(None) == 8
    assert _parse_duration_seconds("garbage") == 8


# ---------------------------------------------------------------------------
# Task 2 — _build_generate_videos_config (pure)
# ---------------------------------------------------------------------------
def test_builds_config_with_all_caller_params():
    cfg = _build_generate_videos_config(
        generate_audio=True, duration="8s", resolution="720p", reference_images=None
    )
    assert cfg.generate_audio is True
    assert cfg.duration_seconds == 8
    assert cfg.resolution == "720p"
    assert cfg.person_generation == "allow_adult"
    assert cfg.aspect_ratio == "16:9"
    assert not cfg.reference_images  # None/empty when no refs


def test_generate_audio_false_is_respected():
    # duration "6s" is server-valid for image_to_video; "5s" would clamp (see
    # the Bug 2 clamp tests below) -- keep this test focused on the audio flag.
    cfg = _build_generate_videos_config(
        generate_audio=False, duration="6s", resolution="720p", reference_images=None
    )
    assert cfg.generate_audio is False
    assert cfg.duration_seconds == 6


def test_wraps_reference_images_into_config():
    # Refs land in config.reference_images as VideoGenerationReferenceImage (ASSET),
    # NOT as raw Image and NOT top-level (the TypeError bug).
    img = types.Image(gcs_uri="gs://x/y.png")
    cfg = _build_generate_videos_config(
        generate_audio=False, duration="8s", resolution="720p", reference_images=[img]
    )
    assert cfg.reference_images is not None and len(cfg.reference_images) == 1
    ref = cfg.reference_images[0]
    assert isinstance(ref, types.VideoGenerationReferenceImage)
    assert ref.reference_type == types.VideoGenerationReferenceType.ASSET


# ---------------------------------------------------------------------------
# Task 3 — generate_video() call-site contract (no illegal top-level kwargs)
# ---------------------------------------------------------------------------
def _completed_operation():
    op = MagicMock()
    op.name = "operations/veo-123"
    op.done = True
    op.error = None  # a successful operation has no error (Bug 3 reads operation.error)
    gen_vid = MagicMock()
    # Make the Vertex inline-bytes path explicit (Lane V M1): _extract_video_bytes
    # prefers video_bytes, so set it rather than relying on a truthy MagicMock.
    gen_vid.video.video_bytes = b"VIDEO_BYTES"
    op.response.generated_videos = [gen_vid]
    op.response.rai_media_filtered_reasons = []
    return op


def test_generate_video_passes_config_not_toplevel_kwargs():
    """The regression guard: generate_video must call generate_videos with the
    config carrying audio + wrapped refs, and NO top-level reference_images/
    reference_video kwarg (which the SDK rejects -> TypeError)."""
    api = VeoNativeAPI.__new__(VeoNativeAPI)  # bypass __init__ (no real client)
    api._model = "veo-3.1-generate-001"
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return _completed_operation()

    api.client = MagicMock()
    api.client.models.generate_videos.side_effect = _capture
    api.client.operations.get.side_effect = lambda o: o
    api.client.files.download.return_value = b"\x00\x00"

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with patch("veo_native.os.path.exists", return_value=True), \
         patch("veo_native.os.path.getsize", return_value=10), \
         patch("google.genai.types.Image.from_file", return_value=fake_img), \
         patch("builtins.open", mock_open()):
        result = api.generate_video(
            image_path="/tmp/frame.png",
            prompt="hello",
            output_path="/tmp/out.mp4",
            reference_images=["/tmp/ref1.png"],
            generate_audio=True,
            duration="8s",
        )

    assert result == "/tmp/out.mp4"
    # The bug fix: NO illegal top-level kwargs
    assert "reference_images" not in captured
    assert "reference_video" not in captured
    # Audio threaded via the config; refs NOT threaded — image-to-video uses the
    # start frame for identity and rejects image+reference_images (Bug #4).
    cfg = captured["config"]
    assert cfg.generate_audio is True
    assert not cfg.reference_images


def test_invalid_video_bytes_do_not_replace_existing_output(tmp_path, monkeypatch):
    api = VeoNativeAPI.__new__(VeoNativeAPI)
    api._model = "veo-3.1-generate-001"
    api.client = MagicMock()
    api.client.models.generate_videos.return_value = _completed_operation()
    api.client.operations.get.side_effect = lambda operation: operation
    image_path = tmp_path / "frame.png"
    image_path.write_bytes(b"input")
    output_path = tmp_path / "out.mp4"
    output_path.write_bytes(b"known-good")
    monkeypatch.setattr(
        veo_native,
        "validate_video_artifact",
        lambda _path: "invalid test container",
    )

    with patch(
        "google.genai.types.Image.from_file",
        return_value=types.Image(gcs_uri="gs://x/y.png"),
    ):
        with pytest.raises(VeoNativeJobDeferred) as deferred:
            api.generate_video(
                image_path=str(image_path),
                prompt="hello",
                output_path=str(output_path),
            )

    assert deferred.value.reason == "completed_output_invalid"
    assert deferred.value.job_id == "operations/veo-123"
    assert deferred.value.provider_status == "completed"
    assert deferred.value.billed is True
    assert deferred.value.duration_s == 8
    assert output_path.read_bytes() == b"known-good"


def test_reference_images_not_threaded_when_start_image_present():
    """Veo image-to-video: `image` (start frame) and config `reference_images`
    are mutually exclusive — Vertex rejects "Image and reference images cannot
    be both set." (code 3). generate_video ALWAYS supplies a start image (it
    returns None without one), so reference_images can never ride along: the
    config must NOT carry them. Identity comes from the start frame. Mirrors the
    image/video exclusion fixed in f6d6995. (Bug #4, operator live-E2E.)"""
    api = VeoNativeAPI.__new__(VeoNativeAPI)
    api._model = "veo-3.1-generate-001"
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return _completed_operation()

    api.client = MagicMock()
    api.client.models.generate_videos.side_effect = _capture
    api.client.operations.get.side_effect = lambda o: o
    api.client.files.download.return_value = b"\x00"

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with patch("veo_native.os.path.exists", return_value=True), \
         patch("veo_native.os.path.getsize", return_value=10), \
         patch("google.genai.types.Image.from_file", return_value=fake_img), \
         patch("builtins.open", mock_open()):
        api.generate_video(
            image_path="/tmp/frame.png",
            prompt="hello",
            output_path="/tmp/out.mp4",
            reference_images=["/tmp/ref1.png", "/tmp/ref2.png"],
            generate_audio=True,
        )

    assert "image" in captured            # start frame is the identity source
    assert "reference_images" not in captured  # never a top-level kwarg
    cfg = captured["config"]
    assert not cfg.reference_images       # and NOT threaded into the config


def test_driving_video_not_passed_alongside_image():
    """SDK: `image` and `video` are mutually exclusive ("Not allowed if image is
    provided"). A driving clip must NOT be added as `video=` next to the start
    image, or the whole generation fails server-side. Image-only is correct."""
    api = VeoNativeAPI.__new__(VeoNativeAPI)
    api._model = "veo-3.1-generate-001"
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return _completed_operation()

    api.client = MagicMock()
    api.client.models.generate_videos.side_effect = _capture
    api.client.operations.get.side_effect = lambda o: o
    api.client.files.download.return_value = b"\x00"

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with patch("veo_native.os.path.exists", return_value=True), \
         patch("veo_native.os.path.getsize", return_value=10), \
         patch("google.genai.types.Image.from_file", return_value=fake_img), \
         patch("builtins.open", mock_open()):
        api.generate_video(
            image_path="/tmp/frame.png",
            prompt="hello",
            output_path="/tmp/out.mp4",
            driving_video_path="/tmp/drive.mp4",
            generate_audio=False,
        )

    assert "video" not in captured   # image-only; no mutual-exclusion conflict
    assert "image" in captured


# ---------------------------------------------------------------------------
# Bug 2 — image_to_video duration must be server-valid (4/6/8); 5s is rejected
# (operator live test: gRPC code 3 "Unsupported output video duration 5 seconds,
#  supported durations are [8,4,6] for feature image_to_video").
# ---------------------------------------------------------------------------
def test_clamp_image_to_video_duration_snaps_to_valid_set():
    from veo_native import _clamp_image_to_video_duration as clamp

    # Exact valid values pass through.
    assert clamp(4) == 4
    assert clamp(6) == 6
    assert clamp(8) == 8
    # Invalid -> nearest valid; ties round UP (don't truncate requested content).
    assert clamp(5) == 6   # 4 and 6 equidistant -> 6
    assert clamp(7) == 8   # 6 and 8 equidistant -> 8
    assert clamp(3) == 4
    assert clamp(10) == 8  # above range -> max
    assert clamp(1) == 4   # below range -> min


def test_build_config_clamps_invalid_duration():
    # 5s is invalid for image_to_video; the config must carry a server-valid
    # duration so generate_videos isn't rejected with INVALID_ARGUMENT.
    cfg = _build_generate_videos_config(
        generate_audio=True, duration="5s", resolution="720p", reference_images=None
    )
    assert cfg.duration_seconds == 6


@pytest.mark.parametrize("resolution", ["1080p", "4k", "2160p"])
@pytest.mark.parametrize("duration", ["4s", "6s"])
def test_high_resolution_requires_eight_seconds(resolution, duration):
    with pytest.raises(ValueError, match="requires an 8-second duration"):
        _build_generate_videos_config(
            generate_audio=True,
            duration=duration,
            resolution=resolution,
            reference_images=None,
        )


def test_reference_images_require_eight_seconds():
    img = types.Image(gcs_uri="gs://x/y.png")
    with pytest.raises(ValueError, match="reference images.*8-second"):
        _build_generate_videos_config(
            generate_audio=False,
            duration="6s",
            resolution="720p",
            reference_images=[img],
        )


@pytest.mark.parametrize(
    ("requested", "provider_value"),
    [("720p", "720p"), ("1080p", "1080p"), ("4k", "4k"), ("2160p", "4k")],
)
def test_resolution_is_validated_and_normalized(requested, provider_value):
    cfg = _build_generate_videos_config(
        generate_audio=True,
        duration="8s",
        resolution=requested,
        reference_images=None,
    )
    assert cfg.resolution == provider_value


def test_unknown_resolution_is_rejected_before_sdk_config():
    with pytest.raises(ValueError, match="Unsupported Veo resolution"):
        _build_generate_videos_config(
            generate_audio=False,
            duration="8s",
            resolution="480p",
            reference_images=None,
        )


@pytest.mark.parametrize("aspect_ratio", ["1:1", "16:10", "portrait", ""])
def test_unknown_aspect_ratio_is_rejected_before_sdk_config(aspect_ratio):
    with pytest.raises(ValueError, match="Unsupported Veo aspect ratio"):
        _build_generate_videos_config(
            generate_audio=False,
            duration="8s",
            resolution="720p",
            reference_images=None,
            aspect_ratio=aspect_ratio,
        )


@pytest.mark.parametrize(
    ("duration", "resolution", "aspect_ratio", "with_reference", "valid"),
    [
        ("4s", "720p", "16:9", False, True),
        ("6s", "720p", "9:16", False, True),
        ("8s", "1080p", "16:9", False, True),
        ("8s", "4k", "9:16", False, True),
        ("4s", "1080p", "16:9", False, False),
        ("6s", "4k", "9:16", False, False),
        ("6s", "720p", "16:9", True, False),
        ("8s", "720p", "9:16", True, True),
    ],
)
def test_veo_config_cross_field_matrix(
    duration, resolution, aspect_ratio, with_reference, valid
):
    kwargs = {
        "generate_audio": False,
        "duration": duration,
        "resolution": resolution,
        "reference_images": [types.Image(gcs_uri="gs://x/ref.png")]
        if with_reference else None,
        "aspect_ratio": aspect_ratio,
    }
    if valid:
        config = _build_generate_videos_config(**kwargs)
        assert config.aspect_ratio == aspect_ratio
        assert config.resolution == resolution
    else:
        with pytest.raises(ValueError, match="requires an 8-second duration"):
            _build_generate_videos_config(**kwargs)


# ---------------------------------------------------------------------------
# Bug 1 (CRITICAL) — Vertex returns the video INLINE (video_bytes); the Files
# API download() raises on Vertex ("only supported in the Gemini Developer
# client"). Prefer inline bytes; fall back to download only for the Gemini
# backend.
# ---------------------------------------------------------------------------
def test_extract_video_bytes_prefers_inline_vertex():
    from veo_native import _extract_video_bytes

    client = MagicMock()
    gen_vid = MagicMock()
    gen_vid.video.video_bytes = b"VERTEX_INLINE"
    assert _extract_video_bytes(client, gen_vid) == b"VERTEX_INLINE"
    client.files.download.assert_not_called()  # Vertex: download() would raise


def test_extract_video_bytes_falls_back_to_download_for_gemini():
    from veo_native import _extract_video_bytes

    client = MagicMock()
    client.files.download.return_value = b"GEMINI_DL"
    gen_vid = MagicMock()
    gen_vid.video.video_bytes = None  # Gemini Developer backend: no inline bytes
    assert _extract_video_bytes(client, gen_vid) == b"GEMINI_DL"
    client.files.download.assert_called_once_with(file=gen_vid.video)


# ---------------------------------------------------------------------------
# Bug 3 (MEDIUM) — operation.error must be surfaced, not masked as the generic
# "empty response" (the deterministic INVALID_ARGUMENT cost two debug rounds).
# ---------------------------------------------------------------------------
def test_generate_video_surfaces_operation_error(capsys):
    api = VeoNativeAPI.__new__(VeoNativeAPI)  # bypass __init__ (no real client)
    api._model = "veo-3.1-generate-001"

    op = MagicMock()
    op.done = True
    op.error = {"code": 3, "message": "Unsupported output video duration 5 seconds"}

    api.client = MagicMock()
    api.client.models.generate_videos.return_value = op
    api.client.operations.get.side_effect = lambda o: o

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with patch("veo_native.os.path.exists", return_value=True), \
         patch("google.genai.types.Image.from_file", return_value=fake_img):
        result = api.generate_video(
            image_path="/tmp/frame.png", prompt="x", output_path="/tmp/out.mp4",
        )

    assert result is None
    out = capsys.readouterr().out
    assert "Generation error" in out
    assert "Unsupported output video duration" in out


def test_submit_acknowledgement_ambiguity_requires_recovery():
    """A raised submit call cannot prove that the service rejected the job."""
    api = VeoNativeAPI.__new__(VeoNativeAPI)
    api._model = "veo-3.1-generate-001"
    api.client = MagicMock()
    api.client.models.generate_videos.side_effect = RuntimeError("response lost")

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with (
        patch("veo_native.os.path.exists", return_value=True),
        patch("google.genai.types.Image.from_file", return_value=fake_img),
        pytest.raises(VeoNativeJobDeferred) as deferred,
    ):
        api.generate_video(
            image_path="/tmp/frame.png",
            prompt="x",
            output_path="/tmp/out.mp4",
        )

    assert deferred.value.reason == "submit_outcome_unknown"
    assert deferred.value.status == "recovery_required"
    assert deferred.value.job_id is None
    assert deferred.value.provider_status == "submission_unknown"
    assert deferred.value.billed is False
    assert deferred.value.duration_s == 8


def test_poll_transport_ambiguity_defers_bound_operation():
    """A returned operation name owns the request after a poll response is lost."""
    api = VeoNativeAPI.__new__(VeoNativeAPI)
    api._model = "veo-3.1-generate-001"

    pending = MagicMock()
    pending.name = "projects/p/locations/l/operations/veo-bound-456"
    pending.done = False
    pending.error = None

    api.client = MagicMock()
    api.client.models.generate_videos.return_value = pending
    api.client.operations.get.side_effect = RuntimeError("connection reset")

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with (
        patch("veo_native.os.path.exists", return_value=True),
        patch("veo_native.time.sleep", return_value=None),
        patch("google.genai.types.Image.from_file", return_value=fake_img),
        pytest.raises(VeoNativeJobDeferred) as deferred,
    ):
        api.generate_video(
            image_path="/tmp/frame.png",
            prompt="x",
            output_path="/tmp/out.mp4",
        )

    assert deferred.value.reason == "accepted_job_poll_error"
    assert deferred.value.status == "pending"
    assert deferred.value.job_id == pending.name
    assert deferred.value.provider_status == "pending"
    assert deferred.value.billed is False
    assert deferred.value.duration_s == 8


# ---------------------------------------------------------------------------
# Task 3 — generate_video() must accept and thread aspect_ratio into the config
# RED: today generate_video has no aspect_ratio param → TypeError or it's dropped
# ---------------------------------------------------------------------------
def test_generate_video_threads_portrait_aspect_ratio():
    """generate_video(..., aspect_ratio='9:16') must cause the built config to
    carry aspect_ratio == '9:16'. Today generate_video has no such parameter,
    so calling it raises TypeError (missing or unexpected keyword argument).
    After the fix, the config must carry the caller-supplied value."""
    api = VeoNativeAPI.__new__(VeoNativeAPI)
    api._model = "veo-3.1-generate-001"
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return _completed_operation()

    api.client = MagicMock()
    api.client.models.generate_videos.side_effect = _capture
    api.client.operations.get.side_effect = lambda o: o
    api.client.files.download.return_value = b"\x00\x00"

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with patch("veo_native.os.path.exists", return_value=True), \
         patch("veo_native.os.path.getsize", return_value=10), \
         patch("google.genai.types.Image.from_file", return_value=fake_img), \
         patch("builtins.open", mock_open()):
        result = api.generate_video(
            image_path="/tmp/frame.png",
            prompt="portrait test",
            output_path="/tmp/out.mp4",
            aspect_ratio="9:16",
        )

    assert result == "/tmp/out.mp4"
    cfg = captured["config"]
    assert cfg.aspect_ratio == "9:16"


def test_generate_video_defaults_aspect_ratio_to_16_9():
    """Without aspect_ratio kwarg, the config must default to '16:9' (landscape).
    Keeps the existing landscape baseline green."""
    api = VeoNativeAPI.__new__(VeoNativeAPI)
    api._model = "veo-3.1-generate-001"
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return _completed_operation()

    api.client = MagicMock()
    api.client.models.generate_videos.side_effect = _capture
    api.client.operations.get.side_effect = lambda o: o
    api.client.files.download.return_value = b"\x00\x00"

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with patch("veo_native.os.path.exists", return_value=True), \
         patch("veo_native.os.path.getsize", return_value=10), \
         patch("google.genai.types.Image.from_file", return_value=fake_img), \
         patch("builtins.open", mock_open()):
        api.generate_video(
            image_path="/tmp/frame.png",
            prompt="landscape test",
            output_path="/tmp/out.mp4",
        )

    cfg = captured["config"]
    assert cfg.aspect_ratio == "16:9"


# ---------------------------------------------------------------------------
# generate_video — on_billed fires exactly at the provider's billed-video
# boundary (money-gate 2026-07-11 class, extended to veo_native in slice M2:
# a post-billing bytes-retrieval failure must still be distinguishable from a
# pre-billing failure to the caller). Mirrors kling_native.py's on_billed
# tests (commit 55c0797e).
# ---------------------------------------------------------------------------

def test_pre_billing_failure_does_not_call_on_billed():
    """An empty response (no generated_videos) => the provider never
    delivered a video => never billed => on_billed must NOT fire."""
    api = VeoNativeAPI.__new__(VeoNativeAPI)
    api._model = "veo-3.1-generate-001"
    on_billed = MagicMock()

    op = MagicMock()
    op.done = True
    op.error = None
    op.response.generated_videos = []
    op.response.rai_media_filtered_reasons = []
    op.response.rai_media_filtered_count = 0

    api.client = MagicMock()
    api.client.models.generate_videos.return_value = op
    api.client.operations.get.side_effect = lambda o: o

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with patch("veo_native.os.path.exists", return_value=True), \
         patch("google.genai.types.Image.from_file", return_value=fake_img):
        result = api.generate_video(
            image_path="/tmp/frame.png", prompt="x", output_path="/tmp/out.mp4",
            on_billed=on_billed,
        )

    assert result is None
    on_billed.assert_not_called()


def test_post_billing_bytes_retrieval_failure_still_notes_billed():
    """RED->GREEN target: a bytes-retrieval failure AFTER the operation
    response reports a generated video must still fire on_billed. Pre-fix,
    _extract_video_bytes's failure fell into the blanket
    `except Exception: return None`, indistinguishable from a pre-billing
    failure and losing the spend to the caller's budget gate. on_billed must
    fire BEFORE the retrieval attempt, not after."""
    api = VeoNativeAPI.__new__(VeoNativeAPI)
    api._model = "veo-3.1-generate-001"

    call_order: list[str] = []
    on_billed = MagicMock(side_effect=lambda: call_order.append("billed"))

    gen_vid = MagicMock()
    gen_vid.video.video_bytes = None  # Gemini backend: falls through to files.download

    op = MagicMock()
    op.name = "operations/veo-download-456"
    op.done = True
    op.error = None
    op.response.generated_videos = [gen_vid]
    op.response.rai_media_filtered_reasons = []

    def _failing_download(*args, **kwargs):
        call_order.append("download")
        raise RuntimeError("simulated post-billing bytes-retrieval failure")

    api.client = MagicMock()
    api.client.models.generate_videos.return_value = op
    api.client.operations.get.side_effect = lambda o: o
    api.client.files.download.side_effect = _failing_download

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with patch("veo_native.os.path.exists", return_value=True), \
         patch("google.genai.types.Image.from_file", return_value=fake_img):
        with pytest.raises(VeoNativeJobDeferred) as deferred:
            api.generate_video(
                image_path="/tmp/frame.png", prompt="x", output_path="/tmp/out.mp4",
                on_billed=on_billed,
            )

    assert deferred.value.reason == "completed_output_unavailable"
    assert deferred.value.job_id == "operations/veo-download-456"
    assert deferred.value.provider_status == "completed"
    assert deferred.value.billed is True
    assert deferred.value.duration_s == 8
    on_billed.assert_called_once()
    assert call_order == ["billed", "download"], (
        "on_billed must fire BEFORE the bytes-retrieval attempt so a caller's "
        f"spend record is never lost to a post-billing failure; got {call_order!r}"
    )


def test_success_fires_on_billed_exactly_once():
    """The happy path also bills — on_billed must fire exactly once, before
    bytes retrieval, even when retrieval subsequently succeeds."""
    api = VeoNativeAPI.__new__(VeoNativeAPI)
    api._model = "veo-3.1-generate-001"
    on_billed = MagicMock()

    api.client = MagicMock()
    api.client.models.generate_videos.return_value = _completed_operation()
    api.client.operations.get.side_effect = lambda o: o
    api.client.files.download.return_value = b"\x00\x00"

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with patch("veo_native.os.path.exists", return_value=True), \
         patch("veo_native.os.path.getsize", return_value=10), \
         patch("google.genai.types.Image.from_file", return_value=fake_img), \
         patch("builtins.open", mock_open()):
        result = api.generate_video(
            image_path="/tmp/frame.png", prompt="x", output_path="/tmp/out.mp4",
            on_billed=on_billed,
        )

    assert result == "/tmp/out.mp4"
    on_billed.assert_called_once()


def test_on_billed_exception_does_not_abort_success():
    """A broken accounting callback must never abort an otherwise-successful
    generation — the callback's own exception must be swallowed and logged,
    not allowed to propagate into the outer except and blank out a real
    video."""
    api = VeoNativeAPI.__new__(VeoNativeAPI)
    api._model = "veo-3.1-generate-001"

    def _bad_callback():
        raise RuntimeError("accounting hook bug")

    api.client = MagicMock()
    api.client.models.generate_videos.return_value = _completed_operation()
    api.client.operations.get.side_effect = lambda o: o
    api.client.files.download.return_value = b"\x00\x00"

    fake_img = types.Image(gcs_uri="gs://x/y.png")
    with patch("veo_native.os.path.exists", return_value=True), \
         patch("veo_native.os.path.getsize", return_value=10), \
         patch("google.genai.types.Image.from_file", return_value=fake_img), \
         patch("builtins.open", mock_open()):
        result = api.generate_video(
            image_path="/tmp/frame.png", prompt="x", output_path="/tmp/out.mp4",
            on_billed=_bad_callback,
        )

    assert result == "/tmp/out.mp4", (
        "A broken on_billed callback must not abort an otherwise-successful generation"
    )
