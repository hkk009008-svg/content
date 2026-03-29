import os
from dotenv import load_dotenv
from typing import Optional, List
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
            model_id="eleven_v3",
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

# ─────────────────────────────────────────────────────────────
# VOICE DIRECTION SYSTEM
# Maps delivery styles to precise ElevenLabs v3 voice parameters
# and optional SSML-like text markup for prosody control.
#
# Each profile defines:
#   stability: 0-1 (lower = more expressive/variable, higher = more consistent)
#   similarity: 0-1 (how close to the original voice)
#   style: 0-1 (0 = neutral, 1 = maximum emotional expression)
#   speaker_boost: bool (enhanced clarity/presence)
#   markup: optional function to wrap text with pauses/emphasis
# ─────────────────────────────────────────────────────────────

VOICE_DIRECTIONS = {
    # --- Calm / Neutral ---
    "natural": {
        "stability": 0.55, "similarity": 0.85, "style": 0.50,
        "speaker_boost": True,
        "description": "Natural conversational delivery",
    },
    "calm": {
        "stability": 0.70, "similarity": 0.85, "style": 0.30,
        "speaker_boost": True,
        "description": "Steady, measured, reassuring tone",
    },
    "flat": {
        "stability": 0.90, "similarity": 0.90, "style": 0.10,
        "speaker_boost": False,
        "description": "Monotone, emotionless, robotic delivery",
    },
    "deadpan": {
        "stability": 0.85, "similarity": 0.85, "style": 0.15,
        "speaker_boost": False,
        "description": "Dry, ironic, understated humor",
    },

    # --- Quiet / Intimate ---
    "whisper": {
        "stability": 0.75, "similarity": 0.80, "style": 0.35,
        "speaker_boost": False,
        "description": "Barely audible, breathy whisper",
        "markup": lambda t: f"(whispering) {t}",
    },
    "soft": {
        "stability": 0.65, "similarity": 0.85, "style": 0.45,
        "speaker_boost": True,
        "description": "Gentle, tender, intimate delivery",
    },
    "gentle": {
        "stability": 0.65, "similarity": 0.85, "style": 0.45,
        "speaker_boost": True,
        "description": "Warm, caring, soothing",
    },
    "hushed": {
        "stability": 0.70, "similarity": 0.80, "style": 0.40,
        "speaker_boost": False,
        "description": "Speaking quietly, as if someone might hear",
        "markup": lambda t: f"(in a hushed voice) {t}",
    },
    "confessional": {
        "stability": 0.60, "similarity": 0.80, "style": 0.55,
        "speaker_boost": False,
        "description": "Intimate admission, vulnerable and quiet",
        "markup": lambda t: f"(quietly, confessing) {t}",
    },

    # --- Strong / Commanding ---
    "firm": {
        "stability": 0.40, "similarity": 0.85, "style": 0.75,
        "speaker_boost": True,
        "description": "Assertive, decisive, commanding",
    },
    "angry": {
        "stability": 0.30, "similarity": 0.80, "style": 0.90,
        "speaker_boost": True,
        "description": "Heated, aggressive, sharp delivery",
        "markup": lambda t: f"(angrily) {t}",
    },
    "furious": {
        "stability": 0.20, "similarity": 0.75, "style": 1.0,
        "speaker_boost": True,
        "description": "Explosive rage, barely controlled",
        "markup": lambda t: f"(with fury) {t}!",
    },
    "commanding": {
        "stability": 0.35, "similarity": 0.85, "style": 0.80,
        "speaker_boost": True,
        "description": "Military authority, no room for debate",
        "markup": lambda t: f"(commanding) {t}",
    },
    "stern": {
        "stability": 0.45, "similarity": 0.85, "style": 0.70,
        "speaker_boost": True,
        "description": "Disapproving, serious, no-nonsense",
    },

    # --- Emotional / Dramatic ---
    "emotional": {
        "stability": 0.35, "similarity": 0.80, "style": 0.85,
        "speaker_boost": True,
        "description": "Deeply moved, voice breaking with emotion",
        "markup": lambda t: f"(with deep emotion) {t}",
    },
    "crying": {
        "stability": 0.25, "similarity": 0.75, "style": 0.95,
        "speaker_boost": False,
        "description": "Speaking through tears, voice cracking",
        "markup": lambda t: f"(through tears) {t}",
    },
    "grief": {
        "stability": 0.30, "similarity": 0.80, "style": 0.90,
        "speaker_boost": False,
        "description": "Devastated, hollow, barely holding together",
        "markup": lambda t: f"(with grief) {t}",
    },
    "heartbroken": {
        "stability": 0.30, "similarity": 0.78, "style": 0.88,
        "speaker_boost": False,
        "description": "Voice cracking with loss",
        "markup": lambda t: f"(heartbroken) {t}",
    },
    "desperate": {
        "stability": 0.25, "similarity": 0.80, "style": 0.90,
        "speaker_boost": True,
        "description": "Pleading, urgent, on the verge of panic",
        "markup": lambda t: f"(desperately) {t}",
    },
    "trembling": {
        "stability": 0.25, "similarity": 0.78, "style": 0.80,
        "speaker_boost": False,
        "description": "Voice shaking with fear or cold",
        "markup": lambda t: f"(voice trembling) {t}",
    },

    # --- Happy / Energetic ---
    "cheerful": {
        "stability": 0.50, "similarity": 0.85, "style": 0.70,
        "speaker_boost": True,
        "description": "Bright, upbeat, genuinely happy",
    },
    "excited": {
        "stability": 0.35, "similarity": 0.80, "style": 0.85,
        "speaker_boost": True,
        "description": "Enthusiastic, high energy, can barely contain it",
        "markup": lambda t: f"(excitedly) {t}!",
    },
    "laughing": {
        "stability": 0.30, "similarity": 0.75, "style": 0.80,
        "speaker_boost": True,
        "description": "Speaking while laughing, joy breaking through",
        "markup": lambda t: f"(laughing) {t}",
    },
    "playful": {
        "stability": 0.45, "similarity": 0.85, "style": 0.65,
        "speaker_boost": True,
        "description": "Teasing, flirtatious, lighthearted",
    },
    "sarcastic": {
        "stability": 0.55, "similarity": 0.85, "style": 0.60,
        "speaker_boost": True,
        "description": "Dry wit, ironic emphasis, knowing tone",
    },

    # --- Fear / Tension ---
    "scared": {
        "stability": 0.30, "similarity": 0.80, "style": 0.80,
        "speaker_boost": False,
        "description": "Frightened, voice higher and quicker",
        "markup": lambda t: f"(fearfully) {t}",
    },
    "terrified": {
        "stability": 0.20, "similarity": 0.75, "style": 0.90,
        "speaker_boost": False,
        "description": "Paralyzed with fear, barely able to speak",
        "markup": lambda t: f"(in terror) {t}",
    },
    "nervous": {
        "stability": 0.40, "similarity": 0.82, "style": 0.55,
        "speaker_boost": False,
        "description": "Uncertain, fidgety, slightly stammering",
    },
    "suspicious": {
        "stability": 0.55, "similarity": 0.85, "style": 0.50,
        "speaker_boost": True,
        "description": "Questioning, wary, not trusting what they hear",
    },
    "tense": {
        "stability": 0.45, "similarity": 0.85, "style": 0.65,
        "speaker_boost": True,
        "description": "Controlled but clearly stressed, tight voice",
    },

    # --- Professional / Narrative ---
    "narration": {
        "stability": 0.60, "similarity": 0.88, "style": 0.55,
        "speaker_boost": True,
        "description": "Documentary narrator, authoritative and clear",
    },
    "announcer": {
        "stability": 0.65, "similarity": 0.90, "style": 0.50,
        "speaker_boost": True,
        "description": "News anchor, polished and precise",
    },
    "dramatic_narration": {
        "stability": 0.45, "similarity": 0.85, "style": 0.75,
        "speaker_boost": True,
        "description": "Cinematic voiceover, sweeping and powerful",
        "markup": lambda t: f"(with gravitas) {t}",
    },
    "internal_monologue": {
        "stability": 0.60, "similarity": 0.80, "style": 0.50,
        "speaker_boost": False,
        "description": "Inner thoughts, reflective, slightly detached",
        "markup": lambda t: f"(thinking to themselves) {t}",
    },

    # --- Specialty ---
    "shouting": {
        "stability": 0.20, "similarity": 0.78, "style": 0.95,
        "speaker_boost": True,
        "description": "Yelling across distance or in confrontation",
        "markup": lambda t: f"(shouting) {t.upper()}!",
    },
    "exhausted": {
        "stability": 0.65, "similarity": 0.80, "style": 0.40,
        "speaker_boost": False,
        "description": "Out of breath, drained, barely keeping going",
        "markup": lambda t: f"(exhausted, catching breath) {t}",
    },
    "drunk": {
        "stability": 0.20, "similarity": 0.70, "style": 0.70,
        "speaker_boost": False,
        "description": "Slurred, loose, uninhibited speech",
        "markup": lambda t: f"(slurring slightly) {t}",
    },
    "seductive": {
        "stability": 0.60, "similarity": 0.82, "style": 0.65,
        "speaker_boost": False,
        "description": "Low, slow, intentionally alluring",
        "markup": lambda t: f"(in a low, enticing voice) {t}",
    },
    "cold": {
        "stability": 0.75, "similarity": 0.88, "style": 0.30,
        "speaker_boost": True,
        "description": "Emotionally distant, clinical, chilling",
    },
    "mocking": {
        "stability": 0.40, "similarity": 0.82, "style": 0.70,
        "speaker_boost": True,
        "description": "Ridiculing, patronizing, cruelly amused",
        "markup": lambda t: f"(mockingly) {t}",
    },
}


