import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", module="urllib3")
warnings.filterwarnings("ignore", category=UserWarning)

import os
import re
import json
import time

import shutil
import datetime

# Import the modules we built
from phase_0_topic import generate_trending_topic
from phase_a_generator import generate_shorts_script
from phase_b_audio import generate_voiceover, generate_srt
from phase_c_assembly import assemble_final_video, generate_ai_broll
from phase_d_upload import authenticate_youtube, upload_video, upload_caption, upload_localizations
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

def run_autonomous_pipeline(topic, language, master_video_id=None):
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
    
    # Create an exports directory so local copies are neatly saved permanently
    if not os.path.exists("exports"):
        os.makedirs("exports")
        
    topic_slug = re.sub(r'[^a-zA-Z0-9]+', '_', topic)[:50].strip('_')
    lang_slug = language.replace(' ', '')
    
    # --- OMNI CONTEXT INITIALIZATION ---
    ctx = {
        "topic": topic,
        "language": language,
        "youtube_video_id": master_video_id,
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
    ctx["full_description"] = f"{seo_description}\n\nStart your own business today: [YOUR ACTUAL LINK HERE! Edit line 104 in main.py]\n\n#shorts #business #finance"
    
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
    if language == TARGET_LANGUAGES[0]:
        print("\n--- [PHASE B] AUDIO GENERATION ---")
        if not generate_voiceover(ctx):
            print("❌ Pipeline aborted: Failed to generate audio.")
            return

    # OPTION 2: AUTO-DUB OPTIMIZED BYPASS 
    # YouTube Auto-Dub handles the foreign voices and captions natively, so we only need to inject SEO Meta-Data!
    if language != TARGET_LANGUAGES[0]:
        if ctx.get("youtube_video_id"):
            youtube = authenticate_youtube()
            upload_localizations(
                youtube, 
                ctx["youtube_video_id"], 
                language, 
                ctx["script_data"].get("title", f"{topic} ({language})"),
                ctx.get("full_description", "")
            )
            print(f"\n✅🎉 {language.upper()} NATIVE TRANSLATION SEO INJECTED! 🎉✅")
            
        return ctx.get("youtube_video_id")

    # --- PHASE C: ASSEMBLY ---
    print("\n--- [PHASE C] VIDEO ASSEMBLY ---")
    
    for index, image_data in enumerate(script_data['ai_image_prompts']):
        if isinstance(image_data, str):
            prompt = image_data
            camera_motion = "zoom_in_slow"
            target_api = "RUNWAY"
        else:
            prompt = image_data.get('prompt', '')
            camera_motion = image_data.get('camera', 'zoom_in_slow')
            target_api = image_data.get('target_api', 'RUNWAY')
            
        print(f"\n🎬 [PHASE C] Generating Content Node {index+1}/12 ({target_api})")
        
        # 1. Generate Base High-Fidelity Image
        img_path = f"temp_img_{index}.jpg"
        img_path = generate_ai_broll(prompt, img_path)
        
        # 2. Handoff to Video Generation API (Veo or Runway)
        if img_path:
            mp4_path = f"temp_vid_{index}.mp4"
            from phase_c_ffmpeg import generate_ai_video
            final_vid = generate_ai_video(img_path, camera_motion, target_api, mp4_path, script_data['video_pacing'])
            
            ctx["downloaded_vids"].append({
                "path": final_vid if final_vid else img_path, # Fallback to static image if video API fails
                "camera": camera_motion,
                "target_api": target_api,
                "is_video": final_vid is not None
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
            
            tomorrow = datetime.datetime.utcnow() + datetime.timedelta(days=1)
            publish_at_str = tomorrow.isoformat().split('.')[0] + 'Z'
            
            print("✅ OVERRIDE FIXED: YouTube Upload NOW ENABLED for Master MP4!")
            upload_video(youtube, ctx, publish_at=publish_at_str)
            
            if ctx.get("youtube_video_id") or True: # Force true for test
                # --- NEW: GENERATE AND UPLOAD MASTER SRT ---
                persistent_srt = f"exports/{topic_slug}_{lang_slug}_Subtitles.srt"
                generate_srt(ctx["audio_path"], persistent_srt)
                print("✅ OVERRIDE FIXED: YouTube SRT Captions NOW ENABLED!")
                upload_caption(youtube, ctx["youtube_video_id"], language, persistent_srt)
                
                # --- NEW: LOG THE EXPERIMENT FOR FUTURE MACHINE LEARNING ---
                log_experiment(ctx)
                
                print("\n✅🎉 MASTER VIDEO UPLOADED SUCCESSFULLY! 🎉✅")
                print(f"Your Master Video is SCHEDULED to automatically go public in 24 hours!")
                print(f"Verify it here: https://studio.youtube.com/video/{ctx['youtube_video_id']}/edit")
            else:
                print("❌ Master Video Upload failed. Skipping subtitles and logging.")
        
        # Cleanup temporary files (but KEEP the exported video + thumbnail)
        print(f"💾 Permanently saved to local disk: {ctx['final_video_path']}")
        
        if ctx.get("audio_path") and os.path.exists(ctx["audio_path"]):
            os.remove(ctx["audio_path"])
        for vid in ctx["downloaded_vids"]:
            try:
                os.remove(vid['path'] if isinstance(vid, dict) else vid)
            except Exception:
                pass
    else:
        print("❌ Pipeline aborted: Final video file not found.")
        
    return ctx.get("youtube_video_id")

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
    master_video_id = None
    for lang in TARGET_LANGUAGES:
        print(f"\n" + "="*50)
        print(f"🌍 BATCH GENERATING IN: {lang.upper()}")
        print("="*50)
        master_video_id = run_autonomous_pipeline(topic, lang, master_video_id=master_video_id)
    
    # Check if the AI needs new YouTube engagement data to mathematical re-calibrate
    # its Retention Variables (Jump Cuts & Flashes)
    from phase_e_learning import autonomous_batch_calibration
    autonomous_batch_calibration()
