"""Multi-character dialogue voiceover (ElevenLabs TTS + ffmpeg concat).

Contents
========

- ``generate_dialogue_voiceover`` — per-character TTS for a list of
  dialogue lines, concatenated into one MP3 with configurable inter-line
  silence via ffmpeg.
- ``generate_cartesia`` — Cartesia Sonic 2 REST TTS for low-latency
  Korean (and other) prosody; called by ``_resolve_tts_provider`` when
  language routing selects it. Re-introduced cycle-16+ with explicit
  caller integration (Bundle-D 4.3 removed the orphan at commit
  ``48f2a24`` on 2026-05-24 for zero live callers; re-add addresses
  that head-on).

Dependencies (all eager — no cycles):

- ``audio._client.client``               — shared ElevenLabs instance
- ``audio.voiceover.get_voice_direction`` — delivery → voice-param resolver
- ``elevenlabs.save``                    — write streamed audio to disk
- ``requests``                           — Cartesia REST POST

This module is a leaf consumer: nothing in ``audio/*`` imports it.
"""

import os
from typing import TYPE_CHECKING, Optional

import requests
from elevenlabs import save

from audio._client import client
from audio.voiceover import get_voice_direction
from cinema.context import get_project_setting
from config.settings import settings

if TYPE_CHECKING:
    from cinema.context import PipelineContext


# ---------------------------------------------------------------------------
# Cartesia Sonic 2 — low-latency neural TTS (native Korean prosody)
# ---------------------------------------------------------------------------

