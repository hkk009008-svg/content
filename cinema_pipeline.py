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
from scene_decomposer import decompose_scene, update_scene_shots, competitive_decompose_scene
from dialogue_writer import generate_dialogue
from llm.style_director import generate_style_rules
from audio.dialogue import generate_dialogue_voiceover
from audio.music import generate_fal_bgm
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

logger = logging.getLogger(__name__)


def _build_transition_prompt(from_mood: str, to_mood: str) -> str:
    """
    Build a cinematic transition prompt based on the emotional arc between two scenes.
    The transition should feel motivated — not just a random morph but a purposeful shift.
    """
    from_mood = from_mood.lower()
    to_mood = to_mood.lower()

    # Mood-aware transition descriptions
    if from_mood == to_mood:
        return f"Smooth continuous camera movement, same {from_mood} atmosphere, natural flow between moments"

    # Emotional contrasts
    dark_moods = {"suspense", "thriller", "horror", "noir", "dystopian", "grief", "dark", "tense"}
    light_moods = {"hopeful", "uplifting", "romantic", "dreamy", "peaceful", "ethereal", "triumphant"}

    if from_mood in dark_moods and to_mood in light_moods:
        return "Slow dissolve from darkness to light, gradual warmth entering the frame, sunrise-like transition, hopeful opening"
    elif from_mood in light_moods and to_mood in dark_moods:
        return "Light fading to shadow, colors desaturating, warmth draining from the frame, ominous shift"
    elif from_mood in dark_moods and to_mood in dark_moods:
        return "Slow atmospheric dissolve, maintaining tension, dark environment shifting, continuous unease"
    elif from_mood in light_moods and to_mood in light_moods:
        return "Warm cross-dissolve, maintaining positive energy, gentle movement, flowing continuity"

    # Default: cinematic match cut
    return f"Cinematic transition from {from_mood} to {to_mood} mood, smooth camera movement, natural temporal flow, professional film edit"


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
        self._runstate = RunState()

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
            dialogue_lines = generate_dialogue(scene, characters, scene.get("mood", "neutral"), language=lang)
        elif dialogue:
            if isinstance(dialogue, list):
                dialogue_lines = dialogue
            else:
                dialogue_lines = generate_dialogue(scene, characters, scene.get("mood", "neutral"), language=lang)
        else:
            return None

        if not dialogue_lines:
            return None

        output_path = os.path.join(self.temp_dir, f"audio_{scene_id}.mp3")
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
        )
        if result and os.path.exists(output_path):
            self.scene_audio[scene_id] = output_path
            self._save_checkpoint()
            return output_path
        return None

    def _ensure_bgm(self, settings: dict) -> str:
        self.progress("AUDIO", "Generating background music...", 5)
        music_mood = settings.get("music_mood", "suspense")
        bgm_path = os.path.join(self.temp_dir, f"bgm_{music_mood}.mp3")
        if not os.path.exists(bgm_path):
            generate_fal_bgm(music_mood, bgm_path, duration=47)

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
            result = generate_stability_foley(prompt, foley_path, duration=scene_duration)
            if result and os.path.exists(result):
                self.scene_foley[scene_id] = result
                self._runstate.foley_audio_paths.append(result)
                self._save_checkpoint()
                return result
        except Exception:
            logger.warning("Foley generation skipped for scene %s (non-critical)", scene_id, exc_info=True)
        return ""

    def _build_scene_packages(self, project: Optional[dict] = None) -> tuple[list[dict], list[str]]:
        active_project = project or self.project
        scene_packages = []
        missing_shots: list[str] = []
        self.scene_clips = {}

        for scene in active_project.get("scenes", []):
            scene_id = scene.get("id", "")
            clips = []
            for shot in scene.get("shots", []):
                final_take_id = shot.get("approved_final_take_id", "")
                final_path = self._resolve_take_path(shot, final_take_id)
                if not final_path or not os.path.exists(final_path):
                    missing_shots.append(shot.get("id", ""))
                    continue
                clips.append(final_path)

            self.scene_clips[scene_id] = clips
            characters = [
                character for character in active_project.get("characters", [])
                if character.get("id") in scene.get("characters_present", [])
            ]
            scene_audio = self._ensure_scene_audio(scene, characters)
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
        if _screening_stage_enabled():
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
                aspect_ratio=settings.get("aspect_ratio", "16:9"),
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
            chars_in_scene = [
                c for c in project["characters"]
                if c["id"] in scene.get("characters_present", [])
            ]
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
                        shots = competitive_decompose_scene(scene, chars_in_scene, location, settings, style_rules)
                    except Exception:
                        logger.exception(
                            "Competitive decomposition failed, falling back to standard",
                            extra={"scene_id": scene_id},
                        )
                        shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules)
                else:
                    shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules)

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
                    shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules)

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
        self.progress("MOTION_DONE", motion_result.message, 80)
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
        file is left untouched (two_pass_loudnorm returns False)."""
        from phase_c_ffmpeg import two_pass_loudnorm
        normed = final_path.replace(".mp4", "_loud.mp4")
        if two_pass_loudnorm(final_path, normed):
            os.replace(normed, final_path)
            logger.info(
                "Two-pass EBU R128 loudnorm applied",
                extra={"final_path": os.path.basename(final_path)},
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
                f.write(f"file '{os.path.abspath(p)}'\n")
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

    def _assemble_final(self, scene_data: list, bgm_path: str, settings: dict) -> Optional[str]:
        """
        Assembles all scene clips into the final video:
        - Hard cuts between all clips (no transitions)
        - Preserves embedded audio from dialogue clips (Omnihuman/Veo)
        - Normalizes to 1920x1080@30fps WITHOUT forcing duration (preserves natural clip length)
        - Mixes: clip audio (dialogue) + BGM (0.12 vol) + foley (0.20 vol, when available)
        - Foley volume 0.20 > BGM 0.12: environmental beds carry diegetic info
        - Color grading applied globally
        """
        final_output = os.path.join(self.export_dir, "final_cinema.mp4")

        # 1. Collect clips in scene order — deduplicate (use only final version per shot)
        all_clips = []
        for si, sd in enumerate(scene_data):
            scene_id = sd.get("scene_id", f"scene_{si}")
            clips = sd.get("clips", [])
            for clip_path in clips:
                if clip_path and os.path.exists(clip_path):
                    all_clips.append(clip_path)
                    logger.debug(
                        "Assembly clip queued",
                        extra={
                            "scene_index": si,
                            "scene_id": scene_id,
                            "clip": os.path.basename(clip_path),
                        },
                    )

        if not all_clips:
            logger.warning("No clips to assemble")
            return None

        logger.info(
            "Assembling clips",
            extra={"clip_count": len(all_clips)},
        )

        # 2. Normalize clips: 1920x1080@30fps, PRESERVE audio, PRESERVE original duration
        all_normalized = []
        for clip_path in all_clips:
            norm_path = os.path.join(self.temp_dir,
                os.path.basename(clip_path).replace(".mp4", "_norm.mp4"))
            try:
                # Normalize resolution + fps without forcing duration or stripping audio
                cmd = [
                    "ffmpeg", "-y", "-i", clip_path,
                    "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
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

        # 3. Stitch with hard cuts using concat demuxer
        stitched = os.path.join(self.temp_dir, "stitched.mp4")
        concat_list = os.path.join(self.temp_dir, "concat_list.txt")
        with open(concat_list, "w") as f:
            for clip in all_normalized:
                f.write(f"file '{os.path.abspath(clip)}'\n")

        try:
            # Use concat demuxer — requires same codec/resolution (normalized above)
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                stitched,
            ], check=True, capture_output=True, timeout=120)
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
        # The stitched video already has audio from dialogue clips (Omnihuman/Veo).
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

        try:
            if os.path.exists(bgm_path):
                use_foley = foley_track_path and os.path.exists(foley_track_path)
                if use_foley:
                    # Primary: 3-input tri-mix (voice + BGM + foley)
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", stitched,
                        "-i", bgm_path,
                        "-i", foley_track_path,
                        "-filter_complex",
                        "[0:a]volume=1.0[voice];"
                        "[1:a]volume=0.12[bgm];"
                        "[2:a]volume=0.20[foley];"
                        "[voice][bgm][foley]amix=inputs=3:duration=first:dropout_transition=2[aout]",
                        "-map", "0:v", "-map", "[aout]",
                        "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k",
                        final_output,
                    ]
                    mix_label = "voice+BGM+foley"
                else:
                    # Fallback 1: 2-input mix (no foley)
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", stitched,
                        "-i", bgm_path,
                        "-filter_complex",
                        "[0:a]volume=1.0[voice];"
                        "[1:a]volume=0.12[bgm];"
                        "[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                        "-map", "0:v", "-map", "[aout]",
                        "-c:v", "copy",  # No re-encode — just audio mix
                        "-c:a", "aac", "-b:a", "192k",
                        final_output,
                    ]
                    mix_label = "voice+BGM"
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
