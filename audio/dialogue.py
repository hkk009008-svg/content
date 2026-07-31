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

import hashlib
import json
import os
import re
import subprocess
import warnings
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
# Character-filter helpers (ticket T-E)
# ---------------------------------------------------------------------------

def scene_characters(all_characters: list, scene: dict) -> list:
    """Return the subset of all_characters whose id appears in scene["characters_present"].

    Scene audio is a SCENE-scoped artifact: ``dialogue_cache_key`` hashes the
    (id, voice_id) pairs of the characters list, so scene audio MUST be keyed
    with the scene-level character subset — exactly matching the pipeline writer
    at ``cinema_pipeline.py:738-741``.  Passing a narrower in-frame subset
    re-keys the artifact → paid TTS regen + off-frame lines voiced via the
    wrong character (9aed3ce bug class).

    ``or []`` guards are intentional: strictly more robust than
    ``.get(key, [])`` for the ``None``-valued case.
    """
    ids = (scene or {}).get("characters_present") or []
    return [c for c in (all_characters or []) if c.get("id") in ids]


def shot_characters(all_characters: list, shot: dict, scene: dict) -> list:
    """Return the subset of all_characters visible in this shot.

    Shot audio is a SHOT-scoped artifact keyed by in-frame characters
    (``shot["characters_in_frame"]``), falling back to the scene's
    ``characters_present`` when the shot does not carry an in-frame list.

    ``or []`` guards: same rationale as ``scene_characters`` above.
    """
    ids = (shot or {}).get("characters_in_frame") or (scene or {}).get("characters_present") or []
    return [c for c in (all_characters or []) if c.get("id") in ids]


# ---------------------------------------------------------------------------
# Content-hash key helper (ticket T-B)
# ---------------------------------------------------------------------------

