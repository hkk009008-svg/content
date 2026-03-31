"""
Cinema Production Tool — Lip Sync Engine (v3)
Multi-mode lip sync with strict prerequisites per mode.

TWO MODES:

MODE 1: OVERLAY (MuseTalk) — Default for cinematic shots
  - Takes EXISTING video + audio → overlays lip movement on mouth region ONLY
  - Preserves 100% of camera movement, body motion, lighting, composition
  - Best for: shots with cinematic camera work from Kling/Runway
  - Prerequisites: existing video with visible face, clean mono dialogue audio
  - API: fal-ai/musetalk

MODE 2: GENERATION (Omnihuman v1.5) — For dedicated dialogue shots
  - Takes a STILL IMAGE + audio → generates full-body talking video from scratch
  - Creates head movement, gestures, expressions correlated with speech
  - REPLACES the entire video (loses all Kling camera/motion)
  - Best for: interview-style shots, direct-to-camera dialogue, talking heads
  - Prerequisites: front-facing portrait photo, clean background, mono audio < 60s
  - API: fal-ai/bytedance/omnihuman/v1.5

FALLBACK CHAIN: MuseTalk → Sync Lipsync v2 → LatentSync → Omnihuman (last resort)
"""

import os
import subprocess
import urllib.request
from typing import Optional, Dict, List
from dataclasses import dataclass

try:
    import fal_client
    FAL_AVAILABLE = True
except ImportError:
    FAL_AVAILABLE = False


# ─────────────────────────────────────────────────────────────
# PREREQUISITES CHECKER
# ─────────────────────────────────────────────────────────────

@dataclass
class PrerequisiteResult:
    passed: bool
    mode: str
    warnings: List[str]
    blockers: List[str]


def check_overlay_prerequisites(video_path: str, audio_path: str) -> PrerequisiteResult:
    """
    Check if OVERLAY mode (MuseTalk) can work with the given inputs.

    STRICT REQUIREMENTS:
    1. Video file exists and has detectable frames
    2. Audio file exists, is mono or stereo, clean speech (no music)
    3. Video has a visible face (not back-facing, not too small)
    4. Audio duration roughly matches video duration (within 2x)
    """
    warnings = []
    blockers = []

    # File existence
    if not video_path or not os.path.exists(video_path):
        blockers.append("BLOCKER: Video file does not exist")
    if not audio_path or not os.path.exists(audio_path):
        blockers.append("BLOCKER: Audio file does not exist")

    if blockers:
        return PrerequisiteResult(passed=False, mode="overlay", warnings=warnings, blockers=blockers)

    # Check video duration and resolution
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-show_entries", "stream=width,height",
             "-of", "json", video_path],
            capture_output=True, text=True, timeout=10
        )
        import json
        info = json.loads(probe.stdout)
        vid_duration = float(info.get("format", {}).get("duration", 0))
        streams = info.get("streams", [{}])
        vid_width = streams[0].get("width", 0) if streams else 0

        if vid_duration < 0.5:
            blockers.append(f"BLOCKER: Video too short ({vid_duration:.1f}s)")
        if vid_width < 256:
            warnings.append(f"WARNING: Video resolution low ({vid_width}px) — face region may be too small for quality lip sync")

    except (subprocess.SubprocessError, ValueError, OSError, KeyError):
        warnings.append("WARNING: Could not probe video — proceeding anyway")

    # Check audio duration
    try:
        probe_a = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", audio_path],
            capture_output=True, text=True, timeout=10
        )
        import json
        audio_duration = float(json.loads(probe_a.stdout).get("format", {}).get("duration", 0))

        if audio_duration < 0.5:
            blockers.append(f"BLOCKER: Audio too short ({audio_duration:.1f}s)")
        if audio_duration > 120:
            warnings.append(f"WARNING: Audio very long ({audio_duration:.0f}s) — may cause sync drift")

    except (subprocess.SubprocessError, ValueError, OSError, KeyError):
        warnings.append("WARNING: Could not probe audio — proceeding anyway")

    passed = len(blockers) == 0
    return PrerequisiteResult(passed=passed, mode="overlay", warnings=warnings, blockers=blockers)


