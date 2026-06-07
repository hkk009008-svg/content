"""Unit tests for T-A: per-provider Cartesia voice mapping + skip-without-HTTP guard.

Coverage (per ticket spec):
1. _resolve_cartesia_voice: 11labs-shaped id + Korean + female/absent gender → Seoyun UUID
2. Same + male gender hint → Jaewon UUID
3. UUID-shaped input → returned unchanged (no mapping lookup)
4. Language with no Cartesia keys (English) + 11labs id → None
5. Dispatch-level: provider=CARTESIA + unmappable voice → generate_cartesia NOT called,
   ElevenLabs path receives ORIGINAL voice_id
6. Dispatch-level: mappable voice → generate_cartesia called with the mapped UUID;
   on its False return, ElevenLabs fallback still gets the ORIGINAL 11labs id

All HTTP calls are mocked; zero network activity during test execution.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Cartesia voice UUIDs from domain/language_defaults.py Korean entry
# (verified via live voices API 2026-06-08)
# ---------------------------------------------------------------------------
SEOYUN_UUID = "ce9ca2b6-2bed-4452-99bb-052e1ec0b534"   # Seoyun — Warm Guide (female)
JAEWON_UUID = "89f4372f-1f73-4b85-8e1e-5d24ed8bc826"   # Jaewon — Steady Advisor (male)

# A sample ElevenLabs id (not UUID-shaped)
EL_FEMALE_KO = "uyVNoMrnUku1dZyVEXwD"  # 안나 (Anna) — the Korean female 11labs default
EL_MALE_KO = "1W00IGEmNmwmsDeYy7ag"    # 준호 (Junho) — the Korean male 11labs default
EL_ENGLISH = "21m00Tcm4TlvDq8ikWAM"    # Rachel — English female


# ---------------------------------------------------------------------------
# Test 1 & 2: _resolve_cartesia_voice — 11labs id + Korean gender mapping
# ---------------------------------------------------------------------------

class TestResolveCartesiaVoice:
    """Unit tests for the pure _resolve_cartesia_voice helper."""

    def test_korean_female_absent_gender_maps_to_seoyun(self):
        """11labs id + Korean + no gender → Seoyun (female default)."""
        from audio.dialogue import _resolve_cartesia_voice

        result = _resolve_cartesia_voice(EL_FEMALE_KO, {}, "Korean")
        assert result == SEOYUN_UUID, (
            f"Korean female default should be Seoyun ({SEOYUN_UUID}); got {result!r}"
        )

    def test_iso_code_ko_maps_like_korean(self):
        """Live-verification regression: real projects store language='ko'
        (ISO code), which the router routes to Cartesia by prefix — the
        resolver must normalize the same way, not exact-match the defaults
        dict key ("Korean"). 'ko' fell to _default → None → skip in prod."""
        from audio.dialogue import _resolve_cartesia_voice

        for lang in ("ko", "ko_KR", "korean", "KOREAN"):
            result = _resolve_cartesia_voice(EL_FEMALE_KO, {}, lang)
            assert result == SEOYUN_UUID, (
                f"language={lang!r} must map like 'Korean' (router routes it "
                f"to Cartesia by 'ko' prefix); got {result!r}"
            )

    def test_korean_female_explicit_gender_maps_to_seoyun(self):
        """11labs id + Korean + gender='female' → Seoyun."""
        from audio.dialogue import _resolve_cartesia_voice

        result = _resolve_cartesia_voice(EL_FEMALE_KO, {"gender": "female"}, "Korean")
        assert result == SEOYUN_UUID

    def test_korean_male_gender_hint_maps_to_jaewon(self):
        """11labs id + Korean + gender='male' → Jaewon."""
        from audio.dialogue import _resolve_cartesia_voice

        result = _resolve_cartesia_voice(EL_MALE_KO, {"gender": "male"}, "Korean")
        assert result == JAEWON_UUID, (
            f"Korean male hint should map to Jaewon ({JAEWON_UUID}); got {result!r}"
        )

    def test_korean_gender_m_hint_maps_to_jaewon(self):
        """Short 'm' gender code is treated as male hint."""
        from audio.dialogue import _resolve_cartesia_voice

        result = _resolve_cartesia_voice(EL_MALE_KO, {"gender": "m"}, "Korean")
        assert result == JAEWON_UUID

    def test_korean_gender_man_hint_maps_to_jaewon(self):
        """'man' gender code is treated as male hint."""
        from audio.dialogue import _resolve_cartesia_voice

        result = _resolve_cartesia_voice(EL_MALE_KO, {"gender": "man"}, "Korean")
        assert result == JAEWON_UUID

    def test_korean_mixed_case_gender_male(self):
        """Gender matching is case-insensitive."""
        from audio.dialogue import _resolve_cartesia_voice

        result = _resolve_cartesia_voice(EL_MALE_KO, {"gender": "Male"}, "Korean")
        assert result == JAEWON_UUID

    # ---- Test 3: UUID-shaped input returned unchanged -----------------------

    def test_uuid_shaped_input_returned_unchanged_female(self):
        """If voice_id is already a Cartesia UUID, return it unchanged (no lookup)."""
        from audio.dialogue import _resolve_cartesia_voice

        # Any UUID (including the actual Seoyun id) — returned as-is
        result = _resolve_cartesia_voice(SEOYUN_UUID, {"gender": "male"}, "Korean")
        assert result == SEOYUN_UUID, (
            "UUID-shaped input must be returned unchanged, regardless of gender"
        )

    def test_uuid_shaped_input_returned_unchanged_male(self):
        """Jaewon UUID input returned unchanged (no table lookup performed)."""
        from audio.dialogue import _resolve_cartesia_voice

        result = _resolve_cartesia_voice(JAEWON_UUID, {}, "Korean")
        assert result == JAEWON_UUID

    def test_arbitrary_uuid_returned_unchanged(self):
        """Any UUID-shaped string passes through, even if not in our table."""
        from audio.dialogue import _resolve_cartesia_voice

        arbitrary_uuid = "12345678-abcd-ef01-2345-678901234567"
        result = _resolve_cartesia_voice(arbitrary_uuid, {}, "Korean")
        assert result == arbitrary_uuid

    # ---- Test 4: language with no Cartesia keys → None ----------------------

    def test_english_no_cartesia_keys_returns_none(self):
        """English has no cartesia_default_* keys → returns None (skip the lane)."""
        from audio.dialogue import _resolve_cartesia_voice

        result = _resolve_cartesia_voice(EL_ENGLISH, {}, "English")
        assert result is None, (
            "English has no cartesia_default_* keys; should return None to skip Cartesia lane"
        )

    def test_japanese_no_cartesia_keys_returns_none(self):
        """Japanese has no cartesia_default_* keys → None."""
        from audio.dialogue import _resolve_cartesia_voice

        result = _resolve_cartesia_voice("pNInz6obpgDQGcFmaJgB", {}, "Japanese")
        assert result is None

    def test_unknown_language_no_cartesia_keys_returns_none(self):
        """Unknown / unregistered language → None (falls through _default which has no cartesia keys)."""
        from audio.dialogue import _resolve_cartesia_voice

        result = _resolve_cartesia_voice(EL_ENGLISH, {}, "Klingon")
        assert result is None

    def test_domain_import_failure_returns_none(self):
        """If domain import fails (deploy without domain package), returns None, never raises."""
        from audio.dialogue import _resolve_cartesia_voice

        import builtins
        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "domain.language_defaults":
                raise ImportError("simulated domain unavailable")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            result = _resolve_cartesia_voice(EL_ENGLISH, {}, "Korean")
        assert result is None


# ---------------------------------------------------------------------------
# Test 5: Dispatch-level: unmappable voice → generate_cartesia NOT called
# ---------------------------------------------------------------------------

class TestDispatchSkipWithoutHTTP:
    """Dispatch-level tests for the skip-without-HTTP guard (T-A's core fix)."""

    def _make_ctx(self, language: str = "English"):
        from cinema.context import PipelineContext
        return PipelineContext(global_settings={"language": language})

    def test_unmappable_voice_cartesia_not_called_elevenlabs_gets_original(self, tmp_path):
        """Provider=CARTESIA + 11labs id + English (no mapping) → generate_cartesia
        NOT called; ElevenLabs path receives the ORIGINAL 11labs voice_id.

        This is the T-A closed-loop regression test: the old code would have called
        generate_cartesia with the 11labs id (guaranteed 400); new code skips it.
        """
        from audio import dialogue as dlg

        original_voice_id = EL_ENGLISH  # 11labs Rachel — not a Cartesia UUID

        dialogue_lines = [
            {"character_id": "char1", "text": "Hello", "delivery": "natural"},
        ]
        # Set voice_id to an ElevenLabs id
        characters = [{"id": "char1", "name": "Alice", "voice_id": original_voice_id}]
        output = str(tmp_path / "out.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test_cartesia"
        # Force CARTESIA route for English (normally wouldn't route there;
        # we patch _resolve_tts_provider to test the guard in isolation)

        cartesia_calls = []
        def fake_cartesia(*a, **kw):
            cartesia_calls.append(kw)
            return True

        elevenlabs_voice_ids_seen = []
        mock_client = MagicMock()
        def fake_el_convert(**kw):
            elevenlabs_voice_ids_seen.append(kw.get("voice_id"))
            return b"fake_audio"
        mock_client.text_to_speech.convert.side_effect = fake_el_convert

        with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
             patch.object(dlg, "generate_cartesia", side_effect=fake_cartesia), \
             patch.object(dlg, "_resolve_tts_provider", return_value="CARTESIA_SONIC_2"), \
             patch.object(dlg, "settings", mock_settings), \
             patch("audio.dialogue.client", mock_client), \
             patch("audio.dialogue.save") as mock_save, \
             patch("subprocess.run") as mock_subproc:

            def fake_save(audio_bytes, path):
                with open(path, "wb") as f:
                    f.write(b"fake_eleven_mp3")
            mock_save.side_effect = fake_save

            def fake_subproc_run(args, *_a, **_kw):
                with open(args[-1], "wb") as f:
                    f.write(b"assembled")
                return MagicMock(returncode=0)
            mock_subproc.side_effect = fake_subproc_run

            # English project: cartesia_default_*_voice keys absent → None → skip
            ctx = self._make_ctx(language="English")
            dlg.generate_dialogue_voiceover(dialogue_lines, characters, output, ctx=ctx)

        # generate_cartesia must NOT have been called (skip-without-HTTP guard)
        assert len(cartesia_calls) == 0, (
            "generate_cartesia must not be called when no Cartesia voice mapping exists"
        )
        # ElevenLabs path must receive the ORIGINAL voice_id
        assert len(elevenlabs_voice_ids_seen) == 1
        assert elevenlabs_voice_ids_seen[0] == original_voice_id, (
            f"ElevenLabs fallback must receive the ORIGINAL voice_id {original_voice_id!r}; "
            f"got {elevenlabs_voice_ids_seen[0]!r}"
        )

    def test_skip_logged_once_not_per_line(self, tmp_path, capsys):
        """Skip-log fires exactly once per invocation, even for multiple lines."""
        from audio import dialogue as dlg

        dialogue_lines = [
            {"character_id": "char1", "text": "Line one", "delivery": "natural"},
            {"character_id": "char1", "text": "Line two", "delivery": "natural"},
            {"character_id": "char1", "text": "Line three", "delivery": "natural"},
        ]
        characters = [{"id": "char1", "name": "Alice", "voice_id": EL_ENGLISH}]
        output = str(tmp_path / "out.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test_cartesia"

        cartesia_calls = []
        mock_client = MagicMock()
        mock_client.text_to_speech.convert.return_value = b"fake"

        with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
             patch.object(dlg, "generate_cartesia", side_effect=lambda *a, **kw: cartesia_calls.append(kw) or True), \
             patch.object(dlg, "_resolve_tts_provider", return_value="CARTESIA_SONIC_2"), \
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

            ctx = self._make_ctx(language="English")
            dlg.generate_dialogue_voiceover(dialogue_lines, characters, output, ctx=ctx)

        # generate_cartesia not called (all 3 lines mapped to None → skipped)
        assert len(cartesia_calls) == 0

        # The skip log appears exactly once in stdout (not 3 times)
        captured = capsys.readouterr()
        skip_count = captured.out.count("no Cartesia voice mapping")
        assert skip_count == 1, (
            f"Skip-log must fire exactly once per invocation; found {skip_count} occurrences"
        )


# ---------------------------------------------------------------------------
# Test 6: Dispatch-level: mappable voice → generate_cartesia called with UUID;
#          on False return, ElevenLabs fallback gets the ORIGINAL 11labs id
# ---------------------------------------------------------------------------

class TestDispatchMappableVoice:
    """Mappable (Korean) voice: generate_cartesia is called with the mapped UUID;
    on Cartesia failure (False), ElevenLabs fallback gets the ORIGINAL 11labs id."""

    def _make_ctx(self, language: str = "Korean"):
        from cinema.context import PipelineContext
        return PipelineContext(global_settings={"language": language})

    def test_mappable_voice_cartesia_called_with_uuid(self, tmp_path):
        """Korean + 11labs id → _resolve_cartesia_voice maps to Seoyun UUID;
        generate_cartesia is called with the Cartesia UUID, not the 11labs id."""
        from audio import dialogue as dlg

        original_voice_id = EL_FEMALE_KO  # 11labs Anna — ElevenLabs id
        dialogue_lines = [
            {"character_id": "char1", "text": "안녕하세요", "delivery": "natural"},
        ]
        characters = [{"id": "char1", "name": "안나", "voice_id": original_voice_id}]
        output = str(tmp_path / "out.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test_cartesia"

        cartesia_calls = []
        def fake_cartesia(*a, **kw):
            cartesia_calls.append(kw)
            # Write the output file to satisfy the success branch
            with open(kw["output_path"], "wb") as f:
                f.write(b"fake_cartesia_mp3")
            return True

        mock_client = MagicMock()

        with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
             patch.object(dlg, "generate_cartesia", side_effect=fake_cartesia), \
             patch.object(dlg, "settings", mock_settings), \
             patch("audio.dialogue.client", mock_client), \
             patch("subprocess.run") as mock_subproc:

            def fake_subproc_run(args, *_a, **_kw):
                with open(args[-1], "wb") as f:
                    f.write(b"assembled")
                return MagicMock(returncode=0)
            mock_subproc.side_effect = fake_subproc_run

            ctx = self._make_ctx(language="Korean")
            dlg.generate_dialogue_voiceover(dialogue_lines, characters, output, ctx=ctx)

        # generate_cartesia was called once
        assert len(cartesia_calls) == 1, (
            "generate_cartesia must be called for Korean with a mappable voice"
        )
        # The voice_id passed to Cartesia must be the mapped UUID, not the 11labs id
        used_voice_id = cartesia_calls[0]["voice_id"]
        assert used_voice_id == SEOYUN_UUID, (
            f"generate_cartesia must receive Seoyun UUID ({SEOYUN_UUID}); got {used_voice_id!r}"
        )
        assert used_voice_id != original_voice_id, (
            "generate_cartesia must NOT receive the original 11labs voice_id"
        )
        # ElevenLabs path was NOT called (Cartesia succeeded)
        assert not mock_client.text_to_speech.convert.called

    def test_mappable_voice_cartesia_false_elevenlabs_gets_original(self, tmp_path):
        """Korean + 11labs id → Cartesia called with UUID but returns False;
        ElevenLabs fallback receives the ORIGINAL 11labs voice_id (not the mapped UUID).
        """
        from audio import dialogue as dlg

        original_voice_id = EL_FEMALE_KO
        dialogue_lines = [
            {"character_id": "char1", "text": "안녕하세요", "delivery": "natural"},
        ]
        characters = [{"id": "char1", "name": "안나", "voice_id": original_voice_id}]
        output = str(tmp_path / "out.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test_cartesia"

        cartesia_calls = []
        def fake_cartesia(*a, **kw):
            cartesia_calls.append(kw)
            return False  # Simulate Cartesia failure

        elevenlabs_voice_ids_seen = []
        mock_client = MagicMock()
        def fake_el_convert(**kw):
            elevenlabs_voice_ids_seen.append(kw.get("voice_id"))
            return b"fake_audio"
        mock_client.text_to_speech.convert.side_effect = fake_el_convert

        with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
             patch.object(dlg, "generate_cartesia", side_effect=fake_cartesia), \
             patch.object(dlg, "settings", mock_settings), \
             patch("audio.dialogue.client", mock_client), \
             patch("audio.dialogue.save") as mock_save, \
             patch("subprocess.run") as mock_subproc:

            def fake_save(audio_bytes, path):
                with open(path, "wb") as f:
                    f.write(b"fake_eleven_mp3")
            mock_save.side_effect = fake_save

            def fake_subproc_run(args, *_a, **_kw):
                with open(args[-1], "wb") as f:
                    f.write(b"assembled")
                return MagicMock(returncode=0)
            mock_subproc.side_effect = fake_subproc_run

            ctx = self._make_ctx(language="Korean")
            dlg.generate_dialogue_voiceover(dialogue_lines, characters, output, ctx=ctx)

        # Cartesia was called with the mapped UUID
        assert len(cartesia_calls) == 1
        assert cartesia_calls[0]["voice_id"] == SEOYUN_UUID

        # ElevenLabs fallback received the ORIGINAL 11labs voice_id (not the Cartesia UUID)
        assert len(elevenlabs_voice_ids_seen) == 1
        assert elevenlabs_voice_ids_seen[0] == original_voice_id, (
            f"ElevenLabs fallback must receive ORIGINAL voice_id {original_voice_id!r}; "
            f"got {elevenlabs_voice_ids_seen[0]!r} — the Cartesia UUID must not leak to ElevenLabs"
        )

    def test_korean_male_voice_mapped_to_jaewon(self, tmp_path):
        """Korean + male character + 11labs id → generate_cartesia called with Jaewon UUID."""
        from audio import dialogue as dlg

        original_voice_id = EL_MALE_KO
        dialogue_lines = [
            {"character_id": "char1", "text": "안녕하세요", "delivery": "natural"},
        ]
        characters = [{"id": "char1", "name": "준호", "voice_id": original_voice_id, "gender": "male"}]
        output = str(tmp_path / "out.mp3")

        mock_settings = MagicMock()
        mock_settings.cartesia_api_key = "sk_test_cartesia"

        cartesia_calls = []
        def fake_cartesia(*a, **kw):
            cartesia_calls.append(kw)
            with open(kw["output_path"], "wb") as f:
                f.write(b"fake_cartesia_mp3")
            return True

        with patch.object(dlg, "_try_dialogue_mode", return_value=None), \
             patch.object(dlg, "generate_cartesia", side_effect=fake_cartesia), \
             patch.object(dlg, "settings", mock_settings), \
             patch("audio.dialogue.client", MagicMock()), \
             patch("subprocess.run") as mock_subproc:

            def fake_subproc_run(args, *_a, **_kw):
                with open(args[-1], "wb") as f:
                    f.write(b"assembled")
                return MagicMock(returncode=0)
            mock_subproc.side_effect = fake_subproc_run

            ctx = self._make_ctx(language="Korean")
            dlg.generate_dialogue_voiceover(dialogue_lines, characters, output, ctx=ctx)

        assert len(cartesia_calls) == 1
        assert cartesia_calls[0]["voice_id"] == JAEWON_UUID, (
            f"Male Korean character must use Jaewon UUID ({JAEWON_UUID}); "
            f"got {cartesia_calls[0]['voice_id']!r}"
        )


# ---------------------------------------------------------------------------
# Regression: verify language_defaults has the Cartesia keys for Korean
# ---------------------------------------------------------------------------

class TestLanguageDefaultsCartesiaKeys:
    """Verify domain/language_defaults.py carries the Cartesia keys for Korean
    (Rule #12 write-evidence — the read side of the table written in T-A)."""

    def test_korean_has_cartesia_female_voice(self):
        from domain.language_defaults import get_language_defaults
        defaults = get_language_defaults("Korean")
        assert "cartesia_default_female_voice" in defaults, (
            "Korean language_defaults must have cartesia_default_female_voice"
        )
        val = defaults["cartesia_default_female_voice"]
        from audio.dialogue import _CARTESIA_UUID_RE
        assert _CARTESIA_UUID_RE.fullmatch(val), (
            f"cartesia_default_female_voice {val!r} must be UUID-shaped"
        )
        assert val == SEOYUN_UUID, f"Expected Seoyun UUID; got {val!r}"

    def test_korean_has_cartesia_male_voice(self):
        from domain.language_defaults import get_language_defaults
        defaults = get_language_defaults("Korean")
        assert "cartesia_default_male_voice" in defaults
        val = defaults["cartesia_default_male_voice"]
        from audio.dialogue import _CARTESIA_UUID_RE
        assert _CARTESIA_UUID_RE.fullmatch(val), (
            f"cartesia_default_male_voice {val!r} must be UUID-shaped"
        )
        assert val == JAEWON_UUID, f"Expected Jaewon UUID; got {val!r}"

    def test_english_has_no_cartesia_keys(self):
        """English must NOT have cartesia_default_* keys (absent key = lane skipped)."""
        from domain.language_defaults import get_language_defaults
        defaults = get_language_defaults("English")
        assert "cartesia_default_female_voice" not in defaults
        assert "cartesia_default_male_voice" not in defaults

    def test_japanese_has_no_cartesia_keys(self):
        from domain.language_defaults import get_language_defaults
        defaults = get_language_defaults("Japanese")
        assert "cartesia_default_female_voice" not in defaults
        assert "cartesia_default_male_voice" not in defaults

    def test_default_fallback_has_no_cartesia_keys(self):
        from domain.language_defaults import get_language_defaults
        defaults = get_language_defaults("Klingon")  # falls back to _default
        assert "cartesia_default_female_voice" not in defaults
        assert "cartesia_default_male_voice" not in defaults
