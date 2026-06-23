"""Per-brief_version rework circuit-breaker (spec §9): >2 AUTHORIZED rework cycles -> ESCALATE.

ADR-060 (C1 Part 2): the breaker counts only AUTHORIZED reworks. A rework cycle for a brief
version = a candidate that (a) is authoritatively aborted by its bound-pair executing_coordinator
(ADR-059 `is_aborted`) AND (b) whose AUTHORITATIVE candidate belongs to that brief_id/brief_version
(the candidate's brief_version is in the signed envelope). Counting over reduced EffectiveState —
not raw events — is doubly fail-safe: a forged abort fails the authority check, and an abort with no
real candidate fails the candidate check, so neither can trip the breaker (a forced-ESCALATE
merge-DoS) nor inflate a rival brief-version's count.
"""
from __future__ import annotations

REWORK_CAP = 2


def rework_count(state, brief_id, brief_version) -> int:
    """Distinct candidates of (brief_id, brief_version) that were AUTHORITATIVELY aborted."""
    n = 0
    for cid in state.aborted_candidate_ids():
        if not state.is_aborted(cid):
            continue                       # ADR-059 authority filter (drops forged aborts)
        cand = state.authoritative_candidate(cid)
        if cand is not None and cand.brief_id == brief_id and cand.brief_version == brief_version:
            n += 1
    return n


def should_escalate(state, brief_id, brief_version) -> bool:
    return rework_count(state, brief_id, brief_version) > REWORK_CAP
