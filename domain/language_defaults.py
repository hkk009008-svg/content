"""Per-language pipeline defaults.

When a project's dialogue language is set, the BEST quality settings differ
from English defaults:

  - Some TTS providers have native-language training (ElevenLabs v3 Korean,
    Cartesia Sonic 2 Korean, etc.) — pick those over multilingual fallbacks.
  - Voice pool filter — surface only voices that sound native in the target
    language.
  - Lipsync engine priority — most are language-agnostic (audio-driven), but
    a few (MuseTalk) were trained primarily on English/Chinese and produce
    weaker results on Korean phonemes. Reorder to lead with multi-language
    engines (Hedra C3, sync.so v3).
  - Per-purpose API ranking — for dialogue purposes, prefer engines with
    proven non-English performance.

PHILOSOPHY
----------
Apply defaults on language CHANGE (not silently every save). User customizations
override these — defaults seed sensible starting points, not lock-in.

WHY TTS+LIPSYNC IS PREFERRED FOR KOREAN OVER NATIVE-AUDIO VIDEO
---------------------------------------------------------------
Native-audio video models (Veo 3.1, Sora 2) generate the audio alongside the
video for perfect sync-by-construction. But for Korean dialogue specifically:

  - ElevenLabs v3 Korean voices have native prosody training. Veo 3.1's Korean
    audio is generic and less expressive.
  - Voice cloning is impossible with native-audio video — every character
    sounds whatever the model emits. ElevenLabs lets you assign different
    voices per character for cinematic consistency.
  - Native-audio video gives no per-line delivery control (whispered, urgent,
    sarcastic). ElevenLabs v3 has 40+ delivery styles.
  - Hedra Character-3 lipsync (Q=0.93) handles Korean phonemes well — sync
    quality is high enough that the two-stage approach matches native-audio.

USE NATIVE-AUDIO VIDEO (Veo 3.1) WHEN:
  - Single short clip with no recurring character (one-off establishing dialogue)
  - Extreme phoneme-level sync precision matters more than voice character
  - You want to skip the lipsync stage entirely for speed
"""

from __future__ import annotations

from typing import Optional


PIPELINE_LANGUAGE_DEFAULTS = {
    "English": {
        # English defaults — what the codebase has been tuned for
        "tts_provider": "ELEVENLABS_V3",
        "dialogue_mode_enabled": True,
        "forced_alignment_enabled": True,
        "lipsync_engine_priority": ["HEDRA_C3", "SYNC_SO_V3", "MUSETALK", "LATENTSYNC", "OMNIHUMAN_V1_5", "SYNC_V2"],
        "lipsync_quality_validation": True,
        "lipsync_validation_threshold": 0.65,
        # Per-purpose video API picks for dialogue
        "dialogue_video_api": "KLING_NATIVE",
        # Voice pool filter — voice categories to surface in pickers
        "voice_pool_filter": None,  # None = no filter, all voices
        # Recommended character voices (auto-assigned for new characters)
        "default_male_voice": "pNInz6obpgDQGcFmaJgB",    # Adam
        "default_female_voice": "21m00Tcm4TlvDq8ikWAM", # Rachel
    },

    "Korean": {
        # Korean-optimized defaults — best quality path documented above
        "tts_provider": "ELEVENLABS_V3",          # Korean voices have native prosody
        "dialogue_mode_enabled": True,            # multi-speaker Korean works well
        "forced_alignment_enabled": True,         # WhisperX has Korean wav2vec2
        # Hedra leads (multi-language native). MuseTalk demoted (English/Chinese-trained).
        "lipsync_engine_priority": ["HEDRA_C3", "SYNC_SO_V3", "LATENTSYNC", "OMNIHUMAN_V1_5", "MUSETALK", "SYNC_V2"],
        "lipsync_quality_validation": True,
        # Slightly stricter gate for Korean — phoneme set is narrower so misses
        # are more obvious to native speakers
        "lipsync_validation_threshold": 0.70,
        # For Korean dialogue close-ups, Kling 3.0 + Hedra C3 is the gold path.
        # Veo 3.1 native-audio is a strong second when you need built-in sync.
        "dialogue_video_api": "KLING_NATIVE",
        "voice_pool_filter": ["korean_woman", "korean_man"],
        "default_male_voice": "1W00IGEmNmwmsDeYy7ag",    # 준호 (Junho) — deep narrator
        "default_female_voice": "uyVNoMrnUku1dZyVEXwD", # 안나 (Anna) — warm conversational
    },

    "Japanese": {
        "tts_provider": "ELEVENLABS_V3",
        "dialogue_mode_enabled": True,
        "forced_alignment_enabled": True,
        "lipsync_engine_priority": ["HEDRA_C3", "SYNC_SO_V3", "LATENTSYNC", "OMNIHUMAN_V1_5", "MUSETALK"],
        "lipsync_quality_validation": True,
        "lipsync_validation_threshold": 0.70,
        "dialogue_video_api": "KLING_NATIVE",
        "voice_pool_filter": None,  # no JP-tagged voices in pool yet
        "default_male_voice": "pNInz6obpgDQGcFmaJgB",
        "default_female_voice": "21m00Tcm4TlvDq8ikWAM",
    },

    "Mandarin": {
        "tts_provider": "ELEVENLABS_V3",
        "dialogue_mode_enabled": True,
        "forced_alignment_enabled": True,
        # MuseTalk back to higher priority — its training set included Chinese
        "lipsync_engine_priority": ["HEDRA_C3", "MUSETALK", "SYNC_SO_V3", "LATENTSYNC", "OMNIHUMAN_V1_5"],
        "lipsync_quality_validation": True,
        "lipsync_validation_threshold": 0.65,
        "dialogue_video_api": "KLING_NATIVE",
        "voice_pool_filter": None,
        "default_male_voice": "pNInz6obpgDQGcFmaJgB",
        "default_female_voice": "21m00Tcm4TlvDq8ikWAM",
    },

    # Fallback for languages we haven't tuned individually. Multilingual ElevenLabs
    # v3 + Hedra is universally reasonable — most failure modes only show up
    # under native-speaker scrutiny.
    "_default": {
        "tts_provider": "ELEVENLABS_V3",
        "dialogue_mode_enabled": True,
        "forced_alignment_enabled": True,
        "lipsync_engine_priority": ["HEDRA_C3", "SYNC_SO_V3", "LATENTSYNC", "OMNIHUMAN_V1_5", "MUSETALK"],
        "lipsync_quality_validation": True,
        "lipsync_validation_threshold": 0.65,
        "dialogue_video_api": "KLING_NATIVE",
        "voice_pool_filter": None,
        "default_male_voice": "pNInz6obpgDQGcFmaJgB",
        "default_female_voice": "21m00Tcm4TlvDq8ikWAM",
    },
}


