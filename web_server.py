"""
Cinema Production Tool — Flask Web Server
Dashboard API with SSE streaming for real-time generation progress.
Serves the React frontend and exposes all project/character/location/scene endpoints.
"""

# IMPORT ORDER CONTRACT -- this must stay the first import in this module.
#
# TensorFlow and PyArrow both vendor Abseil (lts_20250814) and export the same
# symbols. macOS binds the first-loaded copy process-wide, and pandas pulls
# PyArrow in (pandas/compat/pyarrow.py) long before deepface pulls TensorFlow
# (deepface/DeepFace.py). When that happens, TensorFlow's
# absl::Notification::WaitForNotification() waits on libarrow's Abseil while the
# notification is signalled in TensorFlow's own -- the wake-up can never arrive.
#
# Measured on this machine: identity scoring hung indefinitely at 0% CPU with
# the main thread in Mutex::Block via libarrow.2400.dylib, and no timeout exists
# on that path, so an experiment cell stays "running" forever. With TensorFlow
# imported first the same scoring call completes in 3.6s.
#
# Guarded because TensorFlow is an optional dependency: environments without
# deepface must still start the server.
try:  # pragma: no cover - depends on whether deepface/TensorFlow is installed
    import tensorflow  # noqa: F401  (imported for load order, not for use)
except Exception:  # pragma: no cover - absence is fine; collision is not
    pass

import atexit
import hashlib
import logging
import math
import mimetypes
import os
import re
import shutil
import tempfile
import uuid
import warnings
from collections import Counter, deque
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
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

logger = logging.getLogger(__name__)

import json
import threading
import queue
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory, Response, send_file
from flask_cors import CORS
from filelock import FileLock, Timeout as FileLockTimeout
from werkzeug.utils import secure_filename
from project_manager import (
    MutationResult, ProjectLockError, create_project, load_project, delete_project,
    is_safe_project_id, list_projects, load_existing_project_readonly,
    mutate_project,
    add_character, remove_character, add_location, remove_location,
    add_object, remove_object, get_object,
    add_scene, remove_scene, reorder_scenes,
    make_character, make_location, make_object, make_scene, get_project_dir,
)
from character_manager import create_character_with_images, VOICE_POOL
from location_manager import create_location_with_images
from scene_decomposer import decompose_scene, update_scene_shots, CAMERA_MOTIONS, VISUAL_EFFECTS, TARGET_APIS, API_REGISTRY, MUSIC_MOODS
from domain.models import DirectorialIntent, Project, Shot
from domain.character_manager import _to_project_relative
from domain.optimizer_cache import optimizer_cache_is_valid
from domain.flux2_candidate import flux2_candidate_status
from performance.worker_readiness import (
    PerformanceWorkerUnavailable,
    require_flux2_worker_ready,
)
from domain.scene_decomposer import PURPOSE_TAGS, PURPOSE_API_RANKING, BILLING_PROVIDERS, estimate_short_cost
from dialogue_writer import generate_dialogue
from llm.style_director import generate_style_rules
from cinema_pipeline import CinemaPipeline
from cinema.aspect import SUPPORTED_ASPECT_RATIOS, is_supported, DEFAULT_ASPECT_RATIO
from cinema.core import PipelineCore, build_pipeline_core
from cinema.services import state_snapshot, checkpoint_info
from cinema.trace_store import trace_context
from domain.provider_catalog import CATALOG, Modality, RuntimeSnapshot
from domain.video_engine_policy import (
    VideoPolicyReason,
    VideoTargetPolicyError,
    build_runtime_snapshot,
    evaluate_shot_target,
)
from workflow_selector import WORKFLOW_TEMPLATES
from web_services import make_progress_callback
from config.settings import settings as env_settings
from paid_provider import PaidCallBudgetBlocked, PaidCallDeferred, PaidCallUnbilled
from performance._net import validate_video_artifact
from cinema.artifact_versions import ArtifactVersionError
from cinema.artifact_indexing import record_auxiliary_version
from pipeline_jobs import (
    JobExecutionContext,
    PipelineJob,
    PipelineJobDispatcher,
    PipelineJobStore,
    safe_error_summary,
)
from web_observability import observability_api
from web_artifacts import artifact_api
from web_gpu_workers import gpu_workers_api
from web_gpu_worker_control import gpu_worker_control_api
from web_identity_experiments import (
    configure_identity_project_guard,
    identity_character_has_active_experiment,
    identity_experiment_api,
    identity_project_has_active_experiment,
)
from web_project_operation_lock import project_operation_lock
app = Flask(__name__, static_folder="web/dist", static_url_path="")
# CORS allowlist comes from settings.web_cors_origins. Default is
# localhost-only ("http://localhost:8080" + "http://localhost:5173" for
# Vite dev). To opt back into the pre-hardening wide-open behavior,
# set WEB_CORS_ORIGINS=* in .env. Bound by env to support LAN/multi-device
# use cases via WEB_CORS_ORIGINS=http://localhost:8080,http://<lan-ip>:8080.
CORS(app, origins=list(env_settings.web_cors_origins))
app.register_blueprint(observability_api)
app.register_blueprint(artifact_api)
app.register_blueprint(gpu_workers_api)
app.register_blueprint(gpu_worker_control_api)
app.register_blueprint(identity_experiment_api)

# ---------------------------------------------------------------------------
# Broadcast-safe SSE event fan-out with replay (Slice 11a)
# ---------------------------------------------------------------------------
#
# Replaces the pre-11a design where every project had exactly ONE
# queue.Queue and every /stream subscriber called .get() on it directly:
# since a queue.Queue hands each item to exactly one getter, two concurrent
# listeners competed for the same events (one "steals" what the other
# should also have seen) instead of each observing every event, and there
# was no event history at all, so a reconnecting client could not recover
# anything it missed while disconnected.
#
# Wire contract (also consumed by web/src/hooks/useSSE.ts and future
# 11b/11c reconnect/resume work):
#
#   * Every published event is assigned a monotonically increasing integer
#     id, scoped to one _ProjectEventBus instance -- i.e. one /generate
#     run's lifetime. A fresh run gets a fresh bus and fresh id numbering,
#     exactly like today's fresh-queue-per-run; ids are NOT durable across
#     separate runs of the same project.
#   * The id is emitted twice on the wire: as the standard SSE `id:` framing
#     line (so `EventSource.lastEventId` / a browser's own silent automatic
#     reconnect keeps working) AND inlined as `"id"` in the JSON `data:`
#     body, for a client that only reads `data:` and manages reconnection
#     itself -- which is what today's useSSE.ts does (it closes and
#     constructs a brand-new EventSource on backoff, which does NOT
#     preserve the browser's own last-event-id bookkeeping). Control
#     frames (GAP/END/HEARTBEAT) carry no id -- they are wire-only
#     notices, never stored or replayed, so they must never advance a
#     client's replay position.
#   * A subscriber resumes from a specific point via the standard
#     `Last-Event-ID` request header (case-insensitive; read through
#     Werkzeug's header mapping) or, as a fallback for a manually
#     reconnecting client that cannot rely on the browser's own header, a
#     `?last_event_id=` query parameter. The header wins if both are
#     present. Malformed/absent input is treated as "no known position"
#     (the snapshot path below) rather than a 400 -- a client with a
#     garbled id still deserves a stream, just without replay.
#   * Known position still inside the replay buffer: every buffered event
#     with id > N replays, in order, each tagged `"replayed": true`, then
#     live delivery continues. No duplicates, nothing silently dropped.
#   * Known position OLDER than the oldest buffered id (evicted by the
#     cap): one `{"stage": "GAP", "gap_from": ..., "gap_to": ...}` event
#     emits first, naming the lost id range, THEN every still-buffered
#     event newer than N replays as above. Data that aged out is reported,
#     never silently skipped.
#   * No known position (fresh subscriber -- first visit, or a client that
#     never persisted an id): one snapshot event sends -- a verbatim
#     replay of the single latest published event (if any yet exist),
#     tagged `"replayed": true` and carrying its real id -- so a late
#     joiner can render current truth immediately without replaying the
#     whole run from event 1. Reconnecting later with that id as
#     Last-Event-ID replays nothing further unless newer events have since
#     landed.
#   * The replay buffer is capped at _EVENT_REPLAY_CAP entries per project
#     (bounded memory); older entries are evicted first (FIFO via
#     `deque(maxlen=...)`).
#   * FIX-SSE: each subscriber's LIVE delivery inbox (as opposed to the
#     shared replay buffer above) is ALSO bounded, at _SUBSCRIBER_INBOX_CAP.
#     Before this, a client that opened /stream and never read its HTTP
#     response accumulated every published event in server memory for the
#     run's lifetime -- unbounded per subscriber, multiplied by however many
#     such clients attached. On overflow the oldest still-undelivered entry
#     for THAT subscriber (and only that one) is dropped to make room; the
#     drop is never silent -- the next live delivery to that subscriber is
#     preceded by the same `{"stage": "GAP", "gap_from": ..., "gap_to": ...}`
#     notice the reconnect-past-the-cap path above produces, so the client
#     knows to re-sync. Delivery (publish() and close()) is always non-
#     blocking: a slow/stalled subscriber can never stall the publisher,
#     close(), or any OTHER subscriber. See _ProjectEventBus._deliver.

_EVENT_REPLAY_CAP = 500  # ~500 small JSON dicts/project; bounded, documented.
_SUBSCRIBER_INBOX_CAP = 500  # FIX-SSE: bounds each subscriber's live-delivery
# inbox so a client that never reads /stream can't grow server memory without
# limit; same order of magnitude as _EVENT_REPLAY_CAP -- a subscriber this far
# behind is already as stale as a fresh reconnect, so degrading it the same
# way (drop oldest + explicit GAP) loses nothing a reconnect wouldn't already.


@dataclass(frozen=True)
class _EventSubscription:
    """One /stream subscriber's attachment to a _ProjectEventBus.

    sub_id:  opaque handle passed back to unsubscribe().
    inbox:   this subscriber's PRIVATE queue -- future publishes land here
             (never shared with any other subscriber). Bounded at
             _SUBSCRIBER_INBOX_CAP (FIX-SSE); see _ProjectEventBus._deliver
             for the drop-oldest-and-GAP overflow contract.
    backlog: [(id, event), ...] to replay, in order, before live delivery;
             empty when there's nothing to replay.
    gap:     (first_lost_id, last_lost_id) inclusive, or None -- set when
             the requested resume point aged out of the replay buffer.
    closed:  True if the bus was already closed at subscribe time -- the
             route must emit backlog/gap then immediately end the stream
             rather than block on `inbox` (the close() broadcast already
             ran and will never wake a subscriber that attached after it).
    """

    sub_id: int
    inbox: "queue.Queue"
    backlog: list[tuple[int, dict]]
    gap: tuple[int, int] | None
    closed: bool


class _ProjectEventBus:
    """Per-project broadcast fan-out with a bounded, replayable event log.

    Thread-safety: one lock guards `_buffer`, `_next_id`, `_subscribers`,
    `_gaps`, and `closed`. Delivery (via `_deliver`) always happens OUTSIDE
    the lock so a slow or already-abandoned subscriber queue can never
    block a publish, a subscribe, or an unsubscribe on another thread.

    FIX-SSE: each subscriber's own inbox is bounded (`_inbox_cap`, default
    _SUBSCRIBER_INBOX_CAP) -- previously unbounded, so a subscriber that
    never drained its /stream response grew server memory by one event
    per publish for as long as the run lasted. `_deliver` makes delivery
    non-blocking and self-healing: a full inbox degrades ONLY that one
    subscriber (oldest entry dropped, gap recorded in `_gaps` and
    surfaced via `pop_gap`) and never blocks the publisher, `close()`, or
    any other subscriber.
    """

    def __init__(self, cap: int = _EVENT_REPLAY_CAP, inbox_cap: int = _SUBSCRIBER_INBOX_CAP):
        self._lock = threading.Lock()
        self._buffer: deque[tuple[int, dict]] = deque(maxlen=cap)
        self._next_id = 1
        self._subscribers: dict[int, queue.Queue] = {}
        self._next_sub_id = 1
        self.closed = False
        self._inbox_cap = inbox_cap
        # FIX-SSE: sub_id -> (gap_from, gap_to) for a subscriber whose
        # inbox overflowed and had its oldest entry evicted (see
        # _deliver). At most one entry per CURRENTLY ATTACHED subscriber
        # -- consumed by pop_gap() (the /stream generator, once per
        # contiguous run of drops) and discarded by unsubscribe() on
        # disconnect, so this dict can never grow with event volume the
        # way the unbounded inbox it replaces did.
        self._gaps: dict[int, tuple[int, int]] = {}

    def publish(self, event: dict) -> int:
        """Assign the next id, retain it in the replay buffer, and fan it
        out to every currently-attached subscriber. Returns the id.

        Delivery (FIX-SSE) is non-blocking: a subscriber whose inbox is
        full because it isn't draining fast enough is degraded on its
        own (see _deliver) -- it never stalls this call for the caller
        or for any other subscriber.
        """
        with self._lock:
            event_id = self._next_id
            self._next_id += 1
            self._buffer.append((event_id, event))
            targets = list(self._subscribers.items())
        for sub_id, inbox in targets:
            self._deliver(sub_id, inbox, ("event", event_id, event))
        return event_id

    def put(self, event: dict) -> None:
        """queue.Queue-compatible alias so web_services.make_progress_callback
        (which only ever calls ``.put(event)``) needs no change for the
        broadcast/replay upgrade."""
        self.publish(event)

    def close(self) -> None:
        """Mark the bus closed and wake every currently-attached subscriber
        with the terminal sentinel. Idempotent -- safe to call more than
        once (only the first call has any effect).

        Delivery is non-blocking (FIX-SSE), exactly like publish() -- the
        durable queue worker's finally block calls close() from its own
        thread, and a subscriber whose inbox is already full must never
        hang that thread waiting for room that will never come.
        """
        with self._lock:
            if self.closed:
                return
            self.closed = True
            targets = list(self._subscribers.items())
        for sub_id, inbox in targets:
            self._deliver(sub_id, inbox, ("end", None, None))

    def _deliver(self, sub_id: int, inbox: "queue.Queue", item: tuple) -> None:
        """Non-blocking delivery of ONE item to ONE subscriber's bounded
        inbox (FIX-SSE). Called by publish() and close() for every
        currently-attached subscriber; never raises and never blocks,
        so one slow subscriber can't stall the publisher, close(), or
        any other subscriber.

        A full inbox means only THIS subscriber isn't draining fast
        enough. Degrade gracefully: evict the oldest still-undelivered
        entry to make room, and record its id via _record_gap so the
        /stream generator can surface an explicit GAP notice for the
        lost range -- mirroring the replay-buffer-eviction GAP already
        used for a reconnect past the cap (module comment above). A
        dropped event is always reported, never silently lost.
        """
        try:
            inbox.put_nowait(item)
            return
        except queue.Full:
            pass
        dropped_event_id = None
        try:
            _kind, dropped_event_id, _evt = inbox.get_nowait()
        except queue.Empty:
            pass  # this subscriber's own consumer drained it concurrently
        if dropped_event_id is not None:
            self._record_gap(sub_id, dropped_event_id)
        try:
            inbox.put_nowait(item)
        except queue.Full:
            # Lost a race for the single slot just freed to ANOTHER
            # concurrent publish()/close() delivering to this same
            # inbox (both call _deliver without holding a lock, by
            # design -- see the class docstring). Vanishingly rare;
            # report THIS item's own id as dropped too rather than
            # lose it silently.
            _kind, item_event_id, _evt = item
            if item_event_id is not None:
                self._record_gap(sub_id, item_event_id)

    def _record_gap(self, sub_id: int, dropped_event_id: int) -> None:
        """Record (coalescing) that dropped_event_id was evicted, unread,
        from sub_id's inbox. Widens any already-pending gap for this
        subscriber rather than replacing it, so an unbroken run of drops
        collapses into exactly one GAP notice."""
        with self._lock:
            if sub_id not in self._subscribers:
                return  # already unsubscribed; no stream left to notify
            existing = self._gaps.get(sub_id)
            if existing is None:
                self._gaps[sub_id] = (dropped_event_id, dropped_event_id)
            else:
                lo, hi = existing
                self._gaps[sub_id] = (min(lo, dropped_event_id), max(hi, dropped_event_id))

    def pop_gap(self, sub_id: int) -> tuple[int, int] | None:
        """Atomically take and clear sub_id's pending drop-gap, if any
        (FIX-SSE overflow eviction recorded by _deliver/_record_gap).
        The /stream generator calls this right before yielding its next
        live-delivered item, so a widening run of drops surfaces as
        exactly one GAP frame instead of one per dropped event."""
        with self._lock:
            return self._gaps.pop(sub_id, None)

    def subscribe(self, last_event_id: int | None) -> _EventSubscription:
        """Attach a new subscriber. See the module comment above this
        class for the full backlog/gap/snapshot contract. ``last_event_id
        is None`` means "no known position" (the snapshot path); an int
        means "replay everything after this id, and tell me if part of
        that range already aged out of the buffer." """
        with self._lock:
            sub_id = self._next_sub_id
            self._next_sub_id += 1
            inbox: queue.Queue = queue.Queue(maxsize=self._inbox_cap)
            self._subscribers[sub_id] = inbox

            oldest_id = self._buffer[0][0] if self._buffer else None
            gap: tuple[int, int] | None = None
            if last_event_id is None:
                # Fresh subscriber: a one-event snapshot of current truth,
                # not the whole history -- the known-id branch below is
                # what replays a bounded backlog for a real reconnect.
                backlog = [self._buffer[-1]] if self._buffer else []
            else:
                if oldest_id is not None and last_event_id < oldest_id - 1:
                    gap = (last_event_id + 1, oldest_id - 1)
                backlog = [
                    (eid, evt) for eid, evt in self._buffer if eid > last_event_id
                ]
            closed = self.closed
        return _EventSubscription(sub_id, inbox, backlog, gap, closed)

    def unsubscribe(self, sub_id: int) -> None:
        """Detach a subscriber (disconnect). Safe to call even if the
        subscriber was never attached or already removed."""
        with self._lock:
            self._subscribers.pop(sub_id, None)
            self._gaps.pop(sub_id, None)  # FIX-SSE: no orphaned gap state


# SSE event buses per project (Slice 11a: was a single queue.Queue per
# project; now a _ProjectEventBus so N concurrent /stream subscribers each
# see every event, with a bounded replay log for reconnects).
_progress_queues: dict[str, _ProjectEventBus] = {}
_running_pipelines: dict[str, CinemaPipeline] = {}
# Short-lived destructive/settings mutations reserve a project here so a
# generation start cannot race the disk write or cache invalidation. Guarded
# by the same lock as ``_running_pipelines``.
_project_admin_in_flight: set[str] = set()
# Direct per-request stage work (motion/keyframe generation, approval,
# iteration, diagnostics, and assembly) leases the project here for its full
# call lifetime. This keeps settings/delete from evicting and closing the
# shared PipelineCore while an endpoint is still using it, and serializes
# otherwise-duplicative direct paid operations. Guarded by _pipelines_lock.
_project_stage_in_flight: set[str] = set()
# A generation request must establish project existence and its durable queue
# row as one same-process administrative boundary.  Without this short-lived
# reservation, deletion can win between the read and enqueue and leave a job
# pointing at a project that no longer exists.  Queue workers deliberately do
# not treat this as a run-time lease: once the row is visible they may claim it.
_project_queue_accept_in_flight: set[str] = set()
# Duplicate clicks wait on the first short admission instead of manufacturing
# a second job or returning a misleading failure. Events are removed as soon
# as the durable row (or a terminal admission error) is known.
_project_queue_accept_events: dict[str, threading.Event] = {}

# Guards _running_pipelines, _progress_queues, and both project reservation
# sets. The construct-window
# sentinel (_PIPELINE_PENDING) lets us reserve a slot atomically while
# the heavy CinemaPipeline constructor runs WITHOUT holding the lock.
# Mirrors the _cores_lock construct-window pattern (Session 5 fix).
# Audit ref: docs/AUDIT-P3-1-concurrency-2026-05-24.md
_pipelines_lock = threading.Lock()
_PIPELINE_PENDING = object()  # sentinel — readers must skip this

# Full-project generation is accepted into this durable SQLite queue before a
# worker touches provider state.  Connections are method-scoped/closed by the
# store; the dispatcher is lazy-started on the first accepted request and owns
# a fixed-size worker pool (never one thread per HTTP request).
_pipeline_job_store = PipelineJobStore()
_pipeline_job_dispatcher: PipelineJobDispatcher | None = None
_pipeline_dispatcher_lock = threading.Lock()

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
# request. Confirmed API settings writes and project deletion evict the idle
# entry; direct out-of-band project.json edits remain invisible until another
# supported mutation or a server restart.
_running_cores: dict[str, PipelineCore] = {}
_cores_lock = threading.Lock()
HTTP_PROJECT_TIMEOUT = 2.0
_DRIVING_VIDEO_MAX_BYTES = 256 * 1024 * 1024
_DRIVING_VIDEO_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
_DRIVING_VIDEO_UPLOAD_CHUNK_BYTES = 1024 * 1024
# Operators may retain a longer reusable acting reference, but each local
# LivePortrait take admits only its authoritative per-shot window capped at
# the first 8 seconds / 200 frames. Upload validation and GPU ingestion are
# intentionally distinct limits; the review UI states both.
_DRIVING_VIDEO_MAX_DURATION_S = 30.0
_DRIVING_VIDEO_MIN_DIMENSIONS = (64, 64)
_DRIVING_VIDEO_MAX_DIMENSIONS = (4096, 4096)
_DRIVING_VIDEO_MAX_PIXELS = 4096 * 2160
_PROJECT_CREATE_NAME_MAX_CHARS = 200
_COST_ESTIMATE_MAX_SHOTS = 120
_COST_ESTIMATE_MAX_CANDIDATES = 16
_COST_ESTIMATE_REQUEST_KEYS = frozenset({
    "shot_count",
    "has_dialogue",
    "dialogue_shot_ratio",
    "quality_tier",
    "candidate_count",
})
_PUBLIC_SHOT_COMPATIBILITY_TYPES = {
    # Observed historical project fields. They are no longer active
    # production writers/readers, so keep them outside the canonical Shot
    # model while allowing a strictly typed public round-trip.
    "plan_review": dict,
    "keyframe_review": dict,
    "scene_location": str,
}


def _json_object_or_none():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _video_policy_runtime_snapshot() -> RuntimeSnapshot:
    """Observe current symbolic readiness without retaining secret values."""

    return build_runtime_snapshot()


def _video_policy_current_date():
    """Return the UTC policy date through a deterministic test seam."""

    return datetime.now(timezone.utc).date()


