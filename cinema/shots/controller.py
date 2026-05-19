"""ShotController — per-shot generation + correction state machine.

Migration Slice B from docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md.

The 6 operator-callable per-shot methods (generate_keyframe_take,
generate_motion_take, regenerate_shot, diagnose_clip, apply_correction,
generate_scene_preview) plus their immediate helpers (_find_shot,
_find_take, _take_output_path, _mutate_shot, _record_diagnostic,
_resolve_previous_approved_keyframe) live here.

Implementation choice
=====================

The class is delivered as a **mixin** rather than a standalone class
holding a CinemaPipeline reference. Reasons:

  - Zero body rewrites: every ``self.X`` reference in the moved
    methods continues to resolve correctly on a CinemaPipeline
    instance (the methods see the same ``self`` either way).

  - Identity preserved: ``CinemaPipeline.generate_keyframe_take is
    ShotControllerMixin.generate_keyframe_take`` evaluates True via
    MRO. The Python function objects are the same.

  - File-level separation: cinema_pipeline.py no longer carries
    these ~540 LOC; reviewers can read this file in isolation.

The trade-off: a standalone ``ShotController(project_dir, lifecycle)``
constructor isn't available yet. Slice E (driver rewire) is where the
controllers become truly composable. For now, the mixin pattern gets
us the file-level decomposition with minimal disruption.

State expected from the host class
==================================

The mixin references the following ``self.X`` attributes that
``CinemaPipeline.__init__`` is responsible for setting up:

  self.project, self.project_dir, self.temp_dir
  self.continuity (ContinuityEngine)
  self.director (ChiefDirector)
  self.ensemble (LLMEnsemble)
  self.vbench, self.quality_tracker, self.cost_tracker
  self.progress (callable)
  self.shot_results (dict)
  self.failed_shots (list)
  self.current_stage / current_scene_id / current_shot_id (str)

Plus the following methods provided by ReviewControllerMixin (Slice C)
or remaining in CinemaPipeline directly:

  self._refresh_project_snapshot, self._rebuild_review_clips,
  self._save_checkpoint, self._candidate_take, self._resolve_take_path
"""

from __future__ import annotations

import os
from typing import Optional

from project_manager import MutationResult, mutate_project, make_take
from llm.style_director import style_rules_to_prompt_suffix
from phase_c_assembly import generate_ai_broll
from phase_c_ffmpeg import generate_ai_video
from phase_c_vision import validate_identity


class ShotControllerMixin:
    """Mixin providing per-shot generation and correction methods.

    Designed to be mixed into ``cinema_pipeline.CinemaPipeline``. See
    the module docstring for the contract with the host class.
    """

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
        self._refresh_project_snapshot()
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
        return self._resolve_take_path(previous_shot, take_id)

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
