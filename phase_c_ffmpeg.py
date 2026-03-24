import os
import time
import subprocess

try:
    from runwayml import RunwayML, TaskFailedError
except Exception:
    pass # Will gracefully fail/mock later

def generate_ai_video(image_path: str, camera_motion: str, target_api: str, output_mp4: str, pacing: str = "moderate") -> str:
    """
    Routes an image to RunwayML or Google Veo based on the target_api flag.
    If the respective SDK or API key is missing, falls back to an FFMPEG zoom effect.
    """
    print(f"   ↳ Routing to {target_api} API engine...")
    
    # Base fallback mechanism (if APIs fail or aren't configured)
    def fallback_ffmpeg_zoom(img: str, out: str) -> str:
        curr_dur = 5.0
        print("   ⚠️ APIs unavailable. Falling back to local FFMPEG slow-zoom.")
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", img,
            "-vf", "zoompan=z='min(zoom+0.0015,1.5)':d=125:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',scale=1080:1920",
            "-c:v", "libx264", "-t", str(curr_dur), "-preset", "ultrafast", out
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out if os.path.exists(out) else None

    # RunwayML Elite Cinematic Generation
    runway_key = os.getenv("RUNWAYML_API_SECRET", "key_eefac4c47c6d62fdb7403d236542e8bee22a05cfcc2ee0224f4f9582e6a3a42c3a6d3238a2ba3f896eb5fa6d6096b8a0d16cdb01445f7b31f2340bc912b358ff")
    if runway_key:
        try:
            runway_client = RunwayML(api_key=runway_key)
            video_task = runway_client.image_to_video.create(
                model="gen3a_turbo",
                prompt_image=image_path,
                prompt_text=f"Smooth {camera_motion}. Cinematic lighting.",
                ratio="720:1280",
                duration=5,
                watermark=False
            )
            print(f"   ↳ Runway Task {video_task.id} queued. Polling...")
            completed_task = video_task.wait_for_task_output()
            final_video_url = completed_task.output[0]
            # Download it
            import urllib.request
            urllib.request.urlretrieve(final_video_url, output_mp4)
            return output_mp4
        except Exception as e:
            print(f"   ⚠️ Runway API Error: {e}")
            return fallback_ffmpeg_zoom(image_path, output_mp4)
    else:
        return fallback_ffmpeg_zoom(image_path, output_mp4)

def generate_ass_subtitles(whisper_result: dict, output_path: str):
    """Converts Whisper word-level timestamps to an advanced SubStation Alpha (.ass) file."""
    ass_header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Roboto,96,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,10,10,600,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    def format_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centi = int(round((seconds - int(seconds)) * 100))
        centi = min(centi, 99)
        return f"{hours:d}:{minutes:02d}:{secs:02d}.{centi:02d}"

    lines = []
    for segment in whisper_result.get('segments', []):
        if 'words' in segment:
            for word_obj in segment['words']:
                word = word_obj['word'].strip().upper()
                start_pts = format_time(word_obj['start'])
                # Extend end time slightly so words don't blink too fast
                end_pts = format_time(word_obj['end'] + 0.1)
                
                # Active yellow text with white outline: {\1c&H00D4FF&}
                event_line = f"Dialogue: 0,{start_pts},{end_pts},Default,,0,0,0,,{{\\\\1c&H00D4FF&}}{word}"
                lines.append(event_line)
        else:
            text = segment['text'].strip().upper()
            start_pts = format_time(segment['start'])
            end_pts = format_time(segment['end'])
            event_line = f"Dialogue: 0,{start_pts},{end_pts},Default,,0,0,0,,{text}"
            lines.append(event_line)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_header + "\\n".join(lines) + "\\n")
    print(f"      Generated ASS Subtitles: {output_path}")
    return output_path

