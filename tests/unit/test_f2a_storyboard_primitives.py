"""Unit tests for F2a: storyboard split helper + reusable finalize-take helper.

Coverage:
  TestSplitVideoIntoSegments  — phase_c_ffmpeg.split_video_into_segments()
  TestFinalizeTakeHelper      — ShotController._finalize_motion_take()

All tests are fully offline — no real video APIs, no GPU.
ffmpeg subprocess is either mocked (for the split helper) or skipped if ffmpeg
is unavailable (using a real tiny synthetic clip when it IS available).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import types
from hashlib import md5
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers for split tests
# ---------------------------------------------------------------------------

def _ffmpeg_available() -> bool:
    """True if ffmpeg is on PATH and can be invoked."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _make_tiny_mp4(
    path: str,
    duration_s: float = 3.0,
    *,
    long_gop: bool = False,
) -> None:
    """Create a minimal valid mp4 at *path* using ffmpeg lavfi (no input file)."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"testsrc2=size=64x48:duration={duration_s}:rate=10",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-t", str(duration_s),
        "-c:v", "libx264",
    ]
    if long_gop:
        cmd += ["-g", "50", "-keyint_min", "50", "-sc_threshold", "0"]
    cmd += ["-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path]
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _make_short_video_with_long_audio(path: str) -> None:
    """Create a container whose audio is much longer than its video stream."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            "testsrc2=size=64x48:duration=3:rate=10",
            "-f", "lavfi", "-i",
            "sine=frequency=1000:sample_rate=44100:duration=15",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            path,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _video_duration(path: str) -> float:
    """Return video duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _first_frame_md5(path: str) -> str:
    """Return the decoded first frame hash for boundary-distinctness checks."""
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", path,
            "-map", "0:v:0", "-frames:v", "1",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ],
        capture_output=True,
        check=True,
    )
    return md5(result.stdout).hexdigest()


@pytest.fixture
def mocked_storyboard_media():
    """Keep command-shape unit tests focused on FFmpeg invocation."""
    with (
        patch(
            "phase_c_ffmpeg._probe_storyboard_video",
            return_value=(60.0, 0.1),
        ),
        patch(
            "phase_c_ffmpeg.validate_storyboard_segment",
            return_value=1.0,
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# TestSplitVideoIntoSegments
# ---------------------------------------------------------------------------

class TestSplitVideoIntoSegments:
    """Tests for phase_c_ffmpeg.split_video_into_segments."""

    def test_returns_empty_list_when_source_missing(self, tmp_path):
        """Missing source file → [] with no error."""
        from phase_c_ffmpeg import split_video_into_segments
        result = split_video_into_segments(
            source_path=str(tmp_path / "nonexistent.mp4"),
            durations=[2.0, 3.0],
            output_dir=str(tmp_path / "segs"),
        )
        assert result == []

    def test_returns_empty_list_when_durations_empty(self, tmp_path):
        """Empty durations list → [] (valid source path, but nothing to cut)."""
        from phase_c_ffmpeg import split_video_into_segments
        src = tmp_path / "src.mp4"
        src.write_bytes(b"fakecontent")  # just needs to exist
        result = split_video_into_segments(
            source_path=str(src),
            durations=[],
            output_dir=str(tmp_path / "segs"),
        )
        assert result == []

    def test_correct_number_of_ffmpeg_calls_mocked(
        self, tmp_path, mocked_storyboard_media,
    ):
        """Mocked subprocess: N durations → N ffmpeg calls, N output paths returned."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "storyboard.mp4"
        src.write_bytes(b"fakevideo")

        durations = [2.5, 3.5, 4.0]
        out_dir = str(tmp_path / "segs")

        captured_calls = []

        def mock_run(cmd, **kwargs):
            captured_calls.append(cmd)
            # Create the output file so os.path.abspath sees a path (doesn't need to exist)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=mock_run):
            result = split_video_into_segments(
                source_path=str(src),
                durations=durations,
                output_dir=out_dir,
            )

        assert len(result) == 3
        assert len(captured_calls) == 3

    def test_ffmpeg_call_structure_for_every_segment(
        self, tmp_path, mocked_storyboard_media,
    ):
        """Every segment is bounded and uses accurate output-side seek."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "storyboard.mp4"
        src.write_bytes(b"fakevideo")

        captured_calls = []

        def mock_run(cmd, **kwargs):
            captured_calls.append(cmd)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=mock_run):
            split_video_into_segments(
                source_path=str(src),
                durations=[2.0, 3.0],
                output_dir=str(tmp_path / "segs"),
            )

        # Every call, including the last, must have an explicit bound.
        first_call = captured_calls[0]
        assert "-t" in first_call
        last_call = captured_calls[1]
        assert "-t" in last_call
        for call_cmd in captured_calls:
            assert call_cmd.index("-i") < call_cmd.index("-ss")
            assert "-c" not in call_cmd
            assert call_cmd[call_cmd.index("-c:v") + 1] == "libx264"

    def test_output_filenames_are_zero_padded(
        self, tmp_path, mocked_storyboard_media,
    ):
        """Segment output paths use zero-padded indices: _000, _001, …"""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "storyboard.mp4"
        src.write_bytes(b"fakevideo")

        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            result = split_video_into_segments(
                source_path=str(src),
                durations=[1.0, 1.0, 1.0],
                output_dir=str(tmp_path / "segs"),
                stem="shot",
            )

        names = [os.path.basename(p) for p in result]
        assert names == ["shot_000.mp4", "shot_001.mp4", "shot_002.mp4"]

    def test_raises_runtime_error_on_ffmpeg_failure(
        self, tmp_path, mocked_storyboard_media,
    ):
        """ffmpeg failure (non-zero exit) → RuntimeError with stderr text."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "storyboard.mp4"
        src.write_bytes(b"fakevideo")

        exc = subprocess.CalledProcessError(1, ["ffmpeg"], stderr=b"codec error")
        with patch("subprocess.run", side_effect=exc):
            with pytest.raises(RuntimeError, match="codec error"):
                split_video_into_segments(
                    source_path=str(src),
                    durations=[2.0],
                    output_dir=str(tmp_path / "segs"),
                )

    def test_start_offsets_accumulate_correctly(
        self, tmp_path, mocked_storyboard_media,
    ):
        """The -ss flag for segment N equals the sum of all prior durations."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "storyboard.mp4"
        src.write_bytes(b"fakevideo")

        durations = [2.0, 3.0, 5.0]
        expected_starts = [0.0, 2.0, 5.0]
        captured_calls = []

        def mock_run(cmd, **kwargs):
            captured_calls.append(cmd)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=mock_run):
            split_video_into_segments(
                source_path=str(src),
                durations=durations,
                output_dir=str(tmp_path / "segs"),
            )

        for i, call_cmd in enumerate(captured_calls):
            ss_idx = call_cmd.index("-ss")
            actual_start = float(call_cmd[ss_idx + 1])
            assert abs(actual_start - expected_starts[i]) < 1e-9, (
                f"Segment {i}: expected start {expected_starts[i]}, got {actual_start}"
            )

    def test_short_source_is_rejected_before_any_ffmpeg_cut(self, tmp_path):
        """Source coverage is a precondition, not an eventual tail failure."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "storyboard.mp4"
        src.write_bytes(b"fakevideo")

        with (
            patch(
                "phase_c_ffmpeg._probe_storyboard_video",
                return_value=(3.0, 0.1),
            ),
            patch(
                "subprocess.run",
                side_effect=AssertionError("ffmpeg cut must not launch"),
            ),
        ):
            with pytest.raises(RuntimeError, match="does not cover"):
                split_video_into_segments(
                    source_path=str(src),
                    durations=[5.0, 5.0, 4.0, 1.0],
                    output_dir=str(tmp_path / "segs"),
                )

        assert not (tmp_path / "segs").exists()

    def test_source_two_frame_coverage_boundary_is_inclusive(
        self,
        tmp_path,
    ):
        """Source coverage consumes its frame tolerance without widening it."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "storyboard.mp4"
        src.write_bytes(b"fakevideo")
        accepted_dir = tmp_path / "accepted"
        cut_calls = []

        def capture_cut(command, **kwargs):
            del kwargs
            cut_calls.append(command)
            return MagicMock(returncode=0)

        with (
            patch(
                "phase_c_ffmpeg._probe_storyboard_video",
                return_value=(4.8000000005, 0.2),
            ),
            patch(
                "phase_c_ffmpeg.validate_storyboard_segment",
                return_value=5.0,
            ),
            patch("phase_c_ffmpeg.subprocess.run", side_effect=capture_cut),
        ):
            accepted = split_video_into_segments(
                source_path=str(src),
                durations=[5.0],
                output_dir=str(accepted_dir),
            )

        assert len(cut_calls) == 1
        assert accepted == [
            os.path.abspath(accepted_dir / "segment_000.mp4")
        ]

        rejected_dir = tmp_path / "rejected"
        with (
            patch(
                "phase_c_ffmpeg._probe_storyboard_video",
                return_value=(4.799998, 0.2),
            ),
            patch(
                "phase_c_ffmpeg.subprocess.run",
                side_effect=AssertionError(
                    "outside source tolerance launched a cut"
                ),
            ),
        ):
            with pytest.raises(RuntimeError, match="does not cover"):
                split_video_into_segments(
                    source_path=str(src),
                    durations=[5.0],
                    output_dir=str(rejected_dir),
                )

        assert not rejected_dir.exists()

    def test_validation_failure_cleans_only_deterministic_outputs(
        self, tmp_path,
    ):
        """A post-cut probe rejection removes every named invocation output."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "storyboard.mp4"
        src.write_bytes(b"fakevideo")
        out_dir = tmp_path / "segs"

        def write_partial_output(cmd, **kwargs):
            del kwargs
            with open(cmd[-1], "wb") as handle:
                handle.write(b"partial")
            return MagicMock(returncode=0)

        with (
            patch(
                "phase_c_ffmpeg._probe_storyboard_video",
                return_value=(10.0, 0.1),
            ),
            patch("subprocess.run", side_effect=write_partial_output),
            patch(
                "phase_c_ffmpeg.validate_storyboard_segment",
                side_effect=RuntimeError("invalid media"),
            ),
        ):
            with pytest.raises(RuntimeError, match="invalid media"):
                split_video_into_segments(
                    source_path=str(src),
                    durations=[2.0, 2.0],
                    output_dir=str(out_dir),
                )

        assert out_dir.exists()
        assert list(out_dir.iterdir()) == []

    def test_probe_rejects_video_stream_without_decoded_frames(self, tmp_path):
        """A declared video stream is insufficient when no frame decodes."""
        from phase_c_ffmpeg import _probe_storyboard_video

        src = tmp_path / "empty-stream.mp4"
        src.write_bytes(b"fakevideo")
        probe_result = MagicMock(
            stdout=(
                '{"streams":[{"codec_type":"video","duration":"5.0",'
                '"avg_frame_rate":"24/1","nb_read_frames":"0"}],'
                '"format":{"duration":"5.0"}}'
            )
        )

        with patch("subprocess.run", return_value=probe_result):
            with pytest.raises(RuntimeError, match="no decoded frames"):
                _probe_storyboard_video(str(src))

    def test_probe_ignores_container_duration_and_uses_frames_per_second(
        self,
        tmp_path,
    ):
        """Missing stream duration derives 3s, not the 15s container value."""
        from phase_c_ffmpeg import _probe_storyboard_video

        src = tmp_path / "audio-inflated-container.mkv"
        src.write_bytes(b"fakevideo")
        probe_result = MagicMock(
            stdout=(
                '{"streams":[{"codec_type":"video","duration":"N/A",'
                '"avg_frame_rate":"10/1","nb_read_frames":"30"}],'
                '"format":{"duration":"15.0"}}'
            )
        )

        with patch("subprocess.run", return_value=probe_result):
            duration_s, tolerance_s = _probe_storyboard_video(str(src))

        assert duration_s == 3.0
        assert tolerance_s == pytest.approx(0.2)

    @pytest.mark.parametrize("frame_rate", ["0/0", "N/A", "malformed"])
    def test_probe_derives_two_frame_tolerance_when_rate_is_missing(
        self,
        tmp_path,
        frame_rate,
    ):
        """A valid stream duration plus frame count still yields two frames."""
        from phase_c_ffmpeg import _probe_storyboard_video

        src = tmp_path / "missing-rate.mp4"
        src.write_bytes(b"fakevideo")
        probe_result = MagicMock(
            stdout=(
                '{"streams":[{"codec_type":"video","duration":"5.0",'
                f'"avg_frame_rate":"{frame_rate}",'
                '"nb_read_frames":"120"}]}'
            )
        )

        with patch("subprocess.run", return_value=probe_result):
            duration_s, tolerance_s = _probe_storyboard_video(str(src))

        assert duration_s == 5.0
        assert tolerance_s == pytest.approx(2.0 / 24.0)

    @pytest.mark.parametrize(
        "stem",
        [
            "",
            ".",
            "..",
            "../escaped",
            "nested/escaped",
            "/absolute/escaped",
            r"..\escaped",
            "%2e%2e%2fescaped",
            "%252e%252e%252fescaped",
            "%2e%2e%5cescaped",
        ],
    )
    def test_unsafe_stem_rejected_before_probe_or_output_creation(
        self,
        tmp_path,
        stem,
    ):
        """Caller-controlled names cannot escape the owned split directory."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "storyboard.mp4"
        src.write_bytes(b"fakevideo")
        out_dir = tmp_path / "segs"

        with patch(
            "phase_c_ffmpeg._probe_storyboard_video",
            side_effect=AssertionError("unsafe stem reached ffprobe"),
        ):
            with pytest.raises(RuntimeError, match="safe filename component"):
                split_video_into_segments(
                    source_path=str(src),
                    durations=[1.0],
                    output_dir=str(out_dir),
                    stem=stem,
                )

        assert not out_dir.exists()

    def test_symlink_output_directory_is_not_invocation_owned(
        self,
        tmp_path,
    ):
        """An empty external directory cannot be adopted through a symlink."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "storyboard.mp4"
        src.write_bytes(b"fakevideo")
        external_dir = tmp_path / "external"
        external_dir.mkdir()
        linked_dir = tmp_path / "linked"
        linked_dir.symlink_to(external_dir, target_is_directory=True)

        with patch(
            "phase_c_ffmpeg._probe_storyboard_video",
            return_value=(2.0, 0.1),
        ):
            with pytest.raises(RuntimeError, match="real invocation-owned"):
                split_video_into_segments(
                    source_path=str(src),
                    durations=[1.0],
                    output_dir=str(linked_dir),
                )

        assert list(external_dir.iterdir()) == []

    @pytest.mark.parametrize("duration", [10**1000, -(10**1000)])
    def test_huge_integer_duration_rejected_before_probe(
        self,
        tmp_path,
        duration,
    ):
        """JSON integers outside float range fail closed without subprocesses."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "storyboard.mp4"
        src.write_bytes(b"fakevideo")
        out_dir = tmp_path / "segs"

        with patch(
            "phase_c_ffmpeg._probe_storyboard_video",
            side_effect=AssertionError("invalid duration reached ffprobe"),
        ):
            with pytest.raises(RuntimeError, match="invalid duration"):
                split_video_into_segments(
                    source_path=str(src),
                    durations=[duration],
                    output_dir=str(out_dir),
                )

        assert not out_dir.exists()

    @pytest.mark.parametrize(
        "expected_duration",
        [
            float("nan"),
            float("inf"),
            float("-inf"),
            0.0,
            -1.0,
            10**1000,
        ],
    )
    def test_invalid_expected_duration_rejected_before_probe(
        self,
        expected_duration,
    ):
        """NaN and non-positive expectations cannot bypass mismatch checks."""
        from phase_c_ffmpeg import validate_storyboard_segment

        with patch(
            "phase_c_ffmpeg._probe_storyboard_video",
            side_effect=AssertionError("invalid expectation reached ffprobe"),
        ):
            with pytest.raises(RuntimeError, match="finite and positive"):
                validate_storyboard_segment(
                    "/unused/segment.mp4",
                    expected_duration,
                )

    def test_exact_two_frame_boundary_is_inclusive_despite_float_error(self):
        """A tiny representation error cannot reject the documented bound."""
        from phase_c_ffmpeg import validate_storyboard_segment

        with patch(
            "phase_c_ffmpeg._probe_storyboard_video",
            return_value=(5.2000000005, 0.2),
        ):
            assert validate_storyboard_segment("/segment.mp4", 5.0) == (
                5.2000000005
            )

    def test_duration_beyond_two_frame_boundary_is_rejected(self):
        """The comparison epsilon must not widen the documented tolerance."""
        from phase_c_ffmpeg import validate_storyboard_segment

        with patch(
            "phase_c_ffmpeg._probe_storyboard_video",
            return_value=(5.200002, 0.2),
        ):
            with pytest.raises(RuntimeError, match="duration mismatch"):
                validate_storyboard_segment("/segment.mp4", 5.0)

    @pytest.mark.parametrize(
        "durations",
        [
            [5.0, 5.0, 4.0, 1.0],
            [5.0, 5.0, 2.0, 1.0, 1.0, 1.0],
        ],
    )
    @pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not available")
    def test_real_split_matches_canonical_fifteen_second_plan(
        self, tmp_path, durations,
    ):
        """Real cuts match both canonical provider-capped allocations."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "combined.mp4"
        _make_tiny_mp4(str(src), duration_s=15.0, long_gop=True)

        result = split_video_into_segments(
            source_path=str(src),
            durations=durations,
            output_dir=str(tmp_path / "segs"),
        )

        assert len(result) == len(durations)
        for expected_duration, seg_path in zip(durations, result):
            assert os.path.exists(seg_path), f"segment file missing: {seg_path}"
            seg_dur = _video_duration(seg_path)
            assert seg_dur == pytest.approx(expected_duration, abs=0.2)

    @pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not available")
    def test_real_long_gop_split_has_bounded_distinct_segments(self, tmp_path):
        """Regression: input-side seek/copy produced cumulative duplicate tails."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "combined.mp4"
        _make_tiny_mp4(str(src), duration_s=6.0, long_gop=True)

        durations = [1.0, 1.0, 1.0, 3.0]
        result = split_video_into_segments(
            source_path=str(src),
            durations=durations,
            output_dir=str(tmp_path / "segs"),
        )

        assert [_video_duration(path) for path in result] == pytest.approx(
            durations,
            abs=0.2,
        )
        assert len({_first_frame_md5(path) for path in result}) == len(result)

    @pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not available")
    def test_short_source_fails_before_writing_any_segment(self, tmp_path):
        """A three-second provider result cannot satisfy a 15-second plan."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "short.mp4"
        _make_tiny_mp4(str(src), duration_s=3.0, long_gop=True)
        out_dir = tmp_path / "segs"

        with pytest.raises(RuntimeError, match="does not cover"):
            split_video_into_segments(
                source_path=str(src),
                durations=[5.0, 5.0, 4.0, 1.0],
                output_dir=str(out_dir),
            )

        assert not out_dir.exists()

    @pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not available")
    def test_long_audio_cannot_inflate_source_video_coverage(self, tmp_path):
        """A 15s container with only 3s of video fails before any cut."""
        from phase_c_ffmpeg import (
            _probe_storyboard_video,
            split_video_into_segments,
        )

        src = tmp_path / "short-video-long-audio.mkv"
        _make_short_video_with_long_audio(str(src))
        assert _video_duration(str(src)) > 14.0
        video_duration_s, _tolerance_s = _probe_storyboard_video(str(src))
        assert video_duration_s == pytest.approx(3.0, abs=0.01)

        out_dir = tmp_path / "segs"
        real_subprocess_run = subprocess.run

        def ffprobe_only(command, **kwargs):
            if command[0] == "ffmpeg":
                raise AssertionError("source coverage failure launched a cut")
            return real_subprocess_run(command, **kwargs)

        with patch(
            "phase_c_ffmpeg.subprocess.run",
            side_effect=ffprobe_only,
        ):
            with pytest.raises(RuntimeError, match="does not cover"):
                split_video_into_segments(
                    source_path=str(src),
                    durations=[5.0, 5.0, 4.0, 1.0],
                    output_dir=str(out_dir),
                )

        assert not out_dir.exists()


