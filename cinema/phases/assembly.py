"""AssemblyPhase — stitches the final video from generated clips + audio.

Wraps `phase_c_assembly.assemble_final_video(ctx)` in the Phase protocol.

What this phase wraps
=====================

`assemble_final_video` is the ONE orchestrator-level entry in
phase_c_assembly. It reads several ctx fields (audio_path, downloaded_vids,
music_vibe, video_pacing, topic), invokes whisper for tempo analysis,
calls into phase_c_ffmpeg for clip normalization + stitching + master
assembly + ASS subtitle generation, and writes the final mp4 to
ctx.final_video_path.

What this phase intentionally does NOT touch
============================================

The other public functions in phase_c_assembly + phase_c_ffmpeg are
per-shot or per-step UTILITIES, not orchestrator phases:

  phase_c_assembly.generate_ai_broll     -- per-shot image generation
  phase_c_assembly._fal_flux_fallback    -- internal fallback
  phase_c_assembly.scale_to_widescreen   -- helper
  phase_c_ffmpeg.generate_ai_video       -- per-shot video generation
  phase_c_ffmpeg.generate_kling_storyboard -- per-shot Kling call
  phase_c_ffmpeg.generate_ass_subtitles  -- subtitle file writer
  phase_c_ffmpeg.normalize_clip          -- ffmpeg normalize
  phase_c_ffmpeg.stitch_modules          -- ffmpeg concat
  phase_c_ffmpeg.execute_master_ffmpeg_assembly -- ffmpeg orchestration
  phase_c_ffmpeg.apply_color_grade       -- color grade
  phase_c_ffmpeg.adjust_speed            -- speed adjust
  phase_c_ffmpeg.assess_motion_quality   -- motion QC
  phase_c_ffmpeg.probe_audio             -- audio inspection

These remain free functions, called either inside the per-shot
generation loop (the broll/video generators) or transitively from
inside assemble_final_video (the ffmpeg helpers). Same architectural
pattern as phase_c_vision: validator/utility service vs. phase.

Pre-conditions
==============

  * ctx.audio_path is set and points to a file on disk
  * ctx.final_video_path is set (used as the output mp4 destination)

The legacy function checks audio_path internally; we check at the phase
boundary too so the failure surfaces as a clean PhaseResult.message
rather than a print + None-return that the orchestrator would have to
interpret.

Return-value handling
=====================

Legacy assemble_final_video has TWO failure modes:

  1. Returns None on missing audio (line 599: explicit `return None`)
  2. Raises on ffmpeg/whisper crashes (no try/except around them)

We treat both as ok=False. On the success path the function does not
have a documented return type; we treat "no exception and ctx.final_
video_path exists post-call" as success.
"""

from __future__ import annotations

import os
import time
import traceback

from cinema.context import PipelineContext
from cinema.phases.base import PhaseResult


class AssemblyPhase:
    """Pipeline phase that stitches the final video.

    Pre-condition:  ctx.audio_path exists on disk.
    Post-condition: ctx.final_video_path exists on disk.
    """

    name = "assembly"

    def run(self, ctx: PipelineContext) -> PhaseResult:
        start = time.time()

        # Cheap pre-flight before pulling whisper into memory.
        if not ctx.audio_path or not os.path.exists(ctx.audio_path):
            return PhaseResult(
                ok=False,
                message=f"audio_path missing or not on disk: {ctx.audio_path!r}",
                elapsed_s=time.time() - start,
            )

        # Lazy import — phase_c_assembly transitively pulls moviepy + whisper.
        from phase_c_assembly import assemble_final_video

        try:
            assemble_final_video(ctx)
            # Success criterion: output mp4 actually written.
            if not ctx.final_video_path or not os.path.exists(ctx.final_video_path):
                return PhaseResult(
                    ok=False,
                    message=(
                        f"assembly returned but final_video_path missing on disk: "
                        f"{ctx.final_video_path!r}"
                    ),
                    elapsed_s=time.time() - start,
                )
            return PhaseResult(
                ok=True,
                message=f"assembled: {ctx.final_video_path}",
                elapsed_s=time.time() - start,
            )
        except Exception as exc:
            traceback.print_exc()
            return PhaseResult(
                ok=False,
                message=f"{type(exc).__name__}: {exc}",
                elapsed_s=time.time() - start,
            )
