"""Confirms synth_driving_face_from_audio returns (path, provider_name)."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

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


# NF-7: FAL attempt removed — _synth_via_hedra must go straight to direct REST
# and must return None immediately when only FAL_KEY is present (no HEDRA_API_KEY).

def test_hedra_with_both_keys_does_not_call_fal_client(tmp_path, monkeypatch):
    """With both FAL_KEY and HEDRA_API_KEY set, _synth_via_hedra must NOT
    import or call fal_client — it goes straight to requests.post on
    https://api.hedra.com/v1/audio/talking-image."""
    audio = tmp_path / "a.wav"; audio.write_bytes(b"\x00")
    kf = tmp_path / "kf.png";   kf.write_bytes(b"\x00")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setenv("FAL_KEY", "fal-test-key")
    monkeypatch.setenv("HEDRA_API_KEY", "hedra-test-key")

    # Inject a fake fal_client into sys.modules so that any import/use would
    # be detectable — the real fal_client package may not be installed.
    fake_fal = MagicMock(name="fal_client")
    monkeypatch.setitem(sys.modules, "fal_client", fake_fal)

    # Stub out requests.post so the function short-circuits cleanly.
    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status_code = 503
    mock_response.text = "stub"

    from performance import driving_video as dv
    fake_settings = MagicMock()
    fake_settings.hedra_api_key = "hedra-test-key"
    with patch.object(dv, "settings", fake_settings):
        with patch("requests.post", return_value=mock_response) as mock_post:
            result = dv._synth_via_hedra(
                audio_path=str(audio),
                keyframe_path=str(kf),
                output_mp4=out,
                duration_s=5.0,
                shot_id="s1",
                video_id="v1",
            )

    # fal_client must NOT have been called at all
    fake_fal.upload_file.assert_not_called()
    fake_fal.subscribe.assert_not_called()

    # requests.post must have targeted the direct Hedra REST endpoint
    assert mock_post.called, "expected requests.post to be called for direct Hedra path"
    called_url = mock_post.call_args[0][0]
    assert "api.hedra.com" in called_url, f"expected api.hedra.com, got: {called_url}"

    # With a failed response it returns None
    assert result is None


def test_hedra_fal_only_key_returns_none_without_fal_attempt(tmp_path, monkeypatch):
    """With ONLY FAL_KEY (no HEDRA_API_KEY), _synth_via_hedra must return None
    immediately WITHOUT attempting any FAL call — strictly better than the old
    guaranteed-timeout-then-fail behaviour."""
    audio = tmp_path / "a.wav"; audio.write_bytes(b"\x00")
    kf = tmp_path / "kf.png";   kf.write_bytes(b"\x00")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setenv("FAL_KEY", "fal-test-key")
    monkeypatch.delenv("HEDRA_API_KEY", raising=False)

    fake_fal = MagicMock(name="fal_client")
    monkeypatch.setitem(sys.modules, "fal_client", fake_fal)

    from performance import driving_video as dv
    # settings is a frozen dataclass — patch the module-level name with a plain
    # object that has hedra_api_key="" so no real key leaks in.
    fake_settings = MagicMock()
    fake_settings.hedra_api_key = ""
    with patch.object(dv, "settings", fake_settings):
        with patch("requests.post") as mock_post:
            result = dv._synth_via_hedra(
                audio_path=str(audio),
                keyframe_path=str(kf),
                output_mp4=out,
                duration_s=5.0,
                shot_id="s1",
                video_id="v1",
            )

    assert result is None, "should return None when no HEDRA_API_KEY"
    fake_fal.subscribe.assert_not_called()
    fake_fal.upload_file.assert_not_called()
    mock_post.assert_not_called()
