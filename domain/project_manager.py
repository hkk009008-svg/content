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
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional, List, Dict

from filelock import FileLock, Timeout
from pydantic import ValidationError

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
    return datetime.utcnow().isoformat() + "Z"


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
) -> dict:
    return {
        "id": f"char_{new_id()}",
        "name": name,
        "description": description,
        "reference_images": reference_images or [],
        "canonical_reference": "",
        "voice_id": voice_id,
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
            # Step-3 (2026-05-24): N=8 best-of per-batch parallelism. 1 = sequential
            # (historic behavior); up to 4 = concurrent workers on the same RunPod
            # pod, overlapping submit/poll/download cycles. ComfyUI still serializes
            # GPU work per pod.
            "max_quality_parallel_workers": 1,
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
    """Pydantic validation pass; logs warnings on schema drift but does NOT
    fail the operation — permissive mode per brief design (start with
    extra='allow', warn-only).  Session 9 may add a CINEMA_STRICT_SCHEMA
    env flag to raise instead of warn.

    Args:
        project: Raw project dict (after normalize_project_schema on load).
        context: Human-readable label for log messages (e.g. "save_project").
    """
    try:
        Project.model_validate(project)
    except ValidationError as e:
        logger.warning(
            "project schema validation failed",
            extra={
                "context": context,
                "project_id": project.get("id"),
                "errors": e.errors()[:5],  # cap at 5 to keep log size bounded
            },
        )
    except Exception as e:
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
    _ensure_projects_dir()
    projects = []
    for pid in os.listdir(PROJECTS_DIR):
        if not os.path.isdir(os.path.join(PROJECTS_DIR, pid)) or pid.startswith("."):
            continue
        p = load_project(pid)
        if p:
            projects.append({"id": p["id"], "name": p["name"]})
    return projects


# ---------------------------------------------------------------------------
# Project mutation helpers
# ---------------------------------------------------------------------------

def add_character(project: dict, character: dict, timeout: float = 10) -> dict:
    pid = project["id"]

    def _mutate(latest: dict):
        latest["characters"].append(character)
        return character

    result = mutate_project(pid, _mutate, timeout=timeout, snapshot=project)
    if result is None:
        raise FileNotFoundError(f"Project '{pid}' not found")
    return result


def remove_character(project: dict, char_id: str, timeout: float = 10) -> bool:
    def _mutate(latest: dict):
        before = len(latest["characters"])
        latest["characters"] = [c for c in latest["characters"] if c["id"] != char_id]
        changed = len(latest["characters"]) < before
        return MutationResult(changed, save=changed)

    result = mutate_project(project["id"], _mutate, timeout=timeout, snapshot=project)
    return bool(result)


def get_character(project: dict, char_id: str) -> Optional[dict]:
    for c in project["characters"]:
        if c["id"] == char_id:
            return c
    return None


def add_object(project: dict, obj: dict, timeout: float = 10) -> dict:
    """Add a product/prop object to the project. Mirrors add_character/add_location."""
    pid = project["id"]

    def _mutate(latest: dict):
        latest.setdefault("objects", []).append(obj)
        return obj

    result = mutate_project(pid, _mutate, timeout=timeout, snapshot=project)
    if result is None:
        raise FileNotFoundError(f"Project '{pid}' not found")
    return result


def remove_object(project: dict, obj_id: str, timeout: float = 10) -> bool:
    def _mutate(latest: dict):
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
    pid = project["id"]

    def _mutate(latest: dict):
        latest["locations"].append(location)
        return location

    result = mutate_project(pid, _mutate, timeout=timeout, snapshot=project)
    if result is None:
        raise FileNotFoundError(f"Project '{pid}' not found")
    return result


def remove_location(project: dict, loc_id: str, timeout: float = 10) -> bool:
    def _mutate(latest: dict):
        before = len(latest["locations"])
        latest["locations"] = [l for l in latest["locations"] if l["id"] != loc_id]
        changed = len(latest["locations"]) < before
        return MutationResult(changed, save=changed)

    result = mutate_project(project["id"], _mutate, timeout=timeout, snapshot=project)
    return bool(result)


def get_location(project: dict, loc_id: str) -> Optional[dict]:
    for l in project["locations"]:
        if l["id"] == loc_id:
            return l
    return None


def add_scene(project: dict, scene: dict, timeout: float = 10) -> dict:
    pid = project["id"]

    def _mutate(latest: dict):
        scene["order"] = len(latest["scenes"])
        latest["scenes"].append(scene)
        return scene

    result = mutate_project(pid, _mutate, timeout=timeout, snapshot=project)
    if result is None:
        raise FileNotFoundError(f"Project '{pid}' not found")
    return result


def update_scene(project: dict, scene_id: str, updates: dict, timeout: float = 10) -> Optional[dict]:
    def _mutate(latest: dict):
        for scene in latest["scenes"]:
            if scene["id"] == scene_id:
                scene.update(updates)
                return scene
        return MutationResult(None, save=False)

    return mutate_project(project["id"], _mutate, timeout=timeout, snapshot=project)


def remove_scene(project: dict, scene_id: str, timeout: float = 10) -> bool:
    def _mutate(latest: dict):
        before = len(latest["scenes"])
        latest["scenes"] = [scene for scene in latest["scenes"] if scene["id"] != scene_id]
        changed = len(latest["scenes"]) < before
        if not changed:
            return MutationResult(False, save=False)
        for index, scene in enumerate(latest["scenes"]):
            scene["order"] = index
        return True

    result = mutate_project(project["id"], _mutate, timeout=timeout, snapshot=project)
    return bool(result)


def reorder_scenes(project: dict, scene_ids: list[str], timeout: float = 10) -> None:
    def _mutate(latest: dict):
        id_to_scene = {scene["id"]: scene for scene in latest["scenes"]}
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
        shot_spec["timestamp"] = datetime.utcnow().isoformat() + "Z"
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
