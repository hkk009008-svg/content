"""
domain/models.py — Pydantic v2 models for project.json validation.

These models mirror the project.json schema as observed in real project
fixtures.  They are used ONLY at the load/save boundary (via
_validate_project in project_manager.py) to emit warnings on schema drift.

Design choices:
- All models use ``extra="allow"`` so organic field additions in existing
  project files don't raise errors — Session 9 can tighten this.
- All fields default to empty / None so partially-populated early-pipeline
  shots validate without errors.
- ``created_at`` stays ``str`` (not datetime) to preserve the exact
  ISO-8601+Z suffix that JSON round-trips rely on.
- Mutable defaults use Field(default_factory=...) to avoid the shared-dict
  Python gotcha.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CascadeMetadata(BaseModel):
    """Session-6 cascade decision metadata carried on a TakeRecord."""

    model_config = ConfigDict(extra="allow")

    engine: str = ""
    score: Optional[float] = None
    threshold: Optional[float] = None
    fallback: Optional[bool] = None
    attempts: Optional[List[str]] = None


class TakeRecord(BaseModel):
    """A single generation attempt (keyframe / motion / performance / postprocess)."""

    model_config = ConfigDict(extra="allow")

    id: str
    kind: Literal["keyframe", "motion", "performance", "postprocess"]
    path: str = ""
    source_take_id: str = ""
    status: str = ""
    created_at: str = ""  # ISO-8601 string; keep as str for JSON round-trip safety
    metadata: dict = Field(default_factory=dict)
    cascade_metadata: Optional[CascadeMetadata] = None


class Shot(BaseModel):
    """One shot within a scene — the core unit of the pipeline."""

    model_config = ConfigDict(extra="allow")

    id: str
    prompt: str = ""
    camera: str = ""
    visual_effect: str = ""
    target_api: str = ""
    scene_foley: str = ""
    characters_in_frame: List[str] = Field(default_factory=list)
    primary_character: str = ""
    action_context: str = ""
    generated_image: str = ""
    generated_video: str = ""
    plan_status: str = ""
    plan_rejection_reason: str = ""
    # Take lists — ALL default to [] so partially-generated shots validate.
    # performance_takes MUST be present; its absence caused the Session-2 P0
    # bug in cinema/shots/controller.py:_find_take.
    keyframe_takes: List[TakeRecord] = Field(default_factory=list)
    approved_keyframe_take_id: str = ""
    motion_takes: List[TakeRecord] = Field(default_factory=list)
    approved_motion_take_id: str = ""
    postprocess_variants: List[TakeRecord] = Field(default_factory=list)
    approved_final_take_id: str = ""
    performance_takes: List[TakeRecord] = Field(default_factory=list)
    performance_take_id: str = ""
    # Misc shot metadata
    diagnostics: List[dict] = Field(default_factory=list)
    intent_notes: str = ""
    negative_constraints: str = ""
    continuity_constraints: str = ""


class Scene(BaseModel):
    """One scene — a list of shots with narrative context."""

    model_config = ConfigDict(extra="allow")

    id: str
    order: int = 0
    title: str = ""
    location_id: str = ""
    characters_present: List[str] = Field(default_factory=list)
    action: str = ""
    dialogue: str = ""
    mood: str = ""
    camera_direction: str = ""
    duration_seconds: float = 0.0
    num_shots: int = 0
    shots: List[Shot] = Field(default_factory=list)


class Character(BaseModel):
    """A named character referenced in the project."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str = ""
    description: str = ""
    voice_id: str = ""
    reference_image: str = ""


class Location(BaseModel):
    """A named location referenced in the project."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str = ""
    description: str = ""
    reference_image: str = ""


class Project(BaseModel):
    """
    Top-level project document.  Permissive by design (extra="allow") so
    unknown top-level fields (global_settings, UI scratchpads, deprecated
    keys) do not fail validation — they emit a warning via _validate_project.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    name: str = ""
    characters: List[Character] = Field(default_factory=list)
    locations: List[Location] = Field(default_factory=list)
    scenes: List[Scene] = Field(default_factory=list)
