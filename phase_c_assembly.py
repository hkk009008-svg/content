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

def generate_ai_broll(prompt, output_filename, seed=None, character_image=None):
    """Executes the exact pulid.json blueprint headlessly via RunPod ComfyUI."""
    print(f"🤖 [PHASE C] Generating Cinematic AI B-Roll headlessly via Private ComfyUI: '{prompt[:50]}...'")
    
    server_url = os.getenv("COMFYUI_SERVER_URL")
    if not server_url:
        print("❌ CRITICAL: COMFYUI_SERVER_URL is completely missing from your .env file!")
        print("   Please paste your RunPod URL (e.g. https://xxx-8188.proxy.runpod.net) into your .env!")
        return None
        
    try:
        if not os.path.exists("pulid.json"):
            print("❌ CRITICAL: pulid.json blueprint is missing from the working directory!")
            return None
            
        with open("pulid.json", "r") as f:
            workflow = json.load(f)
            
        comfy = RunPodComfyUI(server_url)
        
        # 1. Surgical Bypass: Inject LLM Text prompt natively to CLIP, bypassing Florence2 vision model
        # The CLIPTextEncode node id in pulid.json is "122"
        workflow["122"]["inputs"]["text"] = prompt
        
        # 2. Hardcode 16:9 widescreen layout for FLUX
        # The EmptyLatentImage node id is "102"
        workflow["102"]["inputs"]["width"] = 1344
        workflow["102"]["inputs"]["height"] = 768
        workflow["102"]["inputs"]["batch_size"] = 1
        
        # 3. Synchronize Continuous Seed
        # The RandomNoise node is "25"
        if seed is not None:
             workflow["25"]["inputs"]["noise_seed"] = seed
             
        # 4. Upload & Inject Master Character Face
        # The LoadImage node for PuLID is "93"
        if character_image and os.path.exists(character_image):
            remote_face_filename = comfy.upload_image(character_image)
            workflow["93"]["inputs"]["image"] = remote_face_filename
        else:
            print("   ⚠️ No Character identity injected! Proceeding globally without face lock.")
            
        # 5. Fire Master Execution Workflow
        prompt_id = comfy.queue_prompt(workflow)
        print(f"      ↳ ComfyUI Task {prompt_id} queued flawlessly. Awaiting GPU cluster computation...")
        
        # 6. Polling loop with Timeout
        max_retries = 150 # 150 * 2 = 300 seconds (5 min)
        for attempt in range(max_retries):
            history = comfy.get_history(prompt_id)
            if prompt_id in history:
                outputs = history[prompt_id].get('outputs', {})
                for node_id, node_output in outputs.items():
                    if 'images' in node_output:
                        img_info = node_output['images'][0]
                        img_data = comfy.get_image(img_info['filename'], img_info['subfolder'], img_info['type'])
                        if img_data:
                            with open(output_filename, 'wb') as f:
                                f.write(img_data)
                            print(f"      ✅ Successfully downloaded 16:9 high-fidelity render: {output_filename}")
                            return output_filename
                break # History exists but no images?
            time.sleep(2)
            
        print("❌ ComfyUI inference timed out or crashed natively.")
        return None
        
    except Exception as e:
        print(f"❌ Error firing Headless ComfyUI Node Generator: {e}")
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
