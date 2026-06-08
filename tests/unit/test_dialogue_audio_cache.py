"""Unit tests for dialogue-audio content-keyed caching (ticket T-B).

Coverage:
1. dialogue_cache_key: deterministic; changes with line/voice/language;
   survives odd shapes (None text, missing voice_id).
2. _ensure_scene_audio: keyed file pre-exists → generate_dialogue_voiceover
   NOT called; dict populated; path returned.
3. _ensure_scene_audio: no keyed file → generator called with keyed output path.
4. _ensure_shot_audio: same two cases mirrored.
5. Changed dialogue → different key → regeneration.
6. estimate_reassembly_cost: explicit dialogue + no cached artifacts →
   tts_lines_to_generate == line count, estimated_tts_usd == count * 0.01;
   with pre-created keyed artifacts → 0 / 0.0.
7. Per-line path: content-keyed, lives under dirname(output_path), NOT CWD.
"""

from __future__ import annotations

import json
import os
import sys
import types
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
# Helpers
# ---------------------------------------------------------------------------

def _make_pipeline_host(tmp_path):
    """Minimal CinemaPipeline-like host for _ensure_*_audio tests."""
    from cinema_pipeline import CinemaPipeline

    host = object.__new__(CinemaPipeline)
    host._core = MagicMock()
    host._core.temp_dir = str(tmp_path)
    host._core.project = {"global_settings": {"language": "English"}, "characters": []}
    host._core.cost_tracker = None  # cost_tracker is a property: self._core.cost_tracker
    host._runstate = MagicMock()
    host._runstate.scene_audio = {}
    host._runstate.shot_audio = {}
    return host


# ---------------------------------------------------------------------------
# 1. dialogue_cache_key
# ---------------------------------------------------------------------------

class TestDialogueCacheKey:

    def test_deterministic(self):
        """Same inputs always produce the same key."""
        from audio.dialogue import dialogue_cache_key
        lines = [{"character_id": "c1", "text": "Hello world"}]
        chars = [{"id": "c1", "voice_id": "v_abc123"}]
        k1 = dialogue_cache_key(lines, chars, "English")
        k2 = dialogue_cache_key(lines, chars, "English")
        assert k1 == k2
        assert len(k1) == 12

    def test_changes_on_text_edit(self):
        """Changing a line's text produces a different key."""
        from audio.dialogue import dialogue_cache_key
        chars = [{"id": "c1", "voice_id": "v_abc123"}]
        k1 = dialogue_cache_key([{"text": "Hello"}], chars, "English")
        k2 = dialogue_cache_key([{"text": "Goodbye"}], chars, "English")
        assert k1 != k2

    def test_changes_on_voice_edit(self):
        """Changing a character's voice_id produces a different key."""
        from audio.dialogue import dialogue_cache_key
        lines = [{"text": "Same text"}]
        k1 = dialogue_cache_key(lines, [{"id": "c1", "voice_id": "voice_A"}], "English")
        k2 = dialogue_cache_key(lines, [{"id": "c1", "voice_id": "voice_B"}], "English")
        assert k1 != k2

    def test_changes_on_language_edit(self):
        """Changing the language produces a different key."""
        from audio.dialogue import dialogue_cache_key
        lines = [{"text": "안녕하세요"}]
        chars = [{"id": "c1", "voice_id": "v_ko"}]
        k1 = dialogue_cache_key(lines, chars, "Korean")
        k2 = dialogue_cache_key(lines, chars, "English")
        assert k1 != k2

    def test_survives_none_text(self):
        """None text values do not raise (default=str handles them)."""
        from audio.dialogue import dialogue_cache_key
        lines = [{"character_id": "c1", "text": None}]
        chars = [{"id": "c1", "voice_id": "v1"}]
        key = dialogue_cache_key(lines, chars, "English")
        assert isinstance(key, str)
        assert len(key) == 12

    def test_survives_missing_voice_id(self):
        """Characters without voice_id do not raise."""
        from audio.dialogue import dialogue_cache_key
        lines = [{"text": "test"}]
        chars = [{"id": "c1"}]  # no voice_id key
        key = dialogue_cache_key(lines, chars, "English")
        assert isinstance(key, str)
        assert len(key) == 12

    def test_survives_empty_inputs(self):
        """Empty lists and empty language string do not raise."""
        from audio.dialogue import dialogue_cache_key
        key = dialogue_cache_key([], [], "")
        assert isinstance(key, str)
        assert len(key) == 12


