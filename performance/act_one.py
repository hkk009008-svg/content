"""Runway Act-One — character-performance retargeting.

Act-One is Runway's flagship dialogue tool: given a still keyframe of a
character and an audio (or full driving video), it generates a performance
clip with mouth-sync, head motion, and micro-expressions correlated with
the audio.

API surface (as of late-2024 / early-2025 — confirm at implement time):
  - POST https://api.dev.runwayml.com/v1/character_performance
  - GET  https://api.dev.runwayml.com/v1/tasks/{id}  (polled until done)

Auth: bearer token = settings.runwayml_api_secret (already configured for
the existing Runway Gen-4 integration).
"""

from __future__ import annotations

import os
from typing import Optional

from config.settings import settings
from performance._net import safe_download
from performance._poll import poll_task


_POLL_INTERVAL_S = 3


def _cost_log(operation: str, duration_s: float, shot_id: str = "", video_id: str = "") -> None:
    """Best-effort cost log. Doesn't fail the call if tracking isn't wired."""
    try:
        from cost_tracker import CostTracker
        # Runway Act-One: ~$0.05/s of output video (confirm with their pricing page)
        CostTracker().log_api(
            provider="runway",
            model="act_one",
            operation=operation,
            cost_usd=round(0.05 * float(duration_s), 4),
            shot_id=shot_id,
            video_id=video_id,
        )
    except Exception:
        pass


def generate_act_one_performance(
    keyframe_path: str,
    audio_path: str,
    output_mp4: str,
    *,
    driving_video_path: Optional[str] = None,
    duration_s: float = 5.0,
    character_id: str = "",
    shot_id: str = "",
    video_id: str = "",
    poll_timeout_s: int = 300,
) -> Optional[str]:
    """Generate an Act-One performance clip.

    Args:
        keyframe_path: still image of the character (the approved keyframe)
        audio_path:    dialogue audio (used for lip sync + performance timing)
        output_mp4:    local write target
        driving_video_path: optional explicit driving video — Mode A. When
            provided, Act-One uses it for motion + audio for sync. When None,
            Act-One auto-generates the performance from the audio alone.
        duration_s:    target output duration
        character_id / shot_id / video_id: telemetry only

    Returns the output path on success, None on any failure.
    """
    api_key = getattr(settings, "runwayml_api_secret", "") or os.environ.get("RUNWAYML_API_SECRET", "")
    if not api_key:
        print("   [ACT-ONE] RUNWAYML_API_SECRET not set; skipping")
        return None
    if not keyframe_path or not os.path.exists(keyframe_path):
        print(f"   [ACT-ONE] keyframe missing: {keyframe_path}")
        return None
    if not audio_path or not os.path.exists(audio_path):
        print(f"   [ACT-ONE] audio missing: {audio_path}")
        return None

    # Prefer the official SDK when available; fall through to raw REST otherwise.
    # Their Python SDK exposes Act-One as RunwayML().character_performance.create().
    try:
        from runwayml import RunwayML  # type: ignore
        client = RunwayML(api_key=api_key)
        kwargs = {
            "model": "act_one",
            "character": {"type": "image", "uri": _to_data_uri_or_path(keyframe_path)},
            "reference": (
                {"type": "video", "uri": _to_data_uri_or_path(driving_video_path)}
                if driving_video_path and os.path.exists(driving_video_path)
                else {"type": "audio", "uri": _to_data_uri_or_path(audio_path)}
            ),
            "ratio": "1280:720",
            "duration": int(round(duration_s)),
        }
        task = client.character_performance.create(**kwargs)

        def _get_status_sdk():
            t = client.tasks.retrieve(id=task.id)
            return {
                "status": (getattr(t, "status", "") or "").upper(),
                "output": getattr(t, "output", None),
                "failure": getattr(t, "failure", None),
            }

        final = poll_task(
            _get_status_sdk,
            success_states={"SUCCEEDED"},
            terminal_states={"FAILED", "CANCELLED"},
            interval_s=_POLL_INTERVAL_S,
            timeout_s=poll_timeout_s,
        )
        if final is None:
            print(f"   [ACT-ONE] poll terminal or timed out")
            return None
        out_url = (final.get("output") or [None])[0]
        if not out_url:
            print("   [ACT-ONE] SUCCEEDED but no output URL")
            return None
        if not safe_download(out_url, output_mp4):
            return None
        _cost_log("performance_capture", duration_s, shot_id, video_id)
        print(f"   ✅ Act-One: {output_mp4}")
        return output_mp4
    except ImportError:
        # SDK not installed — fall through to raw REST
        return _raw_rest_call(api_key, keyframe_path, audio_path, output_mp4,
                              driving_video_path, duration_s, poll_timeout_s,
                              shot_id, video_id)
    except Exception as e:
        print(f"   [ACT-ONE] SDK call failed: {e}")
        return None


def _to_data_uri_or_path(path: str) -> str:
    """Pass-through. Newer Runway SDK versions accept a file path for the `uri`
    field directly; on older SDKs this would need conversion to a data URI or
    pre-uploaded HTTPS URL. Kept as a seam in case the SDK behavior changes —
    the call falls through to REST on any SDK incompatibility.
    """
    return path


def _raw_rest_call(
    api_key: str, keyframe_path: str, audio_path: str, output_mp4: str,
    driving_video_path: Optional[str], duration_s: float, poll_timeout_s: int,
    shot_id: str, video_id: str,
) -> Optional[str]:
    """Raw REST fallback when the Runway SDK isn't installed.

    Sketches the documented endpoint shape; production should use the SDK.
    Returns None on any failure — graceful for the cascade.
    """
    import base64
    import requests

    def _b64(p: str) -> str:
        with open(p, "rb") as f:
            return "data:application/octet-stream;base64," + base64.b64encode(f.read()).decode()

    try:
        body = {
            "model": "act_one",
            "character": {"type": "image", "uri": _b64(keyframe_path)},
            "ratio": "1280:720",
            "duration": int(round(duration_s)),
        }
        if driving_video_path and os.path.exists(driving_video_path):
            body["reference"] = {"type": "video", "uri": _b64(driving_video_path)}
        else:
            body["reference"] = {"type": "audio", "uri": _b64(audio_path)}

        r = requests.post(
            "https://api.dev.runwayml.com/v1/character_performance",
            json=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Runway-Version": "2024-11-06",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        if r.status_code not in (200, 201, 202):
            print(f"   [ACT-ONE/REST] HTTP {r.status_code}: {r.text[:200]}")
            return None
        task_id = r.json().get("id")
        if not task_id:
            return None

        def _get_status_rest():
            tr = requests.get(
                f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {api_key}", "X-Runway-Version": "2024-11-06"},
                timeout=15,
            )
            if not tr.ok:
                return {"status": "PENDING"}
            body = tr.json()
            return {
                "status": (body.get("status") or "").upper(),
                "output": body.get("output"),
            }

        final = poll_task(
            _get_status_rest,
            success_states={"SUCCEEDED"},
            terminal_states={"FAILED", "CANCELLED"},
            interval_s=_POLL_INTERVAL_S,
            timeout_s=poll_timeout_s,
        )
        if final is None:
            return None
        out_url = (final.get("output") or [None])[0]
        if not out_url:
            return None
        if not safe_download(out_url, output_mp4):
            return None
        _cost_log("performance_capture", duration_s, shot_id, video_id)
        print(f"   ✅ Act-One (REST): {output_mp4}")
        return output_mp4
    except Exception as e:
        print(f"   [ACT-ONE/REST] failed: {e}")
        return None
