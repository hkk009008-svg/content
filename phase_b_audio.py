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
                stability=max(0.40, min(0.85, 0.70 - (0.15 * ctx.get("story_tension", 1.0)))),
                similarity_boost=0.85, 
                # Keep style severely constrained so it feels more like an organic conversation
                style=max(0.10, min(0.40, 0.15 + (0.15 * ctx.get("story_tension", 1.0)))), 
                use_speaker_boost=True
            )
        )
        
        # Save the audio stream to a local file
        save(audio, output_filename)
        print(f"✅ Success! Audio saved locally as: {output_filename}")
        
        ctx["audio_path"] = output_filename
        ctx["voice_id"] = target_voice_id
        return True
        
    except Exception as e:
        print(f"❌ Error generating audio: {e}")
        return False

# Optional: Run this file directly to test just the audio
if __name__ == "__main__":
    test_text = "McDonald's isn't a fast-food company; it's the most aggressive real estate empire on the planet."
    generate_voiceover(test_text, "test_mcdonalds_hook.mp3")
