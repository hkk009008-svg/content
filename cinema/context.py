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

import math

from dataclasses import dataclass, field, fields, asdict
from typing import Any, Iterator, Optional

from cinema.lifecycle import LifecycleService, NullLifecycle


@dataclass
class PipelineContext:
    """The shared mutable state passed between pipeline phases."""

    # --- core ---
    topic: str = ""
    language: str = "English"
    master_image_seed: int = 0

    # --- per-project UI settings ---
    # Mirrors the React side's `project.global_settings` dict. Populated by
    # the web entry point from the active Project; CLI runs leave it empty
    # (defaults take over). All UI-tunable knobs (tts_provider, foley_provider,
    # music_provider, lipsync_*, dialogue_mode_enabled, etc.) MUST be read
    # via `get_project_setting(ctx, key, default)` from this dict — NOT via
    # the frozen env-derived `config.settings.Settings` dataclass.
    global_settings: dict = field(default_factory=dict)

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
    music_vibe: str = ""
    video_pacing: str = ""
    story_tension: float = 0.0

    # --- output paths ---
    final_video_path: str = ""
    final_thumbnail_path: str = ""
    metadata_path: str = ""

    # --- workspace ---
    downloaded_vids: list = field(default_factory=list)

    # --- max-quality tier state ---
    # Pre-VAE-decode latent of the previous shot, cached for LatentBlend in the
    # max tier. Bytes (serialized torch tensor) or None. Only populated when
    # generate_ai_broll(..., quality_tier="max") runs and the pod returns the
    # latent. Production tier ignores this field.
    prev_shot_latent: Optional[bytes] = None
    # Per-character LoRA registry: character_id -> local path to .safetensors.
    # Consumed by quality_max via the char_lora_path kwarg.
    char_lora_paths: dict = field(default_factory=dict)
    # Per-character LoRA validated strength: character_id -> float (0.0–1.0).
    # Written by web_server /train-lora when a LoRA passes identity gating.
    # Consumed by quality_max._inject_identity via char_lora_strength kwarg.
    # Absent key (or None) → tier default (e.g. 1.0 from params).
    char_lora_strengths: dict = field(default_factory=dict)
    # Style reference board for FLUX Redux (max tier). List of local paths.
    style_reference_paths: list = field(default_factory=list)

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


def get_project_setting(ctx, key: str, default=None):
    """Read a per-project UI setting from the request context.

    UI settings live in `project.global_settings` on the React side and are
    threaded into the pipeline via `ctx["global_settings"]` (a plain dict).
    This helper is the canonical read path for any user-tunable knob.

    Do NOT use `config.settings.Settings` for these — that frozen dataclass
    holds env-derived API keys + paths only, NOT per-project UI choices.
    Reading the wrong source was the source of the multi-month
    `tts_provider`-pattern bug where UI knobs silently did nothing.

    Args:
        ctx: PipelineContext, plain dict, or None. None-safe.
        key: setting name (must match the React TS Project type's snake_case key)
        default: value to return if key is missing or None.

    Returns:
        The setting value, or `default`.
    """
    if ctx is None:
        return default
    # PipelineContext exposes .get(); plain dicts have .get() too. Pass-through.
    try:
        gs = ctx.get("global_settings") if hasattr(ctx, "get") else None
    except Exception:
        return default
    if not gs:
        return default
    v = gs.get(key)
    return default if v is None else v


def _finite_or(value, default):
    """Coerce ``value`` to a finite float, else return ``default``.

    The canonical shared guard for numeric gate reads against a NaN/inf/
    non-coercible per-project setting. A bare ``NaN`` token survives in
    project.json because ``json.load`` defaults to ``allow_nan=True``, and a NaN
    defeats every numeric gate because ``score < NaN`` and ``score >= NaN`` are
    both False. ``float(NaN)`` succeeds, so a plain ``try/except`` around the
    cast does NOT catch it — this helper does.

    Placed beside ``get_project_setting`` as its read-side companion: callers
    read a knob via ``get_project_setting`` (or a settings ``.get``) then
    finite-guard it via ``_finite_or``. (quality_max keeps a documented-temporary
    local copy at ``quality_max:191`` pending a trivial import-swap to this one.)
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default
