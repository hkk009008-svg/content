"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_tier.py -q"""
from threeway.policy import default_policy
from threeway.tier import classify_diff, effective_tier, co_sign_satisfied, tier_rank
from threeway.reducer import reduce
from threeway.envelope import Event


P = default_policy()


def test_docs_only_is_t0():
    # both under docs/ — root-level docs (README.md etc.) intentionally fall to the
    # T1 default, which is SAFE (over-classify never under-promotes); see
    # _DEFAULT_RULES in threeway/policy.py.
    assert classify_diff(["docs/x.md", "docs/guide.md"], P) == "T0"


def test_bounded_code_is_t1():
    assert classify_diff(["cinema/foo.py"], P) == "T1"


def test_ci_config_is_t2():
    assert classify_diff([".github/workflows/ci.yml"], P) == "T2"


def test_keys_dir_is_t3():
    assert classify_diff(["coordination/threeway/keys/operator.pub"], P) == "T3"


def test_classify_takes_the_max_over_all_paths():
    assert classify_diff(["docs/x.md", ".github/workflows/ci.yml"], P) == "T2"


def test_effective_tier_is_max_of_claimed_and_path_derived():
    # path-derived T1, brief claimed T2 -> T2
    assert effective_tier("T2", ["cinema/foo.py"], P) == "T2"
    # path-derived T2, brief claimed T0 -> T2 (claim never lowers it)
    assert effective_tier("T0", [".github/workflows/ci.yml"], P) == "T2"


INTEG = "2" * 40
WRONG = "9" * 40


def _assign(seq, *, pair, builder_provider, verifier_seat, verifier_provider,
            signer="overseer:mech:s1"):
    return Event(id=f"as{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="assignment", sender="overseer", recipient="all", signer=signer,
                 payload={"pair": pair, "builder_provider": builder_provider,
                          "primary_verifier": verifier_seat,
                          "primary_verifier_provider": verifier_provider},
                 brief_id="b1", brief_version=1)


def _roster():
    return [_assign(1, pair="A", builder_provider="codex",
                    verifier_seat="operator", verifier_provider="claude"),
            _assign(2, pair="B", builder_provider="claude",
                    verifier_seat="operator2", verifier_provider="codex")]


def _sat(tier, state, *, pair="A", builder="codex", verifier="claude", cand="c1"):
    return co_sign_satisfied(tier, state, cand, candidate_pair=pair,
                             builder_provider=builder, verifier_provider=verifier,
                             integration_sha=INTEG)


def test_t0_t1_cosign_satisfied_without_extra_artifacts():
    state = reduce(_roster())
    assert _sat("T0", state)
    assert _sat("T1", state)


def test_t2_t3_pending_without_any_artifacts():
    state = reduce(_roster())
    assert not _sat("T2", state)
    assert not _sat("T3", state)


def _cosign(seq, *, signer, subject_sha=INTEG, verdict="GO", cand="c1"):
    return Event(id=f"cs{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="co_sign", sender=signer.split(":")[0], recipient="all", signer=signer,
                 payload={"verdict": verdict}, candidate_id=cand, brief_id="b1",
                 brief_version=1, subject_sha=subject_sha)


def test_t2_satisfied_by_mirror_pair_operator():
    state = reduce(_roster() + [_cosign(3, signer="operator2:codex:s1")])
    assert _sat("T2", state)


def test_t2_rejects_cosign_from_primary_verifier_seat():
    state = reduce(_roster() + [_cosign(3, signer="operator:claude:s1")])
    assert not _sat("T2", state)


def test_t2_rejects_provider_spoof_by_primary_verifier():
    state = reduce(_roster() + [_cosign(3, signer="operator:codex:s9")])
    assert not _sat("T2", state)


def test_t2_rejects_cosign_from_builder_director():
    state = reduce(_roster() + [_cosign(3, signer="director:codex:s1")])
    assert not _sat("T2", state)


def test_t2_rejects_cosign_from_coordinator():
    state = reduce(_roster() + [_cosign(3, signer="coordinator2:codex:s1")])
    assert not _sat("T2", state)


