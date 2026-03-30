"""
Cinema Production Tool — Flask Web Server
Dashboard API with SSE streaming for real-time generation progress.
Serves the React frontend and exposes all project/character/location/scene endpoints.
"""

import os
import warnings
from functools import wraps

# Suppress noisy warnings from google/urllib3 libraries
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", module="urllib3")
warnings.filterwarnings("ignore", category=UserWarning)

# Fix OpenMP libomp.dylib conflict (same as main.py)
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import json
import threading
import queue
from flask import Flask, request, jsonify, send_from_directory, Response, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

from project_manager import (
    MutationResult, ProjectLockError, create_project, load_project, delete_project,
    list_projects, mutate_project,
    add_character, remove_character, add_location, remove_location,
    add_scene, update_scene, remove_scene, reorder_scenes,
    make_character, make_location, make_scene, get_project_dir,
)
from character_manager import create_character_with_images, VOICE_POOL
from location_manager import create_location_with_images
from scene_decomposer import decompose_scene, update_scene_shots, CAMERA_MOTIONS, VISUAL_EFFECTS, TARGET_APIS, API_REGISTRY, MUSIC_MOODS
from dialogue_writer import generate_dialogue
from style_director import generate_style_rules
from cinema_pipeline import CinemaPipeline

app = Flask(__name__, static_folder="web/dist", static_url_path="")
CORS(app)

# SSE progress queues per project
_progress_queues: dict[str, queue.Queue] = {}
_running_pipelines: dict[str, CinemaPipeline] = {}
HTTP_PROJECT_TIMEOUT = 2.0

def _get_delivery_styles():
    """Get delivery styles with descriptions for the frontend."""
    try:
        from phase_b_audio import VOICE_DIRECTIONS
        return {k: v.get("description", k) for k, v in VOICE_DIRECTIONS.items()}
    except Exception:
        return {}


def _project_conflict_response(code: str, error: str):
    return jsonify({"code": code, "retryable": True, "error": error}), 409


def _project_locked_response(exc: ProjectLockError):
    return _project_conflict_response("project_locked", str(exc))


def _project_busy_response(pid: str):
    return _project_conflict_response(
        "project_busy",
        f"Project '{pid}' is busy with an active generation run. Retry shortly.",
    )


def _reject_if_project_busy(pid: str):
    if pid in _running_pipelines:
        return _project_busy_response(pid)
    return None


