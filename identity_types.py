"""
Cinema Production Tool — Identity Types
Shared data structures for the unified identity validation system.

Provides:
- FailureReason enum — why identity validation failed
- FrameSample — per-frame analysis result
- CharacterIdentityResult — per-character aggregate
- IdentityValidationResult — complete validation result (backward-compatible .get())
- Shot-type-aware threshold tables
- Adaptive threshold computation
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum


class FailureReason(Enum):
    NO_FACE_DETECTED = "no_face_detected"
    LOW_CONFIDENCE_DETECTION = "low_confidence_detection"
    FACE_ANGLE_EXTREME = "face_angle_extreme"
    OCCLUSION = "occlusion"
    WRONG_PERSON = "wrong_person"
    MULTIPLE_FACES_AMBIGUOUS = "multiple_faces_ambiguous"
    SMALL_FACE_REGION = "small_face_region"
    POOR_LIGHTING = "poor_lighting"
    PASSED = "passed"


@dataclass
class FrameSample:
    """Result of analyzing a single frame for identity."""
    frame_index: int
    frame_position_ratio: float          # 0.0 to 1.0
    face_detected: bool
    face_confidence: float               # DeepFace detection confidence (0-1)
    face_area_ratio: float               # face_bbox_area / frame_area
    face_angle_estimate: str             # "frontal", "three_quarter", "profile", "unknown"
    similarity: float                    # 0.0 to 1.0 (cosine mapped)
    matched: bool
    failure_reason: FailureReason


@dataclass
class CharacterIdentityResult:
    """Per-character identity validation result with diagnostics."""
    character_id: str
    character_name: str
    best_similarity: float
    mean_similarity: float
    min_similarity: float
    frame_results: List[FrameSample]
    matched: bool
    primary_failure_reason: FailureReason
    suggested_pulid_adjustment: float    # -0.1 to +0.1 delta


@dataclass
class IdentityValidationResult:
    """
    Complete validation result for a video or image.
    Backward-compatible: result.get("passed") and result.get("similarity") work.
    """
    passed: bool
    overall_score: float                 # weighted average across characters
    character_results: Dict[str, CharacterIdentityResult]
    frames_sampled: int
    video_duration_seconds: float
    shot_type: str                       # "portrait", "medium", "wide", etc.
    threshold_used: float
    metadata: Dict = field(default_factory=dict)

    def get(self, key, default=None):
        """Dict-compatible accessor for backward compatibility."""
        if key == "passed":
            return self.passed
        if key == "similarity":
            return self.overall_score
        if key == "results":
            return {
                cid: {"matched": cr.matched, "similarity": cr.best_similarity}
                for cid, cr in self.character_results.items()
            }
        return default


# ---------------------------------------------------------------------------
# Shot-type-aware thresholds
# ---------------------------------------------------------------------------

SHOT_TYPE_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "portrait":  {"strict": 0.75, "standard": 0.70, "lenient": 0.60},
    "medium":    {"strict": 0.70, "standard": 0.65, "lenient": 0.55},
    "wide":      {"strict": 0.60, "standard": 0.55, "lenient": 0.45},
    "action":    {"strict": 0.65, "standard": 0.60, "lenient": 0.50},
    "landscape": {"strict": 0.0,  "standard": 0.0,  "lenient": 0.0},
}


def get_threshold_for_shot(
    shot_type: str,
    mode: str = "standard",
    attempt: int = 0,
    max_attempts: int = 3,
) -> float:
    """
    Returns identity threshold adjusted for shot type and retry attempt.

    On first attempt uses the mode threshold. On final attempt degrades
    linearly to lenient. This prevents infinite retry loops while keeping
    early attempts strict.
    """
    thresholds = SHOT_TYPE_THRESHOLDS.get(shot_type, SHOT_TYPE_THRESHOLDS["medium"])

    if attempt == 0:
        return thresholds[mode]
    elif attempt >= max_attempts - 1:
        return thresholds["lenient"]
    else:
        # Linear interpolation between mode and lenient
        t = attempt / max(max_attempts - 1, 1)
        return thresholds[mode] * (1 - t) + thresholds["lenient"] * t
