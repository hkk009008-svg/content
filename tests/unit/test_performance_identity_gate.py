"""Tests for performance/identity_gate.py — ArcFace gate on performance takes."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from performance.identity_gate import (
    validate_performance_take,
    DEFAULT_PERFORMANCE_FLOOR,
)


class TestValidatePerformanceTake:
    def test_missing_video_returns_none(self):
        assert validate_performance_take("/tmp/does_not_exist.mp4", "/tmp/anchor.png") is None

    def test_missing_anchor_returns_none(self, tmp_path):
        vid = tmp_path / "fake.mp4"
        vid.write_bytes(b"\x00" * 100)
        assert validate_performance_take(str(vid), "") is None

    @patch("performance.identity_gate._extract_sample_frame")
    @patch("performance.identity_gate._arcface_score")
    def test_returns_arc_score_when_both_present(self, mock_arc, mock_extract, tmp_path):
        vid = tmp_path / "fake.mp4"
        vid.write_bytes(b"\x00" * 100)
        anchor = tmp_path / "anchor.png"
        anchor.write_bytes(b"\x00" * 100)
        mock_extract.return_value = str(tmp_path / "frame.png")
        mock_arc.return_value = 0.83
        result = validate_performance_take(str(vid), str(anchor))
        assert result == pytest.approx(0.83)

    @patch("performance.identity_gate._extract_sample_frame", return_value=None)
    def test_returns_none_when_frame_extract_fails(self, _mock, tmp_path):
        vid = tmp_path / "fake.mp4"; vid.write_bytes(b"\x00" * 100)
        anchor = tmp_path / "a.png"; anchor.write_bytes(b"\x00" * 100)
        assert validate_performance_take(str(vid), str(anchor)) is None


class TestFloorConstant:
    def test_floor_is_sane(self):
        # Just guard against accidental 0.99 floors that would fail every take.
        assert 0.5 <= DEFAULT_PERFORMANCE_FLOOR <= 0.9
