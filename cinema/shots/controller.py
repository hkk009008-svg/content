"""ShotController -- per-shot generation + correction state machine.

Standalone-controllers Slice 2 (from REFACTOR_HANDOFF.md section 9.1).
Replaces the prior ShotControllerMixin (Slice B) with a composable class
that takes PipelineCore + LifecycleService + a ShotControllerHost
protocol directly.

Architectural seam
==================

ShotController is constructable independently of
``cinema_pipeline.CinemaPipeline``. This unblocks the planned Slice 3
(web_server caching) goal of per-request controller construction
sharing a cached PipelineCore across endpoints.

Cross-controller dependencies (refresh_project_snapshot,
save_checkpoint, candidate_take, ...) are declared as a Protocol
(``ShotControllerHost``) and injected via the constructor.
CinemaPipeline implements the protocol via its remaining mixins
(``ReviewControllerMixin``, ``CheckpointStoreMixin``) and passes
``self`` as the host. A future slice could decouple these further by
making Review and Checkpoint standalone too; for now the host keeps
the call graph honest while still allowing isolated testing of
ShotController (with a stub host).

Runtime state ownership
=======================

ShotController owns ``shot_results`` (per-shot output dict, the only
runtime-state field where shot methods are the primary writers). The
remaining run-state fields stay on the orchestrator because they're
written from the generate() loop more often than from shot methods:

  scene_clips         -- shared (orchestrator's _build_scene_packages
                         writes; generate_scene_preview reads/writes).
                         Accessed via host.
  scene_audio         -- audio-phase state.
  failed_shots        -- orchestrator-only writes.
  current_stage |
  current_scene_id |
  current_shot_id     -- progress pointer. Updated via
                         host.update_progress_pointer(stage, scene_id, shot_id)
                         which writes the trio atomically.
  _completed_scene_indices -- checkpoint internal.

Body-rewrite policy
===================

Method bodies are preserved verbatim from the prior mixin with these
mechanical substitutions:

  self._refresh_project_snapshot()   -> self._host._refresh_project_snapshot()
  self._rebuild_review_clips()       -> self._host._rebuild_review_clips()
  self._save_checkpoint()            -> self._host._save_checkpoint()
  self._resolve_take_path(...)       -> self._host._resolve_take_path(...)
  self._candidate_take(...)          -> self._host._candidate_take(...)
  self._latest_take(...)             -> self._host._latest_take(...)
  self._ensure_scene_audio(...)      -> self._host._ensure_scene_audio(...)
  self.current_stage = "X"           -> self._host.update_progress_pointer("X", scene_id, shot_id)
  self.current_scene_id = ...        -- absorbed into update_progress_pointer
  self.current_shot_id = ...         -- absorbed into update_progress_pointer
  self.scene_clips                   -> self._host.scene_clips
  self.export_dir                    -> self._core.export_dir
  self.project                       -- preserved (proxies to self._core.project)
  self.project_dir                   -- preserved (proxies to self._core.project_dir)
  self.continuity                    -- preserved (proxies to self._core.continuity)
  self.progress(...)                 -- preserved (proxies to self._lifecycle.report_progress)

Note on previously-latent imports: ``time``, ``get_reference_image``,
``face_swap_video_frames``, ``generate_lip_sync_video``,
``generate_rife_interpolation``, ``upscale_video_seedvr2``, and
``stitch_modules`` were referenced bare in method bodies but missing
from the module-level imports through Slice 2. They've been added in
Phase 0 of the V1-close-out track so the rare ``apply_correction`` /
``diagnose_clip`` / ``generate_scene_preview`` code paths no longer
crash on import-time NameError when they execute.
"""

from __future__ import annotations

import logging
import math
import os
import stat
import tempfile
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, TYPE_CHECKING, Optional, Protocol, runtime_checkable

from project_manager import MutationResult, mutate_project, make_take
from llm.style_director import style_rules_to_prompt_suffix
from character_manager import get_reference_image
from cinema.context import PipelineContext, _finite_or
from config.settings import settings as env_settings
from phase_c_assembly import generate_ai_broll
from phase_c_ffmpeg import generate_ai_video, stitch_modules, _probe_duration
from phase_c_vision import face_swap_video_frames
from lip_sync import (
    generate_lip_sync_video,
    generate_rife_interpolation,
    upscale_video_seedvr2,
)
from audio.dialogue import scene_characters as _scene_characters, shot_characters as _shot_characters
from domain.optimizer_cache import (
    sanitize_optimizer_cache,
    sanitize_optimizer_spec,
)
from domain.provider_catalog import RuntimeSnapshot
from domain.reference_set import compose_shot_reference_set
from domain.video_engine_policy import (
    VideoCandidateResult,
    build_runtime_snapshot,
    filter_automatic_dispatch_candidates,
    filter_dispatch_candidates,
)


def _directorial_iteration_enabled() -> bool:
    """Feature flag: CINEMA_DIRECTORIAL_ITERATION controls S16+ iteration endpoints.

    Default ON as of v5.1+ flag-flip (2026-05-26 user-principal authorization;
    operator + director joint flag-flip-recommended per Val#1 V4 LIVE 7/7 +
    Val#1 V8 verb-routing + Val#2 U6 render conditions). Set
    ``CINEMA_DIRECTORIAL_ITERATION=0|false|no`` to opt out (e.g., a
    deployment that needs the pre-S16 endpoint behavior).

    Read at each call so dynamic env mutation is observable without restart.
    """
    return os.environ.get("CINEMA_DIRECTORIAL_ITERATION", "").strip().lower() not in {
        "0", "false", "no",
    }


_VALID_DIALOGUE_VOICE_MODES = {"overlay", "native"}


def _video_policy_runtime_snapshot() -> RuntimeSnapshot:
    """Build the dispatch snapshot at the controller's pre-spend boundary."""

    return build_runtime_snapshot()


def _video_policy_current_date() -> date:
    """UTC policy date, kept as a seam for deterministic boundary tests."""

    return datetime.now(timezone.utc).date()


def _policy_rejections(result: VideoCandidateResult) -> list[dict[str, str]]:
    """Return stable, JSON-safe rejection evidence in seed order."""

    return [
        {"key": rejection.key, "reason": rejection.reason.value}
        for rejection in result.rejections
    ]


