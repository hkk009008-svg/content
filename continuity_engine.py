"""
Cinema Production Tool — Continuity Engine
The core differentiator: ensures characters, locations, objects, and physics
remain consistent throughout the entire cinema production.

Subsystems:
1. CharacterContinuityTracker — multi-character identity + wardrobe persistence
2. LocationPersistence — per-location seeds + verbatim prompt fragments
3. PhysicsPromptEngineer — spatial, lighting, gravity consistency between shots
4. TemporalConsistencyManager — img2img chaining for consecutive shots
"""

import os
import numpy as np
from typing import Optional, List, Dict

from project_manager import get_character, get_location
from character_manager import (
    get_character_embedding, get_reference_image, get_multi_angle_refs,
    get_identity_anchor, IDENTITY_THRESHOLD, IDENTITY_THRESHOLD_LENIENT,
)
from location_manager import get_location_prompt, get_location_seed

try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except ImportError:
    DEEPFACE_AVAILABLE = False


# ---------------------------------------------------------------------------
# 1. Character Continuity Tracker
# ---------------------------------------------------------------------------

class CharacterContinuityTracker:
    """Tracks character identity, wardrobe, and spatial positions across scenes."""

    def __init__(self, project: dict):
        self.project = project
        self.characters = {c["id"]: c for c in project["characters"]}
        self.embeddings: dict[str, np.ndarray] = {}
        self.appearance_log: dict[str, dict] = {}  # char_id -> last known appearance

        # Pre-load embeddings
        for cid in self.characters:
            emb = get_character_embedding(project, cid)
            if emb is not None:
                self.embeddings[cid] = emb

    def build_character_prompt_fragment(
        self,
        char_id: str,
        spatial_position: str = "",
        scene_context: str = "",
    ) -> str:
        """
        Builds a detailed prompt fragment for a character that includes:
        - Physical description and traits
        - Wardrobe continuity from last appearance
        - Spatial position hints
        """
        char = self.characters.get(char_id)
        if not char:
            return ""

        parts = []

        # Core physical identity
        name = char.get("name", "character")
        traits = char.get("physical_traits", char.get("description", ""))
        parts.append(f"{name}: {traits}")

        # Wardrobe continuity — use last known appearance if available
        last_appearance = self.appearance_log.get(char_id, {})
        if last_appearance.get("wardrobe"):
            parts.append(f"wearing {last_appearance['wardrobe']}")

        # Spatial position
        if spatial_position:
            parts.append(f"positioned {spatial_position} in the frame")

        return ", ".join(parts)

    def log_appearance(self, char_id: str, wardrobe: str = "", position: str = ""):
        """Record what a character looked like in a scene for future continuity."""
        self.appearance_log[char_id] = {
            "wardrobe": wardrobe,
            "position": position,
        }

    def get_primary_character(self, characters_in_frame: List[str]) -> Optional[str]:
        """Determine which character gets PuLID face-locking (first in list)."""
        if characters_in_frame:
            return characters_in_frame[0]
        return None

    def get_reference_for_pulid(self, char_id: str) -> Optional[str]:
        """Get the canonical reference image path for PuLID injection."""
        return get_reference_image(self.project, char_id)

    def get_multi_angle_refs(self, char_id: str) -> List[str]:
        """Get all multi-angle reference images for Kling subject binding."""
        return get_multi_angle_refs(self.project, char_id)

    def validate_multi_identity(
        self,
        video_path: str,
        expected_char_ids: List[str],
        threshold: float = 0.55,
    ) -> dict:
        """
        Validates that all expected characters appear in the video.
        Extracts multiple frames, detects all faces, matches to expected characters.

        Returns: {
            "passed": bool,
            "results": {char_id: {"matched": bool, "similarity": float}}
        }
        """
        if not DEEPFACE_AVAILABLE or not expected_char_ids:
            return {"passed": True, "results": {}}

        import cv2

        # Extract 3 frames for robustness
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0:
            cap.release()
            return {"passed": False, "results": {}}

        frame_positions = [
            int(total_frames * 0.25),
            int(total_frames * 0.50),
            int(total_frames * 0.75),
        ]

        best_results = {cid: {"matched": False, "similarity": 0.0} for cid in expected_char_ids}

        for pos in frame_positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if not ret:
                continue

            temp_frame = f"_temp_val_frame_{pos}.jpg"
            cv2.imwrite(temp_frame, frame)

            try:
                # Detect all faces in frame
                faces = DeepFace.extract_faces(
                    img_path=temp_frame,
                    enforce_detection=False,
                )

                for face_data in faces:
                    # Compute embedding for this detected face
                    face_region = face_data.get("face", None)
                    if face_region is None:
                        continue

                    # Save face crop for embedding
                    face_img = (face_region * 255).astype(np.uint8) if face_region.max() <= 1 else face_region
                    temp_face = f"_temp_face_crop_{pos}.jpg"
                    cv2.imwrite(temp_face, cv2.cvtColor(face_img, cv2.COLOR_RGB2BGR))

                    try:
                        face_emb_list = DeepFace.represent(
                            img_path=temp_face,
                            model_name="GhostFaceNet",
                            enforce_detection=False,
                        )
                        if not face_emb_list:
                            continue
                        face_emb = np.array(face_emb_list[0]["embedding"])

                        # Compare against all expected characters
                        for cid in expected_char_ids:
                            ref_emb = self.embeddings.get(cid)
                            if ref_emb is None:
                                continue

                            # Cosine similarity
                            cos_sim = np.dot(face_emb, ref_emb) / (
                                np.linalg.norm(face_emb) * np.linalg.norm(ref_emb) + 1e-10
                            )
                            similarity = float((1 + cos_sim) / 2)  # Map to 0-1

                            if similarity > best_results[cid]["similarity"]:
                                best_results[cid]["similarity"] = similarity
                                best_results[cid]["matched"] = similarity >= threshold

                    except Exception:
                        pass
                    finally:
                        if os.path.exists(temp_face):
                            os.remove(temp_face)

            except Exception as e:
                print(f"   ⚠️ Face detection failed on frame {pos}: {e}")
            finally:
                if os.path.exists(temp_frame):
                    os.remove(temp_frame)

        cap.release()

        all_passed = all(r["matched"] for r in best_results.values())

        for cid, res in best_results.items():
            char_name = self.characters.get(cid, {}).get("name", cid)
            icon = "✅" if res["matched"] else "❌"
            print(f"      {icon} {char_name}: similarity={res['similarity']:.3f}")

        return {"passed": all_passed, "results": best_results}


