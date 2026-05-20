"""CheckpointStore -- pipeline state persistence to disk.

Standalone-controllers Slice 3b (Phase 1b) of REFACTOR_HANDOFF.md.
Replaces the prior CheckpointStoreMixin (Slice D) with a composable
class -- mirroring Slice 2 (ShotController) and Phase 1a
(ReviewController).

Architectural note
==================

Unlike Shot and Review controllers, CheckpointStore owns no per-run
state. It's a pure file-I/O service that serializes host attributes
to JSON and reads them back. The class still takes a lifecycle
(only used for the RESUME progress emit in _restore_from_checkpoint)
to match the constructor shape of the other two controllers.

State expected from the host class
==================================

Read by the save path:
  current_stage, current_scene_id, current_shot_id,
  _completed_scene_indices, scene_clips, scene_audio,
  shot_results, failed_shots

Written by the restore path (all FULL ASSIGNMENT -- the host must
expose settable attributes for these):
  scene_clips, scene_audio, shot_results, failed_shots,
  _completed_scene_indices

shot_results on CinemaPipeline is a property with a setter (added in
Slice 2 because CheckpointStoreMixin already did full reassignment).
The other four are plain instance attributes on CinemaPipeline.

Body-rewrite policy
===================

Method bodies preserved verbatim with these mechanical substitutions:

  self.project       -- preserved (proxies to self._core.project)
  self.temp_dir      -- preserved (proxies to self._core.temp_dir)
  self.progress(...) -- preserved (proxies to self._lifecycle.report_progress)
  self.current_*     -> self._host.current_*  (reads)
  self.scene_clips   -> self._host.scene_clips  (reads + writes)
  self.scene_audio   -> self._host.scene_audio
  self.shot_results  -> self._host.shot_results  (writes via @property setter)
  self.failed_shots  -> self._host.failed_shots
  self._completed_scene_indices  -> self._host._completed_scene_indices
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cinema.lifecycle import LifecycleService

if TYPE_CHECKING:
    # See Pattern L in REFACTOR_HANDOFF.md section 7.
    from cinema.core import PipelineCore


@runtime_checkable
class CheckpointStoreHost(Protocol):
    """Attributes that CheckpointStore reads from and writes to its host.

    All declared as writable attributes (no methods). The host must
    expose each one as either a plain instance attribute or a property
    with a setter.
    """

    current_stage: str
    current_scene_id: str
    current_shot_id: str
    _completed_scene_indices: set
    scene_clips: dict
    scene_audio: dict
    shot_results: dict
    failed_shots: list


class CheckpointStore:
    """Atomic JSON checkpoint persistence for the interactive pipeline.

    Lets a long generation run resume across process restarts: after each
    meaningful step, the in-memory state (completed scene indices, scene
    clips/audio mapping, per-shot results, failed shots) is serialized
    to a temp file under self.temp_dir and atomically replaced via
    os.replace().
    """

    CHECKPOINT_FILE = "pipeline_state.json"

    def __init__(
        self,
        core: PipelineCore,
        lifecycle: LifecycleService,
        host: CheckpointStoreHost,
    ):
        self._core = core
        self._lifecycle = lifecycle
        self._host = host

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

    def _save_checkpoint(self, completed_scene_idx: int = -1):
        """
        Persist pipeline state to disk after each meaningful step.
        Uses atomic write (temp + replace) to avoid half-written files.
        """
        state = {
            "project_id": self.project["id"],
            "current_stage": self._host.current_stage,
            "current_scene_id": self._host.current_scene_id,
            "current_shot_id": self._host.current_shot_id,
            "completed_scene_indices": sorted(self._host._completed_scene_indices),
            "scene_clips": self._host.scene_clips,
            "scene_audio": self._host.scene_audio,
            "shot_results": self._host.shot_results,
            "failed_shots": self._host.failed_shots,
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

        self._host.scene_clips = state.get("scene_clips", {})
        self._host.scene_audio = state.get("scene_audio", {})
        self._host.shot_results = state.get("shot_results", {})
        self._host.failed_shots = state.get("failed_shots", [])
        completed = set(state.get("completed_scene_indices", []))
        self._host._completed_scene_indices = completed

        n = len(completed)
        if n > 0:
            self.progress("RESUME", f"Resuming from checkpoint -- {n} scene(s) already complete", 5)

        return completed
