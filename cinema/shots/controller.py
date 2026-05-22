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

import os
import time
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

from project_manager import MutationResult, mutate_project, make_take
from llm.style_director import style_rules_to_prompt_suffix
from character_manager import get_reference_image
from phase_c_assembly import generate_ai_broll
from phase_c_ffmpeg import generate_ai_video, stitch_modules
from phase_c_vision import validate_identity, face_swap_video_frames
from lip_sync import (
    generate_lip_sync_video,
    generate_rife_interpolation,
    upscale_video_seedvr2,
)

from cinema.lifecycle import LifecycleService

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
        for collection_name in ("keyframe_takes", "motion_takes", "postprocess_variants"):
            for take in shot.get(collection_name, []):
                if take.get("id") == take_id:
                    return collection_name, take
        return None, None

    def _take_output_path(self, shot_id: str, take_id: str, ext: str) -> str:
        output_dir = os.path.join(self.project_dir, "shots", shot_id, "outputs")
        os.makedirs(output_dir, exist_ok=True)
        return os.path.join(output_dir, f"{take_id}{ext}")

    def _mutate_shot(self, shot_id: str, mutator, timeout: float = 10):
        def _mutate(latest_project: dict):
            for scene in latest_project.get("scenes", []):
                for shot in scene.get("shots", []):
                    if shot.get("id") == shot_id:
                        return mutator(scene, shot)
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
        char_lora_paths = settings.get("char_lora_paths", {}) or {}
        # Pick the LoRA for the primary character in this shot. Prefer the
        # explicit primary_character field; otherwise take the first entry in
        # characters_in_frame; otherwise empty string (which yields no LoRA).
        in_frame = shot.get("characters_in_frame") or []
        primary_char_id = shot.get("primary_character") or (in_frame[0] if in_frame else "")
        char_lora_path = char_lora_paths.get(primary_char_id) or None
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
                    )
                    # Persist optimizer output for regen + telemetry
                    def _stash_cache(_scene, project_shot):
                        project_shot["optimizer_cache"] = {
                            "source_prompt": full_prompt,
                            "spec": opt_spec,
                        }
                        return MutationResult(opt_spec, save=True)
                    self._mutate_shot(shot_id, _stash_cache)
                except Exception as e:
                    print(f"[KEYFRAME] prompt_optimizer skipped: {e}")
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
            style_reference=style_reference,
            shot_hint={"prompt": full_prompt, "characters_in_frame": shot.get("characters_in_frame", []),
                       "camera": shot.get("camera", "")},
        )
        if not result or not os.path.exists(img_path):
            return {"success": False, "error": "Image generation failed"}

        identity_score = 0.0
        if primary_ref:
            from phase_c_vision import validate_identity_image
            img_sim = validate_identity_image(img_path, primary_ref, threshold=cc.get("identity_threshold", 0.70))
            identity_score = img_sim.get("similarity", 0.0)
            take["metadata"]["identity_score"] = identity_score

        take["path"] = img_path

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

    def generate_performance_take(self, scene_id: str, shot_id: str) -> dict:
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
        # We pass scene_id, not characters[], because ensure_scene_audio works
        # off the scene's dialogue lines + character voices.
        audio_path = ""
        try:
            audio_path = self._host._ensure_scene_audio(scene["id"]) or ""
        except Exception as e:
            print(f"[PERFORMANCE] scene audio unavailable ({e}); engine={engine}")

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
            except Exception as e:
                print(f"[PERFORMANCE] driving-video synth failed ({e}); engine may degrade")

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

        # Resolve the character's face anchor for the gate. Multi-character shots
        # anchor on the first listed character — operators can override via the
        # PERFORMANCE_REVIEW gate. Uses the existing character_manager helper that
        # already understands the project's character list shape.
        face_anchor = ""
        chars = shot.get("characters_in_frame", []) or []
        if chars:
            try:
                face_anchor = get_reference_image(project, chars[0]) or ""
            except Exception as e:
                print(f"[PERFORMANCE] face_anchor lookup failed for {chars[0]}: {e}")
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

    def generate_motion_take(self, scene_id: str, shot_id: str) -> dict:
        project = self._host._refresh_project_snapshot() or self.project
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

        resolved_shot_type = classify_shot_type(shot)
        raw_api = shot.get("target_api", "AUTO")
        if raw_api == "AUTO":
            template = WORKFLOW_TEMPLATES.get(resolved_shot_type, WORKFLOW_TEMPLATES["medium"])
            target_api = template["target_api"]
            video_fallbacks = template.get("video_fallbacks")
        else:
            target_api = raw_api
            video_fallbacks = None

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
        )
        final_vid = temp_vid or vid_path
        if not final_vid or not os.path.exists(final_vid):
            return {"success": False, "error": "Video generation failed"}

        identity_score = 0.0
        primary_ref = cc.get("primary_reference")
        chars_in_frame = shot.get("characters_in_frame", [])
        if chars_in_frame and primary_ref:
            vid_result = self.continuity.validate_shot(
                final_vid,
                [chars_in_frame[0]],
                shot_type=resolved_shot_type,
                mode="standard",
                attempt=0,
                max_attempts=1,
            )
            identity_score = vid_result.overall_score if hasattr(vid_result, "overall_score") else 0.0
            take["metadata"]["identity_score"] = identity_score

        take["path"] = final_vid

        def _mutator(_scene: dict, project_shot: dict):
            project_shot.setdefault("motion_takes", []).append(take)
            project_shot["generated_video"] = final_vid
            return MutationResult(take, save=True)

        stored_take = self._mutate_shot(shot_id, _mutator)
        self._runstate.shot_results[shot_id] = {
            "image": source_image,
            "video": final_vid,
            "identity_score": identity_score,
            "status": "final_review",
            "take_id": take["id"],
        }
        self._host._rebuild_review_clips()
        self._host._save_checkpoint()
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

    def regenerate_shot(self, scene_id: str, shot_id: str) -> dict:
        """Compatibility wrapper for the older regenerate endpoint."""
        project = self._host._refresh_project_snapshot() or self.project
        _, shot, _ = self._find_shot(shot_id, project, scene_id)
        if not shot:
            return {"success": False, "error": "Shot not found"}
        if shot.get("approved_keyframe_take_id"):
            return self.generate_motion_take(scene_id, shot_id)
        return self.generate_keyframe_take(scene_id, shot_id)

    def diagnose_clip(self, shot_id: str, take_id: str = "") -> dict:
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
        video_path = candidate.get("path", "") if candidate.get("kind") != "keyframe" else ""
        image_path = candidate.get("path", "") if candidate.get("kind") == "keyframe" else self._host._resolve_take_path(
            shot,
            shot.get("approved_keyframe_take_id", ""),
        ) or (self._host._latest_take(shot, "keyframe_takes") or {}).get("path", "")

        # Identity validation
        chars = scene.get("characters_present", [])
        if chars and image_path and os.path.exists(str(image_path)):
            primary_ref = get_reference_image(self.project, chars[0])
            if primary_ref:
                from phase_c_vision import validate_identity_image
                id_result = validate_identity_image(str(image_path), primary_ref)
                result["scores"]["identity"] = id_result.get("similarity", 0)
                if not id_result.get("passed", True):
                    result["recommendations"].append({"tool": "face_swap", "reason": "Low identity score"})
                    result["recommendations"].append({"tool": "regenerate", "reason": "Regenerate with strengthened identity"})

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
                chars = scene.get("characters_present", [])
                primary_ref = get_reference_image(self.project, chars[0]) if chars else None
                if video_path and primary_ref:
                    result = face_swap_video_frames(str(video_path), primary_ref, out_path)
                    if result:
                        variant["path"] = result

            elif action == "lip_sync":
                chars = scene.get("characters_present", [])
                primary_ref = get_reference_image(self.project, chars[0]) if chars else None
                audio_path = self._host._ensure_scene_audio(scene, [c for c in self.project["characters"] if c["id"] in chars])
                if video_path and primary_ref and audio_path:
                    result = generate_lip_sync_video(
                        character_image_path=primary_ref,
                        audio_path=audio_path,
                        output_path=out_path,
                        existing_video_path=str(video_path),
                        mode="auto",
                    )
                    if result:
                        variant["path"] = result

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
                preset = params.get("preset", "warm_cinema")
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
        scene = next((s for s in project["scenes"] if s["id"] == scene_id), None)
        if not scene:
            return None

        clips = self._runstate.scene_clips.get(scene_id, [])
        if not clips:
            clips = []
            for shot in scene.get("shots", []):
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
            except Exception as e_stitch:
                print(f"   [PREVIEW] Stitch failed, returning first clip: {e_stitch}")
                return valid_clips[0] if valid_clips else None
        return None
