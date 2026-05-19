"""Phase protocol + PhaseResult — the contract every pipeline phase implements.

The orchestrator (future `cinema.pipeline.CinemaPipeline`) drives the pipeline by
iterating a list of Phase instances and calling `.run(ctx)` on each. Phases
mutate the shared `PipelineContext` to thread state downstream and return a
`PhaseResult` so the orchestrator can decide whether to continue, skip, retry,
or abort.

Design notes
============

* `Phase` is a `@runtime_checkable` Protocol. We do not require classes to
  inherit from it explicitly — any class with a `name: str` attribute and a
  `run(ctx) -> PhaseResult` method satisfies the contract. This keeps phase
  implementations pluggable and free of inheritance ceremony.

* `PhaseResult.ok` is the sole gate-keeping signal. `message` exists for
  human-readable logging; `elapsed_s` for cost/perf tracking. The contract
  intentionally does NOT include retry policy or fallback logic — that's
  the orchestrator's job, not the phase's.

* The protocol is intentionally minimal. Resist adding optional methods
  (`validate()`, `cleanup()`, ...) until a second phase needs them. Two
  callers makes an abstraction; one is speculative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    # Forward-reference only — avoids cinema.phases.base ↔ cinema.context
    # import-time coupling.
    from cinema.context import PipelineContext


@dataclass
class PhaseResult:
    """The outcome of a single phase's run.

    Attributes
    ----------
    ok : bool
        True if the phase completed successfully. The orchestrator uses this
        to decide whether to continue to the next phase.
    message : str
        Human-readable detail. Logged on failure for diagnosis; ignored on
        success unless verbose mode is on.
    elapsed_s : float
        Wall-clock duration in seconds. Used by tracking/quality.py to
        accumulate per-run cost and perf metrics.
    """

    ok: bool
    message: str = ""
    elapsed_s: float = 0.0


@runtime_checkable
class Phase(Protocol):
    """The contract every pipeline phase implements.

    A phase has a stable `name` (used as a key in logs, progress callbacks,
    and per-phase config) and a `.run(ctx)` method that mutates the shared
    context and returns a PhaseResult.

    Example
    -------
    >>> class MyPhase:
    ...     name = "my_phase"
    ...     def run(self, ctx):
    ...         ctx.topic = ctx.topic.upper()
    ...         return PhaseResult(ok=True)
    >>> isinstance(MyPhase(), Phase)
    True
    """

    name: str

    def run(self, ctx: "PipelineContext") -> PhaseResult: ...
