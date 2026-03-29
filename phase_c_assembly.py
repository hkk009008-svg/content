import os

# Hardcode the Homebrew ImageMagick path before MoviePy imports
os.environ["IMAGEMAGICK_BINARY"] = "/opt/homebrew/bin/magick"

import requests
import whisper
from dotenv import load_dotenv

# Monkey-patch for MoviePy 1.0.3 compatibility with new Pillow versions
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "Resampling", PIL.Image).LANCZOS

from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, TextClip, CompositeVideoClip
import moviepy.video.fx.all as vfx

# Load environment variables
load_dotenv()
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

import json
import uuid
import time
import requests

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
                       pulid_weight_override=None, negative_prompt=""):
    """
    Generates a cinematic image with face-identity preservation.

    v3 priority chain:
    1. fal.ai FLUX Kontext (identity-preserving, no local GPU needed)
    2. ComfyUI + PuLID on RunPod (if models are available)
    3. fal.ai FLUX-Pro (no face-lock, last resort)

    Args:
        prompt: Image generation prompt (enhanced by continuity engine)
        output_filename: Output path for generated image
        seed: Deterministic seed for consistency
        character_image: Primary character reference for face identity
        init_image: Previous shot image for img2img temporal chaining
        denoise_strength: 0.0-1.0, lower = more similar to init_image
        characters: List of character config dicts
    """
    mode = "img2img" if init_image else "txt2img"

    # PRIORITY 1: ComfyUI + PuLID on RunPod RTX 4090 (fastest + strongest face-lock)
    server_url = os.getenv("COMFYUI_SERVER_URL")
    if server_url and os.path.exists("pulid.json"):
        print(f"   [PHASE C] Generating [{mode}] via ComfyUI PuLID (RTX 4090): '{prompt[:60]}...'")
    elif character_image and os.path.exists(character_image) and os.getenv("FAL_KEY"):
        # PRIORITY 2: FLUX Kontext Max Multi (fallback if ComfyUI unavailable)
        result = _fal_flux_fallback(
            prompt, output_filename, seed,
            character_image=character_image,
            multi_angle_refs=multi_angle_refs,
            identity_anchor=identity_anchor,
        )
        if result:
            return result
        return None
    else:
        return _fal_flux_fallback(prompt, output_filename, seed, character_image=character_image)

    # ComfyUI path continues below
    if not server_url:
        return _fal_flux_fallback(prompt, output_filename, seed, character_image=character_image)

    try:
        if not os.path.exists("pulid.json"):
            print("   [WARN] pulid.json missing — using Kontext fallback")
            return _fal_flux_fallback(prompt, output_filename, seed, character_image=character_image)

        with open("pulid.json", "r") as f:
            workflow = json.load(f)

        # WORKFLOW SELECTOR — apply shot-type-specific parameters
        try:
            from workflow_selector import classify_shot_type, get_workflow_params, apply_workflow_params
            # Build a minimal shot dict for classification
            shot_info = {"prompt": prompt, "characters_in_frame": ["char"] if character_image else []}
            shot_type = classify_shot_type(shot_info)
            wf_params = get_workflow_params(shot_type)
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
                return _fal_flux_fallback(prompt, output_filename, seed, character_image=None)
        except ImportError:
            pass  # workflow_selector not available — use defaults

        comfy = RunPodComfyUI(server_url)

        # 1. Inject LLM Text prompt to CLIP node "122"
        workflow["122"]["inputs"]["text"] = prompt

        # 2. Aspect ratio — 16:9 widescreen via EmptyLatentImage node "102"
        workflow["102"]["inputs"]["width"] = 1344
        workflow["102"]["inputs"]["height"] = 768
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

            # Set denoise strength in BasicScheduler (node 17)
            workflow["17"]["inputs"]["denoise"] = denoise_strength
            print(f"      ↳ img2img mode: denoise={denoise_strength:.2f} from {os.path.basename(init_image)}")
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

        # 5d. FACE REFINEMENT: FaceDetailer (Impact Pack) or ReActor post-generation
        # FaceDetailer detects faces, crops the region, regenerates at higher detail,
        # then composites back — fixing eye/mouth artifacts without full regeneration.
        # Falls back to FAL PixVerse cloud face swap if no ComfyUI nodes available.
        if character_image and os.path.exists(character_image):
            _face_refine_node = None
            try:
                # Check which face refinement nodes are available on the pod
                for node_class in ["FaceDetailer", "ReActorFaceSwap"]:
                    _obj_info = requests.get(f"{server_url}/object_info/{node_class}", timeout=5)
                    if _obj_info.status_code == 200:
                        _face_refine_node = node_class
                        break
            except Exception:
                pass

            if _face_refine_node == "FaceDetailer":
                # Impact Pack FaceDetailer — auto-detect face, regenerate at high detail
                workflow["420"] = {
                    "inputs": {
                        "image": ["8", 0],              # VAE decoded output
                        "model": ["301", 0],            # Model from PAG
                        "clip": ["11", 0],              # CLIP for text encoding
                        "vae": ["10", 0],               # VAE for encode/decode
                        "positive": ["60", 0],          # Conditioning
                        "negative": ["60", 0],          # Same (FLUX has no negative)
                        "bbox_detector": "bbox/face_yolov8m.pt",
                        "guide_size": 512,
                        "guide_size_for": True,
                        "max_size": 1024,
                        "seed": ["25", 0],
                        "steps": 15,
                        "cfg": 3.5,
                        "sampler_name": "dpmpp_2m",
                        "scheduler": "sgm_uniform",
                        "denoise": 0.35,
                        "feather": 5,
                        "noise_mask": True,
                        "force_inpaint": True,
                        "drop_size": 10,
                        "cycle": 1,
                    },
                    "class_type": "FaceDetailer",
                    "_meta": {"title": "FaceDetailer (face region refinement)"}
                }
                workflow["500"]["inputs"]["image"] = ["420", 0]
                print(f"      ↳ FaceDetailer injected (denoise=0.35, guide=512)")
            elif _face_refine_node == "ReActorFaceSwap":
                # ReActor face swap + CodeFormer (if available despite GitHub takedown)
                cfw = 0.7  # Could be overridden from project settings
                workflow["420"] = {
                    "inputs": {
                        "input_image": ["8", 0],
                        "source_image": ["93", 0],
                        "input_faces_index": "0", "source_faces_index": "0",
                        "console_log_level": "1",
                        "face_restore_model": "codeformer-v0.1.0.pth",
                        "face_restore_visibility": 1.0,
                        "codeformer_weight": cfw,
                        "detect_gender_input": "no", "detect_gender_source": "no",
                        "input_faces_order": "left-right", "source_faces_order": "left-right",
                    },
                    "class_type": "ReActorFaceSwap",
                    "_meta": {"title": "ReActor Face Swap + CodeFormer"}
                }
                workflow["500"]["inputs"]["image"] = ["420", 0]
                print(f"      ↳ ReActor+CodeFormer injected (codeformer_weight={cfw})")
            else:
                print(f"      ↳ No face refinement nodes on pod — FAL PixVerse swap used post-video instead")

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
                                return output_filename
                    # Outputs exist but no images — task failed
                    print(f"      ⚠️ ComfyUI task completed but no images in output")
                    break
                # else: outputs empty = task still running, keep polling
            if attempt % 15 == 0 and attempt > 0:
                print(f"      ↳ ComfyUI polling... ({attempt * 2}s elapsed)")
            time.sleep(2)

        print("   [WARN] ComfyUI timed out or crashed. Falling back to FAL FLUX...")
        return _fal_flux_fallback(prompt, output_filename, seed, character_image=character_image)

    except Exception as e:
        print(f"   [WARN] ComfyUI error: {e}. Falling back to FAL FLUX...")
        return _fal_flux_fallback(prompt, output_filename, seed, character_image=character_image)


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
                       multi_angle_refs=None, identity_anchor=""):
    """
    Image generator using FAL.ai FLUX Kontext Max Multi for identity preservation.

    v4 strategy — structured prompt parsing:
    - Parse [SHOT][SCENE][ACTION][OUTFIT][QUALITY] sections from prompt
    - Build Kontext prompt: identity anchor FIRST, then scene + outfit changes only
    - NEVER pass raw character descriptions to Kontext (they compete with face ref)
    - Use Kontext Max Multi with up to 9 reference images (AuraFace embeddings)
    """
    fal_key = os.getenv("FAL_KEY")
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
                    arguments={
                        "prompt": kontext_prompt,
                        "image_urls": image_urls,
                        "guidance_scale": 3.5,
                        "aspect_ratio": "16:9",
                        "output_format": "jpeg",
                        "num_images": 1,
                    },
                )
                img_url = result["images"][0]["url"]
                urllib.request.urlretrieve(img_url, output_filename)
                print(f"      [OK] FLUX Kontext image: {output_filename}")
                return output_filename
            except Exception as e_kontext:
                print(f"      [WARN] FLUX Kontext failed: {e_kontext}, trying FLUX-Pro...")

        # PRIORITY 2: FLUX-Pro text-to-image (no face-lock)
        print(f"   [FALLBACK] FLUX-Pro (no face-lock): '{prompt[:60]}...'")
        try:
            result = fal_client.subscribe(
                "fal-ai/flux-pro/v1.1-ultra",
                arguments={
                    "prompt": prompt,
                    "aspect_ratio": "16:9",
                    "output_format": "jpeg",
                    "seed": seed,
                    "num_inference_steps": 32,
                    "guidance_scale": 3.5,
                },
            )
            img_url = result["images"][0]["url"]
            urllib.request.urlretrieve(img_url, output_filename)
            print(f"      [OK] FLUX-Pro image: {output_filename}")
            return output_filename
        except Exception as e1:
            print(f"      [WARN] FLUX-Pro failed: {e1}, trying FLUX schnell...")

        # Fallback to schnell (faster, lower quality)
        try:
            import fal_client
            result = fal_client.subscribe(
                "fal-ai/flux/schnell",
                arguments={
                    "prompt": prompt,
                    "image_size": "landscape_16_9",
                    "num_inference_steps": 4,
                    "seed": seed,
                },
            )
            img_url = result["images"][0]["url"]
            urllib.request.urlretrieve(img_url, output_filename)
            print(f"      ✅ FAL FLUX-schnell image: {output_filename}")
            return output_filename
        except Exception as e2:
            print(f"      ⚠️ FLUX-schnell also failed: {e2}")

        # Last resort: Pollinations (free, lower quality)
        import urllib.parse
        encoded = urllib.parse.quote(prompt)
        poll_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1344&height=768&nologo=True&model=flux&seed={seed or 42}"
        img_data = urllib.request.urlopen(poll_url).read()
        if len(img_data) > 5000:
            with open(output_filename, "wb") as f:
                f.write(img_data)
            print(f"      ✅ Pollinations fallback image: {output_filename}")
            return output_filename

        print("❌ All image generation methods failed.")
        return None

    except Exception as e:
        print(f"❌ Fallback image generation failed: {e}")
        return None

