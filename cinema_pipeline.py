"""
Cinema Production Tool — Interactive Pipeline Orchestrator
Replaces main.py's run_autonomous_pipeline() for interactive cinema production.
Orchestrates: scene decomposition → continuity enhancement → image gen → video gen
→ identity validation → FaceFusion face-swap → RIFE interpolation → Real-ESRGAN upscale
→ per-scene audio → per-scene assembly → global assembly → final export.
"""

import logging
import os
import re
import glob
import random
import subprocess
from typing import Optional, List

from project_manager import load_project, mutate_project
from phase_c_ffmpeg import two_pass_loudnorm, probe_final_media
from scene_decomposer import decompose_scene, update_scene_shots, competitive_decompose_scene
from dialogue_writer import generate_dialogue
from llm.style_director import generate_style_rules
from audio.dialogue import dialogue_cache_key, generate_dialogue_voiceover, scene_characters
from audio.music import generate_bgm
from cinema.auto_approve import record_director_review_on_shots
from cinema.context import PipelineContext
from cinema.core import PipelineCore, build_pipeline_core
from cinema.lifecycle import ThreadedLifecycle
from cinema.phases.keyframe_render import KeyframeRenderPhase
from cinema.phases.motion_render import MotionRenderPhase
from cinema.phases.performance import PerformanceCapturePhase
from cinema.runstate import RunState
from cinema.shots.controller import ShotController
from cinema.review.controller import ReviewController
from cinema.checkpoint import CheckpointStore
from cinema.aspect import resolve_output_dimensions, DEFAULT_ASPECT_RATIO, is_supported

logger = logging.getLogger(__name__)


def _normalize_filter(w: int, h: int) -> str:
    """ffmpeg -vf for clip normalization at (w,h): fit-inside + pad + 30fps.

    16:9 (1920,1080) reproduces the historical literal byte-for-byte.
    """
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps=30")


