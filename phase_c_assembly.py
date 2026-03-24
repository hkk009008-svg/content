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

def generate_ai_broll(prompt, output_filename):
    """Hits the industrial Fal.ai Flux endpoint for instant, ban-free 4K vertical image generation."""
    print(f"🤖 [PHASE C] Generating AI B-Roll: '{prompt[:50]}...'")
    import os
    import requests
    import urllib.parse
    
    fal_key = os.getenv("FAL_KEY")
    
    try:
        img_data = b""
        if fal_key:
            # Generate instantly using the premium Fal.ai Flux Schnell engine
            url = "https://fal.run/fal-ai/flux/schnell"
            headers = {
                "Authorization": f"Key {fal_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "prompt": prompt,
                "image_size": "portrait_16_9",
                "num_inference_steps": 4,
                "num_images": 1
            }
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

def crop_to_vertical(clip):
    """Automatically crops a horizontal video to the 9:16 YouTube Shorts standard."""
    target_ratio = 9 / 16
    current_ratio = clip.w / clip.h
    
    if current_ratio > target_ratio:
        # Video is wider than 9:16, crop the sides to center it
        new_width = int(clip.h * target_ratio)
        x_center = clip.w / 2
        clip = clip.crop(x_center=x_center, y_center=clip.h/2, width=new_width, height=clip.h)
    
    # Enforce strict 4K vertical cinema resolution (2160x3840) to prevent render crashes
    return clip.resize((2160, 3840))

def add_top_banner(video_clip, topic_text):
    """Adds a persistent 'Case File' authority banner to the top of the video with proper word-wrapping."""
    from moviepy.editor import ColorClip, TextClip, CompositeVideoClip
    
    # 1. Background Box (Slightly taller to handle multiline text and almost fully opaque for legibility)
    banner_bg = ColorClip(size=(2160, 360), color=(10, 10, 10)).set_opacity(1.0).set_position(('center', 'top')).set_duration(video_clip.duration)
    
    # 2. Modern Brand Accent Line (Ultra-thin minimalist white line)
    accent_line = ColorClip(size=(2160, 3), color=(255, 255, 255)).set_position(('center', 360)).set_duration(video_clip.duration)
    
    # 3. Small "Authority" Badge Text (Clean minimalist sans-serif)
    try:
        badge_txt = TextClip(
            "A N A L Y S I S", 
            fontsize=40, 
            color='#E0E0E0', 
            font='/System/Library/Fonts/Supplemental/Arial Unicode.ttf'
        ).set_position((100, 70)).set_duration(video_clip.duration)
    except:
        badge_txt = TextClip("A N A L Y S I S", fontsize=40, color='#E0E0E0').set_position((100, 70)).set_duration(video_clip.duration)
        
    # 4. Main Title (High-end editorial fashion serif)
    try:
        main_txt = TextClip(
            topic_text.upper(), 
            fontsize=65, 
            color='white', 
            font='/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            align='West',
            method='caption',
            size=(1900, None) # This tells MoviePy to auto word-wrap within 1900 pixels
        ).set_position((100, 150)).set_duration(video_clip.duration)
    except:
        main_txt = TextClip(topic_text.upper(), fontsize=65, color='white', align='West', method='caption', size=(1900, None)).set_position((100, 150)).set_duration(video_clip.duration)
    
    return CompositeVideoClip([video_clip, banner_bg, accent_line, badge_txt, main_txt])

