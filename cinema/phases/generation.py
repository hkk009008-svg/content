"""GenerationPhase — script-generation pass, the POC for the Phase protocol.

Wraps the legacy `phase_a_generator.generate_shorts_script(ctx: dict) -> bool`
function in the `Phase` protocol contract introduced in this commit.

Why this phase first
====================

`generate_shorts_script` is the cleanest possible POC target:

* Single public function, single positional arg, single bool return.
* Already operates on the `ctx: dict` pattern the entire pipeline uses.
* Bool return maps trivially to `PhaseResult.ok`.

Behavior preservation
=====================

This wrapper does NOT change generation behavior. It only:

  1. Times the call.
  2. Catches exceptions and surfaces them via `PhaseResult.message`
     (the legacy function already returns False on internal failure; we
     extend that to crashes from its dependencies).
  3. Passes the `PipelineContext` through — which is dict-API compatible,
     so the legacy function uses `ctx["topic"]` / `ctx.get(...)` unchanged.

Future migration: a later sub-commit will refactor `generate_shorts_script`
itself to consume the typed `PipelineContext` directly, after which this
wrapper becomes a 4-line method on the phase class.
"""

from __future__ import annotations

import time
import traceback

from cinema.context import PipelineContext
from cinema.phases.base import PhaseResult


class GenerationPhase:
    """Pipeline phase that runs the script-generation pass.

    Satisfies the `Phase` protocol structurally — no inheritance required.
    """

    name = "generation"

    def run(self, ctx: PipelineContext) -> PhaseResult:
        # Lazy import — keeps the cinema package importable even in
        # environments where phase_a_generator's transitive deps aren't
        # installed yet (e.g. running cinema.phases.base tests in isolation).
        from phase_a_generator import generate_shorts_script

        start = time.time()
        try:
            ok = generate_shorts_script(ctx)
            message = "" if ok else "script generation returned False"
        except Exception as exc:
            ok = False
            # Short message in PhaseResult; full traceback printed for the operator.
            message = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()

        return PhaseResult(
            ok=ok,
            message=message,
            elapsed_s=time.time() - start,
        )
