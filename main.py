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
from phase_0_director import generate_production_blueprint
from phase_a_generator import generate_shorts_script
from phase_b_audio import generate_voiceover, generate_srt
from phase_c_assembly import assemble_final_video, generate_ai_broll
from phase_c_vision import quality_control_image
from phase_d_upload import authenticate_youtube, upload_video, upload_caption, upload_localizations
from phase_e_learning import log_experiment, fetch_and_update_analytics

# ==============================================================================
# 🌍 GLOBAL CONFIGURATION: Set your target audience language list here!
# Adding multiple languages here will batch-generate and upload ALL of them!
# Examples: "English", "Hindi", "Mandarin (Simplified)", "Spanish", "Arabic"
# ==============================================================================
TARGET_LANGUAGES = [
    "English"
    # "Mandarin (Simplified)", 
    # "Korean", 
    # "Japanese", 
    # "Spanish (Latin America)", 
    # "Hindi"
]

AFFILIATE_LINKS = """
"""

def run_autonomous_pipeline(topic, language, master_video_id=None):
    # Auto-generate the logo if it doesn't exist yet
    if not os.path.exists("logo.png"):
        print("🎨 [BRANDING] Generating Permanent Channel Logo...")
        import requests, urllib.parse
        new_prompt = "a deeply soothing, elegant, and visually comforting youtube channel logo, cosmic awe aesthetic, soft glowing gradients, minimalist vector icon, high resolution, solid dark background"
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
    
    topic_slug = re.sub(r'[^a-zA-Z0-9]+', '_', topic)[:50].strip('_')
    
    export_dir = f"exports/{topic_slug}"
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
        
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
        "final_video_path": f"{export_dir}/video.mp4",
        "final_thumbnail_path": f"{export_dir}/thumbnail.jpg",
        "metadata_path": f"{export_dir}/metadata.txt",
        "full_description": ""
    }
    
    # --- PHASE 0: DIRECTOR BLUEPRINT ---
    if not generate_production_blueprint(ctx):
        print("❌ Pipeline aborted: Failed to generate Master Production Blueprint.")
        return
        
    # --- PHASE A: SCRIPTING ---
    print("\n--- [PHASE A] SCRIPT GENERATION ---")
    if not generate_shorts_script(ctx):
        print("❌ Pipeline aborted: Failed to generate script.")
        return
        
    script_data = ctx["script_data"]
    seo_description = script_data.get('youtube_description', f"The insane truth about {topic}.")
    ctx["full_description"] = f"{seo_description}"
    
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
        
        # 1. Generate Base High-Fidelity Image with Vision QC
        img_path = f"temp_img_{index}.jpg"
        
        max_qc_retries = 3
        hero_subject = ctx.get("production_blueprint", {}).get("hero_subject", "A mysterious subject")
        for qc_attempt in range(max_qc_retries):
            # Pass a modified prompt so Pollinations/Fal generate a different seed on retry
            mod_prompt = prompt if qc_attempt == 0 else f"{prompt} (high definition, ultra realistic, highly detailed variant {qc_attempt})"
            img_path = generate_ai_broll(mod_prompt, img_path)
            
            if img_path and quality_control_image(img_path, hero_subject):
                break
            else:
                print(f"   🔄 [VISION QC] Retrying generation ({qc_attempt+1}/{max_qc_retries})...")
        
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
        return None

    # Cleanup ALL temporary generated files inside the root directory
    import glob
    print(f"💾 Permanently saved to local disk: {ctx['final_video_path']}")
    print("🧹 Sweeping all intermediate temporary nodes from the root directory...")
    
    for temp_file in glob.glob("temp_*") + glob.glob("norm_clip_*") + glob.glob("bg_*.mp3"):
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception:
            pass
            
    # ✅ METADATA EXPORT
    # Write the SEO metadata to a highly readable local txt file
    script_data = ctx.get("script_data", {})
    export_metadata_path = ctx.get("metadata_path", f"exports/{topic_slug}/metadata.txt")
    with open(export_metadata_path, "w", encoding="utf-8") as f:
        f.write(f"=== YOUTUBE UPLOAD METADATA ===\n\n")
        f.write(f"TITLE (Optimized):\n{script_data.get('title', 'Unknown Title')}\n\n")
        f.write("A/B TEST TITLES (For the YouTube 'Test & Compare' Tool):\n")
        for idx, t in enumerate(script_data.get('ab_test_titles', []), 1):
            f.write(f"{idx}. {t}\n")
        f.write(f"\nDESCRIPTION:\n{ctx.get('full_description', '')}\n\n")
        f.write(f"TAGS (Comma separated):\n{', '.join(script_data.get('youtube_tags', []))}\n\n")
        f.write(f"PLAYLIST CATEGORY:\n{script_data.get('playlist_category', '')}\n")
    
    print(f"📝 Metadata saved to: {export_metadata_path}")
            
    return ctx