def get_voice_direction(delivery: str) -> dict:
    """
    Get voice direction profile from a delivery description.
    Handles exact matches and fuzzy keyword matching.

    Returns dict with: stability, similarity, style, speaker_boost, markup (optional)
    """
    delivery_lower = delivery.lower().strip()

    # Exact match
    if delivery_lower in VOICE_DIRECTIONS:
        return VOICE_DIRECTIONS[delivery_lower]

    # Fuzzy keyword match — check if any key appears in the delivery string
    for key, profile in VOICE_DIRECTIONS.items():
        if key in delivery_lower:
            return profile

    # Default to natural
    return VOICE_DIRECTIONS["natural"]


# List of all available delivery styles (for frontend dropdown)
DELIVERY_STYLES = sorted(VOICE_DIRECTIONS.keys())


# ─────────────────────────────────────────────────────────────
# NARRATION MODE
# Separate narrator voice OVER the video — not characters speaking.
# Like a documentary voiceover or omniscient narrator in a film.
# ─────────────────────────────────────────────────────────────

# Dedicated narrator voices (separate from character pool)
NARRATOR_VOICES = [
    {"id": "2EiwWnXFnvU5JabPnv8n", "name": "Clyde", "style": "Warm storyteller, veteran narrator"},
    {"id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel", "style": "Authoritative British narrator"},
    {"id": "N2lVS1w4EtoT3dr4eOWO", "name": "Callum", "style": "Intense, dramatic narrator"},
    {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam", "style": "Deep, commanding narrator"},
    {"id": "ODq5zmih8GrVes37Dizd", "name": "Patrick", "style": "Wise, elder narrator"},
    {"id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte", "style": "Warm, narrative woman (British)"},
    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "style": "Gentle female narrator"},
]


