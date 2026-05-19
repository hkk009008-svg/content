"""ReviewController — operator review gates + per-shot review queries.

Migration Slice C from docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md.

Operator-facing methods for shot-plan and take approval flows, plus
the gate-status / gate-wait machinery and the supporting per-shot
query helpers.

Same mixin pattern as ShotControllerMixin (Slice B): delivered as a
mixin on CinemaPipeline rather than a standalone class, so method
bodies are unchanged and the function objects on the host class are
identical to those on the mixin (via MRO).

Contents
========

Operator API (called from web_server endpoints):

  approve_shot_plan(shot_id, approved, reason="") — accept/reject a shot plan
  approve_take(shot_id, take_id, approval_kind)   — accept a keyframe/motion take
  proceed_to_assembly()                           — operator unlocks the final gate

Gate machinery (called from the generation loop):

  _project_gate_status(project=None)    — counts approved shots vs total
  _gate_satisfied(gate, project=None)   — predicate for a specific gate
  _wait_for_gate(gate, detail, percent) — blocks (via self.pause()) until the gate opens
  _rebuild_review_clips(project=None)   — recomputes the review-clip manifest

Per-shot query helpers (also used by ShotController, but live here
because the review flow has the heaviest query usage):

  _all_shots(project=None)
  _latest_take(shot, collection_name)
  _resolve_take_path(shot, take_id)
  _candidate_take(shot)

State expected from the host class
==================================

  self.project, self.current_stage, self.progress, self.pause(),
  self._check_pause, self._refresh_project_snapshot, self._find_take,
  self._save_checkpoint
"""

from __future__ import annotations

from typing import Optional

from project_manager import MutationResult, mutate_project


class ReviewControllerMixin:
    """Mixin providing operator review gates + per-shot query helpers.

    Designed to be mixed into ``cinema_pipeline.CinemaPipeline`` alongside
    ShotControllerMixin (Slice B) and CheckpointStoreMixin (Slice D).
    """

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
        _, take = self._find_take(shot, take_id)
        return take.get("path", "") if take else ""

    def _candidate_take(self, shot: dict) -> Optional[dict]:
        if shot.get("approved_final_take_id"):
            _, take = self._find_take(shot, shot["approved_final_take_id"])
            if take:
                return take
        for collection_name in ("postprocess_variants", "motion_takes", "keyframe_takes"):
            take = self._latest_take(shot, collection_name)
            if take:
                return take
        return None

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
            project = self._refresh_project_snapshot() or self.project
            if self._gate_satisfied(gate, project):
                return True
            self.current_stage = gate
            self.progress(gate, detail, percent)
            self.pause()
            if not self._check_pause():
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

    def approve_shot_plan(self, shot_id: str, approved: bool, reason: str = "") -> dict:
        status = "approved" if approved else "rejected"

        def _mutator(_scene: dict, shot: dict):
            shot["plan_status"] = status
            shot["plan_rejection_reason"] = "" if approved else reason
            return MutationResult(
                {"shot_id": shot_id, "plan_status": shot["plan_status"], "reason": shot["plan_rejection_reason"]},
                save=True,
            )

        result = self._mutate_shot(shot_id, _mutator)
        return result or {"error": "Shot not found"}

    def approve_take(self, shot_id: str, take_id: str, approval_kind: str) -> dict:
        def _resolve_motion_source(shot: dict, candidate_take: dict) -> str:
            current = candidate_take
            visited = set()
            while current and current.get("id") not in visited:
                visited.add(current.get("id"))
                collection_name, _ = self._find_take(shot, current.get("id", ""))
                if collection_name == "motion_takes":
                    return current.get("id", "")
                source_take_id = current.get("source_take_id", "")
                if not source_take_id:
                    break
                _, current = self._find_take(shot, source_take_id)
            return ""

        def _mutator(_scene: dict, shot: dict):
            collection_name, take = self._find_take(shot, take_id)
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

        result = self._mutate_shot(shot_id, _mutator)
        return result or {"error": "Shot not found"}

    def proceed_to_assembly(self):
        """Resume pipeline from REVIEW stage to transitions + assembly."""
        project = self._refresh_project_snapshot() or self.project
        if not self._gate_satisfied("REVIEW", project):
            missing = [
                shot.get("id")
                for _, _, shot in self._all_shots(project)
                if not shot.get("approved_final_take_id")
            ]
            return {"success": False, "error": f"Final approvals missing for: {', '.join(missing)}"}
        self.progress("REVIEW_COMPLETE", "Director's Cut approved — proceeding to assembly", 88)
        self.resume()
        return {"success": True}
