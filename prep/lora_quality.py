"""LoRA quality gate + auto-retrain control loop.

See docs/superpowers/specs/2026-06-03-validate-lora-quality-design.md for design + rationale.

Units:
  _next_lora_action(...)        -> pure policy decision (no IO)
  _generate_with_lora(...)      -> one honest ComfyUI generation (no N=8 best-of)
  validate_lora_quality(...)    -> scoring oracle: sweep strengths, ArcFace-score vs reference
  train_character_lora_gated(.) -> orchestrator: train -> validate -> decide -> persist best
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class LoraAction(Enum):
    ACCEPT = "accept"                   # register best (caller warns if best < threshold)
    RETRY_MORE_STEPS = "retry_more_steps"
    RETRY_HIGHER_RANK = "retry_higher_rank"
    REJECT = "reject"                   # do NOT register; PuLID-only fallback


@dataclass
class StrengthScore:
    strength: float
    mean_arc: Optional[float]           # mean arc_score across prompts; None if all samples skipped
    per_prompt: list[tuple[str, Optional[float]]] = field(default_factory=list)  # [(label, arc_score|None), ...]


@dataclass
class LoraQualityResult:
    best_score: Optional[float]         # mean_arc at best strength; None if skipped
    best_strength: Optional[float]      # argmax strength; None if skipped
    sweep: list[StrengthScore] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


def _next_lora_action(attempt: int, best_score: Optional[float], *,
                      threshold: float, baseline: float, budget: int) -> LoraAction:
    """Pure policy. `attempt` is the 0-based index of the train just validated;
    `budget` is the max number of trains. Implements decision D3 (spec section 3/6.3)."""
    if best_score is None:                      # validation skipped -> register unvalidated
        return LoraAction.ACCEPT
    if best_score >= threshold:
        return LoraAction.ACCEPT
    if attempt + 1 >= budget:                   # retrain budget exhausted
        return LoraAction.ACCEPT if best_score >= baseline else LoraAction.REJECT
    return LoraAction.RETRY_MORE_STEPS if attempt == 0 else LoraAction.RETRY_HIGHER_RANK


# ---------------------------------------------------------------------------
# Task 2 — lazy wrappers + _generate_with_lora
# ---------------------------------------------------------------------------
# All quality_max / phase_c_assembly / workflow_selector imports are inside
# the _qm_* wrappers so that `import prep.lora_quality` stays light and the
# pure-fn tests never pull the heavy ComfyUI stack.

def _qm_load_max_workflow():
    from quality_max import _load_max_workflow
    return _load_max_workflow()


def _qm_inject_identity(*a, **k):
    from quality_max import _inject_identity
    return _inject_identity(*a, **k)


def _qm_inject_conditioning(*a, **k):
    from quality_max import _inject_conditioning
    return _inject_conditioning(*a, **k)


def _qm_inject_sampling(*a, **k):
    from quality_max import _inject_sampling
    return _inject_sampling(*a, **k)


def _qm_run_one_candidate(*a, **k):
    from quality_max import _run_one_candidate
    return _run_one_candidate(*a, **k)


def _make_comfy(url: str):
    # NOTE: RunPodComfyUI lives in phase_c_assembly (imported into quality_max
    # at line 60 as `from phase_c_assembly import RunPodComfyUI`); we import
    # from the canonical source directly.
    from phase_c_assembly import RunPodComfyUI
    return RunPodComfyUI(url)


def _default_max_params(shot_type: str = "portrait") -> dict:
    """Tier params baseline — the SAME source generate_ai_broll_max uses
    (`params = get_max_quality_params(shot_type)`).

    NOTE: get_max_quality_params is in workflow_selector (imported into
    quality_max at line 57 as `from workflow_selector import ..., get_max_quality_params`);
    we import from the canonical source directly.
    """
    from workflow_selector import get_max_quality_params
    return dict(get_max_quality_params(shot_type))


def _generate_with_lora(lora_path: str, prompt: str, *, strength: float, seed: int,
                        out_path: str, comfyui_url: str) -> Optional[str]:
    """ONE honest ComfyUI generation with `lora_path` at `strength`.  No best-of,
    no ArcFace gating.  Returns image path or None on any infra failure (never
    raises).

    Assembly order mirrors generate_ai_broll_max:
      load -> inject_identity -> inject_conditioning -> inject_sampling -> run_one
    """
    try:
        wf = _qm_load_max_workflow()
        params = {**_default_max_params(),
                  "lora_strength_model": strength,
                  "lora_strength_clip": strength,
                  "seed": seed}
        # _inject_identity(workflow, char_lora, face_anchor_remote, params, has_character)
        _qm_inject_identity(wf, lora_path, None, params, True)
        # _inject_conditioning(workflow, prompt, prev_shot_remote, style_remote, params, has_character)
        _qm_inject_conditioning(wf, prompt, None, None, params, True)
        _qm_inject_sampling(wf, params)
        # _inject_sampling does NOT touch the seed; generate_ai_broll_max sets it
        # directly on node 25 (quality_max.py:884 `wf["25"]["inputs"]["noise_seed"]`).
        # Mirror that so per-prompt seeds actually vary the output and the validation
        # score is reproducible — otherwise every gen reuses the template's baked seed.
        if "25" in wf:
            wf["25"]["inputs"]["noise_seed"] = seed
        comfy = _make_comfy(comfyui_url)  # RunPodComfyUI is stateless (request-per-call) — no close() needed
        return _qm_run_one_candidate(comfy, wf, out_path)
    except Exception as e:
        # Swallow-and-skip is required (never crash training), but keep the traceback
        # for diagnosis (Lane V #13 M-3 pattern) instead of a bare print.
        logger.error("[lora_quality] generation failed (%s); treating as skip", e, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Task 3 — validate_lora_quality (scoring oracle)
# ---------------------------------------------------------------------------

DEFAULT_STRENGTH_SWEEP = [0.45, 0.55, 0.7, 1.0]
DEFAULT_VALIDATION_PROMPTS = [
    "{trigger} photo, professional headshot, soft natural light",
    "{trigger} photo, full body, daylight, casual outfit",
    "{trigger} portrait, side profile, indoor window light",
]
_VALIDATION_SEEDS = [101, 202, 303]   # fixed per-prompt seeds for reproducibility


def _score_candidate(image_path: str, anchor: str):
    from face_validator_gate import score_candidate
    return score_candidate(image_path, anchor)   # threshold=0.0 default -> just scores


def _resolve_comfyui_url(comfyui_url: Optional[str]) -> str:
    if comfyui_url:
        return comfyui_url
    from config.settings import get_settings  # cached singleton; same object quality_max uses
    return get_settings().comfyui_server_url


def validate_lora_quality(lora_path, character, *, strengths=None, prompts=None,
                          comfyui_url=None) -> LoraQualityResult:
    """Scoring oracle: sweep strengths x prompts, ArcFace-score each generation vs the
    character's canonical_reference, pick the best strength. See spec section 6.2."""
    anchor = (character.get("canonical_reference") or "")
    if not anchor or not os.path.exists(anchor):
        return LoraQualityResult(None, None, skipped=True, skip_reason="no_canonical_reference")

    trigger = character.get("trigger_token") or f"<{character['id']}>"
    strengths = strengths or DEFAULT_STRENGTH_SWEEP
    prompt_tmpls = prompts or DEFAULT_VALIDATION_PROMPTS
    url = _resolve_comfyui_url(comfyui_url)

    # Generated validation images are transient: write them to a temp dir, score
    # in-loop, then discard — don't litter cwd/repo root (quality_max writes wherever
    # out_path points, so we own the location). Images are consumed before cleanup.
    tmpdir = tempfile.mkdtemp(prefix="loraval_")
    sweep = []
    try:
        for strength in strengths:
            sample_scores = []
            per_prompt = []
            for i, tmpl in enumerate(prompt_tmpls):
                prompt = tmpl.format(trigger=trigger) if "{trigger}" in tmpl else f"{trigger} {tmpl}"
                seed = _VALIDATION_SEEDS[i % len(_VALIDATION_SEEDS)]
                out_path = os.path.join(tmpdir, f"loraval_{character['id']}_{strength:.2f}_{i}.png")
                img = _generate_with_lora(lora_path, prompt, strength=strength, seed=seed,
                                          out_path=out_path, comfyui_url=url)
                arc = None
                if img:
                    sc = _score_candidate(img, anchor)
                    if getattr(sc, "has_arc", False):
                        arc = sc.arc_score
                if arc is not None:
                    sample_scores.append(arc)
                per_prompt.append((tmpl, arc))
            mean_arc = (sum(sample_scores) / len(sample_scores)) if sample_scores else None
            sweep.append(StrengthScore(strength=strength, mean_arc=mean_arc, per_prompt=per_prompt))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    scored = [s for s in sweep if s.mean_arc is not None]
    if not scored:
        return LoraQualityResult(None, None, sweep=sweep, skipped=True,
                                 skip_reason="generation_or_scoring_unavailable")
    best = max(scored, key=lambda s: s.mean_arc)
    return LoraQualityResult(best_score=best.mean_arc, best_strength=best.strength, sweep=sweep)