def generate_narration(
    text: str,
    output_filename: str,
    narrator_voice: str = "auto",
    delivery: str = "dramatic_narration",
    mood: str = "cinematic",
) -> Optional[str]:
    """
    Generate narrator voiceover — a separate voice OVER the video.
    Not a character speaking, but an omniscient narrator like in documentaries or films.

    Args:
        text: Narration text
        output_filename: Output path
        narrator_voice: Voice name or "auto" to match mood
        delivery: Delivery style from VOICE_DIRECTIONS
        mood: Scene mood for auto voice selection
    """
    from elevenlabs import VoiceSettings

    # Auto-select narrator voice based on mood
    if narrator_voice == "auto":
        mood_to_narrator = {
            "suspense": "Adam", "thriller": "Callum", "horror": "Callum",
            "noir": "Daniel", "dystopian": "Callum",
            "melancholic": "Rachel", "romantic": "Charlotte", "hopeful": "Rachel",
            "epic": "Patrick", "dramatic": "Callum",
            "ethereal": "Charlotte", "dreamy": "Rachel",
        }
        narrator_name = mood_to_narrator.get(mood.lower(), "Daniel")
        voice_id = next((v["id"] for v in NARRATOR_VOICES if v["name"] == narrator_name), NARRATOR_VOICES[1]["id"])
    else:
        voice_id = next((v["id"] for v in NARRATOR_VOICES if v["name"].lower() == narrator_voice.lower()), NARRATOR_VOICES[1]["id"])

    profile = get_voice_direction(delivery)

    try:
        directed_text = profile["markup"](text) if profile.get("markup") else text
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            output_format="mp3_44100_128",
            text=directed_text,
            model_id="eleven_v3",
            voice_settings=VoiceSettings(
                stability=profile["stability"],
                similarity_boost=profile["similarity"],
                style=profile["style"],
                use_speaker_boost=profile.get("speaker_boost", True),
            ),
        )
        save(audio, output_filename)
        narrator_name = next((v["name"] for v in NARRATOR_VOICES if v["id"] == voice_id), "Unknown")
        print(f"   [NARRATION] {narrator_name} ({delivery}): {output_filename}")
        return output_filename
    except Exception as e:
        print(f"   [NARRATION] Failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# VOICE EFFECTS PROCESSOR
# Two engines:
#   1. FFmpeg filters — fast, reliable, covers 90% of use cases
#   2. Pedalboard + AU plugins — loads your macOS Audio Unit plugins
#      headlessly for professional studio-quality processing
# ─────────────────────────────────────────────────────────────

# Check for Pedalboard (Spotify's headless AU/VST3 plugin host)
try:
    import pedalboard
    from pedalboard import (
        Pedalboard, Reverb, Compressor, Gain, Delay,
        HighpassFilter, LowpassFilter, Chorus, Distortion,
        load_plugin,
    )
    from pedalboard.io import AudioFile
    PEDALBOARD_AVAILABLE = True
except ImportError:
    PEDALBOARD_AVAILABLE = False

VOICE_EFFECTS = {
    "none": {
        "filter": None,
        "description": "Clean, unprocessed voice",
    },
    "cinema_reverb": {
        "filter": "aecho=0.8:0.88:60:0.4,highpass=f=80,treble=gain=2",
        "description": "Cinematic reverb — large room, warm echo",
    },
    "intimate_room": {
        "filter": "aecho=0.8:0.9:20:0.3,highpass=f=100,lowpass=f=8000",
        "description": "Small room ambience — intimate, close",
    },
    "cathedral": {
        "filter": "aecho=0.8:0.88:100:0.5:60:0.35:40:0.2,highpass=f=60",
        "description": "Cathedral echo — massive reverberant space",
    },
    "telephone": {
        "filter": "highpass=f=400,lowpass=f=3400,volume=0.8",
        "description": "Phone call effect — bandpass filtered",
    },
    "radio": {
        "filter": "highpass=f=300,lowpass=f=5000,acompressor=threshold=-20dB:ratio=4:attack=5:release=50,volume=0.9",
        "description": "Radio broadcast — compressed, mid-range focused",
    },
    "megaphone": {
        "filter": "highpass=f=500,lowpass=f=4000,acompressor=threshold=-15dB:ratio=8,volume=1.2,overdrive=gain=3",
        "description": "Bullhorn/megaphone — harsh, distorted, loud",
    },
    "underwater": {
        "filter": "lowpass=f=500,aecho=0.8:0.7:40:0.5,volume=0.6",
        "description": "Underwater muffled — deep, submerged",
    },
    "dream_sequence": {
        "filter": "aecho=0.8:0.88:80:0.5:60:0.4,atempo=0.95,lowpass=f=6000,chorus=0.5:0.9:50|60:0.4|0.32:0.25|0.4:2|2.3",
        "description": "Dream/memory effect — slowed, reverberant, ethereal",
    },
    "robot": {
        "filter": "asetrate=48000*0.9,aresample=44100,chorus=0.7:0.9:55:0.4:0.25:2",
        "description": "Robotic/AI voice — pitch shifted, chorus effect",
    },
    "warm_broadcast": {
        "filter": "highpass=f=80,treble=gain=3,acompressor=threshold=-18dB:ratio=3:makeup=2,loudnorm=I=-16",
        "description": "Broadcast quality — warm, compressed, polished",
    },
    "whisper_intimate": {
        "filter": "highpass=f=100,treble=gain=4,aecho=0.8:0.9:15:0.2,volume=1.3",
        "description": "Enhanced whisper — breathy, close-mic feel",
    },
    "vintage_film": {
        "filter": "highpass=f=200,lowpass=f=6000,acompressor=threshold=-20dB:ratio=3,volume=0.85",
        "description": "Old film sound — warm, limited bandwidth, compressed",
    },
    "epic_narrator": {
        "filter": "aecho=0.8:0.88:40:0.3,treble=gain=2,bass=gain=3,acompressor=threshold=-14dB:ratio=4:makeup=3,loudnorm=I=-14",
        "description": "Epic narration — booming, present, reverberant",
    },
}


def apply_au_plugin(
    audio_path: str,
    output_path: str,
    plugin_name: str,
    parameters: dict = None,
) -> Optional[str]:
    """
    Apply a macOS Audio Unit plugin to an audio file using Pedalboard.
    This loads your installed AU plugins headlessly — no DAW needed.

    Args:
        audio_path: Input audio file
        output_path: Output processed file
        plugin_name: Name of the AU plugin (e.g., "Decapitator", "uaudio_la2a")
        parameters: Dict of plugin parameter overrides

    Returns:
        Path to processed audio, or original on failure
    """
    if not PEDALBOARD_AVAILABLE:
        print(f"   [AU] Pedalboard not installed — pip install pedalboard")
        return audio_path

    try:
        # Search for the plugin
        plugin_paths = [
            "/Library/Audio/Plug-Ins/Components/",
            os.path.expanduser("~/Library/Audio/Plug-Ins/Components/"),
        ]

        plugin_file = None
        for base in plugin_paths:
            if os.path.exists(base):
                for f in os.listdir(base):
                    if plugin_name.lower() in f.lower() and f.endswith(".component"):
                        plugin_file = os.path.join(base, f)
                        break

        if not plugin_file:
            print(f"   [AU] Plugin '{plugin_name}' not found")
            return audio_path

        print(f"   [AU] Loading: {os.path.basename(plugin_file)}")
        plugin = load_plugin(plugin_file)

        # Set parameters if provided
        if parameters:
            for k, v in parameters.items():
                try:
                    setattr(plugin, k, v)
                except Exception:
                    pass

        # Process audio
        with AudioFile(audio_path) as f:
            audio = f.read(f.frames)
            sr = f.samplerate

        board = Pedalboard([plugin])
        processed = board(audio, sr)

        with AudioFile(output_path, "w", sr, processed.shape[0]) as f:
            f.write(processed)

        print(f"   [AU] Processed with {os.path.basename(plugin_file)}: {output_path}")
        return output_path

    except Exception as e:
        print(f"   [AU] Plugin processing failed: {e}")
        return audio_path


def apply_pedalboard_chain(
    audio_path: str,
    output_path: str,
    effects: list = None,
) -> Optional[str]:
    """
    Apply a chain of Pedalboard built-in effects (no AU plugins needed).
    Works cross-platform. Good for programmatic effect chains.

    Args:
        audio_path: Input audio file
        output_path: Output processed file
        effects: List of effect dicts, e.g.:
            [
                {"type": "highpass", "cutoff": 80},
                {"type": "compressor", "threshold": -20, "ratio": 4},
                {"type": "reverb", "room_size": 0.6, "wet_level": 0.3},
                {"type": "gain", "gain_db": 2},
            ]
    """
    if not PEDALBOARD_AVAILABLE:
        return audio_path

    if not effects:
        return audio_path

    try:
        effect_map = {
            "reverb": lambda p: Reverb(room_size=p.get("room_size", 0.5), wet_level=p.get("wet_level", 0.3)),
            "compressor": lambda p: Compressor(threshold_db=p.get("threshold", -20), ratio=p.get("ratio", 4)),
            "gain": lambda p: Gain(gain_db=p.get("gain_db", 0)),
            "delay": lambda p: Delay(delay_seconds=p.get("delay", 0.3), feedback=p.get("feedback", 0.3)),
            "highpass": lambda p: HighpassFilter(cutoff_frequency_hz=p.get("cutoff", 80)),
            "lowpass": lambda p: LowpassFilter(cutoff_frequency_hz=p.get("cutoff", 8000)),
            "chorus": lambda p: Chorus(rate_hz=p.get("rate", 1.0), depth=p.get("depth", 0.25)),
            "distortion": lambda p: Distortion(drive_db=p.get("drive", 10)),
        }

        chain = []
        for fx in effects:
            fx_type = fx.get("type", "")
            if fx_type in effect_map:
                chain.append(effect_map[fx_type](fx))

        if not chain:
            return audio_path

        with AudioFile(audio_path) as f:
            audio = f.read(f.frames)
            sr = f.samplerate

        board = Pedalboard(chain)
        processed = board(audio, sr)

        with AudioFile(output_path, "w", sr, processed.shape[0]) as f:
            f.write(processed)

        print(f"   [PEDALBOARD] Applied {len(chain)} effects: {output_path}")
        return output_path

    except Exception as e:
        print(f"   [PEDALBOARD] Chain failed: {e}")
        return audio_path


def list_au_plugins() -> list:
    """List all available AU plugins on this Mac."""
    plugins = []
    for base in ["/Library/Audio/Plug-Ins/Components/",
                 os.path.expanduser("~/Library/Audio/Plug-Ins/Components/")]:
        if os.path.exists(base):
            for f in os.listdir(base):
                if f.endswith(".component"):
                    plugins.append(f.replace(".component", ""))
    return sorted(plugins)


def apply_voice_effect(
    audio_path: str,
    output_path: str,
    effect: str = "none",
    au_plugin: str = None,
    pedalboard_chain: list = None,
) -> Optional[str]:
    """
    Apply post-processing audio effect. Three engines available:

    1. FFmpeg filters (effect="cinema_reverb" etc.) — fast, reliable
    2. AU plugin (au_plugin="Decapitator") — your macOS plugins, headless
    3. Pedalboard chain (pedalboard_chain=[...]) — cross-platform effect chain

    Priority: AU plugin > Pedalboard chain > FFmpeg filter
    """
    import subprocess

    # Priority 1: AU plugin (if specified)
    if au_plugin and PEDALBOARD_AVAILABLE:
        result = apply_au_plugin(audio_path, output_path, au_plugin)
        if result != audio_path:
            return result

    # Priority 2: Pedalboard chain (if specified)
    if pedalboard_chain and PEDALBOARD_AVAILABLE:
        result = apply_pedalboard_chain(audio_path, output_path, pedalboard_chain)
        if result != audio_path:
            return result

    # Priority 3: FFmpeg filter
    if effect == "none" or effect not in VOICE_EFFECTS:
        return audio_path

    filter_chain = VOICE_EFFECTS[effect]["filter"]
    if not filter_chain:
        return audio_path

    try:
        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-af", filter_chain,
            "-c:a", "libmp3lame", "-b:a", "128k",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"   [FX] Applied '{effect}': {output_path}")
            return output_path
        return audio_path
    except Exception as e:
        print(f"   [FX] Effect '{effect}' failed: {e}")
        return audio_path


