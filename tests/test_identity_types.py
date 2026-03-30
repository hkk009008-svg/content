import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from identity_types import (
    FailureReason,
    FrameSample,
    CharacterIdentityResult,
    IdentityValidationResult,
    SHOT_TYPE_THRESHOLDS,
    get_threshold_for_shot,
)


# --- FailureReason enum ---

class TestFailureReason:
    def test_has_all_expected_values(self):
        expected = [
            "NO_FACE_DETECTED",
            "LOW_CONFIDENCE_DETECTION",
            "FACE_ANGLE_EXTREME",
            "OCCLUSION",
            "WRONG_PERSON",
            "MULTIPLE_FACES_AMBIGUOUS",
            "SMALL_FACE_REGION",
            "POOR_LIGHTING",
            "PASSED",
        ]
        for name in expected:
            assert hasattr(FailureReason, name), f"FailureReason missing {name}"


# --- FrameSample ---

class TestFrameSample:
    def test_can_be_constructed(self):
        sample = FrameSample(
            frame_index=0,
            frame_position_ratio=0.0,
            face_detected=True,
            face_confidence=0.95,
            face_area_ratio=0.1,
            face_angle_estimate="frontal",
            similarity=0.85,
            matched=True,
            failure_reason=FailureReason.PASSED,
        )
        assert sample.frame_index == 0
        assert sample.matched is True


# --- CharacterIdentityResult ---

class TestCharacterIdentityResult:
    def test_can_be_constructed(self):
        result = CharacterIdentityResult(
            character_id="char_01",
            character_name="Alice",
            best_similarity=0.90,
            mean_similarity=0.80,
            min_similarity=0.70,
            frame_results=[],
            matched=True,
            primary_failure_reason=FailureReason.PASSED,
            suggested_pulid_adjustment=0.0,
        )
        assert result.character_id == "char_01"
        assert result.matched is True


# --- IdentityValidationResult ---

def _make_validation_result(passed=True, score=0.85):
    char_result = CharacterIdentityResult(
        character_id="char_01",
        character_name="Alice",
        best_similarity=0.90,
        mean_similarity=0.80,
        min_similarity=0.70,
        frame_results=[],
        matched=True,
        primary_failure_reason=FailureReason.PASSED,
        suggested_pulid_adjustment=0.0,
    )
    return IdentityValidationResult(
        passed=passed,
        overall_score=score,
        character_results={"char_01": char_result},
        frames_sampled=5,
        video_duration_seconds=4.0,
        shot_type="portrait",
        threshold_used=0.70,
    )


class TestIdentityValidationResult:
    def test_get_passed_returns_passed(self):
        result = _make_validation_result(passed=True)
        assert result.get("passed") is True

    def test_get_similarity_returns_overall_score(self):
        result = _make_validation_result(score=0.85)
        assert result.get("similarity") == 0.85

    def test_get_results_returns_correct_dict(self):
        result = _make_validation_result()
        results_dict = result.get("results")
        assert "char_01" in results_dict
        assert results_dict["char_01"]["matched"] is True
        assert results_dict["char_01"]["similarity"] == 0.90

    def test_get_unknown_key_returns_default(self):
        result = _make_validation_result()
        assert result.get("unknown_key") is None
        assert result.get("unknown_key", 42) == 42


# --- get_threshold_for_shot ---

