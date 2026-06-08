"""
Cinema Production Tool — Project Manager
Handles project CRUD, persistence, and data model definitions.
Projects are stored as JSON files under projects/<project_id>/.
"""

import os
import json
import logging
import uuid
import random
import shutil
import tempfile
from datetime import datetime, timezone
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional, List, Dict

from filelock import FileLock, Timeout
from pydantic import ValidationError

from cinema.auto_approve import AutoApproveConfig
from domain.models import Project

logger = logging.getLogger(__name__)

PROJECTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects")


class ProjectLockError(RuntimeError):
    """Raised when a project mutation cannot acquire the project lock in time."""

    def __init__(self, project_id: str, timeout: float):
        self.project_id = project_id
        self.timeout = timeout
        super().__init__(
            f"Project '{project_id}' is locked by another operation. Retry shortly."
        )


@dataclass
class MutationResult:
    value: Any
    save: bool = True


def _ensure_projects_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def _project_dir(project_id: str) -> str:
    return os.path.join(PROJECTS_DIR, project_id)


def _project_file(project_id: str) -> str:
    return os.path.join(_project_dir(project_id), "project.json")


def _project_lock_path(project_id: str) -> str:
    return os.path.join(_project_dir(project_id), "project.lock")


def _ensure_project_dir(project_id: str):
    _ensure_projects_dir()
    os.makedirs(_project_dir(project_id), exist_ok=True)


@contextmanager
def _acquire_project_lock(project_id: str, timeout: float = 10):
    _ensure_project_dir(project_id)
    lock = FileLock(_project_lock_path(project_id), timeout=timeout)
    try:
        with lock:
            yield
    except Timeout as exc:
        raise ProjectLockError(project_id, timeout) from exc


