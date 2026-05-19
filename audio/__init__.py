"""Cinema Pipeline — audio domain package.

Phase 6 of the architecture refactor: split the 1,348-line `phase_b_audio.py`
god module into focused submodules under this package. Sibling to
`identity/` (validation domain) and `llm/` (LLM domain).

Roadmap
=======

  audio/srt.py        — caption-file writer (whisper-driven SRT generation)
                         landed in slice 1
  audio/voiceover.py  — TTS narration + voice effects (TODO)
  audio/dialogue.py   — per-character dialogue TTS (TODO)
  audio/foley.py      — environmental foley generation (TODO)
  audio/music.py      — BGM + mastering (TODO)

The legacy `phase_b_audio.py` remains in place during migration and
re-exports the moved functions, so existing callers (main.py,
cinema_pipeline.py, cinema/phases/audio.py) continue to work
unchanged. Each migration slice moves one or two related functions
and updates phase_b_audio.py's re-export list.
"""
