"""Pure-helper tests for scripts/_probe_halves_faces.py (no DeepFace import)."""
import pytest

from scripts._probe_halves_faces import (
    TINY_AREA_RATIO,
    classify_detection,
    format_probe_table,
)


class TestClassifyDetection:
    def test_whole_image_fallback_is_degenerate(self):
        # enforce_detection=False no-face fallback: bbox == crop (1px short)
        assert classify_detection(1919, 2159, 1920, 2160, 0.0) == "DEGENERATE"

    def test_degenerate_even_with_high_confidence(self):
        # pass_a right half emitted a whole-image box at conf 0.96
        assert classify_detection(1919, 2159, 1920, 2160, 0.96) == "DEGENERATE"

    def test_texture_patch_is_tiny(self):
        # the 59x59 blob that supplied pass_a left man 0.587
        assert classify_detection(59, 59, 1920, 2160, 0.97) == "TINY"

    def test_real_figure_is_ok(self):
        # pass_a left true figure: 867x867 of 1920x2160 (18.1%)
        assert classify_detection(867, 867, 1920, 2160, 0.96) == "OK"

    def test_tiny_boundary_is_exclusive(self):
        # exactly at the ratio -> OK; just under -> TINY
        w = h = int((TINY_AREA_RATIO * 1000 * 1000) ** 0.5)
        assert classify_detection(w + 1, h + 1, 1000, 1000, 0.9) == "OK"
        assert classify_detection(w - 1, h - 1, 1000, 1000, 0.9) == "TINY"


class TestFormatProbeTable:
    def test_one_row_renders_scores_and_class(self):
        rows = [{
            "crop": "x_left.jpg", "face_index": 0,
            "x": 1, "y": 2, "w": 59, "h": 59,
            "area_pct": 0.08, "confidence": 0.97,
            "man": 0.587, "aria": 0.43, "classification": "TINY",
        }]
        out = format_probe_table(rows)
        assert "x_left.jpg" in out
        assert "0.587" in out
        assert "TINY" in out

    def test_empty_rows_render_header_only(self):
        out = format_probe_table([])
        assert "HALVES PER-FACE PROBE" in out
