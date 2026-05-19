"""PipelineContext — the typed replacement for the untyped `ctx: dict`.

Inventoried empirically by grepping every `ctx["..."]` / `ctx.get("...")` site
in the codebase. Eighteen fields, falling into five conceptual groups:

  * core         — topic, language, video id, master seed
  * script       — script_data, production_blueprint, full text/description
  * audio        — audio path, voice, foley, music vibe, pacing, tension
  * output       — final paths for video / thumbnail / metadata
  * workspace    — downloaded video staging list

Migration strategy
==================

For Phase 5's POC we want every existing phase function — those still typed
`def f(ctx: dict)` — to keep working unchanged when a `PipelineContext`
instance is passed in. To make that work we provide the four dict APIs the
legacy code uses:

  * `ctx["key"]`         (__getitem__)
  * `ctx["key"] = value` (__setitem__)
  * `ctx.get("key", d)`  (get)
  * `ctx.update({...})`  (update)

A future Phase 5 sub-commit will migrate legacy functions to use typed
attribute access (`ctx.topic`) directly, after which these dict-compat
methods become safe-to-remove.

Forward-compatibility note
==========================

Because the legacy code occasionally writes ctx keys that aren't in our
declared field list (rare but possible), `__setitem__` falls back to a
plain `setattr`. Python permits this on dataclasses, and the value will
be accessible via `__getitem__`. However `as_dict()` only serialises
declared fields — unknown keys won't round-trip through asdict(). If you
add a new key, declare it as a dataclass field.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, asdict
from typing import Any, Iterator, Optional

from cinema.lifecycle import LifecycleService, NullLifecycle


@dataclass
class PipelineContext:
    """The shared mutable state passed between pipeline phases."""

    # --- core ---
    topic: str = ""
    language: str = "English"
    youtube_video_id: Optional[str] = None
    master_image_seed: int = 0

    # --- lifecycle (cancel / pause / gate-wait / progress) ---
    # Default is the no-op NullLifecycle so phases can call
    # ``ctx.lifecycle.check_pause()`` etc. unconditionally without the
    # CLI path needing to construct anything. Interactive callers
    # (web_server) construct a ThreadedLifecycle and assign it before
    # calling driver.run().
    lifecycle: LifecycleService = field(default_factory=NullLifecycle)

    # --- script & blueprint ---
    script_data: dict = field(default_factory=dict)
    production_blueprint: dict = field(default_factory=dict)
    full_text: str = ""
    full_description: str = ""

    # --- audio ---
    audio_path: str = ""
    voice_id: str = ""
    foley_audio_paths: list = field(default_factory=list)
    music_vibe: str = ""
    video_pacing: str = ""
    story_tension: float = 0.0

    # --- output paths ---
    final_video_path: str = ""
    final_thumbnail_path: str = ""
    metadata_path: str = ""

    # --- workspace ---
    downloaded_vids: list = field(default_factory=list)

    # -----------------------------------------------------------------
    # dict-compat layer (so legacy `def f(ctx: dict)` keeps working)
    # -----------------------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        # Setattr permits new (undeclared) keys; we document the trade-off
        # in the module docstring.
        setattr(self, key, value)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return (f.name for f in fields(self))

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def update(self, data: dict) -> None:
        for k, v in data.items():
            setattr(self, k, v)

    def keys(self):
        return [f.name for f in fields(self)]

    def items(self):
        return [(f.name, getattr(self, f.name)) for f in fields(self)]

    def values(self):
        return [getattr(self, f.name) for f in fields(self)]

    def as_dict(self) -> dict:
        """Snapshot of declared fields as a plain dict (asdict)."""
        return asdict(self)
