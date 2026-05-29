"""ReviewController -- operator review gates + per-shot review queries.

Standalone-controllers Slice 3b (from REFACTOR_HANDOFF.md section 9.1).
Replaces the prior ReviewControllerMixin (Slice C) with a composable
class that takes (PipelineCore, LifecycleService, ReviewControllerHost)
directly -- mirroring the ShotController extraction from Slice 2.

Architectural seam
==================

ReviewController is constructable independently of
``cinema_pipeline.CinemaPipeline``. After Phase 1c lands, web_server
endpoints can build it per-request from a cached PipelineCore.

Cross-controller dependencies (_refresh_project_snapshot,
_find_take, _mutate_shot, _check_pause, pause/resume) are declared
as a Protocol (``ReviewControllerHost``) and injected via the
constructor. CinemaPipeline implements the protocol (the project-
state refresh stays on the orchestrator; the take helpers reach
ShotController via the delegates restored in Phase 0.5; the
lifecycle wrappers preserve the existing progress-event emit).

Runtime state ownership
=======================

ReviewController owns ``review_clips`` (per-shot review-clip
manifest, built by _rebuild_review_clips). Other state read by the
review methods (project, current_stage) lives on the host.

State expected from the host class
==================================

  _refresh_project_snapshot   (CinemaPipeline implementation)
  _find_take                  (delegated to ShotController by host)
  _mutate_shot                (delegated to ShotController by host)
  resume()                    (host resume + progress("RESUMED") emit
                              -- called by proceed_to_assembly only)
  current_stage               (writable attribute -- updated during
                              _wait_for_gate)

Phase 2 removed pause() + _check_pause from this list. _wait_for_gate
now uses lifecycle.wait_for_gate (predicate-poll), so gates no longer
pause the pipeline. Manual pause via pipeline.pause() is still
respected at other lifecycle.check_pause() call sites in generate().

Body-rewrite policy
===================

Method bodies preserved verbatim from the prior mixin with these
mechanical substitutions:

  self._refresh_project_snapshot()  -> self._host._refresh_project_snapshot()
  self._find_take(...)              -> self._host._find_take(...)
  self._mutate_shot(...)            -> self._host._mutate_shot(...)
  self.resume()                     -> self._host.resume()
  self.current_stage = gate         -> self._host.current_stage = gate
  self.project                      -- preserved (proxies to self._core.project)
  self.progress(...)                -- preserved (proxies to self._lifecycle.report_progress)

Phase 2 rewrote _wait_for_gate to use self._lifecycle.wait_for_gate
instead of the pause()+_check_pause cycle. See the method docstring
for the behavior-change rationale.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

from project_manager import MutationResult, mutate_project

from cinema.auto_approve import (
    AutoApproveConfig,
    AutoApproveDecision,
    check_gate,
    is_motion_gate_enabled,
    pick_best_take_by_composite,
    pick_best_take_for_final,
)
from cinema.lifecycle import LifecycleService

_aa_logger = logging.getLogger(__name__ + ".auto_approve")

if TYPE_CHECKING:
    # See Pattern L in REFACTOR_HANDOFF.md section 7 -- avoid pulling
    # cinema.core at runtime on Python 3.9 (PEP 604 issue via
    # vbench_evaluator).
    from cinema.core import PipelineCore
    from cinema.runstate import RunState


class GateNotSatisfiedError(RuntimeError):
    """Raised by ``_wait_for_gate`` in a headless run when a review gate cannot
    be cleared: auto-approve did not approve it and there is no operator / web
    UI to approve it manually. Replaces the prior infinite poll (the cycle-17
    headless plan-review-gate stall) with a fast, diagnosable failure naming
    the unsatisfied shots + reasons. Web runs (``headless`` False) never raise
    this -- they block on ``ThreadedLifecycle`` until the operator approves.
    """


@runtime_checkable
class ReviewControllerHost(Protocol):
    """Methods that ReviewController calls on its host.

    V1.1 #5 dropped ``current_stage`` from this protocol -- the
    progress-pointer state lives on RunState now and ReviewController
    writes via ``self._runstate.current_stage = gate`` directly.
    """

    # -- Project-state refresh (lives on CinemaPipeline directly) --
    def _refresh_project_snapshot(self, timeout: float = 10) -> Optional[dict]: ...

    # -- ShotController helpers reached via host delegate (Phase 0.5 fix) --
    def _find_take(
        self, shot: dict, take_id: str
    ) -> tuple[Optional[str], Optional[dict]]: ...
    def _mutate_shot(self, shot_id: str, mutator, timeout: float = 10): ...

    # -- Resume wrapper preserves the RESUMED progress emit. (Phase 2
    #    removed pause() and _check_pause from this protocol -- gates
    #    no longer pause the pipeline; they poll via lifecycle.wait_for_gate.)
    def resume(self) -> None: ...


class ReviewController:
    """Operator review gates + per-shot review queries, composable.

    Parameters
    ----------
    core : PipelineCore
        Long-lived project deps. Provides ``project`` via the
        ``self.project`` proxy below.
    lifecycle : LifecycleService
        Per-run progress reporting. Reached via ``self.progress(...)``
        proxy.
    host : ReviewControllerHost
        Cross-controller + orchestrator-shared callables and
        attributes. CinemaPipeline implements this protocol; tests
        can pass a lightweight stub.
    """

    def __init__(
        self,
        core: PipelineCore,
        lifecycle: LifecycleService,
        host: ReviewControllerHost,
        runstate: RunState,
    ):
        self._core = core
        self._lifecycle = lifecycle
        self._host = host
        # V1.1 #5: review_clips + current_stage live on the shared
        # RunState.
        self._runstate = runstate

    # ------------------------------------------------------------------
    # PipelineCore + Lifecycle property proxies -- preserve self.X
    # access in the moved method bodies (Pattern H).
    # ------------------------------------------------------------------

    @property
    def project(self) -> dict:
        return self._core.project

    @property
    def progress(self):
        """Bound-method-shaped proxy so legacy self.progress(...) calls work."""
        return self._lifecycle.report_progress

    # ------------------------------------------------------------------
    # Per-shot query helpers (also used by ShotController, reached via
    # host._latest_take / host._resolve_take_path / host._candidate_take
    # delegates after Phase 1a).
    # ------------------------------------------------------------------

    def _all_shots(self, project: Optional[dict] = None) -> list[tuple[dict, int, dict]]:
        active_project = project or self.project
        rows: list[tuple[dict, int, dict]] = []
        for scene in active_project.get("scenes", []):
            for shot_index, shot in enumerate(scene.get("shots", [])):
                rows.append((scene, shot_index, shot))
        return rows

    def _latest_take(self, shot: dict, collection_name: str) -> Optional[dict]:
        takes = shot.get(collection_name, [])
        return takes[-1] if takes else None

    def _resolve_take_path(self, shot: dict, take_id: str) -> str:
        _, take = self._host._find_take(shot, take_id)
        return take.get("path", "") if take else ""

    def _candidate_take(self, shot: dict) -> Optional[dict]:
        if shot.get("approved_final_take_id"):
            _, take = self._host._find_take(shot, shot["approved_final_take_id"])
            if take:
                return take
        for collection_name in ("postprocess_variants", "motion_takes", "keyframe_takes"):
            take = self._latest_take(shot, collection_name)
            if take:
                return take
        return None

    # ------------------------------------------------------------------
    # Gate machinery -- called from CinemaPipeline.generate() to block
    # at PLAN_REVIEW / KEYFRAME_REVIEW / REVIEW until the operator
    # approves all shots in the relevant collection.
    # ------------------------------------------------------------------

    def _project_gate_status(self, project: Optional[dict] = None) -> dict:
        active_project = project or self.project
        shots = [shot for _, _, shot in self._all_shots(active_project)]
        total = len(shots)
        return {
            "total_shots": total,
            "plans_approved": sum(1 for shot in shots if shot.get("plan_status") == "approved"),
            "keyframes_approved": sum(1 for shot in shots if shot.get("approved_keyframe_take_id")),
            "performance_approved": sum(1 for shot in shots if shot.get("approved_performance_take_id")),
            "motions_generated": sum(1 for shot in shots if shot.get("motion_takes")),
            "finals_approved": sum(1 for shot in shots if shot.get("approved_final_take_id")),
        }

    def _gate_satisfied(self, gate: str, project: Optional[dict] = None) -> bool:
        active_project = project or self.project
        shots = [shot for _, _, shot in self._all_shots(active_project)]
        if not shots:
            return False
        if gate == "PLAN_REVIEW":
            return all(shot.get("plan_status") == "approved" for shot in shots)
        if gate == "KEYFRAME_REVIEW":
            return all(shot.get("approved_keyframe_take_id") for shot in shots)
        if gate == "PERFORMANCE_REVIEW":
            # A shot is satisfied for PERFORMANCE_REVIEW iff it doesn't need a
            # performance (SKIP engine or no keyframe approved) OR the operator
            # has explicitly approved a performance take. Mirrors the orchestrator's
            # all_skipped bypass at cinema_pipeline.py:768-773, extended with the
            # explicit-approval branch.
            return all(
                (shot.get("performance_engine") or "").upper() == "SKIP"
                or not shot.get("approved_keyframe_take_id")
                or shot.get("approved_performance_take_id")
                for shot in shots
            )
        if gate == "REVIEW":
            return all(shot.get("approved_final_take_id") for shot in shots)
        return False

    # ------------------------------------------------------------------
    # Auto-approve integration (P4-3, Session 11)
    # ------------------------------------------------------------------

    def _run_auto_approve_pass(self, gate: str) -> None:
        """Run auto-approve checks for all shots that haven't yet passed this
        gate, and pre-approve qualifying shots before the operator poll loop.

        Contract:
        - Called BEFORE ``_lifecycle.wait_for_gate`` so pre-approved shots
          satisfy the gate predicate on the first poll.
        - NEVER raises: all exceptions are caught and logged; the gate
          falls through to manual review in the worst case (belt-and-
          suspenders pattern matching ``_validate_project``).
        - Appends to ``shot["auto_approve_audit"]`` for every shot checked,
          regardless of outcome (Session 12 reads this list).
        - Sets ``shot["<gate>_auto_approved"] = True`` only when
          ``decision.auto_approved`` is True.

        Gate → audit key mapping:
          PLAN_REVIEW        → gate arg "plan"
          KEYFRAME_REVIEW    → gate arg "image"
          REVIEW             → gate arg "final"
          PERFORMANCE_REVIEW → gate arg "motion" (OPT-IN: set CINEMA_AUTO_APPROVE_MOTION=1)
        """
        # Map pipeline gate names to auto_approve gate keys.
        _gate_map = {
            "PLAN_REVIEW": "plan",
            "KEYFRAME_REVIEW": "image",
            "REVIEW": "final",
        }
        if is_motion_gate_enabled():
            _gate_map["PERFORMANCE_REVIEW"] = "motion"
        aa_gate = _gate_map.get(gate)
        if aa_gate is None:
            return

        try:
            project = self._host._refresh_project_snapshot() or self.project
            config = AutoApproveConfig.from_project(project)

            for _scene, _shot_index, shot in self._all_shots(project):
                try:
                    # Skip if gate already satisfied for this shot.
                    if aa_gate == "plan" and shot.get("plan_status") == "approved":
                        continue
                    if aa_gate == "image" and shot.get("approved_keyframe_take_id"):
                        continue
                    if aa_gate == "final" and shot.get("approved_final_take_id"):
                        continue
                    if aa_gate == "motion" and shot.get("approved_motion_take_id"):
                        continue

                    # Build takes list for the relevant gate.
                    if aa_gate == "plan":
                        takes: list[dict] = []
                    elif aa_gate == "image":
                        takes = [
                            t for t in (shot.get("keyframe_takes") or [])
                            if isinstance(t, dict)
                        ]
                    elif aa_gate == "final":
                        takes = [
                            t for t in (shot.get("postprocess_variants") or [])
                                   + (shot.get("motion_takes") or [])
                            if isinstance(t, dict)
                        ]
                    elif aa_gate == "motion":
                        takes = [
                            t for t in (shot.get("motion_takes") or [])
                            if isinstance(t, dict)
                        ]
                    else:
                        takes = []

                    decision: AutoApproveDecision = check_gate(
                        aa_gate,
                        shot_state=shot,
                        project=project,
                        takes=takes,
                        config=config,
                    )

                    # Append audit entry (always — Session 12 reads these).
                    audit_entry = {
                        "gate": aa_gate,
                        "auto_approved": decision.auto_approved,
                        "vetoes": decision.vetoes,
                        "rule_names": decision.rule_names,
                        "deferred": decision.deferred,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

                    # Emit observable marker for log scanning / unattended runs.
                    if decision.auto_approved:
                        _gate_label = "APPROVED"
                    elif decision.deferred:
                        _gate_label = "DEFERRED"
                    else:
                        _gate_label = f"VETO({','.join(decision.rule_names)})"
                    print(f"[AUTO-APPROVE] {aa_gate}: {_gate_label}")

                    if decision.auto_approved:
                        shot_id = shot.get("id", "unknown")
                        flag_key = f"{aa_gate}_auto_approved"
                        _aa_logger.info(
                            "auto_approve: gate=%r shot=%r — approved",
                            aa_gate,
                            shot_id,
                        )

                        # Mutate the shot to mark it approved.
                        if aa_gate == "plan":
                            def _plan_mutator(_scene_ignored, s, _entry=audit_entry, _key=flag_key):
                                s["plan_status"] = "approved"
                                s["plan_rejection_reason"] = ""
                                s.setdefault("auto_approve_audit", []).append(_entry)
                                s[_key] = True
                                return MutationResult(
                                    {"shot_id": s["id"], "plan_status": "approved"},
                                    save=True,
                                )
                            self._host._mutate_shot(shot_id, _plan_mutator)

                        elif aa_gate == "image":
                            # v1.1 fix (Session 11 review): pick the take with
                            # the highest composite score (matches the image
                            # veto rule's "best = max(composite)" semantics).
                            # Was: keyframe_takes[-1] — could mark a worse take
                            # as approved when latest-by-position ≠ best-by-score.
                            best_take = pick_best_take_by_composite(
                                shot.get("keyframe_takes") or []
                            )
                            best_take_id = (best_take or {}).get("id", "")
                            if best_take_id:
                                def _img_mutator(
                                    _scene_ignored, s,
                                    _tid=best_take_id,
                                    _entry=audit_entry,
                                    _key=flag_key,
                                ):
                                    s["approved_keyframe_take_id"] = _tid
                                    s.setdefault("auto_approve_audit", []).append(_entry)
                                    s[_key] = True
                                    return MutationResult(
                                        {"shot_id": s["id"], "approved_keyframe_take_id": _tid},
                                        save=True,
                                    )
                                self._host._mutate_shot(shot_id, _img_mutator)

                        elif aa_gate == "final":
                            # v1.1 fix (Session 11 review): prefer non-fallback
                            # takes, then pick by max composite. Was: simply
                            # final_candidates[-1] — could approve a fallback
                            # take when non-fallback options existed, or pick
                            # a low-composite take over a higher one.
                            final_candidates = (
                                shot.get("postprocess_variants") or []
                            ) + (shot.get("motion_takes") or [])
                            best_final = pick_best_take_for_final(final_candidates)
                            best_final_id = (best_final or {}).get("id", "")
                            if best_final_id:
                                # Resolve motion source for approved_motion_take_id.
                                motion_take_id = ""
                                for mt in reversed(shot.get("motion_takes") or []):
                                    if isinstance(mt, dict) and mt.get("id"):
                                        motion_take_id = mt["id"]
                                        break

                                def _final_mutator(
                                    _scene_ignored, s,
                                    _ftid=best_final_id,
                                    _mtid=motion_take_id,
                                    _entry=audit_entry,
                                    _key=flag_key,
                                ):
                                    if _mtid:
                                        s["approved_motion_take_id"] = _mtid
                                    s["approved_final_take_id"] = _ftid
                                    s.setdefault("auto_approve_audit", []).append(_entry)
                                    s[_key] = True
                                    return MutationResult(
                                        {
                                            "shot_id": s["id"],
                                            "approved_final_take_id": _ftid,
                                        },
                                        save=True,
                                    )
                                self._host._mutate_shot(shot_id, _final_mutator)

                        elif aa_gate == "motion":
                            # Pick best motion take by motion_fidelity → motion_score →
                            # identity_score (primary: what motion rules threshold on;
                            # fallback: motion_score; tiebreak: identity_score).
                            motion_takes = [
                                t for t in (shot.get("motion_takes") or [])
                                if isinstance(t, dict)
                            ]

                            def _motion_score_tuple(t):
                                meta = t.get("metadata") if isinstance(t.get("metadata"), dict) else {}
                                return (
                                    meta.get("motion_fidelity") or meta.get("motion_score") or 0.0,
                                    meta.get("identity_score") or 0.0,
                                )

                            best_motion = (
                                max(motion_takes, key=_motion_score_tuple) if motion_takes else None
                            )
                            best_motion_id = (best_motion or {}).get("id", "")

                            if best_motion_id:
                                def _motion_mutator(
                                    _scene_ignored, s,
                                    _mtid=best_motion_id,
                                    _entry=audit_entry,
                                    _key=flag_key,
                                ):
                                    s["approved_motion_take_id"] = _mtid
                                    s.setdefault("auto_approve_audit", []).append(_entry)
                                    s[_key] = True
                                    return MutationResult(
                                        {"shot_id": s["id"], "approved_motion_take_id": _mtid},
                                        save=True,
                                    )
                                self._host._mutate_shot(shot_id, _motion_mutator)

                    else:
                        # Vetoed: still append audit entry to shot (no approval).
                        shot_id = shot.get("id", "unknown")

                        def _audit_only_mutator(
                            _scene_ignored, s, _entry=audit_entry
                        ):
                            s.setdefault("auto_approve_audit", []).append(_entry)
                            return MutationResult(
                                {"shot_id": s["id"], "auto_approve_audit_appended": True},
                                save=True,
                            )
                        self._host._mutate_shot(shot_id, _audit_only_mutator)

                except Exception as shot_exc:
                    _aa_logger.warning(
                        "auto_approve: error processing shot %r at gate %r: %r",
                        shot.get("id"),
                        aa_gate,
                        shot_exc,
                    )
                    # Continue with remaining shots.

        except Exception as exc:
            _aa_logger.warning(
                "auto_approve: _run_auto_approve_pass failed (gate=%r): %r — "
                "falling through to manual review",
                gate,
                exc,
            )

    def _wait_for_gate(self, gate: str, detail: str, percent: float) -> bool:
        """Block until the named gate is satisfied (or run cancelled).

        Phase 2 migration: uses ``LifecycleService.wait_for_gate``'s
        predicate-poll pattern instead of the previous
        ``self._host.pause()`` + ``self._host._check_pause()`` cycle.

        The predicate re-refreshes the project snapshot on each poll
        (default 0.5s interval) so operator approvals that mutate the
        on-disk project state are picked up automatically. No explicit
        "Resume" click is required after approving; the gate auto-
        resolves within ``poll_interval`` seconds of the last approval.

        Manual pause (via pipeline.pause() / Pause button) is still
        respected at every other ctx.lifecycle.check_pause() call
        site in the generate() loop -- this method just removes the
        coupling between gate state and pause state. Gates no longer
        force a pause.

        P4-3 (Session 11): auto-approve pass runs before the poll loop.
        Qualifying shots are pre-approved; the gate may be satisfied
        immediately without operator input. If the pass errors, it is
        silently skipped and normal manual review proceeds.
        """
        self._runstate.current_stage = gate
        self.progress(gate, detail, percent)

        # P4-3: attempt to pre-approve shots before waiting for operator.
        self._run_auto_approve_pass(gate)

        def predicate() -> bool:
            project = self._host._refresh_project_snapshot() or self.project
            return self._gate_satisfied(gate, project)

        # Headless / non-interactive run: no operator + no web UI to approve a
        # gate that auto-approve didn't clear. Fail fast with the per-shot
        # reasons instead of polling forever (the cycle-17 headless
        # plan-review-gate stall). Web runs leave headless False and keep the
        # blocking poll below.
        if self._runstate.headless:
            # Refresh the snapshot once and reuse it for both the satisfied-check
            # and the reason detail (avoids a redundant second snapshot on the
            # raise path).
            project = self._host._refresh_project_snapshot() or self.project
            if not self._gate_satisfied(gate, project):
                details = self._gate_block_details(gate, project)
                raise GateNotSatisfiedError(
                    f"{gate} not satisfied in a headless run with no operator to "
                    f"approve it (auto-approve did not clear): " + "; ".join(details)
                )
            return True

        return self._lifecycle.wait_for_gate(gate, predicate)

    def _gate_block_details(self, gate: str, project: Optional[dict] = None) -> list[str]:
        """Per-shot reasons ``gate`` is unsatisfied -- for the headless
        ``GateNotSatisfiedError`` message. Best-effort and human-readable.

        For PLAN_REVIEW it surfaces the auto-approve veto rule names (when the
        ``auto_approve_audit`` is present) or the ChiefDirector ``decision``,
        so a headless operator sees WHY the plan wasn't auto-approved. The
        per-gate conditions mirror ``_gate_satisfied``.
        """
        active_project = project or self.project
        details: list[str] = []
        for _scene, _shot_index, shot in self._all_shots(active_project):
            sid = shot.get("id", "?")
            if gate == "PLAN_REVIEW":
                if shot.get("plan_status") == "approved":
                    continue
                director_review = shot.get("director_review") or {}
                plan_audit = [
                    a for a in (shot.get("auto_approve_audit") or [])
                    if a.get("gate") == "plan"
                ]
                why = (
                    ",".join((plan_audit[-1].get("rule_names") if plan_audit else []) or [])
                    or director_review.get("decision")
                    or shot.get("plan_status")
                    or "pending_review"
                )
                details.append(f"shot {sid} (plan: {why})")
            elif gate == "KEYFRAME_REVIEW":
                if not shot.get("approved_keyframe_take_id"):
                    details.append(f"shot {sid} (no approved keyframe)")
            elif gate == "PERFORMANCE_REVIEW":
                # Unsatisfied iff the shot NEEDS a performance but lacks an
                # approved one (mirror of _gate_satisfied's PERFORMANCE branch).
                if (
                    (shot.get("performance_engine") or "").upper() != "SKIP"
                    and shot.get("approved_keyframe_take_id")
                    and not shot.get("approved_performance_take_id")
                ):
                    details.append(f"shot {sid} (no approved performance)")
            elif gate == "REVIEW":
                if not shot.get("approved_final_take_id"):
                    details.append(f"shot {sid} (no approved final take)")
        return details or [f"all shots (gate {gate})"]

    def _rebuild_review_clips(self, project: Optional[dict] = None) -> dict:
        active_project = project or self.project
        manifest = {}
        for scene, shot_index, shot in self._all_shots(active_project):
            candidate = self._candidate_take(shot) or {}
            keyframe_path = self._resolve_take_path(shot, shot.get("approved_keyframe_take_id", "")) or (
                self._latest_take(shot, "keyframe_takes") or {}
            ).get("path")
            manifest[shot["id"]] = {
                "scene_id": scene.get("id", ""),
                "shot_index": shot_index,
                "prompt": shot.get("prompt", ""),
                "camera": shot.get("camera", ""),
                "target_api": shot.get("target_api", "AUTO"),
                "image": keyframe_path,
                "video": candidate.get("path", "") if candidate.get("kind") != "keyframe" else "",
                "take_id": candidate.get("id", ""),
                "take_kind": candidate.get("kind", ""),
                "status": "pending_review",
            }
        self._runstate.review_clips = manifest
        return manifest

    # ------------------------------------------------------------------
    # Operator API (called from web_server endpoints).
    # ------------------------------------------------------------------

    def approve_shot_plan(self, shot_id: str, approved: bool, reason: str = "") -> dict:
        status = "approved" if approved else "rejected"

        def _mutator(_scene: dict, shot: dict):
            shot["plan_status"] = status
            shot["plan_rejection_reason"] = "" if approved else reason
            return MutationResult(
                {"shot_id": shot_id, "plan_status": shot["plan_status"], "reason": shot["plan_rejection_reason"]},
                save=True,
            )

        result = self._host._mutate_shot(shot_id, _mutator)
        return result or {"error": "Shot not found"}

    def approve_take(self, shot_id: str, take_id: str, approval_kind: str) -> dict:
        def _resolve_motion_source(shot: dict, candidate_take: dict) -> str:
            current = candidate_take
            visited = set()
            while current and current.get("id") not in visited:
                visited.add(current.get("id"))
                collection_name, _ = self._host._find_take(shot, current.get("id", ""))
                if collection_name == "motion_takes":
                    return current.get("id", "")
                source_take_id = current.get("source_take_id", "")
                if not source_take_id:
                    break
                _, current = self._host._find_take(shot, source_take_id)
            return ""

        def _mutator(_scene: dict, shot: dict):
            collection_name, take = self._host._find_take(shot, take_id)
            if not take:
                return MutationResult({"error": "Take not found"}, save=False)
            if approval_kind == "keyframe":
                if collection_name != "keyframe_takes":
                    return MutationResult({"error": "Take is not a keyframe"}, save=False)
                shot["approved_keyframe_take_id"] = take_id
            elif approval_kind == "performance":
                if collection_name != "performance_takes":
                    return MutationResult({"error": "Take is not a performance"}, save=False)
                shot["approved_performance_take_id"] = take_id
            elif approval_kind == "final":
                if collection_name == "keyframe_takes":
                    return MutationResult({"error": "Keyframes cannot be approved as final takes"}, save=False)
                motion_take_id = take_id if collection_name == "motion_takes" else _resolve_motion_source(shot, take)
                if motion_take_id:
                    shot["approved_motion_take_id"] = motion_take_id
                shot["approved_final_take_id"] = take_id
            else:
                return MutationResult({"error": f"Unsupported approval kind '{approval_kind}'"}, save=False)
            return MutationResult({"shot_id": shot_id, "take_id": take_id, "approval_kind": approval_kind}, save=True)

        result = self._host._mutate_shot(shot_id, _mutator)
        return result or {"error": "Shot not found"}

    def proceed_to_assembly(self):
        """Resume pipeline from REVIEW stage to transitions + assembly."""
        project = self._host._refresh_project_snapshot() or self.project
        if not self._gate_satisfied("REVIEW", project):
            missing = [
                shot.get("id")
                for _, _, shot in self._all_shots(project)
                if not shot.get("approved_final_take_id")
            ]
            return {"success": False, "error": f"Final approvals missing for: {', '.join(missing)}"}
        self.progress("REVIEW_COMPLETE", "Director's Cut approved -- proceeding to assembly", 88)
        self._host.resume()
        return {"success": True}
