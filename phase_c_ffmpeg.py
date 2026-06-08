from __future__ import annotations

import os
import time
import json
import subprocess
from typing import TYPE_CHECKING, Optional
from config.settings import settings

if TYPE_CHECKING:
    from cinema.context import PipelineContext

# VEO is still in the default cascade (see line ~99 below). Quota exhaustion
# carries a TTL-based cooldown rather than a permanent flag: any VEO 429 sets
# _VEO_QUOTA_EXHAUSTED_UNTIL to (now + _VEO_QUOTA_TTL_S), and subsequent calls
# short-circuit to try_next_api() until that timestamp passes. Set to 0 means
# no active cooldown. Process restart also clears state (module-level reset).
_VEO_QUOTA_EXHAUSTED_UNTIL: float = 0.0
_VEO_QUOTA_TTL_S: int = 1800  # 30 minutes — Google Veo quotas typically reset hourly

# Providers that can produce 9:16 portrait video (aspect-aware via Phase-3 T3-T6, or
# keyframe-driven). Portrait projects filter the cascade to this set. EXCLUDED:
# LTX (native-only/pod-gated, not aspect-wired), FAL_SVD (not aspect-wired), SEEDANCE
# (intentionally left 16:9). Note: the Kling dispatch keys are KLING_NATIVE + KLING_3_0
# (there is no bare "KLING"); there is no Hedra branch in this module.
PORTRAIT_CAPABLE = frozenset({
    "VEO_NATIVE", "VEO", "SORA_NATIVE", "SORA_2",
    "KLING_NATIVE", "KLING_3_0", "RUNWAY_GEN4", "RUNWAY",
})


def _veo_quota_blocked() -> bool:
    """True if a recent VEO 429 means we should still cascade past VEO.

    Auto-expires after _VEO_QUOTA_TTL_S seconds so the operator doesn't need
    to restart the server to retry once Google's quota window rolls over.
    """
    return _VEO_QUOTA_EXHAUSTED_UNTIL > time.time()

try:
    from runwayml import RunwayML, TaskFailedError
except ImportError:
    RunwayML = None
    TaskFailedError = None

try:
    import fal_client
    FAL_AVAILABLE = True
except ImportError:
    FAL_AVAILABLE = False


