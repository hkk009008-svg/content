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
import time
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

from project_manager import MutationResult, mutate_project, make_take
from llm.style_director import style_rules_to_prompt_suffix
from character_manager import get_reference_image
from cinema.context import PipelineContext
from phase_c_assembly import generate_ai_broll
from phase_c_ffmpeg import generate_ai_video, stitch_modules, _probe_duration
from phase_c_vision import face_swap_video_frames
from lip_sync import (
    generate_lip_sync_video,
    generate_rife_interpolation,
    upscale_video_seedvr2,
)
from audio.dialogue import scene_characters as _scene_characters, shot_characters as _shot_characters


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


def _dialogue_voice_mode(settings: dict) -> str:
    """Resolve the dialogue voice mode from global_settings (default 'overlay').

    'overlay' = Veo silent video + our TTS lip-sync overlay (consistent voice).
    'native'  = Veo generates its own embedded voice (legacy).

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
      a Veo RAI-block can cascade to a silent engine (F1b overlay still fires).
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
) -> bool:
    """Return True when the winning engine's take should be tagged audio_embedded.

    Pure helper — mirrors the inline if-expression at generate_motion_take:1251-1253.

    audio_embedded is True only when ALL three conditions hold:
    - The winning engine has native_audio=True in API_REGISTRY.
    - The shot has dialogue (has_dialogue=True).
    - The voice mode is 'native' (overlay mode intentionally skips the tag so
      the F1b TTS overlay pass runs).

    Args:
        engine_info: API_REGISTRY entry for the winning engine (may be {}).
        has_dialogue: True when the shot purpose is a dialogue purpose.
        voice_mode: The resolved voice mode string ('overlay' or 'native').

    Returns:
        bool
    """
    return bool(
        engine_info.get("native_audio")
        and has_dialogue
        and voice_mode == "native"
    )


# Supported Veo clip durations (ascending).  The clamp picks the smallest
# value >= speech_seconds; values beyond the maximum are capped to "8s".
_VEO_SUPPORTED_DURATIONS = ("4s", "6s", "8s")
_VEO_DURATION_SECONDS = {d: float(d[:-1]) for d in _VEO_SUPPORTED_DURATIONS}


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


def _resolve_identity_strategy(shot, quality_tier, settings, cc):
    """Resolve the per-shot identity-conditioning promise (P1-1 spec §3d).

    Pure decision function: replaces the primary-only asset derivation
    (formerly inline at the MAX-TIER WIRE-UP block) and names which characters
    are promised identity conditioning under which mechanism. quality_tier and
    style_reference remain the caller's concern — inputs, not outputs.
    """
    from cinema.shots.strategy import (
        IdentityStrategy, CharIdentitySpec,
        PRIMARY_ONLY, KONTEXT_MULTI_CHAR, MAX_TIER_PRIMARY_ONLY, MAX_TIER_MULTI_LORA,
        NO_IDENTITY_ASSET,
    )
    in_frame = shot.get("characters_in_frame") or []
    primary_char_id = shot.get("primary_character") or (in_frame[0] if in_frame else "")
    char_lora_paths = settings.get("char_lora_paths", {}) or {}
    char_lora_path = char_lora_paths.get(primary_char_id) or None
    char_lora_strength = (settings.get("char_lora_strengths", {}) or {}).get(primary_char_id)
    char_lora_triggers = settings.get("char_lora_triggers", {}) or {}
    char_lora_trigger = char_lora_triggers.get(primary_char_id) or None
    primary_ref = cc.get("primary_reference")
    secondary = cc.get("secondary_chars") or []

    if not in_frame or not primary_ref:
        return IdentityStrategy(
            mechanism_tag=NO_IDENTITY_ASSET,
            primary_char_id=primary_char_id,
            char_lora_path=char_lora_path,
            char_lora_strength=char_lora_strength,
            char_lora_trigger=char_lora_trigger,
            unconditioned_chars=list(in_frame),
        )

    conditioned = [CharIdentitySpec(
        char_id=primary_char_id, reference=primary_ref,
        identity_anchor=cc.get("identity_anchor", ""),
        multi_angle_refs=tuple(cc.get("multi_angle_refs") or ()),
        fidelity="pulid" if quality_tier == "max" else "reference",
    )]
    conditioned_ids = {primary_char_id}

    if quality_tier == "max":
        # P1-1 slice 2 (§3b + §3c-A): same registered-ref gate + 2-cap as the
        # Kontext arm; per-secondary LoRA assets looked up exactly like the
        # primary's (settings dicts keyed by char_id). A LoRA-less secondary
        # still rides as fidelity="reference" — the ReActor rescue swaps its
        # face from the canonical even without a LoRA.
        for entry in secondary[:2]:
            sec_id = entry["char_id"]
            sec_lora = char_lora_paths.get(sec_id) or None
            conditioned.append(CharIdentitySpec(
                char_id=sec_id, reference=entry["reference"],
                identity_anchor=entry.get("identity_anchor", ""),
                multi_angle_refs=tuple(entry.get("multi_angle_refs") or ()),
                fidelity="lora" if sec_lora else "reference",
                lora_path=sec_lora,
                lora_strength=(settings.get("char_lora_strengths", {}) or {}).get(sec_id),
                # `or None` matches the primary's coercion (:298) — a ""
                # trigger must not diverge between primary and secondary.
                # (Strength stays bare .get(): 0.0 is a real value, cf. the
                # is-not-None gate at web_server.py:781.)
                trigger=char_lora_triggers.get(sec_id) or None,
            ))
            conditioned_ids.add(sec_id)
        tag = MAX_TIER_MULTI_LORA if len(conditioned) > 1 else MAX_TIER_PRIMARY_ONLY
    elif secondary:
        # Kontext-tier cap: 2 secondaries (spec §3a); overflow degrades to text-only.
        for entry in secondary[:2]:
            conditioned.append(CharIdentitySpec(
                char_id=entry["char_id"], reference=entry["reference"],
                identity_anchor=entry.get("identity_anchor", ""),
                # V-5: without this, the Task-7 allocator's
                # entry.get("multi_angle_refs") is ALWAYS empty via this path
                # and secondaries can never fill their 2 slots.
                multi_angle_refs=tuple(entry.get("multi_angle_refs") or ()),
                fidelity="reference",
            ))
            conditioned_ids.add(entry["char_id"])
        tag = KONTEXT_MULTI_CHAR if len(conditioned) > 1 else PRIMARY_ONLY
    else:
        tag = PRIMARY_ONLY

    return IdentityStrategy(
        mechanism_tag=tag,
        primary_char_id=primary_char_id,
        char_lora_path=char_lora_path,
        char_lora_strength=char_lora_strength,
        char_lora_trigger=char_lora_trigger,
        conditioned_chars=conditioned,
        unconditioned_chars=[c for c in in_frame if c not in conditioned_ids],
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

    def _record_diagnostic(self, shot_id: str, diagnostic: dict) -> None:
        def _mutator(_scene: dict, shot: dict):
            shot.setdefault("diagnostics", []).append(diagnostic)
            return MutationResult(diagnostic, save=True)

        self._mutate_shot(shot_id, _mutator)

    def _resolve_previous_approved_keyframe(self, scene: dict, shot_index: int) -> str:
        if shot_index <= 0:
            return ""
        previous_shot = scene.get("shots", [])[shot_index - 1]
        take_id = previous_shot.get("approved_keyframe_take_id", "")
        return self._host._resolve_take_path(previous_shot, take_id)

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
        if shot.get("plan_status") != "approved":
            return {"success": False, "error": "Shot plan must be approved before generating a keyframe"}

        settings = project.get("global_settings", {})
        style_suffix = style_rules_to_prompt_suffix(settings.get("style_rules", {}))
        prev_shot = scene.get("shots", [])[shot_index - 1] if shot_index > 0 else None
        approved_anchor = self._resolve_previous_approved_keyframe(scene, shot_index)
        enhanced = self.continuity.enhance_shot_prompt(
            shot,
            scene,
            prev_shot,
            shot_index,
            approved_anchor_image=approved_anchor,
        )
        full_prompt = positive_prompt or enhanced["prompt"]
        if style_suffix:
            full_prompt = f"{full_prompt}. {style_suffix}"

        cc = enhanced.get("continuity_config", {})
        primary_ref = cc.get("primary_reference")
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

        # --- MAX-TIER WIRE-UP ---
        # Forward the project's quality_tier setting + per-character LoRA + style ref
        # into generate_ai_broll. Backward-compatible: when quality_tier is unset or
        # 'production', the kwargs default to None/'production' and behavior is
        # identical to before.
        quality_tier = settings.get("quality_tier", "production")
        strategy = _resolve_identity_strategy(shot, quality_tier, settings, cc)
        primary_char_id = strategy.primary_char_id
        char_lora_path = strategy.char_lora_path
        char_lora_strength = strategy.char_lora_strength
        take["metadata"]["identity_strategy"] = strategy.to_metadata_dict()
        style_refs = settings.get("style_reference_paths", []) or []
        style_reference = style_refs[0] if style_refs else None

        # --- PROMPT OPTIMIZER (highest quality lever) ---
        # When enabled, run the shot prompt through the LLM-based optimizer which
        # produces a cinematography-precise prompt + per-shot API recommendations +
        # identity anchor + negative constraints. The result is cached on the shot
        # (.optimizer_cache) so regen doesn't repeat the LLM call.
        opt_enabled = settings.get("prompt_optimizer_enabled", False)
        opt_spec = None
        if opt_enabled:
            cached = shot.get("optimizer_cache")
            # Re-optimize when the source prompt changed OR no cache exists
            if cached and cached.get("source_prompt") == full_prompt:
                opt_spec = cached.get("spec")
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
                    opt_spec = optimize_shot_prompt(
                        user_input=full_prompt,
                        characters=shot_chars,
                        objects=shot_objs,
                        location=location,
                        global_settings=settings,
                        scene_context=f"Scene: {scene.get('title', '')}\nAction: {scene.get('action', '')[:300]}",
                        has_dialogue=has_dialogue,
                        intent_notes=shot.get("intent_notes", ""),
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
            identity_anchor_override = opt_spec.get("identity_anchor") or cc.get("identity_anchor", "")
            negative_override = opt_spec.get("negative_constraints") or negative_prompt
            # If the user hasn't pinned a target_api, take the optimizer's suggestion
            if shot.get("target_api", "AUTO") == "AUTO":
                suggested = opt_spec.get("suggested_video_api")
                if suggested and suggested != "AUTO":
                    take["metadata"]["target_api"] = suggested
        else:
            identity_anchor_override = cc.get("identity_anchor", "")
            negative_override = negative_prompt or cc.get("negative_constraints") or shot.get("negative_constraints", "")

        # Image-engine routing — mirror the video-routing AUTO guard above
        # (shot["target_api"]): a user-pinned shot["image_api"] wins; otherwise
        # forward the optimizer's suggestion. Guards a future image_api user-pin
        # from being silently overridden by the optimizer (Lane V #20 M-2).
        _pinned_image_api = shot.get("image_api", "AUTO")
        if _pinned_image_api and _pinned_image_api != "AUTO":
            _image_api_hint = _pinned_image_api
        elif opt_spec:
            _image_api_hint = opt_spec.get("suggested_image_api")
        else:
            _image_api_hint = None

        # Build a lightweight PipelineContext so max-tier UI knobs
        # (MaxTierComfyControls + halt overrides) flow through to
        # generate_ai_broll_max.  settings is a plain dict; wrapping it in
        # PipelineContext lets get_project_setting() read it correctly.
        ctx = PipelineContext(global_settings=settings)

        result = generate_ai_broll(
            full_prompt,
            img_path,
            seed=cc.get("scene_seed"),
            character_image=primary_ref,
            init_image=cc.get("init_image") if cc.get("use_img2img") else None,
            denoise_strength=cc.get("denoise_strength", 1.0),
            multi_angle_refs=cc.get("multi_angle_refs", []),
            identity_anchor=identity_anchor_override,
            pulid_weight_override=cc.get("pulid_weight_override"),
            negative_prompt=negative_override,
            quality_tier=quality_tier,
            char_lora_path=char_lora_path,
            char_lora_strength=char_lora_strength,
            char_lora_trigger=strategy.char_lora_trigger,
            style_reference=style_reference,
            secondary_char_refs=[c.to_dict() for c in strategy.secondary_specs] or None,
            shot_hint={"prompt": full_prompt, "characters_in_frame": shot.get("characters_in_frame", []),
                       "camera": shot.get("camera", ""),
                       "image_api": _image_api_hint},
            ctx=ctx,
        )
        if not result or not os.path.exists(img_path):
            return {"success": False, "error": "Image generation failed"}

        actual = result.api_name
        if actual == "FLUX_KONTEXT" and strategy.secondary_specs:
            # V-2 / spec §3(d): api_name is backend-granular — a successful
            # Kontext call looks identical for multi-char and primary-only, so
            # derive the actual from api_name x what the strategy emitted.
            # This records EMISSION, not server honoring; S1 + per-char
            # validation cover the latter.
            actual = "FLUX_KONTEXT_MULTI_CHAR"
        take["metadata"]["mechanism_actually_used"] = actual

        identity_score = 0.0
        if primary_ref:
            from phase_c_vision import _get_shared_validator
            # Project-wide `identity_strictness` setting overrides the per-shot
            # `identity_threshold` so the operator can raise/lower the bar
            # without touching every shot. Falls back to the per-shot value.
            strictness = settings.get("identity_strictness")
            threshold = strictness if strictness is not None else cc.get("identity_threshold", 0.70)
            id_result = _get_shared_validator().validate_image(
                img_path, primary_ref,
                character_id=primary_char_id,
                threshold=threshold,
            )
            identity_score = id_result.overall_score  # None on skip = not scored
            take["metadata"]["identity_score"] = identity_score
            # Surface rich diagnostics from the singleton — the deprecated
            # validate_identity_image wrapper discarded these. Retry logic +
            # operator-facing review can read failure cause and a suggested
            # PuLID weight delta from the take metadata.
            char_diag = id_result.character_results.get(primary_char_id)
            if char_diag and not id_result.passed:
                take["metadata"]["identity_failure_reason"] = char_diag.primary_failure_reason.value
                take["metadata"]["suggested_pulid_adjustment"] = char_diag.suggested_pulid_adjustment
                # T6: deterministic remediation advisory (pure; advisory-only).
                # Best-effort: advisory must NEVER break keyframe generation, so any
                # failure here (import, config read, builder) is swallowed — the take
                # still carries identity_failure_reason + suggested_pulid_adjustment.
                try:
                    from cinema.auto_approve import AdvisoryConfig
                    from llm.negative_prompts import build_remediation_advisory
                    if AdvisoryConfig.from_project(project).enabled:
                        _adv = build_remediation_advisory(
                            char_diag.primary_failure_reason.value,
                            char_diag.suggested_pulid_adjustment,
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
                )
                per_char[spec_c.char_id] = sec_result.overall_score
            take["metadata"]["identity_per_char"] = per_char

        take["path"] = img_path

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

        def _mutator(_scene: dict, project_shot: dict):
            project_shot.setdefault("keyframe_takes", []).append(take)
            project_shot["generated_image"] = img_path
            return MutationResult(take, save=True)

        stored_take = self._mutate_shot(shot_id, _mutator)
        self._runstate.shot_results[shot_id] = {
            "image": img_path,
            "video": None,
            "identity_score": identity_score,
            "status": "keyframe_review",
            "take_id": take["id"],
        }
        self._host._rebuild_review_clips()
        self._host._save_checkpoint()

        # Record image generation cost under the backend that ACTUALLY ran.
        # generate_ai_broll threads the real provenance back via
        # ImageGenResult.api_name (COMFYUI_PULID on the pod; FLUX_KONTEXT /
        # FLUX_PRO / FLUX_SCHNELL / POLLINATIONS on FAL fallback; QUALITY_MAX for
        # the max tier) rather than a quality_tier-based guess — so cost_log can
        # tell a pod generation from a FAL fallback (both used to log 'fal').
        # result is a truthy ImageGenResult here (the `if not result` guard above
        # already returned on failure).
        _image_api = result.api_name
        try:
            video_id = self.project.get("id", "")
            self.cost_tracker.record_api_call(
                _image_api,
                operation="keyframe_generation",
                shot_id=shot_id,
                video_id=video_id,
            )
        except Exception:
            # Cost tracking is best-effort; the keyframe itself succeeded.
            logger.warning(
                "keyframe cost record skipped",
                exc_info=True,
                extra={"shot_id": shot_id},
            )

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
    ) -> dict:
        """Per-shot performance capture (handoff §7).

        Sits between keyframe review and motion render. Routes the shot to one
        of {ACT_ONE, LIVE_PORTRAIT, VIGGLE, SKIP} via domain.performance.
        SKIP is a happy-path no-op — motion_render falls through to text-to-video
        without a driving reference.

        Effect on the shot:
          performance_takes:          appended-to (one take per call)
          approved_performance_take_id: set on first success (operator can re-approve via gate)
          performance_engine:         the engine string actually used (or "SKIP")
        """
        project = self._host._refresh_project_snapshot() or self.project
        scene, shot, shot_index = self._find_shot(shot_id, project, scene_id)
        if not scene or not shot:
            return {"success": False, "error": "Shot not found"}
        if shot.get("plan_status") != "approved":
            return {"success": False, "error": "Shot plan must be approved before performance capture"}
        keyframe_take_id = shot.get("approved_keyframe_take_id", "")
        if not keyframe_take_id:
            return {"success": False, "error": "Approved keyframe required before performance capture"}

        # --- 1. Routing ---
        from domain.performance import (
            route_performance_engine, ENGINE_SKIP, driving_video_source,
        )
        engine = route_performance_engine(shot, scene)

        if engine == ENGINE_SKIP:
            # Happy-path no-op — record the skip on the shot so motion_render
            # knows to fall through to text-to-video without a driving ref.
            def _mut_skip(_scene: dict, project_shot: dict):
                project_shot["performance_engine"] = "SKIP"
                return MutationResult(True, save=True)
            self._mutate_shot(shot_id, _mut_skip)
            self.progress(
                "PERFORMANCE_SKIPPED",
                f"Shot {shot_id}: SKIP (wide/landscape or no characters)",
                -1, scene_id=scene_id, shot_id=shot_id, performance_engine="SKIP",
            )
            return {"success": True, "skipped": True, "engine": "SKIP"}

        # --- 2. Resolve assets ---
        source_image = self._host._resolve_take_path(shot, keyframe_take_id)
        if not source_image or not os.path.exists(source_image):
            return {"success": False, "error": "Approved keyframe asset is missing"}

        # Audio comes from the scene-level dialogue track (ensured upstream).
        # _ensure_scene_audio(scene, characters) — pass the full scene dict
        # AND the filtered character list, mirroring the caller at line 1491.
        characters = _scene_characters(project.get("characters") or [], scene)
        audio_path = ""
        try:
            audio_path = self._host._ensure_scene_audio(scene, characters) or ""
        except Exception:
            # Scene audio is advisory for several performance engines;
            # downstream code handles missing audio gracefully.
            logger.warning(
                "scene audio unavailable",
                exc_info=True,
                extra={"scene_id": scene["id"], "engine": engine},
            )

        # Hard precondition check — refuse to allocate a take when we know it'll
        # fail in the adapter. Audio-less ACT_ONE silently mis-syncs; LIVE_PORTRAIT
        # and VIGGLE fail to start at all.
        from domain.performance import precondition_error
        pre_err = precondition_error(engine, audio_path, shot.get("driving_video_path") or "")
        if pre_err:
            def _mut_pre_fail(_scene: dict, project_shot: dict):
                project_shot["performance_engine"] = "SKIP"
                return MutationResult(True, save=True)
            self._mutate_shot(shot_id, _mut_pre_fail)
            self.progress(
                "PERFORMANCE_SKIPPED",
                f"Shot {shot_id}: {engine} precondition failed: {pre_err}",
                -1, scene_id=scene_id, shot_id=shot_id, performance_engine="SKIP",
            )
            return {"success": True, "skipped": True, "engine": engine, "error": pre_err}

        # --- 3. Driving video — Mode A (operator upload) wins, else Mode B synth ---
        driving = (shot.get("driving_video_path") or "").strip()
        source_mode = driving_video_source(shot)
        # Initialize BEFORE the branch so Mode A (operator upload) doesn't NameError.
        # Mode A reuses the operator's video → no synth → provider stays None.
        driving_provider: Optional[str] = None
        if not driving and source_mode == "tts_auto" and audio_path:
            try:
                from performance.driving_video import synth_driving_face_from_audio
                temp_driving = self._take_output_path(shot_id, f"driving_{keyframe_take_id}", ".mp4")
                synth_result = synth_driving_face_from_audio(
                    audio_path=audio_path,
                    keyframe_path=source_image,
                    output_mp4=temp_driving,
                    duration_s=float(scene.get("duration_seconds", 5.0)),
                    shot_id=shot_id, video_id=str(project.get("id", "")),
                )
                if synth_result:
                    driving, driving_provider = synth_result
            except Exception:
                logger.exception(
                    "driving-video synth failed; engine may degrade",
                    extra={"shot_id": shot_id, "engine": engine},
                )

        # --- 4. Dispatch to the chosen engine ---
        take = make_take(
            "performance",
            source_take_id=keyframe_take_id,
            metadata={
                "scene_id": scene_id,
                "shot_id": shot_id,
                "engine": engine,
                "driving_source": "upload" if shot.get("driving_video_path") else (
                    "tts_auto" if driving else "none"
                ),
                "audio_path": audio_path,
                "duration_s": float(scene.get("duration_seconds", 5.0)),
                "driving_provider": driving_provider,  # "hedra" | "sadtalker" | "cache" | None
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

        try:
            from performance._router import dispatch
            result_path = dispatch(
                engine,
                keyframe_path=source_image,
                audio_path=audio_path or None,
                driving_video_path=driving or None,
                output_mp4=perf_path,
                duration_s=float(scene.get("duration_seconds", 5.0)),
                shot_id=shot_id,
                video_id=str(project.get("id", "")),
            )
        except Exception as e:
            return {"success": False, "error": f"Performance dispatch raised: {e}"}

        if not result_path or not os.path.exists(perf_path):
            # Engine failed gracefully (returned None). Mark as SKIP so motion_render
            # uses plain text-to-video — pipeline keeps moving.
            def _mut_fail(_scene: dict, project_shot: dict):
                project_shot["performance_engine"] = "SKIP"
                return MutationResult(True, save=True)
            self._mutate_shot(shot_id, _mut_fail)
            self.progress(
                "PERFORMANCE_SKIPPED",
                f"Shot {shot_id}: {engine} produced no output; falling through to text-to-video",
                -1, scene_id=scene_id, shot_id=shot_id, performance_engine="SKIP",
            )
            return {"success": True, "skipped": True, "engine": engine,
                    "error": "engine returned no output"}

        # --- 5. Persist the take + identity-gate the auto-approve ---
        take["path"] = perf_path

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
        arc_score = validate_performance_take(perf_path, face_anchor) if face_anchor else None
        gate_passed = (arc_score is None) or (arc_score >= DEFAULT_PERFORMANCE_FLOOR)

        def _mut_success(_scene: dict, project_shot: dict):
            project_shot.setdefault("performance_takes", []).append(take)
            # Auto-approve ONLY when the identity gate passed (or was inconclusive).
            # A score below floor leaves approval to the operator via PERFORMANCE_REVIEW.
            if gate_passed and not project_shot.get("approved_performance_take_id"):
                project_shot["approved_performance_take_id"] = take["id"]
            project_shot["performance_engine"] = engine
            # Stash the score for the review UI to surface.
            take.setdefault("metadata", {})["identity_score"] = arc_score
            return MutationResult(take, save=True)

        stored_take = self._mutate_shot(shot_id, _mut_success)
        self._host._save_checkpoint()
        if not gate_passed:
            self.progress(
                "PERFORMANCE_REVIEW_REQUIRED",
                f"Shot {shot_id}: identity score {arc_score:.3f} below floor "
                f"{DEFAULT_PERFORMANCE_FLOOR}; awaiting operator review",
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
                rife_result = generate_rife_interpolation(video_path, rife_out)
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
                    try:
                        self.cost_tracker.record_api_call(
                            "FAL_RIFE",
                            operation="rife_interpolation",
                            shot_id=shot_id,
                            video_id=self.project.get("id", ""),
                        )
                    except Exception:
                        logger.warning(
                            "auto-RIFE cost record skipped",
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
        take["path"] = video_path

        # 4–5. Persist take via mutation
        final_vid = video_path

        def _mutator(_scene: dict, project_shot: dict):
            project_shot.setdefault("motion_takes", []).append(take)
            project_shot["generated_video"] = final_vid
            return MutationResult(take, save=True)

        stored_take = self._mutate_shot(shot_id, _mutator)

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
                self.cost_tracker.record_api_call(
                    target_api,
                    operation="motion_generation",
                    shot_id=shot_id,
                    video_id=video_id,
                )
            except Exception:
                logger.warning(
                    "motion cost record skipped",
                    exc_info=True,
                    extra={"shot_id": shot_id},
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
        if shot.get("plan_status") != "approved":
            return {"success": False, "error": "Shot plan must be approved before generating motion"}
        keyframe_take_id = shot.get("approved_keyframe_take_id", "")
        if not keyframe_take_id:
            return {"success": False, "error": "Approved keyframe required before generating motion"}

        source_image = self._host._resolve_take_path(shot, keyframe_take_id)
        if not source_image or not os.path.exists(source_image):
            return {"success": False, "error": "Approved keyframe asset is missing"}

        prev_shot = scene.get("shots", [])[shot_index - 1] if shot_index > 0 else None
        approved_anchor = self._resolve_previous_approved_keyframe(scene, shot_index)
        enhanced = self.continuity.enhance_shot_prompt(
            shot,
            scene,
            prev_shot,
            shot_index,
            approved_anchor_image=approved_anchor,
        )
        cc = enhanced.get("continuity_config", {})
        from workflow_selector import classify_shot_type, WORKFLOW_TEMPLATES
        from domain.scene_decomposer import API_REGISTRY

        resolved_shot_type = classify_shot_type(shot)
        raw_api = shot.get("target_api", "AUTO")

        # F1a: Read the optimizer cache to recover the purpose + suggested_video_api
        # that was computed during keyframe generation but not forwarded here.
        # The cache structure is: shot["optimizer_cache"]["spec"]["purpose"] / ["suggested_video_api"]
        opt_cache = shot.get("optimizer_cache") or {}
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

        if raw_api == "AUTO":
            # Prefer the optimizer's per-shot suggestion over the shot-type template.
            cached_suggestion = opt_spec_cached.get("suggested_video_api", "")
            if cached_suggestion and cached_suggestion != "AUTO" and cached_suggestion in API_REGISTRY:
                target_api = cached_suggestion
                # F1a Lane V #18 §2 fix: preserve template fallbacks even when honoring
                # a cached suggestion, so non-dialogue shots with a suggestion don't lose
                # their cross-engine fallback chain.  Dialogue shots (see upgrade below)
                # get None explicitly because the native-audio engine's internal cascade
                # handles failures and cross-engine fallback to KLING_NATIVE would
                # reintroduce the "no native audio" bug.
                template = WORKFLOW_TEMPLATES.get(resolved_shot_type, WORKFLOW_TEMPLATES["medium"])
                video_fallbacks = template.get("video_fallbacks")
            else:
                template = WORKFLOW_TEMPLATES.get(resolved_shot_type, WORKFLOW_TEMPLATES["medium"])
                target_api = template["target_api"]
                video_fallbacks = template.get("video_fallbacks")

            # F1a Lane V #18 §1 fix (consumer-side): when has_dialogue is True, the
            # resolved target_api MUST carry native_audio for the native-audio path to
            # work.  The optimizer's suggestion for dialogue_close_up returns KLING_NATIVE
            # (first video-modality entry in PURPOSE_API_RANKING before VEO_NATIVE), which
            # has no native_audio.  Override to the first native_audio video engine in the
            # purpose ranking.  If none exists (policy change in API_REGISTRY), fall through
            # to the current target_api and rely on the standalone lipsync pass (F1b).
            #
            # Task 3 (dialogue_voice_mode):
            # - overlay mode (default): keep VEO_NATIVE as primary via the override,
            #   but DO NOT null video_fallbacks. Restored cascade means a Veo RAI-block
            #   falls through to Kling/Sora/etc. (silent) → F1b overlay still fires.
            # - native mode: preserve today's behavior verbatim (force native-audio
            #   engine + video_fallbacks=None so embedded voice is never lost to a
            #   cross-engine fallback that lacks native_audio).
            if has_dialogue:
                _pre_override_api = target_api
                target_api, video_fallbacks = _resolve_dialogue_routing(
                    cached_purpose,
                    _voice_mode,
                    target_api,
                    video_fallbacks,
                )
                if target_api != _pre_override_api:
                    logger.info(
                        "dialogue routing override: %s → %s "
                        "(purpose=%s; original suggestion lacked native_audio)",
                        _pre_override_api,
                        target_api,
                        cached_purpose,
                    )
                # If no native_audio engine found in ranking: keep resolved target_api.
                # F1b's mandatory lipsync pass will cover the gap.
        else:
            target_api = raw_api
            video_fallbacks = None

        # Pre-spend budget gate (STRATEGIC_REVIEW-2026-06-10 P0-2 / ADR-022):
        # all PER-TAKE motion spend routes through this function (web
        # endpoint, phase loop, regenerate, iterate, retry); the F2b
        # storyboard BATCH launch is gated separately in
        # cinema/phases/motion_render.py. Soft cap: API_COST_USD estimates
        # are ±30% and price only the resolved primary — a fallback-cascade
        # winner can cost several times the admitted estimate. The motion
        # phase loop aborts on the structured "budget" refusal below.
        if self.cost_tracker.would_exceed(target_api):
            self.progress(
                "BUDGET_EXCEEDED",
                f"Estimated {target_api} cost would push spend "
                f"${self.cost_tracker.spent_usd:.2f} past budget cap "
                f"${self.cost_tracker.budget_usd:.2f}. Pausing before generation.",
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
            driving_video_path = self._host._resolve_take_path(shot, performance_take_id) or ""

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

        _video_cascade: dict = {}
        temp_vid = generate_ai_video(
            source_image,
            shot.get("camera", "zoom_in_slow"),
            target_api,
            vid_path,
            pacing="calculated",
            character_id=cc.get("primary_character", ""),
            multi_angle_refs=cc.get("multi_angle_refs", []),
            negative_prompt=shot.get("negative_constraints", ""),
            shot_type=resolved_shot_type,
            video_fallbacks=video_fallbacks,
            driving_video_path=driving_video_path,
            has_dialogue=has_dialogue,
            dialogue_native_audio=dialogue_native_audio,
            duration=_veo_duration,
            ctx=motion_ctx,
            _cascade_out=_video_cascade,
        )
        final_vid = temp_vid or vid_path
        if not final_vid or not os.path.exists(final_vid):
            return {"success": False, "error": "Video generation failed"}
        if "cascade_metadata" in _video_cascade:
            take["cascade_metadata"] = _video_cascade["cascade_metadata"]

        # F1a: Tag the take when the winning engine carries embedded voice audio.
        # Check the API_REGISTRY native_audio flag rather than hardcoding a name.
        # The assembler (F1b) reads audio_embedded=True to skip the TTS+mux path.
        # Task 4: gate behind native mode — in overlay mode (default) the tag is NOT
        # set so the F1b TTS overlay pass at :1267 runs and overlays the per-shot TTS.
        winning_engine = (
            _video_cascade.get("cascade_metadata", {}).get("engine", target_api).upper()
        )
        engine_info = API_REGISTRY.get(winning_engine, {})
        if _should_tag_audio_embedded(engine_info, has_dialogue, _voice_mode):
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
        # HEDRA_C3) as an engine-level hint, but there is no engine-selection knob on
        # generate_lip_sync_video — the engine cascade inside lipsync_overlay/generation
        # handles selection internally.  We pass mode="auto" (same as the manual
        # lip_sync correction action) and let the cascade choose.
        if has_dialogue and not take["metadata"].get("audio_embedded"):
            try:
                from lip_sync import generate_lip_sync_video, validate_lipsync_quality
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
                    ls_result = generate_lip_sync_video(
                        character_image_path=primary_ref_for_sync,
                        audio_path=audio_path_for_sync,
                        output_path=lipsync_out,
                        existing_video_path=final_vid,
                        mode=settings.get("lip_sync_mode", "auto"),
                        settings=settings,
                        _cascade_out=_ls_cascade,
                    )
                    if ls_result and os.path.exists(ls_result):
                        # Replace take video with the lip-synced output.
                        final_vid = ls_result
                        take["metadata"]["lipsync_score"] = validate_lipsync_quality(
                            ls_result, audio_path_for_sync
                        )
                        if "cascade_metadata" in _ls_cascade:
                            take["metadata"]["lipsync_cascade"] = _ls_cascade["cascade_metadata"]
                        # Chunk 3 / Task 7: mark that this clip already carries
                        # per-shot TTS so the assembler (_build_scene_packages)
                        # suppresses the scene-level TTS mux and avoids double-voice.
                        take["metadata"]["dialogue_audio_in_clip"] = True
                        logger.info(
                            "[DIALOGUE] shot=%s audio=standalone+lipsync score=%.3f",
                            shot_id,
                            take["metadata"]["lipsync_score"],
                        )
                        # Cost-track the lipsync generation (Tier F NEW-2: lipsync was
                        # previously untracked). Attribute to the winning cascade engine;
                        # unpriced engines record $0.00 + a warning, same as other gens.
                        try:
                            _ls_engine = (_ls_cascade.get("cascade_metadata", {})
                                          .get("engine") or "LIPSYNC")
                            self.cost_tracker.record_api_call(
                                _ls_engine, operation="lipsync",
                                shot_id=shot_id, video_id=self.project.get("id", ""),
                            )
                        except Exception:
                            logger.warning("lipsync cost record skipped", exc_info=True, extra={"shot_id": shot_id})
                    else:
                        # Lipsync pass returned nothing — leave lipsync_score absent
                        # (0.0 sentinel) so the auto-approve gate treats this as FAIL.
                        take["metadata"]["lipsync_score"] = 0.0
                        logger.warning(
                            "[DIALOGUE] shot=%s audio=DEGRADED-no-lipsync "
                            "(generate_lip_sync_video returned no output)",
                            shot_id,
                        )
                else:
                    # Missing audio or character ref — cannot run lipsync.
                    take["metadata"]["lipsync_score"] = 0.0
                    logger.warning(
                        "[DIALOGUE] shot=%s audio=DEGRADED-no-lipsync "
                        "(missing audio_path=%s or primary_ref=%s)",
                        shot_id,
                        audio_path_for_sync,
                        primary_ref_for_sync,
                    )
            except Exception:
                # Lipsync pass is advisory for generation; never fail the take.
                # Leave lipsync_score absent/0.0 so the gate catches the gap.
                take["metadata"].setdefault("lipsync_score", 0.0)
                logger.warning(
                    "[DIALOGUE] shot=%s audio=DEGRADED-lipsync-exception",
                    shot_id,
                    exc_info=True,
                )
        elif has_dialogue and take["metadata"].get("audio_embedded"):
            # Native-audio take: voice is baked in at generation time.
            # Use a high constant score — the engine's own sync quality is
            # not measurable offline, but native-audio sync is structurally
            # reliable (the model generates speech and video together).
            # The auto-approve gate treats audio_embedded=True as a pass;
            # this score is stored for telemetry only.
            NATIVE_AUDIO_LIPSYNC_SCORE = 1.0
            take["metadata"]["lipsync_score"] = NATIVE_AUDIO_LIPSYNC_SCORE
            logger.info("[DIALOGUE] shot=%s audio=embedded-native", shot_id)
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
        video_path = candidate.get("path", "") if candidate.get("kind") != "keyframe" else ""
        image_path = candidate.get("path", "") if candidate.get("kind") == "keyframe" else self._host._resolve_take_path(
            shot,
            shot.get("approved_keyframe_take_id", ""),
        ) or (self._host._latest_take(shot, "keyframe_takes") or {}).get("path", "")

        # Identity validation
        # Align with fe2aa47: prefer in-frame chars so the score is about
        # the person actually visible, not scene-chars[0] who may be absent.
        chars = shot.get("characters_in_frame", []) or scene.get("characters_present", [])
        if chars and image_path and os.path.exists(str(image_path)):
            primary_ref = get_reference_image(self.project, chars[0])
            if primary_ref:
                from phase_c_vision import _get_shared_validator
                id_result = _get_shared_validator().validate_image(
                    str(image_path), primary_ref, character_id=chars[0]
                )
                result["scores"]["identity"] = id_result.overall_score  # None on skip = not scored
                if not id_result.passed:
                    # Specific failure mode + recommended PuLID delta replace
                    # the previous generic "Low identity score" string.
                    char_diag = id_result.character_results.get(chars[0])
                    failure_label = char_diag.primary_failure_reason.value if char_diag else "low_identity"
                    delta = char_diag.suggested_pulid_adjustment if char_diag else 0.0
                    # T6: structured advisory + negative-prompt-enriched regen reason.
                    from llm.negative_prompts import build_remediation_advisory, get_negative_prompt_for_failure
                    _adv = build_remediation_advisory(failure_label, delta)
                    if _adv:
                        result["remediation_advisory"] = _adv
                    _neg = get_negative_prompt_for_failure(failure_label)
                    _regen_reason = f"Regenerate with PuLID weight +{delta:.2f}"
                    if _neg:
                        _regen_reason += f"; add negative prompt: {_neg}"
                    result["recommendations"].append(
                        {"tool": "face_swap", "reason": f"Identity gate failed ({failure_label})"}
                    )
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
                prev_img = self._host._resolve_take_path(previous_shot, previous_shot.get("approved_keyframe_take_id", "")) or (
                    self._host._latest_take(previous_shot, "keyframe_takes") or {}
                ).get("path", "")
                if os.path.exists(prev_img):
                    from coherence_analyzer import assess_coherence
                    coh = assess_coherence(str(image_path), prev_img)
                    result["scores"]["coherence"] = coh.overall_coherence_score
                    result["scores"]["color_drift"] = coh.color_drift
                    _drift_threshold = _diag_settings.get("color_drift_sensitivity", 0.3)
                    if coh.color_drift > _drift_threshold:
                        result["recommendations"].append({"tool": "color_grade", "reason": "Color palette drift detected"})
                    # Per-project `coherence_threshold` triggers a regenerate
                    # recommendation when the overall coherence score is too low.
                    _coherence_floor = _diag_settings.get("coherence_threshold", 0.6)
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
                        _deep = ChiefDirector(self.project).evaluate_generation_quality(
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

        base_take = None
        if take_id:
            _, base_take = self._find_take(shot, take_id)
        if base_take is None:
            base_take = self._host._candidate_take(shot)
        if base_take is None:
            return {"success": False, "error": "No take available to correct"}

        video_path = base_take.get("path", "") if base_take.get("kind") != "keyframe" else ""
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
                _settings = self.project.get("global_settings", {})
                if not _settings.get("face_swap_enabled", True):
                    return {"success": False, "error": "face_swap disabled in project settings"}
                # Align with fe2aa47: use in-frame chars so we swap the face
                # of the person actually visible, not scene-chars[0].
                chars = shot.get("characters_in_frame", []) or scene.get("characters_present", [])
                primary_ref = get_reference_image(self.project, chars[0]) if chars else None
                if video_path and primary_ref:
                    result = face_swap_video_frames(str(video_path), primary_ref, out_path)
                    if result:
                        variant["path"] = result
                    else:
                        # face_swap_video_frames is a best-effort cascade
                        # (fal.ai → FaceFusion CLI → skip); None means every
                        # path failed or was unavailable.  Surface a specific
                        # reason so the operator knows the swap was not applied,
                        # rather than receiving the generic action-failed message.
                        return {
                            "success": False,
                            "error": "face_swap could not be applied (no swapper succeeded)",
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
                    result = generate_lip_sync_video(
                        character_image_path=primary_ref,
                        audio_path=audio_path,
                        output_path=out_path,
                        existing_video_path=str(video_path),
                        mode=_settings.get("lip_sync_mode", "auto"),
                        settings=_settings,
                        _cascade_out=_lipsync_cascade,
                    )
                    if result:
                        variant["path"] = result
                        if "cascade_metadata" in _lipsync_cascade:
                            variant["cascade_metadata"] = _lipsync_cascade["cascade_metadata"]
                        # Cost-track the lipsync correction (Tier F NEW-2: previously
                        # untracked). Attribute to the winning cascade engine.
                        try:
                            _ls_engine = (_lipsync_cascade.get("cascade_metadata", {})
                                          .get("engine") or "LIPSYNC")
                            self.cost_tracker.record_api_call(
                                _ls_engine, operation="lipsync",
                                shot_id=shot_id, video_id=self.project.get("id", ""),
                            )
                        except Exception:
                            logger.warning("lipsync cost record skipped", exc_info=True, extra={"shot_id": shot_id})

            elif action == "rife":
                if video_path:
                    result = generate_rife_interpolation(str(video_path), out_path)
                    if result:
                        variant["path"] = result

            elif action == "upscale":
                if video_path:
                    result = upscale_video_seedvr2(str(video_path), out_path)
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

            def _mutator(_scene: dict, project_shot: dict):
                project_shot.setdefault("postprocess_variants", []).append(variant)
                return MutationResult(variant, save=True)

            stored_variant = self._mutate_shot(shot_id, _mutator)
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
                final_path = self._host._resolve_take_path(shot, shot.get("approved_final_take_id", ""))
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
                return preview_path
            except Exception:
                logger.exception(
                    "Preview stitch failed; returning first clip",
                    extra={"scene_id": scene_id},
                )
                return valid_clips[0] if valid_clips else None
        return None
