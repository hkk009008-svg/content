"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_reducer.py -q"""
from threeway.envelope import Event
from threeway.reducer import reduce


def _ev(seq, kind, payload=None, **over):
    base = dict(
        id=f"e{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
        kind=kind, sender="operator", recipient="all",
        signer="operator:claude:s1", payload=payload or {},
        candidate_id="c1", brief_id="b1", brief_version=1,
    )
    base.update(over)
    return Event(**base)


def _att(seq, verdict, subject="dead", kind_att="release", signer="operator:claude:s1", **o):
    return _ev(seq, "attestation",
               payload={"kind": kind_att, "verdict": verdict},
               subject_sha=subject, signer=signer, **o)


def test_latest_verdict_wins_go_then_fail_leaves_no_effective_go():
    state = reduce([_att(1, "GO"), _att(2, "FAIL")])
    eff = state.effective_attestation("c1", "release", "operator")
    assert eff is not None and eff.payload["verdict"] == "FAIL"


def test_explicit_revocation_removes_effective_attestation():
    events = [_att(1, "GO"), _ev(2, "attestation_revoked", revokes_event_id="e1")]
    state = reduce(events)
    assert state.effective_attestation("c1", "release", "operator") is None


def test_distinct_signers_tracked_separately():
    a = _att(1, "GO", signer="operator:claude:s1")
    b = _att(2, "FAIL", signer="operator2:codex:s1")
    state = reduce([a, b])
    assert state.effective_attestation("c1", "release", "operator").payload["verdict"] == "GO"
    assert state.effective_attestation("c1", "release", "operator2").payload["verdict"] == "FAIL"


def test_candidate_aborted_is_recorded():
    state = reduce([_ev(1, "candidate_aborted")])
    assert state.is_aborted("c1")


def test_latest_non_superseded_brief_version():
    events = [
        _ev(1, "brief", brief_version=1, payload={"brief_id": "b1"}),
        _ev(2, "brief", brief_version=2, payload={"brief_id": "b1"}),
        _ev(3, "brief_superseded", brief_version=1, supersedes_event_id="e1"),
    ]
    state = reduce(events)
    assert state.latest_brief_version("b1") == 2


def test_latest_brief_version_skips_a_superseded_latest():
    # the LATEST version (v2) is superseded -> latest live version is v1
    events = [
        _ev(1, "brief", brief_version=1, payload={"brief_id": "b1"}),
        _ev(2, "brief", brief_version=2, payload={"brief_id": "b1"}),
        _ev(3, "brief_superseded", brief_version=2, supersedes_event_id="e2"),
    ]
    state = reduce(events)
    assert state.latest_brief_version("b1") == 1


def test_brief_accessor_returns_event_or_none():
    state = reduce([_ev(1, "brief", brief_version=1, payload={"brief_id": "b1"})])
    assert state.brief("b1", 1) is not None
    assert state.brief("b1", 2) is None


def test_release_order_lookup_by_candidate_and_sha():
    state = reduce([_ev(1, "release_order", subject_sha="abc",
                        payload={"candidate_id": "c1"})])
    ro = state.release_order("c1")
    assert ro is not None and ro.subject_sha == "abc"


def test_cycle_go_lookup_returns_latest():
    events = [
        _ev(1, "cycle_go", payload={"brief_id": "b1", "brief_version": 1, "tier": "T1"}),
        _ev(2, "cycle_go", payload={"brief_id": "b1", "brief_version": 1, "tier": "T2"}),
    ]
    state = reduce(events)
    assert state.cycle_go("b1", 1).payload["tier"] == "T2"


def test_ci_result_lookup_by_sha():
    state = reduce([_ev(1, "ci_result", subject_sha="sha9",
                        payload={"result": "PASS", "policy_digest": "p1"})])
    assert state.ci_result("sha9").payload["result"] == "PASS"


def test_merge_completed_lookup_for_idempotency():
    state = reduce([_ev(1, "merge_completed", payload={"candidate_id": "c1"})])
    assert state.merge_completed("c1") is not None
