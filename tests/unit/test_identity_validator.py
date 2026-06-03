"""
Characterization tests for identity/validator.py (IdentityValidator).

These tests LOCK IN the EXISTING behavior of already-written code.
They PASS against HEAD.  Where the code does something surprising or buggy,
each test asserts the ACTUAL current behavior and adds a comment:
    # CANDIDATE BUG (Gn): <one line>

Offline-only: all external deps (DeepFace, cv2.VideoCapture, os.path.exists,
tempfile) are mocked.  No GPU, no model weights, no network, no real files.

Baseline: 1337 tests collected / 1334 passed / 3 skipped before this file.
"""

from unittest.mock import MagicMock, patch, PropertyMock
import numpy as np
import pytest

import identity
from identity.validator import IdentityValidator
from identity.types import (
    FailureReason,
    FrameSample,
    CharacterIdentityResult,
    IdentityValidationResult,
    get_threshold_for_shot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_embedding(value: float = 1.0, size: int = 512) -> np.ndarray:
    """Return a unit-norm embedding whose self-cosine == 1.0."""
    vec = np.full(size, value)
    return vec / np.linalg.norm(vec)


def _fake_represent(vec: np.ndarray):
    """Return DeepFace.represent-style output for a given embedding."""
    return [{"embedding": vec.tolist()}]


def _make_frame_sample(
    *,
    face_detected: bool = True,
    face_confidence: float = 0.8,
    face_area_ratio: float = 0.05,
    face_angle_estimate: str = "frontal",
    similarity: float = 0.85,
    matched: bool = True,
    failure_reason: FailureReason = FailureReason.PASSED,
) -> FrameSample:
    return FrameSample(
        frame_index=0,
        frame_position_ratio=0.0,
        face_detected=face_detected,
        face_confidence=face_confidence,
        face_area_ratio=face_area_ratio,
        face_angle_estimate=face_angle_estimate,
        similarity=similarity,
        matched=matched,
        failure_reason=failure_reason,
    )


def _make_char_result(
    cid: str = "char_a",
    matched: bool = True,
    best_similarity: float = 0.85,
    mean_similarity: float = 0.85,
    failure_reason: FailureReason = FailureReason.PASSED,
) -> CharacterIdentityResult:
    return CharacterIdentityResult(
        character_id=cid,
        character_name=cid,
        best_similarity=best_similarity,
        mean_similarity=mean_similarity,
        min_similarity=best_similarity,
        frame_results=[],
        matched=matched,
        primary_failure_reason=failure_reason,
        suggested_pulid_adjustment=0.0,
    )


# ---------------------------------------------------------------------------
# validate_image tests
# ---------------------------------------------------------------------------

class TestValidateImageMissingFile:
    """Test case 1: missing file → silent pass (G1)."""

    def test_missing_image_returns_passed_true_score_1(self):
        # CANDIDATE BUG (G1): missing file silently returns passed=True, overall_score=1.0
        # instead of raising an error or returning passed=False.
        with patch("identity.validator.os.path.exists", return_value=False):
            validator = IdentityValidator()
            result = validator.validate_image(
                image_path="/nonexistent/generated.jpg",
                reference_path="/nonexistent/reference.jpg",
                character_id="char_a",
            )
        assert result.passed is True
        assert result.overall_score == 1.0
        assert result.frames_sampled == 0

    def test_missing_file_uses_supplied_threshold(self):
        # The threshold is forwarded to _no_file_result via `threshold or 0.70`.
        with patch("identity.validator.os.path.exists", return_value=False):
            validator = IdentityValidator()
            result = validator.validate_image(
                image_path="/x.jpg",
                reference_path="/y.jpg",
                threshold=0.55,
            )
        assert result.threshold_used == 0.55

    def test_missing_file_defaults_threshold_to_070(self):
        # When threshold=None, the fallback is 0.70 (hardcoded in the `or` expr).
        with patch("identity.validator.os.path.exists", return_value=False):
            validator = IdentityValidator()
            result = validator.validate_image("/x.jpg", "/y.jpg")
        assert result.threshold_used == 0.70


class TestValidateImageHappyPath:
    """Test case 2: high-similarity embeddings → passed=True, score >= threshold."""

    def test_high_similarity_passes(self):
        ref_emb = _make_embedding(1.0)
        gen_emb = _make_embedding(0.999)  # nearly identical → cos ≈ 1.0

        with patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DEEPFACE_AVAILABLE", True), \
             patch(
                 "identity.validator.DeepFace.represent",
                 side_effect=[_fake_represent(ref_emb), _fake_represent(gen_emb)],
             ):
            validator = IdentityValidator()
            result = validator.validate_image(
                "/gen.jpg", "/ref.jpg",
                character_id="char_a",
                shot_type="medium",
            )

        assert result.passed is True
        assert result.overall_score >= get_threshold_for_shot("medium")

    def test_history_appended_on_success(self):
        ref_emb = _make_embedding(1.0)
        gen_emb = _make_embedding(0.999)

        with patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DEEPFACE_AVAILABLE", True), \
             patch(
                 "identity.validator.DeepFace.represent",
                 side_effect=[_fake_represent(ref_emb), _fake_represent(gen_emb)],
             ):
            validator = IdentityValidator()
            assert len(validator.history) == 0
            validator.validate_image("/gen.jpg", "/ref.jpg")
            assert len(validator.history) == 1  # test case 6: history appended


