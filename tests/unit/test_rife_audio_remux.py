"""Audio-preservation tests for generate_rife_interpolation (lip_sync.py).

THE BUG (verified 2026-06-13, operator2 adversarial workflow wf_19be47de-ffc):
fal-ai/rife/video returns VIDEO-ONLY output (its schema has no audio field; the
reference RIFE impl ships an explicit transferAudio() because bare RIFE strips
audio). generate_rife_interpolation downloaded that result verbatim with no
re-mux, so a RIFE pass on a lip-synced / native-audio dialogue clip silently
dropped the dialogue track. Default-on auto-RIFE (65e9b88) then rebinds the take
path to the silent clip, and the assembler suppresses the scene-TTS re-mux
because dialogue_audio_in_clip=True still claims the clip carries its audio →
silent dialogue in the final export.

These tests pin the fix: RIFE must restore the source clip's audio track.
They use REAL ffmpeg/ffprobe on tiny synthetic clips (only the fal cloud
round-trip is mocked) so they prove the actual re-mux works, not a mock of it.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

# Real ffmpeg/ffprobe are required to build fixtures and assert audio streams.
_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")


def _make_clip(path, *, with_audio: bool) -> None:
    """Build a 1s 64x64 test clip, optionally with a 440Hz sine audio track."""
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=10"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "aac"]
    cmd += ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-shortest", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


def _has_audio_stream(path) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return "audio" in out.stdout


def _mock_cloud(monkeypatch, cloud_returns_path):
    """Patch generate_rife_interpolation's cloud round-trip so safe_download
    drops `cloud_returns_path` (the video-only RIFE result) at the requested dest."""
    import types

    import lip_sync
    from unittest.mock import MagicMock

    monkeypatch.setattr(lip_sync, "FAL_AVAILABLE", True, raising=False)
    # ENV_SETTINGS is a frozen dataclass — replace the whole module reference with
    # a stub (generate_rife_interpolation only reads .fal_key) rather than mutating
    # a frozen field.
    monkeypatch.setattr(lip_sync, "ENV_SETTINGS", types.SimpleNamespace(fal_key="test-key"))
    fake_fal = MagicMock()
    fake_fal.upload_file.return_value = "https://fake/upload"
    fake_fal.subscribe.return_value = {"video": {"url": "https://fake/rife.mp4"}}
    monkeypatch.setattr(lip_sync, "fal_client", fake_fal, raising=False)

    def _fake_download(url, dest):
        shutil.copyfile(cloud_returns_path, dest)
        return dest

    monkeypatch.setattr(lip_sync, "safe_download", _fake_download)


def test_rife_restores_source_audio_track(tmp_path, monkeypatch):
    """RIFE on an audio-bearing clip must return a clip that STILL has audio.

    This is the dialogue-silence bug: the cloud returns video-only; without a
    re-mux the source audio is lost.
    """
    import lip_sync

    source = tmp_path / "source_with_audio.mp4"
    _make_clip(source, with_audio=True)
    assert _has_audio_stream(source), "fixture sanity: source must have audio"

    cloud_video_only = tmp_path / "rife_cloud_result.mp4"
    _make_clip(cloud_video_only, with_audio=False)
    _mock_cloud(monkeypatch, cloud_video_only)

    out = lip_sync.generate_rife_interpolation(str(source), str(tmp_path / "out.mp4"))

    assert out is not None
    assert _has_audio_stream(out), "RIFE output silently dropped the source audio track"


def test_rife_silent_source_stays_video_only(tmp_path, monkeypatch):
    """A genuinely silent (non-dialogue) source must still succeed and stay
    video-only — the audio re-mux is optional (-map 1:a:0?), no regression for
    the common non-dialogue path."""
    import lip_sync

    source = tmp_path / "silent_source.mp4"
    _make_clip(source, with_audio=False)
    assert not _has_audio_stream(source), "fixture sanity: source must be silent"

    cloud_video_only = tmp_path / "rife_cloud_result.mp4"
    _make_clip(cloud_video_only, with_audio=False)
    _mock_cloud(monkeypatch, cloud_video_only)

    out = lip_sync.generate_rife_interpolation(str(source), str(tmp_path / "out.mp4"))

    assert out is not None, "RIFE must still succeed on a silent clip"
    assert not _has_audio_stream(out)


def test_rife_remux_failure_returns_none(tmp_path, monkeypatch):
    """If the audio re-mux fails, generate_rife_interpolation returns None so the
    caller keeps the ORIGINAL audio-bearing clip rather than a silent RIFE one —
    audio integrity is preferred over smoothing."""
    import lip_sync

    source = tmp_path / "source_with_audio.mp4"
    _make_clip(source, with_audio=True)

    cloud_video_only = tmp_path / "rife_cloud_result.mp4"
    _make_clip(cloud_video_only, with_audio=False)
    _mock_cloud(monkeypatch, cloud_video_only)
    # Force the re-mux to fail.
    monkeypatch.setattr(lip_sync, "_restore_audio_track", lambda *a, **k: False)

    out = lip_sync.generate_rife_interpolation(str(source), str(tmp_path / "out.mp4"))

    assert out is None, "re-mux failure must surface as None (caller keeps original)"


def test_rife_temp_cleaned_on_unexpected_remux_exception(tmp_path, monkeypatch):
    """If the re-mux helper raises an UNEXPECTED exception (not the ffmpeg errors
    it catches internally), the .noaudio.mp4 temp must still be cleaned up
    (try/finally) and the call returns None so the caller keeps the original."""
    import lip_sync

    source = tmp_path / "source_with_audio.mp4"
    _make_clip(source, with_audio=True)
    cloud_video_only = tmp_path / "rife_cloud_result.mp4"
    _make_clip(cloud_video_only, with_audio=False)
    _mock_cloud(monkeypatch, cloud_video_only)

    def _boom(*a, **k):
        raise RuntimeError("unexpected re-mux failure")

    monkeypatch.setattr(lip_sync, "_restore_audio_track", _boom)

    out_path = tmp_path / "out.mp4"
    out = lip_sync.generate_rife_interpolation(str(source), str(out_path))

    assert out is None
    assert not (tmp_path / "out.mp4.noaudio.mp4").exists(), "temp file leaked on unexpected exception"
