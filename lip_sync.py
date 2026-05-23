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
import urllib.request  # retained for legacy code paths; new downloads use performance._net.safe_download
from performance._net import safe_download
from typing import Optional, Dict, List
from dataclasses import dataclass
from config.settings import settings

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
    if not FAL_AVAILABLE or not settings.fal_key:
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

    # Gate setup for sync-validated escalation across overlay engines
    import shutil as _shutil_overlay
    overlay_gate_enabled, overlay_threshold = _sync_gate_settings()
    overlay_candidates: list = []

    def _overlay_gate_or_stash(engine_name: str) -> bool:
        if not overlay_gate_enabled:
            return True
        score = validate_lipsync_quality(output_path, audio_path)
        print(f"   [LIPSYNC-GATE] overlay/{engine_name} sync_score={score:.3f} (threshold {overlay_threshold:.2f})")
        if score >= overlay_threshold:
            return True
        stash = f"{output_path}.{engine_name}.tmp"
        try:
            _shutil_overlay.copyfile(output_path, stash)
            overlay_candidates.append((score, stash, engine_name))
        except Exception as _e:
            print(f"   [LIPSYNC-GATE] could not stash overlay/{engine_name}: {_e}")
        return False

    # ATTEMPT 0: sync.so v3 (Q=0.90, Sync Labs current best generalist)
    # Handles motion + occlusion + side angles where MuseTalk often fails.
    # Slightly more expensive but better baseline quality on hard inputs.
    try:
        print(f"   [LIPSYNC-OVERLAY] sync.so v3: best generalist...")
        result = fal_client.subscribe(
            "fal-ai/sync-lipsync/v3",
            arguments={
                "video_url": video_url,
                "audio_url": audio_url,
            },
            with_logs=True,
        )
        out_url = result.get("video", {}).get("url")
        if out_url:
            if safe_download(out_url, output_path) is None:
                print(f"   [LIPSYNC-OVERLAY] sync.so v3 download failed")
            elif _overlay_gate_or_stash("syncSoV3"):
                print(f"   [LIPSYNC-OVERLAY] sync.so v3 success: {output_path}")
                return output_path
    except Exception as e:
        # sync.so v3 endpoint might be named differently or not yet on FAL.
        # Falls through to MuseTalk silently — no user-visible regression.
        print(f"   [LIPSYNC-OVERLAY] sync.so v3 failed: {e}")

    # ATTEMPT 1: MuseTalk (mouth-only overlay, cheapest)
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
            if safe_download(out_url, output_path) is None:
                print(f"   [LIPSYNC-OVERLAY] MuseTalk download failed")
            elif _overlay_gate_or_stash("MuseTalk"):
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
            if safe_download(out_url, output_path) is None:
                print(f"   [LIPSYNC-OVERLAY] LatentSync download failed")
            elif _overlay_gate_or_stash("LatentSync"):
                print(f"   [LIPSYNC-OVERLAY] LatentSync success: {output_path}")
                return output_path
    except Exception as e:
        print(f"   [LIPSYNC-OVERLAY] LatentSync failed: {e}")

    # ATTEMPT 3: Sync Lipsync v2 (premium fallback for hard cases)
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
            if safe_download(out_url, output_path) is None:
                print(f"   [LIPSYNC-OVERLAY] Sync Lipsync v2 download failed")
            elif _overlay_gate_or_stash("SyncV2"):
                print(f"   [LIPSYNC-OVERLAY] Sync Lipsync v2 success: {output_path}")
                return output_path
    except Exception as e:
        print(f"   [LIPSYNC-OVERLAY] Sync v2 failed: {e}")

    # Best-of-failed recovery for overlay pipeline
    if overlay_candidates:
        overlay_candidates.sort(key=lambda c: c[0], reverse=True)
        best_score, best_path, best_name = overlay_candidates[0]
        print(f"   [LIPSYNC-GATE] No overlay engine cleared threshold {overlay_threshold:.2f}. "
              f"Returning best-of-failed: {best_name} (score={best_score:.3f})")
        try:
            _shutil_overlay.copyfile(best_path, output_path)
        except Exception as e:
            print(f"   [LIPSYNC-GATE] could not restore best candidate: {e}")
        for _, p, _ in overlay_candidates:
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass
        return output_path

    print("   [LIPSYNC-OVERLAY] All overlay methods failed")
    return None