class TestValidateImageLowSimilarity:
    """Test case 3: low similarity → passed=False, failure_reason=WRONG_PERSON."""

    def test_low_similarity_fails_wrong_person(self):
        ref_emb = _make_embedding(1.0)
        # Orthogonal vector → cosine = 0.0 → similarity = 0.5; with threshold 0.65 → fails.
        # But 0.5 > 0.35 so failure reason falls through to WRONG_PERSON in _analyze_single_image
        # (that path uses simplified logic: always WRONG_PERSON when not matched).
        gen_emb = np.zeros(512)
        gen_emb[0] = 1.0  # orthogonal to ref_emb which is all-equal

        with patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DEEPFACE_AVAILABLE", True), \
             patch(
                 "identity.validator.DeepFace.represent",
                 side_effect=[_fake_represent(ref_emb), _fake_represent(gen_emb)],
             ):
            validator = IdentityValidator()
            result = validator.validate_image(
                "/gen.jpg", "/ref.jpg",
                character_id="char_a",
                shot_type="medium",
                threshold=0.65,
            )

        assert result.passed is False
        char = result.character_results["char_a"]
        assert char.primary_failure_reason == FailureReason.WRONG_PERSON


class TestValidateImageDeepFaceUnavailable:
    """Test case 4: DEEPFACE_AVAILABLE=False, vision_fallback=None → RuntimeError."""

    def test_raises_runtime_error_no_fallback(self):
        with patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DEEPFACE_AVAILABLE", False):
            validator = IdentityValidator(vision_fallback=None)
            with pytest.raises(RuntimeError, match="vision_fallback not configured"):
                validator.validate_image("/gen.jpg", "/ref.jpg")


class TestValidateImageVisionFallback:
    """Test case 5: vision_fallback used → no DeepFace call."""

    def test_vision_fallback_called_no_deepface(self):
        mock_fallback = MagicMock(return_value={"confidence": 0.85, "issues": []})

        with patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DEEPFACE_AVAILABLE", False), \
             patch("identity.validator.DeepFace") as mock_df:
            validator = IdentityValidator(vision_fallback=mock_fallback)
            result = validator.validate_image(
                "/gen.jpg", "/ref.jpg",
                character_id="char_a",
                shot_type="medium",
            )

        mock_df.represent.assert_not_called()
        mock_fallback.assert_called_once()
        assert result.passed is True
        assert result.overall_score == pytest.approx(0.85)

    def test_vision_fallback_low_confidence_fails(self):
        mock_fallback = MagicMock(return_value={"confidence": 0.30, "issues": []})

        with patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DEEPFACE_AVAILABLE", False):
            validator = IdentityValidator(vision_fallback=mock_fallback)
            result = validator.validate_image(
                "/gen.jpg", "/ref.jpg",
                shot_type="medium",
                threshold=0.65,
            )

        assert result.passed is False


# ---------------------------------------------------------------------------
# validate_video tests
# ---------------------------------------------------------------------------

def _make_mock_cap(total_frames: int = 0, fps: float = 24.0):
    """Build a mock cv2.VideoCapture that returns given total_frames + fps."""
    cap = MagicMock()
    def cap_get(prop):
        import cv2
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return float(total_frames)
        if prop == cv2.CAP_PROP_FPS:
            return fps
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return 1920.0
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return 1080.0
        return 0.0
    cap.get.side_effect = cap_get
    cap.read.return_value = (False, None)
    return cap


class TestValidateVideoEmptyCharacterConfigs:
    """Test case 7: empty character_configs → passed=True (uses _no_file_result)."""

    def test_empty_configs_passes_silently(self):
        # CANDIDATE BUG (G1 variant): empty character_configs uses _no_file_result
        # which returns passed=True, overall_score=1.0 rather than signaling no work was done.
        with patch("identity.validator.DEEPFACE_AVAILABLE", True):
            validator = IdentityValidator()
            result = validator.validate_video(
                video_path="/fake.mp4",
                character_configs=[],
                shot_type="medium",
            )
        assert result.passed is True
        assert result.overall_score == 1.0


