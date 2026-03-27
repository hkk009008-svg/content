import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs import save

# Load environment variables
load_dotenv()

# Initialize the ElevenLabs client
client = ElevenLabs(
    api_key=os.getenv("ELEVENLABS_API_KEY"),
)

def generate_voiceover(ctx: dict) -> bool:
    """
    Takes the text from OmniContext and generates a hyper-realistic audio file.
    """
    text_script = ctx.get("full_text", "")
    music_vibe = ctx.get("music_vibe", "suspense")
    output_filename = "temp_voiceover.mp3"
    
    print(f"\n🎙️ [PHASE B] Sending script to ElevenLabs (Mood: {music_vibe.upper()})...")
    
    # Map the script's psychological mood to the perfect physical voice actor
    voice_profiles = {
        "suspense": "pNInz6obpgDQGcFmaJgB", # Adam (Deep, authoritative)
        "corporate": "ErXwobaYiN019PkySvjV", # Antoni (Clean professional)
        "gritty": "D38z5RcWu1voky8WS1ja", # Fin (Visceral, gritty)
        "cyberpunk": "cjVigY5qzO86Huf0OWal", # Eric (Grizzly, mature, dark)
    }
    
    breathtaking_voices = [
        {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (Epic Deep Narrator)"},
        {"id": "cjVigY5qzO86Huf0OWal", "name": "Eric (Grizzly & Mature)"},
        {"id": "D38z5RcWu1voky8WS1ja", "name": "Fin (Visceral & Gritty)"},
        {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni (Clean Professional)"}
    ]
    
    import random
    chosen_actor = random.choice(breathtaking_voices)
    target_voice_id = chosen_actor["id"]
    print(f"🎭 [PHASE B] Randomly Selected Voice Actor: {chosen_actor['name']}")
    
    try:
        # Generate the audio using ElevenLabs API v2+ structure with Elite Emotional VoiceSettings
        from elevenlabs import VoiceSettings
        # For breathtaking narration, we want high style (emotion) but solid stability
        audio = client.text_to_speech.convert(
            voice_id=target_voice_id,
            output_format="mp3_44100_128",
            text=text_script,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(
                stability=0.55, # Slightly lower stability allows the AI actor to dramatically inflect
                similarity_boost=0.85, 
                style=0.60, # Substantially boosted style constraint to force passionate, sweeping emotional delivery
                use_speaker_boost=True
            )
        )
        
        # Save the audio stream to a local file
        save(audio, output_filename)
        
        # --- NEW: Strip leading and trailing silence to ensure perfect infinite loops ---
        import subprocess
        import os
        trimmed_file = "temp_trimmed_" + output_filename
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", output_filename,
                "-af", "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,areverse",
                trimmed_file
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            os.replace(trimmed_file, output_filename)
            print("✂️  [PHASE B] Silence trimmed from audio to guarantee infinite loop sync!")
        except Exception as e:
            print(f"⚠️ Warning: Failed to trim silence from TTS track. {e}")
            
        print(f"✅ Success! Audio saved locally as: {output_filename}")
        
        ctx["audio_path"] = output_filename
        ctx["voice_id"] = target_voice_id
        
        # Generate BGM dynamically alongside Voiceover
        generate_fal_bgm(music_vibe, f"bg_{music_vibe}.mp3")
        
        return True
        
    except Exception as e:
        print(f"❌ Error generating audio: {e}")
        return False

# Optional: Run this file directly to test just the audio
if __name__ == "__main__":
    test_text = "McDonald's isn't a fast-food company; it's the most aggressive real estate empire on the planet."
    generate_voiceover({"full_text": test_text, "music_vibe": "suspense"})

def generate_fal_bgm(music_vibe: str, output_filename: str, duration: int = 42):
    """Uses Fal.ai's text-to-audio engine to generate custom background music."""
    import os
    import urllib.request
    
    print(f"🎵 [PHASE B] Generating Custom [{music_vibe.upper()}] Background Audio via Fal.ai...")
    try:
        import fal_client
        vibe_prompts = {
            "suspense": "Slow, deep sub-bass drones, cinematic espionage suspense, ominous dark ambient thriller, ticking clock tension, Hans Zimmer.",
            "corporate": "Sleek, atmospheric tech ambient, minimalist synth pulses, high-stakes global documentary, Ridley Scott neo-noir.",
            "gritty": "Heavy industrial distorted bass, gritty tension, visceral mechanical pulse, hard hitting, dark documentary.",
            "cyberpunk": "Dark synthwave, neon cyberpunk atmosphere, driving analog synthesizers, futuristic dystopia ambient."
        }
        prompt = vibe_prompts.get(music_vibe.lower(), "Ambient cinematic drone, slow, ethereal, beautiful.")
        
        result = fal_client.subscribe(
            "fal-ai/stable-audio", # Top tier ambient/music generation
            arguments={
                "prompt": prompt,
                "seconds_total": duration
            }
        )
        
        audio_url = None
        if 'audio_file' in result:
            audio_url = result['audio_file']['url']
        elif 'audio' in result:
            o = result['audio']
            audio_url = o['url'] if isinstance(o, dict) else o
        
        if audio_url:
            urllib.request.urlretrieve(audio_url, output_filename)
            print(f"✅ Fal.ai Generated BGM saved as: {output_filename}")
            return True
            
        print("⚠️ Fal.ai BGM Warning: No audio URL returned.")
        return False
    except Exception as e:
        print(f"⚠️ Fal.ai BGM Generation Sub-Error (Using fallback generic BGM via assembly): {e}")
        return False

def generate_srt(audio_path: str, srt_path: str):
    print(f"📝 [PHASE B] Transcribing audio back to precise SRT captions: {audio_path}")
    import whisper
    import datetime
    
    # Use the base model for speed and accuracy
    model = whisper.load_model("base")
    result = model.transcribe(audio_path)
    
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(result["segments"], start=1):
            start = datetime.timedelta(seconds=segment["start"])
            end = datetime.timedelta(seconds=segment["end"])
            
            # Format timedelta to SRT format (HH:MM:SS,mmm)
            def format_time(td):
                total_seconds = int(td.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                milliseconds = int(td.microseconds / 1000)
                return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
                
            f.write(f"{i}\n")
            f.write(f"{format_time(start)} --> {format_time(end)}\n")
            f.write(f"{segment['text'].strip()}\n\n")
            
    print(f"✅ SRT successfully saved to {srt_path}")
    return srt_path

def generate_scene_foley_library(ctx: dict) -> bool:
    """Iterates through each cinematic shot and generates custom ambient Foley layer using ElevenLabs."""
    print("\n🎧 [PHASE B] Generating Immersive Environmental Foley for each scene...")
    prompts = ctx.get("script_data", {}).get("ai_image_prompts", [])
    ctx["foley_audio_paths"] = []
    
    for i, p in enumerate(prompts):
        foley_desc = p.get("scene_foley", "soft cinematic room tone, faint ambient hum")
        print(f"   ↳ Generating Foley Scene {i+1}: '{foley_desc}'")
        output_filename = f"temp_foley_{i}.mp3"
        try:
            # Generate the sound effect
            result = client.text_to_sound_effects.convert(
                text=foley_desc,
                duration_seconds=5, # Average visual clip length
                prompt_influence=0.4
            )
            with open(output_filename, "wb") as f:
                for chunk in result:
                    if chunk:
                        f.write(chunk)
            ctx["foley_audio_paths"].append(output_filename)
        except Exception as e:
            print(f"      ⚠️ Warning: Foley generation failed for Scene {i+1}: {e}")
            ctx["foley_audio_paths"].append(None) # Safe fallback
            
    return True
