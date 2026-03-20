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

def generate_voiceover(text_script, output_filename="temp_voiceover.mp3", music_vibe="suspense"):
    """
    Takes a text string and generates a hyper-realistic audio file using ElevenLabs.
    """
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
                stability=0.35, # Dropped low to allow extreme emotional volatility and natural dynamic inflections
                similarity_boost=0.85, # Keep the core hyper-realistic voice identity intact
                style=0.65, # Heavy storytelling stylistic exaggeration for maximum addiction
                use_speaker_boost=True
            )
        )
        
        # Save the audio stream to a local file
        save(audio, output_filename)
        print(f"✅ Success! Audio saved locally as: {output_filename}")
        
        return output_filename
        
    except Exception as e:
        print(f"❌ Error generating audio: {e}")
        return None

# Optional: Run this file directly to test just the audio
if __name__ == "__main__":
    test_text = "McDonald's isn't a fast-food company; it's the most aggressive real estate empire on the planet."
    generate_voiceover(test_text, "test_mcdonalds_hook.mp3")