def generate_dialogue_voiceover(
    dialogue_lines: list,
    characters: list,
    output_filename: str = "temp_dialogue_voiceover.mp3",
    pause_between_lines: float = 0.3,
) -> Optional[str]:
    """
    Multi-character dialogue voiceover for cinema production.
    Generates separate audio per character using their assigned voice_id,
    then concatenates in dialogue order with pauses.

    Args:
        dialogue_lines: List of {character_id, text, delivery}
        characters: List of character dicts with 'id' and 'voice_id'
        output_filename: Output MP3 path
        pause_between_lines: Silence between lines in seconds

    Returns:
        Path to assembled dialogue audio, or None on failure
    """
    from elevenlabs import VoiceSettings

    char_voices = {c["id"]: c.get("voice_id", "") for c in characters}
    temp_files = []

    print(f"🎙️ [CINEMA] Generating multi-character dialogue ({len(dialogue_lines)} lines)...")

    for i, line in enumerate(dialogue_lines):
        cid = line.get("character_id", "")
        text = line.get("text", "")
        if not text.strip():
            continue

        voice_id = char_voices.get(cid, "")
        if not voice_id:
            # Fallback to first available voice
            voice_id = next((v for v in char_voices.values() if v), "pNInz6obpgDQGcFmaJgB")

        char_name = next((c["name"] for c in characters if c["id"] == cid), cid)
        delivery = line.get("delivery", "natural")

        # Voice direction system — maps delivery to precise voice parameters + text markup
        voice_profile = get_voice_direction(delivery)
        directed_text = voice_profile["markup"](text) if voice_profile.get("markup") else text

        temp_path = f"temp_dialogue_line_{i}.mp3"
        try:
            audio = client.text_to_speech.convert(
                voice_id=voice_id,
                output_format="mp3_44100_128",
                text=directed_text,
                model_id="eleven_v3",
                voice_settings=VoiceSettings(
                    stability=voice_profile["stability"],
                    similarity_boost=voice_profile["similarity"],
                    style=voice_profile["style"],
                    use_speaker_boost=voice_profile.get("speaker_boost", True),
                ),
            )
            save(audio, temp_path)
            temp_files.append(temp_path)
            print(f"   ✅ Line {i+1}: {char_name} ({delivery}) → {temp_path}")
        except Exception as e:
            print(f"   ⚠️ Failed to generate line {i+1} for {char_name}: {e}")

    if not temp_files:
        print("❌ No dialogue lines generated.")
        return None

    # Concatenate all lines with pauses using ffmpeg
    try:
        import subprocess

        # Create a concat list file
        concat_list = "temp_dialogue_concat.txt"
        silence_file = "temp_silence.mp3"

        # Generate a short silence file for pauses
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"anullsrc=r=44100:cl=mono:d={pause_between_lines}",
             "-c:a", "libmp3lame", silence_file],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )

        with open(concat_list, "w") as f:
            for j, tf in enumerate(temp_files):
                f.write(f"file '{tf}'\n")
                if j < len(temp_files) - 1:
                    f.write(f"file '{silence_file}'\n")

        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_list, "-c:a", "libmp3lame", "-q:a", "2", output_filename],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )

        print(f"   ✅ Multi-character dialogue assembled: {output_filename}")

        # Cleanup temp files
        for tf in temp_files:
            if os.path.exists(tf):
                os.remove(tf)
        for f in [concat_list, silence_file]:
            if os.path.exists(f):
                os.remove(f)

        return output_filename

    except Exception as e:
        print(f"   ⚠️ Dialogue concatenation failed: {e}")
        # Return last generated file as fallback
        return temp_files[0] if temp_files else None


