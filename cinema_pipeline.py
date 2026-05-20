"""
Cinema Production Tool — Interactive Pipeline Orchestrator
Replaces main.py's run_autonomous_pipeline() for interactive cinema production.
Orchestrates: scene decomposition → continuity enhancement → image gen → video gen
→ identity validation → FaceFusion face-swap → RIFE interpolation → Real-ESRGAN upscale
→ per-scene audio → per-scene assembly → global assembly → final export.
"""

import os
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import json
import time
import glob
import random
import subprocess
from project_manager import MutationResult, load_project, mutate_project, make_take
from character_manager import get_reference_image
from location_manager import get_location_prompt, get_location_seed
from scene_decomposer import decompose_scene, update_scene_shots
from dialogue_writer import generate_dialogue, format_dialogue_for_voiceover
from llm.style_director import generate_style_rules, style_rules_to_prompt_suffix
from phase_c_assembly import generate_ai_broll
from phase_c_ffmpeg import generate_ai_video, generate_kling_storyboard, normalize_clip, stitch_modules
from phase_c_vision import (
    validate_identity, validate_multi_identity, face_swap_video_frames
)
from audio.dialogue import generate_dialogue_voiceover
from audio.music import generate_fal_bgm
from audio.foley import generate_scene_foley, generate_layered_foley
from audio.srt import generate_srt
from lip_sync import (
    generate_lip_sync_video, generate_rife_interpolation,
    extract_last_frame, generate_transition_clip,
    upscale_video_seedvr2,
)
from cinema.context import PipelineContext
from cinema.core import PipelineCore, build_pipeline_core
from cinema.lifecycle import ThreadedLifecycle
from cinema.phases.keyframe_render import KeyframeRenderPhase
from cinema.phases.motion_render import MotionRenderPhase
from cinema.shots.controller import ShotController
from cinema.review.controller import ReviewControllerMixin
from cinema.checkpoint import CheckpointStoreMixin
from scene_decomposer import competitive_decompose_scene


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


