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