class TestGetThresholdForShot:
    def test_attempt_0_returns_mode_threshold(self):
        assert get_threshold_for_shot("portrait", mode="standard", attempt=0) == 0.70

    def test_final_attempt_returns_lenient(self):
        assert get_threshold_for_shot("portrait", mode="standard", attempt=2, max_attempts=3) == 0.60

    def test_middle_attempt_interpolates(self):
        # attempt=1, max_attempts=3: t = 1/2 = 0.5
        # standard=0.70, lenient=0.60 → 0.70*0.5 + 0.60*0.5 = 0.65
        result = get_threshold_for_shot("portrait", mode="standard", attempt=1, max_attempts=3)
        assert abs(result - 0.65) < 1e-9

    def test_unknown_shot_type_uses_medium_fallback(self):
        result = get_threshold_for_shot("unknown_type", mode="standard", attempt=0)
        expected = SHOT_TYPE_THRESHOLDS["medium"]["standard"]
        assert result == expected

    def test_landscape_always_returns_zero(self):
        for mode in ("strict", "standard", "lenient"):
            assert get_threshold_for_shot("landscape", mode=mode, attempt=0) == 0.0

    @pytest.mark.parametrize("shot_type", SHOT_TYPE_THRESHOLDS.keys())
    def test_all_shot_types_have_all_modes(self, shot_type):
        thresholds = SHOT_TYPE_THRESHOLDS[shot_type]
        for mode in ("strict", "standard", "lenient"):
            assert mode in thresholds, f"{shot_type} missing mode '{mode}'"


# --- Parametric boundary tests ---


class TestThresholdOrdering:
    """Verify strict > standard > lenient for all shot types."""

    @pytest.mark.parametrize("shot_type", [st for st in SHOT_TYPE_THRESHOLDS if st != "landscape"])
    def test_strict_greater_than_standard(self, shot_type):
        t = SHOT_TYPE_THRESHOLDS[shot_type]
        assert t["strict"] > t["standard"], (
            f"{shot_type}: strict ({t['strict']}) should be > standard ({t['standard']})"
        )

    @pytest.mark.parametrize("shot_type", [st for st in SHOT_TYPE_THRESHOLDS if st != "landscape"])
    def test_standard_greater_than_lenient(self, shot_type):
        t = SHOT_TYPE_THRESHOLDS[shot_type]
        assert t["standard"] > t["lenient"], (
            f"{shot_type}: standard ({t['standard']}) should be > lenient ({t['lenient']})"
        )


class TestThresholdDegradation:
    """Verify thresholds degrade monotonically across retry attempts."""

    @pytest.mark.parametrize("shot_type", [st for st in SHOT_TYPE_THRESHOLDS if st != "landscape"])
    @pytest.mark.parametrize("mode", ["strict", "standard", "lenient"])
    def test_monotonic_degradation(self, shot_type, mode):
        max_attempts = 4
        prev = float("inf")
        for attempt in range(max_attempts):
            threshold = get_threshold_for_shot(shot_type, mode=mode, attempt=attempt, max_attempts=max_attempts)
            assert threshold <= prev, (
                f"{shot_type}/{mode}: attempt {attempt} threshold ({threshold}) "
                f"should be <= attempt {attempt-1} ({prev})"
            )
            prev = threshold

    @pytest.mark.parametrize("shot_type", [st for st in SHOT_TYPE_THRESHOLDS if st != "landscape"])
    def test_final_attempt_equals_lenient(self, shot_type):
        max_attempts = 4
        threshold = get_threshold_for_shot(
            shot_type, mode="strict", attempt=max_attempts - 1, max_attempts=max_attempts
        )
        expected = SHOT_TYPE_THRESHOLDS[shot_type]["lenient"]
        assert abs(threshold - expected) < 1e-9, (
            f"{shot_type}: final attempt ({threshold}) should equal lenient ({expected})"
        )

    def test_landscape_always_zero_across_attempts(self):
        for attempt in range(5):
            for mode in ("strict", "standard", "lenient"):
                threshold = get_threshold_for_shot("landscape", mode=mode, attempt=attempt, max_attempts=5)
                assert threshold == 0.0


class TestThresholdPositive:
    """All non-landscape thresholds should be positive."""

    @pytest.mark.parametrize("shot_type", [st for st in SHOT_TYPE_THRESHOLDS if st != "landscape"])
    @pytest.mark.parametrize("mode", ["strict", "standard", "lenient"])
    def test_all_thresholds_positive(self, shot_type, mode):
        assert SHOT_TYPE_THRESHOLDS[shot_type][mode] > 0
