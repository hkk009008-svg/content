"""Fail-closed lip-sync prerequisite evidence."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from lip_sync import check_generation_prerequisites, check_overlay_prerequisites


def _probe(duration: float, *, width: int | None = None):
    streams = [] if width is None else [{"width": width, "height": 720}]
    return SimpleNamespace(
        stdout=json.dumps(
            {"format": {"duration": str(duration)}, "streams": streams}
        )
    )


def test_overlay_requires_measured_face_and_bounded_duration_ratio(tmp_path):
    video = tmp_path / "take.mp4"
    audio = tmp_path / "dialogue.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")

    with (
        patch("lip_sync.subprocess.run", side_effect=[_probe(4.0, width=1280), _probe(9.0)]),
        patch("lip_sync._detect_visible_face_in_video", return_value=True),
    ):
        result = check_overlay_prerequisites(str(video), str(audio))

    assert result.passed is False
    assert any("duration ratio exceeds 2x" in blocker for blocker in result.blockers)


def test_overlay_blocks_when_face_is_absent_or_unmeasurable(tmp_path):
    video = tmp_path / "take.mp4"
    audio = tmp_path / "dialogue.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")

    for face_state, expected in (
        (False, "No sufficiently large frontal face"),
        (None, "Could not verify face visibility"),
    ):
        with (
            patch("lip_sync.subprocess.run", side_effect=[_probe(4.0, width=1280), _probe(4.0)]),
            patch("lip_sync._detect_visible_face_in_video", return_value=face_state),
        ):
            result = check_overlay_prerequisites(str(video), str(audio))

        assert result.passed is False
        assert any(expected in blocker for blocker in result.blockers)


def test_overlay_passes_only_when_all_required_evidence_is_measured(tmp_path):
    video = tmp_path / "take.mp4"
    audio = tmp_path / "dialogue.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")

    with (
        patch("lip_sync.subprocess.run", side_effect=[_probe(4.0, width=1280), _probe(5.0)]),
        patch("lip_sync._detect_visible_face_in_video", return_value=True),
    ):
        result = check_overlay_prerequisites(str(video), str(audio))

    assert result.passed is True
    assert result.blockers == []


def test_generation_requires_dimensions_face_and_audio_probe(tmp_path):
    image = tmp_path / "portrait.png"
    audio = tmp_path / "dialogue.wav"
    image.write_bytes(b"image")
    audio.write_bytes(b"audio")
    opened = MagicMock(size=(320, 320))

    with (
        patch("PIL.Image.open", return_value=opened),
        patch("lip_sync._detect_visible_face_in_image", return_value=None),
        patch("lip_sync.subprocess.run", side_effect=OSError("ffprobe missing")),
    ):
        result = check_generation_prerequisites(str(image), str(audio))

    assert result.passed is False
    assert any("Image too small" in blocker for blocker in result.blockers)
    assert any("Could not verify face visibility" in blocker for blocker in result.blockers)
    assert any("Could not verify audio duration" in blocker for blocker in result.blockers)
