"""BGM generation + music mastering.

Providers wired:
  - Suno V5 (full songs with vocals — generate_suno_v5)
  - FAL Stable Audio (instrumental BGM — generate_fal_bgm, default)

Plus the mastering chain:
  master_music            -- Pedalboard / macOS AU / FFmpeg routing
  MUSIC_MASTERING_PRESETS -- preset dictionary used by master_music
                             (cinema_master, lo_fi, epic_wide, intimate_acoustic,
                              dark_ambient, none)

Cross-module: `master_music` uses `apply_au_plugin` + `apply_pedalboard_chain`
from `audio.effects` (eager import at module top).
"""

from __future__ import annotations

import os

from audio.effects import (
    apply_au_plugin,
    apply_pedalboard_chain,
)
from typing import Optional


# ---------------------------------------------------------------------------
# Mastering presets
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# BGM generation
# ---------------------------------------------------------------------------

def _build_music_prompt(music_vibe: str) -> str:
    """Producer-grade prompt for the given mood. Reused across Suno + FAL paths."""
    vibe_prompts = {
        "suspense": "70bpm D minor, slow deep sub-bass drones, distant reversed piano, ticking clock polyrhythm, cinematic brass stabs, Hans Zimmer tension, dark ambient thriller score.",
        "thriller": "90bpm E minor, pulsing synth bass, staccato strings, heartbeat kick, rising tension builds, Trent Reznor atmosphere.",
        "horror": "60bpm C minor, dissonant string clusters, music box detuned, deep sub-bass, whispered textures, Ari Aster dread.",
        "noir": "75bpm Bb minor, smoky jazz saxophone, brushed drums, walking upright bass, rain-soaked city, 1940s detective.",
        "dystopian": "85bpm F# minor, industrial metallic percussion, distorted analog synth drones, mechanical rhythms, Blade Runner 2049.",
        "melancholic": "65bpm A minor, solo piano with sustain pedal, distant cello legato, vinyl crackle, gentle rain, Chopin meets Nils Frahm.",
        "contemplative": "62bpm B minor, sparse Rhodes piano arpeggios, sustained cello pad, soft tape hiss, slow breathing pace, introspective film montage, Ryuichi Sakamoto reflection, Lost in Translation interior.",
        "romantic": "72bpm D major, warm acoustic guitar fingerpicking, soft string quartet, golden hour, Richard Linklater film.",
        "bittersweet": "68bpm G minor, solo violin, piano arpeggios, muted trumpet, autumn nostalgia, Wong Kar-wai mood.",
        "grief": "55bpm C minor, slow cello solo, sparse piano with long reverb, silences, devastating, Schindler's List.",
        "hopeful": "80bpm C major, rising piano, warm analog strings crescendo, gentle tambourine, sunrise, uplifting but restrained.",
        "epic": "120bpm D minor, massive orchestral brass fanfare, taiko drums, choir chanting, sweeping strings, Lord of the Rings.",
        "action": "130bpm E minor, driving electronic beats, distorted guitar, aggressive drums, Jason Bourne intensity.",
        "triumphant": "100bpm Bb major, full orchestra fortissimo, French horns, snare roll crescendo, John Williams glory.",
        "chase": "140bpm A minor, relentless hi-hat patterns, pulsing synth bass, rising pitch tension, Bourne Identity chase.",
        "ethereal": "50bpm F major, shimmering pad synths, granular texture clouds, distant vocal oh, Brian Eno ambient.",
        "dreamy": "60bpm Ab major, lo-fi tape warble, soft Rhodes piano, bedroom reverb, vinyl hiss, Tame Impala haze.",
        "meditative": "45bpm D major, singing bowls, gentle drone, flowing water, bamboo flute, spa atmosphere.",
        "cosmic": "55bpm whole tone, deep space synth pads, radio static textures, Interstellar organ, vast emptiness.",
        "cyberpunk": "110bpm F minor, dark synthwave arpeggios, neon atmosphere, Moog bass, 80s retrofuturism.",
        "corporate": "95bpm G major, clean minimalist synth pulses, subtle marimba, polished, Apple keynote.",
        "gritty": "85bpm Eb minor, heavy industrial distorted bass, mechanical percussion, factory ambience, NIN documentary.",
        "urban": "90bpm Cm, lo-fi hip hop beats, muted jazz samples, city rain, late night study session.",
        "uplifting": "100bpm A major, bright acoustic guitar, clapping rhythm, indie film montage, Little Miss Sunshine.",
        "jazz_noir": "80bpm Dm7, walking upright bass, brushed snare, smoky saxophone improvisation, Miles Davis Kind of Blue.",
        "classical": "Andante E minor, string quartet, chamber music intimacy, Vivaldi elegance.",
        "western": "75bpm Am, lone acoustic guitar, distant harmonica, desert wind, Ennio Morricone whistling.",
        "electronic_minimal": "115bpm C minor, minimal techno pulse, evolving single note, Berlin club 4am, Richie Hawtin precision.",
    }
    return vibe_prompts.get(
        music_vibe.lower(),
        f"Cinematic ambient music, {music_vibe} mood, slow, atmospheric, film score quality, professional production.",
    )