def get_language_defaults(language: str) -> dict:
    """Return the recommended settings block for a language. Falls back to
    _default for unknown languages. Caller decides whether to apply them.
    """
    return dict(PIPELINE_LANGUAGE_DEFAULTS.get(language, PIPELINE_LANGUAGE_DEFAULTS["_default"]))


# Fields that get copied into project.global_settings when defaults are applied.
# The 'voice_pool_filter' and 'default_male_voice' / 'default_female_voice' are
# UI hints, not settings the pipeline reads directly — they shape the voice
# picker without forcing voice assignments on existing characters.
APPLIED_SETTINGS_FIELDS = (
    "tts_provider",
    "dialogue_mode_enabled",
    "forced_alignment_enabled",
    "lipsync_engine_priority",
    "lipsync_quality_validation",
    "lipsync_validation_threshold",
)


def merge_language_defaults_into_settings(
    settings: dict,
    language: str,
    overwrite_existing: bool = False,
) -> tuple[dict, list[str]]:
    """Merge language-optimized defaults into a settings dict.

    Args:
        settings: project.global_settings (mutated in place + returned)
        language: target language name
        overwrite_existing: when False (default), only writes fields the user
            hasn't customized. When True, overwrites everything — useful for
            "Apply defaults" button that user confirmed.

    Returns: (settings, list of fields that were actually changed).
    """
    defaults = get_language_defaults(language)
    changed: list[str] = []
    for field in APPLIED_SETTINGS_FIELDS:
        if field not in defaults:
            continue
        new_value = defaults[field]
        current = settings.get(field)
        if overwrite_existing or current is None:
            if current != new_value:
                settings[field] = new_value
                changed.append(field)
    # Always persist the language itself
    if settings.get("language") != language:
        settings["language"] = language
        changed.append("language")
    return settings, changed


def get_voice_pool_filter(language: str) -> Optional[list]:
    """Voice category filter for the UI. Returns the list of category prefixes
    to show in voice pickers, or None for no filter.
    """
    return get_language_defaults(language).get("voice_pool_filter")


def recommended_voices_for_language(language: str, voice_pool: list) -> dict:
    """Pick reasonable default male/female voice IDs for a language.
    Returns: {"male": voice_id, "female": voice_id, "available_count": N}
    """
    defaults = get_language_defaults(language)
    filt = defaults.get("voice_pool_filter")
    if filt:
        matching = [v for v in voice_pool if v.get("category") in filt]
    else:
        matching = voice_pool
    return {
        "male": defaults.get("default_male_voice"),
        "female": defaults.get("default_female_voice"),
        "available_count": len(matching),
    }
