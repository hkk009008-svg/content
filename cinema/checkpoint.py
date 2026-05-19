"""CheckpointStore — pipeline state persistence to disk.

Migration Slice D from docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md.

Atomic JSON checkpointing for the interactive pipeline. Lets a long
generation run resume across process restarts: after each meaningful
step, the in-memory state (completed scene indices, scene clips/audio
mapping, per-shot results, failed shots) is serialized to a temp file
under self.temp_dir and atomically replaced via os.replace().

Same mixin pattern as Slices B and C — delivered as a mixin on
CinemaPipeline; the moved methods see exactly the same ``self`` they
saw before, so no body rewrites.

Contents
========

  CHECKPOINT_FILE             — class constant "pipeline_state.json"
  _checkpoint_path()          — absolute path under self.temp_dir
  _save_checkpoint(completed_scene_idx=-1)  — atomic write of state JSON
  _load_checkpoint()          — load + validate (missing files marked "lost")
  _clear_checkpoint()         — delete on successful completion
  has_checkpoint()            — file-exists predicate
  resume_info()               — human-readable summary for the UI
  _restore_from_checkpoint()  — populate self.{scene_clips, scene_audio,
                                shot_results, failed_shots} from disk

State expected from the host class
==================================

Read by the save path:
  self.project["id"], self.current_stage, self.current_scene_id,
  self.current_shot_id, self._completed_scene_indices, self.scene_clips,
  self.scene_audio, self.shot_results, self.failed_shots

Written by the restore path:
  self.scene_clips, self.scene_audio, self.shot_results,
  self.failed_shots, self._completed_scene_indices

Directory deps:
  self.temp_dir
"""

from __future__ import annotations

import json
import os


class CheckpointStoreMixin:
    """Mixin providing checkpoint persistence (atomic JSON to self.temp_dir).

    Designed to be mixed into ``cinema_pipeline.CinemaPipeline`` alongside
    ShotControllerMixin (Slice B) and ReviewControllerMixin (Slice C).
    """

    CHECKPOINT_FILE = "pipeline_state.json"

    def _checkpoint_path(self) -> str:
        return os.path.join(self.temp_dir, self.CHECKPOINT_FILE)

    def _save_checkpoint(self, completed_scene_idx: int = -1):
        """
        Persist pipeline state to disk after each meaningful step.
        Uses atomic write (temp + replace) to avoid half-written files.
        """
        state = {
            "project_id": self.project["id"],
            "current_stage": self.current_stage,
            "current_scene_id": self.current_scene_id,
            "current_shot_id": self.current_shot_id,
            "completed_scene_indices": sorted(self._completed_scene_indices),
            "scene_clips": self.scene_clips,
            "scene_audio": self.scene_audio,
            "shot_results": self.shot_results,
            "failed_shots": self.failed_shots,
        }
        path = self._checkpoint_path()
        import tempfile as _tmp
        fd, tmp = _tmp.mkstemp(suffix=".json.tmp", dir=self.temp_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def _load_checkpoint(self) -> dict:
        """Load saved checkpoint if it exists and files are still valid."""
        path = self._checkpoint_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            # Validate that referenced files still exist
            for shot_id, sr in state.get("shot_results", {}).items():
                for key in ("image", "video"):
                    p = sr.get(key)
                    if p and not os.path.exists(p):
                        sr[key] = None
                        sr["status"] = "lost"
            return state
        except (json.JSONDecodeError, OSError):
            return {}

    def _clear_checkpoint(self):
        """Remove checkpoint file after successful completion."""
        path = self._checkpoint_path()
        if os.path.exists(path):
            os.remove(path)

    def has_checkpoint(self) -> bool:
        """Check if a resumable checkpoint exists."""
        return os.path.exists(self._checkpoint_path())

    def resume_info(self) -> dict:
        """Return summary of what can be resumed."""
        state = self._load_checkpoint()
        if not state:
            return {"resumable": False}
        completed = state.get("completed_scene_indices", [])
        total = len(self.project.get("scenes", []))
        return {
            "resumable": True,
            "completed_scenes": len(completed),
            "total_scenes": total,
            "stage": state.get("current_stage", ""),
            "shots_done": len([s for s in state.get("shot_results", {}).values()
                               if s.get("status") not in ("failed", "lost")]),
            "shots_failed": len(state.get("failed_shots", [])),
        }

    def _restore_from_checkpoint(self) -> set:
        """
        Restore pipeline state from checkpoint.
        Returns set of completed scene indices to skip.
        """
        state = self._load_checkpoint()
        if not state:
            return set()

        self.scene_clips = state.get("scene_clips", {})
        self.scene_audio = state.get("scene_audio", {})
        self.shot_results = state.get("shot_results", {})
        self.failed_shots = state.get("failed_shots", [])
        completed = set(state.get("completed_scene_indices", []))
        self._completed_scene_indices = completed

        n = len(completed)
        if n > 0:
            self.progress("RESUME", f"Resuming from checkpoint — {n} scene(s) already complete", 5)

        return completed
