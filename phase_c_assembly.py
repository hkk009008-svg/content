import os
import json
import uuid
import time

import requests

from typing import NamedTuple

from config.settings import settings
from cinema.aspect import portrait_swap, fal_image_size, fal_aspect_ratio, DEFAULT_ASPECT_RATIO
from cinema.fal_limits import FAL_TIMEOUT_IMAGE_S
from cinema.context import get_project_setting

PEXELS_API_KEY = settings.pexels_api_key


class ImageGenResult(NamedTuple):
    """Provenance-carrying result of an image-generation backend.

    ``path`` is the saved image (equals ``output_filename`` on success);
    ``api_name`` is the cost_tracker API key for the backend that ACTUALLY ran
    (``COMFYUI_PULID`` | ``FLUX_KONTEXT`` | ``FLUX_PRO`` | ``FLUX_SCHNELL`` |
    ``POLLINATIONS`` | ``QUALITY_MAX``). Callers record ``api_name`` so cost_log
    reflects where the image was really generated (pod vs FAL), not a tier-based
    guess. Backends return ``None`` (not this type) on failure, so the caller's
    ``if not result`` success guard is preserved (a 2-field NamedTuple is always
    truthy).
    """

    path: str
    api_name: str


class RunPodComfyUI:
    def __init__(self, server_url):
        self.server_url = server_url.rstrip('/')
        self.client_id = str(uuid.uuid4())

    def upload_image(self, image_path):
        print(f"      ↳ Uploading {os.path.basename(image_path)} to RunPod ephemeral disk...")
        url = f"{self.server_url}/upload/image"
        with open(image_path, 'rb') as f:
            files = {'image': f}
            response = requests.post(url, files=files)
            if response.status_code == 200:
                return response.json()['name']
            else:
                raise Exception(f"Failed to upload image: {response.text}")

    def queue_prompt(self, prompt_workflow):
        p = {"prompt": prompt_workflow, "client_id": self.client_id}
        url = f"{self.server_url}/prompt"
        response = requests.post(url, json=p)
        if response.status_code == 200:
            return response.json()['prompt_id']
        else:
            raise Exception(f"Failed to queue prompt: {response.text}")

    def get_image(self, filename, subfolder, folder_type):
        url = f"{self.server_url}/view"
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.content
        return None

    def get_history(self, prompt_id):
        url = f"{self.server_url}/history/{prompt_id}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        return {}