def generate_scene_foley(foley_description: str, output_filename: str, duration: float = 5.0) -> Optional[str]:
    """Generate a single foley sound effect for a specific shot."""
    try:
        result = client.text_to_sound_effects.convert(
            text=foley_description,
            duration_seconds=duration,
            prompt_influence=0.4,
        )
        with open(output_filename, "wb") as f:
            for chunk in result:
                if chunk:
                    f.write(chunk)
        return output_filename
    except Exception as e:
        print(f"   [FOLEY] Generation failed: {e}")
        return None


def generate_layered_foley(
    shot: dict,
    scene: dict,
    output_filename: str,
    duration: float = 5.0,
) -> Optional[str]:
    """
    Generate multi-layer foley sound design for a shot.

    3 layers mixed together:
    1. AMBIENCE — continuous room tone / environmental background
    2. ACTION — specific sounds matching what's physically happening
    3. TEXTURE — atmospheric detail that fills the sonic space

    Each layer is generated separately via ElevenLabs SFX, then mixed
    via FFmpeg at calibrated volumes (ambience 70%, action 100%, texture 40%).
    """
    import subprocess
    import tempfile

    foley_desc = shot.get("scene_foley", "")
    action = shot.get("action_context", scene.get("action", ""))
    location_desc = scene.get("location_description", "")
    mood = scene.get("mood", "neutral")
    weather = scene.get("weather", "clear")

    # Build targeted prompts for each layer
    ambience_prompt = _build_ambience_prompt(location_desc, weather, mood)
    action_prompt = _build_action_prompt(action, foley_desc)
    texture_prompt = _build_texture_prompt(mood, weather, location_desc)

    print(f"   [FOLEY] Layered sound design: ambience + action + texture")

    # Generate all 3 layers — quality over speed
    temp_dir = tempfile.mkdtemp(prefix="foley_")
    layer_files = []

    for layer_name, prompt in [
        ("ambience", ambience_prompt),
        ("action", action_prompt),
        ("texture", texture_prompt),
    ]:
        layer_path = os.path.join(temp_dir, f"{layer_name}.mp3")
        result = generate_scene_foley(prompt, layer_path, duration=duration)
        if result:
            layer_files.append((layer_name, layer_path))
            print(f"      [FOLEY] {layer_name}: generated")
        else:
            print(f"      [FOLEY] {layer_name}: failed (skipping)")

    if not layer_files:
        # All layers failed — fall back to simple foley
        return generate_scene_foley(foley_desc or "ambient room tone", output_filename, duration)

    # Mix layers with FFmpeg — calibrated volumes per layer
    volume_map = {"ambience": 0.7, "action": 1.0, "texture": 0.4}

    try:
        cmd = ["ffmpeg", "-y"]
        filter_parts = []
        for i, (name, path) in enumerate(layer_files):
            cmd.extend(["-i", path])
            vol = volume_map.get(name, 0.5)
            filter_parts.append(f"[{i}:a]volume={vol}[a{i}]")

        # Mix all layers
        mix_inputs = "".join(f"[a{i}]" for i in range(len(layer_files)))
        filter_parts.append(f"{mix_inputs}amix=inputs={len(layer_files)}:duration=longest:dropout_transition=2[out]")

        cmd.extend([
            "-filter_complex", ";".join(filter_parts),
            "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "128k",
            output_filename,
        ])

        subprocess.run(cmd, capture_output=True, timeout=30)

        # Cleanup temp files
        for _, path in layer_files:
            if os.path.exists(path):
                os.remove(path)

        if os.path.exists(output_filename):
            print(f"   [FOLEY] Mixed {len(layer_files)} layers: {output_filename}")
            return output_filename

    except Exception as e:
        print(f"   [FOLEY] Mix failed: {e}")

    # Fallback: return first successful layer
    if layer_files:
        import shutil
        shutil.copy2(layer_files[0][1], output_filename)
        return output_filename

    return None


