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
        _ev(1, "brief", brief_version=1, payload={"brief_id": "b1"}, signer="overseer:mech:s1"),
        _ev(2, "brief", brief_version=2, payload={"brief_id": "b1"}, signer="overseer:mech:s1"),
        _ev(3, "brief_superseded", brief_version=1, supersedes_event_id="e1",
            signer="overseer:mech:s1"),
    ]
    state = reduce(events)
    assert state.latest_brief_version("b1") == 2


def test_latest_brief_version_skips_a_superseded_latest():
    # the LATEST version (v2) is superseded -> latest live version is v1
    events = [
        _ev(1, "brief", brief_version=1, payload={"brief_id": "b1"}, signer="overseer:mech:s1"),
        _ev(2, "brief", brief_version=2, payload={"brief_id": "b1"}, signer="overseer:mech:s1"),
        _ev(3, "brief_superseded", brief_version=2, supersedes_event_id="e2",
            signer="overseer:mech:s1"),
    ]
    state = reduce(events)
    assert state.latest_brief_version("b1") == 1


def test_brief_accessor_returns_event_or_none():
    state = reduce([_ev(1, "brief", brief_version=1, payload={"brief_id": "b1"},
                        signer="overseer:mech:s1")])
    assert state.brief("b1", 1) is not None
    assert state.brief("b1", 2) is None


def test_release_order_lookup_by_candidate_and_sha():
    state = reduce([_ev(1, "release_order", subject_sha="abc",
                        payload={"candidate_id": "c1"}, signer="overseer:mech:s1")])
    ro = state.release_order("c1")
    assert ro is not None and ro.subject_sha == "abc"


def test_cycle_go_lookup_returns_latest():
    events = [
        _ev(1, "cycle_go", payload={"brief_id": "b1", "brief_version": 1, "tier": "T1"},
            signer="overseer:mech:s1"),
        _ev(2, "cycle_go", payload={"brief_id": "b1", "brief_version": 1, "tier": "T2"},
            signer="overseer:mech:s1"),
    ]
    state = reduce(events)
    assert state.cycle_go("b1", 1).payload["tier"] == "T2"


def test_ci_result_lookup_by_sha():
    state = reduce([_ev(1, "ci_result", subject_sha="sha9",
                        payload={"result": "PASS", "policy_digest": "p1"},
                        signer="ci:mech:s1")])
    assert state.ci_result("sha9").payload["result"] == "PASS"


def test_merge_completed_lookup_for_idempotency():
    state = reduce([_ev(1, "merge_completed", payload={"candidate_id": "c1"},
                        signer="merge-gate:mech:gate")])
    assert state.merge_completed("c1") is not None


INTEG = "2" * 40


def test_co_sign_accessor_hides_revoked():
    cs = _ev(1, "co_sign", payload={"verdict": "GO"}, subject_sha=INTEG,
             signer="operator2:codex:s1")
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1",
              signer="overseer:mech:s1")   # cs.id == "e1"; authorized (overseer)
    assert reduce([cs]).co_sign("c1", "operator2") is not None
    assert reduce([cs, rev]).co_sign("c1", "operator2") is None


def test_re_verify_accessor_hides_revoked():
    rv = _ev(1, "re_verify", payload={"verdict": "GO"}, subject_sha=INTEG,
             signer="operator:claude:s2")
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1")
    assert reduce([rv, rev]).re_verify("c1", "operator") is None


def test_human_approvals_accessor_hides_revoked():
    h = _ev(1, "human_approval", signer="overseer:mech:s1",
            payload={"approver_identity": "chief-gemini", "integration_sha": INTEG,
                     "decision": "approve"})
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1", signer="overseer:mech:s1")
    assert reduce([h]).human_approvals("c1") != []
    assert reduce([h, rev]).human_approvals("c1") == []


def test_assignments_returns_latest_per_pair():
    a1 = _ev(1, "assignment", payload={"pair": "A", "primary_verifier": "operator"},
             signer="overseer:mech:s1")
    a2 = _ev(2, "assignment", payload={"pair": "B", "primary_verifier": "operator2"},
             signer="overseer:mech:s1")
    a1b = _ev(3, "assignment", payload={"pair": "A", "primary_verifier": "operatorX"},
              signer="overseer:mech:s1")          # same pair, higher seq → supersedes a1
    got = {e.payload["pair"]: e.payload["primary_verifier"]
           for e in reduce([a1, a2, a1b]).assignments()}
    assert got == {"A": "operatorX", "B": "operator2"}   # last-write-wins for A


