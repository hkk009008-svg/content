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
import threading
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


# IdentityValidator is now a process-singleton wired via
# identity.get_shared_validator (see identity/__init__.py). No local cache
# needed — the factory handles thread-safety + lazy load.


# --- Aesthetic v2 (LAION CLIP+MLP scorer, lazy-loaded) ---------------------
_AES_MODEL = None
_AES_PROCESSOR = None
_AES_TRIED_LOAD = False
_AES_LOCK = threading.Lock()


def _try_load_aesthetic_v2():
    """Lazy-load LAION Aesthetic Predictor v2. Sets module globals on success.

    Strategy: try the `simple-aesthetics-predictor` package first (cleanest API).
    Falls back to manual CLIP-L + MLP if that's not installed. Returns True on
    success, False on any failure (so callers know to skip aesthetic scoring).

    Thread-safe: two concurrent shots could both reach _try_load before either
    finishes; the lock serializes the import + model load.
    """
    global _AES_MODEL, _AES_PROCESSOR, _AES_TRIED_LOAD
    with _AES_LOCK:
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


def _get_validator() -> Optional["IdentityValidator"]:
    """Return the process-singleton IdentityValidator, or None if ArcFace unavailable.

    Delegates to identity.get_shared_validator so this gate and the other
    two identity consumers (phase_c_vision, performance.identity_gate)
    share one instance: ArcFace weights load once, and rolling-stats
    history accumulates signal from all three contexts.
    """
    if not _ARC_AVAILABLE:
        return None
    try:
        from identity import get_shared_validator
        return get_shared_validator()
    except Exception as e:
        print(f"[FaceGate] IdentityValidator init failed: {e}")
        return None


def _arcface_score(
    image_path: str,
    reference_path: str,
    threshold: float = 0.0,
) -> Optional[float]:
    """ArcFace cosine similarity in [0, 1]. None on failure / no face.

    `threshold` is forwarded to `IdentityValidator.validate_image` so the
    `passed=score >= threshold` flag on the rolling-history entry reflects
    actual acceptance. Default 0.0 preserves the historical "always passed"
    behavior for callers that haven't been updated yet; new callers should
    pass the project's `identity_strictness` (or shot-type threshold) so
    `get_rolling_stats(...).success_rate` becomes a meaningful signal for
    `get_adaptive_pulid_weight`.
    """
    validator = _get_validator()
    if validator is None:
        return None
    try:
        result = validator.validate_image(image_path, reference_path, threshold=threshold)
        if result.overall_score is None:        # skipped: no comparable face
            return None
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
    threshold: float = 0.0,
) -> CandidateScore:
    """Score a single candidate image against the face anchor.

    Args:
        image_path: Generated candidate to score.
        face_anchor: Path to reference face image. If None, ArcFace is skipped
            (landscape shots, no-character shots).
        weights: {"arc": float, "aesthetic": float}. Defaults to 0.6/0.4.
        threshold: Pass-through to `_arcface_score` -> `IdentityValidator.
            validate_image`. The `passed` flag on the resulting rolling-history
            entry reflects whether the candidate met this bar. Default 0.0
            preserves prior "always passed" behavior; callers should pass a
            non-zero value (typically `identity_strictness`) so rolling-stats
            `success_rate` becomes a meaningful signal.

    Returns CandidateScore with arc, aesthetic, and composite filled.
    Missing scores fall back to a neutral value (0.5) for the composite so
    the candidate isn't unfairly penalized.
    """
    w = weights or DEFAULT_WEIGHTS
    score = CandidateScore(image_path=image_path, seed=-1)

    if face_anchor and os.path.exists(face_anchor):
        arc = _arcface_score(image_path, face_anchor, threshold=threshold)
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
    halt_threshold_arc: float = 0.85,
    halt_min_n: int = 4,
    halt_max_n: int = 8,
    has_character: bool = True,          # informational — see docstring
    halt_rule: str = "composite_only",
) -> HaltDecision:
    """Decide whether N=8 best-of generation can stop early.

    halt_rule governs the QUALITY early-halt check (n >= halt_min_n branch).
    The budget halt (n >= halt_max_n) is unconditional for all modes.

    Supported values:
      'composite_only' (default):
        Halt when composite >= halt_threshold_composite. Arc is informational.
      'conjunctive':
        Halt when composite >= halt_threshold_composite AND
        arc >= halt_threshold_arc. Enforces an identity floor — but only when
        there is an identity to gate: the floor is skipped (auto-satisfied) for
        non-character shots and candidates without an ArcFace score, so they
        halt on composite alone instead of burning the full budget.
      'budget_only':
        # budget_only: deferred — falls back to composite_only.
        Behaves identically to 'composite_only'. Distinct "never-early-halt"
        semantics deferred pending user decision.

    has_character: enforced in the 'conjunctive' branch as an identity-floor
    bypass for non-character shots; informational (reason string only) for the
    other modes.
    """
    if not scores:
        return HaltDecision(halt=False, reason="no candidates yet")

    best = max(scores, key=lambda s: s.composite)
    n = len(scores)

    if n >= halt_max_n:
        return HaltDecision(halt=True, reason=f"budget exhausted (n={n})", best=best)

    if n < halt_min_n:
        return HaltDecision(halt=False, reason=f"below halt_min_n ({n} < {halt_min_n})", best=best)

    if halt_rule == "conjunctive":
        # Composite must pass; the arc identity-floor applies ONLY when there's an
        # identity to gate. For non-character shots (or candidates with no ArcFace
        # score) the floor is auto-satisfied — otherwise such shots could never
        # early-halt and would burn the full N-budget. Mirrors needs_regenerate's
        # has_character/has_arc guard.
        composite_ok = best.composite >= halt_threshold_composite
        arc_floor_bypassed = (not has_character) or (not best.has_arc)
        arc_ok = arc_floor_bypassed or best.arc_score >= halt_threshold_arc
        if composite_ok and arc_ok:
            # When the floor is bypassed, arc_score may be 0.0 — say so rather than
            # printing a misleading "arc=0.000 >= 0.85".
            arc_clause = (
                "arc floor bypassed: no_identity"
                if arc_floor_bypassed
                else f"arc={best.arc_score:.3f} >= {halt_threshold_arc:.2f}"
            )
            return HaltDecision(
                halt=True,
                reason=(f"conjunctive threshold met (composite={best.composite:.3f} >= "
                        f"{halt_threshold_composite:.2f}, {arc_clause}, n={n})"),
                best=best,
            )
        return HaltDecision(
            halt=False,
            reason=(f"conjunctive threshold not met (composite={best.composite:.3f}, "
                    f"composite_ok={composite_ok}, arc={best.arc_score:.3f}, "
                    f"arc_ok={arc_ok}, n={n})"),
            best=best,
        )

    # composite_only / budget_only (deferred) / unknown → composite-only behavior
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
