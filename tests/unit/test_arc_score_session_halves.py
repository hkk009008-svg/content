"""Unit tests for halves-mode helpers in scripts/_arc_score_session.py.

Tests cover the two pure (environment-independent) helpers:
  - collect_halves_artifacts: path list order + membership
  - format_halves_table: rendered table shape + values

The score path itself is environment-bound (DeepFace/ArcFace); its
verification is the logs/halves_rescore_20260612.{json,txt} artifact.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts._arc_score_session import collect_halves_artifacts, format_halves_table


def test_collect_halves_artifacts_all_dual_char():
    """collect_halves_artifacts returns all 9 dual-char artifact paths."""
    paths = collect_halves_artifacts()
    assert len(paths) == 9
    expected = [
        "logs/pass_a_multichar_FAILED_landscape_20260610.jpg",
        "logs/pass_a_multichar.jpg",
        "logs/s2_dual_n1.jpg",
        "logs/s2_dual_n2.jpg",
        "logs/s2_dual_n3.jpg",
        "logs/s2_dual_n4.jpg",
        "logs/s3_stack_sec35.jpg",
        "logs/s3_stack_sec45.jpg",
        "logs/s3_stack_sec55.jpg",
    ]
    assert paths == expected


def test_collect_halves_artifacts_no_single_char():
    """Single-char-only artifact (max_lora_live_check.jpg) is excluded from halves mode."""
    paths = collect_halves_artifacts()
    assert not any("max_lora_live_check" in p for p in paths)


def test_format_halves_table_header_present():
    """format_halves_table output includes the section header line."""
    rows = [
        {"artifact": "logs/foo.jpg", "half": "left", "ref": "man", "arc_score": 0.750, "note": ""},
    ]
    out = format_halves_table(rows)
    assert "HALVES MODE ARC SCORE TABLE" in out


def test_format_halves_table_score_formatted():
    """Arc scores appear as 3-decimal floats."""
    rows = [
        {"artifact": "logs/foo.jpg", "half": "left", "ref": "aria", "arc_score": 0.832, "note": ""},
    ]
    out = format_halves_table(rows)
    assert "0.832" in out


def test_format_halves_table_missing_score():
    """Missing score (arc_score=None) renders as dash placeholder."""
    rows = [
        {"artifact": "logs/missing.jpg", "half": "right", "ref": "man", "arc_score": None, "note": "MISSING"},
    ]
    out = format_halves_table(rows)
    assert "—" in out


def test_format_halves_table_note_included():
    """Notes are included in the rendered line."""
    rows = [
        {"artifact": "logs/err.jpg", "half": "left", "ref": "man", "arc_score": None, "note": "ERROR: oops"},
    ]
    out = format_halves_table(rows)
    assert "ERROR: oops" in out


def test_format_halves_table_multiple_rows():
    """Multiple rows each appear as separate lines in the output."""
    rows = [
        {"artifact": "logs/a.jpg", "half": "left", "ref": "man", "arc_score": 0.700, "note": ""},
        {"artifact": "logs/b.jpg", "half": "right", "ref": "aria", "arc_score": 0.800, "note": ""},
    ]
    out = format_halves_table(rows)
    assert "logs/a.jpg" in out
    assert "logs/b.jpg" in out
    lines = out.strip().split("\n")
    # header + divider + 2 data rows = at least 4 lines (plus the "===" title)
    assert len(lines) >= 4
