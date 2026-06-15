"""PerformanceCapturePhase — per-shot performance retargeting.

Sits between KeyframeRenderPhase and MotionRenderPhase. Iterates all shots
that have an approved keyframe but no approved performance take, generates
a driving performance via ShotController.generate_performance_take(), and
stores the result on the shot. Shots routed to SKIP are no-ops.

Same shape as KeyframeRenderPhase and MotionRenderPhase.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from cinema.phases.base import PhaseResult


class PerformanceCapturePhase:
    """Iterate all shots; capture a performance take for each one that needs one."""

    name = "performance_capture"

    def __init__(
        self,
        shot_generator=None,
        project: Optional[dict] = None,
        on_failure: Optional[Callable[[str, str, str], None]] = None,
    ):
        """shot_generator must expose ``generate_performance_take(scene_id, shot_id)``."""
        self._gen = shot_generator
        self._project = project
        self._on_failure = on_failure or (lambda scene_id, shot_id, error: None)

    def run(self, ctx) -> PhaseResult:
        start = time.time()
        if self._gen is None or self._project is None:
            return PhaseResult(
                ok=False,
                message="PerformanceCapturePhase requires shot_generator and project",
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
                # Already has an approved performance — done
                if shot.get("approved_performance_take_id"):
                    skip_count += 1
                    continue
                # Explicitly marked SKIP by previous routing — done
                if (shot.get("performance_engine") or "").upper() == "SKIP":
                    skip_count += 1
                    continue
                # No keyframe to drive off of yet — skip (motion_render also skips)
                if not shot.get("approved_keyframe_take_id"):
                    skip_count += 1
                    continue

                result = self._gen.generate_performance_take(scene["id"], shot["id"])
                if result.get("success"):
                    if result.get("skipped"):
                        skip_count += 1
                    else:
                        ok_count += 1
                elif result.get("error_kind") == "budget":
                    return PhaseResult(
                        ok=False,
                        message=(
                            f"budget cap reached at {shot['id']} — performance phase "
                            f"stopped (ok={ok_count}, skip={skip_count}, "
                            f"fail={fail_count})"
                        ),
                        elapsed_s=time.time() - start,
                    )
                else:
                    fail_count += 1
                    self._on_failure(scene["id"], shot["id"], result.get("error", ""))

        return PhaseResult(
            ok=True,
            message=f"performance: {ok_count} new, {skip_count} skipped, {fail_count} failed",
            elapsed_s=time.time() - start,
        )
