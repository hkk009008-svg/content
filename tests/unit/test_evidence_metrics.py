"""Instrument validation. Every metric reproduces a KNOWN value before it is
trusted on an unknown one.

This file is the reason the evidence harness is allowed to report numbers at
all. The recurring failure in this project has not been the system, it has been
the apparatus: an exit code read through a pipe reporting `tail`'s status, a
`grep -c` counting its own shell, a test patching a method name that does not
exist, a suite run concurrently with the edits it was measuring. Each read
plausibly and was wrong.

The two validations that matter most here are the NEGATIVE ones — the crop
cases. `structure_match` must FALL under a crop and `palette_match` must NOT.
Without
that pair, either function could be responding to "same file" rather than to the
property it claims to measure, and a continuity number computed with the wrong
one would mostly report how similar two framings were — the opposite of what
good shot coverage looks like.
"""

from __future__ import annotations

import numpy as np
import pytest

from domain.evidence_metrics import (
    palette_match,
    structure_match,
    summarise,
    temporal_drift,
)


def _scene(seed: int, side: int = 128) -> np.ndarray:
    """A ROOM, not a noise field: one dominant lit surface plus a few local
    elements.

    The fixture shape is load-bearing. The first version of these tests used a
    grid of independent random colours, and under a crop its PALETTE genuinely
    changed — so `test_palette_match_SURVIVES_a_crop` failed against a metric
    that was actually fine. A real frame is mostly one lit surface, which is
    exactly why the crop preserves its palette and why a naive luminance
    correlation could not tell two different rooms apart (see the module
    docstring). Modelling that here is what let both problems surface.
    """

    rng = np.random.default_rng(seed)
    wall = np.array(rng.integers(60, 200, size=3), dtype=np.float64)
    falloff = np.linspace(0.75, 1.25, side)[:, None, None]
    image = np.repeat((wall[None, None, :] * falloff).clip(0, 255), side, axis=1)
    for _ in range(4):
        height, width = rng.integers(10, 26, size=2)
        top, left = rng.integers(0, side - 26, size=2)
        image[top:top + height, left:left + width] = rng.integers(0, 255, size=3)
    return image.astype(np.uint8)


def _crop(image: np.ndarray, fraction: float = 0.6) -> np.ndarray:
    """A different FRAMING of the same content — what an adjacent shot is."""

    side = image.shape[0]
    keep = int(side * fraction)
    offset = (side - keep) // 2
    return image[offset:offset + keep, offset:offset + keep]


# ---------------------------------------------------------------------------
# structure_match — spatial
# ---------------------------------------------------------------------------

def test_identical_images_correlate_perfectly() -> None:
    image = _scene(1)
    assert structure_match(image, image) == pytest.approx(1.0, abs=1e-9)


def test_unrelated_rooms_do_not() -> None:
    """The measurement that forced the gradient rewrite.

    Correlating raw luminance scored unrelated rooms as high as 0.874, because
    every interior frame is dominated by a wall and its falloff. An instrument
    that cannot separate two different rooms would confirm the keyframe
    hypothesis whatever the provider did. On gradients the same pairs stay low.
    """

    scores = [abs(structure_match(_scene(s), _scene(s + 100))) for s in range(20)]
    assert max(scores) < 0.35


def test_an_inverted_image_reads_as_the_same_STRUCTURE() -> None:
    """A stated limitation, pinned so it cannot be forgotten.

    Gradient magnitude is polarity-blind: an inverted frame has identical edges,
    so this metric calls it a perfect structural match. That is correct for the
    question it answers ("same things in the same places") and useless as a
    quality verdict on its own — which is why palette_match, which collapses on
    the same pair, is always reported beside it.
    """

    image = _scene(3)
    inverted = (255 - image.astype(np.int64)).astype(np.uint8)
    assert structure_match(image, inverted) == pytest.approx(1.0, abs=1e-6)
    assert palette_match(image, inverted) < 0.2


def test_a_uniform_exposure_shift_does_not_move_it() -> None:
    """Zero-meaning is deliberate: a slightly brighter render of the same shot
    is the same shot, and a metric that called it a different one would reject
    correct footage."""

    image = _scene(4).astype(np.int64)
    brighter = np.clip(image + 20, 0, 255)
    assert structure_match(image, brighter) > 0.98


def test_a_flat_frame_is_not_a_perfect_match() -> None:
    """A blank output is a generation FAILURE. Correlation is undefined against
    a flat field, and returning 1.0 there would make the worst possible clip
    score best."""

    flat = np.full((64, 64, 3), 128, dtype=np.uint8)
    assert structure_match(_scene(5), flat) == 0.0
    assert structure_match(flat, flat) == 0.0


