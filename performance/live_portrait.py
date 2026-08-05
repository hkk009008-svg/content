"""LivePortrait via ComfyUI — budget driving-face engine.

LivePortrait drives a single still keyframe with a driving video to produce a
matched-motion clip. The driving video must be uploaded by the operator.
LivePortrait does NOT generate motion from audio alone — it needs visual
frames.

Runs on the dedicated authenticated ComfyUI worker via the
ComfyUI-LivePortraitKJ custom node (Kijai's port). Returns None when the
role-bound worker contract is unavailable or execution fails.
"""

from __future__ import annotations

import math
import os
from typing import Optional
from urllib.parse import urlencode

from comfyui_client import ComfyUIClient
from config.settings import settings
from cost_tracker_lifecycle import cost_tracker_scope
from paid_provider import has_paid_attempt_authority
from performance.comfyui_endpoint import resolve_performance_comfyui
from performance.live_portrait_workflow import build_live_portrait_workflow
from performance.worker_readiness import (
    performance_capability_from_unified,
    validate_performance_gateway_readiness,
)
from performance._net import safe_download, validate_video_artifact


_POLL_INTERVAL_S = 2


def _cost_log(duration_s: float, shot_id: str = "", video_id: str = "", cost_tracker=None) -> None:
    """Tiny fixed cost — Railway GPU amortization (~$0.02 per 5s clip)."""
    try:
        with cost_tracker_scope(cost_tracker) as tracker:
            tracker.log_api(
                provider="comfyui",
                model="live_portrait",
                operation="performance_capture",
                cost_usd=round(0.02 + 0.004 * float(duration_s), 4),
                shot_id=shot_id,
                video_id=video_id,
            )
    except Exception:
        pass  # Cost tracking is best-effort — import or write failure doesn't fail the render


def _estimated_cost(duration_s: float) -> float:
    """Return the same bounded estimate used by the historical cost log."""

    try:
        duration = float(duration_s)
    except (TypeError, ValueError, OverflowError):
        duration = 5.0
    if not math.isfinite(duration) or duration < 0.0:
        duration = 5.0
    return round(0.02 + 0.004 * duration, 4)


def generate_live_portrait_performance(
    keyframe_path: str,
    driving_video_path: str,
    output_mp4: str,
    *,
    duration_s: float = 5.0,
    shot_id: str = "",
    video_id: str = "",
    request_id: str = "",
    poll_timeout_s: int = 300,
    cost_tracker=None,
) -> Optional[str]:
    """LivePortrait via ComfyUI — driving video required."""
    endpoint = resolve_performance_comfyui(settings)
    server_url = endpoint.server_url
    if not server_url:
        print(
            "   [LIVE-PORTRAIT] PERFORMANCE_COMFYUI_SERVER_URL not set; skipping"
        )
        return None
    if not endpoint.usable:
        print(
            "   [LIVE-PORTRAIT] dedicated worker configuration rejected; skipping"
        )
        return None
    if not (keyframe_path and os.path.exists(keyframe_path)):
        print(f"   [LIVE-PORTRAIT] keyframe missing: {keyframe_path}")
        return None
    if not (driving_video_path and os.path.exists(driving_video_path)):
        print(f"   [LIVE-PORTRAIT] driving video missing: {driving_video_path}")
        return None

    try:
        comfy = ComfyUIClient(
            server_url,
            auth_token=endpoint.api_key,
        )

        # Validate the role, tracked workflow/manifests, and successful
        # one-frame execution proof before any source media leaves the Mac.
        if endpoint.requires_capability_proof:
            performance_capability_from_unified(
                comfy.get_gateway_capabilities_readiness()
            )
        else:
            validate_performance_gateway_readiness(comfy.get_gateway_readiness())

        # The shared client provides bearer auth, graph preflight, bounded
        # transport, WebSocket/history recovery, and ID-scoped cancellation.
        remote_kf = comfy.upload_image(keyframe_path)
        remote_dv = comfy.upload_image(driving_video_path)

        # Build the pinned Kijai 1.1.0 graph. Frame limiting happens at video
        # ingestion, before the driving batch can consume system/GPU memory.
        workflow = build_live_portrait_workflow(remote_kf, remote_dv, duration_s)

        durable = has_paid_attempt_authority(cost_tracker)
        if durable:
            from paid_provider import (
                file_fingerprint,
                paid_attempt_id,
                request_fingerprint,
                run_durable_comfy_job,
            )

            stable_request = request_fingerprint(
                "comfy-live-portrait",
                file_fingerprint(keyframe_path),
                file_fingerprint(driving_video_path),
                float(duration_s),
                request_id,
            )
            attempt_id = paid_attempt_id(
                "comfy-live-portrait",
                video_id,
                shot_id,
                stable_request,
            )
            history = run_durable_comfy_job(
                client=comfy,
                workflow=workflow,
                attempt_id=attempt_id,
                engine="LIVE_PORTRAIT",
                operation="performance_capture",
                estimated_cost_usd=_estimated_cost(duration_s),
                request_fingerprint_value=stable_request,
                cost_tracker=cost_tracker,
                shot_id=shot_id,
                video_id=video_id,
                poll_timeout_s=float(poll_timeout_s),
                poll_interval_s=float(_POLL_INTERVAL_S),
            )
        else:
            prompt_id = comfy.queue_prompt(workflow)
            history = comfy.wait_for_completion(
                prompt_id,
                timeout=float(poll_timeout_s),
                poll_interval=float(_POLL_INTERVAL_S),
            )
        prompt_id = next(iter(history), "") if durable else prompt_id
        record = history.get(prompt_id, {})
        outputs = record.get("outputs", {}) if isinstance(record, dict) else {}
        for node_id, nout in outputs.items():
            if "gifs" in nout or "videos" in nout:
                items = nout.get("gifs") or nout.get("videos") or []
                if items:
                    fname = items[0].get("filename")
                    sub = items[0].get("subfolder", "")
                    ftype = items[0].get("type", "output")
                    query = urlencode({
                        "filename": fname,
                        "subfolder": sub,
                        "type": ftype,
                    })
                    view = f"{server_url}/view?{query}"
                    token = endpoint.api_key
                    request_headers = (
                        {"Authorization": f"Bearer {token}"} if token else None
                    )
                    # HTTP is allowed only for the operator-configured private
                    # gateway. Authentication is forwarded explicitly because
                    # safe_download owns a separate pooled session.
                    if not safe_download(
                        view,
                        output_mp4,
                        allow_http=True,
                        request_headers=request_headers,
                        allowed_content_types=("video/mp4",),
                        content_validator=validate_video_artifact,
                    ):
                        return None
                    if not durable:
                        _cost_log(duration_s, shot_id, video_id, cost_tracker=cost_tracker)
                    print(f"   ✅ LivePortrait: {output_mp4}")
                    return output_mp4
        return None
    except Exception as e:
        print(f"   [LIVE-PORTRAIT] failed: {e}")
        return None