def _build_ambience_prompt(location: str, weather: str, mood: str) -> str:
    """Build an ambience prompt from location and weather context."""
    # Location-based ambient sounds
    location_lower = location.lower() if location else ""

    if any(w in location_lower for w in ["park", "garden", "forest", "outdoor", "field"]):
        base = "Birds chirping, gentle breeze through leaves, distant dog barking"
    elif any(w in location_lower for w in ["city", "street", "urban", "downtown"]):
        base = "Distant traffic hum, pedestrian footsteps, car horns far away, city ambience"
    elif any(w in location_lower for w in ["office", "room", "indoor", "apartment", "home"]):
        base = "Quiet room tone, air conditioning hum, distant muffled sounds through walls"
    elif any(w in location_lower for w in ["beach", "ocean", "coast", "shore"]):
        base = "Ocean waves crashing rhythmically, seagulls calling, sand shifting underfoot"
    elif any(w in location_lower for w in ["mountain", "hill", "cliff"]):
        base = "Mountain wind, eagle cry in distance, rocks shifting, vast open space echo"
    elif any(w in location_lower for w in ["cafe", "restaurant", "bar"]):
        base = "Quiet cafe murmur, clinking glasses, espresso machine, soft background chatter"
    else:
        base = f"Ambient room tone, {location}" if location else "Quiet ambient room tone"

    # Weather overlay
    weather_lower = weather.lower() if weather else "clear"
    if "rain" in weather_lower:
        base += ", steady rain falling on surfaces, occasional thunder rumble"
    elif "snow" in weather_lower:
        base += ", muffled snowy silence, wind through bare branches, crunching snow"
    elif "wind" in weather_lower:
        base += ", gusting wind, rustling fabric, swaying branches"
    elif "storm" in weather_lower:
        base += ", heavy storm, thunder cracks, torrential rain, wind howling"

    return base


def _build_action_prompt(action: str, foley_desc: str) -> str:
    """Build an action foley prompt from what the character is doing."""
    if foley_desc:
        return foley_desc

    action_lower = action.lower() if action else ""

    if any(w in action_lower for w in ["walk", "step", "pace"]):
        return "Footsteps on ground, rhythmic walking pace, clothing rustle with movement"
    elif any(w in action_lower for w in ["run", "sprint", "chase"]):
        return "Fast running footsteps, heavy breathing, wind rushing past ears"
    elif any(w in action_lower for w in ["sit", "stand", "lean"]):
        return "Clothing adjustment sounds, chair creak, subtle body movement"
    elif any(w in action_lower for w in ["talk", "speak", "whisper"]):
        return "Subtle lip sounds, breath between words, room presence"
    elif any(w in action_lower for w in ["door", "open", "close", "enter"]):
        return "Door handle turning, door creaking open, footsteps entering room"
    elif any(w in action_lower for w in ["car", "drive", "vehicle"]):
        return "Car engine idling, leather seat movement, turn signal clicking"
    elif any(w in action_lower for w in ["cook", "kitchen", "eat"]):
        return "Sizzling pan, chopping vegetables, running water, plates clinking"
    elif any(w in action_lower for w in ["type", "computer", "work"]):
        return "Keyboard typing, mouse clicking, computer fan hum"
    else:
        return f"Subtle movement sounds, {action}" if action else "Ambient presence, subtle room sounds"