# ---------------------------------------------------------------------------
# 2 & 3. _ensure_scene_audio: disk-first cache hit + miss
# ---------------------------------------------------------------------------

class TestEnsureSceneAudioCache:

    def test_disk_cache_hit_skips_voiceover(self, tmp_path):
        """Pre-existing keyed file on disk → generate_dialogue_voiceover NOT called."""
        from audio.dialogue import dialogue_cache_key
        from cinema_pipeline import CinemaPipeline

        host = _make_pipeline_host(tmp_path)
        # Explicitly override _save_checkpoint to a no-op
        host._save_checkpoint = MagicMock()

        scene_id = "scene_cache_hit"
        dialogue_lines = [{"character_id": "c1", "text": "Pre-cached line"}]
        characters = [{"id": "c1", "voice_id": "v_abc", "name": "Alice"}]
        lang = "English"

        key = dialogue_cache_key(dialogue_lines, characters, lang)
        cached_path = str(tmp_path / f"audio_{scene_id}_{key}.mp3")
        with open(cached_path, "wb") as f:
            f.write(b"pre-existing-audio")

        scene = {"id": scene_id, "dialogue": dialogue_lines}

        call_count = {"n": 0}

        def fake_voiceover(*args, **kwargs):
            call_count["n"] += 1
            return True

        with patch("cinema_pipeline.generate_dialogue_voiceover", side_effect=fake_voiceover):
            result = host._ensure_scene_audio(scene, characters)

        assert result == cached_path
        assert call_count["n"] == 0, "should NOT call voiceover on disk hit"
        assert host._runstate.scene_audio.get(scene_id) == cached_path

    def test_disk_cache_miss_calls_voiceover_with_keyed_path(self, tmp_path):
        """No cached file → generate_dialogue_voiceover called with keyed output path."""
        from audio.dialogue import dialogue_cache_key
        from cinema_pipeline import CinemaPipeline

        host = _make_pipeline_host(tmp_path)
        host._save_checkpoint = MagicMock()

        scene_id = "scene_cache_miss"
        dialogue_lines = [{"character_id": "c1", "text": "Fresh line"}]
        characters = [{"id": "c1", "voice_id": "v_xyz", "name": "Bob"}]
        lang = "English"

        key = dialogue_cache_key(dialogue_lines, characters, lang)
        expected_path = str(tmp_path / f"audio_{scene_id}_{key}.mp3")

        scene = {"id": scene_id, "dialogue": dialogue_lines}

        captured = {}

        def fake_voiceover(lines, chars, out_path, ctx=None, cost_tracker=None):
            captured["out_path"] = out_path
            with open(out_path, "wb") as f:
                f.write(b"generated-audio")
            return True

        with patch("cinema_pipeline.generate_dialogue_voiceover", side_effect=fake_voiceover):
            result = host._ensure_scene_audio(scene, characters)

        assert result == expected_path
        assert captured["out_path"] == expected_path
        assert host._runstate.scene_audio.get(scene_id) == expected_path


# ---------------------------------------------------------------------------
# 4. _ensure_shot_audio: disk-first cache hit + miss (mirrors scene site)
# ---------------------------------------------------------------------------

