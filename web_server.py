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

# Ensure Homebrew binaries (ffmpeg, ffprobe) are in PATH
_homebrew_bin = "/opt/homebrew/bin"
if _homebrew_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _homebrew_bin + ":" + os.environ.get("PATH", "")

# Install structured JSON logging BEFORE any cinema_pipeline imports so
# their module-level logger.getLogger() calls inherit the root config.
from cinema.logging_config import setup_logging  # noqa: E402

setup_logging()

import json
import threading
import queue
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory, Response, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from project_manager import (
    MutationResult, ProjectLockError, create_project, load_project, delete_project,
    list_projects, mutate_project,
    add_character, remove_character, add_location, remove_location,
    add_object, remove_object, get_object,
    add_scene, update_scene, remove_scene, reorder_scenes,
    make_character, make_location, make_object, make_scene, get_project_dir,
)
from character_manager import create_character_with_images, VOICE_POOL
from location_manager import create_location_with_images
from scene_decomposer import decompose_scene, update_scene_shots, CAMERA_MOTIONS, VISUAL_EFFECTS, TARGET_APIS, API_REGISTRY, MUSIC_MOODS
from domain.models import DirectorialIntent, Project
from domain.scene_decomposer import PURPOSE_TAGS, PURPOSE_API_RANKING, BILLING_PROVIDERS, estimate_short_cost
from dialogue_writer import generate_dialogue
from llm.style_director import generate_style_rules
from cinema_pipeline import CinemaPipeline
from cinema.core import PipelineCore, build_pipeline_core
from cinema.services import state_snapshot, checkpoint_info
from workflow_selector import WORKFLOW_TEMPLATES
from web_services import make_progress_callback
from config.settings import settings as env_settings

app = Flask(__name__, static_folder="web/dist", static_url_path="")
# CORS allowlist comes from settings.web_cors_origins. Default is
# localhost-only ("http://localhost:8080" + "http://localhost:5173" for
# Vite dev). To opt back into the pre-hardening wide-open behavior,
# set WEB_CORS_ORIGINS=* in .env. Bound by env to support LAN/multi-device
# use cases via WEB_CORS_ORIGINS=http://localhost:8080,http://<lan-ip>:8080.
CORS(app, origins=list(env_settings.web_cors_origins))

# SSE progress queues per project
_progress_queues: dict[str, queue.Queue] = {}
_running_pipelines: dict[str, CinemaPipeline] = {}

# Guards _running_pipelines and _progress_queues. The construct-window
# sentinel (_PIPELINE_PENDING) lets us reserve a slot atomically while
# the heavy CinemaPipeline constructor runs WITHOUT holding the lock.
# Mirrors the _cores_lock / _lora_training_lock pattern (Session 5 fix
# and LoRA training). Audit ref: docs/AUDIT-P3-1-concurrency-2026-05-24.md
_pipelines_lock = threading.Lock()
_PIPELINE_PENDING = object()  # sentinel — readers must skip this

# Review-gate stages where the pipeline worker thread is BLOCKED at
# lifecycle.wait_for_gate (cinema/lifecycle.py:172-188 polling Event.wait
# loop), not actively running steps. The pid remains in _running_pipelines
# for the entire gate-wait, but endpoints that operate ON the gate
# (iterate, /screening/approve, /assemble/re-assemble) MUST be reachable
# during this window — operator workflow is iterate-during-gate-then-approve.
# See _reject_if_project_busy_outside_gate for the bypass semantics.
# Lane V #8 I1 codified this set; before, only the re-assemble + screening-
# approve endpoints had ad-hoc bypasses, and the iterate endpoint missed
# the bypass entirely (rendering Surface B's iterate-during-screening flow
# unreachable behind the flag combination).
_GATE_STAGES = frozenset({
    "PLAN_REVIEW",
    "KEYFRAME_REVIEW",
    "PERFORMANCE_REVIEW",
    "REVIEW",
    "SCREENING",
})

# PipelineCore cache (Slice 3b Phase 1c). Caches the heavy long-lived
# services (ContinuityEngine, ChiefDirector, LLMEnsemble,
# QualityTracker, CostTracker) per project_id so that per-endpoint
# CinemaPipeline construction doesn't re-instantiate them on every
# request. Lifetime: until process restart. Not invalidated on
# project-settings change on disk -- known limitation; restart the
# server if you edit settings.json out-of-band.
_running_cores: dict[str, PipelineCore] = {}
_cores_lock = threading.Lock()
HTTP_PROJECT_TIMEOUT = 2.0

# S21 (cycle-9 Surface B): re-assembly busy tracking.
# The re-assembly endpoint runs a heavyweight ffmpeg pipeline
# (normalize + stitch + grade + bgm + loudnorm). Two concurrent
# re-assemblies on the same project would clobber final_cinema.mp4.
# But we CANNOT use _reject_if_project_busy because re-assembly runs
# WHILE the pipeline is gate-waiting in SCREENING -- the pipeline
# IS in _running_pipelines (it's the SCREENING-waiter), so busy-fencing
# would deadlock the operator (cannot re-assemble while the screening
# gate is open, but the gate is open precisely so the operator can
# re-assemble). Mirrors the same fence-bypass reasoning at
# api_screening_approve. Re-entrancy is the actual concern; this
# narrower in-flight set + its own lock handles it.
_reassembly_in_flight: set[str] = set()
_reassembly_lock = threading.Lock()


def _get_or_build_core(pid: str) -> PipelineCore:
    """Return a cached PipelineCore for ``pid``, building one if absent.

    Thread-safe via _cores_lock. Raises ValueError (from
    build_pipeline_core) if the project_id doesn't resolve to a saved
    project -- callers handle the same way they handled the equivalent
    raise from CinemaPipeline.__init__ before this slice.
    """
    with _cores_lock:
        core = _running_cores.get(pid)
        if core is None:
            core = build_pipeline_core(pid)
            _running_cores[pid] = core
        return core


def _get_running_pipeline(pid: str):
    """Return the active CinemaPipeline for pid, or None if absent /
    still mid-construction (sentinel). Callers should treat None as
    "no generation in progress" — the sentinel state is brief (only
    during CinemaPipeline.__init__) but visible to readers.

    This is the single safe reader for _running_pipelines. All endpoint
    code that needs the pipeline object MUST use this helper — never call
    _running_pipelines.get(pid) directly, since object() is truthy and
    would crash with AttributeError on any method call.
    """
    pipeline = _running_pipelines.get(pid)
    if pipeline is None or pipeline is _PIPELINE_PENDING:
        return None
    return pipeline


def _ensure_progress_queue(pid: str) -> queue.Queue:
    with _pipelines_lock:
        q = _progress_queues.get(pid)
        if q is None:
            q = queue.Queue()
            _progress_queues[pid] = q
        return q


def _make_progress_cb(pid: str, q: queue.Queue | None = None):
    """Per-project SSE progress callback. Thin wrapper around web_services.

    Resolves the queue (explicit arg or module-state lookup), then
    delegates to ``web_services.make_progress_callback`` which contains
    the actual SSE-event-shaping logic. Keeping this resolver in
    web_server.py preserves the module-state contract used by other
    endpoints; the pure builder is reusable.
    """
    progress_queue = q or _progress_queues.get(pid)
    return make_progress_callback(progress_queue)


def _get_stage_pipeline(pid: str) -> CinemaPipeline:
    pipeline = _get_running_pipeline(pid)  # returns None during sentinel window
    if pipeline:
        return pipeline
    # Build a per-request CinemaPipeline that shares the cached core --
    # amortizes the heavy service construction across endpoint calls.
    # Also reached during the _PIPELINE_PENDING window (treat like absent).
    return CinemaPipeline(pid, core=_get_or_build_core(pid), progress_callback=_make_progress_cb(pid))


