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
from config.settings import settings


# ---------------------------------------------------------------------------
# Alternate TTS providers — OpenAI gpt-4o-audio + Cartesia Sonic 2
# ---------------------------------------------------------------------------
# These slot in as drop-in replacements for generate_voiceover when the
# project's `tts_provider` setting picks one of them. Each is defensive:
# returns None on any failure so callers fall back to ElevenLabs gracefully.

# OpenAI gpt-4o-audio voices (10 voices, multilingual including Korean)
OPENAI_AUDIO_VOICES = {
    "alloy":   "neutral, balanced — default narrator voice",
    "ash":     "warm, conversational",
    "ballad":  "expressive, dramatic — good for emotional dialogue",
    "coral":   "bright, friendly woman",
    "echo":    "deep, mature man",
    "fable":   "story-telling, animated",
    "onyx":    "deep, authoritative man",
    "nova":    "young, energetic woman",
    "sage":    "calm, thoughtful — narration",
    "shimmer": "warm, soothing woman",
}


def generate_openai_audio(
    text: str,
    output_filename: str,
    voice: str = "alloy",
    audio_format: str = "mp3",
    instructions: Optional[str] = None,
) -> Optional[str]:
    """Generate audio via OpenAI's gpt-4o-audio-preview model.

    Pros vs ElevenLabs: more expressive on long-form prose, accepts plain
    English instructions ("speak slowly, like reading bedtime stories") that
    shape delivery. Multilingual including Korean.

    Cons: only 10 fixed voices (no cloning), per-minute pricing higher than
    ElevenLabs at scale.

    Args:
        text: dialogue line or narration to speak
        output_filename: path to write audio (mp3 by default)
        voice: one of OPENAI_AUDIO_VOICES keys
        audio_format: 'mp3' | 'wav' | 'flac' | 'opus' | 'pcm16'
        instructions: optional natural-language delivery directive (e.g.,
            "whispered, urgent")

    Returns the output path on success, None on failure.
    """
    import base64

    api_key = settings.openai_api_key
    if not api_key:
        print("   [OPENAI-AUDIO] OPENAI_API_KEY not set; skipping")
        return None

    try:
        import openai
        oa = openai.OpenAI(api_key=api_key)

        messages = []
        if instructions:
            messages.append({"role": "system", "content": instructions})
        messages.append({"role": "user", "content": f"Please say exactly: {text}"})

        response = oa.chat.completions.create(
            model="gpt-4o-audio-preview",
            modalities=["text", "audio"],
            audio={"voice": voice, "format": audio_format},
            messages=messages,
        )

        audio_b64 = response.choices[0].message.audio.data
        audio_bytes = base64.b64decode(audio_b64)
        with open(output_filename, "wb") as f:
            f.write(audio_bytes)

        print(f"   ✅ OpenAI gpt-4o-audio ({voice}): {output_filename}")
        return output_filename
    except Exception as e:
        print(f"   [OPENAI-AUDIO] failed: {e}")
        return None


# Cartesia Sonic 2 voice IDs from their public library. Replace with your own
# cloned voices for production.
CARTESIA_DEFAULT_VOICES = {
    "narrator_en":  "a0e99841-438c-4a64-b679-ae501e7d6091",
    "narrator_ko":  "57e5dba7-44df-4d44-b85f-7c40c92e1e9e",  # Korean multilingual
    "warm_female":  "79a125e8-cd45-4c13-8a67-188112f4dd22",
    "deep_male":    "421b3369-f63f-4b03-8980-37a44df1d4e8",
    "young_female": "f6141af3-5f94-418c-80ed-a45d450e7e2e",
}


def generate_cartesia(
    text: str,
    output_filename: str,
    voice_id: str = CARTESIA_DEFAULT_VOICES["narrator_en"],
    model_id: str = "sonic-2",
    language: str = "en",
    speed: str = "normal",
) -> Optional[str]:
    """Generate audio via Cartesia Sonic 2 — low-latency streaming TTS.

    Pros: ~75ms time-to-first-byte (real-time during editing), native
    multilingual including Korean, supports speed modifiers.

    Cons: smaller voice library than ElevenLabs, no built-in cloning on the
    free tier.

    Args:
        text: line to synthesize
        output_filename: write target (mp3)
        voice_id: Cartesia voice UUID
        model_id: "sonic-2" (recommended) | "sonic" (legacy)
        language: ISO 639-1 code — "en" | "ko" | "ja" | "zh" | etc.
        speed: "slow" | "normal" | "fast"

    Returns the output path on success, None on failure.
    """
    import requests

    api_key = settings.cartesia_api_key
    if not api_key:
        print("   [CARTESIA] CARTESIA_API_KEY not set; skipping")
        return None

    try:
        url = "https://api.cartesia.ai/tts/bytes"
        headers = {
            "X-API-Key": api_key,
            "Cartesia-Version": "2024-11-13",
            "Content-Type": "application/json",
        }
        payload = {
            "model_id": model_id,
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "output_format": {
                "container": "mp3",
                "sample_rate": 44100,
                "bit_rate": 128000,
            },
            "language": language,
        }
        if speed in ("slow", "fast"):
            payload["experimental_controls"] = {"speed": speed}

        r = requests.post(url, json=payload, headers=headers, timeout=30)
        if r.status_code != 200:
            print(f"   [CARTESIA] HTTP {r.status_code}: {r.text[:200]}")
            return None
        with open(output_filename, "wb") as f:
            f.write(r.content)
        print(f"   ✅ Cartesia Sonic 2 ({language}): {output_filename}")
        return output_filename
    except Exception as e:
        print(f"   [CARTESIA] failed: {e}")
        return None


