"""Tests for llm.negative_prompts — failure-reason → negative-prompt lookup.

The mapping is a pure lookup keyed on identity-validator failure-reason
values (the .value strings from identity.types.FailureReason). Tests
verify:
- Each known reason returns a non-empty, semantically-relevant phrase
- Unknown reasons return '' (opt-in semantics)
- None returns ''

Keys follow the audit at task B.0 — snake_case .value strings, not
uppercase enum names.
"""

from __future__ import annotations

import pytest


_ACTIVE_FAILURE_REASONS = [
    "no_face_detected",
    "low_confidence_detection",
    "small_face_region",
    "face_angle_extreme",
    "wrong_person",
    "poor_lighting",
    "occlusion",
]


@pytest.mark.parametrize("reason", _ACTIVE_FAILURE_REASONS)
def test_every_active_failure_reason_returns_non_empty(reason):
    """Every actively-emitted failure reason MUST have a negative-prompt entry.

    Keys are from the B.0 audit of identity/types.FailureReason — only
    reasons that actually get assigned by identity/validator.py are
    covered. `multiple_faces_ambiguous` is in the enum but never set,
    so it's intentionally excluded; including a key for it would
    create a dead entry that never gets hit.
    """
    from llm.negative_prompts import get_negative_prompt_for_failure
    result = get_negative_prompt_for_failure(reason)
    assert result, f"reason {reason!r} returned empty/falsy: {result!r}"


def test_face_angle_extreme_returns_profile_phrasing():
    from llm.negative_prompts import get_negative_prompt_for_failure
    result = get_negative_prompt_for_failure("face_angle_extreme")
    assert isinstance(result, str)
    assert result != ""
    lower = result.lower()
    assert "profile" in lower or "side" in lower, (
        f"face_angle_extreme should mention profile/side; got: {result!r}"
    )


def test_wrong_person_returns_identity_phrasing():
    from llm.negative_prompts import get_negative_prompt_for_failure
    result = get_negative_prompt_for_failure("wrong_person")
    assert isinstance(result, str)
    assert result != ""
    lower = result.lower()
    assert any(
        kw in lower for kw in ("different", "wrong", "mismatch", "drift")
    ), f"wrong_person should reference identity drift; got: {result!r}"


def test_unknown_reason_returns_empty():
    from llm.negative_prompts import get_negative_prompt_for_failure
    result = get_negative_prompt_for_failure("xyzzy_unknown")
    assert result == "", (
        f"unknown reason must return empty (opt-in semantics); got: {result!r}"
    )


def test_none_returns_empty():
    """Defensive: first-try takes have no prior failure reason."""
    from llm.negative_prompts import get_negative_prompt_for_failure
    result = get_negative_prompt_for_failure(None)
    assert result == "", (
        f"None must return empty (no prior failure); got: {result!r}"
    )


def test_mapping_keys_match_live_failure_reason_enum():
    """Every key in NEGATIVE_PROMPT_BY_FAILURE_REASON must be a real FailureReason
    .value string. If identity/types.py renames a value, this test catches the
    stale key before it silently becomes an unreachable opt-in entry."""
    from llm.negative_prompts import NEGATIVE_PROMPT_BY_FAILURE_REASON
    from identity.types import FailureReason

    live_values = {r.value for r in FailureReason}
    stale_keys = set(NEGATIVE_PROMPT_BY_FAILURE_REASON.keys()) - live_values
    assert not stale_keys, (
        f"these mapping keys are no longer valid FailureReason values: {stale_keys}. "
        f"Either rename them to match identity/types.FailureReason or delete them."
    )


from llm.negative_prompts import build_remediation_advisory


def test_advisory_none_when_no_failure_reason():
    assert build_remediation_advisory(None) is None
    assert build_remediation_advisory("") is None


def test_advisory_known_reason_has_negative_prompt():
    adv = build_remediation_advisory("wrong_person", 0.05)
    assert adv == {
        "failure_reason": "wrong_person",
        "suggested_negative_prompt": "wrong person, different face, identity drift, mismatched features",
        "suggested_pulid_adjustment": 0.05,
        "source": "deterministic",
    }


def test_advisory_unknown_reason_empty_negative_prompt():
    adv = build_remediation_advisory("low_identity", 0.0)
    assert adv["failure_reason"] == "low_identity"
    assert adv["suggested_negative_prompt"] == ""   # not in the map -> opt-in empty
    assert adv["source"] == "deterministic"