def _raise_if_target_rejected(
    requested: str,
    *,
    shot_id: str,
    current_target: object,
    may_grandfather: bool,
    snapshot: RuntimeSnapshot,
    on_date,
    api_engines: Mapping[str, object] | None,
    aspect_ratio: object,
) -> None:
    """Fence a proposed target while preserving one exact historical value."""

    if may_grandfather and requested == current_target:
        return
    decision = evaluate_shot_target(
        requested,
        snapshot=snapshot,
        on_date=on_date,
        api_engines=api_engines,
        aspect_ratio=aspect_ratio,
    )
    if decision.accepted:
        return
    reason = (
        decision.reason.value
        if decision.reason is not None
        else VideoPolicyReason.UNKNOWN.value
    )
    raise VideoTargetPolicyError(
        target=requested,
        reason=reason,
        shot_id=shot_id,
    )


def _shot_target_policy_response(exc: VideoTargetPolicyError):
    return jsonify({
        "error": "Target video engine is unavailable",
        "error_kind": "target_api_policy",
        "code": "target_api_unavailable",
        "target_api": exc.target,
        "reason": exc.reason,
        "retryable": False,
        "shot_id": exc.shot_id,
    }), 409


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


def _evict_cached_project_core(pid: str) -> None:
    """Drop an idle project's settings-bound services and close its DB.

    Callers hold an administrative reservation for ``pid``. Generation slots
    and direct-stage leases both exclude that reservation, preventing any core
    user from overlapping the pop and close.
    """
    with _cores_lock:
        cached_core = _running_cores.pop(pid, None)
    if cached_core is None:
        return
    try:
        cached_core.cost_tracker.close()
    except Exception:
        logger.warning(
            "Failed to close cached project cost tracker during eviction",
            extra={"pid": pid},
            exc_info=True,
        )


def _close_all_cached_cores() -> None:
    """Close every controller-owned SQLite connection during normal shutdown."""
    with _cores_lock:
        cached = list(_running_cores.items())
        _running_cores.clear()
    for pid, core in cached:
        try:
            core.cost_tracker.close()
        except Exception:
            logger.warning(
                "Failed to close cached project cost tracker during shutdown",
                extra={"pid": pid},
                exc_info=True,
            )


atexit.register(_close_all_cached_cores)


def _reserve_project_admin(pid: str) -> bool:
    """Atomically exclude core users and another admin mutation for ``pid``."""
    queue_job = _pipeline_job_store.project_job(pid, active_only=True)
    with _pipelines_lock:
        if (
            pid in _running_pipelines
            or pid in _project_admin_in_flight
            or pid in _project_stage_in_flight
            or pid in _project_queue_accept_in_flight
            or queue_job is not None
        ):
            return False
        _project_admin_in_flight.add(pid)
        return True


def _release_project_admin(pid: str) -> None:
    with _pipelines_lock:
        _project_admin_in_flight.discard(pid)


# Identity Lab blueprint routes are imported before the shared reservation
# primitives are defined. Bind them now so every mutating Identity request
# participates in the same admission/admin exclusion used by project writes.
configure_identity_project_guard(
    _reserve_project_admin,
    _release_project_admin,
    timeout=HTTP_PROJECT_TIMEOUT,
)


def _reserve_project_stage(pid: str) -> bool:
    """Acquire one exclusive direct-stage lease for ``pid``.

    A real running pipeline may be reused by a gate operation, but its
    construction sentinel may not: the object/core pair is not available yet.
    """

    queue_job = _pipeline_job_store.project_job(pid, active_only=True)
    with _pipelines_lock:
        local_pipeline = _running_pipelines.get(pid)
        queue_owned_elsewhere_or_waiting = (
            queue_job is not None
            and (
                queue_job.state == "queued"
                or local_pipeline is None
            )
        )
        if (
            pid in _project_admin_in_flight
            or pid in _project_stage_in_flight
            or pid in _project_queue_accept_in_flight
            or local_pipeline is _PIPELINE_PENDING
            or queue_owned_elsewhere_or_waiting
        ):
            return False
        _project_stage_in_flight.add(pid)
        if local_pipeline is not None:
            # The review predicate polls independently of HTTP operation
            # locks.  Publish the lease onto the live pipeline before the
            # endpoint can validate or mutate so a gate cannot advance on the
            # approval snapshot that the in-flight action is replacing.
            try:
                local_pipeline._direct_stage_in_flight = True
            except AttributeError:
                # A few compatibility/test callers use an opaque sentinel to
                # mean "a gate waiter exists". It has no review predicate to
                # coordinate with, so the process-wide lease remains the only
                # applicable guard.
                pass
        return True


def _release_project_stage(pid: str) -> None:
    with _pipelines_lock:
        local_pipeline = _running_pipelines.get(pid)
        if local_pipeline is not None and local_pipeline is not _PIPELINE_PENDING:
            try:
                local_pipeline._direct_stage_in_flight = False
            except AttributeError:
                pass
        _project_stage_in_flight.discard(pid)


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


def _ensure_progress_queue(pid: str) -> _ProjectEventBus:
    """Return pid's event bus, creating one if absent OR if the existing
    entry was already closed by a finished run. The closed-bus branch is
    defensive: under the normal lock discipline (see _execute_pipeline_job's
    finally block below) a closed bus is popped from _progress_queues
    before close() runs, so it should not be reachable in practice -- but
    a stale/closed bus must never be silently reused for a fresh run's
    events (its subscribe() would report `closed=True` and truncate the
    new run's stream immediately).
    """
    with _pipelines_lock:
        bus = _progress_queues.get(pid)
        if bus is None or bus.closed:
            bus = _ProjectEventBus()
            _progress_queues[pid] = bus
        return bus


def _make_progress_cb(pid: str, bus: "_ProjectEventBus | None" = None):
    """Per-project SSE progress callback. Thin wrapper around web_services.

    Resolves the event bus (explicit arg or module-state lookup), then
    delegates to ``web_services.make_progress_callback`` which contains
    the actual SSE-event-shaping logic. ``_ProjectEventBus.put()`` is a
    queue.Queue-compatible alias for ``.publish()`` (Slice 11a), so the
    builder itself needed no change for the broadcast/replay upgrade.
    """
    event_bus = bus or _progress_queues.get(pid)
    return make_progress_callback(event_bus)


def _get_stage_pipeline(pid: str) -> CinemaPipeline:
    """Resolve the pipeline protected by the caller's direct-stage lease."""

    pipeline = _get_running_pipeline(pid)  # returns None during sentinel window
    if pipeline:
        return pipeline
    # Build a per-request CinemaPipeline that shares the cached core --
    # amortizes the heavy service construction across endpoint calls.
    # _reserve_project_stage rejects the _PIPELINE_PENDING window, so a
    # production route can only reach this branch while no generation exists.
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
    with _pipelines_lock:
        stage_busy = pid in _project_stage_in_flight
        admin_busy = pid in _project_admin_in_flight
        queue_accept_busy = pid in _project_queue_accept_in_flight
    queued_job = _pipeline_job_store.project_job(pid, active_only=True)
    if stage_busy:
        detail = (
            f"Project '{pid}' is busy with another direct stage operation. "
            "Retry shortly."
        )
    elif admin_busy:
        detail = f"Project '{pid}' is being updated. Retry shortly."
    elif queue_accept_busy:
        detail = f"Project '{pid}' is being admitted to the generation queue. Retry shortly."
    elif queued_job is not None and queued_job.state == "queued":
        detail = f"Project '{pid}' already has a queued generation run."
    else:
        detail = (
            f"Project '{pid}' is busy with an active generation run. "
            "Retry shortly."
        )
    return _project_conflict_response(
        "project_busy",
        detail,
    )


def _reject_if_project_busy(pid: str):
    queued_job = _pipeline_job_store.project_job(pid, active_only=True)
    with _pipelines_lock:
        busy = (
            pid in _running_pipelines
            or pid in _project_admin_in_flight
            or pid in _project_stage_in_flight
            or pid in _project_queue_accept_in_flight
            or queued_job is not None
        )
    if busy:
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


def _require_exact_pipeline_stage(pid: str, expected_stage: str):
    """Return a deterministic 409 unless the live run owns ``expected_stage``.

    A direct-stage lease only prevents concurrent mutations; it does not prove
    which review gate the pipeline worker is parked at. Gate-specific actions
    must bind to the live run's exact stage so a hidden/stale client cannot
    invoke them during plan, keyframe, final review, or ordinary execution.
    """

    pipeline = _get_running_pipeline(pid)
    actual_stage = str(getattr(pipeline, "current_stage", "") or "")
    if actual_stage == expected_stage:
        return None
    return jsonify({
        "code": "wrong_pipeline_stage",
        "retryable": False,
        "error": (
            f"Action requires {expected_stage}; current pipeline stage is "
            f"{actual_stage or 'IDLE'}"
        ),
        "required_stage": expected_stage,
        "current_stage": actual_stage,
    }), 409


def _require_iteration_pipeline_stage(pid: str, target_stage: str):
    """Bind directorial iteration to its live review authority.

    Screening is the deliberate cross-stage remediation surface: it may send
    any supported take kind back through its matching generator and marks the
    shot dirty for reassembly.  Ordinary review gates may invoke only their
    own generator.
    """

    required_stage = {
        "keyframe": "KEYFRAME_REVIEW",
        "performance": "PERFORMANCE_REVIEW",
        "motion": "REVIEW",
    }[target_stage]
    pipeline = _get_running_pipeline(pid)
    actual_stage = str(getattr(pipeline, "current_stage", "") or "")
    allowed_stages = (required_stage, "SCREENING")
    if actual_stage in allowed_stages:
        return None
    return jsonify({
        "code": "wrong_pipeline_stage",
        "retryable": False,
        "error": (
            f"Iteration target {target_stage} requires {required_stage} "
            f"or SCREENING; current pipeline stage is {actual_stage or 'IDLE'}"
        ),
        "required_stage": required_stage,
        "allowed_stages": list(allowed_stages),
        "current_stage": actual_stage,
        "target_stage": target_stage,
    }), 409


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


def _pipeline_action_authority(pid: str) -> tuple[bool, list[str]]:
    """Derive ``(running, allowed_actions)`` from the pipeline lifecycle
    registry — the SAME ``_running_pipelines`` / ``_PIPELINE_PENDING``
    mechanism that gates ``/generate``, ``/cancel``, ``/pause``, and
    ``/resume``. Never inspects transport/SSE connectivity (``_progress_queues``,
    ``/stream`` subscriber count, etc.) — a client can disconnect from the
    SSE stream while generation keeps running, and vice versa, so
    transport state is never job truth.

    ``allowed_actions`` mirrors each control endpoint's own real gate
    instead of being hardcoded, so the response tells the UI exactly
    which of {"start", "resume_checkpoint", "cancel", "pause", "resume"}
    would currently succeed:

      - idle (pid absent from ``_running_pipelines``), no resumable
        on-disk checkpoint: running=False; only "start" is legal —
        ``api_generate``'s ``if pid in _running_pipelines`` check is the
        sole gate.
      - idle WITH a resumable checkpoint (Slice 11c —
        ``cinema.services.checkpoint_info`` reports ``resumable=True``
        because a prior run crashed, was cancelled, or the process
        restarted before ``temp/pipeline_state.json`` was cleared):
        running=False; "start" AND "resume_checkpoint" are both legal.
        Both dispatch through the SAME ``POST /generate`` endpoint,
        distinguished only by the request body's ``resume`` flag —
        "start" always sends ``resume=False`` (a fresh run; it does NOT
        silently continue the checkpoint) and "resume_checkpoint" always
        sends ``resume=True`` (it does NOT silently discard the
        checkpoint). A run that finishes successfully clears its own
        checkpoint (``CheckpointStore._clear_checkpoint``, called right
        before the terminal ``COMPLETE`` progress event) so a completed
        project reports only "start", identically to a project that
        never ran.
      - idle generation registry but a direct-stage/admin reservation is
        active: running=False; no generation action is currently legal.
        This matches api_generate's project_busy fence while keeping
        ``running`` reserved for a real/pending full-pipeline run.
      - pending-start (``_PIPELINE_PENDING`` sentinel present —
        ``CinemaPipeline.__init__`` is constructing but hasn't registered
        the real object yet): running=True; NO action is currently legal
        — "start" would still 409 (pid is already ``in
        _running_pipelines``), and cancel/pause/resume all 404
        (``_get_running_pipeline`` returns None for the sentinel).
        Reported as running so the UI does not repaint a start-again
        affordance during this brief construction window.
      - running (real pipeline object, not paused), NOT parked at a
        review-gate stage (``_GATE_STAGES``): running=True; "cancel" and
        "pause" are legal.
      - running (real pipeline object, not paused), parked at a
        review-gate stage (Slice 11c, via ``_pipeline_at_gate_stage``):
        running=True; only "cancel" is legal. "pause" is deliberately
        withheld here — the gate-wait loop
        (``ThreadedLifecycle.wait_for_gate``) never consults
        ``check_pause()``, so pausing while blocked on operator review
        has NO observable effect until the gate itself clears, which
        would make "pause" a legal-but-inert action. "cancel" DOES take
        effect immediately: ``ThreadedLifecycle.cancel`` explicitly
        signals every gate ``Event``, so a blocked ``wait_for_gate``
        wakes and returns ``False`` right away.
      - paused (real pipeline object, paused): running=True; "cancel"
        and "resume" are legal.
    """
    queue_job = _pipeline_job_store.project_job(pid, active_only=True)
    if queue_job is not None and queue_job.state == "queued":
        return True, ["cancel"]
    if (
        pid not in _running_pipelines
        and (
            pid in _project_admin_in_flight
            or pid in _project_stage_in_flight
        )
    ):
        return False, []
    if pid not in _running_pipelines:
        # A running lease owned by another process (or the brief local
        # claim-to-construction window) is still real work.  Only durable
        # cancellation is universally legal; pause/resume require the
        # process-local CinemaPipeline instance.
        if queue_job is not None and queue_job.state == "running":
            return True, ["cancel"]
        actions = ["start"]
        if checkpoint_info(pid).get("resumable"):
            actions.append("resume_checkpoint")
        return False, actions
    pipeline = _get_running_pipeline(pid)
    if pipeline is None:
        return True, []
    try:
        paused = bool(pipeline.paused)
    except AttributeError:
        # Defensive: mirrors _pipeline_at_gate_stage's tolerance for bare
        # object() sentinels injected by tests / unexpected registry
        # entries. Treat as "not paused" — the conservative branch that
        # offers cancel/pause rather than asserting an unverifiable resume.
        paused = False
    if paused:
        return True, ["cancel", "resume"]
    if _pipeline_at_gate_stage(pid):
        return True, ["cancel"]
    return True, ["cancel", "pause"]


def _project_lock_guard(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        pid = kwargs.get("pid")
        if not isinstance(pid, str) and args:
            pid = args[0]
        try:
            if not isinstance(pid, str):
                return fn(*args, **kwargs)
            with project_operation_lock(pid, timeout=HTTP_PROJECT_TIMEOUT):
                return fn(*args, **kwargs)
        except ProjectLockError as exc:
            return _project_locked_response(exc)

    return wrapper


def _project_admin_guard(fn):
    """Hold the process-local admin reservation for one complete mutation."""

    @wraps(fn)
    def wrapper(pid, *args, **kwargs):
        if not _reserve_project_admin(pid):
            return _project_busy_response(pid)
        try:
            return fn(pid, *args, **kwargs)
        finally:
            _release_project_admin(pid)

    return wrapper


def _project_stage_guard(fn):
    """Hold a direct-stage lease across one complete endpoint invocation."""

    @wraps(fn)
    def wrapper(pid, *args, **kwargs):
        if not _reserve_project_stage(pid):
            return _project_busy_response(pid)
        try:
            return fn(pid, *args, **kwargs)
        finally:
            _release_project_stage(pid)

    return wrapper


@app.before_request
def _reject_non_object_json_body():
    """Make the HTTP JSON boundary object-only for mutating routes.

    Endpoint code may safely use ``.get`` after this guard. Arrays, scalars,
    JSON null, and malformed JSON receive a deterministic 400 instead of an
    AttributeError/500 deeper in a route.
    """

    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.is_json:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "JSON object required"}), 400
    return None


@app.before_request
def _reject_noncanonical_project_route_id():
    """Fence every ``<pid>`` route before endpoint code can touch storage."""

    pid = (request.view_args or {}).get("pid")
    if pid is not None and not is_safe_project_id(pid):
        return jsonify({"error": "Invalid project_id"}), 400
    return None


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

# Per-engine project overrides — the shape/default catalog served at
# /api/config and seeded into global_settings.api_engines on settings-save.
#
# Deliberately NARROW, and it must stay that way. Exactly two keys are read
# anywhere in the program:
#   enabled         → domain/video_engine_policy.py _is_project_disabled
#                     (the single funnel every api_engines consumer routes
#                     through: web_server, scene_decomposer, workflow_selector,
#                     prompt_optimizer, phase_c_ffmpeg)
#   storyboard_mode → cinema/phases/motion_render.py _get_storyboard_mode
#                     (KLING_NATIVE only)
# Engine duration / resolution / audio / camera params are NOT configured
# here — each dispatch branch in phase_c_ffmpeg.py derives them per shot from
# shot_type, which is the behavior we want (an action beat and a portrait beat
# need different lengths; a flat per-engine override would flatten that).
#
# Do NOT re-add decorative sub-fields (ADR-080). `duration` especially is a
# money source, not a free knob: the per-clip cost record recomputes from the
# dispatch-side tables (SEEDANCE_DURATIONS in phase_c_ffmpeg.py), so a
# settings-side duration would fork the figure the budget gate trusts — the
# 38%-under-record failure the 2026-07-11 money-gate review caught.
_AUTOMATIC_VIDEO_ENGINE_KEYS = (
    "GEMINI_OMNI",
    "VEO_NATIVE",
    "SEEDANCE",
    "KLING_3_0",
    "RUNWAY_GEN4",
    "LTX",
    "VEO",
)

# Ordered automatic-cascade participation controls. Deprecated explicit-only
# adapters (notably KLING_NATIVE and SORA_NATIVE) deliberately stay out of
# this surface: historical shots can still discover their compatibility rows,
# but neither a fresh project nor stale ``api_engines`` JSON advertises them
# as a current product toggle.
_API_ENGINE_DEFAULTS = {
    key: {"enabled": True}
    for key in _AUTOMATIC_VIDEO_ENGINE_KEYS
}


def _project_video_engine_rows(
    project: dict,
    *,
    snapshot: RuntimeSnapshot,
    on_date,
) -> list[dict]:
    """Build a public, secret-free target discovery view for one project."""

    persisted_targets: list[str] = []
    for scene in project.get("scenes", []):
        if not isinstance(scene, Mapping):
            continue
        for shot in scene.get("shots", []):
            if not isinstance(shot, Mapping):
                continue
            target = shot.get("target_api")
            if isinstance(target, str) and target and target not in persisted_targets:
                persisted_targets.append(target)
    in_use = frozenset(persisted_targets)

    settings = project.get("global_settings", {})
    api_engines = (
        settings.get("api_engines", {})
        if isinstance(settings, Mapping)
        else {}
    )
    if not isinstance(api_engines, Mapping):
        api_engines = {}
    aspect_ratio = (
        settings.get("aspect_ratio", DEFAULT_ASPECT_RATIO)
        if isinstance(settings, Mapping)
        else DEFAULT_ASPECT_RATIO
    )

    def _configuration(key: str) -> tuple[bool, bool]:
        configured = api_engines.get(key)
        default = _API_ENGINE_DEFAULTS.get(key)
        source = configured if isinstance(configured, Mapping) else default
        enabled = (
            source.get("enabled", True) is not False
            if isinstance(source, Mapping)
            else True
        )
        # Configuration is an allowlist, not a reflection of whatever an old
        # project happened to persist. The latter would turn stale/unknown
        # compatibility keys back into live UI controls merely by loading the
        # project.
        can_configure = key in _API_ENGINE_DEFAULTS
        return enabled, can_configure

    typed_entries = [
        CATALOG["AUTO"],
        *[CATALOG[key] for key in _AUTOMATIC_VIDEO_ENGINE_KEYS],
        *[
            entry
            for key, entry in CATALOG.items()
            if (
                key != "AUTO"
                and key not in _API_ENGINE_DEFAULTS
                and entry.modality is Modality.VIDEO
            )
        ],
    ]
    rows: list[dict] = []
    typed_video_keys: set[str] = set()
    for entry in typed_entries:
        typed_video_keys.add(entry.key)
        decision = evaluate_shot_target(
            entry.key,
            snapshot=snapshot,
            on_date=on_date,
            api_engines=api_engines,
            aspect_ratio=aspect_ratio,
        )
        configured_enabled, can_configure = _configuration(entry.key)
        is_in_use = entry.key in in_use
        rows.append({
            "key": entry.key,
            "label": entry.label,
            "can_select": decision.accepted,
            "reason": (
                decision.reason.value
                if decision.reason is not None
                else None
            ),
            "configured_enabled": configured_enabled,
            "can_configure": can_configure,
            "in_use": is_in_use,
            "historical": is_in_use and not decision.accepted,
        })

    for key in persisted_targets:
        if key in typed_video_keys:
            continue
        decision = evaluate_shot_target(
            key,
            snapshot=snapshot,
            on_date=on_date,
            api_engines=api_engines,
            aspect_ratio=aspect_ratio,
        )
        configured_enabled, can_configure = _configuration(key)
        legacy = API_REGISTRY.get(key, {})
        label = (
            legacy.get("label")
            if isinstance(legacy, Mapping)
            and isinstance(legacy.get("label"), str)
            else key
        )
        rows.append({
            "key": key,
            "label": label,
            "can_select": False,
            "reason": (
                decision.reason.value
                if decision.reason is not None
                else VideoPolicyReason.UNKNOWN.value
            ),
            "configured_enabled": configured_enabled,
            "can_configure": can_configure,
            "in_use": True,
            "historical": True,
        })
    return rows


