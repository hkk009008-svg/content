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
    """Adds a persistent 'Case File' authority banner to the top of the video."""
    from moviepy.editor import ColorClip
    
    # Format the text so it's not obnoxiously long
    clean_topic = topic_text[:35] + "..." if len(topic_text) > 35 else topic_text
    banner_str = f"[ CASE FILE: {clean_topic.upper()} ]"
    
    # Transparent Black Bar at the top (Scaled for 4K)
    banner_bg = ColorClip(size=(2160, 260), color=(0, 0, 0)).set_opacity(0.75).set_position(('center', 'top')).set_duration(video_clip.duration)
    
    # The text inside the banner (Scaled for 4K)
    try:
        banner_txt = TextClip(
            banner_str, 
            fontsize=80, 
            color='white', 
            font='/System/Library/Fonts/Supplemental/Courier New Bold.ttf' # Classic typewriter case file font
        ).set_position(('center', 90)).set_duration(video_clip.duration)
    except:
        # Fallback to Arial if Courier is missing
        banner_txt = TextClip(banner_str, fontsize=80, color='white', font='/System/Library/Fonts/Supplemental/Arial Bold.ttf').set_position(('center', 90)).set_duration(video_clip.duration)
    
    return CompositeVideoClip([video_clip, banner_bg, banner_txt])

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
            "colors": ["#FFFFFF", "#FF0000"], # White and Red strobe
            "opacity": 0.85,
            "stroke": 4,
            "size": 170
        },
        "corporate": {
            "font": '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            "colors": ["#FEFA00"], # Solid static Hormozi Yellow
            "opacity": 1.0,
            "stroke": 10,
            "size": 210
        },
        "lofi": {
            "font": '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            "colors": ["#FFFFFF"], # Solid Soft White
            "opacity": 0.80,
            "stroke": 4,
            "size": 160
        },
        "upbeat": {
            "font": '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            "colors": ["#FEFA00", "#00FFFF"], # Exuberant Yellow and Cyan flash
            "opacity": 1.0,
            "stroke": 8,
            "size": 200
        },
        "aggressive": {
            "font": '/System/Library/Fonts/Supplemental/Courier New Bold.ttf',
            "colors": ["#FF0000", "#FFFFFF"], # Intense Blood Red lead strobe
            "opacity": 0.95,
            "stroke": 6,
            "size": 190
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
            try:
                txt_clip = TextClip(
                    word_text, 
                    fontsize=style["size"],
                    color=color_choice, 
                    font=style["font"], 
                    stroke_color='black',
                    stroke_width=style["stroke"],
                    method='caption',
                    size=(1800, None) # 4K boundary wrapper
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

def assemble_final_video(audio_path, video_paths, output_filename="FINAL_READY_TO_UPLOAD.mp4", music_vibe="suspense", topic_text="CLASSIFIED"):
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
                "speed": 0.8, # Buttery slow-mo creeping dread
                "scale": 1.05, 
                "pan": "diagonal_down_right",
                "color_grade": lambda c: c.fx(vfx.blackwhite).fx(vfx.colorx, 0.6) # Pitch black high contrast
            },
            "lofi": {
                "speed": 0.6, # Dreamy hyperslow flow
                "scale": 1.07, 
                "pan": "horizontal_right",
                "color_grade": lambda c: c.fx(vfx.colorx, 0.55) # Dimmed but keeps raw colors intact
            },
            "corporate": {
                "speed": 1.0, # Stable reality
                "scale": 1.04, 
                "pan": "diagonal_up_left",
                "color_grade": lambda c: c.fx(vfx.colorx, 0.85) # Clean documentary dimming
            },
            "upbeat": {
                "speed": 1.15, # Fast paced hyper-energy
                "scale": 1.04, 
                "pan": "horizontal_left",
                "color_grade": lambda c: c.fx(vfx.colorx, 0.95) # Bright and explosive
            },
            "aggressive": {
                "speed": 1.3, # Violent fast forward
                "scale": 1.15, # Massive pan distance mapping for frantic camera sweep
                "pan": "diagonal_down_left",
                "color_grade": lambda c: c.fx(vfx.blackwhite).fx(vfx.colorx, 0.5) # Grim and striking
            }
        }
        
        # Load the targeted profile
        profile = optic_profiles.get(music_vibe, optic_profiles["suspense"])

        processed_clips = []
        for vid_path in video_paths:
            clip = VideoFileClip(vid_path)
            
            # Apply dynamic emotional color grade
            clip = profile["color_grade"](clip)
            
            # Apply dynamic time warp physics
            clip = clip.fx(vfx.speedx, profile["speed"])
            
            # Trim if too long, loop if too short
            if clip.duration > time_per_clip:
                clip = clip.subclip(0, time_per_clip)
            else:
                clip = clip.fx(vfx.loop, duration=time_per_clip)
                
            # Enforce strict 4K vertical cinema resolution (2160x3840) to prevent render crashes
            clip = crop_to_vertical(clip)
            
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
                
            clip = add_cinematic_drift(clip, profile["scale"], profile["pan"])
            processed_clips.append(clip)
        
        # Stitch them all together
        final_video = concatenate_videoclips(processed_clips, method="compose")
        
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
            
        bg_clip = AudioFileClip(bg_music_path).volumex(0.12) # 12% volume mix
        
        # Loop music if it's shorter than the voiceover
        from moviepy.audio.fx.all import audio_loop
        if bg_clip.duration < audio_clip.duration:
            bg_clip = audio_loop(bg_clip, duration=audio_clip.duration)
        else:
            bg_clip = bg_clip.subclip(0, audio_clip.duration)
            
        from moviepy.audio.AudioClip import CompositeAudioClip
        final_audio = CompositeAudioClip([bg_clip, audio_clip])
        
        # Attach the mixed voiceover + music and lock the duration to prevent infinite rendering loops
        final_video = final_video.set_audio(final_audio).set_duration(total_audio_duration)
        
        # --- NEW: Thumbnail Extraction ---
        thumbnail_path = "thumbnail.png"
        print("📸 Extracting high-impact thumbnail frame...")
        # Save the frame at 0.5 seconds where the yellow hook caption is perfectly visible
        final_video.save_frame(thumbnail_path, t=0.5)
        
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
