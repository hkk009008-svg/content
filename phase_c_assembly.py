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
            
            # Find the best HD link (1920x1080 usually)
            hd_file = next((file for file in video_files if file["quality"] == "hd"), video_files[0])
            video_url = hd_file["link"]
            
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
    
    # Standardize all clips to 1080x1920 to prevent crashes during concatenation
    return clip.resize((1080, 1920))

def add_dynamic_captions(audio_path, video_clip):
    """
    Uses local Whisper AI to transcribe audio and burn word-by-word 
    captions onto the MoviePy video clip.
    """
    print("🧠 [PHASE C] Loading Whisper AI model (this takes a few seconds)...")
    # 'base' is fast and highly accurate for English.
    model = whisper.load_model("base") 
    
    print("📝 [PHASE C] Transcribing audio and extracting word timestamps...")
    # word_timestamps=True is the secret to Hormozi-style pop-up captions
    result = model.transcribe(audio_path, word_timestamps=True)
    
    text_clips = []
    
    # Loop through the transcription data
    for segment in result['segments']:
        for word_info in segment['words']:
            word_text = word_info['word'].strip().upper() # ALL CAPS for visual impact
            start_time = word_info['start']
            end_time = word_info['end']
            
            # Create a bold graphic for each word
            try:
                txt_clip = TextClip(
                    word_text, 
                    fontsize=105, 
                    color='#FEFA00', 
                    font='/System/Library/Fonts/Supplemental/Arial Bold.ttf', # Direct path bypasses Mac font cache bugs
                    stroke_color='black',
                    stroke_width=5,
                    method='caption',
                    size=(900, None) # Wraps text if it gets too long
                )
                
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

def assemble_final_video(audio_path, video_paths, output_filename="FINAL_READY_TO_UPLOAD.mp4"):
    """Stitches the cropped videos together and syncs the ElevenLabs audio."""
    print("\n🎬 [PHASE C] Assembling the final video cut...")
    
    try:
        audio_clip = AudioFileClip(audio_path)
        total_audio_duration = audio_clip.duration
        
        # Calculate exactly how long each video clip should play
        time_per_clip = total_audio_duration / len(video_paths)
        
        processed_clips = []
        for vid_path in video_paths:
            clip = VideoFileClip(vid_path)
            
            # Darken the background slightly by 30% so yellow text pops
            clip = clip.fx(vfx.colorx, 0.7)
            
            # Trim if too long, loop if too short
            if clip.duration > time_per_clip:
                clip = clip.subclip(0, time_per_clip)
            else:
                clip = clip.fx(vfx.loop, duration=time_per_clip)
                
            # Force into the vertical Shorts format
            clip = crop_to_vertical(clip)
            processed_clips.append(clip)
        
        # Stitch them all together
        final_video = concatenate_videoclips(processed_clips, method="compose")
        
        # 🟢 NEW: BURN IN THE CAPTIONS HERE 🟢
        final_video = add_dynamic_captions(audio_path, final_video)
        
        # --- Add Background Music ---
        bg_music_path = "bg_music.mp3"
        if not os.path.exists(bg_music_path):
            print("🎵 Downloading royalty-free suspense background music...")
            import urllib.request
            # A reliable, intense royalty-free looping background track
            urllib.request.urlretrieve("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3", bg_music_path)
            
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
        
        # Write the final file
        final_video.write_videofile(
            output_filename, 
            fps=30, 
            codec="libx264", 
            audio_codec="aac", 
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
