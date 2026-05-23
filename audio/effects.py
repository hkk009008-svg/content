"""Cinema Pipeline — voice-effects / DSP helpers.

Phase 6 slice 4 of the architecture refactor: extract the voice-effects
processor out of the 932-line ``phase_b_audio.py`` god module into this
focused submodule. Sibling to ``audio/srt.py`` (slice 1),
``audio/music.py`` (slice 2), and ``audio/foley.py`` (slice 3).

Contents
========

- ``VOICE_EFFECTS``        — FFmpeg-filter presets for stylized voice FX.
- ``apply_au_plugin``      — load an installed macOS AU plugin headlessly.
- ``apply_pedalboard_chain`` — apply a Pedalboard built-in effect chain.
- ``list_au_plugins``      — enumerate available AU plugins on this Mac.
- ``apply_voice_effect``   — top-level voice-FX router (AU > Pedalboard > FFmpeg).

The legacy ``phase_b_audio`` module re-exports every name above so existing
``from phase_b_audio import apply_voice_effect`` style callers keep working.
New code should import directly from ``audio.effects``.

Pedalboard (Spotify's headless AU/VST3 plugin host) is a hard dependency
pinned in requirements-frozen-py39.txt.
"""

import os
from typing import Optional

from pedalboard import (
    Pedalboard, Reverb, Compressor, Gain, Delay,
    HighpassFilter, LowpassFilter, Chorus, Distortion,
    load_plugin,
)
from pedalboard.io import AudioFile


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
                except (AttributeError, ValueError, TypeError) as e_param:
                    print(f"   [AU] Could not set plugin param {k}: {e_param}")

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
    if au_plugin:
        result = apply_au_plugin(audio_path, output_path, au_plugin)
        if result != audio_path:
            return result

    # Priority 2: Pedalboard chain (if specified)
    if pedalboard_chain:
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
