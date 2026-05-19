"""MotionRenderPhase — per-shot motion (image→video) generation.

Extracted from the inline motion loop in cinema_pipeline.CinemaPipeline.generate()
during Slice E (Option B). Sibling of KeyframeRenderPhase; same shape,
different inner call.

The phase iterates every shot in the project, calling
``shot_generator.generate_motion_take(scene_id, shot_id)`` for each
shot that doesn't already have an approved final take. The motion
generator itself enforces the precondition (approved keyframe must
exist); shots whose keyframe wasn't approved get back
``{"success": False, "error": "Approved keyframe required..."}`` and
flow through on_failure.

Cancellation, parameters, and failure semantics match KeyframeRenderPhase.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from cinema.phases.base import PhaseResult


class MotionRenderPhase:
    """Iterate all shots, generate a motion take for each unfinalized one."""

    name = "motion_render"

    def __init__(
        self,
        shot_generator=None,
        project: Optional[dict] = None,
        on_failure: Optional[Callable[[str, str, str], None]] = None,
    ):
        """See KeyframeRenderPhase for parameter docs. shot_generator
        must have a ``generate_motion_take(scene_id, shot_id)`` method."""
        self._gen = shot_generator
        self._project = project
        self._on_failure = on_failure or (lambda scene_id, shot_id, error: None)

    def run(self, ctx) -> PhaseResult:
        start = time.time()
        if self._gen is None or self._project is None:
            return PhaseResult(
                ok=False,
                message="MotionRenderPhase requires shot_generator and project",
                elapsed_s=0.0,
            )

        ok_count = 0
        skip_count = 0
        fail_count = 0

        for scene in self._project.get("scenes", []):
            if ctx.lifecycle.is_cancelled():
                return PhaseResult(
                    ok=False,
                    message=f"cancelled (ok={ok_count}, skip={skip_count}, fail={fail_count})",
                    elapsed_s=time.time() - start,
                )
            for shot in scene.get("shots", []):
                if ctx.lifecycle.is_cancelled():
                    return PhaseResult(
                        ok=False,
                        message=f"cancelled (ok={ok_count}, skip={skip_count}, fail={fail_count})",
                        elapsed_s=time.time() - start,
                    )
                if shot.get("approved_final_take_id"):
                    skip_count += 1
                    continue
                result = self._gen.generate_motion_take(scene["id"], shot["id"])
                if result.get("success"):
                    ok_count += 1
                else:
                    fail_count += 1
                    self._on_failure(scene["id"], shot["id"], result.get("error", ""))

        return PhaseResult(
            ok=True,
            message=f"motion: {ok_count} new, {skip_count} pre-finalized, {fail_count} failed",
            elapsed_s=time.time() - start,
        )