@app.route("/api/config", methods=["GET"])
def get_config():
    """Returns all controllable parameters for the UI panels."""
    project_id = request.args.get("project_id")
    project = None
    if project_id is not None:
        if not is_safe_project_id(project_id):
            return jsonify({"error": "Invalid project_id"}), 400
        project = load_existing_project_readonly(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

    config = {
        "camera_motions": CAMERA_MOTIONS,
        "visual_effects": VISUAL_EFFECTS,
        "target_apis": TARGET_APIS,
        "api_registry": API_REGISTRY,
        "music_moods": MUSIC_MOODS,
        "voice_pool": VOICE_POOL,
        "delivery_styles": _get_delivery_styles(),
        "aspect_ratios": SUPPORTED_ASPECT_RATIOS,
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
        "color_grade_presets": [
            "warm_cinema", "cool_noir", "vibrant", "desaturated",
            "golden_hour", "moonlight", "high_contrast", "pastel",
        ],
        "lip_sync_modes": ["auto", "overlay", "generation", "skip"],
        "dialogue_voice_modes": ["overlay", "native"],
        "api_engine_defaults": _API_ENGINE_DEFAULTS,
        "creative_llm_options": [
            {"value": "auto", "label": "Auto (Router decides)"},
            {"value": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
            {"value": "gpt-4o", "label": "GPT-4o"},
        ],
        "quality_judge_options": [
            {"value": "auto", "label": "Auto (Best available)"},
            {"value": "claude-opus", "label": "Claude Opus 4.8"},
            {"value": "gpt-4o", "label": "GPT-4o"},
            {"value": "gemini-pro", "label": "Gemini 3.1 Pro (Preview)"},
        ],
        "workflow_templates": WORKFLOW_TEMPLATES,
        # Purpose-based API routing surface (consumed by SettingsPanel)
        "purpose_tags": PURPOSE_TAGS,
        "purpose_api_ranking": PURPOSE_API_RANKING,
        # Billing attribution for cost estimator
        "billing_providers": BILLING_PROVIDERS,
        "flux2_candidate": flux2_candidate_status(env_settings).public_dict(),
    }
    if project is not None:
        config["video_engines"] = _project_video_engine_rows(
            project,
            snapshot=_video_policy_runtime_snapshot(),
            on_date=_video_policy_current_date(),
        )
    return jsonify(config)


@app.route("/api/projects/<pid>/apply-language-defaults", methods=["POST"])
@_project_lock_guard
def api_apply_language_defaults(pid):
    """Apply per-language optimized defaults to a project's global_settings.

    Body (JSON):
      {
        "language": "Korean",
        "overwrite_existing": false,
        "expected_revision": 0
      }

    When overwrite_existing is False (default), only fields the user hasn't
    customized are touched. The response includes the list of fields that
    actually changed so the UI can show a diff.
    """
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = _json_object_or_none()
    if data is None:
        return jsonify({"error": "JSON object required"}), 400
    if "expected_revision" not in data:
        return jsonify({
            "error": "expected_revision is required",
            "code": "revision_required",
            "retryable": False,
        }), 400
    expected_revision = data["expected_revision"]
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        return jsonify({
            "error": "expected_revision must be an integer",
            "code": "invalid_revision",
            "retryable": False,
        }), 400

    try:
        from domain.language_defaults import (
            merge_language_defaults_into_settings,
            recommended_voices_for_language,
            get_language_defaults,
        )
        from domain.character_manager import VOICE_POOL
    except Exception as e:
        return jsonify({"error": f"language_defaults unavailable: {e}"}), 500

    if not _reserve_project_admin(pid):
        return _project_busy_response(pid)
    try:
        project = load_project(pid)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        # Validate the read snapshot before deriving the fallback language.
        # The authoritative revision check still happens inside mutate_project.
        Project.model_validate(project)
        language = (
            data.get("language")
            or project.get("global_settings", {}).get("language", "English")
        )
        overwrite = bool(data.get("overwrite_existing", False))
        changed_fields: list[str] = []
        conflict = None

        def _mutate(latest):
            nonlocal changed_fields, conflict
            Project.model_validate(latest)
            current_revision = _current_settings_revision(latest)
            if expected_revision != current_revision:
                conflict = _settings_revision_conflict_payload(
                    current_revision, latest.get("global_settings", {})
                )
                return MutationResult(None, save=False)

            settings = latest.setdefault("global_settings", {})
            _, changed = merge_language_defaults_into_settings(
                settings,
                language,
                overwrite_existing=overwrite,
            )
            changed_fields = changed
            if changed:
                settings[_SETTINGS_REVISION_KEY] = current_revision + 1
            return MutationResult(True, save=bool(changed))

        mutation_result = mutate_project(
            pid,
            _mutate,
            timeout=HTTP_PROJECT_TIMEOUT,
        )
        if conflict is not None:
            return jsonify(conflict), 409
        if mutation_result is None:
            return jsonify({"error": "Project not found"}), 404
        if changed_fields:
            _evict_cached_project_core(pid)

        recommended_voices = recommended_voices_for_language(language, VOICE_POOL)
        return jsonify({
            "language": language,
            "changed_fields": changed_fields,
            "applied_defaults": {
                key: get_language_defaults(language).get(key)
                for key in changed_fields
            },
            "recommended_voices": recommended_voices,
        })
    finally:
        _release_project_admin(pid)


@app.route("/api/cost-estimate", methods=["POST"])
def api_cost_estimate():
    """Return a bounded estimate for one strictly typed JSON request."""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = _json_object_or_none()
    if data is None:
        return jsonify({"error": "JSON object required"}), 400

    unknown_keys = sorted(set(data) - _COST_ESTIMATE_REQUEST_KEYS)
    invalid_keys: dict[str, str] = {}

    shot_count = data.get("shot_count", 60)
    if (
        isinstance(shot_count, bool)
        or not isinstance(shot_count, int)
        or not 1 <= shot_count <= _COST_ESTIMATE_MAX_SHOTS
    ):
        invalid_keys["shot_count"] = "must be an integer between 1 and 120"

    has_dialogue = data.get("has_dialogue", True)
    if not isinstance(has_dialogue, bool):
        invalid_keys["has_dialogue"] = "must be a boolean"

    dialogue_shot_ratio = data.get("dialogue_shot_ratio", 0.5)
    if (
        isinstance(dialogue_shot_ratio, bool)
        or not isinstance(dialogue_shot_ratio, (int, float))
        or not math.isfinite(dialogue_shot_ratio)
        or not 0 <= dialogue_shot_ratio <= 1
    ):
        invalid_keys["dialogue_shot_ratio"] = (
            "must be a finite number between 0 and 1"
        )

    quality_tier = data.get("quality_tier", "production")
    if quality_tier != "production":
        invalid_keys["quality_tier"] = "must be 'production'"

    candidate_count = data.get("candidate_count", 1)
    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or not 1 <= candidate_count <= _COST_ESTIMATE_MAX_CANDIDATES
    ):
        invalid_keys["candidate_count"] = "must be an integer between 1 and 16"

    if unknown_keys or invalid_keys:
        payload = {
            "error": "Invalid cost estimate request",
            "code": "invalid_cost_estimate",
            "retryable": False,
        }
        if unknown_keys:
            payload["unknown_keys"] = unknown_keys
        if invalid_keys:
            payload["invalid_keys"] = invalid_keys
        return jsonify(payload), 400

    est = estimate_short_cost(
        shot_count=shot_count,
        has_dialogue=has_dialogue,
        dialogue_shot_ratio=float(dialogue_shot_ratio),
        quality_tier=quality_tier,
        candidate_count=candidate_count,
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
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = _json_object_or_none()
    if data is None:
        return jsonify({"error": "JSON object required"}), 400

    unknown_keys = sorted(set(data) - {"name"})
    invalid_keys: dict[str, str] = {}
    raw_name = data.get("name")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    if (
        not isinstance(raw_name, str)
        or not name
        or len(name) > _PROJECT_CREATE_NAME_MAX_CHARS
        or any(not char.isprintable() for char in name)
    ):
        invalid_keys["name"] = (
            "must be a nonblank string of at most 200 characters"
        )

    if unknown_keys or invalid_keys:
        payload = {
            "error": "Invalid project create request",
            "code": "invalid_project_create",
            "retryable": False,
        }
        if unknown_keys:
            payload["unknown_keys"] = unknown_keys
        if invalid_keys:
            payload["invalid_keys"] = invalid_keys
        return jsonify(payload), 400

    project = create_project(name)
    return jsonify(project), 201


@app.route("/api/projects/<pid>", methods=["GET"])
def api_get_project(pid):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project)


@app.route("/api/projects/<pid>/capability-scorecard", methods=["GET"])
def api_capability_scorecard(pid):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    from cinema.capability_scorecard import build_capability_scorecard
    scorecard = build_capability_scorecard(project)
    return jsonify(scorecard)


# ---------------------------------------------------------------------------
# Project settings — validated write contract (slice 9a; PUT's revision
# guard hardened to fail-closed post-9a-review — see
# _settings_revision_established below)
#
# The whole-object PUT below has historically round-tripped an entire
# global_settings object with no per-key validation and no way to detect a
# stale write: two browser tabs (or an inspector control that PUTs the full
# settings object on every keystroke — see SettingsInspector.tsx / ShotInspector.tsx
# `update()`) can race, and whichever response lands last silently wins even
# though it started from older state. PATCH below adds a strict, partial,
# revision-guarded alternative that ALWAYS requires a matching revision.
#
# PUT keeps a compat window for callers that have never seen the field, but
# the guard is FAIL-CLOSED rather than opt-in: once global_settings carries
# an ESTABLISHED revision (any write — PUT or PATCH — already stamped one),
# every subsequent PUT MUST echo a matching "revision", whether or not this
# particular caller meant to opt in. Omitting the field is no longer a
# silent bypass: the original opt-in design let a caller that simply never
# echoes "revision" clobber newer revision-guarded state with a 200 and no
# conflict (live-probed: A PATCHes rev 0->1, B PUTs a stale snapshot with no
# "revision" key, A's change vanishes, revision advances, nobody is told).
# Only a project whose settings have NEVER been stamped gets an
# unconditional accept-and-stamp on this one bootstrapping write — the only
# compat window, and it closes permanently the moment that first write
# lands. A caller that supplies an explicit "revision" before one is
# established is still held to it (existing behavior, preserved): claim a
# revision, even an invented one, and get checked against it.
# ---------------------------------------------------------------------------

_SETTINGS_REVISION_KEY = "revision"


def _current_settings_revision(project: dict) -> int:
    """Read the settings revision counter; absent/legacy/malformed → 0."""
    settings = project.get("global_settings")
    if not isinstance(settings, dict):
        return 0
    value = settings.get(_SETTINGS_REVISION_KEY, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _settings_revision_established(project: dict) -> bool:
    """True once global_settings carries a real (int) revision counter.

    Mirrors _current_settings_revision's own validity rule so "established"
    and "the value a caller must match" never disagree: absent
    global_settings, a non-dict value, or a malformed (non-int / bool)
    stored "revision" are all "not established yet" — the one legacy/
    bootstrap bucket that gets an unconditional accept-and-stamp on its next
    write (see api_update_project's _mutate_project below). A project only
    ever reaches "established" via that same stamp (PUT/PATCH always write
    current_revision + 1, i.e. >= 1), so in practice this agrees with
    ``_current_settings_revision(project) != 0`` — but it is not simply
    that check: it stays correct even against a hand-edited or
    fixture-seeded explicit ``"revision": 0``, which IS "carrying a
    revision" by the letter of the write contract even though its value
    happens to be the same as "absent".
    """
    settings = project.get("global_settings")
    if not isinstance(settings, dict):
        return False
    value = settings.get(_SETTINGS_REVISION_KEY)
    return isinstance(value, int) and not isinstance(value, bool)


def _settings_revision_conflict_payload(current_revision: int, settings: object) -> dict:
    return {
        "error": "Project settings changed since last read",
        "code": "settings_revision_conflict",
        "retryable": True,
        "current_revision": current_revision,
        "global_settings": dict(settings) if isinstance(settings, dict) else {},
    }


class _SettingsValidationError(ValueError):
    """Fail-closed: a settings patch had an unknown key or an invalid value.

    Carries every offending key at once (not just the first) so the 400
    response can report the complete problem in one round trip.
    """

    def __init__(self, unknown_keys: list, invalid_keys: dict):
        self.unknown_keys = unknown_keys
        self.invalid_keys = invalid_keys
        super().__init__("invalid project settings patch")


class _ImageBackendBlockedError(RuntimeError):
    """A locked mutation tried to activate an unavailable image backend."""

    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__(payload["error"])


def _guard_image_backend_selection(project: dict, incoming_settings: dict) -> None:
    """Require a live exact proof before a project selects local FLUX.2."""

    current_settings = project.get("global_settings")
    current_backend = (
        current_settings.get("identity_backend", "gemini_multiref")
        if isinstance(current_settings, dict)
        else "gemini_multiref"
    )
    requested_backend = incoming_settings.get("identity_backend", current_backend)
    if requested_backend == current_backend:
        return
    if requested_backend != "local_flux2_klein":
        return
    try:
        require_flux2_worker_ready(env_settings)
    except PerformanceWorkerUnavailable as exc:
        raise _ImageBackendBlockedError({
            "error": str(exc),
            "code": "local_flux2_not_ready",
            "retryable": True,
        }) from exc


def _validate_bool_setting(value):
    if not isinstance(value, bool):
        raise ValueError("must be a boolean")
    return value


def _validate_string_setting(value):
    if not isinstance(value, str):
        raise ValueError("must be a string")
    return value


def _validate_object_setting(value):
    if not isinstance(value, dict):
        raise ValueError("must be a JSON object")
    return value


def _validate_int_setting(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("must be an integer")
    return value


def _validate_nonneg_number_setting(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a number")
    if not math.isfinite(value):
        raise ValueError("must be a finite number")
    if value < 0:
        raise ValueError("must be >= 0")
    return value


def _validate_unit_interval_setting(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a number")
    if not math.isfinite(value):
        raise ValueError("must be a finite number")
    if not (0.0 <= value <= 1.0):
        raise ValueError("must be between 0 and 1")
    return float(value)


def _validate_aspect_ratio_setting(value):
    if not isinstance(value, str) or not is_supported(value):
        raise ValueError(f"unsupported aspect_ratio (supported: {SUPPORTED_ASPECT_RATIOS})")
    return value


def _validate_identity_backend_setting(value):
    if not isinstance(value, str) or value not in {
        "gemini_multiref", "local_flux2_klein",
    }:
        raise ValueError("must be one of: gemini_multiref, local_flux2_klein")
    return value


# Per-key validators for the strict partial-write path (PATCH). Deliberately
# narrower than every key the legacy whole-object PUT tolerates today —
# web/src/components/setup/inspector/*.tsx and ShotInspector.tsx already
# write several settings with no reconciled runtime consumer yet. Wiring
# those is slice 9b/9c/9d's "distinct consumer families" work; extend this
# table there rather than loosening the fail-closed default here.
#
# VoiceSection.tsx + VideoSection.tsx's own settings (TTS/voice selection,
# the lipsync cascade cluster, dialogue pace/mix, video-cascade + post-
# process controls) are covered below — slice 9c wired both components into
# the Setup page before this table caught up, so the new strict PATCH 400ed
# on every key either section writes (a 9a<->9c integration gap).
#
# IdentitySection and ImageSection settings are included only when the runtime
# has a real consumer. Retired ComfyUI sampler, step, guidance, and denoise
# controls are deliberately absent from this strict write contract.
_SETTINGS_KEY_VALIDATORS: dict[str, Callable[[object], object]] = {
    "aspect_ratio": _validate_aspect_ratio_setting,
    "music_mood": _validate_string_setting,
    "color_palette": _validate_string_setting,
    "language": _validate_string_setting,
    "master_seed": _validate_int_setting,
    "style_rules": _validate_object_setting,
    "budget_limit_usd": _validate_nonneg_number_setting,
    "identity_strictness": _validate_unit_interval_setting,
    "creative_llm": _validate_string_setting,
    "quality_judge_llm": _validate_string_setting,
    "competitive_generation": _validate_bool_setting,
    "location_research": _validate_bool_setting,
    "coherence_check_enabled": _validate_bool_setting,
    "color_drift_sensitivity": _validate_unit_interval_setting,
    "prompt_optimizer_enabled": _validate_bool_setting,
    "auto_approve": _validate_object_setting,
    "api_engines": _validate_object_setting,
    # VoiceSection.tsx — TTS provider + default voices.
    "tts_provider": _validate_string_setting,
    "default_male_voice": _validate_string_setting,
    "default_female_voice": _validate_string_setting,
    # VoiceSection.tsx — dialogue-quality toggles.
    "dialogue_mode_enabled": _validate_bool_setting,
    "forced_alignment_enabled": _validate_bool_setting,
    # VoiceSection.tsx — active lip-sync policy controls. Engine ordering is
    # purpose-owned by the backend; the removed UI priority list must not be
    # resurrected through this strict settings contract.
    "lip_sync_mode": _validate_string_setting,
    "lipsync_quality_validation": _validate_bool_setting,
    "lipsync_validation_threshold": _validate_unit_interval_setting,
    # VoiceSection.tsx — dialogue pace + music mix.
    "dialogue_target_wpm": _validate_nonneg_number_setting,
    "music_mastering": _validate_string_setting,
    # VideoSection.tsx — cascade + native-voice routing.
    "cascade_retry_limit": _validate_int_setting,
    "dialogue_voice_mode": _validate_string_setting,
    # VideoSection.tsx — post-processing / color.
    "color_grade_preset": _validate_string_setting,
    "motion_quality_threshold": _validate_unit_interval_setting,
    "scene_transitions": _validate_bool_setting,
    "transition_duration": _validate_nonneg_number_setting,
    "face_swap_enabled": _validate_bool_setting,
    # IdentitySection.tsx — retry budget and coherence floor.
    # The validators enforce the type/domain invariant each consumer needs,
    # not the narrower slider bounds (retry 1-5, guidance 2.0-5.0, coherence
    # 0.3-1.0) — same latitude cascade_retry_limit above already takes.
    "identity_retry_max": _validate_int_setting,
    "coherence_threshold": _validate_unit_interval_setting,
    # ImageSection.tsx — exact image backend selection.
    "identity_backend": _validate_identity_backend_setting,
}


def _validate_settings_patch(patch: dict) -> dict:
    """Validate a partial global_settings write.

    Fail closed: any unknown key or invalid value raises
    _SettingsValidationError listing every problem found. Callers apply
    nothing when this raises — the whole patch is atomic.
    """
    validated: dict = {}
    unknown: list = []
    invalid: dict = {}
    for key, value in patch.items():
        validator = _SETTINGS_KEY_VALIDATORS.get(key)
        if validator is None:
            unknown.append(key)
            continue
        try:
            validated[key] = validator(value)
        except ValueError as exc:
            invalid[key] = str(exc)
    if unknown or invalid:
        raise _SettingsValidationError(sorted(unknown), invalid)
    return validated


@app.route("/api/projects/<pid>", methods=["PUT"])
@_project_lock_guard
def api_update_project(pid):
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = _json_object_or_none()
    if data is None:
        return jsonify({"error": "JSON object required"}), 400
    if "id" in data and data["id"] != pid:
        return jsonify({
            "error": "Body id must match route id",
            "route_id": pid,
        }), 400

    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    has_incoming_gs = "global_settings" in data
    incoming_gs = data.get("global_settings")
    if has_incoming_gs and not isinstance(incoming_gs, dict):
        return jsonify({"error": "global_settings must be a JSON object", "code": "invalid_global_settings", "retryable": False}), 400
    if has_incoming_gs and "aspect_ratio" in incoming_gs and not is_supported(incoming_gs["aspect_ratio"]):
        return jsonify({"error": "unsupported aspect_ratio", "value": incoming_gs["aspect_ratio"],
                        "supported": SUPPORTED_ASPECT_RATIOS}), 400

    conflict = None

    def _mutate_project(project: dict):
        # Inner validation and the revision comparison use the locked latest state.
        nonlocal conflict
        Project.model_validate(project)
        if has_incoming_gs:
            # Fail-closed optimistic-concurrency guard (slice 9a; hardened
            # post-9a-review — see the module comment above this route and
            # _settings_revision_established). Once global_settings has an
            # ESTABLISHED revision, the caller MUST echo a matching one —
            # omitting "revision" no longer opts out of the check (that
            # silent omission was the exact gap: a stale whole-object PUT
            # with no "revision" key clobbered a newer revision-guarded
            # write with 200 and no conflict). Before one is established,
            # this route keeps its original opt-in behavior so a caller
            # that DOES supply an (unsolicited, wrong) "revision" on a
            # brand-new project is still held to it — only a payload that
            # omits the key entirely gets the one-time bootstrap
            # accept-and-stamp.
            current_revision = _current_settings_revision(project)
            key_present = _SETTINGS_REVISION_KEY in incoming_gs
            mismatched = (
                key_present and incoming_gs[_SETTINGS_REVISION_KEY] != current_revision
            )
            missing_while_established = (
                _settings_revision_established(project) and not key_present
            )
            if mismatched or missing_while_established:
                conflict = _settings_revision_conflict_payload(
                    current_revision, project.get("global_settings", {})
                )
                return MutationResult(None, save=False)
            _guard_image_backend_selection(project, incoming_gs)
        if "name" in data:
            project["name"] = data["name"]
        if has_incoming_gs:
            settings = project.setdefault("global_settings", {})
            settings.update(incoming_gs)
            # Recompute unconditionally so no caller (accidental or not) can
            # set the counter directly through the merge above — the stored
            # value always reflects this route's own bump, never the
            # incoming payload's claim.
            settings[_SETTINGS_REVISION_KEY] = current_revision + 1
        return project

    if not _reserve_project_admin(pid):
        return _project_busy_response(pid)
    try:
        try:
            project = mutate_project(pid, _mutate_project, timeout=HTTP_PROJECT_TIMEOUT)
        except _ImageBackendBlockedError as exc:
            return jsonify(exc.payload), 409
        if conflict is not None:
            return jsonify(conflict), 409
        if not project:
            return jsonify({"error": "Project not found"}), 404
        # PipelineCore snapshots budget/director/ensemble settings at build
        # time. A confirmed write must retire that idle snapshot before a
        # later generation can reuse it.
        _evict_cached_project_core(pid)
        return jsonify(project)
    finally:
        _release_project_admin(pid)


@app.route("/api/projects/<pid>", methods=["PATCH"])
@_project_lock_guard
def api_patch_project_settings(pid):
    """Strict partial write for project settings.

    The revision-guarded counterpart to the compat whole-object PUT above.
    Only the keys the caller sends are applied; each is validated against
    _SETTINGS_KEY_VALIDATORS — an unknown or invalid key rejects the whole
    request (400, no mutation). The caller MUST echo the last-observed
    ``global_settings.revision``; a mismatch rejects the whole request (409,
    no mutation) with the current revision so the caller can refetch and
    retry — the conflict shape a typed API client can treat as non-2xx and
    handle by refreshing authoritative state.
    """
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = _json_object_or_none()
    if data is None:
        return jsonify({"error": "JSON object required"}), 400
    if "id" in data and data["id"] != pid:
        return jsonify({
            "error": "Body id must match route id",
            "route_id": pid,
        }), 400

    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    incoming_gs = data.get("global_settings")
    if not isinstance(incoming_gs, dict):
        return jsonify({
            "error": "global_settings must be a JSON object",
            "code": "invalid_global_settings",
            "retryable": False,
        }), 400

    patch = dict(incoming_gs)
    if _SETTINGS_REVISION_KEY not in patch:
        return jsonify({
            "error": "global_settings.revision is required",
            "code": "revision_required",
            "retryable": False,
        }), 400
    expected_revision = patch.pop(_SETTINGS_REVISION_KEY)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        return jsonify({
            "error": "global_settings.revision must be an integer",
            "code": "invalid_revision",
            "retryable": False,
        }), 400

    try:
        validated = _validate_settings_patch(patch)
    except _SettingsValidationError as exc:
        payload = {
            "error": "Unknown or invalid project setting(s)",
            "code": "invalid_setting_key",
            "retryable": False,
        }
        if exc.unknown_keys:
            payload["unknown_keys"] = exc.unknown_keys
        if exc.invalid_keys:
            payload["invalid_keys"] = exc.invalid_keys
        return jsonify(payload), 400

    conflict = None

    def _mutate(project: dict):
        nonlocal conflict
        Project.model_validate(project)
        current_revision = _current_settings_revision(project)
        if expected_revision != current_revision:
            conflict = _settings_revision_conflict_payload(
                current_revision, project.get("global_settings", {})
            )
            return MutationResult(None, save=False)
        _guard_image_backend_selection(project, validated)
        settings = project.setdefault("global_settings", {})
        settings.update(validated)
        settings[_SETTINGS_REVISION_KEY] = current_revision + 1
        return project

    if not _reserve_project_admin(pid):
        return _project_busy_response(pid)
    try:
        try:
            project = mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT)
        except _ImageBackendBlockedError as exc:
            return jsonify(exc.payload), 409
        if conflict is not None:
            return jsonify(conflict), 409
        if not project:
            return jsonify({"error": "Project not found"}), 404
        _evict_cached_project_core(pid)
        return jsonify(project)
    finally:
        _release_project_admin(pid)


@app.route("/api/projects/<pid>", methods=["DELETE"])
@_project_lock_guard
def api_delete_project(pid):
    if not _reserve_project_admin(pid):
        return _project_busy_response(pid)
    try:
        try:
            identity_active = identity_project_has_active_experiment(pid)
        except Exception:
            logger.exception(
                "Identity Lab deletion fence could not be verified",
                extra={"pid": pid},
            )
            return jsonify({
                "error": "Project deletion is blocked because Identity Lab state could not be verified",
                "code": "identity_lab_fence_unavailable",
                "retryable": False,
            }), 409
        if identity_active:
            return jsonify({
                "error": "Project has an active Identity Lab experiment",
                "code": "identity_experiment_active",
                "retryable": False,
            }), 409
        if not delete_project(pid, timeout=HTTP_PROJECT_TIMEOUT):
            return jsonify({"error": "Project not found"}), 404

        # A deleted project must disappear from process-local state as well
        # as disk. The admin reservation prevents a same-id generation from
        # acquiring either cache while eviction is in progress.
        _evict_cached_project_core(pid)
        with _pipelines_lock:
            cached_bus = _progress_queues.pop(pid, None)

        # close() may wake subscribers and takes the bus's own lock, so keep
        # it outside the shared registry lock. Deletion already succeeded;
        # a close failure is diagnostic rather than a misleading HTTP 500.
        if cached_bus is not None:
            try:
                cached_bus.close()
            except Exception:
                logger.warning(
                    "Failed to close cached project event bus after deletion",
                    extra={"pid": pid},
                    exc_info=True,
                )

        return jsonify({"deleted": True})
    finally:
        _release_project_admin(pid)


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

_PENDING_CHARACTER_CREATION_KEY = "pending_character_creation"
_CHARACTER_CREATION_RECONCILIATIONS_KEY = "character_creation_reconciliations"
_PENDING_CHARACTER_STATUSES = {
    "submitting",
    "retryable",
    "reconciliation_required",
}
_CHARACTER_RECONCILIATION_CONFIRMATION = "reconciled_no_resumable_paid_work"
_CHARACTER_NAME_MAX_CHARS = 200
_CHARACTER_DESCRIPTION_MAX_CHARS = 10_000
_CHARACTER_VOICE_ID_MAX_CHARS = 200


def _character_form_metadata_or_error() -> tuple[tuple[str, str, str] | None, str | None]:
    values = (
        ("name", request.form.get("name", "Unnamed Character"), _CHARACTER_NAME_MAX_CHARS),
        ("description", request.form.get("description", ""), _CHARACTER_DESCRIPTION_MAX_CHARS),
        ("voice_id", request.form.get("voice_id", ""), _CHARACTER_VOICE_ID_MAX_CHARS),
    )
    for field, value, limit in values:
        if not isinstance(value, str) or len(value) > limit or "\x00" in value:
            return None, f"{field} must be at most {limit} characters and contain no NUL bytes"
    return (values[0][1], values[1][1], values[2][1]), None


def _bounded_character_recovery_text(value, limit: int) -> str:
    """Return one bounded, printable line for the public recovery contract."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _public_pending_character_creation(value) -> dict | None:
    """Project-safe projection: deliberately excludes paths, files and inputs."""
    if not isinstance(value, dict):
        return None
    request_id = value.get("creation_request_id")
    status = value.get("status")
    if (
        not isinstance(request_id, str)
        or not re.fullmatch(r"[0-9a-f]{32}", request_id)
        or status not in _PENDING_CHARACTER_STATUSES
    ):
        return None
    return {
        "creation_request_id": request_id,
        "name": _bounded_character_recovery_text(value.get("name"), 200)
        or "Unnamed Character",
        "status": status,
        "retryable": value.get("retryable") is True,
        "message": _bounded_character_recovery_text(value.get("message"), 500),
        "provider_job_id": (
            _bounded_character_recovery_text(value.get("provider_job_id"), 200)
            or None
        ),
        "attempt_state": (
            _bounded_character_recovery_text(value.get("attempt_state"), 64)
            or None
        ),
        "created_at": (
            _bounded_character_recovery_text(value.get("created_at"), 64)
            or None
        ),
        "updated_at": (
            _bounded_character_recovery_text(value.get("updated_at"), 64)
            or None
        ),
    }


def _character_recovery_dir(pid: str, creation_request_id: str) -> str:
    return os.path.join(
        get_project_dir(pid), "temp_uploads", creation_request_id
    )


def _character_recovery_sidecar_path(pid: str, creation_request_id: str) -> str:
    return os.path.join(
        _character_recovery_dir(pid, creation_request_id),
        ".creation-request.json",
    )


def _cleanup_character_recovery_dir(pid: str, creation_request_id: str) -> None:
    """Remove one exact request's private staging after its fence is cleared."""
    if not re.fullmatch(r"[0-9a-f]{32}", creation_request_id):
        raise ValueError("Invalid character creation request id")
    temp_root = os.path.realpath(os.path.join(get_project_dir(pid), "temp_uploads"))
    target = os.path.realpath(
        _character_recovery_dir(pid, creation_request_id)
    )
    expected = os.path.join(temp_root, creation_request_id)
    if target != expected or os.path.commonpath([temp_root, target]) != temp_root:
        raise ValueError("Unsafe character recovery cleanup target")
    if os.path.isdir(target):
        shutil.rmtree(target)


def _write_character_recovery_sidecar(
    pid: str,
    creation_request_id: str,
    payload: dict,
) -> None:
    """Atomically persist private retry inputs before entering paid dispatch."""
    recovery_dir = _character_recovery_dir(pid, creation_request_id)
    os.makedirs(recovery_dir, exist_ok=True)
    target = _character_recovery_sidecar_path(pid, creation_request_id)
    fd, temp_path = tempfile.mkstemp(
        prefix=".creation-request-", suffix=".tmp", dir=recovery_dir
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def _load_character_recovery_sidecar(
    pid: str,
    creation_request_id: str,
) -> dict | None:
    try:
        with open(
            _character_recovery_sidecar_path(pid, creation_request_id),
            "r",
            encoding="utf-8",
        ) as handle:
            value = json.load(handle)
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("creation_request_id") != creation_request_id:
        return None
    return value


def _hash_file(path: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _hash_uploaded_file(upload) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    stream = upload.stream
    try:
        position = stream.tell()
    except (AttributeError, OSError):
        position = 0
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    try:
        stream.seek(position)
    except (AttributeError, OSError):
        pass
    return digest.hexdigest(), size


def _stage_character_recovery_uploads(
    pid: str,
    creation_request_id: str,
    images: list,
) -> tuple[list[str], list[dict]]:
    project_dir = os.path.realpath(get_project_dir(pid))
    recovery_dir = _character_recovery_dir(pid, creation_request_id)
    os.makedirs(recovery_dir, exist_ok=True)
    paths: list[str] = []
    records: list[dict] = []
    for index, image in enumerate(images):
        if not image.filename:
            continue
        filename = secure_filename(image.filename)
        if not filename:
            continue
        path = os.path.join(recovery_dir, f"{index:03d}-{filename}")
        image.save(path)
        sha256, byte_size = _hash_file(path)
        relative = os.path.relpath(path, project_dir).replace(os.sep, "/")
        paths.append(path)
        records.append({
            "filename": filename,
            "relative_path": relative,
            "sha256": sha256,
            "byte_size": byte_size,
        })
    return paths, records


def _character_recovery_input_fingerprint(
    name: str,
    description: str,
    voice_id: str,
    upload_records: list[dict],
) -> str:
    safe_uploads = [
        {
            "filename": item.get("filename"),
            "sha256": item.get("sha256"),
            "byte_size": item.get("byte_size"),
        }
        for item in upload_records
    ]
    encoded = json.dumps(
        {
            "name": name,
            "description": description,
            "voice_id": voice_id,
            "uploads": safe_uploads,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_character_recovery_uploads(
    pid: str,
    creation_request_id: str,
    upload_records,
) -> list[str] | None:
    if not isinstance(upload_records, list):
        return None
    recovery_root = os.path.realpath(
        _character_recovery_dir(pid, creation_request_id)
    )
    project_root = os.path.realpath(get_project_dir(pid))
    expected_prefix = f"temp_uploads/{creation_request_id}/"
    paths: list[str] = []
    for item in upload_records:
        if not isinstance(item, dict):
            return None
        relative = item.get("relative_path")
        expected_hash = item.get("sha256")
        expected_size = item.get("byte_size")
        if (
            not isinstance(relative, str)
            or not relative.startswith(expected_prefix)
            or os.path.isabs(relative)
            or not isinstance(expected_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
            or isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
        ):
            return None
        resolved = os.path.realpath(os.path.join(project_root, relative))
        try:
            if os.path.commonpath([recovery_root, resolved]) != recovery_root:
                return None
        except ValueError:
            return None
        if not os.path.isfile(resolved):
            return None
        actual_hash, actual_size = _hash_file(resolved)
        if actual_hash != expected_hash or actual_size != expected_size:
            return None
        paths.append(resolved)
    return paths


def _resume_uploads_match(upload_records, images: list) -> bool:
    submitted = [image for image in images if image.filename]
    if len(submitted) != len(upload_records):
        return False
    for stored, image in zip(upload_records, submitted):
        if not isinstance(stored, dict):
            return False
        filename = secure_filename(image.filename or "")
        sha256, byte_size = _hash_uploaded_file(image)
        if (
            filename != stored.get("filename")
            or sha256 != stored.get("sha256")
            or byte_size != stored.get("byte_size")
        ):
            return False
    return True


def _pending_character_payload(
    creation_request_id: str,
    *,
    name: str,
    input_fingerprint: str,
    status: str = "submitting",
    retryable: bool = True,
    message: str = "Character creation is in progress and can be resumed safely.",
    provider_job_id=None,
    attempt_state=None,
    created_at: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "creation_request_id": creation_request_id,
        "name": _bounded_character_recovery_text(name, 200) or "Unnamed Character",
        "status": status,
        "retryable": retryable,
        "message": _bounded_character_recovery_text(message, 500),
        "provider_job_id": (
            _bounded_character_recovery_text(provider_job_id, 200) or None
        ),
        "attempt_state": (
            _bounded_character_recovery_text(attempt_state, 64) or None
        ),
        "created_at": created_at or now,
        "updated_at": now,
        # A one-way identity fence is safe to store in project.json and lets
        # a second worker reject changed inputs before any provider dispatch.
        "input_fingerprint": input_fingerprint,
    }


def _claim_pending_character_creation(pid: str, candidate: dict) -> tuple[dict | None, str]:
    disposition = "created"

    def _mutate(latest: dict):
        nonlocal disposition
        existing = latest.get(_PENDING_CHARACTER_CREATION_KEY)
        if existing is not None:
            if not isinstance(existing, dict):
                disposition = "malformed"
                return MutationResult(None, save=False)
            if existing.get("creation_request_id") != candidate["creation_request_id"]:
                disposition = "conflict"
                return MutationResult(existing, save=False)
            if existing.get("input_fingerprint") != candidate["input_fingerprint"]:
                disposition = "input_mismatch"
                return MutationResult(existing, save=False)
            disposition = "existing"
            return MutationResult(existing, save=False)
        latest[_PENDING_CHARACTER_CREATION_KEY] = candidate
        return candidate

    result = mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT)
    return result, disposition


def _update_pending_character_creation(
    pid: str,
    creation_request_id: str,
    *,
    status: str,
    retryable: bool,
    message: str,
    provider_job_id=None,
    attempt_state=None,
) -> dict | None:
    def _mutate(latest: dict):
        existing = latest.get(_PENDING_CHARACTER_CREATION_KEY)
        if (
            not isinstance(existing, dict)
            or existing.get("creation_request_id") != creation_request_id
        ):
            return MutationResult(None, save=False)
        updated = _pending_character_payload(
            creation_request_id,
            name=str(existing.get("name") or "Unnamed Character"),
            input_fingerprint=str(existing.get("input_fingerprint") or ""),
            status=status,
            retryable=retryable,
            message=message,
            provider_job_id=provider_job_id,
            attempt_state=attempt_state,
            created_at=str(existing.get("created_at") or "") or None,
        )
        latest[_PENDING_CHARACTER_CREATION_KEY] = updated
        return updated

    return mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT)


def _clear_pending_character_creation(
    pid: str,
    creation_request_id: str,
    *,
    reconciled: bool = False,
) -> bool:
    def _mutate(latest: dict):
        existing = latest.get(_PENDING_CHARACTER_CREATION_KEY)
        if (
            not isinstance(existing, dict)
            or existing.get("creation_request_id") != creation_request_id
        ):
            return MutationResult(False, save=False)
        if reconciled:
            history = latest.setdefault(
                _CHARACTER_CREATION_RECONCILIATIONS_KEY, []
            )
            if not isinstance(history, list):
                history = []
                latest[_CHARACTER_CREATION_RECONCILIATIONS_KEY] = history
            history.append({
                "creation_request_id": creation_request_id,
                "name": _bounded_character_recovery_text(existing.get("name"), 200),
                "previous_status": (
                    _bounded_character_recovery_text(existing.get("status"), 64)
                    or "unknown"
                ),
                "provider_job_id": (
                    _bounded_character_recovery_text(
                        existing.get("provider_job_id"), 200
                    ) or None
                ),
                "reconciled_at": datetime.now(timezone.utc).isoformat(),
                "source": "operator_ui",
            })
            del history[:-50]
        latest.pop(_PENDING_CHARACTER_CREATION_KEY, None)
        return True

    return mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT) is True


def _validated_character_resume_inputs(
    pid: str,
    creation_request_id: str,
    pending: dict,
    images: list,
) -> tuple[tuple[str, str, str, list[str]] | None, str | None]:
    internal = _load_character_recovery_sidecar(pid, creation_request_id)
    if internal is None:
        return None, "missing"
    name = internal.get("name")
    description = internal.get("description")
    voice_id = internal.get("voice_id")
    upload_records = internal.get("uploads")
    if not all(isinstance(value, str) for value in (name, description, voice_id)):
        return None, "corrupt"
    if not isinstance(upload_records, list):
        return None, "corrupt"
    fingerprint = _character_recovery_input_fingerprint(
        name, description, voice_id, upload_records
    )
    if (
        internal.get("input_fingerprint") != fingerprint
        or pending.get("input_fingerprint") != fingerprint
    ):
        return None, "corrupt"
    for key, stored in (
        ("name", name),
        ("description", description),
        ("voice_id", voice_id),
    ):
        if key in request.form and request.form.get(key) != stored:
            return None, "metadata_mismatch"
    if images and not _resume_uploads_match(upload_records, images):
        return None, "uploads_mismatch"
    image_paths = _resolve_character_recovery_uploads(
        pid, creation_request_id, upload_records
    )
    if image_paths is None:
        return None, "corrupt"
    return (name, description, voice_id, image_paths), None


def _pending_character_conflict_response(pending, *, malformed: bool = False):
    public = _public_pending_character_creation(pending)
    return jsonify({
        "error": (
            "Character creation recovery data is malformed; new paid work is "
            "blocked pending operator reconciliation."
            if malformed
            else "A recoverable character creation already owns this project. "
            "Resume or reconcile it before starting another paid request."
        ),
        "code": "character_creation_recovery_required",
        "retryable": False,
        "pending_creation": public,
    }), 409


@app.route(
    "/api/projects/<pid>/characters/pending-creation",
    methods=["GET"],
)
def api_get_pending_character_creation(pid):
    project = load_existing_project_readonly(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    raw = project.get(_PENDING_CHARACTER_CREATION_KEY)
    if raw is None:
        return jsonify({"pending_creation": None})
    public = _public_pending_character_creation(raw)
    if public is None:
        return jsonify({
            "error": "Character recovery state requires operator reconciliation.",
            "code": "character_creation_recovery_malformed",
            "retryable": False,
        }), 500
    return jsonify({"pending_creation": public})


@app.route(
    "/api/projects/<pid>/characters/pending-creation",
    methods=["DELETE"],
)
@_project_lock_guard
def api_reconcile_pending_character_creation(pid):
    if not request.is_json or not isinstance(request.json, dict):
        return jsonify({"error": "JSON object required"}), 400
    creation_request_id = request.json.get("creation_request_id")
    confirmation = request.json.get("confirmation")
    if (
        not isinstance(creation_request_id, str)
        or not re.fullmatch(r"[0-9a-f]{32}", creation_request_id)
        or confirmation != _CHARACTER_RECONCILIATION_CONFIRMATION
    ):
        return jsonify({
            "error": (
                "Exact request id and reconciliation confirmation are required."
            )
        }), 400
    if not _reserve_project_admin(pid):
        return _project_busy_response(pid)
    try:
        project = load_project(pid)
        if not project:
            return jsonify({"error": "Project not found"}), 404
        pending = project.get(_PENDING_CHARACTER_CREATION_KEY)
        if not isinstance(pending, dict):
            return jsonify({"error": "No pending character creation"}), 404
        if pending.get("creation_request_id") != creation_request_id:
            return _pending_character_conflict_response(pending)
        request_lock = FileLock(
            os.path.join(
                _character_recovery_dir(pid, creation_request_id), ".resume.lock"
            ),
            timeout=0,
        )
        try:
            request_lock.acquire()
        except FileLockTimeout:
            return jsonify({
                "error": (
                    "This character request is actively running and cannot be "
                    "reconciled yet."
                ),
                "code": "character_creation_in_progress",
                "retryable": True,
                "pending_creation": _public_pending_character_creation(pending),
            }), 409
        try:
            pending = _update_pending_character_creation(
                pid,
                creation_request_id,
                status="reconciliation_required",
                retryable=False,
                message="Operator-confirmed reconciliation is being finalized.",
                provider_job_id=pending.get("provider_job_id"),
                attempt_state=pending.get("attempt_state"),
            ) or pending
        finally:
            request_lock.release()
        _cleanup_character_recovery_dir(pid, creation_request_id)
        if not _clear_pending_character_creation(
            pid, creation_request_id, reconciled=True
        ):
            return jsonify({"error": "Pending character creation changed"}), 409
        _evict_cached_project_core(pid)
        return jsonify({"reconciled": True, "pending_creation": None})
    finally:
        _release_project_admin(pid)

@app.route("/api/projects/<pid>/characters", methods=["POST"])
@_project_lock_guard
def api_add_character(pid):
    if not _reserve_project_admin(pid):
        return _project_busy_response(pid)
    try:
        project = load_project(pid)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        creation_request_id = request.form.get("creation_request_id", "")
        if not re.fullmatch(r"[0-9a-f]{32}", creation_request_id):
            return jsonify({
                "error": (
                    "creation_request_id must be 32 lowercase hexadecimal "
                    "characters"
                )
            }), 400

        images = request.files.getlist("reference_images")
        pending = project.get(_PENDING_CHARACTER_CREATION_KEY)
        if pending is not None and not isinstance(pending, dict):
            return _pending_character_conflict_response(pending, malformed=True)
        if (
            isinstance(pending, dict)
            and pending.get("creation_request_id") != creation_request_id
        ):
            return _pending_character_conflict_response(pending)
        if (
            isinstance(pending, dict)
            and pending.get("status") == "reconciliation_required"
            and pending.get("retryable") is not True
        ):
            return jsonify({
                "error": str(
                    pending.get("message")
                    or "This character request requires operator reconciliation."
                ),
                "code": "paid_work_reconciliation_required",
                "retryable": False,
                "pending_creation": _public_pending_character_creation(pending),
            }), 409

        if isinstance(pending, dict):
            resume_inputs, resume_error = _validated_character_resume_inputs(
                pid, creation_request_id, pending, images
            )
            if resume_error in {"metadata_mismatch", "uploads_mismatch"}:
                return jsonify({
                    "error": (
                        "This creation_request_id belongs to different character "
                        "inputs. Resume it without changing the form or files."
                    ),
                    "code": "character_creation_input_mismatch",
                    "retryable": False,
                    "pending_creation": _public_pending_character_creation(pending),
                }), 409
            if resume_inputs is None:
                pending = _update_pending_character_creation(
                    pid,
                    creation_request_id,
                    status="reconciliation_required",
                    retryable=False,
                    message=(
                        "The staged recovery inputs could not be verified. New paid "
                        "work is blocked until an operator reconciles this request."
                    ),
                ) or pending
                return jsonify({
                    "error": str(pending.get("message") or "Recovery data invalid"),
                    "code": "character_creation_recovery_invalid",
                    "retryable": False,
                    "pending_creation": _public_pending_character_creation(pending),
                }), 409
            name, description, voice_id, image_paths = resume_inputs
        else:
            metadata, metadata_error = _character_form_metadata_or_error()
            if metadata is None:
                return jsonify({
                    "error": metadata_error,
                    "code": "invalid_character_metadata",
                    "retryable": False,
                }), 400
            name, description, voice_id = metadata
            image_paths, upload_records = _stage_character_recovery_uploads(
                pid, creation_request_id, images
            )
            input_fingerprint = _character_recovery_input_fingerprint(
                name, description, voice_id, upload_records
            )
            candidate = _pending_character_payload(
                creation_request_id,
                name=name,
                input_fingerprint=input_fingerprint,
            )
            pending, disposition = _claim_pending_character_creation(pid, candidate)
            if disposition in {"conflict", "malformed"}:
                _cleanup_character_recovery_dir(pid, creation_request_id)
                return _pending_character_conflict_response(
                    pending, malformed=disposition == "malformed"
                )
            if disposition == "input_mismatch":
                return jsonify({
                    "error": (
                        "This creation_request_id is already bound to different "
                        "character inputs."
                    ),
                    "code": "character_creation_input_mismatch",
                    "retryable": False,
                    "pending_creation": _public_pending_character_creation(pending),
                }), 409
            if pending is None:
                _cleanup_character_recovery_dir(pid, creation_request_id)
                return jsonify({"error": "Project not found"}), 404
            if disposition == "created":
                try:
                    _write_character_recovery_sidecar(
                        pid,
                        creation_request_id,
                        {
                            "schema_version": 1,
                            "creation_request_id": creation_request_id,
                            "name": name,
                            "description": description,
                            "voice_id": voice_id,
                            "uploads": upload_records,
                            "input_fingerprint": input_fingerprint,
                        },
                    )
                except Exception:
                    logger.exception(
                        "could not persist character recovery inputs pid=%s", pid
                    )
                    _update_pending_character_creation(
                        pid,
                        creation_request_id,
                        status="reconciliation_required",
                        retryable=False,
                        message="Recovery staging cleanup is being finalized.",
                    )
                    _cleanup_character_recovery_dir(pid, creation_request_id)
                    _clear_pending_character_creation(pid, creation_request_id)
                    return jsonify({
                        "error": "Could not persist character recovery inputs.",
                        "code": "character_creation_recovery_write_failed",
                        "retryable": False,
                    }), 500
            else:
                resume_inputs, resume_error = _validated_character_resume_inputs(
                    pid, creation_request_id, pending, images
                )
                if resume_inputs is None:
                    return jsonify({
                        "error": (
                            "This character request is already being prepared. "
                            "Retry the same request shortly."
                        ),
                        "code": "character_creation_in_progress",
                        "retryable": True,
                        "pending_creation": _public_pending_character_creation(pending),
                    }), 409
                name, description, voice_id, image_paths = resume_inputs

        # The request-specific file lock extends the in-process admin guard to
        # multiple server workers. A crashed worker releases it automatically;
        # the next same-token request then resumes against the paid ledger.
        request_lock = FileLock(
            os.path.join(
                _character_recovery_dir(pid, creation_request_id), ".resume.lock"
            ),
            timeout=0,
        )
        try:
            request_lock.acquire()
        except FileLockTimeout:
            return jsonify({
                "error": "This character request is already running.",
                "code": "character_creation_in_progress",
                "retryable": True,
                "pending_creation": _public_pending_character_creation(pending),
            }), 409

        recovery: dict[str, object] = {}
        terminal_cleanup = False
        try:
            # The reservation was saved before this boundary. Reload the
            # project so domain persistence starts from the authoritative row.
            project = load_project(pid)
            if not project:
                return jsonify({"error": "Project not found"}), 404
            core = _get_or_build_core(pid)
            character = create_character_with_images(
                project,
                name,
                description,
                reference_image_paths=image_paths,
                voice_id=voice_id,
                commit_timeout=HTTP_PROJECT_TIMEOUT,
                cost_tracker=core.cost_tracker,
                creation_request_id=creation_request_id,
                _recovery_out=recovery,
            )
        except PaidCallBudgetBlocked as exc:
            _update_pending_character_creation(
                pid,
                creation_request_id,
                status="reconciliation_required",
                retryable=False,
                message="Budget refusal confirmed no paid submission; cleanup is being finalized.",
                attempt_state=exc.snapshot.attempt.get("state"),
            )
            terminal_cleanup = True
            return jsonify({
                "error": "Project budget refused a character reference generation.",
                "code": "paid_budget_blocked",
                "retryable": False,
                "attempt_state": exc.snapshot.attempt.get("state"),
            }), 409
        except PaidCallDeferred as exc:
            attempt_state = str(exc.snapshot.attempt.get("state") or "")
            provider_job_id = exc.snapshot.attempt.get("provider_job_id") or None
            exact_resume_available = (
                isinstance(provider_job_id, str)
                and attempt_state
                in {"accepted_unknown", "running", "cancel_requested", "succeeded"}
            )
            message = (
                "Character reference generation has durable paid work pending; "
                "resume this same character request."
                if exact_resume_available
                else "Character reference billing or submission is ambiguous; "
                "automatic replay is blocked pending operator reconciliation."
            )
            pending = _update_pending_character_creation(
                pid,
                creation_request_id,
                status=(
                    "retryable"
                    if exact_resume_available
                    else "reconciliation_required"
                ),
                retryable=exact_resume_available,
                message=message,
                provider_job_id=provider_job_id,
                attempt_state=attempt_state,
            )
            return jsonify({
                "error": message,
                "code": (
                    "paid_work_pending"
                    if exact_resume_available
                    else "paid_work_reconciliation_required"
                ),
                "retryable": exact_resume_available,
                "attempt_state": attempt_state,
                "provider_job_id": provider_job_id,
                "pending_creation": _public_pending_character_creation(pending),
            }), 409
        except PaidCallUnbilled as exc:
            _update_pending_character_creation(
                pid,
                creation_request_id,
                status="reconciliation_required",
                retryable=False,
                message="Provider rejection was confirmed unbilled; cleanup is being finalized.",
                attempt_state=exc.attempt.get("state"),
            )
            terminal_cleanup = True
            return jsonify({
                "error": "Character reference generation was rejected before billing.",
                "code": "provider_rejected_unbilled",
                "retryable": False,
                "attempt_state": exc.attempt.get("state"),
            }), 502
        except ArtifactVersionError:
            logger.exception(
                "character artifact indexing is pending for pid=%s", pid
            )
            message = (
                "Character references were generated but immutable indexing is "
                "pending; resume this same character request."
            )
            pending = _update_pending_character_creation(
                pid,
                creation_request_id,
                status="retryable",
                retryable=True,
                message=message,
            )
            return jsonify({
                "error": message,
                "code": "artifact_version_pending",
                "retryable": True,
                "pending_creation": _public_pending_character_creation(pending),
            }), 503
        except ValueError as exc:
            # Includes the A3 single-face guard and request-token reuse with
            # different inputs. Both are caller-correctable validation errors.
            _update_pending_character_creation(
                pid,
                creation_request_id,
                status="reconciliation_required",
                retryable=False,
                message="Validation failed before billable work; cleanup is being finalized.",
            )
            terminal_cleanup = True
            return jsonify({"error": str(exc)}), 400
        except ProjectLockError:
            # Let the outer cross-process operation guard translate domain
            # lock contention into the standard retryable HTTP 409. Preserve
            # the durable request reservation so a potentially paid attempt
            # remains resumable rather than being discarded as a generic 500.
            raise
        except Exception:
            logger.exception(
                "character creation failed with unresolved provider state pid=%s",
                pid,
            )
            message = (
                "Character creation stopped with an unknown provider outcome. "
                "New paid work is blocked pending operator reconciliation."
            )
            pending = _update_pending_character_creation(
                pid,
                creation_request_id,
                status="reconciliation_required",
                retryable=False,
                message=message,
            )
            return jsonify({
                "error": message,
                "code": "character_creation_reconciliation_required",
                "retryable": False,
                "pending_creation": _public_pending_character_creation(pending),
            }), 500
        finally:
            request_lock.release()
            if terminal_cleanup:
                _cleanup_character_recovery_dir(pid, creation_request_id)
                _clear_pending_character_creation(pid, creation_request_id)

        # The cached creative services hold a project snapshot. The durable
        # tracker has finished its writes, so evict the now-stale core and let
        # the next operation rebuild against the newly added character.
        _cleanup_character_recovery_dir(pid, creation_request_id)
        _clear_pending_character_creation(pid, creation_request_id)
        _evict_cached_project_core(pid)
        status = 200 if recovery.get("idempotent") is True else 201
        return jsonify(character), status
    finally:
        _release_project_admin(pid)


@app.route("/api/projects/<pid>/characters/<cid>", methods=["PUT"])
@_project_lock_guard
@_project_admin_guard
def api_update_character(pid, cid):
    """Update an existing character's fields. Supports JSON or multipart (for file uploads)."""
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # P1-3 part 12 (Variant 1 full): outer boundary validate — fail fast
    # on malformed project before lock acquisition.
    # Project.model_validate(...) raises ValidationError UNCONDITIONALLY
    # on shape mismatch (race protection requires deterministic raise; NOT
    # gated by CINEMA_STRICT_SCHEMA).  See docs/MIGRATION-PATTERN-pydantic-
    # caller.md §"Variant 1".
    Project.model_validate(project)  # outer boundary validate
    char = next((c for c in project["characters"] if c["id"] == cid), None)
    if not char:
        return jsonify({"error": "Character not found"}), 404

    if request.files.getlist("reference_images"):
        try:
            identity_active = identity_character_has_active_experiment(pid, cid)
        except Exception:
            logger.exception(
                "Identity Lab character-mutation fence could not be verified",
                extra={"pid": pid, "character_id": cid},
            )
            return jsonify({
                "error": "Reference replacement is blocked because Identity Lab state could not be verified",
                "code": "identity_lab_fence_unavailable",
                "retryable": False,
            }), 409
        if identity_active:
            return jsonify({
                "error": "Character has an active Identity Lab experiment",
                "code": "identity_experiment_active",
                "retryable": False,
            }), 409

    # Accept both JSON and form data
    if request.is_json:
        data = request.json or {}
    else:
        data = request.form.to_dict()

    # Handle reference image uploads.
    #
    # A3 single-face enforcement, PUT path: an image arriving via update is the
    # same registration event as create — multi-face references corrupt every
    # downstream identity score, so they must not enter via either door. Same
    # 400-with-message contract as api_add_character's ValueError path.
    #
    # bug_001 (cloud review): VALIDATE IN A STAGING DIR before moving anything
    # into char_dir. Writing straight into char_dir (then os.remove on
    # rejection) destroyed a pre-existing valid reference whenever an uploaded
    # filename collided with it — secure_filename is deterministic, f.save
    # truncates 'wb', and the cleanup loop then deleted the clobbered file
    # while the 400 returned before _mutate_project, leaving the record
    # pointing at a now-missing path. Staging means a rejected (or colliding)
    # upload never touches an existing reference.
    saved_paths = []
    if request.files.getlist("reference_images"):
        import shutil
        import tempfile
        from domain.character_manager import DEEPFACE_AVAILABLE, _count_faces
        project_dir = get_project_dir(pid)
        char_dir = os.path.join(project_dir, "characters", cid)
        os.makedirs(char_dir, exist_ok=True)
        with tempfile.TemporaryDirectory() as staging:
            staged = []  # (tmp_path, safe_name) — index-prefixed temp names so
            # same-request duplicate filenames don't clobber each other in staging
            for i, f in enumerate(request.files.getlist("reference_images")):
                if f.filename:
                    safe_name = secure_filename(f.filename) or "file"
                    tmp_path = os.path.join(staging, f"{i}_{safe_name}")
                    f.save(tmp_path)
                    staged.append((tmp_path, safe_name))
            if DEEPFACE_AVAILABLE:
                for tmp_path, safe_name in staged:
                    n = _count_faces(tmp_path)
                    if n >= 2:
                        return jsonify({
                            "error": (
                                f"Reference image '{safe_name}' contains "
                                f"{n} faces but exactly 1 is required. "
                                f"Provide a single-person reference photo."
                            )
                        }), 400
            # All uploads validated — commit them into char_dir now.
            for tmp_path, safe_name in staged:
                dst = os.path.join(char_dir, safe_name)
                shutil.move(tmp_path, dst)
                saved_paths.append(dst)
            # FIX-REFWRITE: persist project-relative (Product invariant #6)
            # via the SAME chokepoint create_character_with_images already
            # uses on the create path -- domain.character_manager's readers
            # (get_reference_image / get_character_embedding /
            # get_multi_angle_refs) resolve through
            # _resolve_stored_media_path, which accepts both this relative
            # shape and a legacy absolute path, so this is a pure write-side
            # fix with no reader change required.
            saved_paths = [_to_project_relative(project_dir, p) for p in saved_paths]

    def _mutate_project(latest_project: dict):
        # P1-3 part 12 (Variant 1 full): inner validate + typed-iterate-
        # for-find.  Project.model_validate(latest_project) validates the
        # latest snapshot the mutator sees; race protection requires this
        # deterministic raise on shape mismatch (NOT gated by
        # CINEMA_STRICT_SCHEMA).  Typed-iterate for FIND; dict-write to
        # MUTATE under the lock.  Index parity between
        # latest_typed.characters[i] and latest_project["characters"][i]
        # is preserved by pydantic list-order invariant (see pattern doc
        # §"Caveat: pydantic list-order preservation").
        latest_typed = Project.model_validate(latest_project)
        for i, char in enumerate(latest_typed.characters):
            if char.id == cid:
                latest_char = latest_project["characters"][i]
                for field in ["name", "description", "voice_id", "physical_traits"]:
                    if field in data:
                        latest_char[field] = data[field]
                if saved_paths:
                    refs = latest_char.setdefault("reference_images", [])
                    for save_path in saved_paths:
                        if save_path not in refs:
                            refs.append(save_path)
                    if not latest_char.get("canonical_reference"):
                        latest_char["canonical_reference"] = saved_paths[0]
                return latest_char
        return MutationResult(None, save=False)

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
@_project_admin_guard
def api_remove_character(pid, cid):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if not any(character.get("id") == cid for character in project.get("characters", [])):
        return jsonify({"error": "Character not found"}), 404
    try:
        identity_active = identity_character_has_active_experiment(pid, cid)
    except Exception:
        logger.exception(
            "Identity Lab character-deletion fence could not be verified",
            extra={"pid": pid, "character_id": cid},
        )
        return jsonify({
            "error": "Character deletion is blocked because Identity Lab state could not be verified",
            "code": "identity_lab_fence_unavailable",
            "retryable": False,
        }), 409
    if identity_active:
        return jsonify({
            "error": "Character has an active Identity Lab experiment",
            "code": "identity_experiment_active",
            "retryable": False,
        }), 409
    if remove_character(project, cid, timeout=HTTP_PROJECT_TIMEOUT):
        return jsonify({"deleted": True})
    return jsonify({"error": "Character not found"}), 404


class _DrivingVideoTooLarge(ValueError):
    pass


class _DrivingVideoEmpty(ValueError):
    pass


def _driving_video_destination(pid: str, scene_id: str, sid: str) -> tuple[str, str] | None:
    """Resolve one shot-owned destination without trusting persisted IDs as paths."""

    for component in (scene_id, sid):
        if (
            not isinstance(component, str)
            or not component
            or len(component) > 200
            or component in {".", ".."}
            or "\x00" in component
            or os.path.basename(component) != component
        ):
            return None

    project_dir = os.path.realpath(get_project_dir(pid))
    performance_root_path = os.path.join(project_dir, "performance_inputs")
    os.makedirs(performance_root_path, exist_ok=True)
    performance_root = os.path.realpath(performance_root_path)
    dest_dir = os.path.realpath(os.path.join(performance_root, scene_id, sid))
    try:
        if (
            os.path.commonpath([project_dir, performance_root]) != project_dir
            or os.path.commonpath([performance_root, dest_dir]) != performance_root
            or dest_dir == performance_root
        ):
            return None
    except ValueError:
        return None
    os.makedirs(dest_dir, exist_ok=True)
    return dest_dir, os.path.join(dest_dir, "driving.mp4")


def _stage_driving_video_upload(file_obj, dest_dir: str) -> tuple[str, int]:
    """Copy an untrusted upload into a bounded, fsynced destination sibling."""

    fd, staged_path = tempfile.mkstemp(
        prefix=".driving-upload-",
        suffix=".mp4",
        dir=dest_dir,
    )
    keep_stage = False
    try:
        written = 0
        with os.fdopen(fd, "wb") as staged:
            while True:
                chunk = file_obj.stream.read(_DRIVING_VIDEO_UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > _DRIVING_VIDEO_MAX_BYTES:
                    raise _DrivingVideoTooLarge
                staged.write(chunk)
            if written == 0:
                raise _DrivingVideoEmpty
            staged.flush()
            os.fsync(staged.fileno())
        keep_stage = True
        return staged_path, written
    finally:
        if not keep_stage:
            try:
                os.remove(staged_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning(
                    "Could not remove rejected driving-video stage %s",
                    staged_path,
                    exc_info=True,
                )


def _performance_upload_paid_work_fence(
    pid: str,
    video_id: str,
    shot: Mapping[str, object],
):
    """Return a 409 response while changing input could orphan paid work."""

    from cinema.shots.controller import (
        _PERFORMANCE_REQUEST_ACTIVE_STATES,
        _performance_paid_attempts,
        _take_reconciles_paid_attempt,
    )
    from cost_tracker import PAID_ATTEMPT_ACTIVE_STATES

    current_request = shot.get("performance_generation_request")
    if (
        isinstance(current_request, Mapping)
        and str(current_request.get("status") or "")
        in _PERFORMANCE_REQUEST_ACTIVE_STATES
    ):
        return jsonify({
            "code": "performance_request_active",
            "retryable": True,
            "error": (
                "The driving video cannot be replaced while the saved "
                "performance request requires recovery"
            ),
            "request": dict(current_request),
        }), 409

    try:
        tracker = _get_or_build_core(pid).cost_tracker
        attempts = _performance_paid_attempts(
            tracker,
            video_id=video_id,
            shot_id=str(shot.get("id") or ""),
        )
    except Exception:
        # Keep this boundary deterministic even when the cached core or its
        # database cannot be opened. Input replacement is never worth losing
        # all-provider paid-job authority.
        logger.warning(
            "Driving-video upload could not verify paid performance work",
            exc_info=True,
            extra={"pid": pid, "shot_id": shot.get("id")},
        )
        return jsonify({
            "code": "performance_authority_unavailable",
            "retryable": True,
            "error": (
                "Performance paid-work authority is unavailable; driving "
                "video replacement is blocked"
            ),
        }), 409

    if attempts is None:
        return jsonify({
            "code": "performance_authority_unavailable",
            "retryable": True,
            "error": (
                "Performance paid-work authority is unavailable; driving "
                "video replacement is blocked"
            ),
        }), 409

    blocking_attempt = next(
        (
            attempt
            for attempt in attempts
            if str(attempt.get("state") or "") in PAID_ATTEMPT_ACTIVE_STATES
            or (
                str(attempt.get("state") or "") == "succeeded"
                and not _take_reconciles_paid_attempt(shot, attempt)
            )
        ),
        None,
    )
    if blocking_attempt is not None:
        return jsonify({
            "code": "provider_job_deferred",
            "retryable": True,
            "error": (
                "The driving video cannot be replaced until existing "
                "performance provider work is reconciled"
            ),
            "engine": str(blocking_attempt.get("engine") or ""),
            "paid_attempt": blocking_attempt,
        }), 409
    return None


@app.route("/api/projects/<pid>/shots/<sid>/upload-driving-video", methods=["POST"])
@_project_lock_guard
@_project_stage_guard
def api_upload_driving_video(pid, sid):
    """Operator upload of a driving video for a specific shot.

    Validated bytes are retained under a content-addressed, project-relative
    path. Replacements move only the active pointer: historical input bytes,
    performance takes, and artifact-ledger provenance remain immutable.
    """
    pipeline = _get_running_pipeline(pid)
    active_stage = str(getattr(pipeline, "current_stage", "") or "")
    if pipeline is not None and active_stage != "PERFORMANCE_REVIEW":
        return _require_exact_pipeline_stage(pid, "PERFORMANCE_REVIEW")

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
    located = next(
        (
            (scene.id, shot)
            for scene in project_typed.scenes
            for shot in scene.shots
            if shot.id == sid
        ),
        None,
    )
    if located is None:
        return jsonify({"error": "Shot not found in project"}), 404
    scene_id, initial_shot = located

    paid_work_fence = _performance_upload_paid_work_fence(
        pid,
        str(project.get("id") or pid),
        initial_shot.model_dump(),
    )
    if paid_work_fence is not None:
        return paid_work_fence

    content_length = request.content_length
    if (
        content_length is not None
        and content_length
        > _DRIVING_VIDEO_MAX_BYTES + _DRIVING_VIDEO_MULTIPART_OVERHEAD_BYTES
    ):
        return jsonify({
            "error": "Driving video exceeds the upload size limit",
            "max_bytes": _DRIVING_VIDEO_MAX_BYTES,
        }), 413

    file_obj = request.files.get("driving_video")
    if not file_obj or not file_obj.filename:
        return jsonify({"error": "No file uploaded under field 'driving_video'"}), 400

    destination = _driving_video_destination(pid, scene_id, sid)
    if destination is None:
        return jsonify({"error": "Shot media path is unsafe"}), 400
    dest_dir, _legacy_dest_path = destination
    project_dir = os.path.realpath(get_project_dir(pid))

    staged_path = None
    published_path = None
    published_new = False
    try:
        try:
            staged_path, byte_size = _stage_driving_video_upload(file_obj, dest_dir)
        except _DrivingVideoTooLarge:
            return jsonify({
                "error": "Driving video exceeds the upload size limit",
                "max_bytes": _DRIVING_VIDEO_MAX_BYTES,
            }), 413
        except _DrivingVideoEmpty:
            return jsonify({"error": "Driving video is empty"}), 400

        validation_error = validate_video_artifact(
            staged_path,
            min_dimensions=_DRIVING_VIDEO_MIN_DIMENSIONS,
            max_dimensions=_DRIVING_VIDEO_MAX_DIMENSIONS,
            max_pixels=_DRIVING_VIDEO_MAX_PIXELS,
            max_duration_s=_DRIVING_VIDEO_MAX_DURATION_S,
        )
        if validation_error is not None:
            return jsonify({
                "error": "Driving video failed validation",
                "details": validation_error,
            }), 400

        with open(staged_path, "rb") as staged_handle:
            digest = hashlib.file_digest(staged_handle, "sha256").hexdigest()
        published_path = os.path.join(dest_dir, f"driving-{digest}.mp4")
        if os.path.exists(published_path):
            with open(published_path, "rb") as retained_handle:
                retained_digest = hashlib.file_digest(
                    retained_handle, "sha256"
                ).hexdigest()
            if retained_digest != digest:
                return jsonify({"error": "Driving video history is corrupted"}), 500
            os.remove(staged_path)
            staged_path = None
        else:
            os.replace(staged_path, published_path)
            staged_path = None
            published_new = True

        relative_path = os.path.relpath(published_path, project_dir)
        if relative_path == os.pardir or relative_path.startswith(os.pardir + os.sep):
            raise OSError("Driving video publication escaped the project root")

        def _selection_matches(current_path: object) -> bool:
            if not isinstance(current_path, str) or not current_path:
                return False
            if current_path == relative_path:
                return True
            candidate = (
                current_path
                if os.path.isabs(current_path)
                else os.path.join(project_dir, current_path)
            )
            return os.path.realpath(candidate) == os.path.realpath(published_path)

        # Exact-byte retries are selection-idempotent. Do not mint a duplicate
        # artifact version, invalidate an approval, or append review/history
        # events when these bytes are already the active revision.
        if _selection_matches(initial_shot.driving_video_path):
            matching_history = next(
                (
                    entry
                    for entry in reversed(initial_shot.driving_video_history or [])
                    if isinstance(entry, dict)
                    and entry.get("sha256") == digest
                    and _selection_matches(entry.get("path"))
                ),
                {},
            )
            return jsonify({
                "uploaded": True,
                "unchanged": True,
                "path": relative_path,
                "sha256": digest,
                "artifact_id": str(matching_history.get("artifact_id") or ""),
                "invalidated_performance_take_id": "",
                "requires_performance_regeneration": False,
            }), 200

        try:
            artifact = record_auxiliary_version(
                pid,
                "driving_video",
                sid,
                published_path,
                parameters={
                    "scene_id": scene_id,
                    "shot_id": sid,
                    "sha256": digest,
                    "size_bytes": byte_size,
                },
                project_snapshot=project,
                project_root=project_dir,
            )
        except ArtifactVersionError as exc:
            if published_new:
                try:
                    os.remove(published_path)
                    published_new = False
                except OSError:
                    logger.warning(
                        "Could not remove unindexed driving-video revision %s",
                        published_path,
                        exc_info=True,
                    )
            logger.warning(
                "Driving-video provenance indexing failed for project=%s shot=%s: %s",
                pid,
                sid,
                exc,
            )
            return jsonify({"error": "Driving video provenance could not be recorded"}), 500

        upload_record = {
            "path": relative_path,
            "sha256": digest,
            "size_bytes": byte_size,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "artifact_id": artifact["artifact_id"],
        }
        invalidated_take_id = ""

        def _mutate(latest):
            nonlocal invalidated_take_id
            # P1-3 part 12 (Variant 1 full): inner validate + typed-iterate-
            # for-find.  Project.model_validate(latest) validates the latest
            # snapshot the mutator sees; race protection requires this
            # deterministic raise on shape mismatch (NOT gated by
            # CINEMA_STRICT_SCHEMA).  Typed-iterate for FIND; dict-write to
            # MUTATE under the lock.  Index parity between
            # latest_typed.scenes[i].shots[j] and latest["scenes"][i]["shots"][j]
            # is preserved by pydantic list-order invariant (see pattern doc
            # §"Caveat: pydantic list-order preservation").
            latest_typed = Project.model_validate(latest)
            for i, scn in enumerate(latest_typed.scenes):
                for j, shot in enumerate(scn.shots):
                    if shot.id == sid:
                        project_shot = latest["scenes"][i]["shots"][j]
                        if _selection_matches(project_shot.get("driving_video_path")):
                            return MutationResult(
                                {"path": relative_path, "unchanged": True},
                                save=False,
                            )
                        invalidated_take_id = str(
                            project_shot.get("approved_performance_take_id") or ""
                        )
                        project_shot["driving_video_path"] = relative_path
                        project_shot.setdefault("driving_video_history", []).append(
                            upload_record
                        )
                        # New input bytes invalidate only the active decision.
                        # Historical takes and their old input revisions remain.
                        project_shot["approved_performance_take_id"] = ""
                        project_shot["performance_engine"] = ""
                        project_shot["performance_skip"] = None
                        current_request = project_shot.get(
                            "performance_generation_request"
                        )
                        if isinstance(current_request, dict):
                            superseded_request = dict(current_request)
                            superseded_request.update({
                                "status": "superseded_input",
                                "superseded_at": upload_record["uploaded_at"],
                                "superseded_by_driving_video_path": relative_path,
                                "superseded_by_driving_video_sha256": digest,
                                "updated_at": upload_record["uploaded_at"],
                            })
                            project_shot.setdefault(
                                "performance_generation_request_history", []
                            ).append(superseded_request)
                            project_shot["performance_generation_request"] = (
                                superseded_request
                            )
                        project_shot.setdefault("performance_review_history", []).append({
                            "id": f"performance_review_{uuid.uuid4().hex}",
                            "action": "upload",
                            "created_at": upload_record["uploaded_at"],
                            "driving_video_path": relative_path,
                            "driving_video_sha256": digest,
                            "previous_approved_performance_take_id": invalidated_take_id,
                        })
                        return MutationResult(
                            {"path": relative_path, "unchanged": False},
                            save=True,
                        )
            return MutationResult(None, save=False)

        try:
            saved_path = mutate_project(
                pid,
                _mutate,
                timeout=HTTP_PROJECT_TIMEOUT,
                snapshot=project,
            )
        except BaseException:
            # Provenance was durably indexed before the active pointer. Keep
            # its exact bytes even when project selection fails; deleting them
            # here would leave the artifact ledger pointing at missing data.
            logger.warning(
                "Driving-video revision was indexed but not selected for "
                "project=%s shot=%s; retaining immutable bytes",
                pid,
                sid,
            )
            raise
        if not isinstance(saved_path, dict) or not saved_path.get("path"):
            logger.warning(
                "Driving-video revision was indexed but its active selection "
                "missed project=%s shot=%s; retaining immutable bytes",
                pid,
                sid,
            )
            return jsonify({"error": "Shot not found"}), 404
        if saved_path.get("unchanged") is True:
            return jsonify({
                "uploaded": True,
                "unchanged": True,
                "path": relative_path,
                "sha256": digest,
                "artifact_id": artifact["artifact_id"],
                "invalidated_performance_take_id": "",
                "requires_performance_regeneration": False,
            }), 200
        return jsonify({
            "uploaded": True,
            "unchanged": False,
            "path": saved_path["path"],
            "sha256": digest,
            "artifact_id": artifact["artifact_id"],
            "invalidated_performance_take_id": invalidated_take_id,
            "requires_performance_regeneration": True,
        }), 201
    except OSError as exc:
        logger.warning(
            "Driving-video upload storage failed for project=%s shot=%s: %s",
            pid,
            sid,
            exc,
        )
        return jsonify({"error": "Driving video could not be stored"}), 500
    finally:
        if staged_path is not None:
            try:
                os.remove(staged_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning(
                    "Could not remove driving-video stage %s",
                    staged_path,
                    exc_info=True,
                )


@app.route("/api/projects/<pid>/shots/<sid>/performance", methods=["DELETE"])
@_project_lock_guard
def api_clear_performance(pid, sid):
    """Operator clears a shot's performance take so the next run regenerates.
    Used by the PERFORMANCE_REVIEW gate's "re-record" affordance.
    """
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # P1-3 part 12 (Variant 1 full): outer boundary validate — fail fast
    # on malformed project before lock acquisition.
    # Project.model_validate(...) raises ValidationError UNCONDITIONALLY
    # on shape mismatch (race protection requires deterministic raise; NOT
    # gated by CINEMA_STRICT_SCHEMA).  See docs/MIGRATION-PATTERN-pydantic-
    # caller.md §"Variant 1".
    Project.model_validate(project)  # outer boundary validate

    def _mutate(latest):
        # P1-3 part 12 (Variant 1 full): inner validate + typed-iterate-
        # for-find.  Project.model_validate(latest) validates the latest
        # snapshot the mutator sees; race protection requires this
        # deterministic raise on shape mismatch (NOT gated by
        # CINEMA_STRICT_SCHEMA).  Typed-iterate for FIND; dict-write to
        # MUTATE under the lock.  Index parity between
        # latest_typed.scenes[i].shots[j] and latest["scenes"][i]["shots"][j]
        # is preserved by pydantic list-order invariant.
        latest_typed = Project.model_validate(latest)
        for i, scn in enumerate(latest_typed.scenes):
            for j, shot in enumerate(scn.shots):
                if shot.id == sid:
                    latest["scenes"][i]["shots"][j]["approved_performance_take_id"] = ""
                    latest["scenes"][i]["shots"][j]["performance_engine"] = ""
                    return MutationResult(True, save=True)
        return MutationResult(None, save=False)

    cleared = mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT, snapshot=project)
    if not cleared:
        return jsonify({"error": "Shot not found"}), 404
    return jsonify({"cleared": True})


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
        # FIX-REFWRITE: persist project-relative (Product invariant #6) --
        # objects are the same class of project-owned reference-image
        # output as characters/locations; reuses the SAME chokepoint
        # create_character_with_images / create_location_with_images use.
        image_paths = [_to_project_relative(project_dir, p) for p in image_paths]

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

    # P1-3 part 12 (Variant 1 full): outer boundary validate — fail fast
    # on malformed project before lock acquisition.
    # Project.model_validate(...) raises ValidationError UNCONDITIONALLY
    # on shape mismatch (race protection requires deterministic raise; NOT
    # gated by CINEMA_STRICT_SCHEMA).  See docs/MIGRATION-PATTERN-pydantic-
    # caller.md §"Variant 1".
    Project.model_validate(project)  # outer boundary validate

    obj = get_object(project, oid)
    if not obj:
        return jsonify({"error": "Object not found"}), 404

    data = (request.json or {}) if request.is_json else request.form.to_dict()

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
        # FIX-REFWRITE: persist project-relative (Product invariant #6) --
        # same chokepoint as api_add_object's create path above.
        saved_paths = [_to_project_relative(project_dir, p) for p in saved_paths]

    def _mutate_project(latest_project: dict):
        # P1-3 part 12 (Variant 1 full, remove_object deviation): inner
        # validate for race protection — Project.model_validate(latest_project)
        # raises ValidationError UNCONDITIONALLY on shape mismatch (NOT gated
        # by CINEMA_STRICT_SCHEMA).  Typed-iterate-for-find is NOT applicable
        # for objects: Project.extra="allow" stores objects as raw dicts (no
        # typed List[Object]), so items are accessed via dict-style o["id"]
        # comparison — mirrors B-005's remove_object deviation at c296105.
        # Race protection from inner validate is preserved regardless.
        Project.model_validate(latest_project)
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

    # Read project-level location_research toggle (default OFF).
    # Stored at project["global_settings"]["location_research"]; written via
    # PUT /api/projects/<pid> → global_settings.update(data["global_settings"]).
    auto_research = (
        project.get("global_settings", {}).get("location_research", False) is True
    )

    location = create_location_with_images(
        project, name, description,
        reference_image_paths=image_paths,
        lighting=lighting,
        time_of_day=time_of_day,
        weather=weather,
        commit_timeout=HTTP_PROJECT_TIMEOUT,
        auto_research=auto_research,
        cost_tracker=_get_or_build_core(pid).cost_tracker,
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
        # FIX-REFWRITE: persist project-relative (Product invariant #6) --
        # mirrors create_location_with_images's create-path fix via the
        # SAME chokepoint (domain.location_manager's readers resolve
        # through _resolve_stored_media_path, which already accepts both
        # this relative shape and a legacy absolute path).
        saved_paths = [_to_project_relative(project_dir, p) for p in saved_paths]

    def _mutate_project(latest_project: dict):
        # P1-3 part 12 (Variant 1 full): inner validate + typed-iterate-
        # for-find.  Project.model_validate(latest_project) validates the
        # latest snapshot the mutator sees; race protection requires this
        # deterministic raise on shape mismatch (NOT gated by
        # CINEMA_STRICT_SCHEMA).  Outer boundary validate ALREADY exists at
        # the P1-3 part 5 migration above (Project.model_validate(project));
        # do NOT add a second outer validate here.  Typed-iterate for FIND;
        # dict-write to MUTATE under the lock.  Index parity between
        # latest_typed.locations[i] and latest_project["locations"][i] is
        # preserved by pydantic list-order invariant.
        latest_typed = Project.model_validate(latest_project)
        for i, loc in enumerate(latest_typed.locations):
            if loc.id == lid:
                latest_location = latest_project["locations"][i]
                for field in ["name", "description", "lighting", "time_of_day", "weather"]:
                    if field in data:
                        latest_location[field] = data[field]
                if saved_paths:
                    refs = latest_location.setdefault("reference_images", [])
                    for save_path in saved_paths:
                        if save_path not in refs:
                            refs.append(save_path)
                return latest_location
        return MutationResult(None, save=False)

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
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = _json_object_or_none()
    if data is None:
        return jsonify({"error": "JSON object required"}), 400
    if "id" in data and data["id"] != sid:
        return jsonify({
            "error": "Body id must match route id",
            "route_id": sid,
        }), 400

    shots_are_updated = "shots" in data
    proposed_shots = data.get("shots")
    if shots_are_updated:
        if not isinstance(proposed_shots, list):
            return jsonify({"error": "shots must be a JSON array"}), 400
        for index, shot in enumerate(proposed_shots):
            if not isinstance(shot, dict):
                return jsonify({
                    "error": f"shots[{index}] must be a JSON object",
                }), 400
            unsupported_fields = sorted(
                set(shot).difference(
                    Shot.model_fields,
                    _PUBLIC_SHOT_COMPATIBILITY_TYPES,
                )
            )
            if unsupported_fields:
                return jsonify({
                    "error": (
                        f"shots[{index}] contains unsupported fields: "
                        + ", ".join(unsupported_fields)
                    ),
                }), 400
            if (
                "target_api" not in shot
                or not isinstance(shot["target_api"], str)
            ):
                return jsonify({
                    "error": (
                        f"shots[{index}].target_api must be a string"
                    ),
                }), 400
            if any(
                field in shot
                and not isinstance(
                    shot[field],
                    _PUBLIC_SHOT_COMPATIBILITY_TYPES[field],
                )
                for field in _PUBLIC_SHOT_COMPATIBILITY_TYPES
            ):
                return jsonify({
                    "error": f"shots[{index}] does not match the shot schema",
                }), 400
            if not optimizer_cache_is_valid(
                shot.get("optimizer_cache", {}),
            ):
                return jsonify({
                    "error": f"shots[{index}] does not match the shot schema",
                }), 400
            try:
                # The normal persistence validator is intentionally
                # compatibility-permissive.  A public replacement payload is
                # a different boundary: reject type coercion before entering
                # the project lock so a malformed member cannot partially
                # update the containing scene.
                Shot.model_validate(shot, strict=True)
            except ValueError:
                return jsonify({
                    "error": f"shots[{index}] does not match the shot schema",
                }), 400

    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    def _mutate_project(latest_project: dict):
        latest_typed = Project.model_validate(latest_project)
        matching_scene_indices = [
            index
            for index, scene in enumerate(latest_typed.scenes)
            if scene.id == sid
        ]
        if not matching_scene_indices:
            return MutationResult(None, save=False)
        scene_index = matching_scene_indices[0]

        if shots_are_updated:
            latest_matches: dict[str, list[tuple[str, str]]] = {}
            for scene in latest_typed.scenes:
                for shot in scene.shots:
                    latest_matches.setdefault(shot.id, []).append(
                        (scene.id, shot.target_api)
                    )
            proposed_counts = Counter(
                shot.get("id")
                for shot in proposed_shots
                if isinstance(shot.get("id"), str)
            )
            policy_snapshot = _video_policy_runtime_snapshot()
            policy_date = _video_policy_current_date()
            settings = latest_project.get("global_settings", {})
            api_engines = (
                settings.get("api_engines", {})
                if isinstance(settings, Mapping)
                else {}
            )
            aspect_ratio = (
                settings.get("aspect_ratio", DEFAULT_ASPECT_RATIO)
                if isinstance(settings, Mapping)
                else DEFAULT_ASPECT_RATIO
            )
            for shot in proposed_shots:
                shot_id = (
                    shot.get("id")
                    if isinstance(shot.get("id"), str)
                    else ""
                )
                matches = latest_matches.get(shot_id, [])
                may_grandfather = (
                    bool(shot_id)
                    and len(matching_scene_indices) == 1
                    and len(matches) == 1
                    and matches[0][0] == sid
                    and proposed_counts[shot_id] == 1
                )
                current_target = (
                    matches[0][1]
                    if may_grandfather
                    else None
                )
                _raise_if_target_rejected(
                    shot["target_api"],
                    shot_id=shot_id,
                    current_target=current_target,
                    may_grandfather=may_grandfather,
                    snapshot=policy_snapshot,
                    on_date=policy_date,
                    api_engines=api_engines,
                    aspect_ratio=aspect_ratio,
                )

        if len(matching_scene_indices) != 1:
            return MutationResult(None, save=False)

        # The path selects an immutable scene identity. An equal body ID is
        # accepted for full-object round-trips but never written back.
        scene_updates = {
            field: value
            for field, value in data.items()
            if field != "id"
        }
        if shots_are_updated:
            scene_updates["num_shots"] = len(proposed_shots)
        latest_project["scenes"][scene_index].update(scene_updates)
        return latest_project["scenes"][scene_index]

    try:
        result = mutate_project(
            pid,
            _mutate_project,
            timeout=HTTP_PROJECT_TIMEOUT,
            snapshot=project,
        )
    except VideoTargetPolicyError as exc:
        return _shot_target_policy_response(exc)
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
    lines = generate_dialogue(
        scene.model_dump(),
        [c.model_dump() for c in chars],
        scene.mood or "neutral",
        language=lang,
        cost_tracker=_get_or_build_core(pid).cost_tracker,
    )
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
        cost_tracker=_get_or_build_core(pid).cost_tracker,
    )
    try:
        update_scene_shots(
            project,
            sid,
            shots,
            timeout=HTTP_PROJECT_TIMEOUT,
        )
    except VideoTargetPolicyError as exc:
        return _shot_target_policy_response(exc)

    return jsonify({"shots": shots})


# ---------------------------------------------------------------------------
# Style Rules
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/style-rules", methods=["POST"])
@_project_lock_guard
def api_generate_style_rules(pid):
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = _json_object_or_none()
    if data is None:
        return jsonify({"error": "JSON object required"}), 400
    if "expected_revision" not in data:
        return jsonify({
            "error": "expected_revision is required",
            "code": "revision_required",
            "retryable": False,
        }), 400
    expected_revision = data["expected_revision"]
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        return jsonify({
            "error": "expected_revision must be an integer",
            "code": "invalid_revision",
            "retryable": False,
        }), 400

    if not _reserve_project_admin(pid):
        return _project_busy_response(pid)
    try:
        project = load_project(pid)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        Project.model_validate(project)
        settings = project.get("global_settings", {})
        current_revision = _current_settings_revision(project)
        if expected_revision != current_revision:
            return jsonify(_settings_revision_conflict_payload(
                current_revision, settings
            )), 409

        # use_web_research defaults True: cinematography research is on by
        # default. Non-empty reference_films additionally triggers per-film
        # aesthetic research when enabled.
        rules = generate_style_rules(
            project_name=project["name"],
            mood=data.get("mood", settings.get("music_mood", "cinematic")),
            color_palette=data.get("color_palette", settings.get("color_palette", "")),
            music_mood=data.get("music_mood", settings.get("music_mood", "suspense")),
            aspect_ratio=settings.get("aspect_ratio", DEFAULT_ASPECT_RATIO),
            reference_films=data.get("reference_films", ""),
            use_web_research=data.get("use_web_research", True),
            cost_tracker=_get_or_build_core(pid).cost_tracker,
        )
        conflict = None

        def _mutate_project(latest_project: dict):
            nonlocal conflict
            Project.model_validate(latest_project)
            latest_revision = _current_settings_revision(latest_project)
            if expected_revision != latest_revision:
                conflict = _settings_revision_conflict_payload(
                    latest_revision, latest_project.get("global_settings", {})
                )
                return MutationResult(None, save=False)

            latest_settings = latest_project.setdefault("global_settings", {})
            latest_settings["style_rules"] = rules
            latest_settings[_SETTINGS_REVISION_KEY] = latest_revision + 1
            return True

        mutation_result = mutate_project(
            pid,
            _mutate_project,
            timeout=HTTP_PROJECT_TIMEOUT,
        )
        if conflict is not None:
            return jsonify(conflict), 409
        if mutation_result is None:
            return jsonify({"error": "Project not found"}), 404
        _evict_cached_project_core(pid)
        return jsonify(rules)
    finally:
        _release_project_admin(pid)


# ---------------------------------------------------------------------------
# Generation Pipeline with SSE Streaming
# ---------------------------------------------------------------------------


class _PipelineRunFailed(RuntimeError):
    """A pipeline returned without a deliverable and without cancellation."""


def _execute_pipeline_job(job: PipelineJob, execution: JobExecutionContext) -> None:
    """Bind one stable queue/job correlation id across the complete run."""

    with trace_context(trace_id=job.job_id, project_id=job.project_id):
        logger.info(
            "Durable pipeline job claimed",
            extra={
                "project_id": job.project_id,
                "state": job.state,
                "attempt_id": job.job_id,
            },
        )
        _execute_pipeline_job_traced(job, execution)


def _execute_pipeline_job_traced(job: PipelineJob, execution: JobExecutionContext) -> None:
    """Run one claimed durable job through the existing pipeline/checkpoint path."""

    pid = job.project_id
    if not load_existing_project_readonly(pid):
        raise _PipelineRunFailed("Project no longer exists")

    # The queue owns the cross-process claim.  This in-process sentinel keeps
    # all pre-existing direct-stage/admin fences and action endpoints aligned
    # while CinemaPipeline and its cached core are being constructed.
    with _pipelines_lock:
        if pid in _project_admin_in_flight or pid in _project_stage_in_flight:
            raise _PipelineRunFailed("Project became busy before its queued run started")
        if pid in _running_pipelines:
            raise _PipelineRunFailed("Project already has a local generation runner")
        _running_pipelines[pid] = _PIPELINE_PENDING

    bus = _ensure_progress_queue(pid)
    progress_cb = _make_progress_cb(pid, bus)
    pipeline: CinemaPipeline | None = None
    try:
        pipeline = CinemaPipeline(
            pid,
            core=_get_or_build_core(pid),
            progress_callback=progress_cb,
        )
        execution.set_cancel_callback(pipeline.cancel)
        with _pipelines_lock:
            if _running_pipelines.get(pid) is not _PIPELINE_PENDING:
                raise _PipelineRunFailed("Local generation reservation was lost")
            _running_pipelines[pid] = pipeline

        result = pipeline.generate(resume=job.effective_resume)
        latest_job = _pipeline_job_store.get(job.job_id)
        cancelled = execution.cancel_requested or bool(
            latest_job is not None and latest_job.cancel_requested
        )
        if cancelled:
            bus.publish({"stage": "CANCELLED", "detail": "Generation cancelled", "percent": 0})
            return
        if result is None:
            raise _PipelineRunFailed("Pipeline completed without a deliverable")
        bus.publish({"stage": "DONE", "detail": result, "percent": 100})
    except Exception as exc:
        summary = safe_error_summary(exc)
        bus.publish({"stage": "ERROR", "detail": summary, "percent": 0})
        raise
    finally:
        with _pipelines_lock:
            current = _running_pipelines.get(pid)
            if current is _PIPELINE_PENDING or current is pipeline:
                _running_pipelines.pop(pid, None)
            if _progress_queues.get(pid) is bus:
                _progress_queues.pop(pid, None)
        bus.close()


def _ensure_pipeline_dispatcher() -> PipelineJobDispatcher:
    global _pipeline_job_dispatcher
    with _pipeline_dispatcher_lock:
        dispatcher = _pipeline_job_dispatcher
        if dispatcher is None:
            dispatcher = PipelineJobDispatcher(
                _pipeline_job_store,
                _execute_pipeline_job,
            )
            _pipeline_job_dispatcher = dispatcher
        dispatcher.start()
    dispatcher.wake()
    return dispatcher


def _stop_pipeline_dispatcher() -> None:
    dispatcher = _pipeline_job_dispatcher
    if dispatcher is not None:
        # Do not wait indefinitely for a provider call or human review gate.
        # stop() cancels local lifecycle waiters but deliberately leaves the
        # durable row running; its lease makes it resumable after restart.
        dispatcher.stop(wait=True, timeout=5.0)


atexit.register(_stop_pipeline_dispatcher)


@app.before_request
def _resume_durable_pipeline_jobs_after_restart():
    """Start the fixed dispatcher on the first normal server request."""

    # Unit tests explicitly start an isolated dispatcher through /generate;
    # they must not accidentally consume a developer's default runtime DB on
    # unrelated GETs. Production receives its first health/UI request and then
    # resumes any expired/queued lease automatically.
    if not app.config.get("TESTING"):
        _ensure_pipeline_dispatcher()
    return None

@app.route("/api/projects/<pid>/generate", methods=["POST"])
@_project_lock_guard
def api_generate(pid):
    """Idempotently accept a fresh/checkpoint run into the durable queue.

    The response is 202 because provider work has not necessarily started.
    Repeated requests while this project is queued/running return the same
    stable job id; they never create a second paid run.
    """
    data = _json_object_or_none() if request.is_json else {}
    if data is None:
        return jsonify({"error": "JSON object required"}), 400
    resume = bool(data.get("resume", False))
    # Reserve the short existence-read -> durable-enqueue window. Destructive
    # and direct-stage operations inspect this set under the same lock, so a
    # delete cannot remove the project after our read but before the job row is
    # committed. Simultaneous duplicate requests wait only for this admission
    # window, then re-enter and receive the same stable SQLite job id.
    while True:
        with _pipelines_lock:
            if pid in _project_admin_in_flight:
                return _project_conflict_response(
                    "project_busy",
                    f"Project '{pid}' is being updated. Retry shortly.",
                )
            if pid in _project_stage_in_flight:
                return _project_conflict_response(
                    "project_busy",
                    f"Project '{pid}' is busy with another direct stage operation. "
                    "Retry shortly.",
                )
            pending_event = _project_queue_accept_events.get(pid)
            if pending_event is None:
                accept_event = threading.Event()
                _project_queue_accept_events[pid] = accept_event
                _project_queue_accept_in_flight.add(pid)
                break
        if not pending_event.wait(timeout=HTTP_PROJECT_TIMEOUT):
            return _project_conflict_response(
                "project_busy",
                f"Project '{pid}' queue admission is taking longer than expected. "
                "Retry shortly.",
            )

    try:
        if not is_safe_project_id(pid) or not load_existing_project_readonly(pid):
            return jsonify({"error": "Project not found"}), 404

        # The queue's BEGIN IMMEDIATE transaction supplies the cross-process
        # idempotency boundary for generation requests themselves.
        with _pipelines_lock:
            active_job = _pipeline_job_store.project_job(pid, active_only=True)
            if pid in _running_pipelines and active_job is None:
                return _project_conflict_response(
                    "generation_in_progress",
                    "Generation already in progress. Refresh to see the current state.",
                )
            job, created = _pipeline_job_store.enqueue(pid, resume=resume)
    finally:
        with _pipelines_lock:
            if _project_queue_accept_events.get(pid) is accept_event:
                _project_queue_accept_events.pop(pid, None)
                _project_queue_accept_in_flight.discard(pid)
                accept_event.set()

    # Make /stream reachable immediately while the job waits behind another
    # project. The claimed worker reuses this exact bus in this process.
    _ensure_progress_queue(pid)
    _ensure_pipeline_dispatcher()
    snapshot = _pipeline_job_store.public_snapshot(
        _pipeline_job_store.get(job.job_id) or job
    )
    return jsonify({
        "accepted": True,
        "started": False,
        "idempotent": not created,
        "job_id": job.job_id,
        "resume": job.requested_resume,
        "queue": snapshot,
        "message": "Generation queued. Connect to /api/projects/<pid>/stream for progress.",
    }), 202


@app.route("/api/projects/<pid>/checkpoint")
def api_checkpoint(pid):
    """Check if a resumable checkpoint exists for this project.

    Same helper (``cinema.services.checkpoint_info``) and response shape
    as the ``checkpoint`` object ``GET /pipeline-state`` now threads onto
    its idle branch (Slice 11c) — this route stays as the standalone,
    directly-pollable entry point; ``pipeline-state`` is the one the
    action-authority ("resume_checkpoint" in ``allowed_actions``) is
    actually derived from.
    """
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    # Lightweight path — reads the checkpoint JSON directly. No need to
    # construct CinemaPipeline (with its ContinuityEngine + ChiefDirector
    # + LLMEnsemble + tracker instantiation) just to read a JSON file.
    return jsonify(checkpoint_info(pid))


def _parse_last_event_id() -> int | None:
    """Resolve the client's replay position for GET /stream.

    Prefers the standard ``Last-Event-ID`` HTTP header — what a browser
    EventSource sends automatically on ITS OWN silent reconnect (read via
    Werkzeug's header mapping, so lookup is case-insensitive). Falls back
    to a ``?last_event_id=`` query parameter for a caller that manages its
    own reconnection and constructs a brand-new EventSource each time —
    today's web/src/hooks/useSSE.ts backoff-reconnect does exactly that,
    so the browser never gets a chance to attach the header itself; a
    future slice can thread the last-seen id through as a query param to
    resume across a manual reconnect. Missing/unparseable input is treated
    as "no known position" (the snapshot path) rather than a 400 — a
    client with a garbled id still deserves a stream, just without replay.
    """
    raw = request.headers.get("Last-Event-ID")
    if raw is None:
        raw = request.args.get("last_event_id")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _sse_format(event: dict, *, event_id: int | None, replayed: bool = False) -> str:
    """Render one SSE wire frame.

    When ``event_id`` is not None: emits the standard ``id:`` framing line
    (so ``EventSource.lastEventId`` / a browser's own automatic reconnect
    keeps working) AND inlines ``"id"`` into the JSON body for a client
    that only reads ``data:`` — today's web/src/hooks/useSSE.ts. Control
    frames (GAP/END/HEARTBEAT) pass ``event_id=None`` — they are wire-only
    notices, never stored/replayed, so they must never advance a client's
    replay position. ``replayed=True`` additionally inlines
    ``"replayed": true`` so a client can distinguish a resend (snapshot or
    reconnect backlog) from a fresh live occurrence; omitted when False to
    keep live events exactly as lean as before this slice.
    """
    body = dict(event)
    if event_id is not None:
        body["id"] = event_id
    if replayed:
        body["replayed"] = True
    frame = f"data: {json.dumps(body)}\n\n"
    if event_id is not None:
        frame = f"id: {event_id}\n{frame}"
    return frame


def _gap_event_dict(gap_from: int, gap_to: int, *, reason: str) -> dict:
    """Build the wire shape for a GAP control frame.

    Shared by the two places a subscriber can lose events without ever
    being silently kept in the dark: a reconnect whose Last-Event-ID
    aged out of the replay buffer, and FIX-SSE's live-delivery inbox
    overflow (a subscriber too slow to keep up had its oldest
    undelivered entry dropped -- see _ProjectEventBus._deliver). Same
    stage/percent/gap_from/gap_to shape either way, so a client need
    not special-case which path produced it; only ``reason`` (folded
    into ``detail``, informational only) differs.
    """
    return {
        "stage": "GAP",
        "detail": f"Missed events {gap_from}-{gap_to} ({reason})",
        "percent": -1,
        "gap_from": gap_from,
        "gap_to": gap_to,
    }


@app.route("/api/projects/<pid>/stream")
def api_stream(pid):
    """SSE endpoint for real-time generation progress.

    Broadcast-safe fan-out with replay (Slice 11a): every subscriber gets
    its own private inbox fed by the project's ``_ProjectEventBus``, so N
    concurrent listeners each see every event instead of competing for one
    shared queue. See the module comment above ``_ProjectEventBus`` (near
    ``_progress_queues``) for the full id/replay/gap/snapshot wire
    contract; ``_parse_last_event_id`` and ``_sse_format`` above implement
    the HTTP/SSE framing halves of that contract.
    """
    bus = _progress_queues.get(pid)
    if bus is None:
        queued_job = _pipeline_job_store.project_job(pid, active_only=True)
        if queued_job is not None and load_existing_project_readonly(pid):
            bus = _ensure_progress_queue(pid)
            _ensure_pipeline_dispatcher()
    if not bus:
        return jsonify({"error": "No generation in progress"}), 404

    last_event_id = _parse_last_event_id()
    sub = bus.subscribe(last_event_id)

    def event_stream():
        try:
            if sub.gap is not None:
                gap_from, gap_to = sub.gap
                yield _sse_format(
                    _gap_event_dict(gap_from, gap_to, reason="replay buffer cap exceeded"),
                    event_id=None,
                )
            for buffered_id, buffered_event in sub.backlog:
                yield _sse_format(buffered_event, event_id=buffered_id, replayed=True)
            if sub.closed:
                # The bus finished (and broadcast its own terminal sentinel
                # to whoever was attached at the time) before this
                # subscriber attached — nothing further will ever arrive
                # on `sub.inbox`. End the stream now instead of blocking.
                yield _sse_format({"stage": "END", "detail": "Stream closed", "percent": 100}, event_id=None)
                return
            while True:
                try:
                    kind, event_id, event = sub.inbox.get(timeout=30)
                    # FIX-SSE: this subscriber's inbox is bounded; an
                    # overflow (this subscriber too slow to keep up)
                    # records exactly which id range got dropped instead
                    # of silently discarding it (_ProjectEventBus._deliver
                    # / _record_gap). Surface it now, before whatever was
                    # just dequeued -- pop_gap only ever concerns ids
                    # strictly older than anything still queued, since
                    # eviction always removes the then-current-oldest
                    # entry, so this ordering is always correct.
                    gap = bus.pop_gap(sub.sub_id)
                    if gap is not None:
                        gap_from, gap_to = gap
                        yield _sse_format(
                            _gap_event_dict(gap_from, gap_to, reason="subscriber too slow to keep up, events dropped"),
                            event_id=None,
                        )
                    if kind == "end":
                        yield _sse_format({"stage": "END", "detail": "Stream closed", "percent": 100}, event_id=None)
                        break
                    yield _sse_format(event, event_id=event_id)
                except queue.Empty:
                    yield _sse_format({"stage": "HEARTBEAT", "detail": "waiting", "percent": -1}, event_id=None)
        finally:
            # Disconnect (client close, generator GC, or normal END/return
            # above) always removes this subscriber — mirrors the daemon's
            # own _progress_queues[pid] cleanup discipline, one level down.
            bus.unsubscribe(sub.sub_id)

    return Response(event_stream(), content_type="text/event-stream")


@app.route("/api/projects/<pid>/cancel", methods=["POST"])
@_project_lock_guard
def api_cancel(pid):
    if not is_safe_project_id(pid) or not load_existing_project_readonly(pid):
        return jsonify({"error": "Project not found"}), 404

    job = _pipeline_job_store.cancel_project(pid)
    pipeline = _get_running_pipeline(pid)
    if pipeline:
        pipeline.cancel()
    if job is not None:
        dispatcher = _pipeline_job_dispatcher
        if dispatcher is not None:
            dispatcher.wake()
        snapshot = _pipeline_job_store.public_snapshot(
            _pipeline_job_store.get(job.job_id) or job
        )
        if snapshot is not None and snapshot["state"] == "cancelled":
            with _pipelines_lock:
                bus = _progress_queues.pop(pid, None)
            if bus is not None:
                bus.publish({"stage": "CANCELLED", "detail": "Queued run cancelled", "percent": 0})
                bus.close()
        return jsonify({
            "cancelled": snapshot is not None and snapshot["state"] == "cancelled",
            "cancellation_requested": snapshot is not None and snapshot["cancel_requested"],
            "job_id": job.job_id,
            "queue": snapshot,
        })
    if pipeline:
        # Backward-compatible fallback for a process-local pipeline that
        # predates queue adoption (or a test fixture injected directly).
        return jsonify({"cancelled": True, "cancellation_requested": True})
    return jsonify({"error": "No generation in progress"}), 404


@app.route("/api/projects/<pid>/queue/abandon", methods=["POST"])
def api_abandon_unverifiable_queue_job(pid):
    """Close an expired, unverifiable lease after explicit risk acceptance."""

    if not is_safe_project_id(pid) or not load_existing_project_readonly(pid):
        return jsonify({"error": "Project not found"}), 404
    data = _json_object_or_none()
    if data is None:
        return jsonify({"error": "JSON object required"}), 400
    job_id = data.get("job_id")
    if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id):
        return jsonify({"error": "job_id must be a 32-character lowercase hexadecimal ID"}), 400
    if data.get("acknowledge_paid_work_risk") is not True:
        return jsonify({
            "error": "acknowledge_paid_work_risk must be true",
            "code": "operator_acknowledgement_required",
        }), 400
    if _get_running_pipeline(pid) is not None:
        return _project_conflict_response(
            "owner_still_local",
            "The project still has a local pipeline owner; stop it before abandonment.",
        )

    try:
        job, outcome = _pipeline_job_store.abandon_unverifiable(pid, job_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if outcome == "not_found":
        return jsonify({"error": "Queue job not found"}), 404
    if outcome != "abandoned":
        messages = {
            "not_running": "The queue job is no longer running.",
            "lease_active": "The worker lease has not expired.",
            "owner_live": "The worker owner fence is still active.",
            "owner_stopped": "The stopped worker was safely recovered; abandonment is not allowed.",
        }
        return jsonify({
            "error": messages.get(outcome, "Queue job cannot be abandoned."),
            "code": outcome,
            "queue": _pipeline_job_store.public_snapshot(job),
        }), 409

    dispatcher = _pipeline_job_dispatcher
    if dispatcher is not None:
        dispatcher.wake()
    with _pipelines_lock:
        bus = _progress_queues.pop(pid, None)
    if bus is not None:
        bus.publish({
            "stage": "CANCELLED",
            "detail": "Expired unverifiable queue job abandoned by operator",
            "percent": 0,
        })
        bus.close()
    return jsonify({
        "abandoned": True,
        "job_id": job_id,
        "queue": _pipeline_job_store.public_snapshot(job),
    })


# ---------------------------------------------------------------------------
# Export / Preview
# ---------------------------------------------------------------------------

def _send_project_media(real_path: str, *, migrated: bool):
    """Send a containment-checked, existing file for api_serve_file.

    Uses mimetypes.guess_type instead of the old 2-extension ternary (which
    silently mislabeled every non-.jpg/.mp4 file, including audio, as
    "audio/mpeg") so PNG/WAV/MOV/etc. get their real MIME type; a genuinely
    unrecognized extension falls back to the standard unknown-binary type
    rather than a wrong, specific label. When the file was found via the
    legacy-path suffix migration below, the response is tagged so the UI can
    render an explicit "migrated" state instead of treating it identically
    to a normal hit.
    """
    mimetype, _ = mimetypes.guess_type(real_path)
    response = send_file(real_path, mimetype=mimetype or "application/octet-stream")
    if migrated:
        response.headers["X-Media-Migrated"] = "1"
    return response


@app.route("/api/projects/<pid>/file")
def api_serve_file(pid):
    """Serve a generated file (image/video/audio) from the project directory.

    `path` accepts either persistence shape a take/shot record carries
    (Product invariant #6 -- portable persistence, slice 10):
      - a project-relative path (current form for newly-generated output),
        joined directly onto the project's CURRENT directory; or
      - a legacy absolute path baked in before this fix (or before a repo
        move) -- served as-is when it still resolves under the project
        directory, or via a SAFE suffix migration when it doesn't: the
        remainder from this project's own directory segment onward is
        derived and re-rooted under the CURRENT project directory, so a
        project relocated to a new repo root still serves its own media
        instead of going dark behind the (correctly firing) root guard.

    Every candidate -- relative-joined, as-given absolute, or migrated -- is
    realpath-resolved and RE-CHECKED for containment within the project
    directory before being served, so accepting the two extra shapes never
    weakens the existing traversal/root guard: a path that isn't genuinely
    this project's own (however it's spelled, including via a crafted
    "legacy-looking" prefix followed by `..` components) still 403s.
    """
    raw_path = request.args.get("path", "")
    if not raw_path:
        return jsonify({"error": "Invalid path"}), 400

    project_dir = os.path.realpath(get_project_dir(pid))

    def _contained(candidate_real_path: str) -> bool:
        return candidate_real_path == project_dir or candidate_real_path.startswith(project_dir + os.sep)

    primary_candidate = raw_path if os.path.isabs(raw_path) else os.path.join(project_dir, raw_path)
    primary_real = os.path.realpath(primary_candidate)

    if _contained(primary_real) and os.path.exists(primary_real):
        return _send_project_media(primary_real, migrated=False)

    # The direct candidate is missing (or, for a legacy absolute path, may no
    # longer even be contained here because the repo -- and so project_dir --
    # moved since it was persisted). Attempt the safe suffix migration, only
    # meaningful for an absolute input naming THIS project's own id segment;
    # a relative path is already unambiguous and has no legacy form.
    if os.path.isabs(raw_path):
        anchor = f"{os.sep}{pid}{os.sep}"
        idx = raw_path.rfind(anchor)
        if idx != -1:
            remainder = raw_path[idx + len(anchor):]
            if remainder:
                migrated_real = os.path.realpath(os.path.join(project_dir, remainder))
                # Re-check containment on the RECONSTRUCTED candidate too --
                # a crafted "/.../<pid>/../../../etc/passwd" must not use the
                # migration path to escape the root the primary check just
                # refused.
                if _contained(migrated_real):
                    if os.path.exists(migrated_real):
                        return _send_project_media(migrated_real, migrated=True)
                    # The pid anchor matched and the reconstruction is safely
                    # rooted under THIS project -- it's our own stale
                    # reference, just gone, not an escape attempt: "missing",
                    # not "denied".
                    return jsonify({"error": "File not found"}), 404

    if not _contained(primary_real):
        return jsonify({"error": "Access denied"}), 403
    return jsonify({"error": "File not found"}), 404


@app.route("/api/projects/<pid>/shots/<shot_id>/plan/approve", methods=["POST"])
@_project_lock_guard
@_project_stage_guard
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
@_project_stage_guard
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
@_project_stage_guard
def api_generate_keyframe(pid, shot_id):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    scene, _shot = _locate_shot(project, shot_id)
    if not scene:
        return jsonify({"error": "Shot not found"}), 404
    stage_error = _require_exact_pipeline_stage(pid, "KEYFRAME_REVIEW")
    if stage_error is not None:
        return stage_error

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


@app.route(
    "/api/projects/<pid>/shots/<shot_id>/keyframes/recovery/resolve",
    methods=["POST"],
)
@_project_lock_guard
@_project_stage_guard
def api_resolve_keyframe_recovery(pid, shot_id):
    data = request.get_json(silent=True)
    if (
        not isinstance(data, dict)
        or set(data) != {"confirmed"}
        or data.get("confirmed") is not True
    ):
        return jsonify({
            "error": (
                "Explicit confirmation is required after reconciling the "
                "provider queue and history"
            )
        }), 400

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    _scene, shot = _locate_shot(project, shot_id)
    if not shot:
        return jsonify({"error": "Shot not found"}), 404

    try:
        result = _get_stage_pipeline(pid).resolve_deferred_keyframe_job(shot_id)
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    status = 200 if result.get("success") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/keyframes/<take_id>/approve", methods=["POST"])
@_project_lock_guard
@_project_stage_guard
def api_approve_keyframe_take(pid, shot_id, take_id):
    try:
        result = _get_stage_pipeline(pid).approve_take(shot_id, take_id, "keyframe")
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    status = 200 if not result.get("error") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/performance/<take_id>/approve", methods=["POST"])
@_project_lock_guard
@_project_stage_guard
def api_approve_performance_take(pid, shot_id, take_id):
    """Approve a performance take so the PERFORMANCE_REVIEW gate predicate opens.

    Symmetric with the keyframe + final approve routes. The orchestrator's
    _wait_for_gate("PERFORMANCE_REVIEW", ...) polls cinema/review/controller.py's
    _gate_satisfied("PERFORMANCE_REVIEW", ...) every 500ms; this endpoint
    persists the approval onto project.json so the predicate flips to True.
    """
    stage_error = _require_exact_pipeline_stage(pid, "PERFORMANCE_REVIEW")
    if stage_error is not None:
        return stage_error
    try:
        result = _get_stage_pipeline(pid).approve_take(shot_id, take_id, "performance")
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    status = 200 if not result.get("error") else 409
    return jsonify(result), status


@app.route(
    "/api/projects/<pid>/shots/<shot_id>/performance/generate",
    methods=["POST"],
)
@_project_lock_guard
@_project_stage_guard
def api_generate_performance(pid, shot_id):
    """Generate or retry one review-stage performance candidate."""

    data = request.get_json(silent=True)
    if (
        not isinstance(data, dict)
        or set(data) != {"request_id"}
        or not isinstance(data.get("request_id"), str)
        or not re.fullmatch(r"[0-9a-f]{32}", data["request_id"])
    ):
        return jsonify({
            "code": "invalid_performance_request_id",
            "error": "request_id must be 32 lowercase hexadecimal characters",
        }), 400

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    scene, _shot = _locate_shot(project, shot_id)
    if not scene:
        return jsonify({"error": "Shot not found"}), 404
    stage_error = _require_exact_pipeline_stage(pid, "PERFORMANCE_REVIEW")
    if stage_error is not None:
        return stage_error
    try:
        result = _get_stage_pipeline(pid).generate_performance_take(
            scene["id"],
            shot_id,
            operator_requested=True,
            operator_request_id=data["request_id"],
        )
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    status = 200 if result.get("success") else 409
    return jsonify(result), status


@app.route(
    "/api/projects/<pid>/shots/<shot_id>/performance/skip",
    methods=["POST"],
)
@_project_lock_guard
@_project_stage_guard
def api_skip_performance(pid, shot_id):
    """Persist an explicit skip; never infer it from provider failure."""

    data = request.get_json(silent=True)
    if (
        not isinstance(data, dict)
        or set(data) != {"confirmed", "reason"}
        or data.get("confirmed") is not True
    ):
        return jsonify({
            "error": (
                "Explicit confirmation and a bounded operator reason are "
                "required to skip performance capture"
            )
        }), 400
    from domain.performance import normalize_performance_skip_reason

    try:
        operator_reason = normalize_performance_skip_reason(data.get("reason"))
    except ValueError as exc:
        return jsonify({
            "code": "invalid_performance_skip_reason",
            "error": str(exc),
        }), 400

    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    scene, _shot = _locate_shot(project, shot_id)
    if not scene:
        return jsonify({"error": "Shot not found"}), 404
    stage_error = _require_exact_pipeline_stage(pid, "PERFORMANCE_REVIEW")
    if stage_error is not None:
        return stage_error
    try:
        result = _get_stage_pipeline(pid).skip_performance_take(
            scene["id"], shot_id, reason=operator_reason
        )
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    status = 200 if result.get("success") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/motion/generate", methods=["POST"])
@_project_lock_guard
@_project_stage_guard
def api_generate_motion(pid, shot_id):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    scene, _shot = _locate_shot(project, shot_id)
    if not scene:
        return jsonify({"error": "Shot not found"}), 404
    stage_error = _require_exact_pipeline_stage(pid, "REVIEW")
    if stage_error is not None:
        return stage_error

    try:
        result = _get_stage_pipeline(pid).generate_motion_take(scene["id"], shot_id)
    except ValueError:
        return jsonify({"error": "Project not found"}), 404

    status = 200 if result.get("success") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/final/<take_id>/approve", methods=["POST"])
@_project_lock_guard
@_project_stage_guard
def api_approve_final_take(pid, shot_id, take_id):
    try:
        result = _get_stage_pipeline(pid).approve_take(shot_id, take_id, "final")
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    status = 200 if not result.get("error") else 409
    return jsonify(result), status


@app.route("/api/projects/<pid>/shots/<shot_id>/takes/<take_id>/iterate", methods=["POST"])
@_project_lock_guard
@_project_stage_guard
def api_iterate_take(pid, shot_id, take_id):
    """S16: directorial iteration endpoint.

    Accepts an operator's directorial intent (DirectorialIntent JSON body),
    calls ``ShotController.regenerate_with_intent``, and returns the new take.

    Feature-flagged behind CINEMA_DIRECTORIAL_ITERATION (§7.7.3 Class B
    opt-out UX flag). Default ON as of v5.1+ flag-flip (2026-05-26); set
    ``CINEMA_DIRECTORIAL_ITERATION=0`` to opt out. Returns 404 when
    explicitly disabled.

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

    stage_error = _require_iteration_pipeline_stage(pid, intent.target_stage)
    if stage_error is not None:
        return stage_error

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
        # P1-3 part 12 (Variant 1 full): inner validate + typed-iterate-
        # for-find.  Project.model_validate(project) validates the latest
        # snapshot the mutator sees; race protection requires this
        # deterministic raise on shape mismatch (NOT gated by
        # CINEMA_STRICT_SCHEMA).  Typed-iterate for FIND (using scene.shots
        # typed attribute); dict-write to MUTATE under the lock.  Dynamic key
        # flag_key = f"{gate}_auto_approved" is computed in the outer scope;
        # dict-write via shot_dict[flag_key] preserves the string-key dynamic
        # dispatch.  Index parity between latest_typed.scenes[i].shots[j] and
        # project["scenes"][i]["shots"][j] is preserved by pydantic list-order
        # invariant.
        latest_typed = Project.model_validate(project)
        for i, scene in enumerate(latest_typed.scenes):
            for j, shot in enumerate(scene.shots):
                if shot.id == shot_id:
                    shot_dict = project["scenes"][i]["shots"][j]
                    shot_dict.setdefault("auto_approve_audit", []).append(audit_entry)
                    shot_dict[flag_key] = False
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

    data = _json_object_or_none()
    if data is None:
        return jsonify({"error": "JSON object required"}), 400
    new_prompt = data.get("prompt", "")

    def _mutate_project(project: dict):
        # P1-3 part 12 (Variant 1 full): inner validate + typed-iterate-
        # for-find.  Project.model_validate(project) validates the latest
        # snapshot the mutator sees; race protection requires this
        # deterministic raise on shape mismatch (NOT gated by
        # CINEMA_STRICT_SCHEMA).  Typed-iterate for FIND; dict-write to
        # MUTATE under the lock.  Index parity between
        # latest_typed.scenes[i].shots[j] and project["scenes"][i]["shots"][j]
        # is preserved by pydantic list-order invariant.
        latest_typed = Project.model_validate(project)
        for i, scene in enumerate(latest_typed.scenes):
            for j, shot in enumerate(scene.shots):
                if shot.id == shot_id:
                    project["scenes"][i]["shots"][j]["prompt"] = new_prompt
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

    data = _json_object_or_none()
    if data is None:
        return jsonify({"error": "JSON object required"}), 400
    allowed_fields = {
        "target_api",
        "camera",
        "visual_effect",
        "prompt",
        "scene_foley",
        "negative_constraints",
        "continuity_constraints",
        "intent_notes",
        "performance_budget_mode",
    }
    updates = {k: v for k, v in data.items() if k in allowed_fields}

    if (
        "target_api" in updates
        and not isinstance(updates["target_api"], str)
    ):
        return jsonify({"error": "target_api must be a string"}), 400

    if "performance_budget_mode" in updates:
        performance_mode = updates["performance_budget_mode"]
        if not isinstance(performance_mode, str) or performance_mode not in {"", "budget"}:
            return jsonify({
                "error": "performance_budget_mode must be '' or 'budget'"
            }), 400

    target_is_updated = "target_api" in updates
    def _mutate_project(project: dict):
        # P1-3 part 12 (Variant 1 full): inner validate + typed-iterate-
        # for-find.  Project.model_validate(project) validates the latest
        # snapshot the mutator sees; race protection requires this
        # deterministic raise on shape mismatch (NOT gated by
        # CINEMA_STRICT_SCHEMA).  Typed-iterate for FIND; dict-write to
        # MUTATE under the lock.  updates are pre-filtered against
        # allowed_fields in outer scope.  Index parity between
        # latest_typed.scenes[i].shots[j] and project["scenes"][i]["shots"][j]
        # is preserved by pydantic list-order invariant.
        latest_typed = Project.model_validate(project)
        matches = [
            (scene_index, shot_index, shot)
            for scene_index, scene in enumerate(latest_typed.scenes)
            for shot_index, shot in enumerate(scene.shots)
            if shot.id == shot_id
        ]
        if matches:
            scene_index, shot_index, shot = matches[0]
            if "performance_budget_mode" in updates:
                current_mode = (
                    "budget"
                    if shot.performance_budget_mode.lower() in {"budget", "cheap"}
                    else ""
                )
                requested_mode = updates["performance_budget_mode"]
                if shot.approved_performance_take_id and requested_mode != current_mode:
                    return MutationResult({
                        "error": (
                            "Cannot change dialogue performance routing while an "
                            "approved performance take exists"
                        ),
                        "error_kind": "approved_performance_route_conflict",
                        "code": "approved_performance_route_conflict",
                        "shot_id": shot_id,
                    }, save=False)
            if target_is_updated:
                policy_snapshot = _video_policy_runtime_snapshot()
                policy_date = _video_policy_current_date()
                settings = project.get("global_settings", {})
                api_engines = (
                    settings.get("api_engines", {})
                    if isinstance(settings, Mapping)
                    else {}
                )
                aspect_ratio = (
                    settings.get("aspect_ratio", DEFAULT_ASPECT_RATIO)
                    if isinstance(settings, Mapping)
                    else DEFAULT_ASPECT_RATIO
                )
                _raise_if_target_rejected(
                    updates["target_api"],
                    shot_id=shot_id,
                    current_target=shot.target_api,
                    may_grandfather=len(matches) == 1,
                    snapshot=policy_snapshot,
                    on_date=policy_date,
                    api_engines=api_engines,
                    aspect_ratio=aspect_ratio,
                )
            project["scenes"][scene_index]["shots"][shot_index].update(
                updates
            )
            return True
        return MutationResult(False, save=False)

    try:
        result = mutate_project(
            pid,
            _mutate_project,
            timeout=HTTP_PROJECT_TIMEOUT,
        )
    except VideoTargetPolicyError as exc:
        return _shot_target_policy_response(exc)
    if result is None:
        return jsonify({"error": "Project not found"}), 404
    if isinstance(result, Mapping) and result.get("code") == "approved_performance_route_conflict":
        return jsonify(dict(result)), 409
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
    """Get current pipeline execution state.

    Additive to the legacy shape (Slice 8a): every response that reflects
    a real project also carries server-derived action authority so the
    UI never has to guess —

      running: bool             -- see _pipeline_action_authority.
      allowed_actions: list[str] -- subset of {"start", "resume_checkpoint",
                                     "cancel", "pause", "resume"} currently
                                     legal for pid.

    Slice 11c additionally threads a ``checkpoint`` object (the exact
    shape ``GET /checkpoint`` returns — see
    ``cinema.services.checkpoint_info``) onto the disk-snapshot
    (no-live-pipeline) branch ONLY. A checkpoint is only actionable while
    idle — "resume_checkpoint" only ever appears in ``allowed_actions``
    there too (see ``_pipeline_action_authority``) — so a live pipeline's
    response is left exactly as Slice 8a shipped it rather than layering a
    second, potentially-stale on-disk read on top of its own real
    ``current_stage``/progress.

    The 404 "Project not found" shape is intentionally left unchanged —
    there is no pid-scoped authority to report for a project that does
    not exist.
    """
    running, allowed_actions = _pipeline_action_authority(pid)
    queue_snapshot = _pipeline_job_store.project_snapshot(pid)
    pipeline = _get_running_pipeline(pid)
    if pipeline:
        state = pipeline.get_state()
        state["running"] = running
        state["allowed_actions"] = allowed_actions
        state["queue"] = queue_snapshot
        return jsonify(state)
    project = load_existing_project_readonly(pid)
    if not project:
        return jsonify({"error": "Project not found", "paused": False, "cancelled": False}), 404
    # Lightweight path — replicates get_state() shape without spinning
    # up CinemaPipeline's heavy ctor.
    state = state_snapshot(pid)
    state["running"] = running
    state["allowed_actions"] = allowed_actions
    state["queue"] = queue_snapshot
    state["checkpoint"] = checkpoint_info(pid)
    return jsonify(state)


@app.route("/api/projects/<pid>/shots/<shot_id>/restart", methods=["POST"])
@_project_lock_guard
@_project_stage_guard
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
        # P1-3 part 12 (Base read-only): boundary validate on the locked
        # snapshot — Project.model_validate(...) raises ValidationError
        # UNCONDITIONALLY on shape mismatch (race protection requires
        # deterministic raise; NOT gated by CINEMA_STRICT_SCHEMA).  No inner
        # validate required (save=False; no dict-write under lock).  Raw-dict
        # double-loop preserved (read-only; typed-iterate not required per
        # pattern doc §"Base read-only").  See docs/MIGRATION-PATTERN-
        # pydantic-caller.md §"Pattern variants" / Base entry.
        Project.model_validate(project)
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

    stage_error = _require_exact_pipeline_stage(pid, "KEYFRAME_REVIEW")
    if stage_error is not None:
        return stage_error

    # The exact-stage guard above proves a live pipeline exists.  Idle restart
    # is deliberately unavailable, so the former temporary-pipeline branch is
    # dead and would be unsafe if a lifecycle race ever made it reachable.
    if pipeline is None:
        return _require_exact_pipeline_stage(pid, "KEYFRAME_REVIEW")
    result = pipeline.restart_shot(
        scene_id, shot_id, positive_prompt, negative_prompt,
    )
    return jsonify(result)


@app.route("/api/projects/<pid>/shots/<shot_id>/regenerate", methods=["POST"])
@_project_lock_guard
@_project_stage_guard
def api_regenerate_shot(pid, shot_id):
    """Regenerate a single shot (legacy/compat path).

    Optional body: {positive_prompt, negative_prompt}.
    - positive_prompt, when set, replaces the shot's stored prompt before
      regeneration.
    - negative_prompt, when set, is threaded into the keyframe regeneration
      (ShotController.regenerate_shot -> generate_keyframe_take). It is NOT
      persisted on the shot, and does NOT apply when the shot already has an
      approved keyframe (regenerate_shot then regenerates the motion take, which
      has no negative_prompt input). For a clean full restart that always
      regenerates the keyframe, use POST .../restart (api_restart_shot).
    """
    pipeline = _get_running_pipeline(pid)
    new_prompt = request.json.get("positive_prompt") if request.is_json else None
    negative_prompt = request.json.get("negative_prompt") if request.is_json else None

    def _mutate_project(project: dict):
        # P1-3 part 12 (Mixed-shape conditional): inner validate is required
        # UNCONDITIONALLY because the write path (new_prompt set) does
        # dict-write under lock and needs race protection on the latest
        # snapshot shape.  The no-write path benefits from the same validate
        # for consistency (cheap; ~1-2ms per call).
        # Project.model_validate(...) raises ValidationError UNCONDITIONALLY
        # on shape mismatch (NOT gated by CINEMA_STRICT_SCHEMA).
        # Write path: returns scene["id"] as a raw str (mutate_project
        # treats non-MutationResult truthy returns as save=True).
        # No-write path: returns MutationResult(scene["id"], save=False).
        # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1".
        Project.model_validate(project)
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
        result = pipeline.regenerate_shot(scene_id, shot_id, negative_prompt=negative_prompt)
        return jsonify(result)

    try:
        temp_pipeline = CinemaPipeline(pid, core=_get_or_build_core(pid), progress_callback=_make_progress_cb(pid))
        result = temp_pipeline.regenerate_shot(scene_id, shot_id, negative_prompt=negative_prompt)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/projects/<pid>/shots/<shot_id>/correct", methods=["POST"])
@_project_lock_guard
@_project_stage_guard
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
@_project_lock_guard
@_project_stage_guard
def api_diagnose_shot(pid, shot_id):
    """Run quality diagnostics on a clip. `deep=true` adds an LLM deep diagnosis."""
    body = request.json if request.is_json else {}
    take_id = body.get("take_id", "")
    deep = bool(body.get("deep", False))
    try:
        result = _get_stage_pipeline(pid).diagnose_clip(shot_id, take_id=take_id, deep=deep)
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(result)


@app.route("/api/projects/<pid>/assemble", methods=["POST"])
@app.route("/api/projects/<pid>/proceed-assembly", methods=["POST"])
@_project_lock_guard
@_project_stage_guard
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

    Feature-flagged behind CINEMA_SCREENING_STAGE (§7.7.3 Class B opt-out
    UX flag; shared convention with the directorial-iteration endpoint).
    Default ON as of v5.1+ flag-flip (2026-05-26); set
    ``CINEMA_SCREENING_STAGE=0`` to opt out. Returns 404 when explicitly
    disabled.

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
    _cost_est = estimate_reassembly_cost(project)
    return jsonify({
        "success": True,
        "assembled_mp4_path": assembled_path,
        "timeline_manifest": manifest,
        "needs_reassembly": get_needs_reassembly(project),
        "cost_estimate_seconds": _cost_est["seconds"],
        "tts_lines_to_generate": _cost_est["tts_lines_to_generate"],
        "estimated_tts_usd": _cost_est["estimated_tts_usd"],
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
    except ValueError as e:
        # Lane V #12 I1 (advisory): discriminate ValidationError from
        # plain ValueError.  pydantic.ValidationError is a subclass of
        # ValueError, so a bare `except ValueError:` here would silently
        # swallow corrupt-snapshot shape errors raised by broad-A's
        # Variant 1 inner validate inside `mark_screening_approved`.
        # ONLY plain ValueError ("project not found") should 404; a
        # ValidationError (malformed on-disk project) must propagate so
        # the operator sees a 500 and can investigate the corruption.
        from pydantic import ValidationError as _ValidationError
        if isinstance(e, _ValidationError):
            raise
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

    if not _reserve_project_stage(pid):
        with _reassembly_lock:
            _reassembly_in_flight.discard(pid)
        return _project_busy_response(pid)

    try:
        data = request.get_json(silent=True) or {}
        only_if_changed = bool(data.get("only_if_changed", True))

        project = load_project(pid)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        dirty_shots = get_needs_reassembly(project)
        _cost_est = estimate_reassembly_cost(project)
        cost_estimate = _cost_est["seconds"]

        # Short-circuit: only_if_changed=true AND no dirty shots -> nothing to do.
        # The operator's UI suppresses the button in this state; the endpoint
        # double-checks so a stale-cached UI doesn't trigger a spurious rerun.
        if only_if_changed and not dirty_shots:
            return jsonify({
                "success": True,
                "new_assembled_path": "",
                "regenerated_shots": [],
                "cost_estimate_seconds": cost_estimate,
                "tts_lines_to_generate": _cost_est["tts_lines_to_generate"],
                "estimated_tts_usd": _cost_est["estimated_tts_usd"],
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
                "tts_lines_to_generate": _cost_est["tts_lines_to_generate"],
                "estimated_tts_usd": _cost_est["estimated_tts_usd"],
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
        except ValueError as e:
            # Lane V #12 I1 (advisory): discriminate ValidationError from
            # plain ValueError.  pydantic.ValidationError is a subclass of
            # ValueError, so a bare `except ValueError:` would silently
            # swallow corrupt-snapshot shape errors raised by broad-A's
            # Variant 1 inner validate inside `clear_needs_reassembly`.
            # Plain ValueError (race: project deleted) is best-effort
            # logged below; ValidationError must propagate as 500.
            from pydantic import ValidationError as _ValidationError
            if isinstance(e, _ValidationError):
                raise
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
            "tts_lines_to_generate": _cost_est["tts_lines_to_generate"],
            "estimated_tts_usd": _cost_est["estimated_tts_usd"],
            "skipped": False,
        }), 200
    finally:
        _release_project_stage(pid)
        with _reassembly_lock:
            _reassembly_in_flight.discard(pid)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

@app.route("/api/projects/<pid>/cleanup", methods=["POST"])
@_project_lock_guard
def api_cleanup(pid):
    """Clean up temporary files from a project."""
    from cleanup import cleanup_project, get_project_disk_usage

    busy_response = _reject_if_project_busy(pid)
    if busy_response:
        return busy_response

    data = _json_object_or_none() if request.is_json else {}
    data = data or {}
    aggressive = data.get("aggressive", False)
    dry_run = data.get("dry_run", False)

    result = cleanup_project(pid, aggressive=aggressive, dry_run=dry_run)
    result["disk_usage"] = get_project_disk_usage(pid)
    return jsonify(result)


@app.route("/api/projects/<pid>/disk-usage")
def api_disk_usage(pid):
    """Get disk usage breakdown for a project."""
    from cleanup import get_project_disk_usage
    return jsonify(get_project_disk_usage(pid))


def _project_budget_authority(project: Mapping[str, object]) -> tuple[str, float | None]:
    """Normalize the persisted project cap without turning corruption into unlimited."""
    settings = project.get("global_settings")
    raw = settings.get("budget_limit_usd") if isinstance(settings, Mapping) else None
    if raw is None or (not isinstance(raw, bool) and raw == 0):
        return "unlimited", None
    if isinstance(raw, bool):
        return "invalid", None
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return "invalid", None
    if not math.isfinite(value) or value < 0:
        return "invalid", None
    if value == 0:
        return "unlimited", None
    return "active", value


@contextmanager
def _project_cost_tracker(pid: str, project: Mapping[str, object]):
    """Yield the cached tracker or an owned, deterministically-closed reader."""
    with _cores_lock:
        cached_core = _running_cores.get(pid)
    if cached_core is not None:
        yield cached_core.cost_tracker
        return

    from cost_tracker import CostTracker

    settings = project.get("global_settings")
    budget = settings.get("budget_limit_usd") if isinstance(settings, Mapping) else None
    with CostTracker(budget_usd=budget) as tracker:
        yield tracker


_PUBLIC_PAID_ATTEMPT_FIELDS = (
    "attempt_id", "provider", "engine", "operation", "shot_id", "video_id",
    "state", "reserved_cost_usd", "reconciled_cost_usd", "billed",
    "provider_job_id", "provider_status", "failure_code", "detail",
    "created_at", "updated_at", "active",
)


def _public_paid_attempt(attempt: Mapping[str, object]) -> dict[str, object]:
    """Project only the stable operator contract; omit request internals."""
    return {field: attempt.get(field) for field in _PUBLIC_PAID_ATTEMPT_FIELDS}


def _cost_live_snapshot(pid: str, project: Mapping[str, object], tracker) -> dict:
    cost = tracker.get_video_cost(pid)
    paid = tracker.get_paid_attempts_snapshot(pid)
    charged = round(float(cost.get("total_usd") or 0.0), 6)
    reserved = round(float(paid.get("active_reservation_usd") or 0.0), 6)
    committed = round(charged + reserved, 6)
    budget_status, budget_limit = _project_budget_authority(project)
    remaining = (
        round(max(0.0, budget_limit - committed), 6)
        if budget_status == "active" and budget_limit is not None
        else 0.0 if budget_status == "invalid"
        else None
    )

    all_attempts = [
        row for row in paid.get("attempts", []) if isinstance(row, Mapping)
    ]
    active_attempts = [row for row in all_attempts if row.get("active") is True]
    recent_terminal = [row for row in all_attempts if row.get("active") is not True][-25:]
    visible_ids: set[object] = set()
    visible_attempts: list[dict[str, object]] = []
    for row in active_attempts + recent_terminal:
        attempt_id = row.get("attempt_id")
        if attempt_id in visible_ids:
            continue
        visible_ids.add(attempt_id)
        visible_attempts.append(_public_paid_attempt(row))

    return {
        # total_usd remains for compatibility with older polling clients.
        "total_usd": charged,
        "charged_usd": charged,
        "active_reservation_usd": reserved,
        "committed_usd": committed,
        "budget_status": budget_status,
        "budget_limit_usd": budget_limit,
        "remaining_usd": remaining,
        "accepted_unknown_count": int(paid.get("accepted_unknown_count") or 0),
        "billed_failure_count": int(paid.get("billed_failure_count") or 0),
        "blocked_attempt_count": int(paid.get("blocked_attempt_count") or 0),
        "attempts": visible_attempts,
    }


@app.route("/api/projects/<pid>/cost-live", methods=["GET"])
def api_cost_live(pid):
    """Return durable charged spend, reservations, exposure, and paid jobs."""
    project = load_existing_project_readonly(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    try:
        with _project_cost_tracker(pid, project) as tracker:
            return jsonify(_cost_live_snapshot(pid, project, tracker))
    except Exception as exc:
        logger.exception("cost-live query failed for pid=%s", pid)
        return jsonify({"error": "Cost query failed"}), 500


@app.route(
    "/api/projects/<pid>/paid-attempts/<attempt_id>/cancel",
    methods=["POST"],
)
@_project_lock_guard
def api_cancel_paid_attempt(pid, attempt_id):
    """Request cancellation for one project-owned active Runway task."""
    project = load_existing_project_readonly(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    try:
        with _project_cost_tracker(pid, project) as tracker:
            attempt = tracker.get_paid_attempt(attempt_id)
            # Return one indistinguishable 404 for unknown and cross-project IDs.
            if not attempt or attempt.get("video_id") != pid:
                return jsonify({"error": "Paid attempt not found"}), 404
            if attempt.get("provider") != "runway":
                return jsonify({"error": "Only Runway attempts support cancellation"}), 409
            if attempt.get("active") is not True:
                return jsonify({"error": "Paid attempt is already terminal"}), 409

            from performance.runway_tasks import cancel_runway_attempt

            cancellation = cancel_runway_attempt(tracker, attempt_id)
            payload = _cost_live_snapshot(pid, project, tracker)
            payload["cancellation"] = _public_paid_attempt(cancellation)
            return jsonify(payload), 202
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        logger.exception("paid-attempt cancellation failed for pid=%s", pid)
        return jsonify({"error": "Cancellation request failed"}), 500


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

    # Standalone startup must reclaim expired leases even before the first UI
    # or health request arrives. Imported WSGI deployments retain the
    # before_request fallback above because their lifecycle is server-owned.
    _ensure_pipeline_dispatcher()

    print("\n" + "=" * 60)
    print("🎬 CINEMA PRODUCTION TOOL — Web Server")
    print("=" * 60)
    print(f"Open http://localhost:8080 in your browser")
    print(f"  bind:  {bind_host}:8080")
    print(f"  CORS:  {', '.join(cors_origins)}")
    print("=" * 60 + "\n")
    app.run(host=bind_host, port=8080, debug=False, use_reloader=False)
