"""KeyframeRenderPhase — per-shot keyframe generation, parallelizable.

Extracted from the inline keyframe loop in cinema_pipeline.CinemaPipeline.generate()
during Slice E (Option B: extract loops as phases, keep gates inline).

The phase iterates every shot in the project, calling
``shot_generator.generate_keyframe_take(scene_id, shot_id)`` for each
shot that doesn't already have an approved keyframe. Failures are
reported via the on_failure callback (which the caller wires up to
its own ``failed_shots`` list + progress event); individual shot
failures do NOT fail the phase, matching the legacy behavior where
operators can rework failed shots from the review UI.

Cancellation
============

The phase polls ``ctx.lifecycle.is_cancelled()`` at scene boundaries
and shot boundaries. Cancellation between shots causes the phase to
return ``PhaseResult(ok=False, message="cancelled (...)")`` with
counts of work done so far.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from cinema.phases.base import PhaseResult


class KeyframeRenderPhase:
    """Iterate all shots, generate a keyframe for each unapproved one."""

    name = "keyframe_render"

    def __init__(
        self,
        shot_generator=None,
        project: Optional[dict] = None,
        on_failure: Optional[Callable[[str, str, str], None]] = None,
    ):
        """
        Parameters
        ----------
        shot_generator:
            Anything with a ``generate_keyframe_take(scene_id, shot_id)``
            method. In practice this is a ``cinema_pipeline.CinemaPipeline``
            instance (which has the method via ShotControllerMixin).
            Duck-typed; the phase module does not import that class.
        project:
            The project dict (load_project() result). The phase reads
            ``project["scenes"][...]["shots"][...]`` to drive its loop.
        on_failure:
            Called with ``(scene_id, shot_id, error)`` when a single
            shot's generation fails. The caller's callback typically
            appends to its ``failed_shots`` list and emits a SHOT_FAILED
            progress event. Defaults to a no-op.

        All parameters default to None so the class satisfies the Phase
        protocol's ``cls()`` instantiation requirement for the §0 smoke
        test. A no-arg instance returns ``ok=False`` from .run() with a
        "not configured" message — useful as a defensive default.
        """
        self._gen = shot_generator
        self._project = project
        self._on_failure = on_failure or (lambda scene_id, shot_id, error: None)

    def run(self, ctx) -> PhaseResult:
        start = time.time()
        if self._gen is None or self._project is None:
            return PhaseResult(
                ok=False,
                message="KeyframeRenderPhase requires shot_generator and project",
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
                if shot.get("approved_keyframe_take_id"):
                    skip_count += 1
                    continue
                result = self._gen.generate_keyframe_take(scene["id"], shot["id"])
                if result.get("success"):
                    ok_count += 1
                else:
                    fail_count += 1
                    self._on_failure(scene["id"], shot["id"], result.get("error", ""))

        return PhaseResult(
            ok=True,  # legacy semantics — partial failures don't fail the phase
            message=f"keyframes: {ok_count} new, {skip_count} pre-approved, {fail_count} failed",
            elapsed_s=time.time() - start,
        )
