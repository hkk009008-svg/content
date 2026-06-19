"""Per-brief_version rework circuit-breaker (spec §9): >2 rework cycles -> ESCALATE."""
from __future__ import annotations

REWORK_CAP = 2


def rework_count(events, brief_id, brief_version) -> int:
    return sum(
        1 for e in events
        if e.kind == "candidate_aborted"
        and e.brief_id == brief_id and e.brief_version == brief_version
    )


def should_escalate(events, brief_id, brief_version) -> bool:
    return rework_count(events, brief_id, brief_version) > REWORK_CAP