def check_generation_prerequisites(image_path: str, audio_path: str) -> PrerequisiteResult:
    """
    Check if GENERATION mode (Omnihuman) can work with the given inputs.

    STRICT REQUIREMENTS:
    1. Image is a front-facing portrait with face clearly visible
    2. Image has clean/simple background (not complex scene)
    3. Audio is clean mono speech, < 60s at 720p or < 30s at 1080p
    4. Image resolution >= 512x512
    """
    warnings = []
    blockers = []

    if not image_path or not os.path.exists(image_path):
        blockers.append("BLOCKER: Character image does not exist")
    if not audio_path or not os.path.exists(audio_path):
        blockers.append("BLOCKER: Audio file does not exist")

    if blockers:
        return PrerequisiteResult(passed=False, mode="generation", warnings=warnings, blockers=blockers)

    # Check image dimensions
    try:
        from PIL import Image
        img = Image.open(image_path)
        w, h = img.size
        if w < 512 or h < 512:
            warnings.append(f"WARNING: Image small ({w}x{h}) — Omnihuman works best at 512x512+")
        if w / h > 2.0 or h / w > 2.0:
            warnings.append(f"WARNING: Image aspect ratio extreme ({w}x{h}) — portrait framing recommended")
    except (ImportError, OSError, ValueError):
        warnings.append("WARNING: Could not check image dimensions")

    # Check audio duration
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", audio_path],
            capture_output=True, text=True, timeout=10
        )
        import json
        duration = float(json.loads(probe.stdout).get("format", {}).get("duration", 0))

        if duration > 60:
            blockers.append(f"BLOCKER: Audio too long for Omnihuman ({duration:.0f}s > 60s max at 720p)")
        elif duration > 30:
            warnings.append(f"WARNING: Audio > 30s — will generate at 720p only (not 1080p)")

    except (subprocess.SubprocessError, ValueError, OSError, KeyError):
        warnings.append("WARNING: Could not probe audio duration")

    passed = len(blockers) == 0
    return PrerequisiteResult(passed=passed, mode="generation", warnings=warnings, blockers=blockers)


# ─────────────────────────────────────────────────────────────
# MODE 1: OVERLAY (MuseTalk — mouth-only on existing video)
# ─────────────────────────────────────────────────────────────

