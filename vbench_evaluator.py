"""
VBench-2.0 Inspired Video Quality Evaluator
=============================================
Implements VBench evaluation CONCEPTS using pipeline-available tools
(vision LLMs, OpenCV, numpy). This is NOT the academic VBench library.

Dimensions evaluated:
  - identity_consistency  (25%)  Claude Vision face comparison
  - temporal_flicker      (20%)  pixel-level frame differencing
  - motion_smoothness     (15%)  optical flow variance
  - aesthetic_quality     (15%)  GPT-4o shot quality
  - prompt_adherence      (15%)  Gemini semantic matching
  - physics_plausibility  (10%)  Gemini physics reasoning
"""

import cv2
import numpy as np
import os
import json
import base64
import tempfile
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

# Pipeline imports — graceful fallback if unavailable
try:
    from phase_c_vision import validate_shot_quality_vision, validate_identity_vision
    VISION_MODULE_AVAILABLE = True
except ImportError:
    VISION_MODULE_AVAILABLE = False
    print("[VBENCH] WARNING: phase_c_vision not importable — LLM dimensions will use defaults")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class VBenchResult:
    """Container for all VBench evaluation results."""
    identity_consistency: float = 0.0   # 0-1, face/character stability
    temporal_flicker: float = 0.0       # 0-1, inter-frame luminance stability (1=no flicker)
    motion_smoothness: float = 0.0      # 0-1, optical flow consistency
    aesthetic_quality: float = 0.0      # 0-1, composition/lighting/color
    prompt_adherence: float = 0.0       # 0-1, semantic match to prompt
    physics_plausibility: float = 0.0   # 0-1, gravity/collision/material behavior
    overall_score: float = 0.0          # 0-1, weighted average
    dimension_scores: dict = field(default_factory=dict)
    recommendations: list = field(default_factory=list)
    evaluation_cost_usd: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        # Ensure numpy floats are serialized as plain Python floats
        for key, val in d.items():
            if isinstance(val, (np.floating, np.integer)):
                d[key] = float(val)
            elif isinstance(val, dict):
                d[key] = {k: float(v) if isinstance(v, (np.floating, np.integer)) else v for k, v in val.items()}
        return d

    def summary(self) -> str:
        lines = [
            f"=== VBench Evaluation ===",
            f"  Overall Score:         {self.overall_score:.3f}",
            f"  Identity Consistency:  {self.identity_consistency:.3f}  (25%)",
            f"  Temporal Flicker:      {self.temporal_flicker:.3f}  (20%)",
            f"  Motion Smoothness:     {self.motion_smoothness:.3f}  (15%)",
            f"  Aesthetic Quality:     {self.aesthetic_quality:.3f}  (15%)",
            f"  Prompt Adherence:      {self.prompt_adherence:.3f}  (15%)",
            f"  Physics Plausibility:  {self.physics_plausibility:.3f}  (10%)",
            f"  Est. Cost:             ${self.evaluation_cost_usd:.4f}",
        ]
        if self.recommendations:
            lines.append("  Recommendations:")
            for rec in self.recommendations:
                lines.append(f"    - {rec}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

DIMENSION_WEIGHTS = {
    "identity_consistency": 0.25,
    "temporal_flicker": 0.20,
    "motion_smoothness": 0.15,
    "aesthetic_quality": 0.15,
    "prompt_adherence": 0.15,
    "physics_plausibility": 0.10,
}


# ---------------------------------------------------------------------------
# Frame extraction helper
# ---------------------------------------------------------------------------

def _extract_frames(video_path: str, fps: int = 1) -> list[np.ndarray]:
    """
    Extract frames from a video at the given FPS using OpenCV.
    Returns a list of BGR numpy arrays.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    if video_fps <= 0:
        video_fps = 30.0  # sensible default

    frame_interval = max(1, int(round(video_fps / fps)))
    frames = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            frames.append(frame)
        frame_idx += 1

    cap.release()

    if len(frames) == 0:
        raise RuntimeError(f"No frames extracted from {video_path}")

    return frames


def _save_frame_temp(frame: np.ndarray, prefix: str = "vbench_frame") -> str:
    """Save a single frame to a temporary file, return the path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", prefix=prefix, delete=False)
    cv2.imwrite(tmp.name, frame)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class VBenchEvaluator:
    """
    VBench-2.0 inspired multi-dimensional video quality evaluator.
    Uses OpenCV for signal-level metrics and vision LLMs for semantic metrics.
    """

    def __init__(self, verbose: bool = True, flicker_threshold: float = 0.85,
                 regression_tolerance: float = 0.05):
        self.verbose = verbose
        self.flicker_threshold = flicker_threshold
        self.regression_tolerance = regression_tolerance
        self._cost = 0.0  # accumulate estimated API cost

    def _log(self, msg: str):
        if self.verbose:
            print(f"[VBENCH] {msg}")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def evaluate(
        self,
        video_path: str,
        prompt: str,
        reference_images: Optional[list[str]] = None,
        shot_type: str = "medium",
    ) -> VBenchResult:
        """
        Run all VBench dimensions on a video and return a VBenchResult.

        Args:
            video_path: Path to the video file.
            prompt: The original generation prompt.
            reference_images: Optional list of reference face/character images.
            shot_type: Shot framing hint (close-up, medium, wide).

        Returns:
            VBenchResult with all dimension scores and recommendations.
        """
        self._cost = 0.0
        self._log(f"Evaluating: {video_path}")
        self._log(f"Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

        # Extract frames at 1 FPS
        frames = _extract_frames(video_path, fps=1)
        self._log(f"Extracted {len(frames)} frames at 1 FPS")

        # Run each dimension evaluator
        identity = self._evaluate_identity_consistency(frames, reference_images)
        flicker = self._evaluate_temporal_flicker(frames)
        smoothness = self._evaluate_motion_smoothness(frames)
        aesthetic = self._evaluate_aesthetic_quality(frames, prompt)
        adherence = self._evaluate_prompt_adherence(frames, prompt)
        physics = self._evaluate_physics_plausibility(frames)

        # Build scores dict
        scores = {
            "identity_consistency": identity,
            "temporal_flicker": flicker,
            "motion_smoothness": smoothness,
            "aesthetic_quality": aesthetic,
            "prompt_adherence": adherence,
            "physics_plausibility": physics,
        }

        # Weighted overall
        overall = sum(scores[k] * DIMENSION_WEIGHTS[k] for k in DIMENSION_WEIGHTS)

        # Generate recommendations
        recommendations = self._generate_recommendations(scores, shot_type)

        result = VBenchResult(
            identity_consistency=identity,
            temporal_flicker=flicker,
            motion_smoothness=smoothness,
            aesthetic_quality=aesthetic,
            prompt_adherence=adherence,
            physics_plausibility=physics,
            overall_score=round(overall, 4),
            dimension_scores=scores,
            recommendations=recommendations,
            evaluation_cost_usd=round(self._cost, 6),
        )

        self._log(result.summary())
        return result

    # ------------------------------------------------------------------
    # Temporal Flicker (cv2 + numpy only)
    # ------------------------------------------------------------------

    def _evaluate_temporal_flicker(self, frames: list[np.ndarray]) -> float:
        """
        Compute inter-frame luminance stability.
        Score = 1.0 - normalized_mean_abs_diff (1.0 = no flicker).
        Uses cv2 and numpy only.
        """
        if len(frames) < 2:
            return 1.0  # single frame = no flicker by definition

        diffs = []
        for i in range(len(frames) - 1):
            gray_a = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY).astype(np.float32)
            gray_b = cv2.cvtColor(frames[i + 1], cv2.COLOR_BGR2GRAY).astype(np.float32)
            abs_diff = np.abs(gray_a - gray_b)
            mean_diff = np.mean(abs_diff)
            diffs.append(mean_diff)

        # Normalize: pixel diffs are 0-255, so divide by 255
        avg_diff = np.mean(diffs)
        normalized = min(avg_diff / 255.0, 1.0)

        score = round(1.0 - normalized, 4)
        self._log(f"Temporal flicker: avg_diff={avg_diff:.2f}, score={score:.4f}")
        return score

    # ------------------------------------------------------------------
    # Motion Smoothness (cv2 + numpy only)
    # ------------------------------------------------------------------

    def _evaluate_motion_smoothness(self, frames: list[np.ndarray]) -> float:
        """
        Compute optical flow consistency via Farneback.
        Low variance in flow magnitudes = smooth motion = high score.
        Uses cv2 and numpy only.
        """
        if len(frames) < 2:
            return 1.0

        flow_magnitudes = []

        for i in range(len(frames) - 1):
            gray_a = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            gray_b = cv2.cvtColor(frames[i + 1], cv2.COLOR_BGR2GRAY)

            flow = cv2.calcOpticalFlowFarneback(
                gray_a, gray_b,
                None,
                pyr_scale=0.5,
                levels=3,
                winsize=15,
                iterations=3,
                poly_n=5,
                poly_sigma=1.2,
                flags=0,
            )

            magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
            flow_magnitudes.append(np.mean(magnitude))

        if len(flow_magnitudes) < 2:
            return 0.9  # only one pair, assume reasonably smooth

        # Variance of mean magnitudes across frames
        variance = np.var(flow_magnitudes)

        # Map variance to score: low variance = high score
        # Empirical: variance < 1 is very smooth, > 50 is very jittery
        # Using sigmoid-like mapping
        score = 1.0 / (1.0 + variance / 10.0)
        score = round(min(max(score, 0.0), 1.0), 4)

        self._log(
            f"Motion smoothness: flow_var={variance:.2f}, "
            f"mean_magnitudes={[f'{m:.1f}' for m in flow_magnitudes]}, score={score:.4f}"
        )
        return score

    # ------------------------------------------------------------------
    # Identity Consistency (Claude Vision via phase_c_vision)
    # ------------------------------------------------------------------

    def _evaluate_identity_consistency(
        self,
        frames: list[np.ndarray],
        reference_images: Optional[list[str]] = None,
    ) -> float:
        """
        Compare reference faces against frames at 25%, 50%, 75% positions.
        Uses Claude Vision (validate_identity_vision) when available.
        Returns 0.75 neutral default if no API key or no references.
        """
        if not reference_images:
            self._log("Identity consistency: no reference images, returning 0.75 default")
            return 0.75

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key or not VISION_MODULE_AVAILABLE:
            self._log("Identity consistency: no ANTHROPIC_API_KEY or vision module, returning 0.75 default")
            return 0.75

        # Sample frames at 25%, 50%, 75%
        positions = [0.25, 0.50, 0.75]
        sample_indices = [min(int(p * len(frames)), len(frames) - 1) for p in positions]

        temp_files = []
        confidences = []

        try:
            for ref_path in reference_images:
                if not os.path.exists(ref_path):
                    continue

                for idx in sample_indices:
                    frame_path = _save_frame_temp(frames[idx], prefix="vbench_id_")
                    temp_files.append(frame_path)

                    try:
                        result = validate_identity_vision(ref_path, frame_path)
                        conf = result.get("confidence", 0.7)
                        confidences.append(conf)
                        # Estimate cost: ~$0.003 per Claude vision call
                        self._cost += 0.003
                    except Exception as e:
                        self._log(f"Identity check failed for frame {idx}: {e}")
                        confidences.append(0.7)

        finally:
            for tmp in temp_files:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

        if not confidences:
            return 0.75

        score = round(np.mean(confidences), 4)
        self._log(f"Identity consistency: {len(confidences)} checks, avg={score:.4f}")
        return score

    # ------------------------------------------------------------------
    # Aesthetic Quality (GPT-4o via phase_c_vision)
    # ------------------------------------------------------------------

    def _evaluate_aesthetic_quality(self, frames: list[np.ndarray], prompt: str) -> float:
        """
        Send the middle frame + prompt to GPT-4o for aesthetic scoring.
        Normalizes the 0-10 score to 0-1.
        Returns 0.7 neutral default if no API key.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or not VISION_MODULE_AVAILABLE:
            self._log("Aesthetic quality: no OPENAI_API_KEY or vision module, returning 0.7 default")
            return 0.7

        mid_idx = len(frames) // 2
        frame_path = _save_frame_temp(frames[mid_idx], prefix="vbench_aes_")

        try:
            result = validate_shot_quality_vision(frame_path, prompt)
            raw_score = result.get("score", 7)
            # Estimate cost: ~$0.005 per GPT-4o vision call
            self._cost += 0.005

            score = round(min(max(raw_score / 10.0, 0.0), 1.0), 4)
            self._log(f"Aesthetic quality: GPT-4o raw={raw_score}/10, normalized={score:.4f}")
            return score

        except Exception as e:
            self._log(f"Aesthetic quality evaluation failed: {e}")
            return 0.7

        finally:
            try:
                os.unlink(frame_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Prompt Adherence (Gemini 2.5 Flash)
    # ------------------------------------------------------------------

    def _evaluate_prompt_adherence(self, frames: list[np.ndarray], prompt: str) -> float:
        """
        Send the middle frame + prompt to Gemini 2.5 Flash for semantic match scoring.
        Returns 0.7 neutral default if no API key.
        """
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            self._log("Prompt adherence: no GOOGLE_API_KEY/GEMINI_API_KEY, returning 0.7 default")
            return 0.7

        mid_idx = len(frames) // 2
        frame_path = _save_frame_temp(frames[mid_idx], prefix="vbench_prompt_")

        try:
            from google import genai

            client = genai.Client(api_key=api_key)

            with open(frame_path, "rb") as f:
                image_bytes = f.read()

            image_part = genai.types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/jpeg",
            )

            query = (
                f"You are evaluating how well a generated image matches its original prompt.\n\n"
                f"Original prompt: \"{prompt}\"\n\n"
                f"Rate on a scale of 0-10 how well this image matches the prompt. Consider:\n"
                f"- Subject matter accuracy\n"
                f"- Setting/environment match\n"
                f"- Mood and tone alignment\n"
                f"- Detail accuracy (clothing, objects, colors mentioned)\n\n"
                f"Respond with ONLY a JSON object: {{\"score\": <0-10>, \"reasoning\": \"...\"}}"
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[image_part, query],
            )

            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            parsed = json.loads(raw)
            raw_score = parsed.get("score", 7)
            # Estimate cost: ~$0.001 per Gemini flash call
            self._cost += 0.001

            score = round(min(max(raw_score / 10.0, 0.0), 1.0), 4)
            self._log(f"Prompt adherence: Gemini raw={raw_score}/10, normalized={score:.4f}")
            return score

        except Exception as e:
            self._log(f"Prompt adherence evaluation failed: {e}")
            return 0.7

        finally:
            try:
                os.unlink(frame_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Physics Plausibility (Gemini 2.5 Flash)
    # ------------------------------------------------------------------

    def _evaluate_physics_plausibility(self, frames: list[np.ndarray]) -> float:
        """
        Send 3 frames (start, mid, end) to Gemini for physics violation analysis.
        Returns 0.75 neutral default if no API key.
        """
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            self._log("Physics plausibility: no GOOGLE_API_KEY/GEMINI_API_KEY, returning 0.75 default")
            return 0.75

        # Select start, middle, end frames
        indices = [0, len(frames) // 2, len(frames) - 1]
        # Deduplicate if video is very short
        indices = list(dict.fromkeys(indices))

        temp_files = []

        try:
            from google import genai

            client = genai.Client(api_key=api_key)

            image_parts = []
            for idx in indices:
                frame_path = _save_frame_temp(frames[idx], prefix="vbench_phys_")
                temp_files.append(frame_path)

                with open(frame_path, "rb") as f:
                    image_bytes = f.read()

                image_parts.append(
                    genai.types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/jpeg",
                    )
                )

            query = (
                "These are frames from a generated video (start, middle, end in order). "
                "Analyze them for physics violations:\n"
                "1. Gravity — do objects fall/float incorrectly?\n"
                "2. Collisions — do objects pass through each other?\n"
                "3. Material behavior — do materials deform unnaturally?\n"
                "4. Proportions — do body/object proportions change impossibly?\n"
                "5. Shadows/reflections — are they physically consistent?\n\n"
                "Rate the overall physics plausibility 0-10 "
                "(10 = perfectly realistic, 0 = completely broken).\n\n"
                "Respond with ONLY a JSON object: "
                "{\"score\": <0-10>, \"violations\": [\"...\"]}"
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[*image_parts, query],
            )

            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            parsed = json.loads(raw)
            raw_score = parsed.get("score", 7.5)
            # Estimate cost: ~$0.002 per Gemini flash call with multiple images
            self._cost += 0.002

            score = round(min(max(raw_score / 10.0, 0.0), 1.0), 4)
            self._log(f"Physics plausibility: Gemini raw={raw_score}/10, normalized={score:.4f}")
            return score

        except Exception as e:
            self._log(f"Physics plausibility evaluation failed: {e}")
            return 0.75

        finally:
            for tmp in temp_files:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Recommendations engine
    # ------------------------------------------------------------------

    def _generate_recommendations(self, scores: dict, shot_type: str) -> list[str]:
        """Generate actionable improvement suggestions based on dimension scores."""
        recs = []

        if scores["identity_consistency"] < 0.6:
            recs.append(
                "Identity consistency is low. Consider using face-swap post-processing "
                "(fal.ai PixVerse or FaceFusion) or adding PuLID/IP-Adapter identity locking."
            )
        elif scores["identity_consistency"] < 0.75:
            recs.append(
                "Identity consistency is moderate. Try increasing reference image weight "
                "or using closer framing for face shots."
            )

        if scores["temporal_flicker"] < 0.85:
            recs.append(
                "Temporal flicker detected. Consider applying frame interpolation (RIFE/FILM) "
                "or using a model with stronger temporal coherence (Kling, Veo)."
            )

        if scores["motion_smoothness"] < 0.6:
            recs.append(
                "Motion is jittery. Reduce camera movement in the prompt, use motion smoothing "
                "in post-processing, or switch to a model with better temporal stability."
            )
        elif scores["motion_smoothness"] < 0.75:
            recs.append(
                "Motion smoothness is moderate. Consider simplifying camera movements "
                "or using longer generation durations for smoother transitions."
            )

        if scores["aesthetic_quality"] < 0.6:
            recs.append(
                "Aesthetic quality is low. Improve the prompt with specific lighting, composition, "
                "and color palette instructions. Consider using style references."
            )

        if scores["prompt_adherence"] < 0.6:
            recs.append(
                "Prompt adherence is low. Simplify the prompt, focus on fewer elements, "
                "or use a model with better instruction following (Sora, Veo)."
            )

        if scores["physics_plausibility"] < 0.6:
            recs.append(
                "Physics violations detected. Avoid complex physics interactions in the prompt "
                "or use models trained with physics-aware objectives."
            )

        if not recs:
            recs.append("All dimensions scored well. No major improvements needed.")

        return recs

    # ------------------------------------------------------------------
    # Comparison: A vs B
    # ------------------------------------------------------------------

    def compare(
        self,
        video_a: str,
        video_b: str,
        prompt: str,
        reference_images: Optional[list[str]] = None,
    ) -> dict:
        """
        Evaluate two videos and compare them dimension by dimension.

        Returns a dict with:
            - result_a: VBenchResult for video A
            - result_b: VBenchResult for video B
            - per_dimension: {dim: {"winner": "A"|"B"|"tie", "delta": float}}
            - overall_winner: "A" | "B" | "tie"
        """
        self._log(f"Comparing: A={video_a} vs B={video_b}")

        result_a = self.evaluate(video_a, prompt, reference_images)
        result_b = self.evaluate(video_b, prompt, reference_images)

        per_dimension = {}
        for dim in DIMENSION_WEIGHTS:
            score_a = result_a.dimension_scores[dim]
            score_b = result_b.dimension_scores[dim]
            delta = score_a - score_b

            if abs(delta) < 0.02:
                winner = "tie"
            elif delta > 0:
                winner = "A"
            else:
                winner = "B"

            per_dimension[dim] = {
                "winner": winner,
                "score_a": round(score_a, 4),
                "score_b": round(score_b, 4),
                "delta": round(delta, 4),
            }

        overall_delta = result_a.overall_score - result_b.overall_score
        if abs(overall_delta) < 0.02:
            overall_winner = "tie"
        elif overall_delta > 0:
            overall_winner = "A"
        else:
            overall_winner = "B"

        comparison = {
            "result_a": result_a.to_dict(),
            "result_b": result_b.to_dict(),
            "per_dimension": per_dimension,
            "overall_winner": overall_winner,
            "overall_delta": round(overall_delta, 4),
        }

        self._log(f"Comparison result: overall_winner={overall_winner} (delta={overall_delta:.4f})")
        return comparison

    # ------------------------------------------------------------------
    # Regression check
    # ------------------------------------------------------------------

    def regression_check(
        self,
        current_scores: VBenchResult,
        baseline: dict,
        tolerance: float | None = None,
    ) -> list[str]:
        """
        Compare current evaluation against a baseline.

        Args:
            current_scores: VBenchResult from the current evaluation.
            baseline: Dict of {dimension_name: float} baseline scores.
            tolerance: Allowed drop before flagging. Defaults to self.regression_tolerance.

        Returns:
            List of dimension names that regressed beyond tolerance.
        """
        if tolerance is None:
            tolerance = self.regression_tolerance
        regressions = []

        for dim, baseline_score in baseline.items():
            current_score = current_scores.dimension_scores.get(dim)
            if current_score is None:
                continue

            if current_score < (baseline_score - tolerance):
                drop = baseline_score - current_score
                regressions.append(dim)
                self._log(
                    f"REGRESSION: {dim} dropped from {baseline_score:.3f} to "
                    f"{current_score:.3f} (delta={drop:.3f}, tolerance={tolerance})"
                )

        if not regressions:
            self._log("No regressions detected against baseline.")
        else:
            self._log(f"Regressions found in {len(regressions)} dimension(s): {regressions}")

        return regressions


# ---------------------------------------------------------------------------
# CLI / standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("VBench Evaluator — Standalone Test")
    print("=" * 60)

    # Find a test video in the current directory or Content/
    test_videos = [
        "test_kling_native.mp4",
        "test_ltx_native.mp4",
        "test_sora.mp4",
        "test_veo.mp4",
        "test_ltx.mp4",
    ]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = None

    for tv in test_videos:
        candidate = os.path.join(script_dir, tv)
        if os.path.exists(candidate):
            video_path = candidate
            break

    if video_path is None:
        # Allow passing a video path as argument
        if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
            video_path = sys.argv[1]
        else:
            print(f"No test video found in {script_dir}")
            print(f"Checked: {test_videos}")
            print("Usage: python vbench_evaluator.py [video_path]")
            print()
            print("Running signal-level tests on synthetic frames instead...")

            # Create synthetic test frames (gradient with slight flicker)
            print()
            print("--- Temporal Flicker Test (synthetic) ---")
            evaluator = VBenchEvaluator(verbose=True)

            # Stable frames (low flicker)
            stable_frames = []
            for i in range(5):
                frame = np.full((256, 256, 3), 128, dtype=np.uint8)
                frame[:, :, 0] = 128 + i  # tiny variation in blue channel
                stable_frames.append(frame)

            flicker_score = evaluator._evaluate_temporal_flicker(stable_frames)
            print(f"  Stable frames flicker score: {flicker_score:.4f} (expected ~0.99)")

            # Flickery frames (high flicker)
            flickery_frames = []
            for i in range(5):
                val = 50 if i % 2 == 0 else 200
                frame = np.full((256, 256, 3), val, dtype=np.uint8)
                flickery_frames.append(frame)

            flicker_score2 = evaluator._evaluate_temporal_flicker(flickery_frames)
            print(f"  Flickery frames flicker score: {flicker_score2:.4f} (expected ~0.41)")

            print()
            print("--- Motion Smoothness Test (synthetic) ---")

            # Smooth horizontal pan
            smooth_frames = []
            for i in range(5):
                frame = np.zeros((256, 256, 3), dtype=np.uint8)
                x_offset = i * 10  # consistent 10px shift
                cv2.rectangle(frame, (50 + x_offset, 100), (100 + x_offset, 150), (255, 255, 255), -1)
                smooth_frames.append(frame)

            smooth_score = evaluator._evaluate_motion_smoothness(smooth_frames)
            print(f"  Smooth motion score: {smooth_score:.4f} (expected > 0.7)")

            print()
            print("--- Regression Check Test ---")

            mock_result = VBenchResult(
                identity_consistency=0.80,
                temporal_flicker=0.92,
                motion_smoothness=0.70,
                aesthetic_quality=0.65,
                prompt_adherence=0.75,
                physics_plausibility=0.80,
                overall_score=0.78,
                dimension_scores={
                    "identity_consistency": 0.80,
                    "temporal_flicker": 0.92,
                    "motion_smoothness": 0.70,
                    "aesthetic_quality": 0.65,
                    "prompt_adherence": 0.75,
                    "physics_plausibility": 0.80,
                },
            )

            baseline = {
                "identity_consistency": 0.85,
                "temporal_flicker": 0.90,
                "motion_smoothness": 0.72,
                "aesthetic_quality": 0.80,
                "prompt_adherence": 0.70,
                "physics_plausibility": 0.78,
            }

            regressions = evaluator.regression_check(mock_result, baseline, tolerance=0.05)
            print(f"  Regressions detected: {regressions}")
            print(f"  Expected: ['identity_consistency', 'aesthetic_quality']")

            print()
            print("Synthetic tests complete.")
            sys.exit(0)

    # Full evaluation on a real video
    print(f"Using video: {video_path}")
    print()

    evaluator = VBenchEvaluator(verbose=True)
    test_prompt = "A cinematic medium shot of a person speaking confidently in a modern office"

    result = evaluator.evaluate(
        video_path=video_path,
        prompt=test_prompt,
    )

    print()
    print("=== Full Result Dict ===")
    print(json.dumps(result.to_dict(), indent=2, default=str))
