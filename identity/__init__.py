"""Cinema Pipeline — Identity validation package.

Public API:
    from identity import (
        IdentityValidator,
        make_validator,                    # factory that auto-wires phase_c_vision fallback
        FailureReason, FrameSample,
        CharacterIdentityResult, IdentityValidationResult,
        SHOT_TYPE_THRESHOLDS, get_threshold_for_shot,
    )

`identity.validator` is intentionally independent of `phase_c_vision` so we
can import it without triggering the cinematography/vision stack. Callers
who need the vision-LLM fallback should construct via `make_validator()`,
which does a lazy import of phase_c_vision.
"""

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

    The import of `phase_c_vision.validate_identity_vision` is lazy so that
    `from identity import make_validator` does not pull the entire vision
    stack into the import graph until a validator is actually constructed.
    """
    if "vision_fallback" not in kwargs:
        from phase_c_vision import validate_identity_vision
        kwargs["vision_fallback"] = validate_identity_vision
    return IdentityValidator(**kwargs)


__all__ = [
    "IdentityValidator",
    "VisionValidator",
    "make_validator",
    "FailureReason",
    "FrameSample",
    "CharacterIdentityResult",
    "IdentityValidationResult",
    "SHOT_TYPE_THRESHOLDS",
    "get_threshold_for_shot",
]
