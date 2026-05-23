"""Negative-prompt vocabulary keyed off identity-validator failure reasons.

When a take fails validation, the next attempt for that shot gets a
negative-prompt hint describing what the previous take got wrong. This
is opt-in: only known failure reasons contribute; unknown reasons fall
through to empty string.

Keys are the `.value` strings from `identity/types.FailureReason` — see
the B.0 audit in docs/superpowers/plans/2026-05-23-quality-uplift.md §5.2
for the taxonomy. `multiple_faces_ambiguous` is defined in the enum but
never emitted by identity/validator.py; intentionally NOT mapped.
`passed` is the success sentinel, never a failure reason.

Used by llm.chief_director when assembling prompt mutations after a
validation failure. Per-engine formatting is the consumer's concern;
this module returns plain English phrases.
"""

from __future__ import annotations

from typing import Optional


# Map keys MUST match identity/types.FailureReason.value verbatim.
# If a value is renamed in identity/types.py, update it here in the same
# commit. Unknown reasons are silently ignored (opt-in semantics).
NEGATIVE_PROMPT_BY_FAILURE_REASON: dict[str, str] = {
    "no_face_detected": "no face visible, hidden face, fully obscured, no person in frame",
    "low_confidence_detection": "blurry face, low-quality face detection, ambiguous facial features",
    "small_face_region": "small distant face, tiny face, face too far from camera, blurry features",
    "face_angle_extreme": "profile view, side angle, head turned away, obscured face",
    "wrong_person": "wrong person, different face, identity drift, mismatched features",
    "poor_lighting": "harsh shadows, underexposed face, poorly lit subject, low-key lighting on face",
    "occlusion": "occluded face, partially hidden face, hand covering face, object blocking face",
    # TODO: add "multiple_faces_ambiguous" here once identity/validator.py
    # starts emitting it (currently defined in the enum but never assigned —
    # see B.0 audit in docs/superpowers/plans/2026-05-23-quality-uplift.md).
}


def get_negative_prompt_for_failure(reason: Optional[str]) -> str:
    """Return the negative-prompt string for a single failure reason.

    Opt-in: unknown reasons return ''. None returns '' (defensive — first-try
    takes have no prior failure reason).
    """
    if reason is None:
        return ""
    return NEGATIVE_PROMPT_BY_FAILURE_REASON.get(reason, "")
