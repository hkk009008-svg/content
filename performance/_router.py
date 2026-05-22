"""Performance-engine dispatcher.

Maps the engine name (returned by domain.performance.route_performance_engine)
to the actual adapter call. Keeps ShotController free of per-engine import
boilerplate — controller just calls dispatch().
"""

from __future__ import annotations

import os
import threading
from typing import Optional

from domain.performance import (
    ENGINE_ACT_ONE, ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE, ENGINE_SKIP,
)

# Per-provider concurrency caps. Conservative defaults — Runway and Viggle
# bill per-job and rate-limit hard; LivePortrait runs on our own pod and
# can take a couple in flight. Tune via settings later if needed.
_SEMAPHORE_LIMITS = {
    "ACT_ONE":       1,
    "LIVE_PORTRAIT": 2,
    "VIGGLE":        1,
}
_SEMAPHORES = {
    engine: threading.Semaphore(limit)
    for engine, limit in _SEMAPHORE_LIMITS.items()
}


def _dispatch_inner(
    engine: str,
    *,
    keyframe_path: str,
    audio_path: Optional[str],
    driving_video_path: Optional[str],
    output_mp4: str,
    duration_s: float = 5.0,
    shot_id: str = "",
    video_id: str = "",
) -> Optional[str]:
    """Call the right adapter for the requested engine.

    Returns the output path on success, None on failure (so callers can
    fall through to text-to-video without crashing).

    SKIP returns None immediately — the controller interprets that as
    "no performance, motion_render will use plain text-to-video".
    """
    if engine == ENGINE_SKIP or not engine:
        return None

    if engine == ENGINE_ACT_ONE:
        from performance.act_one import generate_act_one_performance
        return generate_act_one_performance(
            keyframe_path, audio_path or "", output_mp4,
            driving_video_path=driving_video_path,
            duration_s=duration_s,
            shot_id=shot_id, video_id=video_id,
        )

    if engine == ENGINE_LIVE_PORTRAIT:
        # LivePortrait NEEDS a driving video. If none supplied, bail.
        if not (driving_video_path and os.path.exists(driving_video_path)):
            print(f"   [DISPATCH] LIVE_PORTRAIT requires driving video; got none")
            return None
        from performance.live_portrait import generate_live_portrait_performance
        return generate_live_portrait_performance(
            keyframe_path, driving_video_path, output_mp4,
            duration_s=duration_s,
            shot_id=shot_id, video_id=video_id,
        )

    if engine == ENGINE_VIGGLE:
        if not (driving_video_path and os.path.exists(driving_video_path)):
            print(f"   [DISPATCH] VIGGLE requires driving video; got none")
            return None
        from performance.viggle import generate_viggle_performance
        return generate_viggle_performance(
            keyframe_path, driving_video_path, output_mp4,
            shot_id=shot_id, video_id=video_id,
        )

    print(f"   [DISPATCH] unknown engine '{engine}'; skipping")
    return None


def dispatch(
    engine: str,
    *,
    keyframe_path: str,
    audio_path: Optional[str],
    driving_video_path: Optional[str],
    output_mp4: str,
    duration_s: float = 5.0,
    shot_id: str = "",
    video_id: str = "",
) -> Optional[str]:
    """Public entry. Acquires per-provider semaphore, then delegates."""
    if engine == ENGINE_SKIP or not engine:
        return None
    sem = _SEMAPHORES.get(engine)
    if sem is None:
        return _dispatch_inner(
            engine,
            keyframe_path=keyframe_path, audio_path=audio_path,
            driving_video_path=driving_video_path, output_mp4=output_mp4,
            duration_s=duration_s, shot_id=shot_id, video_id=video_id,
        )
    with sem:
        return _dispatch_inner(
            engine,
            keyframe_path=keyframe_path, audio_path=audio_path,
            driving_video_path=driving_video_path, output_mp4=output_mp4,
            duration_s=duration_s, shot_id=shot_id, video_id=video_id,
        )