def test_t2_rejects_cosign_bound_to_wrong_sha():
    state = reduce(_roster() + [_cosign(3, signer="operator2:codex:s1", subject_sha=WRONG)])
    assert not _sat("T2", state)


def test_t2_rejects_non_go_cosign():
    state = reduce(_roster() + [_cosign(3, signer="operator2:codex:s1", verdict="NITS")])
    assert not _sat("T2", state)


def test_t2_rejects_when_mirror_assignment_not_overseer_signed():
    roster = [_assign(1, pair="A", builder_provider="codex", verifier_seat="operator",
                      verifier_provider="claude"),
              _assign(2, pair="B", builder_provider="claude", verifier_seat="operator2",
                      verifier_provider="codex", signer="director:codex:s1")]
    state = reduce(roster + [_cosign(3, signer="operator2:codex:s1")])
    assert not _sat("T2", state)


def test_t2_rejects_wrong_family_other_pair():
    roster = [_assign(1, pair="A", builder_provider="codex", verifier_seat="operator",
                      verifier_provider="claude"),
              _assign(2, pair="B", builder_provider="claude", verifier_seat="operatorB",
                      verifier_provider="claude")]
    state = reduce(roster + [_cosign(3, signer="operatorB:claude:s1")])
    assert not _sat("T2", state)


def test_t2_fail_closed_on_two_mirror_pairs():
    roster = _roster() + [_assign(3, pair="C", builder_provider="claude",
                                  verifier_seat="operatorC", verifier_provider="codex")]
    state = reduce(roster + [_cosign(4, signer="operator2:codex:s1"),
                             _cosign(5, signer="operatorC:codex:s1")])
    assert not _sat("T2", state)


def test_t2_rejects_self_mirror_candidate_pair():
    # Degenerate roster: the candidate's OWN pair A is provider-swap-eligible
    # (builder_provider == primary_verifier_provider == "codex"). The `pair !=
    # candidate_pair` skip in _mirror_pair_verifier_seat is the ONLY thing preventing
    # pair A's own operator from self-satisfying the mirror co-sign here.
    roster = [_assign(1, pair="A", builder_provider="codex",
                      verifier_seat="operator", verifier_provider="codex")]
    state = reduce(roster + [_cosign(2, signer="operator:codex:s1")])
    assert not _sat("T2", state, pair="A", builder="codex", verifier="codex")


def test_t2_pair_b_direction():
    state = reduce(_roster() + [_cosign(3, signer="operator:claude:s1")])
    assert _sat("T2", state, pair="B", builder="claude", verifier="codex")


def _reverify(seq, *, signer, subject_sha=INTEG, verdict="GO", cand="c1"):
    return Event(id=f"rv{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="re_verify", sender=signer.split(":")[0], recipient="all", signer=signer,
                 payload={"verdict": verdict}, candidate_id=cand, brief_id="b1",
                 brief_version=1, subject_sha=subject_sha)


def _human(seq, *, approver, signer="overseer:mech:s1", subject=INTEG,
           decision="approve", cand="c1"):
    return Event(id=f"h{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="human_approval", sender="overseer", recipient="all", signer=signer,
                 payload={"approver_identity": approver, "integration_sha": subject,
                          "decision": decision},
                 candidate_id=cand, brief_id="b1", brief_version=1)


def _revoke(seq, *, target_id, cand="c1"):
    return Event(id=f"rk{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="attestation_revoked", sender="x", recipient="all",
                 signer="overseer:mech:s1", payload={}, candidate_id=cand,
                 brief_id="b1", brief_version=1, revokes_event_id=target_id)


def _t3_ok():
    return _roster() + [
        _cosign(3, signer="operator2:codex:s1"),
        _reverify(4, signer="operator:claude:s2"),
        _human(5, approver="chief-gemini"),
        _human(6, approver="chief-chatgpt"),
    ]


def test_t3_satisfied_full_set():
    assert _sat("T3", reduce(_t3_ok()))


def test_t3_pending_without_re_verify():
    assert not _sat("T3", reduce([e for e in _t3_ok() if e.kind != "re_verify"]))


