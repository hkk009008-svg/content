import os
import json
import time

# Import the modules we built
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

    # Combine text for the voiceover
    full_text = f"{script_data['hook']} {' '.join(script_data['body_paragraphs'])} {script_data['call_to_action']}"
    print(f"✅ Script compiled. Length: {len(full_text.split())} words.")

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
    assemble_final_video(audio_file, downloaded_vids, final_video_path)

    # --- PHASE D: UPLOAD ---
    print("\n--- [PHASE D] YOUTUBE UPLOAD ---")
    if os.path.exists(final_video_path):
        youtube = authenticate_youtube()
        
        # We use the title from Phase A, and the description contains our affiliate link!
        description = f"The insane truth about {topic}.\n\nStart your own business today: [YOUR_AFFILIATE_LINK]\n\n#shorts #business #finance"
        tags = ["business", "finance", "case study", "entrepreneur"]
        
        video_id = upload_video(youtube, final_video_path, script_data['title'], description, tags)
        
        print("\n🎉 PIPELINE COMPLETE! 🎉")
        print(f"Your video is waiting for your approval: https://studio.youtube.com/video/{video_id}/edit")
        
        # Optional: Clean up temporary files
        os.remove(audio_file)
        for vid in downloaded_vids:
            os.remove(vid)
    else:
        print("❌ Pipeline aborted: Final video file not found.")

if __name__ == "__main__":
    # Press run!
    run_autonomous_pipeline("How McDonald's actually makes its money from real estate.")