def upload_pipeline(ctx, offset_hours=0):
    topic = ctx["topic"]
    language = ctx["language"]
    topic_slug = re.sub(r'[^a-zA-Z0-9]+', '_', topic)[:50].strip('_')
    lang_slug = language.replace(' ', '')
    script_data = ctx["script_data"]

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
            # --- SCHEDULED RELEASE WORKFLOW ---
            # Automatically schedule the video to be published x hours in the future
            publish_time = datetime.datetime.utcnow() + datetime.timedelta(hours=offset_hours)
            # YouTube API requires ISO 8601 formatting with a fractional seconds truncation
            publish_at_str = publish_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            
            # --- NEW: A/B TEST EXPORT ---
            ab_test_file = f"exports/{topic_slug}_{lang_slug}_AB_TITLES.txt"
            with open(ab_test_file, "w", encoding="utf-8") as f:
                f.write(f"TEST TITLES FOR TOPIC: {topic}\n\n")
                f.write("Copy and paste these into the YouTube Studio 'Test & Compare' Tool:\n")
                for idx, t in enumerate(script_data.get('ab_test_titles', []), 1):
                    f.write(f"{idx}. {t}\n")
            print(f"📦 A/B Test Titles packaged: {ab_test_file}")
            
            # Compile the final native description with SEO (Spam Footprints Removed)
            base_description = script_data.get('youtube_description', '')
            ctx["full_description"] = f"{base_description}"
            
            print(f"✅ Master MP4 Payload locked. Uploading and scheduling for {offset_hours} hours from now.")
            upload_video(youtube, ctx, publish_at=publish_at_str)
            
            if ctx.get("youtube_video_id") or True: # Force true for test
                # --- NEW: GENERATE AND UPLOAD MASTER SRT ---
                persistent_srt = f"exports/{topic_slug}_{lang_slug}_Subtitles.srt"
                generate_srt(ctx["audio_path"], persistent_srt)
                print("✅ OVERRIDE FIXED: YouTube SRT Captions NOW ENABLED!")
                upload_caption(youtube, ctx["youtube_video_id"], language, persistent_srt)
                
                # --- NEW: LOG THE EXPERIMENT FOR FUTURE MACHINE LEARNING ---
                log_experiment(ctx)
                
                print(f"\n✅🎉 MASTER VIDEO SUCCESSFULLY SCHEDULED FOR RELEASE IN {offset_hours} HOURS! 🎉✅")
                print(f"Review your scheduled video here: https://studio.youtube.com/video/{ctx['youtube_video_id']}/edit")
            else:
                print("❌ Master Video Upload failed. Skipping subtitles and logging.")
    else:
        print("❌ Pipeline aborted: Final video file not found.")
        
    return ctx.get("youtube_video_id")

if __name__ == "__main__":
    import sys
    
    print("\n" + "="*50)
    print("🔥 LAUNCHING LOCAL EXPORT PIPELINE 🔥")
    print("="*50)
    
    # Check if a topic was passed as a command line argument
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        # Generate a single trending topic to perform an isolated run
        topic = generate_trending_topic()
        print(f"✅ Selected Autopilot Topic: {topic}\n")
        
    ctx = run_autonomous_pipeline(topic, "English")
    
    if ctx:
        topic_slug = re.sub(r'[^a-zA-Z0-9]+', '_', topic)[:50].strip('_')
        print("\n" + "="*50)
        print("✅ SUCCESS! PIPELINE COMPLETE.")
        print(f"Your video, thumbnail, and SEO metadata text file have been securely packaged in:")
        print(f"📁 exports/{topic_slug}/")
        print("="*50 + "\n")
    else:
        print("❌ Pipeline failed to complete the export.")