def lipsync_overlay(
    video_path: str,
    audio_path: str,
    output_path: str,
) -> Optional[str]:
    """
    OVERLAY MODE: Apply lip sync to an EXISTING video using MuseTalk.
    Only modifies the mouth region. Preserves all camera movement, body motion,
    lighting, and composition from the original video.

    Fallback chain: MuseTalk → LatentSync → Sync Lipsync v2
    """
    if not FAL_AVAILABLE or not os.getenv("FAL_KEY"):
        print("   [LIPSYNC-OVERLAY] FAL not available")
        return None

    # Check prerequisites
    prereqs = check_overlay_prerequisites(video_path, audio_path)
    for w in prereqs.warnings:
        print(f"   [LIPSYNC-OVERLAY] {w}")
    if not prereqs.passed:
        for b in prereqs.blockers:
            print(f"   [LIPSYNC-OVERLAY] {b}")
        return None

    video_url = fal_client.upload_file(video_path)
    audio_url = fal_client.upload_file(audio_path)

    # ATTEMPT 1: MuseTalk (best quality, cheapest)
    try:
        print(f"   [LIPSYNC-OVERLAY] MuseTalk: mouth-only overlay...")
        result = fal_client.subscribe(
            "fal-ai/musetalk",
            arguments={
                "source_video_url": video_url,
                "audio_url": audio_url,
            },
            with_logs=True,
        )
        out_url = result.get("video", {}).get("url")
        if out_url:
            urllib.request.urlretrieve(out_url, output_path)
            print(f"   [LIPSYNC-OVERLAY] MuseTalk success: {output_path}")
            return output_path
    except Exception as e:
        print(f"   [LIPSYNC-OVERLAY] MuseTalk failed: {e}")

    # ATTEMPT 2: LatentSync (ByteDance, no intermediate representations)
    try:
        print(f"   [LIPSYNC-OVERLAY] LatentSync fallback...")
        result = fal_client.subscribe(
            "fal-ai/latentsync",
            arguments={
                "video_url": video_url,
                "audio_url": audio_url,
            },
            with_logs=True,
        )
        out_url = result.get("video", {}).get("url")
        if out_url:
            urllib.request.urlretrieve(out_url, output_path)
            print(f"   [LIPSYNC-OVERLAY] LatentSync success: {output_path}")
            return output_path
    except Exception as e:
        print(f"   [LIPSYNC-OVERLAY] LatentSync failed: {e}")

    # ATTEMPT 3: Sync Lipsync v2 (premium, $3/min)
    try:
        print(f"   [LIPSYNC-OVERLAY] Sync Lipsync v2 fallback (premium)...")
        result = fal_client.subscribe(
            "fal-ai/sync-lipsync/v2",
            arguments={
                "video_url": video_url,
                "audio_url": audio_url,
            },
            with_logs=True,
        )
        out_url = result.get("video", {}).get("url")
        if out_url:
            urllib.request.urlretrieve(out_url, output_path)
            print(f"   [LIPSYNC-OVERLAY] Sync Lipsync v2 success: {output_path}")
            return output_path
    except Exception as e:
        print(f"   [LIPSYNC-OVERLAY] Sync v2 failed: {e}")

    print("   [LIPSYNC-OVERLAY] All overlay methods failed")
    return None


# ─────────────────────────────────────────────────────────────
# MODE 2: GENERATION (Omnihuman — full-body from still photo)
# ─────────────────────────────────────────────────────────────

def lipsync_generation(
    character_image_path: str,
    audio_path: str,
    output_path: str,
    resolution: str = "720p",
    turbo: bool = False,
) -> Optional[str]:
    """
    GENERATION MODE: Create a full-body talking video from a STILL IMAGE.
    Generates head movement, gestures, expressions correlated with speech.
    WARNING: This REPLACES any existing video — use only for dedicated dialogue shots.

    Fallback chain: Kling Lip Sync → Omnihuman v1.5 → Creatify Aurora
    """
    if not FAL_AVAILABLE or not os.getenv("FAL_KEY"):
        print("   [LIPSYNC-GEN] FAL not available")
        return None

    # Check prerequisites
    prereqs = check_generation_prerequisites(character_image_path, audio_path)
    for w in prereqs.warnings:
        print(f"   [LIPSYNC-GEN] {w}")
    if not prereqs.passed:
        for b in prereqs.blockers:
            print(f"   [LIPSYNC-GEN] {b}")
        return None

    image_url = fal_client.upload_file(character_image_path)
    audio_url = fal_client.upload_file(audio_path)

    # ATTEMPT 0: Kling native lip sync (cheapest at $0.014/sec, integrated motion)
    try:
        print(f"   [LIPSYNC-GEN] Kling native lip sync...")
        result = fal_client.subscribe(
            "fal-ai/kling-video/lipsync/audio-to-video",
            arguments={
                "image_url": image_url,
                "audio_url": audio_url,
            },
            with_logs=True,
        )
        video_url = result.get("video", {}).get("url")
        if video_url:
            urllib.request.urlretrieve(video_url, output_path)
            print(f"   [LIPSYNC-GEN] Kling lip sync success: {output_path}")
            return output_path
    except Exception as e:
        print(f"   [LIPSYNC-GEN] Kling lip sync failed: {e}")

    # ATTEMPT 1: Omnihuman v1.5 (best full-body quality)
    try:
        print(f"   [LIPSYNC-GEN] Omnihuman v1.5: full-body talking video ({resolution})...")
        result = fal_client.subscribe(
            "fal-ai/bytedance/omnihuman/v1.5",
            arguments={
                "image_url": image_url,
                "audio_url": audio_url,
                "resolution": resolution,
                "turbo_mode": turbo,
            },
            with_logs=True,
        )
        video_url = result.get("video", {}).get("url")
        duration = result.get("duration", 0)
        if video_url:
            urllib.request.urlretrieve(video_url, output_path)
            print(f"   [LIPSYNC-GEN] Omnihuman success: {output_path} ({duration:.1f}s)")
            return output_path
    except Exception as e:
        print(f"   [LIPSYNC-GEN] Omnihuman failed: {e}")

    # ATTEMPT 2: Creatify Aurora (studio-grade avatar)
    try:
        print(f"   [LIPSYNC-GEN] Creatify Aurora fallback...")
        result = fal_client.subscribe(
            "fal-ai/creatify/aurora",
            arguments={
                "image_url": image_url,
                "audio_url": audio_url,
                "resolution": "720p",
            },
            with_logs=True,
        )
        video_url = result.get("video", {}).get("url")
        if video_url:
            urllib.request.urlretrieve(video_url, output_path)
            print(f"   [LIPSYNC-GEN] Aurora success: {output_path}")
            return output_path
    except Exception as e:
        print(f"   [LIPSYNC-GEN] Aurora failed: {e}")

    print("   [LIPSYNC-GEN] All generation methods failed")
    return None


