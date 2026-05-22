"""
Face Validator Gate — scores generated candidates and decides early-halt.

Used by quality_max.generate_ai_broll_max for the N=8 adaptive halt strategy:

  1. Generate a batch of candidates with different seeds.
  2. Score each: composite = w_arc * ArcFace_sim + w_aes * AestheticV2.
  3. If best composite >= halt_threshold AND best ArcFace >= arc_threshold
     AND minimum candidate count met, halt early.
  4. Otherwise generate another batch.
  5. Return the best candidate (or trigger regenerate if best ArcFace < floor).

ArcFace similarity comes from the existing IdentityValidator (identity/validator.py).
Aesthetic v2 comes from LAION's CLIP+MLP scorer. Both gracefully degrade to
neutral scores when their models aren't available — the gate still works on
ArcFace alone, just with less discrimination on the aesthetic axis.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

# --- ArcFace similarity (reuse existing IdentityValidator) -----------------
try:
    from identity.validator import IdentityValidator
    from phase_c_vision import validate_identity_vision
    _ARC_AVAILABLE = True
except Exception as _e_arc:
    _ARC_AVAILABLE = False
    _arc_import_error = str(_e_arc)


# --- Aesthetic v2 (LAION CLIP+MLP scorer, lazy-loaded) ---------------------
_AES_MODEL = None
_AES_PROCESSOR = None
_AES_TRIED_LOAD = False


def _try_load_aesthetic_v2():
    """Lazy-load LAION Aesthetic Predictor v2. Sets module globals on success.

    Strategy: try the `simple-aesthetics-predictor` package first (cleanest API).
    Falls back to manual CLIP-L + MLP if that's not installed. Returns True on
    success, False on any failure (so callers know to skip aesthetic scoring).
    """
    global _AES_MODEL, _AES_PROCESSOR, _AES_TRIED_LOAD
    if _AES_TRIED_LOAD:
        return _AES_MODEL is not None
    _AES_TRIED_LOAD = True

    try:
        from aesthetics_predictor import AestheticsPredictorV2Linear
        from transformers import CLIPProcessor
        _AES_MODEL = AestheticsPredictorV2Linear.from_pretrained(
            "shunk031/aesthetics-predictor-v2-sac-logos-ava1-l14-linearMSE"
        )
        _AES_PROCESSOR = CLIPProcessor.from_pretrained(
            "openai/clip-vit-large-patch14"
        )
        _AES_MODEL.train(False)
        print("[FaceGate] Aesthetic v2 loaded (LAION SAC+LOGOS+AVA1 linearMSE)")
        return True
    except Exception as e:
        print(f"[FaceGate] Aesthetic v2 unavailable ({e}). "
              f"Composite scoring will use ArcFace only.")
        return False


def _aesthetic_score(image_path: str) -> Optional[float]:
    """Score an image's aesthetic quality on [0, 10] (LAION v2 scale).

    Returns a normalized [0, 1] float (raw_score / 10) or None if scorer
    isn't available. The 0-10 scale is LAION's: ~5 = average, 6+ = good,
    7+ = excellent.
    """
    if not _try_load_aesthetic_v2():
        return None
    try:
        from PIL import Image
        import torch
        img = Image.open(image_path).convert("RGB")
        inputs = _AES_PROCESSOR(images=img, return_tensors="pt")
        with torch.no_grad():
            raw = _AES_MODEL(**inputs).logits.squeeze().item()
        return max(0.0, min(1.0, raw / 10.0))
    except Exception as e:
        print(f"[FaceGate] Aesthetic score failed for {os.path.basename(image_path)}: {e}")
        return None


def _arcface_score(image_path: str, reference_path: str) -> Optional[float]:
    """ArcFace cosine similarity in [0, 1]. None on failure / no face."""
    if not _ARC_AVAILABLE:
        return None
    try:
        validator = IdentityValidator(vision_fallback=validate_identity_vision)
        result = validator.validate_image(image_path, reference_path, threshold=0.0)
        return float(result.overall_score)
    except Exception as e:
        print(f"[FaceGate] ArcFace failed for {os.path.basename(image_path)}: {e}")
        return None


# ---------------------------------------------------------------------------
# Scoring API
# ---------------------------------------------------------------------------

@dataclass
class CandidateScore:
    """Score components for one generated candidate."""
    image_path: str
    seed: int
    arc_score: float = 0.0           # [0, 1] ArcFace cosine similarity
    aesthetic_score: float = 0.5     # [0, 1] LAION Aesthetic v2 normalized
    composite: float = 0.0           # weighted blend (see DEFAULT_WEIGHTS)
    has_arc: bool = False
    has_aesthetic: bool = False


# Default composite weights. Override per call if needed.
DEFAULT_WEIGHTS = {"arc": 0.6, "aesthetic": 0.4}


def score_candidate(
    image_path: str,
    face_anchor: Optional[str],
    weights: Optional[dict] = None,
) -> CandidateScore:
    """Score a single candidate image against the face anchor.

    Args:
        image_path: Generated candidate to score.
        face_anchor: Path to reference face image. If None, ArcFace is skipped
            (landscape shots, no-character shots).
        weights: {"arc": float, "aesthetic": float}. Defaults to 0.6/0.4.

    Returns CandidateScore with arc, aesthetic, and composite filled.
    Missing scores fall back to a neutral value (0.5) for the composite so
    the candidate isn't unfairly penalized.
    """
    w = weights or DEFAULT_WEIGHTS
    score = CandidateScore(image_path=image_path, seed=-1)

    if face_anchor and os.path.exists(face_anchor):
        arc = _arcface_score(image_path, face_anchor)
        if arc is not None:
            score.arc_score = arc
            score.has_arc = True

    aes = _aesthetic_score(image_path)
    if aes is not None:
        score.aesthetic_score = aes
        score.has_aesthetic = True

    # Composite: if one component is missing, replace with neutral 0.5 so
    # the present component still drives selection.
    arc_contrib = score.arc_score if score.has_arc else 0.5
    aes_contrib = score.aesthetic_score if score.has_aesthetic else 0.5
    score.composite = w["arc"] * arc_contrib + w["aesthetic"] * aes_contrib
    return score


# ---------------------------------------------------------------------------
# Adaptive halt
# ---------------------------------------------------------------------------

@dataclass
class HaltDecision:
    halt: bool
    reason: str
    best: Optional[CandidateScore] = None


def should_halt(
    scores: List[CandidateScore],
    halt_threshold_composite: float = 0.92,
    halt_threshold_arc: float = 0.85,  # retained for back-compat / logging
    halt_min_n: int = 4,
    halt_max_n: int = 8,
    has_character: bool = True,
) -> HaltDecision:
    """Decide whether N=8 best-of generation can stop early.

    Composite-only rule (Option 2):
      - If we've hit halt_max_n, stop regardless (budget exhausted).
      - If we've generated >= halt_min_n AND best.composite >= halt_threshold_composite
        -> halt with success.
      - Otherwise -> keep going.

    Identity is NOT gated separately at halt time — it's already folded into
    the composite via the 0.6 weight in DEFAULT_WEIGHTS. A high composite with
    a low arc means the aesthetic score lifted the average; that candidate
    can still fail the regenerate_floor_arc check in needs_regenerate() and
    trigger a PuLID-boost retry. So the two stages stay decoupled: halt =
    "is the best of the batch good enough?"; regenerate = "is the best of
    the batch identity-acceptable?".

    halt_threshold_arc is retained so callers can log/audit what arc bar was
    expected, even though it's not enforced here.
    """
    if not scores:
        return HaltDecision(halt=False, reason="no candidates yet")

    best = max(scores, key=lambda s: s.composite)
    n = len(scores)

    if n >= halt_max_n:
        return HaltDecision(halt=True, reason=f"budget exhausted (n={n})", best=best)

    if n < halt_min_n:
        return HaltDecision(halt=False, reason=f"below halt_min_n ({n} < {halt_min_n})", best=best)

    if best.composite >= halt_threshold_composite:
        return HaltDecision(
            halt=True,
            reason=(f"composite threshold met (composite={best.composite:.3f} >= "
                    f"{halt_threshold_composite:.2f}, arc={best.arc_score:.3f} "
                    f"[informational, not gated], n={n})"),
            best=best,
        )

    return HaltDecision(
        halt=False,
        reason=f"composite below threshold (composite={best.composite:.3f} < {halt_threshold_composite:.2f}, n={n})",
        best=best,
    )


def select_best(scores: List[CandidateScore]) -> Optional[CandidateScore]:
    """Pick the highest-composite candidate. None if scores is empty."""
    if not scores:
        return None
    return max(scores, key=lambda s: s.composite)


def needs_regenerate(
    best: CandidateScore,
    regenerate_floor_arc: float,
    has_character: bool,
) -> bool:
    """True if even the best candidate failed the identity floor and we should
    regenerate with a PuLID weight boost.

    For non-character shots (landscape, environment) this always returns False
    since there's no face to validate against.
    """
    if not has_character:
        return False
    if not best.has_arc:
        return False
    return best.arc_score < regenerate_floor_arc
