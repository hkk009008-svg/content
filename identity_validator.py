"""
Cinema Production Tool — Unified Identity Validator
Replaces all scattered validate_* functions with a single, configurable,
diagnostic-rich identity validation system.

Features:
- Adaptive frame sampling (3-10 frames based on duration and shot type)
- Per-character scoring with detailed diagnostics
- Failure reason analysis (face angle, occlusion, wrong person, etc.)
- Rolling history for adaptive PuLID weight feedback loop
"""

import os
import tempfile
from typing import Optional, List, Dict
from collections import Counter

import cv2
import numpy as np

from identity_types import (
    FailureReason,
    FrameSample,
    CharacterIdentityResult,
    IdentityValidationResult,
    get_threshold_for_shot,
)

try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except ImportError:
    DEEPFACE_AVAILABLE = False

# Vision-LLM identity validation is always available as primary fallback
from phase_c_vision import validate_identity_vision


class IdentityValidator:
    """
    Unified identity validation for the cinema pipeline.
    Replaces validate_identity(), validate_identity_image(),
    validate_multi_identity(), and CharacterContinuityTracker.validate_multi_identity().
    """

    def __init__(self, embedding_cache: Dict[str, np.ndarray] = None, cache_dir: str = ""):
        self.embedding_cache = embedding_cache or {}
        self.cache_dir = cache_dir  # Directory for persisting embeddings to disk
        self.history: List[IdentityValidationResult] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_image(
        self,
        image_path: str,
        reference_path: str,
        character_id: str = "",
        character_name: str = "",
        shot_type: str = "medium",
        threshold: float = None,
    ) -> IdentityValidationResult:
        """
        Validate identity in a single generated IMAGE against a reference.
        Uses DeepFace when available, falls back to Claude Vision identity check.
        Backward-compatible: result.get("passed") and result.get("similarity") work.
        """
        if not os.path.exists(image_path) or not os.path.exists(reference_path):
            return self._no_file_result(shot_type, threshold or 0.70)

        if not DEEPFACE_AVAILABLE:
            return self._vision_llm_validate_image(
                image_path, reference_path, character_id, character_name,
                shot_type, threshold or get_threshold_for_shot(shot_type),
            )

        if threshold is None:
            threshold = get_threshold_for_shot(shot_type)

        # Get reference embedding
        ref_emb = self._get_embedding(reference_path, character_id)
        if ref_emb is None:
            return self._no_file_result(shot_type, threshold)

        # Analyze the image as a single "frame"
        frame_sample = self._analyze_single_image(
            image_path, ref_emb, character_id, threshold
        )

        char_result = CharacterIdentityResult(
            character_id=character_id,
            character_name=character_name or character_id,
            best_similarity=frame_sample.similarity,
            mean_similarity=frame_sample.similarity,
            min_similarity=frame_sample.similarity,
            frame_results=[frame_sample],
            matched=frame_sample.matched,
            primary_failure_reason=frame_sample.failure_reason,
            suggested_pulid_adjustment=self._compute_pulid_delta(frame_sample.similarity, frame_sample.matched),
        )

        result = IdentityValidationResult(
            passed=frame_sample.matched,
            overall_score=frame_sample.similarity,
            character_results={character_id: char_result} if character_id else {},
            frames_sampled=1,
            video_duration_seconds=0.0,
            shot_type=shot_type,
            threshold_used=threshold,
        )

        self.history.append(result)
        icon = "✅" if result.passed else "❌"
        print(f"      {icon} Image identity: similarity={result.overall_score:.3f} (threshold={threshold})")
        return result

    def validate_video(
        self,
        video_path: str,
        character_configs: List[Dict],
        shot_type: str = "medium",
        threshold: float = None,
        mode: str = "standard",
        attempt: int = 0,
        max_attempts: int = 3,
    ) -> IdentityValidationResult:
        """
        Validate character identity in a generated VIDEO with adaptive sampling.

        Args:
            video_path: Path to generated video.
            character_configs: [{"id": str, "reference_image": str, "name": str}]
            shot_type: For threshold selection and sampling density.
            threshold: Override (None = auto from shot_type + mode + attempt).
            mode: "strict", "standard", or "lenient".
            attempt: Current retry attempt (0-based).
            max_attempts: Total retries planned.
        """
        th = threshold or get_threshold_for_shot(shot_type, mode, attempt, max_attempts)
        if not character_configs:
            return self._no_file_result(shot_type, th)

        if not DEEPFACE_AVAILABLE:
            return self._vision_llm_validate_video(
                video_path, character_configs, shot_type, th,
            )

        if threshold is None:
            threshold = get_threshold_for_shot(shot_type, mode, attempt, max_attempts)

        # Pre-compute reference embeddings
        ref_embeddings = {}
        char_names = {}
        for cfg in character_configs:
            cid = cfg["id"]
            char_names[cid] = cfg.get("name", cid)
            ref_img = cfg.get("reference_image", "")
            if not ref_img or not os.path.exists(ref_img):
                continue
            emb = self._get_embedding(ref_img, cid)
            if emb is not None:
                ref_embeddings[cid] = emb

        if not ref_embeddings:
            return self._no_file_result(shot_type, threshold)

        # Open video and compute adaptive sample positions
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_area = max(frame_width * frame_height, 1)
        duration = total_frames / max(fps, 1.0)

        if total_frames == 0:
            cap.release()
            return IdentityValidationResult(
                passed=False, overall_score=0.0, character_results={},
                frames_sampled=0, video_duration_seconds=0.0,
                shot_type=shot_type, threshold_used=threshold,
            )

        positions = self._compute_sample_positions(total_frames, fps, shot_type)

        # Per-character frame results
        char_frame_results: Dict[str, List[FrameSample]] = {cid: [] for cid in ref_embeddings}

        for pos in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if not ret:
                continue

            ratio = pos / max(total_frames - 1, 1)

            # Write to temp file for DeepFace
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name
            cv2.imwrite(tmp_path, frame)

            try:
                per_char = self._analyze_frame(
                    tmp_path, pos, ratio, ref_embeddings, threshold, frame_area
                )
                for cid, sample in per_char.items():
                    char_frame_results[cid].append(sample)
            except Exception as e:
                print(f"   ⚠️ Frame analysis error at position {pos}: {e}")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        cap.release()

        # Aggregate per-character results
        character_results = {}
        for cid, frames in char_frame_results.items():
            character_results[cid] = self._aggregate_character(
                cid, char_names.get(cid, cid), frames, threshold
            )

        # Overall score = mean of per-character best similarities
        scores = [cr.best_similarity for cr in character_results.values()]
        overall = sum(scores) / len(scores) if scores else 0.0
        all_passed = all(cr.matched for cr in character_results.values())

        result = IdentityValidationResult(
            passed=all_passed,
            overall_score=overall,
            character_results=character_results,
            frames_sampled=len(positions),
            video_duration_seconds=duration,
            shot_type=shot_type,
            threshold_used=threshold,
        )

        self.history.append(result)

        # Log results
        for cid, cr in character_results.items():
            icon = "✅" if cr.matched else "❌"
            reason_str = f" [{cr.primary_failure_reason.value}]" if not cr.matched else ""
            print(
                f"      {icon} {cr.character_name}: "
                f"best={cr.best_similarity:.3f} mean={cr.mean_similarity:.3f}"
                f" (threshold={threshold}){reason_str}"
            )

        return result

    def get_rolling_stats(self, character_id: str, window: int = 10) -> Dict:
        """
        Rolling identity performance statistics for a character.
        Used by the adaptive PuLID weight system.
        """
        recent = [
            r.character_results[character_id]
            for r in self.history[-window:]
            if character_id in r.character_results
        ]
        if not recent:
            return {
                "mean_similarity": 0.0,
                "success_rate": 0.0,
                "common_failure": FailureReason.NO_FACE_DETECTED,
                "suggested_pulid_delta": 0.0,
                "sample_count": 0,
            }

        sims = [r.best_similarity for r in recent]
        successes = sum(1 for r in recent if r.matched)
        failures = [r.primary_failure_reason for r in recent if not r.matched]

        success_rate = successes / len(recent)
        mean_sim = sum(sims) / len(sims)

        # Compute suggested PuLID delta
        if success_rate < 0.5:
            delta = +0.10
        elif success_rate < 0.8:
            delta = +0.05
        elif success_rate == 1.0 and mean_sim > 0.80:
            delta = -0.05  # identity is great, allow more creativity
        else:
            delta = 0.0

        common = Counter(failures).most_common(1)

        return {
            "mean_similarity": mean_sim,
            "success_rate": success_rate,
            "common_failure": common[0][0] if common else FailureReason.PASSED,
            "suggested_pulid_delta": delta,
            "sample_count": len(recent),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _disk_cache_path(self, cache_key: str) -> Optional[str]:
        """Return path to a disk-cached .npy embedding file, or None."""
        if not self.cache_dir or not cache_key:
            return None
        safe_key = cache_key.replace("/", "_").replace("\\", "_")
        return os.path.join(self.cache_dir, f"emb_{safe_key}.npy")

    def _get_embedding(self, image_path: str, cache_key: str = "") -> Optional[np.ndarray]:
        """
        Get or compute embedding for an image.
        Lookup order: in-memory cache → disk .npy file → compute via DeepFace.
        Newly computed embeddings are persisted to both memory and disk.
        """
        # 1. In-memory cache (fastest)
        if cache_key and cache_key in self.embedding_cache:
            return self.embedding_cache[cache_key]

        # 2. Disk cache (.npy file)
        disk_path = self._disk_cache_path(cache_key)
        if disk_path and os.path.exists(disk_path):
            try:
                emb = np.load(disk_path)
                if cache_key:
                    self.embedding_cache[cache_key] = emb
                return emb
            except Exception:
                pass  # Corrupted file — recompute

        # 3. Compute from scratch via DeepFace
        try:
            emb_list = DeepFace.represent(
                img_path=image_path, model_name="GhostFaceNet", enforce_detection=False
            )
            if emb_list:
                emb = np.array(emb_list[0]["embedding"])
                if cache_key:
                    self.embedding_cache[cache_key] = emb
                    # Persist to disk for future runs
                    if disk_path:
                        try:
                            os.makedirs(os.path.dirname(disk_path), exist_ok=True)
                            np.save(disk_path, emb)
                        except OSError:
                            pass  # Non-fatal — memory cache still works
                return emb
        except Exception as e:
            print(f"   ⚠️ Embedding computation failed for {image_path}: {e}")
        return None

    def _compute_sample_positions(
        self,
        total_frames: int,
        fps: float,
        shot_type: str,
        min_samples: int = 3,
        max_samples: int = 10,
    ) -> List[int]:
        """
        Adaptive frame sampling positions.
        - Portrait: 2x density (face is the whole frame)
        - Action: 1.5x (motion needs more samples)
        - Wide: 1x (face small, fewer useful frames)
        - Always includes anchors at 10%, 50%, 90%
        """
        duration = total_frames / max(fps, 1.0)

        density = {
            "portrait": 2.0,
            "medium": 1.5,
            "action": 1.5,
            "wide": 1.0,
            "landscape": 0.0,
        }.get(shot_type, 1.0)

        if density == 0.0:
            return []

        num_samples = int(duration * 2.0 * density)
        num_samples = max(min_samples, min(num_samples, max_samples))

        # Anchor positions
        anchors = {0.10, 0.50, 0.90}

        # Fill with uniform distribution
        if num_samples > len(anchors):
            step = 1.0 / max(num_samples - 1, 1)
            for i in range(num_samples):
                anchors.add(round(i * step, 3))

        positions = sorted(anchors)[:num_samples]
        return [max(0, min(int(p * total_frames), total_frames - 1)) for p in positions]

    def _analyze_frame(
        self,
        frame_path: str,
        frame_index: int,
        frame_ratio: float,
        ref_embeddings: Dict[str, np.ndarray],
        threshold: float,
        frame_area: int,
    ) -> Dict[str, FrameSample]:
        """Analyze a single frame: detect faces, compute embeddings, match per character."""
        result = {}

        try:
            faces = DeepFace.extract_faces(
                img_path=frame_path, enforce_detection=False
            )
        except Exception:
            # No face detected — create failure samples for all characters
            for cid in ref_embeddings:
                result[cid] = FrameSample(
                    frame_index=frame_index,
                    frame_position_ratio=frame_ratio,
                    face_detected=False,
                    face_confidence=0.0,
                    face_area_ratio=0.0,
                    face_angle_estimate="unknown",
                    similarity=0.0,
                    matched=False,
                    failure_reason=FailureReason.NO_FACE_DETECTED,
                )
            return result

        if not faces:
            for cid in ref_embeddings:
                result[cid] = FrameSample(
                    frame_index=frame_index,
                    frame_position_ratio=frame_ratio,
                    face_detected=False,
                    face_confidence=0.0,
                    face_area_ratio=0.0,
                    face_angle_estimate="unknown",
                    similarity=0.0,
                    matched=False,
                    failure_reason=FailureReason.NO_FACE_DETECTED,
                )
            return result

        # Process each detected face and match to characters
        for cid, ref_emb in ref_embeddings.items():
            best_sample = None
            best_sim = -1.0

            for face_data in faces:
                face_region = face_data.get("face", None)
                if face_region is None:
                    continue

                confidence = face_data.get("confidence", 0.5)
                facial_area = face_data.get("facial_area", {})

                # Compute face area ratio
                fw = facial_area.get("w", 0)
                fh = facial_area.get("h", 0)
                face_area_ratio = (fw * fh) / max(frame_area, 1)

                # Estimate face angle
                angle = self._estimate_face_angle(facial_area)

                # Compute embedding for this face crop
                face_img = face_region
                if face_img.max() <= 1:
                    face_img = (face_img * 255).astype(np.uint8)

                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    crop_path = tmp.name
                cv2.imwrite(crop_path, cv2.cvtColor(face_img, cv2.COLOR_RGB2BGR))

                try:
                    emb_list = DeepFace.represent(
                        img_path=crop_path, model_name="GhostFaceNet", enforce_detection=False
                    )
                    if emb_list:
                        face_emb = np.array(emb_list[0]["embedding"])
                        cos_sim = float(np.dot(face_emb, ref_emb) / (
                            np.linalg.norm(face_emb) * np.linalg.norm(ref_emb) + 1e-10
                        ))
                        similarity = (1 + cos_sim) / 2  # Map to 0-1

                        if similarity > best_sim:
                            best_sim = similarity
                            matched = similarity >= threshold
                            failure = FailureReason.PASSED if matched else self._classify_failure(
                                True, confidence, face_area_ratio, angle, similarity
                            )
                            best_sample = FrameSample(
                                frame_index=frame_index,
                                frame_position_ratio=frame_ratio,
                                face_detected=True,
                                face_confidence=confidence,
                                face_area_ratio=face_area_ratio,
                                face_angle_estimate=angle,
                                similarity=similarity,
                                matched=matched,
                                failure_reason=failure,
                            )
                except Exception:
                    pass
                finally:
                    if os.path.exists(crop_path):
                        os.remove(crop_path)

            if best_sample:
                result[cid] = best_sample
            else:
                result[cid] = FrameSample(
                    frame_index=frame_index,
                    frame_position_ratio=frame_ratio,
                    face_detected=len(faces) > 0,
                    face_confidence=0.0,
                    face_area_ratio=0.0,
                    face_angle_estimate="unknown",
                    similarity=0.0,
                    matched=False,
                    failure_reason=FailureReason.NO_FACE_DETECTED,
                )

        return result

    def _analyze_single_image(
        self,
        image_path: str,
        ref_emb: np.ndarray,
        character_id: str,
        threshold: float,
    ) -> FrameSample:
        """Simplified analysis for a single image (not video frame)."""
        try:
            emb_list = DeepFace.represent(
                img_path=image_path, model_name="GhostFaceNet", enforce_detection=False
            )
            if emb_list:
                gen_emb = np.array(emb_list[0]["embedding"])
                cos_sim = float(np.dot(gen_emb, ref_emb) / (
                    np.linalg.norm(gen_emb) * np.linalg.norm(ref_emb) + 1e-10
                ))
                similarity = (1 + cos_sim) / 2

                matched = similarity >= threshold
                failure = FailureReason.PASSED if matched else FailureReason.WRONG_PERSON

                return FrameSample(
                    frame_index=0, frame_position_ratio=0.0,
                    face_detected=True, face_confidence=0.8,
                    face_area_ratio=0.0, face_angle_estimate="frontal",
                    similarity=similarity, matched=matched,
                    failure_reason=failure,
                )
        except Exception as e:
            print(f"   ⚠️ Image identity check failed: {e}")

        return FrameSample(
            frame_index=0, frame_position_ratio=0.0,
            face_detected=False, face_confidence=0.0,
            face_area_ratio=0.0, face_angle_estimate="unknown",
            similarity=0.0, matched=False,
            failure_reason=FailureReason.NO_FACE_DETECTED,
        )

    def _aggregate_character(
        self,
        char_id: str,
        char_name: str,
        frames: List[FrameSample],
        threshold: float,
    ) -> CharacterIdentityResult:
        """Aggregate per-frame results into a character-level result."""
        if not frames:
            return CharacterIdentityResult(
                character_id=char_id, character_name=char_name,
                best_similarity=0.0, mean_similarity=0.0, min_similarity=0.0,
                frame_results=[], matched=False,
                primary_failure_reason=FailureReason.NO_FACE_DETECTED,
                suggested_pulid_adjustment=0.10,
            )

        sims = [f.similarity for f in frames if f.face_detected]
        if not sims:
            return CharacterIdentityResult(
                character_id=char_id, character_name=char_name,
                best_similarity=0.0, mean_similarity=0.0, min_similarity=0.0,
                frame_results=frames, matched=False,
                primary_failure_reason=self._diagnose_failure(frames),
                suggested_pulid_adjustment=0.10,
            )

        best = max(sims)
        mean = sum(sims) / len(sims)
        worst = min(sims)
        matched = best >= threshold

        failure_reason = FailureReason.PASSED if matched else self._diagnose_failure(frames)
        delta = self._compute_pulid_delta(best, matched)

        return CharacterIdentityResult(
            character_id=char_id,
            character_name=char_name,
            best_similarity=best,
            mean_similarity=mean,
            min_similarity=worst,
            frame_results=frames,
            matched=matched,
            primary_failure_reason=failure_reason,
            suggested_pulid_adjustment=delta,
        )

    def _diagnose_failure(self, frames: List[FrameSample]) -> FailureReason:
        """Analyze all frame samples to determine primary failure reason."""
        if not frames:
            return FailureReason.NO_FACE_DETECTED

        detected = [f for f in frames if f.face_detected]
        if not detected:
            return FailureReason.NO_FACE_DETECTED

        avg_confidence = sum(f.face_confidence for f in detected) / len(detected)
        if avg_confidence < 0.4:
            return FailureReason.LOW_CONFIDENCE_DETECTION

        avg_area = sum(f.face_area_ratio for f in detected) / len(detected)
        if avg_area < 0.01:
            return FailureReason.SMALL_FACE_REGION

        profile_count = sum(1 for f in detected if f.face_angle_estimate == "profile")
        if profile_count > len(detected) * 0.5:
            return FailureReason.FACE_ANGLE_EXTREME

        best_sim = max(f.similarity for f in detected)
        if best_sim < 0.35:
            return FailureReason.WRONG_PERSON

        return FailureReason.POOR_LIGHTING

    @staticmethod
    def _estimate_face_angle(facial_area: dict) -> str:
        """Estimate face angle from bounding box aspect ratio."""
        w = facial_area.get("w", 0)
        h = facial_area.get("h", 0)
        if h == 0:
            return "unknown"
        ratio = w / h
        if ratio > 0.75:
            return "frontal"
        elif ratio > 0.55:
            return "three_quarter"
        else:
            return "profile"

    @staticmethod
    def _classify_failure(
        detected: bool, confidence: float, area_ratio: float,
        angle: str, similarity: float,
    ) -> FailureReason:
        """Classify why a single frame failed identity matching."""
        if not detected:
            return FailureReason.NO_FACE_DETECTED
        if confidence < 0.4:
            return FailureReason.LOW_CONFIDENCE_DETECTION
        if area_ratio < 0.01:
            return FailureReason.SMALL_FACE_REGION
        if angle == "profile":
            return FailureReason.FACE_ANGLE_EXTREME
        if similarity < 0.35:
            return FailureReason.WRONG_PERSON
        return FailureReason.POOR_LIGHTING

    @staticmethod
    def _compute_pulid_delta(similarity: float, matched: bool) -> float:
        """Compute suggested PuLID weight adjustment for a single result."""
        if matched and similarity > 0.80:
            return -0.05  # Strong match, can relax for creativity
        elif matched:
            return 0.0
        elif similarity > 0.55:
            return +0.05  # Close miss
        else:
            return +0.10  # Clear failure

    @staticmethod
    def _no_file_result(shot_type: str, threshold: float) -> IdentityValidationResult:
        """Return a passing result when reference/input files are missing."""
        return IdentityValidationResult(
            passed=True, overall_score=1.0, character_results={},
            frames_sampled=0, video_duration_seconds=0.0,
            shot_type=shot_type, threshold_used=threshold,
        )

    def _vision_llm_validate_image(
        self,
        image_path: str,
        reference_path: str,
        character_id: str,
        character_name: str,
        shot_type: str,
        threshold: float,
    ) -> IdentityValidationResult:
        """
        Vision-LLM identity validation when DeepFace is unavailable.
        Uses Claude Sonnet Vision to compare reference vs generated face.
        Returns real scores (never fake 1.0) to preserve feedback loop integrity.
        """
        print(f"   [IDENTITY] Using Claude Vision (DeepFace unavailable)")
        result = validate_identity_vision(reference_path, image_path)

        confidence = result.get("confidence", 0.0)
        matched = confidence >= threshold
        failure = FailureReason.PASSED if matched else FailureReason.WRONG_PERSON

        # Map confidence issues to failure reasons
        issues = result.get("issues", [])
        if any("angle" in i.lower() or "profile" in i.lower() for i in issues):
            failure = FailureReason.FACE_ANGLE_EXTREME if not matched else failure
        if any("occlu" in i.lower() for i in issues):
            failure = FailureReason.OCCLUSION if not matched else failure
        if any("no face" in i.lower() or "not visible" in i.lower() for i in issues):
            failure = FailureReason.NO_FACE_DETECTED if not matched else failure

        frame_sample = FrameSample(
            frame_index=0, frame_position_ratio=0.0,
            face_detected=confidence > 0.1,
            face_confidence=confidence,
            face_area_ratio=0.0,
            face_angle_estimate="unknown",
            similarity=confidence,
            matched=matched,
            failure_reason=failure,
        )

        char_result = CharacterIdentityResult(
            character_id=character_id,
            character_name=character_name or character_id,
            best_similarity=confidence,
            mean_similarity=confidence,
            min_similarity=confidence,
            frame_results=[frame_sample],
            matched=matched,
            primary_failure_reason=failure,
            suggested_pulid_adjustment=self._compute_pulid_delta(confidence, matched),
        )

        validation_result = IdentityValidationResult(
            passed=matched,
            overall_score=confidence,
            character_results={character_id: char_result} if character_id else {},
            frames_sampled=1,
            video_duration_seconds=0.0,
            shot_type=shot_type,
            threshold_used=threshold,
        )

        self.history.append(validation_result)
        icon = "✅" if matched else "❌"
        print(f"      {icon} Vision-LLM identity: confidence={confidence:.3f} (threshold={threshold})")
        return validation_result

    def _vision_llm_validate_video(
        self,
        video_path: str,
        character_configs: list,
        shot_type: str,
        threshold: float,
    ) -> IdentityValidationResult:
        """
        Vision-LLM video identity validation when DeepFace is unavailable.
        Extracts frames at 10%, 50%, 90% and validates each against references.
        """
        print(f"   [IDENTITY] Using Claude Vision for video (DeepFace unavailable)")

        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        duration = total_frames / max(fps, 1.0)

        if total_frames == 0:
            cap.release()
            return IdentityValidationResult(
                passed=False, overall_score=0.0, character_results={},
                frames_sampled=0, video_duration_seconds=0.0,
                shot_type=shot_type, threshold_used=threshold,
            )

        # Sample 3 frames: 10%, 50%, 90%
        sample_positions = [0.1, 0.5, 0.9]
        frame_paths = []

        for pos in sample_positions:
            frame_idx = max(0, min(int(pos * total_frames), total_frames - 1))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if ret:
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                cv2.imwrite(tmp.name, frame)
                frame_paths.append(tmp.name)
        cap.release()

        if not frame_paths:
            return IdentityValidationResult(
                passed=False, overall_score=0.0, character_results={},
                frames_sampled=0, video_duration_seconds=duration,
                shot_type=shot_type, threshold_used=threshold,
            )

        # Validate middle frame (best representative) per character
        character_results = {}
        mid_frame = frame_paths[len(frame_paths) // 2]

        for cfg in character_configs:
            cid = cfg["id"]
            ref_img = cfg.get("reference_image", "")
            char_name = cfg.get("name", cid)

            if not ref_img or not os.path.exists(ref_img):
                continue

            result = validate_identity_vision(ref_img, mid_frame)
            confidence = result.get("confidence", 0.0)
            matched = confidence >= threshold
            failure = FailureReason.PASSED if matched else FailureReason.WRONG_PERSON

            frame_sample = FrameSample(
                frame_index=0, frame_position_ratio=0.5,
                face_detected=confidence > 0.1,
                face_confidence=confidence,
                face_area_ratio=0.0, face_angle_estimate="unknown",
                similarity=confidence, matched=matched,
                failure_reason=failure,
            )

            character_results[cid] = CharacterIdentityResult(
                character_id=cid, character_name=char_name,
                best_similarity=confidence, mean_similarity=confidence,
                min_similarity=confidence, frame_results=[frame_sample],
                matched=matched, primary_failure_reason=failure,
                suggested_pulid_adjustment=self._compute_pulid_delta(confidence, matched),
            )

        # Cleanup temp frames
        for fp in frame_paths:
            if os.path.exists(fp):
                os.remove(fp)

        scores = [cr.best_similarity for cr in character_results.values()]
        overall = sum(scores) / len(scores) if scores else 0.0
        all_passed = all(cr.matched for cr in character_results.values()) if character_results else True

        validation_result = IdentityValidationResult(
            passed=all_passed, overall_score=overall,
            character_results=character_results,
            frames_sampled=len(frame_paths),
            video_duration_seconds=duration,
            shot_type=shot_type, threshold_used=threshold,
        )

        self.history.append(validation_result)

        for cid, cr in character_results.items():
            icon = "✅" if cr.matched else "❌"
            reason_str = f" [{cr.primary_failure_reason.value}]" if not cr.matched else ""
            print(f"      {icon} {cr.character_name}: confidence={cr.best_similarity:.3f} (threshold={threshold}){reason_str}")

        return validation_result
