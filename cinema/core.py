"""PipelineCore — long-lived project deps + services, separable from runtime state.

Split out of cinema_pipeline.CinemaPipeline.__init__ during the
post-Slice-E "standalone controllers" effort. The goal: let
controllers (Shot/Review/Checkpoint) be constructed from a
PipelineCore alone, without the runtime-state machinery
(shot_results, failed_shots, current_*) that the orchestrator's
generate() flow uses.

What lives in PipelineCore (long-lived, one per project)
========================================================

  project      dict        — loaded by load_project(), mutated in place
                             by _refresh_project_snapshot
  project_dir  str         — filesystem root
  temp_dir     str         — intermediate artifacts
  export_dir   str         — final outputs
  continuity   ContinuityEngine
  director     ChiefDirector
  quality_tracker QualityTracker
  cost_tracker CostTracker
  ensemble     LLMEnsemble

What does NOT live here (per-run state)
=======================================

  shot_results / failed_shots / current_stage|scene_id|shot_id   →
    these are mutable bookkeeping that exists only during a generation
    run. The orchestrator (CinemaPipeline) holds them.

  lifecycle    →   injected separately so the same Core can be reused
    across runs with different progress callbacks / cancellation
    tokens.

Construction
============

Use ``build_pipeline_core(project_id)`` for the factory. It loads
the project, ensures temp/export dirs exist, and constructs all the
service objects with their global_settings parameters. Raises
ValueError if the project isn't found (same contract as the legacy
CinemaPipeline.__init__).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.project_manager import load_project, get_project_dir
from llm.chief_director import ChiefDirector
from llm.ensemble import LLMEnsemble
from domain.continuity_engine import ContinuityEngine
from quality_tracker import QualityTracker
from cost_tracker import CostTracker

if TYPE_CHECKING:
    # Avoid circular import at runtime
    pass


@dataclass
class PipelineCore:
    """Long-lived project deps + services. One per project, reusable across runs."""

    project: dict
    project_dir: str
    temp_dir: str
    export_dir: str
    continuity: ContinuityEngine
    director: ChiefDirector
    quality_tracker: QualityTracker
    cost_tracker: CostTracker
    ensemble: LLMEnsemble


def build_pipeline_core(project_id: str) -> PipelineCore:
    """Construct a PipelineCore for the given project_id.

    Loads the project from disk, ensures temp/ + exports/ directories
    exist, and instantiates the service objects with project-specific
    global_settings.

    Raises
    ------
    ValueError
        If the project_id doesn't resolve to a saved project.
    """
    project = load_project(project_id)
    if not project:
        raise ValueError(f"Project '{project_id}' not found")

    project_dir = get_project_dir(project_id)
    temp_dir = os.path.join(project_dir, "temp")
    export_dir = os.path.join(project_dir, "exports")
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(export_dir, exist_ok=True)

    settings = project.get("global_settings", {})

    return PipelineCore(
        project=project,
        project_dir=project_dir,
        temp_dir=temp_dir,
        export_dir=export_dir,
        continuity=ContinuityEngine(project),
        director=ChiefDirector(project),
        quality_tracker=QualityTracker(),
        cost_tracker=CostTracker(),
        ensemble=LLMEnsemble(settings=settings),
    )