# ---------------------------------------------------------------------------
# TestFinalizeTakeHelper
# ---------------------------------------------------------------------------

def _build_controller_stub(project: dict):
    """Build a minimal ShotController with mocked host + core dependencies.

    Mirrors the pattern in test_iterate_endpoint.py._build_controller.
    """
    from cinema.shots.controller import ShotController

    host = MagicMock()
    host._refresh_project_snapshot.return_value = project
    host._rebuild_review_clips.return_value = None
    host._save_checkpoint.return_value = None
    host._resolve_take_path.return_value = "/fake/keyframe.jpg"

    lifecycle = MagicMock()
    runstate = MagicMock()
    runstate.shot_results = {}

    core = MagicMock()
    core.project = project
    core.project_dir = "/tmp/fake_project"
    core.continuity = MagicMock()

    mock_cost = MagicMock()
    mock_cost.is_over_budget.return_value = False
    core.cost_tracker = mock_cost

    ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
    return ctrl


def _make_scene_and_shot(scene_id="scene_1", shot_id="shot_1_0"):
    scene = {
        "id": scene_id,
        "shots": [
            {
                "id": shot_id,
                "characters_in_frame": [],
                "plan_status": "approved",
            }
        ],
    }
    shot = scene["shots"][0]
    return scene, shot