def test_assignments_hides_revoked():
    a = _ev(1, "assignment", payload={"pair": "A"}, signer="overseer:mech:s1")
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1", signer="overseer:mech:s1")
    assert reduce([a, rev]).assignments() == []


def test_assignment_singular_accessor_hides_revoked():
    a = _ev(1, "assignment", payload={"pair": "A", "primary_verifier": "operator"},
            signer="overseer:mech:s1")
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1",
              signer="overseer:mech:s1")   # a.id == "e1"; authorized (overseer)
    assert reduce([a]).assignment("A") is not None
    assert reduce([a, rev]).assignment("A") is None


# --- revoke authority (ADR-036): revokes_event_id is UNSIGNED, so a revoke takes effect
# only from the overseer (control-plane override) or the target's own signer seat
# (self-revocation). Any other seat's revoke is IGNORED. ---

def test_unauthorized_seat_revoke_is_ignored():
    a = _ev(1, "assignment", payload={"pair": "A"}, signer="overseer:mech:s1")
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1",
              signer="operatorB:codex:s1")   # not overseer, not the target's seat
    assert reduce([a, rev]).assignments() != []   # forged revoke has no authority → ignored


def test_overseer_revoke_of_other_seats_fact_is_honored():
    cs = _ev(1, "co_sign", payload={"verdict": "GO"}, signer="operator2:codex:s1")
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1", signer="overseer:mech:s1")
    assert reduce([cs, rev]).co_sign("c1", "operator2") is None   # overseer may revoke anything


def test_self_revocation_is_honored_across_sessions():
    cs = _ev(1, "co_sign", payload={"verdict": "GO"}, signer="operator2:codex:s1")
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1",
              signer="operator2:codex:s9")   # same seat, different session → self-revocation
    assert reduce([cs, rev]).co_sign("c1", "operator2") is None


def test_id_collision_cannot_forge_self_revocation():
    # ADR-036 follow-up: event `id` is signed but not globally unique. A decoy re-using a
    # victim fact's id (attacker's OWN seat, higher seq) must NOT let the decoy's seat forge
    # a "self-revocation" — a CONTESTED id (>1 signer seat) is overseer-only revocable.
    victim = _ev(1, "co_sign", payload={"verdict": "GO"}, signer="operator2:codex:s1")  # id e1
    decoy = _ev(2, "attestation", payload={"kind": "release", "verdict": "GO"},
                signer="operator:claude:s1", id="e1")          # collides with the victim's id
    revoke = _ev(3, "attestation_revoked", revokes_event_id="e1", signer="operator:claude:s1")
    assert reduce([victim, decoy, revoke]).co_sign("c1", "operator2") is not None


def test_overseer_can_revoke_contested_id():
    victim = _ev(1, "co_sign", payload={"verdict": "GO"}, signer="operator2:codex:s1")
    decoy = _ev(2, "attestation", payload={"kind": "release"}, signer="operator:claude:s1", id="e1")
    revoke = _ev(3, "attestation_revoked", revokes_event_id="e1", signer="overseer:mech:s1")
    assert reduce([victim, decoy, revoke]).co_sign("c1", "operator2") is None   # overseer override


def test_non_load_bearing_event_cannot_contest_id_to_block_self_revoke():
    # ADR-037: seat_by_id is built from LOAD-BEARING events only, so a non-load-bearing carrier
    # re-using a victim's id cannot contest it and block the victim's legitimate self-revoke.
    att = _att(1, "GO")                                           # operator release GO, id e1
    shadow = _ev(2, "event_sent", signer="director:codex:s1", id="e1")   # non-LB, colliding id
    rev = _ev(3, "attestation_revoked", revokes_event_id="e1",
              signer="operator:claude:s9")                        # operator self-revokes its own GO
    assert reduce([att, shadow, rev]).effective_attestation("c1", "release", "operator") is None


def test_forged_nonoverseer_brief_supersede_is_ignored():
    # Rule #13 sibling of revoke-authority: supersedes_event_id is the OTHER unsigned reference
    # field (envelope.py:67-69); a non-overseer brief_superseded must NOT roll back an
    # overseer-signed brief version (same authority rule as a revoke).
    b1 = _ev(1, "brief", brief_version=1, payload={"brief_id": "b1"}, signer="overseer:mech:s1")
    b2 = _ev(2, "brief", brief_version=2, payload={"brief_id": "b1"}, signer="overseer:mech:s1")
    forged = _ev(3, "brief_superseded", supersedes_event_id="e2", signer="operator:claude:s1")
    assert reduce([b1, b2, forged]).latest_brief_version("b1") == 2   # forged supersede ignored


