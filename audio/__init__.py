"""Cinema pipeline — audio domain package.

Sibling to `identity/` (validation domain) and `llm/` (LLM domain).
The legacy `phase_b_audio.py` god module has been fully migrated and
deleted; consumers import directly from these submodules.

Submodules:
  audio/_client.py    — ElevenLabs SDK singleton (private)
  audio/srt.py        — Whisper-driven .srt caption writer
  audio/voiceover.py  — TTS narration (OpenAI / Cartesia / ElevenLabs)
  audio/dialogue.py   — per-character dialogue TTS + alignment sidecar
  audio/foley.py      — environmental foley (Stability / ElevenLabs)
  audio/music.py      — BGM generation (Suno / FAL Stable Audio) + mastering
  audio/effects.py    — Pedalboard + macOS AU voice/audio FX (hard dep)
  audio/alignment.py  — WhisperX forced alignment for lip-sync

No __all__ is exported from this package — callers import targeted
names directly from submodules (e.g.
``from audio.dialogue import generate_dialogue_voiceover``).
"""