# ---------------------------------------------------------------------------
# Task 4 — train_character_lora_gated (orchestrator)
# ---------------------------------------------------------------------------

PASS_THRESHOLD = 0.6
NET_NEGATIVE_BASELINE = 0.45
MAX_LORA_TRAIN_ATTEMPTS = 3
_BASE_STEPS = 3000      # mirror DEFAULT_TRAIN_CONFIG["steps"] (prep/lora_training.py:103)
_HIGHER_RANK = 64       # escalate from base 32 (prep/lora_training.py:100)


def _train_character_lora(project_dir, character, *, config_overrides=None):
    from prep.lora_training import train_character_lora
    return train_character_lora(project_dir, character, config_overrides=config_overrides)


def _escalate_config(config: dict, action: LoraAction) -> dict:
    nxt = dict(config)
    if action is LoraAction.RETRY_MORE_STEPS:
        nxt["steps"] = int(nxt.get("steps", _BASE_STEPS) * 1.5)
    elif action is LoraAction.RETRY_HIGHER_RANK:
        nxt["rank"] = _HIGHER_RANK
        nxt["alpha"] = _HIGHER_RANK
    return nxt


def _gated_result(train: dict, *, score, strength, lora_path, warning, rejected,
                  skipped=False, skip_reason="", attempts=1) -> dict:
    # NOTE: train["quality_score"] is the single-train stub value (None); we always
    # REPLACE it with the validated score (or None when skipped) — the clobber is
    # deliberate, not a bug. The orchestrator owns quality_score, not the trainer.
    out = dict(train)
    out.update(lora_path=lora_path, quality_score=score, best_strength=strength,
               quality_warning=warning, rejected=rejected, skipped=skipped,
               skip_reason=skip_reason, attempts=attempts)
    return out


