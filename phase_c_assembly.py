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

def download_pexels_video(keyword, output_filename):
    """Searches Pexels for a keyword and downloads the highest quality HD video."""
    print(f"🔍 [PHASE C] Searching Pexels for: '{keyword}'...")
    
    if not PEXELS_API_KEY:
        print("❌ Error: PEXELS_API_KEY not found in .env file.")
        return None

    headers = {"Authorization": PEXELS_API_KEY}
    # Fetch top 15 landscape videos to choose randomly to avoid the exact same footage every time
    url = f"https://api.pexels.com/videos/search?query={keyword}&per_page=15&orientation=landscape"
    
    try:
        response = requests.get(url, headers=headers).json()
        
        if "videos" in response and len(response["videos"]) > 0:
            import random
            random_video = random.choice(response["videos"])
            video_files = random_video["video_files"]
            
            # Grab raw 4K UHD if available, fallback to 1080p HD
            best_file = next((file for file in video_files if file["quality"] == "uhd"), None)
            if not best_file:
                best_file = next((file for file in video_files if file["quality"] == "hd"), video_files[0])
            video_url = best_file["link"]
            
            print(f"⬇️ Downloading background footage for '{keyword}'...")
            vid_data = requests.get(video_url).content
            with open(output_filename, 'wb') as handler:
                handler.write(vid_data)
                
            return output_filename
        else:
            print(f"⚠️ No video found on Pexels for keyword: '{keyword}'")
            return None
            
    except Exception as e:
        print(f"❌ Error downloading from Pexels: {e}")
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
    banner_bg = ColorClip(size=(2160, 360), color=(10, 10, 12)).set_opacity(0.95).set_position(('center', 'top')).set_duration(video_clip.duration)
    
    # 2. Modern Brand Accent Line (Neon Yellow Underline)
    accent_line = ColorClip(size=(2160, 10), color=(255, 234, 0)).set_position(('center', 360)).set_duration(video_clip.duration)
    
    # 3. Small "Authority" Badge Text
    try:
        badge_txt = TextClip(
            "// DECLASSIFIED CASE STUDY", 
            fontsize=40, 
            color='#FFEA00', # Neon Yellow
            font='/System/Library/Fonts/Supplemental/Courier New Bold.ttf'
        ).set_position((100, 70)).set_duration(video_clip.duration)
    except:
        badge_txt = TextClip("// DECLASSIFIED CASE STUDY", fontsize=40, color='#FFEA00').set_position((100, 70)).set_duration(video_clip.duration)
        
    # 4. Main Title properly word-wrapped inside a 1900px boundary so it NEVER cuts off
    try:
        main_txt = TextClip(
            topic_text.upper(), 
            fontsize=80, 
            color='white', 
            font='/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            align='West',
            method='caption',
            size=(1900, None) # This tells MoviePy to auto word-wrap within 1900 pixels
        ).set_position((100, 150)).set_duration(video_clip.duration)
    except:
        main_txt = TextClip(topic_text.upper(), fontsize=80, color='white', align='West', method='caption', size=(1900, None)).set_position((100, 150)).set_duration(video_clip.duration)
    
    return CompositeVideoClip([video_clip, banner_bg, accent_line, badge_txt, main_txt])

