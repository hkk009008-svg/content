"""Shared service helpers for the Flask web server.

Phase 7 (partial) of the architecture refactor. The full Phase 7 — deep
decoupling of ``web_server.py`` from ``cinema_pipeline.CinemaPipeline`` —
is a multi-slice effort documented in
``docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md``. This module is the
narrow-scope companion slice: it pulls out helpers from web_server.py
that don't depend on the CinemaPipeline class itself, so they can be
unit-tested and reused once the deep migration starts.

Today's contents:

  make_progress_callback — build an SSE-event-producing callable around
                            a thread-safe queue. The callable is what
                            CinemaPipeline (or any future controller)
                            invokes during long-running operations.

The companion file ``web_server.py`` constructs queues and threads them
through this builder; the builder itself is pure (no module state).
"""

from __future__ import annotations

import json
import queue
from typing import Callable, Optional


def make_progress_callback(progress_queue: Optional[queue.Queue]) -> Callable:
    """Build a progress callback that emits SSE-shaped events into a queue.

    Parameters
    ----------
    progress_queue:
        Destination queue. If None, the returned callback is a no-op —
        useful for non-streaming contexts (CLI, tests) where the same
        producer code is wired into both flows.

    Returns
    -------
    A callable with the signature CinemaPipeline expects as
    ``progress_callback``. Only non-empty / non-negative fields are
    included in each emitted event so the SSE stream stays lean.
    """

    def progress_cb(
        stage,
        detail,
        percent,
        scene_id="",
        shot_id="",
        image_url="",
        identity_score=-1,
        director_review=None,
        coherence_score=-1,
        motion_score=-1,
        shot_type="",
        failure_reason="",
        quality_metrics=None,
        video_url="",
        take_id="",
        take_kind="",
        gate_status=None,
        **kwargs,
    ):
        event = {"stage": stage, "detail": detail, "percent": percent}
        if scene_id:
            event["scene_id"] = scene_id
        if shot_id:
            event["shot_id"] = shot_id
        if image_url:
            event["image_url"] = image_url
        if video_url:
            event["video_url"] = video_url
        if take_id:
            event["take_id"] = take_id
        if take_kind:
            event["take_kind"] = take_kind
        if identity_score >= 0:
            event["identity_score"] = identity_score
        if director_review:
            event["director_review"] = director_review
        if coherence_score >= 0:
            event["coherence_score"] = coherence_score
        if motion_score >= 0:
            event["motion_score"] = motion_score
        if shot_type:
            event["shot_type"] = shot_type
        if failure_reason:
            event["failure_reason"] = failure_reason
        if quality_metrics:
            event["quality_metrics"] = quality_metrics
        if gate_status:
            event["gate_status"] = gate_status
        # NF-3 (docs/STRATEGIC_REVIEW-2026-06-10.md P1-3): pass producer
        # extras through instead of silently discarding **kwargs — this
        # function lagging its producers WAS the defect class (engine on
        # MOTION, spent/budget on BUDGET_EXCEEDED, performance_engine on
        # the SKIP path never reached the UI). Lean-ness: None/"" dropped;
        # 0 and False are real data and pass. Safety: the /stream generator
        # json.dumps()'s every event — ONE non-serializable value would
        # kill the whole SSE stream, so unserializable extras drop here.
        for key, value in kwargs.items():
            if key in event or value is None or value == "":
                continue
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                continue
            event[key] = value
        if progress_queue is not None:
            progress_queue.put(event)

    return progress_cb
