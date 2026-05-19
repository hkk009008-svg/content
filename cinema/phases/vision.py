"""VisionPhase — optional post-assembly QC checkpoint for the final thumbnail.

Architectural note: this phase is **different in nature** from the other
phases migrated in Phase 5.
====================================================================

`phase_c_vision` is a *toolkit of validator functions* (validate_identity,
quality_control_image, validate_shot_quality_vision, etc.), not a single
pipeline step. Its functions are called from within other phases — most
visibly, per-shot during generation — as a **validator service**, not as
an orchestrator-driven phase.

We therefore do NOT try to "migrate phase_c_vision into one Phase class."
That would force a square peg into a round hole. The validators stay as
free functions in `phase_c_vision.py` and continue to be called from
wherever needs them.

What this VisionPhase is instead
================================

A new, opt-in checkpoint the future orchestrator can run AFTER assembly:
take the final thumbnail (ctx.final_thumbnail_path) and ask GPT-4o Vision
whether it passes structural QC. This is currently NOT done in V1 — the
thumbnail is uploaded blind. Adding this Phase makes the option available
to the future driver.

Pre-condition:  ctx.final_thumbnail_path exists on disk.
Post-condition: ok=True iff QC score >= internal threshold.

If your goal is to validate per-shot images (not the thumbnail), use the
validators in `phase_c_vision` directly — that's the right tool for that
job, and forcing it through Phase.run() would be ceremony for no benefit.
"""

from __future__ import annotations

import os
import time
import traceback

from cinema.context import PipelineContext
from cinema.phases.base import PhaseResult


class VisionPhase:
    """Pipeline phase that QCs the final thumbnail before upload.

    A new V2-style checkpoint (legacy V1 does not validate the thumbnail).
    The orchestrator can include this phase between AssemblyPhase and
    UploadPhase to fail the run early if the thumbnail is obviously bad.
    """

    name = "vision"

    def run(self, ctx: PipelineContext) -> PhaseResult:
        start = time.time()

        thumb = ctx.final_thumbnail_path
        if not thumb or not os.path.exists(thumb):
            return PhaseResult(
                ok=False,
                message=f"final_thumbnail_path missing or not on disk: {thumb!r}",
                elapsed_s=time.time() - start,
            )

        # Lazy import — phase_c_vision pulls OpenAI/GPT-4o deps.
        from phase_c_vision import quality_control_image

        try:
            ok = quality_control_image(thumb, ctx.topic)
            return PhaseResult(
                ok=ok,
                message="thumbnail passed QC" if ok else "thumbnail failed QC",
                elapsed_s=time.time() - start,
            )
        except Exception as exc:
            traceback.print_exc()
            return PhaseResult(
                ok=False,
                message=f"{type(exc).__name__}: {exc}",
                elapsed_s=time.time() - start,
            )
