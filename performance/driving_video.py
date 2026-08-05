"""Mode B driving-video synthesis.

When a dialogue shot has no operator-uploaded driving video (Mode A), we
generate one automatically from the TTS audio + the approved keyframe.
The result feeds back as `driving_video_path` for LivePortrait or as a
reference for Act-Two.

Provider chain (try in order, fall through on failure):
  1. SadTalker via ComfyUI — free on existing pod
  2. None — caller falls through to a SKIP performance for this shot
"""

from __future__ import annotations

import math
import os
from typing import Optional, Tuple
from urllib.parse import urlencode

from comfyui_client import RunPodComfyUI
from config.settings import settings
from cost_tracker_lifecycle import cost_tracker_scope
from paid_provider import has_paid_attempt_authority
from performance._net import safe_download, validate_video_artifact


# Polling configuration — pulled to constants so timing is auditable and tunable
# without rummaging through the body. SadTalker via ComfyUI is bursty, often
# taking a while to return.
_SADTALKER_POLL_TIMEOUT_S = 240
_SADTALKER_POLL_INTERVAL_S = 2

# Per-provider estimate shape: base + per-second. SadTalker rates are a
# GPU-time estimate.
_DRIVING_FACE_BASE_COST_USD = {"sadtalker": 0.02}
_DRIVING_FACE_COST_PER_SECOND_USD = {"sadtalker": 0.005}


def estimate_driving_face_cost(provider: str, duration_s: float) -> float:
    """Estimate Mode-B driving-face spend for a provider and clip duration."""
    try:
        duration = float(duration_s)
    except (TypeError, ValueError):
        duration = 5.0
    if not math.isfinite(duration) or duration < 0:
        duration = 5.0
    provider_key = (provider or "sadtalker").lower()
    base = _DRIVING_FACE_BASE_COST_USD.get(provider_key, _DRIVING_FACE_BASE_COST_USD["sadtalker"])
    per_s = _DRIVING_FACE_COST_PER_SECOND_USD.get(provider_key, _DRIVING_FACE_COST_PER_SECOND_USD["sadtalker"])
    return round(base + per_s * duration, 4)


def _cost_log(provider: str, duration_s: float, shot_id: str, video_id: str, cost_tracker=None) -> None:
    try:
        with cost_tracker_scope(cost_tracker) as tracker:
            tracker.log_api(
                provider=provider, model="driving_face",
                operation="performance_capture_driving",
                cost_usd=estimate_driving_face_cost(provider, duration_s),
                shot_id=shot_id, video_id=video_id,
            )
    except Exception:
        pass  # Cost tracking is best-effort — import or write failure doesn't fail the render


