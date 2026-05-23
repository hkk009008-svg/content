"""Shared ElevenLabs client singleton for the ``audio`` package.

Sibling modules (``audio.voiceover``, ``audio.foley``, ``audio.dialogue``)
all share this one eager top-level instance — no lazy imports, no
circular-dependency dance. The leading underscore is intentional: this
is package-internal. External code should import directly from the
specific consumer module (``audio.dialogue``, ``audio.foley``, etc.)
rather than reaching for ``audio._client.client``.
"""

from elevenlabs.client import ElevenLabs

from config.settings import settings

client = ElevenLabs(
    api_key=settings.elevenlabs_api_key,
)
