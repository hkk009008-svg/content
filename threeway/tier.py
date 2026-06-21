"""Gate-computed risk tier (spec §7.2). The gate NEVER trusts a claimed tier:
effective_tier = max(brief.assigned_tier, classify(diff, policy)).
"""
from __future__ import annotations

_ORDER = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}


def tier_rank(t: str) -> int:
    return _ORDER[t]


def _path_tier(path: str, policy) -> str:
    for prefix, tier in policy.rules:
        if path == prefix or path.startswith(prefix):
            return tier
    # default for any code path not otherwise matched
    return "T1"


def classify_diff(paths, policy) -> str:
    tiers = [_path_tier(p, policy) for p in paths]
    if not tiers:
        return "T0"
    return max(tiers, key=tier_rank)


def effective_tier(claimed_tier: str, paths, policy) -> str:
    return max(claimed_tier, classify_diff(paths, policy), key=tier_rank)


def _signer_seat(signer: str) -> str:
    """The KEY-BOUND identity: the gate looks up <seat>.pub by this token, so only the
    real keyholder can produce a valid event with it. The provider/session TAIL of the
    signer string is UNSIGNED (envelope.py:67) and MUST NOT be trusted."""
    return signer.split(":", 1)[0]


def co_sign_satisfied(tier: str, state, candidate_id: str, *, candidate_pair: str,
                      builder_provider: str, verifier_provider: str,
                      integration_sha: str) -> bool:
    """Whether the tier-SPECIFIC extra approvals exist (beyond the primary release GO +
    the coordinator candidate sig, checked separately). Spec §7.2. Identity is resolved
    from overseer-signed `assignment` facts + key-bound seat tokens, NEVER from the
    unsigned signer-string provider/session. Ambiguity fails CLOSED. False is fail-safe."""
    if tier in ("T0", "T1"):
        return True
    # escalated tiers require cross-provider independence (defense-in-depth: predicate.py:67
    # rejects this upstream, but co_sign_satisfied is public + unit-tested directly).
    if verifier_provider == builder_provider:
        return False
    if not _t2_mirror_cosign(state, candidate_id, candidate_pair,
                             builder_provider, verifier_provider, integration_sha):
        return False
    if tier == "T2":
        return True
    # tier == "T3"
    if not _t3_cross_provider_re_verify(state, candidate_id, candidate_pair,
                                        builder_provider, verifier_provider, integration_sha):
        return False
    return _two_distinct_human_approvals(state, candidate_id, integration_sha)


def _mirror_pair_verifier_seat(state, candidate_pair, builder_provider,
                               verifier_provider) -> str | None:
    """The MIRROR pair's primary-verifier SEAT, from overseer-signed assignments. The
    mirror (D3 'provider-role swap only') is the pair != candidate_pair whose providers
    are the exact swap: builder_provider == OUR verifier_provider AND
    primary_verifier_provider == OUR builder_provider. Fail-CLOSED: returns None unless
    EXACTLY ONE such pair exists (zero → not yet assigned; >1 → ambiguous co-signer)."""
    # Count swap-eligible PAIRS (spec: "EXACTLY ONE mirror pair or fail closed"), NOT
    # non-null seats — a second eligible pair that omits its seat must still register as
    # ambiguity rather than be silently dropped to resolve the other.
    mirror_seats = []
    for assign in state.assignments():
        if _signer_seat(assign.signer) != "overseer":
            continue
        ap = assign.payload
        if ap.get("pair") == candidate_pair:
            continue
        if (ap.get("builder_provider") == verifier_provider
                and ap.get("primary_verifier_provider") == builder_provider):
            mirror_seats.append(ap.get("primary_verifier"))
    if len(mirror_seats) != 1:          # zero → not assigned; >1 → ambiguous co-signer
        return None
    seat = mirror_seats[0]
    return seat if seat else None       # a single eligible-but-seatless pair → fail closed


def _t2_mirror_cosign(state, candidate_id, candidate_pair, builder_provider,
                      verifier_provider, integration_sha) -> bool:
    seat = _mirror_pair_verifier_seat(state, candidate_pair, builder_provider, verifier_provider)
    if seat is None:
        return False
    ev = state.co_sign(candidate_id, seat)
    return (ev is not None
            and ev.payload.get("verdict") == "GO"
            and ev.subject_sha == integration_sha)


