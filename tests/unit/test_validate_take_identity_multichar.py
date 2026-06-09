"""TDD: `_validate_take_identity` validates ALL characters in frame.

The motion-take identity gate passed `[chars_in_frame[0]]` only — a slice
carried over verbatim through the ShotController extraction (4db9b8a) from
the pre-mixin monolith; no recorded decision backs it. The downstream chain
is fully multi-character capable (`ContinuityEngine.validate_shot` builds
one config per character that has a registered reference image;
`IdentityValidator.validate_video` samples frames per character and
averages per-character best similarities into `overall_score`, tracking
`matched` per character). Net effect of the slice: in a two-character
dialogue shot, character B's identity drift sailed through unvalidated.

The helper extracts step 1 of `_finalize_motion_take` so this seam is
unit-testable at all — the parent method needs the full pipeline scaffold
(mutations, checkpoints, budget gate, progress events).

Characters without a registered reference are skipped inside
`validate_shot` (config list), so passing background extras cannot
false-fail the gate.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from cinema.shots.controller import ShotController


# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------

class _BareController(ShotController):
    """Mixin host stub: only what _validate_take_identity touches.

    ShotController exposes ``continuity`` as a read-only property delegating
    to the pipeline host, so the stub overrides the property.
    """

    def __init__(self, continuity):
        self._test_continuity = continuity

    @property
    def continuity(self):
        return self._test_continuity


def _result(overall=0.81, per_char=None):
    """Duck-typed stand-in for IdentityValidationResult."""
    return SimpleNamespace(
        overall_score=overall,
        character_results=per_char if per_char is not None else {},
    )


def _run(chars, *, primary_ref="ref.png", result=None, settings=None):
    continuity = MagicMock()
    continuity.validate_shot.return_value = result if result is not None else _result()
    ctl = _BareController(continuity)
    take = {"metadata": {}}
    score = ctl._validate_take_identity(
        "video.mp4",
        {"characters_in_frame": chars},
        {"primary_reference": primary_ref},
        settings if settings is not None else {},
        "medium",
        take,
    )
    return score, take, continuity


# ---------------------------------------------------------------------------
# The multi-char regression: full list reaches validate_shot
# ---------------------------------------------------------------------------

class TestFullCharacterListValidated:
    def test_all_chars_in_frame_passed_not_just_first(self):
        _, _, continuity = _run(["char_a", "char_b", "char_c"])
        args, kwargs = continuity.validate_shot.call_args
        assert args[1] == ["char_a", "char_b", "char_c"]

    def test_single_char_shot_unchanged(self):
        _, _, continuity = _run(["char_a"])
        args, _ = continuity.validate_shot.call_args
        assert args[1] == ["char_a"]

    def test_validation_params_forwarded(self):
        _, _, continuity = _run(
            ["char_a", "char_b"], settings={"identity_retry_max": 5}
        )
        _, kwargs = continuity.validate_shot.call_args
        assert kwargs["shot_type"] == "medium"
        assert kwargs["mode"] == "standard"
        assert kwargs["attempt"] == 0
        assert kwargs["max_attempts"] == 5


# ---------------------------------------------------------------------------
# Skip + score semantics (behavior-identical to the inline block)
# ---------------------------------------------------------------------------

class TestSkipAndScore:
    def test_no_chars_in_frame_skips_validation(self):
        score, take, continuity = _run([])
        assert score == 0.0
        continuity.validate_shot.assert_not_called()
        assert "identity_score" not in take["metadata"]

    def test_no_primary_reference_skips_validation(self):
        score, _, continuity = _run(["char_a"], primary_ref=None)
        assert score == 0.0
        continuity.validate_shot.assert_not_called()

    def test_score_and_metadata_from_overall_score(self):
        score, take, _ = _run(["char_a"], result=_result(overall=0.77))
        assert score == 0.77
        assert take["metadata"]["identity_score"] == 0.77

    def test_overall_none_yields_zero(self):
        # _skipped_result carries overall_score=None (no fabricated score).
        score, take, _ = _run(["char_a"], result=_result(overall=None))
        assert score == 0.0
        assert take["metadata"]["identity_score"] == 0.0


# ---------------------------------------------------------------------------
# Per-character outcomes surfaced for review
# ---------------------------------------------------------------------------

class TestPerCharacterMetadata:
    def test_per_char_scores_recorded(self):
        per_char = {
            "char_a": SimpleNamespace(best_similarity=0.91, matched=True),
            "char_b": SimpleNamespace(best_similarity=0.42, matched=False),
        }
        _, take, _ = _run(
            ["char_a", "char_b"], result=_result(overall=0.665, per_char=per_char)
        )
        assert take["metadata"]["identity_per_char"] == {
            "char_a": 0.91, "char_b": 0.42,
        }
        assert take["metadata"]["identity_all_matched"] is False

    def test_all_matched_true_when_every_char_matches(self):
        per_char = {
            "char_a": SimpleNamespace(best_similarity=0.91, matched=True),
            "char_b": SimpleNamespace(best_similarity=0.88, matched=True),
        }
        _, take, _ = _run(
            ["char_a", "char_b"], result=_result(per_char=per_char)
        )
        assert take["metadata"]["identity_all_matched"] is True

    def test_empty_character_results_writes_no_per_char_keys(self):
        _, take, _ = _run(["char_a"], result=_result(per_char={}))
        assert "identity_per_char" not in take["metadata"]
        assert "identity_all_matched" not in take["metadata"]


# ---------------------------------------------------------------------------
# Wiring: _finalize_motion_take delegates (no scaffold-free way to run it)
# ---------------------------------------------------------------------------

class TestFinalizeWiring:
    def test_finalize_delegates_and_slice_is_gone(self):
        import inspect

        src = inspect.getsource(ShotController._finalize_motion_take)
        assert "_validate_take_identity(" in src
        assert "chars_in_frame[0]" not in src
