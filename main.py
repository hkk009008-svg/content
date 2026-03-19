import os
import json
import time

# Import the modules we built
from phase_0_topic import generate_trending_topic
from phase_a_generator import generate_shorts_script
from phase_b_audio import generate_voiceover
from phase_c_assembly import download_pexels_video, assemble_final_video
from phase_d_upload import authenticate_youtube, upload_video

def run_autonomous_pipeline(topic):
    print(f"🚀 STARTING PIPELINE FOR TOPIC: {topic}\n")
    
    # --- PHASE A: SCRIPTING ---
    print("--- [PHASE A] SCRIPT GENERATION ---")
    script_data = generate_shorts_script(topic)
    
    if not script_data:
        print("❌ Pipeline aborted: Failed to generate script.")
        return
        
    seo_description = script_data.get('youtube_description', f"The insane truth about {topic}.")
    full_description = f"{seo_description}\n\nStart your own business today: [YOUR_AFFILIATE_LINK]\n\n#shorts #business #finance"
    seo_tags = script_data.get('youtube_tags', ["business", "finance", "case study", "entrepreneur"])

    # Combine text for the voiceover
    full_text = f"{script_data['hook']} {' '.join(script_data['body_paragraphs'])} {script_data['call_to_action']}"
    print(f"✅ Script compiled. Length: {len(full_text.split())} words.")
    
    music_vibe = script_data.get('music_vibe', 'suspense')
    print(f"🎵 Computed Music Vibe: {music_vibe.upper()}")

    # --- PHASE B: AUDIO ---
    print("\n--- [PHASE B] AUDIO GENERATION ---")
    audio_file = generate_voiceover(full_text, "temp_voiceover.mp3")
    
    if not audio_file:
        print("❌ Pipeline aborted: Failed to generate audio.")
        return

    # --- PHASE C: ASSEMBLY ---
    print("\n--- [PHASE C] VIDEO ASSEMBLY ---")
    downloaded_vids = []
    
    # Download 1 video for each keyword
    for index, keyword in enumerate(script_data['pexels_search_keywords']):
        # Remember our trick: clean the keyword of specific brands if needed
        clean_keyword = keyword.replace("mcdonalds", "fast food building")
        
        vid_path = download_pexels_video(clean_keyword, f"temp_vid_{index}.mp4")
        if vid_path:
            downloaded_vids.append(vid_path)
            
    if not downloaded_vids:
        print("❌ Pipeline aborted: Could not download any background footage.")
        return
        
    final_video_path = "FINAL_READY_TO_UPLOAD.mp4"
    final_thumbnail_path = "thumbnail.png"
    
    # Pre-clean left-over files from previous runs to prevent uploading wrong videos if a crash occurs
    for old_file in [final_video_path, final_thumbnail_path]:
        if os.path.exists(old_file):
            os.remove(old_file)

    assembly_success = assemble_final_video(audio_file, downloaded_vids, final_video_path, music_vibe=music_vibe, topic_text=topic)
    if not assembly_success or not os.path.exists(final_video_path):
        print("❌ Pipeline aborted: Video assembly crashed. Aborting upload.")
        return

    # --- PHASE D: UPLOAD ---
    print("\n--- [PHASE D] YOUTUBE UPLOAD ---")
    if os.path.exists(final_video_path):
        youtube = authenticate_youtube()
        
        import datetime
        tomorrow = datetime.datetime.utcnow() + datetime.timedelta(days=1)
        # Format as ISO 8601 string expected by YouTube API (e.g., 2026-03-20T15:00:00Z)
        publish_at_str = tomorrow.isoformat().split('.')[0] + 'Z'
        
        playlist_name = script_data.get('playlist_category', "Digital Case Studies")
        video_id = upload_video(youtube, final_video_path, script_data['title'], full_description, seo_tags, final_thumbnail_path, publish_at=publish_at_str, playlist_name=playlist_name)
        
        print("\n🎉 PIPELINE COMPLETE! 🎉")
        print(f"Your video is completely done and SCHEDULED to automatically go public in exactly 24 hours!")
        print(f"Verify it here: https://studio.youtube.com/video/{video_id}/edit")
        
        # Cleanup ALL temporary files so nothing leaks into the next run
        os.remove(audio_file)
        if os.path.exists(final_thumbnail_path):
            os.remove(final_thumbnail_path)
        if os.path.exists(final_video_path):
            os.remove(final_video_path)
        for vid in downloaded_vids:
            os.remove(vid)
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
        
    run_autonomous_pipeline(topic)
