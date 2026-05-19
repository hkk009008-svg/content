"""LearningPhase — records the just-uploaded experiment to SQLite for future ML.

Wraps `phase_e_learning.log_experiment(ctx)` in the Phase protocol. Terminal
side-effect phase: writes one row to `data/experiments.db`'s
`shorts_experiments` table capturing the genesis parameters of the new video
(title, topic, playlist_category, music_vibe, video_pacing, script_tone,
hook_text, voice_id, loop_bridge, video_id).

What this phase DOES
====================

1. Call `log_experiment(ctx)` — which itself calls `init_db()` first, so no
   orchestrator-level DB setup is required.
2. Return ok=True iff no exception was raised. The legacy function returns
   None on success; we infer success from "no exception".

What this phase intentionally DOES NOT do (deferred)
====================================================

`phase_e_learning` exposes a second "learning" concern: ``fetch_and_update_
analytics(youtube)``, which pulls historical YouTube analytics for PREVIOUS
videos to inform the next run. Conceptually distinct from `log_experiment`:

* ``fetch_and_update_analytics`` is a **pre-upload** sync (runs once at the
  top of the run to update past data).
* ``log_experiment`` is a **post-upload** writer (one row per new video).

They live in the same module today because both touch the experiments DB,
not because they belong in the same phase. A future slice can introduce an
``AnalyticsSyncPhase`` that runs near the start of the pipeline; until then,
the analytics-sync call in main.py stays where it is.

Pre-condition
=============

Strictly: the upload phase should have populated `ctx.youtube_video_id`.
The legacy `log_experiment` is permissive (silently logs NULL video_id),
and we preserve that behaviour rather than tightening it here — tightening
the contract retroactively would surprise main.py, which intentionally
forces logging with `if ctx.get("youtube_video_id") or True:`.
"""

from __future__ import annotations

import time
import traceback

from cinema.context import PipelineContext
from cinema.phases.base import PhaseResult


class LearningPhase:
    """Pipeline phase that records the upload's genesis parameters to SQLite."""

    name = "learning"

    def run(self, ctx: PipelineContext) -> PhaseResult:
        from phase_e_learning import log_experiment

        start = time.time()
        try:
            log_experiment(ctx)
            return PhaseResult(
                ok=True,
                message=f"logged experiment for video_id={ctx.get('youtube_video_id') or '(none)'}",
                elapsed_s=time.time() - start,
            )
        except Exception as exc:
            traceback.print_exc()
            return PhaseResult(
                ok=False,
                message=f"{type(exc).__name__}: {exc}",
                elapsed_s=time.time() - start,
            )
