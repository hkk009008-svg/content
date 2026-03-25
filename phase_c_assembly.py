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
    
    # 👾 SUBLIMINAL GLITCH STIMULATION ENGINE 👾
    # Creates mathematically random micro-tears in the background video behind the text
    import numpy as np
    import random
    
    def glitch_filter(get_frame, t):
        frame = get_frame(t)
        # 3% chance per frame for a faint cybernetic horizontal tear
        if random.random() < 0.03:
            h, w, c = frame.shape
            y_start = random.randint(0, int(h * 0.9))
            y_end = y_start + random.randint(15, 60)
            shift_amount = random.randint(20, 50) * random.choice([-1, 1])
            
            # Avoid mutating the read-only frame buffer directly
            glitched = np.copy(frame)
            glitched[y_start:y_end, :, :] = np.roll(glitched[y_start:y_end, :, :], shift=shift_amount, axis=1)
            
            # 1% chance for an absolute color inversion (subliminal frame flash)
            if random.random() < 0.33:
                glitched = 255 - glitched
                
            return glitched
        return frame
        
    print("👾 [PHASE C] Applying Faint Subliminal VHS Glitching to Background Layer...")
    video_clip = video_clip.fl(glitch_filter)
    
    # 💥 VERY CLEAN & NEAT V4 AESTHETIC 💥
    # Focus: Highest legibility, vivid white bold, thin crisp outline, soft outer shadow
    font_choice = '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'
    font_size = 85

    # Extract ALL individual words globally
    words_data = []
    for segment in result['segments']:
        if 'words' in segment:
            for w in segment['words']:
                words_data.append({
                    'text': w['word'].strip().upper(),
                    'start': w['start'],
                    'end': w['end']
                })
        else:
            words_data.append({
                'text': segment['text'].strip().upper(),
                'start': segment['start'],
                'end': segment['end']
            })

    # Group into 1-2 words max for standard legible pacing
    kinetic_chunks = []
    current_chunk = []
    current_start = 0
    
    for i, w_dict in enumerate(words_data):
        current_chunk.append(w_dict['text'])
        if len(current_chunk) == 1:
            current_start = w_dict['start']
            
        if len(current_chunk) >= 2 or len(w_dict['text']) > 8 or i == len(words_data) - 1:
            kinetic_chunks.append({
                'text': " ".join(current_chunk),
                'start': current_start,
                'end': w_dict['end']
            })
            current_chunk = []

    # Generate the hyper-legible shadow-layered TextClips
    for chunk in kinetic_chunks:
        segment_text = chunk['text']
        start_time = chunk['start']
        end_time = chunk['end']
        
        try:
            # 1. The Soft Outer Shadow (Thick semi-transparent black stroke creates a soft glow layer)
            shadow_clip = TextClip(
                segment_text, 
                fontsize=font_size,
                color='black', 
                font=font_choice, 
                stroke_color='black',
                stroke_width=12,
                method='caption',
                size=(950, None), 
                align='center'
            ).set_opacity(0.4).set_start(start_time).set_end(end_time).set_position(('center', 'center'))
            
            # 2. The Vivid Inner Text (White bold with very thin crisp black outline)
            main_clip = TextClip(
                segment_text, 
                fontsize=font_size,
                color='white', 
                font=font_choice, 
                stroke_color='black',
                stroke_width=2,
                method='caption',
                size=(950, None), 
                align='center'
            ).set_opacity(1.0).set_start(start_time).set_end(end_time).set_position(('center', 'center'))
            
            # Append BOTH to the visual pipeline to compound the 3D aesthetic
            text_clips.append(shadow_clip)
            text_clips.append(main_clip)
            
        except Exception as e:
            print(f"⚠️ Warning: Could not generate typography for '{segment_text}'. Error: {e}")
                
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
        
        # # PERFECT SYNC DURATION CALCULATION # #
        # Match narration evenly across the generated visual frames
        num_clips = len(video_paths)
        clip_duration = total_audio_duration / num_clips if num_clips > 0 else 3.0
        
        normalized_clips = []
        current_dur = 0
        img_index = 0
        
        print(f"⚡ [PHASE C] Normalizing {num_clips} Base Video Modules to {clip_duration:.2f}s each...")
        
        # 2. DYNAMIC API CLIP SYNC AND NORMALIZATION 
        for vid_data in video_paths:
            raw_vid_path = vid_data['path'] if isinstance(vid_data, dict) else vid_data
            
            active_cut_length = clip_duration
            
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
