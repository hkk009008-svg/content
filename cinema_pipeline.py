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
from project_manager import MutationResult, load_project, get_project_dir, mutate_project, make_take
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

    def _all_shots(self, project: Optional[dict] = None) -> list[tuple[dict, int, dict]]:
        active_project = project or self.project
        rows: list[tuple[dict, int, dict]] = []
        for scene in active_project.get("scenes", []):
            for shot_index, shot in enumerate(scene.get("shots", [])):
                rows.append((scene, shot_index, shot))
        return rows

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

    def _latest_take(self, shot: dict, collection_name: str) -> Optional[dict]:
        takes = shot.get(collection_name, [])
        return takes[-1] if takes else None

    def _resolve_take_path(self, shot: dict, take_id: str) -> str:
        _, take = self._find_take(shot, take_id)
        return take.get("path", "") if take else ""

    def _candidate_take(self, shot: dict) -> Optional[dict]:
        if shot.get("approved_final_take_id"):
            _, take = self._find_take(shot, shot["approved_final_take_id"])
            if take:
                return take
        for collection_name in ("postprocess_variants", "motion_takes", "keyframe_takes"):
            take = self._latest_take(shot, collection_name)
            if take:
                return take
        return None

    def _project_gate_status(self, project: Optional[dict] = None) -> dict:
        active_project = project or self.project
        shots = [shot for _, _, shot in self._all_shots(active_project)]
        total = len(shots)
        return {
            "total_shots": total,
            "plans_approved": sum(1 for shot in shots if shot.get("plan_status") == "approved"),
            "keyframes_approved": sum(1 for shot in shots if shot.get("approved_keyframe_take_id")),
            "motions_generated": sum(1 for shot in shots if shot.get("motion_takes")),
            "finals_approved": sum(1 for shot in shots if shot.get("approved_final_take_id")),
        }

    def _gate_satisfied(self, gate: str, project: Optional[dict] = None) -> bool:
        active_project = project or self.project
        shots = [shot for _, _, shot in self._all_shots(active_project)]
        if not shots:
            return False
        if gate == "PLAN_REVIEW":
            return all(shot.get("plan_status") == "approved" for shot in shots)
        if gate == "KEYFRAME_REVIEW":
            return all(shot.get("approved_keyframe_take_id") for shot in shots)
        if gate == "REVIEW":
            return all(shot.get("approved_final_take_id") for shot in shots)
        return False

    def _wait_for_gate(self, gate: str, detail: str, percent: float) -> bool:
        while True:
            project = self._refresh_project_snapshot() or self.project
            if self._gate_satisfied(gate, project):
                return True
            self.current_stage = gate
            self.progress(gate, detail, percent)
            self.pause()
            if not self._check_pause():
                return False

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
        self._refresh_project_snapshot()
        return result

    def _record_diagnostic(self, shot_id: str, diagnostic: dict) -> None:
        def _mutator(_scene: dict, shot: dict):
            shot.setdefault("diagnostics", []).append(diagnostic)
            return MutationResult(diagnostic, save=True)

        self._mutate_shot(shot_id, _mutator)

    def _rebuild_review_clips(self, project: Optional[dict] = None) -> dict:
        active_project = project or self.project
        manifest = {}
        for scene, shot_index, shot in self._all_shots(active_project):
            candidate = self._candidate_take(shot) or {}
            keyframe_path = self._resolve_take_path(shot, shot.get("approved_keyframe_take_id", "")) or (
                self._latest_take(shot, "keyframe_takes") or {}
            ).get("path")
            manifest[shot["id"]] = {
                "scene_id": scene.get("id", ""),
                "shot_index": shot_index,
                "prompt": shot.get("prompt", ""),
                "camera": shot.get("camera", ""),
                "target_api": shot.get("target_api", "AUTO"),
                "image": keyframe_path,
                "video": candidate.get("path", "") if candidate.get("kind") != "keyframe" else "",
                "take_id": candidate.get("id", ""),
                "take_kind": candidate.get("kind", ""),
                "status": "pending_review",
            }
        self.review_clips = manifest
        return manifest

    def approve_shot_plan(self, shot_id: str, approved: bool, reason: str = "") -> dict:
        status = "approved" if approved else "rejected"

        def _mutator(_scene: dict, shot: dict):
            shot["plan_status"] = status
            shot["plan_rejection_reason"] = "" if approved else reason
            return MutationResult(
                {"shot_id": shot_id, "plan_status": shot["plan_status"], "reason": shot["plan_rejection_reason"]},
                save=True,
            )

        result = self._mutate_shot(shot_id, _mutator)
        return result or {"error": "Shot not found"}

    def approve_take(self, shot_id: str, take_id: str, approval_kind: str) -> dict:
        def _resolve_motion_source(shot: dict, candidate_take: dict) -> str:
            current = candidate_take
            visited = set()
            while current and current.get("id") not in visited:
                visited.add(current.get("id"))
                collection_name, _ = self._find_take(shot, current.get("id", ""))
                if collection_name == "motion_takes":
                    return current.get("id", "")
                source_take_id = current.get("source_take_id", "")
                if not source_take_id:
                    break
                _, current = self._find_take(shot, source_take_id)
            return ""

        def _mutator(_scene: dict, shot: dict):
            collection_name, take = self._find_take(shot, take_id)
            if not take:
                return MutationResult({"error": "Take not found"}, save=False)
            if approval_kind == "keyframe":
                if collection_name != "keyframe_takes":
                    return MutationResult({"error": "Take is not a keyframe"}, save=False)
                shot["approved_keyframe_take_id"] = take_id
            elif approval_kind == "final":
                if collection_name == "keyframe_takes":
                    return MutationResult({"error": "Keyframes cannot be approved as final takes"}, save=False)
                motion_take_id = take_id if collection_name == "motion_takes" else _resolve_motion_source(shot, take)
                if motion_take_id:
                    shot["approved_motion_take_id"] = motion_take_id
                shot["approved_final_take_id"] = take_id
            else:
                return MutationResult({"error": f"Unsupported approval kind '{approval_kind}'"}, save=False)
            return MutationResult({"shot_id": shot_id, "take_id": take_id, "approval_kind": approval_kind}, save=True)

        result = self._mutate_shot(shot_id, _mutator)
        return result or {"error": "Shot not found"}

    def _resolve_previous_approved_keyframe(self, scene: dict, shot_index: int) -> str:
        if shot_index <= 0:
            return ""
        previous_shot = scene.get("shots", [])[shot_index - 1]
        take_id = previous_shot.get("approved_keyframe_take_id", "")
        return self._resolve_take_path(previous_shot, take_id)

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
                from phase_b_audio import master_music
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

    def generate_keyframe_take(
        self,
        scene_id: str,
        shot_id: str,
        positive_prompt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
    ) -> dict:
        project = self._refresh_project_snapshot() or self.project
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
        self.current_stage = "KEYFRAME"
        self.current_scene_id = scene_id
        self.current_shot_id = shot_id
        self.progress(
            "KEYFRAME",
            f"Generating keyframe for {shot_id}",
            -1,
            scene_id=scene_id,
            shot_id=shot_id,
            take_id=take["id"],
        )

        result = generate_ai_broll(
            full_prompt,
            img_path,
            seed=cc.get("scene_seed"),
            character_image=primary_ref,
            init_image=cc.get("init_image") if cc.get("use_img2img") else None,
            denoise_strength=cc.get("denoise_strength", 1.0),
            multi_angle_refs=cc.get("multi_angle_refs", []),
            identity_anchor=cc.get("identity_anchor", ""),
            pulid_weight_override=cc.get("pulid_weight_override"),
            negative_prompt=negative_prompt or cc.get("negative_constraints") or shot.get("negative_constraints", ""),
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
        self.shot_results[shot_id] = {
            "image": img_path,
            "video": None,
            "identity_score": identity_score,
            "status": "keyframe_review",
            "take_id": take["id"],
        }
        self._rebuild_review_clips()
        self._save_checkpoint()
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

    def generate_motion_take(self, scene_id: str, shot_id: str) -> dict:
        project = self._refresh_project_snapshot() or self.project
        scene, shot, shot_index = self._find_shot(shot_id, project, scene_id)
        if not scene or not shot:
            return {"success": False, "error": "Shot not found"}
        if shot.get("plan_status") != "approved":
            return {"success": False, "error": "Shot plan must be approved before generating motion"}
        keyframe_take_id = shot.get("approved_keyframe_take_id", "")
        if not keyframe_take_id:
            return {"success": False, "error": "Approved keyframe required before generating motion"}

        source_image = self._resolve_take_path(shot, keyframe_take_id)
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
        self.current_stage = "MOTION"
        self.current_scene_id = scene_id
        self.current_shot_id = shot_id
        self.progress(
            "MOTION",
            f"Generating motion for {shot_id}",
            -1,
            scene_id=scene_id,
            shot_id=shot_id,
            take_id=take["id"],
        )

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
        self.shot_results[shot_id] = {
            "image": source_image,
            "video": final_vid,
            "identity_score": identity_score,
            "status": "final_review",
            "take_id": take["id"],
        }
        self._rebuild_review_clips()
        self._save_checkpoint()
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
        project = self._refresh_project_snapshot() or self.project
        _, shot, _ = self._find_shot(shot_id, project, scene_id)
        if not shot:
            return {"success": False, "error": "Shot not found"}
        if shot.get("approved_keyframe_take_id"):
            return self.generate_motion_take(scene_id, shot_id)
        return self.generate_keyframe_take(scene_id, shot_id)

    # ------------------------------------------------------------------
    # DIRECTOR'S CUT — Correction & Diagnosis
    # ------------------------------------------------------------------

    def diagnose_clip(self, shot_id: str, take_id: str = "") -> dict:
        """
        Run all quality analyzers on a clip and return scores + recommendations.
        """
        project = self._refresh_project_snapshot() or self.project
        scene, shot, shot_index = self._find_shot(shot_id, project)
        if not scene or not shot:
            return {"error": "Clip not found"}

        candidate = None
        if take_id:
            _, candidate = self._find_take(shot, take_id)
        if candidate is None:
            candidate = self._candidate_take(shot)
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
        image_path = candidate.get("path", "") if candidate.get("kind") == "keyframe" else self._resolve_take_path(
            shot,
            shot.get("approved_keyframe_take_id", ""),
        ) or (self._latest_take(shot, "keyframe_takes") or {}).get("path", "")

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
                prev_img = self._resolve_take_path(previous_shot, previous_shot.get("approved_keyframe_take_id", "")) or (
                    self._latest_take(previous_shot, "keyframe_takes") or {}
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
        project = self._refresh_project_snapshot() or self.project
        scene, shot, shot_index = self._find_shot(shot_id, project)
        if not scene or not shot:
            return {"success": False, "error": "Clip not found in review"}

        base_take = None
        if take_id:
            _, base_take = self._find_take(shot, take_id)
        if base_take is None:
            base_take = self._candidate_take(shot)
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
                audio_path = self._ensure_scene_audio(scene, [c for c in self.project["characters"] if c["id"] in chars])
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
            self._rebuild_review_clips()
            self._save_checkpoint()
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

    def proceed_to_assembly(self):
        """Resume pipeline from REVIEW stage to transitions + assembly."""
        project = self._refresh_project_snapshot() or self.project
        if not self._gate_satisfied("REVIEW", project):
            missing = [
                shot.get("id")
                for _, _, shot in self._all_shots(project)
                if not shot.get("approved_final_take_id")
            ]
            return {"success": False, "error": f"Final approvals missing for: {', '.join(missing)}"}
        self.progress("REVIEW_COMPLETE", "Director's Cut approved — proceeding to assembly", 88)
        self.resume()
        return {"success": True}

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

        project = self._refresh_project_snapshot() or self.project
        for scene, _shot_index, shot in self._all_shots(project):
            if self.cancelled:
                self.progress("CANCELLED", "Pipeline cancelled by user", 0)
                return None
            if shot.get("approved_keyframe_take_id"):
                continue
            result = self.generate_keyframe_take(scene["id"], shot["id"])
            if not result.get("success"):
                self.failed_shots.append(shot["id"])
                self.progress("SHOT_FAILED", result.get("error", "Keyframe generation failed"), 40, scene_id=scene["id"], shot_id=shot["id"])

        if not self._wait_for_gate("KEYFRAME_REVIEW", "Approve all keyframes to continue", 55):
            self.progress("CANCELLED", "Pipeline cancelled during keyframe review", 0)
            return None

        project = self._refresh_project_snapshot() or self.project
        for scene, _shot_index, shot in self._all_shots(project):
            if self.cancelled:
                self.progress("CANCELLED", "Pipeline cancelled by user", 0)
                return None
            if shot.get("approved_final_take_id"):
                continue
            result = self.generate_motion_take(scene["id"], shot["id"])
            if not result.get("success"):
                self.failed_shots.append(shot["id"])
                self.progress("SHOT_FAILED", result.get("error", "Motion generation failed"), 70, scene_id=scene["id"], shot_id=shot["id"])

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

    def generate_scene_preview(self, scene_id: str) -> Optional[str]:
        """Generate just one scene for preview purposes."""
        project = self._refresh_project_snapshot() or self.project
        scene = next((s for s in project["scenes"] if s["id"] == scene_id), None)
        if not scene:
            return None

        clips = self.scene_clips.get(scene_id, [])
        if not clips:
            clips = []
            for shot in scene.get("shots", []):
                final_path = self._resolve_take_path(shot, shot.get("approved_final_take_id", ""))
                if final_path and os.path.exists(final_path):
                    clips.append(final_path)
            if not clips:
                return None
            self.scene_clips[scene_id] = clips

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
