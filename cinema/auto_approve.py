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
from dataclasses import dataclass, field
from typing import Callable, Literal

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
    image_min_composite: float = 0.97         # conservative threshold
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


def _rules_for_image(config: AutoApproveConfig) -> list[VetoRule]:
    """Veto rules for the KEYFRAME_REVIEW gate."""
    rules: list[VetoRule] = []

    min_composite = config.image_min_composite

    if min_composite > 0:
        rules.append(
            VetoRule(
                name="image_composite_below_threshold",
                predicate=lambda ctx, _thr=min_composite: _best_take_composite(
                    ctx["takes"]
                )
                < _thr,
                reason_template=f"best keyframe composite below threshold (< {min_composite:.2f})",
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
    """Return the highest lipsync_score across all takes, or 1.0 if none present.

    1.0 default: when lipsync wasn't computed (shot has no dialogue) the
    gate should not veto on this rule.  The predicate only fires when the
    score IS present and below threshold.
    """
    for take in takes:
        metadata = take.get("metadata") or {}
        score = metadata.get("lipsync_score")
        if score is not None:
            return float(score)
    # No lipsync score present — treat as "not applicable", don't veto.
    return 1.0


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
                    "auto_approve rule %r predicate raised: %r — treating as veto",
                    rule.name,
                    pred_exc,
                )
                fired = True  # conservative: predicate failure → veto
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
            "falling back to manual review",
            gate,
            (shot_state or {}).get("id"),
            exc,
        )
        return AutoApproveDecision(
            auto_approved=False,
            vetoes=["auto_approve module error — manual review required"],
            rule_names=["module_error"],
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