def train_character_lora_gated(project_dir, character, *, config_overrides=None) -> dict:
    """Train -> validate -> decide loop (spec section 6.4). Persists nothing itself;
    returns the best result + quality_warning + rejected for the caller to register."""
    best = None   # (score, strength, lora_path)
    config = dict(config_overrides or {})
    for attempt in range(MAX_LORA_TRAIN_ATTEMPTS):
        train = _train_character_lora(project_dir, character, config_overrides=config)
        if not train.get("success"):
            return train                                  # infra/train error -> surface, NO retrain
        result = validate_lora_quality(train["lora_path"], character)
        if result.skipped:                                # no GPU/anchor -> register unvalidated
            return _gated_result(train, score=None, strength=None, lora_path=train["lora_path"],
                                 warning=False, rejected=False, skipped=True,
                                 skip_reason=result.skip_reason, attempts=attempt + 1)
        if best is None or result.best_score > best[0]:
            best = (result.best_score, result.best_strength, train["lora_path"])
        action = _next_lora_action(attempt, best[0], threshold=PASS_THRESHOLD,
                                   baseline=NET_NEGATIVE_BASELINE, budget=MAX_LORA_TRAIN_ATTEMPTS)
        if action is LoraAction.ACCEPT:
            return _gated_result(train, score=best[0], strength=best[1], lora_path=best[2],
                                 warning=best[0] < PASS_THRESHOLD, rejected=False, attempts=attempt + 1)
        if action is LoraAction.REJECT:
            return _gated_result(train, score=best[0], strength=best[1], lora_path=best[2],
                                 warning=True, rejected=True, attempts=attempt + 1)
        config = _escalate_config(config, action)
    # Unreachable (budget-exhausted branch always ACCEPT/REJECTs), but be safe:
    return _gated_result(train, score=best[0], strength=best[1], lora_path=best[2],
                         warning=best[0] < PASS_THRESHOLD, rejected=best[0] < NET_NEGATIVE_BASELINE,
                         attempts=MAX_LORA_TRAIN_ATTEMPTS)
