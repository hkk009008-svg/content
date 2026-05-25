"""SCREENING stage scaffolding -- S19 (cycle-9 Surface B).

The post-ASSEMBLY operator-driven screening pause where the operator
watches the assembled cut and (in later slices) iterates on individual
shots before approving the final cut.

This module provides three things:

1. ``_screening_stage_enabled()`` -- the env-flag helper (mirrors the
   ``_directorial_iteration_enabled()`` shape at
   ``cinema/shots/controller.py:100`` so future feature-flag readers
   recognise the convention).

2. ``_build_timeline_manifest(project)`` -- pure-function builder that
   walks scenes/shots in order and emits the per-shot manifest
   consumed by the ``POST /assemble/screen`` endpoint. Per-shot
   duration source priority: take ``metadata.duration_s`` (set by the
   performance phase at ``cinema/shots/controller.py:674``) > scene
   ``duration_seconds`` > ``5.0`` fallback (matches the controller's
   own fallback at the same line). No ffprobe at runtime -- the
   manifest is constructed entirely from project state, which the
   proposal §"Backend flow" calls out as the cheap path.

3. ``is_screening_approved(project)`` / ``mark_screening_approved(pid)``
   -- the gate-predicate accessor + the mutator that the
   ``POST /screening/approve`` endpoint calls. The flag lives at the
   project's top level as ``screening_approved: bool``. Per director-
   seat REPLY 2026-05-25T14-56-42Z (Q4 endorsement): "the simplest
   possible (``project.screening_approved == True`` or similar boolean)
   so the stage overhead is minimal vs. the lifecycle properties you
   gain." Stored via ``mutate_project`` so the gate survives crashes /
   SSE drops the same way the existing four review gates do.

Design notes (for the reviewer)
===============================

- **No new Pydantic field on the Project model.** ``screening_approved``
  travels through ``ConfigDict(extra="allow")`` (``domain/models.py:167``)
  and is read via ``project.get("screening_approved", False)``. This
  mirrors the S15 substrate's permissive-schema pattern and avoids a
  migration that would force every existing project.json on disk to
  re-serialise. If a future slice tightens the schema, the field can
  be added then.

- **Gate predicate is poll-only.** Mirrors the existing
  ``_wait_for_gate`` pattern at ``cinema/review/controller.py:487`` --
  the lifecycle's ``wait_for_gate(name, predicate)`` loop re-reads the
  predicate on every ``poll_interval``. No SSE / callback wiring
  required for v1.

- **Stage name string is "SCREENING".** Matches the frontend constant
  added to ``PIPELINE_STAGES`` in ``usePipelineState.ts``.
"""

from __future__ import annotations

import logging
import os
from typing import Optional


logger = logging.getLogger(__name__)


SCREENING_STAGE_NAME = "SCREENING"
SCREENING_APPROVED_KEY = "screening_approved"


def _screening_stage_enabled() -> bool:
    """Feature flag: CINEMA_SCREENING_STAGE=1|true|yes enables S19+ screening stage.

    Per §7.7.3 convention. Default off -- flag must be set explicitly.
    Truthy-value set matches ``_directorial_iteration_enabled()`` exactly
    so an operator who sets the directorial-iteration flag with the same
    spelling gets the same answer here.
    """
    return os.environ.get("CINEMA_SCREENING_STAGE", "").strip().lower() in {
        "1", "true", "yes",
    }