def _locate_shot(project: dict, shot_id: str):
    for scene in project.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot.get("id") == shot_id:
                return scene, shot
    return None, None

def _get_delivery_styles():
    """Get delivery styles with descriptions for the frontend."""
    try:
        from audio.voiceover import VOICE_DIRECTIONS
        return {k: v.get("description", k) for k, v in VOICE_DIRECTIONS.items()}
    except (ImportError, AttributeError) as e:
        print(f"   [WEB] Could not load delivery styles: {e}")
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


def _pipeline_at_gate_stage(pid: str) -> bool:
    """Return True if pid's pipeline is parked at a review-gate stage.

    Used by ``_reject_if_project_busy_outside_gate`` to skip the busy
    fence for endpoints that operate ON the gate (iterate,
    /screening/approve, /assemble/re-assemble). The pipeline worker is
    blocked at ``lifecycle.wait_for_gate``, not actively running steps,
    so concurrent gate-acting endpoint calls are safe.

    Race-safe: ``_get_running_pipeline`` returns ``None`` during the
    sentinel window (treat as "not at a gate; fence normally"). Returns
    ``False`` on any ``AttributeError`` accessing ``current_stage`` so
    test fixtures injecting bare ``object()`` sentinels don't crash —
    they're treated as "fence normally" too, which preserves the
    legacy busy-fence semantics for code paths that haven't migrated.
    """
    pipeline = _get_running_pipeline(pid)
    if pipeline is None:
        return False
    try:
        return pipeline.current_stage in _GATE_STAGES
    except AttributeError:
        return False


def _reject_if_project_busy_outside_gate(pid: str):
    """Like ``_reject_if_project_busy`` but allows calls through when the
    running pipeline is parked at a review-gate stage. Operator workflow
    expects iterate-during-gate; without this bypass, the entire
    Surface A + Surface B value proposition is unreachable behind the
    flag combination.

    Mirrors the explicit bypasses already coded for
    ``api_screening_approve`` and ``api_assemble_reassemble`` (see the
    block comment at lines 90-101). Lane V #8 I1 surfaced the gap —
    iterate was the only gate-acting endpoint that still busy-fenced
    unconditionally, despite the same fence-bypass reasoning applying
    verbatim. Codified as the canonical helper here so future gate-
    acting endpoints can share the discipline.
    """
    if pid in _running_pipelines and not _pipeline_at_gate_stage(pid):
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
        "workflow_templates": WORKFLOW_TEMPLATES,
        # Purpose-based API routing surface (consumed by SettingsPanel)
        "purpose_tags": PURPOSE_TAGS,
        "purpose_api_ranking": PURPOSE_API_RANKING,
        # Billing attribution for cost estimator
        "billing_providers": BILLING_PROVIDERS,
    })


@app.route("/api/projects/<pid>/apply-language-defaults", methods=["POST"])
@_project_lock_guard
def api_apply_language_defaults(pid):
    """Apply per-language optimized defaults to a project's global_settings.

    Body (JSON):
      { "language": "Korean", "overwrite_existing": false }

    When overwrite_existing is False (default), only fields the user hasn't
    customized are touched. The response includes the list of fields that
    actually changed so the UI can show a diff.
    """
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    data = request.json or {}
    language = data.get("language") or project.get("global_settings", {}).get("language", "English")
    overwrite = bool(data.get("overwrite_existing", False))

    try:
        from domain.language_defaults import (
            merge_language_defaults_into_settings,
            recommended_voices_for_language,
            get_language_defaults,
        )
        from domain.character_manager import VOICE_POOL
    except Exception as e:
        return jsonify({"error": f"language_defaults unavailable: {e}"}), 500

    changed_fields: list[str] = []

    def _mutate(latest):
        nonlocal changed_fields
        settings = latest.setdefault("global_settings", {})
        _, changed = merge_language_defaults_into_settings(settings, language, overwrite_existing=overwrite)
        changed_fields = changed
        return MutationResult(True, save=bool(changed))

    mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT, snapshot=project)
    recommended_voices = recommended_voices_for_language(language, VOICE_POOL)
    return jsonify({
        "language": language,
        "changed_fields": changed_fields,
        "applied_defaults": {k: get_language_defaults(language).get(k) for k in changed_fields},
        "recommended_voices": recommended_voices,
    })


@app.route("/api/cost-estimate", methods=["POST"])
def api_cost_estimate():
    """Live cost estimate. Body: { shot_count, has_dialogue, quality_tier, candidate_count, dialogue_shot_ratio }."""
    data = request.json or {}
    est = estimate_short_cost(
        shot_count=int(data.get("shot_count", 60)),
        has_dialogue=bool(data.get("has_dialogue", True)),
        dialogue_shot_ratio=float(data.get("dialogue_shot_ratio", 0.5)),
        quality_tier=str(data.get("quality_tier", "production")),
        candidate_count=int(data.get("candidate_count", 1)),
    )
    return jsonify(est)


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
                safe_name = secure_filename(f.filename) or "file"
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
# Objects (products / props for commercials)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# LoRA training (per-character) — triggers async training, exposes status.
# ---------------------------------------------------------------------------
# Active jobs tracked in-memory; survives only for the lifetime of the server.
# Status sidecar on disk (<project>/loras/<char>/status.json) is the source of truth.
# The lock guards check-and-insert into _lora_training_threads to prevent the
# TOCTOU race where two concurrent POSTs both pass the is_alive() check before
# either starts a thread.
_lora_training_threads: dict[str, threading.Thread] = {}
_lora_training_lock = threading.Lock()


@app.route("/api/projects/<pid>/characters/<cid>/train-lora", methods=["POST"])
@_project_lock_guard
def api_train_lora(pid, cid):
    """Trigger LoRA training for a character. Runs in a background thread.
    Body (JSON, optional): { config_overrides: {rank, alpha, steps, learning_rate, ...} }
    """
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    char = next((c for c in project.get("characters", []) if c["id"] == cid), None)
    if not char:
        return jsonify({"error": "Character not found"}), 404

    if len(char.get("reference_images", []) or []) < 15:
        return jsonify({
            "error": "Insufficient reference images",
            "needed": 15,
            "have": len(char.get("reference_images", []) or []),
            "guidance": "25-50 varied angles + lighting recommended for FLUX LoRA training",
        }), 400

    key = f"{pid}:{cid}"

    try:
        from prep.lora_training import train_character_lora
    except Exception as e:
        return jsonify({"error": f"prep.lora_training unavailable: {e}"}), 500

    project_dir = get_project_dir(pid)
    config_overrides = (request.json or {}).get("config_overrides") if request.is_json else None

    def _runner():
        try:
            result = train_character_lora(project_dir, char, config_overrides=config_overrides)
            # On success, register the LoRA path in project.global_settings.char_lora_paths
            if result.get("success") and result.get("lora_path"):
                def _mutate(latest):
                    settings = latest.setdefault("global_settings", {})
                    paths = settings.setdefault("char_lora_paths", {})
                    paths[cid] = result["lora_path"]
                    return MutationResult(True, save=True)
                try:
                    mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT)
                except Exception as me:
                    print(f"[LoRA] could not persist lora_path to settings: {me}")
        finally:
            with _lora_training_lock:
                _lora_training_threads.pop(key, None)

    # Atomic check-and-insert: the lock serializes the existence check and the
    # thread-start so two concurrent POSTs can't both pass the check.
    with _lora_training_lock:
        existing = _lora_training_threads.get(key)
        if existing and existing.is_alive():
            return jsonify({"error": "Training already in progress for this character"}), 409
        t = threading.Thread(target=_runner, daemon=True, name=f"lora-train-{cid}")
        _lora_training_threads[key] = t
        t.start()

    return jsonify({"started": True, "char_id": cid, "background": True}), 202


