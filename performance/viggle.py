"""Viggle — full-body motion retargeting.

Driving video shows a human performing an action; Viggle maps the motion
onto the character in the keyframe. Best for non-dialogue action beats —
running, fighting, dancing, gesturing.

Requires:
  - VIGGLE_API_KEY env var (new)
  - operator-uploaded driving_video_path (Mode A only — Viggle doesn't
    auto-generate driving from audio)
"""

from __future__ import annotations

import os
import time
import urllib.request
from typing import Optional

from config.settings import settings


def _cost_log(shot_id: str = "", video_id: str = "") -> None:
    """Viggle is per-clip pricing (~$0.10–$0.25)."""
    try:
        from cost_tracker import CostTracker
        CostTracker().log_api(
            provider="viggle",
            model="motion_retarget",
            operation="performance_capture",
            cost_usd=0.20,
            shot_id=shot_id,
            video_id=video_id,
        )
    except Exception:
        pass


def generate_viggle_performance(
    keyframe_path: str,
    driving_video_path: str,
    output_mp4: str,
    *,
    background_mode: str = "white",   # 'white' | 'green' | 'transparent'
    shot_id: str = "",
    video_id: str = "",
    poll_timeout_s: int = 300,
) -> Optional[str]:
    """Viggle motion retargeting. Driving video is mandatory.

    Returns the local output path on success, None on failure (graceful).
    """
    api_key = getattr(settings, "viggle_api_key", "") or os.environ.get("VIGGLE_API_KEY", "")
    if not api_key:
        print("   [VIGGLE] VIGGLE_API_KEY not set; skipping")
        return None
    if not (keyframe_path and os.path.exists(keyframe_path)):
        return None
    if not (driving_video_path and os.path.exists(driving_video_path)):
        print(f"   [VIGGLE] driving video missing: {driving_video_path}")
        return None

    try:
        import requests

        # Endpoint shape from Viggle's public API docs. Confirm at implement time —
        # they've changed naming a couple times between v1 and v2.
        url = "https://api.viggle.ai/v1/motion-transfer"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "multipart/form-data",
        }

        with open(keyframe_path, "rb") as kf, open(driving_video_path, "rb") as dv:
            files = {
                "character_image": kf,
                "motion_video": dv,
            }
            data = {"background": background_mode}
            r = requests.post(url, headers={"Authorization": f"Bearer {api_key}"},
                              files=files, data=data, timeout=120)
        if r.status_code not in (200, 201, 202):
            print(f"   [VIGGLE] HTTP {r.status_code}: {r.text[:200]}")
            return None

        body = r.json()
        # Some Viggle plans return the output URL directly, others return a job id
        out_url = body.get("output_url") or body.get("video_url")
        job_id = body.get("job_id") or body.get("id")

        if not out_url and job_id:
            start = time.time()
            while time.time() - start < poll_timeout_s:
                pr = requests.get(
                    f"https://api.viggle.ai/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=15,
                )
                if pr.ok:
                    pb = pr.json()
                    if (pb.get("status") or "").lower() in ("complete", "done", "succeeded"):
                        out_url = pb.get("output_url") or pb.get("video_url")
                        break
                    if (pb.get("status") or "").lower() in ("failed", "error"):
                        return None
                time.sleep(3)

        if not out_url:
            return None
        urllib.request.urlretrieve(out_url, output_mp4)
        _cost_log(shot_id, video_id)
        print(f"   ✅ Viggle: {output_mp4}")
        return output_mp4
    except Exception as e:
        print(f"   [VIGGLE] failed: {e}")
        return None
