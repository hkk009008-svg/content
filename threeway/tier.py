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


def co_sign_satisfied(tier: str, state, candidate_id: str, builder_provider: str) -> bool:
    """Whether the tier-SPECIFIC extra approvals exist (beyond the primary release
    GO + the coordinator candidate sig, which the predicate checks separately).

    Slice 1 implements T0/T1 only. T2 needs the OTHER pair's operator co_sign and
    T3 adds a new-session re_verify + two human_approval facts — both land in
    Slice 3 (they need Pair B / the human relay). Returning False here is the safe
    default: an escalated change simply cannot promote yet.
    """
    if tier in ("T0", "T1"):
        return True
    return False  # Slice 3: implement T2 (other-pair co_sign) and T3 (re_verify + 2 human_approval)
