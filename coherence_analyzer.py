"""
Cinema Production Tool — Visual Coherence Analyzer
Validates that consecutive shots maintain consistent color, lighting,
and composition to look like they belong in the same film.

Subsystems:
1. ColorCoherenceAnalyzer — histogram comparison, palette drift detection
2. CompositionAnalyzer — brightness distribution, lighting direction, exposure
3. SceneCoherenceResult — aggregate coherence score with recommendations
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional

import cv2
import numpy as np


@dataclass
class SceneCoherenceResult:
    """Aggregate coherence result for a pair or sequence of shots."""
    overall_coherence_score: float       # 0-1 (weighted: 0.4 color + 0.3 lighting + 0.3 composition)
    color_drift: float                   # 0-1 (higher = more drift)
    lighting_consistency: float          # 0-1 (higher = more consistent)
    composition_similarity: float        # 0-1
    recommendations: List[str] = field(default_factory=list)


class ColorCoherenceAnalyzer:
    """Detects color palette drift between consecutive shots."""

    @staticmethod
    def extract_color_histogram(image_path: str, bins: int = 64) -> Optional[np.ndarray]:
        """Extract normalized HSV histogram from an image."""
        img = cv2.imread(image_path)
        if img is None:
            return None
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [bins, bins], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist

    @staticmethod
    def compare_histograms(hist_a: np.ndarray, hist_b: np.ndarray) -> float:
        """
        Compare two histograms using correlation method.
        Returns 0-1 similarity (1 = identical palettes).
        """
        if hist_a is None or hist_b is None:
            return 0.0
        score = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL)
        return max(0.0, min(1.0, score))

    @staticmethod
    def compute_scene_palette(image_paths: List[str], k: int = 5) -> Optional[np.ndarray]:
        """
        Compute dominant colors for a scene via k-means clustering
        across all provided images.
        Returns k dominant BGR colors as (k, 3) array.
        """
        all_pixels = []
        for path in image_paths:
            img = cv2.imread(path)
            if img is None:
                continue
            # Downsample for speed
            small = cv2.resize(img, (64, 64))
            pixels = small.reshape(-1, 3).astype(np.float32)
            all_pixels.append(pixels)

        if not all_pixels:
            return None

        data = np.vstack(all_pixels)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
        _, _, centers = cv2.kmeans(data, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
        return centers

    def detect_palette_drift(
        self,
        current_image: str,
        scene_images: List[str],
    ) -> float:
        """
        Measure how much the current image's palette has drifted from
        the scene's established palette.
        Returns 0-1 drift score (0 = no drift, 1 = completely different).
        """
        if not scene_images:
            return 0.0

        current_hist = self.extract_color_histogram(current_image)
        if current_hist is None:
            return 0.0

        similarities = []
        for path in scene_images:
            ref_hist = self.extract_color_histogram(path)
            if ref_hist is not None:
                sim = self.compare_histograms(current_hist, ref_hist)
                similarities.append(sim)

        if not similarities:
            return 0.0

        avg_similarity = sum(similarities) / len(similarities)
        return 1.0 - avg_similarity  # Invert: 0 = consistent, 1 = drifted


class CompositionAnalyzer:
    """Analyzes brightness, lighting direction, and exposure consistency."""

    @staticmethod
    def analyze_brightness_distribution(image_path: str) -> Dict:
        """
        Analyze brightness distribution of an image.
        Returns mean brightness, std deviation, and key type.
        """
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return {"mean_brightness": 0.0, "std_brightness": 0.0, "key_type": "unknown"}

        mean_val = float(np.mean(img))
        std_val = float(np.std(img))

        if mean_val > 170:
            key_type = "high_key"
        elif mean_val < 85:
            key_type = "low_key"
        else:
            key_type = "balanced"

        return {
            "mean_brightness": mean_val / 255.0,
            "std_brightness": std_val / 255.0,
            "key_type": key_type,
        }

    @staticmethod
    def compare_lighting_direction(img_a_path: str, img_b_path: str) -> float:
        """
        Compare lighting direction between two images using gradient analysis.
        Returns 0-1 consistency score (1 = same lighting direction).
        """
        img_a = cv2.imread(img_a_path, cv2.IMREAD_GRAYSCALE)
        img_b = cv2.imread(img_b_path, cv2.IMREAD_GRAYSCALE)
        if img_a is None or img_b is None:
            return 0.5

        def _gradient_direction(img):
            # Compute Sobel gradients
            gx = cv2.Sobel(img, cv2.CV_64F, 1, 0, ksize=5)
            gy = cv2.Sobel(img, cv2.CV_64F, 0, 1, ksize=5)
            # Average gradient direction
            avg_gx = np.mean(gx)
            avg_gy = np.mean(gy)
            angle = np.arctan2(avg_gy, avg_gx)
            return angle

        angle_a = _gradient_direction(img_a)
        angle_b = _gradient_direction(img_b)

        # Angular difference, normalized to 0-1 (0 = same direction)
        diff = abs(angle_a - angle_b)
        if diff > np.pi:
            diff = 2 * np.pi - diff
        consistency = 1.0 - (diff / np.pi)
        return max(0.0, min(1.0, consistency))

    def detect_exposure_shift(self, image_paths: List[str]) -> float:
        """
        Detect maximum exposure difference across a set of images.
        Returns the max brightness delta (0-1 scale).
        """
        if len(image_paths) < 2:
            return 0.0

        brightnesses = []
        for path in image_paths:
            info = self.analyze_brightness_distribution(path)
            brightnesses.append(info["mean_brightness"])

        if not brightnesses:
            return 0.0

        return max(brightnesses) - min(brightnesses)


# ---------------------------------------------------------------------------
# Main coherence assessment function
# ---------------------------------------------------------------------------

def assess_coherence(
    current_image: str,
    previous_image: str,
    scene_images: List[str] = None,
) -> SceneCoherenceResult:
    """
    Assess visual coherence between current and previous shot.
    Optionally compares against the full scene palette if scene_images provided.

    Returns SceneCoherenceResult with per-dimension scores and recommendations.
    """
    color_analyzer = ColorCoherenceAnalyzer()
    comp_analyzer = CompositionAnalyzer()
    recommendations = []

    # 1. Color coherence
    color_drift = color_analyzer.detect_palette_drift(
        current_image,
        scene_images or [previous_image],
    )
    if color_drift > 0.3:
        recommendations.append("adjust_color_prompt")

    # 2. Lighting consistency
    lighting = comp_analyzer.compare_lighting_direction(previous_image, current_image)
    if lighting < 0.5:
        recommendations.append("match_lighting")

    # 3. Composition / exposure similarity
    prev_brightness = comp_analyzer.analyze_brightness_distribution(previous_image)
    curr_brightness = comp_analyzer.analyze_brightness_distribution(current_image)
    brightness_delta = abs(prev_brightness["mean_brightness"] - curr_brightness["mean_brightness"])
    composition_sim = 1.0 - min(brightness_delta * 2, 1.0)  # Penalize large shifts

    if brightness_delta > 0.15:
        recommendations.append("tighten_denoise")

    # Weighted overall score
    overall = (
        (1.0 - color_drift) * 0.4 +
        lighting * 0.3 +
        composition_sim * 0.3
    )

    return SceneCoherenceResult(
        overall_coherence_score=overall,
        color_drift=color_drift,
        lighting_consistency=lighting,
        composition_similarity=composition_sim,
        recommendations=recommendations,
    )
