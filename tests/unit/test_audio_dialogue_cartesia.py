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


# ---------------------------------------------------------------------------
# _resolve_tts_provider — language routing
# ---------------------------------------------------------------------------

class TestResolveTtsProvider:
    """The router selects CARTESIA_SONIC_2 for Korean when the key is set;
    ELEVENLABS otherwise. Scene-level language wins over character-level;
    both fall back to "en"/ELEVENLABS when absent.
    """

    def _settings(self, key: str = "sk_test_cartesia"):
        s = MagicMock()
        s.cartesia_api_key = key
        return s

    # ---- Korean routing -----------------------------------------------------

    def test_korean_scene_routes_to_cartesia(self):
        from audio.dialogue import _resolve_tts_provider
        scene = {"language": "ko"}
        char = {}
        result = _resolve_tts_provider(scene, char, self._settings())
        assert result == "CARTESIA_SONIC_2"

    def test_ko_kr_locale_routes_to_cartesia(self):
        """`ko_KR` (full locale code) also matches Korean."""
        from audio.dialogue import _resolve_tts_provider
        result = _resolve_tts_provider({"language": "ko_KR"}, {}, self._settings())
        assert result == "CARTESIA_SONIC_2"

    def test_human_name_korean_routes_to_cartesia(self):
        """`"Korean"` (human name from PIPELINE_LANGUAGE_DEFAULTS) starts with
        case-insensitive "ko" and routes correctly."""
        from audio.dialogue import _resolve_tts_provider
        result = _resolve_tts_provider({"language": "Korean"}, {}, self._settings())
        assert result == "CARTESIA_SONIC_2"

    def test_case_insensitive_match(self):
        from audio.dialogue import _resolve_tts_provider
        result = _resolve_tts_provider({"language": "KO_KR"}, {}, self._settings())
        assert result == "CARTESIA_SONIC_2"

    def test_character_language_fallback_when_scene_missing(self):
        """Scene lacks language → fall back to character language."""
        from audio.dialogue import _resolve_tts_provider
        result = _resolve_tts_provider({}, {"language": "ko"}, self._settings())
        assert result == "CARTESIA_SONIC_2"

    def test_scene_language_wins_over_character_language(self):
        """Scene language takes precedence — English scene with Korean char."""
        from audio.dialogue import _resolve_tts_provider
        result = _resolve_tts_provider({"language": "en"}, {"language": "ko"}, self._settings())
        assert result == "ELEVENLABS"

    # ---- English / non-Korean routing --------------------------------------

    def test_english_routes_to_elevenlabs(self):
        from audio.dialogue import _resolve_tts_provider
        result = _resolve_tts_provider({"language": "en"}, {}, self._settings())
        assert result == "ELEVENLABS"

    def test_japanese_routes_to_elevenlabs(self):
        """Other multilingual languages stay on ElevenLabs multilingual."""
        from audio.dialogue import _resolve_tts_provider
        result = _resolve_tts_provider({"language": "ja"}, {}, self._settings())
        assert result == "ELEVENLABS"

    def test_mandarin_routes_to_elevenlabs(self):
        from audio.dialogue import _resolve_tts_provider
        result = _resolve_tts_provider({"language": "zh_CN"}, {}, self._settings())
        assert result == "ELEVENLABS"

    def test_missing_language_defaults_to_elevenlabs(self):
        """Neither scene nor character has language → default `en` → ElevenLabs."""
        from audio.dialogue import _resolve_tts_provider
        result = _resolve_tts_provider({}, {}, self._settings())
        assert result == "ELEVENLABS"

    # ---- Cartesia key missing → fallback to ElevenLabs even for Korean ------

    def test_korean_without_cartesia_key_falls_back_to_elevenlabs(self):
        """CARTESIA_API_KEY unset → Korean still routes to ElevenLabs (graceful)."""
        from audio.dialogue import _resolve_tts_provider
        result = _resolve_tts_provider({"language": "ko"}, {}, self._settings(key=""))
        assert result == "ELEVENLABS"

    def test_korean_with_none_cartesia_key_falls_back_to_elevenlabs(self):
        """`None` API key (not just empty string) also falls back."""
        from audio.dialogue import _resolve_tts_provider
        s = MagicMock()
        s.cartesia_api_key = None
        result = _resolve_tts_provider({"language": "ko"}, {}, s)
        assert result == "ELEVENLABS"

    # ---- Defensive: None inputs handled ------------------------------------

    def test_none_scene_and_character_default_to_elevenlabs(self):
        """Robustness — None inputs don't crash; default to ELEVENLABS."""
        from audio.dialogue import _resolve_tts_provider
        result = _resolve_tts_provider(None, None, self._settings())
        assert result == "ELEVENLABS"


