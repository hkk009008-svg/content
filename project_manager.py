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
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict

from filelock import FileLock

PROJECTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects")


def _ensure_projects_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def _project_dir(project_id: str) -> str:
    return os.path.join(PROJECTS_DIR, project_id)


def _project_file(project_id: str) -> str:
    return os.path.join(_project_dir(project_id), "project.json")


def _project_lock_path(project_id: str) -> str:
    return os.path.join(_project_dir(project_id), "project.lock")


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
    os.makedirs(_project_dir(project_id), exist_ok=True)
    lock = FileLock(_project_lock_path(project_id), timeout=timeout)
    with lock:
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
        },
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def create_project(name: str) -> dict:
    _ensure_projects_dir()
    project = make_project(name)
    pid = project["id"]
    os.makedirs(_project_dir(pid), exist_ok=True)
    os.makedirs(os.path.join(_project_dir(pid), "characters"), exist_ok=True)
    os.makedirs(os.path.join(_project_dir(pid), "locations"), exist_ok=True)
    os.makedirs(os.path.join(_project_dir(pid), "exports"), exist_ok=True)
    os.makedirs(os.path.join(_project_dir(pid), "temp"), exist_ok=True)
    save_project(project)
    print(f"🎬 Created project '{name}' → projects/{pid}/")
    return project


def save_project(project: dict) -> None:
    """
    Atomically save project JSON.
    Writes to a temp file first, then replaces the target — prevents
    half-written files if the process crashes mid-write.
    Uses per-project file lock to prevent concurrent-write corruption.
    """
    pid = project["id"]
    _ensure_projects_dir()
    os.makedirs(_project_dir(pid), exist_ok=True)

    target = _project_file(pid)
    lock = FileLock(_project_lock_path(pid), timeout=10)
    with lock:
        fd, tmp_path = tempfile.mkstemp(
            suffix=".json.tmp", dir=_project_dir(pid)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(project, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, target)  # atomic on POSIX
        except BaseException:
            # Clean up temp file on any failure
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise


def load_project(project_id: str) -> Optional[dict]:
    """Load project JSON with file-lock protection against concurrent writes."""
    path = _project_file(project_id)
    if not os.path.exists(path):
        return None
    lock = FileLock(_project_lock_path(project_id), timeout=10)
    with lock:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def delete_project(project_id: str) -> bool:
    d = _project_dir(project_id)
    if os.path.exists(d):
        shutil.rmtree(d)
        return True
    return False


def list_projects() -> List[dict]:
    _ensure_projects_dir()
    projects = []
    for pid in os.listdir(PROJECTS_DIR):
        p = load_project(pid)
        if p:
            projects.append({"id": p["id"], "name": p["name"]})
    return projects


# ---------------------------------------------------------------------------
# Project mutation helpers
# ---------------------------------------------------------------------------

def add_character(project: dict, character: dict) -> dict:
    project["characters"].append(character)
    save_project(project)
    return character


def remove_character(project: dict, char_id: str) -> bool:
    before = len(project["characters"])
    project["characters"] = [c for c in project["characters"] if c["id"] != char_id]
    if len(project["characters"]) < before:
        save_project(project)
        return True
    return False


def get_character(project: dict, char_id: str) -> Optional[dict]:
    for c in project["characters"]:
        if c["id"] == char_id:
            return c
    return None


def add_location(project: dict, location: dict) -> dict:
    project["locations"].append(location)
    save_project(project)
    return location


def remove_location(project: dict, loc_id: str) -> bool:
    before = len(project["locations"])
    project["locations"] = [l for l in project["locations"] if l["id"] != loc_id]
    if len(project["locations"]) < before:
        save_project(project)
        return True
    return False


def get_location(project: dict, loc_id: str) -> Optional[dict]:
    for l in project["locations"]:
        if l["id"] == loc_id:
            return l
    return None


def add_scene(project: dict, scene: dict) -> dict:
    scene["order"] = len(project["scenes"])
    project["scenes"].append(scene)
    save_project(project)
    return scene


def update_scene(project: dict, scene_id: str, updates: dict) -> Optional[dict]:
    for s in project["scenes"]:
        if s["id"] == scene_id:
            s.update(updates)
            save_project(project)
            return s
    return None


def remove_scene(project: dict, scene_id: str) -> bool:
    before = len(project["scenes"])
    project["scenes"] = [s for s in project["scenes"] if s["id"] != scene_id]
    for i, s in enumerate(project["scenes"]):
        s["order"] = i
    if len(project["scenes"]) < before:
        save_project(project)
        return True
    return False


def reorder_scenes(project: dict, scene_ids: list[str]) -> None:
    id_to_scene = {s["id"]: s for s in project["scenes"]}
    reordered = []
    for i, sid in enumerate(scene_ids):
        if sid in id_to_scene:
            scene = id_to_scene[sid]
            scene["order"] = i
            reordered.append(scene)
    project["scenes"] = reordered
    save_project(project)


def get_project_dir(project_id: str) -> str:
    return _project_dir(project_id)