class TestEnsureShotAudioCache:

    def test_disk_cache_hit_skips_voiceover(self, tmp_path):
        """Pre-existing keyed file on disk → voiceover NOT called."""
        from audio.dialogue import dialogue_cache_key
        from cinema_pipeline import CinemaPipeline

        host = _make_pipeline_host(tmp_path)

        shot_id = "shot_cache_hit"
        dialogue = "Pre-cached shot line"
        dialogue_lines = [{"text": dialogue}]
        characters = [{"id": "c1", "voice_id": "v_abc", "name": "Alice"}]
        lang = "English"

        key = dialogue_cache_key(dialogue_lines, characters, lang)
        cached_path = str(tmp_path / f"audio_{shot_id}_{key}.mp3")
        with open(cached_path, "wb") as f:
            f.write(b"pre-existing-shot-audio")

        shot = {"id": shot_id, "dialogue": dialogue}
        scene = {"id": "scene_1"}

        call_count = {"n": 0}

        def fake_voiceover(*args, **kwargs):
            call_count["n"] += 1
            return True

        with patch("cinema_pipeline.generate_dialogue_voiceover", side_effect=fake_voiceover):
            result = host._ensure_shot_audio(shot, scene, characters)

        assert result == cached_path
        assert call_count["n"] == 0
        assert host._runstate.shot_audio.get(shot_id) == cached_path

    def test_disk_cache_miss_calls_voiceover_with_keyed_path(self, tmp_path):
        """No cached file → voiceover called with keyed path."""
        from audio.dialogue import dialogue_cache_key
        from cinema_pipeline import CinemaPipeline

        host = _make_pipeline_host(tmp_path)

        shot_id = "shot_cache_miss"
        dialogue = "Fresh shot line"
        dialogue_lines = [{"text": dialogue}]
        characters = [{"id": "c1", "voice_id": "v_xyz", "name": "Bob"}]
        lang = "English"

        key = dialogue_cache_key(dialogue_lines, characters, lang)
        expected_path = str(tmp_path / f"audio_{shot_id}_{key}.mp3")

        shot = {"id": shot_id, "dialogue": dialogue}
        scene = {"id": "scene_1"}

        captured = {}

        def fake_voiceover(lines, chars, out_path, ctx=None, cost_tracker=None):
            captured["out_path"] = out_path
            with open(out_path, "wb") as f:
                f.write(b"generated-shot-audio")
            return True

        with patch("cinema_pipeline.generate_dialogue_voiceover", side_effect=fake_voiceover):
            result = host._ensure_shot_audio(shot, scene, characters)

        assert result == expected_path
        assert captured["out_path"] == expected_path


# ---------------------------------------------------------------------------
# 5. Changed dialogue → different key → regeneration
# ---------------------------------------------------------------------------

class TestKeyChangeTriggersRegeneration:

    def test_changed_line_triggers_regeneration(self, tmp_path):
        """If dialogue changes, old key misses → voiceover called again."""
        from audio.dialogue import dialogue_cache_key

        host = _make_pipeline_host(tmp_path)
        host._save_checkpoint = MagicMock()

        scene_id = "scene_regen"
        characters = [{"id": "c1", "voice_id": "v1", "name": "Alice"}]
        lang = "English"

        # Create a pre-existing artifact with the OLD key
        old_lines = [{"character_id": "c1", "text": "Old line"}]
        old_key = dialogue_cache_key(old_lines, characters, lang)
        old_path = str(tmp_path / f"audio_{scene_id}_{old_key}.mp3")
        with open(old_path, "wb") as f:
            f.write(b"old-audio")

        # Scene now has DIFFERENT dialogue → different key → miss
        new_lines = [{"character_id": "c1", "text": "New line"}]
        new_key = dialogue_cache_key(new_lines, characters, lang)
        assert old_key != new_key, "keys should differ for different dialogue"

        scene = {"id": scene_id, "dialogue": new_lines}

        call_count = {"n": 0}

        def fake_voiceover(lines, chars, out_path, ctx=None, cost_tracker=None):
            call_count["n"] += 1
            with open(out_path, "wb") as f:
                f.write(b"new-audio")
            return True

        with patch("cinema_pipeline.generate_dialogue_voiceover", side_effect=fake_voiceover):
            result = host._ensure_scene_audio(scene, characters)

        assert call_count["n"] == 1, "voiceover should be called for changed dialogue"
        expected_new_path = str(tmp_path / f"audio_{scene_id}_{new_key}.mp3")
        assert result == expected_new_path


# ---------------------------------------------------------------------------
# 6. estimate_reassembly_cost: tts_lines_to_generate + estimated_tts_usd
# ---------------------------------------------------------------------------