def _synth_via_sadtalker(
    audio_path: str, keyframe_path: str, output_mp4: str, duration_s: float,
    shot_id: str, video_id: str, cost_tracker=None,
) -> Optional[str]:
    """SadTalker via ComfyUI.

    Requires the ComfyUI-SadTalker custom node installed on the pod. We
    follow the same upload→queue→poll pattern as live_portrait.py.
    """
    server_url = (getattr(settings, "comfyui_server_url", "") or "").rstrip("/")
    if not server_url:
        return None

    try:
        comfy = RunPodComfyUI(
            server_url,
            auth_token=getattr(settings, "comfyui_api_key", "") or "",
        )
        remote_kf = comfy.upload_image(keyframe_path)
        remote_audio = comfy.upload_image(audio_path)

        workflow = {
            "10": {"class_type": "LoadImage", "inputs": {"image": remote_kf}},
            "11": {"class_type": "LoadAudio", "inputs": {"audio": remote_audio}},
            "20": {
                "class_type": "SadTalker",
                "inputs": {
                    "image": ["10", 0],
                    "audio": ["11", 0],
                    "preprocess": "crop",
                    "still_mode": False,
                    "expression_scale": 1.0,
                    "size": 256,
                },
            },
            "30": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["20", 0],
                    "frame_rate": 25,
                    "filename_prefix": "sadtalker_driving",
                    "format": "video/h264-mp4",
                },
            },
        }

        durable_cost_recorded = False
        if not has_paid_attempt_authority(cost_tracker):
            prompt_id = comfy.queue_prompt(workflow)
            history = comfy.wait_for_completion(
                prompt_id,
                timeout=float(_SADTALKER_POLL_TIMEOUT_S),
                poll_interval=float(_SADTALKER_POLL_INTERVAL_S),
            )
        else:
            from paid_provider import (
                PaidCallBudgetBlocked,
                PaidCallDeferred,
                PaidCallUnbilled,
                file_fingerprint,
                paid_attempt_id,
                request_fingerprint,
                run_durable_comfy_job,
            )

            stable_request = request_fingerprint(
                "comfy-sadtalker-mode-b",
                file_fingerprint(audio_path),
                file_fingerprint(keyframe_path),
                float(duration_s),
                os.path.abspath(output_mp4),
            )
            try:
                history = run_durable_comfy_job(
                    client=comfy,
                    workflow=workflow,
                    attempt_id=paid_attempt_id(
                        "comfy-mode-b", video_id, shot_id, stable_request
                    ),
                    engine="PERFORMANCE_DRIVING_SADTALKER",
                    operation="performance_capture_driving",
                    estimated_cost_usd=estimate_driving_face_cost(
                        "sadtalker", duration_s
                    ),
                    request_fingerprint_value=stable_request,
                    cost_tracker=cost_tracker,
                    shot_id=shot_id,
                    video_id=video_id,
                    poll_timeout_s=float(_SADTALKER_POLL_TIMEOUT_S),
                    poll_interval_s=float(_SADTALKER_POLL_INTERVAL_S),
                )
                durable_cost_recorded = True
                attempt = cost_tracker.get_latest_paid_attempt(
                    video_id=video_id,
                    shot_id=shot_id,
                    engine="PERFORMANCE_DRIVING_SADTALKER",
                    operation="performance_capture_driving",
                )
                prompt_id = str((attempt or {}).get("provider_job_id") or "")
            except PaidCallBudgetBlocked:
                print("   [DRIVING/SADTALKER] atomic budget reservation refused")
                return None
            except PaidCallDeferred:
                print("   [DRIVING/SADTALKER] prompt requires recovery; no replay started")
                return None
            except PaidCallUnbilled:
                print("   [DRIVING/SADTALKER] prompt is terminal and unbilled")
                return None
        record = history.get(prompt_id, {})
        outputs = record.get("outputs", {}) if isinstance(record, dict) else {}
        for _, nout in outputs.items():
            items = nout.get("gifs") or nout.get("videos") or []
            if items:
                item = items[0]
                query = urlencode({
                    "filename": item.get("filename"),
                    "subfolder": item.get("subfolder", ""),
                    "type": item.get("type", "output"),
                })
                view = f"{server_url}/view?{query}"
                token = (getattr(settings, "comfyui_api_key", "") or "").strip()
                request_headers = (
                    {"Authorization": f"Bearer {token}"} if token else None
                )
                # HTTP is restricted to the operator-configured private,
                # authenticated gateway.
                if not safe_download(
                    view,
                    output_mp4,
                    allow_http=True,
                    request_headers=request_headers,
                    allowed_content_types=("video/mp4",),
                    content_validator=validate_video_artifact,
                ):
                    return None
                if not durable_cost_recorded:
                    _cost_log("sadtalker", duration_s, shot_id, video_id, cost_tracker=cost_tracker)
                print(f"   ✅ SadTalker driving face: {output_mp4}")
                return output_mp4
        return None
    except Exception as e:
        print(f"   [DRIVING/SADTALKER] failed: {e}")
        return None


def synth_driving_face_from_audio(
    audio_path: str,
    keyframe_path: str,
    output_mp4: str,
    *,
    duration_s: float = 5.0,
    engine: str = "auto",     # 'auto' | 'sadtalker'
    shot_id: str = "",
    video_id: str = "",
    cost_tracker=None,
) -> Optional[Tuple[str, str]]:
    """Generate a driving face video from TTS audio + a still keyframe.

    Used as Mode B autopilot when no operator-uploaded driving video exists.
    The output feeds into Act-Two or LivePortrait as the driving reference.

    Cascade:
      'auto'      → SadTalker
      'sadtalker' → SadTalker only

    Cache:
      Results are cached by sha256(audio) + sha256(keyframe) + duration under
      PERFORMANCE_CACHE_DIR (default: data/cache/driving/). On a cache hit the
      function returns immediately with provider='cache' and skips all API calls.

    Returns:
        (path, provider_name) tuple on success — provider_name is one of
        {"sadtalker", "cache"}. None on full failure.
    """
    if not (audio_path and os.path.exists(audio_path)):
        return None
    if not (keyframe_path and os.path.exists(keyframe_path)):
        return None

    # --- Content-hash cache check (MUST come AFTER existence guards above) ---
    import shutil as _shutil
    from performance._cache import driving_cache_key, lookup_cache, store_cache

    key = driving_cache_key(audio_path, keyframe_path, duration_s)
    cached = lookup_cache(key)
    if cached:
        _shutil.copyfile(cached, output_mp4)
        print(f"   ✅ Driving-video cache hit: {cached}")
        return (output_mp4, "cache")

    if engine in ("auto", "sadtalker"):
        r = _synth_via_sadtalker(audio_path, keyframe_path, output_mp4, duration_s, shot_id, video_id, cost_tracker=cost_tracker)
        if r:
            store_cache(key, output_mp4)
            return (r, "sadtalker")

    return None