@app.route("/api/projects/<pid>/characters/<cid>/lora-status", methods=["GET"])
def api_lora_status(pid, cid):
    """Poll training status. Returns idle when no training has ever run for this character."""
    try:
        from prep.lora_training import get_lora_status
    except Exception as e:
        return jsonify({"error": f"prep.lora_training unavailable: {e}"}), 500
    project_dir = get_project_dir(pid)
    return jsonify(get_lora_status(project_dir, cid))


@app.route("/api/projects/<pid>/shots/<sid>/upload-driving-video", methods=["POST"])
@_project_lock_guard
def api_upload_driving_video(pid, sid):
    """Operator upload of a driving video for a specific shot (Mode A).

    Saves to <project>/performance_inputs/<scene_id>/<shot_id>/driving.mp4
    and sets shot.driving_video_path. PerformanceCapturePhase will pick it
    up automatically on the next run.
    """
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # P1-3 part 6 migration (fifth canonical example): cross-scene nested
    # shot lookup returning the parent scene_id. New shape vs prior parts:
    # iterates project.scenes and inside each scene's typed shots to find
    # the one whose id matches `sid`. The outer scope only needs the parent
    # scene_id (a string); shot/scene typed objects are intentionally
    # discarded. The inner `_mutate` callback below operates on its own
    # `latest` dict snapshot via mutate_project() — only the outer lookup
    # was migrated. See docs/MIGRATION-PATTERN-pydantic-caller.md.
    project_typed = Project.model_validate(project)
    scene_id = next(
        (s.id for s in project_typed.scenes if any(sh.id == sid for sh in s.shots)),
        None,
    )
    if not scene_id:
        return jsonify({"error": "Shot not found in project"}), 404

    file_obj = request.files.get("driving_video")
    if not file_obj or not file_obj.filename:
        return jsonify({"error": "No file uploaded under field 'driving_video'"}), 400

    project_dir = get_project_dir(pid)
    dest_dir = os.path.join(project_dir, "performance_inputs", scene_id, sid)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, "driving.mp4")
    file_obj.save(dest_path)

    def _mutate(latest):
        for scn in latest.get("scenes", []):
            for shot in scn.get("shots", []):
                if shot.get("id") == sid:
                    shot["driving_video_path"] = dest_path
                    # Clear any prior auto-skip so the next run actually generates
                    if shot.get("performance_engine", "").upper() == "SKIP":
                        shot["performance_engine"] = ""
                    return MutationResult(dest_path, save=True)
        return MutationResult(None, save=False)

    mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT, snapshot=project)
    return jsonify({"uploaded": True, "path": dest_path}), 201


@app.route("/api/projects/<pid>/shots/<sid>/performance", methods=["DELETE"])
@_project_lock_guard
def api_clear_performance(pid, sid):
    """Operator clears a shot's performance take so the next run regenerates.
    Used by the PERFORMANCE_REVIEW gate's "re-record" affordance.
    """
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    def _mutate(latest):
        for scn in latest.get("scenes", []):
            for shot in scn.get("shots", []):
                if shot.get("id") == sid:
                    shot["approved_performance_take_id"] = ""
                    shot["performance_engine"] = ""
                    return MutationResult(True, save=True)
        return MutationResult(None, save=False)

    mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT, snapshot=project)
    return jsonify({"cleared": True})


@app.route("/api/projects/<pid>/style-board", methods=["POST"])
@_project_lock_guard
def api_upload_style_board(pid):
    """Multi-image upload for the project style board. Drives FLUX Redux conditioning."""
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    images = request.files.getlist("references")
    if not images:
        return jsonify({"error": "No images uploaded under field 'references'"}), 400

    project_dir = get_project_dir(pid)
    style_dir = os.path.join(project_dir, "style_board")
    os.makedirs(style_dir, exist_ok=True)

    saved = []
    for f in images:
        if f.filename:
            safe_name = secure_filename(f.filename) or "file"
            path = os.path.join(style_dir, safe_name)
            f.save(path)
            saved.append(path)

    def _mutate(latest):
        settings = latest.setdefault("global_settings", {})
        refs = settings.setdefault("style_reference_paths", [])
        for p in saved:
            if p not in refs:
                refs.append(p)
        return refs

    refs = mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT)
    return jsonify({"uploaded": len(saved), "total_refs": len(refs or [])}), 201


@app.route("/api/projects/<pid>/objects", methods=["POST"])
@_project_lock_guard
def api_add_object(pid):
    """Create a new product/prop object. Supports multipart for reference image upload."""
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Accept JSON or multipart form
    if request.is_json:
        data = request.json or {}
    else:
        data = request.form.to_dict()

    name = data.get("name", "Unnamed Object")
    description = data.get("description", "")
    brand = data.get("brand", "")
    material_traits = data.get("material_traits", "")
    surface_type = data.get("surface_type", "matte")
    branding_constraints = data.get("branding_constraints", "")
    scale_reference = data.get("scale_reference", "")
    texture_anchor = data.get("texture_anchor", "")
    ip_weight = float(data.get("ip_adapter_weight", "0.85"))

    # Create the object FIRST to claim a unique id, then save uploaded references
    # into <project>/objects/<obj_id>/. The previous flow used a shared
    # `obj_pending` staging dir which raced when two operators uploaded to the
    # same project concurrently — second upload's files were lost to the first
    # rename. Race-free now because every upload gets its own object dir.
    obj = make_object(
        name=name,
        description=description,
        brand=brand,
        reference_images=[],
        material_traits=material_traits,
        surface_type=surface_type,
        branding_constraints=branding_constraints,
        scale_reference=scale_reference,
        texture_anchor=texture_anchor,
        ip_adapter_weight=ip_weight,
    )

    image_paths = []
    if not request.is_json:
        images = request.files.getlist("reference_images")
        project_dir = get_project_dir(pid)
        obj_dir = os.path.join(project_dir, "objects", obj["id"])
        os.makedirs(obj_dir, exist_ok=True)
        for img in images:
            if img.filename:
                fname = secure_filename(img.filename) or "file"
                path = os.path.join(obj_dir, fname)
                img.save(path)
                image_paths.append(path)

    if image_paths:
        obj["reference_images"] = image_paths
        obj["canonical_reference"] = image_paths[0]

    add_object(project, obj, timeout=HTTP_PROJECT_TIMEOUT)
    return jsonify(obj), 201


@app.route("/api/projects/<pid>/objects/<oid>", methods=["PUT"])
@_project_lock_guard
def api_update_object(pid, oid):
    """Update an object's fields. JSON or multipart (for adding more refs)."""
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    obj = get_object(project, oid)
    if not obj:
        return jsonify({"error": "Object not found"}), 404

    data = request.json if request.is_json else request.form.to_dict()

    # Handle additional reference image uploads
    saved_paths = []
    if not request.is_json and request.files.getlist("reference_images"):
        project_dir = get_project_dir(pid)
        obj_dir = os.path.join(project_dir, "objects", oid)
        os.makedirs(obj_dir, exist_ok=True)
        for f in request.files.getlist("reference_images"):
            if f.filename:
                safe_name = secure_filename(f.filename) or "file"
                save_path = os.path.join(obj_dir, safe_name)
                f.save(save_path)
                saved_paths.append(save_path)

    def _mutate_project(latest_project: dict):
        latest_obj = next(
            (o for o in latest_project.get("objects", []) if o["id"] == oid),
            None,
        )
        if not latest_obj:
            return MutationResult(None, save=False)
        for field in ["name", "description", "brand", "material_traits",
                      "surface_type", "branding_constraints", "scale_reference",
                      "texture_anchor"]:
            if field in data:
                latest_obj[field] = data[field]
        if "ip_adapter_weight" in data:
            latest_obj["ip_adapter_weight"] = float(data["ip_adapter_weight"])
        if saved_paths:
            refs = latest_obj.setdefault("reference_images", [])
            for p in saved_paths:
                if p not in refs:
                    refs.append(p)
            if not latest_obj.get("canonical_reference"):
                latest_obj["canonical_reference"] = saved_paths[0]
        return latest_obj

    updated = mutate_project(pid, _mutate_project, timeout=HTTP_PROJECT_TIMEOUT, snapshot=project)
    if not updated:
        return jsonify({"error": "Object not found"}), 404
    return jsonify({"updated": True, "object": updated})


