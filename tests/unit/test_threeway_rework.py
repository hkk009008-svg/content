"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_rework.py -q

Authority-aware rework circuit-breaker (ADR-060 / C1 Part 2). should_escalate counts only
AUTHORIZED reworks — candidates aborted by their bound-pair executing_coordinator (ADR-059
is_aborted), tied to the AUTHORITATIVE candidate's brief_id/brief_version — so a forged abort can
neither trip the breaker (a forced-ESCALATE merge-DoS) nor inflate a rival brief-version's count.
"""
from threeway.envelope import Event
from threeway.reducer import reduce
from threeway.rework import rework_count, should_escalate, REWORK_CAP


def _ev(seq, kind, payload=None, **over):
    base = dict(
        id=f"e{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
        kind=kind, sender="x", recipient="all", signer="coordinator:claude:s1",
        payload=payload or {}, candidate_id="A:c1", brief_id="b1", brief_version=1,
    )
    base.update(over)
    return Event(**base)


def _assignment(seq, pair="A", coordinator="coordinator"):
    # overseer-signed assignment binding `pair` to its executing_coordinator
    return _ev(seq, "assignment",
               payload={"pair": pair, "executing_coordinator": coordinator},
               signer="overseer:mech:s1", candidate_id=f"{pair}:assign")


def _cycles(start_seq, n, *, brief_version=1, abort_signer="coordinator:claude:s1",
            cand_signer="coordinator:claude:s1", pair="A"):
    """n rework cycles, each = a (candidate, candidate_aborted) pair for a distinct cid."""
    events, seq = [], start_seq
    for i in range(n):
        cid = f"{pair}:c{i}"
        events.append(_ev(seq, "candidate", payload={"pair": pair}, candidate_id=cid,
                          signer=cand_signer, brief_version=brief_version))
        seq += 1
        events.append(_ev(seq, "candidate_aborted", candidate_id=cid,
                          signer=abort_signer, brief_version=brief_version))
        seq += 1
    return events


def test_three_authorized_reworks_escalate():
    state = reduce([_assignment(1)] + _cycles(2, 3))
    assert rework_count(state, "b1", 1) == 3
    assert should_escalate(state, "b1", 1)


def test_two_authorized_reworks_do_not_escalate():
    # boundary: REWORK_CAP (2) is allowed; the cap is a strict `>` so 2 does NOT escalate
    state = reduce([_assignment(1)] + _cycles(2, REWORK_CAP))
    assert rework_count(state, "b1", 1) == REWORK_CAP
    assert not should_escalate(state, "b1", 1)


def test_forged_aborts_from_non_coordinator_do_not_count():
    # ADR-060 (forced-ESCALATE merge-DoS): aborts signed by an operator (NOT the executing
    # coordinator) are unauthorized -> not counted -> the breaker is NOT tripped by a forger.
    state = reduce([_assignment(1)] + _cycles(2, 3, abort_signer="operator:claude:s1"))
    assert rework_count(state, "b1", 1) == 0
    assert not should_escalate(state, "b1", 1)


def test_cross_pair_coordinator_aborts_do_not_count():
    # coordinator2 (the OTHER pair's coordinator) cannot abort pair-A candidates.
    state = reduce([_assignment(1)] + _cycles(2, 3, abort_signer="coordinator2:claude:s1"))
    assert rework_count(state, "b1", 1) == 0


def test_reworks_scoped_to_brief_version():
    # 3 authorized reworks under v1 do not count toward v2 (the brief version is the
    # authoritative candidate's signed brief_version).
    state = reduce([_assignment(1)] + _cycles(2, 3, brief_version=1))
    assert rework_count(state, "b1", 1) == 3
    assert rework_count(state, "b1", 2) == 0


def test_authorized_abort_without_candidate_is_not_a_rework_cycle():
    # an authorized-signer abort with NO candidate fact has no authoritative_candidate -> no real
    # rework cycle -> not counted (the count ties to the verified candidate, not the abort's claim).
    state = reduce([
        _assignment(1),
        _ev(2, "candidate_aborted", candidate_id="A:cX", signer="coordinator:claude:s1"),
    ])
    assert rework_count(state, "b1", 1) == 0


def test_distinct_candidates_counted_once_each_despite_multiple_aborts():
    # two abort events for the SAME candidate = one rework cycle, not two.
    state = reduce([
        _assignment(1),
        _ev(2, "candidate", payload={"pair": "A"}, candidate_id="A:c0",
            signer="coordinator:claude:s1"),
        _ev(3, "candidate_aborted", candidate_id="A:c0", signer="coordinator:claude:s1"),
        _ev(4, "candidate_aborted", candidate_id="A:c0", signer="coordinator:claude:s1"),
    ])
    assert rework_count(state, "b1", 1) == 1
