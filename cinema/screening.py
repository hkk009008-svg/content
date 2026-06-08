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

# audio.dialogue is a leaf module (no circular-import risk); import the
# char-filter helpers AND the cache-key fn together at module level. (A prior
# lazy guard for dialogue_cache_key was dead code: these module-level helper
# imports already make audio.dialogue a hard dependency of this module, so the
# guard could never fire — see T-E Lane V.)
from audio.dialogue import (
    dialogue_cache_key as _cache_key,
    scene_characters as _scene_chars,
    shot_characters as _shot_chars,
)

# TTS pricing: $0.01 per line — mirrors cost_tracker.py:66 ("ELEVENLABS": 0.01).
# Imported lazily below in estimate_reassembly_cost rather than at module level
# to avoid circular-import risk; this constant is the canonical reference.
# Deliberate single-rate approximation (T-B review note): Cartesia-routed
# lines actually cost 0.008 (cost_tracker.py "CARTESIA_SONIC_2") — the
# estimate over-states Korean projects by ~25%; acceptable for a pre-run
# advisory figure.
_TTS_COST_PER_LINE_USD = 0.01  # sourced from cost_tracker.py:66


logger = logging.getLogger(__name__)


SCREENING_STAGE_NAME = "SCREENING"
SCREENING_APPROVED_KEY = "screening_approved"

# S21 (cycle-9 Surface B): operator iterates a shot DURING screening,
# producing a new approved take. The assembled mp4 on disk no longer
# matches the project's current approved takes. The shot_id goes into
# ``project[NEEDS_REASSEMBLY_KEY]`` (a JSON-friendly list of shot_ids)
# so the operator-facing "Re-assemble" button can show how many shots
# are dirty + the re-assemble endpoint can short-circuit when nothing
# changed. Cleared atomically when re-assemble runs successfully.
#
# Field lives at the project's top level via ConfigDict(extra="allow")
# (domain/models.py:167) -- no Pydantic field added, matching the
# screening_approved precedent. Stored as a list (not a set) because
# JSON has no set primitive; helpers below preserve set semantics
# (idempotent add, no duplicates).
NEEDS_REASSEMBLY_KEY = "needs_reassembly"


