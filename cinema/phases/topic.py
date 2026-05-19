"""TopicPhase — selects the day's viral topic, populating ctx.topic.

Wraps `phase_0_topic.generate_trending_topic()` in the Phase protocol.

Shape difference vs GenerationPhase
====================================

GenerationPhase is a *transformer* — it reads ctx and writes ctx. TopicPhase
is a *source* — it accepts no inputs (it pulls fresh data from YouTube trends,
market sentiment, and the `used_topics.txt` history), and writes one field
into ctx (`ctx.topic`). Future "source" phases (e.g. BlueprintPhase, which
calls Gemini fresh) follow the same shape.

The Phase protocol intentionally does NOT differentiate between source and
transformer phases — both have the same `.run(ctx) -> PhaseResult` signature.
The pattern just happens to recur in the implementation bodies.
"""

from __future__ import annotations

import time
import traceback

from cinema.context import PipelineContext
from cinema.phases.base import PhaseResult


class TopicPhase:
    """Pipeline phase that selects the day's viral topic.

    Mutates `ctx.topic`. If the generator returns an empty string, treat
    that as a failure (the rest of the pipeline can't proceed without a
    topic).
    """

    name = "topic"

    def run(self, ctx: PipelineContext) -> PhaseResult:
        from phase_0_topic import generate_trending_topic

        start = time.time()
        try:
            topic = generate_trending_topic()
            if not topic:
                return PhaseResult(
                    ok=False,
                    message="generate_trending_topic returned empty string",
                    elapsed_s=time.time() - start,
                )
            ctx.topic = topic
            return PhaseResult(
                ok=True,
                message=f"topic: {topic[:60]}",
                elapsed_s=time.time() - start,
            )
        except Exception as exc:
            traceback.print_exc()
            return PhaseResult(
                ok=False,
                message=f"{type(exc).__name__}: {exc}",
                elapsed_s=time.time() - start,
            )