def _build_texture_prompt(mood: str, weather: str, location: str) -> str:
    """Build an atmospheric texture prompt from mood context."""
    mood_lower = mood.lower() if mood else ""

    textures = {
        "melancholic": "Distant piano note reverb, lonely wind, emotional space, minor key drone",
        "tense": "Low frequency rumble, barely perceptible heartbeat, metallic shimmer",
        "dramatic": "Swelling low drone, distant thunder roll, dramatic tension build",
        "mysterious": "Eerie whistle, metallic resonance, unexplained creak, suspense texture",
        "peaceful": "Gentle wind chimes, flowing water stream, birds in distance, warm sunlight feeling",
        "dark": "Deep rumbling bass, metallic scraping far away, industrial undertone",
        "hopeful": "Warm rising tone, gentle shimmer, bright air, morning bird first call",
        "romantic": "Soft vinyl crackle, warm room tone, gentle breathing, intimate closeness",
        "energetic": "Pulsing low frequency, urban hum, electrical buzz, active presence",
    }

    base = textures.get(mood_lower, "Subtle atmospheric drone, cinematic texture, room presence")

    # Weather texture overlay
    if "rain" in (weather or "").lower():
        base += ", rain pattering on window"
    elif "snow" in (weather or "").lower():
        base += ", crystalline silence, muffled world"

    return base


def generate_fal_bgm(music_vibe: str, output_filename: str, duration: int = 42):
    """Uses Fal.ai's text-to-audio engine to generate custom background music."""
    import os
    import urllib.request

    print(f"   [BGM] Generating [{music_vibe.upper()}] via Fal.ai Stable Audio...")
    try:
        import fal_client

        # Producer-grade music prompts with BPM, key, instrumentation, texture
        vibe_prompts = {
            # --- Tension / Dark ---
            "suspense": "70bpm, D minor, slow deep sub-bass drones, distant reversed piano chords, ticking clock polyrhythm, cinematic brass stabs, Hans Zimmer-style tension, foley creaking, dark ambient thriller.",
            "thriller": "90bpm, E minor, pulsing synth bass, staccato strings, heartbeat kick drum, rising tension builds, thriller chase energy, Trent Reznor atmosphere.",
            "horror": "60bpm, C minor, dissonant string clusters, music box melody detuned, deep rumbling sub-bass, whispered textures, silence gaps, unsettling foley scratches, Ari Aster dread.",
            "noir": "75bpm, Bb minor, smoky jazz saxophone, brushed drums, upright bass walking line, rain-soaked city atmosphere, dim lounge piano, 1940s detective film.",
            "dystopian": "85bpm, F# minor, industrial metallic percussion, distorted analog synth drones, post-apocalyptic atmosphere, mechanical rhythms, Blade Runner 2049.",

            # --- Emotional / Dramatic ---
            "melancholic": "65bpm, A minor, solo piano with sustain pedal, distant cello legato, vinyl crackle texture, gentle rain ambience, introspective, Chopin meets Nils Frahm.",
            "romantic": "72bpm, D major, warm acoustic guitar fingerpicking, soft string quartet, gentle woodwind, golden hour warmth, tender, intimate, Richard Linklater film.",
            "bittersweet": "68bpm, G minor, solo violin melody, piano arpeggios, muted trumpet, autumn leaves atmosphere, nostalgic, wistful, Wong Kar-wai mood.",
            "grief": "55bpm, C minor, slow cello solo, sparse piano chords with long reverb, silence between notes, distant choir hum, devastating emotional weight, Schindler's List.",
            "hopeful": "80bpm, C major, rising piano chords, warm analog strings crescendo, gentle tambourine, sunrise atmosphere, new beginning energy, uplifting but restrained.",

            # --- Energy / Action ---
            "epic": "120bpm, D minor, massive orchestral brass fanfare, taiko drums, choir chanting, sweeping string runs, battle preparation energy, Lord of the Rings grandeur.",
            "action": "130bpm, E minor, driving electronic beats, distorted guitar riffs, aggressive drum patterns, adrenaline rush, Jason Bourne intensity.",
            "triumphant": "100bpm, Bb major, full orchestra fortissimo, French horns melody, snare roll crescendo, victorious brass, medal ceremony energy, John Williams glory.",
            "chase": "140bpm, A minor, relentless hi-hat patterns, pulsing synth bass, rising pitch tension, fast cuts energy, Bourne Identity chase scene.",

            # --- Ambient / Atmosphere ---
            "ethereal": "50bpm, F major, shimmering pad synths, granular texture clouds, distant female vocal oh, space between sounds, Brian Eno ambient, transcendent.",
            "dreamy": "60bpm, Ab major, lo-fi tape warble, soft Rhodes piano, bedroom reverb, vinyl hiss, floating melody, Tame Impala haze.",
            "meditative": "45bpm, D major, singing bowls, gentle drone, nature field recording, flowing water, bamboo flute, deep breathing space, spa atmosphere.",
            "cosmic": "55bpm, whole tone scale, deep space synthesizer pads, radio static textures, granular time stretching, Interstellar organ, vast emptiness.",

            # --- Modern / Urban ---
            "cyberpunk": "110bpm, F minor, dark synthwave arpeggios, neon atmosphere, Moog bass, analog drum machine, 80s retrofuturism, Kavinsky meets Vangelis.",
            "corporate": "95bpm, G major, clean minimalist synth pulses, subtle marimba, tech startup energy, polished and precise, Apple keynote underscore.",
            "gritty": "85bpm, Eb minor, heavy industrial distorted bass, mechanical percussion, factory ambience, raw visceral texture, Nine Inch Nails documentary.",
            "urban": "90bpm, Cm, lo-fi hip hop beats, muted jazz samples, city rain, subway rumble, coffee shop vinyl, late night study session.",
            "uplifting": "100bpm, A major, bright acoustic guitar, clapping rhythm, warm synth pad, indie film montage, feel-good energy, Little Miss Sunshine.",

            # --- Period / Genre ---
            "jazz_noir": "80bpm, Dm7, walking upright bass, brushed snare, smoky saxophone improvisation, dim bar atmosphere, Miles Davis Kind of Blue.",
            "classical": "Andante, E minor, string quartet, first violin melody, chamber music intimacy, concert hall reverb, Baroque ornaments, Vivaldi elegance.",
            "western": "75bpm, Am, lone acoustic guitar, distant harmonica, desert wind, tumbling percussion, Ennio Morricone whistling, vast landscape.",
            "electronic_minimal": "115bpm, C minor, minimal techno pulse, single repeating synth note evolving, subtle filter sweeps, Berlin club at 4am, Richie Hawtin precision.",
        }
        prompt = vibe_prompts.get(music_vibe.lower(), f"Cinematic ambient music, {music_vibe} mood, slow, atmospheric, film score quality, professional production.")

        # Enhance prompt with real film score references via Tavily
        try:
            from research_engine import research_music_reference
            music_ref = research_music_reference(music_vibe, "")
            if music_ref:
                prompt = f"{prompt}. Reference: {music_ref[:200]}"
                print(f"   [BGM] Enhanced with research reference")
        except Exception:
            pass  # Research is optional

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