def generate_ai_video(
    image_path: str,
    camera_motion: str,
    target_api: str,
    output_mp4: str,
    pacing: str = "moderate",
    character_id: str = None,
    attempted_apis: list = None,
    multi_angle_refs: list = None,
    _cascade_retries: int = 0,
    negative_prompt: str = None,
    shot_type: str = None,
    video_fallbacks: list = None,
    driving_video_path: str = "",
    has_dialogue: bool = False,
    dialogue_native_audio: bool = False,
    duration: str = "8s",
    ctx: Optional["PipelineContext"] = None,
    _cascade_out: Optional[dict] = None,
) -> str:
    """
    Routes an image → video via smart shot-type-aware routing with native APIs.

    v3 changes:
    - Native Kling API (JWT auth, subject binding, face_consistency)
    - Native Google Veo 3.1 (reference images, native audio)
    - Native OpenAI Sora 2 (best motion physics)
    - LTX Video (4K, keyframe interpolation, cheapest)
    - Runway Gen-4 (style refs, turbo preview)
    - Smart routing: shot_type determines primary API
    - Fallback cascade per shot type from workflow_selector

    v4 addition — driving_video_path:
        Optional path to a performance-capture clip (output of Act-One /
        LivePortrait / Viggle). When supplied, engines that accept a
        reference video use it as motion guidance:
          - Veo 3.1 native : reference-video mode
          - Sora 2 native  : init_video parameter
          - Runway Gen-4   : motion reference
          - Kling, LTX     : ignored (no clean motion-reference input) —
                             fall through silently to text-to-video baseline.
        Empty string disables the feature — preserves existing behavior
        for all callers that haven't been updated yet.
    """
    from cinema.context import get_project_setting
    from cinema.aspect import DEFAULT_ASPECT_RATIO, fal_aspect_ratio, runway_ratio, is_portrait
    _aspect = get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)

    if attempted_apis is None:
        attempted_apis = []
    _api_upper = target_api.upper()
    if _api_upper not in attempted_apis:
        attempted_apis.append(_api_upper)

    def _record_video_cascade(winning_engine: str) -> None:
        """Write cascade_metadata into _cascade_out when this engine succeeds.
        attempted_apis reflects all engines tried so far in chronological order
        (oldest first; deduped on append). Called before each engine's
        successful return — Session 6 P2-3.
        """
        if _cascade_out is not None:
            _cascade_out["cascade_metadata"] = {
                "engine": winning_engine,
                "attempts": list(attempted_apis),
            }

    # Shot-type-aware negative prompt — tailored to what each shot type actually suffers from
    if negative_prompt is None:
        _base_neg = (
            "blur, distortion, deformed face, identity change, face morph, extra limbs, "
            "floating objects, flickering, temporal inconsistency, plastic skin, "
            "over-smoothed texture, unnatural eye movement, teeth distortion, "
            "clothing pattern change, sudden lighting shift, smearing motion blur"
        )
        _shot_neg = {
            "portrait": ", closed eyes, half-closed eyes, blown highlights on face, asymmetric pupils, double chin artifact",
            "medium": ", disappearing hands, finger merge, prop teleportation",
            "action": ", frozen pose, static cloth, weightless movement, speed ramp glitch",
            "wide": ", miniature people, giant head, forced perspective error, depth plane pop",
            "landscape": ", floating structures, impossible architecture, sky banding, horizon tilt",
        }
        negative_prompt = _base_neg + _shot_neg.get(shot_type, "")

    print(f"   [VIDEO] Routing to {target_api} (motion: {camera_motion}, shot: {shot_type or 'auto'})")

    def try_next_api():
        # Smart cascade — use shot-type-specific fallbacks if provided
        if video_fallbacks:
            fallback_list = video_fallbacks
        else:
            # Default cascade: all engines in quality order
            fallback_list = [
                "KLING_NATIVE", "SORA_NATIVE", "RUNWAY_GEN4",
                "LTX", "VEO_NATIVE", "KLING_3_0", "SORA_2", "VEO", "RUNWAY",
            ]

        # Filter cascade to engines the operator has enabled.
        # Missing key → treat as enabled (permissive). Explicit enabled:False → drop.
        if ctx is not None:
            from cinema.context import get_project_setting
            _api_engines = get_project_setting(ctx, "api_engines", None)
            if isinstance(_api_engines, dict):
                fallback_list = [
                    api for api in fallback_list
                    if _api_engines.get(api, {}).get("enabled", True) is not False
                ]

        if is_portrait(_aspect):
            fallback_list = [api for api in fallback_list if api.upper() in PORTRAIT_CAPABLE]

        for api in fallback_list:
            if api not in attempted_apis:
                print(f"   [CASCADE] -> {api}")
                return generate_ai_video(
                    image_path, camera_motion, api, output_mp4, pacing,
                    character_id, attempted_apis, multi_angle_refs,
                    shot_type=shot_type, video_fallbacks=video_fallbacks,
                    has_dialogue=has_dialogue,
                    dialogue_native_audio=dialogue_native_audio,
                    duration=duration,
                    ctx=ctx, _cascade_out=_cascade_out,
                )

        # All APIs failed — try the cascade once more after a quota cooldown.
        # Counts: initial pass + 1 retry = 2 total attempts. Operator may raise
        # this limit via the cascade_retry_limit UI knob.
        MAX_CASCADE_RETRIES = 1
        if ctx is not None:
            from cinema.context import get_project_setting
            _override = get_project_setting(ctx, "cascade_retry_limit", None)
            if isinstance(_override, int) and _override >= 0:
                MAX_CASCADE_RETRIES = _override
        if _cascade_retries >= MAX_CASCADE_RETRIES:
            print(f"   [WARN] All video APIs exhausted after {MAX_CASCADE_RETRIES} retry pass(es).")
            return None
        print(
            f"   [WARN] All APIs exhausted. Waiting 30s for quota refresh "
            f"(retry {_cascade_retries + 1}/{MAX_CASCADE_RETRIES})..."
        )
        time.sleep(30)
        first_api = (video_fallbacks or ["KLING_NATIVE"])[0]
        return generate_ai_video(
            image_path, camera_motion, first_api, output_mp4, pacing,
            character_id, [], multi_angle_refs, _cascade_retries=_cascade_retries + 1,
            shot_type=shot_type, video_fallbacks=video_fallbacks,
            has_dialogue=has_dialogue,
            dialogue_native_audio=dialogue_native_audio,
            duration=duration,
            ctx=ctx, _cascade_out=_cascade_out,
        )

    # If the operator has disabled this engine via api_engines, skip straight to
    # the cascade. This check is placed after try_next_api() is defined so it can
    # call it immediately. Respects operator intent: "if I disabled engine X,
    # don't use X even when explicitly targeted."
    if ctx is not None:
        from cinema.context import get_project_setting
        _api_engines = get_project_setting(ctx, "api_engines", None)
        if isinstance(_api_engines, dict):
            if _api_engines.get(target_api.upper(), {}).get("enabled", True) is False:
                print(f"   [VIDEO] {target_api.upper()} disabled by api_engines — delegating to cascade")
                return try_next_api()

    # ═══════════════════════════════════════════════════════════════
    # NATIVE API HANDLERS (priority — direct, no proxy, lower cost)
    # ═══════════════════════════════════════════════════════════════

    if target_api.upper() == "KLING_NATIVE":
        # Native Kling 3.0 — JWT auth, subject binding, face_consistency
        try:
            from kling_native import KlingNativeAPI
            kling = KlingNativeAPI()
            result = kling.generate_video(
                image_path=image_path,
                prompt=(
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration and deceleration. "
                    f"SUBJECT: Maintain rigid facial bone structure — zero face deformation between frames. "
                    f"Same hair, skin tone, clothing pattern in every frame. "
                    f"PHYSICS: Natural body movement with weight and momentum, realistic motion blur. "
                    f"TEMPORAL: Consistent inter-frame luminance, stable color temperature, no flickering. "
                    f"QUALITY: Photorealistic cinematic footage, high definition, consistent volumetric lighting."
                ),
                output_path=output_mp4,
                negative_prompt=negative_prompt,
                face_consistency=True if shot_type in ("portrait", "medium", "action") else False,
                image_references=multi_angle_refs,
                duration="5",
                mode="pro",
            )
            if result:
                # Aspect backstop (also at the other 10 cascade success sites): probe output_mp4 —
                # the file the provider wrote (result==output_mp4 for native branches; see the
                # _accept_or_reject caller contract). Wrong orientation → cascade; no-op for landscape.
                if not _accept_or_reject(output_mp4, _aspect):
                    print(f"   [ASPECT-BACKSTOP] {target_api.upper()} produced wrong orientation for {_aspect} — rejecting → cascade")
                    return try_next_api()
                _record_video_cascade(target_api.upper())
                return result
            return try_next_api()
        except Exception as e:
            print(f"   [WARN] Kling Native error: {e}")
            return try_next_api()

    elif target_api.upper() == "SORA_NATIVE":
        # Native OpenAI Sora 2 — best motion physics
        try:
            from sora_native import SoraNativeAPI
            sora = SoraNativeAPI()

            # Smart duration: Sora accepts [4,8,12,16,20] — pick based on shot type
            # Action/dynamic shots benefit from 8s for full physics arcs
            # Portrait/medium stay at 4s to minimize temporal drift
            _sora_durations = {"action": 8, "wide": 8, "landscape": 8, "portrait": 4, "medium": 4}
            sora_duration = _sora_durations.get(shot_type, 4)

            # Sora excels at cloth simulation and gravity — emphasize these.
            # When a performance-capture driving clip exists, Sora uses it as
            # input_reference (video conditioning) so the character's motion
            # follows the real human performance.
            result = sora.generate_video(
                image_path=image_path,
                prompt=(
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration, weight-aware deceleration. "
                    f"SUBJECT: Maintain exact character appearance throughout — same clothing texture and pattern. "
                    f"PHYSICS: Natural body movement with realistic weight distribution, cloth draping and fabric "
                    f"responding to movement direction, hair physics with momentum, consistent gravity throughout. "
                    f"TEMPORAL: Consistent luminance, stable color temperature, no flickering between frames. "
                    f"QUALITY: Photorealistic cinematic footage, natural film grain, volumetric depth."
                ),
                output_path=output_mp4,
                duration=sora_duration,
                resolution="1080p",
                driving_video_path=driving_video_path,
                aspect_ratio=fal_aspect_ratio(_aspect),
            )
            if result:
                if not _accept_or_reject(output_mp4, _aspect):
                    print(f"   [ASPECT-BACKSTOP] {target_api.upper()} produced wrong orientation for {_aspect} — rejecting → cascade")
                    return try_next_api()
                _record_video_cascade(target_api.upper())
                return result
            return try_next_api()
        except Exception as e:
            print(f"   [WARN] Sora Native error: {e}")
            return try_next_api()

    elif target_api.upper() == "VEO_NATIVE":
        # Native Google Veo 3.1 — reference images + native audio
        try:
            from veo_native import VeoNativeAPI
            veo = VeoNativeAPI()
            result = veo.generate_video(
                image_path=image_path,
                prompt=(
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration. "
                    f"PRESERVE: Maintain exact character appearance from reference images. "
                    f"PHYSICS: Natural body weight and momentum, cloth physics, realistic shadows. "
                    f"TEMPORAL: Consistent luminance, stable color temperature, no flickering. "
                    f"QUALITY: Photorealistic cinematic footage, consistent volumetric lighting."
                ),
                output_path=output_mp4,
                reference_images=multi_angle_refs,
                generate_audio=(shot_type == "landscape" or dialogue_native_audio),  # Environments + native-mode dialogue
                driving_video_path=driving_video_path,
                duration=duration,
                aspect_ratio=fal_aspect_ratio(_aspect),
            )
            if result:
                if not _accept_or_reject(output_mp4, _aspect):
                    print(f"   [ASPECT-BACKSTOP] {target_api.upper()} produced wrong orientation for {_aspect} — rejecting → cascade")
                    return try_next_api()
                _record_video_cascade(target_api.upper())
                return result
            return try_next_api()
        except Exception as e:
            print(f"   [WARN] Veo Native error: {e}")
            return try_next_api()

    elif target_api.upper() == "LTX":
        # LTX Video 2.3 — 4K, cheapest, best for environments + transitions
        try:
            from ltx_native import LTXVideoAPI
            ltx = LTXVideoAPI()

            # LTX has 15 native camera motions — map our motions to LTX params
            _ltx_camera_map = {
                "zoom_in_slow": "zoom_in", "zoom_out_slow": "zoom_out",
                "zoom_in_fast": "zoom_in", "pan_right": "pan_right",
                "pan_left": "pan_left", "pan_up_crane": "crane_up",
                "pan_down": "jib_down", "static_drone": "static",
                "dolly_in_rapid": "dolly_in",
            }
            ltx_camera = _ltx_camera_map.get(camera_motion, camera_motion)

            # Use 4K for landscape, 1080p for everything else
            ltx_resolution = "4k" if shot_type == "landscape" else "1080p"

            result = ltx.generate_video(
                image_path=image_path,
                prompt=(
                    f"MOTION: Smooth cinematic {camera_motion}, gradual acceleration. "
                    f"PRESERVE: Maintain character appearance and environment consistency throughout. "
                    f"QUALITY: Photorealistic cinematic footage, natural motion, architectural detail, "
                    f"consistent volumetric lighting, no artifacts."
                ),
                output_path=output_mp4,
                camera_motion=ltx_camera,
                resolution=ltx_resolution,
            )
            if result:
                if not _accept_or_reject(output_mp4, _aspect):
                    print(f"   [ASPECT-BACKSTOP] {target_api.upper()} produced wrong orientation for {_aspect} — rejecting → cascade")
                    return try_next_api()
                _record_video_cascade(target_api.upper())
                return result
            return try_next_api()
        except Exception as e:
            print(f"   [WARN] LTX error: {e}")
            return try_next_api()

    elif target_api.upper() == "RUNWAY_GEN4":
        # Runway Gen-4 — style lock with 3 refs, best prompt adherence
        try:
            from runwayml import RunwayML
            client = RunwayML(api_key=settings.runwayml_api_secret)
            import urllib.request

            print(f"   [RUNWAY-GEN4] Runway Gen-4 I2V with style lock")

            # Upload image as data URI or use URL
            import base64
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            data_uri = f"data:image/jpeg;base64,{img_b64}"

            task = client.image_to_video.create(
                model="gen4_turbo",
                prompt_image=data_uri,
                prompt_text=(
                    f"Smooth cinematic {camera_motion}. "
                    f"Maintain exact character appearance throughout. "
                    f"Natural body movement, consistent lighting, photorealistic quality."
                ),
                duration=10,
                ratio=runway_ratio(_aspect, "gen4_turbo"),
            )
            # Poll
            task = client.tasks.retrieve(id=task.id)
            max_wait = 300
            elapsed = 0
            while task.status not in ("SUCCEEDED", "FAILED") and elapsed < max_wait:
                time.sleep(10)
                elapsed += 10
                task = client.tasks.retrieve(id=task.id)
                if elapsed % 30 == 0:
                    print(f"   [RUNWAY-GEN4] Polling... ({elapsed}s)")

            if task.status == "SUCCEEDED" and task.output:
                video_url = task.output[0] if isinstance(task.output, list) else task.output
                urllib.request.urlretrieve(video_url, output_mp4)
                print(f"   [RUNWAY-GEN4] Success: {output_mp4}")
                if not _accept_or_reject(output_mp4, _aspect):
                    print(f"   [ASPECT-BACKSTOP] {target_api.upper()} produced wrong orientation for {_aspect} — rejecting → cascade")
                    return try_next_api()
                _record_video_cascade(target_api.upper())
                return output_mp4

            print(f"   [WARN] Runway Gen-4 {task.status}")
            return try_next_api()

        except Exception as e:
            print(f"   [WARN] Runway Gen-4 error: {e}")
            return try_next_api()

    # ═══════════════════════════════════════════════════════════════
    # FAL PROXY HANDLERS (fallback — when native APIs unavailable)
    # ═══════════════════════════════════════════════════════════════

    elif target_api.upper() == "SORA_2":
        # Sora 2 via fal.ai — strongest motion physics, 25 seconds continuous
        fal_key = settings.fal_key
        if fal_key and FAL_AVAILABLE:
            try:
                import urllib.request

                print(f"   [SORA2] fal.ai Sora 2 I2V (25s continuous)")

                start_url = fal_client.upload_file(image_path)

                sora_prompt = (
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration and deceleration, "
                    f"no abrupt speed changes. "
                    f"SUBJECT: Maintain rigid facial bone structure — zero face deformation between frames. "
                    f"Same hair, skin, clothing texture in every frame. "
                    f"PRESERVE: Do not morph, distort, or alter character identity at any frame. "
                    f"PHYSICS: Natural body movement with weight and momentum, realistic directional motion blur, "
                    f"consistent gravity, cloth physics responding to movement. "
                    f"TEMPORAL: Consistent inter-frame luminance, stable color temperature, "
                    f"no flickering or sudden lighting shifts. "
                    f"QUALITY: Photorealistic cinematic footage, natural film grain, high definition."
                )

                result = fal_client.subscribe(
                    "fal-ai/sora-2/image-to-video",
                    arguments={
                        "prompt": sora_prompt,
                        "image_url": start_url,
                        "aspect_ratio": fal_aspect_ratio(_aspect),
                        "duration": 4,
                    },
                    with_logs=True,
                )

                video_url = result.get("video", {}).get("url")
                if video_url:
                    urllib.request.urlretrieve(video_url, output_mp4)
                    print(f"   [SORA2] Success: {output_mp4}")
                    if not _accept_or_reject(output_mp4, _aspect):
                        print(f"   [ASPECT-BACKSTOP] {target_api.upper()} produced wrong orientation for {_aspect} — rejecting → cascade")
                        return try_next_api()
                    _record_video_cascade(target_api.upper())
                    return output_mp4

                return try_next_api()

            except Exception as e:
                print(f"   [WARN] Sora 2 error: {e}")
                return try_next_api()
        else:
            print("   [WARN] FAL_KEY missing for Sora 2. Cascading...")
            return try_next_api()

    elif target_api.upper() == "VEO":
        # Veo 3.1 reference-to-video via fal.ai — preserves subject from reference images
        global _VEO_QUOTA_EXHAUSTED_UNTIL
        if _veo_quota_blocked():
            remaining = int(_VEO_QUOTA_EXHAUSTED_UNTIL - time.time())
            print(f"   [VEO] Quota cooldown active ({remaining}s remaining). Cascading...")
            return try_next_api()

        fal_key = settings.fal_key
        if fal_key and FAL_AVAILABLE:
            try:
                import urllib.request

                print(f"   [VEO] fal.ai Veo 3.1 reference-to-video")

                # Upload reference images for subject preservation
                image_urls = []
                if multi_angle_refs:
                    for ref_path in multi_angle_refs[:4]:
                        if os.path.exists(ref_path):
                            try:
                                image_urls.append(fal_client.upload_file(ref_path))
                            except (OSError, RuntimeError) as e:
                                print(f"   [WARN] Failed to upload ref {ref_path}: {e}")

                # Always include the source keyframe
                if not image_urls:
                    image_urls = [fal_client.upload_file(image_path)]

                veo_prompt = (
                    f"MOTION: Smooth cinematic {camera_motion}, natural acceleration, no sudden jumps. "
                    f"PRESERVE: Maintain rigid facial bone structure from reference images — "
                    f"zero face deformation between frames. Same hair, skin tone, clothing texture throughout. "
                    f"CONSTRAIN: Do not morph facial features. Do not change clothing pattern. "
                    f"Do not alter skin tone or hair between frames. "
                    f"PHYSICS: Natural body weight and momentum, cloth physics, realistic shadows. "
                    f"TEMPORAL: Consistent inter-frame luminance, stable color temperature, no flickering. "
                    f"QUALITY: Photorealistic cinematic footage, natural motion physics, "
                    f"consistent volumetric lighting throughout, no visual artifacts."
                )

                result = fal_client.subscribe(
                    "fal-ai/veo3.1/reference-to-video",
                    arguments={
                        "prompt": veo_prompt,
                        "image_urls": image_urls,
                        "aspect_ratio": fal_aspect_ratio(_aspect),
                        "duration": duration,
                        "resolution": "720p",
                        "generate_audio": False,
                    },
                    with_logs=True,
                )

                video_url = result.get("video", {}).get("url")
                if video_url:
                    urllib.request.urlretrieve(video_url, output_mp4)
                    print(f"   [VEO] Success: {output_mp4}")
                    if not _accept_or_reject(output_mp4, _aspect):
                        print(f"   [ASPECT-BACKSTOP] {target_api.upper()} produced wrong orientation for {_aspect} — rejecting → cascade")
                        return try_next_api()
                    _record_video_cascade(target_api.upper())
                    return output_mp4

                return try_next_api()

            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
                    _VEO_QUOTA_EXHAUSTED_UNTIL = time.time() + _VEO_QUOTA_TTL_S
                    print(f"   [VEO] Quota exhausted — blocking VEO for {_VEO_QUOTA_TTL_S}s")
                print(f"   [WARN] Veo 3.1 error: {e}")
                return try_next_api()
        else:
            print("   [WARN] FAL_KEY missing for Veo. Cascading...")
            return try_next_api()
            
    elif target_api.upper() == "KLING_3_0":
        # Kling 3.0 Pro via fal.ai — with subject binding + multi-angle references
        fal_key = settings.fal_key
        if fal_key and FAL_AVAILABLE:
            max_attempts = 2
            for attempt in range(1, max_attempts + 1):
                try:
                    import urllib.request

                    print(f"   [KLING] fal.ai Kling 3.0 Pro I2V (attempt {attempt}/{max_attempts})")

                    # Upload the source keyframe
                    start_image_url = fal_client.upload_file(image_path)

                    # Build arguments with structured prompt
                    # Use @Element1 only if we have multi_angle_refs to bind, otherwise generic subject reference
                    has_elements = multi_angle_refs and len([r for r in multi_angle_refs if os.path.exists(r)]) > 0
                    subject_ref = "@Element1" if has_elements else "The character"
                    kling_prompt = (
                        f"MOTION: Smooth cinematic {camera_motion}, natural acceleration and deceleration. "
                        f"SUBJECT: {subject_ref} maintains rigid facial bone structure — zero face deformation between frames. "
                        f"Same hair, skin tone, clothing pattern in every frame. "
                        f"PRESERVE: Do not morph, distort, or alter facial features, eyes, teeth, or hair at any frame. "
                        f"PHYSICS: Natural body movement with weight and momentum, realistic directional motion blur, "
                        f"consistent gravity, cloth physics responding to movement. "
                        f"TEMPORAL: Consistent inter-frame luminance, stable color temperature, no flickering. "
                        f"QUALITY: Photorealistic cinematic footage, high definition, consistent volumetric lighting."
                    )
                    args = {
                        "start_image_url": start_image_url,
                        "prompt": kling_prompt,
                        "duration": "5",
                        "generate_audio": False,
                        "cfg_scale": 0.5,
                        "negative_prompt": (
                            "blur, distortion, deformed face, identity change, face morph, extra limbs, "
                            "floating objects, flickering, temporal inconsistency, plastic skin, "
                            "over-smoothed texture, unnatural eye movement, teeth distortion, "
                            "clothing pattern change, sudden lighting shift, smearing motion blur"
                        ),
                    }

                    # Subject binding — upload multi-angle character references
                    if multi_angle_refs and len(multi_angle_refs) > 0:
                        valid_refs = [r for r in multi_angle_refs if os.path.exists(r)]
                        if valid_refs:
                            frontal_url = fal_client.upload_file(valid_refs[0])
                            extra_urls = []
                            for ref_path in valid_refs[1:6]:  # Up to 5 additional angles  # Max 3 additional angles
                                try:
                                    extra_urls.append(fal_client.upload_file(ref_path))
                                except (OSError, RuntimeError) as e:
                                    print(f"   [WARN] Failed to upload ref {ref_path}: {e}")

                            args["elements"] = [{
                                "frontal_image_url": frontal_url,
                                "reference_image_urls": extra_urls,
                            }]
                            print(f"   [KLING] Subject bound: 1 frontal + {len(extra_urls)} angle refs")

                    result = fal_client.subscribe(
                        "fal-ai/kling-video/v3/pro/image-to-video",
                        arguments=args,
                        with_logs=True,
                    )

                    video_url = result.get("video", {}).get("url")
                    if video_url:
                        urllib.request.urlretrieve(video_url, output_mp4)
                        print(f"   [KLING] Success: {output_mp4}")
                        if not _accept_or_reject(output_mp4, _aspect):
                            print(f"   [ASPECT-BACKSTOP] {target_api.upper()} produced wrong orientation for {_aspect} — rejecting → cascade")
                            return try_next_api()
                        _record_video_cascade(target_api.upper())
                        return output_mp4

                    print(f"   [WARN] Kling returned no video URL")
                    return try_next_api()

                except Exception as e:
                    print(f"   [WARN] Kling 3.0 Pro fal.ai error: {e}")
                    if attempt < max_attempts:
                        time.sleep(5)
                        continue
                    return try_next_api()
        else:
            print("   [WARN] FAL_KEY missing for Kling. Cascading...")
            return try_next_api()

    elif target_api.upper() == "FAL_SVD":
        # Stable Video Diffusion via Fal.ai serverless endpoint (fal-ai/fast-svd).
        # Previously named "COMFY_UI" — misleading because this branch does NOT
        # talk to ComfyUI; it calls the FAL fast-SVD endpoint directly. Renamed
        # for accuracy. Operator override key in shot.target_api should now be
        # "FAL_SVD".
        fal_key = settings.fal_key
        if fal_key and FAL_AVAILABLE:
            try:
                print(f"   ↳ Generating frame via FAL fast-SVD endpoint...")

                # IP-Adapter Injection Simulation:
                ref_img_url = ""
                if character_id and os.path.exists("characters.json"):
                    with open("characters.json") as f:
                        chars = json.load(f)
                    ref_img = chars.get(character_id, {}).get("reference_image")
                    if ref_img and os.path.exists(ref_img):
                        print(f"      ↳ Injecting IP-Adapter Weights for Character: {character_id}")
                        try:
                            ref_img_url = fal_client.upload_file(ref_img)
                        except AttributeError as e:
                            # fal_client.upload_file missing — SDK not loaded properly.
                            # We previously swallowed this and proceeded with an empty
                            # ref URL (silent identity loss). Surface it and cascade.
                            print(f"   [ERROR] fal_client.upload_file missing while uploading character ref: {e}")
                            return try_next_api()

                try:
                    base_img_url = fal_client.upload_file(image_path)
                except AttributeError as e:
                    # We previously substituted a random picsum.photos placeholder.
                    # That produced "successful" videos with the wrong content.
                    # Fail cleanly so the cascade can route to a working backend.
                    print(f"   [ERROR] fal_client.upload_file missing for base image ({image_path}): {e}")
                    return try_next_api()

                result = fal_client.subscribe(
                    "fal-ai/fast-svd",
                    arguments={
                        "image_url": base_img_url,
                        "motion_bucket_id": 127,
                        "cond_aug": 0.02
                    }
                )

                video_url = result.get("video", {}).get("url")
                if video_url:
                    import urllib.request
                    urllib.request.urlretrieve(video_url, output_mp4)
                    if not _accept_or_reject(output_mp4, _aspect):
                        print(f"   [ASPECT-BACKSTOP] {target_api.upper()} produced wrong orientation for {_aspect} — rejecting → cascade")
                        return try_next_api()
                    _record_video_cascade(target_api.upper())
                    return output_mp4
                return try_next_api()
            except Exception as e:
                print(f"   ⚠️ FAL_SVD Serverless Error: {e}")
                print("   ⚠️ Re-routing gracefully...")
                return try_next_api()
        else:
            print("   ⚠️ FAL_KEY missing. Re-routing gracefully...")
            return try_next_api()
            
    elif target_api.upper() == "RUNWAY":
        # RunwayML Elite Cinematic Generation
        runway_key = settings.runwayml_api_secret
        if runway_key:
            try:
                from runwayml import RunwayML
                import base64
                with open(image_path, "rb") as f:
                    b64_img = base64.b64encode(f.read()).decode('utf-8')
                data_uri = f"data:image/jpeg;base64,{b64_img}"

                runway_client = RunwayML(api_key=runway_key)
                video_task = runway_client.image_to_video.create(
                    model="gen3a_turbo",
                    prompt_image=data_uri,
                    prompt_text=f"Smooth {camera_motion}. Cinematic lighting.",
                    ratio=runway_ratio(_aspect, "gen3a_turbo"),
                    duration=5
                )
                print(f"   ↳ Runway Task {video_task.id} queued. Polling...")
                completed_task = video_task.wait_for_task_output()
                final_video_url = completed_task.output[0]
                import urllib.request
                urllib.request.urlretrieve(final_video_url, output_mp4)
                if not _accept_or_reject(output_mp4, _aspect):
                    print(f"   [ASPECT-BACKSTOP] {target_api.upper()} produced wrong orientation for {_aspect} — rejecting → cascade")
                    return try_next_api()
                _record_video_cascade(target_api.upper())
                return output_mp4
            except Exception as e:
                print(f"   ⚠️ Runway API Error: {e}")
                return try_next_api()
        else:
            print("   ⚠️ RunwayML key missing. Re-routing gracefully...")
            return try_next_api()
            
    elif target_api.upper() == "SEEDANCE":
        # Seedance 2.0 (ByteDance) — supports up to 9 reference images for multi-character
        # Best for: multi-character scenes, complex interactions, long duration (20s)
        seedance_key = settings.seedance_api_key
        if seedance_key:
            try:
                import requests
                import base64
                print(f"   ↳ Generating via Seedance 2.0 API (multi-ref capable)...")

                # Encode the source image
                with open(image_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")

                url = "https://api.seedance.ai/v1/video/generate"
                payload = {
                    "model": "seedance-2.0",
                    "prompt": f"Smooth {camera_motion}. Cinematic lighting. Photorealistic. High definition.",
                    "reference_images": [{"image": img_b64, "type": "subject"}],
                    "aspect_ratio": "16:9",
                    "duration": 5,
                    "quality": "high",
                }

                # If we have a character reference, add it as identity reference
                if character_id:
                    char_ref = None
                    if os.path.exists("characters.json"):
                        with open("characters.json", "r") as f:
                            chars = json.load(f)
                        char_data = chars.get(character_id, {})
                        char_ref = char_data.get("reference_image")
                    if char_ref and os.path.exists(char_ref):
                        with open(char_ref, "rb") as f:
                            face_b64 = base64.b64encode(f.read()).decode("utf-8")
                        payload["reference_images"].append({"image": face_b64, "type": "identity"})
                        print(f"      ↳ Seedance: injected identity reference for {character_id}")

                headers = {
                    "Authorization": f"Bearer {seedance_key}",
                    "Content-Type": "application/json",
                }
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                resp.raise_for_status()
                task_id = resp.json().get("task_id") or resp.json().get("id")
                print(f"   ↳ Seedance Task {task_id} queued. Polling...")

                # Poll for completion
                poll_url = f"https://api.seedance.ai/v1/video/status/{task_id}"
                for _ in range(120):  # 10 min max
                    time.sleep(5)
                    poll_resp = requests.get(poll_url, headers=headers).json()
                    status = poll_resp.get("status", "")
                    if status in ("completed", "success"):
                        video_url = poll_resp.get("video_url") or poll_resp.get("output", {}).get("video_url")
                        if video_url:
                            import urllib.request
                            urllib.request.urlretrieve(video_url, output_mp4)
                            print(f"   ✅ Seedance video downloaded: {output_mp4}")
                            if not _accept_or_reject(output_mp4, _aspect):
                                print(f"   [ASPECT-BACKSTOP] {target_api.upper()} produced wrong orientation for {_aspect} — rejecting → cascade")
                                return try_next_api()
                            _record_video_cascade(target_api.upper())
                            return output_mp4
                        break
                    elif status in ("failed", "error"):
                        print(f"   ⚠️ Seedance generation failed: {poll_resp}")
                        break

                return try_next_api()
            except Exception as e:
                print(f"   ⚠️ Seedance API Error: {e}")
                return try_next_api()
        else:
            print("   ⚠️ SEEDANCE_API_KEY missing. Re-routing gracefully...")
            return try_next_api()
    
    else:
        # Fallback if UNKNOWN target API is given
        return try_next_api()

def stitch_modules(module_paths: list, final_output: str) -> str:
    """Stitches normalized MP4 modules sequentially using the FFmpeg concat demuxer."""
    list_file = "concat_list.txt"
    with open(list_file, "w") as f:
        for path in module_paths:
            f.write(f"file '{os.path.abspath(path)}'\n")
            
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", final_output
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"      ❌ FFMPEG CONCAT ERROR: {e.stderr.decode()}")
        raise
        
    os.remove(list_file)
    print(f"      Stitched sequence: {final_output}")
    return final_output


