"""Unit tests for the project-level default_male_voice / default_female_voice
fallback tier in generate_dialogue_voiceover's per-line voice resolution
(slice 9c).

Before this change, a character with no assigned voice_id (and no other
character's voice to borrow) fell straight to the PER-LANGUAGE static table
in domain/language_defaults.py -- the project's OWN "Default male voice" /
"Default female voice" pickers in VoiceSection.tsx were stored in
global_settings but never read here, even though they use the identical
field names (a same-name-different-source confusion the audit flagged
alongside the active TTS provider settings).

Fallback chain under test (see audio/dialogue.py generate_dialogue_voiceover):
  1. Any other character's assigned voice in this project      (VG-B1, unchanged)
  2. The project's OWN default_male_voice / default_female_voice   (NEW, this slice)
  3. The per-language static table (domain/language_defaults.py)   (unchanged, demoted)
  4. Adam hardcode                                                  (unchanged, last resort)

All HTTP calls are mocked; zero network activity during test execution.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


PROJECT_MALE_VOICE = "custom_male_voice_id_123"
PROJECT_FEMALE_VOICE = "custom_female_voice_id_456"


def _make_ctx(**extra_settings):
    from cinema.context import PipelineContext
    settings = {"language": "English", "forced_alignment_enabled": False}
    settings.update(extra_settings)
    return PipelineContext(global_settings=settings)


def _run_dialogue(dialogue_lines, characters, ctx, tmp_path, elevenlabs_voice_ids_seen):
    """Drive generate_dialogue_voiceover through PATH 2 (per-line ElevenLabs),
    capturing every voice_id passed to the (mocked) ElevenLabs client."""
    from audio import dialogue as dlg

    output = str(tmp_path / "out.mp3")

    mock_settings = MagicMock()
    mock_settings.cartesia_api_key = ""  # force ElevenLabs (no Cartesia key)

    mock_client = MagicMock()

    def fake_el_convert(**kw):
        elevenlabs_voice_ids_seen.append(kw.get("voice_id"))
        return b"fake_audio"
    mock_client.text_to_speech.convert.side_effect = fake_el_convert

    with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
         patch.object(dlg, "settings", mock_settings), \
         patch("audio.dialogue.client", mock_client), \
         patch("audio.dialogue.save") as mock_save, \
         patch("subprocess.run") as mock_subproc:

        def fake_save(audio_bytes, path):
            with open(path, "wb") as f:
                f.write(b"fake_mp3")
        mock_save.side_effect = fake_save

        def fake_subproc_run(args, *_a, **_kw):
            with open(args[-1], "wb") as f:
                f.write(b"assembled")
            return MagicMock(returncode=0)
        mock_subproc.side_effect = fake_subproc_run

        dlg.generate_dialogue_voiceover(dialogue_lines, characters, output, ctx=ctx)


class TestProjectDefaultVoiceFallback:
    def test_no_voice_id_uses_project_default_male_voice(self, tmp_path):
        """Character has no voice_id, no other character to borrow from,
        gender=male -> the project's OWN default_male_voice is used, NOT
        the per-language static table's Adam id."""
        ctx = _make_ctx(default_male_voice=PROJECT_MALE_VOICE)
        dialogue_lines = [{"character_id": "c1", "text": "Hello", "delivery": "natural"}]
        characters = [{"id": "c1", "name": "Bob", "gender": "male"}]  # no voice_id

        seen: list = []
        _run_dialogue(dialogue_lines, characters, ctx, tmp_path, seen)

        assert seen == [PROJECT_MALE_VOICE]

    def test_no_voice_id_uses_project_default_female_voice(self, tmp_path):
        """Same, gender unspecified -> defaults to the female tier per the
        existing "default to female unless explicit male hint" rule."""
        ctx = _make_ctx(default_female_voice=PROJECT_FEMALE_VOICE)
        dialogue_lines = [{"character_id": "c1", "text": "Hello", "delivery": "natural"}]
        characters = [{"id": "c1", "name": "Alice"}]  # no gender, no voice_id

        seen: list = []
        _run_dialogue(dialogue_lines, characters, ctx, tmp_path, seen)

        assert seen == [PROJECT_FEMALE_VOICE]

    def test_absent_project_default_falls_through_to_language_table(self, tmp_path):
        """Regression guard: when the project has NOT configured a default
        voice, behavior is unchanged -- falls to the per-language static
        table (English female default: Rachel, 21m00Tcm4TlvDq8ikWAM)."""
        ctx = _make_ctx()  # no default_male_voice / default_female_voice
        dialogue_lines = [{"character_id": "c1", "text": "Hello", "delivery": "natural"}]
        characters = [{"id": "c1", "name": "Alice"}]

        seen: list = []
        _run_dialogue(dialogue_lines, characters, ctx, tmp_path, seen)

        assert seen == ["21m00Tcm4TlvDq8ikWAM"]  # English default_female_voice (Rachel)

    def test_another_characters_voice_still_wins_over_project_default(self, tmp_path):
        """Ordering guard: tier 1 (borrow any other assigned voice in this
        project, VG-B1) must still outrank the new tier 2 (project default)
        -- the new tier was inserted BELOW tier 1, not above it."""
        ctx = _make_ctx(default_male_voice=PROJECT_MALE_VOICE)
        dialogue_lines = [
            {"character_id": "c1", "text": "Hi", "delivery": "natural"},
            {"character_id": "c2", "text": "Hello", "delivery": "natural"},
        ]
        # c1 has an assigned voice; c2 does not and should borrow c1's,
        # NOT fall through to the project's configured default_male_voice.
        characters = [
            {"id": "c1", "name": "Zed", "voice_id": "already_assigned_voice"},
            {"id": "c2", "name": "Bob", "gender": "male"},
        ]

        seen: list = []
        _run_dialogue(dialogue_lines, characters, ctx, tmp_path, seen)

        assert seen == ["already_assigned_voice", "already_assigned_voice"]