def _screening_stage_enabled(project: dict | None = None) -> bool:
    """Feature flag: project-level ``global_settings.screening_stage_enabled``
    wins over env-var ``CINEMA_SCREENING_STAGE``; either may disable.

    Lookup order (closes M-B1 — cycle-16 Tier B surfaced that project-level
    setting was completely ignored; env-var was the only knob):

      1. ``project["global_settings"]["screening_stage_enabled"]`` (if project
         passed AND key is explicitly present — truthy/falsy interpreted
         leniently for backward compat with operator-typed UI values like
         ``"true"`` / ``"1"`` / ``False``).
      2. Env var ``CINEMA_SCREENING_STAGE`` (legacy path; default ON; falsy
         values ``0|false|no`` opt out).
      3. Default ON.

    Default ON history: v5.1+ flag-flip (2026-05-26 user-principal
    authorization; operator + director joint flag-flip-recommended per
    Val#1 V3+V5 LIVE + Val#2 U3 14-stage rail DOM-confirmed; V1
    defense-in-depth fold shipped pre-flip at ``d10b849``).

    Falsy-value set matches ``_directorial_iteration_enabled()`` exactly
    so an operator who disables the directorial-iteration flag with the
    same spelling gets the same answer here. Read at each call so dynamic
    env mutation is observable without restart.

    Callers that don't have project context (e.g., the cold endpoint at
    ``web_server.py:2147`` before ``load_project`` is invoked) may pass
    ``None`` (default) and get the env-only legacy behavior — backward
    compatible.
    """
    if project is not None:
        global_settings = project.get("global_settings") or {}
        if "screening_stage_enabled" in global_settings:
            val = global_settings["screening_stage_enabled"]
            # Lenient truthy/falsy: handle bool, int, and string values
            # from the project schema (UI may store any of these).
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return val != 0
            if isinstance(val, str):
                return val.strip().lower() not in {"0", "false", "no", ""}
            # Any other type — fall through to env-var path
    return os.environ.get("CINEMA_SCREENING_STAGE", "").strip().lower() not in {
        "0", "false", "no",
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

    P1-3 migration template (S10 + part 9 Variant 1; B-006-broad-A) --
    inner mutator-scope validate under the per-project lock. No outer
    boundary validate here: the function takes ``project_id: str``, not
    a project dict, so the load-then-mutate flow places the only project
    dict inside the mutator. Inner validate catches a corrupt on-disk
    snapshot before the root-scalar write. See
    docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 c296105).
    """
    from project_manager import MutationResult, mutate_project
    from domain.models import Project as _Project

    def _mutator(latest_project: dict):
        _Project.model_validate(latest_project)  # inner mutator-scope validate
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


# ---------------------------------------------------------------------------
# S21 (cycle-9 Surface B): dirty-shot tracking + re-assembly cost estimation
# ---------------------------------------------------------------------------


def get_needs_reassembly(project: dict) -> list[str]:
    """Return the list of shot_ids that have been iterated during SCREENING.

    Reads ``project[NEEDS_REASSEMBLY_KEY]`` defensively: a missing key,
    a None value, or any non-list value returns an empty list. Order is
    preserved (insertion order) -- callers that need stable iteration
    can rely on it; callers that need set semantics should convert.
    """
    if not isinstance(project, dict):
        return []
    raw = project.get(NEEDS_REASSEMBLY_KEY) or []
    if not isinstance(raw, list):
        return []
    # Defensive: filter to str entries only (corrupted JSON could
    # round-trip as something else)
    return [s for s in raw if isinstance(s, str)]


def mark_shot_needs_reassembly(project_id: str, shot_id: str) -> dict:
    """Atomically add ``shot_id`` to ``project.needs_reassembly``.

    Called from ``ShotController.regenerate_with_intent`` after a
    successful iterate that fires DURING SCREENING. Idempotent: re-
    adding the same shot_id is a no-op (no duplicates).

    Returns a small result dict with the post-mutation list. Returns
    ``{"success": False, "error": "..."}`` if the project doesn't
    exist (the controller swallows this since dirty-tracking is best-
    effort -- the operator can re-iterate to retry).

    Import is lazy (mirrors mark_screening_approved) so this module
    stays import-safe under cold-flag probes.

    P1-3 migration template (S10 + part 9 Variant 1; B-006-broad-A) --
    inner mutator-scope validate under the per-project lock. No outer
    boundary validate (function takes ``project_id: str``); inner validate
    catches a corrupt on-disk snapshot before the root-list idempotent-add.
    The shot_id-empty early-return guard below stays unchanged (validate
    only runs once we're entering the lock-held mutator). See
    docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 c296105).
    """
    if not shot_id:
        return {"success": False, "error": "shot_id is empty"}

    from project_manager import MutationResult, mutate_project
    from domain.models import Project as _Project

    def _mutator(latest_project: dict):
        _Project.model_validate(latest_project)  # inner mutator-scope validate
        current = latest_project.get(NEEDS_REASSEMBLY_KEY) or []
        if not isinstance(current, list):
            current = []
        # Idempotent add: preserve insertion order, dedupe via set membership.
        if shot_id not in current:
            current.append(shot_id)
        latest_project[NEEDS_REASSEMBLY_KEY] = current
        return MutationResult(
            {"success": True, "needs_reassembly": list(current)},
            save=True,
        )

    result = mutate_project(project_id, _mutator)
    if result is None:
        return {"success": False, "error": f"Project '{project_id}' not found"}
    return result


def clear_needs_reassembly(
    project_id: str,
    only_shots: list[str] | None = None,
) -> dict:
    """Atomically clear ``project.needs_reassembly``.

    Called from the re-assemble endpoint after a successful re-stitch.
    Idempotent: clearing an empty list is fine (no-op shape, but the
    mutate still runs to ensure persistence is consistent with the
    just-written assembled mp4). Returns a small result dict.

    When ``only_shots`` is provided, ONLY those shot_ids are removed
    from the needs_reassembly list — any shots added concurrently
    (e.g., from an iterate-during-re-assemble window once Lane V #8
    I1 is fixed) are preserved. The caller passes the snapshot list it
    re-rendered into the new mp4; everything else stays dirty. Lane V
    #8 I3 closed this race; without the parameter, the post-assembly
    wipe would silently drop fresh iterations that landed during the
    ~30-90s re-assemble window.

    When ``only_shots`` is ``None`` (legacy default), wipes the entire
    list. Preserved for callers that don't need the snapshot semantics.

    Raises ``ValueError`` if the project doesn't exist (caller surfaces
    as 404).

    P1-3 migration template (S10 + part 9 Variant 1; B-006-broad-A) --
    inner mutator-scope validate under the per-project lock. No outer
    boundary validate (function takes ``project_id: str``); inner validate
    catches a corrupt on-disk snapshot before the root-list filter/wipe.
    See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 c296105).
    """
    from project_manager import MutationResult, mutate_project
    from domain.models import Project as _Project

    def _mutator(latest_project: dict):
        _Project.model_validate(latest_project)  # inner mutator-scope validate
        if only_shots is None:
            latest_project[NEEDS_REASSEMBLY_KEY] = []
            cleared: list[str] = []
        else:
            current = set(latest_project.get(NEEDS_REASSEMBLY_KEY) or [])
            to_clear = set(only_shots)
            latest_project[NEEDS_REASSEMBLY_KEY] = sorted(current - to_clear)
            cleared = sorted(current & to_clear)
        return MutationResult(
            {
                "success": True,
                "needs_reassembly": list(latest_project[NEEDS_REASSEMBLY_KEY]),
                "cleared": cleared,
            },
            save=True,
        )

    result = mutate_project(project_id, _mutator)
    if result is None:
        raise ValueError(f"Project '{project_id}' not found")
    return result


# S21 cost-estimate heuristic constants. Derived from the Q5 measurement
# spike (see commit body of S21 -- commit 4075f8e) -- synthetic
# _assemble_final timing at N=5/30/60 stub mp4s produced a roughly-linear
# cost curve on (a) per-clip normalize (per-shot ffmpeg fork + libx264
# encode) and (b) total-output-duration stages (stitch + grade + bgm +
# loudnorm). For real production projects at avg 5s/shot, multiply the
# duration-bound stages by ~5x. These constants err generous (operator
# sees "it'll be slower than this if we're wrong").
#
# (S21 reviewer Minor #6 fold) Pasting the raw Q5 measurement table here
# so the constants stay auditable in 12 months without ``git log`` archaeology:
#
#   Synthetic _assemble_final timing (Macbook M-series, ffmpeg 8.1).
#   1s clips at 640x360 -> 1920x1080@30fps:
#     N    norm  stitch  grade   bgm  loudnorm   total
#     5    0.49   0.02   0.72   0.09     0.22    1.54s
#    30    2.92   0.05   3.89   0.44     0.95    8.25s
#    60    5.98   0.08   8.41   0.87     1.86   17.21s
#
#   Real-world projection for 60 shots * 5s avg (300s source):
#     normalize ~30s, grade ~45s, loudnorm ~10s, total ~90s.
#   Typical 30-shot project: ~45s, well within the 60s operator target.
#
# Per-clip cost (libx264 encode + ffmpeg fork): ~0.1s/clip baseline,
#   amortized by source-clip duration. For real shots at 5s avg:
#   ~0.5s/clip normalize.
# Total-output-duration cost: ~0.07x of source duration for stitch+grade+bgm
#   combined; loudnorm adds another ~0.02x. Combined factor: ~0.09x.
#
# Formula: cost_s ~= shot_count * 0.5 + total_duration_s * 0.09
# Floor: 5s (single-shot project has fixed setup overhead).
_REASSEMBLY_PER_SHOT_OVERHEAD_S = 0.5
_REASSEMBLY_DURATION_FACTOR = 0.09
_REASSEMBLY_FLOOR_S = 5.0


def estimate_reassembly_cost(project: dict) -> dict:
    """Estimate the wall-clock cost of a full re-assembly in seconds.

    Cost model derived from the Q5 measurement spike (S21 commit body):
    decomposes into per-shot overhead (ffmpeg fork + libx264 encode for
    normalize) + a duration-bound factor for the stitch/grade/bgm/loudnorm
    stages. The constants are conservative (real time should usually beat
    the estimate).

    Returns ``{seconds: float, breakdown: {...}, shot_count: int,
    total_source_duration_s: float, tts_lines_to_generate: int,
    estimated_tts_usd: float}``. The breakdown dict surfaces the per-stage
    estimate so the UI can show a tooltip ("normalize: 30s, encode pass: 45s,
    loudnorm: 10s, TTS: $0.05") without re-doing the math.

    tts_lines_to_generate and estimated_tts_usd (ticket T-B): counts
    dialogue lines whose keyed artifact does NOT exist in the project temp dir
    (i.e., lines that would trigger a fresh paid TTS call on re-assembly).
    LLM-generated dialogue (non-list) is counted as needing regeneration since
    the content is nondeterministic and the key cannot be predicted here.

    Defensive: an empty project / no scenes returns ``{seconds: floor, ...}``
    -- the floor catches "operator clicks re-assemble before anything is
    assembled," which is itself a no-op but should still estimate as small
    (not 0, not negative).
    """
    if not isinstance(project, dict):
        return {
            "seconds": _REASSEMBLY_FLOOR_S,
            "shot_count": 0,
            "total_source_duration_s": 0.0,
            "tts_lines_to_generate": 0,
            "estimated_tts_usd": 0.0,
            "breakdown": {
                "normalize_s": 0.0,
                "duration_bound_s": 0.0,
                "floor_s": _REASSEMBLY_FLOOR_S,
            },
        }

    # Derive the project temp dir the same way build_pipeline_core does at
    # cinema/core.py:92 — os.path.join(project_dir, "temp").
    pid = project.get("id", "")
    try:
        from domain.project_manager import get_project_dir
        _temp_dir = os.path.join(get_project_dir(pid), "temp") if pid else None
    except Exception:
        _temp_dir = None

    proj_settings = project.get("global_settings", {}) or {}
    lang = proj_settings.get("language", "English")
    all_characters = project.get("characters", []) or []

    shot_count = 0
    total_duration_s = 0.0
    tts_lines_to_generate = 0

    scenes = project.get("scenes") or []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("id", "")
        scene_fallback = 5.0
        raw = scene.get("duration_seconds")
        if raw is not None:
            try:
                scene_fallback = float(raw)
            except (TypeError, ValueError):
                scene_fallback = 5.0

        # Scene-level characters: mirror cinema_pipeline.py:738-741 exactly —
        # filter project characters by characters_present (per-scene subset).
        # Using the project-wide list here would produce a different cache key
        # from the writer and cause false "not cached" counts (T-D fix).
        scene_characters = _scene_chars(all_characters, scene)

        # Scene-level dialogue TTS estimate (mirrors _ensure_scene_audio logic).
        scene_dialogue = scene.get("dialogue", "")
        if scene_dialogue:
            if isinstance(scene_dialogue, list) and _cache_key and _temp_dir:
                # Explicit list: can predict the key and check disk.
                key = _cache_key(scene_dialogue, scene_characters, lang)
                cached_path = os.path.join(_temp_dir, f"audio_{scene_id}_{key}.mp3")
                if not os.path.exists(cached_path):
                    tts_lines_to_generate += len(scene_dialogue)
            else:
                # LLM-generated or no cache check available — assume regeneration.
                if isinstance(scene_dialogue, list):
                    tts_lines_to_generate += len(scene_dialogue)
                elif isinstance(scene_dialogue, str):
                    # Count as 1 generate-dialogue LLM call + unknown lines;
                    # use 1 as a conservative lower bound so the estimate is
                    # not zero for LLM-dialogue scenes.
                    tts_lines_to_generate += 1
        elif scene_characters and scene.get("action"):
            # Action-only scene: _ensure_scene_audio generates dialogue via
            # LLM then renders TTS for it (cinema_pipeline.py — the
            # characters-and-action-no-dialogue branch). Count a conservative
            # 1 line so these scenes aren't silently omitted from the
            # estimate (T-B spec review SI-1).
            tts_lines_to_generate += 1

        for shot in scene.get("shots", []) or []:
            if not isinstance(shot, dict):
                continue
            if not shot.get("approved_final_take_id"):
                continue
            shot_count += 1
            # Find approved take to read its duration_s; fall back to scene.
            approved_id = shot.get("approved_final_take_id", "")
            take_dur = scene_fallback
            for coll_name in (
                "postprocess_variants", "motion_takes",
                "performance_takes", "keyframe_takes",
            ):
                for take in shot.get(coll_name, []) or []:
                    if isinstance(take, dict) and take.get("id") == approved_id:
                        take_dur = _take_duration_seconds(take, scene_fallback)
                        break
                else:
                    continue
                break
            total_duration_s += take_dur

            # Shot-level dialogue TTS estimate (mirrors _ensure_shot_audio).
            shot_id = shot.get("id", "")
            shot_dialogue = shot.get("dialogue")
            if shot_dialogue:
                if isinstance(shot_dialogue, str):
                    shot_dialogue_lines = [{"text": shot_dialogue}]
                elif isinstance(shot_dialogue, list):
                    shot_dialogue_lines = shot_dialogue
                else:
                    shot_dialogue_lines = None

                if shot_dialogue_lines and _cache_key and _temp_dir:
                    # Mirror the shot_characters helper (audio/dialogue.py):
                    # shot-level characters filtered by characters_in_frame,
                    # falling back to the scene's characters_present set
                    # (Rule #13 audit). The canonical shot-level derivation now
                    # lives in the helper rather than inline in controller.py.
                    shot_characters = _shot_chars(all_characters, shot, scene)
                    key = _cache_key(shot_dialogue_lines, shot_characters, lang)
                    cached_path = os.path.join(_temp_dir, f"audio_{shot_id}_{key}.mp3")
                    if not os.path.exists(cached_path):
                        tts_lines_to_generate += len(shot_dialogue_lines)
                elif shot_dialogue_lines:
                    tts_lines_to_generate += len(shot_dialogue_lines)

    normalize_s = shot_count * _REASSEMBLY_PER_SHOT_OVERHEAD_S
    duration_bound_s = total_duration_s * _REASSEMBLY_DURATION_FACTOR
    raw_total = normalize_s + duration_bound_s
    seconds = max(_REASSEMBLY_FLOOR_S, raw_total)
    estimated_tts_usd = round(tts_lines_to_generate * _TTS_COST_PER_LINE_USD, 2)

    return {
        "seconds": round(seconds, 2),
        "shot_count": shot_count,
        "total_source_duration_s": round(total_duration_s, 2),
        "tts_lines_to_generate": tts_lines_to_generate,
        "estimated_tts_usd": estimated_tts_usd,
        "breakdown": {
            "normalize_s": round(normalize_s, 2),
            "duration_bound_s": round(duration_bound_s, 2),
            "floor_s": _REASSEMBLY_FLOOR_S,
        },
    }
