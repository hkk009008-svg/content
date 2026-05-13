"""Cinema Production Tool — Shared Pipeline Context (loader)

Single source of truth for all LLM components. Every LLM in the pipeline
(Scene Decomposer, Chief Director, Dialogue Writer, Style Director, Phase 0
Director, Vision validators) imports `PIPELINE_CONTEXT` and appends it to
its system prompt.

The content lives in `config/prompts/pipeline_context.md` — edit that file
to update pipeline behavior. All LLMs pick it up automatically on next run.
"""

from pathlib import Path

_CONTEXT_FILE = Path(__file__).resolve().parent / "config" / "prompts" / "pipeline_context.md"
PIPELINE_CONTEXT = "\n" + _CONTEXT_FILE.read_text() + "\n"