class TestEstimateReassemblyCostTTS:

    def _make_project(self, scene_id: str, shot_id: str, dialogue_lines: list) -> dict:
        """Build a minimal project dict with one approved shot and explicit dialogue.

        The scene includes ``characters_present: ["c1"]`` so the T-D fix's
        scene-filtered character list resolves to the single project character
        (matching the writer's behaviour for a scene with one active character).
        """
        return {
            "id": "proj_test",
            "global_settings": {"language": "English"},
            "characters": [{"id": "c1", "voice_id": "v1"}],
            "scenes": [
                {
                    "id": scene_id,
                    "duration_seconds": 5.0,
                    "characters_present": ["c1"],  # T-D: writer filters by this
                    "dialogue": dialogue_lines,
                    "shots": [
                        {
                            "id": shot_id,
                            "approved_final_take_id": "take_1",
                            "motion_takes": [
                                {"id": "take_1", "metadata": {"duration_s": 5.0}},
                            ],
                        }
                    ],
                }
            ],
        }

    def test_no_cached_artifacts_counts_all_lines(self, tmp_path):
        """Without cached artifacts, tts_lines_to_generate == line count."""
        from cinema.screening import estimate_reassembly_cost
        from audio.dialogue import dialogue_cache_key

        scene_id = "scene_tts_est"
        shot_id = "shot_tts_est"
        dialogue_lines = [
            {"character_id": "c1", "text": "Line one"},
            {"character_id": "c1", "text": "Line two"},
        ]
        project = self._make_project(scene_id, shot_id, dialogue_lines)
        project["id"] = "proj_tts_test"

        # Patch get_project_dir to point at tmp_path so estimate looks in
        # tmp_path/temp (which is empty — no cached files).
        temp_dir = str(tmp_path / "temp")
        os.makedirs(temp_dir, exist_ok=True)

        with patch("cinema.screening.os.path.join", wraps=os.path.join), \
             patch("domain.project_manager.get_project_dir", return_value=str(tmp_path)):
            result = estimate_reassembly_cost(project)

        assert result["tts_lines_to_generate"] == len(dialogue_lines)
        expected_usd = round(len(dialogue_lines) * 0.01, 2)
        assert result["estimated_tts_usd"] == expected_usd

    def test_cached_artifacts_reduce_tts_count(self, tmp_path):
        """With cached keyed artifacts, tts_lines_to_generate == 0."""
        from cinema.screening import estimate_reassembly_cost
        from audio.dialogue import dialogue_cache_key

        scene_id = "scene_cached"
        shot_id = "shot_cached"
        dialogue_lines = [
            {"character_id": "c1", "text": "Cached line"},
        ]
        characters = [{"id": "c1", "voice_id": "v1"}]
        project = self._make_project(scene_id, shot_id, dialogue_lines)
        project["id"] = "proj_cached_test"

        # Write the keyed artifact so estimate sees it as cached.
        temp_dir = str(tmp_path / "temp")
        os.makedirs(temp_dir, exist_ok=True)
        key = dialogue_cache_key(dialogue_lines, characters, "English")
        cached_path = os.path.join(temp_dir, f"audio_{scene_id}_{key}.mp3")
        with open(cached_path, "wb") as f:
            f.write(b"cached")

        with patch("domain.project_manager.get_project_dir", return_value=str(tmp_path)):
            result = estimate_reassembly_cost(project)

        assert result["tts_lines_to_generate"] == 0
        assert result["estimated_tts_usd"] == 0.0

    def test_empty_project_returns_zero_tts(self):
        """Non-dict project returns tts_lines_to_generate=0, estimated_tts_usd=0.0."""
        from cinema.screening import estimate_reassembly_cost
        result = estimate_reassembly_cost(None)  # type: ignore[arg-type]
        assert result["tts_lines_to_generate"] == 0
        assert result["estimated_tts_usd"] == 0.0

    def test_action_only_scene_counts_one_line(self, tmp_path):
        """Action-only scene (characters + action, NO dialogue field) counts a
        conservative 1 line — _ensure_scene_audio LLM-generates dialogue for
        these and renders TTS, so omitting them undercounts (spec review SI-1)."""
        from cinema.screening import estimate_reassembly_cost

        project = self._make_project("scene_action_only", "shot_action_only", [])
        project["id"] = "proj_action_only_test"
        # Remove the dialogue field entirely and give the scene an action.
        del project["scenes"][0]["dialogue"]
        project["scenes"][0]["action"] = "Two figures argue silently in the rain."

        temp_dir = str(tmp_path / "temp")
        os.makedirs(temp_dir, exist_ok=True)

        with patch("domain.project_manager.get_project_dir", return_value=str(tmp_path)):
            result = estimate_reassembly_cost(project)

        assert result["tts_lines_to_generate"] == 1, (
            "Action-only scenes must count >=1 TTS line (LLM-generated dialogue "
            "is rendered by _ensure_scene_audio); silent omission was SI-1"
        )
        assert result["estimated_tts_usd"] == 0.01

    # T-D regression tests: estimator must use scene-filtered characters (not
    # project-wide) when computing dialogue cache keys, mirroring the writer.

    def test_td_subset_scene_writer_key_is_cache_hit(self, tmp_path):
        """T-D regression: project has chars A+B; scene only has B present.

        The writer uses scene-filtered [B] when generating the key.
        A file written at that key path should make the estimator report 0
        tts_lines_to_generate — i.e., the estimator uses the same key.
        """
        from cinema.screening import estimate_reassembly_cost
        from audio.dialogue import dialogue_cache_key

        scene_id = "scene_td_subset"
        shot_id = "shot_td_subset"
        dialogue_lines = [
            {"character_id": "char_b", "text": "Only B speaks here"},
        ]
        # Project has two characters; scene only lists B in characters_present.
        project = {
            "id": "proj_td_subset",
            "global_settings": {"language": "English"},
            "characters": [
                {"id": "char_a", "voice_id": "voice_a"},
                {"id": "char_b", "voice_id": "voice_b"},
            ],
            "scenes": [
                {
                    "id": scene_id,
                    "duration_seconds": 5.0,
                    "characters_present": ["char_b"],  # only B, not A
                    "dialogue": dialogue_lines,
                    "shots": [
                        {
                            "id": shot_id,
                            "approved_final_take_id": "take_1",
                            "motion_takes": [
                                {"id": "take_1", "metadata": {"duration_s": 5.0}},
                            ],
                        }
                    ],
                }
            ],
        }

        # Write the cached artifact at the WRITER's key path — filtered to [B].
        scene_filtered_chars = [{"id": "char_b", "voice_id": "voice_b"}]
        writer_key = dialogue_cache_key(dialogue_lines, scene_filtered_chars, "English")
        temp_dir = str(tmp_path / "temp")
        os.makedirs(temp_dir, exist_ok=True)
        writer_path = os.path.join(temp_dir, f"audio_{scene_id}_{writer_key}.mp3")
        with open(writer_path, "wb") as f:
            f.write(b"cached-by-writer")

        with patch("domain.project_manager.get_project_dir", return_value=str(tmp_path)):
            result = estimate_reassembly_cost(project)

        assert result["tts_lines_to_generate"] == 0, (
            "T-D: estimator must use scene-filtered chars (writer key == estimator key); "
            f"writer_key={writer_key!r} was not recognized as cached — "
            "estimator is still using the project-wide character list"
        )

    def test_td_wrong_key_is_not_a_cache_hit(self, tmp_path):
        """T-D inverse regression: file at the OLD wrong (project-wide) key path
        must NOT be counted as cached — proves the fix actually changed key computation.
        """
        from cinema.screening import estimate_reassembly_cost
        from audio.dialogue import dialogue_cache_key

        scene_id = "scene_td_wrong_key"
        shot_id = "shot_td_wrong_key"
        dialogue_lines = [
            {"character_id": "char_b", "text": "Only B speaks here"},
        ]
        project = {
            "id": "proj_td_wrong_key",
            "global_settings": {"language": "English"},
            "characters": [
                {"id": "char_a", "voice_id": "voice_a"},
                {"id": "char_b", "voice_id": "voice_b"},
            ],
            "scenes": [
                {
                    "id": scene_id,
                    "duration_seconds": 5.0,
                    "characters_present": ["char_b"],  # only B in scene
                    "dialogue": dialogue_lines,
                    "shots": [
                        {
                            "id": shot_id,
                            "approved_final_take_id": "take_1",
                            "motion_takes": [
                                {"id": "take_1", "metadata": {"duration_s": 5.0}},
                            ],
                        }
                    ],
                }
            ],
        }

        # Write a file at the OLD wrong key — project-wide [A, B].
        all_chars = [{"id": "char_a", "voice_id": "voice_a"}, {"id": "char_b", "voice_id": "voice_b"}]
        old_wrong_key = dialogue_cache_key(dialogue_lines, all_chars, "English")
        temp_dir = str(tmp_path / "temp")
        os.makedirs(temp_dir, exist_ok=True)
        old_path = os.path.join(temp_dir, f"audio_{scene_id}_{old_wrong_key}.mp3")
        with open(old_path, "wb") as f:
            f.write(b"wrong-key-artifact")

        with patch("domain.project_manager.get_project_dir", return_value=str(tmp_path)):
            result = estimate_reassembly_cost(project)

        assert result["tts_lines_to_generate"] == len(dialogue_lines), (
            "T-D: artifact at OLD project-wide key must NOT count as cached; "
            f"old_wrong_key={old_wrong_key!r} — estimator is still using the "
            "project-wide character list (pre-fix behavior detected)"
        )


