"""Tests for the Hedra Character-3 dispatch null-generation-id guard (D1 sibling).

generate_talking_head extracted ``gid = g.json()["id"]``. A present-but-null id
(``{"id": null}``) made ``gid`` None, and the code still polled
``/generations/None/status`` up to 150×5s ≈ 12.5 min before timing out — the same
hang class as the Seedance null-task_id bug (D1), here in the hot
lipsync-generation ATTEMPT-0 path. A guard must cascade (return None) at once
instead of polling a dead id.

All network + sleep is mocked — no real Hedra calls, no real waiting.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import hedra_native


class TestHedraNullGenerationId:
    def test_null_generation_id_returns_none_without_polling(self, tmp_path):
        img = tmp_path / "face.png"
        img.write_bytes(b"img-bytes")
        aud = tmp_path / "voice.mp3"
        aud.write_bytes(b"aud-bytes")
        out = str(tmp_path / "talking.mp4")

        api = hedra_native.HedraAPI()
        api._key = "test-key"  # ensure the empty-key short-circuit (line 86) doesn't fire

        gen_resp = MagicMock(status_code=200, text='{"id": null}')
        gen_resp.json.return_value = {"id": None}  # present but null → gid would be None
        poll_resp = MagicMock()
        poll_resp.raise_for_status.return_value = None
        poll_resp.json.return_value = {"status": "processing", "progress": 0.5}
        mock_get = MagicMock(return_value=poll_resp)

        with patch.object(api, "_create_and_upload", side_effect=["img_id", "aud_id"]), \
             patch("hedra_native.requests.post", return_value=gen_resp), \
             patch("hedra_native.requests.get", mock_get), \
             patch("hedra_native.time.sleep", lambda *_: None):
            result = api.generate_talking_head(str(img), str(aud), out)

        assert result is None
        assert mock_get.call_count == 0, (
            f"Hedra polled /status {mock_get.call_count}× with a null generation id — "
            f"must cascade immediately instead of hanging ~12.5 min"
        )
