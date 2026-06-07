"""U3 — Final-media conformance: tests for measure_loudness, probe_final_media,
scorecard media block, and the _apply_final_loudnorm persist hook.

TDD: tests written before implementation.

Offline — subprocess and mutate_project are mocked; no GPU, no pod, no ffmpeg.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Helpers for fake subprocess results
# ---------------------------------------------------------------------------

def _fake_run_loudnorm_ok(cmd, *args, **kwargs):
    """Simulate ffmpeg pass-1 stdout that contains a loudnorm JSON blob."""
    result = MagicMock()
    result.returncode = 0
    result.stderr = (
        "some ffmpeg output\n"
        '{"input_i": "-16.20", "input_tp": "-2.30", "input_lra": "8.50",'
        ' "input_thresh": "-26.50", "target_offset": "0.15"}\n'
    )
    return result


def _fake_run_loudnorm_no_json(cmd, *args, **kwargs):
    result = MagicMock()
    result.returncode = 0
    result.stderr = "some ffmpeg output without any JSON blob"
    return result


def _fake_run_loudnorm_missing_keys(cmd, *args, **kwargs):
    result = MagicMock()
    result.returncode = 0
    result.stderr = '{"input_i": "-16.20"}'  # missing required keys
    return result


# ---------------------------------------------------------------------------
# §6 measure_loudness tests
# ---------------------------------------------------------------------------

class TestMeasureLoudness:
    """Tests for the new measure_loudness() extraction from two_pass_loudnorm."""

    def test_happy_path_returns_dict_with_required_keys(self, tmp_path):
        """measure_loudness returns a dict with input_i/tp/lra/thresh/offset."""
        fake_mp4 = tmp_path / "video.mp4"
        fake_mp4.write_bytes(b"fake")

        import subprocess as _subprocess
        with patch("phase_c_ffmpeg.subprocess.run", side_effect=_fake_run_loudnorm_ok) as mock_run:
            from phase_c_ffmpeg import measure_loudness
            result = measure_loudness(str(fake_mp4))

        assert result is not None
        assert result["input_i"] == "-16.20"
        assert result["input_tp"] == "-2.30"
        assert result["input_lra"] == "8.50"
        # Command should include print_format=json
        cmd = mock_run.call_args[0][0]
        assert "print_format=json" in " ".join(cmd)

    def test_missing_file_returns_none(self):
        """measure_loudness returns None if the file does not exist."""
        from phase_c_ffmpeg import measure_loudness
        result = measure_loudness("/nonexistent/path/video.mp4")
        assert result is None

    def test_no_json_in_stderr_returns_none(self, tmp_path):
        """measure_loudness returns None when ffmpeg emits no JSON blob."""
        fake_mp4 = tmp_path / "video.mp4"
        fake_mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run", side_effect=_fake_run_loudnorm_no_json):
            from phase_c_ffmpeg import measure_loudness
            result = measure_loudness(str(fake_mp4))

        assert result is None

    def test_missing_required_keys_returns_none(self, tmp_path):
        """measure_loudness returns None when the JSON lacks required keys."""
        fake_mp4 = tmp_path / "video.mp4"
        fake_mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run", side_effect=_fake_run_loudnorm_missing_keys):
            from phase_c_ffmpeg import measure_loudness
            result = measure_loudness(str(fake_mp4))

        assert result is None

    def test_timeout_returns_none(self, tmp_path):
        """measure_loudness returns None on subprocess.TimeoutExpired."""
        import subprocess
        fake_mp4 = tmp_path / "video.mp4"
        fake_mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=180)):
            from phase_c_ffmpeg import measure_loudness
            result = measure_loudness(str(fake_mp4))

        assert result is None

    def test_two_pass_loudnorm_still_works_after_extraction(self, tmp_path):
        """two_pass_loudnorm behavior is unchanged after measure_loudness extraction."""
        input_mp4 = tmp_path / "input.mp4"
        output_mp4 = tmp_path / "output.mp4"
        input_mp4.write_bytes(b"fake")

        def fake_run(cmd, *args, **kwargs):
            # pass-1 → loudnorm JSON; pass-2 → success
            if "null" in cmd or "-" in cmd:
                return _fake_run_loudnorm_ok(cmd, *args, **kwargs)
            # pass-2 normalize
            output_mp4.write_bytes(b"normalized")
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            return r

        with patch("phase_c_ffmpeg.subprocess.run", side_effect=fake_run):
            from phase_c_ffmpeg import two_pass_loudnorm
            # Should return True (normalization successful)
            result = two_pass_loudnorm(str(input_mp4), str(output_mp4))

        assert result is True
        assert output_mp4.exists()


# ---------------------------------------------------------------------------
# §6 probe_final_media tests
# ---------------------------------------------------------------------------

FFPROBE_CONFORMANT = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
        {"codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {"duration": "125.4"},
}

FFPROBE_WRONG_CODEC = {
    "streams": [
        {"codec_type": "video", "codec_name": "hevc", "width": 1920, "height": 1080},
        {"codec_type": "audio", "codec_name": "mp3"},
    ],
    "format": {"duration": "60.0"},
}

FFPROBE_WRONG_RES = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
        {"codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {"duration": "30.0"},
}

FFPROBE_NO_AUDIO = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
    ],
    "format": {"duration": "10.0"},
}

FFPROBE_NO_VIDEO = {
    "streams": [
        {"codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {"duration": "10.0"},
}

LOUDNESS_OK = {
    "input_i": "-14.10", "input_tp": "-1.80", "input_lra": "7.20",
    "input_thresh": "-24.10", "target_offset": "0.10",
}


def _make_ffprobe_run(fixture: dict):
    """Return a subprocess.run side_effect that emits the given ffprobe JSON."""
    def fake(cmd, *args, **kwargs):
        r = MagicMock()
        r.returncode = 0
        r.stdout = json.dumps(fixture)
        r.stderr = ""
        return r
    return fake


class TestProbeFinalMedia:
    """Tests for probe_final_media()."""

    def test_conformant_file_returns_full_dict(self, tmp_path):
        """Conformant file → both audio and format sub-dicts present."""
        mp4 = tmp_path / "final_cinema.mp4"
        mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run") as mock_run, \
             patch("phase_c_ffmpeg.measure_loudness", return_value=LOUDNESS_OK):
            mock_run.side_effect = _make_ffprobe_run(FFPROBE_CONFORMANT)
            from phase_c_ffmpeg import probe_final_media
            result = probe_final_media(str(mp4))

        assert result is not None
        assert result["audio"]["integrated_lufs"] == pytest.approx(-14.10)
        assert result["audio"]["true_peak_dbtp"] == pytest.approx(-1.80)
        assert result["audio"]["lra"] == pytest.approx(7.20)
        assert result["format"]["width"] == 1920
        assert result["format"]["height"] == 1080
        assert result["format"]["vcodec"] == "h264"
        assert result["format"]["acodec"] == "aac"
        assert result["format"]["duration_s"] == pytest.approx(125.4)

    def test_wrong_codec_still_returns_dict(self, tmp_path):
        """Wrong codec/res still returned — scorecard will show fail."""
        mp4 = tmp_path / "v.mp4"
        mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run") as mock_run, \
             patch("phase_c_ffmpeg.measure_loudness", return_value=LOUDNESS_OK):
            mock_run.side_effect = _make_ffprobe_run(FFPROBE_WRONG_CODEC)
            from phase_c_ffmpeg import probe_final_media
            result = probe_final_media(str(mp4))

        assert result is not None
        assert result["format"]["vcodec"] == "hevc"
        assert result["format"]["acodec"] == "mp3"

    def test_no_audio_stream_returns_partial(self, tmp_path):
        """No audio stream → format sub-dict present, audio absent."""
        mp4 = tmp_path / "v.mp4"
        mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run") as mock_run, \
             patch("phase_c_ffmpeg.measure_loudness", return_value=LOUDNESS_OK):
            mock_run.side_effect = _make_ffprobe_run(FFPROBE_NO_AUDIO)
            from phase_c_ffmpeg import probe_final_media
            result = probe_final_media(str(mp4))

        assert result is not None
        assert "format" in result
        # acodec would be None when no audio stream found
        assert result["format"]["acodec"] is None

    def test_no_video_stream_returns_partial(self, tmp_path):
        """No video stream → acodec present, width/height/vcodec absent (None)."""
        mp4 = tmp_path / "v.mp4"
        mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run") as mock_run, \
             patch("phase_c_ffmpeg.measure_loudness", return_value=LOUDNESS_OK):
            mock_run.side_effect = _make_ffprobe_run(FFPROBE_NO_VIDEO)
            from phase_c_ffmpeg import probe_final_media
            result = probe_final_media(str(mp4))

        assert result is not None
        assert result["format"]["vcodec"] is None
        assert result["format"]["acodec"] == "aac"

    def test_ffprobe_failure_loudness_ok_returns_partial(self, tmp_path):
        """ffprobe fails but loudness succeeds → audio block present, format absent."""
        import subprocess
        mp4 = tmp_path / "v.mp4"
        mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, "ffprobe")), \
             patch("phase_c_ffmpeg.measure_loudness", return_value=LOUDNESS_OK):
            from phase_c_ffmpeg import probe_final_media
            result = probe_final_media(str(mp4))

        assert result is not None
        assert "audio" in result
        assert "format" not in result

    def test_both_halves_fail_returns_none(self, tmp_path):
        """Both ffprobe and loudness fail → None."""
        import subprocess
        mp4 = tmp_path / "v.mp4"
        mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, "ffprobe")), \
             patch("phase_c_ffmpeg.measure_loudness", return_value=None):
            from phase_c_ffmpeg import probe_final_media
            result = probe_final_media(str(mp4))

        assert result is None

    def test_missing_file_returns_none(self):
        """Missing file → None without calling subprocess."""
        from phase_c_ffmpeg import probe_final_media
        result = probe_final_media("/nonexistent/path.mp4")
        assert result is None

    def test_loudness_failure_ffprobe_ok_returns_partial(self, tmp_path):
        """Loudness fails, ffprobe OK → format block present, audio absent."""
        mp4 = tmp_path / "v.mp4"
        mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run") as mock_run, \
             patch("phase_c_ffmpeg.measure_loudness", return_value=None):
            mock_run.side_effect = _make_ffprobe_run(FFPROBE_CONFORMANT)
            from phase_c_ffmpeg import probe_final_media
            result = probe_final_media(str(mp4))

        assert result is not None
        assert "format" in result
        assert "audio" not in result

    def test_loudness_RAISE_ffprobe_ok_returns_partial(self, tmp_path):
        """Lane V F2: measure_loudness RAISING (not just None) must discard only
        the audio half — the successful ffprobe format half survives."""
        mp4 = tmp_path / "v.mp4"
        mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run") as mock_run, \
             patch("phase_c_ffmpeg.measure_loudness",
                   side_effect=FileNotFoundError("ffmpeg not found")):
            mock_run.side_effect = _make_ffprobe_run(FFPROBE_CONFORMANT)
            from phase_c_ffmpeg import probe_final_media
            result = probe_final_media(str(mp4))

        assert result is not None
        assert "format" in result  # partial-results contract honored
        assert "audio" not in result

    def test_wrong_resolution_surfaced_by_probe(self, tmp_path):
        """Lane V F1: dedicated probe-level wrong-resolution coverage —
        probe_final_media surfaces the real (non-conformant) dimensions so the
        scorecard can mark format.pass False."""
        mp4 = tmp_path / "v.mp4"
        mp4.write_bytes(b"fake")

        with patch("phase_c_ffmpeg.subprocess.run") as mock_run, \
             patch("phase_c_ffmpeg.measure_loudness", return_value=LOUDNESS_OK):
            mock_run.side_effect = _make_ffprobe_run(FFPROBE_WRONG_RES)
            from phase_c_ffmpeg import probe_final_media
            result = probe_final_media(str(mp4))

        assert result is not None
        assert result["format"]["width"] == 1280
        assert result["format"]["height"] == 720


# ---------------------------------------------------------------------------
# §6 Scorecard media block tests
# ---------------------------------------------------------------------------

class TestScorecardMediaBlock:
    """Tests for the media block in build_capability_scorecard."""

    def _sc(self, **proj_overrides):
        from cinema.capability_scorecard import build_capability_scorecard
        proj = {"id": "p1", "name": "test", "characters": [],
                "scenes": [], "global_settings": {}}
        proj.update(proj_overrides)
        return build_capability_scorecard(proj, project_dir="/tmp/x")

    def test_no_media_report_gives_none(self):
        """No media_report key → media: None."""
        sc = self._sc()
        assert sc.get("media") is None

    def test_conformant_report_passes(self):
        """Conformant LUFS and codec → both pass True."""
        report = {
            "audio": {"integrated_lufs": -14.1, "true_peak_dbtp": -1.8, "lra": 7.2},
            "format": {"width": 1920, "height": 1080, "vcodec": "h264", "acodec": "aac",
                       "duration_s": 125.4},
            "loudnorm_applied": True, "measured_at": "2026-06-07T12:00:00Z",
        }
        sc = self._sc(media_report=report)
        assert sc["media"] is not None
        assert sc["media"]["lufs"]["pass"] is True
        assert sc["media"]["lufs"]["value"] == pytest.approx(-14.1)
        assert sc["media"]["lufs"]["target"] == pytest.approx(-14.0)
        assert sc["media"]["lufs"]["tolerance"] == pytest.approx(1.0)
        assert sc["media"]["format"]["pass"] is True
        assert sc["media"]["measured_at"] == "2026-06-07T12:00:00Z"

    def test_off_target_lufs_fails(self):
        """LUFS at -16.2 (delta 2.2 > 1.0 tolerance) → lufs.pass False."""
        report = {
            "audio": {"integrated_lufs": -16.2, "true_peak_dbtp": -2.0, "lra": 9.0},
            "format": {"width": 1920, "height": 1080, "vcodec": "h264", "acodec": "aac",
                       "duration_s": 60.0},
            "loudnorm_applied": False, "measured_at": "2026-06-07T12:00:00Z",
        }
        sc = self._sc(media_report=report)
        assert sc["media"]["lufs"]["pass"] is False
        assert sc["media"]["format"]["pass"] is True

    def test_at_tolerance_edge_passes(self):
        """-15.0 is exactly 1.0 LU from -14 → passes (abs(-15.0 - -14.0) == 1.0 <= 1.0)."""
        report = {
            "audio": {"integrated_lufs": -15.0, "true_peak_dbtp": -1.5, "lra": 7.0},
            "format": {"width": 1920, "height": 1080, "vcodec": "h264", "acodec": "aac",
                       "duration_s": 60.0},
            "loudnorm_applied": True, "measured_at": "2026-06-07T12:00:00Z",
        }
        sc = self._sc(media_report=report)
        assert sc["media"]["lufs"]["pass"] is True

    def test_just_over_tolerance_fails(self):
        """-15.01 is 1.01 LU from -14 → fails."""
        report = {
            "audio": {"integrated_lufs": -15.01, "true_peak_dbtp": -1.5, "lra": 7.0},
            "format": {"width": 1920, "height": 1080, "vcodec": "h264", "acodec": "aac",
                       "duration_s": 60.0},
            "loudnorm_applied": True, "measured_at": "2026-06-07T12:00:00Z",
        }
        sc = self._sc(media_report=report)
        assert sc["media"]["lufs"]["pass"] is False

    def test_wrong_codec_fails_format(self):
        """Wrong vcodec/acodec → format.pass False."""
        report = {
            "audio": {"integrated_lufs": -14.0, "true_peak_dbtp": -1.8, "lra": 7.0},
            "format": {"width": 1920, "height": 1080, "vcodec": "hevc", "acodec": "mp3",
                       "duration_s": 60.0},
            "loudnorm_applied": True, "measured_at": "2026-06-07T12:00:00Z",
        }
        sc = self._sc(media_report=report)
        assert sc["media"]["format"]["pass"] is False

    def test_wrong_resolution_fails_format(self):
        """1280×720 → format.pass False."""
        report = {
            "audio": {"integrated_lufs": -14.0, "true_peak_dbtp": -1.8, "lra": 7.0},
            "format": {"width": 1280, "height": 720, "vcodec": "h264", "acodec": "aac",
                       "duration_s": 60.0},
            "loudnorm_applied": True, "measured_at": "2026-06-07T12:00:00Z",
        }
        sc = self._sc(media_report=report)
        assert sc["media"]["format"]["pass"] is False

    def test_partial_report_audio_only(self):
        """report with only audio half → lufs block present, format block None."""
        report = {
            "audio": {"integrated_lufs": -14.0, "true_peak_dbtp": -1.8, "lra": 7.0},
            "loudnorm_applied": True, "measured_at": "2026-06-07T12:00:00Z",
        }
        sc = self._sc(media_report=report)
        assert sc["media"]["lufs"] is not None
        assert sc["media"]["format"] is None

    def test_partial_report_format_only(self):
        """report with only format half → format block present, lufs block None."""
        report = {
            "format": {"width": 1920, "height": 1080, "vcodec": "h264", "acodec": "aac",
                       "duration_s": 60.0},
            "loudnorm_applied": True, "measured_at": "2026-06-07T12:00:00Z",
        }
        sc = self._sc(media_report=report)
        assert sc["media"]["lufs"] is None
        assert sc["media"]["format"]["pass"] is True

    def test_malformed_report_gives_none(self):
        """Non-dict media_report → media: None (never raises)."""
        sc = self._sc(media_report="not-a-dict")
        assert sc["media"] is None

    def test_audio_lufs_and_format_codec_removed_from_future_dimensions(self):
        """audio_lufs and format_codec must NOT appear in future_dimensions."""
        sc = self._sc()
        assert "audio_lufs" not in sc["future_dimensions"]
        assert "format_codec" not in sc["future_dimensions"]

    def test_audit_only_fields_not_in_media_payload(self):
        """loudnorm_applied and lra/true_peak are audit-only; not in media payload."""
        report = {
            "audio": {"integrated_lufs": -14.1, "true_peak_dbtp": -1.8, "lra": 7.2},
            "format": {"width": 1920, "height": 1080, "vcodec": "h264", "acodec": "aac",
                       "duration_s": 60.0},
            "loudnorm_applied": True, "measured_at": "2026-06-07T12:00:00Z",
        }
        sc = self._sc(media_report=report)
        media = sc["media"]
        assert "loudnorm_applied" not in media
        # true_peak and lra are not in the lufs sub-block
        assert "true_peak_dbtp" not in (media.get("lufs") or {})
        assert "lra" not in (media.get("lufs") or {})


# ---------------------------------------------------------------------------
# §6 Persist hook tests (_apply_final_loudnorm with probe+persist)
# ---------------------------------------------------------------------------

class TestApplyFinalLoudnormPersistHook:
    """Tests for probe+persist behavior added to _apply_final_loudnorm."""

    def _make_pipeline(self, project_id="test_pid"):
        """Build a minimal CinemaPipeline for testing _apply_final_loudnorm."""
        from unittest.mock import MagicMock
        pipeline = MagicMock()
        pipeline.project = {"id": project_id}
        return pipeline

    def test_probe_called_after_loudnorm_success(self, tmp_path):
        """probe_final_media is called after successful loudnorm."""
        from cinema_pipeline import CinemaPipeline

        final_mp4 = tmp_path / "final_cinema.mp4"
        final_mp4.write_bytes(b"fake")
        normed = tmp_path / "final_cinema_loud.mp4"

        probe_result = {
            "audio": {"integrated_lufs": -14.1, "true_peak_dbtp": -1.8, "lra": 7.2},
            "format": {"width": 1920, "height": 1080, "vcodec": "h264", "acodec": "aac",
                       "duration_s": 125.4},
        }

        with patch("cinema_pipeline.two_pass_loudnorm", return_value=True) as mock_norm, \
             patch("cinema_pipeline.probe_final_media", return_value=probe_result) as mock_probe, \
             patch("cinema_pipeline.mutate_project") as mock_mutate, \
             patch("os.replace"), \
             patch("os.path.exists", return_value=True):

            pipeline = MagicMock(spec=CinemaPipeline)
            pipeline.project = {"id": "test_pid"}
            # Call the unbound method with our mock pipeline as self
            CinemaPipeline._apply_final_loudnorm(pipeline, str(final_mp4))

        mock_probe.assert_called_once_with(str(final_mp4))
        mock_mutate.assert_called_once()

    def test_probe_called_even_when_loudnorm_fails(self, tmp_path):
        """probe_final_media is called on the loudnorm-failed path too."""
        from cinema_pipeline import CinemaPipeline

        final_mp4 = tmp_path / "final_cinema.mp4"
        final_mp4.write_bytes(b"fake")

        probe_result = {
            "audio": {"integrated_lufs": -18.0, "true_peak_dbtp": -3.0, "lra": 10.0},
            "format": {"width": 1920, "height": 1080, "vcodec": "h264", "acodec": "aac",
                       "duration_s": 60.0},
        }

        with patch("cinema_pipeline.two_pass_loudnorm", return_value=False), \
             patch("cinema_pipeline.probe_final_media", return_value=probe_result) as mock_probe, \
             patch("cinema_pipeline.mutate_project") as mock_mutate, \
             patch("os.path.exists", return_value=True):

            pipeline = MagicMock(spec=CinemaPipeline)
            pipeline.project = {"id": "test_pid"}
            CinemaPipeline._apply_final_loudnorm(pipeline, str(final_mp4))

        mock_probe.assert_called_once_with(str(final_mp4))
        mock_mutate.assert_called_once()

    def test_probe_failure_does_not_propagate(self, tmp_path):
        """If probe_final_media raises, _apply_final_loudnorm continues normally."""
        from cinema_pipeline import CinemaPipeline

        final_mp4 = tmp_path / "final_cinema.mp4"
        final_mp4.write_bytes(b"fake")

        with patch("cinema_pipeline.two_pass_loudnorm", return_value=True), \
             patch("cinema_pipeline.probe_final_media",
                   side_effect=RuntimeError("ffprobe crashed")), \
             patch("cinema_pipeline.mutate_project") as mock_mutate, \
             patch("os.replace"), \
             patch("os.path.exists", return_value=True):

            pipeline = MagicMock(spec=CinemaPipeline)
            pipeline.project = {"id": "test_pid"}
            # Must not raise
            CinemaPipeline._apply_final_loudnorm(pipeline, str(final_mp4))

        # mutate_project should NOT have been called (probe failed before it)
        mock_mutate.assert_not_called()

    def test_mutate_failure_does_not_propagate(self, tmp_path):
        """If mutate_project raises, _apply_final_loudnorm continues normally."""
        from cinema_pipeline import CinemaPipeline

        final_mp4 = tmp_path / "final_cinema.mp4"
        final_mp4.write_bytes(b"fake")

        probe_result = {
            "audio": {"integrated_lufs": -14.1, "true_peak_dbtp": -1.8, "lra": 7.2},
            "format": {"width": 1920, "height": 1080, "vcodec": "h264", "acodec": "aac",
                       "duration_s": 125.4},
        }

        with patch("cinema_pipeline.two_pass_loudnorm", return_value=True), \
             patch("cinema_pipeline.probe_final_media", return_value=probe_result), \
             patch("cinema_pipeline.mutate_project",
                   side_effect=RuntimeError("db write failed")), \
             patch("os.replace"), \
             patch("os.path.exists", return_value=True):

            pipeline = MagicMock(spec=CinemaPipeline)
            pipeline.project = {"id": "test_pid"}
            # Must not raise
            CinemaPipeline._apply_final_loudnorm(pipeline, str(final_mp4))

    def test_mutate_payload_includes_loudnorm_applied_and_measured_at(self, tmp_path):
        """The persisted payload includes loudnorm_applied (bool) and measured_at (ISO str)."""
        from cinema_pipeline import CinemaPipeline
        import re

        final_mp4 = tmp_path / "final_cinema.mp4"
        final_mp4.write_bytes(b"fake")

        probe_result = {
            "audio": {"integrated_lufs": -14.1, "true_peak_dbtp": -1.8, "lra": 7.2},
            "format": {"width": 1920, "height": 1080, "vcodec": "h264", "acodec": "aac",
                       "duration_s": 125.4},
        }

        captured_mutator = []

        def capture_mutate(project_id, mutator_fn, **kwargs):
            captured_mutator.append(mutator_fn)

        with patch("cinema_pipeline.two_pass_loudnorm", return_value=True), \
             patch("cinema_pipeline.probe_final_media", return_value=probe_result), \
             patch("cinema_pipeline.mutate_project", side_effect=capture_mutate), \
             patch("os.replace"), \
             patch("os.path.exists", return_value=True):

            pipeline = MagicMock(spec=CinemaPipeline)
            pipeline.project = {"id": "test_pid"}
            CinemaPipeline._apply_final_loudnorm(pipeline, str(final_mp4))

        assert len(captured_mutator) == 1
        # Call the captured inner mutator against a minimal valid project dict
        fake_project = {"id": "test_pid", "name": "test", "scenes": [],
                        "characters": [], "locations": []}
        captured_mutator[0](fake_project)
        assert "media_report" in fake_project
        report = fake_project["media_report"]
        assert report["loudnorm_applied"] is True
        assert "measured_at" in report
        # measured_at should be ISO-like
        assert re.match(r"\d{4}-\d{2}-\d{2}T", report["measured_at"])


# ---------------------------------------------------------------------------
# §6 Aspect-ratio-aware format.pass tests
# ---------------------------------------------------------------------------

class TestMediaBlockAspectAware:
    """Phase 1: format.pass derives expected dims from project aspect_ratio."""

    def _report(self, w, h):
        return {"format": {"width": w, "height": h, "vcodec": "h264", "acodec": "aac"},
                "measured_at": "2026-06-07T00:00:00Z"}

    def test_landscape_project_1920x1080_passes(self):
        from cinema.capability_scorecard import _build_media_block
        proj = {"global_settings": {"aspect_ratio": "16:9"}, "media_report": self._report(1920, 1080)}
        assert _build_media_block(proj)["format"]["pass"] is True

    def test_portrait_project_1080x1920_passes(self):
        from cinema.capability_scorecard import _build_media_block
        proj = {"global_settings": {"aspect_ratio": "9:16"}, "media_report": self._report(1080, 1920)}
        assert _build_media_block(proj)["format"]["pass"] is True

    def test_portrait_project_landscape_file_fails(self):
        from cinema.capability_scorecard import _build_media_block
        proj = {"global_settings": {"aspect_ratio": "9:16"}, "media_report": self._report(1920, 1080)}
        assert _build_media_block(proj)["format"]["pass"] is False

    def test_missing_aspect_defaults_to_landscape(self):
        from cinema.capability_scorecard import _build_media_block
        proj = {"global_settings": {}, "media_report": self._report(1920, 1080)}
        assert _build_media_block(proj)["format"]["pass"] is True
