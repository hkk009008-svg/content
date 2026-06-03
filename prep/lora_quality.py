"""LoRA quality gate + auto-retrain control loop.

See docs/superpowers/specs/2026-06-03-validate-lora-quality-design.md for design + rationale.

Units:
  _next_lora_action(...)        -> pure policy decision (no IO)
  _generate_with_lora(...)      -> one honest ComfyUI generation (no N=8 best-of)
  validate_lora_quality(...)    -> scoring oracle: sweep strengths, ArcFace-score vs reference
  train_character_lora_gated(.) -> orchestrator: train -> validate -> decide -> persist best
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


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
        comfy = _make_comfy(comfyui_url)
        return _qm_run_one_candidate(comfy, wf, out_path)
    except Exception as e:
        print(f"[lora_quality] generation failed ({e}); treating as skip")
        return None