def _take_duration_seconds(take: dict, fallback: float) -> float:
    """Extract per-take duration in seconds with graceful fallback.

    Order of preference:
      1. ``take.metadata.duration_s`` (set by performance phase at
         ``cinema/shots/controller.py:674``)
      2. Caller-supplied fallback (typically ``scene.duration_seconds``
         or the hardcoded ``5.0``).

    Returns a float; never raises. A take with non-numeric duration_s
    triggers the fallback (defensive; production data shouldn't hit
    this but a corrupted project.json could).
    """
    if not isinstance(take, dict):
        return fallback
    meta = take.get("metadata") or {}
    raw = meta.get("duration_s") if isinstance(meta, dict) else None
    if raw is None:
        return fallback
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _build_timeline_manifest(project: dict, *, verify_files: bool = False) -> list[dict]:
    """Walk scenes/shots in order, emit per-shot timeline manifest.

    Output entry shape (per proposal §"Endpoint"):
        {
            "shot_id": str,
            "scene_id": str,
            "start_s": float,    # cumulative start time in final assembled cut
            "end_s": float,      # cumulative end time
            "approved_take_id": str,   # the take_id used in assembly
            "take_count": int,   # total takes across all kinds (for iteration depth)
        }

    Inclusion rule: a shot appears in the manifest iff it has an
    ``approved_final_take_id`` -- i.e. iff it would have been included
    in ``_assemble_final``'s stitch. Shots that are still pending /
    SKIP / failed are omitted, so the manifest indexes align with what
    the operator actually sees in the assembled mp4.

    ``verify_files``: when True, also require that the approved take's
    ``path`` field is truthy AND points to an extant file on disk. This
    is the STRICT mirror of ``_build_scene_packages``'s inclusion rule
    at ``cinema_pipeline.py:544-548`` (which filters via
    ``os.path.exists(final_path)`` so the assembled mp4 never references
    a missing file). Without this flag the manifest is a "best-effort"
    view from project state alone; with it, the manifest is guaranteed
    to align with what ``_assemble_final`` would have produced (post
    Lane V #6 review of cycle-9 S19 — operator's `screening` endpoint
    passes True so the operator's timeline scrubber never lands on a
    phantom shot whose mp4 was deleted between assembly and screening).

    Duration source per shot (in order):
      1. The approved take's ``metadata.duration_s`` (performance takes
         set this at ``cinema/shots/controller.py:674``).
      2. The scene's ``duration_seconds``.
      3. ``5.0`` (matches the same controller fallback).

    NOT used: ffprobe at runtime. Per proposal hedge #3 ("haven't
    measured") and director-seat REPLY Q5, we explicitly defer
    runtime-measured manifest durations to S21+ if real operator data
    shows the project-state estimate drifts from the actual cut.
    """
    manifest: list[dict] = []
    cursor_s = 0.0

    scenes = project.get("scenes") or []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("id", "")
        scene_fallback = 5.0
        raw_scene_dur = scene.get("duration_seconds")
        if raw_scene_dur is not None:
            try:
                scene_fallback = float(raw_scene_dur)
            except (TypeError, ValueError):
                scene_fallback = 5.0

        for shot in scene.get("shots", []) or []:
            if not isinstance(shot, dict):
                continue
            approved_id = shot.get("approved_final_take_id", "")
            if not approved_id:
                # Mirrors _build_scene_packages's inclusion rule
                # (cinema_pipeline.py:544-548): no approved final take
                # means the shot was not in the assembly.
                continue

            # Locate the approved take so we can read its duration.
            # The take may live in any of the take collections (motion /
            # postprocess_variants / performance).
            approved_take: Optional[dict] = None
            collections = (
                shot.get("postprocess_variants") or [],
                shot.get("motion_takes") or [],
                shot.get("performance_takes") or [],
                shot.get("keyframe_takes") or [],
            )
            for collection in collections:
                for take in collection:
                    if isinstance(take, dict) and take.get("id") == approved_id:
                        approved_take = take
                        break
                if approved_take is not None:
                    break

            # Strict-mirror file-existence check (Lane V #6 cycle-9 S19 F1
            # IMPORTANT). Without this, a shot whose take_id is set but
            # whose mp4 was deleted between assembly and screening would
            # appear at a stale start_s/end_s while NOT being in the actual
            # assembled video. Mirrors cinema_pipeline.py:544-548.
            if verify_files:
                take_path = (approved_take or {}).get("path", "")
                if not take_path or not os.path.exists(take_path):
                    continue

            duration = _take_duration_seconds(approved_take or {}, scene_fallback)

            # take_count = total takes across all kinds (for iteration depth).
            total_takes = sum(
                len(c) for c in collections
                if isinstance(c, list)
            )

            entry = {
                "shot_id": shot.get("id", ""),
                "scene_id": scene_id,
                "start_s": cursor_s,
                "end_s": cursor_s + duration,
                "approved_take_id": approved_id,
                "take_count": total_takes,
            }
            manifest.append(entry)
            cursor_s += duration

    return manifest


def is_screening_approved(project: dict) -> bool:
    """Gate predicate: True if operator has signalled "approve final cut".

    Reads the top-level ``screening_approved`` boolean. False when the
    field is absent OR when its value is anything other than a truthy
    Python value (defensive against weird JSON round-tripping).
    """
    if not isinstance(project, dict):
        return False
    return bool(project.get(SCREENING_APPROVED_KEY, False))


def mark_screening_approved(project_id: str) -> dict:
    """Set ``project.screening_approved = True`` and persist.

    Called by ``POST /screening/approve``. Returns a small result dict
    with ``success`` + the resulting flag value. Raises ``ValueError``
    if the project doesn't exist (caller surfaces as 404).

    Import is lazy so this module stays import-safe under the
    operator's `unset CINEMA_SCREENING_STAGE` cold-import probe -- we
    never want to drag in the heavy project_manager module unless the
    operator actually calls into the screening path.
    """
    from project_manager import MutationResult, mutate_project

    def _mutator(latest_project: dict):
        latest_project[SCREENING_APPROVED_KEY] = True
        return MutationResult(
            {"success": True, "screening_approved": True},
            save=True,
        )

    result = mutate_project(project_id, _mutator)
    if result is None:
        # mutate_project returns None when the project does not exist;
        # surface as ValueError to match the rest of the project-not-found
        # signalling pattern used by the web_server endpoints.
        raise ValueError(f"Project '{project_id}' not found")
    return result
