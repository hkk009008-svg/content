"""AudioPhase — generates the main voiceover from ctx.full_text.

Wraps `phase_b_audio.generate_voiceover(ctx)` in the Phase protocol.
Standard transformer-phase shape: reads ctx.full_text + ctx.music_vibe,
writes ctx.audio_path (and ctx.voice_id), returns bool mapped to ok.

What this phase intentionally does NOT do (deferred)
====================================================

`phase_b_audio` is the third large V1 module exposing one or two
orchestrator entries plus a constellation of utilities (same shape as
phase_c_assembly + phase_c_ffmpeg + phase_c_vision):

  generate_voiceover(ctx)              -- WRAPPED HERE (main voiceover)
  generate_scene_foley_library(ctx)    -- best-effort foley generation
                                          deferred to a future FoleyPhase
  generate_srt(audio_path, srt_path)   -- caption file writer, used during
                                          upload (not audio phase)

  ...plus 15 utility/helper functions (generate_narration,
  generate_dialogue_voiceover, generate_layered_foley, generate_fal_bgm,
  master_music, apply_au_plugin, apply_pedalboard_chain, etc.) that
  remain free functions called per-shot or transitively.

The workflow doc's Phase 6 separately plans to split phase_b_audio.py
itself into a `audio/` sub-package (audio/voiceover.py, audio/foley.py,
audio/music.py, audio/srt.py) — that's a refactor of the LEGACY module,
distinct from this AudioPhase wrapper.

Foley deferral note
===================

Legacy main.py runs foley AFTER voiceover and ignores its return value
(``generate_scene_foley_library(ctx)`` with no `if not` guard). Combining
voiceover + foley into one Phase would force one of two awkward
contracts: either fail the phase if foley fails (stricter than legacy,
breaks unrelated runs) or silently swallow foley failures (hides bugs).
Both bad. Splitting foley into its own phase (or making it best-effort
via a separate code path) is cleaner. For now, AudioPhase = voiceover
only; foley stays in main.py until the driver swap lands.

Pre-condition
=============

  * ctx.full_text is non-empty (the legacy function reads it via .get with
    "" default, so we surface the missing-text case as a clean failure
    rather than letting the underlying TTS call produce silence).

Post-condition
==============

  * ctx.audio_path points to a generated mp3 on disk.
"""

from __future__ import annotations

import os
import time
import traceback

from cinema.context import PipelineContext
from cinema.phases.base import PhaseResult


class AudioPhase:
    """Pipeline phase that generates the main voiceover.

    Pre-condition:  ctx.full_text is non-empty.
    Post-condition: ctx.audio_path is set and exists on disk.
    """

    name = "audio"

    def run(self, ctx: PipelineContext) -> PhaseResult:
        start = time.time()

        # Pre-flight: no script means nothing to voice. The legacy function
        # would silently produce an empty/garbage mp3; we surface it.
        if not ctx.full_text or not ctx.full_text.strip():
            return PhaseResult(
                ok=False,
                message="ctx.full_text is empty; nothing to voice over",
                elapsed_s=time.time() - start,
            )

        # Lazy import — phase_b_audio pulls ElevenLabs, whisper, pedalboard,
        # and various DSP deps. Heavy.
        from phase_b_audio import generate_voiceover

        try:
            ok = generate_voiceover(ctx)
            if not ok:
                return PhaseResult(
                    ok=False,
                    message="generate_voiceover returned False",
                    elapsed_s=time.time() - start,
                )
            # Post-condition: audio actually written.
            if not ctx.audio_path or not os.path.exists(ctx.audio_path):
                return PhaseResult(
                    ok=False,
                    message=(
                        f"generate_voiceover returned True but audio_path "
                        f"missing on disk: {ctx.audio_path!r}"
                    ),
                    elapsed_s=time.time() - start,
                )
            return PhaseResult(
                ok=True,
                message=f"voiceover: {ctx.audio_path}",
                elapsed_s=time.time() - start,
            )
        except Exception as exc:
            traceback.print_exc()
            return PhaseResult(
                ok=False,
                message=f"{type(exc).__name__}: {exc}",
                elapsed_s=time.time() - start,
            )
