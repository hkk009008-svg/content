"""BlueprintPhase — generates the master production blueprint from a topic.

Wraps `llm.blueprint_director.generate_production_blueprint(ctx: dict) -> bool`
in the Phase protocol.

This phase runs AFTER TopicPhase: it reads `ctx.topic` and writes the
Chief Director's structured production plan into `ctx.production_blueprint`.
The blueprint includes director_vision, cinematography_rules,
color_grading_palette, sound_design_and_music, and hero_subject — all
consumed by downstream phases (script generation, scene decomposition,
style direction).

Design note
===========

We import `generate_production_blueprint` lazily inside `run()` so the
cinema package can be imported without pulling the LLM stack (OpenAI,
Tavily, Firecrawl) into memory. This matters in environments where the
cinema package is being exercised for protocol-conformance tests but the
LLM stack isn't installed.
"""

from __future__ import annotations

import time
import traceback

from cinema.context import PipelineContext
from cinema.phases.base import PhaseResult


class BlueprintPhase:
    """Pipeline phase that generates the master production blueprint."""

    name = "blueprint"

    def run(self, ctx: PipelineContext) -> PhaseResult:
        from llm.blueprint_director import generate_production_blueprint

        start = time.time()
        try:
            ok = generate_production_blueprint(ctx)
            message = "" if ok else "blueprint generation returned False"
        except Exception as exc:
            ok = False
            message = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()

        return PhaseResult(
            ok=ok,
            message=message,
            elapsed_s=time.time() - start,
        )