@app.route("/api/projects/<pid>/objects/<oid>", methods=["DELETE"])
@_project_lock_guard
def api_remove_object(pid, oid):
    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    if remove_object(project, oid, timeout=HTTP_PROJECT_TIMEOUT):
        return jsonify({"deleted": True})
    return jsonify({"error": "Object not found"}), 404


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

    # P1-3 part 5 migration (fourth canonical example): single-entity
    # existence check at endpoint boundary in a MUTATING endpoint. The
    # write-back inside `_mutate_project` (passed to `mutate_project()`
    # below) operates on its own dict snapshot (`latest_project`) and
    # stays on raw dict access by design — only the outer-scope existence
    # check was migrated. Same template as Sessions 10 / P1-3 parts 3 / 4;
    # see docs/MIGRATION-PATTERN-pydantic-caller.md for the full recipe.
    project_typed = Project.model_validate(project)
    loc_typed = next((l for l in project_typed.locations if l.id == lid), None)
    if not loc_typed:
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
                safe_name = secure_filename(f.filename) or "file"
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

    # P1-3 migration template (Session 10): validate to Pydantic at the
    # function boundary, then access via attributes.  Future call sites
    # follow this pattern (Sessions 12+).  See
    # docs/MIGRATION-PATTERN-pydantic-caller.md for the full recipe.
    #
    # Default-translation note: Scene.characters_present and Scene.mood both
    # default to [] and "" respectively in the Pydantic model; the prior dict
    # access used scene.get("characters_present", []) and scene.get("mood",
    # "neutral").  We handle the mood default at call site with `or "neutral"`
    # to preserve identical semantics without changing the Pydantic model.
    #
    # Note: `global_settings` access at line below remains on raw dict by
    # design — only scene/character access was migrated in this template
    # commit. Future sessions migrate global_settings + the rest of the
    # project surface; see the MIGRATION-PATTERN doc's "WHEN" section.
    project_typed = Project.model_validate(project)
    scene = next((s for s in project_typed.scenes if s.id == sid), None)
    if not scene:
        return jsonify({"error": "Scene not found"}), 404

    chars = [c for c in project_typed.characters if c.id in scene.characters_present]
    lang = project.get("global_settings", {}).get("language", "English")
    lines = generate_dialogue(scene.model_dump(), [c.model_dump() for c in chars], scene.mood or "neutral", language=lang)
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

    # P1-3 part 3 migration (second canonical example): scene lookup +
    # characters filter + location lookup via typed access. Same template
    # as Session 10's api_generate_dialogue migration (web_server.py:1113);
    # see docs/MIGRATION-PATTERN-pydantic-caller.md for the full recipe.
    #
    # `settings` and `style_rules` (mid-level dict access on global_settings)
    # remain on raw dict per template's "migrate top-level scene/character
    # /location access only" choice — global_settings has its own future
    # migration session, not bundled here.
    project_typed = Project.model_validate(project)
    scene_typed = next((s for s in project_typed.scenes if s.id == sid), None)
    if scene_typed is None:
        return jsonify({"error": "Scene not found"}), 404

    chars = [c for c in project_typed.characters if c.id in scene_typed.characters_present]
    location_typed = next(
        (l for l in project_typed.locations if l.id == scene_typed.location_id),
        None,
    )
    settings = project.get("global_settings", {})
    style_rules = settings.get("style_rules", {})

    shots = decompose_scene(
        scene_typed.model_dump(),
        [c.model_dump() for c in chars],
        location_typed.model_dump() if location_typed else {},
        settings,
        style_rules,
    )
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

    # Atomic check-then-reserve under the lock. _PIPELINE_PENDING acts as
    # "busy" to other readers while CinemaPipeline.__init__ runs WITHOUT
    # holding the lock (ctor takes 100ms–2s; holding the lock would
    # serialize all /generate calls globally).
    # Audit ref: docs/AUDIT-P3-1-concurrency-2026-05-24.md Finding #1
    with _pipelines_lock:
        if pid in _running_pipelines:
            return jsonify({"error": "Generation already in progress"}), 409
        _running_pipelines[pid] = _PIPELINE_PENDING

    # Create progress queue for SSE (lock released before this call)
    q = _ensure_progress_queue(pid)
    progress_cb = _make_progress_cb(pid, q)

    resume = request.json.get("resume", False) if request.is_json else False

    def run_pipeline():
        try:
            pipeline = CinemaPipeline(pid, core=_get_or_build_core(pid), progress_callback=progress_cb)
            with _pipelines_lock:
                _running_pipelines[pid] = pipeline  # replace sentinel with real pipeline
            result = pipeline.generate(resume=resume)
            q.put({"stage": "DONE", "detail": result or "Failed", "percent": 100})
        except Exception as e:
            import traceback
            traceback.print_exc()
            q.put({"stage": "ERROR", "detail": str(e), "percent": 0})
        finally:
            # Session 9 review fix: cleanup of BOTH dicts under the same
            # lock that _ensure_progress_queue takes. Since both surfaces
            # now share _pipelines_lock, leaving queue-cleanup unguarded
            # re-opens the race the lock was added to close (a concurrent
            # _ensure_progress_queue could see the queue mid-pop and return
            # a popped reference).
            with _pipelines_lock:
                _running_pipelines.pop(pid, None)
                # Bundle-C 3.2 (2026-05-24): release the queue so we don't
                # grow _progress_queues unboundedly across runs. Drop only
                # this run's queue; if another /generate raced and replaced
                # the entry, leave it. The `is q` identity check is preserved
                # — it correctly does nothing if a replacement landed.
                if _progress_queues.get(pid) is q:
                    _progress_queues.pop(pid, None)
            q.put(None)  # Signal end of stream (intentionally outside the lock — q.put doesn't touch shared dicts)

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()

    return jsonify({"started": True, "resume": resume, "message": "Generation started. Connect to /api/projects/<pid>/stream for progress."})


@app.route("/api/projects/<pid>/checkpoint")
def api_checkpoint(pid):
    """Check if a resumable checkpoint exists for this project."""
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    # Lightweight path — reads the checkpoint JSON directly. No need to
    # construct CinemaPipeline (with its ContinuityEngine + ChiefDirector
    # + LLMEnsemble + tracker instantiation) just to read a JSON file.
    return jsonify(checkpoint_info(pid))


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
    pipeline = _get_running_pipeline(pid)
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


@app.route("/api/projects/<pid>/shots/<shot_id>/plan/approve", methods=["POST"])
@_project_lock_guard
def api_approve_shot_plan(pid, shot_id):
    try:
        result = _get_stage_pipeline(pid).approve_shot_plan(shot_id, approved=True)
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    if result.get("error"):
        return jsonify(result), 404
    return jsonify({"approved": True, **result})