def test_overseer_brief_supersede_is_honored():
    b1 = _ev(1, "brief", brief_version=1, payload={"brief_id": "b1"}, signer="overseer:mech:s1")
    b2 = _ev(2, "brief", brief_version=2, payload={"brief_id": "b1"}, signer="overseer:mech:s1")
    sup = _ev(3, "brief_superseded", supersedes_event_id="e2", signer="overseer:mech:s1")
    assert reduce([b1, b2, sup]).latest_brief_version("b1") == 1   # v2 superseded by overseer


# --- record-time authority filter for the 6 static singleton kinds (ADR-039,
# defect threeway-reducer-shadow-dos, MAJOR availability) ---
# The stores auto-assign a monotonic seq, so an insider's higher-seq event appended
# AFTER the authoritative one would win a plain last-write-wins map slot and shadow
# the legitimate fact (blocking a legit promotion — a DoS). The reducer must resolve
# each static singleton to the latest event FROM ITS AUTHORIZED SEAT, never merely
# the latest seat. A non-authorized event of these kinds is ignored for effective
# state (it may still exist on the bus). Authority table:
#   assignment/brief/cycle_go/release_order -> overseer
#   ci_result -> ci
#   merge_completed -> the gate seat (default "merge-gate")

def test_nonoverseer_assignment_shadow_does_not_displace():
    legit = _ev(2, "assignment", payload={"pair": "A", "primary_verifier": "operator"},
                signer="overseer:mech:s1")
    shadow = _ev(9, "assignment", payload={"pair": "A", "primary_verifier": "attacker"},
                 signer="operator:claude:s1")          # higher seq, non-overseer
    st = reduce([legit, shadow])
    assert st.assignment("A").signer == "overseer:mech:s1"
    assert st.assignment("A").payload["primary_verifier"] == "operator"


def test_nonci_ci_result_shadow_does_not_displace():
    legit = _ev(2, "ci_result", subject_sha="sha9",
                payload={"result": "PASS", "policy_digest": "p1"}, signer="ci:mech:s1")
    shadow = _ev(9, "ci_result", subject_sha="sha9",
                 payload={"result": "FAIL", "policy_digest": "p1"},
                 signer="operator:claude:s1")           # higher seq, non-ci
    st = reduce([legit, shadow])
    assert st.ci_result("sha9").signer == "ci:mech:s1"
    assert st.ci_result("sha9").payload["result"] == "PASS"


def test_nonoverseer_release_order_shadow_does_not_displace():
    legit = _ev(2, "release_order", subject_sha="abc",
                payload={"candidate_id": "c1"}, signer="overseer:mech:s1")
    shadow = _ev(9, "release_order", subject_sha="xyz",
                 payload={"candidate_id": "c1"}, signer="operator:claude:s1")  # higher seq
    st = reduce([legit, shadow])
    assert st.release_order("c1").signer == "overseer:mech:s1"
    assert st.release_order("c1").subject_sha == "abc"


def test_nonoverseer_cycle_go_shadow_does_not_displace():
    legit = _ev(2, "cycle_go",
                payload={"brief_id": "b1", "brief_version": 1, "tier": "T1"},
                signer="overseer:mech:s1")
    shadow = _ev(9, "cycle_go",
                 payload={"brief_id": "b1", "brief_version": 1, "tier": "FORGED"},
                 signer="operator:claude:s1")            # higher seq, non-overseer
    st = reduce([legit, shadow])
    assert st.cycle_go("b1", 1).signer == "overseer:mech:s1"
    assert st.cycle_go("b1", 1).payload["tier"] == "T1"


def test_nonoverseer_brief_shadow_does_not_displace():
    legit = _ev(2, "brief", brief_version=1, payload={"brief_id": "b1", "body": "real"},
                signer="overseer:mech:s1")
    shadow = _ev(9, "brief", brief_version=1, payload={"brief_id": "b1", "body": "forged"},
                 signer="operator:claude:s1")            # higher seq, non-overseer
    st = reduce([legit, shadow])
    assert st.brief("b1", 1).signer == "overseer:mech:s1"
    assert st.brief("b1", 1).payload["body"] == "real"


def test_nongate_merge_completed_shadow_does_not_displace():
    legit = _ev(2, "merge_completed", payload={"candidate_id": "c1"},
                signer="merge-gate:mech:gate")
    shadow = _ev(9, "merge_completed", payload={"candidate_id": "c1"},
                 signer="operator:claude:s1")            # higher seq, non-gate seat
    st = reduce([legit, shadow])
    assert st.merge_completed("c1").signer == "merge-gate:mech:gate"


