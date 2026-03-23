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
            "stroke": 12,
            "size": 220
        },
        "corporate": {
            "font": '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            "colors": ["#FACC15"], # Clean Modern Gold for corporate
            "opacity": 1.0,
            "stroke": 12,
            "size": 220
        },
        "lofi": {
            "font": '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            "colors": ["#FFD700"], # Chill Warm Gold for lofi
            "opacity": 1.0,
            "stroke": 12,
            "size": 220
        },
        "upbeat": {
            "font": '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            "colors": ["#FFEA00"], # High-Energy Neon yellow for upbeat
            "opacity": 1.0,
            "stroke": 12,
            "size": 220
        },
        "aggressive": {
            "font": '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            "colors": ["#FFED00"], # Sharp Impact Yellow for aggressive
            "opacity": 1.0,
            "stroke": 12,
            "size": 220
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
            
            # --- MAX RETENTION PATTERN INTERRUPT ---
            # Shock the viewer's retina on the first 3 words to prevent swiping away
            is_hook_word = word_index <= 3
            current_color = "#FF0033" if is_hook_word else color_choice
            
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
    print(f"🎬 [PHASE C] Initializing Assembly Matrix for topic: '{ctx.get('topic')}'")
    
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
        audio_clip = AudioFileClip(audio_path)
        total_audio_duration = audio_clip.duration
        
        # --- 🟢 NEW: SYNCHRONIZING CINEMATIC TEMPO 🟢 ---
        # Analyze the voiceover to extract exact physical sentence lengths for dynamic jump cuts
        print("🧠 [PHASE C] Analyzing Voiceover Tempo via Whisper AI...")
        import whisper
        tempo_model = whisper.load_model("base")
        whisper_result = tempo_model.transcribe(audio_path, word_timestamps=True)
        
        segment_durations = []
        for segment in whisper_result['segments']:
            dur = segment['end'] - segment['start']
            if dur > 1.0: # Skip tiny sub-second glitches
                segment_durations.append(dur)
        
        # 🟢 THE AI VISUAL DIRECTOR 🟢
        # Map Gemini's emotional `music_vibe` directly to physical camera optics, 
        # temporal warp speed, and cinematic color rendering.
        optic_profiles = {
            "suspense": {
                "speed": 0.75, # Buttery slow-mo creeping dread
                "scale": 1.02, # Greatly widened field of view
                "pan": "diagonal_down_right",
                # Highly contrasted shadows with slight dimming to preserve dread
                "color_grade": lambda c: c.fx(vfx.lum_contrast, lum=-10, contrast=0.3, contrast_thr=127).fx(vfx.colorx, 0.85)
            },
            "lofi": {
                "speed": 0.55, # Dreamy hyperslow flow
                "scale": 1.03, 
                "pan": "horizontal_right",
                # Low contrast, soft, faded vintage ambient glow
                "color_grade": lambda c: c.fx(vfx.lum_contrast, lum=15, contrast=-0.2, contrast_thr=127).fx(vfx.colorx, 0.9)
            },
            "corporate": {
                "speed": 0.9, # Stable reality
                "scale": 1.015, 
                "pan": "diagonal_up_left",
                # Complete clarity, pristine professional contrast, strong raw colors
                "color_grade": lambda c: c.fx(vfx.lum_contrast, lum=5, contrast=0.1, contrast_thr=127).fx(vfx.colorx, 1.0)
            },
            "upbeat": {
                "speed": 1.05, # Fast paced hyper-energy
                "scale": 1.02, 
                "pan": "horizontal_left",
                # Extremely vibrant luminance, popping color strength
                "color_grade": lambda c: c.fx(vfx.lum_contrast, lum=20, contrast=0.25, contrast_thr=127).fx(vfx.colorx, 1.1)
            },
            "aggressive": {
                "speed": 1.15, # Violent fast forward
                "scale": 1.04, # Zoomed in chaos
                "pan": "diagonal_down_left",
                # Brutal ultra-high contrast, harsh cinematic lighting, slightly crushed exposure
                "color_grade": lambda c: c.fx(vfx.lum_contrast, lum=-20, contrast=0.5, contrast_thr=127).fx(vfx.colorx, 0.8)
            }
        }
        
        # Load the targeted profile
        profile = optic_profiles.get(music_vibe, optic_profiles["suspense"])

        # --- NEW: SYNERGISTIC HYPER-FAST ADDICTIVENESS CUTS FOR AI IMAGES ---
        # We mathematically link the jump-cut speed to the AI's pacing choice!
        pacing_cut_map = {"fast": 2.8, "moderate": 3.6, "relaxed": 4.8}
        target_cut_length = pacing_cut_map.get(video_pacing, 3.6)
        
        from moviepy.editor import ImageClip
        import random
        
        # Load the dozen AI images and turn them into static video clips
        base_images = []
        for vid_data in video_paths:
            img_path = vid_data['path'] if isinstance(vid_data, dict) else vid_data
            c_motion = vid_data['camera'] if isinstance(vid_data, dict) else "zoom_in_slow"
            try:
                img_clip = ImageClip(img_path).set_duration(target_cut_length)
                img_clip.neural_camera = c_motion
                base_images.append(img_clip)
            except Exception as e:
                print(f"⚠️ Skipping corrupted loaded AI image: {e}")
            
        micro_chunks = []
        current_dur = 0
        img_index = 0
        
        # Snap the physical jump-cuts to the exact length of the spoken sentences!
        while current_dur < total_audio_duration:
            if not base_images:
                break
                
            original_chunk = base_images[img_index % len(base_images)]
            
            # Map the visual cut directly to the spoken sentence length, or fallback to the AI pacing multiplier
            if img_index < len(segment_durations):
                active_cut_length = segment_durations[img_index]
            else:
                active_cut_length = target_cut_length
                
            chunk = original_chunk.set_duration(active_cut_length)
            chunk.neural_camera = getattr(original_chunk, 'neural_camera', 'zoom_in_slow')
            micro_chunks.append(chunk) 
            img_index += 1
            current_dur += active_cut_length
        
        # The Neural Camera Rig
        def apply_neural_camera(c, camera_motion):
            import cv2
            d = c.duration
            def camera_physics(get_frame, t):
                frame = get_frame(t)
                h, w = frame.shape[:2] # Native Fal AI resolution
                
                # --- CUBIC EASING PHYSICS ---
                p = min(t / max(d, 0.01), 1.0)
                eased = (p**2) * (3.0 - 2.0 * p) 
                
                # Default safety
                x1, y1, new_w, new_h = 0, 0, w, h
                
                if camera_motion in ["zoom_in_slow", "zoom_in_fast", "dolly_in_rapid", "static_drone", "zoom_out_slow"]:
                    tension = ctx.get("story_tension", 1.0)
                    if camera_motion == "zoom_in_slow":
                        scale = 1.0 + ((0.15 * tension) * eased) # Increased from 3% to 15% visible zoom
                    elif camera_motion == "zoom_in_fast":
                        scale = 1.0 + ((0.25 * tension) * eased) # Increased from 6% to 25% aggressive zoom
                    elif camera_motion == "dolly_in_rapid":
                        scale = 1.0 + ((0.40 * tension) * eased) # Increased from 10% to 40% rapid zoom
                    elif camera_motion == "zoom_out_slow":
                        scale = 1.15 - ((0.15 * tension) * eased) # Calibrated zoom out range
                    else: # static_drone
                        scale = 1.0 + ((0.02 * tension) * eased)
                        
                    new_w, new_h = int(w/scale), int(h/scale)
                    cx, cy = w//2, h//2
                    x1, y1 = cx - new_w//2, cy - new_h//2
                    
                else: 
                    # Physical Pan
                    scale = 1.20 # Expanded pan room from 6% to 20% for deep, noticeable physical panning
                    new_w, new_h = int(w/scale), int(h/scale)
                    max_x = w - new_w
                    max_y = h - new_h
                    
                    if camera_motion == "pan_right":
                        x1, y1 = int(max_x * eased), max_y // 2
                    elif camera_motion == "pan_left":
                        x1, y1 = int(max_x * (1.0 - eased)), max_y // 2
                    elif camera_motion == "pan_up_crane":
                        x1, y1 = max_x // 2, int(max_y * (1.0 - eased))
                    elif camera_motion == "pan_down":
                        x1, y1 = max_x // 2, int(max_y * eased)
                    else:
                        x1, y1 = max_x // 2, max_y // 2
                        
                x2, y2 = x1 + new_w, y1 + new_h
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                
                cropped = frame[y1:y2, x1:x2]
                # Force strictly 2160x3840 4K for elite render quality
                return cv2.resize(cropped, (2160, 3840), interpolation=cv2.INTER_LINEAR)
                
            return c.fl(camera_physics)
            
        processed_clips = []
        current_dur = 0
        for chunk in micro_chunks:
            if current_dur >= total_audio_duration:
                break
                
            c_motion = getattr(chunk, 'neural_camera', 'zoom_in_slow')
                
            # --- UNIVERSAL CINEMATIC SCHEME NORMALIZER ---
            # Reduced colorx multiplier from 1.25 to 1.10, and gamma from 1.15 to 1.05 to prevent massive cinematic color blowout when stacking 
            clip = chunk.fx(vfx.colorx, 1.10) 
            clip = clip.fx(vfx.gamma_corr, 1.05) 
                
            # Apply dynamic emotional color grade on top of the normalized unified baseline
            clip = profile["color_grade"](clip)
            
            # Apply dynamic time warp physics derived mathematically from Story Tension (Wider Scale)
            base_multiplier = max(0.8, min(1.5, 0.85 + (0.15 * ctx.get("story_tension", 1.0))))
            clip = clip.fx(vfx.speedx, profile["speed"] * base_multiplier)
            
            # If this cut exceeds what we need to finish the video, crop the end of it
            time_needed = total_audio_duration - current_dur
            if clip.duration > time_needed:
                clip = clip.subclip(0, time_needed)
                
            # --- PSYCHOLOGICALLY SYNCED CAMERA PHYSICS ---
            clip = apply_neural_camera(clip, c_motion)
            processed_clips.append(clip)
            current_dur += clip.duration
        
        # Stitch them all together
        final_video = concatenate_videoclips(processed_clips, method="compose")
        
        # --- NEW: PSYCHOLOGICAL COMPLETION ANXIETY PROGRESS BAR ---
        # A Neon Red bar that slowly fills the bottom of the screen to force completions
        def make_progress_bar_frame(t):
            import numpy as np
            progress = min(max(t / total_audio_duration, 0.0), 1.0)
            frame = np.zeros((15, 2160, 3), dtype=np.uint8) # 15 pixels tall, 4K wide
            pixel_width = int(2160 * progress)
            if pixel_width > 0:
                frame[:, :pixel_width] = [255, 0, 51] # Aggressive Neon Red
            return frame
            
        from moviepy.video.VideoClip import VideoClip
        progress_bar = VideoClip(make_progress_bar_frame, duration=total_audio_duration)
        progress_bar = progress_bar.set_position(('center', 'bottom'))
        
        # Add the progress bar to the video
        final_video = CompositeVideoClip([final_video, progress_bar])
        
        # 🟢 NEW: BURN IN THE AUTHORITY BANNER 🟢
        final_video = add_top_banner(final_video, topic_text)
        
        # 🟢 NEW: BURN IN THE CAPTIONS HERE 🟢
        final_video = add_dynamic_captions(audio_path, final_video, music_vibe, pre_transcribed_result=whisper_result)
        
        # --- Add Background Music ---
        bg_music_path = f"bg_{music_vibe}.mp3"
        
        # We assign different SoundHelix URLs for each vibe (in reality this could be an internal folder of your own MP3s)
        music_library = {
            "suspense": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
            "corporate": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
            "lofi": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
            "upbeat": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
            "aggressive": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3"
        }
        music_url = music_library.get(music_vibe, music_library["suspense"])
        
        if not os.path.exists(bg_music_path):
            print(f"🎵 Downloading {music_vibe.upper()} royalty-free background music...")
            import urllib.request
            urllib.request.urlretrieve(music_url, bg_music_path)
            
        # --- Premium Podcast-Level Sound Experience Mixing ---
        # 1. Boost the main voiceover by 50% so it punches heavily through mobile phone speakers
        audio_clip = audio_clip.volumex(1.5)

        # 2. Heavily duck the background music to 7% (down from 12%) so it's purely psychological ambient noise, never competing with the voice
        bg_clip = AudioFileClip(bg_music_path).volumex(0.07) 
        
        # Loop music if it's shorter than the voiceover
        from moviepy.audio.fx.all import audio_loop, audio_fadein, audio_fadeout
        if bg_clip.duration < audio_clip.duration:
            bg_clip = audio_loop(bg_clip, duration=audio_clip.duration)
        else:
            bg_clip = bg_clip.subclip(0, audio_clip.duration)
            
        # 3. Apply smooth fade-in (0.5s) to the music so the video feels like a professional theater cut.
        # CRITICAL: We explicitly DO NOT apply a fade-out. The music must abruptly cut at 100% volume so that when the video infinitely loops back to the start, the audio flawlessly bridges the gap.
        bg_clip = bg_clip.fx(audio_fadein, 0.5)
            
        # --- NEW: SYNTHESIZE CINEMATIC BASS DROP ---
        sfx_path = "bass_drop.wav"
        if not os.path.exists(sfx_path):
            print("🔊 [PHASE C] Synthesizing 80Hz Cinematic Bass Drop...")
            import wave, struct, math
            sample_rate = 44100
            duration = 1.5
            wavef = wave.open(sfx_path, 'w')
            wavef.setnchannels(1) # mono
            wavef.setsampwidth(2) # 16-bit
            wavef.setframerate(sample_rate)
            
            for i in range(int(duration * sample_rate)):
                t = float(i) / sample_rate
                # 80Hz sine wave sweeping down heavily with exponential decay
                freq = 80.0 - (50.0 * t / duration)
                val = 32767.0 * math.sin(2.0 * math.pi * freq * t) * math.exp(-t * 4.0)
                data = struct.pack('<h', int(val))
                wavef.writeframesraw(data)
            wavef.close()
            
        # The Red Hook Flashes exactly at t=0.0 where the voiceover starts
        sfx_clip = AudioFileClip(sfx_path).volumex(1.8)
            
        from moviepy.audio.AudioClip import CompositeAudioClip
        final_audio = CompositeAudioClip([bg_clip, audio_clip, sfx_clip])
        
        # Attach the mixed voiceover + music and lock the duration to prevent infinite rendering loops
        final_video = final_video.set_audio(final_audio).set_duration(total_audio_duration)
        
        # 🟢 NEW: BURN IN THE CHANNEL LOGO WATERMARK 🟢
        if os.path.exists("logo.png"):
            print("🎨 Adding Channel Watermark Logo...")
            from moviepy.editor import ImageClip
            # Load the AI logo, strip the black background completely using color masking thresholds,
            # scale it down significantly for an elegant clean look, and permanently pin it inside the right side of the Top Banner
            logo_clip = ImageClip("logo.png").resize(width=100).fx(vfx.mask_color, color=[0, 0, 0], thr=35, s=15).set_position((2160 - 150, 100)).set_duration(total_audio_duration).set_opacity(1.0)
            final_video = CompositeVideoClip([final_video, logo_clip])
            
        # --- NEW: Thumbnail Extraction ---
        thumbnail_path = ctx.get("final_thumbnail_path", "thumbnail.jpg")
        print(f"📸 Extracting high-impact thumbnail frame to {thumbnail_path}...")
        # Save the frame at 0.5 seconds where the yellow hook caption is perfectly visible
        import PIL.Image
        frame_array = final_video.get_frame(0.5)
        thumbnail_img = PIL.Image.fromarray(frame_array).convert("RGB")
        thumbnail_img.save(thumbnail_path, "JPEG")
        
        print("⏳ Rendering MP4... (This will take a minute depending on your Mac's CPU/GPU)")
        
        # Write the final 4K file
        final_video.write_videofile(
            output_filename, 
            fps=30, 
            codec="libx264", 
            audio_codec="aac",
            bitrate="20000k", # Extremely high ceiling bitrate for 4K quality
            logger=None # Keeps your terminal output clean
        )
        print(f"\n✅ Success! Final video rendered as: {output_filename}")
        return True
        
    except Exception as e:
        print(f"\n❌ Error during video assembly: {e}")
        return False

# Optional testing block
if __name__ == "__main__":
    print("Run this through main.py to test the full pipeline!")
