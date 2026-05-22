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

import json
import os
import time
from typing import Optional

from config.settings import settings
from performance._net import safe_download


_POLL_INTERVAL_S = 2


def _cost_log(duration_s: float, shot_id: str = "", video_id: str = "") -> None:
    """Tiny fixed cost — Railway GPU amortization (~$0.02 per 5s clip)."""
    try:
        from cost_tracker import CostTracker
        CostTracker().log_api(
            provider="comfyui",
            model="live_portrait",
            operation="performance_capture",
            cost_usd=round(0.02 + 0.004 * float(duration_s), 4),
            shot_id=shot_id,
            video_id=video_id,
        )
    except Exception:
        pass


def generate_live_portrait_performance(
    keyframe_path: str,
    driving_video_path: str,
    output_mp4: str,
    *,
    duration_s: float = 5.0,
    shot_id: str = "",
    video_id: str = "",
    poll_timeout_s: int = 300,
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
        import requests

        # 1) Upload both files to the ComfyUI server
        def _upload(path):
            with open(path, "rb") as f:
                rr = requests.post(
                    f"{server_url}/upload/image",
                    files={"image": f},
                    timeout=60,
                )
            rr.raise_for_status()
            return rr.json().get("name") or os.path.basename(path)

        remote_kf = _upload(keyframe_path)
        remote_dv = _upload(driving_video_path)

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

        # 3) Queue it
        qr = requests.post(f"{server_url}/prompt", json={"prompt": workflow}, timeout=30)
        if not qr.ok:
            print(f"   [LIVE-PORTRAIT] queue failed: HTTP {qr.status_code}")
            return None
        prompt_id = qr.json().get("prompt_id")

        # 4) Poll for completion
        start = time.time()
        while time.time() - start < poll_timeout_s:
            hr = requests.get(f"{server_url}/history/{prompt_id}", timeout=15)
            if hr.ok and prompt_id in hr.json():
                hist = hr.json()[prompt_id]
                outputs = hist.get("outputs", {})
                # Find the first video output
                for node_id, nout in outputs.items():
                    if "gifs" in nout or "videos" in nout:
                        items = nout.get("gifs") or nout.get("videos") or []
                        if items:
                            fname = items[0].get("filename")
                            sub = items[0].get("subfolder", "")
                            ftype = items[0].get("type", "output")
                            view = (
                                f"{server_url}/view"
                                f"?filename={fname}&subfolder={sub}&type={ftype}"
                            )
                            # ComfyUI pod is internal-trusted; allow http.
                            if not safe_download(view, output_mp4, allow_http=True):
                                return None
                            _cost_log(duration_s, shot_id, video_id)
                            print(f"   ✅ LivePortrait: {output_mp4}")
                            return output_mp4
                status = hist.get("status", {})
                if status.get("status_str") == "error":
                    print(f"   [LIVE-PORTRAIT] error: {status.get('messages', [])[:200]}")
                    return None
            time.sleep(_POLL_INTERVAL_S)

        print(f"   [LIVE-PORTRAIT] timed out after {poll_timeout_s}s")
        return None
    except Exception as e:
        print(f"   [LIVE-PORTRAIT] failed: {e}")
        return None