_SUNO_MODEL = "V5"  # sunoapi.org: V4 | V4_5 | V4_5PLUS | V4_5ALL | V5 | V5_5 — change per plan
# callBackUrl is a required request field even though we poll record-info for the
# result (this pipeline has no public callback URL); a placeholder satisfies the schema.
_SUNO_CALLBACK_PLACEHOLDER = "https://example.com/suno-callback"
_SUNO_POLL_INTERVAL_S = 5
# sunoapi.org's audioUrl is a CDN asset that 403s the default urllib User-Agent
# (Python-urllib/*); fetch it via requests with a browser UA instead.
_SUNO_DOWNLOAD_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def generate_suno_v5(
    music_vibe: str,
    output_filename: str,
    duration: int = 60,
    instrumental: bool = True,
    custom_lyrics: str = "",
    poll_timeout_s: int = 240,
    cost_tracker: Optional = None,
) -> bool:
    """Generate a song via Suno V5 (the SOTA music model with vocals).

    Requires SUNO_API_KEY + SUNO_API_BASE (sunoapi.org). Enqueues via
    POST /api/v1/generate, then polls GET /api/v1/generate/record-info?taskId=...
    until data.status == 'SUCCESS', then downloads data.response.sunoData[0].audioUrl.

    Falls back to False on any error so the caller can route to FAL/ElevenLabs.

    Args:
        music_vibe:     mood key (see _build_music_prompt for the full list)
        output_filename: where to save the .mp3 (Suno returns MP3)
        duration:        kept for signature compat; sunoapi.org returns full-length songs (no duration knob)
        instrumental:    True for score work; False if you want sung vocals
        custom_lyrics:   optional lyric override (Suno V5's killer feature)
        poll_timeout_s:  give up after this many seconds of polling
    """
    import requests
    from config.settings import settings

    api_key = settings.suno_api_key
    if not api_key:
        print("   [SUNO V5] SUNO_API_KEY not set; skipping")
        return False

    base = settings.suno_api_base.rstrip("/")
    prompt = _build_music_prompt(music_vibe)

    # sunoapi.org custom mode: style + title are required, prompt is optional (we
    # always pass it for guidance); instrumental toggles vocals. There is no
    # duration knob — the service returns full-length songs (trimmed/looped to the
    # scene length downstream). custom_lyrics, when given, is used as the prompt.
    payload = {
        "customMode": True,
        "instrumental": instrumental,
        "model": _SUNO_MODEL,
        "callBackUrl": _SUNO_CALLBACK_PLACEHOLDER,  # required by schema; we poll instead
        "style": music_vibe,
        "title": f"{music_vibe} BGM",
        "prompt": (custom_lyrics or prompt)[:4900],
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    _FAILED = {"CREATE_TASK_FAILED", "GENERATE_AUDIO_FAILED",
               "CALLBACK_EXCEPTION", "SENSITIVE_WORD_ERROR"}

    try:
        print(f"   [SUNO V5] Generating [{music_vibe.upper()}] (model={_SUNO_MODEL}, instrumental={instrumental})...")
        r = requests.post(f"{base}/api/v1/generate", json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json() or {}
        if body.get("code") != 200:
            print(f"   [SUNO V5] generate rejected: code={body.get('code')} msg={body.get('msg')}")
            return False
        task_id = (body.get("data") or {}).get("taskId")
        if not task_id:
            print(f"   [SUNO V5] no taskId in response: {list(body.keys())}")
            return False

        # Poll record-info until SUCCESS (stream URL ~30-40s, full audio ~2-3 min).
        audio_url = ""
        start = time.time()
        while (time.time() - start) < poll_timeout_s:
            time.sleep(_SUNO_POLL_INTERVAL_S)
            sr = requests.get(
                f"{base}/api/v1/generate/record-info",
                params={"taskId": task_id}, headers=headers, timeout=15,
            )
            if not sr.ok:
                continue
            data = (sr.json() or {}).get("data") or {}
            status = (data.get("status") or "").upper()
            if status == "SUCCESS":
                tracks = ((data.get("response") or {}).get("sunoData")) or []
                if tracks:
                    audio_url = tracks[0].get("audioUrl") or tracks[0].get("streamAudioUrl") or ""
                break
            if status in _FAILED:
                print(f"   [SUNO V5] generation failed: status={status}")
                return False
            # else PENDING / TEXT_SUCCESS / FIRST_SUCCESS → keep polling

        if not audio_url:
            print(f"   [SUNO V5] timed out after {poll_timeout_s}s (no audioUrl)")
            return False

        dl = requests.get(audio_url, headers={"User-Agent": _SUNO_DOWNLOAD_UA}, timeout=60)
        dl.raise_for_status()
        with open(output_filename, "wb") as f:
            f.write(dl.content)
        print(f"   ✅ Suno V5 song saved: {output_filename}")
        # Best-effort cost tracking — closes part of M-B2 (cycle-16 Tier B
        # surfaced BGM/foley/TTS sites lacked record_api_call invocations).
        # Mirrors Cartesia pattern at audio/dialogue.py:419-427.
        # T5: use caller-supplied tracker when provided so spend accumulates on
        # the pipeline's budget-aware tracker (cross-process persistence deferred).
        try:
            from cost_tracker import CostTracker
            _tracker = cost_tracker or CostTracker()
            _tracker.record_api_call("SUNO_V5", operation="bgm")
        except Exception:
            print(f"   [SUNO V5] cost record skipped (non-critical)")
        return True
    except requests.RequestException as e:
        print(f"   [SUNO V5] HTTP error: {e}")
        return False
    except Exception as e:
        print(f"   [SUNO V5] failed: {e}")
        return False


def generate_bgm(
    music_vibe: str,
    output_filename: str,
    duration: int = 60,
    prefer_provider: Optional[str] = None,
    custom_lyrics: str = "",
) -> bool:
    """Smart router: Suno V5 → FAL Stable Audio. Returns True on success.

    Caller passes prefer_provider; "AUTO" tries Suno first, then falls through
    to FAL on any failure.
    """
    provider = prefer_provider or "AUTO"

    if provider in ("SUNO_V5", "AUTO"):
        if generate_suno_v5(music_vibe, output_filename, duration=duration, custom_lyrics=custom_lyrics):
            return True
        # Fall through to FAL on Suno failure

    return generate_fal_bgm(music_vibe, output_filename, duration=duration)


import time  # used by Suno polling — placed here to keep the import surface stable

def generate_fal_bgm(music_vibe: str, output_filename: str, duration: int = 42, cost_tracker: Optional = None):
    """Uses Fal.ai's text-to-audio engine to generate custom background music."""
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
            "contemplative": "62bpm, B minor, sparse Rhodes piano arpeggios, sustained cello pad, soft tape hiss, slow breathing pace, introspective film montage, reflective interior monologue, Ryuichi Sakamoto reflection, Lost in Translation atmosphere.",
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
            # Best-effort cost tracking — M-B2 closure (cycle-16). Mirrors
            # Cartesia pattern at audio/dialogue.py:419-427.
            # T5: use caller-supplied tracker when provided so spend accumulates on
            # the pipeline's budget-aware tracker (cross-process persistence deferred).
            try:
                from cost_tracker import CostTracker
                _tracker = cost_tracker or CostTracker()
                _tracker.record_api_call("FAL_STABLE_AUDIO", operation="bgm")
            except Exception:
                print(f"   [FAL] cost record skipped (non-critical)")
            return True

        print("⚠️ Fal.ai BGM Warning: No audio URL returned.")
        return False
    except Exception as e:
        print(f"⚠️ Fal.ai BGM Generation Sub-Error (Using fallback generic BGM via assembly): {e}")
        return False


# ---------------------------------------------------------------------------
# Music mastering
# ---------------------------------------------------------------------------

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
    if au_plugin:
        result = apply_au_plugin(audio_path, output_path, au_plugin)
        if result != audio_path:
            return result

    if preset == "none" or preset not in MUSIC_MASTERING_PRESETS:
        return audio_path

    config = MUSIC_MASTERING_PRESETS[preset]

    # Try Pedalboard first (higher quality)
    if config.get("pedalboard"):
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
