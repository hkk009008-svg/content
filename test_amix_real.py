import subprocess
import os

# Create valid 2-channel audio for video.mp4, tts, bgm
subprocess.run("ffmpeg -y -f lavfi -i color=c=black -f lavfi -i aevalsrc=\"sin(0):c=FL+FR\" -t 1 video.mp4", shell=True, stderr=subprocess.DEVNULL)
subprocess.run("ffmpeg -y -f lavfi -i aevalsrc=\"sin(0):c=FL+FR\" -t 1 tts.m4a", shell=True, stderr=subprocess.DEVNULL)
subprocess.run("ffmpeg -y -f lavfi -i aevalsrc=\"sin(0):c=FL+FR\" -t 1 bgm.m4a", shell=True, stderr=subprocess.DEVNULL)

cmd = [
    "ffmpeg", "-y", 
    "-i", "video.mp4", 
    "-i", "tts.m4a", 
    "-i", "bgm.m4a",
    "-filter_complex",
    "[1:a]volume=1.0[tts_v];[2:a]volume=0.4,aloop=loop=-1:size=2e9[bgm_looped];[bgm_looped][tts_v]sidechaincompress=threshold=0.08:ratio=4:attack=50:release=300[bgm_ducked];[0:a]volume=0.6[foley];[foley][tts_v][bgm_ducked]amix=inputs=3:duration=first:dropout_transition=2[mixed];[mixed]loudnorm=I=-14:LRA=11:TP=-1.5[final_audio]",
    "-map", "0:v", 
    "-map", "[final_audio]",
    "-c:v", "copy",
    "-c:a", "aac", "output.mp4"
]
result = subprocess.run(cmd, capture_output=True, text=True)
print("Return code:", result.returncode)
print("Stderr:", result.stderr[-500:])
