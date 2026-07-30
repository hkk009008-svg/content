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
import tempfile
import time
from datetime import date, datetime, timezone
from typing import Callable, Optional

from cinema.phases.base import PhaseResult
from cinema.storyboard import allocate_storyboard_durations
from domain.provider_catalog import RuntimeSnapshot
from domain.video_engine_policy import (
    build_runtime_snapshot,
    filter_dispatch_candidates,
)

logger = logging.getLogger(__name__)


def _storyboard_policy_runtime_snapshot() -> RuntimeSnapshot:
    """Observe current symbolic runtime eligibility for storyboard dispatch."""

    return build_runtime_snapshot()


def _storyboard_policy_current_date() -> date:
    """Return the UTC lifecycle-policy date through a patchable test seam."""

    return datetime.now(timezone.utc).date()


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

        # Pre-spend budget gate (ADR-022): the batch launch spends BEFORE any
        # per-take gate can run (one batch cost is recorded post-spend below,
        # and per-segment finalize uses record_cost=False). Refuse here and
        # fall through to the per-shot path, whose own gate emits
        # BUDGET_EXCEEDED and aborts the phase — single abort mechanism.
        tracker = getattr(self._gen, "cost_tracker", None)
        if tracker is not None:
            try:
                refused = bool(tracker.would_exceed("KLING_NATIVE"))
            except Exception:
                logger.warning(
                    "storyboard batch: budget gate failed for scene=%s; "
                    "falling through to guarded per-shot path",
                    scene_id,
                    exc_info=True,
                )
                return ok_count, fail_count, False
            if refused:
                logger.info(
                    "storyboard batch: budget gate refused launch for scene=%s; "
                    "falling through to per-shot path",
                    scene_id,
                )
                return ok_count, fail_count, False

        try:
            from kling_native import KlingNativeAPI
            from phase_c_ffmpeg import (
                split_video_into_segments,
                validate_storyboard_segment,
            )
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
        for shot, _kf in shot_kf_pairs:
            prompt = (
                shot.get("motion_description")
                or shot.get("prompt")
                or shot.get("camera")
                or "cinematic motion"
            )
            shots_for_storyboard.append(
                {"prompt": prompt, "duration": shot.get("duration", 5.0)}
            )
        try:
            durations = allocate_storyboard_durations(shots_for_storyboard)
        except (TypeError, ValueError, OverflowError) as exc:
            logger.warning(
                "storyboard batch: invalid duration plan for scene=%s (%s); "
                "falling through to per-shot",
                scene_id,
                exc,
            )
            return ok_count, fail_count, False
        for storyboard_shot, duration in zip(
            shots_for_storyboard, durations
        ):
            storyboard_shot["duration"] = duration

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
                # A storyboard BATCH has no single shot, so shot_id is left empty
                # (a scene_id here would pollute get_video_cost()'s shot_count —
                # one phantom 'shot' per batch). operation="storyboard_generation"
                # + video_id already attribute the cost to the scene batch.
                shot_id="",
                video_id=self._project.get("id", ""),
            )
        except Exception:
            logger.warning(
                "storyboard batch: cost record skipped",
                exc_info=True,
            )

        # Split the combined output back into per-shot segments.  Use a unique
        # directory so ownership is exact: a rejected split can clean only
        # files from this invocation without trusting arbitrary returned paths.
        seg_output_root = os.path.abspath(
            os.path.dirname(storyboard_output_path) or os.curdir
        )
        try:
            seg_output_dir = tempfile.mkdtemp(
                prefix=".storyboard_segments_",
                dir=seg_output_root,
            )
        except OSError as exc:
            logger.warning(
                "storyboard batch: could not create owned segment directory "
                "for scene=%s (%s); falling through to per-shot",
                scene_id,
                exc,
            )
            return ok_count, fail_count, False
        segment_stem = "segment"
        expected_segment_paths = [
            os.path.abspath(
                os.path.join(
                    seg_output_dir,
                    f"{segment_stem}_{index:03d}.mp4",
                )
            )
            for index in range(num_shots)
        ]

        def reject_split() -> None:
            # Unlink only the deterministic names this invocation owns.  A
            # faulty or adversarial splitter may return some other path; that
            # path must never become a cleanup target.
            for expected_path in expected_segment_paths:
                try:
                    os.unlink(expected_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    logger.warning(
                        "storyboard batch: failed to clean rejected segment",
                        extra={
                            "scene_id": scene_id,
                            "segment_path": expected_path,
                        },
                        exc_info=True,
                    )
            try:
                os.rmdir(seg_output_dir)
            except FileNotFoundError:
                pass
            except OSError:
                # Unexpected files are deliberately preserved rather than
                # recursively deleted; they are not owned by this invocation.
                logger.warning(
                    "storyboard batch: owned segment directory retained "
                    "because it contains non-owned entries",
                    extra={
                        "scene_id": scene_id,
                        "segment_dir": seg_output_dir,
                    },
                )

        try:
            segment_paths = split_video_into_segments(
                source_path=combined_path,
                durations=durations,
                output_dir=seg_output_dir,
                stem=segment_stem,
            )
        except Exception as exc:
            reject_split()
            logger.warning(
                "storyboard batch: split failed for scene=%s (%s); "
                "falling through to per-shot",
                scene_id, exc,
            )
            return ok_count, fail_count, False

        try:
            returned_segment_paths = [
                os.path.abspath(os.fspath(path))
                for path in segment_paths
            ]
        except Exception:
            returned_segment_paths = []
        if returned_segment_paths != expected_segment_paths:
            reject_split()
            logger.warning(
                "storyboard batch: split returned non-owned paths or %d "
                "segments for %d shots in scene=%s; falling through to "
                "per-shot",
                len(returned_segment_paths),
                num_shots,
                scene_id,
            )
            return ok_count, fail_count, False
        invalid_segments = []
        for index, (segment_path, duration_s) in enumerate(
            zip(expected_segment_paths, durations)
        ):
            try:
                is_nonempty_file = (
                    bool(segment_path)
                    and os.path.isfile(segment_path)
                    and os.path.getsize(segment_path) > 0
                )
                if is_nonempty_file:
                    validate_storyboard_segment(segment_path, duration_s)
            except OSError:
                is_nonempty_file = False
            except RuntimeError:
                is_nonempty_file = False
            if not is_nonempty_file:
                invalid_segments.append(index)
        if invalid_segments:
            reject_split()
            logger.warning(
                "storyboard batch: invalid media segments %s in scene=%s; "
                "falling through to per-shot",
                invalid_segments,
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
            seg_path = expected_segment_paths[idx]
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

        # This direct batch dispatch bypasses generate_ai_video's mandatory
        # policy fence, so reproduce that typed admission before importing or
        # constructing KlingNativeAPI, generating, or spending. Keep the user
        # toggle separate from eligibility: rejection falls through to the
        # guarded per-shot generate_motion_take path.
        from cinema.aspect import is_portrait, DEFAULT_ASPECT_RATIO
        from cinema.context import get_project_setting
        _aspect = get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)
        storyboard_mode = _get_storyboard_mode(self._project)
        storyboard_batch_admitted = False
        if storyboard_mode:
            settings = self._project.get("global_settings", {}) or {}
            api_engines = settings.get("api_engines", {}) or {}
            dispatch_policy = filter_dispatch_candidates(
                ["KLING_NATIVE"],
                snapshot=_storyboard_policy_runtime_snapshot(),
                on_date=_storyboard_policy_current_date(),
                api_engines=api_engines,
                aspect_ratio=_aspect,
            )
            # KLING_NATIVE's regular per-shot branch is portrait-capable, but
            # generate_storyboard itself accepts no aspect and has no
            # orientation backstop. Retain this batch-specific exclusion even
            # though the shared engine policy admits KLING_NATIVE at portrait.
            storyboard_batch_admitted = (
                dispatch_policy.candidates == ("KLING_NATIVE",)
                and not is_portrait(_aspect)
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
            if storyboard_batch_admitted and 2 <= len(unapproved) <= 6:
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
                elif result.get("error_kind") == "budget":
                    # Pre-spend gate refused (ADR-022): stop the phase rather
                    # than marching through every remaining shot — each would
                    # be refused identically (no spend) but mislabeled as a
                    # shot failure via on_failure. Not a failure: the shot
                    # stays unapproved and regenerates once the budget is
                    # raised.
                    return PhaseResult(
                        ok=False,
                        message=(
                            f"budget cap reached at {shot['id']} — motion phase "
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
            message=f"motion: {ok_count} new, {skip_count} pre-finalized, {fail_count} failed",
            elapsed_s=time.time() - start,
        )
