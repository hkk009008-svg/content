"""P4-3 auto-approve heuristics.

See docs/PRODUCT-DESIGN-P4-3-auto-approve.md for the design.

Decisions confirmed (all defaults per Session 11 brief):
  Decision 1: Veto-list — auto-approve UNLESS ANY veto rule fires.
  Decision 2: Independent per gate — 4 independent config sections.
  Decision 3: Conservative-on — enabled with high thresholds.
  Decision 4: Inline tag + post-run summary (audit log produced here;
              UI surfaces in Session 12).
  Decision 5: Reason capture with skip (frontend in Session 12).

Integration contract for Session 12:
  - ``shot["auto_approve_audit"]``: list of dicts, one per check:
      {"gate": str, "auto_approved": bool, "vetoes": list[str],
       "rule_names": list[str], "timestamp": ISO-8601 str}
  - ``shot["<gate>_auto_approved"]``: bool, True when the gate passed
      without operator review (e.g. ``shot["image_auto_approved"]``).
  - ``shot["auto_approve_audit"]`` accumulates across gates on the same
    shot — Session 12's PostRunSummary modal reads the whole list.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

logger = logging.getLogger(__name__)

Gate = Literal["plan", "image", "motion", "final"]


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VetoRule:
    """A single named veto rule.

    ``predicate`` is called with a context dict that contains:
      - ``shot_state``: the shot dict from project.json
      - ``project``: the full project dict
      - ``takes``: list of take dicts relevant to this gate

    Returns ``True`` if the rule fires (= veto, block auto-approve).
    """

    name: str
    predicate: Callable[[dict], bool]
    reason_template: str  # human-readable "why"; may reference {placeholders}


@dataclass
class AutoApproveDecision:
    """Result of a single ``check_gate`` call."""

    auto_approved: bool
    vetoes: list[str] = field(default_factory=list)   # human-readable reasons
    rule_names: list[str] = field(default_factory=list)  # parallel to vetoes
    deferred: bool = False  # True when the decision is due to an eval-error,
    # not a substantive rule veto.  auto_approved remains False (still routes
    # to manual review) but the caller can distinguish eval-error from real
    # veto.  Additive: existing consumers of auto_approved are unaffected.


@dataclass
class AutoApproveConfig:
    """Per-project, per-gate auto-approve configuration.

    Default values match the conservative-on starting point from the
    product doc (Decision 3 / Decision 1).  Operators tune via
    ``project.json.global_settings.auto_approve`` — this class reads
    and writes that dict via ``from_project`` / ``to_dict``.
    """

    enabled: bool = True  # Decision 3: conservative-on

    # --- Plan gate ---
    plan_require_approved: bool = True       # veto if decision != "APPROVED"
    plan_reject_on_violations: bool = True   # veto if violations[] non-empty

    # --- Image (keyframe) gate ---
    image_min_composite: float = 0.97         # conservative threshold (PuLID-calibrated)
    image_min_composite_fallback: float = 0.78  # fair bar for non-PuLID fallback engines
    image_veto_on_fallback: bool = True       # veto if cascade fallback
    image_max_spent_multiplier: float = 1.5   # veto if spent > 1.5× budget

    # --- Motion gate ---
    motion_min_identity: float = 0.85
    motion_min_motion_score: float = 0.7
    motion_veto_on_fallback: bool = True

    # --- Final gate ---
    final_min_lipsync: float = 0.8
    final_require_human_if_upstream_auto: bool = True  # safety net: if ANY
    # earlier gate auto-approved this shot, require human at final. Ensures
    # at least one human eyeball per shot while reducing friction by ~75%.

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    @classmethod
    def from_project(cls, project: dict) -> "AutoApproveConfig":
        """Build a config from ``project.json.global_settings.auto_approve``.

        Unknown sub-keys are silently ignored; missing sub-keys fall back
        to the dataclass defaults.
        """
        raw: dict = (project.get("global_settings") or {}).get("auto_approve") or {}

        def _get(key: str, default):
            return raw.get(key, default)

        return cls(
            enabled=_get("enabled", cls.enabled),
            plan_require_approved=_get("plan_require_approved", cls.plan_require_approved),
            plan_reject_on_violations=_get(
                "plan_reject_on_violations", cls.plan_reject_on_violations
            ),
            image_min_composite=_get("image_min_composite", cls.image_min_composite),
            image_min_composite_fallback=_get(
                "image_min_composite_fallback", cls.image_min_composite_fallback
            ),
            image_veto_on_fallback=_get("image_veto_on_fallback", cls.image_veto_on_fallback),
            image_max_spent_multiplier=_get(
                "image_max_spent_multiplier", cls.image_max_spent_multiplier
            ),
            motion_min_identity=_get("motion_min_identity", cls.motion_min_identity),
            motion_min_motion_score=_get(
                "motion_min_motion_score", cls.motion_min_motion_score
            ),
            motion_veto_on_fallback=_get(
                "motion_veto_on_fallback", cls.motion_veto_on_fallback
            ),
            final_min_lipsync=_get("final_min_lipsync", cls.final_min_lipsync),
            final_require_human_if_upstream_auto=_get(
                "final_require_human_if_upstream_auto",
                cls.final_require_human_if_upstream_auto,
            ),
        )

    def to_dict(self) -> dict:
        """Serialise to the project.json sub-dict shape consumed by ``from_project``."""
        return {
            "enabled": self.enabled,
            "plan_require_approved": self.plan_require_approved,
            "plan_reject_on_violations": self.plan_reject_on_violations,
            "image_min_composite": self.image_min_composite,
            "image_min_composite_fallback": self.image_min_composite_fallback,
            "image_veto_on_fallback": self.image_veto_on_fallback,
            "image_max_spent_multiplier": self.image_max_spent_multiplier,
            "motion_min_identity": self.motion_min_identity,
            "motion_min_motion_score": self.motion_min_motion_score,
            "motion_veto_on_fallback": self.motion_veto_on_fallback,
            "final_min_lipsync": self.final_min_lipsync,
            "final_require_human_if_upstream_auto": self.final_require_human_if_upstream_auto,
        }


# ---------------------------------------------------------------------------
# Per-gate rule builders
# ---------------------------------------------------------------------------


def _rules_for_plan(config: AutoApproveConfig) -> list[VetoRule]:
    """Veto rules for the PLAN_REVIEW gate."""
    rules: list[VetoRule] = []

    if config.plan_require_approved:
        rules.append(
            VetoRule(
                name="plan_decision_not_approved",
                predicate=lambda ctx: (
                    (ctx["shot_state"].get("director_review") or {}).get("decision")
                    != "APPROVED"
                ),
                reason_template="ChiefDirector decision was not APPROVED",
            )
        )

    if config.plan_reject_on_violations:
        rules.append(
            VetoRule(
                name="plan_has_violations",
                predicate=lambda ctx: len(
                    (ctx["shot_state"].get("director_review") or {}).get("violations")
                    or []
                )
                > 0,
                reason_template="ChiefDirector flagged violations",
            )
        )

    return rules


def record_director_review_on_shots(shots: list[dict], review: dict) -> None:
    """Persist the ChiefDirector's scene-level verdict onto each shot as the
    ``director_review`` field that ``_rules_for_plan`` (above) reads to decide
    the PLAN_REVIEW gate.

    Co-located with the reader on purpose. The headless-gate-stall root cause
    was that the reader existed but NO writer did: plan auto-approve always
    vetoed (``director_review`` absent → ``decision`` None ≠ "APPROVED"), so
    the gate could never auto-satisfy and a non-interactive run hung forever.
    Keeping write + read in one file makes the contract grep-visible
    (Rule #12: a type/field read is not write-evidence).

    ``review`` is the dict returned by ``ChiefDirector.validate_shot_prompts``
    — scene-level ``{decision, violations, shots}``. The decision/violations
    apply to every shot in the scene (the ChiefDirector reviews the scene's
    shots collectively); per-shot ``modifications`` are already applied to the
    shot prompts by the caller before this runs. A MODIFIED verdict is
    normalized to gate-decision "APPROVED" with no violations (the applied
    corrections are the resolution); the raw verdict is kept in
    ``chief_director_verdict``. A missing ``decision`` defaults to "APPROVED",
    mirroring ``validate_shot_prompts``' own parse-fallback.
    """
    decision = (review or {}).get("decision", "APPROVED")
    violations = list((review or {}).get("violations") or [])
    # A MODIFIED verdict means the ChiefDirector already rewrote the shot
    # prompts to resolve what it flagged (the ChiefDirector step applies the
    # modifications in-place before this runs) — the corrections ARE the
    # resolution, so for the PLAN gate MODIFIED counts as APPROVED with no
    # outstanding violations (cycle-17 decision: auto-clear MODIFIED so a
    # headless run doesn't dead-end on a scene the director already fixed).
    # REJECTED is preserved (it fails the gate). The raw verdict is retained in
    # `chief_director_verdict` for audit/logs.
    if decision == "MODIFIED":
        gate_decision, gate_violations = "APPROVED", []
    else:
        gate_decision, gate_violations = decision, violations
    for shot in shots:
        if isinstance(shot, dict):
            shot["director_review"] = {
                "decision": gate_decision,
                "violations": gate_violations,
                "chief_director_verdict": decision,
            }


def _rules_for_image(config: AutoApproveConfig) -> list[VetoRule]:
    """Veto rules for the KEYFRAME_REVIEW gate."""
    rules: list[VetoRule] = []

    min_composite = config.image_min_composite
    min_composite_fallback = config.image_min_composite_fallback

    if min_composite > 0:
        def _image_composite_predicate(
            ctx,
            _thr=min_composite,
            _thr_fallback=min_composite_fallback,
        ) -> bool:
            """Dynamic threshold: use fallback bar when any take used a fallback engine."""
            takes = ctx["takes"]
            if _any_take_has_fallback(takes):
                chosen = _thr_fallback
                print(
                    f"[AUTO-APPROVE] image_min_composite_kontext_fallback={chosen:.2f} applied"
                )
            else:
                chosen = _thr
            return _best_take_composite(takes) < chosen

        rules.append(
            VetoRule(
                name="image_composite_below_threshold",
                predicate=_image_composite_predicate,
                reason_template=(
                    f"best keyframe composite below threshold "
                    f"(< {min_composite:.2f} PuLID / {min_composite_fallback:.2f} fallback)"
                ),
            )
        )

    if config.image_veto_on_fallback:
        rules.append(
            VetoRule(
                name="image_cascade_fallback",
                predicate=lambda ctx: _any_take_has_fallback(ctx["takes"]),
                reason_template="keyframe cascade fell back to a secondary engine",
            )
        )

    max_mult = config.image_max_spent_multiplier

    if max_mult > 0:
        rules.append(
            VetoRule(
                name="image_over_budget",
                predicate=lambda ctx, _mult=max_mult: _shot_over_budget(
                    ctx["shot_state"], ctx["project"], _mult
                ),
                reason_template=f"shot spent_usd exceeds {max_mult:.1f}× per-shot budget",
            )
        )

    return rules


def _rules_for_motion(config: AutoApproveConfig) -> list[VetoRule]:
    """Veto rules for the motion gate (surfaced at REVIEW in the current pipeline)."""
    rules: list[VetoRule] = []

    min_identity = config.motion_min_identity

    if min_identity > 0:
        rules.append(
            VetoRule(
                name="motion_identity_below_threshold",
                predicate=lambda ctx, _thr=min_identity: _best_take_identity(
                    ctx["takes"]
                )
                < _thr,
                reason_template=f"best motion take identity_score below threshold (< {min_identity:.2f})",
            )
        )

    min_motion = config.motion_min_motion_score

    if min_motion > 0:
        rules.append(
            VetoRule(
                name="motion_score_below_threshold",
                predicate=lambda ctx, _thr=min_motion: _best_take_motion_score(
                    ctx["takes"]
                )
                < _thr,
                reason_template=f"best motion take motion_score below threshold (< {min_motion:.2f})",
            )
        )

    if config.motion_veto_on_fallback:
        rules.append(
            VetoRule(
                name="motion_cascade_fallback",
                predicate=lambda ctx: _any_take_has_fallback(ctx["takes"]),
                reason_template="motion cascade fell back to a secondary engine",
            )
        )

    return rules


def _rules_for_final(config: AutoApproveConfig) -> list[VetoRule]:
    """Veto rules for the REVIEW (final) gate."""
    rules: list[VetoRule] = []

    min_lipsync = config.final_min_lipsync

    if min_lipsync > 0:
        rules.append(
            VetoRule(
                name="final_lipsync_below_threshold",
                predicate=lambda ctx, _thr=min_lipsync: _best_take_lipsync(
                    ctx["takes"]
                )
                < _thr,
                reason_template=f"best final take lipsync_score below threshold (< {min_lipsync:.2f})",
            )
        )

    if config.final_require_human_if_upstream_auto:
        rules.append(
            VetoRule(
                name="final_upstream_was_auto_approved",
                predicate=lambda ctx: _any_upstream_gate_auto_approved(
                    ctx["shot_state"]
                ),
                reason_template=(
                    "safety net: a prior gate was auto-approved — "
                    "require human review at final"
                ),
            )
        )

    return rules


# ---------------------------------------------------------------------------
# Context helpers (extract signal values from takes / shot_state)
# ---------------------------------------------------------------------------


def _best_take_composite(takes: list[dict]) -> float:
    """Return the highest composite score across all takes, or 0.0 if none."""
    best = 0.0
    for take in takes:
        metadata = take.get("metadata") or {}
        composite = metadata.get("composite")
        if composite is not None:
            best = max(best, float(composite))
    return best


def _best_take_identity(takes: list[dict]) -> float:
    """Return the highest identity_score across all takes, or 0.0 if none."""
    best = 0.0
    for take in takes:
        metadata = take.get("metadata") or {}
        score = metadata.get("identity_score")
        if score is not None:
            best = max(best, float(score))
    return best


def _best_take_motion_score(takes: list[dict]) -> float:
    """Return the highest motion_fidelity score across all takes, or 0.0 if none."""
    best = 0.0
    for take in takes:
        metadata = take.get("metadata") or {}
        # motion_fidelity is how the ShotController stores it (shots/controller.py:864)
        score = metadata.get("motion_fidelity") or metadata.get("motion_score")
        if score is not None:
            best = max(best, float(score))
    return best


def _best_take_lipsync(takes: list[dict]) -> float:
    """Return the highest lipsync_score across all takes, with dialogue-aware defaults.

    Default semantics (F1b fix):
    - Non-dialogue takes (no take has ``has_dialogue=True``): return 1.0 (N/A pass).
    - Audio-embedded dialogue takes (``audio_embedded=True``): return 1.0 (native sync pass).
    - Dialogue takes with a real ``lipsync_score``: return the max score (existing behaviour).
    - Dialogue takes with NO ``lipsync_score`` AND NOT ``audio_embedded``: return 0.0
      (fail — the lipsync pass was skipped or failed; do not silently approve).

    Fixed v1.1 (Session 11 review): was returning the FIRST take's score
    instead of the MAX, inconsistent with _best_take_composite / _identity
    / _motion_score pattern. A shot with takes
    [lipsync_score=0.7, lipsync_score=0.95] would veto despite an
    acceptable take being present.

    F1b: The original 1.0 blind default masked dialogue shots that went through
    generation with no lipsync pass.  The fix distinguishes: if any take is
    dialogue AND it has neither a lipsync_score nor audio_embedded=True, that
    take is syncing-unverified and should be caught by the gate.
    """
    best = 0.0
    any_score_present = False
    any_dialogue_unverified = False

    for take in takes:
        metadata = take.get("metadata") or {}
        score = metadata.get("lipsync_score")
        if score is not None:
            any_score_present = True
            try:
                best = max(best, float(score))
            except (TypeError, ValueError):
                continue
        elif metadata.get("audio_embedded"):
            # Native-audio take: voice is baked in; treat as perfect sync.
            any_score_present = True
            best = max(best, 1.0)
        elif metadata.get("has_dialogue"):
            # Dialogue take with no lipsync_score and no audio_embedded:
            # lipsync either didn't run or failed — this is the blind gap.
            any_dialogue_unverified = True

    if any_dialogue_unverified and not any_score_present:
        # Every dialogue take is unverified: gate must fail.
        return 0.0
    if any_score_present:
        return best
    # No dialogue takes at all (non-dialogue shot): N/A pass.
    return 1.0


def pick_best_take_by_composite(takes: list[dict]) -> Optional[dict]:
    """Return the take with the highest composite score, falling back to the
    most recent take if no take carries a composite metric.

    Mirrors `_best_take_composite`'s scoring (used by the image veto rule)
    so the controller selects the SAME take the rule evaluated. Without
    this helper the controller picked `keyframe_takes[-1]`, which could
    mark a worse take as approved when the latest-by-position differed
    from the highest-by-score.

    Returns None if takes is empty.
    """
    if not takes:
        return None
    best_take = None
    best_score = -1.0
    for take in takes:
        metadata = take.get("metadata") or {}
        score = metadata.get("composite")
        if score is None:
            continue
        try:
            s = float(score)
        except (TypeError, ValueError):
            continue
        if s > best_score:
            best_score = s
            best_take = take
    return best_take if best_take is not None else takes[-1]


def pick_best_take_for_final(candidates: list[dict]) -> Optional[dict]:
    """Return the best take for the final gate from a candidate pool (typically
    postprocess_variants + motion_takes).

    Strategy:
      1. Prefer non-fallback takes (`cascade_metadata.fallback != True`)
         when any exist — the audit log will say "approved without
         fallback" which is the stronger signal.
      2. Within the chosen pool, pick by composite score (max), else by
         recency (last in list).

    Returns None if candidates is empty.
    """
    if not candidates:
        return None
    non_fallback = []
    for take in candidates:
        cascade = take.get("cascade_metadata") or {}
        if not (isinstance(cascade, dict) and cascade.get("fallback") is True):
            non_fallback.append(take)
    pool = non_fallback if non_fallback else candidates
    return pick_best_take_by_composite(pool)


def _any_take_has_fallback(takes: list[dict]) -> bool:
    """True if any take's cascade_metadata indicates a fallback engine was used."""
    for take in takes:
        cascade = take.get("cascade_metadata") or {}
        if isinstance(cascade, dict) and cascade.get("fallback") is True:
            return True
    return False


def _shot_over_budget(shot_state: dict, project: dict, multiplier: float) -> bool:
    """True if the shot's spent_usd exceeds ``multiplier`` × per-shot budget."""
    budget_total = (project.get("global_settings") or {}).get("budget_limit_usd", 0)
    if not budget_total:
        return False  # no budget set → can't be over budget
    scenes = project.get("scenes", [])
    total_shots = sum(len(scene.get("shots", [])) for scene in scenes)
    if total_shots == 0:
        return False
    per_shot_budget = budget_total / total_shots
    spent = shot_state.get("spent_usd", 0) or 0
    return float(spent) > multiplier * per_shot_budget


def _any_upstream_gate_auto_approved(shot_state: dict) -> bool:
    """True if any gate earlier than 'final' was auto-approved for this shot."""
    return any(
        shot_state.get(flag)
        for flag in ("plan_auto_approved", "image_auto_approved", "motion_auto_approved")
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_motion_gate_enabled() -> bool:
    """Return True if CINEMA_AUTO_APPROVE_MOTION env var is set to a truthy value.

    Off by default per ADR-014 (motion-gate as opt-in production escalation).
    Mirrors Session 10's CINEMA_STRICT_SCHEMA pattern but parses
    case-insensitively via .lower() to accept "True", "YES", etc. — closes
    a papercut that S10's code-quality reviewer flagged. Operators opt in once
    confident motion rules are well-calibrated against their content.
    """
    return os.environ.get("CINEMA_AUTO_APPROVE_MOTION", "").strip().lower() in {
        "1", "true", "yes"
    }


def check_gate(
    gate: Gate,
    *,
    shot_state: dict,
    project: dict,
    takes: list[dict],
    config: AutoApproveConfig | None = None,
) -> AutoApproveDecision:
    """Evaluate auto-approve veto rules for ``gate``.

    Returns ``AutoApproveDecision(auto_approved=True)`` (empty vetoes) if
    all rules pass AND ``config.enabled`` is True.

    Returns ``AutoApproveDecision(auto_approved=False)`` if ANY rule fires
    or if ``config.enabled`` is False.

    Belt-and-suspenders: any exception inside the evaluation is caught,
    logged as a warning, and returns ``auto_approved=False`` so the
    existing manual-review path always runs.  The pipeline is NEVER
    blocked by an auto-approve module failure.
    """
    try:
        if config is None:
            config = AutoApproveConfig.from_project(project)

        if not config.enabled:
            return AutoApproveDecision(
                auto_approved=False,
                vetoes=["disabled"],
                rule_names=["disabled"],
            )

        _builders = {
            "plan": _rules_for_plan,
            "image": _rules_for_image,
            "motion": _rules_for_motion,
            "final": _rules_for_final,
        }
        builder = _builders.get(gate)
        if builder is None:
            logger.warning(
                "auto_approve.check_gate: unknown gate %r — skipping",
                gate,
            )
            return AutoApproveDecision(
                auto_approved=False,
                vetoes=[f"unknown gate: {gate}"],
                rule_names=["unknown_gate"],
            )

        rules = builder(config)
        ctx = {"shot_state": shot_state, "project": project, "takes": takes}

        vetoes: list[str] = []
        rule_names: list[str] = []
        for rule in rules:
            try:
                fired = rule.predicate(ctx)
            except Exception as pred_exc:
                logger.warning(
                    "auto_approve rule %r predicate raised: %r — eval-error",
                    rule.name,
                    pred_exc,
                )
                if not vetoes:
                    # No substantive veto has fired yet — this eval-error means
                    # we cannot reliably decide the gate; defer to manual review
                    # (a distinct state, NOT a real veto).
                    return AutoApproveDecision(
                        auto_approved=False,
                        vetoes=[
                            f"eval error in rule {rule.name!r} — manual review required"
                        ],
                        rule_names=[rule.name],
                        deferred=True,
                    )
                # A substantive veto already fired — it stands; the decision is a
                # real VETO (deferred=False), not masked as DEFERRED. The crashed
                # predicate is skipped as noise rather than overriding the veto.
                continue
            if fired:
                vetoes.append(rule.reason_template)
                rule_names.append(rule.name)

        return AutoApproveDecision(
            auto_approved=(len(vetoes) == 0),
            vetoes=vetoes,
            rule_names=rule_names,
        )

    except Exception as exc:
        logger.warning(
            "auto_approve.check_gate crashed (gate=%r, shot=%r): %r — "
            "falling back to manual review (deferred)",
            gate,
            (shot_state or {}).get("id"),
            exc,
        )
        return AutoApproveDecision(
            auto_approved=False,
            vetoes=["auto_approve module error — manual review required"],
            rule_names=["module_error"],
            deferred=True,
        )


# ---------------------------------------------------------------------------
# Audit log helper (pre-staged for Session 12's PostRunSummary modal)
# ---------------------------------------------------------------------------


def summarize_audit(shot_state: dict) -> dict:
    """Aggregate the per-gate audit entries into a Session-12-ready summary.

    Returns a dict with:
      - ``auto_approved_gates``: list of gate names that were auto-approved
      - ``vetoed_gates``: list of gate names that were vetoed (not auto-approved)
      - ``total_vetoes``: total number of veto reasons across all gates
      - ``per_rule_fire_counts``: dict mapping rule_name → fire count
    """
    audit_entries: list[dict] = shot_state.get("auto_approve_audit") or []

    auto_approved_gates = [e["gate"] for e in audit_entries if e.get("auto_approved")]
    vetoed_gates = [e["gate"] for e in audit_entries if not e.get("auto_approved")]

    per_rule_counts: dict[str, int] = {}
    total_vetoes = 0
    for entry in audit_entries:
        for rule_name in entry.get("rule_names") or []:
            per_rule_counts[rule_name] = per_rule_counts.get(rule_name, 0) + 1
            total_vetoes += 1

    return {
        "auto_approved_gates": auto_approved_gates,
        "vetoed_gates": vetoed_gates,
        "total_vetoes": total_vetoes,
        "per_rule_fire_counts": per_rule_counts,
    }