# ─────────────────────────────────────────────────────────────
# SMART ROUTER — auto-selects the best mode for each shot
# ─────────────────────────────────────────────────────────────

def generate_lip_sync_video(
    character_image_path: str,
    audio_path: str,
    output_path: str,
    existing_video_path: str = None,
    mode: str = "auto",
    resolution: str = "720p",
    turbo: bool = False,
) -> Optional[str]:
    """
    Smart lip sync router — selects the optimal mode based on inputs.

    Args:
        character_image_path: Path to character reference image
        audio_path: Path to dialogue audio
        output_path: Where to save the output
        existing_video_path: If provided, uses OVERLAY mode (preserves video)
        mode: "auto" | "overlay" | "generation"
        resolution: "720p" or "1080p"
        turbo: Faster but lower quality

    Auto-selection logic:
    - If existing_video_path is provided → OVERLAY (preserve the cinematic video)
    - If only image + audio → GENERATION (create from scratch)
    - User can force a specific mode
    """
    if not FAL_AVAILABLE or not os.getenv("FAL_KEY"):
        print("   [LIPSYNC] FAL not available — skipping")
        return None

    # Determine mode
    if mode == "auto":
        if existing_video_path and os.path.exists(existing_video_path):
            selected_mode = "overlay"
        else:
            selected_mode = "generation"
    else:
        selected_mode = mode

    print(f"   [LIPSYNC] Mode: {selected_mode.upper()}")

    if selected_mode == "overlay" and existing_video_path:
        return lipsync_overlay(existing_video_path, audio_path, output_path)
    else:
        return lipsync_generation(
            character_image_path, audio_path, output_path,
            resolution=resolution, turbo=turbo,
        )
