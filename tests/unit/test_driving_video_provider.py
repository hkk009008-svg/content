"""Confirms synth_driving_face_from_audio returns (path, provider_name)."""
from __future__ import annotations

from unittest.mock import patch

from performance.driving_video import synth_driving_face_from_audio


def test_returns_tuple_with_provider(tmp_path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"\x00")
    kf = tmp_path / "kf.png";   kf.write_bytes(b"\x00")
    out = tmp_path / "out.mp4"

    with patch("performance.driving_video._synth_via_hedra", return_value=str(out)):
        result = synth_driving_face_from_audio(
            audio_path=str(audio), keyframe_path=str(kf), output_mp4=str(out),
        )
    assert result == (str(out), "hedra")


def test_returns_none_when_all_fail(tmp_path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"\x00")
    kf = tmp_path / "kf.png";   kf.write_bytes(b"\x00")
    out = tmp_path / "out.mp4"

    with patch("performance.driving_video._synth_via_hedra", return_value=None), \
         patch("performance.driving_video._synth_via_sadtalker", return_value=None):
        result = synth_driving_face_from_audio(
            audio_path=str(audio), keyframe_path=str(kf), output_mp4=str(out),
        )
    assert result is None


def test_returns_sadtalker_when_hedra_fails(tmp_path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"\x00")
    kf = tmp_path / "kf.png";   kf.write_bytes(b"\x00")
    out = tmp_path / "out.mp4"

    with patch("performance.driving_video._synth_via_hedra", return_value=None), \
         patch("performance.driving_video._synth_via_sadtalker", return_value=str(out)):
        result = synth_driving_face_from_audio(
            audio_path=str(audio), keyframe_path=str(kf), output_mp4=str(out),
        )
    assert result == (str(out), "sadtalker")
