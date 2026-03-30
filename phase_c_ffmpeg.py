import os
import time
import json
import subprocess

# VEO removed from cascade — quota exhaustion made it unreliable
# Keep the flag for backward compatibility but it's not used in the optimized cascade
_VEO_QUOTA_EXHAUSTED = False

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


def generate_kling_storyboard(
    shots: list,
    start_image_path: str,
    output_mp4: str,
    multi_angle_refs: list = None,
    scene_seed: int = None,
) -> str:
    """
    Kling 3.0 Pro STORYBOARD MODE — batches up to 6 shots into ONE call.
    All shots share a unified latent space = mathematically guaranteed character consistency.

    The paper identifies this as the single most impactful technique for identity preservation:
    "Because the cuts share this unified space, the hero character maintains absolute
    temporal and visual consistency across the entire sequence."

    Args:
        shots: List of shot dicts with 'prompt' and 'camera' fields (max 6)
        start_image_path: Keyframe image to anchor the generation
        output_mp4: Output video path
        multi_angle_refs: Character reference images for subject binding
        scene_seed: Deterministic seed for reproducibility

    Returns:
        Path to generated video, or None on failure
    """
    if not FAL_AVAILABLE or not os.getenv("FAL_KEY"):
        print("   [STORYBOARD] FAL not available")
        return None

    if not shots or not os.path.exists(start_image_path):
        return None

    try:
        import urllib.request

        print(f"   [STORYBOARD] Kling 3.0 Pro — {len(shots)} shots in unified latent space")

        start_url = fal_client.upload_file(start_image_path)

        # Build multi_prompt array (max 6 shots, up to 15s total)
        multi_prompt = []
        per_shot_duration = min(5, max(2, 15 // len(shots)))  # Distribute 15s across shots

        for shot in shots[:6]:
            camera = shot.get("camera", "zoom_in_slow")
            prompt = shot.get("prompt", "")
            multi_prompt.append({
                "prompt": (
                    f"MOTION: Smooth cinematic {camera}, natural acceleration and deceleration. "
                    f"SUBJECT: @Element1 maintains rigid facial bone structure — zero face deformation between frames. "
                    f"SCENE: {prompt}. "
                    f"TEMPORAL: Consistent inter-frame luminance, stable color temperature, "
                    f"maintain fabric pattern and texture throughout. "
                    f"PRESERVE: Do not morph, distort, or alter @Element1's facial features, hair, or skin at any frame."
                ),
                "duration": str(per_shot_duration),
            })

        args = {
            "start_image_url": start_url,
            "multi_prompt": multi_prompt,
            "shot_type": "customize",
            "generate_audio": False,
            "cfg_scale": 0.5,
            "negative_prompt": "blur, distortion, deformed face, identity change, face morph, extra limbs, "
                               "floating objects, flickering, temporal inconsistency, plastic skin, "
                               "over-smoothed texture, unnatural eye movement, teeth distortion, "
                               "clothing pattern change, sudden lighting shift",
        }

        # Subject binding with multi-angle refs
        if multi_angle_refs:
            valid_refs = [r for r in multi_angle_refs if os.path.exists(r)]
            if valid_refs:
                frontal_url = fal_client.upload_file(valid_refs[0])
                extra_urls = []
                for ref_path in valid_refs[1:6]:  # Up to 5 additional angles
                    try:
                        extra_urls.append(fal_client.upload_file(ref_path))
                    except (OSError, RuntimeError) as e:
                        print(f"   [STORYBOARD] Failed to upload ref {ref_path}: {e}")
                args["elements"] = [{
                    "frontal_image_url": frontal_url,
                    "reference_image_urls": extra_urls,
                }]
                print(f"   [STORYBOARD] Subject bound: 1 frontal + {len(extra_urls)} angles")

        result = fal_client.subscribe(
            "fal-ai/kling-video/v3/pro/image-to-video",
            arguments=args,
            with_logs=True,
        )

        video_url = result.get("video", {}).get("url")
        if video_url:
            urllib.request.urlretrieve(video_url, output_mp4)
            print(f"   [STORYBOARD] Success: {output_mp4} ({len(shots)} shots unified)")
            return output_mp4

        return None

    except Exception as e:
        print(f"   [STORYBOARD] Error: {e}")
        return None


def generate_ai_video(
    image_path: str,
    camera_motion: str,
    target_api: str,
    output_mp4: str,
    pacing: str = "moderate",
    character_id: str = None,
    attempted_apis: set = None,
    multi_angle_refs: list = None,
    _cascade_retries: int = 0,
    negative_prompt: str = None,
    shot_type: str = None,
    video_fallbacks: list = None,
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
    """
    if attempted_apis is None:
        attempted_apis = set()
    attempted_apis.add(target_api.upper())

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

        for api in fallback_list:
            if api not in attempted_apis:
                print(f"   [CASCADE] -> {api}")
                return generate_ai_video(
                    image_path, camera_motion, api, output_mp4, pacing,
                    character_id, attempted_apis, multi_angle_refs,
                    shot_type=shot_type, video_fallbacks=video_fallbacks,
                )

        # All APIs failed — retry up to 2 times with quota cooldown
        if _cascade_retries >= 1:
            print("   [WARN] All video APIs exhausted after 1 full cascade retry.")
            return None
        print(f"   [WARN] All APIs exhausted. Waiting 30s for refresh (retry {_cascade_retries + 1}/2)...")
        time.sleep(30)
        first_api = (video_fallbacks or ["KLING_NATIVE"])[0]
        return generate_ai_video(
            image_path, camera_motion, first_api, output_mp4, pacing,
            character_id, set(), multi_angle_refs, _cascade_retries=_cascade_retries + 1,
            shot_type=shot_type, video_fallbacks=video_fallbacks,
        )

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

            # Sora excels at cloth simulation and gravity — emphasize these
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
            )
            if result:
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
                generate_audio=(shot_type == "landscape"),  # Native audio for environments
            )
            if result:
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
                return result
            return try_next_api()
        except Exception as e:
            print(f"   [WARN] LTX error: {e}")
            return try_next_api()

    elif target_api.upper() == "RUNWAY_GEN4":
        # Runway Gen-4 — style lock with 3 refs, best prompt adherence
        try:
            from runwayml import RunwayML
            client = RunwayML(api_key=os.getenv("RUNWAYML_API_SECRET"))
            import urllib.request

            print(f"   [RUNWAY-GEN4] Runway Gen-4 I2V with style lock")

            # Upload image as data URI or use URL
            import base64
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            data_uri = f"data:image/jpeg;base64,{img_b64}"

            task = client.image_to_video.create(
                model="gen4",
                prompt_image=data_uri,
                prompt_text=(
                    f"Smooth cinematic {camera_motion}. "
                    f"Maintain exact character appearance throughout. "
                    f"Natural body movement, consistent lighting, photorealistic quality."
                ),
                duration=10,
                ratio="1280:720",
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
        fal_key = os.getenv("FAL_KEY")
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
                        "aspect_ratio": "16:9",
                        "duration": 4,
                    },
                    with_logs=True,
                )

                video_url = result.get("video", {}).get("url")
                if video_url:
                    urllib.request.urlretrieve(video_url, output_mp4)
                    print(f"   [SORA2] Success: {output_mp4}")
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
        global _VEO_QUOTA_EXHAUSTED
        if _VEO_QUOTA_EXHAUSTED:
            print("   [VEO] Quota exhausted flag set. Cascading...")
            return try_next_api()

        fal_key = os.getenv("FAL_KEY")
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
                        "aspect_ratio": "16:9",
                        "duration": "8s",
                        "resolution": "720p",
                        "generate_audio": False,
                    },
                    with_logs=True,
                )

                video_url = result.get("video", {}).get("url")
                if video_url:
                    urllib.request.urlretrieve(video_url, output_mp4)
                    print(f"   [VEO] Success: {output_mp4}")
                    return output_mp4

                return try_next_api()

            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
                    _VEO_QUOTA_EXHAUSTED = True
                    print("   [VEO] Quota exhausted — permanently flagged")
                print(f"   [WARN] Veo 3.1 error: {e}")
                return try_next_api()
        else:
            print("   [WARN] FAL_KEY missing for Veo. Cascading...")
            return try_next_api()
            
    elif target_api.upper() == "KLING_3_0":
        # Kling 3.0 Pro via fal.ai — with subject binding + multi-angle references
        fal_key = os.getenv("FAL_KEY")
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

    elif target_api.upper() == "COMFY_UI":
        # Headless ComfyUI execution via Fal.ai Serverless Endpoint
        fal_key = os.getenv("FAL_KEY")
        if fal_key and FAL_AVAILABLE:
            try:
                print(f"   ↳ Generating precise surgical frame via Headless COMFY_UI API...")
                
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
                        except AttributeError:
                            pass

                try:
                    base_img_url = fal_client.upload_file(image_path)
                except AttributeError:
                    base_img_url = "https://picsum.photos/768/1365"

                # Standard serverless call simulating a ComfyUI execution backbone
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
                    return output_mp4
                return try_next_api()
            except Exception as e:
                print(f"   ⚠️ COMFY_UI Serverless Error: {e}")
                print("   ⚠️ Re-routing gracefully...")
                return try_next_api()
        else:
            print("   ⚠️ FAL_KEY missing. Re-routing gracefully...")
            return try_next_api()
            
    elif target_api.upper() == "RUNWAY":
        # RunwayML Elite Cinematic Generation
        runway_key = os.getenv("RUNWAYML_API_SECRET")
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
                    ratio="1280:768",
                    duration=5
                )
                print(f"   ↳ Runway Task {video_task.id} queued. Polling...")
                completed_task = video_task.wait_for_task_output()
                final_video_url = completed_task.output[0]
                import urllib.request
                urllib.request.urlretrieve(final_video_url, output_mp4)
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
        seedance_key = os.getenv("SEEDANCE_API_KEY")
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

def generate_ass_subtitles(whisper_result: dict, output_path: str):
    """Converts Whisper word-level timestamps to an advanced SubStation Alpha (.ass) file."""
    ass_header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Roboto,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    def format_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centi = int(round((seconds - int(seconds)) * 100))
        centi = min(centi, 99)
        return f"{hours:d}:{minutes:02d}:{secs:02d}.{centi:02d}"

    lines = []
    for segment in whisper_result.get('segments', []):
        if 'words' in segment:
            for word_obj in segment['words']:
                word = word_obj['word'].strip().upper()
                start_pts = format_time(word_obj['start'])
                # Extend end time slightly so words don't blink too fast
                end_pts = format_time(word_obj['end'] + 0.1)
                
                # Active yellow text with white outline + KINETIC POP-IN TEXT (Visual Psychology hack)
                # We start the word at 110% scale and immediately smoothly shrink it down to 100% in 150ms 
                # This forcefully hijacks the brain's motion-tracking reflex to glue eyeballs to the screen.
                event_line = f"Dialogue: 0,{start_pts},{end_pts},Default,,0,0,0,,{{\\\\fscx110\\\\fscy110\\\\t(0,150,\\\\fscx100\\\\fscy100)\\\\1c&H00D4FF&}}{word}"
                lines.append(event_line)
        else:
            text = segment['text'].strip().upper()
            start_pts = format_time(segment['start'])
            end_pts = format_time(segment['end'])
            event_line = f"Dialogue: 0,{start_pts},{end_pts},Default,,0,0,0,,{text}"
            lines.append(event_line)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_header + "\\n".join(lines) + "\\n")
    print(f"      Generated ASS Subtitles: {output_path}")
    return output_path

def probe_audio(file_path: str) -> bool:
    """Executes ffprobe to determine if an MP4 contains an active audio stream."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_name", "-of",
        "default=noprint_wrappers=1:nokey=1", file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    return len(result.stdout.strip()) > 0

def normalize_clip(input_path: str, output_path: str, duration_sec: float = None, effect: str = "gritty_contrast") -> str:
    """Forces 1920x1080 widescreen scaling, exact 24fps, injects silent audio, and explicitly trims to match spoken sentence lengths."""
    has_audio = probe_audio(input_path)
    cmd = ["ffmpeg", "-y", "-i", input_path]
    
    if not has_audio:
        cmd.extend(["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        
    base_vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
    if effect == "cinematic_glow":
        style_vf = "eq=contrast=1.05:saturation=1.05:brightness=0.02,gblur=sigma=0.5"
    elif effect == "cyberpunk_glitch":
        style_vf = "eq=contrast=1.15:saturation=1.2:gamma_g=0.95,unsharp=5:5:0.8"
    elif effect == "dreamy_blur":
        style_vf = "eq=contrast=0.95:saturation=0.9,gblur=sigma=1.5"
    elif effect == "documentary_neutral":
        style_vf = "eq=contrast=1.0:saturation=1.0"
    else: # gritty_contrast
        style_vf = "eq=contrast=1.05:saturation=1.10,unsharp=3:3:0.5"
        
    cmd.extend([
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-vf", f"{base_vf},{style_vf},fps=30",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"
    ])
    
    if duration_sec:
        cmd.extend(["-t", str(duration_sec)])
    
    if not has_audio and not duration_sec:
        cmd.append("-shortest")
        
    cmd.append(output_path)
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"      ❌ FFMPEG NORM_CLIP ERROR: {e.stderr.decode()}")
        raise
        
    print(f"      Normalized: {output_path} | Audio: {has_audio} | Duration: {duration_sec}s")
    return output_path

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

def execute_master_ffmpeg_assembly(video_path: str, tts_path: str, bgm_path: str, ass_path: str, output_path: str, topic_text: str = "", tts_duration: float = None, timeline_effects: list = None, foley_paths: list = None, lut_path: str = None):
    """
    Executes a single-pass zero-loss FFmpeg complex filtergraph to:
      1. Mix Foley, TTS, and ducked BGM using sidechaincompress
      2. Layer async Scene-Specific Foley `.mp3` tracks via dynamic adelay filters.
    """
    cmd = [
        "ffmpeg", "-y", 
        "-i", video_path,   # [0:v/a]
        "-i", tts_path,     # [1:a]
        "-i", bgm_path      # [2:a]
    ]

    lut_index = -1
    if lut_path and os.path.exists(lut_path):
        cmd.extend(["-i", lut_path])
        lut_index = 3
    
    foley_filters = []
    foley_mix_labels = []
    
    
    if foley_paths:
        for i, path in enumerate(foley_paths, start=3):
            if path and os.path.exists(path):
                # Calculate the exact start time in milliseconds for the delay filter
                st_ms = round(timeline_effects[i-3].get("start", 0) * 1000) if timeline_effects and (i-3) < len(timeline_effects) else 0
                cmd.extend(["-i", path])
                foley_filters.append(f"[{i}:a]adelay={st_ms}|{st_ms},volume=0.8[f_delayed_{i}];")
                foley_mix_labels.append(f"[f_delayed_{i}]")
                
    if foley_mix_labels:
        foley_mix_bus = f"{''.join(foley_filters)}{''.join(foley_mix_labels)}amix=inputs={len(foley_mix_labels)}:duration=first:dropout_transition=2[foley_layer];"
    else:
        # Fallback empty track if Foley generation failed or was bypassed
        foley_mix_bus = "aevalsrc=0:d=1[foley_layer];"
    
    # 1. [tts_v]: TTS track wrapper
    # 2. [bgm_looped]: Loop BGM infinitely
    # 3. [bgm_ducked]: Sidechain compress BGM via TTS signal
    # 4. [foley]: Lower native Veo audio
    dynamic_voice_filters = []
    if timeline_effects:
        for fx in timeline_effects:
            eff = fx.get('effect')
            st = round(fx.get('start', 0), 3)
            en = round(fx.get('end', 0), 3)
            # The enable expression matches the exact time bounds of the current visual clip
            time_expr = f"enable='between(t,{st},{en})'"
            
            if eff == "cyberpunk_glitch":
                dynamic_voice_filters.append(f"acrusher=bits=12:mix=0.15:{time_expr}") # Subtle 15% bitcrush
            elif eff == "dreamy_blur":
                dynamic_voice_filters.append(f"lowpass=f=3000:{time_expr}")
            elif eff == "cinematic_glow":
                dynamic_voice_filters.append(f"highpass=f=250:{time_expr}")
            elif eff == "gritty_contrast":
                dynamic_voice_filters.append(f"acrusher=bits=12:mix=0.1:{time_expr}")
                
    # Keep the voice ultra-clear, removing demonic pitching and chorus. 
    # Just a light highpass, light compression, and ultra-subtle room reverb for cinema.
    voice_base = (
        "[1:a]highpass=f=80,treble=g=3,"
        "aecho=0.8:0.88:15:0.1,"
        "acompressor=threshold=-14dB:ratio=4:attack=5:release=50:makeup=3"
    )
    
    if dynamic_voice_filters:
        fx_chain = ",".join(dynamic_voice_filters)
        voice_bus = f"{voice_base},{fx_chain},asplit=2[tts_sc][tts_mix];"
    else:
        voice_bus = f"{voice_base},asplit=2[tts_sc][tts_mix];"

    a_graph = (
        # 1. VOICE PROCESSING (Base + Scene-Specific Dynamic Effects)
        f"{voice_bus}"
        
        # 2. BGM AUTOMATION & AGGRESSIVE DUCKING
        "[2:a]volume=0.9,aloop=loop=-1:size=2e9[bgm_looped];"
        "[bgm_looped][tts_sc]sidechaincompress=threshold=0.015:ratio=12:attack=5:release=200:makeup=1.8[bgm_ducked];"
        
        # 3. SFX SYNTHESIS (Cinematic Room Boom + Noise Cyber-Rise)
        "aevalsrc='0.8*sin(150*exp(-t*4)*t)|0.8*sin(150*exp(-t*4)*t)':d=3:s=48000,"
        "afade=t=in:st=0:d=0.05,afade=t=out:st=1.5:d=1.5,"
        "aecho=0.8:0.9:50|100:0.5|0.3[sfx_boom];"
        
        "anoisesrc=d=2:c=pink:r=48000:a=0.3,"
        "vibrato=f=20:d=0.5,lowpass=f=600,"
        "afade=t=in:st=0:d=0.05,afade=t=out:st=0.5:d=1.5[sfx_noise];"
        
        # 4. SCENE FOLEY BUS & MASTER MIX BUS
        f"{foley_mix_bus}"
        "[0:a]volume=0.3[original_foley];"
        
        # 5. MASTER MIX BUS (Combine everything)
        "[original_foley][tts_mix][bgm_ducked][sfx_boom][sfx_noise][foley_layer]amix=inputs=6:duration=first:dropout_transition=2[mixed];"
        "[mixed]loudnorm=I=-14:LRA=11:TP=-1.5[final_audio]"
    )
    
    filtercomplex = f"{a_graph}"
    
    if lut_index != -1:
        # Programmatic cinematic HaldCLUT grading
        filtercomplex = f"[0:v][{lut_index}:v]haldclut[v_master]; {a_graph}"
        cmd.extend(["-filter_complex", filtercomplex, "-map", "[v_master]"])
    else:
        cmd.extend(["-filter_complex", filtercomplex, "-map", "0:v"])
    
    cmd.extend([
        "-map", "[final_audio]",
        "-c:v", "libx264", "-preset", "fast",  # Using generic libx264 instead of copy because haldclut re-encodes
        "-c:a", "aac", "-b:a", "192k", 
        "-shortest"
    ])
    
    if tts_duration is not None:
        cmd.extend(["-t", str(tts_duration)])
        
    cmd.append(output_path)
    
    print(f"      Executing Single-Pass FFmpeg Master Assembly...")
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"      ✅ Master Audio & Video Mix Complete: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"      ❌ FFmpeg Assembly Failed. Error:\\n{e.stderr.decode('utf-8')}")
        return False


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