def _load_project_unlocked(project_id: str) -> Optional[dict]:
    path = _project_file(project_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_project_unlocked(project: dict) -> None:
    pid = project["id"]
    _ensure_project_dir(pid)
    target = _project_file(pid)
    fd, tmp_path = tempfile.mkstemp(suffix=".json.tmp", dir=_project_dir(pid))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(project, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, target)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _sync_project_snapshot(snapshot: Optional[dict], latest: dict) -> None:
    if snapshot is None or snapshot is latest:
        return
    snapshot.clear()
    snapshot.update(latest)


@contextmanager
def project_lock(project_id: str, timeout: int = 10):
    """
    Per-project file lock for thread-safe read-modify-write cycles.
    Use this when multiple operations need to be atomic:

        with project_lock(pid):
            proj = load_project(pid)
            proj["name"] = "new"
            save_project(proj)
    """
    with _acquire_project_lock(project_id, timeout):
        yield


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    # Timezone-aware UTC; datetime.utcnow() is deprecated in 3.12+.
    # `.replace("+00:00", "Z")` preserves the existing project.json
    # timestamp suffix shape so old + new entries are visually consistent.
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_take(
    kind: str,
    path: str = "",
    *,
    source_take_id: str = "",
    status: str = "generated",
    metadata: Optional[dict] = None,
) -> dict:
    return {
        "id": f"take_{new_id()}",
        "kind": kind,
        "path": path,
        "source_take_id": source_take_id,
        "status": status,
        "created_at": _now_iso(),
        "metadata": metadata or {},
    }


def make_character(
    name: str,
    description: str,
    reference_images: Optional[List[str]] = None,
    voice_id: str = "",
    ip_adapter_weight: float = 0.85,
    gender: str = "",
) -> dict:
    return {
        "id": f"char_{new_id()}",
        "name": name,
        "description": description,
        "reference_images": reference_images or [],
        "canonical_reference": "",
        "voice_id": voice_id,
        "gender": gender,
        "ip_adapter_weight": ip_adapter_weight,
        "physical_traits": "",
        "embedding_cache": "",
    }


def make_object(
    name: str,
    description: str,
    brand: str = "",
    reference_images: Optional[List[str]] = None,
    material_traits: str = "",
    surface_type: str = "matte",          # matte | glossy | metallic | translucent | mixed
    branding_constraints: str = "",
    scale_reference: str = "",             # e.g. "fits in adult hand", "tabletop scale"
    texture_anchor: str = "",              # critical visual: logo, badge, signature color
    ip_adapter_weight: float = 0.85,
) -> dict:
    """Factory for ProductObject records — product/prop assets used in commercials.

    Mirrors make_character/make_location so the pipeline treats objects as
    first-class subjects with reference-image conditioning, identity anchors,
    and per-shot routing.
    """
    return {
        "id": f"obj_{new_id()}",
        "name": name,
        "brand": brand,
        "description": description,
        "reference_images": reference_images or [],
        "canonical_reference": "",          # populated when user picks the hero ref
        "material_traits": material_traits,
        "surface_type": surface_type,
        "branding_constraints": branding_constraints,
        "scale_reference": scale_reference,
        "texture_anchor": texture_anchor,
        "ip_adapter_weight": ip_adapter_weight,
        "embedding_cache": "",
    }


def make_location(
    name: str,
    description: str,
    reference_images: Optional[List[str]] = None,
    lighting: str = "",
    time_of_day: str = "day",
    weather: str = "clear",
) -> dict:
    return {
        "id": f"loc_{new_id()}",
        "name": name,
        "description": description,
        "reference_images": reference_images or [],
        "prompt_fragment": "",
        "lighting": lighting,
        "time_of_day": time_of_day,
        "weather": weather,
        "seed": random.randint(100000, 999999),
    }


def make_scene(
    title: str,
    location_id: str = "",
    characters_present: Optional[List[str]] = None,
    action: str = "",
    dialogue: str = "",
    mood: str = "neutral",
    camera_direction: str = "",
    duration_seconds: float = 5.0,
) -> dict:
    return {
        "id": f"scene_{new_id()}",
        "order": 0,
        "title": title,
        "location_id": location_id,
        "characters_present": characters_present or [],
        "action": action,
        "dialogue": dialogue,
        "mood": mood,
        "camera_direction": camera_direction,
        "duration_seconds": duration_seconds,
        "num_shots": 0,
        "shots": [],
    }


def make_shot(
    prompt: str,
    camera: str = "zoom_in_slow",
    visual_effect: str = "cinematic_glow",
    target_api: str = "AUTO",
    scene_foley: str = "",
    characters_in_frame: Optional[List[str]] = None,
    primary_character: str = "",
    objects_in_frame: Optional[List[str]] = None,
    primary_object: str = "",
    shot_id: str = "",
) -> dict:
    return {
        "id": shot_id or f"shot_{new_id()}",
        "prompt": prompt,
        "camera": camera,
        "visual_effect": visual_effect,
        "target_api": target_api,
        "scene_foley": scene_foley,
        "characters_in_frame": characters_in_frame or [],
        "primary_character": primary_character,
        "objects_in_frame": objects_in_frame or [],
        "primary_object": primary_object,
        "action_context": "",
        "generated_image": "",
        "generated_video": "",
        "plan_status": "pending_review",
        "plan_rejection_reason": "",
        "keyframe_takes": [],
        "approved_keyframe_take_id": "",
        "motion_takes": [],
        "approved_motion_take_id": "",
        "postprocess_variants": [],
        "approved_final_take_id": "",
        "diagnostics": [],
        "intent_notes": "",
        "negative_constraints": "blur, distort, deformed face, identity drift, off-model face, broken anatomy, off-brand product, deformed logo, mis-shaped product",
        "continuity_constraints": "",
        "optimizer_cache": {},  # populated by prompt_optimizer when enabled
        # --- Performance capture (handoff §4) ---
        "performance_takes": [],            # list[take dict] — make_take(kind="performance", ...)
        "approved_performance_take_id": "", # mirrors approved_keyframe_take_id
        "performance_engine": "",           # "ACT_ONE" | "LIVE_PORTRAIT" | "VIGGLE" | "SKIP" | ""
        "driving_video_path": "",           # operator-uploaded reference, Mode A
    }


def make_project(name: str) -> dict:
    return {
        "id": new_id(),
        "name": name,
        "characters": [],
        "locations": [],
        "objects": [],
        "scenes": [],
        "global_settings": {
            "aspect_ratio": "16:9",
            "music_mood": "suspense",
            "color_palette": "",
            "master_seed": random.randint(100000, 999999),
            "style_rules": {},
            "budget_limit_usd": 0,
            "identity_strictness": 0.60,
            "creative_llm": "auto",
            "quality_judge_llm": "auto",
            "competitive_generation": True,
            "adaptive_pulid": True,
            "coherence_check_enabled": True,
            "color_drift_sensitivity": 0.3,
            # F-B.2 closure (cycle-16 max-quality audit a79c59): LLM-based
            # shot-prompt optimizer (cinematography-precise grammar + API
            # routing hints + identity anchor + negative constraints).
            # Default ON — cinema/shots/controller.py:391 reads this; was
            # defaulting False because the field never existed in defaults.
            # Caches optimizer output on the shot (.optimizer_cache) so
            # regen doesn't repeat the LLM call.
            "prompt_optimizer_enabled": True,
            # Step-3 (2026-05-24): N=8 best-of per-batch parallelism. 1 = sequential
            # (historic behavior); up to 4 = concurrent workers on the same RunPod
            # pod, overlapping submit/poll/download cycles. ComfyUI still serializes
            # GPU work per pod.
            "max_quality_parallel_workers": 1,
            # P4-3 (Session 11): auto-approve veto rules config. Conservative-on
            # defaults; operator tunes via project settings. Typed schema is
            # Session 10 (P1-3 part 2) work — rides through extra="allow" for now.
            "auto_approve": AutoApproveConfig().to_dict(),
            # api_engines (per-engine config: KLING_NATIVE.storyboard_mode,
            # .enabled, .duration, .face_consistency, etc.) is intentionally
            # NOT scaffolded here: it's operator-opt-in, merged into
            # global_settings only on UI settings-save, seeded from the
            # api_engine_defaults catalog in web_server.py (the source of truth
            # for shape/defaults). Every reader safe-defaults the absent key
            # (cinema/phases/motion_render.py _get_storyboard_mode,
            # phase_c_ffmpeg.py).
        },
    }


def _normalize_take_list(takes: Any, kind: str) -> tuple[list[dict], bool]:
    changed = False
    normalized: list[dict] = []

    if not isinstance(takes, list):
        return [], takes not in (None, [])

    seen_ids: set[str] = set()
    for take in takes:
        if not isinstance(take, dict):
            changed = True
            continue

        take_copy = dict(take)
        take_id = take_copy.get("id")
        if not take_id or take_id in seen_ids:
            take_copy["id"] = f"take_{new_id()}"
            changed = True
        seen_ids.add(take_copy["id"])

        if take_copy.get("kind") != kind:
            take_copy["kind"] = kind
            changed = True

        if "path" not in take_copy:
            take_copy["path"] = ""
            changed = True
        if "status" not in take_copy:
            take_copy["status"] = "generated"
            changed = True
        if "source_take_id" not in take_copy:
            take_copy["source_take_id"] = ""
            changed = True
        if "created_at" not in take_copy:
            take_copy["created_at"] = _now_iso()
            changed = True
        if not isinstance(take_copy.get("metadata"), dict):
            take_copy["metadata"] = {}
            changed = True

        normalized.append(take_copy)

    return normalized, changed


def normalize_shot_schema(
    shot: Any,
    *,
    scene_id: str,
    shot_index: int,
    seen_ids: set[str],
) -> bool:
    changed = False
    if not isinstance(shot, dict):
        return False

    proposed_id = shot.get("id")
    if not proposed_id or proposed_id in seen_ids:
        shot["id"] = f"shot_{scene_id}_{shot_index}"
        changed = True
    seen_ids.add(shot["id"])

    defaults = {
        "prompt": "",
        "camera": "zoom_in_slow",
        "visual_effect": "cinematic_glow",
        "target_api": "AUTO",
        "scene_foley": "",
        "characters_in_frame": [],
        "primary_character": "",
        "action_context": "",
        "generated_image": "",
        "generated_video": "",
        "plan_rejection_reason": "",
        "diagnostics": [],
        "intent_notes": "",
        "negative_constraints": "blur, distort, deformed face, identity drift, off-model face, broken anatomy",
        "continuity_constraints": "",
    }
    for key, value in defaults.items():
        if key not in shot:
            shot[key] = value[:] if isinstance(value, list) else value
            changed = True

    if not isinstance(shot.get("characters_in_frame"), list):
        shot["characters_in_frame"] = []
        changed = True
    if not isinstance(shot.get("diagnostics"), list):
        shot["diagnostics"] = []
        changed = True

    if "plan_status" not in shot:
        if shot.get("approved") is True:
            shot["plan_status"] = "approved"
        elif shot.get("approved") is False:
            shot["plan_status"] = "rejected"
        else:
            shot["plan_status"] = "pending_review"
        changed = True

    keyframe_takes, keyframe_changed = _normalize_take_list(shot.get("keyframe_takes"), "keyframe")
    motion_takes, motion_changed = _normalize_take_list(shot.get("motion_takes"), "motion")
    postprocess_takes, postprocess_changed = _normalize_take_list(shot.get("postprocess_variants"), "postprocess")
    # Performance takes — new in PERFORMANCE_CAPTURE_HANDOFF. Same normalize shape.
    performance_takes, performance_changed = _normalize_take_list(shot.get("performance_takes"), "performance")
    if keyframe_changed or shot.get("keyframe_takes") is None:
        shot["keyframe_takes"] = keyframe_takes
        changed = True
    else:
        shot["keyframe_takes"] = keyframe_takes
    if motion_changed or shot.get("motion_takes") is None:
        shot["motion_takes"] = motion_takes
        changed = True
    else:
        shot["motion_takes"] = motion_takes
    if postprocess_changed or shot.get("postprocess_variants") is None:
        shot["postprocess_variants"] = postprocess_takes
        changed = True
    else:
        shot["postprocess_variants"] = postprocess_takes
    if performance_changed or shot.get("performance_takes") is None:
        shot["performance_takes"] = performance_takes
        changed = True
    else:
        shot["performance_takes"] = performance_takes

    # Migrate legacy generated outputs into additive take history.
    if shot.get("generated_image") and not shot["keyframe_takes"]:
        legacy_take = make_take("keyframe", path=shot["generated_image"], status="legacy_migrated")
        shot["keyframe_takes"].append(legacy_take)
        changed = True

    if shot.get("generated_video") and not shot["motion_takes"]:
        source_take_id = shot.get("approved_keyframe_take_id") or (
            shot["keyframe_takes"][0]["id"] if shot["keyframe_takes"] else ""
        )
        legacy_take = make_take(
            "motion",
            path=shot["generated_video"],
            source_take_id=source_take_id,
            status="legacy_migrated",
        )
        shot["motion_takes"].append(legacy_take)
        changed = True

    for approval_field in (
        "approved_keyframe_take_id",
        "approved_motion_take_id",
        "approved_final_take_id",
        "approved_performance_take_id",   # new field, performance capture
    ):
        if approval_field not in shot:
            shot[approval_field] = ""
            changed = True

    # New string fields from the performance-capture handoff. Add only if missing.
    for str_field in ("performance_engine", "driving_video_path"):
        if str_field not in shot:
            shot[str_field] = ""
            changed = True

    if not shot["approved_keyframe_take_id"] and shot["keyframe_takes"] and shot.get("approved") is True:
        shot["approved_keyframe_take_id"] = shot["keyframe_takes"][-1]["id"]
        changed = True

    if not shot["approved_motion_take_id"] and shot["motion_takes"] and shot.get("approved") is True:
        shot["approved_motion_take_id"] = shot["motion_takes"][-1]["id"]
        changed = True

    if not shot["approved_final_take_id"]:
        if shot["postprocess_variants"] and shot.get("approved") is True:
            shot["approved_final_take_id"] = shot["postprocess_variants"][-1]["id"]
            changed = True
        elif shot["motion_takes"] and shot.get("approved") is True:
            shot["approved_final_take_id"] = shot["motion_takes"][-1]["id"]
            changed = True

    return changed


# Map retired / invalid Anthropic model ids that may be persisted in
# project records' creative_llm setting to their current replacements.
# Applied read-time by normalize_project_schema so records converge on
# next save without requiring a bulk migration script.
_RETIRED_CREATIVE_LLM_IDS = {
    # 618a6b3 swapped live defaults; records persisted pre-swap 404 after 2026-06-15
    "claude-sonnet-4-20250514": "claude-sonnet-4-6",
    # stale BE creative_llm_options value (web_server.py catalog) — never a valid raw API id
    "claude-sonnet": "claude-sonnet-4-6",
}


def normalize_project_schema(project: Optional[dict]) -> bool:
    if not project:
        return False

    changed = False
    if "characters" not in project or not isinstance(project["characters"], list):
        project["characters"] = []
        changed = True
    if "locations" not in project or not isinstance(project["locations"], list):
        project["locations"] = []
        changed = True
    if "scenes" not in project or not isinstance(project["scenes"], list):
        project["scenes"] = []
        changed = True

    settings = project.setdefault("global_settings", {})
    if not isinstance(settings, dict):
        project["global_settings"] = {}
        settings = project["global_settings"]
        changed = True

    # One-time schema migration: drop legacy VBench-pipeline keys that
    # were excised in commit cda5022. Older project.json files on disk
    # still carry these from the pre-pivot make_project default — strip
    # them so files converge to the current schema on next save.
    for legacy_key in (
        "vbench_overall_threshold",       # 9a917b2
        "temporal_flicker_tolerance",     # this commit
        "regression_sensitivity",         # this commit
    ):
        if legacy_key in settings:
            settings.pop(legacy_key, None)
            changed = True

    # Read-time migration: remap retired/invalid creative_llm model ids so
    # projects persisted before 618a6b3 (or with the stale BE catalog value
    # "claude-sonnet") resolve to a valid API id before the 2026-06-15
    # retirement of claude-sonnet-4-20250514 causes 404s in production.
    _creative = settings.get("creative_llm")
    if isinstance(_creative, str) and _creative in _RETIRED_CREATIVE_LLM_IDS:
        settings["creative_llm"] = _RETIRED_CREATIVE_LLM_IDS[_creative]
        changed = True

    seen_shot_ids: set[str] = set()
    for scene_index, scene in enumerate(project["scenes"]):
        if not isinstance(scene, dict):
            continue
        if scene.get("order") != scene_index:
            scene["order"] = scene_index
            changed = True
        shots = scene.get("shots")
        if not isinstance(shots, list):
            scene["shots"] = []
            shots = scene["shots"]
            changed = True
        if scene.get("num_shots") != len(shots):
            scene["num_shots"] = len(shots)
            changed = True
        for shot_index, shot in enumerate(shots):
            if normalize_shot_schema(
                shot,
                scene_id=scene.get("id", f"scene_{scene_index}"),
                shot_index=shot_index,
                seen_ids=seen_shot_ids,
            ):
                changed = True

    return changed


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def create_project(name: str) -> dict:
    _ensure_projects_dir()
    project = make_project(name)
    pid = project["id"]
    _ensure_project_dir(pid)
    os.makedirs(os.path.join(_project_dir(pid), "characters"), exist_ok=True)
    os.makedirs(os.path.join(_project_dir(pid), "locations"), exist_ok=True)
    os.makedirs(os.path.join(_project_dir(pid), "exports"), exist_ok=True)
    os.makedirs(os.path.join(_project_dir(pid), "temp"), exist_ok=True)
    os.makedirs(os.path.join(_project_dir(pid), "shots"), exist_ok=True)
    save_project(project)
    print(f"🎬 Created project '{name}' → projects/{pid}/")
    return project


def _validate_project(project: dict, context: str) -> None:
    """Pydantic validation pass.

    Warn-only by default (Session 8 contract). Set CINEMA_STRICT_SCHEMA=1
    (or "true" / "yes" / "TRUE") in the environment to raise ValidationError
    instead of warning.  This is the Session 10 P1-3 part 2 escalation path:
    operators can opt in to strict validation in production once confident no
    warnings are firing.

    Args:
        project: Raw project dict (after normalize_project_schema on load).
        context: Human-readable label for log messages (e.g. "save_project").
    """
    strict = os.environ.get("CINEMA_STRICT_SCHEMA", "").strip() in (
        "1", "true", "TRUE", "yes"
    )
    try:
        Project.model_validate(project)
    except ValidationError as e:
        if strict:
            raise  # let it propagate; save_project / load_project callers crash
        logger.warning(
            "project schema validation failed",
            extra={
                "context": context,
                "project_id": project.get("id"),
                "errors": e.errors()[:5],  # cap at 5 to keep log size bounded
            },
        )
    except Exception as e:
        if strict:
            raise  # belt-and-suspenders strict propagation
        # Belt-and-suspenders: the brief's "warn-only" contract is broader
        # than ValidationError. A TypeError / RecursionError / etc from a
        # malformed dict must NEVER propagate into save_project or
        # load_project — those callers (web_server.py, cinema_pipeline.py)
        # would crash on what's supposed to be a passive safety net.
        logger.warning(
            "project schema validation crashed (non-ValidationError)",
            extra={
                "context": context,
                "project_id": project.get("id") if isinstance(project, dict) else None,
                "error": repr(e),
            },
        )


def save_project(project: dict, timeout: float = 10) -> None:
    """
    Atomically save project JSON.
    Writes to a temp file first, then replaces the target — prevents
    half-written files if the process crashes mid-write.
    Uses per-project file lock to prevent concurrent-write corruption.
    """
    _validate_project(project, "save_project")
    with _acquire_project_lock(project["id"], timeout):
        _save_project_unlocked(project)


def load_project(project_id: str, timeout: float = 10) -> Optional[dict]:
    """Load project JSON with file-lock protection against concurrent writes."""
    with _acquire_project_lock(project_id, timeout):
        project = _load_project_unlocked(project_id)
        if project is None:
            return None
        if normalize_project_schema(project):
            _save_project_unlocked(project)
        _validate_project(project, "load_project")
        return project


def mutate_project(
    project_id: str,
    mutator: Callable[[dict], Any],
    timeout: float = 10,
    snapshot: Optional[dict] = None,
):
    """
    Atomically apply a read-modify-write mutation under a single project lock.

    The callback receives the latest project snapshot from disk. It may return a
    plain value or a MutationResult(value, save=bool) to skip saving unchanged
    state.
    """
    latest_project: Optional[dict] = None
    result_value: Any = None
    save_project_state = True

    with _acquire_project_lock(project_id, timeout):
        latest_project = _load_project_unlocked(project_id)
        if latest_project is None:
            return None
        normalized = normalize_project_schema(latest_project)

        result = mutator(latest_project)
        if isinstance(result, MutationResult):
            result_value = result.value
            save_project_state = result.save
        else:
            result_value = result

        if save_project_state or normalized:
            _save_project_unlocked(latest_project)

    _sync_project_snapshot(snapshot, latest_project)
    return result_value


def delete_project(project_id: str, timeout: float = 10) -> bool:
    d = _project_dir(project_id)
    if os.path.exists(d):
        with _acquire_project_lock(project_id, timeout):
            if os.path.exists(d):
                shutil.rmtree(d)
                return True
    return False


def list_projects() -> List[dict]:
    """List all projects, sorted by most-recently-modified first.

    Recent-first ordering closes Val#2 U1 (operator-validation #2): without
    a sort, the API returned projects in filesystem-listing order (roughly
    creation order on most platforms), so the "Recent Productions" heading
    on the landing page rendered ancient pytest fixtures alongside live
    work. Sort key is the project.json mtime — captures both "created"
    and "edited" recency cheaply via a single os.stat per project.

    Performance note: this still load_project()s each entry (full JSON
    parse). At N≈2000 projects, ~200-500ms total on local disk; tolerable
    for a landing-page fetch. If the page count grows past ~10k, a
    streaming-pagination API would be the next step.
    """
    _ensure_projects_dir()
    entries = []
    for pid in os.listdir(PROJECTS_DIR):
        project_dir = os.path.join(PROJECTS_DIR, pid)
        if not os.path.isdir(project_dir) or pid.startswith("."):
            continue
        # Read mtime BEFORE load_project so a malformed project.json
        # doesn't lose its mtime (the entry just skips).
        try:
            mtime = os.path.getmtime(os.path.join(project_dir, "project.json"))
        except OSError:
            # project.json missing or unreadable — skip entirely.
            continue
        p = load_project(pid)
        if p:
            entries.append((mtime, {"id": p["id"], "name": p["name"]}))
    # Sort by mtime DESC (newest first). Stable: ties preserve filesystem
    # iteration order.
    entries.sort(key=lambda e: e[0], reverse=True)
    return [entry for _, entry in entries]


# ---------------------------------------------------------------------------
# Project mutation helpers
# ---------------------------------------------------------------------------

def add_character(project: dict, character: dict, timeout: float = 10) -> dict:
    # P1-3 migration template (S10 + part 9 Variant 1) — outer boundary
    # validate at function entry + inner mutator-scope validate under the
    # per-project lock. Catches malformed input at boundary (raises in
    # CINEMA_STRICT_SCHEMA mode); inner validate handles race between
    # outer validation and lock acquisition. Simplified: append-only, no
    # typed-iterate-for-find needed.
    # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 this).
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary validate

    pid = project["id"]

    def _mutate(latest: dict):
        _Project.model_validate(latest)  # inner mutator-scope validate
        latest["characters"].append(character)
        return character

    result = mutate_project(pid, _mutate, timeout=timeout, snapshot=project)
    if result is None:
        raise FileNotFoundError(f"Project '{pid}' not found")
    return result


def remove_character(project: dict, char_id: str, timeout: float = 10) -> bool:
    # P1-3 migration template (S10 + part 9 Variant 1) — outer boundary
    # validate at function entry + inner mutator-scope validate under the
    # per-project lock. Full: typed-iterate-for-find + raw-dict-by-index
    # for kept values (value-preserving filter on c.id != char_id).
    # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 this).
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary validate

    def _mutate(latest: dict):
        latest_typed = _Project.model_validate(latest)  # inner mutator-scope validate
        before = len(latest_typed.characters)
        latest["characters"] = [
            latest["characters"][i]
            for i, c in enumerate(latest_typed.characters)
            if c.id != char_id
        ]
        changed = len(latest["characters"]) < before
        return MutationResult(changed, save=changed)

    result = mutate_project(project["id"], _mutate, timeout=timeout, snapshot=project)
    return bool(result)


def get_character(project: dict, char_id: str) -> Optional[dict]:
    # P1-3 migration template (S10): validate at boundary, then iterate
    # typed for the id comparison. Return type stays Optional[dict] —
    # callers (domain/character_manager.py:343/380/418/429,
    # cinema/* code) use dict-attribute access on the return; tests
    # use `is c` identity comparison. We return the original dict
    # reference (project["characters"][i]), not a fresh model_dump —
    # full caller-side migration would be a separate cycle-10+ slice.
    # See docs/MIGRATION-PATTERN-pydantic-caller.md for the full recipe.
    from domain.models import Project as _Project
    project_typed = _Project.model_validate(project)
    for i, c in enumerate(project_typed.characters):
        if c.id == char_id:
            return project["characters"][i]
    return None


def add_object(project: dict, obj: dict, timeout: float = 10) -> dict:
    """Add a product/prop object to the project. Mirrors add_character/add_location."""
    # P1-3 migration template (S10 + part 9 Variant 1) — outer boundary
    # validate at function entry + inner mutator-scope validate under the
    # per-project lock. Simplified: setdefault+append only, no
    # typed-iterate-for-find needed.
    # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 this).
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary validate

    pid = project["id"]

    def _mutate(latest: dict):
        _Project.model_validate(latest)  # inner mutator-scope validate
        latest.setdefault("objects", []).append(obj)
        return obj

    result = mutate_project(pid, _mutate, timeout=timeout, snapshot=project)
    if result is None:
        raise FileNotFoundError(f"Project '{pid}' not found")
    return result


def remove_object(project: dict, obj_id: str, timeout: float = 10) -> bool:
    # P1-3 migration template (S10 + part 9 Variant 1) — outer boundary
    # validate at function entry + inner mutator-scope validate under the
    # per-project lock. Simplified-filter: objects is an extra="allow" field
    # (not a typed List[Object]), so items are raw dicts; use dict-style
    # o["id"] comparison rather than typed-attribute iteration. Race
    # protection from inner validate is preserved regardless.
    # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 this).
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary validate

    def _mutate(latest: dict):
        _Project.model_validate(latest)  # inner mutator-scope validate
        latest.setdefault("objects", [])
        before = len(latest["objects"])
        latest["objects"] = [o for o in latest["objects"] if o["id"] != obj_id]
        changed = len(latest["objects"]) < before
        return MutationResult(changed, save=changed)

    result = mutate_project(project["id"], _mutate, timeout=timeout, snapshot=project)
    return bool(result)


def get_object(project: dict, obj_id: str) -> Optional[dict]:
    for o in project.get("objects", []):
        if o["id"] == obj_id:
            return o
    return None


def add_location(project: dict, location: dict, timeout: float = 10) -> dict:
    # P1-3 migration template (S10 + part 9 Variant 1) — outer boundary
    # validate at function entry + inner mutator-scope validate under the
    # per-project lock. Simplified: append-only, no typed-iterate-for-find
    # needed.
    # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 this).
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary validate

    pid = project["id"]

    def _mutate(latest: dict):
        _Project.model_validate(latest)  # inner mutator-scope validate
        latest["locations"].append(location)
        return location

    result = mutate_project(pid, _mutate, timeout=timeout, snapshot=project)
    if result is None:
        raise FileNotFoundError(f"Project '{pid}' not found")
    return result


def remove_location(project: dict, loc_id: str, timeout: float = 10) -> bool:
    # P1-3 migration template (S10 + part 9 Variant 1) — outer boundary
    # validate at function entry + inner mutator-scope validate under the
    # per-project lock. Full: typed-iterate-for-find + raw-dict-by-index
    # for kept values (value-preserving filter on l.id != loc_id).
    # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 this).
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary validate

    def _mutate(latest: dict):
        latest_typed = _Project.model_validate(latest)  # inner mutator-scope validate
        before = len(latest_typed.locations)
        latest["locations"] = [
            latest["locations"][i]
            for i, l in enumerate(latest_typed.locations)
            if l.id != loc_id
        ]
        changed = len(latest["locations"]) < before
        return MutationResult(changed, save=changed)

    result = mutate_project(project["id"], _mutate, timeout=timeout, snapshot=project)
    return bool(result)


def get_location(project: dict, loc_id: str) -> Optional[dict]:
    # P1-3 migration template (S10): parallel to get_character above.
    # Return type stays Optional[dict] for caller-identity preservation
    # (domain/location_manager.py callers + tests use `is loc`). See
    # the get_character migration block + docs/MIGRATION-PATTERN-
    # pydantic-caller.md for the full recipe.
    from domain.models import Project as _Project
    project_typed = _Project.model_validate(project)
    for i, l in enumerate(project_typed.locations):
        if l.id == loc_id:
            return project["locations"][i]
    return None


def add_scene(project: dict, scene: dict, timeout: float = 10) -> dict:
    # P1-3 migration template (S10 + part 9 Variant 1) — outer boundary
    # validate at function entry + inner mutator-scope validate under the
    # per-project lock. Simplified: append-only + len() for order, no
    # typed-iterate-for-find needed.
    # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 this).
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary validate

    pid = project["id"]

    def _mutate(latest: dict):
        _Project.model_validate(latest)  # inner mutator-scope validate
        scene["order"] = len(latest["scenes"])
        latest["scenes"].append(scene)
        return scene

    result = mutate_project(pid, _mutate, timeout=timeout, snapshot=project)
    if result is None:
        raise FileNotFoundError(f"Project '{pid}' not found")
    return result


def update_scene(project: dict, scene_id: str, updates: dict, timeout: float = 10) -> Optional[dict]:
    # P1-3 migration template (S10 + part 9 Variant 1) — outer boundary
    # validate at function entry + inner mutator-scope validate under the
    # per-project lock. Full: typed-iterate-for-find (scene.id check) +
    # dict-mutate-in-place at the matched index under the lock.
    # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 this).
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary validate

    def _mutate(latest: dict):
        latest_typed = _Project.model_validate(latest)  # inner mutator-scope validate
        for i, scene in enumerate(latest_typed.scenes):
            if scene.id == scene_id:
                latest["scenes"][i].update(updates)
                return latest["scenes"][i]
        return MutationResult(None, save=False)

    return mutate_project(project["id"], _mutate, timeout=timeout, snapshot=project)


def remove_scene(project: dict, scene_id: str, timeout: float = 10) -> bool:
    # P1-3 migration template (S10 + part 9 Variant 1) — outer boundary
    # validate at function entry + inner mutator-scope validate under the
    # per-project lock. Full + post-filter reorder: typed-iterate-for-find
    # + raw-dict-by-index for kept values (value-preserving filter on
    # scene.id != scene_id), then re-number order via dict-write under lock.
    # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 this).
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary validate

    def _mutate(latest: dict):
        latest_typed = _Project.model_validate(latest)  # inner mutator-scope validate
        before = len(latest_typed.scenes)
        latest["scenes"] = [
            latest["scenes"][i]
            for i, scene in enumerate(latest_typed.scenes)
            if scene.id != scene_id
        ]
        changed = len(latest["scenes"]) < before
        if not changed:
            return MutationResult(False, save=False)
        for index, scene in enumerate(latest["scenes"]):
            scene["order"] = index
        return True

    result = mutate_project(project["id"], _mutate, timeout=timeout, snapshot=project)
    return bool(result)


def reorder_scenes(project: dict, scene_ids: list[str], timeout: float = 10) -> None:
    # P1-3 migration template (S10 + part 9 Variant 1) — outer boundary
    # validate at function entry + inner mutator-scope validate under the
    # per-project lock. Full + dict-build-by-id: typed-iterate for .id key
    # extraction; raw-dict-by-index for the id_to_scene dict values.
    # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
    # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 this).
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary validate

    def _mutate(latest: dict):
        latest_typed = _Project.model_validate(latest)  # inner mutator-scope validate
        id_to_scene = {
            scene.id: latest["scenes"][i]
            for i, scene in enumerate(latest_typed.scenes)
        }
        reordered = []
        for index, scene_id in enumerate(scene_ids):
            if scene_id in id_to_scene:
                scene = id_to_scene[scene_id]
                scene["order"] = index
                reordered.append(scene)
        latest["scenes"] = reordered
        return MutationResult(None, save=True)

    mutate_project(project["id"], _mutate, timeout=timeout, snapshot=project)


def get_project_dir(project_id: str) -> str:
    return _project_dir(project_id)


# ---------------------------------------------------------------------------
# Shot-as-Atomic-Unit Architecture
# ---------------------------------------------------------------------------

def _shot_dir(project_id: str, shot_id: str) -> str:
    return os.path.join(_project_dir(project_id), "shots", shot_id)


def ensure_shot_package(project_id: str, shot_id: str) -> str:
    """
    Create the canonical directory structure for a shot package:

        projects/{project_id}/shots/{shot_id}/
            ├── inputs/
            └── outputs/

    Returns the shot directory path.
    """
    shot_path = _shot_dir(project_id, shot_id)
    os.makedirs(os.path.join(shot_path, "inputs"), exist_ok=True)
    os.makedirs(os.path.join(shot_path, "outputs"), exist_ok=True)
    return shot_path


def save_shot_spec(project_id: str, shot_id: str, shot_spec: dict) -> str:
    """
    Save a shot specification dict as JSON to the shot package.

    shot_spec should include keys such as:
        prompt, camera, visual_effect, target_api,
        characters_in_frame, seed, model_version, timestamp

    A 'timestamp' field is added automatically if not already present.
    Returns the path to the written shot.json file.
    """
    shot_path = ensure_shot_package(project_id, shot_id)
    if "timestamp" not in shot_spec:
        # Timezone-aware UTC (datetime.utcnow() is deprecated 3.12+); same
        # +00:00 → Z suffix substitution as _now_iso() above for visual parity.
        shot_spec["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    spec_file = os.path.join(shot_path, "shot.json")
    with open(spec_file, "w", encoding="utf-8") as f:
        json.dump(shot_spec, f, indent=2, ensure_ascii=False)
    return spec_file


def save_shot_output(
    project_id: str,
    shot_id: str,
    output_type: str,
    file_path: str,
) -> str:
    """
    Copy an output file into the shot package's outputs/ directory.

    The file is stored as  outputs/{output_type}{ext}  where ext is
    preserved from the original file_path.

    output_type examples: "keyframe", "video", "video_post", "audio"

    Returns the new file path inside the shot package.
    """
    shot_path = ensure_shot_package(project_id, shot_id)
    _, ext = os.path.splitext(file_path)
    dest = os.path.join(shot_path, "outputs", f"{output_type}{ext}")
    shutil.copy2(file_path, dest)
    return dest


def save_shot_metrics(project_id: str, shot_id: str, metrics: dict) -> str:
    """
    Save evaluation / cost metrics for a shot.

    Writes metrics dict as JSON to outputs/metrics.json.
    metrics can include: vbench_scores, identity_scores,
    coherence_scores, cost, etc.

    Returns the path to the written metrics.json file.
    """
    shot_path = ensure_shot_package(project_id, shot_id)
    metrics_file = os.path.join(shot_path, "outputs", "metrics.json")
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    return metrics_file


def get_shot_package(project_id: str, shot_id: str) -> Optional[dict]:
    """
    Return a manifest of all files currently in a shot package.

    Returns a dict shaped like:
        {
            "shot_id": "...",
            "shot_dir": "...",
            "spec": "projects/.../shot.json" or None,
            "inputs": {"reference": "path", "pose": "path", ...},
            "outputs": {"keyframe": "path", "video": "path",
                        "metrics": "path", ...},
        }

    Returns None if the shot directory does not exist.
    """
    shot_path = _shot_dir(project_id, shot_id)
    if not os.path.isdir(shot_path):
        return None

    package: Dict[str, object] = {
        "shot_id": shot_id,
        "shot_dir": shot_path,
        "spec": None,
        "inputs": {},
        "outputs": {},
    }

    spec_path = os.path.join(shot_path, "shot.json")
    if os.path.isfile(spec_path):
        package["spec"] = spec_path

    inputs_dir = os.path.join(shot_path, "inputs")
    if os.path.isdir(inputs_dir):
        for fname in os.listdir(inputs_dir):
            key = os.path.splitext(fname)[0]
            package["inputs"][key] = os.path.join(inputs_dir, fname)

    outputs_dir = os.path.join(shot_path, "outputs")
    if os.path.isdir(outputs_dir):
        for fname in os.listdir(outputs_dir):
            key = os.path.splitext(fname)[0]
            package["outputs"][key] = os.path.join(outputs_dir, fname)

    return package


def list_shot_packages(project_id: str) -> List[str]:
    """
    Return a sorted list of shot_ids that have packages under
    projects/{project_id}/shots/.
    """
    shots_root = os.path.join(_project_dir(project_id), "shots")
    if not os.path.isdir(shots_root):
        return []
    return sorted(
        d for d in os.listdir(shots_root)
        if os.path.isdir(os.path.join(shots_root, d))
    )