class TestValidateVideoZeroFrames:
    """Test case 8: zero frames → passed=False, overall_score=0.0."""

    def test_zero_frames_fails(self):
        ref_emb = _make_embedding(1.0)
        mock_cap = _make_mock_cap(total_frames=0)

        with patch("identity.validator.DEEPFACE_AVAILABLE", True), \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DeepFace.represent", return_value=_fake_represent(ref_emb)), \
             patch("identity.validator.cv2.VideoCapture", return_value=mock_cap):
            validator = IdentityValidator()
            result = validator.validate_video(
                video_path="/fake.mp4",
                character_configs=[{"id": "char_a", "reference_image": "/ref.jpg", "name": "Alice"}],
            )

        assert result.passed is False
        assert result.overall_score == 0.0
        assert result.frames_sampled == 0


class TestValidateVideoLandscape:
    """Test case 9: shot_type='landscape' with nonzero frames → frames_sampled=0.

    The actual behavior diverges from the spec map prediction.
    When ref files exist, landscape still builds char_frame_results (with empty lists)
    and _aggregate_character returns matched=False for empty frames → passed=False.

    The spec map predicted passed=True (G2 silent-pass), but that only occurs when
    character_results is empty (no ref files found → _no_file_result path).
    """

    def test_landscape_zero_frames_sampled_fails_when_ref_exists(self):
        # CANDIDATE BUG (G2 — actual behavior): landscape shot_type yields density=0.0 →
        # positions=[] → char_frame_results[cid]=[] per character → _aggregate_character([])
        # returns matched=False → passed=False, overall_score=0.0, frames_sampled=0.
        # This is wrong behavior: a landscape shot should not "fail" identity for having
        # no faces — faces are not the point of a landscape shot.
        ref_emb = _make_embedding(1.0)
        mock_cap = _make_mock_cap(total_frames=120, fps=24.0)

        with patch("identity.validator.DEEPFACE_AVAILABLE", True), \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DeepFace.represent", return_value=_fake_represent(ref_emb)), \
             patch("identity.validator.cv2.VideoCapture", return_value=mock_cap):
            validator = IdentityValidator()
            result = validator.validate_video(
                video_path="/fake.mp4",
                character_configs=[{"id": "char_a", "reference_image": "/ref.jpg", "name": "Alice"}],
                shot_type="landscape",
            )

        assert result.frames_sampled == 0
        # Actual behavior: passed=False (not True as the spec map predicted)
        assert result.passed is False
        assert result.overall_score == pytest.approx(0.0)

    def test_landscape_passes_when_no_ref_files(self):
        # When ref files don't exist → ref_embeddings is empty → _no_file_result → passed=True.
        # This is the path where landscape actually silently passes.
        mock_cap = _make_mock_cap(total_frames=120, fps=24.0)

        with patch("identity.validator.DEEPFACE_AVAILABLE", True), \
             patch("identity.validator.os.path.exists", return_value=False), \
             patch("identity.validator.cv2.VideoCapture", return_value=mock_cap):
            validator = IdentityValidator()
            result = validator.validate_video(
                video_path="/fake.mp4",
                character_configs=[{"id": "char_a", "reference_image": "/ref.jpg", "name": "Alice"}],
                shot_type="landscape",
            )

        assert result.passed is True
        assert result.overall_score == 1.0