def test_authorized_assignment_latest_still_wins():
    # GUARD: prove the filter does not over-drop — two overseer assignments,
    # higher seq still wins (last-authorized-write-wins preserved).
    a1 = _ev(2, "assignment", payload={"pair": "A", "primary_verifier": "operator"},
             signer="overseer:mech:s1")
    a2 = _ev(9, "assignment", payload={"pair": "A", "primary_verifier": "operatorX"},
             signer="overseer:mech:s9")          # same authorized seat, higher seq
    st = reduce([a1, a2])
    assert st.assignment("A").payload["primary_verifier"] == "operatorX"


def test_merge_completed_honors_overridden_gate_seat():
    # the gate seat name is injectable; merge_completed authority follows it.
    legit = _ev(2, "merge_completed", payload={"candidate_id": "c1"},
                signer="custom-gate:mech:gate")
    shadow = _ev(9, "merge_completed", payload={"candidate_id": "c1"},
                 signer="merge-gate:mech:gate")   # default name is NOT authorized here
    st = reduce([legit, shadow], gate_seat="custom-gate")
    assert st.merge_completed("c1").signer == "custom-gate:mech:gate"


# --- ADR-039 candidate shadow-DoS: _candidates is keyed by (candidate_id, seat) and the
# authoritative candidate is the one self-consistent with the overseer's assignment
# (signed by the executing_coordinator the overseer assigned to the pair the candidate
# itself declares). A shadow (bogus pair, or non-coordinator signer) is NOT self-consistent.

def _cand(seq, pair, signer, **over):
    return _ev(seq, "candidate", payload={
        "pair": pair, "staging_base_sha": "1" * 40, "branch_sha": "3" * 40,
        "integration_sha": "2" * 40, "risk_tier_claimed": "T1"},
        subject_sha="2" * 40, signer=signer, **over)


def test_candidate_keyed_by_seat():
    coord = _cand(2, "A", "coordinator:claude:s1", candidate_id="A:c1")
    op = _cand(9, "A", "operator:claude:s1", candidate_id="A:c1")   # higher seq, different seat
    st = reduce([coord, op])
    assert st.candidate("A:c1", "coordinator").signer == "coordinator:claude:s1"
    assert st.candidate("A:c1", "operator").signer == "operator:claude:s1"
    # one-arg locate still works: latest-by-seq across all seats
    assert st.candidate("A:c1").signer == "operator:claude:s1"


def test_authoritative_candidate_resolves_to_executing_coordinator():
    coord = _cand(2, "A", "coordinator:claude:s1", candidate_id="A:c1")
    shadow = _cand(9, "A", "operator:claude:s1", candidate_id="A:c1")   # higher seq, non-coordinator
    assign = _ev(3, "assignment", payload={
        "pair": "A", "executing_coordinator": "coordinator"}, signer="overseer:mech:s1")
    st = reduce([coord, shadow, assign])
    auth = st.authoritative_candidate("A:c1")
    assert auth is not None and auth.signer == "coordinator:claude:s1"


def test_authoritative_candidate_none_when_only_noncoordinator():
    shadow = _cand(9, "A", "operator:claude:s1", candidate_id="A:c1")   # only a non-coordinator candidate
    assign = _ev(3, "assignment", payload={
        "pair": "A", "executing_coordinator": "coordinator"}, signer="overseer:mech:s1")
    st = reduce([shadow, assign])
    assert st.authoritative_candidate("A:c1") is None


# --- ADR-041: reduce() must be TOTAL against malformed insider input. An insider seat
# validly self-signs a load-bearing event whose KEYED field is an unhashable JSON list
# (candidate_id / payload["kind"] / payload["approver_identity"]) or whose infra field
# (id / signer / seq) is the wrong type. The field is inside the signed envelope/payload-
# digest, so the signature is VALID (no forgery). Pre-ADR-041 reduce() raised TypeError/
# AttributeError that escaped run_gate -> a total-bus brick. The fix DROPS the malformed
# event (no authority -> safe) and a co-present legit event still reduces. ---

def test_reduce_drops_unhashable_candidate_id_keeps_legit():
    poison = _ev(1, "co_sign", payload={"verdict": "GO"}, candidate_id=["x", "y"],
                 signer="operator2:codex:s1")
    legit = _ev(2, "co_sign", payload={"verdict": "GO"}, candidate_id="c1",
                signer="operator2:codex:s1")
    st = reduce([poison, legit])                       # must NOT raise
    assert st.co_sign("c1", "operator2") is not None   # legit survives the drop


