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
    Claim("ID-05", "identity", "manual §3.10 / identity/validator.py", "offline", "asserted",
          "character aggregation preserves the specific identity failure reason"),
    Claim("ID-06", "identity", "manual §3.10 / identity/types.py", "offline", "asserted",
          "identity diagnostics contain no provider-specific generation controls"),
    Claim("ID-07", "identity", "manual §3.10 / identity/validator.py:365", "offline", "asserted",
          "_compute_sample_positions: density-by-shot-type, clamp [3,10], anchors 10/50/90%"),
    Claim("ID-LIVE-01", "identity", "manual §5.4 / spec §4 Identity", "live", "asserted",
          "real ComfyUI keyframe ArcFace >= shot-type threshold - margin (later plan)"),
    Claim("ID-E2E-01", "identity", "manual §1 / spec §4 Identity", "e2e", "asserted",
          "same character across ALL shots of the golden mp4 >= lenient (later plan)"),
    # --- gates_orchestration dimension (Plan 2) ---
    # auto-approve veto machinery (cinema/auto_approve.py) — assert-new offline
    Claim("GATE-01", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:218", "offline", "asserted",
          "_rules_for_plan omits plan_decision_not_approved when plan_require_approved=False"),
    Claim("GATE-02", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:230", "offline", "asserted",
          "_rules_for_plan omits plan_has_violations when plan_reject_on_violations=False"),
    Claim("GATE-03", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:298", "offline", "asserted",
          "_rules_for_image omits image_composite_below_threshold when image_min_composite<=0"),
    Claim("GATE-04", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:326", "offline", "asserted",
          "_rules_for_image omits image_cascade_fallback when image_veto_on_fallback=False"),
    Claim("GATE-05", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:337", "offline", "asserted",
          "_rules_for_image omits image_over_budget when image_max_spent_multiplier<=0"),
    Claim("GATE-06", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:413", "offline", "asserted",
          "_rules_for_final omits final_upstream_was_auto_approved when final_require_human_if_upstream_auto=False"),
    Claim("GATE-07", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:600", "offline", "asserted",
          "_any_take_has_fallback True only for dict cascade_metadata with fallback is True"),
    Claim("GATE-08", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:458", "offline", "asserted",
          "_best_take_identity max finite identity_score; 0.0 for empty/non-finite-only"),
    Claim("GATE-09", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:471", "offline", "asserted",
          "_best_take_motion_score prefers motion_fidelity over motion_score; 0.0 for empty"),
    Claim("GATE-10", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:525", "offline", "asserted",
          "_best_take_lipsync non-finite score fails closed -> 0.0 (not 1.0 N/A)"),
    Claim("GATE-11", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:618", "offline", "asserted",
          "_shot_over_budget: NaN budget->True; 0 budget->False; 0 total_shots->False; over-cap->True"),
    Claim("GATE-12", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:374", "offline", "asserted",
          "check_gate('motion') fires motion_score_below_threshold when best motion_fidelity<0.7"),
    Claim("GATE-13", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:416", "offline", "asserted",
          "check_gate('final') fires final_upstream_was_auto_approved when an upstream auto-approve flag is set"),
    Claim("GATE-14", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:283", "offline", "asserted",
          "record_director_review_on_shots skips non-dict shot items without raising"),
    Claim("GATE-15", "gates_orchestration", "spec §4 Headless / cinema/lifecycle.py:89", "offline", "asserted",
          "NullLifecycle.wait_for_gate returns True regardless of predicate (always-True trap)"),
    # ChiefDirector veto-decision composition (llm/chief_director.py) — assert-new offline
    Claim("CD-01", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:459", "offline", "asserted",
          "evaluate_generation_quality no-client + identity fail -> REVIEW_REQUIRED without inferred mutation level"),
    Claim("CD-02", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:461", "offline", "asserted",
          "evaluate_generation_quality no-client + coherence-only fail -> REVIEW_REQUIRED"),
    Claim("CD-03", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:650", "offline", "asserted",
          "unparsable-evidence mutation tiering: >0.55->1, >0.40->2, else->3; unmeasured identity -> REVIEW_REQUIRED without a level"),
    Claim("CD-04", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:305", "offline", "asserted",
          "validate_shot_prompts no-client -> REVIEW_REQUIRED with unavailable-evidence violation"),
    Claim("CD-05", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:27", "offline", "asserted",
          "_strip_json_fences strips ```json/``` fences; passthrough when no fence"),
    Claim("CD-06", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:653", "offline", "asserted",
          "get_diagnostic_summary empty sentinel + per-entry [stage] decision (score=) line"),
    # cross-links — already covered in tests/unit; mapped here so the ledger is a complete picture
    Claim("GATE-XL-01", "gates_orchestration", "spec §4 Headless / cinema/review/controller.py:558", "offline", "cross-linked",
          "headless _wait_for_gate raises GateNotSatisfiedError when gate unsatisfied "
          "(tests/unit/test_cross_controller.py::test_wait_for_gate_headless_raises_when_unsatisfied)"),
    Claim("GATE-XL-02", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:278", "offline", "cross-linked",
          "record_director_review_on_shots MODIFIED->APPROVED normalization "
          "(tests/unit/test_auto_approve.py::TestRecordDirectorReview)"),
    Claim("GATE-XL-03", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:728", "offline", "cross-linked",
          "check_gate predicate-exception -> deferred decision "
          "(tests/unit/test_auto_approve.py::TestDeferredDecision)"),
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
