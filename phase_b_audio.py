import os
from typing import Optional, List
from elevenlabs import save  # still used by generate_dialogue_voiceover (slice 6)

# Phase 6 backward-compat re-exports: functions moved into focused submodules
# under audio/. Existing callers using `from phase_b_audio import X` keep
# working; new code should import from audio.* directly.
from audio._client import client  # noqa: F401 — invariant #7: phase_b_audio.client is ElevenLabs
from audio.srt import generate_srt  # noqa: F401
from audio.music import (  # noqa: F401
    generate_fal_bgm,
    master_music,
    MUSIC_MASTERING_PRESETS,
)
from audio.effects import (  # noqa: F401
    apply_au_plugin,
    apply_pedalboard_chain,
    apply_voice_effect,
    list_au_plugins,
    VOICE_EFFECTS,
    PEDALBOARD_AVAILABLE,
)
from audio.voiceover import (  # noqa: F401
    generate_voiceover,
    generate_narration,
    generate_single_line_audio,
    get_voice_direction,
    VOICE_DIRECTIONS,
    DELIVERY_STYLES,
    NARRATOR_VOICES,
)
from audio.foley import (  # noqa: F401
    generate_scene_foley,
    generate_layered_foley,
    generate_scene_foley_library,
    _build_ambience_prompt,
    _build_action_prompt,
    _build_texture_prompt,
)

# generate_voiceover, VOICE_DIRECTIONS, get_voice_direction, DELIVERY_STYLES,
# NARRATOR_VOICES, and generate_narration were here — moved to
# audio/voiceover.py in Phase 6 slice 5. Backward-compat re-export is at the
# top of this file.


# voice-effects helpers were here — moved to audio/effects.py in Phase 6
# slice 4 (apply_au_plugin, apply_pedalboard_chain, list_au_plugins,
# apply_voice_effect, VOICE_EFFECTS dict, PEDALBOARD_AVAILABLE flag).
# Backward-compat re-export is at the top of this file.


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



# generate_single_line_audio was here — moved to audio/voiceover.py in
# Phase 6 slice 5 (alongside its sibling voice/narration TTS helpers).



# generate_scene_foley, generate_layered_foley, _build_ambience_prompt,
# _build_action_prompt, _build_texture_prompt were here — moved to
# audio/foley.py in Phase 6 slice 3. Backward-compat imports at top.


# generate_fal_bgm, MUSIC_MASTERING_PRESETS, and master_music were here —
# moved to audio/music.py in Phase 6 slice 2. Backward-compat imports at
# the top of this file keep callers working.


# generate_srt was here — moved to audio/srt.py in Phase 6 slice 1.
# Backward-compat import is at the top of this file.

# generate_scene_foley_library was here — moved to audio/foley.py in
# Phase 6 slice 3 (alongside its single-shot peer, generate_scene_foley).