def test_t3_rejects_re_verify_from_wrong_seat():
    evs = _t3_ok(); evs[3] = _reverify(4, signer="operator2:codex:s2")
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_re_verify_wrong_sha():
    evs = _t3_ok(); evs[3] = _reverify(4, signer="operator:claude:s2", subject_sha=WRONG)
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_non_go_re_verify():
    evs = _t3_ok(); evs[3] = _reverify(4, signer="operator:claude:s2", verdict="FAIL")
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_revoked_re_verify():
    assert not _sat("T3", reduce(_t3_ok() + [_revoke(7, target_id="rv4")]))


def test_t3_pending_with_one_human_approval():
    assert not _sat("T3", reduce(_t3_ok()[:5]))


def test_t3_rejects_two_human_approvals_same_identity():
    evs = _t3_ok(); evs[5] = _human(6, approver="chief-gemini")
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_human_approval_not_signed_by_overseer():
    evs = _t3_ok(); evs[5] = _human(6, approver="chief-chatgpt", signer="director:codex:s1")
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_human_approval_wrong_sha():
    evs = _t3_ok(); evs[5] = _human(6, approver="chief-chatgpt", subject=WRONG)
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_human_approval_non_affirmative_decision():
    evs = _t3_ok(); evs[5] = _human(6, approver="chief-chatgpt", decision="reject")
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_revoked_human_approval():
    assert not _sat("T3", reduce(_t3_ok() + [_revoke(7, target_id="h6")]))


def test_t3_rejects_revoked_candidate_pair_assignment():
    # overseer revokes pair A's (candidate pair) assignment → the T3 re_verify seat
    # cannot resolve → fail closed. (T2 mirror, via the rev-aware assignments(), is
    # unaffected since it resolves pair B.)
    assert not _sat("T3", reduce(_t3_ok() + [_revoke(7, target_id="as1")]))


# --- Slice 3 review hardening (defense-in-depth; not attacker-reachable in the signed
# 2-pair topology, but restores fail-closed symmetry the review found missing). ---

def test_t2_rejects_same_provider_builder_verifier():
    # Even if a malformed same-provider "mirror" exists, an escalated promotion must reject
    # when builder and verifier share a provider (no cross-provider independence). The sole
    # production caller is gated upstream (predicate.py:67), but co_sign_satisfied is public.
    roster = [_assign(1, pair="A", builder_provider="codex", verifier_seat="operator",
                      verifier_provider="codex"),
              _assign(2, pair="B", builder_provider="codex", verifier_seat="operator2",
                      verifier_provider="codex")]
    state = reduce(roster + [_cosign(3, signer="operator2:codex:s1")])
    assert not _sat("T2", state, builder="codex", verifier="codex")


def test_t2_fail_closed_when_two_eligible_pairs_one_seatless():
    # Spec rule is "EXACTLY ONE mirror PAIR or fail closed". A second swap-eligible pair
    # whose primary_verifier is empty must NOT be silently dropped to resolve the other.
    roster = _roster() + [_assign(3, pair="C", builder_provider="claude",
                                  verifier_seat="", verifier_provider="codex")]
    state = reduce(roster + [_cosign(4, signer="operator2:codex:s1")])
    assert not _sat("T2", state)


def test_t3_rejects_empty_primary_verifier_seat():
    # An empty-string primary_verifier in the candidate-pair assignment must fail closed,
    # symmetric with the T2 mirror seat guard — an empty-token re_verify must not match.
    roster = [_assign(1, pair="A", builder_provider="codex", verifier_seat="",
                      verifier_provider="claude"),
              _assign(2, pair="B", builder_provider="claude", verifier_seat="operator2",
                      verifier_provider="codex")]
    evs = roster + [_cosign(3, signer="operator2:codex:s1"),
                    _reverify(4, signer=":x:s2"),   # _seat_of -> "" matches the empty seat
                    _human(5, approver="chief-gemini"), _human(6, approver="chief-chatgpt")]
    assert not _sat("T3", reduce(evs))