def generate_cartesia(
    text: str,
    voice_id: str,
    output_path: str,
    language: str = "en",
    model_id: str = "sonic-2",
) -> bool:
    """Generate TTS via Cartesia Sonic 2 REST API. Returns True on success.

    Mirrors the per-line caching pattern of the ElevenLabs path: if
    ``output_path`` already exists this function returns True immediately
    without calling the API. Callers control regeneration by removing
    the file first.

    Args:
        text: text to synthesise
        voice_id: Cartesia voice ID (UUID-shaped strings per Cartesia voice library)
        output_path: where to write the mp3
        language: ISO language code; ``"ko"`` for Korean, ``"en"`` for English.
            Cartesia accepts language hints to bias prosody.
        model_id: Cartesia model identifier (default ``"sonic-2"``)

    Returns:
        ``True`` on success, ``False`` on missing key / HTTP error / timeout /
        format issue. **Never raises** — caller's fallback strategy is to
        route to ElevenLabs on any False return.

    Endpoint: https://docs.cartesia.ai/api-reference/tts/bytes
    """
    # Caller-controlled cache hit
    if os.path.exists(output_path):
        print(f"   [CARTESIA] Cache hit: {output_path}")
        return True

    api_key = settings.cartesia_api_key
    if not api_key:
        print("   [CARTESIA] CARTESIA_API_KEY not set; skipping")
        return False

    try:
        url = "https://api.cartesia.ai/tts/bytes"
        headers = {
            "X-API-Key": api_key,
            "Cartesia-Version": "2024-06-10",
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

        print(f"   [CARTESIA] Generating [language={language}] voice={voice_id[:8]}...")
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()

        # Cartesia bytes endpoint streams audio bytes in the response body.
        with open(output_path, "wb") as f:
            f.write(r.content)
        print(f"   ✅ Cartesia output: {output_path}")
        return True

    except Exception as e:
        print(f"   ⚠️ [CARTESIA] failed: {e}")
        return False


# ---------------------------------------------------------------------------
# TTS provider language router
# ---------------------------------------------------------------------------

def _resolve_tts_provider(scene: dict, character: dict, settings_obj) -> str:
    """Decide which TTS provider to use for this scene-character pair.

    Inspects ``scene["language"]`` first; falls back to
    ``character["language"]``; then to ``settings_obj.language_pref``
    (or ``settings_obj["language_pref"]`` if dict-shaped); defaults to
    ``"en"``. Korean is detected by case-insensitive prefix match on
    ``"ko"`` (matches ``"ko"``, ``"ko_KR"``, ``"korean"``, etc.). When
    Korean is detected AND the Cartesia API key is set, returns
    ``"CARTESIA_SONIC_2"``; otherwise (English, other languages, or
    Cartesia key missing) returns ``"ELEVENLABS"`` — the current default.

    Other languages route to ELEVENLABS multilingual; Cartesia is
    Korean-priority per the descriptor at
    ``domain/scene_decomposer.py:67`` (multilingual fallback is fine but
    ElevenLabs is already wired for non-Korean).

    Args:
        scene: a scene dict (may contain ``"language"`` as an ISO code or
            human name like ``"Korean"``)
        character: a character dict (may contain ``"language"`` as fallback)
        settings_obj: the project settings instance (must expose
            ``cartesia_api_key``; may also expose ``language_pref`` as
            project-wide fallback when scene/character lack ``language``)

    Returns:
        ``"CARTESIA_SONIC_2"`` for Korean+key-set; ``"ELEVENLABS"`` otherwise.
    """
    scene = scene or {}
    character = character or {}
    # Settings-level project-wide fallback: read .language_pref (attr) or
    # ["language_pref"] (dict) when scene/character don't specify a language.
    settings_lang = ""
    if settings_obj is not None:
        settings_lang = (
            getattr(settings_obj, "language_pref", None)
            or (settings_obj.get("language_pref") if isinstance(settings_obj, dict) else None)
            or ""
        )
    raw_lang = (
        scene.get("language")
        or character.get("language")
        or settings_lang
        or "en"
    )
    lang = str(raw_lang).lower().strip()
    is_korean = lang.startswith("ko")
    if is_korean and getattr(settings_obj, "cartesia_api_key", "") and settings_obj.cartesia_api_key:
        return "CARTESIA_SONIC_2"
    # Dict-shaped settings (e.g. project["global_settings"]) — same key access shape.
    if is_korean and isinstance(settings_obj, dict) and settings_obj.get("cartesia_api_key"):
        return "CARTESIA_SONIC_2"
    return "ELEVENLABS"


def _try_dialogue_mode(
    dialogue_lines: list,
    characters: list,
    output_filename: str,
    ctx: "Optional[PipelineContext]" = None,
) -> Optional[str]:
    """ElevenLabs v3 Dialogue Mode — single-call multi-speaker generation.

    Uses ElevenLabs' dedicated dialogue endpoint which produces natural
    turn-taking, prosody continuity across lines, and cross-talk hints —
    far better than per-line concatenation when 2+ speakers are present.

    Returns None on any failure (gated setting off, endpoint missing in
    installed SDK version, API error). Caller falls through to the legacy
    per-line loop, so quality never regresses.

    `ctx` is the PipelineContext carrying `global_settings`. When None,
    the dialogue_mode_enabled gate defaults to True.
    """
    # Gate: only run when explicitly enabled
    if not get_project_setting(ctx, "dialogue_mode_enabled", True):
        return None

    # Need at least 2 distinct speakers for dialogue mode to make sense
    distinct_speakers = {ln.get("character_id") for ln in dialogue_lines if ln.get("text", "").strip()}
    if len(distinct_speakers) < 2:
        return None

    char_voices = {c["id"]: c.get("voice_id", "") for c in characters}

    # Build the inputs payload — ordered list of {text, voice_id}
    inputs = []
    for ln in dialogue_lines:
        text = ln.get("text", "").strip()
        if not text:
            continue
        cid = ln.get("character_id", "")
        voice_id = char_voices.get(cid, "")
        if not voice_id:
            # Can't run dialogue mode without explicit voices — bail to fallback
            return None
        inputs.append({"text": text, "voice_id": voice_id})

    if len(inputs) < 2:
        return None

    print(f"🎙️ [DIALOGUE-MODE] Trying ElevenLabs v3 Dialogue Mode ({len(inputs)} turns)...")

    # Defensively try the dialogue endpoint. SDK field names can drift across
    # versions; we attempt the most likely names and fall through on any miss.
    try:
        # Preferred (eleven_v3 dialogue endpoint)
        audio = client.text_to_dialogue.convert(
            inputs=inputs,
            model_id="eleven_v3",
            output_format="mp3_44100_128",
        )
    except (AttributeError, TypeError):
        # Older SDK shape — fall through to legacy per-line generation
        print("   [DIALOGUE-MODE] text_to_dialogue endpoint not in installed SDK; using per-line path.")
        return None
    except Exception as e:
        print(f"   [DIALOGUE-MODE] dialogue endpoint failed ({e}); using per-line path.")
        return None

    try:
        save(audio, output_filename)
    except Exception as e:
        print(f"   [DIALOGUE-MODE] save failed: {e}")
        return None

    print(f"   ✅ Dialogue Mode output: {output_filename}")
    return output_filename


def _maybe_save_alignment(
    audio_path: str,
    transcript_hint: Optional[str] = None,
    language: Optional[str] = None,
    ctx: "Optional[PipelineContext]" = None,
) -> Optional[str]:
    """Emit a .alignment.json sidecar next to the audio file when enabled.

    Driven by `forced_alignment_enabled` in the per-project global_settings
    on `ctx`. Returns the JSON path on success, None when disabled or
    alignment fails. Downstream consumers (lipsync, SRT writer) load
    these sidecars when present.

    language: project language name. When None, reads from ctx's
    `language` setting. Critical for Korean/Japanese/Chinese — whisper
    drifts badly on these languages without an explicit hint.
    """
    if not get_project_setting(ctx, "forced_alignment_enabled", False):
        return None
    if language is None:
        language = get_project_setting(ctx, "language", "English") or "English"
    try:
        from audio.alignment import align_audio_to_text, save_alignment_json
    except Exception:
        return None
    result = align_audio_to_text(audio_path, transcript_hint=transcript_hint, language=language)
    if not result or not result.words:
        return None
    json_path = os.path.splitext(audio_path)[0] + ".alignment.json"
    save_alignment_json(result, json_path)
    print(f"   📐 Forced alignment ({result.provider}, {len(result.words)} words, lang={language}) → {json_path}")
    return json_path


def generate_dialogue_voiceover(
    dialogue_lines: list,
    characters: list,
    output_filename: str = "temp_dialogue_voiceover.mp3",
    pause_between_lines: float = 0.3,
    ctx: "Optional[PipelineContext]" = None,
) -> Optional[str]:
    """
    Multi-character dialogue voiceover for cinema production.

    PATH 1 (preferred when enabled and 2+ speakers): ElevenLabs v3 Dialogue
    Mode — single-call generation with natural turn-taking and prosody
    continuity. Far better than per-line concat for conversation scenes.

    PATH 2 (legacy / fallback): Generate separate audio per character using
    their assigned voice_id, then concatenate in dialogue order with pauses.

    Both paths emit an optional `.alignment.json` sidecar with word-level
    timestamps when forced_alignment_enabled is set.

    Args:
        dialogue_lines: List of {character_id, text, delivery}
        characters: List of character dicts with 'id' and 'voice_id'
        output_filename: Output MP3 path
        pause_between_lines: Silence between lines in seconds (PATH 2 only)

    Returns:
        Path to assembled dialogue audio, or None on failure
    """
    # PATH 1: try ElevenLabs Dialogue Mode first
    dm_result = _try_dialogue_mode(dialogue_lines, characters, output_filename, ctx=ctx)
    if dm_result:
        transcript_hint = " ".join(ln.get("text", "").strip() for ln in dialogue_lines)
        _maybe_save_alignment(dm_result, transcript_hint=transcript_hint, ctx=ctx)
        return dm_result

    # PATH 2: legacy per-line generation
    from elevenlabs import VoiceSettings

    char_voices = {c["id"]: c.get("voice_id", "") for c in characters}
    char_by_id = {c["id"]: c for c in characters}
    temp_files = []

    # Build a scene-shaped dict from the project's language setting (via
    # PipelineContext.global_settings) so _resolve_tts_provider can read it.
    # The pipeline stores language in global_settings (see cinema_pipeline.py
    # :512-513); this surface keeps the router signature scene-shaped while
    # honoring the actual source-of-truth. I-B1 closure: also accept the
    # brief's `language_pref` alias as fallback — was unbound in code; now
    # both `language` (canonical) and `language_pref` (brief alias) route.
    project_lang = (
        get_project_setting(ctx, "language", None)
        or get_project_setting(ctx, "language_pref", None)
        or "English"
    )
    scene_for_router = {"language": project_lang}

    print(f"🎙️ [CINEMA] Generating multi-character dialogue ({len(dialogue_lines)} lines)...")

    for i, line in enumerate(dialogue_lines):
        cid = line.get("character_id", "")
        text = line.get("text", "")
        if not text.strip():
            continue

        voice_id = char_voices.get(cid, "")
        if not voice_id:
            # Fallback chain (closes VG-B1 — prior code hardcoded
            # "pNInz6obpgDQGcFmaJgB" = Adam English-male; produced wrong-
            # gendered + wrong-language audio for projects where
            # character.voice_id was never assigned at create-time):
            #   1. Any other character's assigned voice in this project
            #   2. Language + gender-aware default from language_defaults
            #      (Korean female → 안나 Anna; Korean male → 준호 Junho;
            #       English → Rachel / Adam; unknown language → English
            #       fallback per get_language_defaults("_default"))
            #   3. Adam (legacy hardcode) — only when import fails
            voice_id = next((v for v in char_voices.values() if v), "")
            if not voice_id:
                try:
                    from domain.language_defaults import get_language_defaults
                    char_record = char_by_id.get(cid, {})
                    char_gender = (char_record.get("gender") or "").lower()
                    lang_defaults = get_language_defaults(project_lang)
                    # Default to female voice unless character has explicit
                    # male gender hint. Female default is closer to common
                    # narrative cinema use than the prior unconditional
                    # male hardcode.
                    if char_gender in {"male", "m", "man"}:
                        voice_id = lang_defaults.get("default_male_voice", "")
                    else:
                        voice_id = lang_defaults.get("default_female_voice", "")
                except Exception:
                    pass
            if not voice_id:
                voice_id = "pNInz6obpgDQGcFmaJgB"  # legacy hardcode last resort

        char_name = next((c["name"] for c in characters if c["id"] == cid), cid)
        delivery = line.get("delivery", "natural")

        # Voice direction system — maps delivery to precise voice parameters + text markup
        voice_profile = get_voice_direction(delivery)
        directed_text = voice_profile["markup"](text) if voice_profile.get("markup") else text

        temp_path = f"temp_dialogue_line_{i}.mp3"

        # Route per-line: language-aware provider selection. Korean +
        # CARTESIA_API_KEY set → Cartesia Sonic 2 (native prosody, low
        # latency). Everything else → ElevenLabs (unchanged path).
        char_record = char_by_id.get(cid, {})
        provider = _resolve_tts_provider(scene_for_router, char_record, settings)
        cartesia_ok = False
        if provider == "CARTESIA_SONIC_2":
            # Cartesia's language field expects an ISO code; map the project
            # language name to "ko" when Korean, else pass the raw value
            # lowercased. The dispatcher already routed correctly upstream
            # so this is just the API param shape.
            lang_for_api = "ko" if str(project_lang).lower().startswith("ko") else str(project_lang).lower()[:2] or "en"
            cartesia_ok = generate_cartesia(
                text=directed_text,
                voice_id=voice_id,
                output_path=temp_path,
                language=lang_for_api,
            )
            if cartesia_ok:
                # Best-effort cost tracking — Cartesia call succeeded; record
                # spend so cycle-16 Tier C budget reflects Korean dialogue
                # accurately. Closes I-2 from cycle-15 code-quality review
                # (`docs/BRIEF-comprehensive-test-2026-05-27.md` v0.9.7 PR-DIALOGUE
                # failure mode #3 noted record_api_call was not wired). Note:
                # ElevenLabs path remains pre-existing untracked (no entry in
                # `API_COST_USD`; no callers across codebase) — adding ElevenLabs
                # tracking is symmetric improvement deferred to v0.9.X+.
                try:
                    from cost_tracker import CostTracker
                    CostTracker().record_api_call(
                        "CARTESIA_SONIC_2",
                        operation="dialogue_tts",
                    )
                except Exception:
                    # Cost tracking is best-effort; the TTS itself succeeded.
                    print(f"   [CARTESIA] cost record skipped for line {i+1} (non-critical)")
                temp_files.append(temp_path)
                print(f"   ✅ Line {i+1}: {char_name} ({delivery}) → {temp_path} [Cartesia]")
                continue
            # Cartesia failed (False return) — fall through to ElevenLabs
            print(f"   [CARTESIA] failed for line {i+1}; falling back to ElevenLabs")

        # ElevenLabs path (default OR Cartesia fallback)
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

        # Optional sidecar — word-level timestamps for downstream lipsync precision
        transcript_hint = " ".join(ln.get("text", "").strip() for ln in dialogue_lines)
        _maybe_save_alignment(output_filename, transcript_hint=transcript_hint, ctx=ctx)

        return output_filename

    except Exception as e:
        print(f"   ⚠️ Dialogue concatenation failed: {e}")
        # Return last generated file as fallback
        return temp_files[0] if temp_files else None
