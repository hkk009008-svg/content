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
from typing import Optional, Tuple

from config.settings import settings
from performance._net import safe_download
from performance._poll import poll_task


# Polling configuration — pulled to constants so timing is auditable and tunable
# without rummaging through the body. Hedra typically returns within 60-120s;
# SadTalker via ComfyUI is bursty, often longer.
_HEDRA_POLL_TIMEOUT_S = 240
_HEDRA_POLL_INTERVAL_S = 3
_SADTALKER_POLL_TIMEOUT_S = 240
_SADTALKER_POLL_INTERVAL_S = 2


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
    """Hedra Character-3 audio→video via direct REST API.

    Uses the direct api.hedra.com REST endpoint exclusively. The fal-ai/hedra/
    character-3 FAL route is HTTP-404-dead (confirmed; see lip_sync.py:574) and
    has been removed. Requires HEDRA_API_KEY; returns None immediately if the
    key is absent so the caller can fall through to the SadTalker cascade without
    burning a timeout window.
    """
    api_key = getattr(settings, "hedra_api_key", "") or os.environ.get("HEDRA_API_KEY", "")

    if not api_key:
        return None

    # Direct Hedra REST API
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
            def _get_status():
                pr = requests.get(
                    f"https://api.hedra.com/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=15,
                )
                if not pr.ok:
                    return {"status": "PENDING"}
                pb = pr.json()
                return {
                    "status": (pb.get("status") or "").upper(),
                    "video_url": pb.get("video_url") or pb.get("output_url"),
                }

            final = poll_task(
                _get_status,
                success_states={"COMPLETE", "DONE", "SUCCEEDED"},
                terminal_states={"FAILED", "ERROR"},
                interval_s=_HEDRA_POLL_INTERVAL_S,
                timeout_s=_HEDRA_POLL_TIMEOUT_S,
            )
            out_url = final.get("video_url") if final else None

        if not out_url:
            return None
        if not safe_download(out_url, output_mp4):
            return None
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

        def _get_sadtalker_status():
            hr = requests.get(f"{server_url}/history/{prompt_id}", timeout=15)
            if not hr.ok or prompt_id not in hr.json():
                return {"status": "PROCESSING"}
            hist = hr.json()[prompt_id]
            inner = hist.get("status", {})
            if inner.get("status_str") == "error":
                return {"status": "FAILED"}
            if hist.get("outputs"):
                return {"status": "SUCCEEDED", "outputs": hist["outputs"]}
            return {"status": "PROCESSING"}

        final = poll_task(
            _get_sadtalker_status,
            success_states={"SUCCEEDED"},
            terminal_states={"FAILED"},
            interval_s=_SADTALKER_POLL_INTERVAL_S,
            timeout_s=_SADTALKER_POLL_TIMEOUT_S,
        )
        if not final:
            return None

        outputs = final["outputs"]
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
                # ComfyUI pod is internal-trusted; allow http (RunPod often
                # exposes the proxy URL without TLS).
                if not safe_download(view, output_mp4, allow_http=True):
                    return None
                _cost_log("sadtalker", duration_s, shot_id, video_id)
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
    engine: str = "auto",     # 'auto' | 'hedra' | 'sadtalker'
    shot_id: str = "",
    video_id: str = "",
) -> Optional[Tuple[str, str]]:
    """Generate a driving face video from TTS audio + a still keyframe.

    Used as Mode B autopilot when no operator-uploaded driving video exists.
    The output feeds into Act-One or LivePortrait as the driving reference.

    Cascade:
      'auto'  → try Hedra first, fall back to SadTalker
      'hedra' → Hedra only
      'sadtalker' → SadTalker only

    Cache:
      Results are cached by sha256(audio) + sha256(keyframe) + duration under
      PERFORMANCE_CACHE_DIR (default: data/cache/driving/). On a cache hit the
      function returns immediately with provider='cache' and skips all API calls,
      avoiding repeat Hedra charges (~$0.05/shot) when inputs haven't changed.

    Returns:
        (path, provider_name) tuple on success — provider_name is one of
        {"hedra", "sadtalker", "cache"}. None on full failure.
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

    if engine in ("auto", "hedra"):
        r = _synth_via_hedra(audio_path, keyframe_path, output_mp4, duration_s, shot_id, video_id)
        if r:
            store_cache(key, output_mp4)
            return (r, "hedra")
        if engine == "hedra":
            return None

    if engine in ("auto", "sadtalker"):
        r = _synth_via_sadtalker(audio_path, keyframe_path, output_mp4, duration_s, shot_id, video_id)
        if r:
            store_cache(key, output_mp4)
            return (r, "sadtalker")

    return None