@app.route("/api/projects/<pid>/shots/<shot_id>/plan/reject", methods=["POST"])
@_project_lock_guard
def api_reject_shot_plan(pid, shot_id):
    reason = request.json.get("reason", "") if request.is_json else ""
    try:
        result = _get_stage_pipeline(pid).approve_shot_plan(shot_id, approved=False, reason=reason)
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    if result.get("error"):
        return jsonify(result), 404
    return jsonify({"rejected": True, **result})


@app.route("/api/projects/<pid>/shots/<shot_id>/keyframes/generate", methods=["POST"])
@_project_lock_guard
def api_generate_keyframe(pid, shot_id):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    scene, _shot = _locate_shot(project, shot_id)
    if not scene:
        return jsonify({"error": "Shot not found"}), 404

    data = request.json if request.is_json else {}
    try:
        result = _get_stage_pipeline(pid).generate_keyframe_take(
            scene["id"],
            shot_id,
            positive_prompt=data.get("positive_prompt"),
            negative_prompt=data.get("negative_prompt"),
        )
    except ValueError:
        return jsonify({"error": "Project not found"}), 404

    status = 200 if result.get("success") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/keyframes/<take_id>/approve", methods=["POST"])
@_project_lock_guard
def api_approve_keyframe_take(pid, shot_id, take_id):
    try:
        result = _get_stage_pipeline(pid).approve_take(shot_id, take_id, "keyframe")
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    status = 200 if not result.get("error") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/performance/<take_id>/approve", methods=["POST"])
@_project_lock_guard
def api_approve_performance_take(pid, shot_id, take_id):
    """Approve a performance take so the PERFORMANCE_REVIEW gate predicate opens.

    Symmetric with the keyframe + final approve routes. The orchestrator's
    _wait_for_gate("PERFORMANCE_REVIEW", ...) polls cinema/review/controller.py's
    _gate_satisfied("PERFORMANCE_REVIEW", ...) every 500ms; this endpoint
    persists the approval onto project.json so the predicate flips to True.
    """
    try:
        result = _get_stage_pipeline(pid).approve_take(shot_id, take_id, "performance")
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    status = 200 if not result.get("error") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/motion/generate", methods=["POST"])
@_project_lock_guard
def api_generate_motion(pid, shot_id):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    scene, _shot = _locate_shot(project, shot_id)
    if not scene:
        return jsonify({"error": "Shot not found"}), 404

    try:
        result = _get_stage_pipeline(pid).generate_motion_take(scene["id"], shot_id)
    except ValueError:
        return jsonify({"error": "Project not found"}), 404

    status = 200 if result.get("success") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/final/<take_id>/approve", methods=["POST"])
@_project_lock_guard
def api_approve_final_take(pid, shot_id, take_id):
    try:
        result = _get_stage_pipeline(pid).approve_take(shot_id, take_id, "final")
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    status = 200 if not result.get("error") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/takes/<take_id>/iterate", methods=["POST"])
@_project_lock_guard
def api_iterate_take(pid, shot_id, take_id):
    """S16: directorial iteration endpoint.

    Accepts an operator's directorial intent (DirectorialIntent JSON body),
    calls ``ShotController.regenerate_with_intent``, and returns the new take.

    Feature-flagged behind CINEMA_DIRECTORIAL_ITERATION. Default ON as
    of v5.1+ flag-flip (2026-05-26); set ``CINEMA_DIRECTORIAL_ITERATION=0``
    to opt out. Returns 404 when explicitly disabled (mirrors §7.7.3
    endpoint-level gate).

    Route is pid-scoped per cycle-6 Lane V F1 convention — `sid` is
    ``shot_{scene}_{i}`` and can collide across projects.

    Body (JSON):
        {
            "prose": "tighten the framing on the face",
            "verb": null,            # optional
            "params": {},            # optional
            "refs": [],              # optional
            "target_stage": "keyframe"  # keyframe|performance|motion
        }

    Response (success): 200 + ``{success: true, take: {...}}``
    Response (feature disabled): 404 + ``{error: "..."}``
    Response (validation error): 400 + ``{error: "..."}``
    Response (shot/take not found): 404 + ``{error: "..."}``
    Response (downstream error): 409 + ``{error: "..."}``
    """
    from cinema.shots.controller import _directorial_iteration_enabled
    if not _directorial_iteration_enabled():
        return jsonify({"error": "Directorial iteration is disabled (unset CINEMA_DIRECTORIAL_ITERATION or set to a non-falsy value)"}), 404

    # Mirror every other mutating endpoint's project-busy fence: an iterate
    # call dispatches a long-running LLM + generator pipeline, which must not
    # race a concurrent pipeline worker on the same project. Both S16 reviewers
    # (spec + code-quality) flagged this absence as the S16 release blocker.
    #
    # Lane V #8 I1 (cycle 10, 2026-05-26): use the gate-aware variant —
    # operator MUST be able to iterate during review-gate waits (SCREENING,
    # KEYFRAME_REVIEW, PERFORMANCE_REVIEW, REVIEW, PLAN_REVIEW). The
    # pipeline worker is blocked at lifecycle.wait_for_gate, not actively
    # running steps. Mirrors the explicit bypasses at api_screening_approve
    # and api_assemble_reassemble. Without this, Surface A iterate is broken
    # at any review gate AND Surface B's iterate-during-screening flow is
    # entirely unreachable behind the flag combination as shipped.
    busy_response = _reject_if_project_busy_outside_gate(pid)
    if busy_response:
        return busy_response

    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    data = request.get_json() or {}
    # F1 accept-both (operator Lane V #4, decision 2026-05-25T15-49-12Z):
    # spec sketched nested `{intent: {prose, ...}}`, impl shipped flat
    # `{prose, ...}`. Accept either shape — if the body has an `intent`
    # key holding the DirectorialIntent fields, unwrap; otherwise treat
    # the body itself as the intent. Forward-compat with no breaking
    # change to the 16 existing tests (which all use the flat shape).
    # Precedence (G1): nested wins when both nested `intent` AND flat
    # fields are present — the rare ambiguous case routes to nested.
    payload = data.get("intent", data) if isinstance(data, dict) and isinstance(data.get("intent"), dict) else data
    try:
        intent = DirectorialIntent.model_validate(payload)
    except Exception as exc:
        return jsonify({"error": f"Invalid intent body: {exc}"}), 400

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Cross-scene shot lookup via typed access (P1-3 part 6 pattern at b28b8b4).
    # Semantically equivalent to `scene, _ = _locate_shot(project, shot_id);
    # scene_id = scene["id"]` used by api_generate_motion / api_approve_final_take,
    # but the typed form preserves the Project.model_validate validation boundary
    # for CINEMA_STRICT_SCHEMA mode. Operator Lane V #4 M-2 flagged the
    # divergence; intentional — sibling consistency would lose validation.
    project_typed = Project.model_validate(project)
    scene_id = next(
        (s.id for s in project_typed.scenes if any(sh.id == shot_id for sh in s.shots)),
        None,
    )
    if not scene_id:
        return jsonify({"error": "Shot not found in project"}), 404

    try:
        result = _get_stage_pipeline(pid).regenerate_with_intent(
            scene_id,
            shot_id,
            take_id,
            intent,
            project_id=pid,
        )
    except ValueError:
        return jsonify({"error": "Project not found"}), 404

    status = 200 if result.get("success") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/reject-auto-approve", methods=["POST"])