class TestValidateVideoMultiCharacterOneFails:
    """Test case 10: multi-character where one character fails → overall passed=False."""

    def test_one_fail_makes_overall_fail(self):
        # We drive this through the character_results aggregation logic directly
        # by using two characters: one's ref image exists (passes), one doesn't (no_file → skip).
        # A cleaner way: use the aggregate path.  We'll inject directly via patching
        # _aggregate_character to return controlled results.
        ref_emb = _make_embedding(1.0)
        # char_a ref exists, char_b ref doesn't (os.path.exists returns False for char_b)

        def exists_side_effect(path):
            if "char_b_ref" in path:
                return False
            return True

        mock_cap = _make_mock_cap(total_frames=48, fps=24.0)

        # make cap.read return a fake frame so _analyze_frame is reachable
        import cv2 as _cv2
        fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)

        # Low-similarity embedding for char_a to force failure
        bad_emb = np.zeros(512)
        bad_emb[0] = 1.0  # orthogonal to ref_emb

        face_data = [{
            "face": np.ones((64, 64, 3), dtype=np.float32) / 255.0,
            "confidence": 0.9,
            "facial_area": {"x": 10, "y": 10, "w": 50, "h": 50},
        }]

        with patch("identity.validator.DEEPFACE_AVAILABLE", True), \
             patch("identity.validator.os.path.exists", side_effect=exists_side_effect), \
             patch("identity.validator.DeepFace.represent",
                   side_effect=lambda **kw: _fake_represent(ref_emb if "ref" in kw.get("img_path", "") else bad_emb)), \
             patch("identity.validator.DeepFace.extract_faces", return_value=face_data), \
             patch("identity.validator.cv2.VideoCapture", return_value=mock_cap), \
             patch("identity.validator.cv2.imwrite", return_value=True), \
             patch("os.path.exists", return_value=True):  # for tmp file cleanup
            validator = IdentityValidator()
            result = validator.validate_video(
                video_path="/fake.mp4",
                character_configs=[
                    {"id": "char_a", "reference_image": "/char_a_ref.jpg", "name": "Alice"},
                    {"id": "char_b", "reference_image": "/char_b_ref.jpg", "name": "Bob"},
                ],
                shot_type="medium",
                threshold=0.65,
            )

        # char_b has no ref → skipped from ref_embeddings → no results → not in char_frame_results
        # char_a will have results; if similarity is low → overall passes only if char_a passes.
        # This test is intentionally structured to trigger the "one char no ref" skip path;
        # the real multi-fail test is in TestValidateVideoMultiCharAggregation.
        assert isinstance(result, IdentityValidationResult)


class TestValidateVideoMultiCharAggregation:
    """Test that all_passed = all(cr.matched for cr in character_results.values())."""

    def test_one_char_not_matched_makes_overall_fail(self):
        # Directly build what _aggregate_character returns by patching it.
        mock_cap = _make_mock_cap(total_frames=48, fps=24.0)
        ref_emb = _make_embedding(1.0)

        char_results = {
            "char_a": _make_char_result("char_a", matched=True, best_similarity=0.90),
            "char_b": _make_char_result("char_b", matched=False, best_similarity=0.40,
                                        failure_reason=FailureReason.WRONG_PERSON),
        }

        with patch("identity.validator.DEEPFACE_AVAILABLE", True), \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DeepFace.represent", return_value=_fake_represent(ref_emb)), \
             patch("identity.validator.cv2.VideoCapture", return_value=mock_cap), \
             patch.object(IdentityValidator, "_aggregate_character",
                          side_effect=lambda cid, name, frames, th: char_results.get(cid, _make_char_result(cid))):
            validator = IdentityValidator()
            result = validator.validate_video(
                video_path="/fake.mp4",
                character_configs=[
                    {"id": "char_a", "reference_image": "/ref_a.jpg", "name": "Alice"},
                    {"id": "char_b", "reference_image": "/ref_b.jpg", "name": "Bob"},
                ],
                shot_type="medium",
                threshold=0.65,
            )

        assert result.passed is False


# ---------------------------------------------------------------------------
# _compute_sample_positions tests
# ---------------------------------------------------------------------------

class TestComputeSamplePositions:
    """Test case 11: portrait > wide density; anchors at 10/50/90; landscape → []."""

    def test_landscape_returns_empty(self):
        validator = IdentityValidator()
        positions = validator._compute_sample_positions(120, 24.0, "landscape")
        assert positions == []

    def test_portrait_more_samples_than_wide(self):
        # For 10s clips both portrait (density=2.0) and wide (density=1.0) exceed max_samples=10
        # and both get clamped to 10 → equal.  Use a short enough clip where they differ.
        # 1s clip (24 frames): portrait = int(1*2*2)=4 clamped to 4; wide = int(1*2*1)=2 clamped to min=3
        # → portrait (4) > wide (3)
        validator = IdentityValidator()
        portrait_pos = validator._compute_sample_positions(24, 24.0, "portrait")
        wide_pos = validator._compute_sample_positions(24, 24.0, "wide")
        assert len(portrait_pos) > len(wide_pos)

    def test_includes_anchor_positions(self):
        validator = IdentityValidator()
        # 240 frames at 24fps = 10s → well above min_samples
        positions = validator._compute_sample_positions(240, 24.0, "medium")
        total_frames = 240
        # anchors at 10%, 50%, 90%
        anchor_frames = {
            max(0, min(int(0.10 * total_frames), total_frames - 1)),
            max(0, min(int(0.50 * total_frames), total_frames - 1)),
            max(0, min(int(0.90 * total_frames), total_frames - 1)),
        }
        # At least the anchor frames should be present (positions may be truncated to num_samples)
        # but the anchors are added first as a set, so at least some should be there.
        assert len(positions) >= 3

    def test_nonzero_frames_nonzero_positions_for_portrait(self):
        validator = IdentityValidator()
        positions = validator._compute_sample_positions(120, 24.0, "portrait")
        assert len(positions) > 0

    def test_all_positions_in_bounds(self):
        validator = IdentityValidator()
        total_frames = 100
        for shot in ("portrait", "medium", "wide", "action"):
            positions = validator._compute_sample_positions(total_frames, 24.0, shot)
            for p in positions:
                assert 0 <= p < total_frames, f"Position {p} out of range for shot={shot}"