# ---------------------------------------------------------------------------
# 2. Location Persistence
# ---------------------------------------------------------------------------

class LocationPersistence:
    """Manages location consistency via deterministic seeds and prompt fragments."""

    def __init__(self, project: dict):
        self.project = project
        self.locations = {l["id"]: l for l in project["locations"]}

    def get_seed(self, location_id: str) -> Optional[int]:
        return get_location_seed(self.project, location_id)

    def get_prompt(self, location_id: str) -> str:
        return get_location_prompt(self.project, location_id)


# ---------------------------------------------------------------------------
# 3. Physics Prompt Engineer
# ---------------------------------------------------------------------------

class PhysicsPromptEngineer:
    """
    Injects physics-aware constraints between consecutive shots to prevent
    spatial violations, teleportation, and lighting inconsistencies.
    """

    def __init__(self):
        self.last_shot_context: dict = {}

    def enforce_spatial_consistency(
        self,
        current_shot: dict,
        previous_shot: Optional[dict],
        characters_present: List[dict],
    ) -> str:
        """
        Generates physics constraint clauses to append to the image prompt.
        Ensures characters don't teleport, lighting stays consistent, etc.
        """
        constraints = []

        if previous_shot:
            constraints.append(
                "This shot continues directly from the previous moment in the same physical space"
            )

            prev_chars = previous_shot.get("characters_in_frame", [])
            curr_chars = current_shot.get("characters_in_frame", [])
            shared = set(prev_chars) & set(curr_chars)
            if shared:
                constraints.append(
                    "Characters maintain their spatial positions from the previous shot"
                )

            constraints.append(
                "Lighting direction and intensity remain exactly the same as the previous shot"
            )

            prev_camera = previous_shot.get("camera", "")
            curr_camera = current_shot.get("camera", "")
            if prev_camera and curr_camera:
                constraints.append(
                    f"Camera smoothly transitions from {prev_camera} to {curr_camera}"
                )

        constraints.append(
            "Obey real-world physics: gravity, reflections, shadows match light source direction, "
            "objects have weight and surface friction, fabric drapes naturally"
        )
        constraints.append(
            "Photorealistic with visible skin pores and subsurface scattering, "
            "natural film grain, volumetric atmospheric lighting, "
            "no AI artifacts, no smooth plastic skin, no over-saturated colors"
        )

        return ". ".join(constraints)

    def generate_motion_constraints(
        self,
        action: str,
        previous_action: str = "",
    ) -> str:
        """Ensure actions follow physical logic (can't walk before standing, etc.)."""
        constraints = []

        if previous_action and action:
            constraints.append(
                f"Action continuity: previously '{previous_action}', now '{action}' — "
                f"ensure smooth physical transition between these states"
            )

        return ". ".join(constraints) if constraints else ""