class TestFinalizeTakeHelper:
    """Tests for ShotController._finalize_motion_take.

    Verifies behavior contract for F2b: that calling _finalize_motion_take
    registers a take with correct metadata, updates shot_results, and records
    cost — all with real controller code, fully mocked dependencies.
    """

    def _setup(self, tmp_path, extra_shot_fields=None):
        """Return (ctrl, scene, shot, take, video_path) for tests."""
        from domain.project_manager import make_take

        scene, shot = _make_scene_and_shot()
        if extra_shot_fields:
            shot.update(extra_shot_fields)

        project = {
            "id": "proj_test",
            "scenes": [scene],
            "global_settings": {},
        }
        ctrl = _build_controller_stub(project)

        # Stub _mutate_shot to capture the appended take.
        stored = {}

        def _fake_mutate(shot_id, mutator, timeout=10):
            # Execute the mutator on a fake shot dict to capture what was appended.
            fake_shot_dict = {"motion_takes": []}
            from cinema.shots.controller import MutationResult
            result = mutator(scene, fake_shot_dict)
            stored["mutation_result"] = result
            stored["shot_after"] = fake_shot_dict
            return result.value

        ctrl._mutate_shot = MagicMock(side_effect=_fake_mutate)

        take = make_take(
            "motion",
            source_take_id="take_kf_001",
            metadata={
                "scene_id": scene["id"],
                "shot_id": shot["id"],
                "target_api": "KLING_NATIVE",
                "shot_type": "medium",
            },
        )

        # Real video file for os.path.exists checks
        video_file = tmp_path / "output.mp4"
        video_file.write_bytes(b"fakevideo")

        return ctrl, scene, shot, take, str(video_file), stored

    def test_registers_take_in_motion_takes(self, tmp_path):
        """_finalize_motion_take appends take to shot's motion_takes array."""
        ctrl, scene, shot, take, video_path, stored = self._setup(tmp_path)

        result = ctrl._finalize_motion_take(
            scene, shot, take, video_path,
            source_image="/fake/kf.jpg",
            target_api="KLING_NATIVE",
            cc={},
            settings={},
            resolved_shot_type="medium",
        )

        assert result["success"] is True
        assert ctrl._mutate_shot.call_count == 1

        # The mutator must have appended the take.
        shot_after = stored["shot_after"]
        assert len(shot_after["motion_takes"]) == 1
        assert shot_after["motion_takes"][0]["id"] == take["id"]

    def test_sets_take_path(self, tmp_path):
        """take['path'] is set to video_path before storing."""
        ctrl, scene, shot, take, video_path, stored = self._setup(tmp_path)

        ctrl._finalize_motion_take(
            scene, shot, take, video_path,
            source_image="/fake/kf.jpg",
            target_api="KLING_NATIVE",
            cc={},
            settings={},
            resolved_shot_type="medium",
        )

        assert take["path"] == video_path

    def test_updates_shot_results(self, tmp_path):
        """shot_results[shot_id] is updated with correct fields."""
        ctrl, scene, shot, take, video_path, stored = self._setup(tmp_path)
        source_img = "/fake/kf.jpg"

        ctrl._finalize_motion_take(
            scene, shot, take, video_path,
            source_image=source_img,
            target_api="KLING_NATIVE",
            cc={},
            settings={},
            resolved_shot_type="medium",
        )

        sr = ctrl._runstate.shot_results[shot["id"]]
        assert sr["video"] == video_path
        assert sr["image"] == source_img
        assert sr["status"] == "final_review"
        assert sr["take_id"] == take["id"]

    def test_records_cost_on_success(self, tmp_path):
        """cost_tracker.record_api_call is invoked once with motion_generation op."""
        ctrl, scene, shot, take, video_path, stored = self._setup(tmp_path)

        ctrl._finalize_motion_take(
            scene, shot, take, video_path,
            source_image="/fake/kf.jpg",
            target_api="VEO_NATIVE",
            cc={},
            settings={},
            resolved_shot_type="wide",
        )

        ctrl.cost_tracker.record_api_call.assert_called_once_with(
            "VEO_NATIVE",
            operation="motion_generation",
            shot_id=shot["id"],
            video_id="proj_test",
        )

    def test_continuity_validation_called_when_chars_and_ref_present(self, tmp_path):
        """continuity.validate_shot is called when characters_in_frame + primary_ref exist."""
        ctrl, scene, shot, take, video_path, stored = self._setup(
            tmp_path,
            extra_shot_fields={"characters_in_frame": ["char_1"]},
        )

        # Configure fake validate_shot result
        fake_result = MagicMock()
        fake_result.overall_score = 0.82
        ctrl.continuity.validate_shot.return_value = fake_result

        cc = {"primary_reference": "/ref/char.jpg"}

        result = ctrl._finalize_motion_take(
            scene, shot, take, video_path,
            source_image="/fake/kf.jpg",
            target_api="KLING_NATIVE",
            cc=cc,
            settings={},
            resolved_shot_type="close_up",
        )

        ctrl.continuity.validate_shot.assert_called_once_with(
            video_path,
            ["char_1"],
            shot_type="close_up",
            mode="standard",
            attempt=0,
            max_attempts=3,
        )
        assert result["identity_score"] == 0.82
        assert take["metadata"]["identity_score"] == 0.82

    def test_continuity_skipped_when_no_chars(self, tmp_path):
        """continuity.validate_shot is NOT called when characters_in_frame is empty."""
        ctrl, scene, shot, take, video_path, stored = self._setup(tmp_path)
        cc = {"primary_reference": "/ref/char.jpg"}

        ctrl._finalize_motion_take(
            scene, shot, take, video_path,
            source_image="/fake/kf.jpg",
            target_api="KLING_NATIVE",
            cc=cc,
            settings={},
            resolved_shot_type="medium",
        )

        ctrl.continuity.validate_shot.assert_not_called()

    def test_extra_metadata_merged_into_take(self, tmp_path):
        """extra_metadata kwarg is merged into take["metadata"]."""
        ctrl, scene, shot, take, video_path, stored = self._setup(tmp_path)

        ctrl._finalize_motion_take(
            scene, shot, take, video_path,
            source_image="/fake/kf.jpg",
            target_api="KLING_NATIVE",
            cc={},
            settings={},
            resolved_shot_type="medium",
            extra_metadata={"storyboard_segment_index": 2, "source_storyboard": "sb_take_xyz"},
        )

        assert take["metadata"]["storyboard_segment_index"] == 2
        assert take["metadata"]["source_storyboard"] == "sb_take_xyz"

    def test_provenance_fields_written(self, tmp_path):
        """parent_take_id and revised_prompt are stored on the take."""
        ctrl, scene, shot, take, video_path, stored = self._setup(tmp_path)

        ctrl._finalize_motion_take(
            scene, shot, take, video_path,
            source_image="/fake/kf.jpg",
            target_api="KLING_NATIVE",
            cc={},
            settings={},
            resolved_shot_type="medium",
            parent_take_id="take_parent_abc",
            revised_prompt="slow dolly in",
        )

        assert take.get("parent_take_id") == "take_parent_abc"
        assert take.get("revised_prompt") == "slow dolly in"

    def test_budget_gate_pauses_lifecycle_when_over(self, tmp_path):
        """lifecycle.pause() is called when cost_tracker reports over-budget."""
        ctrl, scene, shot, take, video_path, stored = self._setup(tmp_path)
        ctrl.cost_tracker.is_over_budget.return_value = True
        # Budget gate formats these as floats — must be real numbers, not MagicMock.
        ctrl.cost_tracker.spent_usd = 12.50
        ctrl.cost_tracker.budget_usd = 10.00

        ctrl._finalize_motion_take(
            scene, shot, take, video_path,
            source_image="/fake/kf.jpg",
            target_api="KLING_NATIVE",
            cc={},
            settings={},
            resolved_shot_type="medium",
        )

        ctrl._lifecycle.pause.assert_called_once()

    def test_return_shape_matches_generate_motion_take_contract(self, tmp_path):
        """Return dict has success=True, take, video, identity_score keys."""
        ctrl, scene, shot, take, video_path, stored = self._setup(tmp_path)

        result = ctrl._finalize_motion_take(
            scene, shot, take, video_path,
            source_image="/fake/kf.jpg",
            target_api="KLING_NATIVE",
            cc={},
            settings={},
            resolved_shot_type="medium",
        )

        assert result["success"] is True
        assert "take" in result
        assert "video" in result
        assert result["video"] == video_path
        assert "identity_score" in result
