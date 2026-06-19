"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_predicate.py -q

These tests exercise the predicate over EFFECTIVE state with a FAKE repo adapter
(no real git) so they stay fast and pure. The real-git path is covered by the gate
suite (Task 14-17).
"""
from threeway.envelope import Event
from threeway.policy import default_policy
from threeway.predicate import evaluate, MERGEABLE, PENDING, REJECTED
from threeway.reducer import reduce


BASE = "1" * 40       # staging_base == main.head
INTEG = "2" * 40      # integration_sha
BRANCH = "3" * 40     # branch_sha


class FakeRepo:
    """Stand-in for git: fixed head + a fixed changed-paths map."""
    def __init__(self, head=BASE, diff=("cinema/foo.py",)):
        self._head = head
        self._diff = list(diff)

    def rev_parse(self, ref):
        return self._head

    def changed_paths(self, base, head):
        return list(self._diff)


def _e(kind, seq, **over):
    base = dict(
        id=f"e{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
        kind=kind, sender="x", recipient="all", signer="x:p:s1", payload={},
        candidate_id="c1", brief_id="b1", brief_version=1,
    )
    base.update(over)
    return Event(**base)


def _full_event_set():
    """A complete, valid T1 promotion for candidate c1."""
    return [
        _e("brief", 1, payload={"brief_id": "b1", "allowed_paths": ["cinema/"]},
           signer="overseer:mech:s1"),
        _e("assignment", 2, payload={
            "pair": "A", "builder": "director", "builder_provider": "codex",
            "primary_verifier": "operator", "primary_verifier_provider": "claude",
            "executing_coordinator": "coordinator"}, signer="overseer:mech:s1"),
        _e("candidate", 3, payload={
            "pair": "A", "staging_base_sha": BASE, "branch_sha": BRANCH,
            "integration_sha": INTEG, "risk_tier_claimed": "T1",
            "policy_digest": default_policy().policy_digest()},
           subject_sha=INTEG, signer="coordinator:claude:s1"),
        _e("attestation", 4, payload={"kind": "preliminary", "verdict": "GO"},
           subject_sha=BRANCH, signer="operator:claude:s1"),
        _e("attestation", 5, payload={"kind": "release", "verdict": "GO"},
           subject_sha=INTEG, signer="operator:claude:s1"),
        _e("cycle_go", 6, payload={"brief_id": "b1", "brief_version": 1, "tier": "T1",
           "policy_digest": default_policy().policy_digest()}, signer="overseer:mech:s1"),
        _e("ci_result", 7, subject_sha=INTEG, payload={
            "result": "PASS", "policy_digest": default_policy().policy_digest()},
           signer="ci:mech:s1"),
        _e("release_requested", 8, payload={"candidate_id": "c1"},
           subject_sha=INTEG, signer="coordinator:claude:s1"),
        _e("release_order", 9, payload={"candidate_id": "c1"},
           subject_sha=INTEG, signer="overseer:mech:s1"),
    ]


def test_full_valid_set_is_mergeable():
    state = reduce(_full_event_set())
    d = evaluate("c1", state, FakeRepo(), default_policy())
    assert d.outcome == MERGEABLE, d.reason


def test_rejects_when_verifier_same_provider_as_builder():
    events = _full_event_set()
    for e in events:
        if e.kind == "assignment":
            e.payload["primary_verifier_provider"] = "codex"  # == builder
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "same provider" in d.reason


def test_rejects_candidate_not_signed_by_executing_coordinator():
    events = _full_event_set()
    for e in events:
        if e.kind == "candidate":
            e.signer = "operator:claude:s1"  # not the coordinator
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "executing coordinator" in d.reason


def test_go_then_fail_release_leaves_no_effective_go_pending():
    events = _full_event_set()
    events.append(_e("attestation", 10, payload={"kind": "release", "verdict": "FAIL"},
                     subject_sha=INTEG, signer="operator:claude:s1"))
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == PENDING and "release GO" in d.reason


def test_revoked_release_attestation_is_pending():
    events = _full_event_set()
    # revoke the release attestation (e5)
    events.append(_e("attestation_revoked", 11, revokes_event_id="e5",
                     signer="operator:claude:s1"))
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == PENDING


def test_rejects_release_attestation_bound_to_wrong_sha():
    events = _full_event_set()
    for e in events:
        if e.kind == "attestation" and e.payload.get("kind") == "release":
            e.subject_sha = "9" * 40
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "integration_sha" in d.reason


def test_rejects_stale_staging_base_when_main_moved():
    events = _full_event_set()
    moved = FakeRepo(head="f" * 40)  # main.head != staging_base
    d = evaluate("c1", reduce(events), moved, default_policy())
    assert d.outcome == REJECTED and "stale" in d.reason


def test_pending_when_release_order_absent():
    events = [e for e in _full_event_set() if e.kind != "release_order"]
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == PENDING and "release_order" in d.reason
