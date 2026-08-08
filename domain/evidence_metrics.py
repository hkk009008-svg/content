"""Measurements for the evidence harness, and what each one can and cannot say.

WHY THESE AND NOT AN IDENTITY SCORE
-----------------------------------
ADR-092: the identity scorer INVERTS RANK off-angle. A real photograph of the
subject in profile scored 0.556 and "failed" the 0.70 gate while a generated
panel the subject confirmed was NOT him scored 0.570. So no claim about a turned
pose, a room, or a product may rest on GhostFaceNet, and every metric here is
chosen to be independent of it.

TWO METRICS, BECAUSE THERE ARE TWO DIFFERENT QUESTIONS
------------------------------------------------------
``structure_match`` is SPATIAL. It asks "is this the same picture?" — the same
things in the same places. That is the right question for "did the approved
keyframe reach the video model?", where the generated first frame should closely
resemble the frame the operator approved.

It correlates GRADIENT MAGNITUDE, not raw luminance, and that choice was forced
by measurement rather than taste. The first version correlated luminance
directly and scored two UNRELATED frames of different rooms as high as 0.874,
because a smooth wall and its lighting falloff dominate the correlation and
every interior frame has one. An instrument that cannot tell two different rooms
apart would have confirmed the keyframe hypothesis no matter what the provider
did. On gradients — which come from edges, i.e. from subjects and furniture, not
from smooth light — the same unrelated pairs score at most 0.157 while identical
frames still score 1.000 and a uniform exposure shift still scores 0.997.

The cost of that choice, stated plainly: gradient magnitude is polarity-blind,
so a colour-inverted frame reads as a perfect structural match. ``palette_match``
is what catches that case, which is one reason both are always reported.

``palette_match`` is deliberately NOT spatial. It asks "is this the same place,
lit the same way?" while ignoring where things sit in frame. That is the right
question for shot-to-shot continuity, where adjacent shots MUST differ in
framing — a spatial metric would score a correct scene change as a failure and
reward the pipeline for repeating a shot.

Using one where the other belongs is the failure mode this docstring exists to
prevent. A "continuity" number computed with ``structure_match`` would mostly measure
how similar two framings were, which is the opposite of what good coverage looks
like.

INSTRUMENT VALIDATION IS PART OF THE CONTRACT
---------------------------------------------
Each function's docstring states the known values it must reproduce, and
``tests/unit/test_evidence_metrics.py`` runs them. A metric is not trusted on an
unknown until it has reproduced a known — including the NEGATIVE known: that
``palette_match`` stays high under a crop, and that ``structure_match`` does not. That
pair is what proves each is measuring what it claims rather than "same file".

PURE
----
Arrays in, floats out. No file reading, no ffmpeg, no provider calls, so the
rules can be tested without a network or a GPU.
"""

from __future__ import annotations

import numpy as np

# Everything is compared at this resolution. Small enough that framing noise and
# codec detail do not dominate, large enough to keep gross composition.
_COMPARE_SIDE = 64

# Bins per RGB axis for the palette histogram. 8 gives 512 buckets: fine enough
# to separate "warm interior" from "cold daylight", coarse enough that JPEG
# quantisation and a re-render's ordinary noise do not scatter a colour across
# neighbouring bins.
_PALETTE_BINS = 8


def _as_rgb_array(image: np.ndarray) -> np.ndarray:
    """Accept H×W (gray), H×W×3 (RGB) or H×W×4 (RGBA); return float RGB."""

    array = np.asarray(image)
    if array.ndim == 2:
        array = np.stack([array] * 3, axis=-1)
    if array.ndim != 3 or array.shape[2] not in (3, 4):
        raise ValueError("expected a gray, RGB or RGBA image array")
    array = array[:, :, :3]
    return array.astype(np.float64)


