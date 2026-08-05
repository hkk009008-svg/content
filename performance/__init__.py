"""Performance-capture engine adapters.

Each module wraps one external engine with a defensive result shape. The
controller treats a missing output as a failed/recoverable capture and keeps
the review gate closed; only natural routing or an explicit operator decision
may bypass performance capture.

  - act_two.py       — Runway Act-Two (best for dialogue close-ups; migrated
                        from the retired Act-One, 2026-07-30 slice 5b)
  - live_portrait.py — ComfyUI LivePortrait (budget path for dialogue)
  - viggle.py        — Viggle (full-body motion retargeting)
  - _router.py       — dispatch(engine_name, ...) → calls the right adapter
"""