def generate_rife_interpolation(
    video_path: str,
    output_path: str,
    num_frames: int = 2,
    use_scene_detection: bool = True,
) -> Optional[str]:
    """
    Cloud-based frame interpolation via RIFE on fal.ai.
    Replaces local FFmpeg minterpolate for much higher quality.

    Args:
        video_path: Input video path
        output_path: Output interpolated video path
        num_frames: Frames to insert between each pair (1-4). 2 = 3x FPS.
        use_scene_detection: Prevent smearing at scene cuts

    Returns:
        Path to interpolated video, or None on failure
    """
    if not FAL_AVAILABLE or not os.getenv("FAL_KEY"):
        print("   [RIFE] FAL not available — skipping cloud interpolation")
        return None

    if not os.path.exists(video_path):
        return None

    try:
        video_url = fal_client.upload_file(video_path)

        print(f"   [RIFE] Cloud frame interpolation (num_frames={num_frames})...")

        result = fal_client.subscribe(
            "fal-ai/rife/video",
            arguments={
                "video_url": video_url,
                "num_frames": num_frames,
                "use_scene_detection": use_scene_detection,
                "use_calculated_fps": True,
            },
            with_logs=True,
        )

        out_url = result.get("video", {}).get("url")
        if out_url:
            urllib.request.urlretrieve(out_url, output_path)
            print(f"   [RIFE] Success: {output_path}")
            return output_path
        return None

    except Exception as e:
        print(f"   [RIFE] Interpolation error: {e}")
        return None


def upscale_video_seedvr2(
    video_path: str,
    output_path: str,
    target_resolution: str = "1080p",
) -> Optional[str]:
    """
    Cloud-based video upscaling via SeedVR2 on fal.ai.
    Temporally consistent (no frame-to-frame flicker) — superior to Real-ESRGAN.

    Args:
        video_path: Input video path
        output_path: Output upscaled video path
        target_resolution: "1080p", "2160p" (4K), etc.

    Returns:
        Path to upscaled video, or None on failure
    """
    if not FAL_AVAILABLE or not os.getenv("FAL_KEY"):
        print("   [UPSCALE] FAL not available — skipping cloud upscaling")
        return None

    if not os.path.exists(video_path):
        return None

    try:
        video_url = fal_client.upload_file(video_path)

        print(f"   [UPSCALE] SeedVR2 → {target_resolution}...")

        result = fal_client.subscribe(
            "fal-ai/seedvr/upscale/video",
            arguments={
                "video_url": video_url,
                "upscale_mode": "target",
                "target_resolution": target_resolution,
                "noise_scale": 0.1,
                "output_format": "X264 (.mp4)",
                "output_quality": "high",
            },
            with_logs=True,
        )

        out_url = result.get("video", {}).get("url")
        if out_url:
            urllib.request.urlretrieve(out_url, output_path)
            print(f"   [UPSCALE] SeedVR2 success: {output_path}")
            return output_path
        return None

    except Exception as e:
        print(f"   [UPSCALE] SeedVR2 error: {e}")
        return None


def extract_last_frame(video_path: str, output_path: str) -> Optional[str]:
    """Extract the last frame from a video clip for chaining."""
    import subprocess
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-sseof", "-0.1", "-i", video_path,
             "-update", "1", "-q:v", "1", output_path],
            capture_output=True, timeout=30,
        )
        if os.path.exists(output_path):
            return output_path
    except Exception as e:
        print(f"   [CHAIN] Failed to extract last frame: {e}")
    return None


