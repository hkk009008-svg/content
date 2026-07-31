"""Forced-alignment write-only warning (capacity audit wf_6be2ee18-f4b).

_maybe_save_alignment writes a .alignment.json sidecar that load_alignment_json
never reads (zero callers — write-only dead chain). Until a consumer is wired,
running it spends compute (WhisperX/whisper) for no output. This asserts the
function warns operators of that, so the cost is visible.
"""
from unittest.mock import MagicMock, patch

import pytest


class TestAlignmentWriteOnlyWarning:
    def test_maybe_save_alignment_warns_when_no_consumer(self, tmp_path):
        import audio.dialogue as dialogue

        fake = MagicMock()
        fake.words = [MagicMock()]
        fake.provider = "whisper"

        def _settings(ctx, key, default=None):
            if key == "forced_alignment_enabled":
                return True
            return default if default is not None else "English"

        with patch.object(dialogue, "get_project_setting", side_effect=_settings), \
             patch("audio.alignment.align_audio_to_text", return_value=fake), \
             patch("audio.alignment.save_alignment_json", return_value=None):
            with pytest.warns(UserWarning, match="consumer"):
                dialogue._maybe_save_alignment(str(tmp_path / "out.mp3"))


class TestForcedAlignmentDefaultReconciliation:
    """Slice 9c: the gate's own fallback default must match VoiceSection's
    display default (`s.forced_alignment_enabled !== false` -> ON when unset)
    and every domain/language_defaults.py entry (`forced_alignment_enabled:
    True`). Before this fix, `get_project_setting(ctx, "forced_alignment_enabled",
    False)` disagreed with both — a project that never wrote the key showed
    the toggle ON but silently never ran alignment.
    """

    def test_absent_key_now_defaults_to_enabled(self, tmp_path):
        """ctx with NO forced_alignment_enabled key must still run alignment
        (default reconciled to True), matching the UI's default-on toggle."""
        import audio.dialogue as dialogue
        from cinema.context import PipelineContext

        fake = MagicMock()
        fake.words = [MagicMock()]
        fake.provider = "whisper"

        # global_settings deliberately omits forced_alignment_enabled.
        ctx = PipelineContext(global_settings={"language": "English"})

        with patch("audio.alignment.align_audio_to_text", return_value=fake) as mock_align, \
             patch("audio.alignment.save_alignment_json", return_value=None):
            with pytest.warns(UserWarning, match="consumer"):
                result = dialogue._maybe_save_alignment(str(tmp_path / "out.mp3"), ctx=ctx)

        mock_align.assert_called_once()
        assert result is not None

    def test_ctx_none_now_defaults_to_enabled(self, tmp_path):
        """ctx=None (CLI path with no per-project settings) also defaults to
        enabled — get_project_setting(None, key, default) returns `default`,
        which must now be True."""
        import audio.dialogue as dialogue

        fake = MagicMock()
        fake.words = [MagicMock()]
        fake.provider = "whisper"

        with patch("audio.alignment.align_audio_to_text", return_value=fake) as mock_align, \
             patch("audio.alignment.save_alignment_json", return_value=None):
            with pytest.warns(UserWarning, match="consumer"):
                dialogue._maybe_save_alignment(str(tmp_path / "out.mp3"))

        mock_align.assert_called_once()

    def test_explicit_false_still_disables(self, tmp_path):
        """An explicit False must still skip alignment — only the ABSENT-key
        default changed, not the ability to opt out."""
        import audio.dialogue as dialogue
        from cinema.context import PipelineContext

        ctx = PipelineContext(global_settings={"forced_alignment_enabled": False})

        with patch("audio.alignment.align_audio_to_text") as mock_align:
            result = dialogue._maybe_save_alignment(str(tmp_path / "out.mp3"), ctx=ctx)

        mock_align.assert_not_called()
        assert result is None
