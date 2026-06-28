"""Intent ledger: maps manual claims -> tests. status: asserted | cross-linked | INTENDED_NOT_WIRED."""
from __future__ import annotations

from dataclasses import dataclass

_STATUSES = {"asserted", "cross-linked", "INTENDED_NOT_WIRED"}
_TIERS = {"offline", "live", "e2e"}


@dataclass(frozen=True)
class Claim:
    claim_id: str
    dimension: str
    manual_section: str
    tier: str
    status: str
    description: str

    def __post_init__(self):
        assert self.tier in _TIERS, f"{self.claim_id}: bad tier {self.tier!r}"
        assert self.status in _STATUSES, f"{self.claim_id}: bad status {self.status!r}"


LEDGER: list[Claim] = [
    Claim("ID-01", "identity", "manual §4 Stage2 / identity/types.py:92", "offline", "cross-linked",
          "SHOT_TYPE_THRESHOLDS strict/std/lenient per shot type"),
    Claim("ID-02", "identity", "manual §4 Stage2 / identity/types.py:101", "offline", "asserted",
          "get_threshold_for_shot degrades standard->lenient linearly across attempts"),
    Claim("ID-03", "identity", "manual §4 Stage2 / face_validator_gate.py:165", "offline", "cross-linked",
          "composite = 0.6*arc + 0.4*aesthetic; missing component -> 0.5"),
    Claim("ID-04", "identity", "manual §4 Stage2 / face_validator_gate.py:225", "offline", "cross-linked",
          "should_halt: composite-only at 0.92 once n>=halt_min_n (or n>=halt_max_n)"),
    Claim("ID-05", "identity", "manual §3.10 / identity/validator.py:266", "offline", "asserted",
          "get_rolling_stats suggested_pulid_delta from success_rate windows"),
    Claim("ID-06", "identity", "manual §3.10 / identity/validator.py:684", "offline", "asserted",
          "_compute_pulid_delta from per-frame similarity + matched flag"),
    Claim("ID-07", "identity", "manual §3.10 / identity/validator.py:365", "offline", "asserted",
          "_compute_sample_positions: density-by-shot-type, clamp [3,10], anchors 10/50/90%"),
    Claim("ID-LIVE-01", "identity", "manual §5.4 / spec §4 Identity", "live", "asserted",
          "real ComfyUI keyframe ArcFace >= shot-type threshold - margin (later plan)"),
    Claim("ID-E2E-01", "identity", "manual §1 / spec §4 Identity", "e2e", "asserted",
          "same character across ALL shots of the golden mp4 >= lenient (later plan)"),
]


def assert_unique() -> None:
    ids = [c.claim_id for c in LEDGER]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate claim_ids: {sorted(dupes)}"


def get(claim_id: str) -> Claim:
    for c in LEDGER:
        if c.claim_id == claim_id:
            return c
    raise KeyError(f"no ledger claim {claim_id!r}")


def by_dimension(dimension: str) -> list[Claim]:
    return [c for c in LEDGER if c.dimension == dimension]
