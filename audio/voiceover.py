"""Voice-direction profiles + delivery-style resolver.

Contents
========

- ``VOICE_DIRECTIONS``    — delivery-style → voice-parameter dict
                            (stability / similarity / style / speaker_boost / description).
- ``get_voice_direction`` — exact + fuzzy-keyword resolver for delivery strings.
- ``DELIVERY_STYLES``     — sorted list of available delivery keys, surfaced to the
                            frontend dropdown.

The TTS-generation functions (``generate_voiceover``, ``generate_narration``,
``generate_single_line_audio``, ``generate_tts_routed``, ``generate_openai_audio``,
``generate_cartesia``) were removed on 2026-05-24 (Bundle-D 4.3) — they were
orphaned post-pivot with zero live callers. The dialogue path
(``audio.dialogue.generate_dialogue_voiceover``) is the actual orchestrator-
wired TTS entry; it consumes ``get_voice_direction`` from this module.
``VOICE_DIRECTIONS`` is also re-exported through web_server.py for the UI
voice-style dropdown.
"""

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
