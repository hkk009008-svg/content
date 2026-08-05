"""
domain/models.py — Pydantic v2 models for project.json validation.

These models mirror the project.json schema as observed in real project
fixtures.  They are used ONLY at the load/save boundary (via
_validate_project in project_manager.py) to emit warnings on schema drift.

Design choices:
- All models use ``extra="allow"`` so organic field additions in existing
  project files don't raise errors — Session 9 can tighten this.
- Optional pipeline fields carry backward-compatible defaults so
  partially-populated early-pipeline records validate without errors.
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


class DirectorialIntent(BaseModel):
    """S15 substrate: operator-supplied directorial intent for take regeneration.

    Created when the operator iterates on a take via the directorial iteration
    loop (gate-review surface, S17+) or the screening stage (post-assembly
    surface, S20). The intent is translated into a revised prompt + parameter
    overrides + anchor refs by ``llm.director.CinemaDirector.translate_intent``
    before the actual regeneration runs.

    Distinct from ``source_take_id`` on TakeRecord (which tracks postprocess
    derivation chains): ``parent_take_id`` on a regenerated TakeRecord tracks
    the directorial-iteration history. The two are orthogonal — an iteration
    of a postprocess variant could carry both.
    """

    model_config = ConfigDict(extra="allow")

    prose: str                                   # Always present; the freeform note
    verb: Optional[str] = None                   # Optional structured verb (S18+ DSL)
    params: dict = Field(default_factory=dict)   # Verb-specific structured params
    refs: List[dict] = Field(default_factory=list)  # Anchor refs (shot/take IDs)
    target_stage: Literal["keyframe", "performance", "motion"] = "keyframe"


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
    # S15 substrate — directorial iteration provenance (all optional, backward-compat).
    # See DirectorialIntent docstring for the orthogonality vs source_take_id.
    parent_take_id: Optional[str] = None
    intent: Optional[DirectorialIntent] = None
    revised_prompt: Optional[str] = None


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
    objects_in_frame: List[str] = Field(default_factory=list)
    primary_object: str = ""
    location_id: str = ""
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
    # Public-safe recovery descriptor for accepted motion-provider work that
    # has not produced a publishable take yet. The server may retain an opaque
    # request fingerprint inside this object to prevent changed-input
    # resubmission; UI consumers render only the documented safe fields.
    deferred_motion_job: Optional[dict] = None
    # Durable cross-request interlock for keyframe submissions whose provider
    # outcome must be reconciled before another paid render can start.
    deferred_keyframe_job: Optional[dict] = None
    postprocess_variants: List[TakeRecord] = Field(default_factory=list)
    approved_final_take_id: str = ""
    performance_takes: List[TakeRecord] = Field(default_factory=list)
    approved_performance_take_id: str = ""
    # Historical-only bare field. Runtime writers use the approved_* shape,
    # but retain this declaration so old project records still round-trip.
    performance_take_id: str = ""
    performance_engine: str = ""
    driving_video_path: str = ""
    # Validated uploads are immutable, content-addressed inputs.  The active
    # pointer may change, while these histories preserve every prior revision
    # and explicit review decision for reproducibility/audit.
    driving_video_history: List[dict] = Field(default_factory=list)
    performance_skip: Optional[dict] = None
    performance_skip_history: List[dict] = Field(default_factory=list)
    performance_review_history: List[dict] = Field(default_factory=list)
    # Misc shot metadata
    diagnostics: List[dict] = Field(default_factory=list)
    intent_notes: str = ""
    negative_constraints: str = ""
    continuity_constraints: str = ""
    # Active extension contract. These fields are written or read by current
    # production paths but were previously admitted only through extra="allow".
    # Keeping the model permissive preserves historical load compatibility;
    # public replacement boundaries separately reject undeclared extras.
    optimizer_cache: dict = Field(default_factory=dict)
    dialogue: str | List[dict] | None = None
    duration: float = 5.0
    motion_description: str = ""
    shot_type: str = ""
    shot_class: str = ""
    performance_budget_mode: str = ""
    target_api_policy_reason: str = ""
    ensemble_winner: Optional[str] = None
    ensemble_scores: List[float] = Field(default_factory=list)
    director_review: dict = Field(default_factory=dict)
    auto_approve_audit: List[dict] = Field(default_factory=list)
    plan_auto_approved: bool = False
    image_auto_approved: bool = False
    motion_auto_approved: bool = False
    final_auto_approved: bool = False
    approved: Optional[bool] = None


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
    # Optional gender hint ("male" / "female" / ""). Used by voice picker to
    # narrow VOICE_POOL when assigning voice_id. Empty means no preference;
    # picker uses language defaults' default_female_voice as the unhinted
    # fallback (closer to common cinema use than the prior hardcoded Adam).
    # See VG-B1 closure 2026-05-27.
    gender: str = ""


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