def add_dynamic_captions(audio_path, video_clip, music_vibe="suspense"):
    """
    Uses local Whisper AI to transcribe audio and burn word-by-word 
    captions onto the MoviePy video clip with dynamically mapped styles.
    """
    print("🧠 [PHASE C] Loading Whisper AI model (this takes a few seconds)...")
    # 'base' is fast and highly accurate for English.
    model = whisper.load_model("base") 
    
    print("📝 [PHASE C] Transcribing audio and extracting word timestamps...")
    # word_timestamps=True is the secret to Hormozi-style pop-up captions
    result = model.transcribe(audio_path, word_timestamps=True)
    
    text_clips = []
    word_index = 0
    
    # Define aesthetic mapping based on Gemini's emotional mood analysis (All dimensions scaled 2x for 4K geometry)
    vibe_styles = {
        "suspense": {
            "font": '/System/Library/Fonts/Supplemental/Courier New Bold.ttf',
            "colors": ["#E2FF3D"], # Acid/Cyber Yellow for suspense
            "opacity": 1.0,
            "stroke": 12,
            "size": 220
        },
        "corporate": {
            "font": '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            "colors": ["#FACC15"], # Clean Modern Gold for corporate
            "opacity": 1.0,
            "stroke": 12,
            "size": 220
        },
        "lofi": {
            "font": '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            "colors": ["#FFD700"], # Chill Warm Gold for lofi
            "opacity": 1.0,
            "stroke": 12,
            "size": 220
        },
        "upbeat": {
            "font": '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            "colors": ["#FFEA00"], # High-Energy Neon yellow for upbeat
            "opacity": 1.0,
            "stroke": 12,
            "size": 220
        },
        "aggressive": {
            "font": '/System/Library/Fonts/Supplemental/Courier New Bold.ttf',
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
                current_size = int(base_size * (8.0 / len(word_text)))
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

def assemble_final_video(audio_path, video_paths, output_filename="FINAL_READY_TO_UPLOAD.mp4", music_vibe="suspense", topic_text="CLASSIFIED", video_pacing="moderate"):
    """Stitches the cropped videos together and syncs the ElevenLabs audio."""
    print("\n🎬 [PHASE C] Assembling the final video cut...")
    
    try:
        audio_clip = AudioFileClip(audio_path)
        total_audio_duration = audio_clip.duration
        
        # Calculate exactly how long each video clip should play
        time_per_clip = total_audio_duration / len(video_paths)
        
        # 🟢 THE AI VISUAL DIRECTOR 🟢
        # Map Gemini's emotional `music_vibe` directly to physical camera optics, 
        # temporal warp speed, and cinematic color rendering.
        optic_profiles = {
            "suspense": {
                "speed": 0.75, # Buttery slow-mo creeping dread
                "scale": 1.05, 
                "pan": "diagonal_down_right",
                "color_grade": lambda c: c.fx(vfx.blackwhite).fx(vfx.colorx, 0.6) # Pitch black high contrast
            },
            "lofi": {
                "speed": 0.55, # Dreamy hyperslow flow
                "scale": 1.07, 
                "pan": "horizontal_right",
                "color_grade": lambda c: c.fx(vfx.colorx, 0.55) # Dimmed but keeps raw colors intact
            },
            "corporate": {
                "speed": 0.9, # Stable reality
                "scale": 1.04, 
                "pan": "diagonal_up_left",
                "color_grade": lambda c: c.fx(vfx.colorx, 0.85) # Clean documentary dimming
            },
            "upbeat": {
                "speed": 1.05, # Fast paced hyper-energy
                "scale": 1.04, 
                "pan": "horizontal_left",
                "color_grade": lambda c: c.fx(vfx.colorx, 0.95) # Bright and explosive
            },
            "aggressive": {
                "speed": 1.15, # Violent fast forward
                "scale": 1.15, # Massive pan distance mapping for frantic camera sweep
                "pan": "diagonal_down_left",
                "color_grade": lambda c: c.fx(vfx.blackwhite).fx(vfx.colorx, 0.5) # Grim and striking
            }
        }
        
        # Load the targeted profile
        profile = optic_profiles.get(music_vibe, optic_profiles["suspense"])

        # --- NEW: SYNERGISTIC HYPER-FAST ADDICTIVENESS CUTS ---
        # Instead of playing one long clip, we mathematically link the jump-cut speed to the AI's pacing choice!
        # This violently forces a visual scene change constantly, resetting the viewer's attention span.
        pacing_cut_map = {"fast": 1.5, "moderate": 2.2, "relaxed": 3.0}
        target_cut_length = pacing_cut_map.get(video_pacing, 2.0)
        
        micro_chunks = []
        import random
        
        for vid_path in video_paths:
            raw_clip = VideoFileClip(vid_path)
            # Chop it into 2-second pieces
            for start_pos in range(0, int(raw_clip.duration), int(target_cut_length)):
                end_pos = min(start_pos + target_cut_length, raw_clip.duration)
                if end_pos - start_pos >= 1.0: # Only keep usable chunks
                    micro_chunks.append(raw_clip.subclip(start_pos, end_pos))
                    
        # Shuffle them so it feels completely chaotic and unpredictable
        random.shuffle(micro_chunks)
        
        # The Digital Camera Pan Rig
        def add_cinematic_drift(c, p_scale, p_dir):
            w_target, h_target = 2160, 3840
            c_oversized = c.resize(p_scale)
            w_over, h_over = c_oversized.size
            max_x = int(w_over - w_target)
            max_y = int(h_over - h_target)
            d = c.duration
            def drift_crop(get_frame, t):
                frame = get_frame(t)
                progress = t / d 
                if p_dir == "diagonal_down_right":
                    x1, y1 = int(max_x * progress), int(max_y * progress)
                elif p_dir == "diagonal_up_left":
                    x1, y1 = int(max_x * (1.0 - progress)), int(max_y * (1.0 - progress))
                elif p_dir == "horizontal_right":
                    x1, y1 = int(max_x * progress), int(max_y / 2)
                elif p_dir == "horizontal_left":
                    x1, y1 = int(max_x * (1.0 - progress)), int(max_y / 2)
                elif p_dir == "diagonal_down_left":
                    x1, y1 = int(max_x * (1.0 - progress)), int(max_y * progress)
                else:
                    x1, y1 = int(max_x * progress), int(max_y * progress)
                return frame[y1:y1+h_target, x1:x1+w_target]
            return c_oversized.fl(drift_crop)
            
        processed_clips = []
        current_dur = 0
        for chunk in micro_chunks:
            if current_dur >= total_audio_duration:
                break
                
            # Apply dynamic emotional color grade
            clip = profile["color_grade"](chunk)
            
            # Apply dynamic time warp physics based on AI video pacing multiplier
            pacing_mult = {"fast": 1.15, "moderate": 1.0, "relaxed": 0.85}.get(video_pacing, 1.0)
            clip = clip.fx(vfx.speedx, profile["speed"] * pacing_mult)
            
            # If this cut exceeds what we need to finish the video, crop the end of it
            time_needed = total_audio_duration - current_dur
            if clip.duration > time_needed:
                clip = clip.subclip(0, time_needed)
                
            # Enforce strict 4K vertical cinema resolution (2160x3840) to prevent render crashes
            clip = crop_to_vertical(clip)
            
            clip = add_cinematic_drift(clip, profile["scale"], profile["pan"])
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
        final_video = add_dynamic_captions(audio_path, final_video, music_vibe)
        
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
            
        # 3. Apply smooth fade-in (0.5s) and fade-out (2.0s) to the music so the video feels like a professional theater cut rather than harshly clipping on loop
        bg_clip = bg_clip.fx(audio_fadein, 0.5).fx(audio_fadeout, 2.0)
            
        from moviepy.audio.AudioClip import CompositeAudioClip
        final_audio = CompositeAudioClip([bg_clip, audio_clip])
        
        # Attach the mixed voiceover + music and lock the duration to prevent infinite rendering loops
        final_video = final_video.set_audio(final_audio).set_duration(total_audio_duration)
        
        # --- NEW: Thumbnail Extraction ---
        thumbnail_path = "thumbnail.jpg"
        print("📸 Extracting high-impact thumbnail frame...")
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