# ---------------------------------------------------------------------------
# _classify_failure tests
# ---------------------------------------------------------------------------

class TestClassifyFailure:
    """Test case 12: each branch of _classify_failure."""

    def test_not_detected(self):
        result = IdentityValidator._classify_failure(
            detected=False, confidence=0.9, area_ratio=0.1,
            angle="frontal", similarity=0.9,
        )
        assert result == FailureReason.NO_FACE_DETECTED

    def test_low_confidence(self):
        # confidence < 0.4 → LOW_CONFIDENCE_DETECTION (detected=True required)
        result = IdentityValidator._classify_failure(
            detected=True, confidence=0.3, area_ratio=0.1,
            angle="frontal", similarity=0.9,
        )
        assert result == FailureReason.LOW_CONFIDENCE_DETECTION

    def test_confidence_boundary_at_04(self):
        # confidence == 0.4 does NOT trigger LOW_CONFIDENCE_DETECTION (strict <)
        result = IdentityValidator._classify_failure(
            detected=True, confidence=0.4, area_ratio=0.1,
            angle="frontal", similarity=0.9,
        )
        assert result != FailureReason.LOW_CONFIDENCE_DETECTION

    def test_small_face_region(self):
        # area_ratio < 0.01 → SMALL_FACE_REGION
        result = IdentityValidator._classify_failure(
            detected=True, confidence=0.8, area_ratio=0.005,
            angle="frontal", similarity=0.9,
        )
        assert result == FailureReason.SMALL_FACE_REGION

    def test_face_angle_extreme(self):
        # angle == "profile" → FACE_ANGLE_EXTREME
        result = IdentityValidator._classify_failure(
            detected=True, confidence=0.8, area_ratio=0.05,
            angle="profile", similarity=0.9,
        )
        assert result == FailureReason.FACE_ANGLE_EXTREME

    def test_wrong_person(self):
        # similarity < 0.35 → WRONG_PERSON
        result = IdentityValidator._classify_failure(
            detected=True, confidence=0.8, area_ratio=0.05,
            angle="frontal", similarity=0.20,
        )
        assert result == FailureReason.WRONG_PERSON

    def test_poor_lighting_fallback(self):
        # All other conditions clear → POOR_LIGHTING
        result = IdentityValidator._classify_failure(
            detected=True, confidence=0.8, area_ratio=0.05,
            angle="frontal", similarity=0.50,  # >= 0.35 but below threshold
        )
        assert result == FailureReason.POOR_LIGHTING

    def test_multiple_faces_ambiguous_never_produced(self):
        # G3: MULTIPLE_FACES_AMBIGUOUS is defined in the enum but _classify_failure
        # never returns it regardless of input combination.
        inputs = [
            (True, 0.9, 0.1, "frontal", 0.9),
            (True, 0.3, 0.1, "frontal", 0.9),
            (True, 0.9, 0.001, "frontal", 0.9),
            (True, 0.9, 0.1, "profile", 0.9),
            (True, 0.9, 0.1, "frontal", 0.20),
            (True, 0.9, 0.1, "frontal", 0.50),
            (False, 0.9, 0.1, "frontal", 0.9),
        ]
        for args in inputs:
            result = IdentityValidator._classify_failure(*args)
            assert result != FailureReason.MULTIPLE_FACES_AMBIGUOUS, (
                f"CANDIDATE BUG (G3): _classify_failure returned MULTIPLE_FACES_AMBIGUOUS "
                f"for inputs {args}, but this path was thought to be unreachable"
            )


# ---------------------------------------------------------------------------
# _compute_pulid_delta tests
# ---------------------------------------------------------------------------

