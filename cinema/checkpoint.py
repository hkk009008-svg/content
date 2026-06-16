"""CheckpointStore -- pipeline state persistence to disk.

V1.1 #5 update: CheckpointStore no longer needs a host. All the
state it reads + writes now lives on the shared ``RunState`` instance
(see ``cinema/runstate.py``), which it accesses directly. The
previous ``CheckpointStoreHost`` protocol class is deleted.

Constructor: ``CheckpointStore(core, lifecycle, runstate)``. The
lifecycle param is used only for the RESUME progress emit.

State expected from RunState
============================

Read by the save path:
  current_stage, current_scene_id, current_shot_id,
  completed_scene_indices, scene_clips, scene_audio, shot_audio,
  shot_results, failed_shots

Written by the restore path (FULL ASSIGNMENT to the runstate
dataclass fields, which are mutable by default):
  current_stage, current_scene_id, current_shot_id, scene_clips, scene_audio,
  shot_audio, shot_results, failed_shots, completed_scene_indices

The previous Slice-3b version used a CheckpointStoreHost protocol to
declare these as writable host attributes. After V1.1 #5, the host
abstraction collapses -- the runstate IS the contract.
"""

from __future__ import annotations

import json
import math
import os
from typing import TYPE_CHECKING

from cinema.lifecycle import LifecycleService

if TYPE_CHECKING:
    # See Pattern L in REFACTOR_HANDOFF.md section 7.
    from cinema.core import PipelineCore
    from cinema.runstate import RunState


class CheckpointStore:
    """Atomic JSON checkpoint persistence for the interactive pipeline.

    Lets a long generation run resume across process restarts: after each
    meaningful step, the in-memory RunState is serialized to a temp file
    under self.temp_dir and atomically replaced via os.replace().
    """

    CHECKPOINT_FILE = "pipeline_state.json"

    def __init__(
        self,
        core: PipelineCore,
        lifecycle: LifecycleService,
        runstate: RunState,
    ):
        self._core = core
        self._lifecycle = lifecycle
        self._runstate = runstate

    # ------------------------------------------------------------------
    # PipelineCore + Lifecycle property proxies.
    # ------------------------------------------------------------------

    @property
    def project(self) -> dict:
        return self._core.project

    @property
    def temp_dir(self) -> str:
        return self._core.temp_dir

    @property
    def progress(self):
        """Bound-method-shaped proxy so self.progress(...) calls work."""
        return self._lifecycle.report_progress

    # ------------------------------------------------------------------
    # File-path + atomic save.
    # ------------------------------------------------------------------

    def _checkpoint_path(self) -> str:
        return os.path.join(self.temp_dir, self.CHECKPOINT_FILE)

    @staticmethod
    def _json_safe(value):
        """Return a JSON-safe copy of checkpoint state."""
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, dict):
            return {key: CheckpointStore._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [CheckpointStore._json_safe(item) for item in value]
        return value

    def _save_checkpoint(self, completed_scene_idx: int = -1):
        """
        Persist pipeline state to disk after each meaningful step.
        Uses atomic write (temp + replace) to avoid half-written files.
        """
        if completed_scene_idx >= 0:
            self._runstate.completed_scene_indices.add(completed_scene_idx)

        state = {
            "project_id": self.project["id"],
            "current_stage": self._runstate.current_stage,
            "current_scene_id": self._runstate.current_scene_id,
            "current_shot_id": self._runstate.current_shot_id,
            "completed_scene_indices": sorted(self._runstate.completed_scene_indices),
            "scene_clips": self._runstate.scene_clips,
            "scene_audio": self._runstate.scene_audio,
            "shot_audio": self._runstate.shot_audio,
            "scene_foley": self._runstate.scene_foley,
            "foley_audio_paths": list(self._runstate.foley_audio_paths),
            "shot_results": self._runstate.shot_results,
            "failed_shots": self._runstate.failed_shots,
        }
        path = self._checkpoint_path()
        import tempfile as _tmp
        fd, tmp = _tmp.mkstemp(suffix=".json.tmp", dir=self.temp_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(
                    self._json_safe(state),
                    f,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                    allow_nan=False,
                )
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
        Restore pipeline state from checkpoint into the runstate.
        Returns set of completed scene indices to skip.
        """
        state = self._load_checkpoint()
        if not state:
            return set()

        saved_project_id = state.get("project_id")
        current_project_id = self.project.get("id")
        if saved_project_id and current_project_id and saved_project_id != current_project_id:
            raise ValueError(
                "Checkpoint project_id mismatch: "
                f"saved {saved_project_id!r}, current {current_project_id!r}"
            )

        self._runstate.scene_clips = state.get("scene_clips", {})
        self._runstate.scene_audio = state.get("scene_audio", {})
        self._runstate.shot_audio = state.get("shot_audio", {})
        self._runstate.scene_foley = state.get("scene_foley", {})
        self._runstate.foley_audio_paths = state.get("foley_audio_paths", [])
        self._runstate.shot_results = state.get("shot_results", {})
        self._runstate.failed_shots = state.get("failed_shots", [])
        completed = set(state.get("completed_scene_indices", []))
        self._runstate.completed_scene_indices = completed
        self._runstate.update_progress_pointer(
            str(state.get("current_stage") or ""),
            str(state.get("current_scene_id") or ""),
            str(state.get("current_shot_id") or ""),
        )

        cost_tracker = getattr(self._core, "cost_tracker", None)
        rehydrate = getattr(cost_tracker, "rehydrate_spent_usd_from_video", None)
        if callable(rehydrate):
            rehydrate(str(self.project.get("id", "")))

        n = len(completed)
        if n > 0:
            self.progress("RESUME", f"Resuming from checkpoint -- {n} scene(s) already complete", 5)

        return completed