def generate_tts_routed(
    text: str,
    output_filename: str,
    voice_id: Optional[str] = None,
    delivery: str = "natural",
    language: Optional[str] = None,
    provider: Optional[str] = None,
) -> Optional[str]:
    """TTS router — picks the engine based on settings.tts_provider (or override).

    Order of resolution for provider:
      1. explicit `provider` kwarg
      2. settings.tts_provider (set via SettingsPanel)
      3. ELEVENLABS_V3 (default)

    Each provider falls through to ElevenLabs on failure so the pipeline
    never blocks. Voice ID handling differs per provider:
      - ELEVENLABS_V3:    ElevenLabs voice ID (default Adam)
      - CARTESIA_SONIC_2: Cartesia voice UUID
      - OPENAI_AUDIO:     one of OPENAI_AUDIO_VOICES keys ("alloy", "onyx", etc.)
    """
    if not provider:
        # Defensive default — primary read of tts_provider now happens at the
        # caller (generate_voiceover) via get_project_setting(ctx, ...). If a
        # standalone caller forgets to pass `provider`, this defaults to EL.
        provider = "ELEVENLABS_V3"

    if language is None:
        language = "English"
    # Covers the 12 languages claimed in GlobalSettings.language. Add new
    # entries here when the project's language set grows — silently defaulting
    # to "en" would route (e.g.) Korean dialogue to an English voice.
    lang_iso = {
        "english": "en", "korean": "ko", "japanese": "ja",
        "mandarin": "zh", "chinese": "zh",
        "spanish": "es", "french": "fr", "german": "de",
        "italian": "it", "portuguese": "pt", "russian": "ru",
        "hindi": "hi", "arabic": "ar",
    }.get(language.lower().strip(), "en")

    # Try the requested provider; fall through to ElevenLabs on failure
    if provider == "CARTESIA_SONIC_2":
        cv = voice_id or (CARTESIA_DEFAULT_VOICES["narrator_ko"] if lang_iso == "ko"
                          else CARTESIA_DEFAULT_VOICES["narrator_en"])
        result = generate_cartesia(text, output_filename, voice_id=cv, language=lang_iso)
        if result:
            return result
        print("   [TTS-ROUTER] Cartesia failed; falling back to ElevenLabs")

    elif provider == "OPENAI_AUDIO":
        ov = voice_id if voice_id in OPENAI_AUDIO_VOICES else "alloy"
        result = generate_openai_audio(text, output_filename, voice=ov,
                                        instructions=f"Speak with {delivery} delivery in {language}")
        if result:
            return result
        print("   [TTS-ROUTER] OpenAI Audio failed; falling back to ElevenLabs")

    # ELEVENLABS_V3 default + fallback path
    try:
        from elevenlabs import VoiceSettings
        voice_profile = get_voice_direction(delivery)
        directed = voice_profile["markup"](text) if voice_profile.get("markup") else text
        audio = client.text_to_speech.convert(
            voice_id=voice_id or "pNInz6obpgDQGcFmaJgB",  # Adam default
            output_format="mp3_44100_128",
            text=directed,
            model_id="eleven_v3",
            voice_settings=VoiceSettings(
                stability=voice_profile["stability"],
                similarity_boost=voice_profile["similarity"],
                style=voice_profile["style"],
                use_speaker_boost=voice_profile.get("speaker_boost", True),
            ),
        )
        save(audio, output_filename)
        return output_filename
    except Exception as e:
        print(f"   [TTS-ROUTER] ElevenLabs fallback also failed: {e}")
        return None


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
        # Read the UI's tts_provider knob via the canonical helper —
        # `config.settings.Settings` does NOT carry per-project UI choices.
        from cinema.context import get_project_setting
        provider = get_project_setting(ctx, "tts_provider", "ELEVENLABS_V3")
        language = ctx.get("language") if hasattr(ctx, "get") else None

        if provider != "ELEVENLABS_V3":
            # Honor the UI's tts_provider knob (Cartesia, OpenAI Audio). voice_id
            # is left None: target_voice_id above is an ElevenLabs ID, not portable
            # across providers, so let the router pick its provider-specific default.
            routed = generate_tts_routed(
                text=text_script,
                output_filename=output_filename,
                voice_id=None,
                delivery="dramatic_narration",
                language=language,
                provider=provider,
            )
            if not routed:
                print(f"❌ TTS routing failed for provider={provider}")
                return False
        else:
            # Default ElevenLabs path — keeps the tuned VoiceSettings for narration.
            from elevenlabs import VoiceSettings
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
