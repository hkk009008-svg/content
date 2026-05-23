"""Lightweight read-only services for web endpoints.

Phase 7 from REFACTOR_HANDOFF.md §9.2 — the deep web_server.py
decoupling from cinema_pipeline.CinemaPipeline. After Migration
Slices A-E reorganized the god module into focused mixins +
LifecycleService, this module exposes per-endpoint helpers that read
project state directly without going through CinemaPipeline's
constructor (which initializes ContinuityEngine, ChiefDirector,
LLMEnsemble, CostTracker — all heavy
and unnecessary for read-only endpoints).

Currently exposes two helpers; both used by web_server.py to replace
``CinemaPipeline(pid).X()`` calls in read-only endpoints:

  state_snapshot(pid)    -- snapshot for /api/projects/<pid>/pipeline-state
                            when no pipeline is running. Replaces the
                            previous CinemaPipeline(pid).get_state().

  checkpoint_info(pid)   -- summary for /api/projects/<pid>/checkpoint.
                            Replaces the previous
                            CinemaPipeline(pid).resume_info().

Both helpers read disk state directly:
  - state_snapshot: load_project(pid) + gate-status math
  - checkpoint_info: read the project's pipeline_state.json + count
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple

from domain.project_manager import load_project, get_project_dir


_CHECKPOINT_FILE = "pipeline_state.json"


def _iter_shots(project: dict) -> List[Tuple[dict, int, dict]]:
    rows: List[Tuple[dict, int, dict]] = []
    for scene in project.get("scenes", []):
        for shot_index, shot in enumerate(scene.get("shots", [])):
            rows.append((scene, shot_index, shot))
    return rows


def _project_gate_status(project: dict) -> Dict[str, int]:
    """Counts of approved-shot states. Matches the in-class implementation."""
    shots = [shot for _, _, shot in _iter_shots(project)]
    total = len(shots)
    return {
        "total_shots": total,
        "plans_approved": sum(1 for shot in shots if shot.get("plan_status") == "approved"),
        "keyframes_approved": sum(1 for shot in shots if shot.get("approved_keyframe_take_id")),
        "motions_generated": sum(1 for shot in shots if shot.get("motion_takes")),
        "finals_approved": sum(1 for shot in shots if shot.get("approved_final_take_id")),
    }


def state_snapshot(project_id: str) -> dict:
    """Return a pipeline-state-shaped dict without instantiating CinemaPipeline.

    Used by /api/projects/<pid>/pipeline-state when no run is in flight.
    In-memory fields (current_stage, shot_results, failed_shots) are
    empty in this snapshot — they only exist on a live pipeline object.
    """
    project = load_project(project_id)
    if not project:
        return {
            "paused": False,
            "cancelled": False,
            "current_stage": "",
            "current_scene_id": "",
            "current_shot_id": "",
            "shot_results": {},
            "failed_shots": [],
            "scenes_completed": 0,
            "gate_status": {
                "total_shots": 0,
                "plans_approved": 0,
                "keyframes_approved": 0,
                "motions_generated": 0,
                "finals_approved": 0,
            },
        }
    return {
        "paused": False,
        "cancelled": False,
        "current_stage": "",
        "current_scene_id": "",
        "current_shot_id": "",
        "shot_results": {},
        "failed_shots": [],
        "scenes_completed": 0,
        "gate_status": _project_gate_status(project),
    }


def checkpoint_info(project_id: str) -> dict:
    """Return a resume-info-shaped dict by reading the checkpoint file directly.

    Used by /api/projects/<pid>/checkpoint. Matches the contract of
    CheckpointStoreMixin.resume_info(): same keys, same shape.
    """
    project = load_project(project_id)
    if not project:
        return {"resumable": False}

    checkpoint_path = os.path.join(
        get_project_dir(project_id), "temp", _CHECKPOINT_FILE,
    )
    if not os.path.exists(checkpoint_path):
        return {"resumable": False}

    try:
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"resumable": False}

    completed = state.get("completed_scene_indices", [])
    return {
        "resumable": True,
        "completed_scenes": len(completed),
        "total_scenes": len(project.get("scenes", [])),
        "stage": state.get("current_stage", ""),
        "shots_done": len([
            s for s in state.get("shot_results", {}).values()
            if s.get("status") not in ("failed", "lost")
        ]),
        "shots_failed": len(state.get("failed_shots", [])),
    }