# ─────────────────────────────────────────────────────────────
# SYNC QUALITY VALIDATION (SyncNet gate)
# ─────────────────────────────────────────────────────────────

def validate_lipsync_quality(video_path: str, audio_path: Optional[str] = None) -> float:
    """Score audio-visual sync confidence in [0, 1].

    Provider chain (best-effort, all optional):
      1. syncnet_python (open-source SyncNet) — true phoneme-level scoring.
      2. Duration-match heuristic — catches GROSS sync failures (mismatched
         clip lengths) but not subtle drift. Better than nothing.
      3. Neutral 1.0 fallback so the gate is a no-op when no scorer is
         installed. The pipeline never blocks on a missing dependency.

    Returns:
        float in [0, 1]. Higher = better sync. 1.0 = "perfect or unmeasurable".
    """
    if not video_path or not os.path.exists(video_path):
        return 0.0

    # Provider 1: syncnet_python (real phoneme-level SyncNet score)
    try:
        from SyncNetInstance import SyncNetInstance  # type: ignore
        import torch  # noqa: F401 — syncnet_python requires torch
        # Defer import; if package present but broken, fall through to heuristic
        scorer = SyncNetInstance()
        # syncnet_python's evaluate returns (offset, confidence, dists).
        # Confidence is the metric we want.
        _offset, conf, _dists = scorer.evaluate({}, video_path)
        return max(0.0, min(1.0, float(conf) / 10.0))  # syncnet conf scale ~ 0-10
    except Exception:
        # ImportError, attribute error, or model checkpoint missing — skip
        pass

    # Provider 2: duration-match heuristic
    try:
        import subprocess
        import json as _json

        def _dur(p):
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", p],
                capture_output=True, text=True, timeout=10,
            )
            return float(_json.loads(r.stdout).get("format", {}).get("duration", 0.0))

        vd = _dur(video_path)
        if vd <= 0:
            return 1.0  # can't probe — neutral
        ad = _dur(audio_path) if audio_path and os.path.exists(audio_path) else vd
        diff_ratio = abs(vd - ad) / max(vd, ad, 0.1)
        # Each 1% drift costs 5pts of sync confidence; 20% drift → 0
        return max(0.0, 1.0 - diff_ratio * 5.0)
    except Exception:
        pass

    # No scorer available — neutral
    return 1.0


def _sync_gate_settings(settings: Optional[dict] = None) -> tuple:
    """Read sync gate config from per-project global settings.

    Returns (enabled, threshold). When `settings` is None, defaults to
    (True, 0.65) — same as before, but no longer pretends to read from the
    env-derived `config.settings.Settings` (which never carried these keys).
    Callers in cinema_pipeline can pass `self.project["global_settings"]`.
    """
    s = settings or {}
    enabled = s.get("lipsync_quality_validation", True)
    try:
        threshold = float(s.get("lipsync_validation_threshold", 0.65))
    except (TypeError, ValueError):
        threshold = 0.65
    return enabled, threshold


# ─────────────────────────────────────────────────────────────
# MODE 2: GENERATION (Hedra Character-3 → Omnihuman → Kling → Aurora)
# ─────────────────────────────────────────────────────────────

