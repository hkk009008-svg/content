"""Unit tests for audio/foley.py — Stability AI Stable Audio 2.0 path.

All HTTP calls are mocked; zero network activity during test execution.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from audio.foley import _build_foley_prompt, generate_stability_foley


# ---------------------------------------------------------------------------
# _build_foley_prompt
# ---------------------------------------------------------------------------

class TestBuildFoleyPrompt:
    def test_known_vibe_returns_elaborated_prompt(self):
        """A recognized descriptor returns a detailed producer-grade prompt."""
        result = _build_foley_prompt("rain")
        assert len(result) > len("rain")
        assert "rain" in result.lower()

    def test_known_vibe_crowd(self):
        result = _build_foley_prompt("crowd")
        assert "crowd" in result.lower() or "murmur" in result.lower()

    def test_fallback_returns_raw_string(self):
        """Unknown descriptor falls through and returns the raw input."""
        raw = "crackling neon signs in a dystopian alley"
        result = _build_foley_prompt(raw)
        assert result == raw

    def test_known_vibe_case_insensitive(self):
        """Lookup is case-insensitive (normalised to lower)."""
        result_lower = _build_foley_prompt("forest")
        result_upper = _build_foley_prompt("FOREST")
        assert result_lower == result_upper

    def test_known_vibe_space_normalised(self):
        """Spaces in descriptor are normalised to underscores for lookup."""
        result_underscore = _build_foley_prompt("light_rain")
        result_space = _build_foley_prompt("light rain")
        assert result_underscore == result_space


# ---------------------------------------------------------------------------
# generate_stability_foley
# ---------------------------------------------------------------------------

class TestGenerateStabilityFoley:

    # ---- success path -------------------------------------------------------

    def test_success_writes_file_and_returns_path(self, tmp_path):
        """Happy path: successful response writes mp3 bytes and returns output_path."""
        output = str(tmp_path / "foley_out.mp3")
        fake_audio = b"ID3\x00fake_mp3_bytes"

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = fake_audio

        mock_settings = MagicMock()
        mock_settings.stability_api_key = "sk-test-key-0123456789"

        with patch("audio.foley.requests.post", return_value=mock_response) as mock_post, \
             patch("audio.foley.settings", mock_settings):
            result = generate_stability_foley("rain ambience", output)

        assert result == output
        assert os.path.exists(output)
        with open(output, "rb") as f:
            assert f.read() == fake_audio
        mock_post.assert_called_once()

    # ---- cache hit ----------------------------------------------------------

    def test_cache_hit_returns_path_without_api_call(self, tmp_path):
        """If output_path already exists, no HTTP call is made."""
        output = str(tmp_path / "cached.mp3")
        # Pre-create the file to simulate a cache hit
        with open(output, "wb") as f:
            f.write(b"cached_audio")

        with patch("audio.foley.requests.post") as mock_post:
            result = generate_stability_foley("rain", output)

        assert result == output
        mock_post.assert_not_called()

    # ---- missing API key ----------------------------------------------------

    def test_no_api_key_returns_none(self, tmp_path):
        """Empty API key returns None and makes no HTTP call."""
        output = str(tmp_path / "foley.mp3")

        mock_settings = MagicMock()
        mock_settings.stability_api_key = ""

        with patch("audio.foley.requests.post") as mock_post, \
             patch("audio.foley.settings", mock_settings):
            result = generate_stability_foley("rain", output)

        assert result is None
        mock_post.assert_not_called()
        assert not os.path.exists(output)

    # ---- HTTP error ---------------------------------------------------------

    def test_http_error_returns_none(self, tmp_path):
        """HTTP error (raise_for_status) returns None (no exception propagation)."""
        import requests as req_lib
        output = str(tmp_path / "foley.mp3")

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req_lib.exceptions.HTTPError("500 Server Error")

        mock_settings = MagicMock()
        mock_settings.stability_api_key = "sk-test-key-0123456789"

        with patch("audio.foley.requests.post", return_value=mock_response), \
             patch("audio.foley.settings", mock_settings):
            result = generate_stability_foley("rain", output)

        assert result is None
        assert not os.path.exists(output)

    # ---- exception from requests --------------------------------------------

    def test_exception_returns_none(self, tmp_path):
        """requests.post raising does not propagate; returns None."""
        output = str(tmp_path / "foley.mp3")

        mock_settings = MagicMock()
        mock_settings.stability_api_key = "sk-test-key-0123456789"

        with patch("audio.foley.requests.post", side_effect=ConnectionError("network down")), \
             patch("audio.foley.settings", mock_settings):
            result = generate_stability_foley("rain", output)

        assert result is None

    # ---- duration cap -------------------------------------------------------

    def test_duration_capped_at_190(self, tmp_path):
        """Duration > 190 is clamped to 190 in the multipart form data."""
        output = str(tmp_path / "foley.mp3")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"fake"

        mock_settings = MagicMock()
        mock_settings.stability_api_key = "sk-test-key-0123456789"

        with patch("audio.foley.requests.post", return_value=mock_response) as mock_post, \
             patch("audio.foley.settings", mock_settings):
            generate_stability_foley("rain", output, duration=300)

        call_kwargs = mock_post.call_args
        files_arg = call_kwargs.kwargs.get("files") or call_kwargs[1]["files"]
        # files dict maps field name -> (None, value_string)
        duration_val = files_arg["duration"][1]
        assert duration_val == "190"

    # ---- duration boundary cases -------------------------------------------

    def test_duration_exact_cap(self, tmp_path):
        """duration=190 (exact cap) produces '190' in form data."""
        output = str(tmp_path / "foley_190.mp3")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"fake"

        mock_settings = MagicMock()
        mock_settings.stability_api_key = "sk-test-key-0123456789"

        with patch("audio.foley.requests.post", return_value=mock_response) as mock_post, \
             patch("audio.foley.settings", mock_settings):
            generate_stability_foley("rain", output, duration=190)

        files_arg = mock_post.call_args.kwargs.get("files") or mock_post.call_args[1]["files"]
        assert files_arg["duration"][1] == "190"

    def test_duration_first_over_cap(self, tmp_path):
        """duration=191 (first-over) is clamped to '190'."""
        output = str(tmp_path / "foley_191.mp3")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"fake"

        mock_settings = MagicMock()
        mock_settings.stability_api_key = "sk-test-key-0123456789"

        with patch("audio.foley.requests.post", return_value=mock_response) as mock_post, \
             patch("audio.foley.settings", mock_settings):
            generate_stability_foley("rain", output, duration=191)

        files_arg = mock_post.call_args.kwargs.get("files") or mock_post.call_args[1]["files"]
        assert files_arg["duration"][1] == "190"

    def test_duration_float_rounds_up(self, tmp_path):
        """duration=5.5 rounds to 6 (not truncated to 5)."""
        output = str(tmp_path / "foley_5_5.mp3")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"fake"

        mock_settings = MagicMock()
        mock_settings.stability_api_key = "sk-test-key-0123456789"

        with patch("audio.foley.requests.post", return_value=mock_response) as mock_post, \
             patch("audio.foley.settings", mock_settings):
            generate_stability_foley("rain", output, duration=5.5)

        files_arg = mock_post.call_args.kwargs.get("files") or mock_post.call_args[1]["files"]
        assert files_arg["duration"][1] == "6"

    # ---- seed propagation ---------------------------------------------------

    def test_seed_passed_when_provided(self, tmp_path):
        """seed=42 appears as '42' in the form data."""
        output = str(tmp_path / "foley.mp3")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"fake"

        mock_settings = MagicMock()
        mock_settings.stability_api_key = "sk-test-key-0123456789"

        with patch("audio.foley.requests.post", return_value=mock_response) as mock_post, \
             patch("audio.foley.settings", mock_settings):
            generate_stability_foley("rain", output, seed=42)

        files_arg = mock_post.call_args.kwargs.get("files") or mock_post.call_args[1]["files"]
        assert "seed" in files_arg
        assert files_arg["seed"][1] == "42"

    def test_seed_omitted_when_none(self, tmp_path):
        """seed=None means no 'seed' key in the multipart form."""
        output = str(tmp_path / "foley.mp3")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"fake"

        mock_settings = MagicMock()
        mock_settings.stability_api_key = "sk-test-key-0123456789"

        with patch("audio.foley.requests.post", return_value=mock_response) as mock_post, \
             patch("audio.foley.settings", mock_settings):
            generate_stability_foley("rain", output, seed=None)

        files_arg = mock_post.call_args.kwargs.get("files") or mock_post.call_args[1]["files"]
        assert "seed" not in files_arg
