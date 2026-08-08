"""
Cinema Production Tool — Continuity Engine
The core differentiator: ensures characters, locations, objects, and physics
remain consistent throughout the entire cinema production.

Subsystems:
1. CharacterContinuityTracker — multi-character identity + wardrobe persistence
2. LocationPersistence — per-location seeds + verbatim prompt fragments
3. PhysicsPromptEngineer — spatial, lighting, gravity consistency between shots
4. Approved continuity references — explicit prior-keyframe conditioning
"""

import os
import numpy as np
from typing import Optional, List, Dict, Sequence

from domain.project_manager import get_character, get_location
from domain.character_manager import (
    get_object_reference_paths,
    get_character_embedding, get_reference_image, get_multi_angle_refs,
    get_identity_anchor, IDENTITY_THRESHOLD, IDENTITY_THRESHOLD_LENIENT,
)
from domain.location_manager import (
    get_location_prompt, get_location_reference_paths, get_location_seed,
)

try:
    from identity.tf_preload import preload_tensorflow
    preload_tensorflow()  # MUST precede the deepface import
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except ImportError:
    DEEPFACE_AVAILABLE = False


# Slot 0 of a reference list carries a SEMANTIC ROLE downstream and nothing
# else establishes it. `phase_c_ffmpeg.py` iterates `multi_angle_refs[:N]` with
# no canonical prepended, and uploads `valid_refs[0]` as Kling's FRONTAL IMAGE.
# Before this normalisation, slot 0 was whatever the character record happened
# to list first — on this project, a left profile, so Kling was told a profile
# was the frontal view.
#
# The rule lives in the PURE module so `compose_shot_reference_set` can apply
# the identical ordering without importing this one (numpy, DeepFace, project
# I/O). Re-exported here because every existing caller and test imports it from
# this module, and two copies of an ordering rule is how they drift apart.
from domain.reference_set import canonical_first  # noqa: E402  (re-export)


# ---------------------------------------------------------------------------
# 1. Character Continuity Tracker
# ---------------------------------------------------------------------------