def _hedra_aspect_ratio_from_image(image_path: str) -> str:
    """Map portrait aspect ratio to Hedra's accepted strings.
    Hedra accepts: '16:9' | '9:16' | '1:1'. We pick the closest match
    rather than failing on odd source ratios — Hedra crops gracefully.
    """
    try:
        from PIL import Image
        img = Image.open(image_path)
        w, h = img.size
        ratio = w / h
    except Exception:
        return "9:16"  # safest default for portraits

    if ratio > 1.4:
        return "16:9"
    if ratio < 0.75:
        return "9:16"
    return "1:1"


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

    Fallback chain: Hedra Character-3 → Kling Lip Sync → Omnihuman v1.5 → Creatify Aurora
    """
    if not FAL_AVAILABLE or not settings.fal_key:
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

    # SyncNet gate — score each engine's output, fall through if below threshold.
    # Track candidates so we can return the best-scored even if none clears the bar.
    import shutil as _shutil
    gate_enabled, gate_threshold = _sync_gate_settings()
    candidates: list = []  # list of (score, stash_path, engine_name)

    def _gate_or_stash(engine_name: str) -> bool:
        """Called after a successful urlretrieve to output_path. Returns True if
        this engine's output passes the SyncNet gate and the function should
        return early. Returns False to fall through to the next engine; stashes
        the failed candidate so we can pick the best-of-failed at the end.
        """
        if not gate_enabled:
            return True
        score = validate_lipsync_quality(output_path, audio_path)
        print(f"   [LIPSYNC-GATE] {engine_name} sync_score={score:.3f} (threshold {gate_threshold:.2f})")
        if score >= gate_threshold:
            return True
        # Stash this candidate before the next engine overwrites output_path
        stash = f"{output_path}.{engine_name}.tmp"
        try:
            _shutil.copyfile(output_path, stash)
            candidates.append((score, stash, engine_name))
        except Exception as _e:
            print(f"   [LIPSYNC-GATE] could not stash {engine_name}: {_e}")
        return False

    # ATTEMPT 0: Hedra Character-3 (Q=0.93, SOTA portrait talking head)
    # Best emotional micro-expressions + head movement correlated with speech.
    # Native full-body output, handles off-axis angles better than Omnihuman.
    try:
        aspect = _hedra_aspect_ratio_from_image(character_image_path)
        print(f"   [LIPSYNC-GEN] Hedra Character-3 (aspect={aspect}, res={resolution})...")
        result = fal_client.subscribe(
            "fal-ai/hedra/character-3",
            arguments={
                "image_url": image_url,
                "audio_url": audio_url,
                "aspect_ratio": aspect,
                "resolution": resolution,
            },
            with_logs=True,
        )
        video_url = result.get("video", {}).get("url")
        if video_url:
            if safe_download(video_url, output_path) is None:
                print(f"   [LIPSYNC-GEN] Hedra Character-3 download failed")
            elif _gate_or_stash("Hedra"):
                print(f"   [LIPSYNC-GEN] Hedra Character-3 success: {output_path}")
                return output_path
    except Exception as e:
        # Graceful fallback — caller will try the next engine below.
        # If the FAL endpoint name or field schema drifts, the cascade keeps the
        # pipeline running on the legacy engines while we patch the integration.
        print(f"   [LIPSYNC-GEN] Hedra Character-3 failed: {e}")

    # ATTEMPT 1: Kling native lip sync (cheapest at $0.014/sec, integrated motion)
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
            if safe_download(video_url, output_path) is None:
                print(f"   [LIPSYNC-GEN] Kling lip sync download failed")
            elif _gate_or_stash("Kling"):
                print(f"   [LIPSYNC-GEN] Kling lip sync success: {output_path}")
                return output_path
    except Exception as e:
        print(f"   [LIPSYNC-GEN] Kling lip sync failed: {e}")

    # ATTEMPT 2: Omnihuman v1.5 (best full-body quality)
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
            if safe_download(video_url, output_path) is None:
                print(f"   [LIPSYNC-GEN] Omnihuman download failed")
            elif _gate_or_stash("Omnihuman"):
                print(f"   [LIPSYNC-GEN] Omnihuman success: {output_path} ({duration:.1f}s)")
                return output_path
    except Exception as e:
        print(f"   [LIPSYNC-GEN] Omnihuman failed: {e}")

    # ATTEMPT 3: Creatify Aurora (studio-grade avatar)
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
            if safe_download(video_url, output_path) is None:
                print(f"   [LIPSYNC-GEN] Aurora download failed")
            elif _gate_or_stash("Aurora"):
                print(f"   [LIPSYNC-GEN] Aurora success: {output_path}")
                return output_path
    except Exception as e:
        print(f"   [LIPSYNC-GEN] Aurora failed: {e}")

    # SyncNet gate fallback: no engine cleared the threshold. Pick the highest-
    # scored candidate from the stashed attempts. Better than returning None
    # when we have *something* — the operator can review and decide.
    if candidates:
        candidates.sort(key=lambda c: c[0], reverse=True)
        best_score, best_path, best_name = candidates[0]
        print(f"   [LIPSYNC-GATE] No engine cleared threshold {gate_threshold:.2f}. "
              f"Returning best-of-failed: {best_name} (score={best_score:.3f})")
        try:
            _shutil.copyfile(best_path, output_path)
        except Exception as e:
            print(f"   [LIPSYNC-GATE] could not restore best candidate: {e}")
        # Clean up stash files
        for _, p, _ in candidates:
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass
        return output_path

    print("   [LIPSYNC-GEN] All generation methods failed")
    return None


# ─────────────────────────────────────────────────────────────
# MODE 3: PERFORMANCE TRANSFER (Runway Act-One)
# ─────────────────────────────────────────────────────────────
#
# Different paradigm from MuseTalk/Hedra/Omnihuman: Act-One takes a DRIVER VIDEO
# of someone performing the dialogue (acting, gestures, mouth shapes) and
# transfers BOTH the lip sync AND the performance to the target character.
# Quality ceiling is the highest in the registry (Q=0.91) for talking heads
# because the AI doesn't have to invent the performance — it inherits one from
# the driver video.
#
# Inputs differ from the audio-driven cascade — caller supplies a driver video
# instead of an audio file. Wire into pipelines that have a director performance
# captured on phone/webcam.

def lipsync_act_one(
    character_image_path: str,
    driver_video_path: str,
    output_path: str,
    ratio: str = "16:9",
) -> Optional[str]:
    """Runway Act-One — performance transfer from driver video to character.

    Args:
        character_image_path: Target character portrait.
        driver_video_path:    Performance capture (someone speaking the lines,
                              acting the scene). Mouth shapes + facial micro-
                              expressions get transferred to the character.
        output_path:          Where to save the result.
        ratio:                "16:9" | "9:16" | "1:1".

    Returns the saved path or None on failure. Designed for hero shots where
    a director has recorded a reference performance.
    """
    if not FAL_AVAILABLE or not settings.fal_key:
        print("   [LIPSYNC-ACT-ONE] FAL not available")
        return None
    if not character_image_path or not os.path.exists(character_image_path):
        print("   [LIPSYNC-ACT-ONE] Character image missing")
        return None
    if not driver_video_path or not os.path.exists(driver_video_path):
        print("   [LIPSYNC-ACT-ONE] Driver video missing")
        return None

    try:
        image_url = fal_client.upload_file(character_image_path)
        driver_url = fal_client.upload_file(driver_video_path)
        print(f"   [LIPSYNC-ACT-ONE] Runway Act-One (ratio={ratio})...")
        result = fal_client.subscribe(
            "fal-ai/runway/act-one",
            arguments={
                "character_image_url": image_url,
                "driver_video_url": driver_url,
                "aspect_ratio": ratio,
            },
            with_logs=True,
        )
        out_url = result.get("video", {}).get("url")
        if not out_url:
            print("   [LIPSYNC-ACT-ONE] No video URL returned")
            return None
        if safe_download(out_url, output_path) is None:
            print("   [LIPSYNC-ACT-ONE] download failed")
            return None
        print(f"   [LIPSYNC-ACT-ONE] success: {output_path}")
        return output_path
    except Exception as e:
        print(f"   [LIPSYNC-ACT-ONE] failed: {e}")
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
    if not FAL_AVAILABLE or not settings.fal_key:
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
    if not FAL_AVAILABLE or not settings.fal_key:
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
            if safe_download(out_url, output_path) is None:
                print("   [RIFE] download failed")
                return None
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
    if not FAL_AVAILABLE or not settings.fal_key:
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
            if safe_download(out_url, output_path) is None:
                print("   [UPSCALE] SeedVR2 download failed")
                return None
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
    if not FAL_AVAILABLE or not settings.fal_key:
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
            if safe_download(out_url, output_path) is None:
                print("   [CHAIN] transition download failed")
                return None
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
