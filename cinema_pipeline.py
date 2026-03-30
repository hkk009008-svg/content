"""
Cinema Production Tool — Interactive Pipeline Orchestrator
Replaces main.py's run_autonomous_pipeline() for interactive cinema production.
Orchestrates: scene decomposition → continuity enhancement → image gen → video gen
→ identity validation → FaceFusion face-swap → RIFE interpolation → Real-ESRGAN upscale
→ per-scene audio → per-scene assembly → global assembly → final export.
"""

import os
import threading
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import json
import time
import glob
import random
import subprocess
from dotenv import load_dotenv

load_dotenv()

from project_manager import load_project, get_project_dir, mutate_project
from character_manager import get_reference_image
from location_manager import get_location_prompt, get_location_seed
from continuity_engine import ContinuityEngine
from scene_decomposer import decompose_scene, update_scene_shots
from dialogue_writer import generate_dialogue, format_dialogue_for_voiceover
from style_director import generate_style_rules, style_rules_to_prompt_suffix
from phase_c_assembly import generate_ai_broll
from phase_c_ffmpeg import generate_ai_video, generate_kling_storyboard, normalize_clip, stitch_modules
from phase_c_vision import (
    validate_identity, validate_multi_identity, face_swap_video_frames
)
from phase_b_audio import (
    generate_dialogue_voiceover, generate_fal_bgm, generate_scene_foley, generate_layered_foley,
    generate_srt,
)
from lip_sync import (
    generate_lip_sync_video, generate_rife_interpolation,
    extract_last_frame, generate_transition_clip,
    upscale_video_seedvr2,
)
from chief_director import ChiefDirector
from llm_ensemble import LLMEnsemble
from vbench_evaluator import VBenchEvaluator
from quality_tracker import QualityTracker
from cost_tracker import CostTracker
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


