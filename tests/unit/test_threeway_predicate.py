"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_predicate.py -q

These tests exercise the predicate over EFFECTIVE state with a FAKE repo adapter
(no real git) so they stay fast and pure. The real-git path is covered by the gate
suite (Task 14-17).
"""
from threeway.envelope import Event
from threeway.policy import default_policy
from threeway.predicate import evaluate, MAIN_REF, MERGEABLE, PENDING, REJECTED
from threeway.reducer import reduce


BASE = "1" * 40       # staging_base == main.head
INTEG = "2" * 40      # integration_sha
BRANCH = "3" * 40     # branch_sha


class FakeRepo:
    """Stand-in for git: fixed head + a fixed changed-paths map.

    rev_parse_map, when given, models existence: a ref/SHA present in the map
    resolves to its value, anything absent resolves to None (gitcas.rev_parse's
    contract for a nonexistent commit). When omitted, every ref resolves to head.
    """
    def __init__(self, head=BASE, diff=("cinema/foo.py",), rev_parse_map=None):
        self._head = head
        self._diff = list(diff)
        self._rev_parse_map = rev_parse_map

    def rev_parse(self, ref):
        if self._rev_parse_map is not None:
            return self._rev_parse_map.get(ref)
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
    # ADR-039 (hardened candidate resolution): a candidate NOT signed by the assignment's
    # executing_coordinator is no longer self-consistent, so authoritative_candidate ignores
    # it entirely. With the ONLY candidate forged to a non-coordinator signer there is no
    # authoritative candidate at all → PENDING (the gate awaits the real coordinator; the
    # forged candidate has ZERO effect, no merge happens). This is strictly safer than the
    # old REJECTED — never weaken production to restore the REJECTED.
    events = _full_event_set()
    for e in events:
        if e.kind == "candidate":
            e.signer = "operator:claude:s1"  # not the coordinator
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == PENDING and "executing coordinator" in d.reason


def test_same_pair_candidate_shadow_does_not_displace():
    # ADR-039: an insider appends a validly-signed shadow candidate for the SAME id, SAME
    # pair, HIGHER seq, signed by a NON-coordinator seat, carrying attacker base/branch/integ.
    # It must NOT displace the coordinator's authoritative candidate (availability/DoS + a
    # promotion-forgery hazard if the gate later merged the shadow's base/branch).
    events = _full_event_set()
    events.append(_e("candidate", 20, payload={
        "pair": "A",
        "staging_base_sha": "a" * 40, "branch_sha": "b" * 40,
        "integration_sha": "c" * 40, "risk_tier_claimed": "T1",
        "policy_digest": default_policy().policy_digest()},
        subject_sha="c" * 40, signer="operator:claude:s1"))
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == MERGEABLE, d.reason


def test_bogus_pair_candidate_shadow_does_not_block():
    # ADR-039 (pair-redirection variant): the shadow declares a BOGUS pair "Z" with no
    # assignment, HIGHER seq, non-coordinator signer. The naive "read pair from latest
    # candidate" fix would resolve assignment("Z") → None → PENDING and block the legit
    # promotion. authoritative_candidate must skip the non-self-consistent shadow and keep
    # the coordinator's candidate → still MERGEABLE.
    events = _full_event_set()
    events.append(_e("candidate", 20, payload={
        "pair": "Z",
        "staging_base_sha": "a" * 40, "branch_sha": "b" * 40,
        "integration_sha": "c" * 40, "risk_tier_claimed": "T1",
        "policy_digest": default_policy().policy_digest()},
        subject_sha="c" * 40, signer="operator:claude:s1"))
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == MERGEABLE, d.reason


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


def test_rejects_tier_escalation_when_diff_exceeds_cycle_go():
    events = _full_event_set()
    # diff touches CI config -> path-derived T2; cycle_go authorized only T1
    repo = FakeRepo(diff=[".github/workflows/ci.yml"])
    # widen allowed_paths so we isolate the tier clause, not scope
    for e in events:
        if e.kind == "brief":
            e.payload["allowed_paths"] = [".github/"]
    d = evaluate("c1", reduce(events), repo, default_policy())
    assert d.outcome == REJECTED and "tier_escalation" in d.reason


def test_tier_mislabel_below_path_minimum_is_ignored_gate_computes():
    # candidate claims T0 but diff is CI config (T2) and cycle_go is T1 -> escalation
    events = _full_event_set()
    for e in events:
        if e.kind == "candidate":
            e.payload["risk_tier_claimed"] = "T0"
        if e.kind == "brief":
            e.payload["allowed_paths"] = [".github/"]
    repo = FakeRepo(diff=[".github/workflows/ci.yml"])
    d = evaluate("c1", reduce(events), repo, default_policy())
    assert d.outcome == REJECTED and "tier_escalation" in d.reason


def test_rejects_diff_outside_allowed_paths():
    events = _full_event_set()
    repo = FakeRepo(diff=["secrets/leak.txt"])
    d = evaluate("c1", reduce(events), repo, default_policy())
    assert d.outcome == REJECTED and "allowed_paths" in d.reason


def test_rejects_candidate_that_weakened_policy_digest():
    events = _full_event_set()
    for e in events:
        if e.kind == "candidate":
            e.payload["policy_digest"] = "0" * 64  # not the accepted policy
        if e.kind in ("cycle_go", "ci_result"):
            e.payload["policy_digest"] = "0" * 64  # keep them internally consistent
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "policy_digest not accepted" in d.reason


def test_pending_when_ci_result_absent():
    events = [e for e in _full_event_set() if e.kind != "ci_result"]
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == PENDING and "ci_result" in d.reason


def test_rejects_ci_result_not_pass():
    events = _full_event_set()
    for e in events:
        if e.kind == "ci_result":
            e.payload["result"] = "FAIL"
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "ci_result not PASS" in d.reason


def test_rejects_superseded_brief_version():
    events = _full_event_set()
    events.append(_e("brief", 12, brief_version=2,
                     payload={"brief_id": "b1", "allowed_paths": ["cinema/"]},
                     signer="overseer:mech:s1"))
    # candidate is still on version 1, now superseded by version 2
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "superseded" in d.reason


def test_rejects_aborted_candidate():
    events = _full_event_set()
    events.append(_e("candidate_aborted", 13))
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "aborted" in d.reason


def test_rejects_sibling_prefix_path_with_no_trailing_slash():
    # an allowed prefix WITHOUT a trailing slash must not swallow a sibling dir
    events = _full_event_set()
    for e in events:
        if e.kind == "brief":
            e.payload["allowed_paths"] = ["cinema"]      # no trailing slash
    repo = FakeRepo(diff=["cinemax/leak.py"])            # sibling — must REJECT
    d = evaluate("c1", reduce(events), repo, default_policy())
    assert d.outcome == REJECTED and "allowed_paths" in d.reason


def test_rejects_nonexistent_integration_sha():
    # main_ref + staging_base resolve (so the :53 stale check passes) but the
    # attested integration_sha resolves to None -> existence guard must REJECT,
    # never crash changed_paths on a ghost SHA.
    events = _full_event_set()
    repo = FakeRepo(rev_parse_map={MAIN_REF: BASE, BASE: BASE})  # INTEG -> None
    d = evaluate("c1", reduce(events), repo, default_policy())
    assert d.outcome == REJECTED and "known commit" in d.reason


def _pair_b_assignment(seq):
    return _e("assignment", seq, payload={
        "pair": "B", "builder": "director2", "builder_provider": "claude",
        "primary_verifier": "operator2", "primary_verifier_provider": "codex",
        "executing_coordinator": "coordinator2"}, signer="overseer:mech:s1")


def _t2_event_set():
    evs = _full_event_set()
    for e in evs:
        if e.kind == "brief":
            e.payload["allowed_paths"] = [".github/"]
            e.payload["assigned_tier"] = "T2"
        elif e.kind == "candidate":
            e.payload["risk_tier_claimed"] = "T2"
        elif e.kind == "cycle_go":
            e.payload["tier"] = "T2"
    evs.append(_pair_b_assignment(10))
    evs.append(_e("co_sign", 11, payload={"verdict": "GO"}, subject_sha=INTEG,
                  signer="operator2:codex:s1"))
    return evs


T2_REPO = FakeRepo(diff=(".github/workflows/ci.yml",))


def test_t2_mergeable_with_mirror_cosign():
    d = evaluate("c1", reduce(_t2_event_set()), T2_REPO, default_policy())
    assert d.outcome == MERGEABLE, d.reason


def test_t2_pending_without_cosign():
    evs = [e for e in _t2_event_set() if e.kind != "co_sign"]
    d = evaluate("c1", reduce(evs), T2_REPO, default_policy())
    assert d.outcome == PENDING and "co_sign not satisfied for T2" in d.reason


def test_t2_pending_with_provider_spoofed_cosign():
    evs = _t2_event_set()
    evs[-1] = _e("co_sign", 11, payload={"verdict": "GO"}, subject_sha=INTEG,
                 signer="operator:codex:s9")
    d = evaluate("c1", reduce(evs), T2_REPO, default_policy())
    assert d.outcome == PENDING and "co_sign not satisfied for T2" in d.reason


# --- ADR-036: forged-revoke cannot defeat the fail-closed mirror resolution. The mirror
# set is revocation-aware (Slice 3), and revokes_event_id is unsigned, so without a revoke-
# authority check any insider seat could revoke a rival/legit overseer-signed assignment to
# either forge a promotion (collapse ambiguity onto a seat it controls) or deny a valid one.

def _t2_two_mirror_exploit_events():
    """A T2 candidate (pair A) with TWO genuinely swap-eligible mirror pairs — B (verifier
    operator2) and C (verifier operatorB) — so resolution is ambiguous and fails closed.
    The attacker controls operatorB and pre-positions its own co_sign GO."""
    evs = _t2_event_set()   # pair B assignment (e10) + operator2 co_sign (e11)
    evs.append(_e("assignment", 12, payload={
        "pair": "C", "builder": "directorC", "builder_provider": "claude",
        "primary_verifier": "operatorB", "primary_verifier_provider": "codex",
        "executing_coordinator": "coordinatorC"}, signer="overseer:mech:s1"))
    evs.append(_e("co_sign", 13, payload={"verdict": "GO"}, subject_sha=INTEG,
                  signer="operatorB:codex:s1"))   # attacker's own co_sign
    return evs


def test_forged_nonoverseer_revoke_cannot_collapse_t2_mirror_ambiguity():
    evs = _t2_two_mirror_exploit_events()
    # genuine ambiguity (two mirrors) must fail closed
    assert evaluate("c1", reduce(evs), T2_REPO, default_policy()).outcome == PENDING
    # attacker forges a non-overseer revoke of the RIVAL mirror's overseer-signed assignment;
    # it must be ignored, so the gate stays PENDING (no forged promotion).
    evs.append(_e("attestation_revoked", 14, revokes_event_id="e10",
                  signer="operatorB:codex:s1"))
    assert evaluate("c1", reduce(evs), T2_REPO, default_policy()).outcome == PENDING


def test_forged_nonoverseer_revoke_cannot_deny_legit_mirror():
    evs = _t2_event_set()   # single legit mirror → MERGEABLE
    assert evaluate("c1", reduce(evs), T2_REPO, default_policy()).outcome == MERGEABLE
    # a non-overseer seat must not revoke the overseer-signed mirror assignment (merge DoS)
    evs.append(_e("attestation_revoked", 12, revokes_event_id="e10",
                  signer="operator:claude:s1"))   # not overseer, not the target's seat
    assert evaluate("c1", reduce(evs), T2_REPO, default_policy()).outcome == MERGEABLE


def test_overseer_revoke_of_mirror_assignment_denies_promotion():
    evs = _t2_event_set()
    evs.append(_e("attestation_revoked", 12, revokes_event_id="e10",
                  signer="overseer:mech:s1"))   # authorized control-plane revoke
    d = evaluate("c1", reduce(evs), T2_REPO, default_policy())
    assert d.outcome == PENDING and "co_sign not satisfied for T2" in d.reason


def _t3_event_set():
    evs = _full_event_set()
    for e in evs:
        if e.kind == "brief":
            e.payload["allowed_paths"] = ["coordination/threeway/keys/"]
            e.payload["assigned_tier"] = "T3"
        elif e.kind == "candidate":
            e.payload["risk_tier_claimed"] = "T3"
        elif e.kind == "cycle_go":
            e.payload["tier"] = "T3"
    evs += [
        _pair_b_assignment(10),
        _e("co_sign", 11, payload={"verdict": "GO"}, subject_sha=INTEG,
           signer="operator2:codex:s1"),
        _e("re_verify", 12, payload={"verdict": "GO"}, subject_sha=INTEG,
           signer="operator:claude:s2"),
        _e("human_approval", 13, payload={"approver_identity": "chief-gemini",
           "integration_sha": INTEG, "decision": "approve"}, signer="overseer:mech:s1"),
        _e("human_approval", 14, payload={"approver_identity": "chief-chatgpt",
           "integration_sha": INTEG, "decision": "approve"}, signer="overseer:mech:s1"),
    ]
    return evs


T3_REPO = FakeRepo(diff=("coordination/threeway/keys/operator.pub",))


def test_t3_mergeable_with_full_cross_family_set():
    d = evaluate("c1", reduce(_t3_event_set()), T3_REPO, default_policy())
    assert d.outcome == MERGEABLE, d.reason


def test_t3_pending_without_re_verify():
    evs = [e for e in _t3_event_set() if e.kind != "re_verify"]
    d = evaluate("c1", reduce(evs), T3_REPO, default_policy())
    assert d.outcome == PENDING and "co_sign not satisfied for T3" in d.reason


def test_t3_pending_with_one_human_approval():
    evs = [e for e in _t3_event_set() if not (e.kind == "human_approval"
           and e.payload.get("approver_identity") == "chief-chatgpt")]
    d = evaluate("c1", reduce(evs), T3_REPO, default_policy())
    assert d.outcome == PENDING and "co_sign not satisfied for T3" in d.reason


def test_revoked_assignment_is_pending():
    evs = _full_event_set()
    # e2 = the assignment; overseer is authorized to revoke it (ADR-036)
    evs.append(_e("attestation_revoked", 12, revokes_event_id="e2", signer="overseer:mech:s1"))
    d = evaluate("c1", reduce(evs), FakeRepo(), default_policy())
    # ADR-039 reason-string shift (still PENDING / non-merge, security preserved): with the
    # assignment revoked, NO candidate is self-consistent (authoritative_candidate finds no
    # overseer assignment for the candidate's pair), so evaluate reports "no candidate from
    # executing coordinator" rather than the old "no assignment fact for pair". Same fail-closed
    # outcome — the revoked control-plane fact still blocks the merge.
    assert d.outcome == PENDING and "executing coordinator" in d.reason
