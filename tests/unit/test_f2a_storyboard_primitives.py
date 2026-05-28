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


def _make_tiny_mp4(path: str, duration_s: float = 3.0) -> None:
    """Create a minimal valid mp4 at *path* using ffmpeg lavfi (no input file)."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=size=64x48:duration={duration_s}:rate=10",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(duration_s),
            "-c:v", "libx264", "-c:a", "aac", "-shortest",
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

    def test_correct_number_of_ffmpeg_calls_mocked(self, tmp_path):
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

    def test_ffmpeg_call_structure_for_non_last_segment(self, tmp_path):
        """Non-last segment ffmpeg call includes -t (duration limit)."""
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

        # First call (non-last): must contain -t
        first_call = captured_calls[0]
        assert "-t" in first_call

        # Second call (last): must NOT contain -t
        last_call = captured_calls[1]
        assert "-t" not in last_call

    def test_output_filenames_are_zero_padded(self, tmp_path):
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

    def test_raises_runtime_error_on_ffmpeg_failure(self, tmp_path):
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

    def test_start_offsets_accumulate_correctly(self, tmp_path):
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

    @pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not available")
    def test_real_split_produces_correct_segment_count(self, tmp_path):
        """Integration: real ffmpeg split of a synthetic 6 s clip into 3 segments."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "combined.mp4"
        _make_tiny_mp4(str(src), duration_s=6.0)

        durations = [2.0, 2.0, 2.0]
        result = split_video_into_segments(
            source_path=str(src),
            durations=durations,
            output_dir=str(tmp_path / "segs"),
        )

        assert len(result) == 3
        for seg_path in result:
            assert os.path.exists(seg_path), f"segment file missing: {seg_path}"
            seg_dur = _video_duration(seg_path)
            # Stream-copy may drift by up to ~0.5 s at keyframe boundaries
            assert seg_dur >= 1.0, f"segment too short: {seg_dur:.2f}s"

    @pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not available")
    def test_real_split_last_segment_absorbs_remainder(self, tmp_path):
        """Last segment runs to end of video even when durations don't sum exactly."""
        from phase_c_ffmpeg import split_video_into_segments

        src = tmp_path / "combined.mp4"
        _make_tiny_mp4(str(src), duration_s=5.0)

        # Ask for two segments whose durations sum to 4.5 (< 5.0)
        durations = [2.0, 2.5]
        result = split_video_into_segments(
            source_path=str(src),
            durations=durations,
            output_dir=str(tmp_path / "segs"),
        )

        assert len(result) == 2
        last_dur = _video_duration(result[-1])
        # Last segment must contain the remainder (≥ 2.5 s, likely ~3.0 s)
        assert last_dur >= 2.0, f"last segment too short: {last_dur:.2f}s"


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