# ---------------------------------------------------------------------------
# Dispatcher integration in generate_dialogue_voiceover
# ---------------------------------------------------------------------------

class TestDispatcherIntegration:
    """End-to-end-ish tests for generate_dialogue_voiceover routing per language.

    Bypass PATH 1 (ElevenLabs Dialogue Mode) by forcing _try_dialogue_mode
    to None; verify the per-line PATH 2 dispatcher selects Cartesia for
    Korean and ElevenLabs for English. Subprocess concat is mocked.
    """

    def _make_ctx(self, language: str = "English"):
        """Build a PipelineContext-shape with the project language set."""
        from cinema.context import PipelineContext
        return PipelineContext(global_settings={"language": language})

    def test_korean_pipeline_routes_to_cartesia(self, tmp_path, monkeypatch):
        """Korean project language → per-line Cartesia generation."""
        from audio import dialogue as dlg

        dialogue_lines = [
            {"character_id": "char1", "text": "안녕하세요", "delivery": "natural"},
        ]
        characters = [{"id": "char1", "name": "준호", "voice_id": "vid_korean_male"}]
        output = str(tmp_path / "ko_dialogue.mp3")

        # Force Cartesia success
        cartesia_calls = []
        def fake_cartesia(text, voice_id, output_path, language="en", model_id="sonic-2"):
            cartesia_calls.append({"text": text, "voice_id": voice_id, "language": language})
            with open(output_path, "wb") as f:
                f.write(b"fake_cartesia_mp3")
            return True

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test_cartesia"

        # Mock subprocess to skip ffmpeg and the elevenlabs SDK to avoid imports
        with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
             patch.object(dlg, "generate_cartesia", side_effect=fake_cartesia), \
             patch.object(dlg, "settings", mock_settings), \
             patch("audio.dialogue.client") as mock_client, \
             patch("subprocess.run") as mock_subproc:

            # Make subprocess "succeed" — create the silence + output files
            def fake_subproc_run(args, *_args, **_kw):
                # Last arg is output filename for both lavfi and concat calls
                out = args[-1]
                with open(out, "wb") as f:
                    f.write(b"fake_audio_assembled")
                return MagicMock(returncode=0)
            mock_subproc.side_effect = fake_subproc_run

            ctx = self._make_ctx(language="Korean")
            result = dlg.generate_dialogue_voiceover(
                dialogue_lines, characters, output, ctx=ctx
            )

        # Cartesia was called (Korean routing succeeded)
        assert len(cartesia_calls) == 1
        assert cartesia_calls[0]["language"] == "ko"
        assert cartesia_calls[0]["voice_id"] == "vid_korean_male"
        # ElevenLabs was NOT called for the Cartesia line
        assert not mock_client.text_to_speech.convert.called

    def test_english_pipeline_routes_to_elevenlabs(self, tmp_path):
        """English project language → ElevenLabs path; Cartesia not called."""
        from audio import dialogue as dlg

        dialogue_lines = [
            {"character_id": "char1", "text": "Hello there", "delivery": "natural"},
        ]
        characters = [{"id": "char1", "name": "Alice", "voice_id": "vid_english"}]
        output = str(tmp_path / "en_dialogue.mp3")

        cartesia_calls = []
        def fake_cartesia(*args, **kw):
            cartesia_calls.append(kw)
            return True

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test_cartesia"

        with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
             patch.object(dlg, "generate_cartesia", side_effect=fake_cartesia), \
             patch.object(dlg, "settings", mock_settings), \
             patch("audio.dialogue.client") as mock_client, \
             patch("audio.dialogue.save") as mock_save, \
             patch("subprocess.run") as mock_subproc:

            mock_client.text_to_speech.convert.return_value = b"el_audio_bytes"

            def fake_subproc_run(args, *_args, **_kw):
                out = args[-1]
                with open(out, "wb") as f:
                    f.write(b"fake_audio_assembled")
                return MagicMock(returncode=0)
            mock_subproc.side_effect = fake_subproc_run

            # Mock save to actually create the temp file
            def fake_save(audio_bytes, path):
                with open(path, "wb") as f:
                    f.write(b"fake_eleven_mp3")
            mock_save.side_effect = fake_save

            ctx = self._make_ctx(language="English")
            result = dlg.generate_dialogue_voiceover(
                dialogue_lines, characters, output, ctx=ctx
            )

        # ElevenLabs was called
        assert mock_client.text_to_speech.convert.called
        # Cartesia was NOT called for English
        assert len(cartesia_calls) == 0

    def test_korean_cartesia_failure_falls_back_to_elevenlabs(self, tmp_path):
        """Cartesia returning False triggers ElevenLabs fallback in same loop."""
        from audio import dialogue as dlg

        dialogue_lines = [
            {"character_id": "char1", "text": "안녕", "delivery": "natural"},
        ]
        characters = [{"id": "char1", "name": "준호", "voice_id": "vid_kr"}]
        output = str(tmp_path / "fallback.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test"

        with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
             patch.object(dlg, "generate_cartesia", return_value=False), \
             patch.object(dlg, "settings", mock_settings), \
             patch("audio.dialogue.client") as mock_client, \
             patch("audio.dialogue.save") as mock_save, \
             patch("subprocess.run") as mock_subproc:

            mock_client.text_to_speech.convert.return_value = b"el_fallback_bytes"

            def fake_save(audio_bytes, path):
                with open(path, "wb") as f:
                    f.write(b"fake_fallback_mp3")
            mock_save.side_effect = fake_save

            def fake_subproc_run(args, *_args, **_kw):
                out = args[-1]
                with open(out, "wb") as f:
                    f.write(b"fake_assembled")
                return MagicMock(returncode=0)
            mock_subproc.side_effect = fake_subproc_run

            ctx = self._make_ctx(language="Korean")
            result = dlg.generate_dialogue_voiceover(
                dialogue_lines, characters, output, ctx=ctx
            )

        # ElevenLabs was called as fallback — exactly once for the failed Cartesia line
        assert mock_client.text_to_speech.convert.called
        assert mock_client.text_to_speech.convert.call_count == 1

    def test_mixed_scene_korean_char_routes_per_line(self, tmp_path):
        """Project language wins per the scene-shaped router input."""
        from audio import dialogue as dlg

        dialogue_lines = [
            {"character_id": "char1", "text": "Hi", "delivery": "natural"},
        ]
        # Even if character.language is set to ko, the scene-language
        # (project default) takes precedence per _resolve_tts_provider semantics.
        characters = [{"id": "char1", "name": "X", "voice_id": "vid", "language": "ko"}]
        output = str(tmp_path / "mixed.mp3")

        cartesia_calls = []
        def fake_cartesia(*args, **kw):
            cartesia_calls.append(kw)
            return True

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test"

        with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
             patch.object(dlg, "generate_cartesia", side_effect=fake_cartesia), \
             patch.object(dlg, "settings", mock_settings), \
             patch("audio.dialogue.client") as mock_client, \
             patch("audio.dialogue.save") as mock_save, \
             patch("subprocess.run") as mock_subproc:

            mock_client.text_to_speech.convert.return_value = b"x"
            def fake_save(b, p):
                with open(p, "wb") as f:
                    f.write(b)
            mock_save.side_effect = fake_save

            def fake_subproc_run(args, *_args, **_kw):
                with open(args[-1], "wb") as f:
                    f.write(b"assembled")
                return MagicMock(returncode=0)
            mock_subproc.side_effect = fake_subproc_run

            ctx = self._make_ctx(language="English")
            dlg.generate_dialogue_voiceover(dialogue_lines, characters, output, ctx=ctx)

        # Scene language (English) wins; Cartesia NOT called even though
        # character.language=ko (the router prioritizes scene/project language).
        assert len(cartesia_calls) == 0
        assert mock_client.text_to_speech.convert.called

    def test_cartesia_success_records_cost_via_cost_tracker(self, tmp_path):
        """Successful Cartesia call records CARTESIA_SONIC_2 spend via CostTracker.

        Closes I-2 from cycle-15 v0.9.7 code-quality review: cost-tracker entry
        was dormant because dispatcher never invoked record_api_call. v0.9.8
        wires the call inside the cartesia_ok success branch.
        """
        from audio import dialogue as dlg

        dialogue_lines = [
            {"character_id": "char1", "text": "안녕하세요", "delivery": "natural"},
        ]
        characters = [{"id": "char1", "name": "준호", "voice_id": "vid_kr"}]
        output = str(tmp_path / "cost.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test"

        # Patch CostTracker at the import site (audio.dialogue imports it
        # lazily inside the success branch, so we patch via the cost_tracker
        # module attribute that the lazy import resolves against).
        mock_tracker_instance = MagicMock()
        mock_tracker_cls = MagicMock(return_value=mock_tracker_instance)

        def fake_cartesia(*args, **kw):
            # Write the temp file so dispatcher's success-branch appending works
            with open(kw.get("output_path"), "wb") as f:
                f.write(b"fake_cartesia_mp3")
            return True

        with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
             patch.object(dlg, "generate_cartesia", side_effect=fake_cartesia), \
             patch.object(dlg, "settings", mock_settings), \
             patch("audio.dialogue.client") as mock_client, \
             patch("audio.dialogue.save") as mock_save, \
             patch("cost_tracker.CostTracker", mock_tracker_cls), \
             patch("subprocess.run") as mock_subproc:

            mock_client.text_to_speech.convert.return_value = b"x"
            def fake_save(b, p):
                with open(p, "wb") as f:
                    f.write(b)
            mock_save.side_effect = fake_save

            def fake_subproc_run(args, *_args, **_kw):
                with open(args[-1], "wb") as f:
                    f.write(b"assembled")
                return MagicMock(returncode=0)
            mock_subproc.side_effect = fake_subproc_run

            ctx = self._make_ctx(language="Korean")
            dlg.generate_dialogue_voiceover(dialogue_lines, characters, output, ctx=ctx)

        # CostTracker was instantiated + record_api_call invoked with CARTESIA_SONIC_2
        assert mock_tracker_cls.called, "CostTracker should be instantiated on Cartesia success"
        assert mock_tracker_instance.record_api_call.called, "record_api_call should be invoked"
        call_kwargs = mock_tracker_instance.record_api_call.call_args
        # First positional arg is api_name = "CARTESIA_SONIC_2"
        assert call_kwargs.args[0] == "CARTESIA_SONIC_2"
        assert call_kwargs.kwargs.get("operation") == "dialogue_tts"

    def test_cartesia_success_cost_tracker_failure_does_not_break_dispatcher(self, tmp_path):
        """If CostTracker fails (SQLite locked / import error), dispatcher continues.

        Best-effort cost tracking — TTS success path must not regress when
        cost-record fails. Mirror's cinema/shots/controller.py:551-554 pattern.
        """
        from audio import dialogue as dlg

        dialogue_lines = [
            {"character_id": "char1", "text": "안녕", "delivery": "natural"},
        ]
        characters = [{"id": "char1", "name": "준호", "voice_id": "vid_kr"}]
        output = str(tmp_path / "cost_fail.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test"

        # CostTracker constructor raises (simulating SQLite lock or similar)
        def explode(*a, **kw):
            raise RuntimeError("simulated cost-tracker failure")
        mock_tracker_cls = MagicMock(side_effect=explode)

        def fake_cartesia(*args, **kw):
            with open(kw.get("output_path"), "wb") as f:
                f.write(b"fake_cartesia_mp3")
            return True

        with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
             patch.object(dlg, "generate_cartesia", side_effect=fake_cartesia), \
             patch.object(dlg, "settings", mock_settings), \
             patch("audio.dialogue.client") as mock_client, \
             patch("audio.dialogue.save") as mock_save, \
             patch("cost_tracker.CostTracker", mock_tracker_cls), \
             patch("subprocess.run") as mock_subproc:

            mock_client.text_to_speech.convert.return_value = b"x"
            def fake_save(b, p):
                with open(p, "wb") as f:
                    f.write(b)
            mock_save.side_effect = fake_save

            def fake_subproc_run(args, *_args, **_kw):
                with open(args[-1], "wb") as f:
                    f.write(b"assembled")
                return MagicMock(returncode=0)
            mock_subproc.side_effect = fake_subproc_run

            ctx = self._make_ctx(language="Korean")
            # Should NOT raise — best-effort cost tracking
            result = dlg.generate_dialogue_voiceover(
                dialogue_lines, characters, output, ctx=ctx
            )

        # CostTracker was attempted but failed; dispatcher continued + assembled output
        assert mock_tracker_cls.called, "CostTracker instantiation should be attempted"
        # Cartesia was the actual TTS provider invoked (didn't fall back to ElevenLabs)
        assert not mock_client.text_to_speech.convert.called, \
            "ElevenLabs should NOT be invoked on Cartesia success (cost-record failure is best-effort)"