def generate_ai_broll(prompt, output_filename, seed=None, character_image=None,
                       init_image=None, denoise_strength=1.0, characters=None,
                       multi_angle_refs=None, identity_anchor="",
                       pulid_weight_override=None, negative_prompt="",
                       quality_tier="production", char_lora_path=None,
                       char_lora_strength=None,
                       style_reference=None, shot_hint=None, ctx=None):
    """
    Generates a cinematic image with face-identity preservation.

    v3 priority chain (production tier, default):
    1. fal.ai FLUX Kontext (identity-preserving, no local GPU needed)
    2. ComfyUI + PuLID on RunPod (if models are available)
    3. fal.ai FLUX-Pro (no face-lock, last resort)

    Quality tiers:
        "production" (default) — pulid.json + parameter overrides, single-shot.
                                 Preserves all existing caller behavior.
        "max"                  — pulid_max.json + N=8 adaptive best-of with
                                 ArcFace gate. Falls back to "production" if
                                 quality_max module / pulid_max.json missing
                                 or returns None.

    Args:
        prompt: Image generation prompt (enhanced by continuity engine)
        output_filename: Output path for generated image
        seed: Deterministic seed for consistency
        character_image: Primary character reference for face identity
        init_image: Previous shot image for img2img temporal chaining
        denoise_strength: 0.0-1.0, lower = more similar to init_image
        characters: List of character config dicts
        quality_tier: "production" | "max" — selects the generation pipeline.
        char_lora_path: (max tier only) Path to per-character LoRA .safetensors.
        style_reference: (max tier only) Path to style-board reference image.
        shot_hint: (max tier only) Pre-classified shot dict; bypasses re-classification.

    Returns:
        ImageGenResult(path, api_name) naming the backend that actually ran
        (COMFYUI_PULID | FLUX_KONTEXT | FLUX_PRO | FLUX_SCHNELL | POLLINATIONS |
        QUALITY_MAX), or None if every backend failed. Callers record
        ``api_name`` for cost attribution so a pod generation is distinguishable
        from a FAL fallback in cost_log.
    """
    # --- MAX-TIER DISPATCH ---
    # Try the maxed-quality path first; fall through to production on any failure
    # so existing callers (production runs, tests) never break.
    if quality_tier == "max":
        try:
            from quality_max import generate_ai_broll_max
            result = generate_ai_broll_max(
                prompt=prompt,
                output_filename=output_filename,
                seed=seed,
                character_image=character_image,
                init_image=init_image,
                denoise_strength=denoise_strength,
                characters=characters,
                multi_angle_refs=multi_angle_refs,
                identity_anchor=identity_anchor,
                pulid_weight_override=pulid_weight_override,
                negative_prompt=negative_prompt,
                char_lora_path=char_lora_path,
                char_lora_strength=char_lora_strength,
                style_reference=style_reference,
                shot_hint=shot_hint,
                ctx=ctx,
            )
            if result:
                return result
            print("[generate_ai_broll] Max tier returned None — falling back to production tier.")
        except ImportError as e:
            print(f"[generate_ai_broll] quality_max unavailable ({e}) — production tier.")
        except Exception as e:
            print(f"[generate_ai_broll] Max tier raised ({e}) — production tier.")

    mode = "img2img" if init_image else "txt2img"

    # Read per-project aspect ratio early — must be in scope at ALL six
    # _fal_flux_fallback call sites (including early-return and except paths).
    # Phase 2: portrait-aware latent dimensions + FAL/Pollinations orientation.
    # get_project_setting is a safe dict lookup with a default (never raises,
    # handles ctx=None), so it is safe to call here outside the try block.
    aspect_ratio = get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)

    # ----- Backend selection (PRIORITY order) -----
    # The previous implementation relied on a confusing if/elif/else where
    # only branch #1 fell through to the ComfyUI path below, and the
    # downstream `if not server_url` check was dead code (the else-branch
    # had already returned). Rewriting with explicit early-returns so the
    # control flow is self-evident.
    server_url = settings.comfyui_server_url

    # PRIORITY 2 / 3: ComfyUI is unavailable — route to FLUX fallback.
    # (Same args as the old elif/else, consolidated.)
    if not (server_url and os.path.exists("pulid.json")):
        if character_image and os.path.exists(character_image) and settings.fal_key:
            return _fal_flux_fallback(
                prompt, output_filename, seed,
                character_image=character_image,
                multi_angle_refs=multi_angle_refs,
                identity_anchor=identity_anchor,
                aspect_ratio=aspect_ratio,
            )
        return _fal_flux_fallback(
            prompt, output_filename, seed,
            character_image=character_image,
            aspect_ratio=aspect_ratio,
        )

    # PRIORITY 1: ComfyUI + PuLID on RunPod RTX 4090 (fastest + strongest face-lock)
    print(f"   [PHASE C] Generating [{mode}] via ComfyUI PuLID (RTX 4090): '{prompt[:60]}...'")

    try:
        if not os.path.exists("pulid.json"):
            print("   [WARN] pulid.json missing — using Kontext fallback")
            return _fal_flux_fallback(prompt, output_filename, seed, character_image=character_image,
                                      aspect_ratio=aspect_ratio)

        with open("pulid.json", "r") as f:
            workflow = json.load(f)

        # WORKFLOW SELECTOR — apply shot-type-specific parameters
        try:
            from workflow_selector import classify_shot_type, get_workflow_params, apply_workflow_params
            # Build a minimal shot dict for classification
            shot_info = {"prompt": prompt, "characters_in_frame": ["char"] if character_image else []}
            shot_type = classify_shot_type(shot_info)
            wf_params = get_workflow_params(shot_type, settings=ctx.global_settings if ctx else None)
            workflow = apply_workflow_params(workflow, wf_params)

            # Apply adaptive PuLID weight override from continuity engine feedback loop
            if pulid_weight_override is not None and "100" in workflow:
                workflow["100"]["inputs"]["weight"] = pulid_weight_override
                print(f"   [WORKFLOW] {shot_type}: PuLID={pulid_weight_override:.2f} (adaptive), CFG={wf_params['guidance']}, steps={wf_params['steps']}")
            else:
                print(f"   [WORKFLOW] {shot_type}: PuLID={wf_params['pulid_weight']}, CFG={wf_params['guidance']}, steps={wf_params['steps']}")

            # Skip ComfyUI entirely for landscape shots (no face-lock needed)
            if shot_type == "landscape" and character_image:
                print(f"   [WORKFLOW] Landscape detected — skipping PuLID, using Kontext")
                return _fal_flux_fallback(prompt, output_filename, seed, character_image=None,
                                          aspect_ratio=aspect_ratio)
        except ImportError:
            pass  # workflow_selector not available — use defaults

        comfy = RunPodComfyUI(server_url)

        # 1. Inject LLM Text prompt to CLIP node "122"
        workflow["122"]["inputs"]["text"] = prompt

        # 2. Aspect ratio — native latent dims via EmptyLatentImage node "102"
        #    portrait_swap transposes 1344×768 → 768×1344 when aspect_ratio=9:16;
        #    landscape / unknown → unchanged. Phase 2 (portrait keyframe support).
        _w, _h = portrait_swap(1344, 768, aspect_ratio)
        workflow["102"]["inputs"]["width"] = _w
        workflow["102"]["inputs"]["height"] = _h
        workflow["102"]["inputs"]["batch_size"] = 1

        # 3. Seed control via RandomNoise node "25"
        if seed is not None:
             workflow["25"]["inputs"]["noise_seed"] = seed

        # 4. Primary character face-lock via PuLID LoadImage node "93"
        if character_image and os.path.exists(character_image):
            remote_face_filename = comfy.upload_image(character_image)
            workflow["93"]["inputs"]["image"] = remote_face_filename
            print(f"      ↳ PuLID face-locked to: {os.path.basename(character_image)}")
        else:
            # No character image — strip ALL PuLID nodes so ComfyUI doesn't validate them
            # Rewire: FreeU takes model directly from UNETLoader (skip PuLID)
            print("   ↳ No character — bypassing PuLID, pure txt2img mode")
            for nid in ["93", "97", "99", "100", "101"]:
                workflow.pop(nid, None)
            # Rewire PAG to take model from UNETLoader directly (node 112), skipping PuLID
            if "301" in workflow:
                workflow["301"]["inputs"]["model"] = ["112", 0]

        # 5a. CONTROLNET DEPTH MODE: Spatial consistency via depth map from init image
        # When we have an init_image, extract depth and use ControlNet to guide spatial layout
        # This prevents character "floating" and ensures consistent spatial positioning
        if init_image and os.path.exists(init_image):
            try:
                # Inject DepthAnything V2 preprocessor (node 400)
                remote_depth_src = comfy.upload_image(init_image)
                workflow["400"] = {
                    # resolution = DepthAnythingV2 preprocessor working size (longest
                    # side), aspect-independent — NOT a latent pixel budget, so it is
                    # intentionally not routed through portrait_swap (node 102 carries dims).
                    "inputs": {"image": remote_depth_src, "resolution": 1344},
                    "class_type": "DepthAnythingV2Preprocessor",
                    "_meta": {"title": "Depth Map (DepthAnything V2)"}
                }
                # Inject ControlNet loader (node 401)
                workflow["401"] = {
                    "inputs": {"control_net_name": "control_v11f1p_sd15_depth.safetensors"},
                    "class_type": "ControlNetLoader",
                    "_meta": {"title": "Load ControlNet Depth"}
                }
                # Inject ControlNet apply — modifies conditioning (node 402)
                # Strength from workflow_selector per shot type (portrait=0.35, wide=0.50, etc.)
                cn_strength = wf_params.get("controlnet_depth_strength", 0.35) if 'wf_params' in dir() else 0.35
                workflow["402"] = {
                    "inputs": {
                        "positive": ["60", 0],
                        "negative": ["60", 0],
                        "control_net": ["401", 0],
                        "image": ["400", 0],
                        "strength": cn_strength,
                        "start_percent": 0.0,
                        "end_percent": 0.5,
                    },
                    "class_type": "ControlNetApplyAdvanced",
                    "_meta": {"title": "Apply ControlNet Depth (spatial lock)"}
                }
                # Rewire: BasicGuider now uses ControlNet-enhanced conditioning
                workflow["22"]["inputs"]["conditioning"] = ["402", 0]
                print(f"      ↳ ControlNet Depth injected (strength=0.35, end=50%) from {os.path.basename(init_image)}")
            except Exception as e_cn:
                print(f"      ↳ ControlNet Depth skipped (node not available): {e_cn}")

        # 5b. IMG2IMG MODE: Temporal consistency via init image
        # Injects a VAEEncode node to convert init image → latent, replacing EmptyLatentImage
        if init_image and os.path.exists(init_image):
            remote_init = comfy.upload_image(init_image)

            # Add a LoadImage node for the init image (node "200")
            workflow["200"] = {
                "inputs": {"image": remote_init},
                "class_type": "LoadImage",
                "_meta": {"title": "Load Init Image (img2img)"}
            }

            # Add a VAEEncode node (node "201") to convert init image → latent
            workflow["201"] = {
                "inputs": {
                    "pixels": ["200", 0],
                    "vae": ["10", 0]  # Same VAE as the decode path (node 10)
                },
                "class_type": "VAEEncode",
                "_meta": {"title": "VAE Encode Init (img2img)"}
            }

            # Rewire: SamplerCustomAdvanced (node 13) now takes latent from VAEEncode
            # instead of EmptyLatentImage (node 102)
            workflow["13"]["inputs"]["latent_image"] = ["201", 0]

            # Set denoise strength in BasicScheduler (node 17).
            # img2img_denoise from global_settings.continuity_options overrides the
            # caller-supplied denoise_strength when present (slider: min 0.2, max 0.6).
            _ui_denoise = None
            if ctx is not None:
                _co = (ctx.global_settings or {}).get("continuity_options", {})
                _raw = _co.get("img2img_denoise")
                if _raw is not None and isinstance(_raw, (int, float)):
                    _ui_denoise = max(0.2, min(0.6, float(_raw)))
            effective_denoise = _ui_denoise if _ui_denoise is not None else denoise_strength
            workflow["17"]["inputs"]["denoise"] = effective_denoise
            print(f"      ↳ img2img mode: denoise={effective_denoise:.2f} from {os.path.basename(init_image)}")
        else:
            # Full text-to-image: EmptyLatentImage feeds sampler (default workflow)
            workflow["13"]["inputs"]["latent_image"] = ["102", 0]
            if "17" in workflow:
                workflow["17"]["inputs"]["denoise"] = 1.0

        # 5c. IP-ADAPTER STYLE TRANSFER: Lock visual style from init image
        # When img2img is active, use the init image as a style reference via IP-Adapter
        # This ensures color grading, lighting tone, and atmosphere carry between shots
        if init_image and os.path.exists(init_image):
            try:
                # IP-Adapter needs the init image uploaded (reuse remote_init if available)
                style_ref = remote_init if 'remote_init' in dir() else comfy.upload_image(init_image)
                # Inject IP-Adapter unified loader (node 410)
                workflow["410"] = {
                    "inputs": {
                        "preset": "PLUS (high strength)",
                        "model": ["301", 0],
                    },
                    "class_type": "IPAdapterUnifiedLoader",
                    "_meta": {"title": "Load IP-Adapter (Style Transfer)"}
                }
                # Inject IP-Adapter apply (node 411)
                # Weight from workflow_selector per shot type (portrait=0.25, wide=0.35, etc.)
                # weight_type "style transfer" isolates style from content
                ipa_weight = wf_params.get("ip_adapter_weight", 0.30) if 'wf_params' in dir() else 0.30
                workflow["411"] = {
                    "inputs": {
                        "weight": ipa_weight,
                        "weight_type": "style transfer",
                        "start_at": 0.0,
                        "end_at": 0.4,
                        "image": ["200", 0],
                        "model": ["410", 0],
                    },
                    "class_type": "IPAdapterAdvanced",
                    "_meta": {"title": "Apply IP-Adapter Style (shot consistency)"}
                }
                # Rewire: BasicScheduler and BasicGuider reference IP-Adapter output
                workflow["17"]["inputs"]["model"] = ["411", 0]
                workflow["22"]["inputs"]["model"] = ["411", 0]
                print(f"      ↳ IP-Adapter style transfer injected (weight=0.3, style-only, end=40%)")
            except Exception as e_ipa:
                print(f"      ↳ IP-Adapter skipped (node not available): {e_ipa}")

        # 5d. FACE REFINEMENT removed. PuLID face-locking provides sufficient identity
        # for the current pipeline; FAL PixVerse swap handles any post-video refinement
        # (see phase_c_vision.face_swap_video_frames).

        # 6. Fire Master Execution Workflow
        prompt_id = comfy.queue_prompt(workflow)
        print(f"      ↳ ComfyUI Task {prompt_id} queued. Awaiting GPU computation...")

        # 7. Polling loop with Timeout
        max_retries = 300  # 300 * 2 = 600 seconds (10 min) — RTX 3090 needs more time for FLUX+PuLID
        for attempt in range(max_retries):
            history = comfy.get_history(prompt_id)
            if prompt_id in history:
                outputs = history[prompt_id].get('outputs', {})
                if outputs:
                    # Task finished — check for images
                    for node_id, node_output in outputs.items():
                        if 'images' in node_output:
                            img_info = node_output['images'][0]
                            img_data = comfy.get_image(img_info['filename'], img_info['subfolder'], img_info['type'])
                            if img_data:
                                with open(output_filename, 'wb') as f:
                                    f.write(img_data)
                                print(f"      ✅ Downloaded {mode} render: {output_filename}")
                                return ImageGenResult(output_filename, "COMFYUI_PULID")
                    # Outputs exist but no images — task failed
                    print(f"      ⚠️ ComfyUI task completed but no images in output")
                    break
                # else: outputs empty = task still running, keep polling
            if attempt % 15 == 0 and attempt > 0:
                print(f"      ↳ ComfyUI polling... ({attempt * 2}s elapsed)")
            time.sleep(2)

        print("   [WARN] ComfyUI timed out or crashed. Falling back to FAL FLUX...")
        return _fal_flux_fallback(prompt, output_filename, seed, character_image=character_image,
                                  aspect_ratio=aspect_ratio)

    except Exception as e:
        print(f"   [WARN] ComfyUI error: {e}. Falling back to FAL FLUX...")
        return _fal_flux_fallback(prompt, output_filename, seed, character_image=character_image,
                                  aspect_ratio=aspect_ratio)


