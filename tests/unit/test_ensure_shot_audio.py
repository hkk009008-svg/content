"""Unit tests for CinemaPipeline._ensure_shot_audio (Task 5 — Chunk 2).

Tests are fully offline — generate_dialogue_voiceover and filesystem
writes are mocked.  The helper mirrors _ensure_scene_audio but renders
only the shot's own dialogue line to audio_{shot_id}_{key}.mp3 (T-B:
content-keyed path; key derived from dialogue_cache_key).

Coverage:
  - shot with "dialogue" -> writes audio_<shot_id>_<key>.mp3, returns path,
    caches.
  - Second call with same shot_id returns cached path (no re-render).
  - shot with no/empty "dialogue" -> returns None (scene-level fallback trigger).
  - render failure (generate_dialogue_voiceover returns falsy) -> returns None.
"""

from __future__ import annotations

import os
import types
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Minimal stubs to avoid heavy imports at module-load time
# ---------------------------------------------------------------------------

def _stub(name: str, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


for _dep in [
    "veo_native", "kling_native", "sora_native", "ltx_native",
    "runway_native", "runway_gen4", "fal_proxy", "kling_3_0",
    "sora_2", "veo_fal",
]:
    if _dep not in sys.modules:
        _stub(_dep)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_host(tmp_path):
    """
    Return a minimal CinemaPipeline-like host object that exposes just the
    attributes _ensure_shot_audio reads (temp_dir, shot_audio dict, project).

    We don't instantiate CinemaPipeline directly (it requires a live
    project_id + PipelineCore).  Instead we attach the unbound method to a
    plain namespace object — same technique used by test_f1b_dialogue_lipsync.
    """
    from cinema_pipeline import CinemaPipeline

    host = object.__new__(CinemaPipeline)
    # Wire only what the method needs.
    host._core = MagicMock()
    host._core.temp_dir = str(tmp_path)
    host._core.project = {"global_settings": {}, "characters": []}
    host._runstate = MagicMock()
    host._runstate.scene_audio = {}
    host._runstate.shot_audio = {}
    return host


def _make_pipeline_context_stub():
    """Return a minimal PipelineContext used by _ensure_shot_audio."""
    from cinema.context import PipelineContext
    return PipelineContext(global_settings={})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEnsureShotAudio:

    def test_shot_with_dialogue_returns_path_and_writes_file(self, tmp_path, monkeypatch):
        """
        When shot has a "dialogue" key with text, the helper renders it to
        audio_{shot_id}_{key}.mp3 (T-B content-keyed) and returns the path.
        """
        from audio.dialogue import dialogue_cache_key

        host = _make_host(tmp_path)

        shot = {"id": "shot_abc", "dialogue": "Hello, world."}
        scene = {"id": "scene_1"}
        characters = [{"id": "char_1", "name": "Alice"}]

        # Compute the expected keyed path (mirrors _ensure_shot_audio logic)
        dialogue_lines = [{"text": "Hello, world."}]
        key = dialogue_cache_key(dialogue_lines, characters, "English")
        expected_path = str(tmp_path / f"audio_shot_abc_{key}.mp3")

        def fake_voiceover(lines, chars, out_path, ctx=None, cost_tracker=None):
            # Simulate writing the mp3.
            with open(out_path, "wb") as f:
                f.write(b"fake_mp3")
            return True

        with patch("cinema_pipeline.generate_dialogue_voiceover", side_effect=fake_voiceover):
            result = host._ensure_shot_audio(shot, scene, characters)

        assert result == expected_path
        assert os.path.exists(expected_path)

    def test_second_call_returns_cached_without_rerender(self, tmp_path, monkeypatch):
        """
        A second call with the same shot_id returns the cached path without
        calling generate_dialogue_voiceover again.
        """
        from audio.dialogue import dialogue_cache_key

        host = _make_host(tmp_path)

        shot = {"id": "shot_cache", "dialogue": "Cached line."}
        scene = {"id": "scene_1"}
        characters = []

        dialogue_lines = [{"text": "Cached line."}]
        key = dialogue_cache_key(dialogue_lines, characters, "English")
        expected_path = str(tmp_path / f"audio_shot_cache_{key}.mp3")

        render_count = {"n": 0}

        def fake_voiceover(lines, chars, out_path, ctx=None, cost_tracker=None):
            render_count["n"] += 1
            with open(out_path, "wb") as f:
                f.write(b"fake_mp3")
            return True

        with patch("cinema_pipeline.generate_dialogue_voiceover", side_effect=fake_voiceover):
            r1 = host._ensure_shot_audio(shot, scene, characters)
            r2 = host._ensure_shot_audio(shot, scene, characters)

        assert r1 == expected_path
        assert r2 == expected_path
        assert render_count["n"] == 1, "should be cached after first render"

    def test_no_dialogue_returns_none(self, tmp_path):
        """
        When shot has no "dialogue" key (or empty string), returns None —
        the caller should fall back to _ensure_scene_audio.
        """
        host = _make_host(tmp_path)

        scene = {"id": "scene_1"}
        characters = []

        # No dialogue key at all.
        result = host._ensure_shot_audio({"id": "shot_nodlg"}, scene, characters)
        assert result is None

        # Empty string.
        result2 = host._ensure_shot_audio({"id": "shot_empty", "dialogue": ""}, scene, characters)
        assert result2 is None

        # None value.
        result3 = host._ensure_shot_audio({"id": "shot_none", "dialogue": None}, scene, characters)
        assert result3 is None

    def test_render_failure_returns_none(self, tmp_path):
        """
        When generate_dialogue_voiceover returns falsy (API error etc.), the
        helper returns None (scene-level fallback trigger).
        """
        host = _make_host(tmp_path)

        shot = {"id": "shot_fail", "dialogue": "Failing line."}
        scene = {"id": "scene_1"}
        characters = []

        def fake_voiceover_fail(lines, chars, out_path, ctx=None, cost_tracker=None):
            # Do NOT write the file — simulate API failure.
            return False

        with patch("cinema_pipeline.generate_dialogue_voiceover", side_effect=fake_voiceover_fail):
            result = host._ensure_shot_audio(shot, scene, characters)

        assert result is None

    def test_cache_hit_skips_rerender_when_file_exists(self, tmp_path):
        """
        If the audio file already exists in the in-memory dict AND on disk
        (e.g., loaded from checkpoint), no re-render is triggered.
        The in-memory fast-path accepts any path shape (old or new naming).
        """
        host = _make_host(tmp_path)

        shot_id = "shot_preexist"
        # Use the new keyed naming shape to reflect current production behaviour,
        # but the in-memory fast-path accepts any existing file path.
        expected_path = str(tmp_path / f"audio_{shot_id}_preexist_key.mp3")
        with open(expected_path, "wb") as f:
            f.write(b"pre-existing")

        # Prime the cache as if a checkpoint loaded it.
        host._runstate.shot_audio[shot_id] = expected_path

        shot = {"id": shot_id, "dialogue": "Already rendered."}
        scene = {"id": "scene_1"}
        characters = []

        call_count = {"n": 0}

        def fake_voiceover(lines, chars, out_path, ctx=None, cost_tracker=None):
            call_count["n"] += 1
            return True

        with patch("cinema_pipeline.generate_dialogue_voiceover", side_effect=fake_voiceover):
            result = host._ensure_shot_audio(shot, scene, characters)

        assert result == expected_path
        assert call_count["n"] == 0, "should NOT re-render when file + cache hit"
