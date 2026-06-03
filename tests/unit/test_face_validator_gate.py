"""Tests for face_validator_gate.py — score_candidate, should_halt, needs_regenerate, select_best."""

import pytest

from face_validator_gate import (
    CandidateScore,
    DEFAULT_WEIGHTS,
    HaltDecision,
    needs_regenerate,
    score_candidate,
    select_best,
    should_halt,
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


# ===================================================================
# 1. TestScoreCandidate — score_candidate()  (line 168)
# ===================================================================


class TestScoreCandidate:
    def test_valid_anchor_populates_arc_and_aesthetic(self, monkeypatch, tmp_path):
        """Both models available: arc and aesthetic fields populated."""
        fake_anchor = tmp_path / "anchor.jpg"
        fake_anchor.write_bytes(b"fake")
        monkeypatch.setattr(
            "face_validator_gate._arcface_score",
            lambda img, anchor, threshold=0.0: 0.8,
        )
        monkeypatch.setattr(
            "face_validator_gate._aesthetic_score",
            lambda img: 0.7,
        )
        score = score_candidate("/fake/image.jpg", str(fake_anchor))
        assert score.has_arc is True
        assert score.arc_score == pytest.approx(0.8)
        assert score.has_aesthetic is True
        assert score.aesthetic_score == pytest.approx(0.7)
        assert score.composite == pytest.approx(0.6 * 0.8 + 0.4 * 0.7)

    def test_composite_formula_matches_default_weights(self, monkeypatch, tmp_path):
        """Canonical boundary case: arc=1.0, aes=0.0 → composite == DEFAULT_WEIGHTS['arc'] (0.6)
        — exact arithmetic; makes the weight contribution unambiguous."""
        fake_anchor = tmp_path / "anchor.jpg"
        fake_anchor.write_bytes(b"fake")
        arc, aes = 1.0, 0.0
        monkeypatch.setattr(
            "face_validator_gate._arcface_score",
            lambda img, anchor, threshold=0.0: arc,
        )
        monkeypatch.setattr(
            "face_validator_gate._aesthetic_score",
            lambda img: aes,
        )
        score = score_candidate("/fake/image.jpg", str(fake_anchor))
        assert score.composite == pytest.approx(DEFAULT_WEIGHTS["arc"])  # 0.6
        # Symmetry check: the inverse boundary
        monkeypatch.setattr(
            "face_validator_gate._arcface_score",
            lambda img, anchor, threshold=0.0: 0.0,
        )
        monkeypatch.setattr(
            "face_validator_gate._aesthetic_score",
            lambda img: 1.0,
        )
        score2 = score_candidate("/fake/image.jpg", str(fake_anchor))
        assert score2.composite == pytest.approx(DEFAULT_WEIGHTS["aesthetic"])  # 0.4

    def test_arc_none_uses_neutral_0_5_in_composite(self, monkeypatch, tmp_path):
        """When ArcFace returns None, composite arc contribution is neutral 0.5."""
        fake_anchor = tmp_path / "anchor.jpg"
        fake_anchor.write_bytes(b"fake")
        aes = 0.6
        monkeypatch.setattr(
            "face_validator_gate._arcface_score",
            lambda img, anchor, threshold=0.0: None,
        )
        monkeypatch.setattr(
            "face_validator_gate._aesthetic_score",
            lambda img: aes,
        )
        score = score_candidate("/fake/image.jpg", str(fake_anchor))
        assert score.has_arc is False
        expected = DEFAULT_WEIGHTS["arc"] * 0.5 + DEFAULT_WEIGHTS["aesthetic"] * aes
        assert score.composite == pytest.approx(expected)

    def test_aesthetic_none_uses_neutral_0_5_in_composite(self, monkeypatch, tmp_path):
        """When aesthetic returns None, composite aesthetic contribution is neutral 0.5."""
        fake_anchor = tmp_path / "anchor.jpg"
        fake_anchor.write_bytes(b"fake")
        arc = 0.75
        monkeypatch.setattr(
            "face_validator_gate._arcface_score",
            lambda img, anchor, threshold=0.0: arc,
        )
        monkeypatch.setattr(
            "face_validator_gate._aesthetic_score",
            lambda img: None,
        )
        score = score_candidate("/fake/image.jpg", str(fake_anchor))
        assert score.has_aesthetic is False
        expected = DEFAULT_WEIGHTS["arc"] * arc + DEFAULT_WEIGHTS["aesthetic"] * 0.5
        assert score.composite == pytest.approx(expected)

    def test_both_helpers_none_neutral_composite(self, monkeypatch):
        """face_anchor=None + aesthetic=None → composite uses 0.5 for both → 0.5 (pure neutral).

        Spec item 5 — guards against a future regression where a single
        unmocked path leaks the wrong default into composite arithmetic.
        """
        monkeypatch.setattr(
            "face_validator_gate._aesthetic_score",
            lambda img: None,
        )
        score = score_candidate("/fake/image.jpg", None)
        assert score.has_arc is False
        assert score.has_aesthetic is False
        # Formula match (both contribs at 0.5)
        expected = DEFAULT_WEIGHTS["arc"] * 0.5 + DEFAULT_WEIGHTS["aesthetic"] * 0.5
        assert score.composite == pytest.approx(expected)
        # Direct anchor: pure neutral 0.5 (0.6*0.5 + 0.4*0.5 = 0.5)
        assert score.composite == pytest.approx(0.5)

    def test_no_anchor_skips_arc(self, monkeypatch):
        """face_anchor=None: ArcFace is never called; has_arc remains False."""
        called = []
        monkeypatch.setattr(
            "face_validator_gate._arcface_score",
            lambda *a, **kw: called.append(a) or 0.9,
        )
        monkeypatch.setattr(
            "face_validator_gate._aesthetic_score",
            lambda img: 0.5,
        )
        score = score_candidate("/fake/image.jpg", None)
        assert not called
        assert score.has_arc is False

    def test_nonexistent_anchor_path_skips_arc(self, monkeypatch, tmp_path):
        """A face_anchor path that doesn't exist on disk skips ArcFace."""
        called = []
        monkeypatch.setattr(
            "face_validator_gate._arcface_score",
            lambda *a, **kw: called.append(a) or 0.9,
        )
        monkeypatch.setattr(
            "face_validator_gate._aesthetic_score",
            lambda img: 0.5,
        )
        nonexistent = str(tmp_path / "no_such_file.jpg")
        score = score_candidate("/fake/image.jpg", nonexistent)
        assert not called
        assert score.has_arc is False

    @pytest.mark.parametrize(
        "weights,arc,aes",
        [
            ({"arc": 0.5, "aesthetic": 0.5}, 0.8, 0.6),  # equal weights
            ({"arc": 0.8, "aesthetic": 0.2}, 0.6, 0.9),  # arc-heavy
            ({"arc": 0.2, "aesthetic": 0.8}, 0.4, 0.5),  # aesthetic-heavy
            ({"arc": 1.0, "aesthetic": 0.0}, 0.7, 0.9),  # arc-only
        ],
    )
    def test_custom_weights_applied(self, monkeypatch, tmp_path, weights, arc, aes):
        """Custom weights dict overrides DEFAULT_WEIGHTS — parametrized across
        4 combos covering equal / arc-heavy / aesthetic-heavy / arc-only."""
        fake_anchor = tmp_path / "anchor.jpg"
        fake_anchor.write_bytes(b"fake")
        monkeypatch.setattr(
            "face_validator_gate._arcface_score",
            lambda img, anchor, threshold=0.0: arc,
        )
        monkeypatch.setattr(
            "face_validator_gate._aesthetic_score",
            lambda img: aes,
        )
        score = score_candidate("/fake/image.jpg", str(fake_anchor), weights=weights)
        expected = weights["arc"] * arc + weights["aesthetic"] * aes
        assert score.composite == pytest.approx(expected)


# ===================================================================
# 2. TestShouldHalt — should_halt()  (line 225)
# ===================================================================


def _make_score(composite: float, arc: float = 0.5) -> CandidateScore:
    """Helper: build a CandidateScore with given composite and arc."""
    return CandidateScore(
        image_path="/fake/img.jpg",
        seed=0,
        arc_score=arc,
        composite=composite,
        has_arc=True,
    )


class TestShouldHalt:
    def test_empty_scores_no_halt(self):
        """Empty list → halt=False, reason contains 'no candidates'."""
        decision = should_halt([])
        assert decision.halt is False
        assert "no candidates" in decision.reason

    def test_budget_exhausted_at_max_n(self):
        """When n >= halt_max_n, halt regardless of composite."""
        scores = [_make_score(0.1) for _ in range(8)]
        decision = should_halt(scores, halt_max_n=8)
        assert decision.halt is True
        assert "n=" in decision.reason

    def test_below_min_n_no_halt(self):
        """n < halt_min_n → halt=False even if composite is great."""
        scores = [_make_score(0.99), _make_score(0.98), _make_score(0.97)]
        decision = should_halt(scores, halt_min_n=4, halt_max_n=8)
        assert decision.halt is False

    def test_threshold_met_halts(self):
        """n >= halt_min_n AND best.composite >= halt_threshold_composite → halt=True."""
        scores = [_make_score(0.95), _make_score(0.80), _make_score(0.70), _make_score(0.60)]
        decision = should_halt(
            scores,
            halt_threshold_composite=0.92,
            halt_min_n=4,
            halt_max_n=8,
        )
        assert decision.halt is True
        assert decision.best is not None
        assert decision.best.composite == pytest.approx(0.95)
        assert "composite=" in decision.reason

    def test_threshold_not_met_continues(self):
        """n >= halt_min_n but best.composite < halt_threshold_composite → halt=False.
        decision.best is still populated (only the empty-scores guard returns None)."""
        scores = [_make_score(0.80), _make_score(0.75), _make_score(0.70), _make_score(0.65)]
        decision = should_halt(
            scores,
            halt_threshold_composite=0.92,
            halt_min_n=4,
            halt_max_n=8,
        )
        assert decision.halt is False
        assert decision.best is not None
        assert decision.best.composite == pytest.approx(0.80)

    def test_best_returned_in_decision(self):
        """should_halt returns the highest-composite candidate as decision.best."""
        low = _make_score(0.50)
        high = _make_score(0.95)
        scores = [low, high, _make_score(0.70), _make_score(0.65)]
        decision = should_halt(
            scores,
            halt_threshold_composite=0.92,
            halt_min_n=4,
            halt_max_n=8,
        )
        assert decision.best is high


# ===================================================================
# 3. TestNeedsRegenerate — needs_regenerate()  (line 289)
# ===================================================================


class TestNeedsRegenerate:
    def test_non_character_shot_never_regenerates(self):
        """has_character=False → always False regardless of arc score.

        Tests both pathological-low and clearly-passing arc to harden the
        "regardless of arc" claim — the early-return at face_validator_gate.py:300
        short-circuits before any arc comparison.
        """
        best_low = CandidateScore(
            image_path="/fake/img.jpg",
            seed=0,
            arc_score=0.0,
            has_arc=True,
        )
        assert needs_regenerate(best_low, regenerate_floor_arc=0.5, has_character=False) is False
        best_high = CandidateScore(
            image_path="/fake/img.jpg",
            seed=0,
            arc_score=0.9,
            has_arc=True,
        )
        assert needs_regenerate(best_high, regenerate_floor_arc=0.5, has_character=False) is False

    def test_no_arc_no_regenerate(self):
        """has_arc=False → False; no arc measurement means no identity gate."""
        best = CandidateScore(
            image_path="/fake/img.jpg",
            seed=0,
            arc_score=0.0,
            has_arc=False,
        )
        assert needs_regenerate(best, regenerate_floor_arc=0.5, has_character=True) is False

    def test_arc_below_floor_triggers_regenerate(self):
        """arc_score < regenerate_floor_arc with character shot → True."""
        best = CandidateScore(
            image_path="/fake/img.jpg",
            seed=0,
            arc_score=0.3,
            has_arc=True,
        )
        assert needs_regenerate(best, regenerate_floor_arc=0.5, has_character=True) is True

    def test_arc_at_or_above_floor_no_regenerate(self):
        """arc_score >= regenerate_floor_arc → False.

        Tests both the boundary (exact equality — strict '<' at line 304)
        and a clearly-above case to document intent.
        """
        # Boundary: arc == floor → False (strict '<' in source)
        best_at = CandidateScore(
            image_path="/fake/img.jpg",
            seed=0,
            arc_score=0.5,
            has_arc=True,
        )
        assert needs_regenerate(best_at, regenerate_floor_arc=0.5, has_character=True) is False
        # Clearly above floor → False
        best_high = CandidateScore(
            image_path="/fake/img.jpg",
            seed=0,
            arc_score=0.9,
            has_arc=True,
        )
        assert needs_regenerate(best_high, regenerate_floor_arc=0.5, has_character=True) is False


# ===================================================================
# 4. TestSelectBest — select_best()  (line 282)
# ===================================================================


class TestSelectBest:
    def test_empty_returns_none(self):
        """Empty list → None."""
        assert select_best([]) is None

    def test_highest_composite_wins(self):
        """Returns the CandidateScore with the highest composite value."""
        low = _make_score(0.4)
        mid = _make_score(0.6)
        high = _make_score(0.9)
        result = select_best([low, high, mid])
        assert result is high


# ===================================================================
# 5. TestArcfaceScoreSkipGuard — _arcface_score() None-score guard
# ===================================================================


class TestArcfaceScoreSkipGuard:
    """Regression: when validate_image returns a skipped result (overall_score=None),
    _arcface_score must return None WITHOUT logging an error (Part-3 T2, pre-skip).

    Before the guard: float(None) raises TypeError; the except-block catches it and
    returns None but prints "[FaceGate] ArcFace failed …" — a misleading error for a
    legitimate skip.  After the guard: early-return None before float(), no log line.
    """

    def test_skip_result_returns_none_without_error_log(self, monkeypatch, tmp_path, capsys):
        """_arcface_score returns None cleanly on a skip result — no 'ArcFace failed' log."""
        from face_validator_gate import _arcface_score

        fake_img = tmp_path / "img.jpg"
        fake_img.write_bytes(b"fake")
        fake_ref = tmp_path / "ref.jpg"
        fake_ref.write_bytes(b"fake")

        # Build a mock validator whose validate_image returns a skip result.
        class _MockValidator:
            def validate_image(self, *args, **kwargs):
                return _skip_result()

        monkeypatch.setattr("face_validator_gate._get_validator", lambda: _MockValidator())

        result = _arcface_score(str(fake_img), str(fake_ref))

        # Must return None (no comparable face / skip).
        assert result is None

        # Must NOT emit a misleading "[FaceGate] ArcFace failed" error — that marker
        # is the observable signal that the old float(None)-via-exception path fired.
        captured = capsys.readouterr()
        assert "ArcFace failed" not in captured.out, (
            "Detected old exception-path log — explicit None guard missing"
        )