# ---------------------------------------------------------------------------
# 4. Temporal Consistency Manager
# ---------------------------------------------------------------------------

class TemporalConsistencyManager:
    """
    Manages img2img chaining between consecutive shots within a scene.
    Uses the previous shot's output as init image with reduced denoising
    to naturally preserve colors, composition, and spatial arrangement.
    """

    def __init__(self):
        self.last_generated_image: Optional[str] = None
        self.current_scene_id: Optional[str] = None

    def should_use_img2img(self, scene_id: str, shot_index: int) -> bool:
        """
        Returns True if this shot should use img2img from the previous shot.
        First shot of each scene uses text-to-image, subsequent shots chain.
        """
        if scene_id != self.current_scene_id:
            # New scene — reset chain
            self.current_scene_id = scene_id
            self.last_generated_image = None
            return False
        return self.last_generated_image is not None and shot_index > 0

    def get_init_image(self) -> Optional[str]:
        """Get the previous shot's generated image for img2img chaining."""
        if self.last_generated_image and os.path.exists(self.last_generated_image):
            return self.last_generated_image
        return None

    def get_denoise_strength(
        self,
        shot_index: int,
        previous_shot: dict = None,
        current_shot: dict = None,
        previous_scene: dict = None,
        current_scene: dict = None,
    ) -> float:
        """
        Context-aware denoising strength based on transition type.

        Transition types (from tightest to loosest):
        - Same location, consecutive shots: 0.30
        - Same location, after time skip: 0.40
        - Location change within scene: 0.50
        - First shot of new scene: 0.55
        - Fallback (shot_index based): 0.45 / 0.35
        """
        # First shot of a scene — maximum creative freedom
        if shot_index == 0 or self.last_generated_image is None:
            return 0.55

        # Check location continuity
        prev_loc = None
        curr_loc = None
        if previous_scene and current_scene:
            prev_loc = previous_scene.get("location_id")
            curr_loc = current_scene.get("location_id")
        elif previous_shot and current_shot:
            prev_loc = previous_shot.get("location_id")
            curr_loc = current_shot.get("location_id")

        if prev_loc and curr_loc and prev_loc != curr_loc:
            return 0.50  # Location change — keep character, new environment

        # Same location — tighter consistency
        if shot_index <= 1:
            return 0.40  # Early shots get slight creative room
        return 0.30  # Later shots are tightest

    def record_generated(self, image_path: str, scene_id: str):
        """Record the generated image for the next shot's img2img reference."""
        self.last_generated_image = image_path
        self.current_scene_id = scene_id

    def reset(self):
        """Reset for a new scene or fresh generation."""
        self.last_generated_image = None
        self.current_scene_id = None


# ---------------------------------------------------------------------------
# Main Continuity Engine — Orchestrates all subsystems
# ---------------------------------------------------------------------------

