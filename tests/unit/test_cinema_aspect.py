"""Phase 1 — cinema/aspect.py: aspect→dims resolver + supported-ratio gate."""
import json
import shutil
import subprocess

import pytest

from cinema.aspect import (
    resolve_output_dimensions, is_portrait, is_supported,
    ASPECT_DIMENSIONS, DEFAULT_ASPECT_RATIO, SUPPORTED_ASPECT_RATIOS,
    portrait_swap, fal_image_size, fal_aspect_ratio, runway_ratio,
)


def test_resolve_landscape():
    assert resolve_output_dimensions("16:9") == (1920, 1080)


def test_resolve_portrait():
    assert resolve_output_dimensions("9:16") == (1080, 1920)


def test_resolve_unknown_empty_none_default_to_landscape():
    assert resolve_output_dimensions("4:3") == (1920, 1080)
    assert resolve_output_dimensions("") == (1920, 1080)
    assert resolve_output_dimensions(None) == (1920, 1080)


def test_is_portrait():
    assert is_portrait("9:16") is True
    assert is_portrait("16:9") is False
    assert is_portrait(None) is False


def test_is_supported_gate_includes_9_16():
    # T10 (Phase 3): portrait un-gated — 9:16 is now a supported delivery ratio.
    # Any other unlisted ratio (e.g. 4:3) remains unsupported.
    assert is_supported("16:9") is True
    assert is_supported("9:16") is True
    assert is_supported("4:3") is False


def test_default_ratio_is_supported_and_known():
    assert DEFAULT_ASPECT_RATIO in SUPPORTED_ASPECT_RATIOS
    assert DEFAULT_ASPECT_RATIO in ASPECT_DIMENSIONS


# --- assembly normalize filter (byte-identical 16:9 regression guard) ---
GOLDEN_16x9 = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
               "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30")


def test_normalize_filter_16x9_is_byte_identical():
    from cinema_pipeline import _normalize_filter
    assert _normalize_filter(1920, 1080) == GOLDEN_16x9


def test_normalize_filter_portrait():
    from cinema_pipeline import _normalize_filter
    assert _normalize_filter(1080, 1920) == (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps=30"
    )


# --- Phase 2 helpers: portrait_swap + fal_image_size ---

def test_portrait_swap_landscape_is_noop():
    assert portrait_swap(1344, 768, "16:9") == (1344, 768)
    assert portrait_swap(1024, 576, "16:9") == (1024, 576)
    assert portrait_swap(3840, 2160, "16:9") == (3840, 2160)


def test_portrait_swap_portrait_transposes():
    assert portrait_swap(1344, 768, "9:16") == (768, 1344)
    assert portrait_swap(1024, 576, "9:16") == (576, 1024)
    assert portrait_swap(3840, 2160, "9:16") == (2160, 3840)


def test_portrait_swap_unknown_and_none_are_noop():
    # unknown/None resolve to the default (16:9) → landscape → no transpose
    assert portrait_swap(1344, 768, None) == (1344, 768)
    assert portrait_swap(1344, 768, "") == (1344, 768)
    assert portrait_swap(1344, 768, "21:9") == (1344, 768)


def test_fal_image_size_maps_orientation():
    assert fal_image_size("16:9") == "landscape_16_9"
    assert fal_image_size("9:16") == "portrait_16_9"
    assert fal_image_size(None) == "landscape_16_9"
    assert fal_image_size("4:3") == "landscape_16_9"


def test_fal_aspect_ratio_maps_orientation():
    assert fal_aspect_ratio("16:9") == "16:9"
    assert fal_aspect_ratio("9:16") == "9:16"
    assert fal_aspect_ratio(None) == "16:9"
    assert fal_aspect_ratio("") == "16:9"
    assert fal_aspect_ratio("4:3") == "16:9"


# --- Phase 3 helpers: runway_ratio ---

def test_runway_ratio_landscape_is_default():
    assert runway_ratio("16:9", "gen4_turbo") == "1280:720"
    assert runway_ratio("16:9", "gen3a_turbo") == "1280:768"
    assert runway_ratio(None, "gen4_turbo") == "1280:720"
    assert runway_ratio("4:3", "gen3a_turbo") == "1280:768"


def test_runway_ratio_portrait_per_model():
    assert runway_ratio("9:16", "gen4_turbo") == "720:1280"
    assert runway_ratio("9:16", "gen3a_turbo") == "768:1280"


# --- Real-ffmpeg behavioral tests: normalize upscales sub-1080 portrait clips ---
# Filter-string correctness is covered by test_normalize_filter_portrait above.
# These tests prove ffmpeg's force_original_aspect_ratio=decrease UPSCALES a
# smaller source to the 1080×1920 target frame (a skeptic could doubt whether
# "decrease" upscales at all). They exercise the PRODUCTION function directly.

_HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _probe_dims(path: str):
    """Return (width, height) of the first video stream in *path*."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            path,
        ],
        capture_output=True, text=True, check=True, timeout=30,
    )
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return stream["width"], stream["height"]


def _make_portrait_clip(path: str, w: int, h: int):
    """Synthesise a 1-second yuv420p clip at *w*x*h* via ffmpeg lavfi testsrc."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi",
            "-i", f"testsrc=size={w}x{h}:duration=1:rate=30",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast",
            path,
        ],
        check=True, timeout=60,
    )


@pytest.mark.skipif(not _HAS_FFMPEG, reason="requires ffmpeg+ffprobe")
def test_normalize_upscales_720x1280_portrait_to_1080x1920(tmp_path):
    """720×1280 is exactly 9:16; scale factor 1.5 → 1080×1920 with no padding."""
    from cinema_pipeline import _normalize_filter

    src = str(tmp_path / "src_720x1280.mp4")
    out = str(tmp_path / "out_720x1280.mp4")

    _make_portrait_clip(src, 720, 1280)

    vf = _normalize_filter(1080, 1920)  # production filter, not hardcoded
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", src,
            "-vf", vf,
            "-frames:v", "1",
            out,
        ],
        check=True, timeout=60,
    )

    width, height = _probe_dims(out)
    assert width == 1080 and height == 1920, (
        f"Expected 1080×1920 after normalize, got {width}×{height} "
        f"(source was 720×1280; normalize did NOT upscale)"
    )


@pytest.mark.skipif(not _HAS_FFMPEG, reason="requires ffmpeg+ffprobe")
def test_normalize_upscales_768x1280_portrait_to_1080x1920(tmp_path):
    """768×1280 is NOT exactly 9:16; scales to 1080×1800 then letterbox-pads to 1080×1920."""
    from cinema_pipeline import _normalize_filter

    src = str(tmp_path / "src_768x1280.mp4")
    out = str(tmp_path / "out_768x1280.mp4")

    _make_portrait_clip(src, 768, 1280)

    vf = _normalize_filter(1080, 1920)  # production filter, not hardcoded
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", src,
            "-vf", vf,
            "-frames:v", "1",
            out,
        ],
        check=True, timeout=60,
    )

    width, height = _probe_dims(out)
    assert width == 1080 and height == 1920, (
        f"Expected 1080×1920 after normalize, got {width}×{height} "
        f"(source was 768×1280; normalize did NOT produce the correct padded frame)"
    )
