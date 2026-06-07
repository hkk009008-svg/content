"""Phase 1 — cinema/aspect.py: aspect→dims resolver + supported-ratio gate."""
from cinema.aspect import (
    resolve_output_dimensions, is_portrait, is_supported,
    ASPECT_DIMENSIONS, DEFAULT_ASPECT_RATIO, SUPPORTED_ASPECT_RATIOS,
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


def test_is_supported_gate_excludes_9_16_until_phase3():
    assert is_supported("16:9") is True
    assert is_supported("9:16") is False
    assert is_supported("4:3") is False


def test_default_ratio_is_supported_and_known():
    assert DEFAULT_ASPECT_RATIO in SUPPORTED_ASPECT_RATIOS
    assert DEFAULT_ASPECT_RATIO in ASPECT_DIMENSIONS