def scale_to_widescreen(clip):
    """Enforces strict 4K widescreen cinema resolution (3840x2160) for long-form movies."""
    # Ensure standard 1080p high definition to prevent MoviePy OOM crashing, but mapped natively for widescreen
    return clip.resize((1920, 1080))

# --- CINEMATIC TEXT BANNER ABOLISHED ---
# The Long-Form engine relies solely on pure uninterrupted visual narrative.

def assemble_final_video(ctx: dict):
    print(f"🎬 [PHASE C] Initializing Zero-Loss Assembly Matrix for topic: '{ctx.get('topic')}'")
    
    audio_path = ctx.get("audio_path")
    video_paths = ctx.get("downloaded_vids", [])
    output_filename = ctx.get("final_video_path", "FINAL_READY_TO_UPLOAD.mp4")
    music_vibe = ctx.get("music_vibe", "suspense")
    video_pacing = ctx.get("video_pacing", "moderate")
    topic_text = ctx.get("topic", "")
    
    import os
    if not os.path.exists(audio_path):
        print(f"❌ Error: Voiceover file {audio_path} not found.")
        return None
    print("\n🎬 [PHASE C] Assembling the final video cut...")
    
    try:
        from phase_c_ffmpeg import normalize_clip, stitch_modules, generate_ass_subtitles, execute_master_ffmpeg_assembly
        
        print("🧠 [PHASE C] Analyzing Voiceover Tempo via Whisper AI [LARGE-V3]...")
        import whisper
        import math
        
        # Get total audio duration via ffprobe since we aren't using moviepy
        import subprocess
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                 "format=duration", "-of",
                                 "default=noprint_wrappers=1:nokey=1", audio_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
        total_audio_duration = float(result.stdout)
        
        tempo_model = whisper.load_model("turbo")
        whisper_result = tempo_model.transcribe(audio_path, word_timestamps=True)
        
        # 1. GENERATE NATIVE SCENE METADATA (Subtitles disabled for Cinematic Engine) 
        # (ass generation skipped)
        
        # # PERFECT SYNC DURATION CALCULATION # #
        # Match narration evenly across the generated visual frames
        num_clips = len(video_paths)
        clip_duration = total_audio_duration / num_clips if num_clips > 0 else 3.0
        
        normalized_clips = []
        current_dur = 0
        img_index = 0
        
        print(f"⚡ [PHASE C] Normalizing {num_clips} Base Video Modules to {clip_duration:.2f}s each...")
        
        import random
        # Map out complementary visual filters for different emotional themes
        vibe_effects = {
            "suspense": ["gritty_contrast", "cinematic_glow", "cyberpunk_glitch", "gritty_contrast"],
            "aggressive": ["cyberpunk_glitch", "gritty_contrast", "cinematic_glow"],
            "lofi": ["dreamy_blur", "cinematic_glow", "documentary_neutral"],
            "corporate": ["documentary_neutral", "cinematic_glow"],
            "upbeat": ["cinematic_glow", "documentary_neutral"]
        }
        active_effects_pool = vibe_effects.get(music_vibe, ["gritty_contrast", "cinematic_glow", "documentary_neutral", "cyberpunk_glitch", "dreamy_blur"])
        
        # 2. DYNAMIC API CLIP SYNC AND NORMALIZATION 
        timeline_effects = []
        for vid_data in video_paths:
            raw_vid_path = vid_data['path'] if isinstance(vid_data, dict) else vid_data
            
            # Apply dynamic multiple effects to complement the scene, avoiding consistent boredom
            if isinstance(vid_data, dict) and vid_data.get('effect'):
                visual_effect = vid_data['effect']
            else:
                visual_effect = random.choice(active_effects_pool)
            
            active_cut_length = clip_duration
            timeline_effects.append({"effect": visual_effect, "start": current_dur, "end": current_dur + active_cut_length})
            
            norm_path = f"norm_clip_{img_index}.mp4"
            normalize_clip(raw_vid_path, norm_path, duration_sec=active_cut_length, effect=visual_effect)
            normalized_clips.append(norm_path)
            
            current_dur += active_cut_length
            img_index += 1
            
        # 3. SEAMLESS ZERO-LOSS FFMPEG CONCATENATION
        stitched_path = "temp_stitched_master.mp4"
        stitch_modules(normalized_clips, stitched_path)
        
        # 3. HIGH-FIDELITY MOVIEPY OVERLAYS (Captions Disabled)
        from moviepy.editor import VideoFileClip
        final_video = VideoFileClip(stitched_path)

        
        temp_overlay_mp4 = "temp_captions_ready.mp4"
        print("⏳ Blazing Fast GPU Rendering CapCut-Style Graphical Master...")
        final_video.write_videofile(
            temp_overlay_mp4, 
            fps=30, 
            codec="h264_videotoolbox", 
            audio=True,
            bitrate="8000k",
            logger=None
        )
        final_video.close()
        
        # 4. MASTER FFMPEG AUDIO MIX & VISUAL COLOR GRADING
        bg_music_path = f"bg_{music_vibe}.mp3"
        lut_path = f"lut_{music_vibe}.png" # Programmatic cinematic color mapping
        
        if not os.path.exists(bg_music_path):
            print(f"⚠️ Warning: Missing bespoke AI audio ({bg_music_path}). Please ensure phase_b_audio successfully called Fal.ai API.")
            
        print("🔊 Orchestrating Master FFMPEG Filtergraph (Audio Ducking & HaldCLUT Color Grading)...")
        success = execute_master_ffmpeg_assembly(
            video_path=temp_overlay_mp4,
            tts_path=audio_path,
            bgm_path=bg_music_path,
            ass_path=None, # Passed as None to ensure disabled subtitles
            output_path=output_filename,
            topic_text=topic_text,
            tts_duration=total_audio_duration,
            timeline_effects=timeline_effects,
            foley_paths=ctx.get("foley_audio_paths", []),
            lut_path=lut_path
        )
        
        if success:
            print(f"\n✅ Success! Final video rendered successfully: {output_filename}")
            return True
        return False
        
    except Exception as e:
        print(f"\n❌ Error during video assembly: {e}")
        return False

# Optional testing block
if __name__ == "__main__":
    print("Run this through main.py to test the full pipeline!")