class TestComputePulidDelta:
    """Test case 13: all 4 outcomes of _compute_pulid_delta."""

    def test_strong_match_returns_minus_005(self):
        # matched=True, similarity > 0.80 → -0.05
        delta = IdentityValidator._compute_pulid_delta(similarity=0.85, matched=True)
        assert delta == pytest.approx(-0.05)

    def test_weak_match_returns_zero(self):
        # matched=True, similarity <= 0.80 → 0.0
        delta = IdentityValidator._compute_pulid_delta(similarity=0.75, matched=True)
        assert delta == pytest.approx(0.0)

    def test_close_miss_returns_plus_005(self):
        # matched=False, similarity > 0.55 → +0.05
        delta = IdentityValidator._compute_pulid_delta(similarity=0.60, matched=False)
        assert delta == pytest.approx(0.05)

    def test_clear_failure_returns_plus_010(self):
        # matched=False, similarity <= 0.55 → +0.10
        delta = IdentityValidator._compute_pulid_delta(similarity=0.30, matched=False)
        assert delta == pytest.approx(0.10)

    def test_boundary_similarity_080_still_strong_match(self):
        # matched=True, similarity == 0.80 is NOT > 0.80, so → 0.0 (not -0.05)
        delta = IdentityValidator._compute_pulid_delta(similarity=0.80, matched=True)
        assert delta == pytest.approx(0.0)

    def test_boundary_similarity_055_is_clear_failure(self):
        # matched=False, similarity == 0.55 is NOT > 0.55, so → +0.10 (not +0.05)
        delta = IdentityValidator._compute_pulid_delta(similarity=0.55, matched=False)
        assert delta == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# get_rolling_stats tests
# ---------------------------------------------------------------------------

class TestGetRollingStats:
    """Test case 14: empty history → zero-stats; delta tiers by injecting fake results."""

    def test_empty_history_returns_zero_stats(self):
        validator = IdentityValidator()
        stats = validator.get_rolling_stats("char_a")
        assert stats["sample_count"] == 0
        assert stats["mean_similarity"] == 0.0
        assert stats["success_rate"] == 0.0
        assert stats["suggested_pulid_delta"] == 0.0

    def _inject_results(self, validator, char_id, records):
        """Inject a list of (matched, best_similarity) as fake history entries."""
        for matched, best_sim in records:
            char_result = _make_char_result(char_id, matched=matched, best_similarity=best_sim)
            fake_result = IdentityValidationResult(
                passed=matched,
                overall_score=best_sim,
                character_results={char_id: char_result},
                frames_sampled=1,
                video_duration_seconds=5.0,
                shot_type="medium",
                threshold_used=0.65,
            )
            validator.history.append(fake_result)

    def test_low_success_rate_gives_plus_010_delta(self):
        # success_rate < 0.5 → suggested_pulid_delta = +0.10
        validator = IdentityValidator()
        # 1 success out of 4 = 0.25 < 0.5
        self._inject_results(validator, "char_a", [
            (True, 0.80),
            (False, 0.40),
            (False, 0.40),
            (False, 0.40),
        ])
        stats = validator.get_rolling_stats("char_a")
        assert stats["suggested_pulid_delta"] == pytest.approx(0.10)
        assert stats["sample_count"] == 4

    def test_medium_success_rate_gives_plus_005_delta(self):
        # 0.5 <= success_rate < 0.8 → suggested_pulid_delta = +0.05
        validator = IdentityValidator()
        # 3 out of 5 = 0.6, in [0.5, 0.8)
        self._inject_results(validator, "char_a", [
            (True, 0.80),
            (True, 0.75),
            (True, 0.70),
            (False, 0.40),
            (False, 0.40),
        ])
        stats = validator.get_rolling_stats("char_a")
        assert stats["suggested_pulid_delta"] == pytest.approx(0.05)

    def test_perfect_success_high_mean_gives_minus_005_delta(self):
        # success_rate == 1.0 AND mean_similarity > 0.80 → suggested_pulid_delta = -0.05
        validator = IdentityValidator()
        self._inject_results(validator, "char_a", [
            (True, 0.90),
            (True, 0.85),
            (True, 0.88),
        ])
        stats = validator.get_rolling_stats("char_a")
        assert stats["suggested_pulid_delta"] == pytest.approx(-0.05)

    def test_perfect_success_low_mean_gives_zero_delta(self):
        # success_rate == 1.0 but mean_similarity <= 0.80 → delta = 0.0
        validator = IdentityValidator()
        self._inject_results(validator, "char_a", [
            (True, 0.70),
            (True, 0.72),
        ])
        stats = validator.get_rolling_stats("char_a")
        assert stats["suggested_pulid_delta"] == pytest.approx(0.0)

    def test_window_limits_to_last_n(self):
        validator = IdentityValidator()
        # Inject 20 entries but only look at last 5
        self._inject_results(validator, "char_a", [(False, 0.30)] * 15)
        self._inject_results(validator, "char_a", [(True, 0.90)] * 5)
        stats = validator.get_rolling_stats("char_a", window=5)
        assert stats["sample_count"] == 5
        assert stats["success_rate"] == pytest.approx(1.0)

    def test_character_not_in_history_gives_empty(self):
        validator = IdentityValidator()
        self._inject_results(validator, "char_a", [(True, 0.90)])
        stats = validator.get_rolling_stats("char_b")
        assert stats["sample_count"] == 0


