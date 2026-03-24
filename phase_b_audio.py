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
        "suspense": "pNInz6obpgDQGcFmaJgB", # Adam (Deep, authoritative gripping narration)
        "lofi": "21m00Tcm4TlvDq8ikWAM", # Rachel (Soft, intimate, slow conversational)
        "corporate": "ErXwobaYiN019PkySvjV", # Antoni (Clean, highly articulate professional)
        "upbeat": "5Q0t7uMcjvnagumLfvZi", # Paul (Highly energetic, bright journalist)
        "aggressive": "D38z5RcWu1voky8WS1ja" # Fin (Visceral, gritty, intense and fast)
    }
    
    target_voice_id = voice_profiles.get(music_vibe, "pNInz6obpgDQGcFmaJgB")
    
    try:
        # Generate the audio using ElevenLabs API v2+ structure with Elite Emotional VoiceSettings
        from elevenlabs import VoiceSettings
        audio = client.text_to_speech.convert(
            voice_id=target_voice_id,
            output_format="mp3_44100_128",
            text=text_script,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(
                # Limit the drop in stability so it always sounds reliable and trustful
                stability=max(0.20, min(0.95, 0.85 - (0.15 * ctx.get("story_tension", 1.0)))),
                similarity_boost=0.85, 
                # Keep style severely constrained so it feels more like an organic conversation
                style=max(0.00, min(0.60, 0.05 + (0.15 * ctx.get("story_tension", 1.0)))), 
                use_speaker_boost=True
            )
        )
        
        # Save the audio stream to a local file
        save(audio, output_filename)
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
            "suspense": "Slow, deep sub-bass drones, cinematic suspense, ominous, dark ambient, 432Hz.",
            "lofi": "Deeply soothing ambient soundscape, slow ethereal synth pads, Hans Zimmer cosmic awe, frequencies of healing, very slow tempo.",
            "corporate": "Bright, uplifting tech ambient, clean synth arpeggios, neutral documentary tone.",
            "upbeat": "High tempo electronic breakbeat, energetic, pulsing synthesizer, driving rhythm.",
            "aggressive": "Heavy industrial distorted bass, aggressive synth wave, cyberpunk, hard hitting."
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
