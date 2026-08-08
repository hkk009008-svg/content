from __future__ import annotations

import logging
import math
import os
import stat
import sys
import time
import json
import subprocess
from datetime import date, datetime, timezone
from importlib.util import find_spec
from typing import TYPE_CHECKING, Optional
from config.settings import settings
from cinema.fal_limits import FAL_TIMEOUT_VIDEO_S
from domain.provider_catalog import RuntimeSnapshot
from domain.video_engine_policy import (
    PORTRAIT_CAPABLE_VIDEO_ENGINES,
    VideoCandidateResult,
    build_runtime_snapshot,
    filter_automatic_dispatch_candidates,
    filter_dispatch_candidates,
)
from performance._net import safe_download, validate_video_artifact

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cinema.context import PipelineContext

# VEO is still in the default cascade (see line ~99 below). Quota exhaustion
# carries a TTL-based cooldown rather than a permanent flag: any VEO 429 sets
# _VEO_QUOTA_EXHAUSTED_UNTIL to (now + _VEO_QUOTA_TTL_S), and subsequent calls
# short-circuit to try_next_api() until that timestamp passes. Set to 0 means
# no active cooldown. Process restart also clears state (module-level reset).
_VEO_QUOTA_EXHAUSTED_UNTIL: float = 0.0
_VEO_QUOTA_TTL_S: int = 1800  # 30 minutes — Google Veo quotas typically reset hourly

# GEMINI_OMNI gets its OWN cooldown pair — do NOT reuse Veo's. Gemini Developer
# API Tier-1 bills a rolling $10/10min spend window (not Veo's hourly-reset
# assumption); at ~$0.90/8s-clip, ~11 calls exhaust the window. Reusing Veo's
# 1800s TTL would over-block 3x once the window actually clears.
_GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL: float = 0.0
_GEMINI_OMNI_QUOTA_TTL_S: int = 600  # 10 min — Gemini Developer API Tier-1 rolling spend window

# Providers that can produce 9:16 portrait video (aspect-aware via Phase-3 T3-T6, or
# keyframe-driven). Portrait projects filter the cascade to this set. EXCLUDED:
# LTX and FAL_SVD are not wired for portrait aspect output.
# SEEDANCE joined 2026-07-11: the fal-based dispatch passes fal_aspect_ratio()
# and Seedance 2.0's aspect_ratio enum includes 9:16 (fal /api schema).
# Note: the Kling dispatch keys are KLING_NATIVE + KLING_3_0
# (there is no bare "KLING"); there is no Hedra branch in this module.
PORTRAIT_CAPABLE = PORTRAIT_CAPABLE_VIDEO_ENGINES

# Seconds requested per shot type from the fal Seedance endpoints (duration
# enum: 4-15s ints; mirrors _sora_durations). Module-level because the cost
# record in cinema/shots/controller.py recomputes the per-clip cost from it —
# API_COST_USD["SEEDANCE"] is a per-~5s figure, so an 8s action clip would
# otherwise under-record by 38% (money-gate review 2026-07-11).
SEEDANCE_DURATIONS = {"action": 8, "wide": 8, "landscape": 8, "portrait": 4, "medium": 4}

# ltx-2-3-pro duration enum (seconds) — MUST stay == ltx_native.LTXVideoAPI.
# DURATION_SECONDS (https://docs.ltx.io/models; both endpoints share this
# enum, confirmed 2026-07-30). Module-level (like SEEDANCE_DURATIONS above)
# rather than a per-call local so it is a proper, importable, testable
# symbol a sync-pin test can check against the real ltx_native constant
# (see the test reference below). Kept as a LITERAL rather than an
# attribute lookup on the imported LTXVideoAPI class: sibling dispatch tests
# replace the whole `ltx_native` module with a bare MagicMock class
# (`ltx_module.LTXVideoAPI = MagicMock(...)`), under which
# `LTXVideoAPI.DURATION_SECONDS` silently returns a MagicMock — iterating it
# yields ZERO items (no TypeError) and indexing it returns another MagicMock,
# not an int, so the snap-up logic below would silently pass a MagicMock as
# `duration` to generate_video() instead of raising or using a real value
# (verified empirically 2026-07-30). A sync-pin test guards against drift
# instead (tests/unit/test_ltx_native.py::
# test_phase_c_ffmpeg_duration_enum_matches_ltx_native).
_LTX_DURATION_ENUM_S = (6, 8, 10)

# Once-per-run structural flag: multiple admitted fallbacks use FAL, so a
# missing client degrades the whole run, not one clip.
_FAL_MISSING_WARNED = False

# Default engine cascade for generate_ai_video when the caller passes no
# video_fallbacks — quality order. Module-level so tests pin the REAL list
# (the old test kept a local copy that silently drifted for two migrations).
# Retired SORA_2 and explicit-only SORA_NATIVE/legacy RUNWAY are absent.
# RUNWAY_GEN4 stays automatic. GEMINI_OMNI was repaired and re-admitted in
# the catalog (Slice 3, 2026-07-30) but is deliberately left out of this
# DEFAULT blind order: duration/resolution/audio are prompt-inferred with no
# structured kwargs, a worse blind-default — opt in via an explicit
# target_api or fallbacks list. This remains an order seed: the typed entry
# guard below is the executable authority for lifecycle, runtime, project,
# and aspect eligibility.
DEFAULT_VIDEO_CASCADE = [
    "VEO_NATIVE", "SEEDANCE", "KLING_3_0", "RUNWAY_GEN4",
    "LTX", "VEO",
]


def _veo_quota_blocked() -> bool:
    """True if a recent VEO 429 means we should still cascade past VEO.

    Auto-expires after _VEO_QUOTA_TTL_S seconds so the operator doesn't need
    to restart the server to retry once Google's quota window rolls over.
    """
    return _VEO_QUOTA_EXHAUSTED_UNTIL > time.time()


def _gemini_omni_quota_blocked() -> bool:
    """True if a recent GEMINI_OMNI budget_exceeded/429 means we should still
    cascade past it. Auto-expires after _GEMINI_OMNI_QUOTA_TTL_S seconds (see
    the module-level comment on that constant for why it's separate from Veo's)."""
    return _GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL > time.time()

FAL_AVAILABLE: bool | None = None


def _load_fal_client() -> bool:
    """Import the FAL provider only after the dispatch policy admits a chain.

    A plain ``import fal_client`` under a ``global`` declaration binds the
    module-level name directly, keeping the subscribe-timeout guard's grammar
    (the bare ``fal_client`` name appears only as an import target and an
    attribute base — never aliased, assigned, passed, or returned). Until the
    first successful load the module attribute is intentionally unbound;
    every FAL call site is gated on ``FAL_AVAILABLE`` truthiness first.
    """

    global fal_client, FAL_AVAILABLE
    if FAL_AVAILABLE is None:
        try:
            import fal_client
        except ImportError:
            FAL_AVAILABLE = False
        else:
            FAL_AVAILABLE = True
    return bool(FAL_AVAILABLE)


def _runtime_module_probe(name: str) -> bool:
    """Treat an injected/loaded module as available without importing it."""

    if name in sys.modules:
        return True
    try:
        return find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _video_policy_runtime_snapshot() -> RuntimeSnapshot:
    """Observe runtime eligibility for the mandatory public entry fence."""

    return build_runtime_snapshot(
        settings_obj=settings,
        module_probe=_runtime_module_probe,
    )


def _video_policy_current_date() -> date:
    """Return the UTC lifecycle-policy date through a patchable test seam."""

    return datetime.now(timezone.utc).date()


def _serialized_policy_rejections(
    result: VideoCandidateResult,
) -> list[dict[str, str]]:
    return [
        {"key": rejection.key, "reason": rejection.reason.value}
        for rejection in result.rejections
    ]


def _dispatch_policy_error(
    requested: object,
    result: VideoCandidateResult,
) -> dict:
    target = requested if isinstance(requested, str) else ""
    reason = next(
        (
            rejection.reason.value
            for rejection in result.rejections
            if target != "AUTO" and rejection.key == target
        ),
        None,
    )
    if reason is None:
        reason = next(
            (
                rejection.reason.value
                for rejection in result.rejections
                if rejection.key != "AUTO"
            ),
            "no_eligible_candidates",
        )
    return {
        "error": "Target video engine is unavailable",
        "error_kind": "target_api_policy",
        "code": "target_api_unavailable",
        "target_api": target,
        "reason": reason,
        "retryable": False,
    }


def generate_ai_video(
    image_path: str,
    camera_motion: str,
    target_api: str,
    output_mp4: str,
    pacing: str = "moderate",
    character_id: str = None,
    attempted_apis: list = None,
    multi_angle_refs: list = None,
    negative_prompt: str = None,
    shot_type: str = None,
    video_fallbacks: list = None,
    driving_video_path: str = "",
    has_dialogue: bool = False,
    dialogue_native_audio: bool = False,
    duration: str = "8s",
    ctx: Optional["PipelineContext"] = None,
    _cascade_out: Optional[dict] = None,
    cost_tracker=None,
    shot_id: str = "",
    video_id: str = "",
) -> str:
    """Filter a complete dispatch seed before entering provider execution.

    Every public call crosses this boundary.  No public argument can supply an
    admission result, lifecycle date, runtime snapshot, or recursion token.
    Recursive cascade and cooldown work stays in
    :func:`_execute_admitted_video_chain` with the immutable tuple produced
    here.
    """
    from cinema.aspect import DEFAULT_ASPECT_RATIO
    from cinema.context import get_project_setting

    aspect = get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)
    requested_api = target_api if isinstance(target_api, str) else ""
    requested_upper = requested_api.upper()
    if requested_upper == "AUTO":
        raw_fallbacks = (
            list(video_fallbacks)
            if video_fallbacks is not None
            else list(DEFAULT_VIDEO_CASCADE)
        )
        policy_seed: list[object] = ["AUTO", *raw_fallbacks]
    elif video_fallbacks is not None:
        policy_seed = [requested_upper, *video_fallbacks]
    else:
        # A concrete target with no explicit chain is pinned.  Provider
        # failure or policy rejection must not revive global defaults.
        policy_seed = [requested_upper]

    policy_filter = (
        filter_automatic_dispatch_candidates
        if requested_upper == "AUTO"
        else filter_dispatch_candidates
    )
    dispatch_policy = policy_filter(
        policy_seed,
        snapshot=_video_policy_runtime_snapshot(),
        on_date=_video_policy_current_date(),
        api_engines=get_project_setting(ctx, "api_engines", None),
        aspect_ratio=aspect,
    )
    serialized_rejections = _serialized_policy_rejections(dispatch_policy)
    if _cascade_out is not None:
        existing_rejections = _cascade_out.setdefault("policy_rejections", [])
        for rejection in serialized_rejections:
            if rejection not in existing_rejections:
                existing_rejections.append(rejection)

    try:
        from cost_tracker import CostTracker
    except Exception:
        CostTracker = None  # type: ignore[assignment,misc]
    _has_paid_authority = (
        CostTracker is not None and isinstance(cost_tracker, CostTracker)
    )
    _recovery_owner: dict | None = None
    if _has_paid_authority and video_id and shot_id:
        paid_snapshot = cost_tracker.get_paid_attempts_snapshot(video_id)
        durable_motion_owners = {
            ("fal", "VEO"),
            ("fal", "KLING_3_0"),
            ("fal", "SEEDANCE"),
            ("fal", "LTX"),
            ("fal", "FAL_SVD"),
            ("kling", "KLING_NATIVE"),
            ("openai", "SORA_NATIVE"),
        }
        active_motion = [
            attempt
            for attempt in paid_snapshot.get("attempts", ())
            if attempt.get("active")
            and attempt.get("shot_id") == shot_id
            and attempt.get("operation") == "motion_generation"
            and (attempt.get("provider"), attempt.get("engine"))
            in durable_motion_owners
        ]
        if len(active_motion) > 1:
            if _cascade_out is not None:
                _cascade_out["policy_error"] = {
                    "error": "Multiple paid motion requests claim this shot",
                    "error_kind": "paid_attempt_authority",
                    "code": "multiple_active_paid_attempts",
                    "target_api": requested_upper,
                    "reason": "operator_reconciliation_required",
                    "retryable": False,
                }
            return None
        if active_motion:
            _recovery_owner = active_motion[0]
            if _cascade_out is not None:
                _cascade_out["recovery_owner"] = {
                    "attempt_id": _recovery_owner.get("attempt_id"),
                    "engine": _recovery_owner.get("engine"),
                    "state": _recovery_owner.get("state"),
                    "provider_job_id": _recovery_owner.get("provider_job_id") or None,
                }

    primary_rejected = any(
        rejection.key == requested_upper
        for rejection in dispatch_policy.rejections
    )
    if _recovery_owner is None and (
        not dispatch_policy.candidates
        or (requested_upper != "AUTO" and primary_rejected)
    ):
        if _cascade_out is not None:
            _cascade_out["policy_error"] = _dispatch_policy_error(
                requested_api,
                dispatch_policy,
            )
        return None

    admitted_candidates = (
        (str(_recovery_owner["engine"]),)
        if _recovery_owner is not None
        else dispatch_policy.candidates
    )
    if requested_upper == "AUTO" and _recovery_owner is None:
        if _has_paid_authority:
            analytics = cost_tracker.get_provider_usage_analytics(
                "",
                terminal_limit=200,
            )
            engine_metrics = analytics.get("by_engine", {})
            health_decisions: list[dict[str, object]] = []
            healthy_candidates: list[str] = []
            for candidate in admitted_candidates:
                metric = engine_metrics.get(candidate, {})
                health = metric.get("health", {}) if isinstance(metric, dict) else {}
                status = str(health.get("status") or "unknown")
                reasons = list(health.get("reasons") or ())
                health_decisions.append({
                    "engine": candidate,
                    "status": status,
                    "reasons": reasons[:8],
                })
                # Unknown history is intentionally neutral. Degraded providers
                # remain usable; only deterministically unhealthy history is
                # removed from automatic paid routing.
                if status != "unhealthy":
                    healthy_candidates.append(candidate)
            admitted_candidates = tuple(healthy_candidates)
            if _cascade_out is not None:
                _cascade_out["provider_health"] = health_decisions
            if not admitted_candidates:
                if _cascade_out is not None:
                    _cascade_out["policy_error"] = {
                        "error": "No automatically eligible healthy video provider",
                        "error_kind": "provider_health",
                        "code": "no_eligible_provider",
                        "target_api": "AUTO",
                        "reason": "all_candidates_unhealthy",
                        "retryable": False,
                    }
                return None
    admitted_primary = (
        admitted_candidates[0]
        if requested_upper == "AUTO"
        else requested_upper
    )
    return _execute_admitted_video_chain(
        image_path,
        camera_motion,
        admitted_primary,
        output_mp4,
        pacing=pacing,
        character_id=character_id,
        attempted_apis=attempted_apis,
        multi_angle_refs=multi_angle_refs,
        _cascade_retries=0,
        negative_prompt=negative_prompt,
        shot_type=shot_type,
        driving_video_path=driving_video_path,
        has_dialogue=has_dialogue,
        dialogue_native_audio=dialogue_native_audio,
        duration=duration,
        ctx=ctx,
        _cascade_out=_cascade_out,
        cost_tracker=cost_tracker,
        shot_id=shot_id,
        video_id=video_id,
        admitted_candidates=admitted_candidates,
        aspect=aspect,
        _attempt_history=list(attempted_apis or ()),
        _expected_paid_attempt_id=(
            str(_recovery_owner["attempt_id"])
            if _recovery_owner is not None
            else None
        ),
    )


