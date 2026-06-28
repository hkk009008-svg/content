import pytest

from identity.types import get_threshold_for_shot
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
def test_pulid_delta_from_similarity(capability_record):
    f = IdentityValidator._compute_pulid_delta  # @staticmethod, callable unbound
    assert f(0.85, True) == pytest.approx(-0.05)
    assert f(0.70, True) == pytest.approx(0.0)
    assert f(0.58, False) == pytest.approx(0.05)
    assert f(0.40, False) == pytest.approx(0.10)
    capability_record(claim_id="ID-06", passed=True)


from identity.types import (
    IdentityValidationResult, CharacterIdentityResult, FailureReason,
)


def _history_result(cid, similarity, matched):
    """Shape get_rolling_stats expects: self.history is a List[IdentityValidationResult];
    each carries a CharacterIdentityResult per character (identity/types.py:46-85)."""
    cr = CharacterIdentityResult(
        character_id=cid, character_name=cid,
        best_similarity=similarity, mean_similarity=similarity, min_similarity=similarity,
        frame_results=[], matched=matched,
        primary_failure_reason=FailureReason.PASSED if matched else FailureReason.WRONG_PERSON,
        suggested_pulid_adjustment=0.0,
    )
    return IdentityValidationResult(
        passed=matched, overall_score=similarity, character_results={cid: cr},
        frames_sampled=1, video_duration_seconds=1.0, shot_type="portrait",
        threshold_used=0.70,
    )


@pytest.mark.offline
def test_rolling_stats_suggested_delta(capability_record):
    v = IdentityValidator()  # __init__ sets only dict/list attrs; no torch/DeepFace
    cid = "char_test"
    # 5 misses -> success_rate < 0.5 -> suggested_pulid_delta +0.10
    v.history.extend(_history_result(cid, 0.40, matched=False) for _ in range(5))
    stats = v.get_rolling_stats(cid, window=10)
    assert stats["suggested_pulid_delta"] == pytest.approx(0.10)
    capability_record(claim_id="ID-05", passed=True)


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
