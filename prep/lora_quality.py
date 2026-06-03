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
    per_prompt: list = field(default_factory=list)  # [(label, arc_score|None), ...]


@dataclass
class LoraQualityResult:
    best_score: Optional[float]         # mean_arc at best strength; None if skipped
    best_strength: Optional[float]      # argmax strength; None if skipped
    sweep: list = field(default_factory=list)        # list[StrengthScore]
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