def _execute_admitted_video_chain(
    image_path: str,
    camera_motion: str,
    target_api: str,
    output_mp4: str,
    pacing: str = "moderate",
    character_id: str = None,
    attempted_apis: list = None,
    multi_angle_refs: list = None,
    _cascade_retries: int = 0,
    negative_prompt: str = None,
    shot_type: str = None,
    driving_video_path: str = "",
    has_dialogue: bool = False,
    dialogue_native_audio: bool = False,
    duration: str = "8s",
    ctx: Optional["PipelineContext"] = None,
    _cascade_out: Optional[dict] = None,
    cost_tracker=None,
    shot_id: str = "",
    video_id: str = "",
    *,
    admitted_candidates: tuple[str, ...],
    aspect: str,
    _attempt_history: list[str],
    _expected_paid_attempt_id: str | None = None,
) -> str:
    """
    Routes an image → video via smart shot-type-aware routing with native APIs.

    v3 changes:
    - Native Kling API (JWT auth, subject binding, face_consistency)
    - Native Google Veo 3.1 (start-image I2V, conditional native audio)
    - Native OpenAI Sora 2 (deprecated explicit image-only compatibility)
    - LTX Video (4K, persisted asynchronous jobs, cheapest)
    - Runway Gen-4 Turbo (single reference image, turbo preview)
    - Smart routing: shot_type determines primary API
    - Fallback cascade per shot type from workflow_selector

    v4 addition — driving_video_path:
        Optional path to a performance-capture clip (output of Act-Two /
        LivePortrait / Viggle). When supplied, engines that accept a
        reference video use it as motion guidance. The current Veo, Sora,
        Kling, LTX, and Runway Gen-4 I2V adapters do not accept that clip.
        In particular, Sora rejects the argument before submission; Veo keeps
        its interface-compatible argument unused because video extension and
        start-image I2V are mutually exclusive. The performance-aware engines
        are selected elsewhere in the pipeline.
        Empty string disables the feature — preserves existing behavior
        for all callers that haven't been updated yet.

    Budget gate:
        The controller performs an early UX precheck, then this dispatcher
        atomically reserves each provider attempt in SQLite immediately before
        submission. Every fallback obtains its own reservation. Calls without
        the PipelineCore's real CostTracker are compatibility/test-only and do
        not gain paid-submission authority from the earlier soft check.
    """
    from cinema.aspect import fal_aspect_ratio, runway_ratio

    _aspect = aspect

    if attempted_apis is None:
        attempted_apis = []
    _api_upper = target_api.upper()
    if _api_upper not in attempted_apis:
        attempted_apis.append(_api_upper)
    # ``attempted_apis`` is deliberately per-cycle: it prevents a fallback
    # from being dispatched twice before the cooldown.  Provenance has a
    # different contract and must retain every actual dispatch, including the
    # same engine appearing again after a cooldown retry.
    _attempt_history.append(_api_upper)
    if _cascade_out is not None:
        _cascade_out["attempt_history"] = list(_attempt_history)

    # Every real motion attempt receives a deterministic, transaction-backed
    # budget reservation before provider code can submit.  Direct utility/test
    # calls that do not carry the PipelineCore's real CostTracker retain the
    # historical adapter-only behavior.
    _paid_attempt: dict | None = None
    _paid_resume_job_id: str | None = None
    _paid_existing_terminal_skip = False
    _paid_billed = False
    _paid_reconciliation_needed = False
    _paid_attempt_id = ""
    _paid_request_fingerprint = ""
    _paid_estimated_cost = 0.0
    _durable_fal_attempt = False

    def _publish_paid_attempt(snapshot: object) -> None:
        if _cascade_out is None or not isinstance(snapshot, dict):
            return
        public = {
            key: snapshot.get(key)
            for key in (
                "attempt_id", "provider", "engine", "operation", "state",
                "reserved_cost_usd", "reconciled_cost_usd", "billed",
                "provider_job_id", "provider_status", "failure_code",
                "detail", "active",
            )
            if key in snapshot
        }
        attempts = _cascade_out.setdefault("paid_attempts", [])
        for index, prior in enumerate(attempts):
            if prior.get("attempt_id") == public.get("attempt_id"):
                attempts[index] = public
                break
        else:
            attempts.append(public)

    try:
        from cost_tracker import CostTracker
    except Exception:
        CostTracker = None  # type: ignore[assignment,misc]
    if CostTracker is not None and isinstance(cost_tracker, CostTracker):
        from performance.runway_tasks import build_attempt_id
        from paid_provider import file_fingerprint

        try:
            _image_identity = file_fingerprint(image_path)
            _reference_identities = [
                {
                    "position": index,
                    "content": (
                        file_fingerprint(ref)
                        if os.path.exists(ref)
                        else "missing"
                    ),
                }
                for index, ref in enumerate(multi_angle_refs or ())
                if isinstance(ref, str) and ref
            ]
        except (OSError, ValueError) as exc:
            if _cascade_out is not None:
                _cascade_out["policy_error"] = {
                    "error": "Paid motion input could not be fingerprinted safely",
                    "error_kind": "paid_attempt_authority",
                    "code": "input_fingerprint_unavailable",
                    "target_api": _api_upper,
                    "reason": type(exc).__name__,
                    "retryable": False,
                }
            return None

        _estimate_duration: float | None = None
        _estimate_kwargs: dict[str, object] = {}
        if _api_upper == "LTX":
            try:
                _requested = int(str(duration).strip().lower().rstrip("s"))
            except (TypeError, ValueError):
                _requested = _LTX_DURATION_ENUM_S[0]
            _estimate_duration = float(next(
                (seconds for seconds in _LTX_DURATION_ENUM_S if _requested <= seconds),
                _LTX_DURATION_ENUM_S[-1],
            ))
            if getattr(settings, "ltx_api_key", ""):
                _estimate_kwargs = {
                    "backend": "native",
                    "operation": "image_to_video",
                    "model": "ltx-2-3-pro",
                    "resolution": (
                        "4k" if shot_type in ("landscape", "wide") else "1080p"
                    ),
                    "audio": False,
                }
        elif _api_upper == "SEEDANCE":
            _estimate_duration = float(SEEDANCE_DURATIONS.get(shot_type, 4))
        elif _api_upper == "RUNWAY_GEN4":
            _estimate_duration = 10.0

        _estimated_cost = CostTracker.estimate_call_cost_usd(
            _api_upper,
            _estimate_duration,
            **_estimate_kwargs,
        )
        _provider_by_engine = {
            "RUNWAY_GEN4": "runway",
            "LTX": "ltx" if getattr(settings, "ltx_api_key", "") else "fal",
            "VEO_NATIVE": "google",
            "SORA_NATIVE": "openai",
            "KLING_NATIVE": "kling",
            "GEMINI_OMNI": "google",
        }
        _provider = _provider_by_engine.get(_api_upper, "fal")
        _attempt_ordinal = sum(
            1 for attempted in _attempt_history if attempted == _api_upper
        )
        _attempt_id, _request_fingerprint = build_attempt_id(
            provider=_provider,
            engine=_api_upper,
            operation="motion_generation",
            video_id=video_id,
            shot_id=shot_id,
            ordinal=_attempt_ordinal,
            request={
                "image": _image_identity,
                "camera_motion": camera_motion,
                "engine": _api_upper,
                "pacing": pacing,
                "character_id": character_id or "",
                "multi_angle_refs": _reference_identities,
                "negative_prompt": negative_prompt or "",
                "shot_type": shot_type or "",
                "duration": str(duration),
                "aspect": str(aspect),
                "driving_video_path": os.path.abspath(driving_video_path)
                if driving_video_path
                else "",
            },
        )
        if _expected_paid_attempt_id is not None:
            _owned_attempt = cost_tracker.get_paid_attempt(_expected_paid_attempt_id)
            if (
                not isinstance(_owned_attempt, dict)
                or not _owned_attempt.get("active")
                or str(_owned_attempt.get("request_fingerprint") or "")
                != _request_fingerprint
            ):
                if isinstance(_owned_attempt, dict):
                    _paid_attempt = _owned_attempt
                    _publish_paid_attempt(_paid_attempt)
                if _cascade_out is not None:
                    _cascade_out["deferred_job"] = {
                        "engine": _api_upper,
                        "status": "recovery_required",
                        "reason": "request_changed_during_recovery",
                        "attempt_id": _expected_paid_attempt_id,
                        "job_id": (
                            _owned_attempt.get("provider_job_id")
                            if isinstance(_owned_attempt, dict)
                            else None
                        ),
                        "billed": (
                            _owned_attempt.get("billed") is True
                            if isinstance(_owned_attempt, dict)
                            else False
                        ),
                    }
                return None
            # Attempt ordinals are historical metadata. The durable row and its
            # matching request fingerprint are the authority for exact resume.
            _attempt_id = _expected_paid_attempt_id
        _paid_attempt_id = _attempt_id
        _paid_request_fingerprint = _request_fingerprint
        _paid_estimated_cost = _estimated_cost
        _durable_fal_attempt = (
            _provider == "fal"
            and _api_upper in {
                "VEO", "KLING_3_0", "SEEDANCE", "LTX", "FAL_SVD",
            }
        )
        # Queue-backed FAL providers must let run_durable_fal_job own the
        # atomic reservation and the first submit. Reserving here as well would
        # leave a ``submitting`` row with no request ID, causing the helper to
        # (correctly) block what looks like a duplicate submission.
        if not _durable_fal_attempt:
            _paid_attempt = cost_tracker.reserve_paid_attempt(
                attempt_id=_attempt_id,
                provider=_provider,
                engine=_api_upper,
                operation="motion_generation",
                estimated_cost_usd=_estimated_cost,
                shot_id=shot_id,
                video_id=video_id,
                request_fingerprint=_request_fingerprint,
            )
            _publish_paid_attempt(_paid_attempt)
            if not _paid_attempt.get("acquired"):
                _existing_state = str(_paid_attempt.get("state") or "")
                _existing_job = _paid_attempt.get("provider_job_id")
                if isinstance(_existing_job, str) and _existing_job:
                    _paid_resume_job_id = _existing_job
                if _existing_state == "blocked_budget":
                    if _cascade_out is not None:
                        _cascade_out["budget_blocked_attempt"] = dict(_paid_attempt)
                    return None
                if _existing_state in {"failed_unbilled", "cancelled"}:
                    _paid_existing_terminal_skip = True
                elif _existing_state == "failed_billed":
                    if _cascade_out is not None:
                        _cascade_out["terminal_paid_attempt"] = dict(_paid_attempt)
                    return None
                elif (
                    _api_upper not in {"RUNWAY_GEN4", "LTX", "KLING_NATIVE"}
                    or not _paid_resume_job_id
                ):
                    _paid_attempt = cost_tracker.update_paid_attempt(
                        _attempt_id,
                        state="accepted_unknown",
                        detail=(
                            "A prior worker claimed submission; no provider task ID "
                            "is available, so duplicate submission is blocked"
                        ),
                    )
                    _publish_paid_attempt(_paid_attempt)
                    if _cascade_out is not None:
                        _cascade_out["deferred_job"] = {
                            "engine": _api_upper,
                            "status": "recovery_required",
                            "reason": "submission_outcome_unknown",
                            "attempt_id": _attempt_id,
                            "billed": False,
                        }
                    return None

    def _update_paid_attempt(state: str, **kwargs: object) -> None:
        nonlocal _paid_attempt
        if _paid_attempt is None or not isinstance(cost_tracker, CostTracker):
            return
        _paid_attempt = cost_tracker.update_paid_attempt(
            str(_paid_attempt["attempt_id"]),
            state=state,
            **kwargs,
        )
        _publish_paid_attempt(_paid_attempt)

    def _reconcile_paid_attempt(state: str, **kwargs: object) -> None:
        nonlocal _paid_attempt, _paid_reconciliation_needed
        if _paid_attempt is None or not isinstance(cost_tracker, CostTracker):
            return
        try:
            _paid_attempt = cost_tracker.reconcile_paid_attempt(
                str(_paid_attempt["attempt_id"]),
                state=state,
                **kwargs,
            )
        except Exception as exc:
            _paid_reconciliation_needed = True
            try:
                _paid_attempt = cost_tracker.update_paid_attempt(
                    str(_paid_attempt["attempt_id"]),
                    state="accepted_unknown",
                    provider_job_id=_paid_attempt.get("provider_job_id"),
                    provider_status=str(kwargs.get("provider_status") or ""),
                    detail=(
                        "Provider result exists but financial ledger reconciliation "
                        f"failed: {type(exc).__name__}"
                    ),
                    billed=True if state in {"succeeded", "failed_billed"} else None,
                )
            except Exception:
                _paid_attempt = {
                    **_paid_attempt,
                    "state": "accepted_unknown",
                    "active": True,
                    "detail": "Provider result exists but ledger reconciliation failed",
                }
            if _cascade_out is not None:
                _cascade_out["deferred_financial_reconciliation"] = {
                    "attempt_id": _paid_attempt.get("attempt_id"),
                    "engine": _api_upper,
                    "state": "accepted_unknown",
                }
        _publish_paid_attempt(_paid_attempt)

    def _run_motion_fal_job(
        application: str,
        arguments: dict[str, object],
        *,
        with_logs: bool = True,
    ) -> tuple[dict | None, str]:
        """Run one FAL motion request and report its fallback disposition.

        Real pipeline calls use the queue-backed submit/status/result helper.
        Calls without paid-attempt authority retain ``subscribe`` solely as a
        compatibility seam for offline adapter tests and one-off utilities.
        """
        nonlocal _paid_attempt, _paid_billed
        if not _durable_fal_attempt:
            return (
                fal_client.subscribe(
                    application,
                    client_timeout=FAL_TIMEOUT_VIDEO_S,
                    arguments=arguments,
                    with_logs=with_logs,
                ),
                "legacy",
            )

        from paid_provider import (
            PaidCallBudgetBlocked,
            PaidCallDeferred,
            PaidCallUnbilled,
            run_durable_fal_job,
        )

        try:
            result = run_durable_fal_job(
                application=application,
                arguments=arguments,
                attempt_id=_paid_attempt_id,
                engine=_api_upper,
                operation="motion_generation",
                estimated_cost_usd=_paid_estimated_cost,
                request_fingerprint_value=_paid_request_fingerprint,
                cost_tracker=cost_tracker,
                shot_id=shot_id,
                video_id=video_id,
                poll_timeout_s=FAL_TIMEOUT_VIDEO_S,
                with_logs=with_logs,
            )
        except PaidCallBudgetBlocked as exc:
            _paid_attempt = dict(exc.snapshot.attempt)
            _publish_paid_attempt(_paid_attempt)
            if _cascade_out is not None:
                _cascade_out["budget_blocked_attempt"] = dict(_paid_attempt)
            return None, "blocked_budget"
        except PaidCallUnbilled as exc:
            _paid_attempt = dict(exc.attempt)
            _publish_paid_attempt(_paid_attempt)
            return None, "failed_unbilled"
        except PaidCallDeferred as exc:
            _paid_attempt = dict(exc.snapshot.attempt)
            _publish_paid_attempt(_paid_attempt)
            state = str(_paid_attempt.get("state") or "accepted_unknown")
            billed = _paid_attempt.get("billed") is True or state == "failed_billed"
            if _cascade_out is not None:
                if state == "failed_billed":
                    _cascade_out["terminal_paid_attempt"] = dict(_paid_attempt)
                _cascade_out["deferred_job"] = {
                    "engine": _api_upper,
                    "status": "recovery_required",
                    "reason": (
                        "provider_failed_billed"
                        if state == "failed_billed"
                        else "provider_request_pending"
                        if _paid_attempt.get("provider_job_id")
                        else "submission_outcome_unknown"
                    ),
                    "job_id": _paid_attempt.get("provider_job_id") or None,
                    "attempt_id": _paid_attempt.get("attempt_id"),
                    "billed": billed,
                }
            return None, "deferred"

        _paid_attempt = cost_tracker.get_paid_attempt(_paid_attempt_id)
        _publish_paid_attempt(_paid_attempt)
        _paid_billed = True
        return result, "succeeded"

    def _record_video_cascade(
        winning_engine: str,
        **verified_capabilities: object,
    ) -> None:
        """Write cascade_metadata into _cascade_out when this engine succeeds.
        ``_attempt_history`` reflects every actual dispatch in chronological
        order, including repeated engines across cooldown cycles.  The separate
        ``attempted_apis`` list remains the current cycle's dedupe guard.
        """
        _actual_cost: float | None = None
        if _paid_attempt is not None and winning_engine.upper() == "LTX":
            _duration_value = verified_capabilities.get("duration_s")
            _backend_value = str(verified_capabilities.get("backend") or "").lower()
            if _backend_value == "native":
                _actual_cost = CostTracker.estimate_call_cost_usd(
                    "LTX",
                    _duration_value,
                    backend="native",
                    operation=str(
                        verified_capabilities.get("pricing_operation")
                        or "image_to_video"
                    ),
                    model=str(
                        verified_capabilities.get("model") or "ltx-2-3-pro"
                    ),
                    resolution=str(
                        verified_capabilities.get("resolution") or "1080p"
                    ),
                    audio=bool(verified_capabilities.get("audio", False)),
                )
            elif _backend_value == "fal":
                _actual_cost = CostTracker.estimate_call_cost_usd(
                    "LTX", _duration_value
                )
        _reconcile_paid_attempt("succeeded", actual_cost_usd=_actual_cost)
        if _cascade_out is not None:
            metadata = {
                "engine": winning_engine,
                "attempts": list(_attempt_history),
            }
            if _paid_attempt is not None:
                metadata["paid_attempt_id"] = _paid_attempt.get("attempt_id")
                metadata["financial_state"] = _paid_attempt.get("state")
            metadata.update(verified_capabilities)
            _cascade_out["cascade_metadata"] = metadata

    def _note_billed_attempt(engine: str) -> None:
        nonlocal _paid_billed
        _paid_billed = True
        # A provider that RETURNED a video is billed regardless of what
        # happens next (download failure, aspect reject). Note every billed
        # attempt so the caller records spend for billed-but-rejected ones too
        # (money-gate finding 2026-07-11: rejects previously accumulated $0
        # while the provider invoiced the full clip). Native branches call
        # this directly (they write via output_path=, bypassing the download
        # helper); fal/URL branches note through _download_video_or_cascade.
        # _cascade_out threads through the cascade recursion so attempts
        # accumulate across hops; the winner is subtracted caller-side.
        if _cascade_out is not None and _paid_attempt is None:
            _cascade_out.setdefault("billed_attempts", []).append(engine.upper())

    def _safe_deferred_job_id(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        if (
            not value
            or len(value) > 1024
            or any(ord(char) < 32 for char in value)
            or "://" in value
            or any(char in value for char in "?#&")
        ):
            return None
        return value

    def _record_native_deferred(
        engine: str,
        exc: BaseException,
        *,
        billed: bool,
        duration_s: object = None,
    ) -> None:
        """Publish one bounded accepted-job descriptor for the controller."""
        if _cascade_out is None:
            _update_paid_attempt(
                "accepted_unknown",
                provider_job_id=getattr(exc, "job_id", None),
                provider_status=str(getattr(exc, "provider_status", "") or ""),
                detail=str(exc),
                billed=billed,
            )
            return

        raw_status = getattr(exc, "status", None)
        status = (
            raw_status
            if isinstance(raw_status, str)
            and raw_status in {"pending", "recovery_required"}
            else "recovery_required"
        )
        raw_reason = getattr(exc, "reason", None)
        reason = (
            raw_reason
            if isinstance(raw_reason, str)
            and 0 < len(raw_reason) <= 100
            and all(char.isalnum() or char in "_-" for char in raw_reason)
            else "provider_job_ambiguous"
        )
        raw_provider_status = getattr(exc, "provider_status", None)
        provider_status = (
            raw_provider_status
            if isinstance(raw_provider_status, str)
            and 0 < len(raw_provider_status) <= 64
            and all(
                char.isalnum() or char in "_-"
                for char in raw_provider_status
            )
            else None
        )
        deferred = {
            "engine": engine,
            "status": status,
            "reason": reason,
            "attempts": list(_attempt_history),
            "billed": bool(billed),
        }
        job_id = _safe_deferred_job_id(getattr(exc, "job_id", None))
        if job_id is not None:
            deferred["job_id"] = job_id
        if provider_status is not None:
            deferred["provider_status"] = provider_status
        if (
            isinstance(duration_s, (int, float))
            and not isinstance(duration_s, bool)
            and math.isfinite(float(duration_s))
            and float(duration_s) > 0
        ):
            deferred["duration_s"] = float(duration_s)
        _cascade_out["deferred_job"] = deferred
        _update_paid_attempt(
            "accepted_unknown",
            provider_job_id=job_id,
            provider_status=provider_status or "",
            detail=str(exc),
            billed=billed,
        )

    def _record_native_submission_ambiguity(
        engine: str,
        *,
        reason: str,
        detail: str,
        job_id: object = None,
        provider_status: str = "outcome_unknown",
        billed: bool = False,
    ) -> None:
        """Fence a native call once its non-idempotent boundary was entered.

        Native SDK convenience methods may collapse submit, poll, and download
        into one nullable return.  After the submit boundary, ``None`` or an
        exception is not proof that the provider rejected the request.  Keep
        the paid row active and publish recovery metadata instead of cascading
        to a second paid engine.
        """
        safe_job_id = _safe_deferred_job_id(job_id)
        _update_paid_attempt(
            "accepted_unknown",
            provider_job_id=safe_job_id,
            provider_status=provider_status,
            detail=detail,
            billed=billed,
        )
        if _cascade_out is not None:
            deferred = {
                "engine": engine,
                "status": "recovery_required",
                "reason": reason,
                "attempts": list(_attempt_history),
                "billed": bool(billed),
            }
            if safe_job_id is not None:
                deferred["job_id"] = safe_job_id
            if _paid_attempt is not None:
                deferred["attempt_id"] = _paid_attempt.get("attempt_id")
            _cascade_out["deferred_job"] = deferred

    def _download_video_or_cascade(video_url: str, engine: str) -> bool:
        nonlocal _paid_reconciliation_needed
        _note_billed_attempt(engine)
        if safe_download(
            video_url,
            output_mp4,
            allowed_content_types=("video/mp4",),
            content_validator=validate_video_artifact,
        ) is None:
            logger.warning(
                "Generated video download failed — cascading (spend still billed)",
                extra={"engine": engine, "output_mp4": output_mp4},
            )
            _paid_reconciliation_needed = True
            return False
        return True

    # Shot-type-aware negative prompt — tailored to what each shot type actually suffers from.
    # Guard is `not negative_prompt` (not `is None`): callers commonly pass "" for a shot with
    # no negative_constraints (controller.py:1600 → shot.get("negative_constraints", "")), and an
    # empty string must still trigger the builder rather than ship the engine an empty negative.
    if not negative_prompt:
        _base_neg = (
            "blur, distortion, deformed face, identity change, face morph, extra limbs, "
            "floating objects, flickering, temporal inconsistency, plastic skin, "
            "over-smoothed texture, unnatural eye movement, teeth distortion, "
            "clothing pattern change, sudden lighting shift, smearing motion blur"
        )
        _shot_neg = {
            "portrait": ", closed eyes, half-closed eyes, blown highlights on face, asymmetric pupils, double chin artifact",
            "medium": ", disappearing hands, finger merge, prop teleportation",
            "action": ", frozen pose, static cloth, weightless movement, speed ramp glitch",
            "wide": ", miniature people, giant head, forced perspective error, depth plane pop",
            "landscape": ", floating structures, impossible architecture, sky banding, horizon tilt",
        }
        negative_prompt = _base_neg + _shot_neg.get(shot_type, "")

    logger.info(
        "Video routing",
        extra={"engine": target_api, "camera_motion": camera_motion, "shot_type": shot_type or "auto"},
    )

    def try_next_api():
        if _paid_reconciliation_needed and _paid_attempt is not None:
            # A durable FAL helper may already have atomically settled the
            # provider request as succeeded before the local download/aspect
            # check fails. Terminal money rows are immutable; retain that truth
            # and surface an artifact-recovery action instead of attempting an
            # illegal succeeded -> accepted_unknown transition.
            if str(_paid_attempt.get("state") or "") != "succeeded":
                _update_paid_attempt(
                    "accepted_unknown",
                    provider_job_id=_paid_attempt.get("provider_job_id"),
                    provider_status="SUCCEEDED",
                    detail=(
                        "Provider succeeded but local output reconciliation failed; "
                        "the same task must be retrieved instead of cascading"
                    ),
                    billed=True,
                )
            if _cascade_out is not None:
                _cascade_out["deferred_job"] = {
                    "engine": _api_upper,
                    "status": "recovery_required",
                    "reason": "local_reconciliation_failed",
                    "job_id": _paid_attempt.get("provider_job_id"),
                    "attempt_id": _paid_attempt.get("attempt_id"),
                    "billed": True,
                }
            return None
        if _paid_attempt is not None:
            _paid_state = str(_paid_attempt.get("state") or "")
            if _paid_state in {"succeeded", "failed_billed"}:
                # Terminal billed work can be retrieved/reviewed, but it can
                # never authorize a replacement provider submission.
                if _cascade_out is not None:
                    _cascade_out["terminal_paid_attempt"] = dict(_paid_attempt)
                return None
            if _paid_state not in {"failed_unbilled", "cancelled"}:
                _reconcile_paid_attempt(
                    "failed_billed" if _paid_billed else "failed_unbilled",
                    provider_job_id=_paid_attempt.get("provider_job_id"),
                    detail=(
                        "Paid output rejected before fallback"
                        if _paid_billed
                        else "Attempt ended before billable provider output"
                    ),
                )
            if _paid_reconciliation_needed:
                return None
        # This tuple was filtered once at the true entry boundary.  Never read
        # raw fallbacks/defaults here: doing so could revive a retired,
        # disabled, unavailable, or aspect-incompatible engine.
        for api in admitted_candidates:
            if api not in attempted_apis:
                logger.info("Cascade routing to next engine", extra={"engine": api})
                return _execute_admitted_video_chain(
                    image_path, camera_motion, api, output_mp4, pacing,
                    character_id, attempted_apis, multi_angle_refs,
                    shot_type=shot_type,
                    has_dialogue=has_dialogue,
                    dialogue_native_audio=dialogue_native_audio,
                    duration=duration,
                    # Carry (do NOT increment) the retry counter across the
                    # next-engine hop — this is the same cascade pass. Dropping it
                    # reset it to 0 on every hop, so a MULTI-engine all-fail cascade
                    # never reached MAX_CASCADE_RETRIES at its terminal quota-check
                    # and looped the 30s retry forever (W1.3; single-engine cascades
                    # terminated, hiding it). Only the quota-cooldown retry below
                    # (site 2) increments it.
                    _cascade_retries=_cascade_retries,
                    # Forward both cascade-sensitive params across the hop:
                    #  - driving_video_path: preserve the caller contract so
                    #    unsupported engines fail closed. Sora rejects it;
                    #    Veo retains but ignores the compatibility argument;
                    #    Runway Gen-4 has no driving-video input.
                    #  - negative_prompt: else an EXPLICIT caller negative is
                    #    re-derived from shot_type only (override lost). W1.1's
                    #    builder (line 124) supplies the default; this preserves
                    #    an explicit override. Orthogonal, both correct.
                    driving_video_path=driving_video_path,
                    negative_prompt=negative_prompt,
                    ctx=ctx, _cascade_out=_cascade_out,
                    cost_tracker=cost_tracker,
                    shot_id=shot_id,
                    video_id=video_id,
                    admitted_candidates=admitted_candidates,
                    aspect=aspect,
                    _attempt_history=_attempt_history,
                )

        # All APIs failed — try the cascade once more after a quota cooldown.
        # Counts: initial pass + 1 retry = 2 total attempts. Operator may raise
        # this limit via the cascade_retry_limit UI knob.
        # Transaction-owned paid work never replays the whole chain. Each
        # transient operation already has bounded provider-local backoff, and
        # replaying every paid engine after a fixed sleep defeats attempt
        # idempotency and can multiply invoices after permanent failures.
        if _paid_attempt is not None:
            logger.warning(
                "Paid video cascade exhausted; whole-chain replay disabled",
                extra={"attempt_id": _paid_attempt.get("attempt_id")},
            )
            return None
        MAX_CASCADE_RETRIES = 1
        if ctx is not None:
            from cinema.context import get_project_setting
            _override = get_project_setting(ctx, "cascade_retry_limit", None)
            if isinstance(_override, int) and _override >= 0:
                MAX_CASCADE_RETRIES = _override
        if _cascade_retries >= MAX_CASCADE_RETRIES:
            logger.warning(
                "All video APIs exhausted",
                extra={"max_cascade_retries": MAX_CASCADE_RETRIES},
            )
            return None
        logger.warning(
            "All APIs exhausted — waiting 30s for quota refresh",
            extra={"retry": _cascade_retries + 1, "max_cascade_retries": MAX_CASCADE_RETRIES},
        )
        time.sleep(30)
        # Retry the already-admitted chain.  Raw/default seeds are never
        # reloaded after the cooldown.
        first_api = admitted_candidates[0]
        return _execute_admitted_video_chain(
            image_path, camera_motion, first_api, output_mp4, pacing,
            character_id, [], multi_angle_refs, _cascade_retries=_cascade_retries + 1,
            shot_type=shot_type,
            has_dialogue=has_dialogue,
            dialogue_native_audio=dialogue_native_audio,
            duration=duration,
            # Preserve the same fail-closed input contract and negative-prompt
            # override across the quota-cooldown retry.
            driving_video_path=driving_video_path,
            negative_prompt=negative_prompt,
            ctx=ctx, _cascade_out=_cascade_out,
            cost_tracker=cost_tracker,
            shot_id=shot_id,
            video_id=video_id,
            admitted_candidates=admitted_candidates,
            aspect=aspect,
            _attempt_history=_attempt_history,
        )

    if _paid_existing_terminal_skip:
        return try_next_api()

    # Provider imports are deliberately delayed until after the entry fence.
    _load_fal_client()

    # ═══════════════════════════════════════════════════════════════
    # NATIVE API HANDLERS (priority — direct, no proxy, lower cost)
    # ═══════════════════════════════════════════════════════════════

    if target_api.upper() == "KLING_NATIVE":
        # LEGACY native Kling (kling-v1-6) — JWT auth; fallback-only since
        # 2026-07-11 (primary = KLING_3_0 fal v3 Pro). Sends v1.6-era
        # subject-binding params; see kling_native.py's module docstring.
        #
        # _kling_billed_noted makes _note_billed_attempt idempotent for this
        # attempt: generate_video's on_billed hook fires the moment the
        # provider returns a playable video URL (covers a post-billing
        # download failure that still returns None — money-gate 2026-07-11),
        # AND the post-call `if result:` compat path below fires for any
        # caller (test double / stub) that hands back a truthy result
        # without ever invoking on_billed. Whichever fires first wins; the
        # guard stops a real success from appending "KLING_NATIVE" to
        # billed_attempts twice, which would otherwise survive the
        # winner-subtraction in controller._record_billed_rejects and get
        # double-billed as a reject.
        _kling_billed_noted = False
        _kling_submission_started = _paid_resume_job_id is not None
        _kling_job_id = _paid_resume_job_id

        def _note_kling_billed() -> None:
            nonlocal _kling_billed_noted
            if _kling_billed_noted:
                return
            _kling_billed_noted = True
            _note_billed_attempt(target_api.upper())

        def _note_kling_submission_started() -> None:
            nonlocal _kling_submission_started
            _kling_submission_started = True
            _update_paid_attempt(
                "submitting",
                provider_status="submitting",
                detail="Entered Kling native non-idempotent submit boundary",
            )

        def _note_kling_submitted(task_id: str) -> None:
            nonlocal _kling_submission_started, _kling_job_id
            _kling_submission_started = True
            _kling_job_id = task_id
            _update_paid_attempt(
                "running",
                provider_job_id=task_id,
                provider_status="queued",
                detail="Kling native task acknowledged; exact-ID recovery enabled",
            )

        try:
            from kling_native import KlingNativeAPI
            kling = KlingNativeAPI()
            result = kling.generate_video(
                image_path=image_path,
                prompt=(
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration and deceleration. "
                    f"SUBJECT: Maintain rigid facial bone structure — zero face deformation between frames. "
                    f"Same hair, skin tone, clothing pattern in every frame. "
                    f"PHYSICS: Natural body movement with weight and momentum, realistic motion blur. "
                    f"TEMPORAL: Consistent inter-frame luminance, stable color temperature, no flickering. "
                    f"QUALITY: Photorealistic cinematic footage, high definition, consistent volumetric lighting."
                ),
                output_path=output_mp4,
                negative_prompt=negative_prompt,
                face_consistency=True if shot_type in ("portrait", "medium", "action") else False,
                image_references=multi_angle_refs,
                duration="5",
                mode="pro",
                on_billed=_note_kling_billed,
                on_submission_started=_note_kling_submission_started,
                on_submitted=_note_kling_submitted,
                expected_job_id=_paid_resume_job_id,
            )
            if result:
                # Native branch wrote output_mp4 directly (billed) — note it
                # before the aspect backstop so a reject still records spend.
                # No-op when the real on_billed hook already fired above.
                _note_kling_billed()
                # Aspect backstop (also at the other 10 cascade success sites): probe output_mp4 —
                # the file the provider wrote (result==output_mp4 for native branches; see the
                # _accept_or_reject caller contract). Wrong orientation → cascade; no-op for landscape.
                if not _accept_or_reject(output_mp4, _aspect):
                    logger.warning(
                        "Aspect backstop: wrong orientation — rejecting → cascade",
                        extra={"engine": target_api.upper(), "aspect_ratio": _aspect},
                    )
                    return try_next_api()
                _record_video_cascade(target_api.upper())
                return result
            if _kling_submission_started:
                _record_native_submission_ambiguity(
                    "KLING_NATIVE",
                    reason=(
                        "provider_job_pending"
                        if _kling_job_id
                        else "submission_outcome_unknown"
                    ),
                    detail=(
                        "Kling native returned no verified local output after "
                        "entering its paid submission boundary"
                    ),
                    job_id=_kling_job_id,
                    provider_status=("queued" if _kling_job_id else "outcome_unknown"),
                    billed=_paid_billed,
                )
                return None
            # Adapter validation failed before its HTTP submission callback.
            # This is the only safe native-Kling fallback boundary.
            return try_next_api()
        except Exception as e:
            logger.warning("Kling Native error", extra={"engine": "KLING_NATIVE", "error": str(e)})
            if _kling_submission_started:
                _record_native_submission_ambiguity(
                    "KLING_NATIVE",
                    reason=(
                        "provider_job_pending"
                        if _kling_job_id
                        else "submission_outcome_unknown"
                    ),
                    detail=(
                        "Kling native raised after entering its paid submission "
                        f"boundary ({type(e).__name__})"
                    ),
                    job_id=_kling_job_id,
                    provider_status=("queued" if _kling_job_id else "outcome_unknown"),
                    billed=_paid_billed,
                )
                return None
            return try_next_api()

    elif target_api.upper() == "SORA_NATIVE":
        # Native OpenAI Sora 2 — best motion physics
        #
        # _sora_billed_noted makes _note_billed_attempt idempotent for this
        # attempt: generate_video's on_billed hook fires the moment the
        # provider reports the generation completed (covers a post-billing
        # download failure that still returns None — money-gate 2026-07-11,
        # extended to this branch in slice M2), AND the post-call `if result:`
        # compat path below fires for any caller (test double / stub) that
        # hands back a truthy result without ever invoking on_billed.
        # Whichever fires first wins; the guard stops a real success from
        # appending "SORA_NATIVE" to billed_attempts twice.
        _sora_billed_noted = False
        _sora_submission_started = False

        def _note_sora_billed() -> None:
            nonlocal _sora_billed_noted
            if _sora_billed_noted:
                return
            _sora_billed_noted = True
            _note_billed_attempt(target_api.upper())

        def _note_sora_submission_started() -> None:
            nonlocal _sora_submission_started
            _sora_submission_started = True
            _update_paid_attempt(
                "submitting",
                provider_status="submitting",
                detail="Entered Sora native non-idempotent submit boundary",
            )

        try:
            from sora_native import SoraNativeAPI
            sora = SoraNativeAPI()

            # Smart duration within Sora's exact [4, 8, 12] enum.
            # Action/dynamic shots benefit from 8s for full physics arcs
            # Portrait/medium stay at 4s to minimize temporal drift
            _sora_durations = {"action": 8, "wide": 8, "landscape": 8, "portrait": 4, "medium": 4}
            sora_duration = _sora_durations.get(shot_type, 4)

            # Sora excels at cloth simulation and gravity — emphasize these.
            # The adapter receives driving_video_path only to reject nonempty
            # values before image/temp/client work; the Videos API reference
            # input is a still image, not a performance-driving video.
            result = sora.generate_video(
                image_path=image_path,
                prompt=(
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration, weight-aware deceleration. "
                    f"SUBJECT: Maintain exact character appearance throughout — same clothing texture and pattern. "
                    f"PHYSICS: Natural body movement with realistic weight distribution, cloth draping and fabric "
                    f"responding to movement direction, hair physics with momentum, consistent gravity throughout. "
                    f"TEMPORAL: Consistent luminance, stable color temperature, no flickering between frames. "
                    f"QUALITY: Photorealistic cinematic footage, natural film grain, volumetric depth."
                ),
                output_path=output_mp4,
                duration=sora_duration,
                resolution="1080p",
                driving_video_path=driving_video_path,
                aspect_ratio=fal_aspect_ratio(_aspect),
                on_billed=_note_sora_billed,
                on_submission_started=_note_sora_submission_started,
            )
            if result:
                # Native branch wrote output_mp4 directly (billed) — note it
                # before the aspect backstop so a reject still records spend.
                # No-op when the real on_billed hook already fired above.
                _note_sora_billed()
                if not _accept_or_reject(output_mp4, _aspect):
                    logger.warning(
                        "Aspect backstop: wrong orientation — rejecting → cascade",
                        extra={"engine": target_api.upper(), "aspect_ratio": _aspect},
                    )
                    return try_next_api()
                _record_video_cascade(target_api.upper())
                return result
            if _sora_submission_started:
                _record_native_submission_ambiguity(
                    "SORA_NATIVE",
                    reason="submission_outcome_unknown",
                    detail=(
                        "Sora native returned no verified local output after "
                        "entering create_and_poll"
                    ),
                    provider_status="outcome_unknown",
                    billed=_paid_billed,
                )
                return None
            # Rejected adapter inputs and preprocessing failures occur before
            # the submission callback and remain proven pre-submit fallbacks.
            return try_next_api()
        except Exception as e:
            logger.warning("Sora Native error", extra={"engine": "SORA_NATIVE", "error": str(e)})
            if _sora_submission_started:
                _record_native_submission_ambiguity(
                    "SORA_NATIVE",
                    reason="submission_outcome_unknown",
                    detail=(
                        "Sora native raised after entering create_and_poll "
                        f"({type(e).__name__})"
                    ),
                    provider_status="outcome_unknown",
                    billed=_paid_billed,
                )
                return None
            return try_next_api()

    elif target_api.upper() == "VEO_NATIVE":
        # Native Google Veo 3.1 — reference images + native audio
        #
        # _veo_billed_noted makes _note_billed_attempt idempotent for this
        # attempt: generate_video's on_billed hook fires the moment the
        # operation response reports a generated video (covers a post-billing
        # bytes-retrieval/write failure that raises a deferred-job signal — money-gate
        # 2026-07-11, extended to this branch in slice M2), AND the post-call
        # `if result:` compat path below fires for any caller (test double /
        # stub) that hands back a truthy result without ever invoking
        # on_billed. Whichever fires first wins; the guard stops a real
        # success from appending "VEO_NATIVE" to billed_attempts twice.
        _veo_billed_noted = False

        def _note_veo_billed() -> None:
            nonlocal _veo_billed_noted
            if _veo_billed_noted:
                return
            _veo_billed_noted = True
            _note_billed_attempt(target_api.upper())

        try:
            from veo_native import VeoNativeJobDeferred
        except Exception:
            VeoNativeJobDeferred = ()

        try:
            from veo_native import VeoNativeAPI
            veo = VeoNativeAPI()
            veo_audio_requested = (
                shot_type == "landscape"
                or (
                    shot_type == "wide"
                    and not (has_dialogue and not dialogue_native_audio)
                )
                or dialogue_native_audio
            )
            veo_audio_generated = bool(
                veo_audio_requested
                and getattr(veo, "supports_native_audio", True)
            )
            result = veo.generate_video(
                image_path=image_path,
                prompt=(
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration. "
                    f"PRESERVE: Maintain exact character appearance from reference images. "
                    f"PHYSICS: Natural body weight and momentum, cloth physics, realistic shadows. "
                    f"TEMPORAL: Consistent luminance, stable color temperature, no flickering. "
                    f"QUALITY: Photorealistic cinematic footage, consistent volumetric lighting."
                ),
                output_path=output_mp4,
                reference_images=multi_angle_refs,
                # Developer-API Veo has no native-audio surface. Preserve the
                # request only on the ADC-backed Vertex client.
                generate_audio=veo_audio_generated,
                driving_video_path=driving_video_path,
                duration=duration,
                aspect_ratio=fal_aspect_ratio(_aspect),
                on_billed=_note_veo_billed,
            )
            if result:
                # Native branch wrote output_mp4 directly (billed) — note it
                # before the aspect backstop so a reject still records spend.
                # No-op when the real on_billed hook already fired above.
                _note_veo_billed()
                if not _accept_or_reject(output_mp4, _aspect):
                    logger.warning(
                        "Aspect backstop: wrong orientation — rejecting → cascade",
                        extra={"engine": target_api.upper(), "aspect_ratio": _aspect},
                    )
                    return try_next_api()
                veo_job_id = _safe_deferred_job_id(
                    getattr(veo, "last_job_id", None)
                )
                veo_success_metadata: dict[str, object] = {
                    "native_audio_generated": veo_audio_generated,
                }
                if veo_job_id is not None:
                    veo_success_metadata["job_id"] = veo_job_id
                _record_video_cascade(
                    target_api.upper(),
                    **veo_success_metadata,
                )
                return result
            # result is None here whether or not the provider billed before
            # failing (on_billed already noted it in the billed case) —
            # cascade to the next engine either way.
            return try_next_api()
        except VeoNativeJobDeferred as e:
            if getattr(e, "billed", False):
                _note_veo_billed()
            logger.warning(
                "Veo Native job deferred — suppressing provider cascade",
                extra={
                    "engine": "VEO_NATIVE",
                    "reason": getattr(e, "reason", "provider_job_ambiguous"),
                    "status": getattr(e, "status", "recovery_required"),
                    "job_id": getattr(e, "job_id", None),
                },
            )
            _record_native_deferred(
                "VEO_NATIVE",
                e,
                billed=_veo_billed_noted,
                duration_s=getattr(e, "duration_s", None),
            )
            return None
        except Exception as e:
            logger.warning("Veo Native error", extra={"engine": "VEO_NATIVE", "error": str(e)})
            return try_next_api()

    elif target_api.upper() == "LTX":
        # LTX Video 2.3 — 4K, cheapest, best for environments + depth/detail
        #
        # _ltx_billed_noted makes _note_billed_attempt idempotent for this
        # attempt: generate_video's on_billed hook fires the moment the
        # provider confirms billable video output (a URL on either path —
        # covers a post-billing download/write failure even when no clip is
        # ultimately published —
        # money-gate 2026-07-11, extended to this branch in slice M2), AND
        # the post-call `if result:` compat path below fires for any caller
        # (test double / stub) that hands back a truthy result without ever
        # invoking on_billed. Whichever fires first wins; the guard stops a
        # real success from appending "LTX" to billed_attempts twice.
        _ltx_billed_noted = False

        def _note_ltx_billed() -> None:
            nonlocal _ltx_billed_noted
            if _ltx_billed_noted:
                return
            _ltx_billed_noted = True
            _note_billed_attempt(target_api.upper())

        def _record_ltx_deferred(
            *,
            reason: str,
            status: str,
            detail: str = "",
            job_id: str | None = None,
            state_path: str | None = None,
            request_fingerprint: str | None = None,
            provider_status: str | None = None,
            duration_s: int | None = None,
        ) -> None:
            """Expose a non-terminal/recovery result without naming a winner."""
            if _cascade_out is None:
                _update_paid_attempt(
                    "accepted_unknown",
                    provider_job_id=job_id,
                    provider_status=provider_status or "",
                    detail=detail or reason,
                    billed=_ltx_billed_noted,
                )
                return
            deferred = {
                "engine": "LTX",
                "status": status,
                "reason": reason,
                "attempts": list(_attempt_history),
                "billed": _ltx_billed_noted,
            }
            optional = {
                "job_id": job_id,
                "state_path": state_path,
                "request_fingerprint": request_fingerprint,
                "provider_status": provider_status,
                "duration_s": duration_s,
                "detail": detail[:500] if detail else None,
            }
            deferred.update(
                (key, value) for key, value in optional.items() if value is not None
            )
            _cascade_out["deferred_job"] = deferred
            _update_paid_attempt(
                "accepted_unknown",
                provider_job_id=job_id,
                provider_status=provider_status or "",
                detail=detail or reason,
                billed=_ltx_billed_noted,
            )

        # Bind exception types BEFORE the main try below so the corresponding
        # except clauses always have real names to
        # evaluate — if `from ltx_native import LTXVideoAPI` itself fails
        # inside that try (module missing, etc.), Python must still be able
        # to resolve the except clause's type expression without a
        # NameError/UnboundLocalError masking the real import failure. The
        # `()` sentinel matches no exception, so an import failure falls
        # through to the generic `except Exception` exactly as before.
        try:
            from ltx_native import LTXContractViolation
        except Exception:
            LTXContractViolation = ()
        try:
            from ltx_native import LTXJobPending
        except Exception:
            LTXJobPending = ()

        try:
            from ltx_native import LTXVideoAPI
            ltx = LTXVideoAPI()

            # LTX has 15 native camera motions — map our motions to LTX params
            _ltx_camera_map = {
                "zoom_in_slow": "zoom_in", "zoom_out_slow": "zoom_out",
                "zoom_in_fast": "zoom_in", "pan_right": "pan_right",
                "pan_left": "pan_left", "pan_up_crane": "crane_up",
                "pan_down": "jib_down", "static_drone": "static",
                "dolly_in_rapid": "dolly_in",
            }
            ltx_camera = _ltx_camera_map.get(camera_motion, camera_motion)

            # Use 4K for landscape + wide (the documented 4K LTX tier), 1080p else.
            # Char-landscape shots reroute to "wide" and must keep their 4K.
            ltx_resolution = "4k" if shot_type in ("landscape", "wide") else "1080p"

            # Thread duration deliberately from the dispatcher/config path
            # (audited 2026-07-30: this call never passed `duration` at all,
            # so every LTX request silently rode the client's old default —
            # itself invalid for the ltx-2-3-pro profile). Parse the shared
            # "Xs"-style config value the same way VEO_NATIVE does, then snap
            # UP to the ltx-2-3-pro duration enum — https://docs.ltx.io/models
            # — via the module-level _LTX_DURATION_ENUM_S (see its own
            # comment for why it's a literal, not an LTXVideoAPI attribute
            # lookup).
            try:
                _ltx_requested_seconds = int(str(duration).strip().lower().rstrip("s"))
            except (TypeError, ValueError):
                _ltx_requested_seconds = _LTX_DURATION_ENUM_S[0]
            ltx_duration = next(
                (s for s in _LTX_DURATION_ENUM_S if _ltx_requested_seconds <= s),
                _LTX_DURATION_ENUM_S[-1],
            )

            # A controller may seed this private cascade channel when retrying
            # deferred native work.  Presence means "resume only": malformed
            # bindings fail closed here, while well-formed values are verified
            # again by the adapter against the freshly computed fingerprint and
            # durable sidecar before any upload/submission.
            _ltx_resume_kwargs: dict[str, object] = {}
            if _cascade_out is not None and "expected_ltx_job" in _cascade_out:
                _ltx_binding = _cascade_out.get("expected_ltx_job")
                if not isinstance(_ltx_binding, dict):
                    _record_ltx_deferred(
                        reason="job_binding_invalid",
                        status="recovery_required",
                        provider_status="unknown",
                        duration_s=ltx_duration,
                    )
                    return None
                _expected_job_id = _ltx_binding.get("job_id")
                _expected_fingerprint = _ltx_binding.get("request_fingerprint")
                if _expected_job_id is None and _expected_fingerprint is None:
                    _record_ltx_deferred(
                        reason="job_binding_invalid",
                        status="recovery_required",
                        provider_status="unknown",
                        duration_s=ltx_duration,
                    )
                    return None
                _ltx_resume_kwargs = {
                    "expected_job_id": _expected_job_id,
                    "expected_request_fingerprint": _expected_fingerprint,
                }

            ltx_prompt = (
                f"MOTION: Smooth cinematic {camera_motion}, gradual acceleration. "
                f"PRESERVE: Maintain character appearance and environment consistency throughout. "
                f"QUALITY: Photorealistic cinematic footage, natural motion, architectural detail, "
                f"consistent volumetric lighting, no artifacts."
            )
            if _durable_fal_attempt and getattr(ltx, "mode", None) == "fal":
                image_url = fal_client.upload_file(image_path)
                folded_prompt = ltx._prompt_with_camera_motion(ltx_prompt, ltx_camera)
                fal_arguments = {
                    "prompt": folded_prompt,
                    "image_url": image_url,
                    "duration": ltx._fal_duration(ltx_duration * 24),
                    "resolution": ltx._fal_resolution(ltx.RESOLUTION_MAP[ltx_resolution]),
                    "generate_audio": False,
                }
                fal_result, fal_disposition = _run_motion_fal_job(
                    ltx.FAL_MODEL_ID,
                    fal_arguments,
                    with_logs=True,
                )
                if fal_result is None:
                    if fal_disposition == "failed_unbilled":
                        return try_next_api()
                    return None
                ltx_job_id = _paid_attempt.get("provider_job_id") if _paid_attempt else None
                if isinstance(ltx_job_id, str) and ltx_job_id:
                    ltx.last_job_id = ltx_job_id
                video_url = fal_result.get("video", {}).get("url")
                if not isinstance(video_url, str) or not video_url:
                    _paid_reconciliation_needed = True
                    return try_next_api()
                result = (
                    output_mp4
                    if _download_video_or_cascade(video_url, "LTX")
                    else None
                )
                if result is None:
                    return try_next_api()
            else:
                # Preserve the existing native LTX sidecar/recovery contract.
                result = ltx.generate_video(
                    image_path=image_path,
                    prompt=ltx_prompt,
                    output_path=output_mp4,
                    camera_motion=ltx_camera,
                    resolution=ltx_resolution,
                    duration=ltx_duration,
                    on_billed=_note_ltx_billed,
                    **_ltx_resume_kwargs,
                )
            _ltx_job_id = getattr(ltx, "last_job_id", None)
            if not isinstance(_ltx_job_id, str) or not _ltx_job_id:
                _ltx_job_id = None
            _ltx_fingerprint = getattr(ltx, "last_request_fingerprint", None)
            if not isinstance(_ltx_fingerprint, str) or not _ltx_fingerprint:
                _ltx_fingerprint = None
            if result:
                # Native branch wrote output_mp4 directly (billed) — note it
                # before the aspect backstop so a reject still records spend.
                # No-op when the real on_billed hook already fired above.
                _note_ltx_billed()
                if not _accept_or_reject(output_mp4, _aspect):
                    logger.warning(
                        "Aspect backstop rejected billed LTX output — deferring",
                        extra={"engine": target_api.upper(), "aspect_ratio": _aspect},
                    )
                    _record_ltx_deferred(
                        reason="output_aspect_rejected",
                        status="recovery_required",
                        job_id=_ltx_job_id,
                        request_fingerprint=_ltx_fingerprint,
                        provider_status="completed",
                        duration_s=ltx_duration,
                    )
                    return None
                # Surface the true dispatched duration and native provider job
                # ID so accounting can use a durable idempotency key.
                _ltx_success_metadata: dict[str, object] = {
                    "duration_s": ltx_duration,
                }
                if _paid_attempt is not None:
                    _ltx_backend = getattr(ltx, "mode", "")
                    if _ltx_backend not in {"native", "fal"}:
                        _ltx_backend = (
                            "native" if getattr(settings, "ltx_api_key", "") else "fal"
                        )
                    _ltx_success_metadata.update({
                        "backend": _ltx_backend,
                        "model": "ltx-2-3-pro",
                        "resolution": ltx_resolution,
                        "audio": False,
                        "pricing_operation": "image_to_video",
                    })
                if _ltx_job_id is not None:
                    _ltx_success_metadata["job_id"] = _ltx_job_id
                _record_video_cascade(
                    target_api.upper(),
                    **_ltx_success_metadata,
                )
                return result
            # A billed LTX result that could not be published must not trigger
            # another provider. Legacy/test-double paths may report this only
            # through the billing callback instead of LTXJobPending.
            if _ltx_billed_noted:
                _record_ltx_deferred(
                    reason="billed_output_unavailable",
                    status="recovery_required",
                    job_id=_ltx_job_id,
                    request_fingerprint=_ltx_fingerprint,
                    provider_status="completed",
                    duration_s=ltx_duration,
                )
                return None
            # An explicit terminal provider failure or a wholly pre-submission
            # failure remains safe to cascade.
            return try_next_api()
        except LTXJobPending as e:
            logger.warning(
                "LTX job deferred — suppressing provider cascade",
                extra={
                    "engine": "LTX",
                    "reason": getattr(e, "reason", "job_pending"),
                    "status": getattr(e, "status", "pending"),
                    "job_id": getattr(e, "job_id", None),
                },
            )
            _record_ltx_deferred(
                reason=getattr(e, "reason", "job_pending"),
                status=getattr(e, "status", "pending"),
                detail=str(e),
                job_id=getattr(e, "job_id", None),
                state_path=getattr(e, "state_path", None),
                request_fingerprint=getattr(e, "request_fingerprint", None),
                provider_status=getattr(e, "provider_status", None),
                duration_s=(
                    getattr(e, "duration_s", None)
                    if isinstance(getattr(e, "duration_s", None), int)
                    else ltx_duration
                ),
            )
            return None
        except LTXContractViolation as e:
            # A LOCAL request-construction bug (e.g. an out-of-enum duration
            # reaching generate_video despite the snap above), not a
            # provider-side failure — the blanket `except Exception` below
            # would otherwise fold it into routine cascade noise
            # indistinguishable from a transient provider error
            # (silent-gate-degradation doctrine: a local-contract bug must be
            # VISIBLE). Still cascades — a broken LTX dispatch must not stall
            # the shot — but at WARNING with a distinct reason, and recorded
            # into _cascade_out for callers/tests to inspect, not just logged.
            logger.warning(
                "LTX contract violation — local request-construction bug, "
                "not a provider failure",
                extra={"engine": "LTX", "reason": "ltx_contract_violation", "error": str(e)},
            )
            if _cascade_out is not None:
                _cascade_out.setdefault("contract_violations", []).append(
                    {"engine": "LTX", "reason": "ltx_contract_violation", "detail": str(e)}
                )
            return try_next_api()
        except Exception as e:
            logger.warning("LTX error", extra={"engine": "LTX", "error": str(e)})
            if _durable_fal_attempt and _paid_attempt is not None:
                _paid_reconciliation_needed = True
            return try_next_api()

    elif target_api.upper() == "RUNWAY_GEN4":
        # Runway Gen-4 Turbo (image_to_video, model="gen4_turbo") — single
        # reference image (prompt_image accepts ONE image here; there is no
        # multi-reference style-lock on this endpoint), best prompt adherence.
        from performance.runway_tasks import (
            call_with_backoff,
            classify_task_failure,
            error_status_code,
            retry_delay_seconds,
        )

        def _defer_runway(reason: str, detail: str, *, status: str = "") -> None:
            _update_paid_attempt(
                "accepted_unknown",
                provider_job_id=_paid_resume_job_id,
                provider_status=status,
                detail=detail,
                billed=_paid_billed,
            )
            if _cascade_out is not None:
                _cascade_out["deferred_job"] = {
                    "engine": "RUNWAY_GEN4",
                    "status": "recovery_required",
                    "reason": reason,
                    "job_id": _paid_resume_job_id,
                    "attempt_id": (
                        _paid_attempt.get("attempt_id") if _paid_attempt else None
                    ),
                    "duration_s": 10,
                    "billed": _paid_billed,
                }

        try:
            # Validate content and build the correctly typed data URI before
            # constructing the SDK client or submitting a paid request.
            data_uri = _runway_image_data_uri(image_path)

            from runwayml import RunwayML
            client = RunwayML(api_key=settings.runwayml_api_secret)

            logger.info("Runway Gen-4 I2V with style lock", extra={"engine": "RUNWAY_GEN4"})
            task_id = _paid_resume_job_id
            if not task_id:
                # A 429 is an explicit refusal and safe to retry; transport and
                # 5xx submit outcomes are ambiguous and must not submit again.
                create_attempt = 0
                while True:
                    try:
                        submitted = client.image_to_video.create(
                            model="gen4_turbo",
                            prompt_image=data_uri,
                            prompt_text=(
                                f"Smooth cinematic {camera_motion}. "
                                f"Maintain exact character appearance throughout. "
                                f"Natural body movement, consistent lighting, photorealistic quality."
                            ),
                            duration=10,
                            ratio=runway_ratio(_aspect, "gen4_turbo"),
                        )
                        break
                    except Exception as exc:
                        create_attempt += 1
                        if error_status_code(exc) == 429 and create_attempt < 4:
                            time.sleep(
                                retry_delay_seconds(exc, create_attempt - 1)
                            )
                            continue
                        if error_status_code(exc) in {401, 403, 400, 422}:
                            logger.warning(
                                "Runway Gen-4 permanently rejected submission",
                                extra={"engine": "RUNWAY_GEN4", "status": error_status_code(exc)},
                            )
                            return try_next_api()
                        _defer_runway(
                            "submission_outcome_unknown",
                            f"Runway submit outcome ambiguous: {type(exc).__name__}",
                        )
                        return None
                task_id = getattr(submitted, "id", None)
                if not isinstance(task_id, str) or not task_id:
                    _defer_runway(
                        "submission_outcome_unknown",
                        "Runway accepted response did not contain a usable task ID",
                    )
                    return None
                _paid_resume_job_id = task_id
                _update_paid_attempt(
                    "running",
                    provider_job_id=task_id,
                    provider_status="PENDING",
                    detail="Runway task accepted; polling durable task identity",
                )

            max_wait = 300
            elapsed = 0
            while True:
                try:
                    task = call_with_backoff(
                        lambda: client.tasks.retrieve(id=task_id),
                        attempts=4,
                        base_delay_s=0.5,
                    )
                except Exception as exc:
                    _defer_runway(
                        "retrieval_ambiguous",
                        f"Runway task retrieval remained unavailable: {type(exc).__name__}",
                    )
                    return None
                task_status = str(getattr(task, "status", "") or "").upper()
                if task_status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    break
                if elapsed >= max_wait:
                    _defer_runway(
                        "poll_timeout",
                        "Runway task still owns the shot after the local poll timeout",
                        status=task_status or "UNKNOWN",
                    )
                    return None
                _update_paid_attempt(
                    "running",
                    provider_job_id=task_id,
                    provider_status=task_status or "PENDING",
                    detail="Runway task is still running",
                )
                time.sleep(10)
                elapsed += 10
                if elapsed % 30 == 0:
                    logger.debug("Runway Gen-4 polling", extra={"engine": "RUNWAY_GEN4", "elapsed_s": elapsed})

            if task_status == "CANCELLED":
                _reconcile_paid_attempt(
                    "cancelled",
                    provider_job_id=task_id,
                    provider_status=task_status,
                    detail="Runway reported terminal cancellation",
                )
                return None

            if task_status == "FAILED":
                failure = classify_task_failure(task)
                terminal_state = "failed_billed" if failure["billed"] else "failed_unbilled"
                _reconcile_paid_attempt(
                    terminal_state,
                    provider_job_id=task_id,
                    provider_status=task_status,
                    failure_code=str(failure["code"]),
                    detail="Runway reported a terminal task failure",
                )
                if failure["billed"] or failure["permanent"]:
                    if _cascade_out is not None:
                        _cascade_out["terminal_paid_attempt"] = dict(_paid_attempt or {})
                    return None
                return try_next_api()

            output = getattr(task, "output", None)
            if task_status == "SUCCEEDED" and output:
                video_url = output[0] if isinstance(output, list) else output
                if not _download_video_or_cascade(video_url, "RUNWAY_GEN4"):
                    return try_next_api()
                logger.info("Runway Gen-4 success", extra={"engine": "RUNWAY_GEN4", "output_mp4": output_mp4})
                if not _accept_or_reject(output_mp4, _aspect):
                    logger.warning(
                        "Aspect backstop: wrong orientation — rejecting → cascade",
                        extra={"engine": target_api.upper(), "aspect_ratio": _aspect},
                    )
                    return try_next_api()
                _record_video_cascade(
                    target_api.upper(),
                    job_id=task_id,
                    duration_s=10,
                )
                return output_mp4

            _defer_runway(
                "provider_output_missing",
                "Runway reported success without a usable output URL",
                status=task_status,
            )
            return None

        except Exception as e:
            logger.warning("Runway Gen-4 error", extra={"engine": "RUNWAY_GEN4", "error": str(e)})
            if _paid_resume_job_id:
                _defer_runway(
                    "retrieval_ambiguous",
                    f"Runway accepted task hit a local error: {type(e).__name__}",
                )
                return None
            return try_next_api()

    # ═══════════════════════════════════════════════════════════════
    # FAL PROXY HANDLERS (fallback — when native APIs unavailable)
    # ═══════════════════════════════════════════════════════════════

    elif target_api.upper() == "VEO":
        # Veo 3.1 reference-to-video via fal.ai — preserves subject from reference images
        global _VEO_QUOTA_EXHAUSTED_UNTIL
        if _veo_quota_blocked():
            remaining = int(_VEO_QUOTA_EXHAUSTED_UNTIL - time.time())
            logger.warning(
                "VEO quota cooldown active — cascading",
                extra={"engine": "VEO", "cooldown_remaining_s": remaining},
            )
            return try_next_api()

        fal_key = settings.fal_key
        if fal_key and FAL_AVAILABLE:
            try:
                logger.info("fal.ai Veo 3.1 reference-to-video", extra={"engine": "VEO"})

                # Upload reference images for subject preservation
                image_urls = []
                if multi_angle_refs:
                    for ref_path in multi_angle_refs[:4]:
                        if os.path.exists(ref_path):
                            try:
                                image_urls.append(fal_client.upload_file(ref_path))
                            except (OSError, RuntimeError) as e:
                                logger.warning(
                                    "Failed to upload ref image",
                                    extra={"engine": "VEO", "ref_path": ref_path, "error": str(e)},
                                )

                # Always include the source keyframe
                if not image_urls:
                    image_urls = [fal_client.upload_file(image_path)]

                veo_prompt = (
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration, no sudden jumps. "
                    f"PRESERVE: Maintain rigid facial bone structure from reference images — "
                    f"zero face deformation between frames. Same hair, skin tone, clothing texture throughout. "
                    f"CONSTRAIN: Do not morph facial features. Do not change clothing pattern. "
                    f"Do not alter skin tone or hair between frames. "
                    f"PHYSICS: Natural body weight and momentum, cloth physics, realistic shadows. "
                    f"TEMPORAL: Consistent inter-frame luminance, stable color temperature, no flickering. "
                    f"QUALITY: Photorealistic cinematic footage, natural motion physics, "
                    f"consistent volumetric lighting throughout, no visual artifacts."
                )

                result, fal_disposition = _run_motion_fal_job(
                    "fal-ai/veo3.1/reference-to-video",
                    {
                        "prompt": veo_prompt,
                        "image_urls": image_urls,
                        "aspect_ratio": fal_aspect_ratio(_aspect),
                        "duration": duration,
                        "resolution": "720p",
                        "generate_audio": False,
                    },
                    with_logs=True,
                )
                if result is None:
                    if fal_disposition == "failed_unbilled":
                        return try_next_api()
                    return None

                video_url = result.get("video", {}).get("url")
                if video_url:
                    if not _download_video_or_cascade(video_url, "VEO"):
                        return try_next_api()
                    logger.info("VEO success", extra={"engine": "VEO", "output_mp4": output_mp4})
                    if not _accept_or_reject(output_mp4, _aspect):
                        logger.warning(
                            "Aspect backstop: wrong orientation — rejecting → cascade",
                            extra={"engine": target_api.upper(), "aspect_ratio": _aspect},
                        )
                        return try_next_api()
                    _record_video_cascade(target_api.upper())
                    return output_mp4

                if fal_disposition == "succeeded":
                    _paid_reconciliation_needed = True
                    return try_next_api()
                return try_next_api()

            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
                    _VEO_QUOTA_EXHAUSTED_UNTIL = time.time() + _VEO_QUOTA_TTL_S
                    logger.warning(
                        "VEO quota exhausted — blocking VEO",
                        extra={"engine": "VEO", "block_duration_s": _VEO_QUOTA_TTL_S},
                    )
                logger.warning("Veo 3.1 error", extra={"engine": "VEO", "error": str(e)})
                if _durable_fal_attempt and _paid_attempt is not None:
                    _paid_reconciliation_needed = True
                    return try_next_api()
                return try_next_api()
        else:
            logger.warning("FAL_KEY missing for Veo — cascading", extra={"engine": "VEO"})
            return try_next_api()
            
    elif target_api.upper() == "KLING_3_0":
        # Kling v3 Pro via fal.ai (fal-ai/kling-video/v3/pro) — the current
        # automatic Kling route in templates and the default cascade. Identity
        # uses the v3-era `elements` mechanism (frontal + reference images,
        # addressed as @Element1 in the prompt); legacy KLING_NATIVE
        # (kling-v1-6) remains explicit-only compatibility.
        fal_key = settings.fal_key
        if fal_key and FAL_AVAILABLE:
            try:
                logger.info("fal.ai Kling 3.0 Pro I2V", extra={"engine": "KLING_3_0"})

                # Uploads are non-generation preparation. The transaction-backed
                # reservation happens immediately before the one queue submit.
                start_image_url = fal_client.upload_file(image_path)
                has_elements = bool(
                    multi_angle_refs
                    and any(os.path.exists(ref) for ref in multi_angle_refs)
                )
                subject_ref = "@Element1" if has_elements else "The character"
                kling_prompt = (
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration and deceleration. "
                    f"SUBJECT: {subject_ref} maintains rigid facial bone structure — zero face deformation between frames. "
                    f"Same hair, skin tone, clothing pattern in every frame. "
                    f"PRESERVE: Do not morph, distort, or alter facial features, eyes, teeth, or hair at any frame. "
                    f"PHYSICS: Natural body movement with weight and momentum, realistic directional motion blur, "
                    f"consistent gravity, cloth physics responding to movement. "
                    f"TEMPORAL: Consistent inter-frame luminance, stable color temperature, no flickering. "
                    f"QUALITY: Photorealistic cinematic footage, high definition, consistent volumetric lighting."
                )
                args = {
                    "start_image_url": start_image_url,
                    "prompt": kling_prompt,
                    "duration": "5",
                    "generate_audio": False,
                    "cfg_scale": 0.5,
                    "negative_prompt": (
                        "blur, distortion, deformed face, identity change, face morph, extra limbs, "
                        "floating objects, flickering, temporal inconsistency, plastic skin, "
                        "over-smoothed texture, unnatural eye movement, teeth distortion, "
                        "clothing pattern change, sudden lighting shift, smearing motion blur"
                    ),
                }

                if multi_angle_refs:
                    valid_refs = [ref for ref in multi_angle_refs if os.path.exists(ref)]
                    if valid_refs:
                        frontal_url = fal_client.upload_file(valid_refs[0])
                        extra_urls = []
                        for ref_path in valid_refs[1:4]:
                            try:
                                extra_urls.append(fal_client.upload_file(ref_path))
                            except (OSError, RuntimeError) as exc:
                                logger.warning(
                                    "Failed to upload ref image",
                                    extra={
                                        "engine": "KLING_3_0",
                                        "ref_path": ref_path,
                                        "error": str(exc),
                                    },
                                )
                        args["elements"] = [{
                            "frontal_image_url": frontal_url,
                            "reference_image_urls": extra_urls,
                        }]
                        logger.info(
                            "Kling subject bound",
                            extra={"engine": "KLING_3_0", "extra_angle_refs": len(extra_urls)},
                        )

                result, fal_disposition = _run_motion_fal_job(
                    "fal-ai/kling-video/v3/pro/image-to-video",
                    args,
                    with_logs=True,
                )
                if result is None:
                    if fal_disposition == "failed_unbilled":
                        return try_next_api()
                    return None

                video_url = result.get("video", {}).get("url")
                if video_url:
                    if not _download_video_or_cascade(video_url, "KLING_3_0"):
                        return try_next_api()
                    logger.info("Kling success", extra={"engine": "KLING_3_0", "output_mp4": output_mp4})
                    if not _accept_or_reject(output_mp4, _aspect):
                        logger.warning(
                            "Aspect backstop: wrong orientation — rejecting → recovery",
                            extra={"engine": target_api.upper(), "aspect_ratio": _aspect},
                        )
                        return try_next_api()
                    _record_video_cascade(target_api.upper())
                    return output_mp4

                logger.warning("Kling returned no video URL", extra={"engine": "KLING_3_0"})
                if fal_disposition == "succeeded":
                    _paid_reconciliation_needed = True
                return try_next_api()

            except Exception as e:
                logger.warning(
                    "Kling 3.0 Pro fal.ai error",
                    extra={"engine": "KLING_3_0", "error": str(e)},
                )
                if _durable_fal_attempt and _paid_attempt is not None:
                    _paid_reconciliation_needed = True
                return try_next_api()
        else:
            global _FAL_MISSING_WARNED
            if not _FAL_MISSING_WARNED:
                _FAL_MISSING_WARNED = True
                logger.warning(
                    "STRUCTURAL: fal client unavailable — the fal primaries "
                    "(KLING_3_0 portrait/medium, SEEDANCE action) are disabled "
                    "for this entire run",
                    extra={"engine": "KLING_3_0"},
                )
            logger.warning("FAL_KEY missing for Kling — cascading", extra={"engine": "KLING_3_0"})
            return try_next_api()

    elif target_api.upper() == "FAL_SVD":
        # Stable Video Diffusion via Fal.ai serverless endpoint (fal-ai/fast-svd).
        # Previously named "COMFY_UI" — misleading because this branch does NOT
        # talk to ComfyUI; it calls the FAL fast-SVD endpoint directly. Renamed
        # for accuracy. Operator override key in shot.target_api should now be
        # "FAL_SVD".
        fal_key = settings.fal_key
        if fal_key and FAL_AVAILABLE:
            try:
                logger.info("Generating frame via FAL fast-SVD endpoint", extra={"engine": "FAL_SVD"})

                # IP-Adapter Injection Simulation:
                ref_img_url = ""
                if character_id and os.path.exists("characters.json"):
                    with open("characters.json") as f:
                        chars = json.load(f)
                    ref_img = chars.get(character_id, {}).get("reference_image")
                    if ref_img and os.path.exists(ref_img):
                        logger.info(
                            "Injecting IP-Adapter weights for character",
                            extra={"engine": "FAL_SVD", "character_id": character_id},
                        )
                        try:
                            ref_img_url = fal_client.upload_file(ref_img)
                        except AttributeError as e:
                            # fal_client.upload_file missing — SDK not loaded properly.
                            # We previously swallowed this and proceeded with an empty
                            # ref URL (silent identity loss). Surface it and cascade.
                            logger.error(
                                "fal_client.upload_file missing while uploading character ref",
                                extra={"engine": "FAL_SVD", "error": str(e)},
                            )
                            return try_next_api()

                try:
                    base_img_url = fal_client.upload_file(image_path)
                except AttributeError as e:
                    # We previously substituted a random picsum.photos placeholder.
                    # That produced "successful" videos with the wrong content.
                    # Fail cleanly so the cascade can route to a working backend.
                    logger.error(
                        "fal_client.upload_file missing for base image",
                        extra={"engine": "FAL_SVD", "image_path": image_path, "error": str(e)},
                    )
                    return try_next_api()

                result, fal_disposition = _run_motion_fal_job(
                    "fal-ai/fast-svd",
                    {
                        "image_url": base_img_url,
                        "motion_bucket_id": 127,
                        "cond_aug": 0.02,
                    },
                    with_logs=False,
                )
                if result is None:
                    if fal_disposition == "failed_unbilled":
                        return try_next_api()
                    return None

                video_url = result.get("video", {}).get("url")
                if video_url:
                    if not _download_video_or_cascade(video_url, "FAL_SVD"):
                        return try_next_api()
                    if not _accept_or_reject(output_mp4, _aspect):
                        logger.warning(
                            "Aspect backstop: wrong orientation — rejecting → cascade",
                            extra={"engine": target_api.upper(), "aspect_ratio": _aspect},
                        )
                        return try_next_api()
                    _record_video_cascade(target_api.upper())
                    return output_mp4
                if fal_disposition == "succeeded":
                    _paid_reconciliation_needed = True
                return try_next_api()
            except Exception as e:
                logger.warning(
                    "FAL_SVD serverless error — re-routing",
                    extra={"engine": "FAL_SVD", "error": str(e)},
                )
                if _durable_fal_attempt and _paid_attempt is not None:
                    _paid_reconciliation_needed = True
                    return None
                return try_next_api()
        else:
            logger.warning("FAL_KEY missing — re-routing", extra={"engine": "FAL_SVD"})
            return try_next_api()
            
    elif target_api.upper() == "SEEDANCE":
        # Seedance 2.0 (ByteDance) via fal.ai — action-tier primary since the
        # Sora sunset (OpenAI retires Sora 2 + the Videos API on 2026-09-24).
        # #1 on the AA i2v arena (2026-07). reference-to-video accepts up to
        # 9 reference images — binds multi-character shots no other cascade
        # member handles. Schema: fal.ai/models/bytedance/seedance-2.0/*/api.
        fal_key = settings.fal_key
        if fal_key and FAL_AVAILABLE:
            try:
                # Upload identity refs beyond the keyframe → reference-to-video
                # (multi-ref identity binding); none → image-to-video (exact
                # keyframe start frame, tightest temporal continuity).
                ref_urls = []
                if multi_angle_refs:
                    # 8, NOT 9. The header above cites the provider's figure of
                    # 9 image_urls TOTAL, and the keyframe occupies the first
                    # slot — so 8 angle refs is exactly the documented capacity,
                    # not one below it. tests/unit/test_seedance_dispatch.py
                    # ::test_refs_capped_at_nine_total pins keyframe+8=9 and
                    # caught a change to 9 here on 2026-08-08.
                    for ref_path in multi_angle_refs[:8]:
                        if os.path.exists(ref_path):
                            try:
                                ref_urls.append(fal_client.upload_file(ref_path))
                            except (OSError, RuntimeError) as e:
                                logger.warning(
                                    "Failed to upload ref image",
                                    extra={"engine": "SEEDANCE", "ref_path": ref_path, "error": str(e)},
                                )

                keyframe_url = fal_client.upload_file(image_path)

                seedance_duration = SEEDANCE_DURATIONS.get(shot_type, 4)

                seedance_prompt = (
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration and deceleration, "
                    f"no abrupt speed changes. "
                    f"SUBJECT: Maintain rigid facial bone structure — zero face deformation between frames. "
                    f"Same hair, skin, clothing texture in every frame. "
                    f"PHYSICS: Natural body movement with weight and momentum, realistic directional motion blur, "
                    f"consistent gravity, cloth physics responding to movement. "
                    f"TEMPORAL: Consistent inter-frame luminance, stable color temperature, "
                    f"no flickering or sudden lighting shifts. "
                    f"QUALITY: Photorealistic cinematic footage, natural film grain, high definition."
                )

                arguments = {
                    "prompt": seedance_prompt,
                    # 720p: the arena-ranked tier; 1080p is ~2.2x the per-second
                    # price and SeedVR upscales downstream anyway.
                    "resolution": "720p",
                    "duration": seedance_duration,
                    "aspect_ratio": fal_aspect_ratio(_aspect),
                    # Assembly owns audio (TTS/BGM/foley); fal charges the same
                    # either way, but a baked-in track would fight the mix.
                    "generate_audio": False,
                }
                if ref_urls:
                    endpoint = "bytedance/seedance-2.0/reference-to-video"
                    arguments["image_urls"] = [keyframe_url] + ref_urls  # keyframe first; ≤9 total
                else:
                    endpoint = "bytedance/seedance-2.0/image-to-video"
                    arguments["image_url"] = keyframe_url

                logger.info(
                    "fal.ai Seedance 2.0 %s" % ("reference-to-video" if ref_urls else "image-to-video"),
                    extra={"engine": "SEEDANCE", "ref_count": len(ref_urls), "duration_s": seedance_duration},
                )
                result, fal_disposition = _run_motion_fal_job(
                    endpoint,
                    arguments,
                    with_logs=True,
                )
                if result is None:
                    if fal_disposition == "failed_unbilled":
                        return try_next_api()
                    return None

                video_url = result.get("video", {}).get("url")
                if video_url:
                    if not _download_video_or_cascade(video_url, "SEEDANCE"):
                        return try_next_api()
                    logger.info("Seedance success", extra={"engine": "SEEDANCE", "output_mp4": output_mp4})
                    if not _accept_or_reject(output_mp4, _aspect):
                        logger.warning(
                            "Aspect backstop: wrong orientation — rejecting → cascade",
                            extra={"engine": target_api.upper(), "aspect_ratio": _aspect},
                        )
                        return try_next_api()
                    _record_video_cascade(target_api.upper())
                    return output_mp4

                if fal_disposition == "succeeded":
                    _paid_reconciliation_needed = True
                return try_next_api()

            except Exception as e:
                logger.warning("Seedance API error", extra={"engine": "SEEDANCE", "error": str(e)})
                if _durable_fal_attempt and _paid_attempt is not None:
                    _paid_reconciliation_needed = True
                return try_next_api()
        else:
            # (global _FAL_MISSING_WARNED is declared once in the KLING_3_0
            # branch above — one declaration covers the whole function scope.)
            if not _FAL_MISSING_WARNED:
                _FAL_MISSING_WARNED = True
                logger.warning(
                    "STRUCTURAL: fal client unavailable — SEEDANCE (default-cascade "
                    "head + action primary) is disabled for this entire run",
                    extra={"engine": "SEEDANCE"},
                )
            logger.warning("FAL_KEY missing for Seedance — cascading", extra={"engine": "SEEDANCE"})
            return try_next_api()

    elif target_api.upper() == "GEMINI_OMNI":
        # Gemini Omni Flash (Preview) dispatch. Repaired + re-admitted in the
        # typed catalog (Slice 3, 2026-07-30) — reachable for any project
        # whose aspect ratio the admission fence accepts for this key (see
        # domain/video_engine_policy.PORTRAIT_CAPABLE_VIDEO_ENGINES for the
        # current portrait allowlist).
        #
        # _gemini_omni_billed_noted makes _note_billed_attempt idempotent for
        # this attempt: generate_video's on_billed hook fires the moment the
        # interaction reaches "completed" status (covers a post-billing video
        # retrieval/write failure that raises a deferred-job signal — money-gate
        # 2026-07-11, extended to this branch in slice M2), AND the post-call
        # `if result:` compat path below fires for any caller (test double /
        # stub) that hands back a truthy result without ever invoking
        # on_billed. Whichever fires first wins; the guard stops a real
        # success from appending "GEMINI_OMNI" to billed_attempts twice.
        _gemini_omni_billed_noted = False

        def _note_gemini_omni_billed() -> None:
            nonlocal _gemini_omni_billed_noted
            if _gemini_omni_billed_noted:
                return
            _gemini_omni_billed_noted = True
            _note_billed_attempt(target_api.upper())

        global _GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL
        if _gemini_omni_quota_blocked():
            remaining = int(_GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL - time.time())
            logger.warning(
                "GEMINI_OMNI quota cooldown active — cascading",
                extra={"engine": "GEMINI_OMNI", "cooldown_remaining_s": remaining},
            )
            return try_next_api()

        try:
            from gemini_omni_native import GeminiOmniJobDeferred
        except Exception:
            GeminiOmniJobDeferred = ()

        try:
            from gemini_omni_native import GeminiOmniAPI
            omni = GeminiOmniAPI()
            # Duration/resolution/audio are prompt-inferred on this API (no
            # structured kwargs) — encode the same audio intent VEO_NATIVE
            # computes structurally (landscape ambient / wide-non-overlay
            # ambient / native dialogue voice) directly into the prompt text.
            _wants_audio = (
                shot_type == "landscape"
                or (shot_type == "wide" and not (has_dialogue and not dialogue_native_audio))
                or dialogue_native_audio
            )
            _audio_intent = (
                "AUDIO: Generate natural synced audio — ambient environment sound and "
                "dialogue voice as appropriate to the scene."
                if _wants_audio else
                "AUDIO: Silent — no generated audio track; audio is added separately downstream."
            )
            result = omni.generate_video(
                image_path=image_path,
                prompt=(
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration. "
                    f"PRESERVE: Maintain exact character appearance from reference images. "
                    f"PHYSICS: Natural body weight and momentum, cloth physics, realistic shadows. "
                    f"TEMPORAL: Consistent luminance, stable color temperature, no flickering. "
                    f"QUALITY: Photorealistic cinematic footage, consistent volumetric lighting. "
                    f"{_audio_intent}"
                ),
                output_path=output_mp4,
                reference_images=multi_angle_refs,
                aspect_ratio=fal_aspect_ratio(_aspect),
                on_billed=_note_gemini_omni_billed,
            )
            if result:
                # Native branch wrote output_mp4 directly (billed) — note it
                # before the aspect backstop so a reject still records spend.
                # No-op when the real on_billed hook already fired above.
                _note_gemini_omni_billed()
                if not _accept_or_reject(output_mp4, _aspect):
                    logger.warning(
                        "Aspect backstop: wrong orientation — rejecting → cascade",
                        extra={"engine": target_api.upper(), "aspect_ratio": _aspect},
                    )
                    return try_next_api()
                omni_job_id = _safe_deferred_job_id(
                    getattr(omni, "last_job_id", None)
                )
                _record_video_cascade(
                    target_api.upper(),
                    **({"job_id": omni_job_id} if omni_job_id else {}),
                )
                return result
            # result is None here whether or not the provider billed before
            # failing (on_billed already noted it in the billed case) —
            # cascade to the next engine either way.
            return try_next_api()
        except GeminiOmniJobDeferred as e:
            if getattr(e, "billed", False):
                _note_gemini_omni_billed()
            logger.warning(
                "Gemini Omni job deferred — suppressing provider cascade",
                extra={
                    "engine": "GEMINI_OMNI",
                    "reason": getattr(e, "reason", "provider_job_ambiguous"),
                    "status": getattr(e, "status", "recovery_required"),
                    "job_id": getattr(e, "job_id", None),
                },
            )
            _record_native_deferred(
                "GEMINI_OMNI",
                e,
                billed=_gemini_omni_billed_noted,
            )
            return None
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str or "exhausted" in error_str or "budget_exceeded" in error_str:
                _GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL = time.time() + _GEMINI_OMNI_QUOTA_TTL_S
                logger.warning(
                    "GEMINI_OMNI quota exhausted — blocking GEMINI_OMNI",
                    extra={"engine": "GEMINI_OMNI", "block_duration_s": _GEMINI_OMNI_QUOTA_TTL_S},
                )
            logger.warning("Gemini Omni error", extra={"engine": "GEMINI_OMNI", "error": str(e)})
            return try_next_api()

    else:
        # Fallback if UNKNOWN target API is given
        return try_next_api()

def stitch_modules(module_paths: list, final_output: str) -> str:
    """Stitches normalized MP4 modules sequentially using the FFmpeg concat demuxer."""
    # Scope the concat list to the output path (mirror audio/dialogue.py:651) so
    # two stitches running from the same CWD for different projects can't clobber
    # each other's list; clean it up in a finally so a failed ffmpeg run can't leak it.
    list_file = f"{final_output}.concat.txt"
    with open(list_file, "w") as f:
        for path in module_paths:
            f.write(f"file '{os.path.abspath(path)}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", final_output
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        logger.exception(
            "ffmpeg concat error",
            extra={"stderr_tail": e.stderr.decode(errors="replace")[-200:]},
        )
        raise
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)

    logger.info("Stitched sequence", extra={"final_output": final_output})
    return final_output


# ---------------------------------------------------------------------------
# Storyboard split (F2a)
# ---------------------------------------------------------------------------

STORYBOARD_SEGMENT_MIN_TOLERANCE_S = 0.05
STORYBOARD_SEGMENT_MAX_TOLERANCE_S = 0.25
STORYBOARD_SEGMENT_COMPARISON_EPSILON_S = 1e-9
STORYBOARD_SEGMENT_STEM_MAX_LENGTH = 128
STORYBOARD_SEGMENT_STEM_MAX_DECODE_PASSES = 8


def _probe_storyboard_video(path: str) -> tuple:
    """Return ``(video_duration_s, duration_tolerance_s)`` for *path*.

    Coverage uses explicit video-stream duration or positive counted decoded
    frames divided by a validated/derived average frame rate—never container
    duration, which a longer audio stream can inflate.  The tolerance is two
    frame periods, bounded to 50–250 ms, accommodating timestamp rounding and
    encoder delay without accepting a materially short or duplicated segment.
    """
    try:
        stat_result = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(stat_result.st_mode) or stat_result.st_size <= 0:
            raise ValueError("not a non-empty regular file")
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-count_frames",
                "-show_entries",
                "stream=codec_type,duration,avg_frame_rate,nb_read_frames",
                "-of", "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        data = json.loads(probe.stdout)
        streams = data.get("streams") or []
        if not streams or streams[0].get("codec_type") != "video":
            raise ValueError("no video stream")
        stream = streams[0]
        raw_frame_count = stream.get("nb_read_frames")
        if raw_frame_count in (None, "N/A"):
            raise ValueError("video stream has no decoded frames")
        decoded_frames = int(raw_frame_count)
        if decoded_frames <= 0:
            raise ValueError("video stream has no decoded frames")

        frame_rate_s = str(stream.get("avg_frame_rate") or "0/0")
        try:
            numerator_text, denominator_text = frame_rate_s.split("/", 1)
            numerator = float(numerator_text)
            denominator = float(denominator_text)
        except (TypeError, ValueError, OverflowError):
            numerator = 0.0
            denominator = 0.0
        candidate_fps = (
            numerator / denominator
            if (
                math.isfinite(numerator)
                and math.isfinite(denominator)
                and numerator > 0
                and denominator > 0
            )
            else 0.0
        )
        fps = (
            candidate_fps
            if math.isfinite(candidate_fps) and candidate_fps > 0
            else 0.0
        )

        # Container duration may be inflated by a longer audio stream.  Use
        # only explicit video-stream duration, or derive video coverage from
        # decoded frames and a validated average frame rate.
        duration_s = None
        raw_duration = stream.get("duration")
        if raw_duration not in (None, "N/A"):
            candidate_duration_s = float(raw_duration)
            if (
                math.isfinite(candidate_duration_s)
                and candidate_duration_s > 0
            ):
                duration_s = candidate_duration_s
        if duration_s is None:
            if fps <= 0:
                raise ValueError(
                    "video duration unavailable and frame rate is invalid"
                )
            duration_s = decoded_frames / fps
        if not math.isfinite(duration_s) or duration_s <= 0:
            raise ValueError("video duration is not finite and positive")
        if fps <= 0:
            fps = decoded_frames / duration_s
            if not math.isfinite(fps) or fps <= 0:
                raise ValueError(
                    "video frame tolerance cannot be derived"
                )

        frame_tolerance = 2.0 / fps
        tolerance_s = min(
            STORYBOARD_SEGMENT_MAX_TOLERANCE_S,
            max(STORYBOARD_SEGMENT_MIN_TOLERANCE_S, frame_tolerance),
        )
        return duration_s, tolerance_s
    except Exception as exc:
        raise RuntimeError(
            f"storyboard video probe failed for {path}: {exc}"
        ) from exc


def validate_storyboard_segment(
    path: str,
    expected_duration_s: float,
) -> float:
    """Require a video stream whose duration matches the allocated segment.

    The expected duration must be finite and positive.  Returns the measured
    video-stream duration.  A RuntimeError means the caller must reject the
    entire split before registering any segment.
    """
    try:
        normalized_expected_s = float(expected_duration_s)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError(
            "storyboard segment expected duration must be finite and positive"
        ) from exc
    if (
        not math.isfinite(normalized_expected_s)
        or normalized_expected_s <= 0
    ):
        raise RuntimeError(
            "storyboard segment expected duration must be finite and positive"
        )

    actual_duration_s, tolerance_s = _probe_storyboard_video(path)
    if (
        abs(actual_duration_s - normalized_expected_s)
        > tolerance_s + STORYBOARD_SEGMENT_COMPARISON_EPSILON_S
    ):
        raise RuntimeError(
            "storyboard segment duration mismatch for "
            f"{path}: expected={normalized_expected_s:.3f}s "
            f"actual={actual_duration_s:.3f}s "
            f"tolerance={tolerance_s:.3f}s"
        )
    return actual_duration_s


def split_video_into_segments(
    source_path: str,
    durations: list,
    output_dir: str,
    stem: str = "segment",
) -> list:
    """Split a combined video into per-segment mp4s matching the given durations.

    Used by the storyboard integration (F2b) to convert Kling's combined
    storyboard output back into per-shot segments so they can flow through
    the normal per-shot continuity / take-registration / assembly machinery.

    Args:
        source_path: Path to the combined mp4 (e.g. storyboard output).
        durations: Ordered list of finite positive floats, one per desired
            segment (seconds).  The source video must cover their full sum.
        output_dir: Invocation-owned directory in which to write segment
            files.  It is created if absent and must be empty, real, and
            non-symlink at entry.
        stem: One canonical ASCII filename-component prefix for segment files,
            at most 128 characters.  Final names are
            ``{stem}_000.mp4``, ``{stem}_001.mp4``, etc.

    Returns:
        List of absolute paths to the written segment files, in order.
        Returns an empty list if ``source_path`` does not exist or
        ``durations`` is empty.

    Raises:
        RuntimeError: If the source is too short, lacks a video stream, any
            ffmpeg subprocess fails, or an output lacks the expected video
            stream/duration; also if durations, stem, or output ownership are
            invalid.  Every returned path must remain lexically and
            realpath-contained by ``output_dir``.  Deterministic output paths
            are removed before the exception escapes.

    Notes:
        - Seeks after opening the input and re-encodes each segment.  This is
          slower than stream-copy but makes non-keyframe boundaries accurate.
        - Segments shorter than 1 s are written as-is (the caller — i.e.,
          the storyboard API — already enforces 1 s minimum per shot during
          duration allocation).
        - Every segment, including the last, has an explicit ``-t`` duration;
          provider tail frames outside the allocated timeline are ignored.
    """
    from urllib.parse import unquote

    if (
        not isinstance(stem, str)
        or not stem
        or len(stem) > STORYBOARD_SEGMENT_STEM_MAX_LENGTH
    ):
        raise RuntimeError(
            "split_video_into_segments: stem must be one safe filename "
            "component"
        )
    decoded_stem = stem
    for decode_pass in range(STORYBOARD_SEGMENT_STEM_MAX_DECODE_PASSES + 1):
        try:
            next_decoded_stem = unquote(decoded_stem, errors="strict")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                "split_video_into_segments: stem must be one safe filename "
                "component"
            ) from exc
        if next_decoded_stem == decoded_stem:
            break
        if (
            decode_pass == STORYBOARD_SEGMENT_STEM_MAX_DECODE_PASSES
            or len(next_decoded_stem) > STORYBOARD_SEGMENT_STEM_MAX_LENGTH
        ):
            raise RuntimeError(
                "split_video_into_segments: stem must be one safe filename "
                "component"
            )
        decoded_stem = next_decoded_stem
    if (
        not decoded_stem
        or len(decoded_stem) > STORYBOARD_SEGMENT_STEM_MAX_LENGTH
        or not decoded_stem[0].isascii()
        or not decoded_stem[0].isalnum()
        or decoded_stem.endswith(".")
        or any(
            not char.isascii()
            or not (char.isalnum() or char in "._-")
            for char in decoded_stem
        )
    ):
        raise RuntimeError(
            "split_video_into_segments: stem must be one safe filename "
            "component"
        )

    if not source_path or not os.path.exists(source_path):
        logger.warning("split_video_into_segments: source not found", extra={"source_path": source_path})
        return []
    if not durations:
        logger.warning("split_video_into_segments: empty durations list")
        return []

    normalized_durations = []
    for idx, raw_duration in enumerate(durations):
        try:
            duration_s = float(raw_duration)
        except (TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError(
                f"split_video_into_segments: invalid duration at index {idx}"
            ) from exc
        if not math.isfinite(duration_s) or duration_s <= 0:
            raise RuntimeError(
                f"split_video_into_segments: invalid duration at index {idx}"
            )
        normalized_durations.append(duration_s)

    # Resolve every deterministic output and prove both lexical and realpath
    # containment before source probing, directory creation, subprocesses, or
    # writes.  The later ownership check still rejects a final symlink or
    # non-empty directory after the source-coverage precondition succeeds.
    try:
        owned_output_dir = os.path.abspath(os.fspath(output_dir))
        real_output_dir = os.path.realpath(owned_output_dir)
        segment_paths = []
        for idx in range(len(normalized_durations)):
            candidate_path = os.path.abspath(
                os.path.join(
                    owned_output_dir,
                    f"{decoded_stem}_{idx:03d}.mp4",
                )
            )
            if (
                os.path.commonpath((owned_output_dir, candidate_path))
                != owned_output_dir
                or os.path.commonpath(
                    (real_output_dir, os.path.realpath(candidate_path))
                )
                != real_output_dir
            ):
                raise RuntimeError(
                    "split_video_into_segments: segment path escaped "
                    "invocation-owned directory"
                )
            segment_paths.append(candidate_path)
    except RuntimeError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "split_video_into_segments: segment path escaped "
            "invocation-owned directory"
        ) from exc

    source_duration_s, source_tolerance_s = _probe_storyboard_video(source_path)
    allocated_duration_s = sum(normalized_durations)
    if (
        source_duration_s
        + source_tolerance_s
        + STORYBOARD_SEGMENT_COMPARISON_EPSILON_S
        < allocated_duration_s
    ):
        raise RuntimeError(
            "split_video_into_segments: source does not cover allocated "
            f"timeline (source={source_duration_s:.3f}s, "
            f"allocated={allocated_duration_s:.3f}s, "
            f"tolerance={source_tolerance_s:.3f}s)"
        )

    os.makedirs(owned_output_dir, exist_ok=True)
    output_stat = os.stat(owned_output_dir, follow_symlinks=False)
    if not stat.S_ISDIR(output_stat.st_mode):
        raise RuntimeError(
            "split_video_into_segments: output_dir must be a real "
            "invocation-owned directory"
        )
    if os.listdir(owned_output_dir):
        raise RuntimeError(
            "split_video_into_segments: output_dir must be empty and "
            "invocation-owned"
        )

    start = 0.0

    try:
        for idx, (dur, out_path) in enumerate(
            zip(normalized_durations, segment_paths)
        ):
            cmd = [
                "ffmpeg", "-y",
                "-i", source_path,
                # Output-side seek decodes through the requested timestamp,
                # avoiding the keyframe drift of input-side -ss + stream-copy.
                "-ss", f"{start:.6f}",
                "-t", f"{dur:.6f}",
                "-map", "0:v:0",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-c:a", "aac",
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                out_path,
            ]
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            validate_storyboard_segment(out_path, dur)
            logger.debug(
                "split_video_into_segments: segment written",
                extra={"segment_idx": idx, "start_s": round(start, 3), "dur_s": round(dur, 3), "out_path": out_path},
            )
            start += dur
    except subprocess.CalledProcessError as exc:
        stderr_value = exc.stderr or b""
        stderr_text = (
            stderr_value.decode(errors="replace")
            if isinstance(stderr_value, bytes)
            else str(stderr_value)
        )
        raise RuntimeError(
            f"split_video_into_segments: ffmpeg failed on segment {idx} "
            f"(start={start:.3f}s, dur={dur:.3f}s): {stderr_text}"
        ) from exc
    finally:
        if sys.exc_info()[0] is not None:
            # These exact names are the only files this invocation is allowed
            # to own.  Never follow or remove a path returned by another layer.
            for out_path in segment_paths:
                try:
                    os.unlink(out_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    logger.warning(
                        "split_video_into_segments: failed to clean rejected output",
                        extra={"path": out_path},
                        exc_info=True,
                    )

    return segment_paths


# ---------------------------------------------------------------------------
# Motion Quality Assessment (Component C)
# ---------------------------------------------------------------------------

def assess_motion_quality(video_path: str, num_samples: int = 10) -> dict:
    """
    Assess video motion quality using optical flow analysis.
    Detects: frame freezing, jitter, warping artifacts.

    Returns:
        {
            "smoothness_score": 0-1 (higher = smoother motion),
            "artifact_frames": [int] (frame indices with issues),
            "frozen_ratio": 0-1 (fraction of near-identical frames),
            "recommendation": "accept" | "interpolate" | "regenerate",
        }
    """
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames < 2:
        cap.release()
        return {
            "smoothness_score": 0.0,
            "artifact_frames": [],
            "frozen_ratio": 1.0,
            "recommendation": "regenerate",
        }

    # Sample frames uniformly
    step = max(1, total_frames // num_samples)
    positions = [i * step for i in range(num_samples) if i * step < total_frames]

    prev_gray = None
    flow_magnitudes = []
    flow_variances = []
    frozen_count = 0
    artifact_frames = []

    for pos in positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = cap.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 180))  # Downsample for speed

        if prev_gray is not None:
            # Farneback optical flow
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, gray, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
            )
            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            mean_mag = float(np.mean(mag))
            var_mag = float(np.var(mag))

            flow_magnitudes.append(mean_mag)
            flow_variances.append(var_mag)

            # Frozen frame detection
            if mean_mag < 0.3:
                frozen_count += 1

            # Artifact detection: extreme flow gradient = warping
            if var_mag > 50.0 or mean_mag > 30.0:
                artifact_frames.append(pos)

        prev_gray = gray

    cap.release()

    if not flow_magnitudes:
        return {
            "smoothness_score": 0.0,
            "artifact_frames": [],
            "frozen_ratio": 1.0,
            "recommendation": "regenerate",
        }

    pairs = len(flow_magnitudes)
    frozen_ratio = frozen_count / pairs if pairs > 0 else 0.0

    # Smoothness = inverse of flow variance (normalized)
    avg_variance = sum(flow_variances) / len(flow_variances)
    smoothness = max(0.0, min(1.0, 1.0 - (avg_variance / 50.0)))

    # Decision
    if frozen_ratio > 0.5:
        recommendation = "regenerate"
    elif len(artifact_frames) > pairs * 0.3:
        recommendation = "regenerate"
    elif smoothness < 0.4:
        recommendation = "interpolate"
    elif frozen_ratio > 0.2:
        recommendation = "interpolate"
    else:
        recommendation = "accept"

    return {
        "smoothness_score": round(smoothness, 3),
        "artifact_frames": artifact_frames,
        "frozen_ratio": round(frozen_ratio, 3),
        "recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# Color Grading & Speed Adjust (Director's Cut tools)
# ---------------------------------------------------------------------------

# Built-in LUT presets mapped to FFmpeg eq/curves filters
COLOR_GRADE_PRESETS = {
    "warm_cinema": "eq=brightness=0.02:contrast=1.1:saturation=1.15,colorbalance=rs=0.05:gs=-0.02:bs=-0.05:rh=0.03",
    "cool_noir": "eq=brightness=-0.03:contrast=1.2:saturation=0.7,colorbalance=rs=-0.05:gs=-0.02:bs=0.08",
    "vibrant": "eq=brightness=0.03:contrast=1.05:saturation=1.4",
    "desaturated": "eq=saturation=0.5:contrast=1.1",
    "golden_hour": "eq=brightness=0.04:saturation=1.2,colorbalance=rs=0.08:gs=0.03:bs=-0.06:rh=0.05:gh=0.02",
    "moonlight": "eq=brightness=-0.05:contrast=1.15:saturation=0.6,colorbalance=rs=-0.03:gs=-0.01:bs=0.1",
    "high_contrast": "eq=contrast=1.4:brightness=-0.02:saturation=0.9",
    "pastel": "eq=brightness=0.06:contrast=0.9:saturation=0.8",
}


def apply_color_grade(video_path: str, output_path: str, preset: str = "warm_cinema", lut_path: str = None) -> str:
    """
    Apply color grading to a video clip.
    Uses either a preset filter chain or a custom LUT file.

    Args:
        video_path: Input video
        output_path: Output graded video
        preset: One of COLOR_GRADE_PRESETS keys
        lut_path: Optional path to .cube/.3dl LUT file (overrides preset)

    Returns:
        Output path on success, None on failure
    """
    if not os.path.exists(video_path):
        return None

    if lut_path and os.path.exists(lut_path):
        vf = f"lut3d={lut_path}"
    else:
        vf = COLOR_GRADE_PRESETS.get(preset, COLOR_GRADE_PRESETS["warm_cinema"])

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        logger.info("Color graded", extra={"preset": preset, "output_path": output_path})
        return output_path
    except Exception as e:
        logger.warning("Color grading failed", extra={"preset": preset, "error": str(e)})
        return None


def adjust_speed(video_path: str, output_path: str, factor: float = 1.0) -> str:
    """
    Adjust video speed using FFmpeg setpts filter.

    Args:
        video_path: Input video
        output_path: Output adjusted video
        factor: Speed multiplier (0.5 = half speed / slow-mo, 2.0 = double speed)

    Returns:
        Output path on success, None on failure
    """
    if not os.path.exists(video_path) or factor <= 0:
        return None

    pts_factor = 1.0 / factor  # setpts is inverse: PTS*0.5 = 2x speed
    atempo = factor  # Audio tempo adjustment

    # FFmpeg atempo only supports 0.5-2.0, chain for extreme values
    atempo_chain = []
    remaining = atempo
    while remaining > 2.0:
        atempo_chain.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        atempo_chain.append("atempo=0.5")
        remaining /= 0.5
    atempo_chain.append(f"atempo={remaining:.4f}")

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-filter:v", f"setpts={pts_factor:.4f}*PTS",
        "-filter:a", ",".join(atempo_chain),
        "-c:v", "libx264", "-preset", "fast",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        logger.info("Speed adjusted", extra={"speed_factor": factor, "output_path": output_path})
        return output_path
    except Exception as e:
        logger.warning("Speed adjustment failed", extra={"speed_factor": factor, "error": str(e)})
        return None


def measure_loudness(path: str, target_i: float = -14.0, target_lra: float = 11.0,
                     target_tp: float = -1.5) -> "dict | None":
    """Pass-1 EBU R128 loudness measurement via ffmpeg loudnorm print_format=json.

    Runs ffmpeg in measurement-only mode (no output file) and parses the JSON
    blob that loudnorm prints to stderr. Returns the parsed dict on success
    (contains at minimum: input_i, input_tp, input_lra, input_thresh,
    target_offset), or None on any failure (missing file, timeout, no JSON,
    missing required keys).

    Extracted from two_pass_loudnorm pass-1 (U3 — Final-media conformance).
    two_pass_loudnorm calls this internally; behavior is identical.
    """
    import re

    if not os.path.exists(path):
        return None

    measure_cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-y",
        "-i", path,
        "-af", f"loudnorm=I={target_i}:LRA={target_lra}:TP={target_tp}:print_format=json",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(measure_cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        logger.warning("Loudness measurement pass timed out")
        return None

    stderr = result.stderr or ""
    # ffmpeg prints the loudnorm JSON near the end of stderr; grab the last
    # {...} block that contains "input_i". Non-greedy + DOTALL.
    matches = re.findall(r'\{[^{}]*?"input_i"[^{}]*?\}', stderr, flags=re.DOTALL)
    if not matches:
        logger.warning("No measurement JSON in ffmpeg loudnorm output")
        return None

    try:
        measured = json.loads(matches[-1])
        required = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
        if not all(k in measured for k in required):
            logger.warning(
                "Loudness measurement JSON missing keys",
                extra={"missing_keys": list(set(required) - set(measured))},
            )
            return None
        return measured
    except json.JSONDecodeError as e:
        logger.warning("Loudness measurement JSON parse failed", extra={"error": str(e)})
        return None


def two_pass_loudnorm(
    input_video_path: str,
    output_video_path: str,
    target_i: float = -14.0,
    target_lra: float = 11.0,
    target_tp: float = -1.5,
) -> bool:
    """Re-normalize a finished video with two-pass EBU R128 loudnorm.

    The first pass measures actual integrated loudness, true peak, and
    loudness range; the second pass feeds those measurements back into
    loudnorm so it normalizes precisely instead of approximating in a
    single pass. The result is ±0.1 LU of target instead of ±1.5 LU.

    The video stream is copied (no re-encode), only audio is re-encoded.

    Defaults: -14 LUFS / 11 LU / -1.5 dBTP — YouTube/Netflix standard.

    Returns True if output_video_path was written, False on any failure
    (caller should keep the original input on False).
    """
    if not os.path.exists(input_video_path):
        return False

    # ---- Pass 1: measure (delegated to measure_loudness) ----
    measured = measure_loudness(input_video_path, target_i=target_i,
                                target_lra=target_lra, target_tp=target_tp)
    if measured is None:
        logger.warning("Loudnorm measurement failed — skipping 2nd pass")
        return False

    # ---- Pass 2: normalize with measured values ----
    af = (
        f"loudnorm=I={target_i}:LRA={target_lra}:TP={target_tp}:"
        f"measured_I={measured['input_i']}:"
        f"measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:"
        f"linear=true:print_format=summary"
    )
    norm_cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-y",
        "-i", input_video_path,
        "-af", af,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        output_video_path,
    ]
    try:
        norm = subprocess.run(norm_cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        logger.warning("Loudnorm normalization pass timed out")
        return False

    if norm.returncode != 0 or not os.path.exists(output_video_path):
        # Surface the tail of ffmpeg's error so failures are diagnosable
        tail = (norm.stderr or "").strip().splitlines()[-3:]
        logger.error(
            "Loudnorm normalization pass failed",
            extra={"stderr_tail": " | ".join(tail)},
        )
        return False

    logger.info(
        "Two-pass loudnorm complete",
        extra={"measured_i_lufs": measured["input_i"], "target_i_lufs": target_i},
    )
    return True


def _accept_or_reject(path: str, aspect_ratio) -> bool:
    """Post-generation aspect backstop. Return True to ACCEPT the clip, False to reject (→ cascade).

    No-op (always True) when the project is landscape — preserves byte-identical 16:9 behavior.
    For portrait, probe the clip's real dimensions and accept only if its orientation matches.
    On probe failure (file missing / ffprobe error / no dims) ACCEPT with a warning — do NOT
    strand the pipeline on a flaky probe (the filter is the primary defense; this is the net).

    Caller contract: `path` MUST be the file the provider actually wrote. Cascade callers pass
    `output_mp4` (the uniform local artifact): the 7 download branches write it directly, and the
    4 native branches (KLING_NATIVE/SORA_NATIVE/VEO_NATIVE/LTX) pass output_path=output_mp4 and
    return that same path — so probing `output_mp4` is correct today. If a future native provider
    ignores its output_path and writes elsewhere, probe THAT returned path here instead."""
    from cinema.aspect import is_portrait as _is_portrait
    if not _is_portrait(aspect_ratio):
        return True  # landscape project: never reject (no-op)
    probed = probe_final_media(path)
    fmt = (probed or {}).get("format") or {}
    w, h = fmt.get("width"), fmt.get("height")
    if not w or not h:
        logger.warning(
            "Aspect backstop: could not probe dims — accepting (probe unavailable)",
            extra={"path": path},
        )
        return True
    return (h > w) == _is_portrait(aspect_ratio)  # portrait file iff portrait project


def probe_final_media(path: str) -> "dict | None":
    """Probe a finished mp4 for format/codec conformance and integrated loudness.

    Runs ffprobe (streams + format JSON) and measure_loudness in sequence.
    Returns a dict with whichever halves succeeded:

        {
          "audio": {"integrated_lufs": float, "true_peak_dbtp": float, "lra": float},
          "format": {"width": int|None, "height": int|None, "vcodec": str|None,
                     "acodec": str|None, "duration_s": float},
        }

    Partial results: if exactly one half succeeds, the dict contains only that
    half. Returns None only when the file is missing or BOTH halves fail.

    Called at assembly-time by cinema_pipeline._apply_final_loudnorm (U3).
    Pure I/O — no mutation, no Flask.
    """
    if not os.path.exists(path):
        return None

    result: dict = {}

    # ---- Format/codec half (ffprobe) ----
    try:
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_streams", "-show_format",
            "-of", "json", path,
        ]
        probe = subprocess.run(probe_cmd, capture_output=True, text=True,
                               timeout=60, check=True)
        probe_data = json.loads(probe.stdout)
        streams = probe_data.get("streams", [])
        fmt = probe_data.get("format", {})

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        result["format"] = {
            "width": video_stream.get("width") if video_stream else None,
            "height": video_stream.get("height") if video_stream else None,
            "vcodec": video_stream.get("codec_name") if video_stream else None,
            "acodec": audio_stream.get("codec_name") if audio_stream else None,
            "duration_s": float(fmt["duration"]) if fmt.get("duration") else None,
        }
    except Exception as e:
        logger.warning("probe_final_media: ffprobe failed", extra={"path": path, "error": str(e)})
        # format half absent — will be omitted from result

    # ---- Loudness half (measure_loudness) ----
    # Defensive: measure_loudness should return None on failure, but guard the
    # call so an unexpected raise (e.g. ffmpeg binary absent) discards only the
    # audio half and preserves the ffprobe half — honoring the partial-results
    # contract (close Lane V F2).
    try:
        measured = measure_loudness(path)
    except Exception as e:
        logger.warning("probe_final_media: loudness measure raised", extra={"path": path, "error": str(e)})
        measured = None
    if measured is not None:
        try:
            result["audio"] = {
                "integrated_lufs": float(measured["input_i"]),
                "true_peak_dbtp": float(measured["input_tp"]),
                "lra": float(measured["input_lra"]),
            }
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("probe_final_media: loudness result parse failed", extra={"error": str(e)})

    if not result:
        return None
    return result


# ---------------------------------------------------------------------------
# Scene-transition helpers (xfade / acrossfade)
# ---------------------------------------------------------------------------

def _probe_duration(path: str) -> float:
    """Return the duration of a media file in seconds via ffprobe."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return float(json.loads(probe.stdout)["format"]["duration"])


def _has_audio_stream(path: str) -> bool:
    """Return True if the media file has at least one audio stream (via ffprobe).

    The default silent-video motion path (Kling-Native image2video, LTX, base
    Veo without audio-drive) produces clips with no audio stream; xfade_concat
    uses this to decide whether an acrossfade chain is valid (Lane V #24 F1).
    """
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "json", path],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return bool(json.loads(probe.stdout).get("streams"))


def _fmt(x: float) -> str:
    """Format a float for an ffmpeg filter arg: strip trailing zeros (8.0 -> '8', 3.5 -> '3.5')."""
    return f"{x:.6f}".rstrip("0").rstrip(".")


def _build_xfade_filtergraph(durations: list, duration: float, transition: str,
                             audio_flags: Optional[list] = None):
    """Build a chained xfade (video) + acrossfade (audio) filter_complex string.

    Returns (filter_complex, final_video_label, final_audio_label).
    Requires len(durations) >= 2. Offset for junction j is
    sum(durations[0..j]) - (j+1)*duration. ``audio_flags`` is a per-input list
    of bools (True = that input has an audio stream); None ≡ all inputs have
    audio:
      - all True  -> raw acrossfade on [j:a]
      - all False -> video-only, audio label None (Lane V #24 F1)
      - mixed     -> normalize every leg + anullsrc-pad the silent legs, then
                     acrossfade, preserving embedded audio (Lane V #25 M1)
    """
    n = len(durations)
    if n < 2:
        raise ValueError("xfade filtergraph requires >= 2 inputs")
    if audio_flags is None:
        audio_flags = [True] * n
    emit_audio = any(audio_flags)
    padded = emit_audio and not all(audio_flags)

    t = _fmt(duration)
    video_parts = []
    prev_v = "0:v"
    cumulative = durations[0]
    for j in range(n - 1):
        offset = cumulative - (j + 1) * duration
        vlabel = f"v{j + 1}"
        video_parts.append(
            f"[{prev_v}][{j + 1}:v]xfade=transition={transition}:"
            f"duration={t}:offset={_fmt(offset)}[{vlabel}]"
        )
        prev_v = vlabel
        cumulative += durations[j + 1]

    if not emit_audio:
        return ";".join(video_parts), f"v{n - 1}", None

    # Audio legs. padded (mixed presence) -> normalize every leg to a canonical
    # format so acrossfade's matching rate/layout/fmt precondition holds across
    # heterogeneous embedded audio + anullsrc silence (Lane V #25 M1). All-audio
    # -> raw [j:a] (unchanged).
    _AFMT = "aformat=sample_fmts=fltp:channel_layouts=stereo"
    leg_parts = []
    if padded:
        audio_src = []
        for j in range(n):
            if audio_flags[j]:
                leg_parts.append(f"[{j}:a]aresample=48000,{_AFMT}[na{j}]")
            else:
                leg_parts.append(
                    f"anullsrc=r=48000:cl=stereo,atrim=0:{_fmt(durations[j])},{_AFMT}[na{j}]"
                )
            audio_src.append(f"na{j}")
    else:
        audio_src = [f"{j}:a" for j in range(n)]

    audio_parts = []
    prev_a = audio_src[0]
    for j in range(n - 1):
        alabel = f"a{j + 1}"
        audio_parts.append(f"[{prev_a}][{audio_src[j + 1]}]acrossfade=d={t}[{alabel}]")
        prev_a = alabel

    filter_complex = ";".join(video_parts + leg_parts + audio_parts)
    return filter_complex, f"v{n - 1}", f"a{n - 1}"


def xfade_concat(scene_videos: list, out_path: str,
                 duration: float = 0.5, transition: str = "dissolve") -> str:
    """Chain per-scene videos with xfade (video) + conditional acrossfade (audio).

    Probes each scene's duration, clamps the transition to fit the shortest
    scene, builds the filtergraph, and re-encodes once to out_path.
    Requires len(scene_videos) >= 2 (caller guarantees). Returns out_path.
    Raises on ffmpeg failure (caller falls back to a plain concat).

    Audio has three cases: all inputs carry audio -> streams are crossfaded
    directly; no input carries audio -> output is video-only (the default
    silent-video motion path, Kling-Native/LTX, has no audio stream, where
    emitting an acrossfade once referenced a non-existent [0:a] and errored ->
    the caller silently hard-cut, Lane V #24 F1); mixed audio-presence -> silent
    legs are anullsrc-padded and every leg normalized so embedded audio is
    preserved across the stitch rather than dropped (Lane V #25 M1). Downstream
    _assemble_final owns the dialogue/BGM/foley mix on every path.
    """
    durations = [_probe_duration(v) for v in scene_videos]
    audio_flags = [_has_audio_stream(v) for v in scene_videos]
    # Mixed audio-presence (some inputs carry an embedded audio stream, some don't):
    # silent inputs are padded with anullsrc and every leg is normalized to a canonical
    # format, so acrossfade runs uniformly and embedded audio is preserved across the
    # stitch rather than dropped (Lane V #25 M1, fixed 2026-05-29). The downstream
    # _assemble_final dialogue mux is unaffected — it selects its voice source on
    # standalone-dialogue-mp3 existence, not on whether this stitch carries audio.
    t_eff = min(duration, 0.4 * min(durations))
    filter_complex, vlab, alab = _build_xfade_filtergraph(
        durations, t_eff, transition, audio_flags=audio_flags)

    cmd = ["ffmpeg", "-y"]
    for v in scene_videos:
        cmd += ["-i", v]
    cmd += ["-filter_complex", filter_complex, "-map", f"[{vlab}]"]
    if alab is not None:
        cmd += ["-map", f"[{alab}]"]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20"]
    if alab is not None:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += [out_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "xfade_concat ffmpeg failed",
            extra={"stderr_tail": exc.stderr.decode(errors="replace")[-200:] if exc.stderr else str(exc)},
        )
        raise
    return out_path


_RUNWAY_IMAGE_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _runway_image_data_uri(image_path: str) -> str:
    """Return a content-validated JPEG, PNG, or WebP Runway data URI."""

    import base64
    from pathlib import Path

    path = Path(image_path)
    expected_mime = _RUNWAY_IMAGE_MIME_BY_SUFFIX.get(path.suffix.lower())
    if expected_mime is None:
        raise ValueError(
            "Runway input must use a .jpg, .jpeg, .png, or .webp suffix"
        )

    payload = path.read_bytes()
    if payload.startswith(b"\xff\xd8\xff"):
        detected_mime = "image/jpeg"
    elif payload.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_mime = "image/png"
    elif (
        len(payload) >= 12
        and payload.startswith(b"RIFF")
        and payload[8:12] == b"WEBP"
    ):
        detected_mime = "image/webp"
    else:
        raise ValueError("Runway input is not a supported JPEG, PNG, or WebP image")

    if detected_mime != expected_mime:
        raise ValueError(
            "Runway input suffix/content mismatch: "
            f"{path.suffix.lower()} declares {expected_mime}, bytes are {detected_mime}"
        )

    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{detected_mime};base64,{encoded}"
