import os
import re
from phase_0_topic import generate_trending_topic
from phase_a_generator import generate_shorts_script
from phase_b_audio import generate_voiceover
from phase_c_assembly import assemble_final_video, generate_ai_broll

def run_local_example():
    print("🤖 Invoking Reverse Psychology Topic Generator...")
    topic = generate_trending_topic()
    print(f"🔥 Auto-Selected Topic for Test: {topic}\n")
    
    if not os.path.exists("exports"):
        os.makedirs("exports")
        
    topic_slug = re.sub(r'[^a-zA-Z0-9]+', '_', topic)[:50].strip('_')
    
    ctx = {
        "topic": topic,
        "language": "English",
        "script_data": {},
        "full_text": "",
        "music_vibe": "",
        "video_pacing": "",
        "audio_path": "",
        "voice_id": "",
        "downloaded_vids": [],
        "final_video_path": f"exports/EXAMPLE_{topic_slug}.mp4",
        "final_thumbnail_path": f"exports/EXAMPLE_{topic_slug}_Thumbnail.jpg",
    }
    
    print("--- [PHASE A] SCRIPT GENERATION ---")
    if not generate_shorts_script(ctx):
        print("❌ Failed script")
        return
        
    print("\n--- [PHASE B] AUDIO GENERATION ---")
    if not generate_voiceover(ctx):
        print("❌ Failed audio")
        return
        
    print("\n--- [PHASE C] VIDEO ASSEMBLY ---")
    script_data = ctx["script_data"]
    for index, image_data in enumerate(script_data['ai_image_prompts']):
        prompt = image_data.get('prompt', '') if isinstance(image_data, dict) else image_data
        camera_motion = image_data.get('camera', 'zoom_in_slow') if isinstance(image_data, dict) else 'zoom_in_slow'
        # Now using the REAL video generation APIs (Runway/Veo) instead of the local fallback!
        target_api = image_data.get('target_api', 'RUNWAY') if isinstance(image_data, dict) else 'RUNWAY' 
        
        print(f"\n🎬 Generating Content Node {index+1}/12")
        img_path = generate_ai_broll(prompt, f"temp_img_{index}.jpg")
        if img_path:
            mp4_path = f"temp_vid_{index}.mp4"
            from phase_c_ffmpeg import generate_ai_video
            final_vid = generate_ai_video(img_path, camera_motion, target_api, mp4_path, script_data['video_pacing'], script_data.get('character_id'))
            
            ctx["downloaded_vids"].append({
                "path": final_vid if final_vid else img_path,
                "camera": camera_motion, "target_api": target_api, "is_video": final_vid is not None
            })
            
    if assemble_final_video(ctx):
        print(f"\n✅ SUCCESS! Local example saved to: {ctx['final_video_path']}")
        print("You can view the video file locally. The script bypassed YouTube upload.")
        
        print("\n🧹 Sweeping all intermediate temporary nodes from the root directory...")
        import glob
        for temp_file in glob.glob("temp_*") + glob.glob("norm_clip_*") + glob.glob("bg_*.mp3"):
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except OSError:
                pass

if __name__ == "__main__":
    print("🚀 STARTING LOCAL TEST PIPELINE...")
    run_local_example()