def test_reduce_drops_unhashable_attestation_kind_keeps_legit():
    poison = _att(1, "GO", kind_att=["x", "y"], signer="operator:claude:s1")
    legit = _att(2, "GO", kind_att="release", signer="operator:claude:s1")
    st = reduce([poison, legit])                       # must NOT raise
    assert st.effective_attestation("c1", "release", "operator") is not None


def test_reduce_drops_unhashable_approver_identity_keeps_legit():
    poison = _ev(1, "human_approval", signer="overseer:mech:s1",
                 payload={"approver_identity": ["chief", "gemini"],
                          "integration_sha": INTEG, "decision": "approve"})
    legit = _ev(2, "human_approval", signer="overseer:mech:s1",
                payload={"approver_identity": "chief-gemini",
                         "integration_sha": INTEG, "decision": "approve"})
    st = reduce([poison, legit])                       # must NOT raise
    assert st.human_approvals("c1") != []              # legit approval survives


def test_reduce_drops_unhashable_event_id_keeps_legit():
    poison = _ev(1, "co_sign", payload={"verdict": "GO"}, id=["e", "1"],
                 signer="operator2:codex:s1")
    legit = _ev(2, "co_sign", payload={"verdict": "GO"}, signer="operator2:codex:s1")
    st = reduce([poison, legit])                       # must NOT raise (seat_by_id / id queries safe)
    assert st.co_sign("c1", "operator2") is not None


def test_reduce_drops_nonstr_signer_keeps_legit():
    poison = _ev(1, "co_sign", payload={"verdict": "GO"}, signer=["operator2", "codex"])
    legit = _ev(2, "co_sign", payload={"verdict": "GO"}, signer="operator2:codex:s1")
    st = reduce([poison, legit])                       # must NOT raise (_seat_of split safe)
    assert st.co_sign("c1", "operator2") is not None


def test_reduce_drops_nonint_seq_keeps_legit():
    poison = _ev("not-an-int", "co_sign", payload={"verdict": "GO"},
                 signer="operator2:codex:s1", id="e-poison")
    legit = _ev(2, "co_sign", payload={"verdict": "GO"}, signer="operator2:codex:s1")
    st = reduce([poison, legit])                       # must NOT raise (sort key safe)
    assert st.co_sign("c1", "operator2") is not None


# --- Task-10 (ADR-041, comprehensive well_formed): the `kind in LOAD_BEARING_KINDS` set test
# (gate.py AND reducer.py's seat_by_id loop) GATES ENTRY to the isinstance block, so an
# unhashable list/dict kind bricks FIRST, before any per-field guard. The well_formed up-front
# filter covers kind (and payload, bus_id, the id-reference fields) too. ---

def test_reduce_drops_unhashable_kind_keeps_legit():
    poison = _ev(1, ["co", "sign"], payload={"verdict": "GO"}, id="e-listkind",
                 signer="operator2:codex:s1")   # kind is a LIST -> seat_by_id `kind in ...` brick
    legit = _ev(2, "co_sign", payload={"verdict": "GO"}, signer="operator2:codex:s1")
    st = reduce([poison, legit])                       # must NOT raise (kind-membership test safe)
    assert st.co_sign("c1", "operator2") is not None


def test_reduce_drops_nondict_payload_candidate_authoritative_safe():
    # A `candidate` whose payload is a LIST is the genuine non-dict-payload brick: the candidate
    # fold keys only on (candidate_id, seat) so it would ENTER _candidates, and authoritative_candidate()
    # then calls c.payload.get("pair") -> .get on a LIST -> AttributeError UNCAUGHT (run_gate step-2a,
    # OUTSIDE its try) -> total-bus brick. well_formed requires payload be a dict, so the malformed
    # candidate is DROPPED up front, never entering _candidates; authoritative_candidate resolves the
    # legit one without raising. (RED pre-fix: AttributeError 'list' has no attribute 'get'.)
    legit = _cand(5, "A", "coordinator:claude:s1", id="e-legit-cand", candidate_id="A:c1")
    assign = _ev(3, "assignment", payload={"pair": "A", "executing_coordinator": "coordinator"},
                 signer="overseer:mech:s1", id="e-assign")
    poison = _ev(9, "candidate", payload=["not", "a", "dict"], id="e-listpayload-cand",
                 candidate_id="A:c1",
                 signer="operator:claude:s1")   # higher seq -> reached first by authoritative_candidate
    st = reduce([legit, assign, poison])               # must NOT raise (payload guaranteed dict)
    auth = st.authoritative_candidate("A:c1")          # must NOT raise (poison dropped)
    assert auth is not None and auth.signer == "coordinator:claude:s1"