class CinemaPipeline:
    """
    Interactive cinema production pipeline with maximum API utilization
    and state-of-the-art continuity techniques.
    """

    def __init__(
        self,
        project_id: str,
        progress_callback=None,
        core: Optional[PipelineCore] = None,
        headless: bool = False,
    ):
        """
        Parameters
        ----------
        project_id:
            Project to operate on. Required even when ``core`` is
            provided, for diagnostics and error messages.
        progress_callback:
            Optional callable wired into the ThreadedLifecycle for SSE
            event emission. Defaults to ``_default_progress`` (stdout).
        core:
            Pre-built ``PipelineCore`` (long-lived deps + services). If
            None, a fresh one is built via ``build_pipeline_core(project_id)``.
            Future standalone controllers + tests can share a single
            core across multiple consumers, avoiding the cost of
            re-instantiating ContinuityEngine / ChiefDirector / LLMEnsemble /
            trackers.
        headless:
            When True, review gates do not block on operator/web approval:
            ReviewController._wait_for_gate raises GateNotSatisfiedError if
            auto-approve cannot clear a gate (for non-interactive script /
            E2E runs). Defaults to False -- web/UI runs block on
            ThreadedLifecycle until the operator approves.
        """
        self._core = core if core is not None else build_pipeline_core(project_id)

        # Lifecycle — per-run mutable runtime service. Replaces the
        # previous self.cancelled + self.paused + self._resume_event
        # quartet (see cinema/lifecycle.py). self.progress remains as a
        # property that proxies to lifecycle.report_progress, so the
        # dozens of existing `self.progress(stage, detail, percent, ...)`
        # call sites are unchanged.
        self.lifecycle = ThreadedLifecycle(
            progress_callback=progress_callback or self._default_progress
        )

        # V1.1 #5: per-run mutable state lives on a shared RunState
        # instance. Single canonical home (vs. previously scattered
        # across ShotController.shot_results, ReviewController.review_clips,
        # and CinemaPipeline's own attributes). All three controllers
        # share the SAME RunState reference -- mutations propagate.
        self._runstate = RunState(headless=headless)

        # ShotController -- composed. Cross-controller calls still flow
        # through self (the host); state reads/writes flow through
        # self._runstate.
        self._shot_ctrl = ShotController(self._core, self.lifecycle, self, self._runstate)

        # ReviewController -- composed. Same shape as ShotController.
        self._review_ctrl = ReviewController(self._core, self.lifecycle, self, self._runstate)

        # CheckpointStore -- composed. V1.1 #5 removed its host
        # protocol entirely; it now reads/writes self._runstate directly,
        # no host needed.
        self._checkpoint = CheckpointStore(self._core, self.lifecycle, self._runstate)

    # ------------------------------------------------------------------
    # PipelineCore proxies — backward-compat property accessors so the
    # mixin code that reads self.project / self.continuity / etc. keeps
    # working unchanged. All proxies return the underlying object (NOT
    # a copy), so in-place mutations like ``self.project.clear()`` in
    # _refresh_project_snapshot() continue to work correctly.
    # ------------------------------------------------------------------

    @property
    def project(self) -> dict:
        return self._core.project

    @property
    def project_dir(self) -> str:
        return self._core.project_dir

    @property
    def temp_dir(self) -> str:
        return self._core.temp_dir

    @property
    def export_dir(self) -> str:
        return self._core.export_dir

    @property
    def continuity(self):
        return self._core.continuity

    @property
    def director(self):
        return self._core.director

    @property
    def cost_tracker(self):
        return self._core.cost_tracker

    @property
    def ensemble(self):
        return self._core.ensemble

    # GENERATED BEGIN -- tools/gen_delegates.py
    # DO NOT EDIT BY HAND. Run `python tools/gen_delegates.py` to regenerate.
    # ------------------------------------------------------------------
    # RunState forwarders (one @property + setter pair per field).
    # Lets pipeline.shot_results / pipeline.scene_clips / etc. read +
    # write through to the shared self._runstate instance.
    # ------------------------------------------------------------------

    @property
    def shot_results(self) -> dict:
        return self._runstate.shot_results
    @shot_results.setter
    def shot_results(self, value: dict) -> None:
        self._runstate.shot_results = value

    @property
    def review_clips(self) -> dict:
        return self._runstate.review_clips
    @review_clips.setter
    def review_clips(self, value: dict) -> None:
        self._runstate.review_clips = value

    @property
    def scene_clips(self) -> dict:
        return self._runstate.scene_clips
    @scene_clips.setter
    def scene_clips(self, value: dict) -> None:
        self._runstate.scene_clips = value

    @property
    def scene_audio(self) -> dict:
        return self._runstate.scene_audio
    @scene_audio.setter
    def scene_audio(self, value: dict) -> None:
        self._runstate.scene_audio = value

    @property
    def shot_audio(self) -> dict:
        return self._runstate.shot_audio
    @shot_audio.setter
    def shot_audio(self, value: dict) -> None:
        self._runstate.shot_audio = value

    @property
    def scene_foley(self) -> dict:
        return self._runstate.scene_foley
    @scene_foley.setter
    def scene_foley(self, value: dict) -> None:
        self._runstate.scene_foley = value

    @property
    def foley_audio_paths(self) -> list:
        return self._runstate.foley_audio_paths
    @foley_audio_paths.setter
    def foley_audio_paths(self, value: list) -> None:
        self._runstate.foley_audio_paths = value

    @property
    def failed_shots(self) -> list:
        return self._runstate.failed_shots
    @failed_shots.setter
    def failed_shots(self, value: list) -> None:
        self._runstate.failed_shots = value

    @property
    def current_stage(self) -> str:
        return self._runstate.current_stage
    @current_stage.setter
    def current_stage(self, value: str) -> None:
        self._runstate.current_stage = value

    @property
    def current_scene_id(self) -> str:
        return self._runstate.current_scene_id
    @current_scene_id.setter
    def current_scene_id(self, value: str) -> None:
        self._runstate.current_scene_id = value

    @property
    def current_shot_id(self) -> str:
        return self._runstate.current_shot_id
    @current_shot_id.setter
    def current_shot_id(self, value: str) -> None:
        self._runstate.current_shot_id = value

    @property
    def _completed_scene_indices(self) -> set:
        return self._runstate.completed_scene_indices
    @_completed_scene_indices.setter
    def _completed_scene_indices(self, value: set) -> None:
        self._runstate.completed_scene_indices = value

    # ------------------------------------------------------------------
    # Delegates -> self._shot_ctrl
    # ------------------------------------------------------------------

    def generate_keyframe_take(self, *args, **kwargs):
        return self._shot_ctrl.generate_keyframe_take(*args, **kwargs)

    def generate_performance_take(self, *args, **kwargs):
        return self._shot_ctrl.generate_performance_take(*args, **kwargs)

    def generate_motion_take(self, *args, **kwargs):
        return self._shot_ctrl.generate_motion_take(*args, **kwargs)

    def regenerate_shot(self, *args, **kwargs):
        return self._shot_ctrl.regenerate_shot(*args, **kwargs)

    def restart_shot(self, *args, **kwargs):
        return self._shot_ctrl.restart_shot(*args, **kwargs)

    def regenerate_with_intent(self, *args, **kwargs):
        return self._shot_ctrl.regenerate_with_intent(*args, **kwargs)

    def diagnose_clip(self, *args, **kwargs):
        return self._shot_ctrl.diagnose_clip(*args, **kwargs)

    def apply_correction(self, *args, **kwargs):
        return self._shot_ctrl.apply_correction(*args, **kwargs)

    def generate_scene_preview(self, *args, **kwargs):
        return self._shot_ctrl.generate_scene_preview(*args, **kwargs)

    def _find_take(self, *args, **kwargs):
        return self._shot_ctrl._find_take(*args, **kwargs)

    def _mutate_shot(self, *args, **kwargs):
        return self._shot_ctrl._mutate_shot(*args, **kwargs)

    # ------------------------------------------------------------------
    # Delegates -> self._review_ctrl
    # ------------------------------------------------------------------

    def approve_shot_plan(self, *args, **kwargs):
        return self._review_ctrl.approve_shot_plan(*args, **kwargs)

    def approve_take(self, *args, **kwargs):
        return self._review_ctrl.approve_take(*args, **kwargs)

    def proceed_to_assembly(self, *args, **kwargs):
        return self._review_ctrl.proceed_to_assembly(*args, **kwargs)

    def _project_gate_status(self, *args, **kwargs):
        return self._review_ctrl._project_gate_status(*args, **kwargs)

    def _gate_satisfied(self, *args, **kwargs):
        return self._review_ctrl._gate_satisfied(*args, **kwargs)

    def _wait_for_gate(self, *args, **kwargs):
        return self._review_ctrl._wait_for_gate(*args, **kwargs)

    def _rebuild_review_clips(self, *args, **kwargs):
        return self._review_ctrl._rebuild_review_clips(*args, **kwargs)

    def _all_shots(self, *args, **kwargs):
        return self._review_ctrl._all_shots(*args, **kwargs)

    def _latest_take(self, *args, **kwargs):
        return self._review_ctrl._latest_take(*args, **kwargs)

    def _resolve_take_path(self, *args, **kwargs):
        return self._review_ctrl._resolve_take_path(*args, **kwargs)

    def _candidate_take(self, *args, **kwargs):
        return self._review_ctrl._candidate_take(*args, **kwargs)

    # ------------------------------------------------------------------
    # Delegates -> self._checkpoint
    # ------------------------------------------------------------------

    def has_checkpoint(self, *args, **kwargs):
        return self._checkpoint.has_checkpoint(*args, **kwargs)

    def resume_info(self, *args, **kwargs):
        return self._checkpoint.resume_info(*args, **kwargs)

    def _save_checkpoint(self, *args, **kwargs):
        return self._checkpoint._save_checkpoint(*args, **kwargs)

    def _restore_from_checkpoint(self, *args, **kwargs):
        return self._checkpoint._restore_from_checkpoint(*args, **kwargs)

    def _clear_checkpoint(self, *args, **kwargs):
        return self._checkpoint._clear_checkpoint(*args, **kwargs)

    # GENERATED END








    def _default_progress(self, stage: str, detail: str, percent: float = 0,
                          scene_id: str = "", shot_id: str = "",
                          image_url: str = "", identity_score: float = -1,
                          director_review: dict = None, **kwargs):
        # DEBUG severity so non-SSE callers (CLI, tests) don't double-log
        # when an adjacent explicit logger.info/warning has already
        # emitted the same event. The SSE path replaces this default at
        # runtime with the queue callback, so SSE consumers are
        # unaffected. Preserves all caller-provided context in `extra`
        # (previously image_url / identity_score / director_review /
        # **kwargs were silently dropped).
        extra = {
            "stage": stage,
            "percent": percent,
            "scene_id": scene_id,
            "shot_id": shot_id,
            "detail": detail,
        }
        if image_url:
            extra["image_url"] = image_url
        if identity_score != -1:
            extra["identity_score"] = identity_score
        if director_review:
            extra["director_review"] = director_review
        extra.update({k: v for k, v in kwargs.items() if v is not None})
        logger.debug("progress", extra=extra)

    # ------------------------------------------------------------------
    # Lifecycle — thin delegations to self.lifecycle (ThreadedLifecycle).
    # ``self.cancelled`` and ``self.paused`` are kept as backward-compat
    # properties so existing checks like ``if self.cancelled:`` keep
    # working everywhere they appear in generate() and the controllers.
    # ------------------------------------------------------------------

    @property
    def cancelled(self) -> bool:
        return self.lifecycle.is_cancelled()

    @property
    def paused(self) -> bool:
        return self.lifecycle.is_paused()

    def cancel(self):
        self.lifecycle.cancel()

    def pause(self):
        """Pause the pipeline at the next checkpoint."""
        if not self.lifecycle.is_paused():
            self.lifecycle.pause()
            self.progress("PAUSED", "Pipeline paused — waiting for resume", -1)

    def resume(self):
        """Resume a paused pipeline."""
        if self.lifecycle.is_paused():
            self.lifecycle.resume()
            self.progress("RESUMED", "Pipeline resumed", -1)

    def _check_pause(self):
        """Checkpoint: block if paused, return False if cancelled.

        Preserved as a method (not just self.lifecycle.check_pause()) so
        the existing ``if not self._check_pause(): return None`` pattern
        in generate() keeps working — those call sites need the bool.
        """
        self.lifecycle.check_pause()
        return not self.lifecycle.is_cancelled()

    @property
    def progress(self):
        """Thin proxy: self.progress(...) routes to self.lifecycle.report_progress(...).

        Kept as a property returning the bound method so existing
        ``self.progress(stage, detail, percent, ...)`` call sites are
        unchanged. Looks identical to a bound method to the caller.
        """
        return self.lifecycle.report_progress

    def get_state(self) -> dict:
        """Return current pipeline state for the UI."""
        gate_status = self._project_gate_status()
        return {
            "paused": self.paused,
            "cancelled": self.cancelled,
            "current_stage": self.current_stage,
            "current_scene_id": self.current_scene_id,
            "current_shot_id": self.current_shot_id,
            "shot_results": self.shot_results,
            "failed_shots": self.failed_shots,
            "scenes_completed": len(self.scene_clips),
            "gate_status": gate_status,
        }

    def _refresh_project_snapshot(self, timeout: float = 10) -> Optional[dict]:
        latest = load_project(self.project["id"], timeout=timeout)
        if not latest:
            return None

        # P1-3 migration template (S10) — parity with continuity_engine.py
        # CharacterContinuityTracker.__init__ + LocationPersistence.__init__.
        # External-writer site rebuilds the typed-id-keyed dicts when the
        # project state is reloaded. Validates the reloaded snapshot at the
        # boundary (raises in CINEMA_STRICT_SCHEMA mode) + uses typed
        # iteration for the .id key extraction, while preserving the
        # original dict references as values (consumer sites at
        # continuity_engine.py:221 + :608 continue to do dict-attribute
        # access on the values).
        #
        # I-1 fix (Lane V #9, cycle 11): validate BEFORE swapping self.project,
        # not after. If validation raises ValidationError, self.project must
        # remain unchanged so tracker indices at lines below stay coherent
        # with the prior state. The previous order (clear → update →
        # validate) created a partial-state window: self.project swapped to
        # `latest` malformed dict; validate raised; tracker indices never
        # rebuilt → continuity engines pointed at stale id-keys against the
        # new project dict. Reachable when project survives _validate_project's
        # warn-mode but fails bare Pydantic strict checks.
        from domain.models import Project as _Project
        latest_typed = _Project.model_validate(latest)
        self.project.clear()
        self.project.update(latest)
        self.continuity.project = self.project
        self.continuity.character_tracker.project = self.project
        self.continuity.character_tracker.characters = {
            c.id: self.project["characters"][i] for i, c in enumerate(latest_typed.characters)
        }
        self.continuity.location_persistence.project = self.project
        self.continuity.location_persistence.locations = {
            l.id: self.project["locations"][i] for i, l in enumerate(latest_typed.locations)
        }
        self.director.project = self.project
        return self.project

















    def _ensure_scene_audio(self, scene: dict, characters: list[dict]) -> Optional[str]:
        scene_id = scene.get("id", "")
        # In-memory fast path: already rendered this session.
        existing = self.scene_audio.get(scene_id)
        if existing and os.path.exists(existing):
            return existing

        dialogue = scene.get("dialogue", "")
        action = scene.get("action", "")
        # Pull project language from settings so dialogue is generated in the
        # target language (Korean, Japanese, etc.). Default English when unset.
        proj_settings = self.project.get("global_settings", {}) if hasattr(self, "project") else {}
        lang = proj_settings.get("language", "English")
        if characters and not dialogue and action:
            dialogue_lines = generate_dialogue(scene, characters, scene.get("mood", "neutral"), language=lang, cost_tracker=self.cost_tracker)
        elif dialogue:
            if isinstance(dialogue, list):
                dialogue_lines = dialogue
            else:
                # LLM-generated dialogue — nondeterministic per run; these won't
                # cache-hit across fresh instances (different dialogue_lines each
                # call), but explicit dialogue lists (the common case) do.
                dialogue_lines = generate_dialogue(scene, characters, scene.get("mood", "neutral"), language=lang, cost_tracker=self.cost_tracker)
        else:
            return None

        if not dialogue_lines:
            return None

        # Disk-first check (ticket T-B): content-keyed output path. If an
        # artifact with the same key exists on disk, reuse it without calling
        # generate_dialogue_voiceover again — prevents paid TTS regeneration
        # on re-assembly when the dialogue/voices/language are unchanged.
        key = dialogue_cache_key(dialogue_lines, characters, lang)
        output_path = os.path.join(self.temp_dir, f"audio_{scene_id}_{key}.mp3")
        if os.path.exists(output_path):
            print(f"   [SCENE-AUDIO] Cache hit (key={key}): {output_path}")
            self.scene_audio[scene_id] = output_path
            self._save_checkpoint()
            return output_path

        # Thread the project's UI settings via PipelineContext so
        # dialogue_mode_enabled, forced_alignment_enabled, and language
        # are honored via get_project_setting — without this the dialogue
        # helpers fall back to their hard-coded defaults.
        dialogue_ctx = PipelineContext(
            global_settings=dict(self.project.get("global_settings", {})) if self.project else {},
        )
        result = generate_dialogue_voiceover(
            dialogue_lines,
            characters,
            output_path,
            ctx=dialogue_ctx,
            cost_tracker=self.cost_tracker,  # T5: gate audio spend on pipeline budget
        )
        if result and os.path.exists(output_path):
            self.scene_audio[scene_id] = output_path
            self._save_checkpoint()
            return output_path
        return None

    def _ensure_shot_audio(
        self,
        shot: dict,
        scene: dict,
        characters: list[dict],
    ) -> Optional[str]:
        """Render and cache the per-shot TTS for a single dialogue line.

        Mirrors _ensure_scene_audio but operates on shot.get("dialogue")
        instead of the full scene dialogue block.  Returns None when the
        shot carries no own dialogue line — the caller should fall back to
        _ensure_scene_audio (scene-level TTS).

        Keyed on shot["id"] so each shot's line is rendered independently,
        giving the overlay pass a correctly-sized audio clip.
        """
        shot_id = shot.get("id", "")
        # In-memory fast path: already rendered this session.
        existing = self.shot_audio.get(shot_id)
        if existing and os.path.exists(existing):
            return existing

        dialogue = shot.get("dialogue")
        if not dialogue:
            return None

        # Wrap the single shot line as a one-element dialogue list so it
        # feeds generate_dialogue_voiceover the same way scene dialogue does.
        if isinstance(dialogue, str):
            dialogue_lines = [{"text": dialogue}]
        elif isinstance(dialogue, list):
            dialogue_lines = dialogue
        else:
            return None

        if not dialogue_lines:
            return None

        # Pull project language from settings — mirrors the scene site at
        # cinema_pipeline.py:_ensure_scene_audio for the same key computation.
        proj_settings = self.project.get("global_settings", {}) if hasattr(self, "project") else {}
        lang = proj_settings.get("language", "English")

        # Disk-first check (ticket T-B): content-keyed output path. Mirrors
        # _ensure_scene_audio exactly — same key function, same check shape.
        key = dialogue_cache_key(dialogue_lines, characters, lang)
        output_path = os.path.join(self.temp_dir, f"audio_{shot_id}_{key}.mp3")
        if os.path.exists(output_path):
            print(f"   [SHOT-AUDIO] Cache hit (key={key}): {output_path}")
            self.shot_audio[shot_id] = output_path
            return output_path

        dialogue_ctx = PipelineContext(
            global_settings=dict(self.project.get("global_settings", {})) if self.project else {},
        )
        result = generate_dialogue_voiceover(
            dialogue_lines,
            characters,
            output_path,
            ctx=dialogue_ctx,
            cost_tracker=self.cost_tracker,  # T5: gate audio spend on pipeline budget
        )
        if result and os.path.exists(output_path):
            self.shot_audio[shot_id] = output_path
            return output_path
        return None

    def _ensure_bgm(self, settings: dict) -> str:
        self.progress("AUDIO", "Generating background music...", 5)
        music_mood = settings.get("music_mood", "suspense")
        bgm_path = os.path.join(self.temp_dir, f"bgm_{music_mood}.mp3")
        if not os.path.exists(bgm_path):
            generate_bgm(music_mood, bgm_path, duration=47, prefer_provider="AUTO", cost_tracker=self.cost_tracker)  # T5: gate audio spend; AUTO = Suno V5 → FAL fallback

        if os.path.exists(bgm_path):
            try:
                from audio.music import master_music
                mastered_path = os.path.join(self.temp_dir, f"bgm_{music_mood}_mastered.mp3")
                _ms_preset = (self.project.get("global_settings", {}) if self.project else {}).get("music_mastering", "cinema_master")
                mastered = master_music(bgm_path, mastered_path, preset=_ms_preset)
                if mastered and os.path.exists(mastered):
                    bgm_path = mastered
                    self.progress("AUDIO", "BGM mastered (cinema_master preset)", 6)
            except Exception:
                # Non-critical: BGM mix degrades gracefully; emit at WARNING
                # so log monitors that alert on ERROR don't false-positive.
                logger.warning("BGM mastering skipped (non-critical)", exc_info=True)
        return bgm_path

    def _ensure_scene_foley(self, scene: dict) -> str:
        """Generate (and cache) environmental foley for a single scene.

        Per-scene caching: one foley file per scene_id, stored in temp_dir.
        Returns the foley file path on success, empty string on failure so
        callers can treat it as a boolean — mirrors _ensure_scene_audio's
        graceful-degradation pattern (scene_packages["foley"] stays empty
        when foley is unavailable).

        The tri-mix consumption of the returned path is T3 scope.
        """
        scene_id = scene.get("id", "")
        existing = self.scene_foley.get(scene_id)
        if existing and os.path.exists(existing):
            return existing

        # Aggregate unique non-empty scene_foley descriptors across the scene's shots
        descriptors: list[str] = []
        for shot in scene.get("shots", []):
            f = shot.get("scene_foley", "").strip()
            if f and f not in descriptors:
                descriptors.append(f)
        scene_foley_descriptor = ", ".join(descriptors) or "subtle ambient room tone"

        # Rough duration proxy: number of shots × 5 s, capped at 60 s
        num_shots = len(scene.get("shots", []))
        scene_duration = float(min(num_shots * 5, 60)) if num_shots else 30.0

        foley_path = os.path.join(self.temp_dir, f"foley_{scene_id}.mp3")

        self.progress("AUDIO", f"Generating foley for scene {scene_id}...", 5)
        try:
            from audio.foley import _build_foley_prompt, generate_stability_foley
            prompt = _build_foley_prompt(scene_foley_descriptor)
            result = generate_stability_foley(prompt, foley_path, duration=scene_duration, cost_tracker=self.cost_tracker)  # T5: gate audio spend on pipeline budget
            if result and os.path.exists(result):
                self.scene_foley[scene_id] = result
                self._runstate.foley_audio_paths.append(result)
                self._save_checkpoint()
                return result
        except Exception:
            logger.warning("Foley generation skipped for scene %s (non-critical)", scene_id, exc_info=True)
        return ""

    @staticmethod
    def _approved_take_metadata(shot: dict) -> dict:
        """Return the metadata dict of the shot's approved final take, or {}.

        Look up approved_final_take_id in motion_takes then postprocess_variants.
        Used by _build_scene_packages to check audio_embedded on approved takes.
        """
        take_id = shot.get("approved_final_take_id", "")
        if not take_id:
            return {}
        for collection in ("motion_takes", "postprocess_variants"):
            for take in shot.get(collection) or []:
                if isinstance(take, dict) and take.get("id") == take_id:
                    return take.get("metadata") or {}
        return {}

    def _build_scene_packages(self, project: Optional[dict] = None) -> tuple[list[dict], list[str]]:
        active_project = project or self.project
        scene_packages = []
        missing_shots: list[str] = []
        self.scene_clips = {}

        for scene in active_project.get("scenes", []):
            scene_id = scene.get("id", "")
            clips = []
            # F1b assembler guard: track whether EVERY approved shot in this
            # scene has audio_embedded=True.  We only suppress standalone TTS
            # when ALL shots are embedded — mixed scenes keep TTS for the
            # non-embedded shots (conservative choice: double-voice on one
            # embedded shot is less bad than silent non-embedded shots).
            approved_shot_count = 0
            all_embedded_count = 0
            for shot in scene.get("shots", []):
                final_take_id = shot.get("approved_final_take_id", "")
                final_path = self._resolve_take_path(shot, final_take_id)
                if not final_path or not os.path.exists(final_path):
                    missing_shots.append(shot.get("id", ""))
                    continue
                clips.append(final_path)
                approved_shot_count += 1
                take_meta = self._approved_take_metadata(shot)
                if take_meta.get("audio_embedded") or take_meta.get("dialogue_audio_in_clip"):
                    all_embedded_count += 1

            self.scene_clips[scene_id] = clips
            characters = scene_characters(active_project.get("characters", []), scene)
            # Suppress standalone TTS only when EVERY approved shot is embedded.
            # Mixed-embedded scenes: include TTS to avoid silent non-embedded shots.
            all_shots_embedded = (
                approved_shot_count > 0 and all_embedded_count == approved_shot_count
            )
            if all_shots_embedded:
                scene_audio = None
                logger.info(
                    "[DIALOGUE] scene=%s: all %d shots are audio-embedded "
                    "— suppressing standalone TTS from mux to avoid double-voice",
                    scene_id,
                    approved_shot_count,
                )
            else:
                scene_audio = self._ensure_scene_audio(scene, characters)
                if all_embedded_count > 0:
                    # Mixed scene: some embedded, some not.  Log for observability.
                    logger.info(
                        "[DIALOGUE] scene=%s: %d/%d shots audio-embedded (mixed) "
                        "— keeping TTS for non-embedded shots",
                        scene_id,
                        all_embedded_count,
                        approved_shot_count,
                    )
            foley_path = self._ensure_scene_foley(scene)
            scene_packages.append({
                "scene_id": scene_id,
                "clips": clips,
                "audio": scene_audio,
                "foley": [foley_path] if foley_path else [],
            })

        return scene_packages, missing_shots




    # ------------------------------------------------------------------
    # DIRECTOR'S CUT — Correction & Diagnosis
    # ------------------------------------------------------------------




    def _assemble_approved_takes_core(self) -> dict:
        """Re-stitch the final cut from current approved takes (S21 helper).

        Encapsulates steps 1-5 of the full assembly path:
            1. refresh project snapshot
            2. REVIEW-gate check (all approved_final_take_id populated)
            3. build per-scene packages (verify approved take mp4s exist)
            4. per-scene preview generation
            5. _assemble_final -> final_path

        Returns the same shape as ``assemble_approved_takes`` on the success
        path (``{"success": True, "final_path": str}``) and on the failure
        paths (``{"success": False, "error": str}``), but DOES NOT run:
            6. the SCREENING gate-wait (S19)
            7. cleanup_project
            8. cost summary
            9. _clear_checkpoint + COMPLETE progress

        Those steps are appropriate for a *fresh* full-pipeline run that
        terminates on operator approval. For the S21 re-assemble path
        (operator iterating DURING SCREENING), they would:
            - SCREENING gate-wait: DEADLOCK the Flask request thread.
              The operator is iterating BEFORE approving; the gate
              predicate ``is_screening_approved`` is False by design,
              and the request thread's fresh pipeline is not the one
              ``/screening/approve`` would ``signal_gate`` on. Closes
              S21 code-quality review Critical #1.
            - cleanup_project: remove temp files that further iterations
              may still need.
            - _clear_checkpoint + COMPLETE: would prematurely tear down
              the original pipeline's checkpoint and emit a misleading
              "COMPLETE" progress event mid-screening.

        Idempotent — safe to call repeatedly on the same project state;
        each call produces a fresh ``final_cinema.mp4`` rewrite.
        """
        project = self._refresh_project_snapshot() or self.project
        if not self._gate_satisfied("REVIEW", project):
            missing = [
                shot.get("id", "")
                for _, _, shot in self._all_shots(project)
                if not shot.get("approved_final_take_id")
            ]
            return {"success": False, "error": f"Final approvals missing for: {', '.join(missing)}"}

        settings = project.get("global_settings", {})
        bgm_path = self._ensure_bgm(settings)
        scene_data, missing_shots = self._build_scene_packages(project)
        if missing_shots:
            return {"success": False, "error": f"Approved take files are missing for: {', '.join(missing_shots)}"}

        preview_total = max(len(scene_data), 1)
        for idx, scene_package in enumerate(scene_data):
            scene_id = scene_package.get("scene_id", "")
            self.current_stage = "SCENE_PREVIEW"
            self.current_scene_id = scene_id
            percent = 86 + int((idx / preview_total) * 4)
            self.progress("SCENE_PREVIEW", f"Building scene preview for {scene_id}", percent, scene_id=scene_id)
            preview_path = self.generate_scene_preview(scene_id)
            if preview_path:
                scene_package["preview"] = preview_path

        self.current_stage = "ASSEMBLY"
        self.progress("ASSEMBLY", "Assembling final video...", 92)
        final_path = self._assemble_final(scene_data, bgm_path, settings)
        if not final_path or not os.path.exists(final_path):
            return {"success": False, "error": "Final assembly failed"}

        return {"success": True, "final_path": final_path}

    def assemble_approved_takes(self) -> dict:
        """Full-pipeline assembly path: core re-stitch + SCREENING gate + cleanup.

        The observable contract for existing callers (``generate`` and
        ``api_proceed_assembly``) is unchanged: a successful call ends
        with ``COMPLETE`` progress at 100% and returns
        ``{"success": True, "final_path": <path>}``. Failures short-
        circuit identically to pre-S21 behaviour.

        The S21 re-assemble endpoint deliberately calls
        ``_assemble_approved_takes_core`` instead, bypassing the
        SCREENING gate-wait + cleanup + cost summary tail (see docstring
        on the core helper for the deadlock rationale).
        """
        core_result = self._assemble_approved_takes_core()
        if not core_result.get("success"):
            return core_result
        final_path = core_result["final_path"]

        # S19 Surface B (cycle-9): SCREENING gate.
        # Behind CINEMA_SCREENING_STAGE flag (§7.7.3 Class B opt-out UX flag;
        # default ON as of v5.1+ flag-flip 2026-05-26). When ON (the default),
        # after the assembled mp4 exists the pipeline enters SCREENING and polls
        # `project.screening_approved` until the operator signals proceed via
        # POST /api/projects/<pid>/screening/approve. When explicitly opted out
        # (CINEMA_SCREENING_STAGE=0), pipeline goes ASSEMBLY -> CLEANUP -> COMPLETE
        # as before -- legacy-compatible pre-flip behavior.
        # Director-seat REPLY Q4 endorsed gate-predicate parity with the existing four
        # review gates (PLAN_REVIEW / KEYFRAME_REVIEW / PERFORMANCE_REVIEW / REVIEW);
        # SCREENING uses the same wait_for_gate(name, predicate) machinery.
        from cinema.screening import (
            SCREENING_STAGE_NAME,
            _screening_stage_enabled,
            is_screening_approved,
        )
        if _screening_stage_enabled(self.project):
            self.current_stage = SCREENING_STAGE_NAME
            self.progress(SCREENING_STAGE_NAME, "Awaiting operator screening approval...", 95)

            def _screening_predicate() -> bool:
                fresh = self._refresh_project_snapshot() or self.project
                return is_screening_approved(fresh)

            opened = self.lifecycle.wait_for_gate(
                SCREENING_STAGE_NAME, _screening_predicate,
            )
            if not opened:
                # wait_for_gate returns False only when the run was cancelled.
                self.progress("CANCELLED", "Pipeline cancelled during screening", 0)
                return {"success": False, "error": "Cancelled during screening"}
            self.progress(SCREENING_STAGE_NAME, "Operator approved final cut", 99)

        try:
            from cleanup import cleanup_project
            cleanup_result = cleanup_project(self.project["id"], aggressive=False)
            if cleanup_result["files_deleted"] > 0:
                self.progress("CLEANUP", f"Cleaned {cleanup_result['files_deleted']} temp files ({cleanup_result['mb_freed']} MB)", 98)
        except Exception:
            # Non-fatal: cleanup is best-effort; emit at WARNING.
            logger.warning("Auto-cleanup failed (non-fatal)", exc_info=True)

        try:
            video_id = self.project.get("id", "unknown")
            cost_summary = self.cost_tracker.get_video_cost(video_id)
            if cost_summary.get("total_usd", 0) > 0:
                logger.info(
                    "Cost summary: total=$%.2f llm=$%.2f api=$%.2f",
                    cost_summary["total_usd"],
                    cost_summary.get("llm_usd", 0),
                    cost_summary.get("api_usd", 0),
                    extra={
                        "video_id": video_id,
                        "total_usd": cost_summary["total_usd"],
                        "llm_usd": cost_summary.get("llm_usd", 0),
                        "api_usd": cost_summary.get("api_usd", 0),
                    },
                )
        except Exception:
            # Reporting-only failure; emit at WARNING (the run itself succeeded).
            logger.warning("Could not retrieve cost summary", exc_info=True)

        self._clear_checkpoint()
        self.progress("COMPLETE", f"Video exported: {final_path}", 100)
        return {"success": True, "final_path": final_path}

    # ------------------------------------------------------------------
    # MAIN PIPELINE
    # ------------------------------------------------------------------

    def generate(self, resume: bool = False) -> Optional[str]:
        """
        Full production pipeline. Returns path to final video or None on failure.
        Pass resume=True to continue from the last checkpoint.
        """
        project = self._refresh_project_snapshot() or self.project
        scenes = project.get("scenes", [])
        if not scenes:
            self.progress("ERROR", "No scenes defined in project", 0)
            return None

        if resume:
            self._restore_from_checkpoint()
            self._rebuild_review_clips(project)

        settings = project.get("global_settings", {})
        self.progress("STYLE", "Generating production style rules...", 2)
        style_rules = settings.get("style_rules", {})
        if not style_rules:
            style_rules = generate_style_rules(
                project_name=project["name"],
                mood=settings.get("music_mood", "cinematic"),
                color_palette=settings.get("color_palette", ""),
                music_mood=settings.get("music_mood", "suspense"),
                aspect_ratio=settings.get("aspect_ratio", DEFAULT_ASPECT_RATIO),
                cost_tracker=self.cost_tracker,  # T5: gate planning LLM spend on pipeline budget
            )
            # P1-3 migration template (S10 + part 9 Variant 1; B-006-broad-A) --
            # inner mutator-scope validate under the per-project lock.
            # Simplified: nested-key write into global_settings.style_rules,
            # no typed-iterate-for-find needed. Outer boundary validate is
            # transitively provided by self._refresh_project_snapshot() at
            # line 761 above (cycle-11 aeccc49 added validate-before-swap),
            # so `project` here is already pydantic-validated. See
            # docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1" for the
            # canonical shape (cycle-10 part 9 f8cd45f / cycle-11 part 11 c296105).
            from domain.models import Project as _Project

            def _persist_style_rules(latest_project: dict):
                _Project.model_validate(latest_project)  # inner mutator-scope validate
                latest_settings = latest_project.setdefault("global_settings", {})
                latest_settings["style_rules"] = style_rules
                return latest_settings["style_rules"]

            mutate_project(
                project["id"],
                _persist_style_rules,
                timeout=10,
                snapshot=self.project,
            )
            settings = project.get("global_settings", {})

        self._ensure_bgm(settings)

        for scene_idx, scene in enumerate(scenes):
            if self.cancelled:
                self.progress("CANCELLED", "Pipeline cancelled by user", 0)
                return None

            scene_id = scene["id"]
            scene_title = scene.get("title", f"Scene {scene_idx + 1}")
            self.progress("SCENE", f"Processing scene {scene_idx+1}/{len(scenes)}: {scene_title}", 10 + scene_idx)
            self.current_stage = "SCENE"
            self.current_scene_id = scene_id

            # --- 2a. Scene decomposition ---
            chars_in_scene = scene_characters(project.get("characters", []), scene)
            location = next(
                (l for l in project["locations"] if l["id"] == scene.get("location_id")),
                {"description": "an unspecified cinematic location", "prompt_fragment": ""},
            )

            shots = scene.get("shots", [])
            if not shots:
                self.progress("DECOMPOSE", f"Decomposing scene into shots...", 12 + scene_idx)
                use_competitive = settings.get("competitive_generation", True)
                if use_competitive:
                    try:
                        shots = competitive_decompose_scene(scene, chars_in_scene, location, settings, style_rules, cost_tracker=self.cost_tracker)
                    except Exception:
                        logger.exception(
                            "Competitive decomposition failed, falling back to standard",
                            extra={"scene_id": scene_id},
                        )
                        shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules, cost_tracker=self.cost_tracker)
                else:
                    shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules, cost_tracker=self.cost_tracker)

                # CHIEF DIRECTOR VALIDATION — review shots before generation
                self.progress("DIRECTOR", "Chief Director reviewing shots...", 13 + scene_idx)
                review = self.director.validate_shot_prompts(shots, scene)
                if review.get("decision") == "MODIFIED":
                    shots = review.get("shots", shots)
                    logger.info(
                        "Shots modified by chief director",
                        extra={
                            "scene_id": scene_id,
                            "violations_count": len(review.get("violations", [])),
                        },
                    )
                elif review.get("decision") == "REJECTED":
                    logger.warning(
                        "Shots REJECTED by chief director, regenerating with corrections",
                        extra={"scene_id": scene_id},
                    )
                    # Regenerate with stricter constraints
                    shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules, cost_tracker=self.cost_tracker)

                # Persist the ChiefDirector verdict onto each shot so the
                # PLAN_REVIEW auto-approve gate can read it. This is the writer
                # for _rules_for_plan's contract; without it plan auto-approve
                # always vetoes (director_review absent) and a non-interactive
                # run hangs forever at the gate.
                record_director_review_on_shots(shots, review)
                update_scene_shots(project, scene_id, shots)
                self._save_checkpoint()
            self._ensure_scene_audio(scene, chars_in_scene)

        if not self._wait_for_gate("PLAN_REVIEW", "Approve all shot plans to continue", 25):
            self.progress("CANCELLED", "Pipeline cancelled during shot-plan review", 0)
            return None

        # Slice E (Option B): the per-shot keyframe + motion loops are
        # extracted into dedicated Phase classes so they can be invoked
        # independently from main.py or test code. Gates remain inline
        # because they're not phase-shaped (they wait on operator input).
        # Thread per-project UI settings into ctx so audio/lipsync/etc. helpers
        # can resolve user-tunable knobs via get_project_setting(ctx, key, default).
        # Without this, every getattr(settings, knob) read at audio/voiceover.py,
        # audio/foley.py, audio/music.py, audio/dialogue.py, lip_sync.py silently
        # returns None and the user's UI choice is ignored.
        project = self._refresh_project_snapshot() or self.project
        ctx = PipelineContext(
            lifecycle=self.lifecycle,
            global_settings=dict(project.get("global_settings", {})) if project else {},
            language=(project.get("global_settings", {}) if project else {}).get("language", "English"),
        )

        def _on_keyframe_fail(scene_id: str, shot_id: str, error: str):
            self.failed_shots.append(shot_id)
            self.progress(
                "SHOT_FAILED",
                error or "Keyframe generation failed",
                40,
                scene_id=scene_id,
                shot_id=shot_id,
            )

        keyframe_result = KeyframeRenderPhase(
            shot_generator=self,
            project=project,
            on_failure=_on_keyframe_fail,
        ).run(ctx)
        self.progress("KEYFRAME_DONE", keyframe_result.message, 50)
        if self.lifecycle.is_cancelled():
            self.progress("CANCELLED", "Pipeline cancelled by user", 0)
            return None

        if not self._wait_for_gate("KEYFRAME_REVIEW", "Approve all keyframes to continue", 55):
            self.progress("CANCELLED", "Pipeline cancelled during keyframe review", 0)
            return None

        project = self._refresh_project_snapshot() or self.project

        # --- PERFORMANCE CAPTURE PHASE (handoff §10) ---
        # Sits between KEYFRAME_REVIEW and motion render. Routes each shot to
        # an engine (ACT_ONE / LIVE_PORTRAIT / VIGGLE) or SKIP. The autopilot
        # path uses Mode B (TTS-driven driving face synth) when no operator
        # upload is provided. Operator can override via PERFORMANCE_REVIEW gate.
        def _on_performance_fail(scene_id: str, shot_id: str, error: str):
            self.failed_shots.append(shot_id)
            self.progress(
                "SHOT_FAILED",
                error or "Performance capture failed",
                60,
                scene_id=scene_id, shot_id=shot_id,
            )

        performance_result = PerformanceCapturePhase(
            shot_generator=self,
            project=project,
            on_failure=_on_performance_fail,
        ).run(ctx)
        self.progress("PERFORMANCE_DONE", performance_result.message, 62)
        if self.lifecycle.is_cancelled():
            self.progress("CANCELLED", "Pipeline cancelled by user", 0)
            return None

        # PERFORMANCE_REVIEW gate — operator can preview each take, re-record
        # (upload a new driving video), or skip. Gate is auto-skipped when
        # every shot routed to SKIP (handoff §19 open question #4).
        project = self._refresh_project_snapshot() or self.project
        all_skipped = all(
            (shot.get("performance_engine") or "").upper() == "SKIP"
            or not shot.get("approved_keyframe_take_id")
            for scene in project.get("scenes", [])
            for shot in scene.get("shots", [])
        )
        if not all_skipped:
            if not self._wait_for_gate(
                "PERFORMANCE_REVIEW",
                "Review performance takes — approve, re-record, or skip",
                65,
            ):
                self.progress("CANCELLED", "Pipeline cancelled during performance review", 0)
                return None
            project = self._refresh_project_snapshot() or self.project
        else:
            self.progress(
                "PERFORMANCE_SKIPPED_GATE",
                "All shots routed to SKIP — skipping performance review gate",
                65,
            )

        # --- MOTION RENDER PHASE (now downstream of performance capture) ---
        def _on_motion_fail(scene_id: str, shot_id: str, error: str):
            self.failed_shots.append(shot_id)
            self.progress(
                "SHOT_FAILED",
                error or "Motion generation failed",
                72,
                scene_id=scene_id,
                shot_id=shot_id,
            )

        motion_result = MotionRenderPhase(
            shot_generator=self,
            project=project,
            on_failure=_on_motion_fail,
        ).run(ctx)
        # An aborted phase (budget halt, cancel) must NOT announce
        # MOTION_DONE at 80% — that event replaces `latest` in the UI and
        # masks the halt the operator needs to see (operator Lane V K2
        # residual, promoted by N3). No FE consumer keys on MOTION_DONE
        # (grep-verified), so the conditional is additive.
        if motion_result.ok:
            self.progress("MOTION_DONE", motion_result.message, 80)
        else:
            self.progress("MOTION_HALTED", motion_result.message, 72)
        if self.lifecycle.is_cancelled():
            self.progress("CANCELLED", "Pipeline cancelled by user", 0)
            return None

        project = self._refresh_project_snapshot() or self.project
        self._rebuild_review_clips(project)
        self._save_checkpoint()
        if not self._wait_for_gate("REVIEW", "Approve all final shot takes before assembly", 82):
            self.progress("CANCELLED", "Pipeline cancelled during final review", 0)
            return None

        if self.cancelled:
            return None

        assembly_result = self.assemble_approved_takes()
        if assembly_result.get("success"):
            return assembly_result.get("final_path")

        self.progress("ERROR", assembly_result.get("error", "Final assembly failed"), 95)
        return None

    # ------------------------------------------------------------------
    # FINAL ASSEMBLY
    # ------------------------------------------------------------------

    def _apply_final_loudnorm(self, final_path: str) -> None:
        """Re-normalize final video audio in-place via two-pass EBU R128.

        Single-pass loudnorm (used inside the BGM mix above) approximates to
        ±1.5 LU of target; the two-pass measure-then-normalize converges to
        ±0.1 LU. Audible on dialogue-heavy content. On failure the original
        file is left untouched (two_pass_loudnorm returns False).

        After loudnorm (success or failure), probes the final artifact and
        persists project["media_report"] via mutate_project. Probe/persist
        errors are logged as warnings and do NOT affect the assembly outcome.
        (U3 — Final-media conformance)
        """
        normed = final_path.replace(".mp4", "_loud.mp4")
        normed_ok = two_pass_loudnorm(final_path, normed)
        if normed_ok:
            os.replace(normed, final_path)
            logger.info(
                "Two-pass EBU R128 loudnorm applied",
                extra={"final_path": os.path.basename(final_path)},
            )

        # ---- U3: probe the artifact and persist media_report ----
        try:
            import datetime
            report = probe_final_media(final_path)
            if report:
                report["loudnorm_applied"] = normed_ok
                report["measured_at"] = (
                    datetime.datetime.now(datetime.timezone.utc)
                    .isoformat(timespec="seconds")
                )
                _report_snapshot = report  # capture for inner closure

                from domain.models import Project as _Project

                def _persist_media_report(latest_project: dict):
                    _Project.model_validate(latest_project)
                    latest_project["media_report"] = _report_snapshot

                mutate_project(
                    self.project["id"],
                    _persist_media_report,
                    timeout=10,
                    snapshot=self.project,
                )
        except Exception:
            logger.warning(
                "probe/persist media_report failed — assembly outcome unaffected",
                exc_info=True,
            )

    def _concat_foley_track(self, paths: list[str]) -> Optional[str]:
        """Pre-concatenate per-scene foley clips into a single foley_track.mp3.

        - Returns None if paths is empty.
        - Returns paths[0] directly if len(paths) == 1 (skip concat).
        - Writes concat_foley_list.txt to temp_dir, runs ffmpeg concat demuxer,
          returns temp_dir/foley_track.mp3 on success, None on failure.
        """
        if not paths:
            return None
        if len(paths) == 1:
            return paths[0]

        foley_list = os.path.join(self.temp_dir, "concat_foley_list.txt")
        foley_track = os.path.join(self.temp_dir, "foley_track.mp3")
        with open(foley_list, "w") as f:
            for p in paths:
                escaped = os.path.abspath(p).replace("'", r"'\''")
                f.write(f"file '{escaped}'\n")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", foley_list, "-c", "copy", foley_track],
                check=True, capture_output=True, timeout=60,
            )
            return foley_track
        except Exception:
            logger.exception("Foley concat failed; foley track will be omitted from mix")
            return None

    def _concat_dialogue_track(self, paths: list[str]) -> Optional[str]:
        """Pre-concatenate per-scene dialogue clips into a single dialogue_track.mp3.

        Parallel to _concat_foley_track. Required when motion engines that don't
        embed dialogue audio (Kling Native image2video, etc) are used — the
        dialogue mp3 must be muxed as a separate input at tri-mix time rather
        than read as `[0:a]` from the stitched video (which has no dialogue
        track in those paths).

        - Returns None if paths is empty.
        - Returns paths[0] directly if len(paths) == 1 (skip concat).
        - Writes concat_dialogue_list.txt to temp_dir, runs ffmpeg concat demuxer,
          returns temp_dir/dialogue_track.mp3 on success, None on failure.
        """
        if not paths:
            return None
        if len(paths) == 1:
            return paths[0]

        dialogue_list = os.path.join(self.temp_dir, "concat_dialogue_list.txt")
        dialogue_track = os.path.join(self.temp_dir, "dialogue_track.mp3")
        with open(dialogue_list, "w") as f:
            for p in paths:
                escaped = os.path.abspath(p).replace("'", r"'\''")
                f.write(f"file '{escaped}'\n")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", dialogue_list, "-c", "copy", dialogue_track],
                check=True, capture_output=True, timeout=60,
            )
            return dialogue_track
        except Exception:
            logger.exception("Dialogue concat failed; dialogue track will be omitted from mix")
            return None

    def _assemble_final(self, scene_data: list, bgm_path: str, settings: dict) -> Optional[str]:
        """
        Assembles all scene clips into the final video:
        - Hard cuts between all clips (no transitions)
        - Preserves embedded audio from dialogue clips (Omnihuman/Veo)
        - Normalizes to the project aspect_ratio's dims @30fps (16:9 → 1920x1080) WITHOUT forcing duration (preserves natural clip length)
        - Mixes: clip audio (dialogue) + BGM (0.12 vol) + foley (0.20 vol, when available)
        - Foley volume 0.20 > BGM 0.12: environmental beds carry diegetic info
        - Color grading applied globally
        """
        final_output = os.path.join(self.export_dir, "final_cinema.mp4")

        scene_transitions = settings.get("scene_transitions", False)
        transition_duration = float(settings.get("transition_duration", 0.5))

        # 1. Collect clips in scene order — deduplicate (use only final version per shot)
        all_clips = []
        scene_sizes = []  # number of valid clips per scene, in order
        for si, sd in enumerate(scene_data):
            scene_id = sd.get("scene_id", f"scene_{si}")
            clips = sd.get("clips", [])
            count = 0
            for clip_path in clips:
                if clip_path and os.path.exists(clip_path):
                    all_clips.append(clip_path)
                    count += 1
                    logger.debug(
                        "Assembly clip queued",
                        extra={
                            "scene_index": si,
                            "scene_id": scene_id,
                            "clip": os.path.basename(clip_path),
                        },
                    )
            if count:
                scene_sizes.append(count)

        if not all_clips:
            logger.warning("No clips to assemble")
            return None

        logger.info(
            "Assembling clips",
            extra={"clip_count": len(all_clips)},
        )

        # 2. Normalize clips: aspect-derived dims @30fps (16:9 → 1920x1080), PRESERVE audio, PRESERVE original duration
        all_normalized = []
        # Phase 1: container dims from the project aspect_ratio (default 16:9).
        # I1 guard: a persisted unsupported ratio (e.g. a stray 9:16 from the
        # pre-gate /api/config window) must NOT silently flip the container —
        # fall back to the default so assembly stays inside the gated set.
        _ar = settings.get("aspect_ratio", DEFAULT_ASPECT_RATIO)
        if not is_supported(_ar):
            _ar = DEFAULT_ASPECT_RATIO
        out_w, out_h = resolve_output_dimensions(_ar)
        norm_vf = _normalize_filter(out_w, out_h)
        for clip_path in all_clips:
            norm_path = os.path.join(self.temp_dir,
                os.path.basename(clip_path).replace(".mp4", "_norm.mp4"))
            try:
                # Normalize resolution + fps without forcing duration or stripping audio
                cmd = [
                    "ffmpeg", "-y", "-i", clip_path,
                    "-vf", norm_vf,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k",  # Preserve audio
                    "-shortest",
                    norm_path,
                ]
                subprocess.run(cmd, check=True, capture_output=True, timeout=60)
                all_normalized.append(norm_path)
            except Exception:
                logger.exception(
                    "Normalize failed; using original clip as fallback",
                    extra={"clip": os.path.basename(clip_path)},
                )
                all_normalized.append(clip_path)  # Use original as fallback

        # 3. Stitch: hard cuts (default) or scene-boundary cross-dissolve (opt-in)
        stitched = os.path.join(self.temp_dir, "stitched.mp4")

        def _concat_copy(clip_paths, dest, tag):
            list_path = os.path.join(self.temp_dir, f"concat_list_{tag}.txt")
            with open(list_path, "w") as f:
                for clip in clip_paths:
                    f.write(f"file '{os.path.abspath(clip)}'\n")
            # Use concat demuxer — requires same codec/resolution (normalized above)
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                 "-c", "copy", dest],
                check=True, capture_output=True, timeout=120,
            )
            return dest

        use_transitions = scene_transitions and len(scene_sizes) >= 2

        if use_transitions:
            try:
                from phase_c_ffmpeg import xfade_concat
                scene_videos = []
                idx = 0
                for si, size in enumerate(scene_sizes):
                    group = all_normalized[idx:idx + size]
                    idx += size
                    scene_mp4 = os.path.join(self.temp_dir, f"scene_{si}.mp4")
                    _concat_copy(group, scene_mp4, f"scene_{si}")
                    scene_videos.append(scene_mp4)
                xfade_concat(scene_videos, stitched, duration=transition_duration)
                logger.info(
                    "Stitched clips with scene transitions",
                    extra={"scene_count": len(scene_videos)},
                )
            except Exception:
                logger.exception("Scene-transition stitch failed; falling back to hard-cut concat")
                try:
                    _concat_copy(all_normalized, stitched, "all")
                    logger.info(
                        "Stitched clips (fallback hard-cut)",
                        extra={"clip_count": len(all_normalized), "stitched_path": stitched},
                    )
                except Exception:
                    logger.exception("Stitch failed")
                    return None
        else:
            try:
                _concat_copy(all_normalized, stitched, "all")
                logger.info(
                    "Stitched clips",
                    extra={
                        "clip_count": len(all_normalized),
                        "stitched_path": stitched,
                    },
                )
            except Exception:
                logger.exception("Stitch failed")
                return None

        # 4. Color grading
        try:
            from phase_c_ffmpeg import apply_color_grade
            mood = settings.get("mood", "cinematic")
            _mood_to_grade = {
                "suspense": "cool_noir", "thriller": "cool_noir", "horror": "moonlight",
                "noir": "cool_noir", "dystopian": "high_contrast",
                "melancholic": "desaturated", "romantic": "golden_hour",
                "bittersweet": "warm_cinema", "hopeful": "golden_hour",
                "epic": "high_contrast", "action": "high_contrast",
                "ethereal": "pastel", "dreamy": "pastel",
                "cyberpunk": "vibrant", "gritty": "high_contrast",
            }
            grade_preset = _mood_to_grade.get(mood, "warm_cinema")
            graded_path = os.path.join(self.temp_dir, "graded.mp4")
            graded = apply_color_grade(stitched, graded_path, preset=grade_preset)
            if graded:
                stitched = graded
                logger.info(
                    "Applied color grade",
                    extra={"grade_preset": grade_preset, "mood": mood},
                )
        except Exception:
            logger.exception("Color grading skipped")

        # 5. Mix audio: voice (1.0) + BGM (0.12) + foley (0.20, when available)
        #
        # Voice source resolution:
        #   - When motion engine embeds dialogue (Omnihuman, Veo audio-drive):
        #     stitched.mp4 already has dialogue baked in → use [0:a] from stitched.
        #   - When motion engine does NOT embed dialogue (Kling Native image2video,
        #     LTX, base Veo without audio-drive): stitched.mp4 has no audio →
        #     mux scene_audio dialogue mp3 as a separate input (input index N).
        #     C-B2 closure: previously the path assumed embedded audio always
        #     and the `[voice]` filtergraph label couldn't bind, dropping
        #     dialogue from the final mix silently.
        #
        # BGM is at 0.12 (ambient bed); foley at 0.20 (slightly louder — diegetic
        # environmental information like footsteps/weather carries meaning).
        # amix duration=first clamps foley/BGM to reel length automatically.
        #
        # Fallback cascade:
        #   Primary:    voice + bgm + foley  (3-input amix)
        #   Fallback 1: voice + bgm          (2-input amix, foley absent or concat failed)
        #   Fallback 2: BGM-only             (voice mix failed)
        #   Fallback 3: copy stitched as-is  (all audio mixing failed)

        # Pre-concat per-scene foley clips into a single track (None if no foley).
        foley_track_path = self._concat_foley_track(self.foley_audio_paths)

        # Pre-concat per-scene dialogue mp3s into a single track (None if no
        # standalone dialogue audio — i.e. engines that embed audio in clips).
        # `scene_data[i]["audio"]` is the path to the per-scene dialogue mp3
        # set by _ensure_scene_audio + threaded through _build_scene_packages.
        dialogue_paths = [
            sd.get("audio") for sd in scene_data
            if sd.get("audio") and os.path.exists(sd.get("audio", ""))
        ]
        dialogue_track_path = self._concat_dialogue_track(dialogue_paths)

        try:
            if os.path.exists(bgm_path):
                use_foley = foley_track_path and os.path.exists(foley_track_path)
                use_standalone_dialogue = (
                    dialogue_track_path and os.path.exists(dialogue_track_path)
                )
                # Voice source label: [N:a] for standalone dialogue input;
                # [0:a] for engine-embedded audio in stitched.
                # Inputs ordering: [0]=stitched [1]=bgm [2]=foley(opt) [3 or 2]=dialogue(opt)
                # Compute dialogue input index dynamically below.
                cmd_inputs = ["ffmpeg", "-y", "-i", stitched, "-i", bgm_path]
                next_idx = 2  # next available input index
                foley_idx = None
                dialogue_idx = None
                if use_foley:
                    cmd_inputs += ["-i", foley_track_path]
                    foley_idx = next_idx
                    next_idx += 1
                if use_standalone_dialogue:
                    cmd_inputs += ["-i", dialogue_track_path]
                    dialogue_idx = next_idx
                    next_idx += 1

                # Build filtergraph parts conditionally.
                voice_label_src = (
                    f"[{dialogue_idx}:a]"
                    if use_standalone_dialogue else "[0:a]"
                )
                filter_parts = [
                    f"{voice_label_src}volume=1.0[voice]",
                    "[1:a]volume=0.12[bgm]",
                ]
                amix_inputs = ["[voice]", "[bgm]"]
                if use_foley:
                    filter_parts.append(f"[{foley_idx}:a]volume=0.20[foley]")
                    amix_inputs.append("[foley]")
                n_inputs = len(amix_inputs)
                # M-B3 closure: when voice is a standalone dialogue track,
                # it may be shorter than the video (e.g. 3.9s dialogue vs 5.1s
                # Kling motion). amix duration=first would clamp audio to
                # dialogue length, leaving a silent tail. duration=longest
                # extends to the longest input (BGM tracks can be 30-60s,
                # foley typically video-length). Pair with -shortest on the
                # ffmpeg output so the container clamps to the shortest INPUT
                # (the video, 5.1s) — audio plays through video length with
                # BGM/foley filling any silent tail past dialogue end.
                # Embedded-voice legacy path (Omnihuman/Veo) preserves
                # duration=first WITHOUT -shortest since voice == video length
                # there.
                amix_duration_mode = "longest" if use_standalone_dialogue else "first"
                filter_parts.append(
                    "".join(amix_inputs)
                    + f"amix=inputs={n_inputs}:duration={amix_duration_mode}:dropout_transition=2[aout]"
                )
                filter_complex = ";".join(filter_parts)

                cmd = cmd_inputs + [
                    "-filter_complex", filter_complex,
                    "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                ]
                # -shortest clamps output to shortest INPUT (the video for
                # standalone-dialogue path); ensures audio doesn't overshoot
                # video length when BGM/foley are longer than video.
                if use_standalone_dialogue:
                    cmd += ["-shortest"]
                cmd += [final_output]
                mix_label = (
                    ("standalone-dialogue" if use_standalone_dialogue else "embedded-voice")
                    + "+BGM"
                    + ("+foley" if use_foley else "")
                )
                subprocess.run(cmd, check=True, capture_output=True, timeout=120)
                logger.info(
                    "Final cinema video assembled",
                    extra={"mix": mix_label, "final_path": final_output},
                )
            else:
                # No BGM — just copy stitched as final
                import shutil
                shutil.copy2(stitched, final_output)
                logger.info(
                    "Final cinema video assembled (no BGM)",
                    extra={"final_path": final_output},
                )

            self._apply_final_loudnorm(final_output)
            return final_output

        except subprocess.CalledProcessError as e:
            # Primary/2-input BGM mix failed (maybe stitched has no audio) — try BGM-only
            logger.warning(
                "BGM mix failed, trying BGM-only fallback",
                extra={
                    "stderr_tail": (
                        e.stderr.decode("utf-8", errors="replace")[-200:]
                        if e.stderr else ""
                    ),
                },
            )
            try:
                cmd_fallback = [
                    "ffmpeg", "-y",
                    "-i", stitched,
                    "-i", bgm_path,
                    "-filter_complex",
                    "[1:a]volume=0.15[aout]",
                    "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    final_output,
                ]
                subprocess.run(cmd_fallback, check=True, capture_output=True, timeout=120)
                logger.info(
                    "Final cinema video assembled (BGM only, no dialogue audio)",
                    extra={"final_path": final_output},
                )
                self._apply_final_loudnorm(final_output)
                return final_output
            except Exception:
                logger.exception("All audio mixing failed; using stitched video as-is")
                import shutil
                shutil.copy2(stitched, final_output)
                self._apply_final_loudnorm(final_output)
                return final_output

# ---------------------------------------------------------------------------
# CLI entry point for testing
# ---------------------------------------------------------------------------

def run_cinema_pipeline(project_id: str) -> Optional[str]:
    """Convenience function to run the full pipeline from CLI."""
    pipeline = CinemaPipeline(project_id)
    return pipeline.generate()


if __name__ == "__main__":
    import sys
    from cinema.logging_config import setup_logging

    setup_logging()

    if len(sys.argv) > 1:
        result = run_cinema_pipeline(sys.argv[1])
        if result:
            logger.info(
                "Cinema production complete",
                extra={"final_path": result},
            )
        else:
            logger.error("Cinema production failed")
            sys.exit(1)
    else:
        logger.error("Usage: python cinema_pipeline.py <project_id>")
        sys.exit(2)
