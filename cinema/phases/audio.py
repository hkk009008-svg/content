"""AudioPhase — generates the main voiceover from ctx.full_text.

Wraps `audio.voiceover.generate_voiceover(ctx)` in the Phase protocol.
Standard transformer-phase shape: reads ctx.full_text + ctx.music_vibe,
writes ctx.audio_path (and ctx.voice_id), returns bool mapped to ok.

What this phase intentionally does NOT do (deferred)
====================================================

The audio domain (Phase 6 of the refactor) is now split across focused
submodules under ``audio/``:

  audio.voiceover.generate_voiceover           -- WRAPPED HERE
  audio.foley.generate_scene_foley_library     -- best-effort foley,
                                                  deferred to a future FoleyPhase
  audio.srt.generate_srt                       -- caption file writer,
                                                  used during upload (not here)

  ...plus the per-character TTS (audio.dialogue), the voice/narration
  helpers (audio.voiceover.generate_narration, generate_single_line_audio),
  the music chain (audio.music.generate_fal_bgm + master_music), and the
  DSP/effects helpers (audio.effects.apply_*) — all free functions called
  per-shot or transitively.

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

        # Lazy import — audio.voiceover pulls ElevenLabs SDK and audio.music
        # (which itself pulls Fal.ai). Heavy.
        from audio.voiceover import generate_voiceover

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