def _resize_nearest(array: np.ndarray, side: int) -> np.ndarray:
    """Index-based resize. Deliberately dependency-free and deterministic —
    an interpolating resize would smooth away exactly the high-frequency
    difference a swimming texture shows up as."""

    height, width = array.shape[:2]
    if height == 0 or width == 0:
        raise ValueError("cannot compare an empty image")
    rows = (np.arange(side) * height // side).clip(0, height - 1)
    cols = (np.arange(side) * width // side).clip(0, width - 1)
    return array[rows][:, cols]


def _edge_map(image: np.ndarray) -> np.ndarray:
    """Gradient magnitude of downsampled luminance.

    Edges come from things — a subject, a doorway, a product — while a smooth
    wall and its light falloff produce almost none. Correlating here is what
    stops a shared background from dominating the score; see the module
    docstring for the measurement that forced it.
    """

    gray = _resize_nearest(_as_rgb_array(image), _COMPARE_SIDE).mean(axis=2)
    gy, gx = np.gradient(gray)
    return np.hypot(gx, gy)


def structure_match(first: np.ndarray, second: np.ndarray) -> float:
    """Normalised cross-correlation of gradient magnitude. SPATIAL.

    Range [-1, 1]; 1.0 means the same structure in the same places.

    Known values it must reproduce (see the tests):
      - identical images                 -> 1.0
      - a uniform exposure shift         -> still > 0.99
      - unrelated frames of other rooms  -> low, and measurably lower than the
                                            luminance version it replaced
      - an image vs its own crop         -> clearly below 1.0

    The crop case is what proves this responds to LAYOUT, and therefore that it
    must NOT be used to judge shot-to-shot continuity, where a layout change is
    correct and expected.
    """

    left = _edge_map(first)
    right = _edge_map(second)
    left = left - left.mean()
    right = right - right.mean()
    denominator = float(np.sqrt((left**2).sum() * (right**2).sum()))
    if denominator == 0.0:
        # One side has no structure at all. Correlation is undefined, not 1.0 —
        # a flat frame is a generation failure and must never read as a perfect
        # match, which is exactly what returning 1.0 here would make it.
        return 0.0
    return float((left * right).sum() / denominator)


def palette_match(first: np.ndarray, second: np.ndarray) -> float:
    """Histogram intersection over binned RGB. NOT spatial.

    Range [0, 1]; 1.0 means the same colours in the same proportions, wherever
    they sit in the frame. This is the shot-to-shot continuity metric: two
    adjacent shots of one scene should share a palette and a light while
    differing in framing.

    Known values it must reproduce:
      - identical images                 -> 1.0
      - an image vs its own crop         -> stays HIGH (framing-insensitive)
      - an image vs a hue-shifted copy   -> drops sharply
      - a red field vs a blue field      -> near 0

    The crop case and the hue case together are the validation: without both, a
    number could be responding to file identity rather than to colour.
    """

    def _histogram(image: np.ndarray) -> np.ndarray:
        array = _as_rgb_array(image)
        binned = np.clip(
            (array / 256.0 * _PALETTE_BINS).astype(np.int64), 0, _PALETTE_BINS - 1
        )
        flat = (
            binned[:, :, 0] * _PALETTE_BINS**2
            + binned[:, :, 1] * _PALETTE_BINS
            + binned[:, :, 2]
        ).ravel()
        counts = np.bincount(flat, minlength=_PALETTE_BINS**3).astype(np.float64)
        total = counts.sum()
        return counts / total if total else counts

    return float(np.minimum(_histogram(first), _histogram(second)).sum())


def temporal_drift(frames: list[np.ndarray]) -> float:
    """Mean successive-frame dissimilarity across a clip. Range [0, 2].

    0 means a frozen video; a small positive number means ordinary motion; a
    large one means the picture is being re-invented frame to frame, which is
    what a swimming logo or a morphing face looks like numerically.

    It cannot separate "large motion" from "instability" — a whip pan and a
    morphing face both read high. It is therefore a screening number for
    comparing two arms of the SAME shot with the same camera move, never an
    absolute quality score, and the harness only ever reports it as a delta
    between matched arms.

    Known values: a constant clip -> 0.0; a clip alternating between two
    unrelated frames -> clearly higher than a clip of one repeated frame.
    """

    if len(frames) < 2:
        return 0.0
    steps = [1.0 - structure_match(a, b) for a, b in zip(frames, frames[1:])]
    return float(sum(steps) / len(steps))


def summarise(values: list[float]) -> dict[str, float]:
    """Mean, min and spread, so an arm cannot be sold on its best frame alone.

    A single mean hides the failure that matters: one badly broken frame in an
    otherwise clean clip is a re-render, and averaging buries it.
    """

    if not values:
        return {"n": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0, "spread": 0.0}
    array = np.asarray(values, dtype=np.float64)
    return {
        "n": float(array.size),
        "mean": float(array.mean()),
        "min": float(array.min()),
        "max": float(array.max()),
        "spread": float(array.max() - array.min()),
    }
