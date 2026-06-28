"""Offline capability tests for cinema/auto_approve.py veto machinery.

All targets construct from plain dicts + AutoApproveConfig dataclass defaults —
no torch/DeepFace/network. We pass ``config=AutoApproveConfig(...)`` explicitly so
the from_project tier-aware default (production -> 0.60) never confuses a
threshold assertion (cinema/auto_approve.py:137).
"""
import pytest

from cinema.auto_approve import (
    AutoApproveConfig,
    _rules_for_plan,
    _rules_for_image,
    _rules_for_final,
    _any_take_has_fallback,
    _best_take_identity,
    _best_take_motion_score,
    _best_take_lipsync,
    _shot_over_budget,
    check_gate,
    record_director_review_on_shots,
)
from cinema.lifecycle import NullLifecycle


def _rule_names(rules):
    return {r.name for r in rules}


# --- rule-absence branches: a config flag removes a veto rule (GATE-01..06) ---

@pytest.mark.offline
def test_plan_rule_absent_when_require_approved_false(capability_record):
    assert "plan_decision_not_approved" in _rule_names(_rules_for_plan(AutoApproveConfig()))
    assert "plan_decision_not_approved" not in _rule_names(
        _rules_for_plan(AutoApproveConfig(plan_require_approved=False)))
    capability_record(claim_id="GATE-01", passed=True)


@pytest.mark.offline
def test_plan_violations_rule_absent_when_reject_on_violations_false(capability_record):
    assert "plan_has_violations" in _rule_names(_rules_for_plan(AutoApproveConfig()))
    assert "plan_has_violations" not in _rule_names(
        _rules_for_plan(AutoApproveConfig(plan_reject_on_violations=False)))
    capability_record(claim_id="GATE-02", passed=True)


@pytest.mark.offline
def test_image_composite_rule_absent_when_min_composite_zero(capability_record):
    assert "image_composite_below_threshold" in _rule_names(_rules_for_image(AutoApproveConfig()))
    assert "image_composite_below_threshold" not in _rule_names(
        _rules_for_image(AutoApproveConfig(image_min_composite=0)))
    capability_record(claim_id="GATE-03", passed=True)


@pytest.mark.offline
def test_image_fallback_rule_absent_when_veto_on_fallback_false(capability_record):
    assert "image_cascade_fallback" in _rule_names(_rules_for_image(AutoApproveConfig()))
    assert "image_cascade_fallback" not in _rule_names(
        _rules_for_image(AutoApproveConfig(image_veto_on_fallback=False)))
    capability_record(claim_id="GATE-04", passed=True)


@pytest.mark.offline
def test_image_budget_rule_absent_when_multiplier_zero(capability_record):
    assert "image_over_budget" in _rule_names(_rules_for_image(AutoApproveConfig()))
    assert "image_over_budget" not in _rule_names(
        _rules_for_image(AutoApproveConfig(image_max_spent_multiplier=0)))
    capability_record(claim_id="GATE-05", passed=True)


@pytest.mark.offline
def test_final_upstream_rule_absent_when_require_human_false(capability_record):
    assert "final_upstream_was_auto_approved" in _rule_names(_rules_for_final(AutoApproveConfig()))
    assert "final_upstream_was_auto_approved" not in _rule_names(
        _rules_for_final(AutoApproveConfig(final_require_human_if_upstream_auto=False)))
    capability_record(claim_id="GATE-06", passed=True)


# --- pure scoring helpers (GATE-07..11) ---

@pytest.mark.offline
def test_any_take_has_fallback_only_for_dict_fallback_true(capability_record):
    assert _any_take_has_fallback([{"cascade_metadata": {"fallback": True}}]) is True
    assert _any_take_has_fallback([{"cascade_metadata": {"fallback": False}}]) is False
    assert _any_take_has_fallback([{"cascade_metadata": None}]) is False
    assert _any_take_has_fallback([{"cascade_metadata": "notadict"}]) is False
    assert _any_take_has_fallback([{}]) is False
    assert _any_take_has_fallback([]) is False
    capability_record(claim_id="GATE-07", passed=True)


@pytest.mark.offline
def test_best_take_identity_max_finite_else_zero(capability_record):
    assert _best_take_identity(
        [{"metadata": {"identity_score": 0.7}}, {"metadata": {"identity_score": 0.9}}]) == pytest.approx(0.9)
    assert _best_take_identity([{"metadata": {"identity_score": float("inf")}}]) == 0.0
    assert _best_take_identity([]) == 0.0
    capability_record(claim_id="GATE-08", passed=True)


@pytest.mark.offline
def test_best_take_motion_score_prefers_motion_fidelity(capability_record):
    # motion_fidelity wins over motion_score within a take
    assert _best_take_motion_score(
        [{"metadata": {"motion_fidelity": 0.8, "motion_score": 0.5}}]) == pytest.approx(0.8)
    # falls back to motion_score when motion_fidelity absent
    assert _best_take_motion_score([{"metadata": {"motion_score": 0.6}}]) == pytest.approx(0.6)
    assert _best_take_motion_score([]) == 0.0
    capability_record(claim_id="GATE-09", passed=True)


