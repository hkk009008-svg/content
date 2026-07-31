"""Performance-capture engine adapters.

Each module wraps one external engine with a defensive try/except shape:
the function returns the local output path on success, None on any
failure. No exceptions escape — callers (cinema/shots/controller.py)
treat None as "skip this engine, cascade to next or fall through to
plain text-to-video".

  - act_two.py       — Runway Act-Two (best for dialogue close-ups; migrated
                        from the retired Act-One, 2026-07-30 slice 5b)
  - live_portrait.py — ComfyUI LivePortrait (budget path for dialogue)
  - viggle.py        — Viggle (full-body motion retargeting)
  - driving_video.py — Mode B synth helpers (SadTalker)
  - _router.py       — dispatch(engine_name, ...) → calls the right adapter
"""
