"""Confirms synth_driving_face_from_audio returns (path, provider_name)."""
from __future__ import annotations

from unittest.mock import patch

from performance.driving_video import synth_driving_face_from_audio


def test_modeb_has_no_hedra():
    import performance.driving_video as dv
    src = __import__("inspect").getsource(dv)
    assert "_synth_via_hedra" not in src
    assert "hedra" not in dv._DRIVING_FACE_BASE_COST_USD
    assert "hedra" not in dv._DRIVING_FACE_COST_PER_SECOND_USD


def test_returns_tuple_with_provider(tmp_path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"\x00")
    kf = tmp_path / "kf.png";   kf.write_bytes(b"\x00")
    out = tmp_path / "out.mp4"

    with patch("performance.driving_video._synth_via_sadtalker", return_value=str(out)):
        result = synth_driving_face_from_audio(
            audio_path=str(audio), keyframe_path=str(kf), output_mp4=str(out),
        )
    assert result == (str(out), "sadtalker")


def test_returns_none_when_all_fail(tmp_path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"\x00")
    kf = tmp_path / "kf.png";   kf.write_bytes(b"\x00")
    out = tmp_path / "out.mp4"

    with patch("performance.driving_video._synth_via_sadtalker", return_value=None):
        result = synth_driving_face_from_audio(
            audio_path=str(audio), keyframe_path=str(kf), output_mp4=str(out),
        )
    assert result is None


def test_engine_sadtalker_explicit(tmp_path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"\x00")
    kf = tmp_path / "kf.png";   kf.write_bytes(b"\x00")
    out = tmp_path / "out.mp4"

    with patch("performance.driving_video._synth_via_sadtalker", return_value=str(out)):
        result = synth_driving_face_from_audio(
            audio_path=str(audio), keyframe_path=str(kf), output_mp4=str(out),
            engine="sadtalker",
        )
    assert result == (str(out), "sadtalker")
