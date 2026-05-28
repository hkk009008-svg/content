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

Storyboard batch path (F2b)
----------------------------
When ``global_settings.api_engines.KLING_NATIVE.storyboard_mode`` is truthy
AND the scene has 2–6 unapproved shots AND every unapproved shot has a usable
keyframe, the phase calls ``KlingNativeAPI.generate_storyboard`` once for the
whole scene, splits the combined output via ``split_video_into_segments``, and
registers each segment as a motion take via
``ShotController._finalize_motion_take``.  Cost is recorded once for the batch;
per-segment finalize calls set ``record_cost=False`` to avoid N-counting a
single generation.

If storyboard generation returns None, the split fails, or the scene is
ineligible, the phase falls through to the normal per-shot loop — a storyboard
failure can never lose the scene.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable, Optional

from cinema.phases.base import PhaseResult

logger = logging.getLogger(__name__)


def _get_storyboard_mode(project: dict) -> bool:
    """Return the storyboard_mode toggle from project global_settings.

    Stored at global_settings.api_engines.KLING_NATIVE.storyboard_mode.
    Default OFF — missing / falsy → False.
    """
    gs = project.get("global_settings", {}) or {}
    api_engines = gs.get("api_engines", {}) or {}
    kling_cfg = api_engines.get("KLING_NATIVE", {}) or {}
    return bool(kling_cfg.get("storyboard_mode", False))


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

    # ------------------------------------------------------------------
    # Storyboard eligibility helpers
    # ------------------------------------------------------------------

    def _scene_keyframes(self, shots: list) -> Optional[list]:
        """Return an ordered list of (shot, keyframe_path) tuples for each shot,
        or None if any shot is missing an approved keyframe.

        Used by the storyboard eligibility check — we only take the batch path
        when every shot has a usable anchor image.
        """
        result = []
        for shot in shots:
            kf_take_id = shot.get("approved_keyframe_take_id", "")
            if not kf_take_id:
                return None
            kf_path = self._gen._resolve_take_path(shot, kf_take_id)
            if not kf_path or not os.path.exists(kf_path):
                return None
            result.append((shot, kf_path))
        return result

    # ------------------------------------------------------------------
    # Storyboard batch path
    # ------------------------------------------------------------------

    def _run_storyboard_scene(
        self,
        scene: dict,
        shot_kf_pairs: list,
        ok_count: int,
        fail_count: int,
    ):
        """Attempt to generate the whole scene as one Kling storyboard batch.

        Returns (ok_count, fail_count, success: bool).  On failure, the caller
        falls through to the per-shot loop; counters are unchanged so the
        per-shot path can accumulate its own results.
        """
        scene_id = scene["id"]
        num_shots = len(shot_kf_pairs)

        try:
            from kling_native import KlingNativeAPI
            from phase_c_ffmpeg import split_video_into_segments
            from domain.project_manager import make_take
        except ImportError as exc:
            logger.warning(
                "storyboard batch: import failed (%s); falling through to per-shot",
                exc,
                extra={"scene_id": scene_id},
            )
            return ok_count, fail_count, False

        # Anchor image: first shot's keyframe.
        anchor_shot, anchor_kf = shot_kf_pairs[0]

        # Per-shot motion prompts + durations.
        shots_for_storyboard = []
        durations = []
        for shot, _kf in shot_kf_pairs:
            prompt = (
                shot.get("motion_description")
                or shot.get("prompt")
                or shot.get("camera")
                or "cinematic motion"
            )
            dur = float(shot.get("duration", 5.0))
            shots_for_storyboard.append({"prompt": prompt, "duration": dur})
            durations.append(dur)

        # image_references: the other shots' keyframes (indices 1..N-1) for
        # cross-shot character/style consistency.
        image_refs = [kf for (_shot, kf) in shot_kf_pairs[1:]] if num_shots > 1 else None

        # Output path for the combined storyboard video.
        # Stored under the first shot's outputs dir when _shot_ctrl is available.
        first_shot_id = shot_kf_pairs[0][0].get("id", "storyboard")
        try:
            storyboard_output_path = self._gen._shot_ctrl._take_output_path(
                first_shot_id, f"storyboard_{scene_id}", ".mp4"
            )
        except Exception:
            # Fallback path (e.g. in test stubs that don't expose _shot_ctrl);
            # project-scope the filename so concurrent same-scene_id runs in
            # different projects can't overwrite each other's /tmp output.
            storyboard_output_path = os.path.join(
                "/tmp", f"storyboard_{self._project.get('id', 'unk')}_{scene_id}.mp4"
            )

        logger.info(
            "storyboard batch: scene=%s shots=%d anchor=%s",
            scene_id, num_shots, anchor_kf,
        )

        kling = KlingNativeAPI()
        combined_path = kling.generate_storyboard(
            image_path=anchor_kf,
            shots=shots_for_storyboard,
            output_path=storyboard_output_path,
            image_references=image_refs or None,
        )

        if not combined_path:
            logger.warning(
                "storyboard batch: generate_storyboard returned None for scene=%s; "
                "falling through to per-shot",
                scene_id,
            )
            return ok_count, fail_count, False

        # Record ONE batch cost for the whole scene (closes Tier F NEW-2:
        # kling_native previously had no call-site cost tracking).
        try:
            self._gen.cost_tracker.record_api_call(
                "KLING_NATIVE",
                operation="storyboard_generation",
                scene_id=scene_id,
                video_id=self._project.get("id", ""),
            )
        except Exception:
            logger.warning(
                "storyboard batch: cost record skipped",
                exc_info=True,
            )

        # Split the combined output back into per-shot segments.
        seg_output_dir = os.path.dirname(storyboard_output_path)
        try:
            segment_paths = split_video_into_segments(
                source_path=combined_path,
                durations=durations,
                output_dir=seg_output_dir,
                stem=f"storyboard_{scene_id}_seg",
            )
        except Exception as exc:
            logger.warning(
                "storyboard batch: split failed for scene=%s (%s); "
                "falling through to per-shot",
                scene_id, exc,
            )
            return ok_count, fail_count, False

        if not segment_paths or len(segment_paths) != num_shots:
            logger.warning(
                "storyboard batch: split returned %d segments for %d shots "
                "in scene=%s; falling through to per-shot",
                len(segment_paths) if segment_paths else 0,
                num_shots,
                scene_id,
            )
            return ok_count, fail_count, False

        # Register each segment as a motion take via _finalize_motion_take.
        # record_cost=False: the batch cost was already recorded above; we
        # MUST NOT re-count it per-shot.
        ctrl = self._gen._shot_ctrl
        settings = self._project.get("global_settings", {}) or {}
        from workflow_selector import classify_shot_type

        for idx, (shot, kf_path) in enumerate(shot_kf_pairs):
            seg_path = segment_paths[idx]
            shot_id = shot.get("id", "")
            kf_take_id = shot.get("approved_keyframe_take_id", "")
            # Classify per shot (not hardcoded "medium") so _finalize_motion_take's
            # motion-fidelity floor / remotion gate matches the normal per-shot path.
            resolved_st = classify_shot_type(shot)

            take = make_take(
                "motion",
                source_take_id=kf_take_id,
                metadata={
                    "scene_id": scene_id,
                    "shot_id": shot_id,
                    "target_api": "KLING_NATIVE",
                    "shot_type": resolved_st,
                    "storyboard_source": combined_path,
                    "storyboard_segment_index": idx,
                },
            )

            finalize_ok = False
            finalize_err = "storyboard segment finalize failed"
            try:
                result = ctrl._finalize_motion_take(
                    scene,
                    shot,
                    take,
                    seg_path,
                    source_image=kf_path,
                    target_api="KLING_NATIVE",
                    cc={},
                    settings=settings,
                    resolved_shot_type=resolved_st,
                    extra_metadata={
                        "storyboard_source": combined_path,
                        "storyboard_segment_index": idx,
                    },
                    record_cost=False,
                )
                finalize_ok = bool(result.get("success"))
                if not finalize_ok:
                    finalize_err = result.get("error", finalize_err)
            except Exception as exc:
                logger.exception(
                    "storyboard batch: _finalize_motion_take failed for "
                    "scene=%s shot=%s",
                    scene_id, shot_id,
                )
                finalize_err = str(exc)

            if finalize_ok:
                ok_count += 1
                continue

            # Partial-finalize failure: retry THIS shot via the normal per-shot
            # path. Keeps the successful batch segments (no scene loss) and does
            # NOT re-generate the ones that succeeded (no double-gen). The retry
            # records its own per-shot motion cost (a separate generation).
            logger.warning(
                "storyboard batch: segment finalize failed for scene=%s shot=%s "
                "(%s) — retrying via per-shot generation",
                scene_id, shot_id, finalize_err,
            )
            try:
                retry = self._gen.generate_motion_take(scene_id, shot_id)
                if retry.get("success"):
                    ok_count += 1
                else:
                    fail_count += 1
                    self._on_failure(
                        scene_id, shot_id, retry.get("error", finalize_err),
                    )
            except Exception as exc:
                logger.exception(
                    "storyboard batch: per-shot retry failed for scene=%s shot=%s",
                    scene_id, shot_id,
                )
                fail_count += 1
                self._on_failure(scene_id, shot_id, str(exc))

        return ok_count, fail_count, True

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def run(self, ctx) -> PhaseResult:
        start = time.time()
        if self._gen is None or self._project is None:
            return PhaseResult(
                ok=False,
                message="MotionRenderPhase requires shot_generator and project",
                elapsed_s=0.0,
            )

        storyboard_mode = _get_storyboard_mode(self._project)

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

            shots = scene.get("shots", [])

            # Partition shots: pre-approved (skip) vs. needs generation.
            approved = [s for s in shots if s.get("approved_final_take_id")]
            unapproved = [s for s in shots if not s.get("approved_final_take_id")]
            skip_count += len(approved)

            if not unapproved:
                continue

            # -----------------------------------------------------------------
            # Storyboard batch path (flag on, 2–6 unapproved shots, all have
            # keyframes).  Falls through to per-shot loop on any failure.
            # -----------------------------------------------------------------
            batch_handled = False
            if storyboard_mode and 2 <= len(unapproved) <= 6:
                if ctx.lifecycle.is_cancelled():
                    return PhaseResult(
                        ok=False,
                        message=f"cancelled (ok={ok_count}, skip={skip_count}, fail={fail_count})",
                        elapsed_s=time.time() - start,
                    )
                try:
                    shot_kf_pairs = self._scene_keyframes(unapproved)
                except Exception:
                    logger.warning(
                        "storyboard eligibility check failed for scene=%s; "
                        "falling through to per-shot",
                        scene.get("id"),
                        exc_info=True,
                    )
                    shot_kf_pairs = None

                if shot_kf_pairs:
                    ok_count, fail_count, batch_ok = self._run_storyboard_scene(
                        scene,
                        shot_kf_pairs,
                        ok_count,
                        fail_count,
                    )
                    if batch_ok:
                        batch_handled = True

            if batch_handled:
                # Storyboard batch succeeded — all unapproved shots are done.
                continue

            # -----------------------------------------------------------------
            # Per-shot loop (default path + storyboard fallback).
            # -----------------------------------------------------------------
            for shot in unapproved:
                if ctx.lifecycle.is_cancelled():
                    return PhaseResult(
                        ok=False,
                        message=f"cancelled (ok={ok_count}, skip={skip_count}, fail={fail_count})",
                        elapsed_s=time.time() - start,
                    )
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
