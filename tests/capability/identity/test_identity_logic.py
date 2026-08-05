from dataclasses import fields

import pytest

from identity.types import (
    CharacterIdentityResult,
    FailureReason,
    FrameSample,
    get_threshold_for_shot,
)
from identity.validator import IdentityValidator


@pytest.mark.offline
def test_threshold_degrades_standard_to_lenient(capability_record):
    # portrait: standard 0.70 -> lenient 0.60 across attempts (max_attempts=3)
    first = get_threshold_for_shot("portrait", mode="standard", attempt=0, max_attempts=3)
    last = get_threshold_for_shot("portrait", mode="standard", attempt=2, max_attempts=3)
    assert first == pytest.approx(0.70)
    assert last == pytest.approx(0.60)
    mids = [get_threshold_for_shot("portrait", attempt=a, max_attempts=3) for a in range(3)]
    assert mids == sorted(mids, reverse=True)  # monotonic non-increasing
    capability_record(claim_id="ID-02", passed=True)


@pytest.mark.offline
@pytest.mark.offline
def test_character_aggregation_preserves_failure_reason(capability_record):
    validator = IdentityValidator()
    frame = FrameSample(
        frame_index=0,
        frame_position_ratio=0.5,
        face_detected=True,
        face_confidence=0.95,
        face_area_ratio=0.2,
        face_angle_estimate="frontal",
        similarity=0.2,
        matched=False,
        failure_reason=FailureReason.WRONG_PERSON,
    )
    result = validator._aggregate_character(
        "char_test", "Character", [frame], threshold=0.7
    )
    assert result.primary_failure_reason is FailureReason.WRONG_PERSON
    capability_record(claim_id="ID-05", passed=True)


@pytest.mark.offline
def test_identity_diagnostics_are_provider_neutral(capability_record):
    field_names = {item.name for item in fields(CharacterIdentityResult)}
    assert "suggested_pulid_adjustment" not in field_names
    assert all("provider" not in name for name in field_names)
    capability_record(claim_id="ID-06", passed=True)


@pytest.mark.offline
def test_sample_positions_density_and_clamp(capability_record):
    v = IdentityValidator()
    pos = v._compute_sample_positions(total_frames=120, fps=30.0, shot_type="portrait")
    assert 3 <= len(pos) <= 10
    assert pos == sorted(pos)
    # landscape density 0.0 -> [] (skip), per identity/validator.py:365-406
    land = v._compute_sample_positions(total_frames=120, fps=30.0, shot_type="landscape")
    assert land == []
    capability_record(claim_id="ID-07", passed=True)


@pytest.mark.offline
def test_identity_offline_claims_are_exercised():
    """Guard against silent ledger drift: every Identity 'asserted' offline claim
    must be one this chunk exercises."""
    import _ledger  # top-level via conftest sys.path shim
    offline_asserted = {c.claim_id for c in _ledger.by_dimension("identity")
                        if c.tier == "offline" and c.status == "asserted"}
    assert offline_asserted == {"ID-02", "ID-05", "ID-06", "ID-07"}
