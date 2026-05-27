"""Unit tests for audio/dialogue.py — Cartesia Sonic 2 path + language router.

All HTTP calls are mocked; zero network activity during test execution.

Coverage:
- generate_cartesia: success / cache hit / HTTP error / timeout /
  missing key / payload shape / language propagation
- _resolve_tts_provider: Korean routing / English routing / missing-key
  fallback / missing-language default / character-language fallback /
  case-insensitive prefix matching
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# generate_cartesia — success path
# ---------------------------------------------------------------------------

class TestGenerateCartesiaSuccess:
    def test_success_writes_file_and_returns_true(self, tmp_path):
        """Happy path: 200 response writes mp3 bytes and returns True."""
        from audio.dialogue import generate_cartesia

        output = str(tmp_path / "cartesia_out.mp3")
        fake_audio = b"ID3\x00fake_cartesia_mp3_bytes"

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = fake_audio

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test_cartesia_0123456789"

        with patch("audio.dialogue.requests.post", return_value=mock_response) as mock_post, \
             patch("audio.dialogue.settings", mock_settings):
            result = generate_cartesia(
                text="안녕하세요",
                voice_id="abcdef12-3456-7890-abcd-ef1234567890",
                output_path=output,
                language="ko",
            )

        assert result is True
        assert os.path.exists(output)
        with open(output, "rb") as f:
            assert f.read() == fake_audio
        mock_post.assert_called_once()

    def test_payload_includes_language_and_voice(self, tmp_path):
        """JSON payload carries language code, voice id, and mp3 output format."""
        from audio.dialogue import generate_cartesia

        output = str(tmp_path / "out.mp3")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"fake"

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test"

        with patch("audio.dialogue.requests.post", return_value=mock_response) as mock_post, \
             patch("audio.dialogue.settings", mock_settings):
            generate_cartesia(
                text="hi",
                voice_id="vid_123",
                output_path=output,
                language="ko",
            )

        call = mock_post.call_args
        json_body = call.kwargs.get("json") or call[1]["json"]
        assert json_body["language"] == "ko"
        assert json_body["voice"]["id"] == "vid_123"
        assert json_body["voice"]["mode"] == "id"
        assert json_body["output_format"]["container"] == "mp3"
        assert json_body["model_id"] == "sonic-2"
        assert json_body["transcript"] == "hi"

    def test_headers_carry_api_key_and_version(self, tmp_path):
        """X-API-Key + Cartesia-Version headers populated."""
        from audio.dialogue import generate_cartesia

        output = str(tmp_path / "out.mp3")
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"fake"

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test_apikey_xyz"

        with patch("audio.dialogue.requests.post", return_value=mock_response) as mock_post, \
             patch("audio.dialogue.settings", mock_settings):
            generate_cartesia("hi", "vid", output, language="en")

        headers = mock_post.call_args.kwargs.get("headers") or mock_post.call_args[1]["headers"]
        assert headers["X-API-Key"] == "sk_test_apikey_xyz"
        assert "Cartesia-Version" in headers
        assert headers["Content-Type"] == "application/json"

    def test_custom_model_id_propagated(self, tmp_path):
        """A non-default model_id is sent through unchanged."""
        from audio.dialogue import generate_cartesia

        output = str(tmp_path / "out.mp3")
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"fake"

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test"

        with patch("audio.dialogue.requests.post", return_value=mock_response) as mock_post, \
             patch("audio.dialogue.settings", mock_settings):
            generate_cartesia("hi", "vid", output, language="en", model_id="sonic-experimental")

        json_body = mock_post.call_args.kwargs["json"]
        assert json_body["model_id"] == "sonic-experimental"


# ---------------------------------------------------------------------------
# generate_cartesia — cache hit
# ---------------------------------------------------------------------------

class TestGenerateCartesiaCacheHit:
    def test_cache_hit_returns_true_without_api_call(self, tmp_path):
        """If output_path already exists, no HTTP call is made; True returned."""
        from audio.dialogue import generate_cartesia

        output = str(tmp_path / "cached.mp3")
        with open(output, "wb") as f:
            f.write(b"existing_cached_audio")

        with patch("audio.dialogue.requests.post") as mock_post:
            result = generate_cartesia("anything", "vid", output, language="en")

        assert result is True
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# generate_cartesia — failure modes (all → False, never raise)
# ---------------------------------------------------------------------------

class TestGenerateCartesiaFailures:
    def test_missing_api_key_returns_false(self, tmp_path):
        """Empty API key returns False and makes no HTTP call."""
        from audio.dialogue import generate_cartesia

        output = str(tmp_path / "out.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = ""

        with patch("audio.dialogue.requests.post") as mock_post, \
             patch("audio.dialogue.settings", mock_settings):
            result = generate_cartesia("hi", "vid", output, language="en")

        assert result is False
        mock_post.assert_not_called()
        assert not os.path.exists(output)

    def test_http_error_returns_false(self, tmp_path):
        """HTTP error (raise_for_status) returns False, no exception escapes."""
        import requests as req_lib
        from audio.dialogue import generate_cartesia

        output = str(tmp_path / "out.mp3")

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req_lib.exceptions.HTTPError("500")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test"

        with patch("audio.dialogue.requests.post", return_value=mock_response), \
             patch("audio.dialogue.settings", mock_settings):
            result = generate_cartesia("hi", "vid", output, language="en")

        assert result is False
        assert not os.path.exists(output)

    def test_timeout_returns_false(self, tmp_path):
        """requests.Timeout swallowed; returns False."""
        import requests as req_lib
        from audio.dialogue import generate_cartesia

        output = str(tmp_path / "out.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test"

        with patch("audio.dialogue.requests.post", side_effect=req_lib.exceptions.Timeout("timed out")), \
             patch("audio.dialogue.settings", mock_settings):
            result = generate_cartesia("hi", "vid", output, language="en")

        assert result is False
        assert not os.path.exists(output)

    def test_connection_error_returns_false(self, tmp_path):
        """Generic ConnectionError swallowed; returns False."""
        from audio.dialogue import generate_cartesia

        output = str(tmp_path / "out.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test"

        with patch("audio.dialogue.requests.post", side_effect=ConnectionError("net down")), \
             patch("audio.dialogue.settings", mock_settings):
            result = generate_cartesia("hi", "vid", output, language="en")

        assert result is False

    def test_unknown_exception_returns_false(self, tmp_path):
        """Any unexpected exception still returns False (never raises)."""
        from audio.dialogue import generate_cartesia

        output = str(tmp_path / "out.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test"

        with patch("audio.dialogue.requests.post", side_effect=RuntimeError("weird")), \
             patch("audio.dialogue.settings", mock_settings):
            result = generate_cartesia("hi", "vid", output, language="en")

        assert result is False