class ContinuityEngine:
    """
    Central continuity orchestrator that combines all subsystems to produce
    fully continuity-aware prompts for each shot in the production.
    """

    def __init__(self, project: dict):
        self.project = project
        self.character_tracker = CharacterContinuityTracker(project)
        self.location_persistence = LocationPersistence(project)
        self.physics_engineer = PhysicsPromptEngineer()
        self.temporal_manager = TemporalConsistencyManager()

        # Shared identity validator with rolling history for adaptive PuLID
        # Pass cache_dir so embeddings persist to disk across pipeline runs
        from identity_validator import IdentityValidator
        from project_manager import get_project_dir
        cache_dir = os.path.join(get_project_dir(project["id"]), "characters")
        self.identity_validator = IdentityValidator(
            embedding_cache=self.character_tracker.embeddings,
            cache_dir=cache_dir,
        )

    def enhance_shot_prompt(
        self,
        shot: dict,
        scene: dict,
        previous_shot: Optional[dict] = None,
        shot_index: int = 0,
    ) -> dict:
        """
        Takes a raw shot prompt from the scene decomposer and enhances it with:
        - Character identity fragments
        - Location prompt fragment
        - Physics consistency constraints
        - Temporal img2img configuration

        Returns the shot dict with enhanced 'prompt' and added 'continuity_config'.
        """
        enhanced = dict(shot)
        prompt_parts = []

        # 1. Original prompt from decomposer
        prompt_parts.append(shot.get("prompt", ""))

        # 2. Location persistence
        loc_id = scene.get("location_id", "")
        if loc_id:
            loc_prompt = self.location_persistence.get_prompt(loc_id)
            if loc_prompt:
                prompt_parts.append(loc_prompt)

        # 3. Character identity fragments
        chars_in_frame = shot.get("characters_in_frame", [])
        for i, cid in enumerate(chars_in_frame):
            position = ""
            if len(chars_in_frame) == 2:
                position = "on the left side" if i == 0 else "on the right side"
            elif len(chars_in_frame) >= 3:
                positions = ["on the left", "in the center", "on the right"]
                position = positions[min(i, 2)]

            char_fragment = self.character_tracker.build_character_prompt_fragment(
                cid, spatial_position=position, scene_context=scene.get("action", "")
            )
            if char_fragment:
                prompt_parts.append(char_fragment)

        # 4. Physics constraints
        physics = self.physics_engineer.enforce_spatial_consistency(
            shot, previous_shot, chars_in_frame
        )
        if physics:
            prompt_parts.append(physics)

        # Motion constraints from action continuity
        prev_action = previous_shot.get("action_context", "") if previous_shot else ""
        motion = self.physics_engineer.generate_motion_constraints(
            scene.get("action", ""), prev_action
        )
        if motion:
            prompt_parts.append(motion)

        # 5. Temporal consistency config
        scene_id = scene.get("id", "")
        use_img2img = self.temporal_manager.should_use_img2img(scene_id, shot_index)

        primary_char = self.character_tracker.get_primary_character(chars_in_frame)

        # Compute a deterministic scene seed — locked across ALL shots in this scene
        loc_seed = self.location_persistence.get_seed(loc_id) if loc_id else None
        scene_seed = loc_seed if loc_seed else hash(scene_id) % (2**31)

        # Classify shot type for adaptive thresholds and PuLID weights
        from workflow_selector import classify_shot_type, get_adaptive_pulid_weight
        from identity_types import get_threshold_for_shot
        shot_type = classify_shot_type(shot)
        identity_threshold = get_threshold_for_shot(shot_type, mode="standard")

        # Adaptive PuLID weight from rolling identity performance
        pulid_weight_override = None
        if primary_char:
            pulid_weight_override = get_adaptive_pulid_weight(
                shot_type, primary_char, self.identity_validator
            )

        # Context-aware denoise
        denoise = self.temporal_manager.get_denoise_strength(
            shot_index,
            previous_shot=previous_shot,
            current_shot=shot,
            current_scene=scene,
        ) if use_img2img else 1.0

        continuity_config = {
            "use_img2img": use_img2img,
            "init_image": self.temporal_manager.get_init_image() if use_img2img else None,
            "denoise_strength": denoise,
            "location_seed": loc_seed,
            "scene_seed": scene_seed,
            "primary_character": primary_char,
            "primary_reference": None,
            "multi_angle_refs": [],
            "identity_anchor": "",
            "identity_threshold": identity_threshold,
            "shot_type": shot_type,
            "pulid_weight_override": pulid_weight_override,
        }

        # Get PuLID reference + multi-angle refs + identity anchor for primary character
        if primary_char:
            continuity_config["primary_reference"] = (
                self.character_tracker.get_reference_for_pulid(primary_char)
            )
            continuity_config["multi_angle_refs"] = (
                self.character_tracker.get_multi_angle_refs(primary_char)
            )
            continuity_config["identity_anchor"] = (
                get_identity_anchor(self.project, primary_char)
            )

        # Assemble final prompt
        enhanced["prompt"] = ". ".join(filter(None, prompt_parts))
        enhanced["continuity_config"] = continuity_config

        return enhanced

    def record_shot_generated(self, image_path: str, scene_id: str):
        """Record generated image for temporal chaining."""
        self.temporal_manager.record_generated(image_path, scene_id)

    def validate_shot(
        self,
        video_path: str,
        expected_chars: List[str],
        threshold: float = None,
        shot_type: str = "medium",
        mode: str = "standard",
        attempt: int = 0,
        max_attempts: int = 3,
    ):
        """
        Validate character identity in generated video.
        Uses the shared IdentityValidator for adaptive thresholds and history tracking.
        Returns IdentityValidationResult (backward-compatible via .get()).
        """
        from identity_types import get_threshold_for_shot

        if threshold is None:
            threshold = get_threshold_for_shot(shot_type, mode, attempt, max_attempts)

        # Build character configs for the validator
        configs = []
        for cid in expected_chars:
            ref = get_reference_image(self.project, cid)
            char_data = self.character_tracker.characters.get(cid, {})
            name = char_data.get("name", cid)
            if ref:
                configs.append({"id": cid, "reference_image": ref, "name": name})

        return self.identity_validator.validate_video(
            video_path, configs,
            shot_type=shot_type,
            threshold=threshold,
            mode=mode,
            attempt=attempt,
            max_attempts=max_attempts,
        )

    def reset_scene(self):
        """Reset temporal state for a new scene."""
        self.temporal_manager.reset()
