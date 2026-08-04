"""Media validators used before atomic network-output publication."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from performance._net import (
    atomic_publish_bytes,
    publish_validated_file,
    validate_audio_artifact,
    validate_image_artifact,
    validate_video_artifact,
)


def _probe_payload(stream: dict, *, duration: str = "2.5") -> SimpleNamespace:
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            {"streams": [stream], "format": {"duration": duration}}
        ),
        stderr="",
    )


def test_image_validator_checks_magic_format_and_dimensions(tmp_path):
    image_path = tmp_path / "frame.bin"
    Image.new("RGB", (32, 48), "red").save(image_path, format="JPEG")

    assert (
        validate_image_artifact(
            str(image_path),
            expected_formats=("JPEG",),
            expected_dimensions=(32, 48),
        )
        is None
    )
    assert "not in" in (
        validate_image_artifact(str(image_path), expected_formats=("PNG",)) or ""
    )
    assert "dimensions" in (
        validate_image_artifact(str(image_path), expected_dimensions=(48, 32)) or ""
    )


def test_image_validator_rejects_html_saved_as_image(tmp_path):
    image_path = tmp_path / "frame.jpg"
    image_path.write_text("<html>provider error</html>")

    assert "decode failed" in (validate_image_artifact(str(image_path)) or "")


def test_video_validator_requires_mp4_magic_and_stream_contract(tmp_path):
    video_path = tmp_path / "take.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    probe = _probe_payload(
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "duration": "2.5",
        }
    )

    with patch("performance._net.subprocess.run", return_value=probe):
        assert (
            validate_video_artifact(
                str(video_path), expected_dimensions=(1920, 1080)
            )
            is None
        )


def test_video_validator_rejects_decode_failure_after_valid_metadata(tmp_path):
    """Container metadata alone cannot bless a truncated/corrupt video."""
    video_path = tmp_path / "take.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    probe = _probe_payload(
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "duration": "2.5",
        }
    )
    decode_failure = SimpleNamespace(
        returncode=69,
        stdout="",
        stderr="corrupt decoded frame",
    )

    with patch(
        "performance._net.subprocess.run",
        side_effect=[probe, decode_failure],
    ):
        error = validate_video_artifact(str(video_path))

    assert "ffmpeg rejected" in (error or "")
    assert "corrupt decoded frame" in (error or "")


def test_video_validator_rejects_non_mp4_before_ffprobe(tmp_path):
    video_path = tmp_path / "take.mp4"
    video_path.write_text("<html>not a video</html>")

    with patch("performance._net.subprocess.run") as probe:
        error = validate_video_artifact(str(video_path))

    assert "missing ftyp" in (error or "")
    probe.assert_not_called()


def test_audio_validator_requires_decodable_stream_metadata(tmp_path):
    audio_path = tmp_path / "voice.mp3"
    audio_path.write_bytes(b"ID3fake")
    probe = _probe_payload(
        {
            "codec_type": "audio",
            "codec_name": "mp3",
            "sample_rate": "48000",
            "channels": 2,
            "duration": "2.5",
        }
    )

    with patch("performance._net.subprocess.run", return_value=probe):
        assert validate_audio_artifact(str(audio_path)) is None


def test_audio_validator_rejects_missing_audio_stream(tmp_path):
    audio_path = tmp_path / "voice.mp3"
    audio_path.write_bytes(b"ID3fake")
    probe = _probe_payload(
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 10,
            "height": 10,
        }
    )

    with patch("performance._net.subprocess.run", return_value=probe):
        assert "no audio stream" in (validate_audio_artifact(str(audio_path)) or "")


def test_audio_validator_rejects_decode_failure_after_valid_metadata(tmp_path):
    audio_path = tmp_path / "voice.mp3"
    audio_path.write_bytes(b"ID3fake")
    probe = _probe_payload(
        {
            "codec_type": "audio",
            "codec_name": "mp3",
            "sample_rate": "48000",
            "channels": 2,
            "duration": "2.5",
        }
    )
    decode_failure = SimpleNamespace(
        returncode=1,
        stdout="",
        stderr="invalid audio frame",
    )

    with patch(
        "performance._net.subprocess.run",
        side_effect=[probe, decode_failure],
    ):
        error = validate_audio_artifact(str(audio_path))

    assert "ffmpeg rejected" in (error or "")
    assert "invalid audio frame" in (error or "")


def test_atomic_publish_bytes_validates_before_replacing_destination(tmp_path):
    destination = tmp_path / "artifact.bin"
    destination.write_bytes(b"known-good")

    result = atomic_publish_bytes(
        b"provider-error",
        str(destination),
        max_bytes=1024,
        content_type="audio/mpeg",
        allowed_content_types=("audio/mpeg",),
        content_validator=lambda _path: "not decodable audio",
    )

    assert result is None
    assert destination.read_bytes() == b"known-good"
    assert list(tmp_path.glob(".safe-download-*.tmp")) == []


def test_atomic_publish_bytes_success_is_bounded_and_atomic(tmp_path):
    destination = tmp_path / "artifact.bin"
    result = atomic_publish_bytes(
        b"validated-payload",
        str(destination),
        max_bytes=1024,
        content_type="audio/mpeg; charset=binary",
        allowed_content_types=("audio/mpeg",),
        content_validator=lambda _path: None,
    )

    assert result == str(destination)
    assert destination.read_bytes() == b"validated-payload"


def test_publish_validated_file_requires_sibling_and_removes_rejected_stage(tmp_path):
    destination = tmp_path / "artifact.bin"
    destination.write_bytes(b"known-good")
    staged = tmp_path / "artifact.bin.part"
    staged.write_bytes(b"bad")

    result = publish_validated_file(
        str(staged),
        str(destination),
        content_validator=lambda _path: "invalid",
    )

    assert result is None
    assert destination.read_bytes() == b"known-good"
    assert not staged.exists()
