"""LivePortrait via ComfyUI — budget driving-face engine.

LivePortrait drives a single still keyframe with a driving video to produce a
matched-motion clip. The driving video must already exist (Mode A operator
upload, or Mode B synth from performance/driving_video.py). LivePortrait
itself does NOT generate motion from audio alone — it needs visual frames.

Runs on the existing RunPod / Railway ComfyUI pod via the
ComfyUI-LivePortraitKJ custom node (Kijai's port). Falls through gracefully
to None when the node isn't installed.
"""

from __future__ import annotations

import math
import os
from typing import Optional
from urllib.parse import urlencode

from comfyui_client import RunPodComfyUI
from config.settings import settings
from cost_tracker_lifecycle import cost_tracker_scope
from paid_provider import has_paid_attempt_authority
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
    poll_timeout_s: int = 300,
    cost_tracker=None,
) -> Optional[str]:
    """LivePortrait via ComfyUI — driving video required."""
    server_url = (getattr(settings, "comfyui_server_url", "") or "").rstrip("/")
    if not server_url:
        print("   [LIVE-PORTRAIT] COMFYUI_SERVER_URL not set; skipping")
        return None
    if not (keyframe_path and os.path.exists(keyframe_path)):
        print(f"   [LIVE-PORTRAIT] keyframe missing: {keyframe_path}")
        return None
    if not (driving_video_path and os.path.exists(driving_video_path)):
        print(f"   [LIVE-PORTRAIT] driving video missing: {driving_video_path}")
        return None

    try:
        comfy = RunPodComfyUI(
            server_url,
            auth_token=getattr(settings, "comfyui_api_key", "") or "",
        )

        # The shared client provides bearer auth, graph preflight, bounded
        # transport, WebSocket/history recovery, and ID-scoped cancellation.
        remote_kf = comfy.upload_image(keyframe_path)
        remote_dv = comfy.upload_image(driving_video_path)

        # 2) Build a minimal LivePortrait workflow. Node IDs are local to this
        # workflow — they don't collide with the keyframe pipeline.
        workflow = {
            "10": {"class_type": "LoadImage", "inputs": {"image": remote_kf}},
            "11": {"class_type": "VHS_LoadVideoPath", "inputs": {"video": remote_dv, "force_rate": 25}},
            "20": {
                "class_type": "LivePortraitProcess",
                "inputs": {
                    "source_image": ["10", 0],
                    "driving_video": ["11", 0],
                    "frame_load_cap": int(round(duration_s * 25)),
                    "expression_friendly": True,
                    "use_relative_motion": True,
                    "lip_zero": False,
                    "eye_retargeting": True,
                    "lip_retargeting": True,
                },
            },
            "30": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["20", 0],
                    "frame_rate": 25,
                    "filename_prefix": "live_portrait",
                    "format": "video/h264-mp4",
                    "crf": 19,
                },
            },
        }

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
                    token = (getattr(settings, "comfyui_api_key", "") or "").strip()
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