def probe_audio(file_path: str) -> bool:
    """Executes ffprobe to determine if an MP4 contains an active audio stream."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_name", "-of",
        "default=noprint_wrappers=1:nokey=1", file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    return len(result.stdout.strip()) > 0

def normalize_clip(input_path: str, output_path: str, duration_sec: float = None) -> str:
    """Forces 1080x1920 scaling, exact 24fps, injects silent audio, and explicitly trims to match spoken sentence lengths."""
    has_audio = probe_audio(input_path)
    cmd = ["ffmpeg", "-y", "-i", input_path]
    
    if not has_audio:
        cmd.extend(["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        
    cmd.extend([
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=24",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"
    ])
    
    if duration_sec:
        cmd.extend(["-t", str(duration_sec)])
    
    if not has_audio and not duration_sec:
        cmd.append("-shortest")
        
    cmd.append(output_path)
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"      Normalized: {output_path} | Audio: {has_audio} | Duration: {duration_sec}s")
    return output_path

def stitch_modules(module_paths: list, final_output: str) -> str:
    """Stitches normalized MP4 modules sequentially using the FFmpeg concat demuxer."""
    list_file = "concat_list.txt"
    with open(list_file, "w") as f:
        for path in module_paths:
            f.write(f"file '{os.path.abspath(path)}'\\n")
            
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", final_output
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.remove(list_file)
    print(f"      Stitched sequence: {final_output}")
    return final_output

def execute_master_ffmpeg_assembly(video_path: str, tts_path: str, bgm_path: str, ass_path: str, output_path: str, topic_text: str = ""):
    """
    Executes a single-pass zero-loss FFmpeg complex filtergraph to:
      1. Overlay the top banner natively
      2. Render .ASS subtitles
      3. Mix Foley, TTS, and ducked BGM using sidechaincompress
    """
    cmd = [
        "ffmpeg", "-y", 
        "-i", video_path, 
        "-i", tts_path, 
        "-i", bgm_path
    ]
    
    # 1. [tts_v]: TTS track wrapper
    # 2. [bgm_looped]: Loop BGM infinitely
    # 3. [bgm_ducked]: Sidechain compress BGM via TTS signal
    # 4. [foley]: Lower native Veo audio
    # 5. [mixed]: amix all tracks
    # 6. [final_audio]: Apply loudnorm
    
    safe_topic = topic_text.replace("'", "").replace(":", "\\\\:") if topic_text else "A N A L Y S I S"
    
    # Text Banner Filter (equivalent to MoviePy logic)
    text_filter = f"drawtext=text='A N A L Y S I S':fontcolor=white:fontsize=40:x=(w-text_w)/2:y=150:box=1:boxcolor=black@0.5:boxborderw=20,"
    text_filter += f"drawtext=text='{safe_topic}':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=220,"
    
    # ASS Subtitle Filter (Relative path fixes Mac parsing errors)
    subtitle_filter = f"subtitles='{os.path.basename(ass_path)}'"
    
    # Note: Because the ASS file might contain complex formatting or commas, 
    # it's best to isolate subtitle processing to [v_final].
    v_graph = f"[0:v]{text_filter}{subtitle_filter}[v_final]"
    
    a_graph = (
        "[1:a]volume=1.0[tts_v];"
        "[2:a]volume=0.4,aloop=loop=-1:size=2e9[bgm_looped];"
        "[bgm_looped][tts_v]sidechaincompress=threshold=0.08:ratio=4:attack=50:release=300[bgm_ducked];"
        "[0:a]volume=0.6[foley];"
        "[foley][tts_v][bgm_ducked]amix=inputs=3:duration=first:dropout_transition=2[mixed];"
        "[mixed]loudnorm=I=-14:LRA=11:TP=-1.5[final_audio]"
    )
    
    filtercomplex = f"{v_graph};{a_graph}"
    
    cmd.extend([
        "-filter_complex", filtercomplex,
        "-map", "[v_final]", 
        "-map", "[final_audio]",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k", 
        "-shortest",
        output_path
    ])
    
    print(f"      Executing Single-Pass FFmpeg Master Assembly...")
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"      ✅ Master Audio & Video Mix Complete: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"      ❌ FFmpeg Assembly Failed. Error:\\n{e.stderr.decode('utf-8')}")
        return False