def _t3_cross_provider_re_verify(state, candidate_id, candidate_pair, builder_provider,
                                 verifier_provider, integration_sha) -> bool:
    """A re_verify GO over integration_sha from the candidate pair's OWN primary_verifier
    (the cross-provider, non-builder family operator), resolved from the signed assignment.

    ADR-043 (threeway-signer-unsigned-session): freshness is now VERIFIABLE from SIGNED facts,
    not asserted via the unsigned signer session. The re_verify must echo the nonce from the
    overseer's `re_verify_challenge` for this candidate+sha, in the re_verify's OWN payload —
    which is bound by `payload_digest` (a signed field), so the verifier cannot forge or alter
    it. A replayed STALE re_verify (from a prior session/cycle) carries the wrong nonce and fails
    the CURRENT challenge; only a re_verify produced in response to this challenge satisfies it.
    Fail-CLOSED on a missing/mismatched challenge or nonce. PRECONDITION (challenge-response is
    only as strong as the challenger): the gate is the verifier and cannot generate entropy, so
    the freshness guarantee rests on the overseer issuing a FRESH, unguessable, non-reused nonce
    for each re-verification it demands — the gate enforces the binding (echo == current
    challenge), not the overseer's nonce-rotation discipline. A reused/low-entropy nonce weakens
    freshness without the gate being able to detect it; emitting fresh nonces is an overseer
    (scope-(b) emitter) responsibility. See DECISIONS.md ADR-043."""
    if verifier_provider == builder_provider:   # standalone fail-closed mirror of predicate.py independence reject; co_sign_satisfied is public + unit-tested directly
        return False
    assign = state.assignment(candidate_pair)
    if assign is None or _signer_seat(assign.signer) != "overseer":
        return False
    seat = assign.payload.get("primary_verifier")
    if not seat:                        # malformed/empty assignment seat → fail closed (symmetric with T2)
        return False
    # freshness challenge — overseer-signed (record-time authority filter), bound to this sha.
    challenge = state.re_verify_challenge(candidate_id)
    if challenge is None or challenge.subject_sha != integration_sha:
        return False                    # no fresh overseer challenge for this candidate+sha
    nonce = challenge.payload.get("nonce")
    if not nonce:                       # malformed/empty challenge nonce → fail closed
        return False
    ev = state.re_verify(candidate_id, seat)
    return (ev is not None
            and ev.payload.get("verdict") == "GO"
            and ev.subject_sha == integration_sha
            and ev.payload.get("challenge_nonce") == nonce)


def _two_distinct_human_approvals(state, candidate_id, integration_sha) -> bool:
    """Two distinct KEY-BOUND human approvers, each on the overseer's allowed-approver roster,
    each a SHA-bound affirmative human_approval (spec §12).

    ADR-043 (threeway-human-approval-overseer-asserted): distinctness is now on the signer SEAT
    (the key-bound identity the gate verifies against <seat>.pub), NOT the attacker-influenceable
    payload `approver_identity` label. The overseer designates WHO may approve via a signed
    `approver_roster`, but it does NOT hold the approvers' private keys — so it can no longer
    assert two labels for one human: two distinct approvals require two distinct keyholders to
    actually sign. Fail-CLOSED without an overseer roster, or a roster naming < 2 approvers."""
    roster = state.approver_roster(candidate_id)
    if roster is None:
        return False                    # no overseer-designated roster → fail closed
    allowed = roster.payload.get("approvers")
    if not isinstance(allowed, list):
        return False                    # malformed roster → fail closed
    allowed_seats = {a for a in allowed if isinstance(a, str)}
    if len(allowed_seats) < 2:
        return False                    # roster cannot authorize two distinct approvers
    approver_seats = set()
    for ev in state.human_approvals(candidate_id):
        seat = _signer_seat(ev.signer)  # the KEY-BOUND identity, not the unsigned label
        if seat not in allowed_seats:
            continue
        if ev.payload.get("integration_sha") != integration_sha:
            continue
        if ev.payload.get("decision") != "approve":
            continue
        approver_seats.add(seat)
    return len(approver_seats) >= 2