def _project_lock_guard(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ProjectLockError as exc:
            return _project_locked_response(exc)

    return wrapper


# ---------------------------------------------------------------------------
# Static Frontend
# ---------------------------------------------------------------------------

@app.route("/")
def serve_frontend():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# Configuration — exposed parameters for the UI
# ---------------------------------------------------------------------------

@app.route("/api/config", methods=["GET"])
def get_config():
    """Returns all controllable parameters for the UI panels."""
    return jsonify({
        "camera_motions": CAMERA_MOTIONS,
        "visual_effects": VISUAL_EFFECTS,
        "target_apis": TARGET_APIS,
        "api_registry": API_REGISTRY,
        "music_moods": MUSIC_MOODS,
        "voice_pool": VOICE_POOL,
        "delivery_styles": _get_delivery_styles(),
        "aspect_ratios": ["16:9", "9:16", "1:1", "21:9", "4:3"],
        "pacing_options": ["relaxed", "moderate", "calculated", "fast"],
        "mood_options": [
            "melancholic", "tense", "hopeful", "dark", "cinematic",
            "mysterious", "romantic", "energetic", "peaceful", "dramatic",
        ],
        "post_processing": {
            "face_swap": {"available": True, "description": "FaceFusion face-swap for 95%+ identity consistency"},
            "frame_interpolation": {"available": True, "description": "RIFE 4x interpolation (8fps → 24fps)"},
            "upscaling": {"available": True, "description": "Real-ESRGAN 2x upscale for 4K output"},
        },
        "continuity_options": {
            "img2img_denoise": {"min": 0.2, "max": 0.6, "default": 0.35, "description": "Lower = more similar to previous shot"},
            "identity_threshold": {"min": 0.4, "max": 0.8, "default": 0.55, "description": "Face similarity threshold for validation"},
            "ip_adapter_weight": {"min": 0.5, "max": 1.0, "default": 0.85, "description": "PuLID face-lock strength"},
        },
        "color_grade_presets": [
            "warm_cinema", "cool_noir", "vibrant", "desaturated",
            "golden_hour", "moonlight", "high_contrast", "pastel",
        ],
        "lip_sync_modes": ["auto", "overlay", "generation", "skip"],
        "api_engine_defaults": {
            "KLING_NATIVE": {
                "enabled": True, "duration": "5", "face_consistency": True,
                "storyboard_mode": False,
            },
            "SORA_NATIVE": {
                "enabled": True, "duration": 4, "resolution": "1080p",
            },
            "VEO_NATIVE": {
                "enabled": True, "duration": "6s", "generate_audio": False,
            },
            "LTX": {
                "enabled": True, "resolution": "1080p", "camera_motion_native": True,
            },
            "RUNWAY_GEN4": {
                "enabled": True, "duration": 10, "resolution": "1080p",
            },
        },
        # V11: dropdown options for new settings
        "cost_optimization_levels": [
            {"value": "quality_first", "label": "Quality First"},
            {"value": "balanced", "label": "Balanced"},
            {"value": "budget_conscious", "label": "Budget Conscious"},
        ],
        "creative_llm_options": [
            {"value": "auto", "label": "Auto (Router decides)"},
            {"value": "claude-sonnet", "label": "Claude Sonnet 4"},
            {"value": "gpt-4o", "label": "GPT-4o"},
        ],
        "quality_judge_options": [
            {"value": "auto", "label": "Auto (Best available)"},
            {"value": "claude-opus", "label": "Claude Opus 4"},
            {"value": "gpt-4o", "label": "GPT-4o"},
            {"value": "gemini-pro", "label": "Gemini 2.5 Pro"},
        ],
    })


# ---------------------------------------------------------------------------
# Projects CRUD
# ---------------------------------------------------------------------------

@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    return jsonify(list_projects())


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    data = request.json or {}
    name = data.get("name", "Untitled Project")
    project = create_project(name)
    return jsonify(project), 201


@app.route("/api/projects/<pid>", methods=["GET"])
def api_get_project(pid):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project)


@app.route("/api/projects/<pid>", methods=["PUT"])
@_project_lock_guard
def api_update_project(pid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    data = request.json or {}

    def _mutate_project(project: dict):
        if "name" in data:
            project["name"] = data["name"]
        if "global_settings" in data:
            project["global_settings"].update(data["global_settings"])
        return project

    project = mutate_project(pid, _mutate_project, timeout=HTTP_PROJECT_TIMEOUT)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project)