def add_dynamic_captions(audio_path, video_clip, music_vibe="suspense", pre_transcribed_result=None):
    """
    Uses local Whisper AI to transcribe audio and burn word-by-word 
    captions onto the MoviePy video clip with dynamically mapped styles.
    """
    if not pre_transcribed_result:
        print("🧠 [PHASE C] Loading Whisper AI model (this takes a few seconds)...")
        # 'base' is fast and highly accurate for English.
        model = whisper.load_model("base") 
        print("📝 [PHASE C] Transcribing audio and extracting word timestamps...")
        # word_timestamps=True is the secret to Hormozi-style pop-up captions
        result = model.transcribe(audio_path, word_timestamps=True)
    else:
        result = pre_transcribed_result
    
    text_clips = []
    word_index = 0
    
    # Define aesthetic mapping based on Gemini's emotional mood analysis (All dimensions scaled 2x for 4K geometry)
    vibe_styles = {
        "suspense": {
            "font": '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            "colors": ["#E2FF3D"], # Acid/Cyber Yellow for suspense
            "opacity": 1.0,
            "stroke": 6,
            "size": 110
        },
        "corporate": {
            "font": '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            "colors": ["#FACC15"], # Clean Modern Gold for corporate
            "opacity": 1.0,
            "stroke": 6,
            "size": 110
        },
        "lofi": {
            "font": '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            "colors": ["#F0F8FF", "#E6E6FA"], # Soft Alice Blue and Lavender for cosmic soothe
            "opacity": 0.9,
            "stroke": 4,
            "size": 90
        },
        "upbeat": {
            "font": '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            "colors": ["#FFEA00"], # High-Energy Neon yellow for upbeat
            "opacity": 1.0,
            "stroke": 6,
            "size": 110
        },
        "aggressive": {
            "font": '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            "colors": ["#FFED00"], # Sharp Impact Yellow for aggressive
            "opacity": 1.0,
            "stroke": 6,
            "size": 110
        }
    }
    
    style = vibe_styles.get(music_vibe, vibe_styles["suspense"])
    
    # Loop through the transcription data
    for segment in result['segments']:
        for word_info in segment['words']:
            word_text = word_info['word'].strip().upper() # ALL CAPS for visual impact
            start_time = word_info['start']
            end_time = word_info['end']
            
            # --- Dynamic Mood Routing ---
            colors = style["colors"]
            color_choice = colors[word_index % len(colors)]
            word_index += 1
            
            # Create a styled graphic for each word
            
            # --- GENTLE IMMERSION ---
            # No aggressive retina shock. Just smooth, pleasing text.
            is_hook_word = word_index <= 3
            current_color = color_choice
            
            # --- DYNAMIC FONT SCALING (PREVENT UGLY BREAKS) ---
            # If a single word or number is excessively long (like "$1,000,000,000" or "entrepreneurship"),
            # it physically exceeds the horizontal screen space. MoviePy tries to awkwardly split it 
            # onto 2 lines. We fix this by crushing the font size inversely to its character length!
            base_size = int(style["size"] * 1.5) if is_hook_word else style["size"]
            
            if len(word_text) > 8:
                # Add a strict floor boundary of 60% of base size to prevent long words from becoming microscopically unreadable
                current_size = max(int(base_size * 0.60), int(base_size * (8.0 / len(word_text))))
            else:
                current_size = base_size
            
            try:
                txt_clip = TextClip(
                    word_text, 
                    fontsize=current_size,
                    color=current_color, 
                    font=style["font"], 
                    stroke_color='black',
                    stroke_width=style["stroke"],
                    method='label' # Strictly forces the text to stay horizontally on ONE single line
                ).set_opacity(style["opacity"])
                
                # Set exact timing and center it on screen
                txt_clip = txt_clip.set_start(start_time).set_end(end_time)
                txt_clip = txt_clip.set_position(('center', 'center'))
                
                text_clips.append(txt_clip)
            except Exception as e:
                print(f"⚠️ Warning: Could not generate text clip for word '{word_text}'. Error: {e}")
                
    print("🔥 [PHASE C] Burning captions into the video timeline...")
    # Overlay all the text graphics onto the background video
    final_video_with_subs = CompositeVideoClip([video_clip] + text_clips)
    
    return final_video_with_subs

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
        
        print("🧠 [PHASE C] Analyzing Voiceover Tempo via Whisper AI...")
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
        
        tempo_model = whisper.load_model("base")
        whisper_result = tempo_model.transcribe(audio_path, word_timestamps=True)
        
        # 1. GENERATE .ASS SUBTITLES NATIVELY
        ass_path = "whisper_captions.ass"
        generate_ass_subtitles(whisper_result, ass_path)
        
        segment_durations = []
        for segment in whisper_result.get('segments', []):
            dur = segment['end'] - segment['start']
            if dur > 1.0:
                segment_durations.append(dur)
                
        if len(segment_durations) > 0 and segment_durations[0] > 1.2:
            remainder = segment_durations[0] - 1.2
            segment_durations[0] = 1.2
            segment_durations.insert(1, remainder)
            
        pacing_cut_map = {"fast": 2.0, "moderate": 2.5, "relaxed": 3.0}
        target_cut_length = pacing_cut_map.get(video_pacing, 2.5)
        
        normalized_clips = []
        current_dur = 0
        img_index = 0
        
        print("⚡ [PHASE C] Normalizing and Trimming Base Video Modules...")
        
        # 2. DYNAMIC API CLIP SYNC AND NORMALIZATION 
        for vid_data in video_paths:
            if current_dur >= total_audio_duration:
                break
                
            raw_vid_path = vid_data['path'] if isinstance(vid_data, dict) else vid_data
            
            if img_index < len(segment_durations):
                active_cut_length = segment_durations[img_index]
            else:
                active_cut_length = target_cut_length
            
            norm_path = f"norm_clip_{img_index}.mp4"
            normalize_clip(raw_vid_path, norm_path, duration_sec=active_cut_length)
            normalized_clips.append(norm_path)
            
            current_dur += active_cut_length
            img_index += 1
            
        # 3. SEAMLESS ZERO-LOSS FFMPEG CONCATENATION
        stitched_path = "temp_stitched_master.mp4"
        stitch_modules(normalized_clips, stitched_path)
        
        # 3. HIGH-FIDELITY MOVIEPY OVERLAYS (Captions, Banners, Logos)
        from moviepy.editor import VideoFileClip
        final_video = VideoFileClip(stitched_path)
        # final_video = add_top_banner(final_video, topic_text) # Removed banner for edge-to-edge full screen
        final_video = add_dynamic_captions(audio_path, final_video, music_vibe, pre_transcribed_result=whisper_result)
        
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
        
        # 4. MASTER FFMPEG AUDIO MIX
        bg_music_path = f"bg_{music_vibe}.mp3"
        if not os.path.exists(bg_music_path):
            print(f"⚠️ Warning: Missing bespoke AI audio ({bg_music_path}). Please ensure phase_b_audio successfully called Fal.ai API.")
            
        print("🔊 Orchestrating Master FFMPEG Filtergraph (Audio Ducking)...")
        success = execute_master_ffmpeg_assembly(
            video_path=temp_overlay_mp4,
            tts_path=audio_path,
            bgm_path=bg_music_path,
            ass_path=ass_path,
            output_path=output_filename,
            topic_text=topic_text
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
