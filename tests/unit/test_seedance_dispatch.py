"""Tests for the Seedance dispatch null-task_id guard (D1).

The Seedance branch reads ``task_id = resp.json().get("task_id") or
resp.json().get("id")``. If the POST response carries neither key, ``task_id``
is ``None`` and the old code still built ``.../v1/video/status/None`` and polled
it up to 120 times (5s sleep each) before giving up — a multi-minute hang on a
request that can never succeed.

A pre-poll guard must convert that into an *immediate* cascade to the next API:
the status endpoint must never be polled when there is no task id.

All network + sleep is mocked — no real Seedance calls, no real waiting.
"""
from __future__ import annotations

import dataclasses
from unittest.mock import patch, MagicMock

import pytest

import phase_c_ffmpeg


class _FakeResp:
    def __init__(self, payload, text="{}"):
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class TestSeedanceNullTaskIdGuard:
    def test_missing_task_id_cascades_without_polling(self, tmp_path):
        """POST 200 with no task_id/id must skip the poll loop entirely.

        Asserts the status endpoint is never hit — a missing task id is a dead
        request and must cascade immediately, not poll ``/status/None`` 120×.
        """
        img = tmp_path / "frame.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        out = str(tmp_path / "out.mp4")

        post_resp = _FakeResp({})            # no "task_id", no "id"
        poll_resp = _FakeResp({"status": "pending"})  # would loop forever pre-fix
        mock_get = MagicMock(return_value=poll_resp)

        # settings is a frozen dataclass; swap the module global for a copy with
        # the key forced truthy so the branch runs regardless of the ambient env.
        test_settings = dataclasses.replace(phase_c_ffmpeg.settings, seedance_api_key="test-key")

        with patch.object(phase_c_ffmpeg, "settings", test_settings), \
             patch.object(phase_c_ffmpeg.time, "sleep", lambda *_: None), \
             patch("requests.post", return_value=post_resp), \
             patch("requests.get", mock_get):
            result = phase_c_ffmpeg.generate_ai_video(
                image_path=str(img),
                camera_motion="static",
                target_api="SEEDANCE",
                output_mp4=out,
                video_fallbacks=["SEEDANCE"],  # nothing else to try → clean exhaust
            )

        assert mock_get.call_count == 0, (
            f"Seedance polled the status endpoint {mock_get.call_count}× with a null "
            f"task_id — must cascade immediately instead"
        )
        # Cascade exhausted with no usable engine → None (no false success).
        assert result is None
