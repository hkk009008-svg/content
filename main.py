import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", module="urllib3")
warnings.filterwarnings("ignore", category=UserWarning)

import os
import json
import time

# Import the modules we built
from phase_0_topic import generate_trending_topic
from phase_a_generator import generate_shorts_script
from phase_b_audio import generate_voiceover
from phase_c_assembly import assemble_final_video
from phase_d_upload import authenticate_youtube, upload_video
from phase_e_learning import log_experiment, fetch_and_update_analytics

# ==============================================================================
# 🌍 GLOBAL CONFIGURATION: Set your target audience language list here!
# Adding multiple languages here will batch-generate and upload ALL of them!
# Examples: "English", "Hindi", "Mandarin (Simplified)", "Spanish", "Arabic"
# ==============================================================================
TARGET_LANGUAGES = [
    "English", 
    "Mandarin (Simplified)", 
    "Korean", 
    "Japanese", 
    "Spanish (Latin America)", 
    "Hindi"
]

def run_autonomous_pipeline(topic, language):
    # Auto-generate the logo if it doesn't exist yet
    if not os.path.exists("logo.png"):
        print("🎨 [BRANDING] Generating Permanent Channel Logo...")
        import requests, urllib.parse
        new_prompt = "a simple, highly trustworthy and friendly youtube channel logo, clean welcoming aesthetic, warm colors, vector flat icon, high resolution, solid background"
        p = urllib.parse.quote(new_prompt)
        try:
            from dotenv import load_dotenv
            load_dotenv()
            
            fal_key = os.getenv("FAL_KEY")
            img_data = b""
            if fal_key:
                url = "https://fal.run/fal-ai/flux/schnell"
                headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}
                payload = {"prompt": new_prompt, "image_size": "square_hd", "num_inference_steps": 4}
                resp = requests.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    img_data = requests.get(resp.json()["images"][0]["url"]).content
            
            if len(img_data) < 5000:
                img_data = requests.get(f"https://image.pollinations.ai/prompt/{p}?width=400&height=400&nologo=True&model=flux").content
                
            if len(img_data) < 5000:
                print("⚠️ Pollinations blocked logo generation. Using uncompressed proxy placeholder.")
                img_data = requests.get("https://picsum.photos/400/400").content
                
            with open("logo.png", "wb") as f:
                f.write(img_data)
        except Exception as e:
            print(f"Failed to generate logo: {e}")
            
    print(f"🚀 STARTING PIPELINE FOR TOPIC: {topic}\n")
    
    import os, re
    # Create an exports directory so local copies are neatly saved permanently
    if not os.path.exists("exports"):
        os.makedirs("exports")
        
    topic_slug = re.sub(r'[^a-zA-Z0-9]+', '_', topic)[:50].strip('_')
    lang_slug = language.replace(' ', '')
    
    # --- OMNI CONTEXT INITIALIZATION ---
    ctx = {
        "topic": topic,
        "language": language,
        "script_data": {},
        "full_text": "",
        "music_vibe": "",
        "video_pacing": "",
        "audio_path": "",
        "voice_id": "",
        "downloaded_vids": [],
        "final_video_path": f"exports/{topic_slug}_{lang_slug}_Final.mp4",
        "final_thumbnail_path": f"exports/{topic_slug}_{lang_slug}_Thumbnail.jpg",
        "youtube_video_id": None,
        "full_description": ""
    }
    
    # --- PHASE A: SCRIPTING ---
    print("--- [PHASE A] SCRIPT GENERATION ---")
    if not generate_shorts_script(ctx):
        print("❌ Pipeline aborted: Failed to generate script.")
        return
        
    script_data = ctx["script_data"]
    seo_description = script_data.get('youtube_description', f"The insane truth about {topic}.")
    ctx["full_description"] = f"{seo_description}\n\nStart your own business today: [YOUR_AFFILIATE_LINK]\n\n#shorts #business #finance"
    
    # --- UNIFIED STORY TENSION ALGORITHM ---
    tension_map = {"lofi": 0.3, "corporate": 0.6, "suspense": 1.0, "upbeat": 1.5, "aggressive": 2.2}
    pacing_map = {"relaxed": 0.5, "moderate": 1.0, "fast": 1.5}
    
    music_vibe = ctx.get("music_vibe", "suspense")
    video_pacing = ctx.get("video_pacing", "moderate")
    
    base_tension = tension_map.get(music_vibe, 1.0)
    pacing_modifier = pacing_map.get(video_pacing, 1.0)
    story_tension = round(base_tension * pacing_modifier, 2)
    
    ctx["story_tension"] = story_tension
    
    print(f"✅ Script compiled. Length: {len(ctx['full_text'].split())} words.")
    print(f"🎵 Computed Music Vibe: {music_vibe.upper()}")
    print(f"⏱️ Computed Video Pacing: {video_pacing.upper()}")
    print(f"🔥 UNIFIED STORY TENSION: {story_tension}x")

    # --- PHASE B: AUDIO ---
    print("\n--- [PHASE B] AUDIO GENERATION ---")
    if not generate_voiceover(ctx):
        print("❌ Pipeline aborted: Failed to generate audio.")
        return

    # --- PHASE C: ASSEMBLY ---
    print("\n--- [PHASE C] VIDEO ASSEMBLY ---")
    
    # Download 1 AI Image for each detailed Midjourney prompt
    from phase_c_assembly import generate_ai_broll, assemble_final_video
    for index, image_data in enumerate(script_data['ai_image_prompts']):
        if isinstance(image_data, str):
            prompt = image_data
            camera_motion = "zoom_in_slow"
        else:
            prompt = image_data.get('prompt', '')
            camera_motion = image_data.get('camera', 'zoom_in_slow')
            
        img_path = generate_ai_broll(prompt, f"temp_img_{index}.jpg")
        if img_path:
            ctx["downloaded_vids"].append({
                "path": img_path,
                "camera": camera_motion
            })
            
    if not ctx["downloaded_vids"]:
        print("❌ Pipeline aborted: Could not generate any AI B-Roll images.")
        return
        
    # Pre-clean left-over files from previous runs
    for old_file in [ctx["final_video_path"], ctx["final_thumbnail_path"]]:
        if os.path.exists(old_file):
            os.remove(old_file)

    assembly_success = assemble_final_video(ctx)
    if not assembly_success or not os.path.exists(ctx["final_video_path"]):
        print("❌ Pipeline aborted: Video assembly crashed. Aborting upload.")
        return

    # --- PHASE D: UPLOAD ---
    print("\n--- [PHASE D] YOUTUBE UPLOAD ---")
    if os.path.exists(ctx["final_video_path"]):
        # OPTION 2: THE MRBEAST STRATEGY
        # Only physically upload the FIRST requested language to the main channel.
        # Skip uploading the exact same video file 5 times to prevent algorithm suicide.
        if language == TARGET_LANGUAGES[0]:
            youtube = authenticate_youtube()
            
            # --- THE MACHINE LEARNING SYNC ---
            fetch_and_update_analytics(youtube)
            
            import datetime
            tomorrow = datetime.datetime.utcnow() + datetime.timedelta(days=1)
            publish_at_str = tomorrow.isoformat().split('.')[0] + 'Z'
            
            upload_video(youtube, ctx, publish_at=publish_at_str)
            
            # --- NEW: LOG THE EXPERIMENT FOR FUTURE MACHINE LEARNING ---
            log_experiment(ctx)
            
            print("\n✅🎉 MASTER VIDEO UPLOADED SUCCESSFULLY! 🎉✅")
            print(f"Your Master Video is SCHEDULED to automatically go public in 24 hours!")
            print(f"Verify it here: https://studio.youtube.com/video/{ctx['youtube_video_id']}/edit")
        else:
            print(f"\n✅🎉 {language.upper()} DUB GENERATED! 🎉✅")
            print("I skipped API upload to protect the algorithm. Please upload the raw audio to the Master Video's Multi-Language panel!")
        
        # Cleanup temporary files (but KEEP the exported video + thumbnail)
        print(f"💾 Permanently saved to local disk: {ctx['final_video_path']}")
        
        # KEEP the raw MP3 file if it's not the primary language so the user can drag-and-drop it into YouTube Studio
        if language != TARGET_LANGUAGES[0] and ctx.get("audio_path") and os.path.exists(ctx["audio_path"]):
            import shutil
            persistent_audio = f"exports/{topic_slug}_{lang_slug}_Vocals.mp3"
            shutil.copy(ctx["audio_path"], persistent_audio)
            print(f"🔉 Retained raw audio for manual YouTube upload: {persistent_audio}")
            
        if ctx.get("audio_path") and os.path.exists(ctx["audio_path"]):
            os.remove(ctx["audio_path"])
        for vid in ctx["downloaded_vids"]:
            try:
                os.remove(vid['path'] if isinstance(vid, dict) else vid)
            except Exception:
                pass
    else:
        print("❌ Pipeline aborted: Final video file not found.")

if __name__ == "__main__":
    import sys
    
    # Check if a topic was passed as a command line argument
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        # Otherwise, interactively ask the user for a topic
        print("\n" + "="*50)
        topic = input("🎬 Enter a topic (Or press ENTER to Auto-Generate the most lucrative topic!):\n> ")
        print("="*50 + "\n")
        
    # Auto-generate if nothing was entered
    if not topic.strip():
        topic = generate_trending_topic()
        print(f"🔥 Auto-Selected Topic: {topic}\n")
        
    # Run the autonomous pipeline for EVERY target language!
    for lang in TARGET_LANGUAGES:
        print(f"\n" + "="*50)
        print(f"🌍 BATCH GENERATING IN: {lang.upper()}")
        print("="*50)
        run_autonomous_pipeline(topic, lang)
    
    # Check if the AI needs new YouTube engagement data to mathematical re-calibrate
    # its Retention Variables (Jump Cuts & Flashes)
    from phase_e_learning import check_calibration_milestone
    check_calibration_milestone()
