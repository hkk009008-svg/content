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

import contextlib
import os
import tempfile
from typing import Optional, List, Dict, Callable, Tuple
from collections import Counter

import cv2
import numpy as np

try:
    from PIL import Image as _PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PILImage = None
    _PIL_AVAILABLE = False

from identity.types import (
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


# Type alias for the vision-LLM fallback hook.
# Returns {"confidence": float, "issues": list[str], ...}.
VisionValidator = Callable[[str, str], Dict]

# ---------------------------------------------------------------------------
# Figure-read constants and helpers (detection filtering)
# ---------------------------------------------------------------------------
# These are module-level so scripts/_face_reads.py can re-export them without
# duplicating code (import direction: scripts → identity is conventional).

#: Below this fraction of crop area a detection is classified TINY (junk).
#: NOTE (completeness item C, 2026-06-12): the ratio is relative to the INPUT
#: image passed to _figure_read_score — a HALF-CROP in the binding path. A face
#: that is 1% of the full frame is ~2% of its half-crop; the effective
#: full-frame floor when scoring half-crops is therefore ~0.5%, not 1%. Callers
#: scoring full images apply a 2x-stricter filter with the same constant.
FIGURE_TINY_AREA_RATIO: float = 0.01

#: A bounding box within this many pixels of the full crop size is classified
#: DEGENERATE — the whole-image fallback that DeepFace emits with
#: enforce_detection=False when no face is found.
FIGURE_DEGENERATE_MARGIN_PX: int = 2


@contextlib.contextmanager
def _cv2_single_thread():
    """Pin OpenCV to a SINGLE thread for the duration of the block, then restore.

    DeepFace's align=True path (the default, and load-bearing — align=False
    collapses the man-binding signal 0.870→0.522) runs an OpenCV operation that
    **races under multi-threading**: it intermittently returns a different,
    mis-aligned crop whose GhostFaceNet embedding is 0.456 cosine-distant from
    the otherwise byte-stable majority — enough to swing an identity score
    0.870→0.762 (the man-ref "cold-draw", operator 2026-06-13). The DETECTED
    bbox is identical across runs; only the aligned crop races. It is an OpenCV
    thread race, NOT seedable RNG (numpy/cv2/Python/TF seeds + TF_DETERMINISTIC_OPS
    do not remove it). Serializing OpenCV pins the result to the deterministic
    majority value, preserving align=True accuracy with no re-baselining.

    VERIFIED (scripts/_probe_embedding_determinism.py --load): under induced
    OpenCV CPU load the UNGUARDED path diverges 8/30 (27%) to the 0.456-distant
    outlier; the GUARDED path is 30/30 byte-identical (the calibrated man-0.870
    value). The race is load-dependent — it rarely fires on a quiet machine, so a
    handful of clean runs is NOT evidence the guard is needed or working.

    CROSS-PLATFORM: cv2.setNumThreads(1) yields one thread on TBB/pthreads
    (Linux pod) but is a NO-OP on the GCD backend (macOS dev): there
    getNumThreads() stays at the system default and only setNumThreads(0)
    serializes. We therefore set 1, and fall back to 0 if 1 didn't take — so
    cv2 is single-threaded on BOTH backends. ⚠ The deterministic value is
    OpenCV-build-specific; the macOS single-threaded value (man 0.870) must be
    re-confirmed on the Linux pod before it is trusted as the production
    pinned value (review 2026-06-13, robustness lens).

    The prior thread count is restored afterward (even on exception) so the
    serialization is localized. Both the binding instrument and the production
    identity path (validate_image/validate_video, via represent AND
    extract_faces — both align) route through this guard.

    NOTE: cv2.setNumThreads is process-global. quality_max.py scores candidates
    in a ThreadPoolExecutor (max_quality_parallel_workers, default 1, up to 4):
    if two threads enter here concurrently, EACH call still runs single-threaded
    (determinism holds per-call), but the restore may land at 1 (a benign
    process-state leak — single-threaded is the desired state for this workload).
    If parallel_workers>1 becomes the default, gate entry with a threading.Lock.
    """
    _prev_threads = cv2.getNumThreads()
    try:
        cv2.setNumThreads(1)
        if cv2.getNumThreads() != 1:  # GCD: setNumThreads(1) is a no-op; 0 serializes
            cv2.setNumThreads(0)
        yield
    finally:
        cv2.setNumThreads(_prev_threads)


# Public alias for the shared cv2 single-thread determinism guard. domain/ embedding
# call sites (character_manager, continuity_engine) import this to route their
# DeepFace.represent/extract_faces through the same guard as the production path.
cv2_single_thread = _cv2_single_thread


def _represent_deterministic(image_path: str) -> list:
    """GhostFaceNet DeepFace.represent under the cv2 single-thread guard.

    The deterministic chokepoint for the five represent call sites (the binding
    instrument's figure/ref reads + the production validate_image/validate_video
    embedding reads). See _cv2_single_thread for the root-cause writeup.
    """
    with _cv2_single_thread():
        return DeepFace.represent(
            img_path=image_path, model_name="GhostFaceNet", enforce_detection=False
        )


def _classify_face_detection(
    bbox_w: int, bbox_h: int, img_w: int, img_h: int, confidence: float
) -> str:
    """Classify one DeepFace detection as DEGENERATE, TINY, or OK.

    DEGENERATE: bbox spans the whole crop (enforce_detection=False fallback;
    confidence is typically 0.0 but may be non-zero on some images).
    TINY: bbox area < FIGURE_TINY_AREA_RATIO of the crop — texture patches that
    routinely score higher vs man ref than the true figure (0.59–0.78 vs 0.47–0.52
    on the 2026-06-12 probe).
    OK: any other detection — treated as a valid face.

    NOTE (completeness item A, director disposition 2026-06-12): the DEGENERATE
    test is CONJUNCTIVE — both dimensions must be within FIGURE_DEGENERATE_MARGIN_PX
    of the crop. An asymmetric near-full-image box (e.g. full width but a few px
    short in height) escapes DEGENERATE, also escapes TINY (area ~100%), and wins
    as the largest OK face — a whole-image-equivalent embedding. Not observed in
    the 2026-06-12 artifacts; tightening the test (area-fraction OR per-dim) needs
    its own regression vs the 28 binding tests and is QUEUED, not done.
    """
    if bbox_w >= img_w - FIGURE_DEGENERATE_MARGIN_PX and bbox_h >= img_h - FIGURE_DEGENERATE_MARGIN_PX:
        return "DEGENERATE"
    if img_w and img_h and (bbox_w * bbox_h) / (img_w * img_h) < FIGURE_TINY_AREA_RATIO:
        return "TINY"
    return "OK"


def _largest_ok_embedding(
    image_path: str, emb_list: List[Dict]
) -> Optional[np.ndarray]:
    """Return the embedding for the largest OK detection, or None.

    This mirrors the reference selection semantics used by the binding
    instrument so production reference reads do not depend on DeepFace detection
    order.
    """
    if not emb_list:
        return None

    try:
        if _PIL_AVAILABLE and _PILImage is not None:
            img = _PILImage.open(image_path)
            img_w, img_h = img.size
        else:
            img_cv = cv2.imread(image_path)
            if img_cv is None:
                return None
            img_h, img_w = img_cv.shape[:2]
    except Exception:
        return None

    best_ok_key: Optional[Tuple[float, int, int, int, int]] = None
    best_ok_emb: Optional[np.ndarray] = None

    for entry in emb_list:
        fa = entry.get("facial_area", {})
        w, h = fa.get("w", 0), fa.get("h", 0)
        conf = float(entry.get("face_confidence") or 0.0)
        if _classify_face_detection(w, h, img_w, img_h, conf) != "OK":
            continue

        area = float(w * h)
        key = (area, -fa.get("x", 0), -fa.get("y", 0), -w, -h)
        if best_ok_key is None or key > best_ok_key:
            best_ok_key = key
            best_ok_emb = np.array(entry["embedding"])

    return best_ok_emb


def _figure_read_score(
    image_path: str,
    ref_emb: np.ndarray,
    *,
    ref_name: str = "ref",
) -> dict:
    """Score a single image against a pre-computed reference embedding.

    Returns only from OK-classified detections (area >= 1% of crop, not a
    whole-image fallback).  Selects the LARGEST OK face (per-figure semantics:
    each half crop contains one figure; largest bbox = that figure; max-similarity
    would re-promote junk blobs whose scores exceed the real figure's score).

    Returns:
        score:           float | None   — (1+cos)/2; None when no OK face
        read_type:       'figure'|'none'
        n_detections:    int
        face_area_pct:   float          — area% of the selected face (0.0 if none)
        detection_class: dict[str,int]  — counts of OK/TINY/DEGENERATE
        ref_name:        str
    """
    if not DEEPFACE_AVAILABLE:
        return {
            "score": None, "read_type": "none", "n_detections": 0,
            "face_area_pct": 0.0,
            "detection_class": {"OK": 0, "TINY": 0, "DEGENERATE": 0},
            "ref_name": ref_name,
        }

    if not os.path.exists(image_path):
        return {
            "score": None, "read_type": "none", "n_detections": 0,
            "face_area_pct": 0.0,
            "detection_class": {"OK": 0, "TINY": 0, "DEGENERATE": 0},
            "ref_name": ref_name,
        }

    if _PIL_AVAILABLE and _PILImage is not None:
        img = _PILImage.open(image_path)
        img_w, img_h = img.size
    else:
        # Fallback: use OpenCV for dimensions
        img_cv = cv2.imread(image_path)
        if img_cv is None:
            return {
                "score": None, "read_type": "none", "n_detections": 0,
                "face_area_pct": 0.0,
                "detection_class": {"OK": 0, "TINY": 0, "DEGENERATE": 0},
                "ref_name": ref_name,
            }
        img_h, img_w = img_cv.shape[:2]

    img_area = img_w * img_h

    emb_list = _represent_deterministic(image_path)

    class_counts: Dict[str, int] = {"OK": 0, "TINY": 0, "DEGENERATE": 0}
    best_ok_area = -1.0
    best_ok_key: Optional[tuple] = None
    best_ok_emb: Optional[np.ndarray] = None
    best_ok_area_pct = 0.0

    for entry in emb_list:
        fa = entry.get("facial_area", {})
        w, h = fa.get("w", 0), fa.get("h", 0)
        conf = float(entry.get("face_confidence") or 0.0)
        cls = _classify_face_detection(w, h, img_w, img_h, conf)
        class_counts[cls] = class_counts.get(cls, 0) + 1

        if cls == "OK":
            area = float(w * h)
            # Largest OK face wins; ties broken by a deterministic geometric
            # key (top-left-most) so selection is a pure function of the
            # detection SET, independent of DeepFace's non-deterministic return
            # ORDER (proven to vary, scripts/_probe_figure_read_determinism.py).
            # Without it, two equal-area OK blobs would select by arrival order
            # → different embeddings across runs.
            key = (area, -fa.get("x", 0), -fa.get("y", 0), -w, -h)
            if best_ok_key is None or key > best_ok_key:
                best_ok_key = key
                best_ok_area = area
                best_ok_emb = np.array(entry["embedding"])
                best_ok_area_pct = 100.0 * area / img_area if img_area else 0.0

    if best_ok_emb is None:
        return {
            "score": None, "read_type": "none",
            "n_detections": len(emb_list),
            "face_area_pct": 0.0,
            "detection_class": class_counts,
            "ref_name": ref_name,
        }

    cos_sim = float(
        np.dot(best_ok_emb, ref_emb)
        / (np.linalg.norm(best_ok_emb) * np.linalg.norm(ref_emb) + 1e-10)
    )
    score = (1.0 + cos_sim) / 2.0

    return {
        "score": score, "read_type": "figure",
        "n_detections": len(emb_list),
        "face_area_pct": best_ok_area_pct,
        "detection_class": class_counts,
        "ref_name": ref_name,
    }


def _ref_embedding_largest_ok(ref_path: str, ref_name: str = "ref") -> Optional[np.ndarray]:
    """Compute a reference embedding using the largest OK detection.

    Guarded variant of _get_embedding: uses the largest OK bbox instead of
    emb_list[0].  MAN_REF (logs/p12_fresh_face_man.jpg) has 2 detections;
    [0] is correct only by ordering luck.  Falls back to emb_list[0] if no
    OK detection is found (should not occur for a well-cropped ref image).
    When that fallback fires (WARNING printed) the returned embedding is
    non-None and UNGUARDED — callers cannot tell it from a guarded read, and
    _compute_binding_scores records note='' (not 'REF_EMBEDDING_FAILED') for it
    (completeness item B, director disposition 2026-06-12). Production
    validate_image / validate_video reference reads now share the same
    largest-OK selection through _get_embedding.

    Returns None if DEEPFACE_AVAILABLE is False or any exception occurs.
    """
    if not DEEPFACE_AVAILABLE:
        return None

    try:
        if _PIL_AVAILABLE and _PILImage is not None:
            img = _PILImage.open(ref_path)
            img_w, img_h = img.size
        else:
            img_cv = cv2.imread(ref_path)
            if img_cv is None:
                return None
            img_h, img_w = img_cv.shape[:2]

        emb_list = _represent_deterministic(ref_path)

        best_ok_area = -1.0
        best_ok_key: Optional[tuple] = None
        best_ok_emb: Optional[np.ndarray] = None

        for entry in emb_list:
            fa = entry.get("facial_area", {})
            w, h = fa.get("w", 0), fa.get("h", 0)
            conf = float(entry.get("face_confidence") or 0.0)
            cls = _classify_face_detection(w, h, img_w, img_h, conf)
            if cls == "OK":
                area = float(w * h)
                # Deterministic tie-break (top-left-most), mirroring
                # _figure_read_score: ref selection is a pure function of the
                # detection set, not DeepFace's return order.
                key = (area, -fa.get("x", 0), -fa.get("y", 0), -w, -h)
                if best_ok_key is None or key > best_ok_key:
                    best_ok_key = key
                    best_ok_area = area
                    best_ok_emb = np.array(entry["embedding"])

        if best_ok_emb is not None:
            n_ok = sum(
                1 for e in emb_list
                if _classify_face_detection(
                    e.get("facial_area", {}).get("w", 0),
                    e.get("facial_area", {}).get("h", 0),
                    img_w, img_h,
                    float(e.get("face_confidence") or 0.0),
                ) == "OK"
            )
            print(
                f"   [face_reads] ref {ref_name}: {len(emb_list)} detection(s), "
                f"{n_ok} OK — using largest OK face ({best_ok_area:.0f}px^2)"
            )
            return best_ok_emb

        # Fallback: no OK detection
        print(
            f"   [face_reads] WARNING: no OK detection in ref {ref_name} "
            f"({ref_path}); falling back to emb_list[0]"
        )
        return np.array(emb_list[0]["embedding"])
    except Exception as e:
        print(f"   [face_reads] ref embedding failed for {ref_path}: {e}")
        return None


class IdentityValidator:
    """
    Unified identity validation for the cinema pipeline.
    Replaces validate_identity(), validate_identity_image(),
    validate_multi_identity(), and CharacterContinuityTracker.validate_multi_identity().

    The vision-LLM fallback (used when DeepFace is unavailable) is injected via
    `vision_fallback` so this module does not depend on phase_c_vision. Use the
    `make_validator()` factory in `identity/__init__.py` to get a validator
    pre-wired with the default vision fallback.
    """

    def __init__(
        self,
        embedding_cache: Dict[str, np.ndarray] = None,
        cache_dir: str = "",
        vision_fallback: Optional[VisionValidator] = None,
    ):
        self.embedding_cache = embedding_cache or {}
        self.cache_dir = cache_dir  # Directory for persisting embeddings to disk
        self.history: List[IdentityValidationResult] = []
        self._vision_fallback = vision_fallback

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
        if not os.path.exists(image_path):
            return self._missing_output_result(shot_type, threshold if threshold is not None else 0.70)
        if not os.path.exists(reference_path):
            return self._skipped_result(shot_type, threshold if threshold is not None else 0.70)

        if not DEEPFACE_AVAILABLE:
            return self._vision_llm_validate_image(
                image_path, reference_path, character_id, character_name,
                shot_type, threshold if threshold is not None else get_threshold_for_shot(shot_type),
            )

        if threshold is None:
            threshold = get_threshold_for_shot(shot_type)

        # Get reference embedding
        ref_emb = self._get_embedding(reference_path, character_id)
        if ref_emb is None:
            return self._skipped_result(shot_type, threshold)

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

    def validate_image_with_binding(
        self,
        image_path: str,
        reference_path: str,
        char_specs: List[Dict],
        character_id: str = "",
        character_name: str = "",
        shot_type: str = "medium",
        threshold: float = None,
    ) -> Tuple[IdentityValidationResult, Dict[str, Dict]]:
        """
        Thin public wrapper returning BOTH the existing presence result and
        per-character binding scores.

        validate_image is called unchanged (backward-compatible); binding
        scores are computed separately via _compute_binding_scores.

        Args:
            image_path: Path to generated image.
            reference_path: Path to primary character reference (used by
                validate_image for the presence check).
            char_specs: List of binding spec dicts, each:
                {
                    "char_id":      str,   # character identifier
                    "ref_path":     str,   # reference image path (path-based,
                                          # same API style as validate_image)
                    "intended_slot": "left" | "right",
                }
            character_id: Forwarded to validate_image unchanged.
            character_name: Forwarded to validate_image unchanged.
            shot_type: Forwarded to validate_image unchanged.
            threshold: Forwarded to validate_image unchanged.

        Returns:
            (presence_result, binding_dict)
            presence_result: same IdentityValidationResult as validate_image.
            binding_dict: char_id -> {
                "binding_score":      float,  # positive = intended side stronger
                "binding_ok":         bool,   # True only when binding_score > 0
                "intended_score":     float,  # figure-read score on intended half
                                              # (0.0 when no OK face detected)
                "other_score":        float,  # figure-read score on other half
                                              # (0.0 when no OK face detected)
                "intended_read_type": str,    # 'figure' | 'none'
                "other_read_type":    str,    # 'figure' | 'none'
                "note":               str,    # '' | 'NO_FACE_INTENDED' |
                                              # 'REF_EMBEDDING_FAILED' |
                                              # 'MISSING_IMAGE' | 'PIL_UNAVAILABLE'
            }

            NO_FACE semantics (director-decided 2026-06-12):
              - intended_read_type='none' → binding_ok=False, note='NO_FACE_INTENDED'
              - other_read_type='none' with intended 'figure' → binding decided
                as intended_score > 0 (face only on intended side = binds)
              - both 'none' → binding_ok=False, note='NO_FACE_INTENDED'

            NOTE — TWO face-selection rules in one return (operator Lane V
            2026-06-12T00:02:59Z, advisory #3). presence_result and binding_dict
            are NOT commensurable scores:
              - presence_result comes from validate_image, whose reference read
                goes through _get_embedding → DeepFace.represent[0] (FIRST
                detection, unfiltered; best-face presence semantics).
              - binding_dict comes from _compute_binding_scores via
                _figure_read_score (LARGEST OK face, classify-filtered;
                per-figure semantics — blobs / whole-image fallbacks excluded).
            The divergence is deliberate (presence asks "is X anywhere in
            frame", binding asks "is X's FIGURE on the intended half"). A caller
            must not compare a presence score against a binding score as if they
            were the same metric.
        """
        presence_result = self.validate_image(
            image_path, reference_path,
            character_id=character_id,
            character_name=character_name,
            shot_type=shot_type,
            threshold=threshold,
        )
        binding_dict = self._compute_binding_scores(image_path, char_specs)
        return presence_result, binding_dict

    def _compute_binding_scores(
        self,
        image_path: str,
        char_specs: List[Dict],
    ) -> Dict[str, Dict]:
        """
        Compute per-character spatial-binding scores using 50%-width half crops.

        For each character spec, answers "is character X's face on the INTENDED
        half of the frame?" using figure_read_score (detection-filtered; only
        OK-classified faces: area >= 1% of crop, not a whole-image fallback).
        The score is from the LARGEST OK face (per-figure semantics).

        INVARIANT — callers MUST assign DISTINCT intended_slot values (director
        disposition 2026-06-12T00:02:59Z; adversarial verify wf_9ed6fbf2-50d).
        In a two-character spike the two specs must be one 'left' + one 'right'.
        If both share a slot — e.g. both defaulting to 'left' via
        spec.get("intended_slot", "left") below — the other-half-none branch can
        return binding_ok=True for BOTH characters on any seed whose un-intended
        half is face-absent: a FALSE Phase-3 GO. This function does NOT yet
        validate slot uniqueness; callers that build char_specs from
        CharIdentitySpec (no intended_slot field) MUST set the slot explicitly.
        The Phase-3 driver assigns opposite slots and is REQUIRED to add the
        O(n) slot-uniqueness guard (SPEC-PASS-B §3.4 item A5 + §5 GO bar).

            binding_score(X) = intended_score - other_score
            binding_ok(X)    = binding_score > 0

        Director-decided NO_FACE semantics (2026-06-12 operator report):
          - intended read_type 'none' → binding_ok=False, note NO_FACE_INTENDED
          - other read_type 'none' with intended 'figure' → binding decided as
            intended_score > 0 (face only on intended side = binds)
          - both 'none' → binding_ok=False

        Boundary: w // 2 EXACTLY — matches _s1_rescore_crops.crop_half and the
        0-based masks in scripts/_arc_score_session.py.

        validate_image is NOT called here; scores come from _figure_read_score
        directly so blob/degenerate detections cannot pollute the binding
        decision.  validate_image itself is byte-unchanged.

        Args:
            image_path: Path to generated image (must exist; silently returns
                zero scores if missing or PIL/DeepFace unavailable).
            char_specs: list of {
                "char_id":      str,
                "ref_path":     str,   # reference image (path-based)
                "intended_slot": "left" | "right",
            }

        Returns:
            Dict[char_id, {
                "binding_score": float,
                "binding_ok":    bool,
                "intended_score": float,     # None-converted to 0.0 for delta
                "other_score":   float,      # None-converted to 0.0 for delta
                "intended_read_type": str,   # 'figure'|'none'
                "other_read_type":    str,   # 'figure'|'none'
                "note":          str,        # '' | 'NO_FACE_INTENDED' | ...
            }]
        """
        result: Dict[str, Dict] = {}

        if not char_specs:
            return result

        if not _PIL_AVAILABLE or _PILImage is None:
            for spec in char_specs:
                result[spec["char_id"]] = {
                    "binding_score": 0.0,
                    "binding_ok": False,
                    "intended_score": 0.0,
                    "other_score": 0.0,
                    "intended_read_type": "none",
                    "other_read_type": "none",
                    "note": "PIL_UNAVAILABLE",
                }
            return result

        if not os.path.exists(image_path):
            for spec in char_specs:
                result[spec["char_id"]] = {
                    "binding_score": 0.0,
                    "binding_ok": False,
                    "intended_score": 0.0,
                    "other_score": 0.0,
                    "intended_read_type": "none",
                    "other_read_type": "none",
                    "note": "MISSING_IMAGE",
                }
            return result

        try:
            img = _PILImage.open(image_path)
            w, h = img.size
            mid = w // 2

            # Pre-compute ref embeddings using largest-OK-face guard so ref
            # images with multiple detections (e.g. MAN_REF has 2) use the
            # correct face rather than emb_list[0] by ordering luck.
            ref_embs: Dict[str, Optional[np.ndarray]] = {}
            for spec in char_specs:
                char_id = spec["char_id"]
                ref_path = spec.get("ref_path", "")
                if char_id not in ref_embs:
                    ref_embs[char_id] = _ref_embedding_largest_ok(ref_path, char_id)

            # Produce the two half crops in a temp dir; clean up after scoring.
            with tempfile.TemporaryDirectory() as tmpdir:
                base = os.path.splitext(os.path.basename(image_path))[0]
                left_path = os.path.join(tmpdir, f"{base}_left.jpg")
                right_path = os.path.join(tmpdir, f"{base}_right.jpg")
                img.crop((0, 0, mid, h)).save(left_path, quality=95)
                img.crop((mid, 0, w, h)).save(right_path, quality=95)

                for spec in char_specs:
                    char_id = spec["char_id"]
                    ref_path = spec.get("ref_path", "")
                    intended_slot = spec.get("intended_slot", "left")

                    if intended_slot == "left":
                        intended_path = left_path
                        other_path = right_path
                    else:
                        intended_path = right_path
                        other_path = left_path

                    ref_emb = ref_embs.get(char_id)

                    if ref_emb is None:
                        # DeepFace unavailable or ref embedding failed
                        result[char_id] = {
                            "binding_score": 0.0,
                            "binding_ok": False,
                            "intended_score": 0.0,
                            "other_score": 0.0,
                            "intended_read_type": "none",
                            "other_read_type": "none",
                            "note": "REF_EMBEDDING_FAILED",
                        }
                        continue

                    intended_read = _figure_read_score(
                        intended_path, ref_emb, ref_name=f"{char_id}_intended"
                    )
                    other_read = _figure_read_score(
                        other_path, ref_emb, ref_name=f"{char_id}_other"
                    )

                    intended_rtype = intended_read["read_type"]
                    other_rtype = other_read["read_type"]

                    intended_score_val = intended_read["score"]  # may be None
                    other_score_val = other_read["score"]         # may be None

                    # Director-decided semantics:
                    if intended_rtype == "none":
                        # No face on the intended side → cannot bind
                        binding_ok = False
                        note = "NO_FACE_INTENDED"
                    elif other_rtype == "none":
                        # Face on intended side, no face on other side →
                        # face is only on the intended side → binds
                        binding_ok = (intended_score_val or 0.0) > 0
                        note = ""
                    else:
                        # Both sides have figure reads — standard delta
                        binding_ok = (intended_score_val or 0.0) > (other_score_val or 0.0)
                        note = ""

                    intended_f = intended_score_val if intended_score_val is not None else 0.0
                    other_f = other_score_val if other_score_val is not None else 0.0
                    binding_score = intended_f - other_f

                    result[char_id] = {
                        "binding_score": binding_score,
                        "binding_ok": binding_ok,
                        "intended_score": intended_f,
                        "other_score": other_f,
                        "intended_read_type": intended_rtype,
                        "other_read_type": other_rtype,
                        "note": note,
                    }

        except Exception as e:
            print(f"   ⚠️ _compute_binding_scores failed: {e}")
            for spec in char_specs:
                cid = spec["char_id"]
                if cid not in result:
                    result[cid] = {
                        "binding_score": 0.0,
                        "binding_ok": False,
                        "intended_score": 0.0,
                        "other_score": 0.0,
                        "intended_read_type": "none",
                        "other_read_type": "none",
                        "note": "ERROR",
                    }

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
        threshold = threshold if threshold is not None else get_threshold_for_shot(shot_type, mode, attempt, max_attempts)
        if not os.path.exists(video_path):
            return self._missing_output_result(shot_type, threshold)
        if not character_configs:
            return self._skipped_result(shot_type, threshold)

        if not DEEPFACE_AVAILABLE:
            return self._vision_llm_validate_video(
                video_path, character_configs, shot_type, threshold,
            )

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
            return self._skipped_result(shot_type, threshold)

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
            return self._missing_output_result(shot_type, threshold, FailureReason.VIDEO_ZERO_FRAMES)

        positions = self._compute_sample_positions(total_frames, fps, shot_type)

        if not positions:
            cap.release()
            return self._skipped_result(shot_type, threshold)

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
            emb_list = _represent_deterministic(image_path)
            if emb_list:
                emb = _largest_ok_embedding(image_path, emb_list)
                if emb is None:
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
            with _cv2_single_thread():
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
                    emb_list = _represent_deterministic(crop_path)
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
                    pass  # Face crop scoring failed — frame skipped; next frame may succeed
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
            emb_list = _represent_deterministic(image_path)
            if emb_list:
                # Score the BEST-matching detected face, not emb_list[0]: on a
                # multi-char frame the gate asks "is this character present",
                # and detection order is arbitrary (first-face scoring read the
                # co-star's face and false-negatived the 2026-06-11 S2 spike
                # two-shots: full-image 0.464 vs the true face's 0.743+).
                similarity = 0.0
                for emb in emb_list:
                    gen_emb = np.array(emb["embedding"])
                    cos_sim = float(np.dot(gen_emb, ref_emb) / (
                        np.linalg.norm(gen_emb) * np.linalg.norm(ref_emb) + 1e-10
                    ))
                    similarity = max(similarity, (1 + cos_sim) / 2)

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
    def _skipped_result(shot_type: str, threshold: float) -> IdentityValidationResult:
        """SKIP: identity genuinely cannot be checked (missing reference, no
        character configured, no face expected). Shot proceeds; not a failure."""
        return IdentityValidationResult(
            passed=True, overall_score=None, character_results={},
            frames_sampled=0, video_duration_seconds=0.0,
            shot_type=shot_type, threshold_used=threshold, skipped=True,
        )

    @staticmethod
    def _missing_output_result(
        shot_type: str,
        threshold: float,
        failure_reason: FailureReason = FailureReason.GENERATED_IMAGE_MISSING,
    ) -> IdentityValidationResult:
        """FAIL: the generated output (image/video) is missing or unreadable — a real
        generation/IO failure that must surface, not silently pass.
        Pass VIDEO_ZERO_FRAMES when the file exists but decoded to 0 frames."""
        return IdentityValidationResult(
            passed=False, overall_score=0.0, character_results={},
            frames_sampled=0, video_duration_seconds=0.0,
            shot_type=shot_type, threshold_used=threshold, skipped=False,
            metadata={"failure_reason": failure_reason.value},
        )

    def _identity_unverified_result(
        self,
        shot_type: str,
        threshold: float,
        character_id: str = "",
        character_name: str = "",
        frame_position_ratio: float = 0.0,
        frames_sampled: int = 1,
        video_duration_seconds: float = 0.0,
        error_reason: str = "identity_check_unavailable",
        issues=None,
    ) -> IdentityValidationResult:
        """FAIL: the identity oracle could not run; never treat as a skip/pass."""
        if issues is None:
            issue_list = ["identity check unavailable"]
        elif isinstance(issues, str):
            issue_list = [issues]
        else:
            issue_list = list(issues)

        failure = FailureReason.IDENTITY_UNVERIFIED
        frame_sample = FrameSample(
            frame_index=0,
            frame_position_ratio=frame_position_ratio,
            face_detected=False,
            face_confidence=0.0,
            face_area_ratio=0.0,
            face_angle_estimate="unknown",
            similarity=0.0,
            matched=False,
            failure_reason=failure,
        )
        char_result = CharacterIdentityResult(
            character_id=character_id,
            character_name=character_name or character_id,
            best_similarity=0.0,
            mean_similarity=0.0,
            min_similarity=0.0,
            frame_results=[frame_sample],
            matched=False,
            primary_failure_reason=failure,
            suggested_pulid_adjustment=self._compute_pulid_delta(0.0, False),
        )
        return IdentityValidationResult(
            passed=False,
            overall_score=0.0,
            character_results={character_id: char_result} if character_id else {},
            frames_sampled=frames_sampled,
            video_duration_seconds=video_duration_seconds,
            shot_type=shot_type,
            threshold_used=threshold,
            skipped=False,
            metadata={
                "failure_reason": failure.value,
                "error_reason": error_reason,
                "issues": issue_list,
            },
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
        if self._vision_fallback is None:
            raise RuntimeError(
                "vision_fallback not configured. Construct IdentityValidator "
                "with vision_fallback=..., or use identity.make_validator()."
            )
        result = self._vision_fallback(reference_path, image_path)

        # Map skip/fail markers from validate_identity_vision to the same
        # policy as the DeepFace path (_skipped_result / _missing_output_result).
        if result.get("skip"):
            return self._skipped_result(shot_type, threshold)
        if result.get("missing_generated"):
            return self._missing_output_result(shot_type, threshold)
        if result.get("error"):
            validation_result = self._identity_unverified_result(
                shot_type=shot_type,
                threshold=threshold,
                character_id=character_id,
                character_name=character_name,
                error_reason=result.get("error_reason", "identity_check_unavailable"),
                issues=result.get("issues"),
            )
            self.history.append(validation_result)
            print(
                "      ❌ Vision-LLM identity: check unavailable "
                f"({validation_result.metadata['error_reason']})"
            )
            return validation_result

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
            return self._missing_output_result(shot_type, threshold, FailureReason.VIDEO_ZERO_FRAMES)

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
        vision_errors = {}
        mid_frame = frame_paths[len(frame_paths) // 2]

        for cfg in character_configs:
            cid = cfg["id"]
            ref_img = cfg.get("reference_image", "")
            char_name = cfg.get("name", cid)

            if not ref_img or not os.path.exists(ref_img):
                continue

            if self._vision_fallback is None:
                raise RuntimeError(
                    "vision_fallback not configured. Construct IdentityValidator "
                    "with vision_fallback=..., or use identity.make_validator()."
                )
            result = self._vision_fallback(ref_img, mid_frame)
            if result.get("error"):
                failure_result = self._identity_unverified_result(
                    shot_type=shot_type,
                    threshold=threshold,
                    character_id=cid,
                    character_name=char_name,
                    frame_position_ratio=0.5,
                    frames_sampled=len(frame_paths),
                    video_duration_seconds=duration,
                    error_reason=result.get("error_reason", "identity_check_unavailable"),
                    issues=result.get("issues"),
                )
                character_results[cid] = failure_result.character_results[cid]
                vision_errors[cid] = {
                    "error_reason": failure_result.metadata["error_reason"],
                    "issues": failure_result.metadata["issues"],
                }
                continue

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
            metadata={
                "failure_reason": FailureReason.IDENTITY_UNVERIFIED.value,
                "vision_errors": vision_errors,
            } if vision_errors else {},
        )

        self.history.append(validation_result)

        for cid, cr in character_results.items():
            icon = "✅" if cr.matched else "❌"
            reason_str = f" [{cr.primary_failure_reason.value}]" if not cr.matched else ""
            print(f"      {icon} {cr.character_name}: confidence={cr.best_similarity:.3f} (threshold={threshold}){reason_str}")

        return validation_result
