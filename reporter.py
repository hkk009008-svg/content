import os
import glob
import time
import json

def generate_report():
    print("==================================================")
    print("📊 CINEMATIC VFX PIPELINE REPORTER")
    print("==================================================")
    
    # Check current directory for temp files
    foley_files = glob.glob("temp_foley_*.mp3")
    img_files = glob.glob("temp_img_*.jpg")
    vid_files = glob.glob("temp_vid_*.mp4")
    
    print(f"\n📂 Live Asset Tracking Status:")
    print(f"   ↳ Foley Audio Tracks:  {len(foley_files)} / 21")
    print(f"   ↳ Reference Images:    {len(img_files)} / 20")
    print(f"   ↳ Final Video Clips:   {len(vid_files)} / 20")
    
    # 2. Check for active stalls
    if 0 < len(vid_files) < 20:
        latest_vid = max(vid_files, key=os.path.getmtime)
        stall_time = time.time() - os.path.getmtime(latest_vid)
        minutes_stalled = stall_time / 60
        
        print(f"\n⏱️ Time since '{latest_vid}' finished generating: {minutes_stalled:.1f} minutes")
        if minutes_stalled > 10.0:
            print("   ⚠️ SYSTEM ALERT: The pipeline is currently frozen or wrestling with violent API rejections!")
            print("   💡 PRO TIP: If you see the Kling error above, hit Ctrl+C and restart to flush the ghost connection.")
        else:
            print("   ✅ SYSTEM STATUS: Actively synthesizing latent structures...")
            
    # 3. Harvest crash report if pipeline failed gracefully
    if os.path.exists("CRASH_REPORT.txt"):
        print("\n💥 FATAL PIPELINE EXCEPTION DETECTED:")
        with open("CRASH_REPORT.txt", "r") as f:
            print("   " + f.read().replace("\n", "\n   "))
            
    # 4. Tail the output logs from MacStudio if it exists
    log_path = "macstudio.log"
    if os.path.exists(log_path):
        print(f"\n📝 Last 10 lines of system logs ({log_path}):")
        with open(log_path, "r") as f:
            lines = f.readlines()
            for line in lines[-10:]:
                print("   > " + line.strip())

    print("\n==================================================")

if __name__ == "__main__":
    generate_report()