class CinemaPipeline(ReviewControllerMixin, CheckpointStoreMixin):
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

        # Per-run runtime state — populated during generate(), reset
        # for each run. None of this belongs in PipelineCore.
        self.scene_clips = {}        # scene_id -> list of video clip paths
        self.scene_audio = {}        # scene_id -> audio path
        self.failed_shots = []       # shot_ids that failed and were skipped
        self.current_stage = ""
        self.current_scene_id = ""
        self.current_shot_id = ""
        self._completed_scene_indices = set()  # for checkpoint resume

        # ShotController -- standalone-controllers Slice 2. Owns
        # shot_results (the only runtime-state field where shot methods
        # are the primary writers). Cross-controller calls and the
        # progress-pointer triple still flow through self (the host),
        # via the ShotControllerHost protocol.
        self._shot_ctrl = ShotController(self._core, self.lifecycle, self)

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
    def vbench(self):
        return self._core.vbench

    @property
    def quality_tracker(self):
        return self._core.quality_tracker

    @property
    def cost_tracker(self):
        return self._core.cost_tracker

    @property
    def ensemble(self):
        return self._core.ensemble

    # ------------------------------------------------------------------
    # ShotController delegates + state proxy (Slice 2).
    # The six public shot methods now live on self._shot_ctrl; these
    # delegates preserve the CinemaPipeline call surface for web_server
    # endpoints, tests, and the inline self.generate_scene_preview()
    # call in assemble_approved_takes().
    # ------------------------------------------------------------------

    @property
    def shot_results(self) -> dict:
        """Proxy to ShotController's run-state dict.

        Returns the underlying object (not a copy) so in-place mutations
        like ``self.shot_results[shot_id] = {...}`` from generate() keep
        working through the property.
        """
        return self._shot_ctrl.shot_results

    @shot_results.setter
    def shot_results(self, value: dict) -> None:
        # Needed for full-assignment sites in CheckpointStoreMixin
        # (_restore_from_checkpoint reassigns the dict wholesale).
        self._shot_ctrl.shot_results = value

    def update_progress_pointer(self, stage: str, scene_id: str, shot_id: str) -> None:
        """Update the current_stage / current_scene_id / current_shot_id triple atomically.

        Called by ShotController via the ShotControllerHost protocol.
        The orchestrator's generate() loop still writes the fields
        directly; this method just keeps the controller's writes from
        scattering three attribute assignments at every step.
        """
        self.current_stage = stage
        self.current_scene_id = scene_id
        self.current_shot_id = shot_id

    def generate_keyframe_take(self, *args, **kwargs) -> dict:
        return self._shot_ctrl.generate_keyframe_take(*args, **kwargs)

    def generate_motion_take(self, *args, **kwargs) -> dict:
        return self._shot_ctrl.generate_motion_take(*args, **kwargs)

    def regenerate_shot(self, *args, **kwargs) -> dict:
        return self._shot_ctrl.regenerate_shot(*args, **kwargs)

    def diagnose_clip(self, *args, **kwargs) -> dict:
        return self._shot_ctrl.diagnose_clip(*args, **kwargs)

    def apply_correction(self, *args, **kwargs) -> dict:
        return self._shot_ctrl.apply_correction(*args, **kwargs)

    def generate_scene_preview(self, *args, **kwargs):
        return self._shot_ctrl.generate_scene_preview(*args, **kwargs)

    # Private-helper delegates -- needed because ReviewControllerMixin
    # calls self._find_take (6x) and self._mutate_shot (2x) which used
    # to resolve via MRO through ShotControllerMixin. After Slice 2
    # dropped that mixin, these calls would AttributeError. Restored
    # as delegates here so ReviewControllerMixin keeps working until
    # Slice 3b promotes ReviewController to standalone (at which point
    # these become cross-controller-via-host calls).

    def _find_take(self, *args, **kwargs):
        return self._shot_ctrl._find_take(*args, **kwargs)

    def _mutate_shot(self, *args, **kwargs):
        return self._shot_ctrl._mutate_shot(*args, **kwargs)

    # ------------------------------------------------------------------
    # Checkpoint / Resume
    # ------------------------------------------------------------------








    def _default_progress(self, stage: str, detail: str, percent: float = 0,
                          scene_id: str = "", shot_id: str = "",
                          image_url: str = "", identity_score: float = -1,
                          director_review: dict = None, **kwargs):
        print(f"[{percent:.0f}%] {stage}: {detail}")

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

        self.project.clear()
        self.project.update(latest)
        self.continuity.project = self.project
        self.continuity.character_tracker.project = self.project
        self.continuity.character_tracker.characters = {
            character["id"]: character for character in self.project["characters"]
        }
        self.continuity.location_persistence.project = self.project
        self.continuity.location_persistence.locations = {
            location["id"]: location for location in self.project["locations"]
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
        if characters and not dialogue and action:
            dialogue_lines = generate_dialogue(scene, characters, scene.get("mood", "neutral"))
        elif dialogue:
            if isinstance(dialogue, list):
                dialogue_lines = dialogue
            else:
                dialogue_lines = generate_dialogue(scene, characters, scene.get("mood", "neutral"))
        else:
            return None

        if not dialogue_lines:
            return None

        output_path = os.path.join(self.temp_dir, f"audio_{scene_id}.mp3")
        result = generate_dialogue_voiceover(dialogue_lines, characters, output_path)
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
                mastered = master_music(bgm_path, mastered_path, preset="cinema_master")
                if mastered and os.path.exists(mastered):
                    bgm_path = mastered
                    self.progress("AUDIO", "BGM mastered (cinema_master preset)", 6)
            except Exception as e_master:
                print(f"   [AUDIO] BGM mastering skipped (non-critical): {e_master}")
        return bgm_path

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
            scene_packages.append({
                "scene_id": scene_id,
                "clips": clips,
                "audio": scene_audio,
                "foley": [],
            })

        return scene_packages, missing_shots




    # ------------------------------------------------------------------
    # DIRECTOR'S CUT — Correction & Diagnosis
    # ------------------------------------------------------------------




    def assemble_approved_takes(self) -> dict:
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

        try:
            from cleanup import cleanup_project
            cleanup_result = cleanup_project(self.project["id"], aggressive=False)
            if cleanup_result["files_deleted"] > 0:
                self.progress("CLEANUP", f"Cleaned {cleanup_result['files_deleted']} temp files ({cleanup_result['mb_freed']} MB)", 98)
        except Exception as e:
            print(f"   [CLEANUP] Auto-cleanup failed (non-fatal): {e}")

        try:
            video_id = self.project.get("id", "unknown")
            cost_summary = self.cost_tracker.get_video_cost(video_id)
            if cost_summary.get("total_usd", 0) > 0:
                print(f"\n   💰 [COST] Total: ${cost_summary['total_usd']:.2f} | LLM: ${cost_summary.get('llm_usd', 0):.2f} | API: ${cost_summary.get('api_usd', 0):.2f}")
        except Exception as e_cost:
            print(f"   [COST] Could not retrieve cost summary: {e_cost}")

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
            def _persist_style_rules(latest_project: dict):
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
                    except Exception as e_cd:
                        print(f"   [DECOMPOSE] Competitive decomposition failed ({e_cd}), falling back to standard")
                        shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules)
                else:
                    shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules)

                # CHIEF DIRECTOR VALIDATION — review shots before generation
                self.progress("DIRECTOR", "Chief Director reviewing shots...", 13 + scene_idx)
                review = self.director.validate_shot_prompts(shots, scene)
                if review.get("decision") == "MODIFIED":
                    shots = review.get("shots", shots)
                    print(f"   [DIRECTOR] Shots modified — {len(review.get('violations', []))} violations corrected")
                elif review.get("decision") == "REJECTED":
                    print(f"   [DIRECTOR] Shots REJECTED — regenerating with corrections")
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
        ctx = PipelineContext(lifecycle=self.lifecycle)

        project = self._refresh_project_snapshot() or self.project

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

        def _on_motion_fail(scene_id: str, shot_id: str, error: str):
            self.failed_shots.append(shot_id)
            self.progress(
                "SHOT_FAILED",
                error or "Motion generation failed",
                70,
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
    # POST-PROCESSING HELPERS
    # ------------------------------------------------------------------

    def _frame_interpolate(self, video_path: str, scene_id: str, shot_idx: int) -> Optional[str]:
        """Frame interpolation using ffmpeg minterpolate filter (no external tools needed)."""
        output = os.path.join(self.temp_dir, f"interp_{scene_id}_{shot_idx}.mp4")
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", video_path,
                 "-vf", "minterpolate=fps=24:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
                 "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                 "-c:a", "copy",
                 output],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and os.path.exists(output):
                print(f"      ✅ Frame interpolation (24fps): {output}")
                return output
        except Exception as e:
            print(f"      ⚠️ Frame interpolation skipped: {e}")
        return None

    def _upscale_video(self, video_path: str, scene_id: str, shot_idx: int) -> Optional[str]:
        """Real-ESRGAN upscale on extracted frames for maximum photorealism."""
        try:
            from realesrgan import RealESRGANer
            from basicsr.archs.rrdbnet_arch import RRDBNet
            import cv2
            import numpy as np

            # Initialize upscaler (2x scale for speed, 4x available)
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)
            upscaler = RealESRGANer(
                scale=2, model_path=None, model=model, tile=400, tile_pad=10, pre_pad=0,
                half=False,  # CPU mode on macOS
            )

            # Extract frames, upscale each, reassemble
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 24
            frames_dir = os.path.join(self.temp_dir, f"upscale_frames_{scene_id}_{shot_idx}")
            os.makedirs(frames_dir, exist_ok=True)

            frame_count = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                output_frame, _ = upscaler.enhance(frame, outscale=2)
                cv2.imwrite(os.path.join(frames_dir, f"frame_{frame_count:05d}.png"), output_frame)
                frame_count += 1
            cap.release()

            if frame_count == 0:
                return None

            # Reassemble with ffmpeg
            output = os.path.join(self.temp_dir, f"upscaled_{scene_id}_{shot_idx}.mp4")
            subprocess.run(
                ["ffmpeg", "-y", "-framerate", str(fps),
                 "-i", os.path.join(frames_dir, "frame_%05d.png"),
                 "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                 "-pix_fmt", "yuv420p", output],
                check=True, capture_output=True,
            )

            # Cleanup frames
            import shutil
            shutil.rmtree(frames_dir, ignore_errors=True)

            if os.path.exists(output):
                print(f"      ✅ Real-ESRGAN 2x upscale: {output}")
                return output

        except ImportError:
            pass  # Real-ESRGAN not installed
        except Exception as e:
            print(f"      ⚠️ Upscale skipped: {e}")
        return None

    # ------------------------------------------------------------------
    # FINAL ASSEMBLY
    # ------------------------------------------------------------------

    def _assemble_final(self, scene_data: list, bgm_path: str, settings: dict) -> Optional[str]:
        """
        Assembles all scene clips into the final video:
        - Hard cuts between all clips (no transitions)
        - Preserves embedded audio from dialogue clips (Omnihuman/Veo)
        - Normalizes to 1920x1080@30fps WITHOUT forcing duration (preserves natural clip length)
        - Mixes: clip audio (dialogue) + BGM (plays once, low volume)
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
                    print(f"   [ASSEMBLY] S{si} clip: {os.path.basename(clip_path)}")

        if not all_clips:
            print("   ⚠️ No clips to assemble")
            return None

        print(f"   [ASSEMBLY] {len(all_clips)} clips total")

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
            except Exception as e:
                print(f"   [WARN] Normalize failed for {os.path.basename(clip_path)}: {e}")
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
            print(f"   [ASSEMBLY] Stitched {len(all_normalized)} clips → {stitched}")
        except Exception as e:
            print(f"   ⚠️ Stitch failed: {e}")
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
                print(f"   [COLOR] Applied '{grade_preset}' color grade (mood: {mood})")
        except Exception as e_cg:
            print(f"   [COLOR] Color grading skipped: {e_cg}")

        # 5. Mix BGM under existing audio (dialogue clips already have voice baked in)
        # The stitched video already has audio from dialogue clips (Omnihuman/Veo).
        # We just add BGM at low volume underneath.
        try:
            if os.path.exists(bgm_path):
                cmd = [
                    "ffmpeg", "-y",
                    "-i", stitched,
                    "-i", bgm_path,
                    "-filter_complex",
                    # If stitched has audio, mix it with BGM. If not, use BGM only.
                    "[0:a]volume=1.0[voice];"
                    "[1:a]volume=0.12[bgm];"
                    "[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                    "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy",  # No re-encode — just audio mix
                    "-c:a", "aac", "-b:a", "192k",
                    final_output,
                ]
                subprocess.run(cmd, check=True, capture_output=True, timeout=120)
                print(f"   ✅ Final cinema video with BGM: {final_output}")
            else:
                # No BGM — just copy stitched as final
                import shutil
                shutil.copy2(stitched, final_output)
                print(f"   ✅ Final cinema video (no BGM): {final_output}")

            return final_output

        except subprocess.CalledProcessError as e:
            # BGM mix failed (maybe stitched has no audio) — try without voice mix
            print(f"   [WARN] BGM mix failed ({e.stderr[-200:] if e.stderr else ''}), trying BGM-only...")
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
                print(f"   ✅ Final cinema video (BGM only, no dialogue audio): {final_output}")
                return final_output
            except Exception as e2:
                print(f"   ⚠️ All audio mixing failed: {e2}")
                import shutil
                shutil.copy2(stitched, final_output)
                return final_output

    # ------------------------------------------------------------------
    # SCENE-LEVEL PREVIEW
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------------

    def cleanup_temp(self):
        """Remove all temporary files."""
        for f in glob.glob(os.path.join(self.temp_dir, "*")):
            try:
                os.remove(f)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# CLI entry point for testing
# ---------------------------------------------------------------------------

def run_cinema_pipeline(project_id: str) -> Optional[str]:
    """Convenience function to run the full pipeline from CLI."""
    pipeline = CinemaPipeline(project_id)
    return pipeline.generate()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = run_cinema_pipeline(sys.argv[1])
        if result:
            print(f"\n✅ Cinema production complete: {result}")
        else:
            print("\n❌ Cinema production failed.")
    else:
        print("Usage: python cinema_pipeline.py <project_id>")
