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

def generate_voiceover(text_script, output_filename="temp_voiceover.mp3"):
    """
    Takes a text string and generates a hyper-realistic audio file using ElevenLabs.
    """
    print("\n🎙️ [PHASE B] Sending script to ElevenLabs...")
    
    try:
        # Generate the audio using ElevenLabs API v2+ structure
        audio = client.text_to_speech.convert(
            voice_id="pNInz6obpgDQGcFmaJgB", # 'Adam' voice ID
            output_format="mp3_44100_128",
            text=text_script,
            model_id="eleven_multilingual_v2"
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
