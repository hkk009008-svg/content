"""RunState -- per-run mutable state shared across the orchestrator and controllers.

V1.1 #5 in REFACTOR_HANDOFF.md. Replaces the previously-scattered
state ownership where ShotController owned ``shot_results``,
ReviewController owned ``review_clips``, and CinemaPipeline owned
the remaining 7 fields (``scene_clips``, ``scene_audio``,
``failed_shots``, ``current_stage`` / ``current_scene_id`` /
``current_shot_id``, ``_completed_scene_indices``).

Why
===

The old model required maintainers to consult §9.1 of the handoff
to figure out where each field lived. New code adding to per-run
state would have to pick an owner. With RunState:

  - One canonical home for per-run state.
  - Controllers + orchestrator share the SAME instance (passed by
    reference). Mutations are visible across all consumers.
  - Adding a new field is one line in this file; no need to touch
    multiple controllers.
  - Type-checking + IDE autocomplete improve (the fields are
    declared, not implicit attribute writes on a host object).

What lives here
===============

Per-run mutable state ONLY. Not long-lived deps (those go in
``cinema/core.PipelineCore``). Not lifecycle/cancel/progress (those
go on ``cinema/lifecycle.LifecycleService``).

What does NOT live here
=======================

- The project dict (lives on PipelineCore; mutated by
  ``_refresh_project_snapshot``).
- The review_clips manifest is here BUT the project's
  ``approved_*_take_id`` fields are NOT -- those are project-state,
  persisted to disk via ``mutate_project``.
- Phase results (those flow through ``PipelineContext`` between
  phases, not run-state).

Construction
============

Just ``RunState()`` -- all defaults are empty. CinemaPipeline
instantiates one per ``__init__`` and passes it to each controller.

Checkpoint restore writes wholesale to the runstate fields. That
works because all fields are dataclass attributes (settable
directly), no @property setters needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunState:
    """Mutable per-run state shared between orchestrator and controllers."""

    # ---------------------------------------------------------------------
    # Shot-domain run-state.
    # Written primarily by ShotController; read by orchestrator + Checkpoint.
    # ---------------------------------------------------------------------

    # shot_id -> {"image", "video", "identity_score", "status", "take_id"}
    shot_results: dict = field(default_factory=dict)

    # ---------------------------------------------------------------------
    # Review-domain run-state.
    # Written by ReviewController._rebuild_review_clips; read by web_server
    # endpoints + the UI.
    # ---------------------------------------------------------------------

    # shot_id -> review-clip manifest entry (scene_id, prompt, image, ...)
    review_clips: dict = field(default_factory=dict)

    # ---------------------------------------------------------------------
    # Scene-domain run-state.
    # Written by orchestrator (_build_scene_packages) + by ShotController
    # (generate_scene_preview). Read across the board.
    # ---------------------------------------------------------------------

    # scene_id -> list of video clip paths
    scene_clips: dict = field(default_factory=dict)

    # scene_id -> audio path
    scene_audio: dict = field(default_factory=dict)

    # scene_id -> foley path
    scene_foley: dict = field(default_factory=dict)

    # Ordered list of all foley paths generated during the run
    # (one per scene; appended by _ensure_scene_foley). Consumed by T3 tri-mix.
    foley_audio_paths: list = field(default_factory=list)

    # ---------------------------------------------------------------------
    # Failure tracking.
    # Written by orchestrator (generate() loop when a shot fails).
    # ---------------------------------------------------------------------

    # shot_ids that failed and were skipped
    failed_shots: list = field(default_factory=list)

    # ---------------------------------------------------------------------
    # Progress pointer triple.
    # Written by ShotController + ReviewController + orchestrator.
    # Read for UI status + checkpoint save.
    # ---------------------------------------------------------------------

    current_stage: str = ""
    current_scene_id: str = ""
    current_shot_id: str = ""

    # ---------------------------------------------------------------------
    # Run-mode flag.
    # Set once at construction (CinemaPipeline(headless=...)). When True,
    # review gates do NOT block on operator/web approval: ReviewController.
    # _wait_for_gate raises GateNotSatisfiedError if a gate can't be cleared
    # by auto-approve (for non-interactive script / E2E runs) instead of
    # polling forever. Web runs leave this False -- ThreadedLifecycle blocks
    # until the operator approves via the UI.
    # ---------------------------------------------------------------------

    headless: bool = False

    # ---------------------------------------------------------------------
    # Checkpoint-resume bookkeeping.
    # ---------------------------------------------------------------------

    # Set of scene indices already completed (skipped on resume)
    completed_scene_indices: set = field(default_factory=set)

    # ---------------------------------------------------------------------
    # Convenience method.
    # ---------------------------------------------------------------------

    def update_progress_pointer(
        self, stage: str, scene_id: str, shot_id: str
    ) -> None:
        """Update all three progress-pointer fields atomically.

        Called by ShotController during keyframe/motion generation
        and by ReviewController._wait_for_gate. The orchestrator's
        generate() loop sets the fields directly (e.g.,
        ``runstate.current_stage = "ASSEMBLY"``) -- this method is
        for the multi-field case where setting one without the
        others would leave a stale partial state.
        """
        self.current_stage = stage
        self.current_scene_id = scene_id
        self.current_shot_id = shot_id
