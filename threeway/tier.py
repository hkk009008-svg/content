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
    seats = set()
    for assign in state.assignments():
        if _signer_seat(assign.signer) != "overseer":
            continue
        ap = assign.payload
        if ap.get("pair") == candidate_pair:
            continue
        if (ap.get("builder_provider") == verifier_provider
                and ap.get("primary_verifier_provider") == builder_provider):
            seat = ap.get("primary_verifier")
            if seat:
                seats.add(seat)
    return next(iter(seats)) if len(seats) == 1 else None


def _t2_mirror_cosign(state, candidate_id, candidate_pair, builder_provider,
                      verifier_provider, integration_sha) -> bool:
    seat = _mirror_pair_verifier_seat(state, candidate_pair, builder_provider, verifier_provider)
    if seat is None:
        return False
    ev = state.co_sign(candidate_id, seat)
    return (ev is not None
            and ev.payload.get("verdict") == "GO"
            and ev.subject_sha == integration_sha)
