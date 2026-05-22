"""Mode B driving-video synthesis.

When a dialogue shot has no operator-uploaded driving video (Mode A), we
generate one automatically from the TTS audio + the approved keyframe.
The result feeds back as `driving_video_path` for LivePortrait or as a
reference for Act-One.

Provider chain (try in order, fall through on failure):
  1. Hedra Character-3 — paid, best lip motion (~$0.05–0.10/shot)
  2. SadTalker via ComfyUI — free on existing pod (cheaper, coarser)
  3. None — caller falls through to a SKIP performance for this shot
"""

from __future__ import annotations

import os
import time
import urllib.request
from typing import Optional

from config.settings import settings


def _cost_log(provider: str, duration_s: float, shot_id: str, video_id: str) -> None:
    try:
        from cost_tracker import CostTracker
        cost = {"hedra": 0.05, "sadtalker": 0.02}.get(provider, 0.02)
        CostTracker().log_api(
            provider=provider, model="driving_face",
            operation="performance_capture_driving",
            cost_usd=cost + 0.005 * float(duration_s),
            shot_id=shot_id, video_id=video_id,
        )
    except Exception:
        pass


def _synth_via_hedra(
    audio_path: str, keyframe_path: str, output_mp4: str, duration_s: float,
    shot_id: str, video_id: str,
) -> Optional[str]:
    """Hedra Character-3 audio→video. We already integrated Hedra for lipsync
    (see lip_sync.py); here we use it specifically to synthesize a driving
    face for downstream Act-One / LivePortrait — same engine, different role.
    """
    api_key = getattr(settings, "hedra_api_key", "") or os.environ.get("HEDRA_API_KEY", "")
    fal_key = getattr(settings, "fal_key", "") or os.environ.get("FAL_KEY", "")

    # Prefer direct Hedra REST when HEDRA_API_KEY is set; otherwise route via
    # FAL (we already integrated Hedra C3 via fal-ai/hedra/character-3).
    if fal_key:
        try:
            import fal_client
            print(f"   [DRIVING/HEDRA-FAL] synth driving face from audio...")
            image_url = fal_client.upload_file(keyframe_path)
            audio_url = fal_client.upload_file(audio_path)
            result = fal_client.subscribe(
                "fal-ai/hedra/character-3",
                arguments={
                    "image_url": image_url,
                    "audio_url": audio_url,
                    "aspect_ratio": "1:1",
                    "resolution": "720p",
                },
                with_logs=False,
            )
            video_url = result.get("video", {}).get("url")
            if video_url:
                urllib.request.urlretrieve(video_url, output_mp4)
                _cost_log("hedra", duration_s, shot_id, video_id)
                print(f"   ✅ Hedra (FAL) driving face: {output_mp4}")
                return output_mp4
        except Exception as e:
            print(f"   [DRIVING/HEDRA-FAL] failed: {e}")

    if not api_key:
        return None

    # Direct Hedra REST API (kept defensive in case FAL is unavailable)
    try:
        import requests
        # 1) Create generation job
        with open(keyframe_path, "rb") as kf, open(audio_path, "rb") as aud:
            files = {"image": kf, "audio": aud}
            r = requests.post(
                "https://api.hedra.com/v1/audio/talking-image",
                headers={"Authorization": f"Bearer {api_key}"},
                files=files,
                timeout=120,
            )
        if not r.ok:
            print(f"   [DRIVING/HEDRA-DIRECT] HTTP {r.status_code}: {r.text[:200]}")
            return None
        body = r.json()
        out_url = body.get("video_url") or body.get("output_url")
        job_id = body.get("job_id") or body.get("id")

        if not out_url and job_id:
            start = time.time()
            while time.time() - start < 240:
                pr = requests.get(
                    f"https://api.hedra.com/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=15,
                )
                if pr.ok:
                    pb = pr.json()
                    if (pb.get("status") or "").lower() in ("complete", "done", "succeeded"):
                        out_url = pb.get("video_url") or pb.get("output_url")
                        break
                    if (pb.get("status") or "").lower() in ("failed", "error"):
                        return None
                time.sleep(3)

        if not out_url:
            return None
        urllib.request.urlretrieve(out_url, output_mp4)
        _cost_log("hedra", duration_s, shot_id, video_id)
        print(f"   ✅ Hedra (direct) driving face: {output_mp4}")
        return output_mp4
    except Exception as e:
        print(f"   [DRIVING/HEDRA-DIRECT] failed: {e}")
        return None


def _synth_via_sadtalker(
    audio_path: str, keyframe_path: str, output_mp4: str, duration_s: float,
    shot_id: str, video_id: str,
) -> Optional[str]:
    """SadTalker via ComfyUI — free fallback when no Hedra access.

    Requires the ComfyUI-SadTalker custom node installed on the pod. We
    follow the same upload→queue→poll pattern as live_portrait.py.
    """
    server_url = (getattr(settings, "comfyui_server_url", "") or "").rstrip("/")
    if not server_url:
        return None

    try:
        import requests

        def _upload(path):
            with open(path, "rb") as f:
                rr = requests.post(f"{server_url}/upload/image", files={"image": f}, timeout=60)
            rr.raise_for_status()
            return rr.json().get("name") or os.path.basename(path)

        remote_kf = _upload(keyframe_path)
        remote_audio = _upload(audio_path)

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

        qr = requests.post(f"{server_url}/prompt", json={"prompt": workflow}, timeout=30)
        if not qr.ok:
            return None
        prompt_id = qr.json().get("prompt_id")

        start = time.time()
        while time.time() - start < 240:
            hr = requests.get(f"{server_url}/history/{prompt_id}", timeout=15)
            if hr.ok and prompt_id in hr.json():
                hist = hr.json()[prompt_id]
                outputs = hist.get("outputs", {})
                for _, nout in outputs.items():
                    items = nout.get("gifs") or nout.get("videos") or []
                    if items:
                        item = items[0]
                        view = (
                            f"{server_url}/view"
                            f"?filename={item.get('filename')}"
                            f"&subfolder={item.get('subfolder', '')}"
                            f"&type={item.get('type', 'output')}"
                        )
                        urllib.request.urlretrieve(view, output_mp4)
                        _cost_log("sadtalker", duration_s, shot_id, video_id)
                        print(f"   ✅ SadTalker driving face: {output_mp4}")
                        return output_mp4
                status = hist.get("status", {})
                if status.get("status_str") == "error":
                    return None
            time.sleep(2)
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
    engine: str = "auto",     # 'auto' | 'hedra' | 'sadtalker'
    shot_id: str = "",
    video_id: str = "",
) -> Optional[str]:
    """Generate a driving face video from TTS audio + a still keyframe.

    Used as Mode B autopilot when no operator-uploaded driving video exists.
    The output feeds into Act-One or LivePortrait as the driving reference.

    Cascade:
      'auto'  → try Hedra first, fall back to SadTalker
      'hedra' → Hedra only
      'sadtalker' → SadTalker only
    """
    if not (audio_path and os.path.exists(audio_path)):
        return None
    if not (keyframe_path and os.path.exists(keyframe_path)):
        return None

    if engine in ("auto", "hedra"):
        r = _synth_via_hedra(audio_path, keyframe_path, output_mp4, duration_s, shot_id, video_id)
        if r:
            return r
        if engine == "hedra":
            return None

    if engine in ("auto", "sadtalker"):
        r = _synth_via_sadtalker(audio_path, keyframe_path, output_mp4, duration_s, shot_id, video_id)
        if r:
            return r

    return None
