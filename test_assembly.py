import traceback
from phase_c_ffmpeg import execute_master_ffmpeg_assembly

# Mock timeline effects similar to production
timeline_effects = [
    {"effect": "cyberpunk_glitch", "start": 0.0, "end": 2.35},
    {"effect": "dreamy_blur", "start": 2.35, "end": 4.70},
    {"effect": "cinematic_glow", "start": 4.70, "end": 7.05},
    {"effect": "gritty_contrast", "start": 7.05, "end": 9.40}
]

try:
    success = execute_master_ffmpeg_assembly(
         video_path="temp_captions_ready.mp4",
         tts_path="temp_voiceover.mp3",
         bgm_path="bg_cyberpunk.mp3",
         ass_path="whisper_captions.ass",
         output_path="FINAL_TEST.mp4",
         topic_text="Test",
         tts_duration=10.0,
         timeline_effects=timeline_effects
    )
    print(f"Assembly Success: {success}")
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