# Music mastering presets using Pedalboard or FFmpeg
MUSIC_MASTERING_PRESETS = {
    "none": {"description": "Raw, unmastered"},
    "cinema_master": {
        "description": "Film score mastering — warm, wide, polished",
        "pedalboard": [
            {"type": "highpass", "cutoff": 30},
            {"type": "compressor", "threshold": -18, "ratio": 3},
            {"type": "reverb", "room_size": 0.3, "wet_level": 0.15},
            {"type": "gain", "gain_db": 2},
        ],
        "ffmpeg": "highpass=f=30,acompressor=threshold=-18dB:ratio=3:makeup=2,aecho=0.8:0.9:30:0.15,loudnorm=I=-14:LRA=11:TP=-1.5",
    },
    "lo_fi": {
        "description": "Lo-fi vinyl warmth — tape hiss, reduced bandwidth",
        "pedalboard": [
            {"type": "lowpass", "cutoff": 8000},
            {"type": "distortion", "drive": 3},
            {"type": "reverb", "room_size": 0.2, "wet_level": 0.1},
        ],
        "ffmpeg": "lowpass=f=8000,volume=0.9,aecho=0.8:0.9:15:0.1",
    },
    "epic_wide": {
        "description": "Epic orchestral — wide stereo, boosted lows, compressed peaks",
        "pedalboard": [
            {"type": "highpass", "cutoff": 20},
            {"type": "compressor", "threshold": -14, "ratio": 4},
            {"type": "reverb", "room_size": 0.7, "wet_level": 0.25},
            {"type": "gain", "gain_db": 3},
        ],
        "ffmpeg": "highpass=f=20,bass=gain=3,acompressor=threshold=-14dB:ratio=4:makeup=3,aecho=0.8:0.88:50:0.25,loudnorm=I=-12",
    },
    "intimate_acoustic": {
        "description": "Intimate acoustic — close, warm, minimal processing",
        "pedalboard": [
            {"type": "highpass", "cutoff": 60},
            {"type": "compressor", "threshold": -22, "ratio": 2},
            {"type": "gain", "gain_db": 1},
        ],
        "ffmpeg": "highpass=f=60,acompressor=threshold=-22dB:ratio=2:makeup=1,loudnorm=I=-16",
    },
    "dark_ambient": {
        "description": "Dark ambient — deep, spacious, mysterious",
        "pedalboard": [
            {"type": "lowpass", "cutoff": 6000},
            {"type": "reverb", "room_size": 0.9, "wet_level": 0.4},
            {"type": "delay", "delay": 0.5, "feedback": 0.3},
        ],
        "ffmpeg": "lowpass=f=6000,aecho=0.8:0.88:80:0.4:60:0.3,volume=0.85",
    },
}


def master_music(
    audio_path: str,
    output_path: str,
    preset: str = "cinema_master",
    au_plugin: str = None,
) -> Optional[str]:
    """
    Apply mastering to generated BGM. Uses Pedalboard if available,
    falls back to FFmpeg. Can also apply AU plugins for studio-grade mastering.

    Args:
        audio_path: Input BGM file
        output_path: Output mastered file
        preset: Preset name from MUSIC_MASTERING_PRESETS
        au_plugin: Optional AU plugin name to apply instead of preset
    """
    if au_plugin and PEDALBOARD_AVAILABLE:
        result = apply_au_plugin(audio_path, output_path, au_plugin)
        if result != audio_path:
            return result

    if preset == "none" or preset not in MUSIC_MASTERING_PRESETS:
        return audio_path

    config = MUSIC_MASTERING_PRESETS[preset]

    # Try Pedalboard first (higher quality)
    if PEDALBOARD_AVAILABLE and config.get("pedalboard"):
        result = apply_pedalboard_chain(audio_path, output_path, config["pedalboard"])
        if result != audio_path:
            print(f"   [MASTER] Pedalboard: {preset} → {output_path}")
            return result

    # Fallback to FFmpeg
    if config.get("ffmpeg"):
        import subprocess
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", audio_path, "-af", config["ffmpeg"],
                 "-c:a", "libmp3lame", "-b:a", "192k", output_path],
                capture_output=True, timeout=30,
            )
            if os.path.exists(output_path):
                print(f"   [MASTER] FFmpeg: {preset} → {output_path}")
                return output_path
        except Exception as e:
            print(f"   [MASTER] Failed: {e}")

    return audio_path


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
