"""Single source of truth for output aspect ratio → delivery dimensions.

Phase 1 of portrait/aspect-aware delivery
(docs/superpowers/specs/2026-06-07-portrait-aspect-delivery-design.md).
Pure module, stdlib only. Every surface that fixes a delivery dimension
(assembly, scorecard) and every gate (UI /api/config, settings PUT) imports
from here so dimensions + the supported-ratio set live in ONE place.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

ASPECT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
}
DEFAULT_ASPECT_RATIO = "16:9"

# The GATE. Phase 3's final task appends "9:16" once native generation lands.
SUPPORTED_ASPECT_RATIOS: list[str] = ["16:9"]


def resolve_output_dimensions(aspect_ratio: Optional[str]) -> tuple[int, int]:
    """Return (width, height) for ``aspect_ratio``.

    Unknown / empty / None → DEFAULT dims. Never raises — assembly and the
    scorecard must not crash on a bad or absent setting.
    """
    dims = ASPECT_DIMENSIONS.get(aspect_ratio or "")
    if dims is None:
        logger.debug("unknown aspect_ratio %r → default %s",
                     aspect_ratio, DEFAULT_ASPECT_RATIO)
        return ASPECT_DIMENSIONS[DEFAULT_ASPECT_RATIO]
    return dims


def is_portrait(aspect_ratio: Optional[str]) -> bool:
    """True when the resolved dimensions are taller than wide."""
    w, h = resolve_output_dimensions(aspect_ratio)
    return h > w


def is_supported(aspect_ratio: Optional[str]) -> bool:
    """True when ``aspect_ratio`` is a currently-offered ratio (the gate)."""
    return aspect_ratio in SUPPORTED_ASPECT_RATIOS


# FAL image_size is a named bucket, not pixel dims — map by orientation.
FAL_IMAGE_SIZE: dict[str, str] = {"16:9": "landscape_16_9", "9:16": "portrait_16_9"}


def portrait_swap(w: int, h: int, aspect_ratio: Optional[str]) -> tuple[int, int]:
    """Transpose (w, h) → (h, w) when ``aspect_ratio`` resolves to portrait.

    Lets each generation path keep its own tuned pixel budget, just rotated.
    Unknown / None / landscape → unchanged. Never raises (delegates to
    is_portrait → resolve_output_dimensions, which defaults to 16:9).
    """
    return (h, w) if is_portrait(aspect_ratio) else (w, h)


def fal_image_size(aspect_ratio: Optional[str]) -> str:
    """FAL's named image_size enum for the given aspect ratio (landscape default)."""
    return FAL_IMAGE_SIZE.get(aspect_ratio or "", "landscape_16_9")


def fal_aspect_ratio(aspect_ratio: Optional[str]) -> str:
    """FAL's aspect_ratio string for FLUX Kontext/Pro (landscape default).

    Unlike fal_image_size's named buckets, the Kontext/Pro APIs take a plain
    "W:H" string. Centralizes the orientation choice so every FAL caller
    (and Phase-3 video) routes through is_portrait, not an inline ternary.
    """
    return "9:16" if is_portrait(aspect_ratio) else "16:9"