@pytest.mark.offline
def test_best_take_lipsync_nonfinite_fails_closed(capability_record):
    # any_score_present is set BEFORE the isfinite check (cinema/auto_approve.py:515/525),
    # so a take whose only lipsync_score is inf/nan yields 0.0, NOT the 1.0 N/A default.
    assert _best_take_lipsync([{"metadata": {"lipsync_score": float("inf")}}]) == 0.0
    assert _best_take_lipsync([{"metadata": {"lipsync_score": float("nan")}}]) == 0.0
    # sanity: no dialogue/score at all -> 1.0 N/A pass
    assert _best_take_lipsync([{"metadata": {}}]) == pytest.approx(1.0)
    capability_record(claim_id="GATE-10", passed=True)


@pytest.mark.offline
def test_shot_over_budget_edges(capability_record):
    def proj(budget, n_shots):
        return {"global_settings": {"budget_limit_usd": budget},
                "scenes": [{"shots": [{}] * n_shots}] if n_shots else []}
    # NaN budget cap -> fail-closed veto fires
    assert _shot_over_budget({"spent_usd": 1.0}, proj(float("nan"), 1), 1.5) is True
    # zero budget -> no cap -> False
    assert _shot_over_budget({"spent_usd": 9999.0}, proj(0, 1), 1.5) is False
    # zero total_shots (empty scenes) -> cannot compute per-shot cap -> False
    assert _shot_over_budget({"spent_usd": 999.0}, proj(10, 0), 1.5) is False
    # over the multiplier*per-shot cap -> True  (per_shot=10, 1.5*10=15, spent 100>15)
    assert _shot_over_budget({"spent_usd": 100.0}, proj(10, 1), 1.5) is True
    capability_record(claim_id="GATE-11", passed=True)


# --- gate firing + record-review + lifecycle trap (GATE-12..15) ---

@pytest.mark.offline
def test_motion_gate_fires_on_low_motion_fidelity(capability_record):
    # identity_score high (0.99 >= 0.85 passes the identity rule) isolates the motion rule;
    # motion_fidelity 0.5 < 0.7 fires motion_score_below_threshold.
    dec = check_gate(
        "motion",
        shot_state={},
        project={},
        takes=[{"metadata": {"identity_score": 0.99, "motion_fidelity": 0.5}}],
        config=AutoApproveConfig(),
    )
    assert dec.auto_approved is False
    assert "motion_score_below_threshold" in dec.rule_names
    capability_record(claim_id="GATE-12", passed=True)


@pytest.mark.offline
def test_final_gate_fires_on_upstream_auto_approval(capability_record):
    # lipsync_score 1.0 passes the lipsync rule (1.0 >= 0.8) so the only veto is the
    # safety-net: an upstream gate auto-approved this shot -> require a human at final.
    dec = check_gate(
        "final",
        shot_state={"plan_auto_approved": True},
        project={},
        takes=[{"metadata": {"lipsync_score": 1.0}}],
        config=AutoApproveConfig(),
    )
    assert dec.auto_approved is False
    assert "final_upstream_was_auto_approved" in dec.rule_names
    capability_record(claim_id="GATE-13", passed=True)


@pytest.mark.offline
def test_record_director_review_skips_non_dict_items(capability_record):
    shots = [None, {"id": "a"}, 42]
    record_director_review_on_shots(shots, {"decision": "APPROVED", "violations": []})
    assert shots[0] is None and shots[2] == 42        # non-dicts untouched
    assert shots[1]["director_review"]["decision"] == "APPROVED"
    capability_record(claim_id="GATE-14", passed=True)


@pytest.mark.offline
def test_nulllifecycle_wait_for_gate_always_true(capability_record):
    # The always-True trap: NullLifecycle.wait_for_gate returns True regardless of the
    # predicate (cinema/lifecycle.py:89) — so using it OUTSIDE a test/headless context
    # silently skips gate enforcement. This isolates that contract (no ReviewController stack).
    lc = NullLifecycle()
    assert lc.wait_for_gate("PLAN_REVIEW", lambda: False) is True
    assert lc.wait_for_gate("PLAN_REVIEW", lambda: True) is True
    capability_record(claim_id="GATE-15", passed=True)


@pytest.mark.offline
def test_gates_offline_claims_are_exercised():
    """Guard against silent ledger drift: the set of offline 'asserted' claims in the
    gates_orchestration dimension must equal exactly the claims these test files record.
    @pytest.mark.offline so CI's `-m offline` filter does not skip the guard."""
    import _ledger  # top-level via conftest sys.path shim
    offline_asserted = {c.claim_id for c in _ledger.by_dimension("gates_orchestration")
                        if c.tier == "offline" and c.status == "asserted"}
    expected = {f"GATE-{i:02d}" for i in range(1, 16)} | {f"CD-{i:02d}" for i in range(1, 7)}
    assert offline_asserted == expected