def dialogue_cache_key(dialogue_lines: list, characters: list, language: str) -> str:
    """12-hex content key for a rendered dialogue-audio artifact.

    Keyed on what determines the rendered audio: the final dialogue lines,
    each character's (id, voice_id) assignment, and the project language.
    Same inputs -> same key -> the artifact on disk is reusable; any edit
    to a line/voice/language changes the key (ticket T-B).

    Never raises on odd input shapes — default=str handles non-serialisable
    values so callers do not need to sanitise before calling.

    Assumption (T-B review note): ``pause_between_lines`` (inter-line
    silence) is NOT part of the key — all production callers use the
    default. Fold it into the payload if it ever becomes configurable.
    """
    payload = {
        "lines": dialogue_lines,
        "voices": sorted(
            (c.get("id", "") if isinstance(c, dict) else "",
             c.get("voice_id", "") if isinstance(c, dict) else "")
            for c in (characters or [])
        ),
        "lang": language,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    return digest[:12]


def _line_cache_key(text: str, voice_id: str, language: str) -> str:
    """12-hex content key for a single dialogue line's rendered audio.

    Keyed on the rendered text (post-direction markup), the ORIGINAL
    (pre-Cartesia-resolved) voice_id so the key is provider-independent,
    and the project language. Used for per-line temp files (ticket T-B).
    """
    payload = {"text": text, "voice_id": voice_id, "lang": language}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    return digest[:12]


# ---------------------------------------------------------------------------
# Cartesia Sonic 2 — low-latency neural TTS (native Korean prosody)
# ---------------------------------------------------------------------------

def generate_cartesia(
    text: str,
    voice_id: str,
    output_path: str,
    language: str = "en",
    model_id: str = "sonic-3.5",
) -> bool:
    """Generate TTS via the Cartesia REST API. Returns True on success.

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
        model_id: Cartesia model identifier (default ``"sonic-3.5"``).
            MIGRATED from ``"sonic-2"`` on 2026-08-01, ahead of its
            2026-10-20 sunset (docs.cartesia.ai/build-with-cartesia/
            tts-models/api-changes). The swap was held until it had evidence,
            because Korean prosody is product-critical here and a provider's
            "current recommended default" is a marketing claim, not a
            measurement.
            Evidence: ``scripts/measure_cartesia_prosody.py`` (committed
            instrument, R-MEASURE) + ``logs/cartesia-prosody-*.json``. On the
            project's own Korean voice, sonic-3.5 renders the same line at
            151.1 wpm vs sonic-2's 129.8, with silence ratio 0.128 vs 0.208 at
            unchanged loudness; the English control moves identically, so the
            difference is the MODEL, not Korean handling. 151 wpm also sits
            near ``dialogue_target_wpm``'s 145 default, so the downstream
            pacing pass has less stretching to do.
            The numbers did not decide it: the retained .wav pairs under
            ``logs/cartesia-prosody-20260801/`` were listened to, and the
            user-principal chose sonic-3.5. Naturalness is a human call —
            see the 2026-07-18 precedent where an audio proxy contradicted
            the listener and the proxy was wrong.
            NOTE the routing key ``CARTESIA_SONIC_2`` is deliberately
            unchanged: it is a stable identifier for the Cartesia lane (same
            pattern as ``ENGINE_ACT_ONE`` now dispatching the Act-Two
            adapter), and renaming it would break stored project settings and
            historical cost rows.

    Returns:
        ``True`` on success, ``False`` on missing key / HTTP error / timeout /
        format issue. **Never raises** — caller's fallback strategy is to
        route to ElevenLabs on any False return.

    Endpoint: https://docs.cartesia.ai/api-reference/tts/bytes (current
    Cartesia-Version header default: 2026-03-01, verified 2026-07-31).
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
            # Current documented default per
            # https://docs.cartesia.ai/build-with-cartesia/tts-models/api-changes
            # (verified 2026-07-31). The only breaking change on /tts/bytes
            # between 2024-06-10 and 2026-03-01 is the retirement of
            # ``voice.mode="embedding"`` (sunset 2026-06-01) — this adapter
            # already only ever sends ``mode="id"`` below, so no request-shape
            # change is needed beyond this version bump. NOTE: sonic-2 itself
            # is scheduled for sunset 2026-10-20 per the same page — tracked
            # as a follow-up, not addressed by this version bump (see
            # generate_cartesia's model_id default below).
            "Cartesia-Version": "2026-03-01",
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
        # Atomic publish (T-B quality fold): a kill mid-write must not leave
        # a partial mp3 — the exists-guard above would cache-hit it forever.
        _part = output_path + ".part"
        with open(_part, "wb") as f:
            f.write(r.content)
        os.replace(_part, output_path)
        print(f"   ✅ Cartesia output: {output_path}")
        return True

    except Exception as e:
        print(f"   ⚠️ [CARTESIA] failed: {e}")
        return False


# ---------------------------------------------------------------------------
# TTS provider language router
# ---------------------------------------------------------------------------

def _resolve_tts_provider(scene: dict, character: dict, settings_obj, tts_override: Optional[str] = None) -> str:
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
        tts_override: the project's explicitly stored ``tts_provider``
            setting (``get_project_setting(ctx, "tts_provider")``), or
            None. Closes the gap where VoiceSection's "Dialogue TTS
            provider" picker persisted a choice the router never
            consulted — an explicit ``"CARTESIA_SONIC_2"`` selection now
            wins over the language auto-route (still gated on the API key
            being present, same as the auto-route below; no key means the
            call would fail anyway, so it falls through instead). Any
            other value — including the picker's own default,
            ``"ELEVENLABS_V3"`` — leaves the language-based auto-routing
            untouched, since ElevenLabs is already that auto-route's
            non-Korean result.

    Returns:
        ``"CARTESIA_SONIC_2"`` for an explicit override (key permitting) or
        Korean+key-set; ``"ELEVENLABS"`` otherwise.
    """
    scene = scene or {}
    character = character or {}

    def _cartesia_key_present() -> bool:
        if getattr(settings_obj, "cartesia_api_key", "") and settings_obj.cartesia_api_key:
            return True
        # Dict-shaped settings (e.g. project["global_settings"]) — same key access shape.
        if isinstance(settings_obj, dict) and settings_obj.get("cartesia_api_key"):
            return True
        return False

    if tts_override == "CARTESIA_SONIC_2" and _cartesia_key_present():
        return "CARTESIA_SONIC_2"

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
    if is_korean and _cartesia_key_present():
        return "CARTESIA_SONIC_2"
    return "ELEVENLABS"


# ---------------------------------------------------------------------------
# Cartesia voice id resolver
# ---------------------------------------------------------------------------

_CARTESIA_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def _resolve_cartesia_voice(voice_id: str, char_record: dict, project_lang: str) -> "str | None":
    """Return a Cartesia-usable voice id, or None to skip the Cartesia lane.

    - voice_id already Cartesia-UUID-shaped (explicit assignment) -> use as-is
    - else map via language_defaults' cartesia_default_{male,female}_voice
      (gender from char_record, same male-hint logic as the 11labs fallback)
    - no mapping for this language -> None (caller skips Cartesia WITHOUT the
      HTTP round-trip; closes ticket T-A's guaranteed-400 burn)
    """
    # Already a Cartesia UUID — use directly without a mapping lookup.
    if _CARTESIA_UUID_RE.fullmatch(voice_id):
        return voice_id

    # Not UUID-shaped (ElevenLabs id or similar) — look up the per-language
    # Cartesia default. Mirror the lazy-import + try/except shape at :366-380
    # so a domain import failure degrades to None, never raises.
    try:
        from domain.language_defaults import get_language_defaults
        # Normalize the language the same way the router detects Korean
        # ('ko' prefix matches 'ko'/'ko_KR'/'korean') — the defaults dict is
        # keyed by display name ("Korean"), so without this the mapper
        # misses EXACTLY when the router routes to Cartesia (live-verification
        # catch: project language 'ko' fell to _default → None → skip).
        _lang_key = "Korean" if str(project_lang).lower().startswith("ko") else project_lang
        lang_defaults = get_language_defaults(_lang_key)
        char_gender = (char_record.get("gender") or "").lower()
        if char_gender in {"male", "m", "man"}:
            return lang_defaults.get("cartesia_default_male_voice") or None
        else:
            return lang_defaults.get("cartesia_default_female_voice") or None
    except Exception:
        return None


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

    # An explicit Cartesia preference must actually route to Cartesia (the
    # bug this closes: this ElevenLabs-only endpoint ran FIRST whenever 2+
    # speakers were present, so a stored `tts_provider="CARTESIA_SONIC_2"`
    # never got a chance — PATH 2's per-line dispatcher is the only path
    # that honors the override). Skip so the caller falls through to it.
    if get_project_setting(ctx, "tts_provider", None) == "CARTESIA_SONIC_2":
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
    alignment fails.

    Default is True when the key is absent — matching VoiceSection's
    "Forced alignment (WhisperX)" toggle (`checked={s.forced_alignment_enabled
    !== false}`, i.e. defaults ON) and every entry in
    domain/language_defaults.py (all languages ship `forced_alignment_enabled:
    True`). This gate previously defaulted to False, so a project that had
    never explicitly written the key showed the toggle ON in the UI while the
    runtime silently skipped alignment — the display/default/consumer
    three-way disagreement slice 9c closes.

    NOTE (2026-06-13, capacity audit wf_6be2ee18-f4b): the sidecar is currently
    WRITE-ONLY — load_alignment_json has zero callers (the SRT writer was deleted;
    lip_sync has no alignment imports). Compute runs for no current output. Wire it
    into lip_sync.validate_lipsync_quality when the mouth-energy scorer lands
    (catB-syncnet integration point) to make this pay off.

    language: project language name. When None, reads from ctx's
    `language` setting. Critical for Korean/Japanese/Chinese — whisper
    drifts badly on these languages without an explicit hint.
    """
    if not get_project_setting(ctx, "forced_alignment_enabled", True):
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
    warnings.warn(
        "[alignment] forced-alignment sidecar written but load_alignment_json has "
        "no consumer — compute runs for no current output. Wire into "
        "lip_sync.validate_lipsync_quality to use (catB-syncnet integration point).",
        stacklevel=2,
    )
    print(f"   📐 Forced alignment ({result.provider}, {len(result.words)} words, lang={language}) → {json_path}")
    return json_path


# ---------------------------------------------------------------------------
# Dialogue pace control (dialogue_target_wpm -> ffmpeg atempo)
# ---------------------------------------------------------------------------
# eleven_v3 ignores the `speed` voice setting, so speaking pace is corrected
# AFTER render: measure the assembled line's actual words-per-minute and
# time-stretch (pitch-preserved atempo) toward the project's
# `dialogue_target_wpm`. Post-render only, so TTS billing is unaffected.

def _pace_factor(words: int, duration_s: float, target_wpm: int,
                 deadband: float = 0.03, lo: float = 0.6, hi: float = 1.6):
    """atempo factor to move `words`/`duration_s` speech toward `target_wpm`,
    or None to skip. factor < 1 slows down (fewer wpm). Returns None when
    disabled/unmeasurable or the change is within +/- `deadband`; otherwise
    clamped to [lo, hi] to protect prosody on outlier inputs."""
    if target_wpm <= 0 or words <= 0 or duration_s <= 0:
        return None
    actual_wpm = words / (duration_s / 60.0)
    factor = target_wpm / actual_wpm
    if abs(factor - 1.0) <= deadband:
        return None
    return max(lo, min(hi, factor))


def _atempo_chain(factor: float) -> str:
    """ffmpeg atempo filter string; chains passes to cover factors outside
    atempo's native 0.5-2.0 range (mirrors phase_c_ffmpeg.adjust_speed)."""
    parts, remaining = [], factor
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.4f}")
    return ",".join(parts)


