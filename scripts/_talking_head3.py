#!/usr/bin/env python3
"""Photoreal 30s 9:16 talking head — uses an EXISTING photoreal reference face (a different
person) rather than a no-PuLID max-tier gen (which over-cooks into grunge regardless of the
enhancement knobs, because the max chain is co-tuned for a PuLID-anchored base). No pod gen
needed — just TTS + Hedra. Face: bf1a4e9e8a9a qipao woman (real-quality reference).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs("logs", exist_ok=True)

from audio.dialogue import generate_dialogue_voiceover
from hedra_native import HedraAPI

FACE = "domain/projects/bf1a4e9e8a9a/characters/char_b29189531779/canonical.jpg"
VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # ElevenLabs "Bella" (premade female voice)
NARRATIVE = (
    "They told me this city forgets everyone eventually. Maybe that's true. But standing here, "
    "watching the lights come on one by one, I've started to think forgetting is just another "
    "word for starting over. I came here with nothing — a name, and a promise I made to myself. "
    "And every night since, this skyline has felt a little more like mine. Tonight, for the first "
    "time, I'm not afraid of being forgotten. I'm ready to be remembered."
)


def main():
    print(f"[1/2] TTS ~30s ({len(NARRATIVE.split())} words, ElevenLabs Bella) ...", flush=True)
    audio = generate_dialogue_voiceover(
        [{"character_id": "narrator", "text": NARRATIVE, "delivery": "natural"}],
        [{"id": "narrator", "name": "Narrator", "voice_id": VOICE_ID}],
        output_filename="logs/th3_audio.mp3",
    )
    if not audio:
        print("FATAL: audio gen failed", flush=True); return 1
    print(f"[1/2] audio -> {audio}", flush=True)

    print(f"[2/2] Hedra Character-3 @ 9:16, face={os.path.basename(FACE)} ...", flush=True)
    out = HedraAPI().generate_talking_head(
        FACE, audio, "logs/talkinghead_photoreal_9x16.mp4", aspect_ratio="9:16", resolution="720p",
    )
    print(f"[2/2] DONE -> {out}", flush=True)
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
