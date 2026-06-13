"""Integration seam: dialogue audio survives auto-RIFE THROUGH the controller.

THE COVERAGE GAP (director2 MAJOR finding, wf_d03785f4-cdc 2026-06-13; independently
re-flagged by the Pair-A operator, 12:22:00Z):

  test_rife_audio_remux.py proves the re-mux at the `generate_rife_interpolation`
  FUNCTION level, but never through the controller. test_auto_rife_finalize.py
  drives the real `_maybe_auto_rife` / `_finalize_motion_take` controller seam but
  MOCKS `generate_rife_interpolation` entirely
  (`patch("cinema.shots.controller.generate_rife_interpolation")`). So a silent
  regression INSIDE the real re-mux, reached THROUGH the controller, would pass
  every existing test undetected.

These tests bridge the two: they drive the REAL `ShotController._maybe_auto_rife`
into the REAL `generate_rife_interpolation` into the REAL `_restore_audio_track`,
mocking ONLY the fal cloud round-trip (upload / subscribe / safe_download). Real
ffmpeg/ffprobe build the fixtures and assert the final, take-rebound file STILL
carries an audio stream — i.e. a dialogue take is not silently muted end to end.

`cinema.shots.controller.generate_rife_interpolation` is the SAME object as
`lip_sync.generate_rife_interpolation` (imported at controller.py:94-96), so
patching the fal boundary inside `lip_sync` is seen by the real function even when
it is invoked from the controller.

The bug chain these guard (test_rife_audio_remux.py docstring + cinema_pipeline.py:734):
silent RIFE clip → take path rebinds to it → `dialogue_audio_in_clip=True` still
claims the clip carries audio → assembler suppresses the scene-TTS re-mux → silent
dialogue in the final export. The fix keeps the rebind target audio-bearing; here we
prove that holds through the controller, with real ffmpeg.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import types
from unittest.mock import MagicMock

import pytest

# Real ffmpeg/ffprobe are required to build fixtures and assert audio streams.
_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")


def _ensure_kling_native_patchable():
    """Guarantee kling_native.KlingNativeAPI exists (some sibling test files inject
    a bare stub module without the class). Mirrors test_auto_rife_finalize.py."""
    mod = sys.modules.get("kling_native")
    if mod is None:
        mod = types.ModuleType("kling_native")
        mod.KlingNativeAPI = MagicMock  # type: ignore[attr-defined]
        sys.modules["kling_native"] = mod
    elif not hasattr(mod, "KlingNativeAPI"):
        mod.KlingNativeAPI = MagicMock  # type: ignore[attr-defined]


_ensure_kling_native_patchable()


# --- real-ffmpeg fixture helpers (same contract as test_rife_audio_remux.py) -------
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


def _mock_fal_cloud(monkeypatch, cloud_returns_path):
    """Patch generate_rife_interpolation's cloud round-trip so safe_download drops
    `cloud_returns_path` (the VIDEO-ONLY RIFE result) at the requested dest. The
    re-mux that follows is REAL. Mirrors test_rife_audio_remux.py::_mock_cloud."""
    import lip_sync

    monkeypatch.setattr(lip_sync, "FAL_AVAILABLE", True, raising=False)
    # ENV_SETTINGS is a frozen dataclass — swap the reference (only .fal_key is read).
    monkeypatch.setattr(lip_sync, "ENV_SETTINGS", types.SimpleNamespace(fal_key="test-key"))
    fake_fal = MagicMock()
    fake_fal.upload_file.return_value = "https://fake/upload"
    fake_fal.subscribe.return_value = {"video": {"url": "https://fake/rife.mp4"}}
    monkeypatch.setattr(lip_sync, "fal_client", fake_fal, raising=False)

    def _fake_download(url, dest):
        shutil.copyfile(cloud_returns_path, dest)
        return dest

    monkeypatch.setattr(lip_sync, "safe_download", _fake_download)


def _make_ctrl(tmp_path):
    """A REAL ShotController, trimmed to what `_maybe_auto_rife` touches
    (`_take_output_path` → project_dir, `cost_tracker`, `project.get('id')`).
    Modeled on test_auto_rife_finalize.py::_setup_ctrl, kept self-contained so a
    peer edit to that sibling cannot break this seam test."""
    from cinema.shots.controller import ShotController

    project = {"id": "proj_rife_integ", "scenes": [], "global_settings": {}}

    core = MagicMock()
    core.project = project
    core.project_dir = str(tmp_path)
    core.continuity = MagicMock()
    cost = MagicMock()
    cost.is_over_budget.return_value = False
    core.cost_tracker = cost

    return ShotController(
        core=core, lifecycle=MagicMock(), host=MagicMock(), runstate=MagicMock()
    )


def _dialogue_take():
    """A finalized motion take that already carries its dialogue audio in-clip —
    the exact precondition under which a silent RIFE rebind muted the export."""
    return {
        "id": "take_dlg",
        "path": "",
        "metadata": {
            "shot_id": "sh1",
            "shot_type": "medium",
            "dialogue_audio_in_clip": True,
        },
    }


# --- the gap-closing assertions ---------------------------------------------------
class TestAutoRifeThroughControllerPreservesAudio:
    def test_dialogue_audio_survives_real_remux_through_controller(self, tmp_path, monkeypatch):
        """REAL _maybe_auto_rife → REAL generate_rife_interpolation → REAL
        _restore_audio_track: a dialogue take's audio must survive to the rebound
        output. This is the seam test_auto_rife_finalize.py mocks away."""
        ctrl = _make_ctrl(tmp_path)
        take = _dialogue_take()

        source = tmp_path / "source_with_dialogue.mp4"
        _make_clip(source, with_audio=True)
        assert _has_audio_stream(source), "fixture sanity: source must carry dialogue audio"

        # The fal cloud returns a VIDEO-ONLY RIFE result (its real behaviour).
        cloud_video_only = tmp_path / "rife_cloud_video_only.mp4"
        _make_clip(cloud_video_only, with_audio=False)
        assert not _has_audio_stream(cloud_video_only), "fixture sanity: cloud result is silent"
        _mock_fal_cloud(monkeypatch, cloud_video_only)

        # assess_motion_quality is not under test — force a below-threshold score so
        # RIFE fires. The re-mux is what we exercise for real.
        mq = {"smoothness_score": 0.2, "recommendation": "interpolate"}
        monkeypatch.setattr("phase_c_ffmpeg.assess_motion_quality", lambda *a, **k: mq)

        result = ctrl._maybe_auto_rife(
            str(source), take, "sh1", {"auto_rife_smoothness_threshold": 0.4}
        )

        # RIFE actually ran and the take rebound to the interpolated output...
        assert take["metadata"].get("auto_rife_applied") is True, "RIFE did not run through the controller"
        assert result != str(source), "expected the rebound RIFE output, not the original path"
        assert os.path.exists(result)
        # ...and THE POINT: the dialogue audio survived the real re-mux end to end.
        assert _has_audio_stream(result), (
            "auto-RIFE through the controller silently dropped the dialogue audio "
            "track — the dialogue-muting regression (1c9bfdc) is back"
        )
        # The clip genuinely carries audio, so the still-True flag is now CORRECT
        # (assembler's TTS suppression is right) rather than the silent-dialogue bug.
        assert take["metadata"]["dialogue_audio_in_clip"] is True

    def test_remux_failure_keeps_original_audio_clip_not_a_silent_one(self, tmp_path, monkeypatch):
        """If the re-mux fails, the controller must keep the ORIGINAL audio-bearing
        clip — never the silent RIFE output. Audio integrity over smoothing, proven
        through the real generate_rife_interpolation None-fallback (not a mock of it)."""
        ctrl = _make_ctrl(tmp_path)
        take = _dialogue_take()

        source = tmp_path / "source_with_dialogue.mp4"
        _make_clip(source, with_audio=True)

        cloud_video_only = tmp_path / "rife_cloud_video_only.mp4"
        _make_clip(cloud_video_only, with_audio=False)
        _mock_fal_cloud(monkeypatch, cloud_video_only)

        # Force ONLY the re-mux to fail; the rest of the real path runs.
        import lip_sync
        monkeypatch.setattr(lip_sync, "_restore_audio_track", lambda *a, **k: False)

        mq = {"smoothness_score": 0.2, "recommendation": "interpolate"}
        monkeypatch.setattr("phase_c_ffmpeg.assess_motion_quality", lambda *a, **k: mq)

        result = ctrl._maybe_auto_rife(
            str(source), take, "sh1", {"auto_rife_smoothness_threshold": 0.4}
        )

        assert result == str(source), "re-mux failure must keep the original clip"
        assert _has_audio_stream(result), "the kept original must still carry dialogue audio"
        assert "auto_rife_applied" not in take["metadata"]
