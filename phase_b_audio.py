"""Legacy ``phase_b_audio`` module — backward-compat re-export shim.

Phase 6 of the architecture refactor split this file (originally
1,348 lines) across focused submodules under ``audio/``. This shim
preserves the legacy ``from phase_b_audio import X`` import surface
so existing callers (main.py, web_server.py, cinema_pipeline.py,
tests, etc.) keep working unchanged. New code should import from
``audio.*`` directly.

Migration history (each line = one commit on
``refactor/architecture-cleanup``):

  slice 1 → audio/srt.py        — generate_srt
  slice 2 → audio/music.py      — generate_fal_bgm, master_music,
                                  MUSIC_MASTERING_PRESETS
  slice 3 → audio/foley.py      — generate_scene_foley(_library),
                                  generate_layered_foley, three pure
                                  _build_*_prompt helpers
  slice 4 → audio/effects.py    — apply_au_plugin, apply_pedalboard_chain,
                                  apply_voice_effect, list_au_plugins,
                                  VOICE_EFFECTS, PEDALBOARD_AVAILABLE
  slice 5 → audio/voiceover.py  — generate_voiceover, generate_narration,
                                  generate_single_line_audio,
                                  get_voice_direction, VOICE_DIRECTIONS,
                                  DELIVERY_STYLES, NARRATOR_VOICES
  slice 5 → audio/_client.py    — shared ElevenLabs client singleton
                                  (re-exported here for invariant #7)
  slice 6 → audio/dialogue.py   — generate_dialogue_voiceover

At this point the file has no function bodies of its own; it is purely
a re-export surface. See REFACTOR_HANDOFF.md §13 tip 3 for the
deletion criteria once all callers migrate to ``audio.*`` paths.
"""

# Shared ElevenLabs client — re-exported from audio._client so that
# ``phase_b_audio.client`` continues to resolve to the same instance
# used everywhere else (REFACTOR_HANDOFF.md invariant #7).
from audio._client import client  # noqa: F401

from audio.srt import generate_srt  # noqa: F401

from audio.music import (  # noqa: F401
    generate_fal_bgm,
    master_music,
    MUSIC_MASTERING_PRESETS,
)

from audio.effects import (  # noqa: F401
    apply_au_plugin,
    apply_pedalboard_chain,
    apply_voice_effect,
    list_au_plugins,
    VOICE_EFFECTS,
    PEDALBOARD_AVAILABLE,
)

from audio.voiceover import (  # noqa: F401
    generate_voiceover,
    generate_narration,
    generate_single_line_audio,
    get_voice_direction,
    VOICE_DIRECTIONS,
    DELIVERY_STYLES,
    NARRATOR_VOICES,
)

from audio.dialogue import generate_dialogue_voiceover  # noqa: F401

from audio.foley import (  # noqa: F401
    generate_scene_foley,
    generate_layered_foley,
    generate_scene_foley_library,
    _build_ambience_prompt,
    _build_action_prompt,
    _build_texture_prompt,
)