# ---------------------------------------------------------------------------
# Storyboard split (F2a)
# ---------------------------------------------------------------------------

def split_video_into_segments(
    source_path: str,
    durations: list,
    output_dir: str,
    stem: str = "segment",
) -> list:
    """Split a combined video into per-segment mp4s matching the given durations.

    Used by the storyboard integration (F2b) to convert Kling's combined
    storyboard output back into per-shot segments so they can flow through
    the normal per-shot continuity / take-registration / assembly machinery.

    Args:
        source_path: Path to the combined mp4 (e.g. storyboard output).
        durations: Ordered list of floats, one per desired segment (seconds).
            They need not sum exactly to the video length — any remainder is
            absorbed into the final segment (clamped to end-of-video).
        output_dir: Directory in which to write segment files.  Created if
            absent.
        stem: Filename prefix for segment files.  Final names are
            ``{stem}_000.mp4``, ``{stem}_001.mp4``, etc.

    Returns:
        List of absolute paths to the written segment files, in order.
        Returns an empty list if ``source_path`` does not exist or
        ``durations`` is empty.

    Raises:
        RuntimeError: If any ffmpeg subprocess exits with a non-zero code.
            The message includes the captured stderr for diagnosis.

    Notes:
        - Uses ``-c copy`` (stream-copy) for speed and lossless quality.
          Stream-copy may drift slightly at non-keyframe boundaries; this is
          acceptable for continuity validation which is score-based, not
          frame-exact.
        - Segments shorter than 1 s are written as-is (the caller — i.e.,
          the storyboard API — already enforces 1 s minimum per shot during
          duration allocation).
        - The last segment always runs to the end of the source video
          (``-to`` is omitted for the final segment) so floating-point
          accumulation errors do not drop the last few frames.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    if not source_path or not os.path.exists(source_path):
        _log.warning("split_video_into_segments: source not found: %s", source_path)
        return []
    if not durations:
        _log.warning("split_video_into_segments: empty durations list")
        return []

    os.makedirs(output_dir, exist_ok=True)

    segment_paths = []
    start = 0.0

    for idx, dur in enumerate(durations):
        out_path = os.path.join(output_dir, f"{stem}_{idx:03d}.mp4")
        is_last = idx == len(durations) - 1

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", source_path,
        ]
        if not is_last:
            cmd += ["-t", str(dur)]
        cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero", out_path]

        try:
            result = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as exc:
            stderr_text = exc.stderr.decode(errors="replace")
            raise RuntimeError(
                f"split_video_into_segments: ffmpeg failed on segment {idx} "
                f"(start={start:.3f}s, dur={dur:.3f}s): {stderr_text}"
            ) from exc

        segment_paths.append(os.path.abspath(out_path))
        _log.debug(
            "split_video_into_segments: segment %d written (start=%.3fs dur=%.3fs) → %s",
            idx, start, dur, out_path,
        )
        start += dur

    return segment_paths


# ---------------------------------------------------------------------------
# Motion Quality Assessment (Component C)
# ---------------------------------------------------------------------------

def assess_motion_quality(video_path: str, num_samples: int = 10) -> dict:
    """
    Assess video motion quality using optical flow analysis.
    Detects: frame freezing, jitter, warping artifacts.

    Returns:
        {
            "smoothness_score": 0-1 (higher = smoother motion),
            "artifact_frames": [int] (frame indices with issues),
            "frozen_ratio": 0-1 (fraction of near-identical frames),
            "recommendation": "accept" | "interpolate" | "regenerate",
        }
    """
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames < 2:
        cap.release()
        return {
            "smoothness_score": 0.0,
            "artifact_frames": [],
            "frozen_ratio": 1.0,
            "recommendation": "regenerate",
        }

    # Sample frames uniformly
    step = max(1, total_frames // num_samples)
    positions = [i * step for i in range(num_samples) if i * step < total_frames]

    prev_gray = None
    flow_magnitudes = []
    flow_variances = []
    frozen_count = 0
    artifact_frames = []

    for pos in positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = cap.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 180))  # Downsample for speed

        if prev_gray is not None:
            # Farneback optical flow
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, gray, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
            )
            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            mean_mag = float(np.mean(mag))
            var_mag = float(np.var(mag))

            flow_magnitudes.append(mean_mag)
            flow_variances.append(var_mag)

            # Frozen frame detection
            if mean_mag < 0.3:
                frozen_count += 1

            # Artifact detection: extreme flow gradient = warping
            if var_mag > 50.0 or mean_mag > 30.0:
                artifact_frames.append(pos)

        prev_gray = gray

    cap.release()

    if not flow_magnitudes:
        return {
            "smoothness_score": 0.0,
            "artifact_frames": [],
            "frozen_ratio": 1.0,
            "recommendation": "regenerate",
        }

    pairs = len(flow_magnitudes)
    frozen_ratio = frozen_count / pairs if pairs > 0 else 0.0

    # Smoothness = inverse of flow variance (normalized)
    avg_variance = sum(flow_variances) / len(flow_variances)
    smoothness = max(0.0, min(1.0, 1.0 - (avg_variance / 50.0)))

    # Decision
    if frozen_ratio > 0.5:
        recommendation = "regenerate"
    elif len(artifact_frames) > pairs * 0.3:
        recommendation = "regenerate"
    elif smoothness < 0.4:
        recommendation = "interpolate"
    elif frozen_ratio > 0.2:
        recommendation = "interpolate"
    else:
        recommendation = "accept"

    return {
        "smoothness_score": round(smoothness, 3),
        "artifact_frames": artifact_frames,
        "frozen_ratio": round(frozen_ratio, 3),
        "recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# Color Grading & Speed Adjust (Director's Cut tools)
# ---------------------------------------------------------------------------

# Built-in LUT presets mapped to FFmpeg eq/curves filters
COLOR_GRADE_PRESETS = {
    "warm_cinema": "eq=brightness=0.02:contrast=1.1:saturation=1.15,colorbalance=rs=0.05:gs=-0.02:bs=-0.05:rh=0.03",
    "cool_noir": "eq=brightness=-0.03:contrast=1.2:saturation=0.7,colorbalance=rs=-0.05:gs=-0.02:bs=0.08",
    "vibrant": "eq=brightness=0.03:contrast=1.05:saturation=1.4",
    "desaturated": "eq=saturation=0.5:contrast=1.1",
    "golden_hour": "eq=brightness=0.04:saturation=1.2,colorbalance=rs=0.08:gs=0.03:bs=-0.06:rh=0.05:gh=0.02",
    "moonlight": "eq=brightness=-0.05:contrast=1.15:saturation=0.6,colorbalance=rs=-0.03:gs=-0.01:bs=0.1",
    "high_contrast": "eq=contrast=1.4:brightness=-0.02:saturation=0.9",
    "pastel": "eq=brightness=0.06:contrast=0.9:saturation=0.8",
}


def apply_color_grade(video_path: str, output_path: str, preset: str = "warm_cinema", lut_path: str = None) -> str:
    """
    Apply color grading to a video clip.
    Uses either a preset filter chain or a custom LUT file.

    Args:
        video_path: Input video
        output_path: Output graded video
        preset: One of COLOR_GRADE_PRESETS keys
        lut_path: Optional path to .cube/.3dl LUT file (overrides preset)

    Returns:
        Output path on success, None on failure
    """
    if not os.path.exists(video_path):
        return None

    if lut_path and os.path.exists(lut_path):
        vf = f"lut3d={lut_path}"
    else:
        vf = COLOR_GRADE_PRESETS.get(preset, COLOR_GRADE_PRESETS["warm_cinema"])

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        print(f"      [COLOR] Graded ({preset}): {output_path}")
        return output_path
    except Exception as e:
        print(f"      [COLOR] Grading failed: {e}")
        return None


def adjust_speed(video_path: str, output_path: str, factor: float = 1.0) -> str:
    """
    Adjust video speed using FFmpeg setpts filter.

    Args:
        video_path: Input video
        output_path: Output adjusted video
        factor: Speed multiplier (0.5 = half speed / slow-mo, 2.0 = double speed)

    Returns:
        Output path on success, None on failure
    """
    if not os.path.exists(video_path) or factor <= 0:
        return None

    pts_factor = 1.0 / factor  # setpts is inverse: PTS*0.5 = 2x speed
    atempo = factor  # Audio tempo adjustment

    # FFmpeg atempo only supports 0.5-2.0, chain for extreme values
    atempo_chain = []
    remaining = atempo
    while remaining > 2.0:
        atempo_chain.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        atempo_chain.append("atempo=0.5")
        remaining /= 0.5
    atempo_chain.append(f"atempo={remaining:.4f}")

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-filter:v", f"setpts={pts_factor:.4f}*PTS",
        "-filter:a", ",".join(atempo_chain),
        "-c:v", "libx264", "-preset", "fast",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        print(f"      [SPEED] Adjusted {factor}x: {output_path}")
        return output_path
    except Exception as e:
        print(f"      [SPEED] Adjustment failed: {e}")
        return None


def measure_loudness(path: str, target_i: float = -14.0, target_lra: float = 11.0,
                     target_tp: float = -1.5) -> "dict | None":
    """Pass-1 EBU R128 loudness measurement via ffmpeg loudnorm print_format=json.

    Runs ffmpeg in measurement-only mode (no output file) and parses the JSON
    blob that loudnorm prints to stderr. Returns the parsed dict on success
    (contains at minimum: input_i, input_tp, input_lra, input_thresh,
    target_offset), or None on any failure (missing file, timeout, no JSON,
    missing required keys).

    Extracted from two_pass_loudnorm pass-1 (U3 — Final-media conformance).
    two_pass_loudnorm calls this internally; behavior is identical.
    """
    import re

    if not os.path.exists(path):
        return None

    measure_cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-y",
        "-i", path,
        "-af", f"loudnorm=I={target_i}:LRA={target_lra}:TP={target_tp}:print_format=json",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(measure_cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print("   [MEASURE-LOUDNESS] Measurement pass timed out")
        return None

    stderr = result.stderr or ""
    # ffmpeg prints the loudnorm JSON near the end of stderr; grab the last
    # {...} block that contains "input_i". Non-greedy + DOTALL.
    matches = re.findall(r'\{[^{}]*?"input_i"[^{}]*?\}', stderr, flags=re.DOTALL)
    if not matches:
        print("   [MEASURE-LOUDNESS] No measurement JSON in ffmpeg output")
        return None

    try:
        measured = json.loads(matches[-1])
        required = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
        if not all(k in measured for k in required):
            print(f"   [MEASURE-LOUDNESS] Measurement JSON missing keys: "
                  f"{set(required) - set(measured)}")
            return None
        return measured
    except json.JSONDecodeError as e:
        print(f"   [MEASURE-LOUDNESS] JSON parse failed: {e}")
        return None


def two_pass_loudnorm(
    input_video_path: str,
    output_video_path: str,
    target_i: float = -14.0,
    target_lra: float = 11.0,
    target_tp: float = -1.5,
) -> bool:
    """Re-normalize a finished video with two-pass EBU R128 loudnorm.

    The first pass measures actual integrated loudness, true peak, and
    loudness range; the second pass feeds those measurements back into
    loudnorm so it normalizes precisely instead of approximating in a
    single pass. The result is ±0.1 LU of target instead of ±1.5 LU.

    The video stream is copied (no re-encode), only audio is re-encoded.

    Defaults: -14 LUFS / 11 LU / -1.5 dBTP — YouTube/Netflix standard.

    Returns True if output_video_path was written, False on any failure
    (caller should keep the original input on False).
    """
    if not os.path.exists(input_video_path):
        return False

    # ---- Pass 1: measure (delegated to measure_loudness) ----
    measured = measure_loudness(input_video_path, target_i=target_i,
                                target_lra=target_lra, target_tp=target_tp)
    if measured is None:
        print("   [LOUDNORM-2PASS] Measurement failed — skipping 2nd pass")
        return False

    # ---- Pass 2: normalize with measured values ----
    af = (
        f"loudnorm=I={target_i}:LRA={target_lra}:TP={target_tp}:"
        f"measured_I={measured['input_i']}:"
        f"measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:"
        f"linear=true:print_format=summary"
    )
    norm_cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-y",
        "-i", input_video_path,
        "-af", af,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        output_video_path,
    ]
    try:
        norm = subprocess.run(norm_cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print("   [LOUDNORM-2PASS] Normalization pass timed out")
        return False

    if norm.returncode != 0 or not os.path.exists(output_video_path):
        # Surface the tail of ffmpeg's error so failures are diagnosable
        tail = (norm.stderr or "").strip().splitlines()[-3:]
        print(f"   [LOUDNORM-2PASS] Normalization failed: {' | '.join(tail)}")
        return False

    print(
        f"   [LOUDNORM-2PASS] Precise normalization: "
        f"measured I={measured['input_i']} -> target I={target_i}"
    )
    return True


def _accept_or_reject(path: str, aspect_ratio) -> bool:
    """Post-generation aspect backstop. Return True to ACCEPT the clip, False to reject (→ cascade).

    No-op (always True) when the project is landscape — preserves byte-identical 16:9 behavior.
    For portrait, probe the clip's real dimensions and accept only if its orientation matches.
    On probe failure (file missing / ffprobe error / no dims) ACCEPT with a warning — do NOT
    strand the pipeline on a flaky probe (the filter is the primary defense; this is the net).

    Caller contract: `path` MUST be the file the provider actually wrote. Cascade callers pass
    `output_mp4` (the uniform local artifact): the 7 download branches write it directly, and the
    4 native branches (KLING_NATIVE/SORA_NATIVE/VEO_NATIVE/LTX) pass output_path=output_mp4 and
    return that same path — so probing `output_mp4` is correct today. If a future native provider
    ignores its output_path and writes elsewhere, probe THAT returned path here instead."""
    from cinema.aspect import is_portrait as _is_portrait
    if not _is_portrait(aspect_ratio):
        return True  # landscape project: never reject (no-op)
    probed = probe_final_media(path)
    fmt = (probed or {}).get("format") or {}
    w, h = fmt.get("width"), fmt.get("height")
    if not w or not h:
        print(f"   [ASPECT-BACKSTOP] could not probe dims for {path} — accepting (probe unavailable)")
        return True
    return (h > w) == _is_portrait(aspect_ratio)  # portrait file iff portrait project


def probe_final_media(path: str) -> "dict | None":
    """Probe a finished mp4 for format/codec conformance and integrated loudness.

    Runs ffprobe (streams + format JSON) and measure_loudness in sequence.
    Returns a dict with whichever halves succeeded:

        {
          "audio": {"integrated_lufs": float, "true_peak_dbtp": float, "lra": float},
          "format": {"width": int|None, "height": int|None, "vcodec": str|None,
                     "acodec": str|None, "duration_s": float},
        }

    Partial results: if exactly one half succeeds, the dict contains only that
    half. Returns None only when the file is missing or BOTH halves fail.

    Called at assembly-time by cinema_pipeline._apply_final_loudnorm (U3).
    Pure I/O — no mutation, no Flask.
    """
    if not os.path.exists(path):
        return None

    result: dict = {}

    # ---- Format/codec half (ffprobe) ----
    try:
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_streams", "-show_format",
            "-of", "json", path,
        ]
        probe = subprocess.run(probe_cmd, capture_output=True, text=True,
                               timeout=60, check=True)
        probe_data = json.loads(probe.stdout)
        streams = probe_data.get("streams", [])
        fmt = probe_data.get("format", {})

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        result["format"] = {
            "width": video_stream.get("width") if video_stream else None,
            "height": video_stream.get("height") if video_stream else None,
            "vcodec": video_stream.get("codec_name") if video_stream else None,
            "acodec": audio_stream.get("codec_name") if audio_stream else None,
            "duration_s": float(fmt["duration"]) if fmt.get("duration") else None,
        }
    except Exception as e:
        print(f"   [PROBE-FINAL-MEDIA] ffprobe failed: {e}")
        # format half absent — will be omitted from result

    # ---- Loudness half (measure_loudness) ----
    # Defensive: measure_loudness should return None on failure, but guard the
    # call so an unexpected raise (e.g. ffmpeg binary absent) discards only the
    # audio half and preserves the ffprobe half — honoring the partial-results
    # contract (close Lane V F2).
    try:
        measured = measure_loudness(path)
    except Exception as e:
        print(f"   [PROBE-FINAL-MEDIA] loudness measure raised: {e}")
        measured = None
    if measured is not None:
        try:
            result["audio"] = {
                "integrated_lufs": float(measured["input_i"]),
                "true_peak_dbtp": float(measured["input_tp"]),
                "lra": float(measured["input_lra"]),
            }
        except (KeyError, ValueError, TypeError) as e:
            print(f"   [PROBE-FINAL-MEDIA] Loudness result parse failed: {e}")

    if not result:
        return None
    return result


# ---------------------------------------------------------------------------
# Scene-transition helpers (xfade / acrossfade)
# ---------------------------------------------------------------------------

def _probe_duration(path: str) -> float:
    """Return the duration of a media file in seconds via ffprobe."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return float(json.loads(probe.stdout)["format"]["duration"])


