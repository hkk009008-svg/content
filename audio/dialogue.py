"""Multi-character dialogue voiceover (ElevenLabs TTS + ffmpeg concat).

Phase 6 slice 6 of the architecture refactor: extract the last
function-with-a-body out of ``phase_b_audio.py``, leaving that module
as a pure backward-compat re-export shim.

Contents
========

- ``generate_dialogue_voiceover`` — per-character TTS for a list of
  dialogue lines, concatenated into one MP3 with configurable inter-line
  silence via ffmpeg.

Dependencies (all eager — no cycles):

- ``audio._client.client``               — shared ElevenLabs instance
- ``audio.voiceover.get_voice_direction`` — delivery → voice-param resolver
- ``elevenlabs.save``                    — write streamed audio to disk

This module is a leaf consumer: nothing in ``audio/*`` imports it.
"""

import os
from typing import Optional

from elevenlabs import save

from audio._client import client
from audio.voiceover import get_voice_direction


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
