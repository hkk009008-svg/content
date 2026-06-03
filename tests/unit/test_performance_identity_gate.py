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

from identity.types import IdentityValidationResult


def _skip_result():
    """An IdentityValidationResult with overall_score=None (skipped state, Part-3 T1 schema)."""
    return IdentityValidationResult(
        passed=True,
        overall_score=None,
        character_results={},
        frames_sampled=0,
        video_duration_seconds=0.0,
        shot_type="medium",
        threshold_used=0.7,
        skipped=True,
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


# ===================================================================
# TestArcfaceScoreSkipGuard — _arcface_score() None-score guard
# ===================================================================


class TestArcfaceScoreSkipGuard:
    """Regression: when validate_image returns a skipped result (overall_score=None),
    _arcface_score must return None WITHOUT logging an error (Part-3 T2, pre-skip).

    Before the guard: float(None) raises TypeError; the except-block catches it and
    returns None but prints "[PerformanceGate] ArcFace score failed …" — misleading.
    After the guard: early-return None before float(), no log line.
    """

    @patch("performance.identity_gate._get_validator")
    def test_skip_result_returns_none_without_error_log(self, mock_get_validator, capsys):
        """_arcface_score returns None cleanly on a skip result — no error log."""
        from performance.identity_gate import _arcface_score

        class _MockValidator:
            def validate_image(self, *args, **kwargs):
                return _skip_result()

        mock_get_validator.return_value = _MockValidator()

        result = _arcface_score("/fake/frame.png", "/fake/anchor.png")

        # Must return None (skip = no comparable face).
        assert result is None

        # Must NOT emit the "[PerformanceGate] ArcFace score failed" error line —
        # that marker is the observable signal that the old exception-path fired.
        captured = capsys.readouterr()
        assert "ArcFace score failed" not in captured.out, (
            "Detected old exception-path log — explicit None guard missing"
        )
