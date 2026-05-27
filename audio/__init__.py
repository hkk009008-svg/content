"""Cinema pipeline — audio domain package.

Sibling to `identity/` (validation domain) and `llm/` (LLM domain).
The legacy `phase_b_audio.py` god module has been fully migrated and
deleted; consumers import directly from these submodules.

Submodules (post Bundle-D 4.3, 2026-05-24 — orphaned modules deleted;
           foley re-added 2026-05-28):
  audio/_client.py    — ElevenLabs SDK singleton (private)
  audio/voiceover.py  — VOICE_DIRECTIONS dict + get_voice_direction resolver
                        (the orphaned generate_voiceover / generate_narration /
                        generate_single_line_audio / generate_tts_routed TTS
                        functions were removed; only the voice-profile
                        catalogue + lookup remain, consumed by dialogue and
                        the web UI voice-style dropdown)
  audio/dialogue.py   — per-character dialogue TTS + alignment sidecar
  audio/music.py      — BGM generation (Suno / FAL Stable Audio) + mastering
  audio/effects.py    — Pedalboard + macOS AU voice/audio FX (hard dep)
  audio/alignment.py  — WhisperX forced alignment for lip-sync
  audio/foley.py      — environmental foley via Stability AI Stable Audio 2.0

Deleted (had zero live callers):
  audio/srt.py        — Whisper-driven .srt caption writer

No __all__ is exported from this package — callers import targeted
names directly from submodules (e.g.
``from audio.dialogue import generate_dialogue_voiceover``).
"""
