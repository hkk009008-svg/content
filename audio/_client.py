"""Shared ElevenLabs client singleton for the ``audio`` package.

Phase 6 slice 5 extracted the ``client = ElevenLabs(...)`` module-level
instance out of ``phase_b_audio.py`` into this private submodule so
sibling modules (``audio.voiceover``, ``audio.foley``, eventually
``audio.dialogue``) can share one client with a single eager top-level
import — no lazy imports, no circular-dependency dance.

The leading underscore is intentional: this is package-internal. External
code should keep using ``phase_b_audio.client`` (re-exported), which
preserves REFACTOR_HANDOFF.md invariant #7 (``phase_b_audio.client`` is an
``ElevenLabs`` instance).
"""

from elevenlabs.client import ElevenLabs

from config.settings import settings

client = ElevenLabs(
    api_key=settings.elevenlabs_api_key,
)
