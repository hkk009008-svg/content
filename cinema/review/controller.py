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
  _check_pause                (CinemaPipeline implementation; returns
                              bool unlike LifecycleService.check_pause)
  pause()                     (host pause + progress("PAUSED") emit)
  resume()                    (host resume + progress("RESUMED") emit)
  current_stage               (writable attribute -- updated during
                              _wait_for_gate)

Body-rewrite policy
===================

Method bodies preserved verbatim from the prior mixin with these
mechanical substitutions:

  self._refresh_project_snapshot()  -> self._host._refresh_project_snapshot()
  self._find_take(...)              -> self._host._find_take(...)
  self._mutate_shot(...)            -> self._host._mutate_shot(...)
  self._check_pause()               -> self._host._check_pause()
  self.pause()                      -> self._host.pause()
  self.resume()                     -> self._host.resume()
  self.current_stage = gate         -> self._host.current_stage = gate
  self.project                      -- preserved (proxies to self._core.project)
  self.progress(...)                -- preserved (proxies to self._lifecycle.report_progress)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol

from project_manager import MutationResult, mutate_project

from cinema.lifecycle import LifecycleService

if TYPE_CHECKING:
    # See Pattern L in REFACTOR_HANDOFF.md section 7 -- avoid pulling
    # cinema.core at runtime on Python 3.9 (PEP 604 issue via
    # vbench_evaluator).
    from cinema.core import PipelineCore


class ReviewControllerHost(Protocol):
    """Methods + attributes that ReviewController calls on its host."""

    # -- Project-state refresh (lives on CinemaPipeline directly) --
    def _refresh_project_snapshot(self, timeout: float = 10) -> Optional[dict]: ...

    # -- ShotController helpers reached via host delegate (Phase 0.5 fix) --
    def _find_take(
        self, shot: dict, take_id: str
    ) -> tuple[Optional[str], Optional[dict]]: ...
    def _mutate_shot(self, shot_id: str, mutator, timeout: float = 10): ...

    # -- Lifecycle wrappers that preserve progress-event emit --
    def _check_pause(self) -> bool: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...

    # -- Orchestrator-shared progress pointer (writable attribute) --
    current_stage: str


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
    ):
        self._core = core
        self._lifecycle = lifecycle
        self._host = host

        # Per-run state owned by this controller.
        self.review_clips: dict = {}

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
        if gate == "REVIEW":
            return all(shot.get("approved_final_take_id") for shot in shots)
        return False

    def _wait_for_gate(self, gate: str, detail: str, percent: float) -> bool:
        while True:
            project = self._host._refresh_project_snapshot() or self.project
            if self._gate_satisfied(gate, project):
                return True
            self._host.current_stage = gate
            self.progress(gate, detail, percent)
            self._host.pause()
            if not self._host._check_pause():
                return False

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
        self.review_clips = manifest
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