def _probe_audio_duration(path: str) -> float:
    """Audio duration in seconds via ffprobe; 0.0 if unmeasurable."""
    if not path or not os.path.exists(path):
        return 0.0
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return float((out.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _apply_target_pace(audio_path: str, transcript: str, target_wpm: int) -> str:
    """Time-stretch `audio_path` IN PLACE toward `target_wpm` (pitch-preserved
    ffmpeg atempo). No-op — returns `audio_path` unchanged — when pacing is
    disabled, the audio/duration is unmeasurable, or the change is within the
    deadband."""
    factor = _pace_factor(len((transcript or "").split()),
                          _probe_audio_duration(audio_path), target_wpm)
    if factor is None:
        return audio_path
    tmp = f"{audio_path}.paced.mp3"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-filter:a", _atempo_chain(factor),
             "-c:a", "libmp3lame", "-q:a", "2", tmp],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120,
        )
        if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, audio_path)
            print(f"   🎚️ [PACE] atempo={factor:.3f} -> target ~{target_wpm} wpm")
    except Exception as e:
        print(f"   [PACE] pace skip (atempo failed, kept original): {e}")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return audio_path


def generate_dialogue_voiceover(
    dialogue_lines: list,
    characters: list,
    output_filename: str = "temp_dialogue_voiceover.mp3",
    pause_between_lines: float = 0.3,
    ctx: "Optional[PipelineContext]" = None,
    cost_tracker: Optional[object] = None,
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
    # Target speaking pace (wpm) — applied via ffmpeg atempo post-render so the
    # UI's `dialogue_target_wpm` control is truthful. Default 145 (cinematic
    # close-up pace); a stored 0/None disables pacing. eleven_v3 ignores the
    # `speed` voice setting, so pacing MUST be a measure-then-stretch
    # post-process, not a TTS parameter.
    try:
        target_wpm = int(get_project_setting(ctx, "dialogue_target_wpm", 145) or 0)
    except (TypeError, ValueError):
        target_wpm = 145

    # PATH 1: try ElevenLabs Dialogue Mode first
    dm_result = _try_dialogue_mode(dialogue_lines, characters, output_filename, ctx=ctx)
    if dm_result:
        transcript_hint = " ".join(ln.get("text", "").strip() for ln in dialogue_lines)
        dm_result = _apply_target_pace(dm_result, transcript_hint, target_wpm)
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

    # The project's explicitly stored TTS provider choice (VoiceSection's
    # "Dialogue TTS provider" picker) — read once, passed to every line's
    # _resolve_tts_provider call below as tts_override.
    tts_override = get_project_setting(ctx, "tts_provider", None)

    print(f"🎙️ [CINEMA] Generating multi-character dialogue ({len(dialogue_lines)} lines)...")

    # Log Cartesia-skip once per invocation (not per line) to avoid log spam.
    _cartesia_skip_logged = False

    for i, line in enumerate(dialogue_lines):
        cid = line.get("character_id", "")
        text = line.get("text", "")
        if not text.strip():
            continue

        voice_id = char_voices.get(cid, "")
        char_record = char_by_id.get(cid, {})
        char_gender = (char_record.get("gender") or "").lower()
        _is_male = char_gender in {"male", "m", "man"}
        if not voice_id:
            # Fallback chain (closes VG-B1 — prior code hardcoded
            # "pNInz6obpgDQGcFmaJgB" = Adam English-male; produced wrong-
            # gendered + wrong-language audio for projects where
            # character.voice_id was never assigned at create-time):
            #   1. Any other character's assigned voice in this project
            #   2. The project's OWN configured default_male_voice /
            #      default_female_voice (VoiceSection's "Default male/female
            #      voice" pickers) — the operator's explicit gender-matched
            #      choice; previously stored in global_settings but never
            #      read here (this fallback chain read only the per-language
            #      static table below, which happens to reuse the same two
            #      field names for an unrelated purpose).
            #   3. Language + gender-aware default from language_defaults
            #      (Korean female → 안나 Anna; Korean male → 준호 Junho;
            #       English → Rachel / Adam; unknown language → English
            #       fallback per get_language_defaults("_default"))
            #   4. Adam (legacy hardcode) — only when import fails
            voice_id = next((v for v in char_voices.values() if v), "")
            if not voice_id:
                _default_key = "default_male_voice" if _is_male else "default_female_voice"
                voice_id = get_project_setting(ctx, _default_key, "") or ""
            if not voice_id:
                try:
                    from domain.language_defaults import get_language_defaults
                    lang_defaults = get_language_defaults(project_lang)
                    # Default to female voice unless character has explicit
                    # male gender hint. Female default is closer to common
                    # narrative cinema use than the prior unconditional
                    # male hardcode.
                    if _is_male:
                        voice_id = lang_defaults.get("default_male_voice", "")
                    else:
                        voice_id = lang_defaults.get("default_female_voice", "")
                except Exception:
                    pass  # Import or lookup failed — legacy hardcode fallback below is safe
            if not voice_id:
                voice_id = "pNInz6obpgDQGcFmaJgB"  # legacy hardcode last resort

        char_name = next((c["name"] for c in characters if c["id"] == cid), cid)
        delivery = line.get("delivery", "natural")

        # Voice direction system — maps delivery to precise voice parameters + text markup
        voice_profile = get_voice_direction(delivery)
        directed_text = voice_profile["markup"](text) if voice_profile.get("markup") else text

        # Content-keyed per-line temp: lives in the same dir as output_path
        # (NOT CWD) so it's project-scoped and reusable across runs with
        # the same content (ticket T-B change 3). Key uses the ORIGINAL
        # voice_id (pre-Cartesia resolution) so it is provider-independent.
        _line_key = _line_cache_key(directed_text, voice_id, project_lang)
        _out_dir = os.path.dirname(output_filename) or "."
        temp_path = os.path.join(_out_dir, f"dialogue_line_{_line_key}.mp3")

        # Route per-line: explicit tts_provider override (when dispatchable)
        # wins; otherwise language-aware auto-selection. Korean +
        # CARTESIA_API_KEY set → Cartesia Sonic 2 (native prosody, low
        # latency). Everything else → ElevenLabs (unchanged path).
        provider = _resolve_tts_provider(scene_for_router, char_record, settings, tts_override=tts_override)
        cartesia_ok = False
        cartesia_voice = None  # init outside the branch — a hoisted guard must never NameError (T-A quality fold)
        if provider == "CARTESIA_SONIC_2":
            # Map the voice id to a Cartesia-UUID-shaped id before dispatch.
            # If no mapping exists for this language, skip the HTTP round-trip
            # entirely (guaranteed-400 burn; closes ticket T-A). Log the skip
            # once per invocation (not per line) via a local flag.
            cartesia_voice = _resolve_cartesia_voice(voice_id, char_record, project_lang)
            if cartesia_voice is None:
                if not _cartesia_skip_logged:
                    print(
                        f"   [CARTESIA] no Cartesia voice mapping for language={project_lang!r}; "
                        "skipping Cartesia lane (no HTTP call) — falling back to ElevenLabs"
                    )
                    _cartesia_skip_logged = True
            else:
                # Cartesia's language field expects an ISO code; map the project
                # language name to "ko" when Korean, else pass the raw value
                # lowercased. The dispatcher already routed correctly upstream
                # so this is just the API param shape.
                lang_for_api = "ko" if str(project_lang).lower().startswith("ko") else str(project_lang).lower()[:2] or "en"
                cartesia_ok = generate_cartesia(
                    text=directed_text,
                    voice_id=cartesia_voice,
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
                    # T5: use caller-supplied tracker when provided so spend accumulates
                    # on the pipeline's budget-aware tracker (cross-process persistence
                    # deferred).
                    _tracker = cost_tracker or CostTracker()
                    _tracker.record_api_call(
                        "CARTESIA_SONIC_2",
                        operation="dialogue_tts",
                    )
                except Exception:
                    # Cost tracking is best-effort; the TTS itself succeeded.
                    print(f"   [CARTESIA] cost record skipped for line {i+1} (non-critical)")
                temp_files.append(temp_path)
                print(f"   ✅ Line {i+1}: {char_name} ({delivery}) → {temp_path} [Cartesia]")
                continue
            # Cartesia generate call returned False — fall through to ElevenLabs
            if cartesia_voice is not None:
                print(f"   [CARTESIA] failed for line {i+1}; falling back to ElevenLabs")

        # ElevenLabs path (default OR Cartesia fallback)
        # Per-line cache hit — mirrors generate_cartesia's guard (T-B quality
        # fold). Safe because all line writes below/above are atomic
        # (.part + os.replace): an existing file is a COMPLETE render.
        if os.path.exists(temp_path):
            print(f"   [ELEVENLABS] Cache hit: {temp_path}")
            temp_files.append(temp_path)
            continue
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
            _part = temp_path + ".part"
            save(audio, _part)
            os.replace(_part, temp_path)
            temp_files.append(temp_path)
            # Best-effort cost tracking — M-B2 closure (cycle-16). Symmetric
            # to Cartesia tracking above; closes the asymmetry noted at
            # cycle-15 v0.9.7 ("ElevenLabs path remains pre-existing
            # untracked... symmetric ElevenLabs tracking deferred to v0.9.X+")
            # by adding the tracking at this version (a la deferred → done).
            try:
                from cost_tracker import CostTracker
                # T5: use caller-supplied tracker when provided so spend accumulates
                # on the pipeline's budget-aware tracker (cross-process persistence
                # deferred).
                _tracker = cost_tracker or CostTracker()
                _tracker.record_api_call("ELEVENLABS", operation="dialogue_tts")
            except Exception:
                print(f"   [ELEVENLABS] cost record skipped for line {i+1} (non-critical)")
            print(f"   ✅ Line {i+1}: {char_name} ({delivery}) → {temp_path}")
        except Exception as e:
            print(f"   ⚠️ Failed to generate line {i+1} for {char_name}: {e}")

    if not temp_files:
        print("❌ No dialogue lines generated.")
        return None

    # Concatenate all lines with pauses using ffmpeg
    try:
        import subprocess

        # Control files keyed to the output artifact (T-B quality fold):
        # the previous CWD-relative shared names ("temp_dialogue_concat.txt")
        # collide across concurrent assemblies of DIFFERENT projects — the
        # re-assembly in-flight fence is per-project only.
        concat_list = f"{output_filename}.concat.txt"
        silence_file = f"{output_filename}.silence.mp3"

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

        # Atomic publish: encode to .part.mp3 then rename — a kill mid-encode
        # must not leave a partial scene artifact (the ensure-sites' disk-first
        # check would cache-hit it forever).
        _part_out = f"{output_filename}.part.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_list, "-c:a", "libmp3lame", "-q:a", "2", _part_out],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        os.replace(_part_out, output_filename)

        # Apply the project's target speaking pace (ffmpeg atempo, pitch-
        # preserved) to the assembled dialogue BEFORE alignment, so any
        # word-timestamp sidecar matches the final (paced) timing.
        _dlg_transcript = " ".join(ln.get("text", "").strip() for ln in dialogue_lines)
        _apply_target_pace(output_filename, _dlg_transcript, target_wpm)

        print(f"   ✅ Multi-character dialogue assembled: {output_filename}")

        # Content-keyed per-line files (dialogue_line_<hash>.mp3) are NOT
        # deleted here — they form the per-line cache that prevents
        # re-generating identical lines across runs (ticket T-B change 3).
        # Only clean up the ephemeral concat control files.
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