def _has_audio_stream(path: str) -> bool:
    """Return True if the media file has at least one audio stream (via ffprobe).

    The default silent-video motion path (Kling-Native image2video, LTX, base
    Veo without audio-drive) produces clips with no audio stream; xfade_concat
    uses this to decide whether an acrossfade chain is valid (Lane V #24 F1).
    """
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "json", path],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return bool(json.loads(probe.stdout).get("streams"))


def _fmt(x: float) -> str:
    """Format a float for an ffmpeg filter arg: strip trailing zeros (8.0 -> '8', 3.5 -> '3.5')."""
    return f"{x:.6f}".rstrip("0").rstrip(".")


def _build_xfade_filtergraph(durations: list, duration: float, transition: str,
                             audio_flags: Optional[list] = None):
    """Build a chained xfade (video) + acrossfade (audio) filter_complex string.

    Returns (filter_complex, final_video_label, final_audio_label).
    Requires len(durations) >= 2. Offset for junction j is
    sum(durations[0..j]) - (j+1)*duration. ``audio_flags`` is a per-input list
    of bools (True = that input has an audio stream); None ≡ all inputs have
    audio:
      - all True  -> raw acrossfade on [j:a]
      - all False -> video-only, audio label None (Lane V #24 F1)
      - mixed     -> normalize every leg + anullsrc-pad the silent legs, then
                     acrossfade, preserving embedded audio (Lane V #25 M1)
    """
    n = len(durations)
    if n < 2:
        raise ValueError("xfade filtergraph requires >= 2 inputs")
    if audio_flags is None:
        audio_flags = [True] * n
    emit_audio = any(audio_flags)
    padded = emit_audio and not all(audio_flags)

    t = _fmt(duration)
    video_parts = []
    prev_v = "0:v"
    cumulative = durations[0]
    for j in range(n - 1):
        offset = cumulative - (j + 1) * duration
        vlabel = f"v{j + 1}"
        video_parts.append(
            f"[{prev_v}][{j + 1}:v]xfade=transition={transition}:"
            f"duration={t}:offset={_fmt(offset)}[{vlabel}]"
        )
        prev_v = vlabel
        cumulative += durations[j + 1]

    if not emit_audio:
        return ";".join(video_parts), f"v{n - 1}", None

    # Audio legs. padded (mixed presence) -> normalize every leg to a canonical
    # format so acrossfade's matching rate/layout/fmt precondition holds across
    # heterogeneous embedded audio + anullsrc silence (Lane V #25 M1). All-audio
    # -> raw [j:a] (unchanged).
    _AFMT = "aformat=sample_fmts=fltp:channel_layouts=stereo"
    leg_parts = []
    if padded:
        audio_src = []
        for j in range(n):
            if audio_flags[j]:
                leg_parts.append(f"[{j}:a]aresample=48000,{_AFMT}[na{j}]")
            else:
                leg_parts.append(
                    f"anullsrc=r=48000:cl=stereo,atrim=0:{_fmt(durations[j])},{_AFMT}[na{j}]"
                )
            audio_src.append(f"na{j}")
    else:
        audio_src = [f"{j}:a" for j in range(n)]

    audio_parts = []
    prev_a = audio_src[0]
    for j in range(n - 1):
        alabel = f"a{j + 1}"
        audio_parts.append(f"[{prev_a}][{audio_src[j + 1]}]acrossfade=d={t}[{alabel}]")
        prev_a = alabel

    filter_complex = ";".join(video_parts + leg_parts + audio_parts)
    return filter_complex, f"v{n - 1}", f"a{n - 1}"