def _parse_structured_prompt(prompt: str) -> dict:
    """
    Parse a structured prompt with [SHOT][SCENE][ACTION][OUTFIT][QUALITY] sections.
    Returns dict with extracted sections. Falls back to full prompt if not structured.
    """
    import re
    sections = {}
    for tag in ["SHOT", "SCENE", "ACTION", "OUTFIT", "QUALITY"]:
        match = re.search(rf'\[{tag}\]\s*(.+?)(?=\[(?:SHOT|SCENE|ACTION|OUTFIT|QUALITY)\]|$)', prompt, re.DOTALL)
        if match:
            sections[tag] = match.group(1).strip()

    # If no sections found, treat entire prompt as scene description
    if not sections:
        sections["SCENE"] = prompt
    return sections


def _fal_flux_fallback(prompt, output_filename, seed=None, character_image=None,
                       multi_angle_refs=None, identity_anchor="", aspect_ratio=None):
    """
    Image generator using FAL.ai FLUX Kontext Max Multi for identity preservation.

    v4 strategy — structured prompt parsing:
    - Parse [SHOT][SCENE][ACTION][OUTFIT][QUALITY] sections from prompt
    - Build Kontext prompt: identity anchor FIRST, then scene + outfit changes only
    - NEVER pass raw character descriptions to Kontext (they compete with face ref)
    - Use Kontext Max Multi with up to 9 reference images (AuraFace embeddings)
    """
    fal_key = settings.fal_key
    if not fal_key:
        print("   [FAIL] FAL_KEY missing. No image generation available.")
        return None

    try:
        import urllib.request
        import fal_client

        # PRIORITY 1: FLUX Kontext Max Multi (strongest identity — up to 9 refs)
        if character_image and os.path.exists(character_image):
            try:
                # Collect all reference image URLs
                image_urls = []
                refs_to_upload = []

                if multi_angle_refs and len(multi_angle_refs) > 0:
                    refs_to_upload = [r for r in multi_angle_refs if os.path.exists(r)]
                else:
                    refs_to_upload = [character_image]

                for ref_path in refs_to_upload[:6]:  # Up to 6 refs for max identity
                    try:
                        image_urls.append(fal_client.upload_file(ref_path))
                    except Exception:
                        pass

                if not image_urls:
                    image_urls = [fal_client.upload_file(character_image)]

                # Parse structured sections from the prompt
                sections = _parse_structured_prompt(prompt)
                scene_desc = sections.get("SCENE", prompt[:200])
                action_desc = sections.get("ACTION", "facing the camera")
                outfit_desc = sections.get("OUTFIT", "")
                shot_desc = sections.get("SHOT", "Medium shot, 85mm lens")

                print(f"   [KONTEXT] Max Multi ({len(image_urls)} refs): scene='{scene_desc[:50]}...'")

                # BUILD KONTEXT PROMPT — audit-grade structured prompt
                # Architecture: PRESERVE → CHANGE → CONSTRAIN
                # Rule: identity tokens go FIRST (early attention priority)

                parts = []

                # BLOCK 1: IDENTITY PRESERVATION (highest priority tokens)
                if identity_anchor:
                    parts.append(
                        f"PRESERVE IDENTITY: The person from @Image1 is {identity_anchor}. "
                        f"Keep this EXACT face, hair, glasses, eye color, skin tone unchanged."
                    )
                else:
                    parts.append(
                        "PRESERVE IDENTITY: Keep the exact same person from @Image1. "
                        "Do not change face, hair, or any physical features."
                    )

                # BLOCK 2: SURGICAL CHANGES (only what differs from reference)
                parts.append(f"CHANGE BACKGROUND: {scene_desc}.")
                if outfit_desc:
                    parts.append(f"CHANGE OUTFIT: {outfit_desc}.")
                parts.append(f"SET POSE: {action_desc}.")
                parts.append(f"SET CAMERA: {shot_desc}.")

                # BLOCK 3: HARD CONSTRAINTS (reinforcement)
                parts.append(
                    "CONSTRAINTS: Do NOT alter facial features, hairstyle, glasses, or skin. "
                    "Do NOT generate a different person. "
                    "The face in the output MUST match @Image1 exactly."
                )

                # BLOCK 4: QUALITY (perceptual tokens FLUX actually understands)
                parts.append(
                    "QUALITY: Photorealistic, visible skin pores and subsurface scattering, "
                    "shallow depth of field with circular bokeh, natural film grain ISO 400, "
                    "volumetric atmospheric lighting, micro-detail in fabric texture, "
                    "no AI artifacts, no smooth plastic skin, no over-saturated colors."
                )

                kontext_prompt = " ".join(parts)

                result = fal_client.subscribe(
                    "fal-ai/flux-pro/kontext/max/multi",
                    client_timeout=FAL_TIMEOUT_IMAGE_S,
                    arguments={
                        "prompt": kontext_prompt,
                        "image_urls": image_urls,
                        "guidance_scale": 3.5,
                        "aspect_ratio": fal_aspect_ratio(aspect_ratio),
                        "output_format": "jpeg",
                        "num_images": 1,
                    },
                )
                img_url = result["images"][0]["url"]
                urllib.request.urlretrieve(img_url, output_filename)
                print(f"      [OK] FLUX Kontext image: {output_filename}")
                return ImageGenResult(output_filename, "FLUX_KONTEXT")
            except Exception as e_kontext:
                print(f"      [WARN] FLUX Kontext failed: {e_kontext}, trying FLUX-Pro...")

        # PRIORITY 2: FLUX-Pro text-to-image (no face-lock)
        print(f"   [FALLBACK] FLUX-Pro (no face-lock): '{prompt[:60]}...'")
        try:
            result = fal_client.subscribe(
                "fal-ai/flux-pro/v1.1-ultra",
                client_timeout=FAL_TIMEOUT_IMAGE_S,
                arguments={
                    "prompt": prompt,
                    "aspect_ratio": fal_aspect_ratio(aspect_ratio),
                    "output_format": "jpeg",
                    "seed": seed,
                    "num_inference_steps": 32,
                    "guidance_scale": 3.5,
                },
            )
            img_url = result["images"][0]["url"]
            urllib.request.urlretrieve(img_url, output_filename)
            print(f"      [OK] FLUX-Pro image: {output_filename}")
            return ImageGenResult(output_filename, "FLUX_PRO")
        except Exception as e1:
            print(f"      [WARN] FLUX-Pro failed: {e1}, trying FLUX schnell...")

        # Fallback to schnell (faster, lower quality)
        try:
            import fal_client
            result = fal_client.subscribe(
                "fal-ai/flux/schnell",
                client_timeout=FAL_TIMEOUT_IMAGE_S,
                arguments={
                    "prompt": prompt,
                    "image_size": fal_image_size(aspect_ratio),
                    "num_inference_steps": 4,
                    "seed": seed,
                },
            )
            img_url = result["images"][0]["url"]
            urllib.request.urlretrieve(img_url, output_filename)
            print(f"      ✅ FAL FLUX-schnell image: {output_filename}")
            return ImageGenResult(output_filename, "FLUX_SCHNELL")
        except Exception as e2:
            print(f"      ⚠️ FLUX-schnell also failed: {e2}")

        # Last resort: Pollinations (free, lower quality)
        import urllib.parse
        encoded = urllib.parse.quote(prompt)
        _pw, _ph = portrait_swap(1344, 768, aspect_ratio)
        poll_url = f"https://image.pollinations.ai/prompt/{encoded}?width={_pw}&height={_ph}&nologo=True&model=flux&seed={seed or 42}"
        img_data = urllib.request.urlopen(poll_url).read()
        if len(img_data) > 5000:
            with open(output_filename, "wb") as f:
                f.write(img_data)
            print(f"      ✅ Pollinations fallback image: {output_filename}")
            return ImageGenResult(output_filename, "POLLINATIONS")

        print("❌ All image generation methods failed.")
        return None

    except Exception as e:
        print(f"❌ Fallback image generation failed: {e}")
        return None