# ---------------------------------------------------------------------------
# 7. Per-line path: content-keyed, lives under dirname(output_path), NOT CWD
# ---------------------------------------------------------------------------

class TestPerLinePathIsContentKeyed:

    def test_per_line_path_lives_under_output_dir(self, tmp_path):
        """Temp line files must live under dirname(output_filename), not CWD."""
        import subprocess
        from audio.dialogue import generate_dialogue_voiceover, _line_cache_key

        output_file = str(tmp_path / "assembled.mp3")
        dialogue_lines = [{"character_id": "c1", "text": "Hello"}]
        characters = [{"id": "c1", "voice_id": "v_test", "name": "Alice"}]

        captured_temp_paths = []

        def fake_cartesia(text, voice_id, output_path, language="en", model_id="sonic-2"):
            captured_temp_paths.append(output_path)
            with open(output_path, "wb") as f:
                f.write(b"fake-audio")
            return True

        def fake_subprocess_run(cmd, **kwargs):
            # For ffmpeg silence generation: write a dummy silence file
            if "-f" in cmd and "lavfi" in cmd:
                silence_out = cmd[-1]
                with open(silence_out, "wb") as f:
                    f.write(b"silence")
            # For ffmpeg concat: write a dummy output file
            elif "-f" in cmd and "concat" in cmd:
                out_idx = cmd.index("-i") + 2  # skip concat list, then output
                # output is the last argument
                out = cmd[-1]
                with open(out, "wb") as f:
                    f.write(b"assembled")
            result = MagicMock()
            result.returncode = 0
            return result

        with patch("audio.dialogue.generate_cartesia", side_effect=fake_cartesia), \
             patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("audio.dialogue._resolve_tts_provider", return_value="CARTESIA_SONIC_2"), \
             patch("audio.dialogue._resolve_cartesia_voice", return_value="fake-uuid-1234-5678-abcd-ef0123456789"), \
             patch("audio.dialogue.settings") as mock_settings:
            mock_settings.cartesia_api_key = "test_key"
            generate_dialogue_voiceover(
                dialogue_lines,
                characters,
                output_file,
            )

        # All temp paths must be under tmp_path, not in the CWD
        for p in captured_temp_paths:
            assert os.path.dirname(p) == str(tmp_path), (
                f"Expected temp path under {tmp_path}, got {p}"
            )
            # Must be content-keyed (not index-based)
            fname = os.path.basename(p)
            assert fname.startswith("dialogue_line_"), f"Unexpected filename: {fname}"
            assert not fname.startswith("temp_dialogue_line_"), (
                f"Old CWD-relative index-keyed name detected: {fname}"
            )