def xfade_concat(scene_videos: list, out_path: str,
                 duration: float = 0.5, transition: str = "dissolve") -> str:
    """Chain per-scene videos with xfade (video) + conditional acrossfade (audio).

    Probes each scene's duration, clamps the transition to fit the shortest
    scene, builds the filtergraph, and re-encodes once to out_path.
    Requires len(scene_videos) >= 2 (caller guarantees). Returns out_path.
    Raises on ffmpeg failure (caller falls back to a plain concat).

    Audio has three cases: all inputs carry audio -> streams are crossfaded
    directly; no input carries audio -> output is video-only (the default
    silent-video motion path, Kling-Native/LTX, has no audio stream, where
    emitting an acrossfade once referenced a non-existent [0:a] and errored ->
    the caller silently hard-cut, Lane V #24 F1); mixed audio-presence -> silent
    legs are anullsrc-padded and every leg normalized so embedded audio is
    preserved across the stitch rather than dropped (Lane V #25 M1). Downstream
    _assemble_final owns the dialogue/BGM/foley mix on every path.
    """
    durations = [_probe_duration(v) for v in scene_videos]
    audio_flags = [_has_audio_stream(v) for v in scene_videos]
    # Mixed audio-presence (some inputs carry an embedded audio stream, some don't):
    # silent inputs are padded with anullsrc and every leg is normalized to a canonical
    # format, so acrossfade runs uniformly and embedded audio is preserved across the
    # stitch rather than dropped (Lane V #25 M1, fixed 2026-05-29). The downstream
    # _assemble_final dialogue mux is unaffected — it selects its voice source on
    # standalone-dialogue-mp3 existence, not on whether this stitch carries audio.
    t_eff = min(duration, 0.4 * min(durations))
    filter_complex, vlab, alab = _build_xfade_filtergraph(
        durations, t_eff, transition, audio_flags=audio_flags)

    cmd = ["ffmpeg", "-y"]
    for v in scene_videos:
        cmd += ["-i", v]
    cmd += ["-filter_complex", filter_complex, "-map", f"[{vlab}]"]
    if alab is not None:
        cmd += ["-map", f"[{alab}]"]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20"]
    if alab is not None:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += [out_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as exc:
        import logging
        logging.getLogger(__name__).warning(
            "xfade_concat ffmpeg failed: %s",
            exc.stderr.decode(errors="replace") if exc.stderr else exc,
        )
        raise
    return out_path
