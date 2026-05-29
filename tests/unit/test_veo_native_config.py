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
from unittest.mock import MagicMock, patch, mock_open

from google.genai import types

# Sibling unit tests (e.g. test_dialogue_routing) stub `veo_native` into
# sys.modules at import time (heavy-dep avoidance via _stub_module), and pytest
# collects them first (alphabetical). This module needs the REAL implementation,
# so drop any stub before importing — the real veo_native imports cleanly
# (google-genai is installed).
sys.modules.pop("veo_native", None)

from veo_native import (  # noqa: E402
    _parse_duration_seconds,
    _build_generate_videos_config,
    VeoNativeAPI,
)


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
    cfg = _build_generate_videos_config(
        generate_audio=False, duration="5s", resolution="720p", reference_images=None
    )
    assert cfg.generate_audio is False
    assert cfg.duration_seconds == 5


def test_wraps_reference_images_into_config():
    # Refs land in config.reference_images as VideoGenerationReferenceImage (ASSET),
    # NOT as raw Image and NOT top-level (the TypeError bug).
    img = types.Image(gcs_uri="gs://x/y.png")
    cfg = _build_generate_videos_config(
        generate_audio=False, duration="5s", resolution="720p", reference_images=[img]
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
    op.done = True
    gen_vid = MagicMock()
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
    # Audio + refs threaded via the config
    cfg = captured["config"]
    assert cfg.generate_audio is True
    assert cfg.reference_images is not None and len(cfg.reference_images) == 1


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