@_project_lock_guard
def api_reject_auto_approve(pid, shot_id):
    """Override an auto-approve decision for a specific gate on a shot.

    Body (JSON): { "gate": "plan"|"image"|"motion"|"final", "reason": "<free text>" }

    Records the rejection as an audit entry with auto_approved=False,
    rule_names=["user_override"], vetoes=[reason], and clears the
    <gate>_auto_approved flag. No separate storage — the audit log IS the
    persistence layer (per S13 brief §Decisions).

    Route includes /projects/<pid>/ per cycle-6 Lane V F1 finding
    (shot_id is `shot_{scene}_{i}` and collides across projects with
    matching layouts; pid-less scan-all-projects design could mutate
    the wrong project or 423 on unrelated lock contention). Mirrors the
    existing `_mutate_shot`-style endpoints (api_update_shot_prompt,
    api_approve_final_take, etc.).
    """
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    data = request.get_json() or {}
    gate = data.get("gate")
    reason = (data.get("reason") or "").strip()

    valid_gates = {"plan", "image", "motion", "final"}
    if gate not in valid_gates:
        return jsonify({"error": "invalid gate"}), 400
    if not reason:
        return jsonify({"error": "reason required"}), 400

    audit_entry = {
        "gate": gate,
        "auto_approved": False,
        "vetoes": [reason],
        "rule_names": ["user_override"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    flag_key = f"{gate}_auto_approved"

    def _mutate_project(project: dict):
        for scene in project.get("scenes", []):
            for shot in scene.get("shots", []):
                if shot.get("id") == shot_id:
                    shot.setdefault("auto_approve_audit", []).append(audit_entry)
                    shot[flag_key] = False
                    return MutationResult({"shot_id": shot_id, "gate": gate}, save=True)
        return MutationResult(False, save=False)

    result = mutate_project(pid, _mutate_project, timeout=HTTP_PROJECT_TIMEOUT)
    if result is None:
        return jsonify({"error": "Project not found"}), 404
    if result:
        return jsonify({"status": "ok", "shot_id": shot_id, "gate": gate})

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
    """Update shot fields used by the guided shot editor."""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    data = request.json
    allowed_fields = {
        "target_api",
        "camera",
        "visual_effect",
        "prompt",
        "scene_foley",
        "negative_constraints",
        "continuity_constraints",
        "intent_notes",
    }
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
    pipeline = _get_running_pipeline(pid)
    if pipeline:
        pipeline.pause()
        return jsonify({"paused": True})
    return jsonify({"error": "No generation in progress"}), 404


@app.route("/api/projects/<pid>/resume", methods=["POST"])
def api_resume(pid):
    """Resume a paused pipeline."""
    pipeline = _get_running_pipeline(pid)
    if pipeline:
        pipeline.resume()
        return jsonify({"resumed": True})
    return jsonify({"error": "No generation in progress"}), 404


@app.route("/api/projects/<pid>/pipeline-state")
def api_pipeline_state(pid):
    """Get current pipeline execution state."""
    pipeline = _get_running_pipeline(pid)
    if pipeline:
        return jsonify(pipeline.get_state())
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found", "paused": False, "cancelled": False}), 404
    # Lightweight path — replicates get_state() shape without spinning
    # up CinemaPipeline's heavy ctor.
    return jsonify(state_snapshot(pid))


@app.route("/api/projects/<pid>/shots/<shot_id>/restart", methods=["POST"])
@_project_lock_guard
def api_restart_shot(pid, shot_id):
    """Full restart for a shot: clear every downstream approval, regenerate
    the keyframe. Take history is preserved; only approval pointers are reset.
    Pairs with the UI's 'Regenerate' button (vs 'Generate another keyframe'
    which adds a candidate take into the existing array). Optional body:
    {positive_prompt, negative_prompt} — if positive_prompt is set, it
    replaces the shot's stored prompt before regeneration."""
    pipeline = _get_running_pipeline(pid)
    payload = request.json if request.is_json else {}
    positive_prompt = (payload or {}).get("positive_prompt")
    negative_prompt = (payload or {}).get("negative_prompt")

    def _resolve_scene_id(project: dict):
        for scene in project["scenes"]:
            for shot in scene.get("shots", []):
                if shot.get("id") == shot_id:
                    return MutationResult(scene["id"], save=False)
        return MutationResult(False, save=False)

    scene_id = mutate_project(pid, _resolve_scene_id, timeout=HTTP_PROJECT_TIMEOUT)
    if scene_id is None:
        return jsonify({"error": "Project not found"}), 404
    if scene_id is False:
        return jsonify({"error": "Shot not found"}), 404

    if pipeline:
        result = pipeline.restart_shot(scene_id, shot_id, positive_prompt, negative_prompt)
        return jsonify(result)

    try:
        temp_pipeline = CinemaPipeline(pid, core=_get_or_build_core(pid), progress_callback=_make_progress_cb(pid))
        result = temp_pipeline.restart_shot(scene_id, shot_id, positive_prompt, negative_prompt)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/projects/<pid>/shots/<shot_id>/regenerate", methods=["POST"])
@_project_lock_guard
def api_regenerate_shot(pid, shot_id):
    """Regenerate a single shot. Supports positive_prompt and negative_prompt."""
    pipeline = _get_running_pipeline(pid)
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

    try:
        temp_pipeline = CinemaPipeline(pid, core=_get_or_build_core(pid), progress_callback=_make_progress_cb(pid))
        result = temp_pipeline.regenerate_shot(scene_id, shot_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/projects/<pid>/shots/<shot_id>/correct", methods=["POST"])
@_project_lock_guard
def api_correct_shot(pid, shot_id):
    """Apply a correction tool to a clip during Director's Cut review."""
    data = request.json if request.is_json else {}
    action = data.get("action", "")
    params = data.get("params", {})
    take_id = data.get("take_id", "")

    if not action:
        return jsonify({"error": "Missing 'action' field"}), 400

    try:
        result = _get_stage_pipeline(pid).apply_correction(shot_id, action, params, take_id=take_id)
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    status = 200 if result.get("success") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/diagnose", methods=["POST"])
def api_diagnose_shot(pid, shot_id):
    """Run quality diagnostics on a clip."""
    take_id = request.json.get("take_id", "") if request.is_json else ""
    try:
        result = _get_stage_pipeline(pid).diagnose_clip(shot_id, take_id=take_id)
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(result)


@app.route("/api/projects/<pid>/assemble", methods=["POST"])
@app.route("/api/projects/<pid>/proceed-assembly", methods=["POST"])
def api_proceed_assembly(pid):
    """Assemble only from approved final takes, or resume the paused batch wrapper."""
    pipeline = _get_running_pipeline(pid)
    if not pipeline:
        try:
            result = CinemaPipeline(pid, core=_get_or_build_core(pid), progress_callback=_make_progress_cb(pid)).assemble_approved_takes()
        except ValueError:
            return jsonify({"error": "Project not found"}), 404
        status = 200 if result.get("success") else 409
        return jsonify(result), status

    result = pipeline.proceed_to_assembly()
    status = 200 if result.get("success") else 409
    return jsonify(result), status


# ---------------------------------------------------------------------------
# S19 (cycle-9 Surface B): SCREENING stage endpoints
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/assemble/screen", methods=["POST"])
@_project_lock_guard
def api_assemble_screen(pid):
    """S19: read-only fetch of the assembled mp4 + per-shot timeline manifest.

    Feature-flagged behind CINEMA_SCREENING_STAGE. Default ON as of
    v5.1+ flag-flip (2026-05-26); set ``CINEMA_SCREENING_STAGE=0`` to opt
    out. Returns 404 when explicitly disabled (mirrors §7.7.3 endpoint-level
    gate convention shared with the directorial-iteration endpoint).

    Route is pid-scoped per cycle-6 Lane V F1 convention -- no list_projects
    scan; the pid travels through the URL and is the only project the
    endpoint touches.

    Response (success): 200 + {
        "success": true,
        "assembled_mp4_path": "<absolute_path_to_final_cinema.mp4>",
        "timeline_manifest": [{shot_id, scene_id, start_s, end_s,
                               approved_take_id, take_count}, ...],
    }
    Response (feature disabled): 404 + {"error": "..."}
    Response (project not found): 404 + {"error": "Project not found"}
    Response (assembled mp4 missing): 409 + {"error": "..."} -- the operator
        called /screen before assembly finished (or after the cinema dir
        was cleaned up).
    Response (project busy with active generation): 409 + project_busy.
    """
    from cinema.screening import _screening_stage_enabled, _build_timeline_manifest

    if not _screening_stage_enabled():
        return jsonify({"error": "Screening stage is disabled (unset CINEMA_SCREENING_STAGE or set to a non-falsy value)"}), 404

    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # The assembled mp4 lives at <project_export_dir>/final_cinema.mp4 per
    # _assemble_final at cinema_pipeline.py:911. We mirror the same path
    # construction here (rather than reading it off the running pipeline,
    # which may be None for a project whose pipeline already terminated)
    # so the endpoint is a pure read against on-disk state.
    # (Lane V #7 H3 fold) The previous try/except ImportError shim was
    # dead defensive cruft: ``project_manager.py`` is a 9-line re-export
    # of ``domain.project_manager``, so the canonical import resolves
    # unconditionally.
    from domain.project_manager import get_project_dir
    export_dir = os.path.join(get_project_dir(pid), "exports")
    assembled_path = os.path.join(export_dir, "final_cinema.mp4")
    if not os.path.exists(assembled_path):
        return jsonify({
            "success": False,
            "error": f"Assembled video not found at {assembled_path}. Run /assemble first.",
        }), 409

    # verify_files=True enforces the strict mirror of _build_scene_packages
    # (cinema_pipeline.py:544-548) so the operator's timeline scrubber never
    # lands on a phantom shot whose mp4 was deleted between assembly and
    # screening. Post code-quality review of cycle-9 S19.
    manifest = _build_timeline_manifest(project, verify_files=True)

    # S21 (cycle-9 Surface B): surface dirty-shot tracking + re-assembly
    # cost preview alongside the manifest so the operator's "Re-assemble"
    # button can render its label ("Re-assemble (3 shots dirty)") + tooltip
    # ("~45s estimated") without a second round-trip. Tightly coupled to
    # the manifest itself -- both describe "what would be in the next cut."
    from cinema.screening import (
        get_needs_reassembly,
        estimate_reassembly_cost,
    )
    return jsonify({
        "success": True,
        "assembled_mp4_path": assembled_path,
        "timeline_manifest": manifest,
        "needs_reassembly": get_needs_reassembly(project),
        "cost_estimate_seconds": estimate_reassembly_cost(project)["seconds"],
    }), 200


@app.route("/api/projects/<pid>/screening/approve", methods=["POST"])
@_project_lock_guard
def api_screening_approve(pid):
    """S19: operator signals "approve final cut" -- sets the SCREENING gate flag.

    Sets ``project.screening_approved = True`` on disk via mutate_project,
    then nudges the lifecycle's per-gate event so any pipeline that's
    polling at SCREENING wakes up promptly (instead of waiting out the
    next poll_interval tick).

    Feature-flagged behind CINEMA_SCREENING_STAGE. Default ON as of
    v5.1+ flag-flip; set ``CINEMA_SCREENING_STAGE=0`` to opt out.
    Returns 404 when explicitly disabled.

    Response (success): 200 + {"success": true, "screening_approved": true}
    Response (feature disabled): 404
    Response (project not found): 404
    Response (project busy retry-conflict): 409 project_busy
    """
    from cinema.screening import (
        SCREENING_STAGE_NAME,
        _screening_stage_enabled,
        mark_screening_approved,
    )

    if not _screening_stage_enabled():
        return jsonify({"error": "Screening stage is disabled (unset CINEMA_SCREENING_STAGE or set to a non-falsy value)"}), 404

    # NOTE: we deliberately do NOT call _reject_if_project_busy here.
    # /screening/approve is the operator's exit-signal for the gate the
    # busy pipeline is waiting on -- refusing it on "project_busy" would
    # deadlock the pipeline (it can never approve, because it's busy
    # waiting for approval). The mutation itself is atomic via
    # mutate_project's per-project file lock, which is the right
    # serialisation primitive here.

    # V1 (Val#1 cycle-10 — operator-validation finding at 18beb92):
    # precondition check mirroring /assemble/screen's same-condition
    # check (lines 1980-1987 above). Without this, /screening/approve
    # cheerfully succeeded on an empty project that never had an
    # assembled cut — permanently flipping the persistent screening_approved
    # gate-flag and effectively skipping SCREENING on the next pipeline
    # run for that project. Defense-in-depth: the UI gates the button
    # correctly per spec §4.2 step 5, but URL-level callers (curl typos,
    # scripts, bots) had no backstop.
    from domain.project_manager import get_project_dir
    export_dir = os.path.join(get_project_dir(pid), "exports")
    assembled_path = os.path.join(export_dir, "final_cinema.mp4")
    if not os.path.exists(assembled_path):
        return jsonify({
            "success": False,
            "error": f"Cannot approve screening; no assembled cut exists at {assembled_path}. Run /assemble/screen first.",
            "code": "cannot_approve_screening",
        }), 409

    try:
        result = mark_screening_approved(pid)
    except ValueError:
        return jsonify({"error": "Project not found"}), 404

    # Wake any pipeline that's polling the SCREENING gate so it picks up
    # the flag-flip on this iteration rather than the next poll tick.
    # Best-effort: a project with no live pipeline (operator approved
    # before pipeline reached SCREENING, or after it already proceeded)
    # is a silent no-op here.
    pipeline = _get_running_pipeline(pid)
    if pipeline is not None:
        try:
            pipeline.lifecycle.signal_gate(SCREENING_STAGE_NAME)
        except AttributeError:
            # NullLifecycle / older lifecycle implementations may not
            # expose signal_gate. Polling-only fallback still works --
            # the predicate will pick up the flag on the next poll.
            pass

    return jsonify(result), 200


@app.route("/api/projects/<pid>/assemble/re-assemble", methods=["POST"])
@_project_lock_guard
def api_assemble_reassemble(pid):
    """S21: re-run the final-assembly pipeline against current approved takes.

    The operator iterated one or more shots during SCREENING, producing
    new takes. The assembled mp4 on disk is now stale relative to the
    project's current approved_final_take_id values. This endpoint
    re-runs ``assemble_approved_takes()`` so the operator can preview
    the updated cut before approving the final.

    Body (JSON, optional):
        {"only_if_changed": bool}
            -- when True (default), short-circuits to a no-op when
               ``project.needs_reassembly`` is empty. When False,
               always re-runs. Useful for an "Re-assemble (force)"
               override in case the operator suspects the dirty-tracking
               was missed (e.g. the implementer's best-effort dirty-set
               write swallowed an exception).

    Feature-flagged behind CINEMA_SCREENING_STAGE. Default ON as of
    v5.1+ flag-flip; set ``CINEMA_SCREENING_STAGE=0`` to opt out.
    Returns 404 when explicitly disabled.

    Response (success): 200 + {
        "success": true,
        "new_assembled_path": "<absolute_path>",
        "regenerated_shots": [shot_id, ...],   # the shots that were dirty
        "cost_estimate_seconds": float,         # the pre-run estimate
        "skipped": bool                         # True iff short-circuited
    }
    Response (feature disabled): 404
    Response (project not found): 404
    Response (re-assembly already in flight for this project): 409 reassembly_busy
    Response (no approved takes / assembly error): 409

    Busy-fence: bypasses ``_reject_if_project_busy`` (the SCREENING gate
    occupies _running_pipelines; busy-fencing would deadlock the operator).
    Instead, a narrower module-level ``_reassembly_in_flight`` set guards
    against re-entrant re-assembly on the same project. The heavyweight
    ffmpeg work runs OUTSIDE that lock; the lock only guards the
    "in-flight?" set membership check + add.
    """
    from cinema.screening import (
        _screening_stage_enabled,
        clear_needs_reassembly,
        estimate_reassembly_cost,
        get_needs_reassembly,
    )

    if not _screening_stage_enabled():
        return jsonify({"error": "Screening stage is disabled (unset CINEMA_SCREENING_STAGE or set to a non-falsy value)"}), 404

    # See module-level _reassembly_in_flight comment for why we don't
    # call _reject_if_project_busy here. Re-entrancy is the actual concern.
    with _reassembly_lock:
        if pid in _reassembly_in_flight:
            return jsonify({
                "code": "reassembly_busy",
                "retryable": True,
                "error": f"Project '{pid}' has a re-assembly in flight. Retry shortly.",
            }), 409
        _reassembly_in_flight.add(pid)

    try:
        data = request.get_json(silent=True) or {}
        only_if_changed = bool(data.get("only_if_changed", True))

        project = load_project(pid)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        dirty_shots = get_needs_reassembly(project)
        cost_estimate = estimate_reassembly_cost(project)["seconds"]

        # Short-circuit: only_if_changed=true AND no dirty shots -> nothing to do.
        # The operator's UI suppresses the button in this state; the endpoint
        # double-checks so a stale-cached UI doesn't trigger a spurious rerun.
        if only_if_changed and not dirty_shots:
            return jsonify({
                "success": True,
                "new_assembled_path": "",
                "regenerated_shots": [],
                "cost_estimate_seconds": cost_estimate,
                "skipped": True,
                "note": "no dirty shots; assembled mp4 is current",
            }), 200

        # Run the full re-assembly. Q5 measurement (S21 spike) showed full
        # re-rerun completes in well under 60s for a 30-shot project at
        # avg 5s/shot (~45s real-world); ~90s for 60 shots. Delta-render
        # was considered (skip-loudnorm preview) but the grade pass
        # dominates the cost curve and skipping it would degrade the
        # preview's fidelity. See commit body for the measurement.
        try:
            # Lane V #8 I2: pass a no-op progress_callback rather than
            # _make_progress_cb(pid). _make_progress_cb resolves the SAME
            # _progress_queues[pid] entry the original gate-waiting pipeline's
            # SSE client is subscribed to. _assemble_approved_takes_core
            # emits SCENE_PREVIEW (86-90%) and ASSEMBLY (92%) events; these
            # would leak into the SSE channel while the UI is at SCREENING
            # (95%) — flipping the visible stage backward, regressing the
            # progress bar, and confusing the operator with unexpected
            # progress chatter. The endpoint's request/response cycle is the
            # operator's status indicator (button → pending → success/error).
            pipeline = CinemaPipeline(
                pid,
                core=_get_or_build_core(pid),
                progress_callback=lambda *args, **kwargs: None,
            )
            # S21 Critical #1 fix: call the helper that runs steps 1-5
            # only (REVIEW gate + scene_packages + previews + _assemble_final).
            # The public ``assemble_approved_takes`` would tail with the
            # SCREENING gate-wait, which would deadlock the Flask request
            # thread: the operator iterating during SCREENING has NOT
            # approved yet (that's the whole point of re-assemble), and
            # ``/screening/approve`` signals only the ORIGINAL running
            # pipeline's lifecycle, not this fresh one. See the docstring
            # on ``_assemble_approved_takes_core`` for the full rationale.
            assembly_result = pipeline._assemble_approved_takes_core()
        except ValueError:
            return jsonify({"error": "Project not found"}), 404

        if not assembly_result.get("success"):
            return jsonify({
                "success": False,
                "error": assembly_result.get("error", "Re-assembly failed"),
                "regenerated_shots": dirty_shots,
                "cost_estimate_seconds": cost_estimate,
            }), 409

        # Clear dirty-tracking AFTER successful re-assembly. If we cleared
        # before and the assembly failed, the operator would have to manually
        # re-iterate the shots to repopulate the dirty list -- bad UX.
        #
        # Lane V #8 I3: pass the snapshot dirty_shots as only_shots so the
        # mutator does a set-diff rather than a full wipe. Any iterate that
        # fires DURING the re-assemble window (~30-90s of ffmpeg work; now
        # reachable once I1's gate-bypass lets iterate-during-screening
        # through) adds new shot_ids via mark_shot_needs_reassembly. Without
        # the snapshot semantics, the post-assembly wipe drops those new
        # entries silently, and the subsequent only_if_changed=true re-assemble
        # would short-circuit on an empty list — silent data loss for the
        # operator's most recent iterate.
        try:
            clear_needs_reassembly(pid, only_shots=dirty_shots)
        except ValueError:
            # Race: project deleted between assemble + clear. Best-effort;
            # the assembled mp4 still exists, so the operator's preview
            # still works.
            logger.warning(
                "Failed to clear needs_reassembly after successful re-assembly",
                extra={"pid": pid},
            )

        return jsonify({
            "success": True,
            "new_assembled_path": assembly_result.get("final_path", ""),
            "regenerated_shots": dirty_shots,
            "cost_estimate_seconds": cost_estimate,
            "skipped": False,
        }), 200
    finally:
        with _reassembly_lock:
            _reassembly_in_flight.discard(pid)


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


@app.route("/api/projects/<pid>/cost-live", methods=["GET"])
def api_cost_live(pid):
    """Sum of cost_log entries for this video_id since pipeline start.

    Returns total_usd rounded to 4 decimal places. Unknown video_id (no
    rows) returns {"total_usd": 0.0} — not a 404 — because Telemetry
    polls this before any cost entries exist.
    """
    try:
        from cost_tracker import CostTracker
        # Re-use the cached PipelineCore's tracker when available so we
        # share the same SQLite connection rather than opening a second one.
        with _cores_lock:
            cached_core = _running_cores.get(pid)
        tracker = cached_core.cost_tracker if cached_core else CostTracker()
        row = tracker.conn.execute(
            "SELECT SUM(cost_usd) AS total FROM cost_log WHERE video_id = ?",
            (pid,),
        ).fetchone()
        total = round(float(row["total"] or 0.0), 4)
        return jsonify({"total_usd": total})
    except Exception as exc:
        print(f"[cost-live] query failed for pid={pid}: {exc}")
        return jsonify({"error": "Cost query failed"}), 500


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
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    bind_host = env_settings.web_bind_host
    cors_origins = env_settings.web_cors_origins
    lan_note = (
        "  ⚠ Bound to 0.0.0.0 — reachable from any device on this network. "
        "Set WEB_BIND_HOST=127.0.0.1 to limit to this machine.\n"
        if bind_host == "0.0.0.0"
        else ""
    )
    cors_note = (
        "  ⚠ CORS=* (wide open) — any origin can call the API. "
        "Unset WEB_CORS_ORIGINS to restore localhost-only default.\n"
        if cors_origins == ("*",)
        else ""
    )

    print("\n" + "=" * 60)
    print("🎬 CINEMA PRODUCTION TOOL — Web Server")
    print("=" * 60)
    print(f"Open http://localhost:8080 in your browser")
    print(f"  bind:  {bind_host}:8080")
    print(f"  CORS:  {', '.join(cors_origins)}")
    if lan_note or cors_note:
        print()
        if lan_note:
            print(lan_note, end="")
        if cors_note:
            print(cors_note, end="")
    print("=" * 60 + "\n")
    app.run(host=bind_host, port=8080, debug=False, use_reloader=False)