def test_structure_match_FALLS_under_a_crop() -> None:
    """THE NEGATIVE VALIDATION for this metric.

    A crop is the same place seen with different framing — exactly what an
    adjacent shot in a scene is. structure_match must notice, which is what makes it
    the right instrument for "did the keyframe reach the model" and the WRONG
    one for "are these two shots the same scene".
    """

    scores = [structure_match(_scene(s), _crop(_scene(s))) for s in range(20)]
    assert max(scores) < 0.5


# ---------------------------------------------------------------------------
# palette_match — deliberately not spatial
# ---------------------------------------------------------------------------

def test_identical_images_match_fully() -> None:
    image = _scene(7)
    assert palette_match(image, image) == pytest.approx(1.0, abs=1e-9)


def test_opposite_colours_do_not_match() -> None:
    red = np.zeros((64, 64, 3), dtype=np.uint8)
    red[:, :, 0] = 240
    blue = np.zeros((64, 64, 3), dtype=np.uint8)
    blue[:, :, 2] = 240
    assert palette_match(red, blue) < 0.05


def test_a_hue_shift_drops_it_sharply() -> None:
    """Proves it responds to COLOUR, so a scene relit between shots is caught."""

    scores = [palette_match(_scene(s), _scene(s)[:, :, ::-1]) for s in range(20)]
    assert max(scores) < 0.7


def test_palette_match_SURVIVES_a_crop() -> None:
    """THE NEGATIVE VALIDATION for this metric, and the whole reason it exists.

    Two adjacent shots of one scene MUST differ in framing. A continuity metric
    that punished that would reward the pipeline for repeating a shot. Combined
    with the hue test above, this shows the number tracks palette and not layout
    — and combined with test_structure_match_FALLS_under_a_crop, it shows the two
    metrics genuinely measure different things rather than being two spellings
    of "same file".
    """

    scores = [palette_match(_scene(s), _crop(_scene(s))) for s in range(20)]
    assert min(scores) > 0.6


def test_the_two_metrics_disagree_on_the_same_pair() -> None:
    """The pair, stated as one assertion: on a crop, one falls and one holds.

    If this ever fails, the harness is reporting one measurement twice under two
    names and every 'continuity' conclusion drawn from it is void.
    """

    for seed in range(20):
        image = _scene(seed)
        cropped = _crop(image)
        assert structure_match(image, cropped) < 0.5, seed
        assert palette_match(image, cropped) > 0.6, seed


# ---------------------------------------------------------------------------
# temporal_drift
# ---------------------------------------------------------------------------

def test_a_frozen_clip_has_no_drift() -> None:
    frame = _scene(11)
    assert temporal_drift([frame] * 5) == pytest.approx(0.0, abs=1e-9)


def test_a_thrashing_clip_drifts_more_than_a_still_one() -> None:
    a, b = _scene(12), _scene(13)
    assert temporal_drift([a, b, a, b]) > temporal_drift([a, a, a, a])


def test_a_single_frame_cannot_drift() -> None:
    assert temporal_drift([_scene(14)]) == 0.0
    assert temporal_drift([]) == 0.0


# ---------------------------------------------------------------------------
# summarise
# ---------------------------------------------------------------------------

def test_the_summary_exposes_the_worst_frame_not_just_the_mean() -> None:
    """One badly broken frame in an otherwise clean clip is a re-render, and a
    mean buries it."""

    stats = summarise([0.95, 0.96, 0.10, 0.94])
    assert stats["min"] == pytest.approx(0.10)
    assert stats["mean"] > 0.5           # the mean looks fine...
    assert stats["spread"] > 0.8         # ...and the spread says it is not
    assert stats["n"] == 4


def test_an_empty_summary_claims_nothing() -> None:
    assert summarise([]) == {
        "n": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0, "spread": 0.0,
    }


# ---------------------------------------------------------------------------
# Shape tolerance — real frames arrive in whatever the codec produced
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("shape", [(40, 90, 3), (90, 40, 3), (33, 33)])
def test_mismatched_and_odd_shapes_still_compare(shape) -> None:
    """A 1080p keyframe against a 720p video frame is the ordinary case, and a
    grayscale frame is a real codec outcome."""

    rng = np.random.default_rng(15)
    odd = rng.integers(0, 255, size=shape, dtype=np.uint8)
    assert -1.0 <= structure_match(odd, _scene(16)) <= 1.0
    assert 0.0 <= palette_match(odd, _scene(16)) <= 1.0


def test_an_empty_image_is_refused_rather_than_scored() -> None:
    with pytest.raises(ValueError):
        structure_match(np.zeros((0, 10, 3), dtype=np.uint8), _scene(17))
