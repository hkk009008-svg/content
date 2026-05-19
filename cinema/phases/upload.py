"""UploadPhase — uploads the final video to YouTube (minimal scope).

Wraps the primary-language portion of `phase_d_upload`'s API in the Phase
protocol. **This is intentionally a minimal slice of the legacy upload flow.**

What this phase DOES
====================

1. Validate that `ctx.final_video_path` exists on disk.
2. Authenticate with YouTube (OAuth2 dance via `authenticate_youtube`).
3. Call `upload_video(youtube, ctx)` — the legacy function reads ctx for
   title, description, thumbnail, and stamps `ctx.youtube_video_id` on
   success.
4. Return ok=True iff `ctx.youtube_video_id` is now populated.

What this phase intentionally DOES NOT do (deferred)
====================================================

The legacy `main.py` upload block (lines ~293-340) interleaves several
concerns with the upload itself. These are NOT wrapped here:

* **Scheduled publishing** (`publish_at`) — `main.py` computes a
  publish-time `offset_hours` in the future. There's no
  `ctx.publish_at` field yet; add one and pass it through when needed.
* **Caption upload** (`upload_caption` + SRT generation) — properly
  belongs in its own CaptionPhase (writes SRT, then uploads it).
* **Localization upload** (`upload_localizations`) — used only when
  re-uploading the same video file for foreign-language SEO. Different
  control flow; deserves its own LocalizationPhase if revived.
* **Analytics sync** (`fetch_and_update_analytics`) — really a learning
  concern; will land in LearningPhase.
* **A/B test title export** — file I/O, not an upload concern.

Keeping this phase minimal means each migrated phase has a single,
testable responsibility. Cohesion > coverage.
"""

from __future__ import annotations

import os
import time
import traceback

from cinema.context import PipelineContext
from cinema.phases.base import PhaseResult


class UploadPhase:
    """Pipeline phase that uploads the final video to YouTube.

    Pre-condition:  `ctx.final_video_path` exists.
    Post-condition: `ctx.youtube_video_id` is populated on success.
    """

    name = "upload"

    def run(self, ctx: PipelineContext) -> PhaseResult:
        start = time.time()

        # Cheap precondition check before any auth.
        if not ctx.final_video_path or not os.path.exists(ctx.final_video_path):
            return PhaseResult(
                ok=False,
                message=f"final_video_path missing or not on disk: {ctx.final_video_path!r}",
                elapsed_s=time.time() - start,
            )

        # Lazy import — phase_d_upload pulls Google OAuth deps; keep the
        # cinema package import-graph clean.
        from phase_d_upload import authenticate_youtube, upload_video

        try:
            youtube = authenticate_youtube()
            upload_video(youtube, ctx)
            youtube_video_id = ctx.get("youtube_video_id")
            if not youtube_video_id:
                return PhaseResult(
                    ok=False,
                    message="upload_video returned but ctx.youtube_video_id is empty",
                    elapsed_s=time.time() - start,
                )
            return PhaseResult(
                ok=True,
                message=f"uploaded: video_id={youtube_video_id}",
                elapsed_s=time.time() - start,
            )
        except Exception as exc:
            traceback.print_exc()
            return PhaseResult(
                ok=False,
                message=f"{type(exc).__name__}: {exc}",
                elapsed_s=time.time() - start,
            )