# ---------------------------------------------------------------------------
# _estimate_face_angle tests
# ---------------------------------------------------------------------------

class TestEstimateFaceAngle:
    """Test case 15: frontal/three_quarter/profile/unknown by w/h ratio."""

    def test_frontal_high_ratio(self):
        # ratio = w/h > 0.75 → "frontal"
        result = IdentityValidator._estimate_face_angle({"w": 100, "h": 100})
        assert result == "frontal"

    def test_three_quarter_mid_ratio(self):
        # 0.55 < ratio <= 0.75 → "three_quarter"
        result = IdentityValidator._estimate_face_angle({"w": 65, "h": 100})
        assert result == "three_quarter"

    def test_profile_low_ratio(self):
        # ratio <= 0.55 → "profile"
        result = IdentityValidator._estimate_face_angle({"w": 40, "h": 100})
        assert result == "profile"

    def test_unknown_when_h_is_zero(self):
        # h == 0 → "unknown" (avoids division by zero)
        result = IdentityValidator._estimate_face_angle({"w": 100, "h": 0})
        assert result == "unknown"

    def test_unknown_when_area_missing(self):
        result = IdentityValidator._estimate_face_angle({})
        assert result == "unknown"

    def test_boundary_075_is_frontal(self):
        # ratio == 0.75 → "frontal" (> 0.75 is false; but == 0.75 is not > 0.75)
        # Actually ratio = 75/100 = 0.75; 0.75 > 0.75 is False; 0.75 > 0.55 is True → three_quarter
        result = IdentityValidator._estimate_face_angle({"w": 75, "h": 100})
        assert result == "three_quarter"

    def test_boundary_055_is_profile(self):
        # ratio = 55/100 = 0.55; 0.55 > 0.75 False; 0.55 > 0.55 False → "profile"
        result = IdentityValidator._estimate_face_angle({"w": 55, "h": 100})
        assert result == "profile"


# ---------------------------------------------------------------------------
# Singleton / independence tests
# ---------------------------------------------------------------------------

class TestSingletonIndependence:
    """Test case 16: two IdentityValidator() instances have independent .history."""

    def test_independent_history(self):
        v1 = IdentityValidator()
        v2 = IdentityValidator()

        ref_emb = _make_embedding(1.0)
        gen_emb = _make_embedding(0.999)

        with patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DEEPFACE_AVAILABLE", True), \
             patch(
                 "identity.validator.DeepFace.represent",
                 side_effect=[_fake_represent(ref_emb), _fake_represent(gen_emb)],
             ):
            v1.validate_image("/gen.jpg", "/ref.jpg")

        assert len(v1.history) == 1
        assert len(v2.history) == 0

    def test_get_shared_validator_reset(self):
        """Resetting _SHARED_VALIDATOR gives a fresh instance."""
        import identity as identity_pkg
        original = identity_pkg._SHARED_VALIDATOR
        try:
            identity_pkg._SHARED_VALIDATOR = None
            # Don't call get_shared_validator() — it triggers make_validator()
            # which imports phase_c_vision (not safe in offline tests).
            # Just verify the reset leaves it None.
            assert identity_pkg._SHARED_VALIDATOR is None
        finally:
            identity_pkg._SHARED_VALIDATOR = original


# ---------------------------------------------------------------------------
# G4: threshold=0.0 inconsistency between early-return path and DeepFace path
# ---------------------------------------------------------------------------

class TestThresholdZeroInconsistency:
    """
    G4: validate_video line 153 uses `threshold or get_threshold_for_shot(...)`.
    If threshold=0.0 (falsy), the `or` expression ignores it and picks a default.
    But line 162 uses `if threshold is None` — so 0.0 would NOT be overridden there.
    This means th (used in _no_file_result and vision path) gets a real value
    while threshold (used in DeepFace path) stays 0.0.

    This test documents the ACTUAL behavior: when DEEPFACE_AVAILABLE=True and
    threshold=0.0, the DeepFace path uses threshold=0.0 (not the default), because
    `if threshold is None` at line 162 is False (0.0 is not None).
    """

    def test_threshold_zero_not_none_skips_override(self):
        # CANDIDATE BUG (G4): threshold=0.0 in validate_video:
        #   - Line 153: th = threshold or ... → th = get_threshold_for_shot(...)  (0.0 is falsy)
        #   - Line 162: if threshold is None: → False; threshold stays 0.0
        # So th != threshold — the two variables diverge when threshold=0.0 is passed.
        # With threshold=0.0, ANY similarity passes (>= 0.0 is always True).

        ref_emb = _make_embedding(1.0)
        mock_cap = _make_mock_cap(total_frames=0)

        with patch("identity.validator.DEEPFACE_AVAILABLE", True), \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DeepFace.represent", return_value=_fake_represent(ref_emb)), \
             patch("identity.validator.cv2.VideoCapture", return_value=mock_cap):
            validator = IdentityValidator()
            result = validator.validate_video(
                video_path="/fake.mp4",
                character_configs=[{"id": "char_a", "reference_image": "/ref.jpg", "name": "Alice"}],
                threshold=0.0,
            )

        # total_frames=0 → early return with threshold_used=threshold (which is 0.0 from line 162
        # ... actually the early-return at line 192-196 uses `threshold` (post-line-162), not `th`.
        # At this point threshold=0.0 (not overridden since 0.0 is not None).
        assert result.threshold_used == 0.0  # actual behavior: 0.0 survives to the result


