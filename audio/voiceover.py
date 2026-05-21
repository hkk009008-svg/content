"""TTS narration, voice-direction profiles, and single-line audio.

Phase 6 slice 5 of the architecture refactor: split the voiceover/narration
TTS surface out of ``phase_b_audio.py`` into this focused submodule.
Multi-character dialogue (``generate_dialogue_voiceover``) remains in
``phase_b_audio.py`` and will move in slice 6.

Contents
========

- ``generate_voiceover``         — main ElevenLabs TTS for a full script.
- ``VOICE_DIRECTIONS``           — delivery-style → voice-parameter dict.
- ``get_voice_direction``        — exact / fuzzy resolver for delivery.
- ``DELIVERY_STYLES``            — sorted list of available delivery keys.
- ``NARRATOR_VOICES``            — dedicated narrator voice pool.
- ``generate_narration``         — narrator voiceover with mood-routed voice.
- ``generate_single_line_audio`` — single dialogue-line TTS (per-shot).

The ElevenLabs client comes from ``audio._client``. ``audio.music`` is
imported eagerly for ``generate_fal_bgm`` (called from
``generate_voiceover`` to spawn the BGM alongside the narration).
"""

from typing import Optional

from elevenlabs import save

from audio._client import client
from audio.music import generate_fal_bgm


def generate_voiceover(ctx: dict) -> bool:
    """
    Takes the text from OmniContext and generates a hyper-realistic audio file.
    """
    text_script = ctx.get("full_text", "")
    music_vibe = ctx.get("music_vibe", "suspense")
    output_filename = "temp_voiceover.mp3"

    print(f"\n🎙️ [PHASE B] Sending script to ElevenLabs (Mood: {music_vibe.upper()})...")

    # Map the script's psychological mood to the perfect physical voice actor.
    # If the mood isn't in the map, fall back to a random pick from the
    # narrator-grade pool below.
    voice_profiles = {
        "suspense": {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (Epic Deep Narrator)"},
        "corporate": {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni (Clean Professional)"},
        "gritty":   {"id": "D38z5RcWu1voky8WS1ja", "name": "Fin (Visceral & Gritty)"},
        "cyberpunk": {"id": "cjVigY5qzO86Huf0OWal", "name": "Eric (Grizzly & Mature)"},
    }

    breathtaking_voices = [
        {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (Epic Deep Narrator)"},
        {"id": "cjVigY5qzO86Huf0OWal", "name": "Eric (Grizzly & Mature)"},
        {"id": "D38z5RcWu1voky8WS1ja", "name": "Fin (Visceral & Gritty)"},
        {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni (Clean Professional)"},
    ]

    import random
    if music_vibe in voice_profiles:
        chosen_actor = voice_profiles[music_vibe]
        print(f"🎭 [PHASE B] Mood-matched Voice Actor: {chosen_actor['name']} (mood={music_vibe})")
    else:
        chosen_actor = random.choice(breathtaking_voices)
        print(f"🎭 [PHASE B] Unmapped mood {music_vibe!r} — random fallback: {chosen_actor['name']}")
    target_voice_id = chosen_actor["id"]

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


def generate_single_line_audio(
    text: str,
    voice_id: str,
    delivery: str = "natural",
    output_path: str = "temp_single_line.mp3",
) -> Optional[str]:
    """
    Generate TTS audio for a SINGLE dialogue line.
    Used for per-shot audio assignment so each shot gets only its character's line.
    """
    from elevenlabs import VoiceSettings

    if not text.strip() or not voice_id:
        return None

    voice_profile = get_voice_direction(delivery)
    directed_text = voice_profile["markup"](text) if voice_profile.get("markup") else text

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
        save(audio, output_path)
        return output_path
    except Exception as e:
        print(f"   ⚠️ Single line TTS failed: {e}")
        return None
