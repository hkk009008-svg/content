"""Cinema Pipeline — Identity validation package.

Public API:
    from identity import (
        IdentityValidator,
        make_validator,                    # fresh validator with vision_fallback wired
        get_shared_validator,              # process-singleton validator (preferred)
        FailureReason, FrameSample,
        CharacterIdentityResult, IdentityValidationResult,
        SHOT_TYPE_THRESHOLDS, get_threshold_for_shot,
    )

`identity.validator` is intentionally independent of `phase_c_vision` so we
can import it without triggering the cinematography/vision stack. Callers
who need the vision-LLM fallback should construct via `make_validator()`
(fresh instance per call) or `get_shared_validator()` (process-singleton).

Prefer `get_shared_validator()` for nearly all callers — sharing one
IdentityValidator instance across phase_c_vision, face_validator_gate,
and performance.identity_gate means: (a) ArcFace weights load once per
process instead of three times, and (b) the rolling-stats history that
feeds `workflow_selector.get_adaptive_pulid_weight` collects signal from
every identity check in the pipeline.
"""

import threading
from typing import Optional

from identity.types import (
    FailureReason,
    FrameSample,
    CharacterIdentityResult,
    IdentityValidationResult,
    SHOT_TYPE_THRESHOLDS,
    get_threshold_for_shot,
)
from identity.validator import IdentityValidator, VisionValidator


def make_validator(**kwargs) -> IdentityValidator:
    """Factory wiring the vision-LLM fallback from phase_c_vision.

    Returns a FRESH IdentityValidator on every call. Use this only when
    you specifically need an isolated instance (tests, etc.). For normal
    runtime use, prefer get_shared_validator() so all consumers share
    one cache + history.

    The import of `phase_c_vision.validate_identity_vision` is lazy so that
    `from identity import make_validator` does not pull the entire vision
    stack into the import graph until a validator is actually constructed.
    """
    if "vision_fallback" not in kwargs:
        from phase_c_vision import validate_identity_vision
        kwargs["vision_fallback"] = validate_identity_vision
    return IdentityValidator(**kwargs)


_SHARED_VALIDATOR: Optional[IdentityValidator] = None
_SHARED_VALIDATOR_LOCK = threading.Lock()


def get_shared_validator() -> IdentityValidator:
    """Process-singleton IdentityValidator with canonical vision_fallback wired.

    Replaces three previously-independent singletons in phase_c_vision,
    face_validator_gate, and performance.identity_gate. Sharing one
    instance means:

      - ArcFace weights load once per process (was 3x).
      - Rolling-stats history accumulates signal from per-shot keyframe
        validations + N=8 best-of grading + performance-gate scoring,
        giving workflow_selector.get_adaptive_pulid_weight a much
        richer sample to work from.

    Thread-safe via _SHARED_VALIDATOR_LOCK. Raises whatever
    IdentityValidator's constructor raises (typically due to missing
    insightface / ArcFace weights); callers that need a None-on-failure
    contract should wrap in try/except.
    """
    global _SHARED_VALIDATOR
    if _SHARED_VALIDATOR is not None:
        return _SHARED_VALIDATOR
    with _SHARED_VALIDATOR_LOCK:
        if _SHARED_VALIDATOR is None:
            _SHARED_VALIDATOR = make_validator()
        return _SHARED_VALIDATOR


__all__ = [
    "IdentityValidator",
    "VisionValidator",
    "make_validator",
    "get_shared_validator",
    "FailureReason",
    "FrameSample",
    "CharacterIdentityResult",
    "IdentityValidationResult",
    "SHOT_TYPE_THRESHOLDS",
    "get_threshold_for_shot",
]