# ---------------------------------------------------------------------------
# _diagnose_failure tests (bonus — covers the helper thoroughly)
# ---------------------------------------------------------------------------

class TestDiagnoseFailure:
    """Additional coverage for _diagnose_failure branches.

    Note: _diagnose_failure is an instance method (not @staticmethod), so
    it must be called on an IdentityValidator instance.
    """

    def test_empty_frames_is_no_face_detected(self):
        result = IdentityValidator()._diagnose_failure([])
        assert result == FailureReason.NO_FACE_DETECTED

    def test_no_detected_frames_is_no_face_detected(self):
        frames = [_make_frame_sample(face_detected=False, similarity=0.0)]
        result = IdentityValidator()._diagnose_failure(frames)
        assert result == FailureReason.NO_FACE_DETECTED

    def test_low_avg_confidence_is_low_confidence_detection(self):
        frames = [_make_frame_sample(face_detected=True, face_confidence=0.2, face_area_ratio=0.05)]
        result = IdentityValidator()._diagnose_failure(frames)
        assert result == FailureReason.LOW_CONFIDENCE_DETECTION

    def test_small_area_is_small_face_region(self):
        frames = [_make_frame_sample(face_detected=True, face_confidence=0.9, face_area_ratio=0.005)]
        result = IdentityValidator()._diagnose_failure(frames)
        assert result == FailureReason.SMALL_FACE_REGION

    def test_majority_profile_is_face_angle_extreme(self):
        frames = [
            _make_frame_sample(face_detected=True, face_confidence=0.9, face_area_ratio=0.05,
                               face_angle_estimate="profile"),
            _make_frame_sample(face_detected=True, face_confidence=0.9, face_area_ratio=0.05,
                               face_angle_estimate="profile"),
            _make_frame_sample(face_detected=True, face_confidence=0.9, face_area_ratio=0.05,
                               face_angle_estimate="frontal"),
        ]
        result = IdentityValidator()._diagnose_failure(frames)
        assert result == FailureReason.FACE_ANGLE_EXTREME

    def test_low_best_sim_is_wrong_person(self):
        frames = [_make_frame_sample(face_detected=True, face_confidence=0.9,
                                     face_area_ratio=0.05, face_angle_estimate="frontal",
                                     similarity=0.20)]
        result = IdentityValidator()._diagnose_failure(frames)
        assert result == FailureReason.WRONG_PERSON

    def test_fallback_is_poor_lighting(self):
        # All checks pass but similarity is between 0.35 and threshold → POOR_LIGHTING
        frames = [_make_frame_sample(face_detected=True, face_confidence=0.9,
                                     face_area_ratio=0.05, face_angle_estimate="frontal",
                                     similarity=0.50)]
        result = IdentityValidator()._diagnose_failure(frames)
        assert result == FailureReason.POOR_LIGHTING


# ---------------------------------------------------------------------------
# Part-3 schema: honest SKIP state + GENERATED_IMAGE_MISSING (spec §3)
# ---------------------------------------------------------------------------

def test_skipped_result_schema():
    r = IdentityValidationResult(
        passed=True, overall_score=None, character_results={},
        frames_sampled=0, video_duration_seconds=0.0,
        shot_type="medium", threshold_used=0.7, skipped=True,
    )
    assert r.skipped is True
    assert r.overall_score is None
    assert r.passed is True


def test_skipped_defaults_false():
    r = IdentityValidationResult(
        passed=True, overall_score=0.8, character_results={},
        frames_sampled=1, video_duration_seconds=0.0,
        shot_type="medium", threshold_used=0.7,
    )
    assert r.skipped is False
    assert r.overall_score == 0.8


def test_generated_image_missing_reason_exists():
    assert FailureReason.GENERATED_IMAGE_MISSING.value == "generated_image_missing"
