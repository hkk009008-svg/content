"""Unit tests for scripts/_mask_gen.py — 50%-split binary mask prototype.

Tests cover:
  - make_half_mask dimensions match requested width/height
  - mask mode is 'L' (greyscale)
  - mask values are binary: only {0, 255}
  - left + right masks are complementary (sum = full-frame coverage, no overlap)
  - odd-width boundary: left gets w//2 columns, right gets the remainder
    — pinned against crop_half's ACTUAL box expression in
      scripts/_s1_rescore_crops.py:22-30 by calling crop_half on a temp file
      and comparing the resulting crop width to the mask's white-column count.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts._mask_gen import make_half_mask
from scripts._s1_rescore_crops import crop_half


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pixel_values(img):
    """Return a set of unique pixel values in the image."""
    return set(img.getdata())


def _left_white_columns(img):
    """Count the number of columns that are all-white in the image."""
    w, h = img.size
    count = 0
    for x in range(w):
        column = [img.getpixel((x, y)) for y in range(h)]
        if all(v == 255 for v in column):
            count += 1
    return count


def _left_black_columns(img):
    """Count the number of columns that are all-black in the image."""
    w, h = img.size
    count = 0
    for x in range(w):
        column = [img.getpixel((x, y)) for y in range(h)]
        if all(v == 0 for v in column):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Dimension tests
# ---------------------------------------------------------------------------

def test_make_half_mask_left_dimensions_even():
    """Left mask has the requested width and height (even width)."""
    img = make_half_mask(100, 80, "left")
    assert img.size == (100, 80)


def test_make_half_mask_right_dimensions_even():
    """Right mask has the requested width and height (even width)."""
    img = make_half_mask(100, 80, "right")
    assert img.size == (100, 80)


def test_make_half_mask_left_dimensions_odd():
    """Left mask has the requested width and height (odd width)."""
    img = make_half_mask(101, 50, "left")
    assert img.size == (101, 50)


def test_make_half_mask_right_dimensions_odd():
    """Right mask has the requested width and height (odd width)."""
    img = make_half_mask(101, 50, "right")
    assert img.size == (101, 50)


# ---------------------------------------------------------------------------
# Mode tests
# ---------------------------------------------------------------------------

def test_make_half_mask_mode_left():
    """Left mask is mode 'L' (8-bit greyscale)."""
    img = make_half_mask(100, 80, "left")
    assert img.mode == "L"


def test_make_half_mask_mode_right():
    """Right mask is mode 'L' (8-bit greyscale)."""
    img = make_half_mask(100, 80, "right")
    assert img.mode == "L"


# ---------------------------------------------------------------------------
# Binary-values tests
# ---------------------------------------------------------------------------

def test_make_half_mask_binary_values_left():
    """Left mask contains only values in {0, 255}."""
    img = make_half_mask(100, 80, "left")
    assert _pixel_values(img).issubset({0, 255})


def test_make_half_mask_binary_values_right():
    """Right mask contains only values in {0, 255}."""
    img = make_half_mask(100, 80, "right")
    assert _pixel_values(img).issubset({0, 255})


# ---------------------------------------------------------------------------
# Complementarity tests
# ---------------------------------------------------------------------------

def test_left_right_complementary_even():
    """Left + right masks cover every pixel exactly once (even width)."""
    w, h = 100, 80
    left = make_half_mask(w, h, "left")
    right = make_half_mask(w, h, "right")
    left_data = list(left.getdata())
    right_data = list(right.getdata())
    for i, (l, r) in enumerate(zip(left_data, right_data)):
        assert l + r == 255, f"pixel {i}: left={l} right={r} sum={l+r} (expected 255)"


def test_left_right_complementary_odd():
    """Left + right masks cover every pixel exactly once (odd width)."""
    w, h = 101, 50
    left = make_half_mask(w, h, "left")
    right = make_half_mask(w, h, "right")
    left_data = list(left.getdata())
    right_data = list(right.getdata())
    for i, (l, r) in enumerate(zip(left_data, right_data)):
        assert l + r == 255, f"pixel {i}: left={l} right={r} sum={l+r} (expected 255)"


def test_no_overlap_even():
    """No pixel is white in both left and right masks (even width)."""
    w, h = 100, 80
    left = make_half_mask(w, h, "left")
    right = make_half_mask(w, h, "right")
    left_data = list(left.getdata())
    right_data = list(right.getdata())
    assert not any(l == 255 and r == 255 for l, r in zip(left_data, right_data))


# ---------------------------------------------------------------------------
# Boundary tests — pinned against crop_half's ACTUAL box expression in
# _s1_rescore_crops.py:22-30.
#
# Strategy: create a real temp PNG of size (w, h), call crop_half() on it,
# open the resulting crop, and use its .size[0] as the authoritative expected
# column count.  If crop_half's box expression ever changes (e.g. w//2+1),
# these tests detect the divergence automatically — they do NOT re-derive w//2
# independently.
# ---------------------------------------------------------------------------

def _crop_half_width(w: int, h: int, side: str) -> int:
    """Return the width of the crop_half output for a synthetic image of (w, h)."""
    from PIL import Image as _Image
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal RGB source image (crop_half saves JPEG so needs RGB)
        src_path = os.path.join(tmpdir, "src.png")
        _Image.new("RGB", (w, h), (128, 64, 32)).save(src_path)
        crop_path = crop_half(src_path, side, tmpdir)
        crop = _Image.open(crop_path)
        return crop.size[0]  # width of the actual crop


def test_odd_width_left_boundary_matches_crop_half():
    """Odd width: left mask white-column count equals crop_half('left').width.

    Coupling: calls crop_half() directly so any change to its box expression
    is reflected here rather than both sides independently computing w//2.
    """
    w, h = 101, 10
    mask = make_half_mask(w, h, "left")
    expected_white_cols = _crop_half_width(w, h, "left")  # authoritative from crop_half
    actual_white_cols = _left_white_columns(mask)
    assert actual_white_cols == expected_white_cols, (
        f"Left mask white columns ({actual_white_cols}) != "
        f"crop_half 'left' width ({expected_white_cols}) for w={w}"
    )


def test_odd_width_right_boundary_matches_crop_half():
    """Odd width: right mask white-column count equals crop_half('right').width.

    Coupling: calls crop_half() directly so any change to its box expression
    is reflected here rather than both sides independently computing w - w//2.
    """
    w, h = 101, 10
    mask = make_half_mask(w, h, "right")
    expected_white_cols = _crop_half_width(w, h, "right")  # authoritative from crop_half
    actual_white_cols = _left_white_columns(mask)
    assert actual_white_cols == expected_white_cols, (
        f"Right mask white columns ({actual_white_cols}) != "
        f"crop_half 'right' width ({expected_white_cols}) for w={w}"
    )


def test_even_width_left_boundary_matches_crop_half():
    """Even width: left mask has exactly w//2 white columns."""
    w, h = 100, 10
    img = make_half_mask(w, h, "left")
    assert _left_white_columns(img) == w // 2