@app.route("/api/projects/<pid>", methods=["DELETE"])
@_project_lock_guard
def api_delete_project(pid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    if delete_project(pid, timeout=HTTP_PROJECT_TIMEOUT):
        return jsonify({"deleted": True})
    return jsonify({"error": "Project not found"}), 404


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/characters", methods=["POST"])
@_project_lock_guard
def api_add_character(pid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Handle multipart form data (images + JSON)
    name = request.form.get("name", "Unnamed Character")
    description = request.form.get("description", "")
    voice_id = request.form.get("voice_id", "")
    ip_weight = float(request.form.get("ip_adapter_weight", "0.85"))

    # Save uploaded reference images
    images = request.files.getlist("reference_images")
    image_paths = []
    temp_upload_dir = os.path.join(get_project_dir(pid), "temp_uploads")
    os.makedirs(temp_upload_dir, exist_ok=True)

    for img in images:
        if img.filename:
            filename = secure_filename(img.filename)
            path = os.path.join(temp_upload_dir, filename)
            img.save(path)
            image_paths.append(path)

    # Create character with full processing
    character = create_character_with_images(
        project, name, description,
        reference_image_paths=image_paths,
        voice_id=voice_id,
        ip_adapter_weight=ip_weight,
        commit_timeout=HTTP_PROJECT_TIMEOUT,
    )

    return jsonify(character), 201


@app.route("/api/projects/<pid>/characters/<cid>", methods=["PUT"])
@_project_lock_guard
def api_update_character(pid, cid):
    """Update an existing character's fields. Supports JSON or multipart (for file uploads)."""
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    char = next((c for c in project["characters"] if c["id"] == cid), None)
    if not char:
        return jsonify({"error": "Character not found"}), 404

    # Accept both JSON and form data
    if request.is_json:
        data = request.json
    else:
        data = request.form.to_dict()

    # Handle reference image uploads
    saved_paths = []
    if request.files.getlist("reference_images"):
        project_dir = get_project_dir(pid)
        char_dir = os.path.join(project_dir, "characters", cid)
        os.makedirs(char_dir, exist_ok=True)
        for f in request.files.getlist("reference_images"):
            if f.filename:
                safe_name = f.filename.replace("/", "_").replace("\\", "_")
                save_path = os.path.join(char_dir, safe_name)
                f.save(save_path)
                saved_paths.append(save_path)

    def _mutate_project(latest_project: dict):
        latest_char = next(
            (character for character in latest_project["characters"] if character["id"] == cid),
            None,
        )
        if not latest_char:
            return MutationResult(None, save=False)

        for field in ["name", "description", "voice_id", "physical_traits"]:
            if field in data:
                latest_char[field] = data[field]
        if "ip_adapter_weight" in data:
            latest_char["ip_adapter_weight"] = float(data["ip_adapter_weight"])

        if saved_paths:
            refs = latest_char.setdefault("reference_images", [])
            for save_path in saved_paths:
                if save_path not in refs:
                    refs.append(save_path)
            if not latest_char.get("canonical_reference"):
                latest_char["canonical_reference"] = saved_paths[0]

        return latest_char

    updated_char = mutate_project(
        pid,
        _mutate_project,
        timeout=HTTP_PROJECT_TIMEOUT,
        snapshot=project,
    )
    if not updated_char:
        return jsonify({"error": "Character not found"}), 404
    return jsonify({"updated": True, "character": updated_char})


@app.route("/api/projects/<pid>/characters/<cid>", methods=["DELETE"])
@_project_lock_guard
def api_remove_character(pid, cid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if remove_character(project, cid, timeout=HTTP_PROJECT_TIMEOUT):
        return jsonify({"deleted": True})
    return jsonify({"error": "Character not found"}), 404


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/locations", methods=["POST"])
@_project_lock_guard
def api_add_location(pid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    name = request.form.get("name", "Unnamed Location")
    description = request.form.get("description", "")
    lighting = request.form.get("lighting", "")
    time_of_day = request.form.get("time_of_day", "day")
    weather = request.form.get("weather", "clear")

    images = request.files.getlist("reference_images")
    image_paths = []
    temp_dir = os.path.join(get_project_dir(pid), "temp_uploads")
    os.makedirs(temp_dir, exist_ok=True)
    for img in images:
        if img.filename:
            path = os.path.join(temp_dir, secure_filename(img.filename))
            img.save(path)
            image_paths.append(path)

    location = create_location_with_images(
        project, name, description,
        reference_image_paths=image_paths,
        lighting=lighting,
        time_of_day=time_of_day,
        weather=weather,
        commit_timeout=HTTP_PROJECT_TIMEOUT,
    )

    return jsonify(location), 201


@app.route("/api/projects/<pid>/locations/<lid>", methods=["PUT"])
@_project_lock_guard
def api_update_location(pid, lid):
    """Update an existing location's fields. Supports JSON or multipart for file uploads."""
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    loc = next((l for l in project["locations"] if l["id"] == lid), None)
    if not loc:
        return jsonify({"error": "Location not found"}), 404

    data = request.json if request.is_json else request.form.to_dict()
    # Handle reference image uploads
    saved_paths = []
    if request.files.getlist("reference_images"):
        project_dir = get_project_dir(pid)
        loc_dir = os.path.join(project_dir, "locations", lid)
        os.makedirs(loc_dir, exist_ok=True)
        for f in request.files.getlist("reference_images"):
            if f.filename:
                safe_name = f.filename.replace("/", "_").replace("\\", "_")
                save_path = os.path.join(loc_dir, safe_name)
                f.save(save_path)
                saved_paths.append(save_path)

    def _mutate_project(latest_project: dict):
        latest_location = next(
            (location for location in latest_project["locations"] if location["id"] == lid),
            None,
        )
        if not latest_location:
            return MutationResult(None, save=False)

        for field in ["name", "description", "lighting", "time_of_day", "weather"]:
            if field in data:
                latest_location[field] = data[field]

        if saved_paths:
            refs = latest_location.setdefault("reference_images", [])
            for save_path in saved_paths:
                if save_path not in refs:
                    refs.append(save_path)

        return latest_location

    updated_location = mutate_project(
        pid,
        _mutate_project,
        timeout=HTTP_PROJECT_TIMEOUT,
        snapshot=project,
    )
    if not updated_location:
        return jsonify({"error": "Location not found"}), 404
    return jsonify({"updated": True, "location": updated_location})


@app.route("/api/projects/<pid>/locations/<lid>", methods=["DELETE"])
@_project_lock_guard
def api_remove_location(pid, lid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if remove_location(project, lid, timeout=HTTP_PROJECT_TIMEOUT):
        return jsonify({"deleted": True})
    return jsonify({"error": "Location not found"}), 404


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/scenes", methods=["POST"])
@_project_lock_guard
def api_add_scene(pid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    data = request.json or {}
    scene = make_scene(
        title=data.get("title", "Untitled Scene"),
        location_id=data.get("location_id", ""),
        characters_present=data.get("characters_present", []),
        action=data.get("action", ""),
        dialogue=data.get("dialogue", ""),
        mood=data.get("mood", "neutral"),
        camera_direction=data.get("camera_direction", ""),
        duration_seconds=float(data.get("duration_seconds", 5)),
    )
    result = add_scene(project, scene, timeout=HTTP_PROJECT_TIMEOUT)
    return jsonify(result), 201


@app.route("/api/projects/<pid>/scenes/<sid>", methods=["PUT"])
@_project_lock_guard
def api_update_scene(pid, sid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    data = request.json or {}
    result = update_scene(project, sid, data, timeout=HTTP_PROJECT_TIMEOUT)
    if result:
        return jsonify(result)
    return jsonify({"error": "Scene not found"}), 404


@app.route("/api/projects/<pid>/scenes/<sid>", methods=["DELETE"])
@_project_lock_guard
def api_remove_scene(pid, sid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if remove_scene(project, sid, timeout=HTTP_PROJECT_TIMEOUT):
        return jsonify({"deleted": True})
    return jsonify({"error": "Scene not found"}), 404


@app.route("/api/projects/<pid>/scenes/reorder", methods=["POST"])
@_project_lock_guard
def api_reorder_scenes(pid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    data = request.json or {}
    scene_ids = data.get("scene_ids", [])
    reorder_scenes(project, scene_ids, timeout=HTTP_PROJECT_TIMEOUT)
    return jsonify({"reordered": True})


# ---------------------------------------------------------------------------
# Dialogue Generation
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/scenes/<sid>/generate-dialogue", methods=["POST"])
def api_generate_dialogue(pid, sid):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    scene = next((s for s in project["scenes"] if s["id"] == sid), None)
    if not scene:
        return jsonify({"error": "Scene not found"}), 404

    chars = [c for c in project["characters"] if c["id"] in scene.get("characters_present", [])]
    lines = generate_dialogue(scene, chars, scene.get("mood", "neutral"))
    return jsonify({"dialogue_lines": lines})


# ---------------------------------------------------------------------------
# Scene Decomposition
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/scenes/<sid>/decompose", methods=["POST"])
@_project_lock_guard
def api_decompose_scene(pid, sid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    scene = next((s for s in project["scenes"] if s["id"] == sid), None)
    if not scene:
        return jsonify({"error": "Scene not found"}), 404

    chars = [c for c in project["characters"] if c["id"] in scene.get("characters_present", [])]
    location = next((l for l in project["locations"] if l["id"] == scene.get("location_id")), {})
    settings = project.get("global_settings", {})
    style_rules = settings.get("style_rules", {})

    shots = decompose_scene(scene, chars, location, settings, style_rules)
    update_scene_shots(project, sid, shots, timeout=HTTP_PROJECT_TIMEOUT)

    return jsonify({"shots": shots})


# ---------------------------------------------------------------------------
# Style Rules
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/style-rules", methods=["POST"])
@_project_lock_guard
def api_generate_style_rules(pid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    data = request.json or {}
    settings = project.get("global_settings", {})

    rules = generate_style_rules(
        project_name=project["name"],
        mood=data.get("mood", settings.get("music_mood", "cinematic")),
        color_palette=data.get("color_palette", settings.get("color_palette", "")),
        music_mood=data.get("music_mood", settings.get("music_mood", "suspense")),
        aspect_ratio=settings.get("aspect_ratio", "16:9"),
        reference_films=data.get("reference_films", ""),
        use_web_research=data.get("use_web_research", False),
    )

    def _mutate_project(latest_project: dict):
        latest_settings = latest_project.setdefault("global_settings", {})
        latest_settings["style_rules"] = rules
        return latest_settings["style_rules"]

    mutate_project(
        pid,
        _mutate_project,
        timeout=HTTP_PROJECT_TIMEOUT,
        snapshot=project,
    )
    return jsonify(rules)


# ---------------------------------------------------------------------------
# Generation Pipeline with SSE Streaming
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/generate", methods=["POST"])
def api_generate(pid):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    if pid in _running_pipelines:
        return jsonify({"error": "Generation already in progress"}), 409

    # Create progress queue for SSE
    q = queue.Queue()
    _progress_queues[pid] = q

    def progress_cb(stage, detail, percent, scene_id="", shot_id="",
                    image_url="", identity_score=-1, director_review=None,
                    coherence_score=-1, motion_score=-1, shot_type="",
                    failure_reason="", quality_metrics=None):
        event = {"stage": stage, "detail": detail, "percent": percent}
        if scene_id:
            event["scene_id"] = scene_id
        if shot_id:
            event["shot_id"] = shot_id
        if image_url:
            event["image_url"] = image_url
        if identity_score >= 0:
            event["identity_score"] = identity_score
        if director_review:
            event["director_review"] = director_review
        if coherence_score >= 0:
            event["coherence_score"] = coherence_score
        if motion_score >= 0:
            event["motion_score"] = motion_score
        if shot_type:
            event["shot_type"] = shot_type
        if failure_reason:
            event["failure_reason"] = failure_reason
        if quality_metrics:
            event["quality_metrics"] = quality_metrics
        q.put(event)

    resume = request.json.get("resume", False) if request.is_json else False

    def run_pipeline():
        try:
            pipeline = CinemaPipeline(pid, progress_callback=progress_cb)
            _running_pipelines[pid] = pipeline
            result = pipeline.generate(resume=resume)
            q.put({"stage": "DONE", "detail": result or "Failed", "percent": 100})
        except Exception as e:
            q.put({"stage": "ERROR", "detail": str(e), "percent": 0})
        finally:
            _running_pipelines.pop(pid, None)
            q.put(None)  # Signal end of stream

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()

    return jsonify({"started": True, "resume": resume, "message": "Generation started. Connect to /api/projects/<pid>/stream for progress."})


@app.route("/api/projects/<pid>/checkpoint")
def api_checkpoint(pid):
    """Check if a resumable checkpoint exists for this project."""
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    try:
        pipeline = CinemaPipeline(pid)
        info = pipeline.resume_info()
        return jsonify(info)
    except Exception as e:
        return jsonify({"resumable": False, "error": str(e)})


@app.route("/api/projects/<pid>/stream")
def api_stream(pid):
    """SSE endpoint for real-time generation progress."""
    q = _progress_queues.get(pid)
    if not q:
        return jsonify({"error": "No generation in progress"}), 404

    def event_stream():
        while True:
            try:
                msg = q.get(timeout=30)
                if msg is None:
                    yield f"data: {json.dumps({'stage': 'END', 'detail': 'Stream closed', 'percent': 100})}\n\n"
                    break
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'stage': 'HEARTBEAT', 'detail': 'waiting', 'percent': -1})}\n\n"

    return Response(event_stream(), content_type="text/event-stream")


@app.route("/api/projects/<pid>/cancel", methods=["POST"])
def api_cancel(pid):
    pipeline = _running_pipelines.get(pid)
    if pipeline:
        pipeline.cancel()
        return jsonify({"cancelled": True})
    return jsonify({"error": "No generation in progress"}), 404


# ---------------------------------------------------------------------------
# Export / Preview
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/file")
def api_serve_file(pid):
    """Serve a generated file (image/video) from the project directory."""
    file_path = request.args.get("path", "")
    if not file_path:
        return jsonify({"error": "Invalid path"}), 400
    # Security: resolve to real path and verify containment within project dir
    real_path = os.path.realpath(file_path)
    project_dir = os.path.realpath(get_project_dir(pid))
    if not real_path.startswith(project_dir + os.sep) and real_path != project_dir:
        return jsonify({"error": "Access denied"}), 403
    if not os.path.exists(real_path):
        return jsonify({"error": "File not found"}), 404
    mimetype = "image/jpeg" if real_path.endswith(".jpg") else "video/mp4" if real_path.endswith(".mp4") else "audio/mpeg"
    return send_file(real_path, mimetype=mimetype)


@app.route("/api/projects/<pid>/shots/<shot_id>/approve", methods=["POST"])
@_project_lock_guard
def api_approve_shot(pid, shot_id):
    """Approve a shot's generated image — proceed to video generation."""
    def _mutate_project(project: dict):
        for scene in project["scenes"]:
            for shot in scene.get("shots", []):
                if shot.get("id") == shot_id:
                    shot["approved"] = True
                    return True
        return MutationResult(False, save=False)

    result = mutate_project(pid, _mutate_project, timeout=HTTP_PROJECT_TIMEOUT)
    if result is None:
        return jsonify({"error": "Project not found"}), 404
    if result:
        return jsonify({"approved": True, "shot_id": shot_id})
    return jsonify({"error": "Shot not found"}), 404


@app.route("/api/projects/<pid>/shots/<shot_id>/reject", methods=["POST"])
@_project_lock_guard
def api_reject_shot(pid, shot_id):
    """Reject a shot's image — mark for regeneration."""
    reason = request.json.get("reason", "") if request.is_json else ""

    def _mutate_project(project: dict):
        for scene in project["scenes"]:
            for shot in scene.get("shots", []):
                if shot.get("id") == shot_id:
                    shot["approved"] = False
                    shot["rejection_reason"] = reason
                    return True
        return MutationResult(False, save=False)

    result = mutate_project(pid, _mutate_project, timeout=HTTP_PROJECT_TIMEOUT)
    if result is None:
        return jsonify({"error": "Project not found"}), 404
    if result:
        return jsonify({"rejected": True, "shot_id": shot_id, "reason": reason})
    return jsonify({"error": "Shot not found"}), 404


@app.route("/api/projects/<pid>/shots/<shot_id>/prompt", methods=["PUT"])
@_project_lock_guard
def api_update_shot_prompt(pid, shot_id):
    """Update a shot's prompt before regeneration."""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    new_prompt = request.json.get("prompt", "")

    def _mutate_project(project: dict):
        for scene in project["scenes"]:
            for shot in scene.get("shots", []):
                if shot.get("id") == shot_id:
                    shot["prompt"] = new_prompt
                    return True
        return MutationResult(False, save=False)

    result = mutate_project(pid, _mutate_project, timeout=HTTP_PROJECT_TIMEOUT)
    if result is None:
        return jsonify({"error": "Project not found"}), 404
    if result:
        return jsonify({"updated": True, "shot_id": shot_id})
    return jsonify({"error": "Shot not found"}), 404


@app.route("/api/projects/<pid>/shots/<shot_id>", methods=["PUT"])
@_project_lock_guard
def api_update_shot(pid, shot_id):
    """Update shot fields (target_api, camera, visual_effect, prompt, scene_foley)."""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    data = request.json
    allowed_fields = {"target_api", "camera", "visual_effect", "prompt", "scene_foley"}
    updates = {k: v for k, v in data.items() if k in allowed_fields}

    if "target_api" in updates and updates["target_api"] not in TARGET_APIS:
        return jsonify({"error": f"Invalid target_api. Must be one of: {TARGET_APIS}"}), 400

    def _mutate_project(project: dict):
        for scene in project["scenes"]:
            for shot in scene.get("shots", []):
                if shot.get("id") == shot_id:
                    shot.update(updates)
                    return True
        return MutationResult(False, save=False)

    result = mutate_project(pid, _mutate_project, timeout=HTTP_PROJECT_TIMEOUT)
    if result is None:
        return jsonify({"error": "Project not found"}), 404
    if result:
        return jsonify({"updated": True, "shot_id": shot_id, "fields": list(updates.keys())})
    return jsonify({"error": "Shot not found"}), 404


# ---------------------------------------------------------------------------
# Pipeline Controls (pause/resume/state/regenerate)
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/pause", methods=["POST"])
def api_pause(pid):
    """Pause the running pipeline at the next checkpoint."""
    pipeline = _running_pipelines.get(pid)
    if pipeline:
        pipeline.pause()
        return jsonify({"paused": True})
    return jsonify({"error": "No generation in progress"}), 404


@app.route("/api/projects/<pid>/resume", methods=["POST"])
def api_resume(pid):
    """Resume a paused pipeline."""
    pipeline = _running_pipelines.get(pid)
    if pipeline:
        pipeline.resume()
        return jsonify({"resumed": True})
    return jsonify({"error": "No generation in progress"}), 404


@app.route("/api/projects/<pid>/pipeline-state")
def api_pipeline_state(pid):
    """Get current pipeline execution state."""
    pipeline = _running_pipelines.get(pid)
    if pipeline:
        return jsonify(pipeline.get_state())
    return jsonify({"error": "No generation in progress", "paused": False, "cancelled": False}), 404


@app.route("/api/projects/<pid>/shots/<shot_id>/regenerate", methods=["POST"])
@_project_lock_guard
def api_regenerate_shot(pid, shot_id):
    """Regenerate a single shot. Supports positive_prompt and negative_prompt."""
    pipeline = _running_pipelines.get(pid)
    new_prompt = request.json.get("positive_prompt") if request.is_json else None

    def _mutate_project(project: dict):
        for scene in project["scenes"]:
            for shot in scene.get("shots", []):
                if shot.get("id") == shot_id:
                    if new_prompt:
                        shot["prompt"] = new_prompt
                        return scene["id"]
                    return MutationResult(scene["id"], save=False)
        return MutationResult(False, save=False)

    scene_id = mutate_project(pid, _mutate_project, timeout=HTTP_PROJECT_TIMEOUT)
    if scene_id is None:
        return jsonify({"error": "Project not found"}), 404
    if scene_id is False:
        return jsonify({"error": "Shot not found"}), 404

    if pipeline:
        result = pipeline.regenerate_shot(scene_id, shot_id)
        return jsonify(result)

    q = _progress_queues.get(pid)

    def progress_cb(stage, detail, percent, scene_id="", shot_id="",
                    image_url="", identity_score=-1, director_review=None, **kwargs):
        event = {"stage": stage, "detail": detail, "percent": percent}
        if scene_id:
            event["scene_id"] = scene_id
        if shot_id:
            event["shot_id"] = shot_id
        if image_url:
            event["image_url"] = image_url
        if identity_score >= 0:
            event["identity_score"] = identity_score
        if q:
            q.put(event)

    try:
        temp_pipeline = CinemaPipeline(pid, progress_callback=progress_cb)
        result = temp_pipeline.regenerate_shot(scene_id, shot_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/projects/<pid>/shots/<shot_id>/correct", methods=["POST"])
def api_correct_shot(pid, shot_id):
    """Apply a correction tool to a clip during Director's Cut review."""
    pipeline = _running_pipelines.get(pid)
    if not pipeline:
        return jsonify({"error": "No pipeline running — start generation first"}), 404

    data = request.json if request.is_json else {}
    action = data.get("action", "")
    params = data.get("params", {})

    if not action:
        return jsonify({"error": "Missing 'action' field"}), 400

    result = pipeline.apply_correction(shot_id, action, params)
    return jsonify(result)


@app.route("/api/projects/<pid>/shots/<shot_id>/diagnose", methods=["POST"])
def api_diagnose_shot(pid, shot_id):
    """Run quality diagnostics on a clip."""
    pipeline = _running_pipelines.get(pid)
    if not pipeline:
        return jsonify({"error": "No pipeline running"}), 404

    result = pipeline.diagnose_clip(shot_id)
    return jsonify(result)


@app.route("/api/projects/<pid>/proceed-assembly", methods=["POST"])
def api_proceed_assembly(pid):
    """Resume pipeline from Director's Cut review to final assembly."""
    pipeline = _running_pipelines.get(pid)
    if not pipeline:
        return jsonify({"error": "No pipeline running"}), 404

    pipeline.proceed_to_assembly()
    return jsonify({"proceeding": True})


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/cleanup", methods=["POST"])
def api_cleanup(pid):
    """Clean up temporary files from a project."""
    from cleanup import cleanup_project, get_project_disk_usage

    aggressive = request.json.get("aggressive", False) if request.is_json else False
    dry_run = request.json.get("dry_run", False) if request.is_json else False

    result = cleanup_project(pid, aggressive=aggressive, dry_run=dry_run)
    result["disk_usage"] = get_project_disk_usage(pid)
    return jsonify(result)


@app.route("/api/projects/<pid>/disk-usage")
def api_disk_usage(pid):
    """Get disk usage breakdown for a project."""
    from cleanup import get_project_disk_usage
    return jsonify(get_project_disk_usage(pid))


@app.route("/api/cleanup-all", methods=["POST"])
def api_cleanup_all():
    """Clean up all projects."""
    from cleanup import cleanup_all_projects

    aggressive = request.json.get("aggressive", False) if request.is_json else False
    result = cleanup_all_projects(aggressive=aggressive)
    return jsonify(result)


@app.route("/api/projects/<pid>/export")
def api_export(pid):
    export_dir = os.path.join(get_project_dir(pid), "exports")
    final_path = os.path.join(export_dir, "final_cinema.mp4")
    if os.path.exists(final_path):
        return send_file(final_path, mimetype="video/mp4", as_attachment=True)
    return jsonify({"error": "No exported video found"}), 404


@app.route("/api/projects/<pid>/preview/<sid>")
def api_preview_scene(pid, sid):
    export_dir = os.path.join(get_project_dir(pid), "exports")
    preview_path = os.path.join(export_dir, f"preview_{sid}.mp4")
    if os.path.exists(preview_path):
        return send_file(preview_path, mimetype="video/mp4")
    return jsonify({"error": "No preview available"}), 404


# ---------------------------------------------------------------------------
# Uploaded files serving
# ---------------------------------------------------------------------------

@app.route("/api/files/<path:filepath>")
def serve_project_file(filepath):
    """Serve files from the projects directory (character images, etc.)."""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects")
    full_path = os.path.join(base, filepath)
    if os.path.exists(full_path) and os.path.isfile(full_path):
        return send_file(full_path)
    return jsonify({"error": "File not found"}), 404


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🎬 CINEMA PRODUCTION TOOL — Web Server")
    print("=" * 60)
    print("Open http://localhost:8080 in your browser")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
