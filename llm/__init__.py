"""Cinema Pipeline — LLM package.

Consolidates the LLM-facing modules under a single namespace:

  llm.ensemble           — multi-model competitive generation + judging
  llm.chief_director     — meta-cognitive output reviewer
  llm.blueprint_director — production-blueprint generator (was phase_0_director)
  llm.style_director     — per-project style rules

Public re-exports below are the high-traffic ones. Import a submodule
directly if you need internals.
"""

from llm.ensemble import LLMEnsemble, EnsembleResult, EnsembleQualityResult
from llm.chief_director import ChiefDirector
from llm.blueprint_director import generate_production_blueprint
from llm.style_director import generate_style_rules, style_rules_to_prompt_suffix

__all__ = [
    "LLMEnsemble",
    "EnsembleResult",
    "EnsembleQualityResult",
    "ChiefDirector",
    "generate_production_blueprint",
    "generate_style_rules",
    "style_rules_to_prompt_suffix",
]