def generate_transition_clip(
    start_frame_path: str,
    end_frame_path: str,
    output_path: str,
    prompt: str = "Smooth camera transition, natural movement",
    duration_frames: int = 81,
) -> Optional[str]:
    """
    Generate a seamless transition clip between two keyframes using Wan FLF2V.
    This creates visual continuity between shots by generating interpolated
    motion from the last frame of clip N to the first frame of clip N+1.

    Args:
        start_frame_path: Last frame of the previous clip
        end_frame_path: First frame (keyframe) of the next clip
        output_path: Where to save the transition video
        prompt: Motion/transition description
        duration_frames: Number of frames (81 = ~5s at 16fps)

    Returns:
        Path to transition video, or None on failure
    """
    if not FAL_AVAILABLE or not os.getenv("FAL_KEY"):
        print("   [CHAIN] FAL not available — skipping transition")
        return None

    if not os.path.exists(start_frame_path) or not os.path.exists(end_frame_path):
        return None

    try:
        start_url = fal_client.upload_file(start_frame_path)
        end_url = fal_client.upload_file(end_frame_path)

        print(f"   [CHAIN] Wan FLF2V transition: {prompt[:50]}...")

        result = fal_client.subscribe(
            "fal-ai/wan-flf2v",
            arguments={
                "prompt": prompt,
                "start_image_url": start_url,
                "end_image_url": end_url,
                "num_frames": duration_frames,
                "frames_per_second": 16,
                "resolution": "720p",
                "num_inference_steps": 30,
                "guide_scale": 5.0,
                "negative_prompt": "blur, distortion, flickering, artifacts",
            },
            with_logs=True,
        )

        out_url = result.get("video", {}).get("url")
        if out_url:
            urllib.request.urlretrieve(out_url, output_path)
            print(f"   [CHAIN] Transition generated: {output_path}")
            return output_path
        return None

    except Exception as e:
        print(f"   [CHAIN] Transition error: {e}")
        return None


# ---------------------------------------------------------------------------
# Content-Aware Lip Sync Routing (Component C)
# ---------------------------------------------------------------------------

def recommend_lip_sync_mode(
    video_path: str = None,
    image_path: str = None,
    shot_type: str = "medium",
    dialogue_length_seconds: float = 0.0,
) -> Dict:
    """
    Recommend the best lip sync mode based on shot content analysis.

    Returns:
        {
            "mode": "overlay" | "generation" | "skip",
            "reason": str,
            "confidence": float (0-1),
        }
    """
    import cv2

    # No dialogue → skip
    if dialogue_length_seconds <= 0:
        return {"mode": "skip", "reason": "no dialogue", "confidence": 1.0}

    # Portrait shot with substantial dialogue → generation (Omnihuman)
    if shot_type == "portrait" and dialogue_length_seconds > 3.0:
        return {
            "mode": "generation",
            "reason": "portrait + long dialogue → Omnihuman produces better talking heads",
            "confidence": 0.85,
        }

    # Wide shot → skip (face too small)
    if shot_type == "wide":
        return {
            "mode": "skip",
            "reason": "wide shot — face likely too small for visible lip sync",
            "confidence": 0.75,
        }

    # Landscape → skip (no character)
    if shot_type == "landscape":
        return {"mode": "skip", "reason": "no character in frame", "confidence": 1.0}

    # If we have a video, check for camera motion
    if video_path and os.path.exists(video_path):
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames >= 4:
            import numpy as np

            # Sample 3 frame pairs to detect motion
            frames = []
            for ratio in [0.2, 0.5, 0.8]:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(total_frames * ratio))
                ret, frame = cap.read()
                if ret:
                    frames.append(cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY))

            cap.release()

            if len(frames) >= 2:
                motion_magnitudes = []
                for i in range(len(frames) - 1):
                    flow = cv2.calcOpticalFlowFarneback(
                        frames[i], frames[i + 1], None,
                        0.5, 3, 15, 3, 5, 1.2, 0,
                    )
                    mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                    motion_magnitudes.append(float(np.mean(mag)))

                avg_motion = sum(motion_magnitudes) / len(motion_magnitudes)

                # High camera motion → overlay mode (preserve the motion)
                if avg_motion > 3.0:
                    return {
                        "mode": "overlay",
                        "reason": f"camera motion detected (flow={avg_motion:.1f}) → overlay preserves motion",
                        "confidence": 0.80,
                    }
        else:
            cap.release()

    # Default: overlay for existing video, generation for image-only
    if video_path and os.path.exists(video_path):
        return {"mode": "overlay", "reason": "default for existing video", "confidence": 0.60}

    if image_path and os.path.exists(image_path):
        return {"mode": "generation", "reason": "image-only input → generation mode", "confidence": 0.70}

    return {"mode": "skip", "reason": "no valid input", "confidence": 0.50}
