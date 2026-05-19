"""CinemaPipeline — the thin driver over a list of Phase instances.

End-game of Phase 5: this driver replaces the 1,526-line
`cinema_pipeline.py` god module's orchestration logic for non-interactive
pipeline runs (the `main.py:run_autonomous_pipeline` path).

The legacy `cinema_pipeline.CinemaPipeline` class (used by
`web_server.py` for interactive sessions) remains in place — that
orchestration path includes operator review gates, pause/resume control,
and per-shot progress streaming that don't fit the simple iterate-phases
model. Migrating it is a separate concern, post-Phase-5.

Design
======

The driver knows three things:

  1. A **list of phases** to run, in order. Order is the caller's
     concern — the driver doesn't sort, reorder, or skip.
  2. A **PipelineContext** instance threaded through all phases.
  3. An optional **progress callback** invoked after each phase. The
     default callback prints phase-completion banners to stdout. Pass
     `progress_callback=lambda *a, **k: None` to silence.

What the driver does NOT do
===========================

  * Retry policy. If a phase returns ok=False, the driver stops. Retries
    are the phase's responsibility (or a wrapper phase's).
  * Skip / conditional execution. Conditional phases are the caller's job
    (build different phase lists for different code paths).
  * Side effects on PipelineContext beyond what phases do.
  * Per-shot inner loops — those aren't phases. The caller interleaves
    driver runs with non-phase code as needed.

Example
=======

    from cinema.context import PipelineContext
    from cinema.pipeline import CinemaPipeline
    from cinema.phases.blueprint import BlueprintPhase
    from cinema.phases.generation import GenerationPhase

    ctx = PipelineContext(topic="...", language="English")
    result = CinemaPipeline(
        phases=[BlueprintPhase(), GenerationPhase()],
        ctx=ctx,
    ).run()
    if not result.ok:
        print(f"failed at {result.failed_phase}: {result.failed_message}")
        return
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from cinema.context import PipelineContext
from cinema.phases.base import Phase, PhaseResult


ProgressCallback = Callable[[str, PhaseResult], None]


def _default_progress(name: str, result: PhaseResult) -> None:
    """Print phase-completion banners to stdout.

    Replaces ad-hoc inline `print("--- [PHASE X] ---")` lines scattered
    across the legacy pipeline. The driver emits a uniform line per
    phase using its `name`.
    """
    icon = "✓" if result.ok else "✗"
    print(f"{icon} [{name.upper()}] {result.message} ({result.elapsed_s:.1f}s)")


@dataclass
class PipelineRunResult:
    """Aggregate result of a driver run.

    Attributes
    ----------
    ok : bool
        True iff every phase returned ok=True. False if any phase
        short-circuited the run.
    failed_phase : Optional[str]
        Name of the phase that returned ok=False, if any.
    failed_message : str
        That phase's PhaseResult.message, for diagnosis.
    phase_results : list[tuple[str, PhaseResult]]
        Every phase that ran (including the failed one if there was one),
        in execution order. Useful for cost/perf accounting.
    """

    ok: bool
    failed_phase: Optional[str] = None
    failed_message: str = ""
    phase_results: List[Tuple[str, PhaseResult]] = field(default_factory=list)


class CinemaPipeline:
    """Iterate a list of Phase instances over a shared PipelineContext.

    The driver runs phases in order, short-circuiting on the first
    ok=False return. After each phase the progress callback is invoked
    (default: prints a one-line banner). The PipelineContext is mutated
    in place by each phase; the same context object flows through the
    whole run.
    """

    def __init__(
        self,
        phases: List[Phase],
        ctx: PipelineContext,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        self.phases = phases
        self.ctx = ctx
        self._progress = progress_callback or _default_progress

    def run(self) -> PipelineRunResult:
        results: List[Tuple[str, PhaseResult]] = []
        for phase in self.phases:
            print(f"\n--- [{phase.name.upper()}] ---")
            phase_result = phase.run(self.ctx)
            results.append((phase.name, phase_result))
            self._progress(phase.name, phase_result)
            if not phase_result.ok:
                return PipelineRunResult(
                    ok=False,
                    failed_phase=phase.name,
                    failed_message=phase_result.message,
                    phase_results=results,
                )
        return PipelineRunResult(ok=True, phase_results=results)