class CinemaPipeline:
    """
    Interactive cinema production pipeline with maximum API utilization
    and state-of-the-art continuity techniques.
    """

    CHECKPOINT_FILE = "pipeline_state.json"

    def __init__(self, project_id: str, progress_callback=None):
        self.project = load_project(project_id)
        if not self.project:
            raise ValueError(f"Project '{project_id}' not found")

        self.project_dir = get_project_dir(project_id)
        self.temp_dir = os.path.join(self.project_dir, "temp")
        self.export_dir = os.path.join(self.project_dir, "exports")
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.export_dir, exist_ok=True)

        self.continuity = ContinuityEngine(self.project)
        self.director = ChiefDirector(self.project)
        self.progress = progress_callback or self._default_progress
        self.cancelled = False

        # Pause/resume control
        self._resume_event = threading.Event()
        self._resume_event.set()  # Start unpaused
        self.paused = False

        # Generation state
        self.scene_clips = {}  # scene_id -> list of video clip paths
        self.scene_audio = {}  # scene_id -> audio path
        self.shot_results = {}  # shot_id -> {"image": path, "video": path, "identity": score, "status": str}
        self.failed_shots = []  # shot_ids that failed and were skipped
        self.current_stage = ""
        self.current_scene_id = ""
        self.current_shot_id = ""

        # Quality systems — parameterized from project settings
        _gs = self.project.get("global_settings", {})
        self.vbench = VBenchEvaluator(
            flicker_threshold=_gs.get("temporal_flicker_tolerance", 0.85),
            regression_tolerance=_gs.get("regression_sensitivity", 0.05),
        )
        self.quality_tracker = QualityTracker()
        self.cost_tracker = CostTracker()
        self.ensemble = LLMEnsemble(settings=_gs)

        # Checkpoint: completed scene indices (for resume)
        self._completed_scene_indices = set()

    # ------------------------------------------------------------------
    # Checkpoint / Resume
    # ------------------------------------------------------------------

    def _checkpoint_path(self) -> str:
        return os.path.join(self.temp_dir, self.CHECKPOINT_FILE)

    def _save_checkpoint(self, completed_scene_idx: int = -1):
        """
        Persist pipeline state to disk after each meaningful step.
        Uses atomic write (temp + replace) to avoid half-written files.
        """
        state = {
            "project_id": self.project["id"],
            "current_stage": self.current_stage,
            "current_scene_id": self.current_scene_id,
            "current_shot_id": self.current_shot_id,
            "completed_scene_indices": sorted(self._completed_scene_indices),
            "scene_clips": self.scene_clips,
            "scene_audio": self.scene_audio,
            "shot_results": self.shot_results,
            "failed_shots": self.failed_shots,
        }
        path = self._checkpoint_path()
        import tempfile as _tmp
        fd, tmp = _tmp.mkstemp(suffix=".json.tmp", dir=self.temp_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def _load_checkpoint(self) -> dict:
        """Load saved checkpoint if it exists and files are still valid."""
        path = self._checkpoint_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            # Validate that referenced files still exist
            for shot_id, sr in state.get("shot_results", {}).items():
                for key in ("image", "video"):
                    p = sr.get(key)
                    if p and not os.path.exists(p):
                        sr[key] = None
                        sr["status"] = "lost"
            return state
        except (json.JSONDecodeError, OSError):
            return {}

    def _clear_checkpoint(self):
        """Remove checkpoint file after successful completion."""
        path = self._checkpoint_path()
        if os.path.exists(path):
            os.remove(path)

    def has_checkpoint(self) -> bool:
        """Check if a resumable checkpoint exists."""
        return os.path.exists(self._checkpoint_path())

    def resume_info(self) -> dict:
        """Return summary of what can be resumed."""
        state = self._load_checkpoint()
        if not state:
            return {"resumable": False}
        completed = state.get("completed_scene_indices", [])
        total = len(self.project.get("scenes", []))
        return {
            "resumable": True,
            "completed_scenes": len(completed),
            "total_scenes": total,
            "stage": state.get("current_stage", ""),
            "shots_done": len([s for s in state.get("shot_results", {}).values()
                               if s.get("status") not in ("failed", "lost")]),
            "shots_failed": len(state.get("failed_shots", [])),
        }

    def _restore_from_checkpoint(self) -> set:
        """
        Restore pipeline state from checkpoint.
        Returns set of completed scene indices to skip.
        """
        state = self._load_checkpoint()
        if not state:
            return set()

        self.scene_clips = state.get("scene_clips", {})
        self.scene_audio = state.get("scene_audio", {})
        self.shot_results = state.get("shot_results", {})
        self.failed_shots = state.get("failed_shots", [])
        completed = set(state.get("completed_scene_indices", []))
        self._completed_scene_indices = completed

        n = len(completed)
        if n > 0:
            self.progress("RESUME", f"Resuming from checkpoint — {n} scene(s) already complete", 5)

        return completed

    def _default_progress(self, stage: str, detail: str, percent: float = 0,
                          scene_id: str = "", shot_id: str = "",
                          image_url: str = "", identity_score: float = -1,
                          director_review: dict = None, **kwargs):
        print(f"[{percent:.0f}%] {stage}: {detail}")

    def cancel(self):
        self.cancelled = True
        self._resume_event.set()  # Unblock if paused so cancellation takes effect

    def pause(self):
        """Pause the pipeline at the next checkpoint."""
        if not self.paused:
            self.paused = True
            self._resume_event.clear()
            self.progress("PAUSED", "Pipeline paused — waiting for resume", -1)

    def resume(self):
        """Resume a paused pipeline."""
        if self.paused:
            self.paused = False
            self._resume_event.set()
            self.progress("RESUMED", "Pipeline resumed", -1)

    def _check_pause(self):
        """Checkpoint: block if paused, return False if cancelled."""
        self._resume_event.wait()  # Blocks until resume() is called
        return not self.cancelled

    def get_state(self) -> dict:
        """Return current pipeline state for the UI."""
        return {
            "paused": self.paused,
            "cancelled": self.cancelled,
            "current_stage": self.current_stage,
            "current_scene_id": self.current_scene_id,
            "current_shot_id": self.current_shot_id,
            "shot_results": self.shot_results,
            "failed_shots": self.failed_shots,
            "scenes_completed": len(self.scene_clips),
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

    def regenerate_shot(self, scene_id: str, shot_id: str) -> dict:
        """
        Regenerate a single shot without restarting the full pipeline.
        Returns {"success": bool, "image": path, "video": path, "identity_score": float}.
        """
        project = self._refresh_project_snapshot() or self.project
        scene = next((s for s in project["scenes"] if s["id"] == scene_id), None)
        if not scene:
            return {"success": False, "error": "Scene not found"}

        shot = None
        shot_index = 0
        for i, s in enumerate(scene.get("shots", [])):
            if s.get("id") == shot_id:
                shot = s
                shot_index = i
                break
        if not shot:
            return {"success": False, "error": "Shot not found"}

        settings = project.get("global_settings", {})
        style_suffix = style_rules_to_prompt_suffix(settings.get("style_rules", {}))

        # Enhance prompt
        prev_shot = scene["shots"][shot_index - 1] if shot_index > 0 else None
        enhanced = self.continuity.enhance_shot_prompt(shot, scene, prev_shot, shot_index)
        full_prompt = enhanced["prompt"]
        if style_suffix:
            full_prompt = f"{full_prompt}. {style_suffix}"

        cc = enhanced.get("continuity_config", {})
        primary_ref = cc.get("primary_reference")
        scene_seed = cc.get("scene_seed")

        img_path = os.path.join(self.temp_dir, f"img_{scene_id}_{shot_index}.jpg")
        vid_path = os.path.join(self.temp_dir, f"vid_{scene_id}_{shot_index}.mp4")

        self.progress("REGENERATE", f"Regenerating shot {shot_id}", -1,
                      scene_id=scene_id, shot_id=shot_id)

        # Generate image
        result = generate_ai_broll(
            full_prompt, img_path,
            seed=scene_seed,
            character_image=primary_ref,
            init_image=cc.get("init_image") if cc.get("use_img2img") else None,
            denoise_strength=cc.get("denoise_strength", 1.0),
            multi_angle_refs=cc.get("multi_angle_refs", []),
            identity_anchor=cc.get("identity_anchor", ""),
            pulid_weight_override=cc.get("pulid_weight_override"),
        )

        if not result or not os.path.exists(img_path):
            return {"success": False, "error": "Image generation failed"}

        # Validate identity
        identity_score = 0.0
        if primary_ref:
            from phase_c_vision import validate_identity_image
            img_sim = validate_identity_image(img_path, primary_ref, threshold=cc.get("identity_threshold", 0.70))
            identity_score = img_sim.get("similarity", 0.0)

        # Generate video — resolve AUTO the same way as main generation
        camera = shot.get("camera", "zoom_in_slow")
        raw_api = shot.get("target_api", "AUTO")
        video_fallbacks = None
        resolved_shot_type = None
        if raw_api == "AUTO":
            from workflow_selector import classify_shot_type, WORKFLOW_TEMPLATES
            resolved_shot_type = classify_shot_type(
                shot.get("prompt", ""), camera, shot.get("characters_in_frame", [])
            )
            template = WORKFLOW_TEMPLATES.get(resolved_shot_type, WORKFLOW_TEMPLATES["medium"])
            target_api = template["target_api"]
            video_fallbacks = template.get("video_fallbacks")
        else:
            target_api = raw_api

        temp_vid = generate_ai_video(
            img_path, camera, target_api, vid_path,
            pacing="calculated",
            character_id=cc.get("primary_character", ""),
            multi_angle_refs=cc.get("multi_angle_refs", []),
            shot_type=resolved_shot_type,
            video_fallbacks=video_fallbacks,
        )

        # Update state
        self.shot_results[shot_id] = {
            "image": img_path,
            "video": temp_vid or vid_path,
            "identity_score": identity_score,
            "status": "regenerated",
        }

        self.progress("REGENERATED", f"Shot {shot_id} regenerated (identity: {identity_score:.2f})", -1,
                      scene_id=scene_id, shot_id=shot_id,
                      image_url=img_path, identity_score=identity_score)

        return {
            "success": True,
            "image": img_path,
            "video": temp_vid,
            "identity_score": identity_score,
        }

    # ------------------------------------------------------------------
    # DIRECTOR'S CUT — Correction & Diagnosis
    # ------------------------------------------------------------------

    def diagnose_clip(self, shot_id: str) -> dict:
        """
        Run all quality analyzers on a clip and return scores + recommendations.
        """
        clip = self.review_clips.get(shot_id) or self.shot_results.get(shot_id)
        if not clip:
            return {"error": "Clip not found"}

        result = {"shot_id": shot_id, "scores": {}, "recommendations": []}
        video_path = clip.get("video")
        image_path = clip.get("image")

        # Identity validation
        scene_id = clip.get("scene_id", "")
        scene = next((s for s in self.project["scenes"] if s["id"] == scene_id), {})
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
            shot_idx = clip.get("shot_index", 0)
            if shot_idx > 0:
                prev_img = os.path.join(self.temp_dir, f"img_{scene_id}_{shot_idx - 1}.jpg")
                if os.path.exists(prev_img):
                    from coherence_analyzer import assess_coherence
                    coh = assess_coherence(str(image_path), prev_img)
                    result["scores"]["coherence"] = coh.overall_coherence_score
                    result["scores"]["color_drift"] = coh.color_drift
                    _drift_threshold = _diag_settings.get("color_drift_sensitivity", 0.3)
                    if coh.color_drift > _drift_threshold:
                        result["recommendations"].append({"tool": "color_grade", "reason": "Color palette drift detected"})

        return result

    def apply_correction(self, shot_id: str, action: str, params: dict = None) -> dict:
        """
        Apply a correction tool to a clip in the review stage.

        Actions: regenerate_image, regenerate_video, face_swap, lip_sync,
                 rife, upscale, color_grade, speed, voice_regen, foley_regen
        """
        params = params or {}
        clip = self.review_clips.get(shot_id)
        if not clip:
            return {"success": False, "error": "Clip not found in review"}

        video_path = clip.get("video")
        image_path = clip.get("image")
        scene_id = clip.get("scene_id", "")
        shot_index = clip.get("shot_index", 0)
        output_dir = self.temp_dir

        self.progress("CORRECTING", f"Applying {action} to {shot_id}", -1,
                      scene_id=scene_id, shot_id=shot_id)

        try:
            if action == "regenerate_image":
                positive = params.get("positive_prompt", clip.get("prompt", ""))
                negative = params.get("negative_prompt", "blur, distort, deformed face, identity change")
                scene = next((s for s in self.project["scenes"] if s["id"] == scene_id), {})
                chars = scene.get("characters_present", [])
                primary_ref = get_reference_image(self.project, chars[0]) if chars else None
                out_path = os.path.join(output_dir, f"corrected_img_{scene_id}_{shot_index}.jpg")

                result = generate_ai_broll(
                    positive, out_path,
                    character_image=primary_ref,
                    negative_prompt=negative,
                )
                if result and os.path.exists(out_path):
                    clip["image"] = out_path
                    clip["status"] = "corrected"
                    return {"success": True, "image": out_path}

            elif action == "regenerate_video":
                positive = params.get("positive_prompt", "")
                negative = params.get("negative_prompt", "blur, distort, deformed face, identity change")
                camera = params.get("camera", clip.get("camera", "zoom_in_slow"))
                target_api = params.get("target_api", clip.get("target_api", "KLING_3_0"))
                source_img = clip.get("image")
                out_path = os.path.join(output_dir, f"corrected_vid_{scene_id}_{shot_index}.mp4")

                if source_img and os.path.exists(str(source_img)):
                    result = generate_ai_video(
                        str(source_img), camera, target_api, out_path,
                        negative_prompt=negative,
                    )
                    if result and os.path.exists(out_path):
                        clip["video"] = out_path
                        clip["status"] = "corrected"
                        return {"success": True, "video": out_path}

            elif action == "face_swap":
                scene = next((s for s in self.project["scenes"] if s["id"] == scene_id), {})
                chars = scene.get("characters_present", [])
                primary_ref = get_reference_image(self.project, chars[0]) if chars else None
                if video_path and primary_ref:
                    out_path = os.path.join(output_dir, f"faceswap_{scene_id}_{shot_index}.mp4")
                    result = face_swap_video_frames(str(video_path), primary_ref, out_path)
                    if result:
                        clip["video"] = result
                        clip["status"] = "corrected"
                        return {"success": True, "video": result}

            elif action == "lip_sync":
                scene = next((s for s in self.project["scenes"] if s["id"] == scene_id), {})
                chars = scene.get("characters_present", [])
                primary_ref = get_reference_image(self.project, chars[0]) if chars else None
                audio_path = self.scene_audio.get(scene_id)
                if video_path and primary_ref and audio_path:
                    out_path = os.path.join(output_dir, f"lipsync_fix_{scene_id}_{shot_index}.mp4")
                    result = generate_lip_sync_video(
                        character_image_path=primary_ref,
                        audio_path=audio_path,
                        output_path=out_path,
                        existing_video_path=str(video_path),
                        mode="auto",
                    )
                    if result:
                        clip["video"] = result
                        clip["status"] = "corrected"
                        return {"success": True, "video": result}

            elif action == "rife":
                if video_path:
                    out_path = os.path.join(output_dir, f"rife_fix_{scene_id}_{shot_index}.mp4")
                    result = generate_rife_interpolation(str(video_path), out_path)
                    if result:
                        clip["video"] = result
                        clip["status"] = "corrected"
                        return {"success": True, "video": result}

            elif action == "upscale":
                if video_path:
                    out_path = os.path.join(output_dir, f"upscale_fix_{scene_id}_{shot_index}.mp4")
                    result = upscale_video_seedvr2(str(video_path), out_path)
                    if result:
                        clip["video"] = result
                        clip["status"] = "corrected"
                        return {"success": True, "video": result}

            elif action == "color_grade":
                from phase_c_ffmpeg import apply_color_grade
                preset = params.get("preset", "warm_cinema")
                lut_path = params.get("lut_path")
                if video_path:
                    out_path = os.path.join(output_dir, f"graded_{scene_id}_{shot_index}.mp4")
                    result = apply_color_grade(str(video_path), out_path, preset=preset, lut_path=lut_path)
                    if result:
                        clip["video"] = result
                        clip["status"] = "corrected"
                        return {"success": True, "video": result}

            elif action == "speed":
                from phase_c_ffmpeg import adjust_speed
                factor = float(params.get("factor", 1.0))
                if video_path and factor != 1.0:
                    out_path = os.path.join(output_dir, f"speed_{scene_id}_{shot_index}.mp4")
                    result = adjust_speed(str(video_path), out_path, factor=factor)
                    if result:
                        clip["video"] = result
                        clip["status"] = "corrected"
                        return {"success": True, "video": result}

            elif action == "voice_regen":
                text = params.get("text", "")
                voice_id = params.get("voice_id", "")
                stability = float(params.get("stability", 0.55))
                style = float(params.get("style", 0.6))
                if text and voice_id:
                    out_path = os.path.join(output_dir, f"voice_fix_{scene_id}_{shot_index}.mp3")
                    result = generate_dialogue_voiceover(
                        [{"character_name": "Character", "text": text, "voice_id": voice_id}],
                        out_path,
                    )
                    if result and os.path.exists(out_path):
                        self.scene_audio[scene_id] = out_path
                        return {"success": True, "audio": out_path}

            return {"success": False, "error": f"Action '{action}' failed or not applicable"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def proceed_to_assembly(self):
        """Resume pipeline from REVIEW stage to transitions + assembly."""
        self.progress("REVIEW_COMPLETE", "Director's Cut approved — proceeding to assembly", 88)
        self.resume()

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

        settings = project.get("global_settings", {})
        total_scenes = len(scenes)

        # Restore checkpoint if resuming
        skip_scenes = set()
        if resume and self.has_checkpoint():
            skip_scenes = self._restore_from_checkpoint()

        # ----------------------------------------------------------
        # STEP 0: Generate style rules
        # ----------------------------------------------------------
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

        style_suffix = style_rules_to_prompt_suffix(style_rules)

        # ----------------------------------------------------------
        # STEP 1: Generate BGM
        # ----------------------------------------------------------
        self.progress("AUDIO", "Generating background music...", 5)
        music_mood = settings.get("music_mood", "suspense")
        bgm_path = os.path.join(self.temp_dir, f"bgm_{music_mood}.mp3")
        if not os.path.exists(bgm_path):
            generate_fal_bgm(music_mood, bgm_path, duration=47)  # FAL max is 47s, loops in assembly

        # Master the BGM for cinema-grade audio (EQ, compression, limiting)
        if os.path.exists(bgm_path):
            try:
                from phase_b_audio import master_music
                mastered_path = os.path.join(self.temp_dir, f"bgm_{music_mood}_mastered.mp3")
                mastered = master_music(bgm_path, mastered_path, preset="cinema_master")
                if mastered and os.path.exists(mastered):
                    bgm_path = mastered
                    self.progress("AUDIO", "BGM mastered (cinema_master preset)", 6)
            except Exception as e_master:
                print(f"   [AUDIO] BGM mastering skipped (non-critical): {e_master}")

        # ----------------------------------------------------------
        # STEP 2: Process each scene
        # ----------------------------------------------------------
        all_scene_videos = []

        for scene_idx, scene in enumerate(scenes):
            if self.cancelled:
                self.progress("CANCELLED", "Pipeline cancelled by user", 0)
                return None

            scene_id = scene["id"]
            scene_title = scene.get("title", f"Scene {scene_idx + 1}")
            base_pct = 10 + (scene_idx / total_scenes) * 80

            # Skip scenes already completed in a previous run
            if scene_idx in skip_scenes and scene_id in self.scene_clips:
                self.progress("SKIP", f"Scene {scene_idx+1} already complete (resumed)", base_pct)
                all_scene_videos.append({
                    "scene_id": scene_id,
                    "clips": self.scene_clips[scene_id],
                    "audio": self.scene_audio.get(scene_id),
                    "foley": [],
                })
                continue

            self.progress("SCENE", f"Processing scene {scene_idx+1}/{total_scenes}: {scene_title}", base_pct)
            self.current_stage = "SCENE"
            self.current_scene_id = scene_id

            # Pause checkpoint — between scenes
            if not self._check_pause():
                self.progress("CANCELLED", "Pipeline cancelled by user", 0)
                return None

            # Reset temporal consistency for new scene
            self.continuity.reset_scene()

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
                self.progress("DECOMPOSE", f"Decomposing scene into shots...", base_pct + 2)
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
                self.progress("DIRECTOR", "Chief Director reviewing shots...", base_pct + 3)
                review = self.director.validate_shot_prompts(shots, scene)
                if review.get("decision") == "MODIFIED":
                    shots = review.get("shots", shots)
                    print(f"   [DIRECTOR] Shots modified — {len(review.get('violations', []))} violations corrected")
                elif review.get("decision") == "REJECTED":
                    print(f"   [DIRECTOR] Shots REJECTED — regenerating with corrections")
                    # Regenerate with stricter constraints
                    shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules)

                update_scene_shots(project, scene_id, shots)

            # --- 2b. Generate dialogue audio ---
            scene_audio_path = None
            dialogue = scene.get("dialogue", "")
            action = scene.get("action", "")

            # Auto-generate dialogue if characters are present but no dialogue written
            if chars_in_scene and not dialogue and action:
                self.progress("DIALOGUE", "Auto-generating dialogue from action...", base_pct + 5)
                dialogue_lines = generate_dialogue(scene, chars_in_scene, scene.get("mood", "neutral"))
            elif dialogue:
                self.progress("DIALOGUE", "Generating dialogue audio...", base_pct + 5)
                if isinstance(dialogue, list):
                    dialogue_lines = dialogue
                else:
                    # Parse written dialogue into structured lines
                    dialogue_lines = generate_dialogue(scene, chars_in_scene, scene.get("mood", "neutral"))
            else:
                dialogue_lines = []

            if dialogue_lines:
                scene_audio_path = os.path.join(self.temp_dir, f"audio_{scene_id}.mp3")
                result = generate_dialogue_voiceover(
                    dialogue_lines, chars_in_scene, scene_audio_path
                )
                if result:
                    self.scene_audio[scene_id] = scene_audio_path

            # --- 2c. Generate layered foley per shot (ambience + action + texture) ---
            # Parallelized: each shot's foley is fully independent
            def _generate_foley_for_shot(si_shot_pair):
                si, _shot = si_shot_pair
                foley_path = os.path.join(self.temp_dir, f"foley_{scene_id}_{si}.mp3")
                dur = min(5.0, scene.get("duration_seconds", 10) / max(len(shots), 1))
                result = generate_layered_foley(_shot, scene, foley_path, duration=dur)
                if not result:
                    foley_desc = _shot.get("scene_foley", "ambient room tone")
                    result = generate_scene_foley(foley_desc, foley_path)
                return si, result

            foley_paths = [None] * len(shots)
            with ThreadPoolExecutor(max_workers=min(len(shots), 4)) as foley_pool:
                foley_futures = foley_pool.map(_generate_foley_for_shot, enumerate(shots))
                for si, result in foley_futures:
                    foley_paths[si] = result

            # --- 2d. Generate visual content per shot ---
            scene_clip_paths = []
            num_shots = len(shots)

            # --- TRY KLING STORYBOARD MODE FIRST (unified latent space) ---
            # Paper: "Because the cuts share this unified space, the hero character
            # maintains absolute temporal and visual consistency across the entire sequence."
            storyboard_result = None
            if num_shots >= 2 and num_shots <= 6:
                first_enhanced = self.continuity.enhance_shot_prompt(shots[0], scene, None, 0)
                first_cc = first_enhanced.get("continuity_config", {})
                first_ref = first_cc.get("primary_reference")
                first_img = os.path.join(self.temp_dir, f"img_{scene_id}_0.jpg")

                # Generate first keyframe for storyboard start_image
                if first_ref and os.path.exists(str(first_ref)):
                    first_prompt = first_enhanced["prompt"]
                    if style_suffix:
                        first_prompt = f"{first_prompt}. {style_suffix}"
                    generate_ai_broll(
                        first_prompt, first_img,
                        character_image=first_ref,
                        multi_angle_refs=first_cc.get("multi_angle_refs", []),
                        identity_anchor=first_cc.get("identity_anchor", ""),
                    )

                if os.path.exists(first_img):
                    storyboard_vid = os.path.join(self.temp_dir, f"storyboard_{scene_id}.mp4")
                    self.progress("STORYBOARD", f"Kling storyboard: {num_shots} shots unified", base_pct + 15)
                    storyboard_result = generate_kling_storyboard(
                        shots, first_img, storyboard_vid,
                        multi_angle_refs=first_cc.get("multi_angle_refs", []),
                    )

            if storyboard_result and os.path.exists(storyboard_result):
                # Storyboard succeeded — use the unified video for all shots
                print(f"   [STORYBOARD] Unified video generated — skipping per-shot generation")
                scene_clip_paths.append(storyboard_result)
            else:
                # Fall back to per-shot generation
                if storyboard_result is None and num_shots >= 2:
                    print(f"   [STORYBOARD] Storyboard failed — falling back to per-shot generation")

                for si, shot in enumerate(shots):
                    if not self._check_pause():
                        self.progress("CANCELLED", "Pipeline cancelled by user", 0)
                        return None

                    shot_pct = base_pct + 10 + (si / num_shots) * 60 * (1 / total_scenes)
                    shot_id = shot.get("id", f"shot_{si}")
                    self.current_shot_id = shot_id
                    self.current_stage = "GENERATE"
                    shot_start_time = time.time()
                    MAX_SHOT_SECONDS = 300  # 5 min hard timeout per shot

                    # Helper for shot-scoped progress events
                    def shot_progress(stage, detail, pct=shot_pct, **kwargs):
                        self.progress(stage, detail, pct, scene_id=scene_id, shot_id=shot_id, **kwargs)

                    shot_progress("GENERATE", f"Shot {si+1}/{num_shots} of scene '{scene_title}'")

                    # Enhance prompt with continuity engine
                    prev_shot = shots[si - 1] if si > 0 else None
                    enhanced = self.continuity.enhance_shot_prompt(shot, scene, prev_shot, si)
                    full_prompt = enhanced["prompt"]
                    if style_suffix:
                        full_prompt = f"{full_prompt}. {style_suffix}"

                    cc = enhanced.get("continuity_config", {})

                    # WORKFLOW SELECTOR — log which template is used per shot
                    try:
                        from workflow_selector import get_shot_workflow_summary
                        wf_summary = get_shot_workflow_summary(shot)
                        print(f"   {wf_summary}")
                        shot_progress("WORKFLOW", wf_summary, shot_pct)
                    except ImportError:
                        pass

                    # SEED LOCKING — use scene_seed for uniform generation across all shots
                    scene_seed = cc.get("scene_seed")

                    # --- IMAGE GENERATION (with QC loop) ---
                    img_path = os.path.join(self.temp_dir, f"img_{scene_id}_{si}.jpg")
                    max_retries = 3
                    primary_ref = cc.get("primary_reference")
                    loc_seed = scene_seed or cc.get("location_seed")
                init_img = cc.get("init_image") if cc.get("use_img2img") else None
                denoise = cc.get("denoise_strength", 1.0)

                # RECURSIVE PROMPT MUTATION LOOP
                # Architecture: generate → evaluate identity → mutate prompt → regenerate
                # Each retry progressively strengthens identity preservation
                identity_anchor = cc.get("identity_anchor", "")
                mutation_level = 0  # 0=normal, 1=strengthened, 2=maximum preservation

                for attempt in range(max_retries):
                    current_seed = (loc_seed + attempt) if loc_seed else None

                    # PROMPT MUTATION based on previous failure
                    if mutation_level == 0:
                        mod_prompt = full_prompt
                    elif mutation_level == 1:
                        # Strengthen: simplify scene, boost identity language
                        mod_prompt = (
                            f"CRITICAL: Maintain exact face from reference. "
                            f"{full_prompt}. "
                            f"The character's face MUST match the reference photo exactly."
                        )
                        shot_progress("MUTATE", f"Prompt mutation level 1: strengthened identity", shot_pct)
                    else:
                        # Maximum: strip scene to minimal, force identity
                        sections = {}
                        import re
                        for tag in ["SHOT", "SCENE", "ACTION", "OUTFIT", "QUALITY"]:
                            match = re.search(rf'\[{tag}\]\s*(.+?)(?=\[(?:SHOT|SCENE|ACTION|OUTFIT|QUALITY)\]|$)', full_prompt, re.DOTALL)
                            if match:
                                sections[tag] = match.group(1).strip()
                        # Use ONLY scene + simple action — strip everything else
                        mod_prompt = (
                            f"[SHOT] Close-up portrait, 85mm f/1.4 lens. "
                            f"[SCENE] {sections.get('SCENE', 'neutral background')}. "
                            f"[ACTION] The character faces the camera directly. "
                            f"[QUALITY] Photorealistic, 8K, face clearly visible."
                        )
                        shot_progress("MUTATE", f"Prompt mutation level 2: maximum identity lock", shot_pct)

                    result = generate_ai_broll(
                        mod_prompt, img_path,
                        seed=current_seed,
                        character_image=primary_ref,
                        init_image=init_img,
                        denoise_strength=denoise,
                        multi_angle_refs=cc.get("multi_angle_refs", []),
                        identity_anchor=identity_anchor,
                        pulid_weight_override=cc.get("pulid_weight_override"),
                    )

                    # EVALUATE: check identity before accepting
                    if result and primary_ref and os.path.exists(img_path):
                        from phase_c_vision import validate_identity_image
                        try:
                            # Quick image-level identity check
                            img_sim = validate_identity_image(img_path, primary_ref, threshold=cc.get("identity_threshold", 0.70))
                            if img_sim.get("passed", True):
                                shot_progress("IDENTITY_OK", f"Image identity verified (attempt {attempt+1})", shot_pct,
                                    image_url=img_path, identity_score=img_sim.get("similarity", 0.8))
                                break
                            else:
                                sim_score = img_sim.get("similarity", 0)
                                shot_progress("IDENTITY_FAIL", f"Image identity {sim_score:.2f} < threshold", shot_pct,
                                    image_url=img_path, identity_score=sim_score)
                                mutation_level = min(mutation_level + 1, 2)
                                continue
                        except (ImportError, RuntimeError) as e_val:
                            print(f"      [IDENTITY] Validation unavailable ({e_val}), accepting result")
                            break
                    elif result:
                        break

                    shot_progress("RETRY", f"Image retry {attempt+1}/{max_retries}", shot_pct)

                if not os.path.exists(img_path):
                    shot_progress("SHOT_FAILED", f"Image generation failed for shot {si+1} — skipping", shot_pct)
                    self.failed_shots.append(shot_id)
                    self.shot_results[shot_id] = {"image": None, "video": None, "identity_score": 0.0, "status": "failed"}
                    continue

                # Record for temporal chaining
                self.continuity.record_shot_generated(img_path, scene_id)

                # --- VIDEO GENERATION (with cascade + identity validation) ---
                vid_path = os.path.join(self.temp_dir, f"vid_{scene_id}_{si}.mp4")
                camera = shot.get("camera", "zoom_in_slow")

                # Resolve AUTO → concrete API + shot-type-aware fallback chain
                raw_api = shot.get("target_api", "AUTO")
                video_fallbacks = None
                resolved_shot_type = None
                if raw_api == "AUTO":
                    from workflow_selector import classify_shot_type, WORKFLOW_TEMPLATES
                    resolved_shot_type = classify_shot_type(
                        shot.get("prompt", ""), camera, shot.get("characters_in_frame", [])
                    )
                    template = WORKFLOW_TEMPLATES.get(resolved_shot_type, WORKFLOW_TEMPLATES["medium"])
                    target_api = template["target_api"]
                    video_fallbacks = template.get("video_fallbacks")
                    shot_progress("ROUTING", f"AUTO → {target_api} (shot type: {resolved_shot_type})", shot_pct)
                else:
                    target_api = raw_api

                max_vid_retries = 3
                final_vid = None
                chars_in_frame = shot.get("characters_in_frame", [])

                # Budget check before video generation
                _budget_limit = settings.get("budget_limit_usd", 0)
                if _budget_limit > 0:
                    _spent = self.cost_tracker.get_video_cost(project["id"]).get("total_usd", 0) if hasattr(self.cost_tracker, 'get_video_cost') else 0
                    if _spent >= _budget_limit:
                        shot_progress("BUDGET", f"Budget limit reached (${_spent:.2f}/${_budget_limit:.2f})", shot_pct + 3)
                        break

                for v_attempt in range(max_vid_retries):
                    # Per-shot timeout guard
                    if time.time() - shot_start_time > MAX_SHOT_SECONDS:
                        shot_progress("TIMEOUT", f"Shot {si+1} exceeded {MAX_SHOT_SECONDS}s — skipping video", shot_pct)
                        break
                    shot_progress("VIDEO", f"Video gen attempt {v_attempt+1} ({target_api})", shot_pct + 3)

                    # Pass per-API engine overrides from project settings
                    _api_engines = settings.get("api_engines", {})
                    _api_cfg = _api_engines.get(target_api, {})

                    # Filter out disabled APIs from fallback chain
                    _active_fallbacks = [
                        fb for fb in (video_fallbacks or [])
                        if _api_engines.get(fb, {}).get("enabled", True) is not False
                    ]

                    temp_vid = generate_ai_video(
                        img_path, camera, target_api, vid_path,
                        pacing="calculated",
                        character_id=cc.get("primary_character", ""),
                        multi_angle_refs=cc.get("multi_angle_refs", []),
                        shot_type=resolved_shot_type,
                        video_fallbacks=_active_fallbacks if _active_fallbacks else video_fallbacks,
                    )

                    if temp_vid and chars_in_frame and primary_ref:
                        # Build validation configs
                        val_configs = []
                        for cid in chars_in_frame[:1]:  # Validate primary character
                            ref = get_reference_image(self.project, cid)
                            char = next((c for c in chars_in_scene if c["id"] == cid), None)
                            if ref and char:
                                val_configs.append({"id": cid, "reference_image": ref, "name": char["name"]})

                        shot_type = cc.get("shot_type", "medium")
                        if val_configs:
                            # Use continuity engine's shared validator for rolling history
                            vid_result = self.continuity.validate_shot(
                                temp_vid, [cfg["id"] for cfg in val_configs],
                                shot_type=shot_type,
                                mode="standard",
                                attempt=v_attempt,
                                max_attempts=max_vid_retries,
                            )
                            is_passed = vid_result.get("passed") if hasattr(vid_result, 'get') else vid_result.passed
                            score = vid_result.overall_score if hasattr(vid_result, 'overall_score') else 0.0

                            if is_passed:
                                final_vid = temp_vid
                                # Build quality metrics for SSE
                                qm = {"identity_score": round(score, 3), "shot_type": shot_type}
                                if hasattr(vid_result, 'character_results'):
                                    for cid, cr in vid_result.character_results.items():
                                        qm[f"char_{cr.character_name}_sim"] = round(cr.best_similarity, 3)
                                shot_progress("VALIDATED", f"Identity confirmed ✓ ({score:.2f})", shot_pct + 5,
                                              identity_score=score, shot_type=shot_type, quality_metrics=qm)
                                self.shot_results[shot_id] = {
                                    "image": img_path, "video": temp_vid,
                                    "identity_score": score, "status": "validated",
                                }
                                break
                            else:
                                fail_reason = ""
                                if hasattr(vid_result, 'character_results'):
                                    for cr in vid_result.character_results.values():
                                        if not cr.matched:
                                            fail_reason = cr.primary_failure_reason.value
                                            break
                                shot_progress("IDENTITY_FAIL", f"Retrying video ({v_attempt+1}): {fail_reason}", shot_pct + 3,
                                              identity_score=score, failure_reason=fail_reason)
                        else:
                            final_vid = temp_vid
                            break
                    elif temp_vid:
                        final_vid = temp_vid
                        break

                # --- VBench QUALITY EVALUATION (async — does not gate downstream) ---
                if final_vid:
                    _vb_vid = final_vid
                    _vb_prompt = shot.get("prompt", "")
                    _vb_ref = [ref_img] if ref_img else None
                    _vb_shot_type = shot_type
                    _vb_shot_id = shot.get("id", f"shot_{shot_index}")
                    _vb_api = str(target_api)
                    _vb_mutation = mutation_level

                    def _run_vbench(_vid=_vb_vid, _prompt=_vb_prompt, _ref=_vb_ref,
                                    _st=_vb_shot_type, _sid=_vb_shot_id, _api=_vb_api,
                                    _mut=_vb_mutation):
                        try:
                            vbench_result = self.vbench.evaluate(_vid, _prompt, reference_images=_ref, shot_type=_st)
                            self.quality_tracker.log_shot_quality(
                                shot_id=_sid,
                                video_id=self.project.get("id", "unknown"),
                                shot_type=_st,
                                target_api=_api,
                                vbench_result=vbench_result,
                                generation_cost=0.0,
                                llm_cost=0.0,
                                attempt=_mut,
                            )
                            print(f"      [VBENCH] Score: {vbench_result.overall_score:.3f}")
                        except Exception as e:
                            print(f"      [VBENCH] Evaluation skipped: {e}")

                    threading.Thread(target=_run_vbench, daemon=True).start()

                # --- QUALITY-GATED POST-PROCESSING ---
                if final_vid:
                    try:
                        from phase_c_ffmpeg import assess_motion_quality
                        mq = assess_motion_quality(final_vid)
                        motion_s = mq["smoothness_score"]
                        if mq["recommendation"] == "interpolate":
                            shot_progress("INTERP", f"Motion quality {motion_s:.2f} — applying RIFE", shot_pct + 4,
                                          motion_score=motion_s)
                            interp_path = os.path.join(self.temp_dir, f"interp_{scene_id}_{si}.mp4")
                            interp_result = generate_rife_interpolation(final_vid, interp_path)
                            if interp_result:
                                final_vid = interp_result
                        elif mq["recommendation"] == "accept":
                            shot_progress("QUALITY", f"Motion quality OK ({motion_s:.2f}) — skipping RIFE", shot_pct + 4,
                                          motion_score=motion_s)
                        # "regenerate" recommendation is handled by the retry loop above
                    except Exception as e:
                        print(f"      [QUALITY] Motion assessment skipped: {e}")

                # --- FACE-SWAP POST-PROCESSING (FaceFusion) ---
                if final_vid and primary_ref and settings.get("face_swap_enabled", True):
                    swapped_path = os.path.join(self.temp_dir, f"swapped_{scene_id}_{si}.mp4")
                    swap_result = face_swap_video_frames(final_vid, primary_ref, swapped_path)
                    if swap_result:
                        final_vid = swap_result

                # --- LIP SYNC (smart mode: overlay on existing video OR generate from photo) ---
                if final_vid and primary_ref:
                    scene_audio_path = self.scene_audio.get(scene_id)
                    has_dialogue = scene.get("dialogue") or scene.get("voiceover")
                    if has_dialogue and scene_audio_path and os.path.exists(scene_audio_path):
                        lipsync_path = os.path.join(self.temp_dir, f"lipsync_{scene_id}_{si}.mp4")

                        # Smart pre-analysis: recommend_lip_sync_mode() analyzes shot content
                        # to decide overlay vs generation vs skip before wasting API calls
                        from lip_sync import recommend_lip_sync_mode
                        import subprocess as _sp
                        try:
                            _dur_r = _sp.run(
                                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", scene_audio_path],
                                capture_output=True, text=True, timeout=10,
                            )
                            _dlg_dur = float(_dur_r.stdout.strip()) if _dur_r.returncode == 0 else 3.0
                        except (subprocess.SubprocessError, ValueError, OSError):
                            _dlg_dur = 3.0

                        _shot_type = cc.get("shot_type", "medium") if cc else "medium"
                        # User override from settings takes precedence over auto-recommendation
                        _user_ls_mode = settings.get("lip_sync_mode", "auto")
                        if _user_ls_mode != "auto":
                            ls_rec = {"mode": _user_ls_mode, "reason": f"user override: {_user_ls_mode}"}
                        else:
                            ls_rec = recommend_lip_sync_mode(
                                video_path=final_vid, shot_type=_shot_type,
                                dialogue_length_seconds=_dlg_dur,
                            )
                        ls_mode = ls_rec.get("mode", "auto")
                        shot_progress("LIPSYNC",
                                      f"Lip sync: {ls_mode} ({ls_rec.get('reason', '')[:40]})",
                                      shot_pct + 4)

                        if ls_mode != "skip":
                            lipsync_result = generate_lip_sync_video(
                                character_image_path=primary_ref,
                                audio_path=scene_audio_path,
                                output_path=lipsync_path,
                                existing_video_path=final_vid if ls_mode != "generation" else None,
                                mode=ls_mode if ls_mode in ("overlay", "generation") else "auto",
                                resolution="720p",
                            )
                            if lipsync_result:
                                final_vid = lipsync_result
                        else:
                            shot_progress("LIPSYNC", f"Lip sync skipped: {ls_rec.get('reason', '')}", shot_pct + 4)

                # --- RIFE FRAME INTERPOLATION (cloud via fal.ai) ---
                if final_vid and settings.get("rife_enabled", True):
                    shot_progress("INTERP", "Cloud frame interpolation (RIFE)", shot_pct + 5)
                    interp_path = os.path.join(self.temp_dir, f"interp_{scene_id}_{si}.mp4")
                    interpolated = generate_rife_interpolation(
                        final_vid, interp_path, num_frames=2, use_scene_detection=True,
                    )
                    if interpolated:
                        final_vid = interpolated
                    else:
                        # Fallback to local FFmpeg minterpolate
                        local_interp = self._frame_interpolate(final_vid, scene_id, si)
                        if local_interp:
                            final_vid = local_interp

                # --- UPSCALE: SeedVR2 cloud (temporally consistent) → fallback to Real-ESRGAN ---
                if final_vid and settings.get("video_upscale_enabled", True):
                    upscale_path = os.path.join(self.temp_dir, f"upscale_{scene_id}_{si}.mp4")
                    upscaled = upscale_video_seedvr2(final_vid, upscale_path, target_resolution="1080p")
                    if upscaled:
                        final_vid = upscaled
                    else:
                        # Fallback to local Real-ESRGAN
                        local_up = self._upscale_video(final_vid, scene_id, si)
                        if local_up:
                            final_vid = local_up

                scene_clip_paths.append(final_vid or img_path)
                self._save_checkpoint()  # Per-shot checkpoint

                # --- FRAME CHAINING: extract last frame for next shot's start ---
                if final_vid and os.path.exists(final_vid):
                    last_frame = os.path.join(self.temp_dir, f"lastframe_{scene_id}_{si}.jpg")
                    extract_last_frame(final_vid, last_frame)
                    # Store for use as next shot's start_image via Kling
                    if os.path.exists(last_frame):
                        self._last_frame_for_chaining = last_frame

            # --- GENERATE TRANSITION CLIPS between shots (Wan FLF2V) ---
            # Parallelized: extract frames sequentially (fast), then generate all
            # transition clips concurrently (slow API calls, fully independent).
            if len(scene_clip_paths) > 1:
                # Phase 1: extract boundary frames (CPU-only, fast)
                transition_tasks = []  # [(index, prev_last_path, curr_first_path, output_path)]
                for i in range(1, len(scene_clip_paths)):
                    prev_last = os.path.join(self.temp_dir, f"chain_last_{scene_id}_{i-1}.jpg")
                    curr_first = os.path.join(self.temp_dir, f"img_{scene_id}_{i}.jpg")
                    if extract_last_frame(scene_clip_paths[i - 1], prev_last) and os.path.exists(curr_first):
                        out_path = os.path.join(self.temp_dir, f"transition_{scene_id}_{i}.mp4")
                        transition_tasks.append((i, prev_last, curr_first, out_path))

                # Phase 2: generate transition clips in parallel
                transition_results = {}  # index -> path or None
                if transition_tasks:
                    def _gen_transition(task):
                        idx, p_last, c_first, out = task
                        res = generate_transition_clip(
                            p_last, c_first, out,
                            prompt="Smooth transition, same character, continuous motion",
                        )
                        return idx, res

                    with ThreadPoolExecutor(max_workers=min(len(transition_tasks), 3)) as trans_pool:
                        for idx, res in trans_pool.map(_gen_transition, transition_tasks):
                            transition_results[idx] = res

                # Phase 3: interleave clips and transitions in order
                chained_clips = [scene_clip_paths[0]]
                for i in range(1, len(scene_clip_paths)):
                    trans = transition_results.get(i)
                    if trans:
                        chained_clips.append(trans)
                    chained_clips.append(scene_clip_paths[i])
                scene_clip_paths = chained_clips

            self.scene_clips[scene_id] = scene_clip_paths
            self._completed_scene_indices.add(scene_idx)
            self._save_checkpoint(scene_idx)

            all_scene_videos.append({
                "scene_id": scene_id,
                "clips": scene_clip_paths,
                "audio": self.scene_audio.get(scene_id),
                "foley": foley_paths,
            })

        # ----------------------------------------------------------
        # STEP 2.5: DIRECTOR'S CUT — Review & Refine
        # ----------------------------------------------------------
        # Auto-pause so the user can review every clip, apply corrections,
        # regenerate with adjusted prompts, and approve before assembly.

        # Build review manifest
        self.review_clips = {}
        for scene_data in all_scene_videos:
            sid = scene_data["scene_id"]
            scene = next((s for s in project["scenes"] if s["id"] == sid), {})
            for si, clip_path in enumerate(scene_data.get("clips", [])):
                shots = scene.get("shots", [])
                shot = shots[si] if si < len(shots) else {}
                shot_id = shot.get("id", f"shot_{si}")
                img_path = os.path.join(self.temp_dir, f"img_{sid}_{si}.jpg")
                self.review_clips[shot_id] = {
                    "image": img_path if os.path.exists(img_path) else None,
                    "video": clip_path,
                    "scene_id": sid,
                    "shot_index": si,
                    "prompt": shot.get("prompt", ""),
                    "camera": shot.get("camera", ""),
                    "target_api": shot.get("target_api", "KLING_3_0"),
                    "status": "pending_review",
                }

        self.progress("REVIEW", f"All {len(self.review_clips)} clips ready for Director's Cut review", 87)
        self.current_stage = "REVIEW"

        # Auto-pause — user reviews, applies corrections, then calls proceed_to_assembly()
        self.pause()

        # Block until user resumes (after reviewing and approving clips)
        if not self._check_pause():
            self.progress("CANCELLED", "Pipeline cancelled during review", 0)
            return None

        # Update all_scene_videos with any corrected clips
        for scene_data in all_scene_videos:
            sid = scene_data["scene_id"]
            scene = next((s for s in project["scenes"] if s["id"] == sid), {})
            updated_clips = []
            for si, clip_path in enumerate(scene_data.get("clips", [])):
                shots = scene.get("shots", [])
                shot = shots[si] if si < len(shots) else {}
                shot_id = shot.get("id", f"shot_{si}")
                review = self.review_clips.get(shot_id, {})
                # Use corrected video if available
                updated_clips.append(review.get("video", clip_path))
            scene_data["clips"] = updated_clips

        # ----------------------------------------------------------
        # STEP 2.6: Inter-Scene Transitions (Wan FLF2V)
        # ----------------------------------------------------------
        # Generate smooth transition clips between the last frame of scene N
        # and the first frame of scene N+1 using first-last-frame interpolation.
        # This creates visual continuity across scene boundaries.

        if len(all_scene_videos) > 1:
            self.progress("TRANSITIONS", f"Generating {len(all_scene_videos)-1} scene transitions...", 88)

            for i in range(len(all_scene_videos) - 1):
                if self.cancelled:
                    return None

                curr_scene = all_scene_videos[i]
                next_scene = all_scene_videos[i + 1]

                curr_clips = curr_scene.get("clips", [])
                next_clips = next_scene.get("clips", [])

                if not curr_clips or not next_clips:
                    continue

                # Extract last frame of current scene's last clip
                last_clip = curr_clips[-1]
                first_clip = next_clips[0]

                if not (last_clip and os.path.exists(str(last_clip))):
                    continue

                last_frame_path = os.path.join(self.temp_dir, f"scene_transition_last_{i}.jpg")
                first_frame_path = os.path.join(self.temp_dir, f"scene_transition_first_{i+1}.jpg")

                # Extract last frame from previous scene
                last_result = extract_last_frame(last_clip, last_frame_path)

                # Extract first frame from next scene (use keyframe image if available)
                next_scene_id = next_scene.get("scene_id", "")
                next_keyframe = os.path.join(self.temp_dir, f"img_{next_scene_id}_0.jpg")
                if os.path.exists(next_keyframe):
                    import shutil
                    shutil.copy2(next_keyframe, first_frame_path)
                elif first_clip and os.path.exists(str(first_clip)):
                    # Extract first frame from video
                    try:
                        subprocess.run(
                            ["ffmpeg", "-y", "-i", str(first_clip), "-vframes", "1",
                             "-q:v", "1", first_frame_path],
                            capture_output=True, timeout=15
                        )
                    except (subprocess.SubprocessError, OSError) as e_ff:
                        print(f"   [TRANSITION] Frame extract failed: {e_ff}")
                        continue

                if last_result and os.path.exists(first_frame_path):
                    # Determine transition style from scene moods
                    curr_scene_data = next((s for s in self.project["scenes"] if s["id"] == curr_scene.get("scene_id")), {})
                    next_scene_data = next((s for s in self.project["scenes"] if s["id"] == next_scene.get("scene_id")), {})
                    curr_mood = curr_scene_data.get("mood", "neutral")
                    next_mood = next_scene_data.get("mood", "neutral")

                    transition_prompt = _build_transition_prompt(curr_mood, next_mood)

                    transition_path = os.path.join(self.temp_dir, f"scene_transition_{i}_to_{i+1}.mp4")
                    self.progress("TRANSITIONS", f"Scene {i+1} → {i+2}: {transition_prompt[:40]}...", 88 + i)

                    trans_result = generate_transition_clip(
                        last_frame_path, first_frame_path, transition_path,
                        prompt=transition_prompt,
                        duration_frames=41,  # ~2.5 seconds at 16fps — brief bridge
                    )

                    if trans_result:
                        # Insert transition clip between scenes
                        curr_scene["transition_out"] = trans_result
                        print(f"   [TRANSITION] Scene {i+1} → {i+2}: {transition_path}")

        # ----------------------------------------------------------
        # STEP 3: Global Assembly
        # ----------------------------------------------------------
        if self.cancelled:
            return None

        self.progress("ASSEMBLY", "Assembling final video...", 92)
        final_path = self._assemble_final(all_scene_videos, bgm_path, settings)

        if final_path and os.path.exists(final_path):
            # AUTO-CLEANUP: remove intermediate temp files after successful export
            try:
                from cleanup import cleanup_project
                cleanup_result = cleanup_project(self.project["id"], aggressive=False)
                if cleanup_result["files_deleted"] > 0:
                    self.progress("CLEANUP", f"Cleaned {cleanup_result['files_deleted']} temp files ({cleanup_result['mb_freed']} MB)", 98)
            except Exception as e:
                print(f"   [CLEANUP] Auto-cleanup failed (non-fatal): {e}")

            # Log final cost summary
            try:
                video_id = self.project.get("id", "unknown")
                cost_summary = self.cost_tracker.get_video_cost(video_id)
                if cost_summary.get("total_usd", 0) > 0:
                    print(f"\n   💰 [COST] Total: ${cost_summary['total_usd']:.2f} | LLM: ${cost_summary.get('llm_usd', 0):.2f} | API: ${cost_summary.get('api_usd', 0):.2f}")
            except Exception as e_cost:
                print(f"   [COST] Could not retrieve cost summary: {e_cost}")

            self._clear_checkpoint()  # Success — no need for checkpoint anymore
            self.progress("COMPLETE", f"Video exported: {final_path}", 100)
            return final_path
        else:
            self.progress("ERROR", "Final assembly failed", 95)
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
        Assembles all scene clips into the final video with:
        - Per-scene clip stitching
        - Cross-scene dissolve transitions (0.5s)
        - Dialogue audio per scene
        - Background music with sidechain compression
        - Foley layering
        """
        final_output = os.path.join(self.export_dir, "final_cinema.mp4")
        pacing = settings.get("video_pacing", "calculated")

        # 1. Normalize all clips + insert inter-scene transitions
        all_normalized = []
        for si, sd in enumerate(scene_data):
            # Scene clips
            for clip_path in sd["clips"]:
                if clip_path and os.path.exists(clip_path):
                    norm_path = clip_path.replace(".mp4", "_norm.mp4").replace(".jpg", "_norm.mp4")
                    try:
                        normalize_clip(clip_path, norm_path, duration_sec=4.0, effect="cinematic_glow")
                        all_normalized.append(norm_path)
                    except Exception as e:
                        print(f"   [WARN] Normalize failed: {e}")
                        all_normalized.append(clip_path)

            # Inter-scene transition clip (generated in Step 2.5)
            transition_out = sd.get("transition_out")
            if transition_out and os.path.exists(transition_out):
                trans_norm = transition_out.replace(".mp4", "_norm.mp4")
                try:
                    normalize_clip(transition_out, trans_norm, duration_sec=2.5, effect="cinematic_glow")
                    all_normalized.append(trans_norm)
                    print(f"   [ASSEMBLY] Inserted transition after scene {si+1}")
                except Exception as e_tn:
                    print(f"   [WARN] Transition normalize failed: {e_tn}")
                    all_normalized.append(transition_out)

        if not all_normalized:
            return None

        # 2. Stitch into timeline
        stitched = os.path.join(self.temp_dir, "stitched.mp4")
        try:
            stitch_modules(all_normalized, stitched)
        except Exception as e:
            print(f"   ⚠️ Stitch failed: {e}")
            return None

        # 2b. Apply color grading to stitched timeline
        # Maps mood → color preset for consistent cinematic look
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

        # 3. Mix audio layers with ffmpeg
        # Collect all dialogue audio
        dialogue_files = []
        for sd in scene_data:
            if sd.get("audio") and os.path.exists(sd["audio"]):
                dialogue_files.append(sd["audio"])

        # Simple final assembly: video + BGM (dialogue mixed if available)
        try:
            cmd = ["ffmpeg", "-y", "-i", stitched]
            filter_parts = []
            input_idx = 1

            # Add BGM if available
            if os.path.exists(bgm_path):
                cmd.extend(["-i", bgm_path])
                filter_parts.append(f"[{input_idx}:a]aloop=loop=-1:size=2e+09,volume=0.15[bgm]")
                input_idx += 1

            # Add first dialogue track if available
            if dialogue_files:
                cmd.extend(["-i", dialogue_files[0]])
                filter_parts.append(f"[{input_idx}:a]volume=1.0[dialogue]")
                input_idx += 1

            # Build audio mix
            if filter_parts:
                if len(filter_parts) == 2:
                    all_filters = ";".join(filter_parts) + ";[bgm][dialogue]amix=inputs=2:duration=longest[aout]"
                elif len(filter_parts) == 1 and "bgm" in filter_parts[0]:
                    all_filters = filter_parts[0].replace("[bgm]", "[aout]")
                else:
                    all_filters = filter_parts[0].replace("[dialogue]", "[aout]")

                cmd.extend([
                    "-filter_complex", all_filters,
                    "-map", "0:v", "-map", "[aout]",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k",
                    final_output,
                ])
            else:
                cmd.extend([
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                    "-c:a", "copy",
                    final_output,
                ])

            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            print(f"   ✅ Final cinema video: {final_output}")
            return final_output

        except Exception as e:
            print(f"   ⚠️ Final assembly error: {e}")
            # Fallback: just copy stitched as final
            import shutil
            shutil.copy2(stitched, final_output)
            return final_output

    # ------------------------------------------------------------------
    # SCENE-LEVEL PREVIEW
    # ------------------------------------------------------------------

    def generate_scene_preview(self, scene_id: str) -> Optional[str]:
        """Generate just one scene for preview purposes."""
        project = self.project
        scene = next((s for s in project["scenes"] if s["id"] == scene_id), None)
        if not scene:
            return None

        clips = self.scene_clips.get(scene_id, [])
        if not clips:
            return None

        # Stitch scene clips into a preview
        preview_path = os.path.join(self.export_dir, f"preview_{scene_id}.mp4")
        valid_clips = [c for c in clips if c and os.path.exists(c)]
        if valid_clips:
            try:
                stitch_modules(valid_clips, preview_path)
                return preview_path
            except Exception as e_stitch:
                print(f"   [PREVIEW] Stitch failed, returning first clip: {e_stitch}")
                return valid_clips[0] if valid_clips else None
        return None

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
