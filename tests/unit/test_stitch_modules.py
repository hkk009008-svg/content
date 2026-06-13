"""Tests for stitch_modules() concat-list safety (D4).

Two correctness properties of the FFmpeg concat-demuxer list file:

1. **Scoped, not shared** — the list file is derived from the output path, not a
   bare-CWD ``concat_list.txt``. Two stitches running from the same working
   directory for different projects must not clobber each other's list mid-run.
2. **No leak on failure** — the list file is removed even when ffmpeg fails
   (it must live in a ``finally``, not after a re-``raise``).

ffmpeg is fully mocked — no real subprocess, no real video.
"""
from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

import phase_c_ffmpeg


def _captured_list_file(cmd) -> str:
    """Return the path that ffmpeg's concat demuxer was told to read (-i <list>)."""
    return cmd[cmd.index("-i") + 1]


class TestStitchModulesConcatListScoping:
    def test_list_file_is_scoped_per_output_not_shared(self, tmp_path, monkeypatch):
        """Two different outputs must use two distinct concat-list paths.

        The bug: a bare-CWD ``concat_list.txt`` is shared across every stitch, so
        a concurrent stitch for another project overwrites the list mid-run.
        """
        monkeypatch.chdir(tmp_path)
        captured: dict[str, str] = {}

        def fake_run(cmd, **kwargs):
            out = cmd[-1]
            captured[out] = _captured_list_file(cmd)
            with open(out, "w") as f:  # simulate ffmpeg producing the output
                f.write("video")
            return subprocess.CompletedProcess(cmd, 0)

        with patch("phase_c_ffmpeg.subprocess.run", side_effect=fake_run):
            out_a = str(tmp_path / "projectA_final.mp4")
            out_b = str(tmp_path / "projectB_final.mp4")
            phase_c_ffmpeg.stitch_modules([str(tmp_path / "a1.mp4")], out_a)
            phase_c_ffmpeg.stitch_modules([str(tmp_path / "b1.mp4")], out_b)

        assert captured[out_a] != captured[out_b], (
            "concat list file is shared across outputs — concurrent stitches collide"
        )

    def test_list_file_cleaned_up_when_ffmpeg_fails(self, tmp_path, monkeypatch):
        """A failed ffmpeg run must propagate AND not leak the concat list file."""
        monkeypatch.chdir(tmp_path)
        captured: dict[str, str] = {}

        def fake_run_fail(cmd, **kwargs):
            captured["list_file"] = _captured_list_file(cmd)
            raise subprocess.CalledProcessError(1, cmd, stderr=b"boom")

        with patch("phase_c_ffmpeg.subprocess.run", side_effect=fake_run_fail):
            with pytest.raises(subprocess.CalledProcessError):
                phase_c_ffmpeg.stitch_modules(
                    [str(tmp_path / "a1.mp4")], str(tmp_path / "out.mp4")
                )

        list_file = captured["list_file"]
        if not os.path.isabs(list_file):  # bare name resolves against cwd (tmp_path)
            list_file = os.path.join(str(tmp_path), list_file)
        assert not os.path.exists(list_file), (
            f"concat list file leaked after ffmpeg failure: {list_file}"
        )