class CharacterContinuityTracker:
    """Tracks character identity, wardrobe, and spatial positions across scenes."""

    def __init__(self, project: dict):
        # P1-3 migration template (S10) — value-preserving variant.
        # Validate at boundary + typed iteration for the .id key extraction.
        # Values stay as ORIGINAL dict references from project["characters"][i]
        # (NOT model_dump output) — preserves the implicit contract that
        # mutating project["characters"][0]["name"] is visible through
        # self.characters[char_id]["name"]. Consumer sites
        # (`build_character_prompt_fragment` at line 75 + `validate_continuity_for_scene`
        # at line 221; `ContinuityEngine.validate_shot` at line 608 cross-class)
        # continue to do dict-attribute access (`.get("name", ...)`); migrating
        # those to typed Character access is a separate cycle-11+ slice.
        # See docs/MIGRATION-PATTERN-pydantic-caller.md + part 9
        # (f8cd45f) for the index-by-typed-iteration pattern, + part 10
        # (1bc9263) which extended this variant to external-writer sites.
        from domain.models import Project as _Project
        self.project = project
        project_typed = _Project.model_validate(project)
        self.characters = {c.id: project["characters"][i] for i, c in enumerate(project_typed.characters)}
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
        Builds a continuity-safe prompt fragment for a character.
        Identity remains bound to reference images and embeddings; this fragment
        only reinforces safe continuity cues such as wardrobe, approved
        reference usage, and spatial position.
        """
        char = self.characters.get(char_id)
        if not char:
            return ""

        parts = []

        name = char.get("name", "character")
        parts.append(f"{name} must match the approved reference identity")

        # Wardrobe continuity — use last known appearance if available
        last_appearance = self.appearance_log.get(char_id, {})
        if last_appearance.get("wardrobe"):
            parts.append(f"wardrobe continuity: {last_appearance['wardrobe']}")

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
        """Determine which character owns the primary identity reference."""
        if characters_in_frame:
            return characters_in_frame[0]
        return None

    def get_reference_image(self, char_id: str) -> Optional[str]:
        """Get the canonical approved identity-reference image path."""
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
        from identity.validator import cv2_single_thread, represent_deterministic

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
                # Detect all faces in frame (determinism: serialize OpenCV align)
                with cv2_single_thread():
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
                        # Guard + EMBED_MODEL dispatch live inside the shared
                        # chokepoint (identity.validator.represent_deterministic);
                        # AdaFace is not a DeepFace built-in, so a direct
                        # DeepFace.represent here would crash under it.
                        face_emb_list = represent_deterministic(temp_face)
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

                    except (ValueError, RuntimeError) as e_emb:
                        print(f"   [CONTINUITY] Embedding comparison failed: {e_emb}")
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
        # P1-3 migration template (S10) — value-preserving variant, parallel
        # to CharacterContinuityTracker.__init__ above. self.locations is
        # populated but no INTERNAL consumer reads it within this class —
        # only external code in cinema_pipeline.py:466 (within
        # _refresh_project_snapshot) reassigns it on project reload. The
        # validation here is the value-add: malformed project input fails
        # at the boundary (raises in STRICT mode).
        from domain.models import Project as _Project
        self.project = project
        project_typed = _Project.model_validate(project)
        self.locations = {l.id: project["locations"][i] for i, l in enumerate(project_typed.locations)}

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
                    f"Camera cuts from {prev_camera} to {curr_camera} — hard cut, no dissolve"
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
        # Shared provider-neutral identity validator. Pass cache_dir so
        # embeddings persist to disk across pipeline runs.
        from identity import make_validator
        from domain.project_manager import get_project_dir
        cache_dir = os.path.join(get_project_dir(project["id"]), "characters")
        self.identity_validator = make_validator(
            embedding_cache=self.character_tracker.embeddings,
            cache_dir=cache_dir,
        )

    def enhance_shot_prompt(
        self,
        shot: dict,
        scene: dict,
        previous_shot: Optional[dict] = None,
        shot_index: int = 0,
        continuity_reference_path: Optional[str] = None,
    ) -> dict:
        """
        Takes a raw shot prompt from the scene decomposer and enhances it with:
        - Character identity fragments
        - Location prompt fragment
        - Physics consistency constraints
        - Approved continuity-reference configuration

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

        continuity_notes = shot.get("continuity_constraints", "")
        if continuity_notes:
            prompt_parts.append(f"Continuity note: {continuity_notes}")

        # 5. Approved continuity reference. Only a project-owned, on-disk
        # approved keyframe may enter the hash-bound local reference workflow.
        scene_id = scene.get("id", "")
        anchor_image = (
            continuity_reference_path
            if continuity_reference_path and os.path.exists(continuity_reference_path)
            else None
        )

        primary_char = self.character_tracker.get_primary_character(chars_in_frame)

        # Compute a deterministic scene seed — locked across ALL shots in this scene
        loc_seed = self.location_persistence.get_seed(loc_id) if loc_id else None
        scene_seed = loc_seed if loc_seed is not None else _stable_scene_seed(scene_id)

        # Classify shot type for provider-neutral identity thresholds.
        from workflow_selector import classify_shot_type
        from identity.types import get_threshold_for_shot
        shot_type = classify_shot_type(shot)
        identity_threshold = get_threshold_for_shot(shot_type, mode="standard")

        continuity_config = {
            "continuity_reference": anchor_image,
            "location_seed": loc_seed,
            "scene_seed": scene_seed,
            "primary_character": primary_char,
            "primary_reference": None,
            "multi_angle_refs": [],
            "identity_anchor": "",
            "identity_threshold": identity_threshold,
            "shot_type": shot_type,
            "negative_constraints": shot.get("negative_constraints", ""),
            "secondary_chars": [],
        }

        # Get the approved primary and multi-angle reference set.
        if primary_char:
            continuity_config["primary_reference"] = (
                self.character_tracker.get_reference_image(primary_char)
            )
            continuity_config["multi_angle_refs"] = canonical_first(
                continuity_config["primary_reference"],
                self.character_tracker.get_multi_angle_refs(primary_char),
            )
            continuity_config["identity_anchor"] = (
                get_identity_anchor(self.project, primary_char)
            )

        # P1-1: per-character identity assets for chars beyond the primary.
        # Same existence guard as validation (validate_shot's `if ref:` skip of
        # unregistered chars) — generation mirrors the skip, never fails on it.
        for cid in chars_in_frame[1:]:
            ref = self.character_tracker.get_reference_image(cid)
            if not ref:
                continue
            continuity_config["secondary_chars"].append({
                "char_id": cid,
                "reference": ref,
                "multi_angle_refs": canonical_first(
                    ref, self.character_tracker.get_multi_angle_refs(cid)
                ),
                "identity_anchor": get_identity_anchor(self.project, cid),
            })

        # Product references, which reached NO provider before this. The only
        # generation-path reader of project["objects"] serialises the record
        # into a PROMPT (llm/prompt_optimizer.py:768-779) — brand, material,
        # surface, texture_anchor, scale — so a logo was described in words and
        # never shown. `make_object`'s own docstring claims "reference-image
        # conditioning"; no resolver existed to deliver it.
        #
        # Carried on the config but NOT merged into the character reference
        # list. Slots are scarce (4 on the Veo/fal path, 6-9 on Kontext) and
        # every one an object takes is one a face loses. Which subject wins a
        # contested slot is a real trade with no measurement behind it yet, so
        # the data is made available and the policy is left to a deliberate
        # decision rather than smuggled in as a side effect of plumbing.
        object_refs: Dict[str, List[str]] = {}
        for object_id in (shot.get("objects_in_frame") or []):
            paths = get_object_reference_paths(self.project, object_id)
            if paths:
                object_refs[object_id] = paths
        continuity_config["object_refs"] = object_refs
        continuity_config["primary_object"] = shot.get("primary_object", "")

        # Location plates. `get_location_reference` had ZERO non-test callers:
        # a user uploaded plates through web_server.py:4198-4234, they were
        # stored and path-migrated correctly, and no provider ever saw one. A
        # location is the only subject every shot in a scene shares, so drift
        # there is what makes one scene look like three different rooms.
        continuity_config["location_refs"] = (
            get_location_reference_paths(self.project, loc_id) if loc_id else []
        )

        # Assemble final prompt
        enhanced["prompt"] = ". ".join(filter(None, prompt_parts))
        enhanced["continuity_config"] = continuity_config

        return enhanced

    def validate_shot(
        self,
        video_path: str,
        expected_chars: List[str],
        threshold: float = None,
        shot_type: str = "medium",
        mode: str = "standard",
        attempt: int = 0,
        max_attempts: int = 3,
        *,
        cost_tracker=None,
        video_id: str = "",
        shot_id: str = "",
    ):
        """
        Validate character identity in generated video.
        Uses the shared IdentityValidator for adaptive thresholds and history tracking.
        Returns IdentityValidationResult (backward-compatible via .get()).
        """
        from identity.types import get_threshold_for_shot

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
            cost_tracker=cost_tracker,
            video_id=video_id,
            shot_id=shot_id,
        )


def _stable_scene_seed(scene_id: str) -> int:
    """Return a process- and platform-stable 31-bit seed for a scene ID."""
    from hashlib import sha256

    digest = sha256(scene_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], byteorder="big", signed=False) & 0x7FFFFFFF
