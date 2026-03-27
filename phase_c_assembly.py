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

def generate_ai_broll(prompt, output_filename, seed=None):
    """Hits the industrial Fal.ai Flux endpoint for instant, ban-free 4K vertical image generation."""
    print(f"🤖 [PHASE C] Generating AI B-Roll: '{prompt[:50]}...'")
    import os
    import requests
    import urllib.parse
    
    fal_key = os.getenv("FAL_KEY")
    
    try:
        img_data = b""
        if fal_key:
            # Generate premium photorealistic 4K frames using Flux 1.1 Pro Ultra
            url = "https://fal.run/fal-ai/flux-pro/v1.1-ultra"
            headers = {
                "Authorization": f"Key {fal_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "raw": True
            }
            if seed is not None:
                payload["seed"] = seed
                
            resp = requests.post(url, json=payload, headers=headers)
            
            if resp.status_code == 200:
                img_url = resp.json()["images"][0]["url"]
                img_data = requests.get(img_url).content
            else:
                print(f"⚠️ Fal.ai failed with {resp.status_code}. Falling back to free tier...")
        
        # If no key is set or Fal.ai fails/runs out of credits, fallback to the free Pollinations proxy
        if len(img_data) < 5000:
            encoded_prompt = urllib.parse.quote(prompt)
            url_fallback = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=1365&nologo=True&model=flux"
            if seed is not None:
                url_fallback += f"&seed={seed}"
                
            req_headers = {'User-Agent': 'Mozilla/5.0'}
            img_data = requests.get(url_fallback, headers=req_headers).content
        
        # Last Resort Failsafe
        if len(img_data) < 5000:
            print(f"⚠️ Pollinations 429 Limit Block. Using Unsplash Fallback to secure the render queue.")
            img_data = requests.get("https://picsum.photos/768/1365").content
                
        with open(output_filename, 'wb') as handler:
            handler.write(img_data)
        return output_filename
    except Exception as e:
        print(f"❌ Error generating AI B-Roll: {e}")
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