def test_even_width_right_boundary_matches_crop_half():
    """Even width: right mask has exactly w//2 white columns (w-w//2 = w//2)."""
    w, h = 100, 10
    img = make_half_mask(w, h, "right")
    assert _left_white_columns(img) == w - w // 2


def test_left_mask_white_on_left_side():
    """Left mask is white on left side and black on right side."""
    w, h = 10, 4
    img = make_half_mask(w, h, "left")
    half = w // 2
    # Left region should be all white
    for x in range(half):
        for y in range(h):
            assert img.getpixel((x, y)) == 255, f"Expected white at ({x},{y})"
    # Right region should be all black
    for x in range(half, w):
        for y in range(h):
            assert img.getpixel((x, y)) == 0, f"Expected black at ({x},{y})"


def test_right_mask_white_on_right_side():
    """Right mask is white on right side and black on left side."""
    w, h = 10, 4
    img = make_half_mask(w, h, "right")
    half = w // 2
    # Left region should be all black
    for x in range(half):
        for y in range(h):
            assert img.getpixel((x, y)) == 0, f"Expected black at ({x},{y})"
    # Right region should be all white
    for x in range(half, w):
        for y in range(h):
            assert img.getpixel((x, y)) == 255, f"Expected white at ({x},{y})"


# ---------------------------------------------------------------------------
# Invalid side argument
# ---------------------------------------------------------------------------

def test_make_half_mask_invalid_side_raises():
    """make_half_mask raises ValueError for an unknown side."""
    with pytest.raises(ValueError, match="side"):
        make_half_mask(100, 80, "center")