def _target_policy_failure(
    target_api: object,
    result: VideoCandidateResult,
) -> dict:
    """Build the stable fail-closed response for an unavailable shot target."""

    requested = target_api if isinstance(target_api, str) else ""
    reason = next(
        (
            rejection.reason.value
            for rejection in result.rejections
            if requested != "AUTO" and rejection.key == requested
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
        "success": False,
        "error": "Target video engine is unavailable",
        "error_kind": "target_api_policy",
        "code": "target_api_unavailable",
        "target_api": requested,
        "reason": reason,
        "retryable": False,
        "rejections": _policy_rejections(result),
    }


def _dialogue_voice_mode(settings: dict) -> str:
    """Resolve the dialogue voice mode from global_settings (default 'overlay').

    'overlay' = silent provider video + our TTS lip-sync overlay.
    'native'  = request provider-native voice; unsupported backends still use F1b.

    Mirror of settings.get("lip_sync_mode","auto") at controller.py:1256.
    Unknown values fall back to 'overlay' (typo guard).
    """
    mode = (settings or {}).get("dialogue_voice_mode", "overlay")
    return mode if mode in _VALID_DIALOGUE_VOICE_MODES else "overlay"


def _resolve_dialogue_routing(
    purpose: str,
    voice_mode: str,
    resolved_target_api: str,
    resolved_fallbacks,
):
    """Return (target_api, video_fallbacks) after applying the dialogue routing override.

    Pure helper — mirrors the inline block at generate_motion_take:1144-1173.

    For dialogue shots (has_dialogue=True callers), walks PURPOSE_API_RANKING for the
    given purpose to find the first live video engine with native_audio.  Then:
    - overlay mode: sets target_api to that engine; keeps resolved_fallbacks intact so
      a provider rejection can cascade to a silent engine (F1b overlay still fires).
    - native mode:  sets target_api to that engine AND nulls fallbacks so the
      native-audio engine's internal cascade never routes to a non-native-audio engine.

    If no native_audio video engine is found in the ranking, returns the inputs
    unchanged (F1b lipsync pass covers the gap).

    Args:
        purpose: The cached optimizer purpose (e.g. 'dialogue_close_up').
        voice_mode: The resolved voice mode string ('overlay' or 'native').
        resolved_target_api: The engine already resolved from the optimizer/template.
        resolved_fallbacks: The fallback list already resolved from the template.

    Returns:
        (target_api, video_fallbacks) — potentially overridden.
    """
    from domain.scene_decomposer import PURPOSE_API_RANKING, API_REGISTRY

    target_api = resolved_target_api
    video_fallbacks = resolved_fallbacks

    for _engine_key in PURPOSE_API_RANKING.get(purpose, []):
        _engine_info = API_REGISTRY.get(_engine_key, {})
        if (
            _engine_info.get("native_audio")
            and _engine_info.get("modality") == "video"
            and _engine_info.get("status") == "live"
        ):
            target_api = _engine_key
            if voice_mode == "native":
                video_fallbacks = None
            # overlay mode: video_fallbacks intentionally kept from template
            break
    # If no native_audio engine found: return inputs unchanged.
    return target_api, video_fallbacks


def _should_tag_audio_embedded(
    engine_info: dict,
    has_dialogue: bool,
    voice_mode: str,
    native_audio_generated: Optional[bool] = None,
) -> bool:
    """Return True when the winning engine's take should be tagged audio_embedded.

    Pure helper — mirrors the inline if-expression at generate_motion_take:1251-1253.

    audio_embedded is True only when ALL four conditions hold:
    - The winning engine has native_audio=True in API_REGISTRY.
    - The shot has dialogue (has_dialogue=True).
    - The voice mode is 'native' (overlay mode intentionally skips the tag so
      the F1b TTS overlay pass runs).
    - A backend-specific capability result did not explicitly report that
      native audio was unavailable (Developer-API Veo reports False).

    Args:
        engine_info: API_REGISTRY entry for the winning engine (may be {}).
        has_dialogue: True when the shot purpose is a dialogue purpose.
        voice_mode: The resolved voice mode string ('overlay' or 'native').
        native_audio_generated: Backend evidence when available. False blocks
            the tag; None preserves capability-registry behavior for providers
            whose audio contract is not surfaced as a structured result.

    Returns:
        bool
    """
    return bool(
        native_audio_generated is not False
        and engine_info.get("native_audio")
        and has_dialogue
        and voice_mode == "native"
    )


def _lipsync_cost_api_key(engine: object) -> str:
    """Return the CostTracker API key for a lip-sync cascade engine."""
    raw = str(engine or "default").strip() or "default"
    if raw.upper().startswith("LIPSYNC_"):
        return raw
    return f"LIPSYNC_{raw}"


def _record_rejected_lipsync_candidate(
    *,
    project: Mapping[str, Any],
    project_root: str,
    shot_id: str,
    candidate_id: str,
    source_take_id: str,
    evidence: Mapping[str, Any],
    audio_path: str,
    character_reference_path: str,
    input_video_path: str,
    mode: str,
) -> dict:
    """Copy one paid, locally rejected lip-sync output into artifact history."""

    candidate_path = evidence.get("path")
    if not isinstance(candidate_path, str) or not candidate_path:
        raise RuntimeError("rejected lip-sync candidate has no output path")
    paid_attempt = evidence.get("paid_attempt")
    attempt = dict(paid_attempt) if isinstance(paid_attempt, Mapping) else {}
    cascade_metadata = {
        "engine": evidence.get("engine"),
        "provider": evidence.get("provider"),
        "model": evidence.get("model"),
        "score": evidence.get("score"),
        "validation_state": evidence.get("validation_state"),
        "threshold": evidence.get("threshold"),
        "rejection_stage": evidence.get("rejection_stage"),
        "aspect_ratio": evidence.get("aspect_ratio"),
        "attempt_id": evidence.get("attempt_id") or attempt.get("attempt_id"),
        "provider_job_id": (
            evidence.get("provider_job_id") or attempt.get("provider_job_id")
        ),
        "request_fingerprint": (
            evidence.get("request_fingerprint")
            or attempt.get("request_fingerprint")
        ),
        "provider_status": (
            evidence.get("provider_status") or attempt.get("provider_status")
        ),
        "attempt_state": evidence.get("attempt_state") or attempt.get("state"),
    }
    rejected_take = make_take(
        "postprocess",
        path=candidate_path,
        source_take_id=source_take_id,
        status="rejected",
        metadata={
            "action": "lip_sync",
            "mode": mode,
            "threshold": evidence.get("threshold"),
            "rejection_stage": evidence.get("rejection_stage"),
            "lipsync_score": evidence.get("score"),
            "lipsync_validation_state": evidence.get("validation_state"),
            "audio_path": audio_path,
            "character_reference_path": character_reference_path,
            "lipsync_input_video_path": input_video_path,
        },
    )
    rejected_take["id"] = candidate_id
    rejected_take["cascade_metadata"] = cascade_metadata

    from cinema.artifact_indexing import record_take_version

    return record_take_version(
        str(project.get("id") or ""),
        shot_id,
        "postprocess",
        rejected_take,
        project_snapshot=project,
        project_root=project_root,
    )


def _inherit_audio_flags_from_base(base_take: Optional[dict], variant: dict) -> None:
    """Propagate a base take's audio-embedding flags onto a postprocess variant
    when the variant's output clip actually carries an audio stream.

    Postprocess corrections (apply_correction) mint a variant with no audio-flag
    slot. PRESERVE transforms (rife/color_grade/speed) and successfully re-muxed
    STRIP transforms (upscale/face_swap) carry the source audio through — but
    without ``audio_embedded`` / ``dialogue_audio_in_clip`` the assembler
    (_build_scene_packages) treats the variant as audio-less, generates standalone
    scene-TTS, and the final mux drops the clip's embedded ``[0:a]`` — REPLACING
    the take's real voice with generic TTS (a voice-loss regression).

    Gating on an actual audio stream (``_has_audio_stream``) keeps a failed-remux /
    video-only STRIP variant correctly UNFLAGGED (TTS fills — degraded, not a silent
    clip falsely claiming embedded audio). lip_sync GENERATES fresh dialogue and is
    flagged directly in its branch (a silent base has no flag to inherit), not here.
    [§3 audio-sibling family]
    """
    if not base_take or not isinstance(variant, dict):
        return
    path = variant.get("path")
    if not path:
        return
    try:
        from phase_c_ffmpeg import _has_audio_stream
        if not _has_audio_stream(path):
            return
    except Exception:
        logger.warning(
            "audio flag inheritance skipped; could not confirm variant audio stream",
            exc_info=True,
            extra={"variant_path": path},
        )
        return
    base_meta = base_take.get("metadata") or {}
    variant.setdefault("metadata", {})
    if base_meta.get("audio_embedded"):
        variant["metadata"]["audio_embedded"] = True
    if base_meta.get("dialogue_audio_in_clip"):
        variant["metadata"]["dialogue_audio_in_clip"] = True


# Supported Veo clip durations (ascending).  The clamp picks the smallest
# value >= speech_seconds; values beyond the maximum are capped to "8s".
_VEO_SUPPORTED_DURATIONS = ("4s", "6s", "8s")
_VEO_DURATION_SECONDS = {d: float(d[:-1]) for d in _VEO_SUPPORTED_DURATIONS}

# The production LivePortrait graph runs at 25 fps.  Eight seconds is the
# reviewed per-shot envelope for the local worker: at most 200 frames enter
# the GPU batch even when a scene allocation or uploaded reference is longer.
# Keep the UI's displayed cap synchronized with this backend authority.
MAX_PERFORMANCE_TAKE_DURATION_S = 8.0
DEFAULT_PERFORMANCE_TAKE_DURATION_S = 5.0


def performance_take_duration_details(
    scene: Mapping[str, Any],
) -> tuple[float, float, int]:
    """Return ``(bounded, scene duration, shot count)`` after one validation.

    Scene duration is an aggregate.  The edit UI presents a per-shot
    allocation, so dispatch must divide by the real shot count before applying
    the production cap.  Invalid persisted values fail before provider access
    instead of expanding into an unbounded frame request.
    """

    raw_duration = scene.get("duration_seconds", DEFAULT_PERFORMANCE_TAKE_DURATION_S)
    try:
        scene_duration = float(raw_duration)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Scene duration is invalid for performance capture") from exc
    if not math.isfinite(scene_duration) or scene_duration <= 0:
        raise ValueError(
            "Scene duration must be finite and greater than zero for performance capture"
        )

    shots = scene.get("shots")
    if isinstance(shots, list) and shots:
        shot_count = len(shots)
    else:
        raw_count = scene.get("num_shots", 1)
        if isinstance(raw_count, bool):
            raise ValueError("Scene shot count is invalid for performance capture")
        try:
            shot_count = int(raw_count)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Scene shot count is invalid for performance capture") from exc
        if shot_count <= 0:
            raise ValueError("Scene shot count must be greater than zero")

    return (
        min(scene_duration / shot_count, MAX_PERFORMANCE_TAKE_DURATION_S),
        scene_duration,
        shot_count,
    )


def performance_take_duration_s(scene: Mapping[str, Any]) -> float:
    """Return the authoritative bounded duration for one performance take."""

    return performance_take_duration_details(scene)[0]


_PERFORMANCE_REQUEST_ACTIVE_STATES = frozenset({
    "preparing",
    "dispatching",
    "deferred",
})


class PerformancePaidAttemptAuthorityError(RuntimeError):
    """The production all-provider paid-attempt snapshot is unavailable."""


def _performance_paid_attempts(
    cost_tracker: Any,
    *,
    video_id: str,
    shot_id: str,
) -> Optional[list[dict[str, Any]]]:
    """Return every durable performance attempt for a shot, or ``None``.

    Skip and admission authority must not be scoped to the currently routed
    provider: a route change cannot make an older accepted job disappear.
    """

    snapshot = getattr(cost_tracker, "get_paid_attempts_snapshot", None)
    if not callable(snapshot):
        return None
    declared_authority = callable(
        getattr(type(cost_tracker), "get_paid_attempts_snapshot", None)
    )
    try:
        value = snapshot(video_id)
    except Exception as exc:
        logger.warning(
            "Performance paid-attempt snapshot failed",
            exc_info=True,
            extra={"video_id": video_id, "shot_id": shot_id},
        )
        if declared_authority:
            raise PerformancePaidAttemptAuthorityError(
                "Performance paid-work authority could not be read"
            ) from exc
        # Narrow compatibility for legacy fake trackers that do not declare
        # snapshot authority on their type. Production CostTracker does.
        return None
    if not isinstance(value, Mapping) or not isinstance(value.get("attempts"), list):
        if declared_authority:
            raise PerformancePaidAttemptAuthorityError(
                "Performance paid-work authority returned an invalid snapshot"
            )
        return None
    return [
        dict(attempt)
        for attempt in value["attempts"]
        if isinstance(attempt, Mapping)
        and str(attempt.get("video_id") or "") == video_id
        and str(attempt.get("shot_id") or "") == shot_id
        and str(attempt.get("operation") or "") == "performance_capture"
    ]


def _take_reconciles_paid_attempt(shot: Mapping[str, Any], attempt: Mapping[str, Any]) -> bool:
    """Return whether a stored take is bound to this exact paid job."""

    attempt_id = str(attempt.get("attempt_id") or "")
    provider_job_id = str(attempt.get("provider_job_id") or "")
    attempt_engine = str(attempt.get("engine") or "").upper()
    for take in shot.get("performance_takes") or []:
        if not isinstance(take, Mapping):
            continue
        metadata = take.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        if attempt_id and str(metadata.get("paid_attempt_id") or "") == attempt_id:
            return True
        if (
            provider_job_id
            and str(metadata.get("provider_job_id") or "") == provider_job_id
            and (
                not attempt_engine
                or str(metadata.get("engine") or "").upper() == attempt_engine
            )
        ):
            return True
    return False


def _clamp_veo_duration(speech_seconds: float) -> str:
    """Return the shortest Veo-supported duration string >= speech_seconds.

    E.g. 3.5 → '4s', 4.1 → '6s', 9.0 → '8s' (capped at max).
    Over-length tails are truncated by the overlay engine (flagged
    out-of-scope for this PR; long-line splitting is a future concern).
    """
    for d in _VEO_SUPPORTED_DURATIONS:
        if speech_seconds <= _VEO_DURATION_SECONDS[d]:
            return d
    # Longer than any supported value: cap at max.
    return _VEO_SUPPORTED_DURATIONS[-1]


def _motion_pre_spend_duration_s(
    target_api: str, resolved_shot_type: str
) -> Optional[float]:
    """Best-known duration the dispatcher is ABOUT to request, for
    generate_motion_take's pre-spend gate ONLY (money-gate finding
    2026-07-30/31): would_exceed()/would_exceed_cost() priced LTX and
    SEEDANCE off the flat, one-duration-assuming API_COST_USD estimate
    while record_api_call() was already duration-aware for both post-fact
    (cost_tracker.py's API_COST_PER_SECOND_USD; this module's own
    _motion_cost_kwargs SEEDANCE branch) — an LTX/SEEDANCE call about to
    dispatch at 8s was pre-checked against a shorter-duration flat
    UNDER-estimate (LTX's flat figure assumes a 6s floor; SEEDANCE's
    assumes 5s).

    SEEDANCE: resolved_shot_type is already resolved at this point in
    generate_motion_take (classify_shot_type() runs ahead of the gate), and
    the dispatcher (phase_c_ffmpeg.py's SEEDANCE branch) keys its own
    requested duration off the SAME SEEDANCE_DURATIONS table — so this is
    the exact figure the dispatcher will request, not an estimate.

    LTX: the dispatcher's requested duration is generate_ai_video()'s
    ``duration`` kwarg, which this controller only resolves (as
    ``_veo_duration`` in generate_motion_take) AFTER the pre-spend gate —
    it starts from the "8s" default and, for overlay-mode dialogue shots
    only, is later narrowed to the probed TTS length via
    _clamp_veo_duration (capped at "8s", i.e. never larger). Reordering
    that TTS-probe ahead of the gate is out of this fix's scope, so this
    returns the known "8s" default generate_ai_video always starts from:
    exact for every non-overlay-dialogue shot (the common case), and a
    same-or-over-estimate (never an under-estimate) for the overlay-
    dialogue subset, since the later clamp can only shrink it to 4s/6s/8s.

    Returns None (no opinion — the caller falls back to the flat table
    exactly as before this helper existed) for every other engine.
    """
    api_upper = target_api.upper()
    if api_upper == "SEEDANCE":
        from phase_c_ffmpeg import SEEDANCE_DURATIONS
        return float(SEEDANCE_DURATIONS.get(resolved_shot_type, 4))
    if api_upper == "LTX":
        return 8.0  # generate_ai_video(duration: str = "8s") default, phase_c_ffmpeg.py
    return None


def _resolve_f1b_audio(
    host,
    shot: dict,
    scene: dict,
    all_characters: list,
    voice_mode: str,
) -> "Optional[str]":
    """Resolve the audio path to feed the F1b lipsync overlay pass.

    overlay mode:
      - Try _ensure_shot_audio first (per-shot TTS keyed on this shot's
        in-frame characters via ``shot_characters`` helper).  Falls back to
        ``_ensure_scene_audio`` (scene-scoped artifact, keyed by scene-level
        characters via ``scene_characters`` helper) when the shot has no own
        line (None return).
    native mode:
      - Skip _ensure_shot_audio entirely; use _ensure_scene_audio only
        (preserves legacy behaviour for the native escape hatch).

    ``all_characters`` is the project-level character dict list.  Character
    filtering is derived inside this function — callers must NOT pre-filter,
    or the wrong subset reaches the scene-scoped artifact.  Scene audio is
    keyed by SCENE-level chars (cinema_pipeline.py:738-741 mirror); shot
    audio is keyed by in-frame chars with scene fallback.  Passing the
    in-frame subset to a scene-scoped artifact re-keys dialogue_cache_key →
    paid TTS regen + off-frame lines voiced by the wrong character
    (9aed3ce bug class, ticket T-E).

    Returns the resolved audio path string, or None if both sources fail.
    """
    if voice_mode == "overlay":
        # Shot audio: keyed by in-frame characters (shot_characters helper).
        shot_chars = _shot_characters(all_characters, shot, scene)
        audio = host._ensure_shot_audio(shot, scene, shot_chars)
        if audio is None:
            # Scene audio: SCENE-scoped artifact — must use scene-level chars,
            # not the in-frame subset, or the cache key diverges → paid regen
            # + wrong voice (9aed3ce bug class).
            audio = host._ensure_scene_audio(scene, _scene_characters(all_characters, scene))
        return audio
    # native (or unknown) mode: scene-level TTS only.
    # Scene audio is a SCENE-scoped artifact: key with scene-level characters,
    # not in-frame subset (9aed3ce bug class, ticket T-E Bug site A).
    return host._ensure_scene_audio(scene, _scene_characters(all_characters, scene))


def _resolve_identity_strategy(shot, settings, cc):
    """Resolve the per-shot identity-conditioning promise (P1-1 spec §3d).

    Pure decision function: replaces the primary-only asset derivation
    (formerly inline at the MAX-TIER WIRE-UP block) and names which characters
    are promised identity conditioning through approved reference assets.
    """
    from cinema.shots.strategy import (
        IdentityStrategy, CharIdentitySpec, allocate_flux2_references,
        REFERENCE_PRIMARY_ONLY, REFERENCE_MULTI_CHAR, NO_IDENTITY_ASSET,
    )
    in_frame = shot.get("characters_in_frame") or []
    primary_char_id = shot.get("primary_character") or (in_frame[0] if in_frame else "")
    primary_ref = cc.get("primary_reference")

    # Both supported image routes condition on approved references; actual
    # provider provenance is recorded separately after generation.
    is_gemini_multiref = (settings.get("identity_backend") or "gemini_multiref") == "gemini_multiref"

    # Preserve the established Gemini decision contract. Its provider budget
    # is character-based here and its own adapter owns image selection.
    if is_gemini_multiref:
        if not in_frame or not primary_ref:
            return IdentityStrategy(
                mechanism_tag=NO_IDENTITY_ASSET,
                primary_char_id=primary_char_id,
                unconditioned_chars=list(in_frame),
            )

        conditioned = [CharIdentitySpec(
            char_id=primary_char_id, reference=primary_ref,
            identity_anchor=cc.get("identity_anchor", ""),
            multi_angle_refs=tuple(cc.get("multi_angle_refs") or ()),
            fidelity="reference",
        )]
        conditioned_ids = {primary_char_id}
        secondary = cc.get("secondary_chars") or []
        if secondary:
            # Nano Banana budgets REFERENCE IMAGES, not characters — cap the
            # combined primary+secondary character count against the shared
            # GEMINI_MULTIREF_MAX_REFS ceiling (1 slot already spent on the
            # primary) instead of the Kontext-tier flat 2-secondary cap, which
            # doesn't apply to this mechanism.
            from gemini_image_native import GEMINI_MULTIREF_MAX_REFS

            secondary_cap = max(0, GEMINI_MULTIREF_MAX_REFS - 1)
            for entry in secondary[:secondary_cap]:
                conditioned.append(CharIdentitySpec(
                    char_id=entry["char_id"], reference=entry["reference"],
                    identity_anchor=entry.get("identity_anchor", ""),
                    multi_angle_refs=tuple(entry.get("multi_angle_refs") or ()),
                    fidelity="reference",
                ))
                conditioned_ids.add(entry["char_id"])
        tag = REFERENCE_MULTI_CHAR if len(conditioned) > 1 else REFERENCE_PRIMARY_ONLY
        return IdentityStrategy(
            mechanism_tag=tag,
            primary_char_id=primary_char_id,
            conditioned_chars=conditioned,
            unconditioned_chars=[c for c in in_frame if c not in conditioned_ids],
        )

    # Local FLUX.2 budgets actual graph images rather than character records.
    # Allocate once from the provider's documented precedence and derive every
    # downstream promise from those selected regular files.
    from performance.flux2_klein import MAX_REFERENCE_IMAGES

    primary_angles = tuple(cc.get("multi_angle_refs") or ())
    primary_spec = None
    if primary_char_id in in_frame and (primary_ref or primary_angles):
        primary_spec = CharIdentitySpec(
            char_id=primary_char_id,
            reference=primary_ref or "",
            identity_anchor=cc.get("identity_anchor", ""),
            multi_angle_refs=primary_angles,
            fidelity="reference",
        )
    secondary_specs = []
    seen_secondary_ids = {primary_char_id}
    for entry in (cc.get("secondary_chars") or []):
        if not isinstance(entry, dict):
            continue
        char_id = entry.get("char_id")
        if (
            not isinstance(char_id, str)
            or not char_id
            or char_id not in in_frame
            or char_id in seen_secondary_ids
        ):
            continue
        seen_secondary_ids.add(char_id)
        secondary_specs.append(CharIdentitySpec(
            char_id=char_id,
            reference=entry.get("reference") or "",
            identity_anchor=entry.get("identity_anchor", ""),
            multi_angle_refs=tuple(entry.get("multi_angle_refs") or ()),
            fidelity="reference",
        ))
    allocation = allocate_flux2_references(
        primary=primary_spec,
        secondaries=secondary_specs,
        continuity_reference=cc.get("continuity_reference"),
        cap=MAX_REFERENCE_IMAGES,
    )
    allocated_primary = next(
        (
            spec
            for spec in allocation.conditioned_chars
            if spec.char_id == primary_char_id
        ),
        None,
    )
    if allocated_primary is None:
        # A secondary reference cannot stand in for a missing primary identity
        # asset. Keep the former fail-closed identity promise while still
        # allowing an approved continuity image to act as a non-character
        # graph input for the explicit local route.
        continuity_allocation = allocate_flux2_references(
            primary=None,
            continuity_reference=cc.get("continuity_reference"),
            cap=MAX_REFERENCE_IMAGES,
        )
        return IdentityStrategy(
            mechanism_tag=NO_IDENTITY_ASSET,
            primary_char_id=primary_char_id,
            unconditioned_chars=list(in_frame),
            flux2_reference_paths=continuity_allocation.reference_paths,
            flux2_continuity_reference=(
                continuity_allocation.continuity_reference
            ),
        )

    conditioned = list(allocation.conditioned_chars)
    conditioned_ids = {spec.char_id for spec in conditioned}
    if not conditioned:
        tag = NO_IDENTITY_ASSET
    elif len(conditioned) > 1:
        tag = REFERENCE_MULTI_CHAR
    else:
        tag = REFERENCE_PRIMARY_ONLY

    return IdentityStrategy(
        mechanism_tag=tag,
        primary_char_id=primary_char_id,
        conditioned_chars=conditioned,
        unconditioned_chars=[c for c in in_frame if c not in conditioned_ids],
        flux2_reference_paths=allocation.reference_paths,
        flux2_continuity_reference=allocation.continuity_reference,
    )


from cinema.lifecycle import LifecycleService
from domain.models import DirectorialIntent, Project

if TYPE_CHECKING:
    # PipelineCore lives in cinema.core, which transitively imports
    # vbench_evaluator.py — that file uses PEP 604 in function defaults
    # (``X | None = None``), which fails at import-time on Python 3.9
    # (lesson 8.8 in REFACTOR_HANDOFF.md). Since this file only uses
    # ``PipelineCore`` as a type annotation and ``from __future__ import
    # annotations`` is in effect (annotations are evaluated lazily as
    # strings), the import is unnecessary at runtime. Gating it under
    # TYPE_CHECKING keeps the local 3.9 verification path runnable.
    from cinema.core import PipelineCore
    from cinema.runstate import RunState

logger = logging.getLogger(__name__)


@runtime_checkable
class ShotControllerHost(Protocol):
    """Cross-controller methods that ShotController calls on its host.

    V1.1 #5 simplified this protocol: ``scene_clips`` moved to RunState,
    and ``update_progress_pointer`` moved to RunState as a method.
    The host protocol now declares only the method calls that route
    OUT of ShotController to other controllers (Review, Checkpoint) or
    to the orchestrator (Audio phase).
    """

    # -- ReviewController methods --
    def _refresh_project_snapshot(self, timeout: float = 10) -> Optional[dict]: ...
    def _rebuild_review_clips(self, project: Optional[dict] = None) -> dict: ...
    def _candidate_take(self, shot: dict) -> Optional[dict]: ...
    def _resolve_take_path(self, shot: dict, take_id: str) -> str: ...
    def _latest_take(self, shot: dict, collection_name: str) -> Optional[dict]: ...

    # -- CheckpointStore method --
    def _save_checkpoint(self, completed_scene_idx: int = -1) -> None: ...

    # -- Audio-phase method (still on CinemaPipeline) --
    def _ensure_scene_audio(self, scene: dict, characters: list) -> Optional[str]: ...


class ShotController:
    """Per-shot generation + correction, composed from PipelineCore + Lifecycle + Host.

    Constructable independently of CinemaPipeline -- the seam that
    enables Slice 3's per-request controller construction with a
    cached PipelineCore.

    Parameters
    ----------
    core : PipelineCore
        Long-lived project deps + services. Provides project, project_dir,
        continuity, etc. Single instance can be reused across runs.
    lifecycle : LifecycleService
        Per-run progress reporting / cancellation. Phases poll for
        cancellation at safe points; progress is emitted via
        ``self.progress(stage, detail, percent, **kwargs)``.
    host : ShotControllerHost
        Cross-controller + orchestrator-shared callables and attributes
        that shot methods need. CinemaPipeline implements this protocol;
        tests can pass a lightweight stub.
    """

    def __init__(
        self,
        core: PipelineCore,
        lifecycle: LifecycleService,
        host: ShotControllerHost,
        runstate: RunState,
    ):
        self._core = core
        self._lifecycle = lifecycle
        self._host = host
        # V1.1 #5: shot_results + scene_clips + current_* live on the
        # shared RunState. Single canonical home; no per-controller
        # state ownership.
        self._runstate = runstate

    # ------------------------------------------------------------------
    # PipelineCore + Lifecycle property proxies -- preserve self.X access
    # in the moved method bodies (Pattern H, REFACTOR_HANDOFF.md section 7).
    # ------------------------------------------------------------------

    @property
    def project(self) -> dict:
        return self._core.project

    @property
    def project_dir(self) -> str:
        return self._core.project_dir

    @property
    def continuity(self):
        return self._core.continuity

    @property
    def cost_tracker(self):
        """Proxy to PipelineCore.cost_tracker.

        Bundle-A 1.3 (2026-05-24): the cost-tracking call sites in
        generate_keyframe_take / generate_motion_take previously did
        `self.cost_tracker.record_api_call(...)` wrapped in
        `try/except AttributeError` — `self.cost_tracker` didn't resolve
        anywhere on the instance, so every call silently no-op'd. The
        try/except is kept defensive but the attribute now actually
        resolves through PipelineCore.
        """
        return self._core.cost_tracker

    @property
    def progress(self):
        """Bound-method-shaped proxy so legacy self.progress(...) calls work."""
        return self._lifecycle.report_progress

    # ------------------------------------------------------------------
    # Private helpers (moved from ShotControllerMixin).
    # ------------------------------------------------------------------

    def _find_shot(
        self,
        shot_id: str,
        project: Optional[dict] = None,
        scene_id: str = "",
    ) -> tuple[Optional[dict], Optional[dict], int]:
        active_project = project or self.project
        for scene in active_project.get("scenes", []):
            if scene_id and scene.get("id") != scene_id:
                continue
            for shot_index, shot in enumerate(scene.get("shots", [])):
                if shot.get("id") == shot_id:
                    return scene, shot, shot_index
        return None, None, -1

    def _find_take(self, shot: dict, take_id: str) -> tuple[Optional[str], Optional[dict]]:
        for collection_name in ("keyframe_takes", "performance_takes", "motion_takes", "postprocess_variants"):
            for take in shot.get(collection_name, []):
                if take.get("id") == take_id:
                    return collection_name, take
        return None, None

    def _take_output_path(self, shot_id: str, take_id: str, ext: str) -> str:
        output_dir = os.path.join(self.project_dir, "shots", shot_id, "outputs")
        os.makedirs(output_dir, exist_ok=True)
        return os.path.join(output_dir, f"{take_id}{ext}")

    def _to_project_relative(self, absolute_path: str) -> str:
        """Convert a freshly-written output path to a project-relative form
        for persistence (Product invariant #6: portable persistence -- never
        a repo-location-dependent absolute path in take/shot dicts).

        Write-side counterpart to ``_resolve_stored_media_path``. Falls back
        to the original string unchanged when there's nothing safe to
        relativize: empty input, an already-relative input, a path on a
        different drive (Windows ``ValueError``), or a path that isn't
        actually under ``self.project_dir`` (the relpath would climb out via
        ``..`` -- true production outputs are always constructed under
        project_dir via ``_take_output_path``; this guards test doubles and
        any future caller that passes an unrelated path rather than emit a
        confusing, non-portable ``../../..`` chain with no real benefit).
        """
        if not absolute_path or not os.path.isabs(absolute_path):
            return absolute_path
        try:
            relative = os.path.relpath(absolute_path, self.project_dir)
        except ValueError:
            # e.g. different drive letters on Windows -- nothing to relativize.
            return absolute_path
        if relative == os.pardir or relative.startswith(os.pardir + os.sep):
            return absolute_path
        return relative

    def _resolve_stored_media_path(self, stored_path: str) -> str:
        """Resolve a take/shot ``path`` value read back from persisted state
        to a real, directly-openable absolute path under the CURRENT project
        directory. Read-side counterpart to ``_to_project_relative`` --
        every internal consumer that treats a stored take/shot path as a
        real filesystem path (identity validation, ffmpeg/RIFE/lip-sync
        inputs, coherence checks, scene-preview assembly) must route the raw
        string returned by ``_find_take`` / ``host._resolve_take_path`` /
        ``.get("path")`` through this before use.

        Handles both persistence shapes:
          - project-relative (current form) -- joined onto project_dir.
          - a legacy absolute path baked in before a repo move (or before
            this fix) -- returned as-is when it still exists; otherwise a
            SAFE suffix migration derives the remainder from this project's
            own directory segment onward and re-roots it under the CURRENT
            project_dir (mirroring the /file endpoint's migration so a
            resumed pipeline run can still find its own prior takes after a
            repo move, not just the web preview).
        """
        if not stored_path:
            return stored_path
        if not os.path.isabs(stored_path):
            return os.path.normpath(os.path.join(self.project_dir, stored_path))
        if os.path.exists(stored_path):
            return stored_path
        project_id = self.project.get("id", "")
        if not project_id:
            return stored_path
        anchor = f"{os.sep}{project_id}{os.sep}"
        idx = stored_path.rfind(anchor)
        if idx == -1:
            return stored_path
        remainder = stored_path[idx + len(anchor):]
        if not remainder:
            return stored_path
        return os.path.normpath(os.path.join(self.project_dir, remainder))

    def _mutate_shot(self, shot_id: str, mutator, timeout: float = 10):
        # P1-3 migration template (S10 + part 9 Variant 1; B-006-broad-A) --
        # outer boundary validate on self.project + inner mutator-scope validate
        # under the per-project lock. Full variant: typed-iterate to find the
        # (scene, shot) at parity indices, then PASS DICT-REFS to the
        # caller-provided mutator callback. The 13 internal callers in this
        # file (see grep '_mutate_shot' / '_mutator(' patterns) expect
        # (scene_dict, shot_dict) arguments; that callback API contract is
        # preserved. Race protection: inner validate catches corruption that
        # landed between outer validate and lock acquisition.
        # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
        # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 c296105).
        Project.model_validate(self.project)  # outer boundary validate

        def _mutate(latest_project: dict):
            latest_typed = Project.model_validate(latest_project)  # inner mutator-scope validate
            # Typed-iterate for type-safe find; the matched (scene_idx, shot_idx)
            # are then used to index back into the dict (latest_project) so the
            # callback receives raw dict-refs the lock-held mutator can mutate
            # in place. Pydantic List[Scene] preserves order, so the typed
            # iteration index matches the dict index (see pattern doc caveat
            # at §"Variant 1 — Mutator-inner-validation").
            for scene_idx, scene_typed in enumerate(latest_typed.scenes):
                for shot_idx, shot_typed in enumerate(scene_typed.shots):
                    if shot_typed.id == shot_id:
                        scene_dict = latest_project["scenes"][scene_idx]
                        shot_dict = scene_dict["shots"][shot_idx]
                        return mutator(scene_dict, shot_dict)
            return MutationResult(None, save=False)

        result = mutate_project(self.project["id"], _mutate, timeout=timeout, snapshot=self.project)
        self._host._refresh_project_snapshot()
        return result

    @staticmethod
    def _public_deferred_motion_job(job: object) -> dict:
        """Return the bounded, UI-safe subset of a provider recovery record."""
        if not isinstance(job, dict):
            return {}
        engine = str(job.get("engine") or "Provider")[:64]
        raw_status = str(job.get("status") or "recovery_required")
        status = (
            raw_status
            if raw_status in {"pending", "recovery_required"}
            else "recovery_required"
        )
        result: dict = {"engine": engine, "status": status}
        for key in ("reason", "provider_status"):
            value = job.get(key)
            if isinstance(value, str) and value:
                result[key] = value[:256]
        job_id = job.get("job_id")
        if (
            isinstance(job_id, str)
            and 0 < len(job_id) <= 512
            and job_id == job_id.strip()
            and not any(ord(char) < 32 or ord(char) == 127 for char in job_id)
            and "://" not in job_id
            and not any(char in job_id for char in "?#&")
        ):
            # Keep the exact bounded provider identity. Truncating it would
            # break recovery and CostTracker idempotency for long Google
            # operation names.
            result["job_id"] = job_id
        attempts = job.get("attempts")
        if isinstance(attempts, (list, tuple)):
            result["attempts"] = [
                item[:64]
                for item in attempts[:32]
                if isinstance(item, str) and item
            ]
        if isinstance(job.get("billed"), bool):
            result["billed"] = job["billed"]
        attempt_id = job.get("attempt_id")
        if (
            isinstance(attempt_id, str)
            and 0 < len(attempt_id) <= 512
            and attempt_id == attempt_id.strip()
            and not any(ord(char) < 32 or ord(char) == 127 for char in attempt_id)
        ):
            result["attempt_id"] = attempt_id
        duration_s = job.get("duration_s")
        if (
            isinstance(duration_s, (int, float))
            and not isinstance(duration_s, bool)
            and math.isfinite(float(duration_s))
            and 0 < float(duration_s) <= 3600
        ):
            result["duration_s"] = float(duration_s)
        for key in ("updated_at", "resolve_after"):
            value = job.get(key)
            if isinstance(value, str) and value:
                result[key] = value[:64]
        return result

    @classmethod
    def _deferred_motion_response(cls, job: object, *, detail: str = "") -> dict:
        public = cls._public_deferred_motion_job(job)
        engine = str(public.get("engine") or "Provider")
        status = str(public.get("status") or "recovery_required")
        job_id = public.get("job_id")
        job_suffix = f" (job {job_id})" if job_id else ""
        if detail:
            message = detail
        elif status == "pending":
            message = (
                f"{engine} accepted the generation{job_suffix} and it is still "
                "pending. No fallback was started; Generate Motion will resume it "
                "through the Check / Resume action."
            )
        else:
            message = (
                f"{engine} generation{job_suffix} requires recovery before another "
                "provider can run. No fallback was started."
            )
        return {
            "success": False,
            "code": "provider_job_deferred",
            "error": message,
            "deferred_job": public,
        }

    def _persist_deferred_motion_job(
        self,
        shot_id: str,
        job: Optional[dict],
    ) -> object:
        """Persist or clear one shot's provider recovery descriptor atomically."""
        def _mutator(_scene: dict, project_shot: dict):
            if job is None:
                if "deferred_motion_job" not in project_shot:
                    return MutationResult(True, save=False)
                project_shot.pop("deferred_motion_job", None)
                return MutationResult(True, save=True)
            if project_shot.get("deferred_motion_job") == job:
                return MutationResult(job, save=False)
            project_shot["deferred_motion_job"] = job
            return MutationResult(job, save=True)

        return self._mutate_shot(shot_id, _mutator)

    @classmethod
    def _deferred_keyframe_response(cls, job: object, *, detail: str = "") -> dict:
        """Build the stable HTTP/phase response for a blocked keyframe retry."""
        public = cls._public_deferred_motion_job(job)
        engine = str(public.get("engine") or "Keyframe provider")
        job_id = public.get("job_id")
        job_suffix = f" (job {job_id})" if job_id else ""
        message = detail or (
            f"{engine} keyframe generation{job_suffix} has an unresolved provider "
            "outcome. No replacement render was started. Reconcile the provider "
            "queue and history in Review before allowing another keyframe."
        )
        return {
            "success": False,
            "error_kind": "deferred",
            "code": "keyframe_job_deferred",
            "error": message,
            "deferred_job": public,
        }

    def _claim_deferred_keyframe_job(self, shot_id: str, marker: dict) -> object:
        """Atomically reserve one keyframe submission slot for a shot.

        The reservation is durable before provider dispatch. A second HTTP
        request therefore observes the marker instead of opening another paid
        job, even when the first request lost its response or worker process.
        """
        def _mutator(_scene: dict, project_shot: dict):
            existing = project_shot.get("deferred_keyframe_job")
            if isinstance(existing, dict):
                return MutationResult(
                    {"claimed": False, "job": self._public_deferred_motion_job(existing)},
                    save=False,
                )
            project_shot["deferred_keyframe_job"] = marker
            return MutationResult({"claimed": True, "job": marker}, save=True)

        return self._mutate_shot(shot_id, _mutator)

    def _persist_deferred_keyframe_job(
        self,
        shot_id: str,
        job: Optional[dict],
        *,
        attempt_id: str,
    ) -> object:
        """Update only the marker owned by ``attempt_id``.

        An expired request may finish after an operator reconciles it and a
        newer attempt claims the shot. Conditional replacement/clear prevents
        that older request from erasing the newer paid-work fence.
        """
        def _mutator(_scene: dict, project_shot: dict):
            current = project_shot.get("deferred_keyframe_job")
            if (
                not isinstance(current, dict)
                or current.get("attempt_id") != attempt_id
            ):
                return MutationResult({
                    "updated": False,
                    "job": self._public_deferred_motion_job(current),
                }, save=False)
            if job is None:
                project_shot.pop("deferred_keyframe_job", None)
                return MutationResult({"updated": True, "job": {}}, save=True)
            public = self._public_deferred_motion_job(job)
            persisted = {**public, "attempt_id": attempt_id}
            if current == persisted:
                return MutationResult({"updated": True, "job": public}, save=False)
            project_shot["deferred_keyframe_job"] = persisted
            return MutationResult({"updated": True, "job": public}, save=True)

        return self._mutate_shot(shot_id, _mutator)

    def resolve_deferred_keyframe_job(self, shot_id: str) -> dict:
        """Clear a recovery block only after an operator explicitly reconciles it."""
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()

        def _mutator(_scene: dict, project_shot: dict):
            existing = project_shot.get("deferred_keyframe_job")
            if not isinstance(existing, dict):
                return MutationResult(
                    {"success": False, "error": "No deferred keyframe job to resolve"},
                    save=False,
                )
            public = self._public_deferred_motion_job(existing)
            resolve_after = public.get("resolve_after")
            if existing.get("provider_status") == "submission_claimed" and resolve_after:
                try:
                    safe_after = datetime.fromisoformat(
                        str(resolve_after).replace("Z", "+00:00")
                    )
                    if safe_after.tzinfo is None:
                        safe_after = safe_after.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    safe_after = now_dt + timedelta(seconds=1)
                if now_dt < safe_after:
                    return MutationResult({
                        "success": False,
                        "code": "keyframe_attempt_active",
                        "error": (
                            "The original keyframe request is still within its "
                            "active provider window and cannot be reconciled yet"
                        ),
                        "deferred_job": public,
                    }, save=False)
            project_shot.pop("deferred_keyframe_job", None)
            project_shot.setdefault("diagnostics", []).append({
                "kind": "keyframe_recovery_resolved",
                "timestamp": now,
                "engine": public.get("engine", "Keyframe provider"),
                "provider_status": public.get("provider_status", ""),
                "job_id": public.get("job_id", ""),
                "attempt_id": str(existing.get("attempt_id") or "")[:128],
                "message": (
                    "Operator confirmed provider queue/history reconciliation "
                    "before enabling a new keyframe submission."
                ),
            })
            return MutationResult(
                {"success": True, "resolved": True, "deferred_job": public},
                save=True,
            )

        result = self._mutate_shot(shot_id, _mutator)
        if isinstance(result, dict):
            return result
        return {"success": False, "error": "Shot not found"}

    @staticmethod
    def _pending_motion_reservation_usd(
        project: dict,
        *,
        exclude_shot_id: str = "",
    ) -> float:
        """Sum unbilled deferred commitments visible in the durable project."""
        total = 0.0
        for scene in project.get("scenes", []):
            for project_shot in scene.get("shots", []):
                if project_shot.get("id") == exclude_shot_id:
                    continue
                job = project_shot.get("deferred_motion_job")
                if not isinstance(job, dict) or job.get("billed") is True:
                    continue
                value = job.get("reserved_cost_usd")
                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    and float(value) > 0
                ):
                    total += float(value)
        return round(total, 6)

    def _record_diagnostic(self, shot_id: str, diagnostic: dict) -> None:
        def _mutator(_scene: dict, shot: dict):
            shot.setdefault("diagnostics", []).append(diagnostic)
            return MutationResult(diagnostic, save=True)

        self._mutate_shot(shot_id, _mutator)

    @staticmethod
    def _take_collection(take_kind: str) -> str:
        collections = {
            "keyframe": "keyframe_takes",
            "performance": "performance_takes",
            "motion": "motion_takes",
            "postprocess": "postprocess_variants",
        }
        try:
            return collections[take_kind]
        except KeyError as exc:
            raise ValueError(f"Unsupported take kind: {take_kind}") from exc

    @staticmethod
    def _mark_artifact_version_pending(take: dict) -> None:
        take.setdefault("metadata", {})["artifact_versioning_pending"] = True

    def _finalize_take_artifact_version(
        self,
        shot_id: str,
        take_kind: str,
        take: dict,
    ) -> tuple[Optional[dict], Optional[dict]]:
        """Index accepted bytes, then durably clear their recovery marker.

        The pending marker is written in the same project mutation that
        accepts the take.  A crash or ledger failure therefore cannot turn a
        UI retry into another provider submission: the next call repairs this
        exact take first and returns it without entering generation.
        """

        from cinema.artifact_indexing import record_take_version

        take_id = str(take.get("id") or "")
        try:
            record = record_take_version(
                str(self.project.get("id") or ""),
                shot_id,
                take_kind,
                take,
                project_snapshot=self.project,
                project_root=self.project_dir,
            )
        except Exception:
            logger.exception(
                "Accepted take awaits artifact version recovery",
                extra={"shot_id": shot_id, "take_id": take_id, "take_kind": take_kind},
            )
            return None, {
                "success": False,
                "error": (
                    "The accepted output is retained, but its immutable artifact "
                    "record is pending. Retry repairs this record without starting "
                    "new provider work."
                ),
                "error_kind": "artifact_versioning",
                "code": "artifact_version_pending",
                "retryable": True,
                "accepted_take_id": take_id,
            }

        collection = self._take_collection(take_kind)

        def _clear_pending(_scene: dict, project_shot: dict):
            for candidate in project_shot.get(collection, []):
                if candidate.get("id") != take_id:
                    continue
                metadata = candidate.setdefault("metadata", {})
                metadata.pop("artifact_versioning_pending", None)
                metadata["artifact_version_id"] = record["artifact_id"]
                metadata["artifact_version"] = record["version"]
                return MutationResult(candidate, save=True)
            return MutationResult(None, save=False)

        try:
            updated = self._mutate_shot(shot_id, _clear_pending)
        except Exception:
            logger.exception(
                "Artifact version recorded but take marker could not be cleared",
                extra={"shot_id": shot_id, "take_id": take_id, "take_kind": take_kind},
            )
            updated = None
        if not isinstance(updated, dict):
            return None, {
                "success": False,
                "error": (
                    "The immutable artifact was recorded, but project recovery "
                    "state is still pending. Retry reconciles it without provider work."
                ),
                "error_kind": "artifact_versioning",
                "code": "artifact_version_pending",
                "retryable": True,
                "accepted_take_id": take_id,
            }
        return updated, None

    def _recover_pending_take_artifact(
        self,
        shot_id: str,
        take_kind: str,
        shot: dict,
    ) -> Optional[dict]:
        """Repair accepted pending takes before any new provider dispatch."""

        collection = self._take_collection(take_kind)
        pending = [
            take
            for take in shot.get(collection, [])
            if isinstance(take, dict)
            and isinstance(take.get("metadata"), dict)
            and take["metadata"].get("artifact_versioning_pending") is True
        ]
        if not pending:
            return None

        recovered: Optional[dict] = None
        for take in pending:
            recovered, error = self._finalize_take_artifact_version(
                shot_id, take_kind, take,
            )
            if error is not None:
                return error
        if recovered is None:
            return None

        resolved_path = self._resolve_stored_media_path(str(recovered.get("path") or ""))
        metadata = recovered.get("metadata") if isinstance(recovered.get("metadata"), dict) else {}
        self.progress(
            "ARTIFACT_VERSION_RECOVERED",
            f"Recovered immutable {take_kind} artifact for {shot_id}",
            -1,
            shot_id=shot_id,
            take_id=recovered.get("id"),
            take_kind=take_kind,
        )
        result = {
            "success": True,
            "take": recovered,
            "artifact_recovered": True,
        }
        if take_kind == "keyframe":
            result["image"] = resolved_path
        else:
            result["video"] = resolved_path
        if take_kind == "performance":
            result["engine"] = metadata.get("engine")
        if "identity_score" in metadata:
            result["identity_score"] = metadata.get("identity_score")
        return result

    def _resolve_previous_approved_keyframe(self, scene: dict, shot_index: int) -> str:
        if shot_index <= 0:
            return ""
        previous_shot = scene.get("shots", [])[shot_index - 1]
        take_id = previous_shot.get("approved_keyframe_take_id", "")
        return self._resolve_stored_media_path(self._host._resolve_take_path(previous_shot, take_id))

    # ------------------------------------------------------------------
    # Public methods.
    # ------------------------------------------------------------------

    def generate_keyframe_take(
        self,
        scene_id: str,
        shot_id: str,
        positive_prompt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        *,
        intent_override: Optional[DirectorialIntent] = None,
        parent_take_id: str = "",
        revised_prompt: str = "",
    ) -> dict:
        project = self._host._refresh_project_snapshot() or self.project
        scene, shot, shot_index = self._find_shot(shot_id, project, scene_id)
        if not scene or not shot:
            return {"success": False, "error": "Shot not found"}
        pending_artifact = self._recover_pending_take_artifact(
            shot_id, "keyframe", shot,
        )
        if pending_artifact is not None:
            return pending_artifact
        if shot.get("plan_status") != "approved":
            return {"success": False, "error": "Shot plan must be approved before generating a keyframe"}
        existing_keyframe_job = shot.get("deferred_keyframe_job")
        recovery_attempt_id = ""
        if isinstance(existing_keyframe_job, dict):
            public_existing = self._public_deferred_motion_job(existing_keyframe_job)
            candidate_attempt_id = public_existing.get("attempt_id")
            if (
                isinstance(candidate_attempt_id, str)
                and candidate_attempt_id.startswith("take_")
            ):
                # Re-enter the exact logical take. Durable provider adapters
                # derive their paid-attempt key from this take's output path;
                # reusing it lets FAL/ComfyUI poll the acknowledged request ID
                # after a crash, while non-resumable providers remain fenced
                # as accepted_unknown. A new take ID here would be a new paid
                # request and could duplicate the original work.
                recovery_attempt_id = candidate_attempt_id
            else:
                return self._deferred_keyframe_response(existing_keyframe_job)

        settings = project.get("global_settings", {})
        style_suffix = style_rules_to_prompt_suffix(settings.get("style_rules", {}))
        prev_shot = scene.get("shots", [])[shot_index - 1] if shot_index > 0 else None
        approved_anchor = self._resolve_previous_approved_keyframe(scene, shot_index)
        enhanced = self.continuity.enhance_shot_prompt(
            shot,
            scene,
            prev_shot,
            shot_index,
            continuity_reference_path=approved_anchor,
        )
        full_prompt = positive_prompt or enhanced["prompt"]
        if style_suffix:
            full_prompt = f"{full_prompt}. {style_suffix}"

        cc = enhanced.get("continuity_config", {})
        primary_ref = cc.get("primary_reference")

        # Compose the still stage's reference set ONCE, here, above the gate.
        #
        # A product in frame with no character used to reach the generator as
        # plain text — phase_c_assembly gates its entire reference-conditioned
        # route on ``if character_image and os.path.exists(character_image)``,
        # so a logo was rendered from a sentence describing it. Objects now fill
        # that empty slot, and ONLY that one: a shot with a character keeps every
        # slot it had (see compose_shot_reference_set for why the contested case
        # is left undecided).
        #
        # It must be computed before the pre-spend gate rather than at dispatch,
        # because supplying a conditioning image is exactly what selects the
        # route the gate prices. Reading `primary_ref` below while dispatch read
        # a composed value would reserve FLUX_PRO and then bill FLUX_KONTEXT —
        # a gate priced from a different source than the call it guards.
        _shot_conditioning_ref, _shot_reference_set = compose_shot_reference_set(
            character_reference=primary_ref or "",
            character_angles=cc.get("multi_angle_refs") or (),
            object_refs=cc.get("object_refs") or {},
            primary_object=cc.get("primary_object") or "",
            location_refs=cc.get("location_refs") or (),
        )

        # Pre-spend budget gate. Price the first route this exact project can
        # actually enter; do not reserve a retired backend or a credential-
        # absent provider. Local FLUX.2 has no marginal API charge, while its
        # durable job still appears in provider analytics as ``local_gpu``.
        _identity_backend = settings.get("identity_backend", "gemini_multiref")
        if _identity_backend == "local_flux2_klein":
            _image_engine_estimate = "FLUX2_KLEIN_LOCAL"
        elif (
            _shot_conditioning_ref
            and (env_settings.google_api_key or env_settings.gemini_api_key)
        ):
            _image_engine_estimate = "GEMINI_IMAGE"
        elif env_settings.fal_key:
            _image_engine_estimate = (
                "FLUX_KONTEXT" if _shot_conditioning_ref else "FLUX_PRO"
            )
        else:
            _image_engine_estimate = "POLLINATIONS"
        if self.cost_tracker.would_exceed(_image_engine_estimate):
            self.progress(
                "BUDGET_EXCEEDED",
                (
                    f"Estimated {_image_engine_estimate} cost would push spend "
                    f"${self.cost_tracker.spent_usd:.2f} past budget cap "
                    f"${self.cost_tracker.budget_usd:.2f}. Pausing before generation."
                ),
                -1,
                scene_id=scene_id,
                shot_id=shot_id,
                spent=self.cost_tracker.spent_usd,
                budget=self.cost_tracker.budget_usd,
            )
            self._lifecycle.pause()
            return {
                "success": False,
                "error": "Budget cap reached — keyframe generation not started",
                # Structured kind: the keyframe phase loop keys its abort on
                # this (cinema/phases/keyframe_render.py), not on
                # string-parsing the human-facing error.
                "error_kind": "budget",
            }

        take = make_take(
            "keyframe",
            metadata={
                "scene_id": scene_id,
                "shot_id": shot_id,
                "prompt": full_prompt,
                "camera": shot.get("camera", "zoom_in_slow"),
                "target_api": shot.get("target_api", "AUTO"),
            },
        )
        if recovery_attempt_id:
            take["id"] = recovery_attempt_id
            take["metadata"]["provider_recovery_resume"] = True
        img_path = self._take_output_path(shot_id, take["id"], ".jpg")
        self._runstate.update_progress_pointer("KEYFRAME", scene_id, shot_id)
        self.progress(
            "KEYFRAME",
            f"Generating keyframe for {shot_id}",
            -1,
            scene_id=scene_id,
            shot_id=shot_id,
            take_id=take["id"],
        )

        strategy = _resolve_identity_strategy(shot, settings, cc)
        primary_char_id = strategy.primary_char_id
        take["metadata"]["identity_strategy"] = strategy.to_metadata_dict()
        # --- PROMPT OPTIMIZER (highest quality lever) ---
        # When enabled, run the shot prompt through the LLM-based optimizer which
        # produces a cinematography-precise prompt + per-shot API recommendations +
        # identity anchor + negative constraints. The result is cached on the shot
        # (.optimizer_cache) so regen doesn't repeat the LLM call.
        opt_enabled = settings.get("prompt_optimizer_enabled", False)
        opt_spec = None
        if opt_enabled:
            cached = sanitize_optimizer_cache(shot.get("optimizer_cache"))
            # Re-optimize when the source prompt changed OR no cache exists
            if cached and cached.get("source_prompt") == full_prompt:
                opt_spec = cached.get("spec") or None
            else:
                try:
                    from llm.prompt_optimizer import optimize_shot_prompt
                    chars_in_frame = shot.get("characters_in_frame", [])
                    shot_chars = [c for c in project.get("characters", [])
                                  if c.get("id") in chars_in_frame] or project.get("characters", [])
                    objs_in_frame = shot.get("objects_in_frame", [])
                    shot_objs = [o for o in project.get("objects", [])
                                 if o.get("id") in objs_in_frame]
                    location = next(
                        (l for l in project.get("locations", [])
                         if l.get("id") == scene.get("location_id")),
                        {},
                    )
                    has_dialogue = bool(
                        (scene.get("dialogue") or "").strip()
                        or shot.get("dialogue")
                    )
                    opt_spec = sanitize_optimizer_spec(
                        optimize_shot_prompt(
                            user_input=full_prompt,
                            characters=shot_chars,
                            objects=shot_objs,
                            location=location,
                            global_settings=settings,
                            scene_context=f"Scene: {scene.get('title', '')}\nAction: {scene.get('action', '')[:300]}",
                            has_dialogue=has_dialogue,
                            intent_notes=shot.get("intent_notes", ""),
                            cost_tracker=self.cost_tracker,
                        ),
                    )
                    # Persist optimizer output for regen + telemetry
                    def _stash_cache(_scene, project_shot):
                        project_shot["optimizer_cache"] = {
                            "source_prompt": full_prompt,
                            "spec": opt_spec,
                        }
                        return MutationResult(opt_spec, save=True)
                    self._mutate_shot(shot_id, _stash_cache)
                except Exception:
                    # Optimizer is best-effort enrichment; fall back to the
                    # base prompt at WARNING (not ERROR) — the shot still runs.
                    logger.warning(
                        "prompt_optimizer skipped",
                        exc_info=True,
                        extra={"shot_id": shot_id},
                    )
                    opt_spec = None

        # Apply optimizer outputs (when produced) to the call args
        if opt_spec:
            full_prompt = opt_spec.get("image_prompt") or full_prompt
            # Canonical identity wins: cc["identity_anchor"] is the
            # user-approved, immutable "DNA" string built by
            # character_manager.build_identity_anchor (never changes between
            # shots, by design). The optimizer's own identity_anchor is an
            # LLM-invented guess at face/hair/build (llm/prompt_optimizer.py's
            # "critical visual features to preserve") — or, for object-primary
            # shots, an object-specific anchor. It must stay advisory: only
            # used when the shot has no canonical identity to defend (e.g. no
            # registered primary character), never allowed to override one.
            identity_anchor_override = cc.get("identity_anchor") or opt_spec.get("identity_anchor") or ""
            negative_override = opt_spec.get("negative_constraints") or negative_prompt
            # If the user hasn't pinned a target_api, take the optimizer's suggestion
            if shot.get("target_api", "AUTO") == "AUTO":
                suggested = opt_spec.get("suggested_video_api")
                if suggested and suggested != "AUTO":
                    take["metadata"]["target_api"] = suggested
        else:
            identity_anchor_override = cc.get("identity_anchor", "")
            negative_override = negative_prompt or cc.get("negative_constraints") or shot.get("negative_constraints", "")

        # Keep settings in the shared context shape used by downstream helpers.
        # The keyframe provider path currently consumes the plain settings
        # directly, so this context is retained only for compatible callers.
        ctx = PipelineContext(global_settings=settings)

        attempt_id = take["id"]
        claim_started = datetime.now(timezone.utc)
        submission_marker = {
            "engine": "KEYFRAME_PIPELINE",
            "status": "recovery_required",
            "provider_status": "submission_claimed",
            "reason": (
                "A keyframe submission slot was claimed, but its provider outcome "
                "has not yet been reconciled."
            ),
            "updated_at": claim_started.isoformat(),
            # ComfyUI has a bounded 600-second job deadline. The extra minute
            # covers cancellation/history reconciliation before an operator
            # may clear a marker that can still belong to a live request.
            "resolve_after": (claim_started + timedelta(seconds=660)).isoformat(),
            "attempt_id": attempt_id,
        }
        if not recovery_attempt_id:
            claim = self._claim_deferred_keyframe_job(shot_id, submission_marker)
            if claim is None:
                return {"success": False, "error": "Shot not found"}
            if isinstance(claim, dict) and claim.get("claimed") is False:
                return self._deferred_keyframe_response(claim.get("job"))
        else:
            self.progress(
                "KEYFRAME_RECOVERY",
                f"Resuming the durable keyframe attempt for {shot_id}",
                -1,
                scene_id=scene_id,
                shot_id=shot_id,
                take_id=attempt_id,
            )

        if _identity_backend == "local_flux2_klein":
            allocated_primary = next(
                (
                    spec
                    for spec in strategy.conditioned_chars
                    if spec.char_id == strategy.primary_char_id
                ),
                None,
            )
            generation_primary_ref = (
                allocated_primary.reference if allocated_primary is not None else None
            )
            generation_primary_angles = (
                list(allocated_primary.multi_angle_refs)
                if allocated_primary is not None
                else []
            )
            generation_continuity_ref = (
                strategy.flux2_continuity_reference or None
            )
        else:
            # The composed set, so the call matches the route the gate priced.
            # Local FLUX.2 above is deliberately excluded: its graph reads
            # `strategy.flux2_reference_paths`, allocated separately, and
            # Flux2ReferenceAllocation exists precisely so persisted metadata and
            # the graph's input list cannot describe different conditioning.
            # Adding objects there means teaching the allocator about them, not
            # overwriting the value beside it.
            generation_primary_ref = _shot_conditioning_ref or None
            generation_primary_angles = _shot_reference_set
            generation_continuity_ref = cc.get("continuity_reference")

        # Stays on `primary_ref`, NOT the composed value. This selects whether a
        # FACE validator runs and what it compares against; a product photograph
        # is not a face and must never be handed to one.
        identity_validation_ref = (
            generation_primary_ref
            if _identity_backend == "local_flux2_klein"
            else primary_ref
        )

        recovery: dict = {}
        result = generate_ai_broll(
            full_prompt,
            img_path,
            seed=cc.get("scene_seed"),
            character_image=generation_primary_ref,
            continuity_reference=generation_continuity_ref,
            multi_angle_refs=generation_primary_angles,
            identity_anchor=identity_anchor_override,
            negative_prompt=negative_override,
            secondary_char_refs=[c.to_dict() for c in strategy.secondary_specs] or None,
            shot_hint={"prompt": full_prompt, "characters_in_frame": shot.get("characters_in_frame", []),
                       "camera": shot.get("camera", "")},
            ctx=ctx,
            _recovery_out=recovery,
            cost_tracker=self.cost_tracker,
            shot_id=shot_id,
            video_id=str(project.get("id", "")),
            take_id=take["id"],
            project_snapshot=project,
            project_root=self.project_dir,
            artifact_metadata=take.get("metadata"),
            preallocated_flux2_reference_paths=(
                strategy.flux2_reference_paths
                if _identity_backend == "local_flux2_klein"
                else None
            ),
        )
        if not result:
            # The provider cascade can fail after an earlier provider already
            # billed (for example Gemini generated a frame, local validation
            # raised, and every fallback then failed).  Consume the private
            # accounting handoff even when there is no public recovery marker.
            rejected_engines = recovery.pop("_billed_rejects", ())
            for rejected_engine in rejected_engines:
                try:
                    self.cost_tracker.record_api_call(
                        rejected_engine,
                        operation="image_generation_rejected",
                        shot_id=shot_id,
                        video_id=self.project.get("id", ""),
                    )
                except Exception:
                    logger.warning(
                        "billed-but-rejected image recovery record skipped",
                        exc_info=True,
                        extra={"shot_id": shot_id},
                    )
            if recovery:
                recovery["updated_at"] = datetime.now(timezone.utc).isoformat()
                persisted = self._persist_deferred_keyframe_job(
                    shot_id,
                    recovery,
                    attempt_id=attempt_id,
                )
                if isinstance(persisted, dict) and persisted.get("updated") is False:
                    return self._deferred_keyframe_response(
                        persisted.get("job"),
                        detail=(
                            "This keyframe attempt finished after its recovery marker "
                            "was reconciled or superseded. It did not replace the "
                            "current shot state."
                        ),
                    )
                public_job = persisted.get("job") if isinstance(persisted, dict) else recovery
                return self._deferred_keyframe_response(public_job)
            self._persist_deferred_keyframe_job(
                shot_id,
                None,
                attempt_id=attempt_id,
            )
            return {"success": False, "error": "Image generation failed"}

        # ImageGenResult means provider work completed and may be billable,
        # even if local publication or later identity validation fails. Record
        # the winning provider and any billed Gemini reject before those local
        # gates so spend cannot disappear behind a recovery/error path.
        image_api = result.api_name
        video_id = self.project.get("id", "")
        if not recovery.get("_winner_paid_cost_recorded"):
            try:
                self.cost_tracker.record_api_call(
                    image_api,
                    operation="keyframe_generation",
                    shot_id=shot_id,
                    video_id=video_id,
                )
            except Exception:
                logger.warning(
                    "keyframe cost record skipped",
                    exc_info=True,
                    extra={"shot_id": shot_id},
                )
        for rejected_engine in result.billed_rejects:
            if rejected_engine == image_api:
                continue
            try:
                self.cost_tracker.record_api_call(
                    rejected_engine,
                    operation="image_generation_rejected",
                    shot_id=shot_id,
                    video_id=video_id,
                )
                logger.info(
                    "billed-but-rejected image attempt recorded",
                    extra={"shot_id": shot_id, "engine": rejected_engine},
                )
            except Exception:
                logger.warning(
                    "billed-reject image cost record skipped",
                    exc_info=True,
                    extra={"shot_id": shot_id, "engine": rejected_engine},
                )

        if not os.path.exists(img_path):
            missing_output = {
                "engine": result.api_name,
                "status": "recovery_required",
                "provider_status": "output_missing",
                "reason": (
                    "The provider reported a completed keyframe, but no publishable "
                    "local image was found. Reconcile the provider output before retrying."
                ),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            persisted = self._persist_deferred_keyframe_job(
                shot_id,
                missing_output,
                attempt_id=attempt_id,
            )
            if isinstance(persisted, dict) and persisted.get("updated") is False:
                return self._deferred_keyframe_response(
                    persisted.get("job"),
                    detail=(
                        "This completed keyframe attempt was reconciled or superseded "
                        "before its missing output could be registered."
                    ),
                )
            public_job = persisted.get("job") if isinstance(persisted, dict) else missing_output
            return self._deferred_keyframe_response(public_job)

        actual = result.api_name
        if actual == "FLUX_KONTEXT" and strategy.secondary_specs:
            # V-2 / spec §3(d): api_name is backend-granular — a successful
            # Kontext call looks identical for multi-char and primary-only, so
            # derive the actual from api_name x what the strategy emitted.
            # This records EMISSION, not server honoring; S1 + per-char
            # validation cover the latter.
            actual = "FLUX_KONTEXT_MULTI_CHAR"
        elif actual == "GEMINI_IMAGE" and strategy.secondary_specs:
            # WS3 analog of the FLUX_KONTEXT derivation above: a successful
            # Nano Banana call also looks identical for multi-char vs
            # primary-only at the api_name level.
            actual = "GEMINI_IMAGE_MULTI_CHAR"
        take["metadata"]["mechanism_actually_used"] = actual

        identity_score = 0.0
        if identity_validation_ref:
            from phase_c_vision import _get_shared_validator
            # Project-wide `identity_strictness` setting overrides the per-shot
            # `identity_threshold` so the operator can raise/lower the bar
            # without touching every shot. Falls back to the per-shot value.
            strictness = settings.get("identity_strictness")
            # _finite_or preserves the existing None -> per-shot fallback (float(None)
            # raises -> default) AND guards a NaN/inf identity_strictness: nan is not
            # None, so without this `validate_image(threshold=nan)` makes every frame's
            # `similarity >= nan` False -> identity always fails. NaN-fallback == the
            # absent-setting fallback (per-shot identity_threshold). [Pair-A: confirm.]
            threshold = _finite_or(strictness, cc.get("identity_threshold", 0.70))
            id_result = _get_shared_validator().validate_image(
                img_path, identity_validation_ref,
                character_id=primary_char_id,
                threshold=threshold,
                cost_tracker=self.cost_tracker,
                video_id=str(project.get("id", "")),
                shot_id=shot_id,
            )
            identity_score = id_result.overall_score  # None on skip = not scored
            take["metadata"]["identity_score"] = identity_score
            # Surface provider-neutral failure diagnostics for retry logic and
            # operator-facing review.
            char_diag = id_result.character_results.get(primary_char_id)
            if char_diag and not id_result.passed:
                take["metadata"]["identity_failure_reason"] = char_diag.primary_failure_reason.value
                # Deterministic remediation advisory (pure; advisory-only).
                # Best-effort: advisory must never break keyframe generation.
                try:
                    from cinema.auto_approve import AdvisoryConfig
                    from llm.negative_prompts import build_remediation_advisory
                    if AdvisoryConfig.from_project(project).enabled:
                        _adv = build_remediation_advisory(
                            char_diag.primary_failure_reason.value,
                        )
                        if _adv:
                            take["metadata"]["remediation_advisory"] = _adv
                except Exception:
                    logger.exception("T6 remediation advisory failed (non-fatal); continuing")

            # P1-1: score every conditioned character; unconditioned chars are never
            # scored (a low score on them would be expected, not a generation failure).
            per_char = {primary_char_id: identity_score}
            for spec_c in strategy.secondary_specs:
                sec_result = _get_shared_validator().validate_image(
                    img_path, spec_c.reference,
                    character_id=spec_c.char_id,
                    threshold=threshold,
                    cost_tracker=self.cost_tracker,
                    video_id=str(project.get("id", "")),
                    shot_id=shot_id,
                )
                per_char[spec_c.char_id] = sec_result.overall_score
            take["metadata"]["identity_per_char"] = per_char

        take["path"] = self._to_project_relative(img_path)

        # S16: populate directorial iteration provenance when supplied.
        if parent_take_id:
            take["parent_take_id"] = parent_take_id
        if intent_override is not None:
            take["intent"] = intent_override.model_dump()
        if revised_prompt:
            take["revised_prompt"] = revised_prompt
            # params_delta + anchor_refs are populated post-generation by
            # regenerate_with_intent's _stash_delta mutator (single source of
            # truth — pre-seed removed per operator Lane V #4 F5).

        self._mark_artifact_version_pending(take)

        def _mutator(_scene: dict, project_shot: dict):
            current = project_shot.get("deferred_keyframe_job")
            if (
                not isinstance(current, dict)
                or current.get("attempt_id") != attempt_id
            ):
                return MutationResult({
                    "stored": False,
                    "job": self._public_deferred_motion_job(current),
                }, save=False)
            project_shot.setdefault("keyframe_takes", []).append(take)
            project_shot["generated_image"] = self._to_project_relative(img_path)
            project_shot.pop("deferred_keyframe_job", None)
            return MutationResult({"stored": True, "take": take}, save=True)

        stored = self._mutate_shot(shot_id, _mutator)
        if not isinstance(stored, dict) or stored.get("stored") is not True:
            current_job = stored.get("job") if isinstance(stored, dict) else {}
            return self._deferred_keyframe_response(
                current_job,
                detail=(
                    "This completed keyframe attempt was reconciled or superseded "
                    "before registration. It did not replace the current shot state."
                ),
            )
        stored_take = stored["take"]
        stored_take, artifact_error = self._finalize_take_artifact_version(
            shot_id, "keyframe", stored_take,
        )
        if artifact_error is not None:
            return artifact_error
        self._runstate.shot_results[shot_id] = {
            "image": img_path,
            "video": None,
            "identity_score": identity_score,
            "status": "keyframe_review",
            "take_id": take["id"],
        }
        self._host._rebuild_review_clips()
        self._host._save_checkpoint()

        self.progress(
            "KEYFRAME_READY",
            f"Keyframe ready for {shot_id}",
            -1,
            scene_id=scene_id,
            shot_id=shot_id,
            image_url=img_path,
            identity_score=identity_score,
            take_id=take["id"],
            take_kind="keyframe",
        )
        return {
            "success": True,
            "take": stored_take,
            "image": img_path,
            "identity_score": identity_score,
        }

    def generate_performance_take(
        self,
        scene_id: str,
        shot_id: str,
        *,
        intent_override: Optional[DirectorialIntent] = None,
        parent_take_id: str = "",
        revised_prompt: str = "",
        operator_requested: bool = False,
        operator_request_id: str = "",
    ) -> dict:
        """Per-shot performance capture (handoff §7).

        Sits between keyframe review and motion render. Routes the shot to one
        of {ACT_ONE, LIVE_PORTRAIT, VIGGLE, SKIP} via domain.performance.
        SKIP is a happy-path no-op — motion_render falls through to text-to-video
        without a driving reference.

        Effect on the shot:
          performance_takes:          appended-to (one take per call)
          approved_performance_take_id: set on an automatic first success;
                                        explicit review retries remain unapproved
          performance_engine:         the engine string actually used (or "SKIP")
        """
        project = self._host._refresh_project_snapshot() or self.project
        scene, shot, shot_index = self._find_shot(shot_id, project, scene_id)
        if not scene or not shot:
            return {"success": False, "error": "Shot not found"}
        pending_artifact = self._recover_pending_take_artifact(
            shot_id, "performance", shot,
        )
        if pending_artifact is not None:
            return pending_artifact
        if shot.get("plan_status") != "approved":
            return {"success": False, "error": "Shot plan must be approved before performance capture"}
        keyframe_take_id = shot.get("approved_keyframe_take_id", "")
        if not keyframe_take_id:
            return {"success": False, "error": "Approved keyframe required before performance capture"}

        if operator_requested and (
            len(operator_request_id) != 32
            or any(char not in "0123456789abcdef" for char in operator_request_id)
        ):
            return {
                "success": False,
                "error": "A 32-character lowercase request_id is required",
                "error_kind": "operator_input",
                "code": "invalid_performance_request_id",
            }

        # --- 1. Routing ---
        from domain.performance import (
            driving_video_source,
            ENGINE_SKIP,
            has_current_performance_skip,
            route_performance_engine,
        )
        engine = route_performance_engine(shot, scene)

        video_id = str(project.get("id", ""))
        try:
            paid_attempts = _performance_paid_attempts(
                self.cost_tracker,
                video_id=video_id,
                shot_id=shot_id,
            )
        except PerformancePaidAttemptAuthorityError as exc:
            return {
                "success": False,
                "error": str(exc),
                "error_kind": "authority",
                "code": "performance_authority_unavailable",
            }
        existing_performance_attempt = None
        if paid_attempts is not None:
            matching_attempts = [
                attempt
                for attempt in paid_attempts
                if str(attempt.get("engine") or "").upper() == engine
            ]
            if matching_attempts:
                existing_performance_attempt = matching_attempts[-1]
        else:
            get_latest_performance_attempt = getattr(
                self.cost_tracker, "get_latest_paid_attempt", None
            )
            if callable(get_latest_performance_attempt) and engine != ENGINE_SKIP:
                try:
                    existing_performance_attempt = get_latest_performance_attempt(
                        video_id=video_id,
                        shot_id=shot_id,
                        engine=engine,
                        operation="performance_capture",
                    )
                except Exception:
                    logger.warning(
                        "Performance paid-attempt admission lookup failed",
                        exc_info=True,
                        extra={"shot_id": shot_id, "engine": engine},
                    )

        captured_driving_revision = str(shot.get("driving_video_path") or "")
        resolved_driving_for_binding = self._resolve_stored_media_path(
            captured_driving_revision.strip()
        )
        driving_video_fingerprint = ""
        if resolved_driving_for_binding:
            try:
                from paid_provider import file_fingerprint

                driving_video_fingerprint = file_fingerprint(
                    resolved_driving_for_binding
                )
            except (OSError, ValueError):
                # Input validation below reports the concrete provenance error.
                # An unverifiable file can never inherit an existing request.
                driving_video_fingerprint = ""

        current_request = shot.get("performance_generation_request")
        if not isinstance(current_request, Mapping):
            current_request = {}
        current_request_id = str(current_request.get("request_id") or "")
        current_request_state = str(current_request.get("status") or "")
        same_operator_request = bool(
            operator_requested
            and operator_request_id
            and current_request_id == operator_request_id
        )
        same_request_input_binding = bool(
            same_operator_request
            and captured_driving_revision
            and driving_video_fingerprint
            and str(
                current_request.get("driving_video_revision")
                or current_request.get("driving_video_path")
                or ""
            )
            == captured_driving_revision
            and str(current_request.get("driving_video_fingerprint") or "")
            == driving_video_fingerprint
        )

        if same_operator_request:
            completed_take_id = str(current_request.get("take_id") or "")
            _collection, completed_take = self._find_take(shot, completed_take_id)
            if completed_take:
                take_driving_revision = str(
                    (completed_take.get("metadata") or {}).get(
                        "driving_video_path"
                    )
                    or ""
                )
                input_revision_stale = bool(
                    (completed_take.get("metadata") or {}).get(
                        "input_revision_stale"
                    )
                    or not take_driving_revision
                    or self._resolve_stored_media_path(take_driving_revision)
                    != self._resolve_stored_media_path(captured_driving_revision)
                )
                return {
                    "success": True,
                    "take": completed_take,
                    "video": self._resolve_stored_media_path(
                        str(completed_take.get("path") or "")
                    ),
                    "engine": str(
                        (completed_take.get("metadata") or {}).get("engine") or engine
                    ),
                    "request_id": operator_request_id,
                    "replayed": True,
                    "input_revision_stale": input_revision_stale,
                }
            if (
                current_request_state == "succeeded"
                and str(current_request.get("engine") or "").upper() == "SKIP"
                and has_current_performance_skip(shot, scene)
            ):
                return {
                    "success": True,
                    "skipped": True,
                    "engine": "SKIP",
                    "request_id": operator_request_id,
                    "replayed": True,
                }

        if (
            current_request_state in _PERFORMANCE_REQUEST_ACTIVE_STATES
            and not same_request_input_binding
        ):
            input_mismatch = same_operator_request and not same_request_input_binding
            return {
                "success": False,
                "error": (
                    "The saved performance request belongs to a different "
                    "driving-video revision"
                    if input_mismatch
                    else "Another performance generation request requires recovery"
                ),
                "error_kind": "deferred",
                "code": (
                    "performance_request_input_mismatch"
                    if input_mismatch
                    else "performance_request_active"
                ),
                "request": dict(current_request),
            }

        if paid_attempts is not None:
            from cost_tracker import PAID_ATTEMPT_ACTIVE_STATES

            bound_attempt_id = str(current_request.get("paid_attempt_id") or "")

            def _owned_by_same_request(attempt: Mapping[str, Any]) -> bool:
                if not same_request_input_binding:
                    return False
                attempt_id = str(attempt.get("attempt_id") or "")
                if bound_attempt_id:
                    return attempt_id == bound_attempt_id
                return (
                    isinstance(existing_performance_attempt, Mapping)
                    and attempt_id
                    == str(existing_performance_attempt.get("attempt_id") or "")
                    and str(attempt.get("engine") or "").upper() == engine
                )

            blocking_attempt = next(
                (
                    attempt
                    for attempt in paid_attempts
                    if (
                        str(attempt.get("state") or "")
                        in PAID_ATTEMPT_ACTIVE_STATES
                        or (
                            str(attempt.get("state") or "") == "succeeded"
                            and not _take_reconciles_paid_attempt(shot, attempt)
                        )
                    )
                    and not _owned_by_same_request(attempt)
                ),
                None,
            )
            if blocking_attempt is not None:
                return {
                    "success": False,
                    "error": (
                        "Existing performance provider work must be reconciled "
                        "before another request"
                    ),
                    "error_kind": "deferred",
                    "code": "provider_job_deferred",
                    "engine": str(blocking_attempt.get("engine") or engine),
                    "paid_attempt": blocking_attempt,
                }

        if engine == ENGINE_SKIP:
            # Happy-path no-op — record the skip on the shot so motion_render
            # knows to fall through to text-to-video without a driving ref.
            decision = {
                "id": f"performance_skip_{uuid.uuid4().hex}",
                "action": "skip",
                "reason": "routing",
                "decision_source": "routing",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "routed_engine": "SKIP",
                "driving_video_path": captured_driving_revision,
            }
            if operator_requested:
                decision["request_id"] = operator_request_id

            def _mut_skip(_scene: dict, project_shot: dict):
                project_shot["approved_performance_take_id"] = ""
                project_shot["performance_engine"] = "SKIP"
                project_shot["performance_skip"] = decision
                project_shot.setdefault("performance_skip_history", []).append(decision)
                if operator_requested:
                    project_shot["performance_generation_request"] = {
                        "request_id": operator_request_id,
                        "status": "succeeded",
                        "engine": "SKIP",
                        "take_id": "",
                        "created_at": decision["created_at"],
                        "updated_at": decision["created_at"],
                    }
                return MutationResult(True, save=True)
            self._mutate_shot(shot_id, _mut_skip)
            self.progress(
                "PERFORMANCE_SKIPPED",
                f"Shot {shot_id}: SKIP (wide/landscape or no characters)",
                -1, scene_id=scene_id, shot_id=shot_id, performance_engine="SKIP",
            )
            return {"success": True, "skipped": True, "engine": "SKIP"}

        # An explicit local route is a promise to use the configured worker,
        # not permission to silently fall back to a cloud/text-to-video path.
        # Prove the exact role/artifact/execution
        # contract before resolving or generating any paid dialogue audio.
        if engine == "LIVE_PORTRAIT" and not isinstance(
            existing_performance_attempt, dict
        ):
            from performance.worker_readiness import (
                PerformanceWorkerUnavailable,
                require_liveportrait_worker_ready,
            )

            try:
                require_liveportrait_worker_ready()
            except PerformanceWorkerUnavailable as exc:
                self.progress(
                    "PERFORMANCE_BLOCKED",
                    f"Shot {shot_id}: local LivePortrait worker is not ready",
                    -1,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    performance_engine=engine,
                    error_kind="worker_readiness",
                )
                return {
                    "success": False,
                    "error": str(exc),
                    "error_kind": "worker_readiness",
                    "code": "performance_worker_not_ready",
                    "engine": engine,
                }

        # --- 2. Resolve assets ---
        source_image = self._resolve_stored_media_path(self._host._resolve_take_path(shot, keyframe_take_id))
        if not source_image or not os.path.exists(source_image):
            return {"success": False, "error": "Approved keyframe asset is missing"}

        # driving_video_path is an operator-uploaded reference. The upload
        # endpoint now persists a project-relative, content-addressed path;
        # read-side wrapping resolves it under the current project root so it
        # remains usable after relocation (and still migrates legacy absolute
        # values safely), mirroring take-path handling above.
        driving = resolved_driving_for_binding
        if driving:
            try:
                project_root = os.path.realpath(self.project_dir)
                resolved_driving = os.path.realpath(driving)
                driving_is_project_owned = (
                    os.path.commonpath([project_root, resolved_driving])
                    == project_root
                    and resolved_driving != project_root
                )
            except ValueError:
                driving_is_project_owned = False
            if not driving_is_project_owned:
                self.progress(
                    "PERFORMANCE_BLOCKED",
                    f"Shot {shot_id}: driving-video path is outside the project",
                    -1,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    performance_engine=engine,
                    error_kind="input_provenance",
                )
                return {
                    "success": False,
                    "error": (
                        "Performance driving input must resolve inside the "
                        "current project"
                    ),
                    "error_kind": "input_provenance",
                    "code": "driving_video_outside_project",
                    "engine": engine,
                }
        source_mode = driving_video_source(shot)

        # Block before scene audio generation: that path can itself be paid,
        # and audio is not a substitute for a visual driving performance.
        from domain.performance import precondition_error
        pre_err = precondition_error(engine, None, driving)
        if pre_err:
            self.progress(
                "PERFORMANCE_BLOCKED",
                f"Shot {shot_id}: {pre_err}",
                -1,
                scene_id=scene_id,
                shot_id=shot_id,
                performance_engine=engine,
                error_kind="input_required",
            )
            return {
                "success": False,
                "error": pre_err,
                "error_kind": "input_required",
                "code": "driving_video_required",
                "engine": engine,
            }

        try:
            (
                duration_s,
                raw_scene_duration,
                scene_shot_count,
            ) = performance_take_duration_details(scene)
        except ValueError as exc:
            self.progress(
                "PERFORMANCE_BLOCKED",
                f"Shot {shot_id}: {exc}",
                -1,
                scene_id=scene_id,
                shot_id=shot_id,
                performance_engine=engine,
                error_kind="duration",
            )
            return {
                "success": False,
                "error": str(exc),
                "error_kind": "duration",
                "code": "performance_duration_invalid",
                "engine": engine,
            }

        uncapped_duration_s = raw_scene_duration / scene_shot_count

        # Pre-spend budget gate for the chosen performance provider.
        would_exceed_budget = self.cost_tracker.would_exceed(engine)
        if would_exceed_budget:
            budget_detail = (
                f"Estimated {engine} performance cost would push spend "
                f"${self.cost_tracker.spent_usd:.2f} past budget cap "
                f"${self.cost_tracker.budget_usd:.2f}. Pausing before performance capture."
            )

        if would_exceed_budget:
            self.progress(
                "BUDGET_EXCEEDED",
                budget_detail,
                -1,
                scene_id=scene_id,
                shot_id=shot_id,
                spent=self.cost_tracker.spent_usd,
                budget=self.cost_tracker.budget_usd,
                performance_engine=engine,
            )
            self._lifecycle.pause()
            return {
                "success": False,
                "error": "Budget cap reached — performance capture not started",
                "error_kind": "budget",
                "engine": engine,
            }

        # --- 3. Materialize the exact provider input before any paid work. ---

        # Keep both paths: the active upload revision is the review/approval
        # authority, while every provider receives the same physically bounded
        # derivative.  Act-Two and Viggle do not honor a duration argument.
        driving_video_path = self._to_project_relative(driving) if driving else ""
        if driving and os.path.isabs(driving_video_path):
            return {
                "success": False,
                "error": (
                    "Resolved performance driving input is outside the project; "
                    "copy/upload it into the project before capture"
                ),
                "error_kind": "input_provenance",
                "engine": engine,
            }

        from performance.driving_clip import (
            DrivingClipError,
            prepare_bounded_driving_clip,
        )

        try:
            dispatched_driving = prepare_bounded_driving_clip(
                driving,
                project_root=self.project_dir,
                duration_s=duration_s,
            )
        except (DrivingClipError, OSError) as exc:
            self.progress(
                "PERFORMANCE_BLOCKED",
                f"Shot {shot_id}: bounded driving input could not be prepared",
                -1,
                scene_id=scene_id,
                shot_id=shot_id,
                performance_engine=engine,
                error_kind="input_preparation",
            )
            return {
                "success": False,
                "error": str(exc),
                "error_kind": "input_preparation",
                "code": "driving_video_preparation_failed",
                "engine": engine,
            }
        dispatched_driving_video_path = self._to_project_relative(
            dispatched_driving
        )
        if os.path.isabs(dispatched_driving_video_path):
            return {
                "success": False,
                "error": "Bounded driving input escaped the project root",
                "error_kind": "input_provenance",
                "code": "driving_video_outside_project",
                "engine": engine,
            }
        from paid_provider import file_fingerprint

        driving_video_fingerprint = file_fingerprint(driving)
        dispatched_driving_fingerprint = file_fingerprint(dispatched_driving)

        request_started_at = datetime.now(timezone.utc).isoformat()

        def _set_performance_request(status: str, **fields: Any) -> None:
            if not operator_requested:
                return

            def _mut_request(_scene: dict, project_shot: dict):
                current = project_shot.get("performance_generation_request")
                if (
                    not isinstance(current, dict)
                    or current.get("request_id") != operator_request_id
                ):
                    return MutationResult(False, save=False)
                current["status"] = status
                current["updated_at"] = datetime.now(timezone.utc).isoformat()
                current.update(fields)
                return MutationResult(True, save=True)

            self._mutate_shot(shot_id, _mut_request)

        if operator_requested:
            review_event = {
                "id": f"performance_review_{uuid.uuid4().hex}",
                "action": "generate",
                "request_id": operator_request_id,
                "created_at": request_started_at,
                "previous_approved_performance_take_id": str(
                    shot.get("approved_performance_take_id") or ""
                ),
                "driving_video_revision": captured_driving_revision,
                "driving_video_path": driving_video_path,
                "dispatched_driving_video_path": dispatched_driving_video_path,
            }

            def _mut_begin_request(_scene: dict, project_shot: dict):
                if str(project_shot.get("driving_video_path") or "") != str(
                    captured_driving_revision
                ):
                    return MutationResult(
                        {"accepted": False, "code": "driving_video_changed"},
                        save=False,
                    )
                current = project_shot.get("performance_generation_request")
                if isinstance(current, dict):
                    current_id = str(current.get("request_id") or "")
                    current_status = str(current.get("status") or "")
                    if current_id == operator_request_id:
                        current_input_matches = bool(
                            str(
                                current.get("driving_video_revision")
                                or current.get("driving_video_path")
                                or ""
                            )
                            == captured_driving_revision
                            and str(current.get("driving_video_fingerprint") or "")
                            == driving_video_fingerprint
                        )
                        if not current_input_matches:
                            return MutationResult(
                                {
                                    "accepted": False,
                                    "code": "performance_request_input_mismatch",
                                },
                                save=False,
                            )
                        return MutationResult(
                            {
                                "accepted": True,
                                "existing": True,
                                "status": current_status,
                                "take_id": str(current.get("take_id") or ""),
                            },
                            save=False,
                        )
                    if current_status in _PERFORMANCE_REQUEST_ACTIVE_STATES:
                        return MutationResult(
                            {
                                "accepted": False,
                                "code": "performance_request_active",
                                "request": dict(current),
                            },
                            save=False,
                        )
                project_shot["approved_performance_take_id"] = ""
                if (project_shot.get("performance_engine") or "").upper() == "SKIP":
                    project_shot["performance_engine"] = ""
                project_shot["performance_skip"] = None
                project_shot["performance_generation_request"] = {
                    "request_id": operator_request_id,
                    "status": "dispatching",
                    "engine": engine,
                    "take_id": "",
                    "paid_attempt_id": "",
                    "provider_job_id": "",
                    "driving_video_revision": captured_driving_revision,
                    "driving_video_path": driving_video_path,
                    "driving_video_fingerprint": driving_video_fingerprint,
                    "dispatched_driving_video_path": dispatched_driving_video_path,
                    "dispatched_driving_fingerprint": dispatched_driving_fingerprint,
                    "created_at": request_started_at,
                    "updated_at": request_started_at,
                }
                project_shot.setdefault("performance_review_history", []).append(
                    review_event
                )
                return MutationResult({"accepted": True, "existing": False}, save=True)

            request_admission = self._mutate_shot(shot_id, _mut_begin_request)
            if not isinstance(request_admission, Mapping) or not request_admission.get(
                "accepted"
            ):
                code = (
                    str(request_admission.get("code") or "performance_request_active")
                    if isinstance(request_admission, Mapping)
                    else "performance_request_active"
                )
                return {
                    "success": False,
                    "error": (
                        "Driving video changed before performance dispatch"
                        if code == "driving_video_changed"
                        else (
                            "The request_id is already bound to a different "
                            "driving-video revision"
                            if code == "performance_request_input_mismatch"
                            else "Another performance generation request requires recovery"
                        )
                    ),
                    "error_kind": "deferred",
                    "code": code,
                }
            if request_admission.get("status") == "succeeded":
                refreshed = self._host._refresh_project_snapshot() or self.project
                _scene, refreshed_shot, _index = self._find_shot(
                    shot_id, refreshed, scene_id
                )
                completed_take_id = str(request_admission.get("take_id") or "")
                _collection, completed_take = self._find_take(
                    refreshed_shot or {}, completed_take_id
                )
                if completed_take:
                    return {
                        "success": True,
                        "take": completed_take,
                        "video": self._resolve_stored_media_path(
                            str(completed_take.get("path") or "")
                        ),
                        "engine": engine,
                        "request_id": operator_request_id,
                        "replayed": True,
                    }

        # Audio comes from the scene-level dialogue track. It is resolved only
        # after the durable operator action exists, because audio generation can
        # itself cross a paid boundary.
        characters = _scene_characters(project.get("characters") or [], scene)
        audio_path = ""
        try:
            audio_path = self._host._ensure_scene_audio(scene, characters) or ""
        except Exception:
            logger.warning(
                "scene audio unavailable",
                exc_info=True,
                extra={"scene_id": scene["id"], "engine": engine},
            )

        # A second read closes the automatic-pipeline race: an upload selected
        # after input capture never becomes the provenance for this paid call.
        latest_project = self._host._refresh_project_snapshot() or self.project
        _latest_scene, latest_shot, _latest_index = self._find_shot(
            shot_id, latest_project, scene_id
        )
        if (
            not latest_shot
            or str(latest_shot.get("driving_video_path") or "")
            != captured_driving_revision
        ):
            _set_performance_request(
                "stale_input",
                error_code="driving_video_changed",
            )
            return {
                "success": False,
                "error": "Driving video changed before performance dispatch",
                "error_kind": "input_revision",
                "code": "driving_video_changed",
                "engine": engine,
            }

        # --- 4. Dispatch to the chosen engine ---
        take = make_take(
            "performance",
            source_take_id=keyframe_take_id,
            metadata={
                "scene_id": scene_id,
                "shot_id": shot_id,
                "engine": engine,
                "driving_source": source_mode,
                "driving_video_path": driving_video_path,
                "driving_video_fingerprint": driving_video_fingerprint,
                "dispatched_driving_video_path": dispatched_driving_video_path,
                "dispatched_driving_fingerprint": dispatched_driving_fingerprint,
                "audio_path": audio_path,
                "duration_s": duration_s,
                "scene_duration_s": raw_scene_duration,
                "scene_shot_count": scene_shot_count,
                "duration_cap_s": MAX_PERFORMANCE_TAKE_DURATION_S,
                "duration_capped": uncapped_duration_s > MAX_PERFORMANCE_TAKE_DURATION_S,
                "operator_request_id": operator_request_id if operator_requested else "",
            },
        )
        perf_path = self._take_output_path(shot_id, take["id"], ".mp4")
        self._host._runstate.update_progress_pointer(
            "PERFORMANCE_CAPTURE", scene_id, shot_id,
        ) if hasattr(self._host, "_runstate") and hasattr(self._host._runstate, "update_progress_pointer") else None
        self.progress(
            "PERFORMANCE",
            f"Performance capture for {shot_id} via {engine}",
            -1, scene_id=scene_id, shot_id=shot_id, take_id=take["id"],
            performance_engine=engine,
        )

        dispatch_error: Optional[Exception] = None
        try:
            from performance._router import dispatch
            result_path = dispatch(
                engine,
                keyframe_path=source_image,
                audio_path=audio_path or None,
                driving_video_path=dispatched_driving or None,
                output_mp4=perf_path,
                duration_s=duration_s,
                shot_id=shot_id,
                video_id=video_id,
                request_id=operator_request_id if operator_requested else "",
                cost_tracker=self.cost_tracker,
            )
        except Exception as exc:
            # Keep provider recovery authoritative below: an adapter can raise
            # after recording a durable remote job, and that state must win
            # over either a local failure or a successful SKIP mutation.
            dispatch_error = exc
            result_path = None
            logger.warning(
                "Performance dispatch raised",
                exc_info=True,
                extra={"shot_id": shot_id, "engine": engine},
            )

        paid_attempt = None
        get_latest_attempt = getattr(
            self.cost_tracker, "get_latest_paid_attempt", None
        )
        if (
            engine in {"ACT_ONE", "LIVE_PORTRAIT", "VIGGLE"}
            and callable(get_latest_attempt)
        ):
            try:
                candidate_attempt = get_latest_attempt(
                    video_id=video_id,
                    shot_id=shot_id,
                    engine=engine,
                    operation="performance_capture",
                )
                if isinstance(candidate_attempt, dict):
                    paid_attempt = candidate_attempt
            except Exception:
                logger.warning(
                    "Performance provider durable state lookup failed",
                    exc_info=True,
                    extra={"shot_id": shot_id, "engine": engine},
                )

        if not result_path or not os.path.exists(perf_path):
            if paid_attempt is None and isinstance(existing_performance_attempt, dict):
                paid_attempt = existing_performance_attempt
            if isinstance(paid_attempt, dict) and paid_attempt.get("state") == "blocked_budget":
                _set_performance_request(
                    "blocked_budget",
                    paid_attempt_id=str(paid_attempt.get("attempt_id") or ""),
                    provider_job_id=str(paid_attempt.get("provider_job_id") or ""),
                    paid_attempt_state="blocked_budget",
                )
                self.progress(
                    "BUDGET_EXCEEDED",
                    f"Shot {shot_id}: atomic budget reservation refused {engine}",
                    -1,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    performance_engine=engine,
                    paid_attempt_id=paid_attempt.get("attempt_id"),
                    paid_attempt_state="blocked_budget",
                    spent=self.cost_tracker.spent_usd,
                    budget=self.cost_tracker.budget_usd,
                )
                self._lifecycle.pause()
                return {
                    "success": False,
                    "error": "Budget cap reached — performance capture not started",
                    "error_kind": "budget",
                    "engine": engine,
                    "paid_attempt": paid_attempt,
                }
            if isinstance(paid_attempt, dict) and paid_attempt.get("state") in {
                "reserved",
                "submitting",
                "accepted_unknown",
                "running",
                "cancel_requested",
                "succeeded",
                "failed_billed",
            }:
                state = str(paid_attempt.get("state") or "accepted_unknown")
                _set_performance_request(
                    "deferred",
                    paid_attempt_id=str(paid_attempt.get("attempt_id") or ""),
                    provider_job_id=str(paid_attempt.get("provider_job_id") or ""),
                    paid_attempt_state=state,
                )
                self.progress(
                    "PERFORMANCE_DEFERRED",
                    f"Shot {shot_id}: {engine} task is {state}; no successful skip was recorded",
                    -1,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    performance_engine=engine,
                    paid_attempt_id=paid_attempt.get("attempt_id"),
                    paid_attempt_state=state,
                )
                return {
                    "success": False,
                    "error": f"{engine} paid task requires recovery or operator review",
                    "error_kind": "deferred",
                    "code": "provider_job_deferred",
                    "engine": engine,
                    "paid_attempt": paid_attempt,
                }
            if engine == "LIVE_PORTRAIT":
                detail = (
                    "Local LivePortrait execution failed"
                    if dispatch_error is not None
                    else "Local LivePortrait produced no valid output"
                )
                self.progress(
                    "PERFORMANCE_BLOCKED",
                    f"Shot {shot_id}: {detail.lower()}",
                    -1,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    performance_engine=engine,
                    error_kind="worker_execution",
                )
                _set_performance_request(
                    "failed",
                    error_code="local_performance_failed",
                )
                return {
                    "success": False,
                    "error": detail,
                    "error_kind": "worker_execution",
                    "code": "local_performance_failed",
                    "engine": engine,
                }
            if dispatch_error is not None:
                _set_performance_request(
                    "failed",
                    error_code="performance_capture_failed",
                )
                return {
                    "success": False,
                    "error": f"Performance dispatch raised: {dispatch_error}",
                    "error_kind": "provider_execution",
                    "code": "performance_capture_failed",
                    "engine": engine,
                }
            # A provider returning no output is a failed performance attempt,
            # never an implicit operator decision.  Keep the review gate
            # closed; the operator can retry or choose the explicit skip route.
            self.progress(
                "PERFORMANCE_BLOCKED",
                f"Shot {shot_id}: {engine} produced no valid output",
                -1,
                scene_id=scene_id,
                shot_id=shot_id,
                performance_engine=engine,
                error_kind="provider_execution",
            )
            _set_performance_request(
                "failed",
                error_code="performance_capture_failed",
            )
            return {
                "success": False,
                "error": f"{engine} produced no valid performance output",
                "error_kind": "provider_execution",
                "code": "performance_capture_failed",
                "engine": engine,
            }

        # --- 5. Persist the take + identity-gate the auto-approve ---
        take["path"] = self._to_project_relative(perf_path)
        if isinstance(paid_attempt, dict):
            take.setdefault("metadata", {}).update({
                "paid_attempt_id": str(paid_attempt.get("attempt_id") or ""),
                "provider_job_id": str(paid_attempt.get("provider_job_id") or ""),
                "request_fingerprint": str(
                    paid_attempt.get("request_fingerprint") or ""
                ),
                "paid_attempt_state": str(paid_attempt.get("state") or ""),
            })

        # S16: populate directorial iteration provenance when supplied.
        if parent_take_id:
            take["parent_take_id"] = parent_take_id
        if intent_override is not None:
            take["intent"] = intent_override.model_dump()
        if revised_prompt:
            take["revised_prompt"] = revised_prompt
            # params_delta + anchor_refs are populated post-generation by
            # regenerate_with_intent's _stash_delta mutator (single source of
            # truth — pre-seed removed per operator Lane V #4 F5).

        # Resolve the character's face anchor for the gate. Multi-character shots
        # anchor on the first listed character — operators can override via the
        # PERFORMANCE_REVIEW gate. Uses the existing character_manager helper that
        # already understands the project's character list shape.
        face_anchor = ""
        chars = shot.get("characters_in_frame", []) or []
        if chars:
            try:
                face_anchor = get_reference_image(project, chars[0]) or ""
            except Exception:
                logger.exception(
                    "face_anchor lookup failed",
                    extra={"shot_id": shot_id, "character": chars[0]},
                )
                face_anchor = ""

        from performance.identity_gate import validate_performance_take, DEFAULT_PERFORMANCE_FLOOR
        arc_score = (
            validate_performance_take(
                perf_path,
                face_anchor,
                cost_tracker=self.cost_tracker,
                video_id=str(project.get("id", "")),
                shot_id=shot_id,
            )
            if face_anchor
            else None
        )
        gate_passed = (
            isinstance(arc_score, (int, float))
            and not isinstance(arc_score, bool)
            and math.isfinite(float(arc_score))
            and float(arc_score) >= DEFAULT_PERFORMANCE_FLOOR
        )
        take.setdefault("metadata", {})["identity_score"] = arc_score
        expected_driving_revision = captured_driving_revision

        def _mut_success(_scene: dict, project_shot: dict):
            input_revision_stale = (
                str(project_shot.get("driving_video_path") or "")
                != expected_driving_revision
            )
            take.setdefault("metadata", {})["input_revision_stale"] = (
                input_revision_stale
            )
            project_shot.setdefault("performance_takes", []).append(take)
            # Auto-approve only when measured identity evidence passed. A low
            # or unknown score leaves approval to the operator at review.
            if (
                not input_revision_stale
                and gate_passed
                and not operator_requested
                and not project_shot.get("approved_performance_take_id")
            ):
                project_shot["approved_performance_take_id"] = take["id"]
            if not input_revision_stale:
                project_shot["performance_engine"] = engine
            if operator_requested:
                current_request = project_shot.get("performance_generation_request")
                if (
                    isinstance(current_request, dict)
                    and current_request.get("request_id") == operator_request_id
                ):
                    current_request.update({
                        "status": "stale_input" if input_revision_stale else "succeeded",
                        "take_id": take["id"],
                        "paid_attempt_id": str(
                            (paid_attempt or {}).get("attempt_id") or ""
                        ),
                        "provider_job_id": str(
                            (paid_attempt or {}).get("provider_job_id") or ""
                        ),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    })
            return MutationResult(take, save=True)

        self._mark_artifact_version_pending(take)
        stored_take = self._mutate_shot(shot_id, _mut_success)
        stored_take, artifact_error = self._finalize_take_artifact_version(
            shot_id, "performance", stored_take,
        )
        if artifact_error is not None:
            return artifact_error
        self._host._save_checkpoint()
        input_revision_stale = bool(
            (stored_take.get("metadata") or {}).get("input_revision_stale")
        )
        if input_revision_stale:
            self.progress(
                "PERFORMANCE_REVIEW_REQUIRED",
                (
                    f"Shot {shot_id}: driving input changed after dispatch; "
                    "take retained as history and cannot be approved"
                ),
                -1,
                scene_id=scene_id,
                shot_id=shot_id,
                take_id=take["id"],
                error_kind="input_revision",
            )
        elif not gate_passed:
            score_detail = (
                f"{float(arc_score):.3f} below floor {DEFAULT_PERFORMANCE_FLOOR}"
                if isinstance(arc_score, (int, float))
                and not isinstance(arc_score, bool)
                and math.isfinite(float(arc_score))
                else "UNKNOWN; measured identity evidence is required"
            )
            self.progress(
                "PERFORMANCE_REVIEW_REQUIRED",
                f"Shot {shot_id}: identity score {score_detail}; awaiting operator review",
                -1, scene_id=scene_id, shot_id=shot_id, take_id=take["id"],
                identity_score=arc_score,
            )
        self.progress(
            "PERFORMANCE_READY",
            f"Performance ready for {shot_id}",
            -1, scene_id=scene_id, shot_id=shot_id,
            video_url=perf_path, take_id=take["id"], take_kind="performance",
            performance_engine=engine,
        )
        return {
            "success": True,
            "take": stored_take,
            "video": perf_path,
            "engine": engine,
            "request_id": operator_request_id if operator_requested else "",
            "input_revision_stale": input_revision_stale,
        }

    def skip_performance_take(
        self,
        scene_id: str,
        shot_id: str,
        *,
        reason: str,
    ) -> dict:
        """Record an explicit operator decision to bypass performance capture.

        This is the only failure-recovery path that may turn a shot requiring
        performance into ``SKIP``.  Natural wide/no-character routing remains a
        separate ``reason=routing`` record.  Active or ambiguous provider work
        blocks the decision so a skip cannot hide an accepted paid task.
        """

        from domain.performance import (
            has_current_performance_skip,
            normalize_performance_skip_reason,
        )

        try:
            operator_reason = normalize_performance_skip_reason(reason)
        except ValueError as exc:
            return {
                "success": False,
                "error": str(exc),
                "error_kind": "operator_input",
                "code": "invalid_performance_skip_reason",
            }

        project = self._host._refresh_project_snapshot() or self.project
        scene, shot, _shot_index = self._find_shot(shot_id, project, scene_id)
        if not scene or not shot:
            return {"success": False, "error": "Shot not found"}
        if shot.get("plan_status") != "approved":
            return {
                "success": False,
                "error": "Shot plan must be approved before skipping performance capture",
            }
        if not shot.get("approved_keyframe_take_id"):
            return {
                "success": False,
                "error": "Approved keyframe required before skipping performance capture",
            }

        current_skip = shot.get("performance_skip")
        if (
            has_current_performance_skip(shot, scene)
            and isinstance(current_skip, dict)
            and (
                current_skip.get("decision_source") == "operator"
                or current_skip.get("reason") == "operator"
            )
            and current_skip.get("operator_reason") == operator_reason
        ):
            return {
                "success": True,
                "skipped": True,
                "engine": "SKIP",
                "decision": current_skip,
            }

        from cost_tracker import PAID_ATTEMPT_ACTIVE_STATES
        from domain.performance import ENGINE_SKIP, route_performance_engine

        routed_engine = route_performance_engine(shot, scene)
        video_id = str(project.get("id", ""))
        try:
            attempts = _performance_paid_attempts(
                self.cost_tracker,
                video_id=video_id,
                shot_id=shot_id,
            )
        except PerformancePaidAttemptAuthorityError as exc:
            return {
                "success": False,
                "error": str(exc),
                "error_kind": "authority",
                "code": "performance_authority_unavailable",
            }
        if attempts is None:
            lookup = getattr(self.cost_tracker, "get_latest_paid_attempt", None)
            if not callable(lookup) and routed_engine != ENGINE_SKIP:
                return {
                    "success": False,
                    "error": "Performance provider authority is unavailable; skip blocked",
                    "error_kind": "authority",
                    "code": "performance_authority_unavailable",
                }
            if routed_engine == ENGINE_SKIP:
                attempts = []
            else:
                try:
                    latest_attempt = lookup(
                        video_id=video_id,
                        shot_id=shot_id,
                        engine=routed_engine,
                        operation="performance_capture",
                    )
                except Exception:
                    logger.warning(
                        "Performance skip authority lookup failed",
                        exc_info=True,
                        extra={"shot_id": shot_id, "engine": routed_engine},
                    )
                    return {
                        "success": False,
                        "error": "Performance provider authority could not be verified; skip blocked",
                        "error_kind": "authority",
                        "code": "performance_authority_unavailable",
                    }
                attempts = [latest_attempt] if isinstance(latest_attempt, dict) else []

        active_request = shot.get("performance_generation_request")
        if (
            isinstance(active_request, Mapping)
            and str(active_request.get("status") or "")
            in _PERFORMANCE_REQUEST_ACTIVE_STATES
        ):
            return {
                "success": False,
                "error": "Performance generation requires recovery before skipping",
                "error_kind": "deferred",
                "code": "performance_request_active",
                "request": dict(active_request),
            }

        paid_attempt = next(
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
        attempt_state = str((paid_attempt or {}).get("state") or "")
        if paid_attempt is not None:
            return {
                "success": False,
                "error": (
                    f"{paid_attempt.get('engine') or routed_engine} provider work is "
                    f"{attempt_state}; reconcile it "
                    "before skipping performance"
                ),
                "error_kind": "deferred",
                "code": "provider_job_deferred",
                "engine": str(paid_attempt.get("engine") or routed_engine),
                "paid_attempt": paid_attempt,
            }

        decision = {
            "id": f"performance_skip_{uuid.uuid4().hex}",
            "action": "skip",
            "reason": operator_reason,
            "decision_source": "operator",
            "operator_reason": operator_reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "routed_engine": routed_engine,
            "previous_engine": str(shot.get("performance_engine") or ""),
            "previous_approved_performance_take_id": str(
                shot.get("approved_performance_take_id") or ""
            ),
            "driving_video_path": str(shot.get("driving_video_path") or ""),
        }
        if isinstance(paid_attempt, dict):
            decision["paid_attempt_id"] = str(paid_attempt.get("attempt_id") or "")
            decision["paid_attempt_state"] = attempt_state
            decision["provider_job_id"] = str(paid_attempt.get("provider_job_id") or "")

        def _mut_skip(_scene: dict, project_shot: dict):
            project_shot["approved_performance_take_id"] = ""
            project_shot["performance_engine"] = "SKIP"
            project_shot["performance_skip"] = decision
            project_shot.setdefault("performance_skip_history", []).append(decision)
            project_shot.setdefault("performance_review_history", []).append(decision)
            return MutationResult(decision, save=True)

        stored_decision = self._mutate_shot(shot_id, _mut_skip)
        if not stored_decision:
            return {"success": False, "error": "Shot not found"}
        self._host._save_checkpoint()
        self.progress(
            "PERFORMANCE_SKIPPED",
            f"Shot {shot_id}: operator explicitly skipped performance capture",
            -1,
            scene_id=scene_id,
            shot_id=shot_id,
            performance_engine="SKIP",
            skip_reason="operator",
            skip_decision_id=decision["id"],
        )
        return {
            "success": True,
            "skipped": True,
            "engine": "SKIP",
            "decision": stored_decision,
        }

    def _validate_take_identity(
        self,
        video_path: str,
        shot: dict,
        cc: dict,
        settings: dict,
        resolved_shot_type: str,
        take: dict,
    ) -> float:
        """Step 1 of _finalize_motion_take: continuity / identity validation.

        Validates EVERY character in frame. The previous inline block passed
        ``[chars_in_frame[0]]`` — a slice carried over through the
        ShotController extraction (4db9b8a) with no recorded decision behind
        it, which let a second character's identity drift through unchecked.
        ``ContinuityEngine.validate_shot`` builds one config per character
        that has a registered reference image (background extras without
        refs are skipped, so they cannot false-fail), and the validator
        averages per-character best similarities into ``overall_score``.

        Records ``identity_score`` plus per-character outcomes
        (``identity_per_char``, ``identity_all_matched``) in take metadata
        for operator review; returns the score (0.0 when skipped).
        """
        identity_score = 0.0
        primary_ref = cc.get("primary_reference")
        chars_in_frame = shot.get("characters_in_frame", [])
        if not (chars_in_frame and primary_ref):
            return identity_score
        vid_result = self.continuity.validate_shot(
            video_path,
            list(chars_in_frame),
            shot_type=resolved_shot_type,
            mode="standard",
            attempt=0,
            max_attempts=settings.get("identity_retry_max", 3),
            cost_tracker=self.cost_tracker,
            video_id=str(self.project.get("id", "")),
            shot_id=str(shot.get("id", "")),
        )
        identity_score = (vid_result.overall_score
                          if hasattr(vid_result, "overall_score") and vid_result.overall_score is not None
                          else 0.0)
        take["metadata"]["identity_score"] = identity_score
        char_results = getattr(vid_result, "character_results", None) or {}
        per_char = {
            cid: round(cr.best_similarity, 4)
            for cid, cr in char_results.items()
            if hasattr(cr, "best_similarity")
        }
        if per_char:
            take["metadata"]["identity_per_char"] = per_char
            take["metadata"]["identity_all_matched"] = all(
                getattr(cr, "matched", False)
                for cr in char_results.values()
                if hasattr(cr, "best_similarity")
            )
        return identity_score

    def _maybe_auto_rife(
        self, video_path: str, take: dict, shot_id: str, settings: dict
    ) -> str:
        """Best-effort auto-RIFE smoothness pass for a finalized motion take.

        Reads ``auto_rife_smoothness_threshold`` from per-project global_settings
        (default 0.4; ``<= 0`` disables). Runs ``assess_motion_quality`` and records
        the resulting ``smoothness_score`` on the take. When the score is below the
        threshold, applies ``generate_rife_interpolation`` and, on success, returns
        the interpolated path + records the ``FAL_RIFE`` cost. Auto-applies what
        ``diagnose_clip`` (~:2096) only *recommends*. The ai-video-gen skill notes
        RIFE after lip-sync "smooths boundary artifacts", so it is left on for
        dialogue takes too — the smoothness threshold is the gate. Dialogue audio
        survives because ``generate_rife_interpolation`` re-muxes the source clip's
        audio onto the (video-only) RIFE output (``lip_sync._restore_audio_track``);
        fal-ai/rife/video itself returns no audio track.

        Never raises: any failure leaves the original ``video_path`` intact.

        NOTE: ``assess_motion_quality`` calls cv2 WITHOUT the single-thread guard
        (``identity.validator.cv2_single_thread``) used for binding identity scores.
        Accepted here — the smoothness score gates only a best-effort enhancement,
        so non-determinism can at worst trigger or skip one RIFE call, never corrupt
        a take. Revisit if multi-worker finalize is ever enabled.

        Returns:
            The interpolated video path on success, else the original ``video_path``.
        """
        try:
            threshold = float(settings.get("auto_rife_smoothness_threshold", 0.4))
        except (TypeError, ValueError):
            threshold = 0.4
        # math.isfinite rejects nan AND ±inf: nan would skip every take silently
        # (nan<=0 is False, smoothness<nan is False), +inf would RIFE every take
        # (smoothness<inf always True) — both defeat the threshold as a gate.
        if threshold <= 0 or not math.isfinite(threshold) or not video_path or not os.path.exists(video_path):
            return video_path
        # A take already failed the motion floor → it is bound for manual
        # rejection/regeneration; do not spend a cloud RIFE call smoothing it.
        # (The manual action=="rife" path stays ungated — re-smoothing a
        # floor-failed take there is an explicit operator choice.)
        if take.get("metadata", {}).get("motion_floor_failed"):
            return video_path
        try:
            from phase_c_ffmpeg import assess_motion_quality
            mq = assess_motion_quality(video_path)
            smoothness = mq.get("smoothness_score", 1.0)
            take["metadata"]["smoothness_score"] = smoothness
            # Only interpolate genuinely-jittery-but-recoverable motion. A
            # "regenerate" verdict means frozen / heavily-artifacted / unreadable
            # video that RIFE cannot fix (and is what assess_motion_quality returns
            # for short or unopenable clips) — never send those to the cloud.
            if mq.get("recommendation") != "regenerate" and smoothness < threshold:
                rife_out = self._take_output_path(shot_id, take["id"] + "_rife", ".mp4")
                rife_result = generate_rife_interpolation(
                    video_path,
                    rife_out,
                    cost_tracker=self.cost_tracker,
                    shot_id=shot_id,
                    video_id=self.project.get("id", ""),
                )
                if rife_result and os.path.exists(rife_result):
                    take["metadata"]["auto_rife_applied"] = True
                    logger.info(
                        "auto-RIFE applied",
                        extra={
                            "shot_id": shot_id,
                            "smoothness_score": round(smoothness, 3),
                            "threshold": threshold,
                        },
                    )
                    # The production adapter reconciles the FAL request ID and
                    # cost atomically. Preserve the legacy/mocked seam without
                    # double-charging a real durable attempt.
                    durable_rife = None
                    get_latest_attempt = getattr(
                        self.cost_tracker, "get_latest_paid_attempt", None
                    )
                    if callable(get_latest_attempt):
                        try:
                            durable_rife = get_latest_attempt(
                                video_id=self.project.get("id", ""),
                                shot_id=shot_id,
                                engine="FAL_RIFE",
                                operation="rife_interpolation",
                            )
                        except Exception:
                            durable_rife = None
                    if not (
                        isinstance(durable_rife, dict)
                        and durable_rife.get("state") == "succeeded"
                    ):
                        try:
                            self.cost_tracker.record_api_call(
                                "FAL_RIFE",
                                operation="rife_interpolation",
                                shot_id=shot_id,
                                video_id=self.project.get("id", ""),
                            )
                        except Exception:
                            logger.warning(
                                "auto-RIFE legacy cost record skipped",
                                exc_info=True,
                                extra={"shot_id": shot_id},
                            )
                    return rife_result
                logger.warning(
                    "auto-RIFE produced no output; keeping original",
                    extra={"shot_id": shot_id, "smoothness_score": round(smoothness, 3)},
                )
        except Exception:
            logger.warning(
                "auto-RIFE step skipped (error)",
                exc_info=True,
                extra={"shot_id": shot_id},
            )
        return video_path

    def _motion_cost_kwargs(
        self,
        engine: object,
        resolved_shot_type: str,
        video_path: str = "",
        cascade_metadata: Optional[dict] = None,
    ) -> dict:
        """Per-engine cost overrides for a motion generation record.

        SEEDANCE is per-second-billed with shot-type-dependent durations;
        API_COST_USD["SEEDANCE"] is per ~5s, so recompute for the requested
        duration (8s action clips under-record by 38% on the flat figure).

        LTX is per-second-billed with the TRUE dispatched duration surfaced
        by the dispatcher in ``cascade_metadata["duration_s"]`` (fix-S4-money
        2026-07-31: the 8s shared dispatch default otherwise under-records
        ~33% against the flat 6s-floor table figure). Winner-path only —
        billed-but-rejected attempts have no recorded dispatch duration and
        keep the conservative flat floor.

        GEMINI_OMNI has no structured duration kwarg (duration is
        prompt-inferred/variable on this API) so, unlike SEEDANCE, its
        actual length isn't knowable from resolved_shot_type — instead
        ffprobe the downloaded mp4 at ``video_path`` (winner-path only;
        callers with no file to probe pass "" and get the flat table
        estimate). Fails open to the flat API_COST_USD estimate on any
        probe error, missing file, or non-positive duration reading —
        never crash the finalize step and never record a $0.00 cost.

        Other engines use the table default (empty kwargs).
        """
        _engine = str(engine).upper()
        result: dict = {}
        _job_id = (cascade_metadata or {}).get("job_id")
        if isinstance(_job_id, str) and _job_id:
            # Google/Veo and LTX recovery can observe the same completed job
            # more than once.  Preserve the provider identity for every engine;
            # CostTracker namespaces it by provider and ignores duplicate
            # invoice writes durably.
            result["provider_job_id"] = _job_id
        if _engine == "SEEDANCE":
            from cost_tracker import API_COST_USD
            from phase_c_ffmpeg import SEEDANCE_DURATIONS
            _dur = SEEDANCE_DURATIONS.get(resolved_shot_type, 4)
            result["cost_usd"] = round(API_COST_USD["SEEDANCE"] / 5.0 * _dur, 4)
            return result
        if _engine == "LTX":
            _dur = (cascade_metadata or {}).get("duration_s")
            if isinstance(_dur, (int, float)) and not isinstance(_dur, bool) and _dur > 0:
                result["duration_seconds"] = _dur
            _backend = str((cascade_metadata or {}).get("backend") or "").lower()
            if _backend == "native":
                result.update({
                    "backend": "native",
                    "model": str(
                        (cascade_metadata or {}).get("model") or "ltx-2-3-pro"
                    ),
                    "resolution": str(
                        (cascade_metadata or {}).get("resolution") or "1080p"
                    ),
                    "audio": bool((cascade_metadata or {}).get("audio", False)),
                    "pricing_operation": str(
                        (cascade_metadata or {}).get("pricing_operation")
                        or "image_to_video"
                    ),
                })
            return result
        if _engine == "GEMINI_OMNI" and video_path and os.path.exists(video_path):
            from cost_tracker import API_COST_USD
            try:
                _dur = _probe_duration(video_path)
                if _dur and _dur > 0:
                    result["cost_usd"] = round(API_COST_USD["GEMINI_OMNI"] / 5.0 * _dur, 4)
                    return result
            except Exception:
                logger.warning(
                    "GEMINI_OMNI duration probe failed — using flat table cost",
                    exc_info=True,
                    extra={"video_path": video_path},
                )
            return result
        return result

    def _record_billed_rejects(
        self,
        billed_attempts: Optional[list],
        winner_engine: Optional[str],
        shot_id: str,
        resolved_shot_type: str,
        deferred_job: Optional[dict] = None,
    ) -> None:
        """Record spend for billed-but-REJECTED generation attempts.

        A provider bills once it returns a video; download failures and
        aspect-backstop rejections previously cascaded with ZERO record
        (money-gate finding 2026-07-11) — invisible spend, and the blind
        spot got expensive once the fal primaries became the priciest
        engines. The dispatch notes every billed attempt in the cascade-out
        dict (phase_c_ffmpeg._download_video_or_cascade); the winner's own
        attempt is recorded separately (winner-keyed), so ONE occurrence of
        it is subtracted here. Best-effort like the sibling records.
        """
        rejects = [str(e).upper() for e in (billed_attempts or [])]
        if winner_engine:
            _w = str(winner_engine).upper()
            if _w in rejects:
                rejects.remove(_w)
        for engine in rejects:
            try:
                cost_kwargs = self._motion_cost_kwargs(engine, resolved_shot_type)
                # A deferred LTX invocation represents one exact accepted job,
                # not a fresh anonymous reject.  Thread its ID and duration so
                # repeated Check / Resume actions remain cost-idempotent.  The
                # metadata is intentionally used only for the single no-winner
                # deferred record; assigning a winner's job ID to earlier
                # rejected attempts would collapse distinct provider invoices.
                if (
                    winner_engine is None
                    and len(rejects) == 1
                    and isinstance(deferred_job, dict)
                    and str(deferred_job.get("engine") or "").upper() == engine
                ):
                    cost_kwargs = self._motion_cost_kwargs(
                        engine,
                        resolved_shot_type,
                        cascade_metadata=deferred_job,
                    )
                self.cost_tracker.record_api_call(
                    engine,
                    operation="motion_generation_rejected",
                    shot_id=shot_id,
                    video_id=self.project.get("id", ""),
                    **cost_kwargs,
                )
                logger.info(
                    "billed-but-rejected attempt recorded",
                    extra={"shot_id": shot_id, "engine": engine},
                )
            except Exception:
                logger.warning(
                    "billed-reject cost record skipped",
                    exc_info=True,
                    extra={"shot_id": shot_id, "engine": engine},
                )

    def _finalize_motion_take(
        self,
        scene: dict,
        shot: dict,
        take: dict,
        video_path: str,
        *,
        source_image: str,
        target_api: str,
        cc: dict,
        settings: dict,
        resolved_shot_type: str,
        driving_video_path: str = "",
        parent_take_id: str = "",
        intent_override=None,
        revised_prompt: str = "",
        extra_metadata: Optional[dict] = None,
        record_cost: bool = True,
    ) -> dict:
        """Post-generation finalize step for a motion take.

        Extracted from generate_motion_take (F2a) so the storyboard path
        (F2b) can register each per-shot segment as a motion take without
        duplicating this logic.  The normal generate_motion_take path is
        behavior-identical — it calls this method with the same arguments
        it previously inlined.

        Performs in order:
          1. Continuity / identity validation.
          2. Motion-fidelity gate (when driving_video_path is provided).
          3. Provenance fields (parent_take_id / intent / revised_prompt).
          4. take["path"] assignment.
          4b. Optional auto-RIFE smoothness pass (may rebind take["path"] +
              generated_video; records FAL_RIFE cost on apply).
          5. _mutate_shot (appends to motion_takes + sets generated_video).
          6. shot_results update.
          7. _rebuild_review_clips + _save_checkpoint.
          8. Cost record (best-effort).
          9. Budget gate.
          10. MOTION_READY progress event.

        Returns:
            ``{"success": True, "take": stored_take, "video": video_path,
               "identity_score": <float>}``
        """
        shot_id = shot.get("id", "")
        scene_id = scene.get("id", "")

        # 1. Identity / continuity validation (all characters in frame)
        identity_score = self._validate_take_identity(
            video_path, shot, cc, settings, resolved_shot_type, take,
        )

        # 2. Motion fidelity gate
        if driving_video_path and os.path.exists(driving_video_path):
            try:
                from performance.motion_gate import score_motion_fidelity
                motion_score = score_motion_fidelity(video_path, driving_video_path)
                take["metadata"]["motion_fidelity"] = motion_score
                if motion_score is not None:
                    logger.info(
                        "motion fidelity scored",
                        extra={
                            "shot_id": shot_id,
                            "motion_fidelity": round(motion_score, 3),
                        },
                    )
            except Exception:
                logger.warning(
                    "motion-gate score skipped",
                    exc_info=True,
                    extra={"shot_id": shot_id},
                )
                take["metadata"]["motion_fidelity"] = None

            try:
                from performance.motion_gate import needs_remotion
                motion_score = take["metadata"].get("motion_fidelity")
                floor_override = settings.get("motion_quality_threshold")
                # A non-finite / non-numeric override must NOT silently disable the
                # gate: `motion_score < nan` is always False, so a JSON NaN would let
                # any motion through. Validate → fall back to needs_remotion when bad.
                if floor_override is not None:
                    try:
                        floor_override = float(floor_override)
                        if not math.isfinite(floor_override):
                            floor_override = None
                    except (TypeError, ValueError):
                        floor_override = None
                if motion_score is not None:
                    below_floor = (
                        motion_score < floor_override
                        if floor_override is not None
                        else needs_remotion(motion_score, shot_type=resolved_shot_type)
                    )
                else:
                    below_floor = False
                if below_floor:
                    take["metadata"]["motion_floor_failed"] = True
                    logger.warning(
                        "motion below floor",
                        extra={
                            "shot_id": shot_id,
                            "motion_fidelity": round(motion_score, 3),
                            "shot_type": resolved_shot_type,
                        },
                    )
                    self.progress(
                        "MOTION_BELOW_FLOOR",
                        f"Shot {shot_id} motion fidelity {motion_score:.3f} below floor for {resolved_shot_type}",
                        -1,
                        scene_id=scene_id,
                        shot_id=shot_id,
                        motion_fidelity=motion_score,
                        shot_type=resolved_shot_type,
                    )
            except Exception:
                logger.warning(
                    "motion-gate floor check skipped",
                    exc_info=True,
                    extra={"shot_id": shot_id},
                )

        # 3. Provenance + path
        take["path"] = video_path
        if parent_take_id:
            take["parent_take_id"] = parent_take_id
        if intent_override is not None:
            take["intent"] = intent_override.model_dump()
        if revised_prompt:
            take["revised_prompt"] = revised_prompt
        if extra_metadata:
            take["metadata"].update(extra_metadata)

        # 3b. Auto-RIFE smoothness pass (best-effort; may rebind take["path"]).
        video_path = self._maybe_auto_rife(video_path, take, shot_id, settings)
        # Persist project-relative (Product invariant #6); final_vid stays the
        # ABSOLUTE local value for shot_results/cost/RPC-return use below, so a
        # repo move can never make an in-flight cost probe or checkpoint read
        # a path it can't open in THIS session.
        take["path"] = self._to_project_relative(video_path)

        # 4–5. Persist take via mutation
        final_vid = video_path
        self._mark_artifact_version_pending(take)

        def _mutator(_scene: dict, project_shot: dict):
            project_shot.setdefault("motion_takes", []).append(take)
            project_shot["generated_video"] = self._to_project_relative(final_vid)
            # The exact accepted provider job has now produced a canonical
            # take. Its recovery card must disappear in the same atomic write.
            project_shot.pop("deferred_motion_job", None)
            return MutationResult(take, save=True)

        stored_take = self._mutate_shot(shot_id, _mutator)
        stored_take, artifact_error = self._finalize_take_artifact_version(
            shot_id, "motion", stored_take,
        )
        if artifact_error is not None:
            return artifact_error

        # 6. Update shot_results
        self._runstate.shot_results[shot_id] = {
            "image": source_image,
            "video": final_vid,
            "identity_score": identity_score,
            "status": "final_review",
            "take_id": take["id"],
        }

        # 7. Rebuild + checkpoint
        self._host._rebuild_review_clips()
        self._host._save_checkpoint()

        # 8. Cost record (best-effort).
        # Suppressed when record_cost=False so the storyboard batch path (F2b)
        # can record ONE batch cost via cost_tracker directly and then call
        # _finalize_motion_take per-segment without N-counting the generation.
        if record_cost:
            try:
                video_id = self.project.get("id", "")
                cascade_metadata = take.get("cascade_metadata") or {}
                # Key the record on the cascade WINNER, not the requested
                # primary — a SEEDANCE win behind a cheaper primary otherwise
                # accumulates at the primary's price and defeats both the
                # precheck and the post-hoc budget gate (money-gate review
                # 2026-07-11; mirrors the lipsync winner-keyed record below).
                _motion_engine = (
                    cascade_metadata.get("engine")
                    or target_api
                )
                # The dispatcher now settles transaction-backed paid attempts
                # before publishing success.  Keep the legacy record path for
                # callers/test doubles that do not carry that authority marker.
                if not cascade_metadata.get("paid_attempt_id"):
                    self.cost_tracker.record_api_call(
                        _motion_engine,
                        operation="motion_generation",
                        shot_id=shot_id,
                        video_id=video_id,
                        **self._motion_cost_kwargs(
                            _motion_engine,
                            resolved_shot_type,
                            video_path=final_vid,
                            cascade_metadata=cascade_metadata,
                        ),
                    )
            except Exception:
                logger.warning(
                    "motion cost record skipped",
                    exc_info=True,
                    extra={"shot_id": shot_id},
                )
            # Billed-but-REJECTED attempts (provider returned a video that the
            # download or aspect backstop then discarded) bill the invoice but
            # never become the winner — record them too (money-gate finding
            # 2026-07-11; previously accumulated $0).
            self._record_billed_rejects(
                (take.get("cascade_metadata") or {}).get("billed_attempts"),
                (take.get("cascade_metadata") or {}).get("engine") or target_api,
                shot_id,
                resolved_shot_type,
            )

        # 9. Budget gate
        if self.cost_tracker.is_over_budget():
            self.progress(
                "BUDGET_EXCEEDED",
                f"Spend ${self.cost_tracker.spent_usd:.2f} reached budget cap "
                f"${self.cost_tracker.budget_usd:.2f}. Pausing.",
                -1,
                scene_id=scene_id,
                shot_id=shot_id,
                spent=self.cost_tracker.spent_usd,
                budget=self.cost_tracker.budget_usd,
            )
            self._lifecycle.pause()

        # 10. Progress event
        self.progress(
            "MOTION_READY",
            f"Motion take ready for {shot_id}",
            -1,
            scene_id=scene_id,
            shot_id=shot_id,
            video_url=final_vid,
            identity_score=identity_score,
            take_id=take["id"],
            take_kind="motion",
        )
        return {
            "success": True,
            "take": stored_take,
            "video": final_vid,
            "identity_score": identity_score,
        }

    def generate_motion_take(
        self,
        scene_id: str,
        shot_id: str,
        *,
        intent_override: Optional[DirectorialIntent] = None,
        parent_take_id: str = "",
        revised_prompt: str = "",
    ) -> dict:
        project = self._host._refresh_project_snapshot() or self.project
        settings = project.get("global_settings", {})
        scene, shot, shot_index = self._find_shot(shot_id, project, scene_id)
        if not scene or not shot:
            return {"success": False, "error": "Shot not found"}
        pending_artifact = self._recover_pending_take_artifact(
            shot_id, "motion", shot,
        )
        if pending_artifact is not None:
            return pending_artifact
        if shot.get("plan_status") != "approved":
            return {"success": False, "error": "Shot plan must be approved before generating motion"}
        keyframe_take_id = shot.get("approved_keyframe_take_id", "")
        if not keyframe_take_id:
            return {"success": False, "error": "Approved keyframe required before generating motion"}

        source_image = self._resolve_stored_media_path(self._host._resolve_take_path(shot, keyframe_take_id))
        if not source_image or not os.path.exists(source_image):
            return {"success": False, "error": "Approved keyframe asset is missing"}

        existing_deferred = shot.get("deferred_motion_job")
        resuming_deferred = isinstance(existing_deferred, dict)
        if resuming_deferred:
            deferred_engine = str(existing_deferred.get("engine") or "").upper()
            deferred_job_id = existing_deferred.get("job_id")
            deferred_fingerprint = existing_deferred.get("request_fingerprint")
            fingerprint_is_valid = (
                isinstance(deferred_fingerprint, str)
                and len(deferred_fingerprint) == 64
                and all(
                    char in "0123456789abcdefABCDEF"
                    for char in deferred_fingerprint
                )
            )
            if (
                deferred_engine not in {
                    "VEO", "KLING_3_0", "SEEDANCE", "LTX", "RUNWAY_GEN4",
                }
                or not isinstance(deferred_job_id, str)
                or not deferred_job_id
                or (
                    deferred_fingerprint is not None
                    and not fingerprint_is_valid
                )
            ):
                recovery_job = dict(existing_deferred)
                recovery_job["status"] = "recovery_required"
                recovery_job.setdefault("reason", "recovery_binding_unavailable")
                return self._deferred_motion_response(
                    recovery_job,
                    detail=(
                        "This accepted provider job has no safe automatic recovery "
                        "binding. No new provider was started; inspect the server-side "
                        "job record before clearing it."
                    ),
                )

        from workflow_selector import classify_shot_type, WORKFLOW_TEMPLATES
        from domain.scene_decomposer import API_REGISTRY, PURPOSE_API_RANKING

        resolved_shot_type = classify_shot_type(shot)
        # An unresolved accepted provider job owns this shot until it reaches a
        # terminal state. A changed target must not launch a second provider;
        # the dispatcher receives the persisted exact-request binding below.
        raw_api = deferred_engine if resuming_deferred else shot.get("target_api", "AUTO")

        # F1a: Read the optimizer cache to recover the purpose + suggested_video_api
        # that was computed during keyframe generation but not forwarded here.
        # The cache structure is: shot["optimizer_cache"]["spec"]["purpose"] / ["suggested_video_api"]
        opt_cache = sanitize_optimizer_cache(shot.get("optimizer_cache"))
        opt_spec_cached = opt_cache.get("spec") or {}
        cached_purpose = opt_spec_cached.get("purpose", "")
        _dialogue_purposes = {"dialogue_close_up", "talking_head_full"}
        has_dialogue = cached_purpose in _dialogue_purposes

        # Resolve the dialogue voice mode ONCE, before the AUTO/non-AUTO split,
        # so it is bound on every path. It is used unconditionally below — at the
        # audio-embedded tag (_should_tag_audio_embedded arg) and the
        # dialogue_native_audio / overlay-TTS sites. Previously this was bound
        # only inside the `if raw_api == "AUTO"` branch, so a pinned (non-AUTO)
        # shot — the normal production case per scene_decomposer — raised
        # UnboundLocalError on every shot, dialogue or not. P0 regression fix.
        _voice_mode = _dialogue_voice_mode(settings)  # resolve once; reuse at all dialogue sites

        policy_snapshot = _video_policy_runtime_snapshot()
        policy_date = _video_policy_current_date()

        def _automatic_candidate_is_safe(candidate: object) -> bool:
            """Admit active, dispatch-safe automatic suggestions only.

            UI selectability is intentionally not required: active fallback-only
            engines such as LTX are valid optimizer suggestions. Deprecated or
            retired engines are never introduced automatically, while explicit
            persisted targets retain the compatibility dispatch fence below.
            """

            if not isinstance(candidate, str):
                return False
            return bool(filter_automatic_dispatch_candidates(
                (candidate,),
                snapshot=policy_snapshot,
                on_date=policy_date,
                api_engines=settings.get("api_engines"),
                aspect_ratio=settings.get("aspect_ratio", "16:9"),
            ).candidates)

        if raw_api == "AUTO":
            # The historical optimizer/template values are only an ORDERED
            # seed.  Executability is decided once below by the typed policy.
            template = WORKFLOW_TEMPLATES.get(
                resolved_shot_type,
                WORKFLOW_TEMPLATES["medium"],
            )
            cached_suggestion = opt_spec_cached.get("suggested_video_api", "")
            ordered_seed: list[object] = []
            if (
                cached_suggestion
                and cached_suggestion != "AUTO"
                and _automatic_candidate_is_safe(cached_suggestion)
            ):
                ordered_seed.append(cached_suggestion)
            ordered_seed.append(template.get("target_api", "AUTO"))
            ordered_seed.extend(template.get("video_fallbacks") or ())

            # Preserve dialogue routing using only policy-eligible engines.
            # GEMINI_OMNI is re-admitted when its runtime is ready; otherwise
            # the same typed filter naturally promotes VEO_NATIVE.
            if has_dialogue:
                native_audio_seed = [
                    engine
                    for engine in PURPOSE_API_RANKING.get(cached_purpose, ())
                    if (
                        API_REGISTRY.get(engine, {}).get("native_audio")
                        and API_REGISTRY.get(engine, {}).get("modality") == "video"
                        and _automatic_candidate_is_safe(engine)
                    )
                ]
                if native_audio_seed:
                    if _voice_mode == "native":
                        ordered_seed = native_audio_seed
                    else:
                        ordered_seed = [*native_audio_seed, *ordered_seed]
        else:
            # A persisted explicit target is a pin, not a request to search the
            # global default cascade.
            ordered_seed = [raw_api]

        policy_filter = (
            filter_automatic_dispatch_candidates
            if raw_api == "AUTO"
            else filter_dispatch_candidates
        )
        dispatch_policy = policy_filter(
            ordered_seed,
            snapshot=policy_snapshot,
            on_date=policy_date,
            api_engines=settings.get("api_engines"),
            aspect_ratio=settings.get("aspect_ratio", "16:9"),
        )
        if not dispatch_policy.candidates:
            return _target_policy_failure(raw_api, dispatch_policy)

        target_api = dispatch_policy.primary
        video_fallbacks = (
            list(dispatch_policy.fallbacks)
            if raw_api == "AUTO"
            else None
        )
        policy_rejections = _policy_rejections(dispatch_policy)

        # Continuity enrichment is deliberately after the dispatch fence: an
        # unavailable explicit target or empty AUTO chain exits before any
        # downstream generation preparation.
        prev_shot = scene.get("shots", [])[shot_index - 1] if shot_index > 0 else None
        approved_anchor = self._resolve_previous_approved_keyframe(scene, shot_index)
        enhanced = self.continuity.enhance_shot_prompt(
            shot,
            scene,
            prev_shot,
            shot_index,
            continuity_reference_path=approved_anchor,
        )
        cc = enhanced.get("continuity_config", {})

        # Pre-spend budget gate (STRATEGIC_REVIEW-2026-06-10 P0-2 / ADR-022):
        # all PER-TAKE motion spend routes through this function (web
        # endpoint, phase loop, regenerate, iterate, retry); the F2b
        # storyboard BATCH launch is gated separately in
        # cinema/phases/motion_render.py. Soft cap: API_COST_USD estimates
        # are ±30% and price the resolved primary plus structurally mandatory
        # post-processing. A fallback-cascade winner can still cost several
        # times the admitted estimate. The motion phase loop aborts on the
        # structured "budget" refusal below. Dialogue overlay shots also require
        # the F1b lip-sync pass after video generation, so precheck that required
        # second call with the same multi-call budget-envelope pattern.
        #
        # Duration-aware pricing for the two genuinely per-second-billed
        # video engines (money-gate finding 2026-07-30/31): _pre_spend_duration_s
        # is non-None only for LTX/SEEDANCE (see _motion_pre_spend_duration_s),
        # so every other engine falls through to the exact flat-table call
        # shape this gate used before — CostTracker.estimate_call_cost_usd /
        # would_exceed reuse record_api_call's own rate/round logic, so the
        # pre-check and the eventual post-fact record can never drift apart.
        engine_info = API_REGISTRY.get(target_api.upper(), {})
        native_audio_precheck: Optional[bool] = None
        if target_api.upper() == "VEO_NATIVE":
            try:
                from veo_native import veo_native_audio_available

                native_audio_precheck = bool(veo_native_audio_available())
            except Exception:
                # Unknown backend capability is budgeted conservatively as a
                # second lip-sync call; dispatch can later prove Vertex audio.
                native_audio_precheck = False
        needs_lipsync_precheck = has_dialogue and not _should_tag_audio_embedded(
            engine_info,
            has_dialogue,
            _voice_mode,
            native_audio_generated=native_audio_precheck,
        )
        _pre_spend_duration_s = _motion_pre_spend_duration_s(target_api, resolved_shot_type)
        pending_commitment_usd = self._pending_motion_reservation_usd(
            project,
            exclude_shot_id=shot_id if resuming_deferred else "",
        )
        if resuming_deferred:
            # Recovery polls/downloads an already accepted job. Charging it as
            # a fresh admission can strand paid work behind the budget cap.
            would_exceed_budget = False
        elif needs_lipsync_precheck:
            from cost_tracker import API_COST_USD, CostTracker

            estimated_cost = (
                CostTracker.estimate_call_cost_usd(target_api, _pre_spend_duration_s)
                + API_COST_USD.get("LIPSYNC_DEFAULT", 0.0)
            )
            would_exceed_budget = self.cost_tracker.would_exceed_cost(
                estimated_cost + pending_commitment_usd
            )
        elif _pre_spend_duration_s is not None:
            if pending_commitment_usd:
                from cost_tracker import CostTracker

                would_exceed_budget = self.cost_tracker.would_exceed_cost(
                    CostTracker.estimate_call_cost_usd(
                        target_api,
                        _pre_spend_duration_s,
                    )
                    + pending_commitment_usd
                )
            else:
                would_exceed_budget = self.cost_tracker.would_exceed(
                    target_api, duration_seconds=_pre_spend_duration_s
                )
        else:
            if pending_commitment_usd:
                from cost_tracker import CostTracker

                would_exceed_budget = self.cost_tracker.would_exceed_cost(
                    CostTracker.estimate_call_cost_usd(target_api)
                    + pending_commitment_usd
                )
            else:
                would_exceed_budget = self.cost_tracker.would_exceed(target_api)

        if would_exceed_budget:
            if needs_lipsync_precheck:
                budget_detail = (
                    f"Estimated {target_api} motion plus mandatory lip-sync cost "
                    f"${estimated_cost:.3f} would push spend "
                    f"${self.cost_tracker.spent_usd:.2f} past budget cap "
                    f"${self.cost_tracker.budget_usd:.2f}. Pausing before generation."
                )
            else:
                budget_detail = (
                    f"Estimated {target_api} cost would push spend "
                    f"${self.cost_tracker.spent_usd:.2f} past budget cap "
                    f"${self.cost_tracker.budget_usd:.2f}. Pausing before generation."
                )
            self.progress(
                "BUDGET_EXCEEDED",
                budget_detail,
                -1,
                scene_id=scene_id,
                shot_id=shot_id,
                spent=self.cost_tracker.spent_usd,
                budget=self.cost_tracker.budget_usd,
            )
            self._lifecycle.pause()
            return {
                "success": False,
                "error": "Budget cap reached — motion generation not started",
                # Structured kind: the motion phase loop keys its abort on
                # this (cinema/phases/motion_render.py), not on string-parsing
                # the human-facing error.
                "error_kind": "budget",
            }

        take = make_take(
            "motion",
            source_take_id=keyframe_take_id,
            metadata={
                "scene_id": scene_id,
                "shot_id": shot_id,
                "target_api": target_api,
                "shot_type": resolved_shot_type,
            },
        )
        vid_path = self._take_output_path(shot_id, take["id"], ".mp4")
        self._runstate.update_progress_pointer("MOTION", scene_id, shot_id)
        self.progress(
            "MOTION",
            f"Generating motion for {shot_id}",
            -1,
            scene_id=scene_id,
            shot_id=shot_id,
            take_id=take["id"],
            # P1-3 (NF-3): the engine being TRIED — the cascade winner may
            # differ; the take's cascade_metadata records the actual one.
            engine=target_api,
        )

        # Resolve performance-capture driving video (handoff §8). When the
        # performance phase produced an approved take, surface its path here
        # so generate_ai_video can pass it to native engines that accept a
        # motion reference (Veo / Sora / Runway). Engines that don't accept
        # one (Kling, LTX) fall through silently.
        performance_take_id = shot.get("approved_performance_take_id", "")
        driving_video_path = ""
        if performance_take_id:
            driving_video_path = self._resolve_stored_media_path(
                self._host._resolve_take_path(shot, performance_take_id) or ""
            )

        # Build a lightweight PipelineContext so UI knobs (api_engines filter,
        # cascade_retry_limit) flow through to generate_ai_video. Same pattern
        # as the generate_ai_broll call site above (line ~395).
        motion_ctx = PipelineContext(global_settings=settings)

        # Compute dialogue_native_audio: True only when dialogue + native mode.
        # overlay mode (default) keeps Veo silent; the F1b lipsync pass overlays TTS.
        dialogue_native_audio = has_dialogue and _voice_mode == "native"

        # Task 6: For overlay-mode dialogue, resolve per-shot TTS before generating
        # the video so we can size the Veo clip to the speech duration.
        # _f1b_audio holds the resolved audio path for reuse in the F1b block
        # (avoids a redundant _ensure_scene_audio call there).
        _f1b_audio: Optional[str] = None
        _veo_duration: str = "8s"  # default: unchanged for non-dialogue / native
        if has_dialogue and _voice_mode == "overlay":
            _f1b_audio = _resolve_f1b_audio(
                self._host, shot, scene, self.project.get("characters", []), _voice_mode
            )
            if _f1b_audio:
                try:
                    _speech_secs = _probe_duration(_f1b_audio)
                    _veo_duration = _clamp_veo_duration(_speech_secs)
                except Exception:
                    logger.warning(
                        "[DIALOGUE] shot=%s: could not probe TTS duration; using default '8s'",
                        shot_id,
                        exc_info=True,
                    )

        _video_cascade: dict = {
            "policy_rejections": list(policy_rejections),
        }
        if resuming_deferred and deferred_engine == "LTX":
            _video_cascade["expected_ltx_job"] = {
                "engine": "LTX",
                "job_id": deferred_job_id,
            }
            if fingerprint_is_valid:
                # Backward-compatible with pre-fix recovery records. New
                # records intentionally omit this request-derived hash from
                # the public project JSON; the exact provider job ID plus the
                # adapter's private sidecar is sufficient to resume safely.
                _video_cascade["expected_ltx_job"]["request_fingerprint"] = (
                    deferred_fingerprint
                )
        # AUTO remains AUTO at the public dispatch boundary.  The controller
        # retains ``target_api`` as the resolved primary for budget/progress/
        # take metadata, while the public dispatcher independently re-filters
        # this already ordered safe chain.  Explicit targets stay concrete and
        # pinned; no caller-side flag or admission object can bypass that
        # second fail-closed check.
        dispatch_target_api = "AUTO" if raw_api == "AUTO" else target_api
        dispatch_fallbacks = (
            [target_api, *video_fallbacks]
            if raw_api == "AUTO"
            else None
        )
        # Providers share one output path across the cascade.  Keep that
        # mutable candidate isolated from the canonical take destination:
        # aspect rejection may leave a non-empty file even though the
        # dispatcher truthfully returns None.  Only the exact owned candidate,
        # still a non-empty regular file, may replace ``vid_path``.  The unique
        # tempfile is owned by this call, so rejection cleanup cannot delete a
        # pre-existing take or trust an unrelated/canonical return path.
        candidate_fd, candidate_vid = tempfile.mkstemp(
            prefix=f".{os.path.basename(vid_path)}.",
            suffix=".candidate.mp4",
            dir=os.path.dirname(vid_path) or ".",
        )
        os.close(candidate_fd)
        final_vid = None
        try:
            temp_vid = generate_ai_video(
                source_image,
                shot.get("camera", "zoom_in_slow"),
                dispatch_target_api,
                candidate_vid,
                pacing="calculated",
                character_id=cc.get("primary_character", ""),
                multi_angle_refs=cc.get("multi_angle_refs", []),
                negative_prompt=shot.get("negative_constraints", ""),
                shot_type=resolved_shot_type,
                video_fallbacks=dispatch_fallbacks,
                driving_video_path=driving_video_path,
                has_dialogue=has_dialogue,
                dialogue_native_audio=dialogue_native_audio,
                duration=_veo_duration,
                ctx=motion_ctx,
                _cascade_out=_video_cascade,
                cost_tracker=self.cost_tracker,
                shot_id=shot_id,
                video_id=str(project.get("id", "")),
            )
            try:
                returned_path = os.fspath(temp_vid) if temp_vid else ""
            except TypeError:
                returned_path = ""
            returned_owned_candidate = (
                bool(returned_path)
                and os.path.abspath(returned_path)
                == os.path.abspath(candidate_vid)
            )
            if returned_owned_candidate:
                try:
                    candidate_stat = os.stat(
                        candidate_vid,
                        follow_symlinks=False,
                    )
                    candidate_is_valid = (
                        stat.S_ISREG(candidate_stat.st_mode)
                        and candidate_stat.st_size > 0
                    )
                except OSError:
                    candidate_is_valid = False
                if candidate_is_valid:
                    os.replace(candidate_vid, vid_path)
                    final_vid = vid_path
        finally:
            # On failure/rejection the owned candidate may contain a billed
            # provider output. Retain its exact bytes as an internal immutable
            # version before removing the mutable temp path. It is evidence,
            # not a selectable take, but artifact history must not silently
            # lose a paid output merely because a local gate rejected it.
            retained_reject = False
            candidate_has_bytes = False
            if final_vid is None:
                try:
                    candidate_stat = os.stat(candidate_vid, follow_symlinks=False)
                    candidate_has_bytes = (
                        stat.S_ISREG(candidate_stat.st_mode)
                        and candidate_stat.st_size > 0
                    )
                except OSError:
                    candidate_has_bytes = False
                if candidate_has_bytes:
                    rejected_take = {
                        **take,
                        "path": candidate_vid,
                        "status": "rejected",
                        "metadata": {
                            **(take.get("metadata") or {}),
                            "rejection_stage": "motion_dispatch_or_validation",
                        },
                        "cascade_metadata": dict(_video_cascade),
                    }
                    try:
                        from cinema.artifact_indexing import record_take_version

                        record_take_version(
                            str(project.get("id") or ""),
                            shot_id,
                            "motion",
                            rejected_take,
                            project_snapshot=project,
                            project_root=self.project_dir,
                        )
                        retained_reject = True
                    except Exception:
                        _video_cascade["rejected_artifact_retention_error"] = True
                        logger.exception(
                            "Rejected motion candidate could not be retained; leaving recovery bytes in place",
                            extra={"shot_id": shot_id, "candidate_path": candidate_vid},
                        )
            if retained_reject or not candidate_has_bytes:
                try:
                    os.remove(candidate_vid)
                except FileNotFoundError:
                    pass
                except OSError:
                    logger.warning(
                        "Unable to remove rejected motion candidate",
                        exc_info=True,
                        extra={"shot_id": shot_id, "candidate_path": candidate_vid},
                    )

        if not final_vid or not os.path.exists(final_vid):
            blocked_attempt = _video_cascade.get("budget_blocked_attempt")
            if isinstance(blocked_attempt, dict):
                self.progress(
                    "BUDGET_EXCEEDED",
                    f"Atomic reservation for {blocked_attempt.get('engine', target_api)} was refused; no provider was started.",
                    -1,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    spent=self.cost_tracker.spent_usd,
                    budget=self.cost_tracker.budget_usd,
                )
                self._lifecycle.pause()
                return {
                    "success": False,
                    "error": "Budget cap reached — paid attempt reservation refused",
                    "error_kind": "budget",
                    "attempt_id": blocked_attempt.get("attempt_id"),
                }
            if _video_cascade.get("policy_error"):
                if resuming_deferred:
                    return self._deferred_motion_response(
                        existing_deferred,
                        detail=(
                            f"The accepted {deferred_engine} job is still reserved, but current "
                            "provider policy or configuration blocks recovery. No "
                            "new provider was started."
                        ),
                    )
                return {
                    "success": False,
                    **_video_cascade["policy_error"],
                    "rejections": list(
                        _video_cascade.get("policy_rejections", ())
                    ),
                }
            deferred_job = _video_cascade.get("deferred_job")
            if isinstance(deferred_job, dict):
                # A provider-accepted job is not a generic generation failure.
                # Expose only operator-safe recovery fields: local sidecar paths,
                # request fingerprints, and raw provider detail stay server-side.
                self._record_billed_rejects(
                    _video_cascade.get("billed_attempts"),
                    None,
                    shot_id,
                    resolved_shot_type,
                    deferred_job=deferred_job,
                )
                stored_deferred = self._public_deferred_motion_job(deferred_job)
                stored_deferred["updated_at"] = datetime.now(timezone.utc).isoformat()
                duration_s = stored_deferred.get("duration_s")
                if stored_deferred.get("billed") is not True:
                    try:
                        from cost_tracker import CostTracker

                        reserved = CostTracker.estimate_call_cost_usd(
                            str(stored_deferred.get("engine") or ""),
                            duration_s
                            if isinstance(duration_s, (int, float))
                            else _pre_spend_duration_s,
                        )
                    except Exception:
                        reserved = 0.0
                    if reserved > 0:
                        stored_deferred["reserved_cost_usd"] = round(reserved, 6)
                try:
                    persisted = self._persist_deferred_motion_job(
                        shot_id,
                        stored_deferred,
                    )
                    if persisted is None:
                        raise RuntimeError(
                            "project shot was unavailable during persistence"
                        )
                except Exception:
                    logger.exception(
                        "Unable to persist deferred provider job",
                        extra={
                            "shot_id": shot_id,
                            "engine": stored_deferred.get("engine", "Provider"),
                        },
                    )
                    # The sidecar remains the recovery authority. Return a
                    # truthful recovery-required response instead of allowing
                    # the caller to interpret this as a generic failure.
                    stored_deferred["status"] = "recovery_required"
                    stored_deferred["reason"] = "project_recovery_record_write_failed"
                return self._deferred_motion_response(stored_deferred)
            if resuming_deferred:
                # The bound adapter returned no deferred descriptor, so the
                # accepted job reached a terminal non-success state. Release
                # the durable reservation; a later operator action may start
                # genuinely new work, but this invocation never cascades.
                try:
                    cleared = self._persist_deferred_motion_job(shot_id, None)
                    if cleared is None:
                        raise RuntimeError("project shot was unavailable during clear")
                except Exception:
                    logger.exception(
                        "Unable to clear terminal deferred provider job",
                        extra={"shot_id": shot_id, "engine": deferred_engine},
                    )
                    return self._deferred_motion_response(
                        existing_deferred,
                        detail=(
                            "The provider job reached a terminal state, but its recovery "
                            "record could not be cleared safely. No fallback was started."
                        ),
                    )
                return {
                    "success": False,
                    "code": "provider_job_failed",
                    "error": (
                        "The deferred provider job ended without a publishable video. "
                        "Its reservation was cleared; no fallback was started."
                    ),
                }
            # Total cascade failure can still carry BILLED attempts (a provider
            # returned a video that then failed download / aspect backstop).
            # Record them before bailing or the spend is invisible to the gate.
            self._record_billed_rejects(
                _video_cascade.get("billed_attempts"), None, shot_id, resolved_shot_type,
            )
            return {"success": False, "error": "Video generation failed"}
        if "cascade_metadata" in _video_cascade:
            take["cascade_metadata"] = _video_cascade["cascade_metadata"]
        if _video_cascade.get("policy_rejections"):
            take.setdefault("cascade_metadata", {})["policy_rejections"] = list(
                _video_cascade["policy_rejections"]
            )
        # Billed-attempt trail rides along for the finalize cost record
        # unconditionally. A successful winner can follow one or more billed
        # rejects, including repeated attempts across cooldown cycles.
        if _video_cascade.get("billed_attempts"):
            take.setdefault("cascade_metadata", {})["billed_attempts"] = list(
                _video_cascade["billed_attempts"]
            )

        # F1a: Tag the take when the winning engine carries embedded voice audio.
        # Check the API_REGISTRY native_audio flag rather than hardcoding a name.
        # The assembler (F1b) reads audio_embedded=True to skip the TTS+mux path.
        # Task 4: gate behind native mode — in overlay mode (default) the tag is NOT
        # set so the F1b TTS overlay pass at :1267 runs and overlays the per-shot TTS.
        winning_engine = (
            _video_cascade.get("cascade_metadata", {}).get("engine", target_api).upper()
        )
        engine_info = API_REGISTRY.get(winning_engine, {})
        verified_native_audio = (
            _video_cascade.get("cascade_metadata", {})
            .get("native_audio_generated")
        )
        if _should_tag_audio_embedded(
            engine_info,
            has_dialogue,
            _voice_mode,
            native_audio_generated=verified_native_audio,
        ):
            take["metadata"]["audio_embedded"] = True

        # F1b: Write has_dialogue to the take so the auto-approve gate can
        # distinguish "no-score because no dialogue" from "no-score because
        # lipsync was skipped for a dialogue shot" (the blind-gate bug).
        take["metadata"]["has_dialogue"] = has_dialogue

        # F1b: Mandatory lipsync pass for dialogue shots that are NOT audio-embedded.
        # Mirrors the apply_correction "lip_sync" action path (controller.py:1524-1543)
        # but runs unconditionally during take generation so the gate always has a score.
        #
        # NOTE: generate_lip_sync_video's "mode" param is "auto"/"overlay"/"generation",
        # NOT an engine name.  The optimizer cache carries suggested_lipsync (e.g.
        # SYNC_SO_V3) as an engine-level hint, but there is no engine-selection knob on
        # generate_lip_sync_video — the engine cascade inside lipsync_overlay/generation
        # handles selection internally.  We pass mode="auto" (same as the manual
        # lip_sync correction action) and let the cascade choose.
        if has_dialogue and not take["metadata"].get("audio_embedded"):
            try:
                from lip_sync import (
                    LIPSYNC_QUALITY_FAIL,
                    LIPSYNC_QUALITY_PASS,
                    LIPSYNC_QUALITY_UNKNOWN,
                    classify_lipsync_quality,
                    generate_lip_sync_video,
                    validate_lipsync_quality,
                )
                # chars_for_sync drives the ref/lip target — in-frame chars with
                # scene fallback (only the visible character's face is synced).
                chars_for_sync = shot.get("characters_in_frame", []) or scene.get("characters_present", [])
                project_for_sync = self.project
                # Task 6: reuse the per-shot audio resolved before generate_ai_video
                # (avoids a redundant _ensure_scene_audio call and guarantees the
                # overlay uses the same sized audio the Veo clip was sized for).
                # _f1b_audio is None for native mode / non-dialogue; fall back to
                # _ensure_scene_audio in that case (preserves legacy behaviour).
                if _f1b_audio is not None:
                    audio_path_for_sync = _f1b_audio
                else:
                    # Scene audio is a SCENE-scoped artifact: key with scene-level
                    # characters (scene_characters helper), not the in-frame subset —
                    # or the cache key diverges from the pipeline writer → paid TTS
                    # regen + off-frame lines voiced by the wrong character
                    # (9aed3ce bug class, ticket T-E Bug site B).
                    audio_path_for_sync = self._host._ensure_scene_audio(
                        scene, _scene_characters(project_for_sync.get("characters", []), scene)
                    )
                primary_ref_for_sync = (
                    get_reference_image(project_for_sync, chars_for_sync[0])
                    if chars_for_sync else None
                )
                if audio_path_for_sync and primary_ref_for_sync:
                    lipsync_out = self._take_output_path(shot_id, take["id"] + "_ls", ".mp4")
                    _ls_cascade: dict = {}
                    _rejected_lipsync_count = 0

                    def _retain_f1b_lipsync_reject(evidence: dict) -> dict:
                        nonlocal _rejected_lipsync_count
                        _rejected_lipsync_count += 1
                        return _record_rejected_lipsync_candidate(
                            project=project,
                            project_root=self.project_dir,
                            shot_id=shot_id,
                            candidate_id=(
                                f"{take['id']}-ls-reject-{_rejected_lipsync_count}"
                            ),
                            source_take_id=str(
                                take.get("source_take_id") or keyframe_take_id
                            ),
                            evidence=evidence,
                            audio_path=str(audio_path_for_sync),
                            character_reference_path=str(primary_ref_for_sync),
                            input_video_path=str(final_vid),
                            mode=str(settings.get("lip_sync_mode", "auto")),
                        )

                    ls_result = generate_lip_sync_video(
                        character_image_path=primary_ref_for_sync,
                        audio_path=audio_path_for_sync,
                        output_path=lipsync_out,
                        existing_video_path=final_vid,
                        mode=settings.get("lip_sync_mode", "auto"),
                        settings=settings,
                        _cascade_out=_ls_cascade,
                        cost_tracker=self.cost_tracker,
                        shot_id=shot_id,
                        video_id=self.project.get("id", ""),
                        _retain_rejected_candidate=_retain_f1b_lipsync_reject,
                    )
                    if _ls_cascade.get("rejected_candidate_retention_failed"):
                        return {
                            "success": False,
                            "error": (
                                "A paid lip-sync candidate failed local validation, "
                                "but its immutable artifact record could not be written. "
                                "Fallback stopped and recovery bytes were left in place."
                            ),
                            "code": "lipsync_artifact_retention_failed",
                            "provider_recovery_required": True,
                            "rejected_candidate": _ls_cascade.get(
                                "recovery_candidate", {}
                            ),
                        }
                    if ls_result and os.path.exists(ls_result):
                        # Replace take video with the lip-synced output.
                        final_vid = ls_result
                        _ls_cascade_metadata = _ls_cascade.get("cascade_metadata", {})
                        _ls_state = _ls_cascade_metadata.get("validation_state")
                        if _ls_state in {
                            LIPSYNC_QUALITY_PASS,
                            LIPSYNC_QUALITY_FAIL,
                            LIPSYNC_QUALITY_UNKNOWN,
                        }:
                            # The cascade gate already classified this exact
                            # output. Preserve that evidence so a second probe
                            # cannot launder an UNKNOWN fallback into PASS.
                            _ls_score = _ls_cascade_metadata.get("score")
                        else:
                            # Backward-compatible path for older/mocked lip-sync
                            # implementations that do not emit gate metadata.
                            _ls_score = validate_lipsync_quality(
                                ls_result, audio_path_for_sync, _generation=True
                            )
                            _ls_state = classify_lipsync_quality(
                                _ls_score,
                                _finite_or(
                                    settings.get("lipsync_validation_threshold", 0.65),
                                    0.65,
                                ),
                            )
                        take["metadata"]["lipsync_score"] = _ls_score
                        take["metadata"]["lipsync_validation_state"] = _ls_state
                        if "cascade_metadata" in _ls_cascade:
                            take["metadata"]["lipsync_cascade"] = _ls_cascade["cascade_metadata"]
                        # Chunk 3 / Task 7: mark that this clip already carries
                        # per-shot TTS so the assembler (_build_scene_packages)
                        # suppresses the scene-level TTS mux and avoids double-voice.
                        take["metadata"]["dialogue_audio_in_clip"] = True
                        _ls_score_display = (
                            "UNKNOWN" if _ls_score is None else f"{_ls_score:.3f}"
                        )
                        logger.info(
                            "[DIALOGUE] shot=%s audio=standalone+lipsync score=%s state=%s",
                            shot_id,
                            _ls_score_display,
                            _ls_state,
                        )
                        # Cost-track the lipsync generation (Tier F NEW-2: lipsync was
                        # previously untracked). Attribute to the winning cascade engine,
                        # namespaced LIPSYNC_<engine> so the cost key can't collide with a
                        # same-named video engine (e.g. lipsync "kling" vs KLING_NATIVE)
                        # and resolves against the LIPSYNC_* rows in API_COST_USD.
                        if not _ls_cascade.get("paid_cost_recorded"):
                            try:
                                _ls_engine = (_ls_cascade.get("cascade_metadata", {})
                                              .get("engine") or "default")
                                self.cost_tracker.record_api_call(
                                    _lipsync_cost_api_key(_ls_engine), operation="lipsync",
                                    shot_id=shot_id, video_id=self.project.get("id", ""),
                                )
                            except Exception:
                                logger.warning("lipsync cost record skipped", exc_info=True, extra={"shot_id": shot_id})
                    else:
                        # No scorer result exists: this is UNKNOWN, not a
                        # measured numeric failure.
                        take["metadata"]["lipsync_score"] = None
                        take["metadata"]["lipsync_validation_state"] = "UNKNOWN"
                        logger.warning(
                            "[DIALOGUE] shot=%s audio=DEGRADED-no-lipsync "
                            "(generate_lip_sync_video returned no output)",
                            shot_id,
                        )
                else:
                    # Missing audio or character ref — cannot run lipsync.
                    take["metadata"]["lipsync_score"] = None
                    take["metadata"]["lipsync_validation_state"] = "UNKNOWN"
                    logger.warning(
                        "[DIALOGUE] shot=%s audio=DEGRADED-no-lipsync "
                        "(missing audio_path=%s or primary_ref=%s)",
                        shot_id,
                        audio_path_for_sync,
                        primary_ref_for_sync,
                    )
            except Exception:
                # Lipsync pass is advisory for generation; never fail the take.
                # No scorer result exists, so preserve UNKNOWN evidence.
                take["metadata"]["lipsync_score"] = None
                take["metadata"]["lipsync_validation_state"] = "UNKNOWN"
                logger.warning(
                    "[DIALOGUE] shot=%s audio=DEGRADED-lipsync-exception",
                    shot_id,
                    exc_info=True,
                )
        elif has_dialogue and take["metadata"].get("audio_embedded"):
            # Native-audio take: voice is baked in at generation time.
            # Audio presence proves only that dialogue exists in the clip; it
            # does not measure audio/visual synchronization. Preserve that as
            # UNKNOWN instead of fabricating a perfect score.
            take["metadata"]["lipsync_score"] = None
            take["metadata"]["lipsync_validation_state"] = "UNKNOWN"
            logger.info(
                "[DIALOGUE] shot=%s audio=embedded-native lipsync=UNKNOWN",
                shot_id,
            )
        # Non-dialogue shots: no lipsync_score written → gate defaults to 1.0 (N/A).

        # F2a: delegate the post-generation finalize step to the reusable helper.
        # Behavior is identical to the inlined block this replaces — same take shape,
        # same cost call, same shot_results, same continuity validation.
        return self._finalize_motion_take(
            scene,
            shot,
            take,
            final_vid,
            source_image=source_image,
            target_api=target_api,
            cc=cc,
            settings=settings,
            resolved_shot_type=resolved_shot_type,
            driving_video_path=driving_video_path,
            parent_take_id=parent_take_id,
            intent_override=intent_override,
            revised_prompt=revised_prompt,
        )

    def regenerate_shot(
        self,
        scene_id: str,
        shot_id: str,
        negative_prompt: Optional[str] = None,
    ) -> dict:
        """Compatibility wrapper for the older regenerate endpoint.

        negative_prompt, when provided, is threaded into generate_keyframe_take
        for the keyframe branch (shot has no approved keyframe yet). It is NOT
        persisted on the shot, and does NOT apply to the motion branch:
        generate_motion_take has no negative_prompt parameter and derives any
        negative from the shot's stored constraints. For a clean full restart
        that always regenerates the keyframe (and so always honors
        negative_prompt), use restart_shot (POST /restart).
        """
        project = self._host._refresh_project_snapshot() or self.project
        _, shot, _ = self._find_shot(shot_id, project, scene_id)
        if not shot:
            return {"success": False, "error": "Shot not found"}
        if shot.get("approved_keyframe_take_id"):
            return self.generate_motion_take(scene_id, shot_id)
        return self.generate_keyframe_take(scene_id, shot_id, negative_prompt=negative_prompt)

    def restart_shot(
        self,
        scene_id: str,
        shot_id: str,
        positive_prompt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
    ) -> dict:
        """Full restart: clear every downstream approval and regenerate the keyframe.

        Pairs with the UI's "Regenerate" action (vs "Generate another keyframe"
        which adds a candidate take into the existing array). Take history
        (keyframe_takes / performance_takes / motion_takes / postprocess_variants)
        is PRESERVED so the operator can still look back at prior attempts —
        only the approval pointers are reset.

        Reset fields:
          approved_keyframe_take_id
          approved_performance_take_id
          approved_motion_take_id
          approved_final_take_id
          performance_engine  (re-routed by generate_performance_take next time)

        plan_status is intentionally NOT touched — restart regenerates from
        the same approved plan rather than re-running the plan-review gate.

        positive_prompt, when provided, replaces the shot's stored prompt so
        the next keyframe generation uses the edited text. negative_prompt is
        threaded into generate_keyframe_take but not persisted on the shot
        (matches the legacy regenerate behavior).
        """
        def _mutator(_scene: dict, shot: dict):
            shot["approved_keyframe_take_id"] = ""
            shot["approved_performance_take_id"] = ""
            shot["approved_motion_take_id"] = ""
            shot["approved_final_take_id"] = ""
            if "performance_engine" in shot:
                shot["performance_engine"] = ""
            if positive_prompt:
                shot["prompt"] = positive_prompt
            return MutationResult(
                {"shot_id": shot_id, "restarted": True}, save=True,
            )

        result = self._mutate_shot(shot_id, _mutator)
        if not result:
            return {"success": False, "error": "Shot not found"}
        return self.generate_keyframe_take(
            scene_id,
            shot_id,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
        )

    def regenerate_with_intent(
        self,
        scene_id: str,
        shot_id: str,
        take_id: str,
        intent: DirectorialIntent,
        *,
        project_id: str = "",
    ) -> dict:
        """S16: directorial iteration — translate intent and regenerate the appropriate take stage.

        Calls ``llm.director.intent_translator`` to produce a revised prompt + params_delta +
        anchor_refs, then routes to the matching take generator (keyframe / performance / motion)
        with backward-compat kwargs so the new TakeRecord carries:
          - ``parent_take_id`` pointing at the source take
          - ``intent``         the original DirectorialIntent (serialised)
          - ``revised_prompt`` the LLM-translated prompt

        Per S16 disambiguation:
          - params_delta is stored in take.metadata["params_delta"] only (S18 will use it).
          - anchor_refs is stored in take.metadata["anchor_refs"] only (S18 will wire continuity).
          - intent_translator logging is handled by llm/director.py — we do NOT log here.
        """
        from llm.director import intent_translator

        project = self._host._refresh_project_snapshot() or self.project
        scene, shot, _ = self._find_shot(shot_id, project, scene_id)
        if not scene or not shot:
            return {"success": False, "error": "Shot not found"}

        # Find the parent take for context.
        collection_name, parent_take = self._find_take(shot, take_id)
        if parent_take is None:
            return {"success": False, "error": f"Take {take_id} not found on shot {shot_id}"}

        take_context = {
            "take_id": take_id,
            "kind": parent_take.get("kind", ""),
            "prompt": parent_take.get("metadata", {}).get("prompt", shot.get("prompt", "")),
            "metadata": parent_take.get("metadata", {}),
            "shot_id": shot_id,
        }
        scene_context = {
            "id": scene_id,
            "title": scene.get("title", ""),
            "action": scene.get("action", ""),
            # S18 F2 fold (operator Lane V #4 verification-report 2026-05-25T15-37-08Z),
            # corrected post Lane V #6 (2026-05-25T18-20-57Z F1): original S16 filter
            # checked only approved_keyframe/motion, missing the performance gate. All
            # three runtime fields use the `approved_*_take_id` shape on shot dicts
            # (production writes at controller.py:758, review/controller.py:590,
            # web_server.py:711). The bare `performance_take_id` field exists only as
            # a Pydantic default in domain/models.py — never written to runtime shot
            # dicts. S18 `match_shot` verb looks up ref_shot_id against this list, so
            # missing performance-approved shots would silently demote match_shot to
            # freeform with a `ref_not_found` marker.
            "approved_shots": [
                s for s in scene.get("shots", [])
                if s.get("approved_keyframe_take_id")
                or s.get("approved_motion_take_id")
                or s.get("approved_performance_take_id")
            ],
        }

        translated = intent_translator(
            intent,
            take_context,
            scene_context,
            project=project,
            cost_tracker=self.cost_tracker,
            video_id=project_id or str(project.get("id") or ""),
        )

        revised_prompt = translated.get("revised_prompt") or take_context["prompt"]
        params_delta = translated.get("params_delta") or {}
        anchor_refs = translated.get("anchor_refs") or []

        # Route by target_stage to the matching generator.
        target_stage = intent.target_stage

        if target_stage == "keyframe":
            result = self.generate_keyframe_take(
                scene_id,
                shot_id,
                positive_prompt=revised_prompt,
                intent_override=intent,
                parent_take_id=take_id,
                revised_prompt=revised_prompt,
            )
        elif target_stage == "performance":
            result = self.generate_performance_take(
                scene_id,
                shot_id,
                intent_override=intent,
                parent_take_id=take_id,
                revised_prompt=revised_prompt,
            )
        elif target_stage == "motion":
            result = self.generate_motion_take(
                scene_id,
                shot_id,
                intent_override=intent,
                parent_take_id=take_id,
                revised_prompt=revised_prompt,
            )
        else:
            return {"success": False, "error": f"Unknown target_stage: {target_stage}"}

        # Stash params_delta + anchor_refs into the new take's metadata via mutation.
        #
        # Two-round-trip note (S16; will collapse in S18 when verbs consume
        # params_delta during generation): this is the SECOND `_mutate_shot`
        # call. The generator's own mutator (above) already released its
        # filelock by the time we re-acquire here. The target take is found
        # by ID (never by position), so we cannot corrupt the wrong take.
        # The narrow gap: if a concurrent pipeline phase auto-approves a take
        # between the two mutates, we may write `params_delta`/`anchor_refs`
        # onto a take that has already been superseded. Worst case is a stale
        # metadata key — not data loss. Acceptable for S16 because S18 makes
        # this collapse to a single mutate when params_delta is consumed
        # inside the generator.
        if result.get("success") and (params_delta or anchor_refs):
            new_take = result.get("take") or {}
            new_take_id = new_take.get("id") if isinstance(new_take, dict) else ""
            if new_take_id:
                def _stash_delta(_scene: dict, project_shot: dict) -> MutationResult:
                    for coll in ("keyframe_takes", "performance_takes", "motion_takes"):
                        for t in project_shot.get(coll, []):
                            if t.get("id") == new_take_id:
                                t.setdefault("metadata", {})["params_delta"] = params_delta
                                t.setdefault("metadata", {})["anchor_refs"] = anchor_refs
                                return MutationResult(t, save=True)
                    return MutationResult(None, save=False)
                self._mutate_shot(shot_id, _stash_delta)

        # S21 (cycle-9 Surface B): dirty-shot tracking for re-assembly.
        # When iterate fires DURING SCREENING (the post-ASSEMBLY operator-driven
        # preview-and-iterate phase), the assembled mp4 on disk no longer matches
        # the project's current approved takes. Add shot_id to the project's
        # ``needs_reassembly`` list so the operator-facing "Re-assemble" button
        # can short-circuit on `only_if_changed=true` when nothing changed AND
        # so the UI can show "N shots dirty -- re-assemble suggested."
        #
        # SCREENING detection via live runstate is the right signal here: the
        # iterate endpoint runs synchronously on the same Python process that
        # owns the gate-waiting pipeline, so `self._runstate.current_stage`
        # reflects the pipeline's actual phase. A None / absent runstate
        # (controller built fresh by `_get_stage_pipeline` when no pipeline is
        # running) signals "no SCREENING in flight" -- dirty-tracking is moot.
        #
        # Lazy import preserves the no-screening-flag cold-start property
        # (cinema.screening is only loaded when the screening path actually fires).
        if result.get("success") and project_id:
            try:
                in_screening = (
                    getattr(self._runstate, "current_stage", "") == "SCREENING"
                )
            except AttributeError:
                in_screening = False
            if in_screening:
                try:
                    from cinema.screening import mark_shot_needs_reassembly
                    mark_shot_needs_reassembly(project_id, shot_id)
                except (ImportError, ValueError, RuntimeError):
                    # Best-effort: dirty-tracking failure must NOT mask
                    # iteration success. Log at debug; the operator will
                    # re-trigger if the next re-assemble call short-circuits
                    # incorrectly (only_if_changed semantics are advisory).
                    # (S21 reviewer Minor #3 fold) Narrowed from a bare
                    # ``except Exception:`` so KeyboardInterrupt / SystemExit
                    # / unexpected runtime bugs surface instead of being
                    # silently swallowed.
                    logger.debug(
                        "S21 dirty-tracking failed for shot_id=%s",
                        shot_id, exc_info=True,
                    )

        return result

    def diagnose_clip(self, shot_id: str, take_id: str = "", *, deep: bool = False) -> dict:
        """
        Run all quality analyzers on a clip and return scores + recommendations.
        """
        project = self._host._refresh_project_snapshot() or self.project
        scene, shot, shot_index = self._find_shot(shot_id, project)
        if not scene or not shot:
            return {"error": "Clip not found"}

        candidate = None
        if take_id:
            _, candidate = self._find_take(shot, take_id)
        if candidate is None:
            candidate = self._host._candidate_take(shot)
        if candidate is None:
            return {"error": "No take available for diagnosis"}

        result = {
            "shot_id": shot_id,
            "take_id": candidate.get("id", ""),
            "take_kind": candidate.get("kind", ""),
            "scores": {},
            "recommendations": [],
        }
        id_result = None   # T6: hoisted so the deep block can reference it even if identity is skipped
        coh = None         # T6: hoisted so the deep block can reference it even if coherence is skipped
        video_path = self._resolve_stored_media_path(
            candidate.get("path", "") if candidate.get("kind") != "keyframe" else ""
        )
        image_path = self._resolve_stored_media_path(
            candidate.get("path", "") if candidate.get("kind") == "keyframe" else self._host._resolve_take_path(
                shot,
                shot.get("approved_keyframe_take_id", ""),
            ) or (self._host._latest_take(shot, "keyframe_takes") or {}).get("path", "")
        )

        # Identity validation
        # Align with fe2aa47: prefer in-frame chars so the score is about
        # the person actually visible, not scene-chars[0] who may be absent.
        chars = shot.get("characters_in_frame", []) or scene.get("characters_present", [])
        if chars and image_path and os.path.exists(str(image_path)):
            primary_ref = get_reference_image(self.project, chars[0])
            if primary_ref:
                from phase_c_vision import _get_shared_validator
                id_result = _get_shared_validator().validate_image(
                    str(image_path),
                    primary_ref,
                    character_id=chars[0],
                    cost_tracker=self.cost_tracker,
                    video_id=str(self.project.get("id", "")),
                    shot_id=shot_id,
                )
                result["scores"]["identity"] = id_result.overall_score  # None on skip = not scored
                if not id_result.passed:
                    # Preserve the specific failure mode and recommend
                    # provider-neutral reference conditioning.
                    char_diag = id_result.character_results.get(chars[0])
                    failure_label = char_diag.primary_failure_reason.value if char_diag else "low_identity"
                    # Structured advisory + negative-prompt-enriched regen reason.
                    from llm.negative_prompts import build_remediation_advisory, get_negative_prompt_for_failure
                    _adv = build_remediation_advisory(failure_label)
                    if _adv:
                        result["remediation_advisory"] = _adv
                    _neg = get_negative_prompt_for_failure(failure_label)
                    _regen_reason = "Regenerate with clearer approved reference conditioning"
                    if _neg:
                        _regen_reason += f"; add negative prompt: {_neg}"
                    result["recommendations"].append(
                        {"tool": "regenerate", "reason": _regen_reason}
                    )

        # Motion quality
        if video_path and os.path.exists(str(video_path)):
            from phase_c_ffmpeg import assess_motion_quality
            mq = assess_motion_quality(str(video_path))
            result["scores"]["motion"] = mq["smoothness_score"]
            result["scores"]["frozen_ratio"] = mq["frozen_ratio"]
            if mq["recommendation"] == "interpolate":
                result["recommendations"].append({"tool": "rife", "reason": f"Low smoothness ({mq['smoothness_score']:.2f})"})
            elif mq["recommendation"] == "regenerate":
                result["recommendations"].append({"tool": "regenerate", "reason": "Severe motion artifacts"})

        # Coherence (compare against previous shot's image in same scene)
        _diag_settings = self.project.get("global_settings", {})
        _coherence_enabled = _diag_settings.get("coherence_check_enabled", True)
        if _coherence_enabled and image_path and os.path.exists(str(image_path)):
            if shot_index > 0:
                previous_shot = scene.get("shots", [])[shot_index - 1]
                prev_img = self._resolve_stored_media_path(
                    self._host._resolve_take_path(previous_shot, previous_shot.get("approved_keyframe_take_id", "")) or (
                        self._host._latest_take(previous_shot, "keyframe_takes") or {}
                    ).get("path", "")
                )
                if os.path.exists(prev_img):
                    from coherence_analyzer import assess_coherence
                    coh = assess_coherence(str(image_path), prev_img)
                    if getattr(coh, "valid", True) is False:
                        coherence_error = getattr(coh, "error", "") or "invalid coherence result"
                        logger.warning(
                            "Ignoring invalid coherence result from diagnose_clip",
                            extra={
                                "shot_id": shot_id,
                                "take_id": result["take_id"],
                                "coherence_error": coherence_error,
                            },
                        )
                        result["coherence_error"] = coherence_error
                        coh = None
                    else:
                        result["scores"]["coherence"] = coh.overall_coherence_score
                        result["scores"]["color_drift"] = coh.color_drift
                        _drift_threshold = _finite_or(_diag_settings.get("color_drift_sensitivity", 0.3), 0.3)
                        if coh.color_drift > _drift_threshold:
                            result["recommendations"].append({"tool": "color_grade", "reason": "Color palette drift detected"})
                        # Per-project `coherence_threshold` triggers a regenerate
                        # recommendation when the overall coherence score is too low.
                        _coherence_floor = _finite_or(_diag_settings.get("coherence_threshold", 0.6), 0.6)
                        if coh.overall_coherence_score < _coherence_floor:
                            result["recommendations"].append({"tool": "regenerate", "reason": "Low coherence vs previous shot"})

        if deep:
            from config.settings import settings as _settings
            deep_available = bool(_settings.anthropic_api_key or _settings.openai_api_key)
            result["deep_available"] = deep_available
            if not deep_available:
                result["deep_error"] = "No LLM API key configured"
            else:
                # Deep path fully isolated — config read, ref lookup, and the LLM
                # call are all inside the try so NOTHING here can break the
                # deterministic result already built above (spec §4.3/§8).
                try:
                    from cinema.auto_approve import AdvisoryConfig
                    from llm.chief_director import ChiefDirector
                    # Use shot-level characters_in_frame for the deep diagnosis —
                    # these are exactly who is in frame for this shot.
                    _shot_chars = shot.get("characters_in_frame", [])
                    if AdvisoryConfig.from_project(self.project).deep_enabled and image_path and os.path.exists(str(image_path)):
                        # Build per-character reference list for multi-char shots.
                        # Fall back to char id when name key absent.
                        _char_map = {c["id"]: c.get("name", c["id"]) for c in self.project.get("characters", [])}
                        _refs = []
                        for _cid in _shot_chars:
                            _p = get_reference_image(self.project, _cid)
                            if _p:
                                _refs.append((_char_map.get(_cid, _cid), _p))
                        _deep = ChiefDirector(
                            self.project,
                            cost_tracker=self.cost_tracker,
                            video_id=str(project.get("id") or ""),
                        ).evaluate_generation_quality(
                            image_path=str(image_path),
                            reference_path="",
                            reference_paths=_refs or None,
                            identity_result=id_result,
                            identity_score=result["scores"].get("identity") or 0.0,
                            shot_prompt=shot.get("prompt", ""),
                            scene_context=f"{scene.get('title', '')} — {scene.get('action', '')}",
                            coherence_result=coh,
                        )
                        result["advisory_deep"] = {
                            "diagnosis": _deep.get("diagnosis", ""),
                            "prompt_mutation": _deep.get("prompt_mutation", ""),
                            "mutation_focus": _deep.get("mutation_focus", ""),
                            "decision": _deep.get("decision", ""),
                            "visual_findings": _deep.get("visual_findings", ""),
                            "source": "llm",
                        }
                except Exception as _e:
                    result["deep_error"] = str(_e)

        self._record_diagnostic(shot_id, {
            "created_at": time.time(),
            "take_id": result["take_id"],
            "take_kind": result["take_kind"],
            "scores": result["scores"],
            "recommendations": result["recommendations"],
        })
        return result

    def apply_correction(self, shot_id: str, action: str, params: dict = None, take_id: str = "") -> dict:
        """
        Apply a correction tool to a clip in the review stage.

        Actions: regenerate_image, regenerate_video, face_swap, lip_sync,
                 rife, upscale, color_grade, speed, voice_regen, foley_regen
        """
        params = params or {}
        project = self._host._refresh_project_snapshot() or self.project
        scene, shot, shot_index = self._find_shot(shot_id, project)
        if not scene or not shot:
            return {"success": False, "error": "Clip not found in review"}
        pending_artifact = self._recover_pending_take_artifact(
            shot_id, "postprocess", shot,
        )
        if pending_artifact is not None:
            return pending_artifact

        base_take = None
        if take_id:
            _, base_take = self._find_take(shot, take_id)
        if base_take is None:
            base_take = self._host._candidate_take(shot)
        if base_take is None:
            return {"success": False, "error": "No take available to correct"}

        video_path = self._resolve_stored_media_path(
            base_take.get("path", "") if base_take.get("kind") != "keyframe" else ""
        )
        scene_id = scene.get("id", "")

        self.progress("CORRECTING", f"Applying {action} to {shot_id}", -1,
                      scene_id=scene_id, shot_id=shot_id)

        try:
            if action == "regenerate_image":
                return self.generate_keyframe_take(
                    scene_id,
                    shot_id,
                    positive_prompt=params.get("positive_prompt"),
                    negative_prompt=params.get("negative_prompt"),
                )

            if action == "regenerate_video":
                return self.generate_motion_take(scene_id, shot_id)

            variant = make_take(
                "postprocess",
                source_take_id=base_take.get("id", ""),
                metadata={"action": action, "params": params},
            )
            out_path = self._take_output_path(shot_id, variant["id"], ".mp4")

            if action == "face_swap":
                # face_swap_enabled UI knob acts as a hard gate. When disabled,
                # the operator action no-ops with a clear reason so the
                # frontend can surface "face-swap is off in project settings".
                # Default False (fail-closed): face_swap dispatches a billed
                # FAL PixVerse / FaceFusion call, and this key is never
                # scaffolded by domain.project_manager.make_project, so every
                # project was silently defaulting to enabled=True while
                # VideoSection's "Face swap" toggle displayed off — a
                # spend-truth mismatch (product invariant: paid actions fail
                # closed until the operator opts in; slice 9b audit,
                # 2026-07-31).
                _settings = self.project.get("global_settings", {})
                if not _settings.get("face_swap_enabled", False):
                    return {"success": False, "error": "face_swap disabled in project settings"}
                # Align with fe2aa47: use in-frame chars so we swap the face
                # of the person actually visible, not scene-chars[0].
                chars = shot.get("characters_in_frame", []) or scene.get("characters_present", [])
                primary_ref = get_reference_image(self.project, chars[0]) if chars else None
                if video_path and primary_ref:
                    _faceswap_cascade: dict = {}
                    try:
                        result = face_swap_video_frames(
                            str(video_path),
                            primary_ref,
                            out_path,
                            cost_tracker=self.cost_tracker,
                            shot_id=shot_id,
                            video_id=str(project.get("id") or ""),
                            _cascade_out=_faceswap_cascade,
                        )
                    except Exception as exc:
                        from paid_provider import PaidCallDeferred

                        if not isinstance(exc, PaidCallDeferred):
                            raise
                        attempt = dict(exc.snapshot.attempt)
                        return {
                            "success": False,
                            "error": str(exc),
                            "code": "paid_face_swap_recovery_required",
                            "retryable": bool(attempt.get("provider_job_id")),
                            "provider_recovery_required": True,
                            "paid_attempt": attempt,
                        }
                    if result:
                        variant["path"] = result
                        variant["cascade_metadata"] = dict(_faceswap_cascade)
                        variant["metadata"]["identity_reference_path"] = (
                            self._to_project_relative(primary_ref)
                        )
                        if chars:
                            variant["metadata"]["identity_character_id"] = str(chars[0])
                    else:
                        # None means the paid provider was provably unsubmitted
                        # or unbilled and the eligible local path also failed.
                        return {
                            "success": False,
                            "error": "face_swap could not be applied (no safe swapper succeeded)",
                        }

            elif action == "lip_sync":
                # Align with fe2aa47: use in-frame chars so we sync the lips
                # of the person actually visible, not scene-chars[0].
                chars = shot.get("characters_in_frame", []) or scene.get("characters_present", [])
                primary_ref = get_reference_image(self.project, chars[0]) if chars else None
                # Scene audio is a SCENE-scoped artifact: key it with scene-level
                # characters exactly like the pipeline writer (cinema_pipeline.py
                # _build_scene_packages), or the dialogue_cache_key diverges →
                # paid TTS regen + off-frame lines voiced by the wrong character
                # (item-B quality-review CRITICAL, 9aed3ce). Only the ref follows
                # the frame.
                audio_path = self._host._ensure_scene_audio(
                    scene, _scene_characters(self.project.get("characters", []), scene)
                )
                if video_path and primary_ref and audio_path:
                    _settings = self.project.get("global_settings", {})
                    _lipsync_cascade: dict = {}
                    _rejected_lipsync_count = 0

                    def _retain_correction_lipsync_reject(evidence: dict) -> dict:
                        nonlocal _rejected_lipsync_count
                        _rejected_lipsync_count += 1
                        return _record_rejected_lipsync_candidate(
                            project=project,
                            project_root=self.project_dir,
                            shot_id=shot_id,
                            candidate_id=(
                                f"{variant['id']}-ls-reject-{_rejected_lipsync_count}"
                            ),
                            source_take_id=str(base_take.get("id") or ""),
                            evidence=evidence,
                            audio_path=str(audio_path),
                            character_reference_path=str(primary_ref),
                            input_video_path=str(video_path),
                            mode=str(_settings.get("lip_sync_mode", "auto")),
                        )

                    result = generate_lip_sync_video(
                        character_image_path=primary_ref,
                        audio_path=audio_path,
                        output_path=out_path,
                        existing_video_path=str(video_path),
                        mode=_settings.get("lip_sync_mode", "auto"),
                        settings=_settings,
                        _cascade_out=_lipsync_cascade,
                        cost_tracker=self.cost_tracker,
                        shot_id=shot_id,
                        video_id=self.project.get("id", ""),
                        _retain_rejected_candidate=_retain_correction_lipsync_reject,
                    )
                    if _lipsync_cascade.get(
                        "rejected_candidate_retention_failed"
                    ):
                        return {
                            "success": False,
                            "error": (
                                "A paid lip-sync candidate failed local validation, "
                                "but its immutable artifact record could not be written. "
                                "Fallback stopped and recovery bytes were left in place."
                            ),
                            "code": "lipsync_artifact_retention_failed",
                            "provider_recovery_required": True,
                            "rejected_candidate": _lipsync_cascade.get(
                                "recovery_candidate", {}
                            ),
                        }
                    if result:
                        variant["path"] = result
                        from lip_sync import (
                            LIPSYNC_QUALITY_FAIL,
                            LIPSYNC_QUALITY_PASS,
                            LIPSYNC_QUALITY_UNKNOWN,
                            classify_lipsync_quality,
                        )

                        _ls_metadata = variant.setdefault("metadata", {})
                        _cascade_metadata = _lipsync_cascade.get(
                            "cascade_metadata", {}
                        )
                        if not isinstance(_cascade_metadata, dict):
                            _cascade_metadata = {}
                        _ls_score = _finite_or(
                            _cascade_metadata.get("score"), None
                        )
                        _ls_state = str(
                            _cascade_metadata.get("validation_state") or ""
                        ).upper()
                        if _ls_state not in {
                            LIPSYNC_QUALITY_PASS,
                            LIPSYNC_QUALITY_FAIL,
                            LIPSYNC_QUALITY_UNKNOWN,
                        }:
                            _ls_state = classify_lipsync_quality(
                                _ls_score,
                                _finite_or(
                                    _settings.get(
                                        "lipsync_validation_threshold", 0.65
                                    ),
                                    0.65,
                                ),
                            )
                        elif (
                            _ls_state == LIPSYNC_QUALITY_PASS
                            and _ls_score is None
                        ):
                            # A PASS label without a finite score is malformed.
                            _ls_state = LIPSYNC_QUALITY_UNKNOWN
                        _ls_metadata["lipsync_score"] = _ls_score
                        _ls_metadata["lipsync_validation_state"] = _ls_state
                        # lip_sync GENERATES embedded dialogue (synced to audio_path)
                        # even when the base take was silent/unflagged, so tag the
                        # variant directly — base-flag inheritance has nothing to copy
                        # from a silent base.  Mirrors the motion path at :1801.
                        # [§3 audio-sibling family, completeness find C4]
                        _ls_metadata["dialogue_audio_in_clip"] = True
                        if _cascade_metadata:
                            variant["cascade_metadata"] = _cascade_metadata
                        # Cost-track the lipsync correction (Tier F NEW-2: previously
                        # untracked). Attribute to the winning cascade engine,
                        # namespaced LIPSYNC_<engine> like the motion path so it
                        # resolves against API_COST_USD.
                        if not _lipsync_cascade.get("paid_cost_recorded"):
                            try:
                                _ls_engine = (_lipsync_cascade.get("cascade_metadata", {})
                                              .get("engine") or "default")
                                self.cost_tracker.record_api_call(
                                    _lipsync_cost_api_key(_ls_engine), operation="lipsync",
                                    shot_id=shot_id, video_id=self.project.get("id", ""),
                                )
                            except Exception:
                                logger.warning("lipsync cost record skipped", exc_info=True, extra={"shot_id": shot_id})

            elif action == "rife":
                if video_path:
                    result = generate_rife_interpolation(
                        str(video_path),
                        out_path,
                        cost_tracker=self.cost_tracker,
                        shot_id=shot_id,
                        video_id=self.project.get("id", ""),
                    )
                    if result:
                        variant["path"] = result

            elif action == "upscale":
                if video_path:
                    result = upscale_video_seedvr2(
                        str(video_path),
                        out_path,
                        cost_tracker=self.cost_tracker,
                        shot_id=shot_id,
                        video_id=str(self.project.get("id", "")),
                    )
                    if result:
                        variant["path"] = result

            elif action == "color_grade":
                from phase_c_ffmpeg import apply_color_grade
                # Resolution order: explicit `params.preset` > project's
                # `color_grade_preset` UI knob > "warm_cinema" default.
                _settings = self.project.get("global_settings", {})
                preset = params.get("preset") or _settings.get("color_grade_preset", "warm_cinema")
                lut_path = params.get("lut_path")
                if video_path:
                    result = apply_color_grade(str(video_path), out_path, preset=preset, lut_path=lut_path)
                    if result:
                        variant["path"] = result

            elif action == "speed":
                from phase_c_ffmpeg import adjust_speed
                factor = float(params.get("factor", 1.0))
                if video_path and factor != 1.0:
                    result = adjust_speed(str(video_path), out_path, factor=factor)
                    if result:
                        variant["path"] = result

            elif action == "voice_regen":
                return {"success": False, "error": "voice_regen is not part of the staged clip correction workflow"}

            if not variant.get("path") or not os.path.exists(variant["path"]):
                return {"success": False, "error": f"Action '{action}' failed or not applicable"}

            # Propagate audio-embedding flags so the assembler doesn't substitute
            # scene-TTS for a variant that carries (preserved or re-muxed) dialogue
            # audio.  Gated on a real audio stream → video-only strips stay
            # unflagged (TTS fills).  lip_sync flags itself in-branch above.
            # [§3 audio-sibling family]
            _inherit_audio_flags_from_base(base_take, variant)

            # Persist project-relative (Product invariant #6) -- done AFTER the
            # exists check + audio-stream probe above, which need the real,
            # directly-openable absolute path _take_output_path produced.
            variant["path"] = self._to_project_relative(variant["path"])
            self._mark_artifact_version_pending(variant)

            def _mutator(_scene: dict, project_shot: dict):
                project_shot.setdefault("postprocess_variants", []).append(variant)
                return MutationResult(variant, save=True)

            stored_variant = self._mutate_shot(shot_id, _mutator)
            stored_variant, artifact_error = self._finalize_take_artifact_version(
                shot_id, "postprocess", stored_variant,
            )
            if artifact_error is not None:
                return artifact_error
            self._host._rebuild_review_clips()
            self._host._save_checkpoint()
            self.progress(
                "POSTPROCESS_READY",
                f"{action} ready for {shot_id}",
                -1,
                scene_id=scene_id,
                shot_id=shot_id,
                video_url=variant["path"],
                take_id=variant["id"],
                take_kind="postprocess",
            )
            return {"success": True, "take": stored_variant, "video": variant["path"]}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def generate_scene_preview(self, scene_id: str) -> Optional[str]:
        """Generate just one scene for preview purposes."""
        project = self._host._refresh_project_snapshot() or self.project

        # P1-3 part 4 migration (third canonical application): scene lookup
        # + typed shot iteration with helper-call boundary. Validates the
        # S10 MIGRATION-PATTERN-pydantic-caller recipe at a new consumer
        # shape — per-shot `.model_dump()` for `_resolve_take_path`'s
        # dict-shaped signature (`shot: dict`, controller.py:131). Mirrors
        # web_server.py:1148 api_decompose_scene (P1-3 part 3) and
        # web_server.py:1113 api_generate_dialogue (S10 baseline).
        project_typed = Project.model_validate(project)
        scene_typed = next((s for s in project_typed.scenes if s.id == scene_id), None)
        if scene_typed is None:
            return None

        clips = self._runstate.scene_clips.get(scene_id, [])
        if not clips:
            clips = []
            for shot_typed in scene_typed.shots:
                shot = shot_typed.model_dump()
                final_path = self._resolve_stored_media_path(
                    self._host._resolve_take_path(shot, shot.get("approved_final_take_id", ""))
                )
                if final_path and os.path.exists(final_path):
                    clips.append(final_path)
            if not clips:
                return None
            self._runstate.scene_clips[scene_id] = clips

        # Stitch scene clips into a preview
        preview_path = os.path.join(self._core.export_dir, f"preview_{scene_id}.mp4")
        valid_clips = [c for c in clips if c and os.path.exists(c)]
        if valid_clips:
            try:
                stitch_modules(valid_clips, preview_path)
            except Exception:
                logger.exception(
                    "Preview stitch failed; returning first clip",
                    extra={"scene_id": scene_id},
                )
                return valid_clips[0] if valid_clips else None
            if not os.path.exists(preview_path):
                return valid_clips[0] if valid_clips else None
            try:
                from cinema.artifact_indexing import record_auxiliary_version

                record_auxiliary_version(
                    str(project.get("id") or ""),
                    "scene_preview",
                    scene_id,
                    preview_path,
                    provider="local",
                    model="ffmpeg-scene-stitch",
                    parameters={"clip_count": len(valid_clips)},
                    source_paths={
                        f"clip_{index:03d}": clip
                        for index, clip in enumerate(valid_clips)
                    },
                    project_snapshot=project,
                    project_root=self.project_dir,
                )
            except Exception as exc:
                logger.exception(
                    "Scene preview awaits immutable artifact indexing",
                    extra={"scene_id": scene_id},
                )
                raise RuntimeError(
                    "Scene preview was rendered but artifact versioning failed"
                ) from exc
            return preview_path
        return None
