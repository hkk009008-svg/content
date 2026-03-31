"""
Cinema Production Tool — Project Manager
Handles project CRUD, persistence, and data model definitions.
Projects are stored as JSON files under projects/<project_id>/.
"""

import os
import json
import uuid
import random
import shutil
import tempfile
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional, List, Dict

from filelock import FileLock, Timeout

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
) -> dict:
    return {
        "id": f"shot_{new_id()}",
        "prompt": prompt,
        "camera": camera,
        "visual_effect": visual_effect,
        "target_api": target_api,
        "scene_foley": scene_foley,
        "characters_in_frame": characters_in_frame or [],
        "primary_character": primary_character,
        "generated_image": "",
        "generated_video": "",
    }


def make_project(name: str) -> dict:
    return {
        "id": new_id(),
        "name": name,
        "characters": [],
        "locations": [],
        "scenes": [],
        "global_settings": {
            "aspect_ratio": "16:9",
            "music_mood": "suspense",
            "color_palette": "",
            "master_seed": random.randint(100000, 999999),
            "style_rules": {},
            "default_video_api": "AUTO",
            # V11 defaults
            "budget_limit_usd": 0,
            "cost_optimization": "quality_first",
            "vbench_overall_threshold": 0.60,
            "identity_strictness": 0.60,
            "temporal_flicker_tolerance": 0.85,
            "regression_sensitivity": 0.05,
            "creative_llm": "auto",
            "quality_judge_llm": "auto",
            "competitive_generation": True,
            "quality_cost_weight": 0.8,
            "adaptive_pulid": True,
            "coherence_check_enabled": True,
            "color_drift_sensitivity": 0.3,
        },
    }


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
    save_project(project)
    print(f"🎬 Created project '{name}' → projects/{pid}/")
    return project


def save_project(project: dict, timeout: float = 10) -> None:
    """
    Atomically save project JSON.
    Writes to a temp file first, then replaces the target — prevents
    half-written files if the process crashes mid-write.
    Uses per-project file lock to prevent concurrent-write corruption.
    """
    with _acquire_project_lock(project["id"], timeout):
        _save_project_unlocked(project)


def load_project(project_id: str, timeout: float = 10) -> Optional[dict]:
    """Load project JSON with file-lock protection against concurrent writes."""
    with _acquire_project_lock(project_id, timeout):
        return _load_project_unlocked(project_id)


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

        result = mutator(latest_project)
        if isinstance(result, MutationResult):
            result_value = result.value
            save_project_state = result.save
        else:
            result_value = result

        if save_project_state:
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
