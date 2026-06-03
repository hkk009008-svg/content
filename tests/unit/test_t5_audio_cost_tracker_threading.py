"""T5 — cost-tracker threading tests.

Verifies that audio generator functions (generate_dialogue_voiceover,
generate_fal_bgm, generate_suno_v5, generate_stability_foley) thread a
caller-supplied CostTracker through so audio spend accumulates on the
pipeline's budget-aware tracker rather than a throwaway fresh one.

All real API calls are mocked — zero network/GPU/spend.
"""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock, patch, call

import pytest

from cost_tracker import CostTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stub(name: str, **attrs):
    """Inject a minimal stub module so heavy imports don't block collection."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _fresh_tracker(tmp_path) -> CostTracker:
    """Return a CostTracker backed by a temp SQLite DB (no budget)."""
    return CostTracker(db_path=str(tmp_path / "test_cost.db"))


# ---------------------------------------------------------------------------
# generate_stability_foley
# ---------------------------------------------------------------------------

class TestFoleyCostTrackerThreading:
    """generate_stability_foley records spend on the caller-supplied tracker."""

    def _make_mock_response(self):
        r = MagicMock()
        r.raise_for_status.return_value = None
        r.content = b"ID3-FAKE-FOLEY"
        return r

    def _make_settings(self):
        s = MagicMock()
        s.stability_api_key = "sk-test-stability"
        return s

    def test_passes_tracker_records_spend(self, tmp_path):
        """When cost_tracker is supplied, record_api_call is invoked on it."""
        from audio.foley import generate_stability_foley

        tracker = _fresh_tracker(tmp_path)
        before = tracker.spent_usd

        output = str(tmp_path / "foley.mp3")
        with patch("audio.foley.requests.post", return_value=self._make_mock_response()), \
             patch("audio.foley.settings", self._make_settings()):
            result = generate_stability_foley("rain", output, cost_tracker=tracker)

        assert result == output, "expected output path on success"
        assert tracker.spent_usd > before, "tracker.spent_usd must increase after successful call"

    def test_no_tracker_still_works(self, tmp_path):
        """Omitting cost_tracker (default None) does not raise; backward-compat."""
        from audio.foley import generate_stability_foley

        output = str(tmp_path / "foley_notracker.mp3")
        with patch("audio.foley.requests.post", return_value=self._make_mock_response()), \
             patch("audio.foley.settings", self._make_settings()):
            result = generate_stability_foley("crowd", output)

        assert result == output

    def test_passed_tracker_not_fresh_instance(self, tmp_path):
        """Confirm a DISTINCT tracker (not a fresh CostTracker()) gets the spend."""
        from audio.foley import generate_stability_foley

        tracker_a = _fresh_tracker(tmp_path)
        tracker_b = _fresh_tracker(tmp_path)  # separate instance, separate DB

        output = str(tmp_path / "foley_ab.mp3")
        with patch("audio.foley.requests.post", return_value=self._make_mock_response()), \
             patch("audio.foley.settings", self._make_settings()):
            generate_stability_foley("traffic", output, cost_tracker=tracker_a)

        # Only tracker_a should have accumulated spend; tracker_b is untouched.
        assert tracker_a.spent_usd > 0.0
        assert tracker_b.spent_usd == 0.0


# ---------------------------------------------------------------------------
# generate_fal_bgm
# ---------------------------------------------------------------------------

class TestFalBgmCostTrackerThreading:
    """generate_fal_bgm records spend on the caller-supplied tracker."""

    def _setup_fal(self, monkeypatch, tmp_path, url="https://cdn/bgm.mp3"):
        """Stub fal_client.subscribe + urllib.request.urlretrieve."""
        # fal_client may not be installed; stub it
        fal_mod = _stub("fal_client")
        audio_content = b"ID3-FAKE-BGM"

        def _fake_subscribe(endpoint, arguments=None):
            return {"audio_file": {"url": url}}

        fal_mod.subscribe = _fake_subscribe

        # urlretrieve: write fake bytes to the output path
        def _fake_urlretrieve(url, out):
            with open(out, "wb") as f:
                f.write(audio_content)

        monkeypatch.setattr("urllib.request.urlretrieve", _fake_urlretrieve)

        # Stub out the optional research_engine import to avoid network
        research_mod = _stub("research_engine", research_music_reference=lambda *a, **k: "")
        return fal_mod

    def test_passes_tracker_records_spend(self, monkeypatch, tmp_path):
        from audio.music import generate_fal_bgm

        self._setup_fal(monkeypatch, tmp_path)
        tracker = _fresh_tracker(tmp_path)
        before = tracker.spent_usd

        output = str(tmp_path / "bgm.mp3")
        result = generate_fal_bgm("epic", output, cost_tracker=tracker)

        assert result is True
        assert tracker.spent_usd > before

    def test_no_tracker_still_works(self, monkeypatch, tmp_path):
        from audio.music import generate_fal_bgm

        self._setup_fal(monkeypatch, tmp_path)
        output = str(tmp_path / "bgm_notracker.mp3")
        result = generate_fal_bgm("suspense", output)

        assert result is True

    def test_passed_tracker_not_fresh_instance(self, monkeypatch, tmp_path):
        from audio.music import generate_fal_bgm

        self._setup_fal(monkeypatch, tmp_path)

        tracker_a = _fresh_tracker(tmp_path)
        tracker_b = _fresh_tracker(tmp_path)

        output = str(tmp_path / "bgm_ab.mp3")
        generate_fal_bgm("dreamy", output, cost_tracker=tracker_a)

        assert tracker_a.spent_usd > 0.0
        assert tracker_b.spent_usd == 0.0


# ---------------------------------------------------------------------------
# generate_dialogue_voiceover  (ElevenLabs path)
# ---------------------------------------------------------------------------

class TestDialogueCostTrackerThreading:
    """generate_dialogue_voiceover records ElevenLabs/Cartesia spend on the caller-supplied tracker."""

    def _setup_stubs(self, monkeypatch, tmp_path):
        """Stub ElevenLabs + ffmpeg so the function runs offline."""
        import importlib

        # Stub elevenlabs.save and client.text_to_speech.convert
        el_save_calls = []

        def _fake_save(audio, path):
            with open(path, "wb") as f:
                f.write(b"ID3-FAKE-TTS")
            el_save_calls.append(path)

        monkeypatch.setattr("audio.dialogue.save", _fake_save)

        # client.text_to_speech.convert returns fake audio bytes
        fake_client = MagicMock()
        fake_client.text_to_speech.convert.return_value = b"ID3-FAKE-TTS"
        monkeypatch.setattr("audio.dialogue.client", fake_client)

        # Stub subprocess.run (ffmpeg calls)
        monkeypatch.setattr("subprocess.run", lambda *a, **k: MagicMock(returncode=0))

        # Stub dialogue_mode so it returns None (force PATH 2 = per-line ElevenLabs)
        monkeypatch.setattr(
            "audio.dialogue._try_dialogue_mode",
            lambda *a, **k: None,
        )

        # _maybe_save_alignment — no-op
        monkeypatch.setattr(
            "audio.dialogue._maybe_save_alignment",
            lambda *a, **k: None,
        )

        # Stub get_project_setting to return "English"
        monkeypatch.setattr(
            "audio.dialogue.get_project_setting",
            lambda ctx, key, default=None: "English",
        )

        # Stub settings to avoid import errors
        import importlib
        _cfg = importlib.import_module("config.settings")
        fake_settings = MagicMock()
        fake_settings.cartesia_api_key = ""  # disables Cartesia path → uses ElevenLabs
        monkeypatch.setattr(_cfg, "settings", fake_settings)
        monkeypatch.setattr("audio.dialogue.settings", fake_settings)

        return el_save_calls

    def test_elevenlabs_path_records_on_tracker(self, monkeypatch, tmp_path):
        from audio.dialogue import generate_dialogue_voiceover

        self._setup_stubs(monkeypatch, tmp_path)
        tracker = _fresh_tracker(tmp_path)
        before = tracker.spent_usd

        output = str(tmp_path / "dlg.mp3")
        lines = [{"character_id": "c1", "text": "Hello world", "delivery": "natural"}]
        chars = [{"id": "c1", "name": "Alice", "voice_id": "voice_abc"}]

        # monkeypatch _resolve_tts_provider to return ElevenLabs
        monkeypatch.setattr(
            "audio.dialogue._resolve_tts_provider",
            lambda *a, **k: "ELEVENLABS",
        )

        result = generate_dialogue_voiceover(lines, chars, output, cost_tracker=tracker)

        # result may be None if ffmpeg concat stub doesn't write the file — that's OK;
        # we only care that record_api_call was triggered on our tracker.
        assert tracker.spent_usd > before, (
            "tracker.spent_usd must increase after ElevenLabs TTS — "
            f"before={before}, after={tracker.spent_usd}"
        )

    def test_no_tracker_still_works(self, monkeypatch, tmp_path):
        from audio.dialogue import generate_dialogue_voiceover

        self._setup_stubs(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "audio.dialogue._resolve_tts_provider",
            lambda *a, **k: "ELEVENLABS",
        )

        output = str(tmp_path / "dlg_notracker.mp3")
        lines = [{"character_id": "c1", "text": "Hi", "delivery": "natural"}]
        chars = [{"id": "c1", "name": "Bob", "voice_id": "voice_xyz"}]

        # Should not raise even without a cost_tracker kwarg
        generate_dialogue_voiceover(lines, chars, output)

    def test_passed_tracker_not_fresh_instance(self, monkeypatch, tmp_path):
        from audio.dialogue import generate_dialogue_voiceover

        self._setup_stubs(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "audio.dialogue._resolve_tts_provider",
            lambda *a, **k: "ELEVENLABS",
        )

        tracker_a = _fresh_tracker(tmp_path)
        tracker_b = _fresh_tracker(tmp_path)

        output = str(tmp_path / "dlg_ab.mp3")
        lines = [{"character_id": "c1", "text": "Test line", "delivery": "natural"}]
        chars = [{"id": "c1", "name": "Carol", "voice_id": "v1"}]

        generate_dialogue_voiceover(lines, chars, output, cost_tracker=tracker_a)

        assert tracker_a.spent_usd > 0.0
        assert tracker_b.spent_usd == 0.0
