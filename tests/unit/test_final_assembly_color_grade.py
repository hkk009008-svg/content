"""Final-assembly color-grade preset resolution.

Regression cover for the two-part defect found in the slice-9b video/spend
settings reconciliation audit:

  1. `_assemble_final` never read `global_settings["color_grade_preset"]`, so
     the Setup "Color grade" knob (VideoSection.tsx) — and the four
     PRODUCTION_PRESETS in web/src/lib/guidance.ts that write it — were
     silently discarded in the finished movie. Only the manual per-clip path
     (`apply_correction("color_grade", ...)`) honored the setting.

  2. The mood fallback was itself unreachable: it read `settings["mood"]`, a
     key `GlobalSettings` does not define (the project-level field is
     `music_mood`; bare `mood` is a *Scene* field), and its "cinematic"
     default is absent from the mood map. Every UI-created project therefore
     graded to "warm_cinema" unconditionally.

These tests pin the resolution order only — `explicit preset > mood mapping >
"warm_cinema"` — so they stay honest without invoking ffmpeg.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import cinema_pipeline
import phase_c_ffmpeg
from cinema_pipeline import CinemaPipeline
from phase_c_ffmpeg import COLOR_GRADE_PRESETS


def _resolve_grade_preset(tmp_path, settings: dict) -> str:
    """Drive `_assemble_final` far enough to capture the preset it grades with.

    ffmpeg never runs: `subprocess.run` is mocked (covering both the normalize
    loop and the nested `_concat_copy` stitch), and `apply_color_grade` is
    replaced by a recorder. Steps after grading may fail on the absent media —
    irrelevant, because the preset is captured during step 4.
    """
    temp_dir = tmp_path / "temp"
    export_dir = tmp_path / "exports"
    # exist_ok: some tests resolve several settings dicts under one tmp_path.
    temp_dir.mkdir(exist_ok=True)
    export_dir.mkdir(exist_ok=True)

    clip = temp_dir / "shot_1_0.mp4"
    clip.write_bytes(b"fake-clip")

    # Bypass __init__: _assemble_final reads only these two dirs, and a real
    # CinemaPipeline would require a full project on disk. Both are read-only
    # properties delegating to `_core` (cinema_pipeline.py:143-148), so the
    # stand-in core carries them.
    pipeline = CinemaPipeline.__new__(CinemaPipeline)
    pipeline._core = SimpleNamespace(temp_dir=str(temp_dir), export_dir=str(export_dir))

    captured = {}

    def _recording_grade(video_path, output_path, preset="warm_cinema", lut_path=None):
        captured["preset"] = preset
        return output_path

    scene_data = [{"scene_id": "scene_1", "clips": [str(clip)]}]

    with patch.object(cinema_pipeline.subprocess, "run", MagicMock()), \
         patch.object(phase_c_ffmpeg, "apply_color_grade", _recording_grade):
        try:
            pipeline._assemble_final(scene_data, bgm_path="", settings=settings)
        except Exception:
            # Post-grade steps (audio mix / loudnorm) operate on files that a
            # mocked ffmpeg never wrote. The captured preset is already final.
            pass

    assert "preset" in captured, "color grading step never ran — harness is stale"
    return captured["preset"]


class TestExplicitPresetWins:
    """The operator's explicit choice must reach the finished movie."""

    def test_explicit_preset_is_honored(self, tmp_path):
        """The reported bug: `color_grade_preset` was ignored by final assembly."""
        assert _resolve_grade_preset(tmp_path, {"color_grade_preset": "cool_noir"}) == "cool_noir"

    def test_explicit_preset_overrides_mood_mapping(self, tmp_path):
        """Precedence, not merely presence: an explicit knob beats the mood map.

        `music_mood="action"` maps to "high_contrast"; the operator asked for
        "pastel" and must get it.
        """
        preset = _resolve_grade_preset(
            tmp_path, {"music_mood": "action", "color_grade_preset": "pastel"}
        )
        assert preset == "pastel"

    def test_guidance_preset_settings_survive_assembly(self, tmp_path):
        """web/src/lib/guidance.ts PRODUCTION_PRESETS write both keys together.

        'Kinetic Action' sets music_mood=action AND color_grade_preset=
        high_contrast; 'Dialogue Precision' sets color_grade_preset=desaturated
        with no mood. Both must land as written.
        """
        assert _resolve_grade_preset(
            tmp_path, {"music_mood": "action", "color_grade_preset": "high_contrast"}
        ) == "high_contrast"
        assert _resolve_grade_preset(
            tmp_path, {"color_grade_preset": "desaturated"}
        ) == "desaturated"


class TestMoodFallback:
    """The documented fallback — "Auto-mapped from mood if unset" — must work."""

    def test_music_mood_drives_the_grade_when_preset_unset(self, tmp_path):
        """The second defect: the map read `mood`, but the real key is `music_mood`.

        Before the fix this returned "warm_cinema" for every mood.
        """
        assert _resolve_grade_preset(tmp_path, {"music_mood": "suspense"}) == "cool_noir"

    @pytest.mark.parametrize(
        "music_mood,expected",
        [
            ("suspense", "cool_noir"),
            ("horror", "moonlight"),
            ("melancholic", "desaturated"),
            ("romantic", "golden_hour"),
            ("action", "high_contrast"),
            ("ethereal", "pastel"),
            ("cyberpunk", "vibrant"),
        ],
    )
    def test_mood_map_is_reachable_for_every_family(self, tmp_path, music_mood, expected):
        """One case per distinct grade in the map — proves none is dead code."""
        assert _resolve_grade_preset(tmp_path, {"music_mood": music_mood}) == expected

    def test_legacy_bare_mood_key_still_honored(self, tmp_path):
        """PUT /api/projects/<pid> merges global_settings unrestricted, so a
        hand-crafted project may carry a bare `mood`. It kept working before
        this fix and must keep working after — no silent grade shift."""
        assert _resolve_grade_preset(tmp_path, {"mood": "noir"}) == "cool_noir"

    def test_bare_mood_takes_precedence_over_music_mood(self, tmp_path):
        """Legacy key first preserves the pre-fix result for such a project."""
        preset = _resolve_grade_preset(tmp_path, {"mood": "horror", "music_mood": "action"})
        assert preset == "moonlight"

    def test_default_when_nothing_configured(self, tmp_path):
        assert _resolve_grade_preset(tmp_path, {}) == "warm_cinema"

    def test_unmapped_mood_falls_back_to_default(self, tmp_path):
        """"cinematic" is deliberately absent from the map."""
        assert _resolve_grade_preset(tmp_path, {"music_mood": "cinematic"}) == "warm_cinema"


class TestInvalidPreset:
    """An unusable setting must be reported, not silently swapped."""

    def test_unknown_preset_falls_back_to_mood_and_warns(self, tmp_path, caplog):
        """`apply_color_grade` would swallow an unknown preset via its own
        `.get(preset, warm_cinema)` and log it as if applied. Assembly rejects
        it first, warns, and honors the next tier (the mood map)."""
        with caplog.at_level("WARNING"):
            preset = _resolve_grade_preset(
                tmp_path, {"color_grade_preset": "cool_noirr", "music_mood": "horror"}
            )

        assert preset == "moonlight"
        assert any(
            "Unknown color_grade_preset" in r.message for r in caplog.records
        ), "an unusable preset must warn, not degrade silently"

    def test_resolved_preset_is_always_a_known_key(self, tmp_path):
        """Whatever the inputs, assembly hands ffmpeg a real preset."""
        for settings in ({}, {"music_mood": "gritty"}, {"color_grade_preset": "bogus"}):
            assert _resolve_grade_preset(tmp_path, settings) in COLOR_GRADE_PRESETS


class TestParityWithManualCorrection:
    """The two color-grade paths must not drift apart again."""

    def test_assembly_matches_manual_correction_default_resolution(self, tmp_path):
        """`controller.apply_correction` resolves
        `params.preset > color_grade_preset > "warm_cinema"`. With no per-clip
        override, assembly must reach the same preset from the same settings."""
        settings = {"color_grade_preset": "golden_hour"}

        manual = settings.get("color_grade_preset", "warm_cinema")  # controller.py:2980
        assert _resolve_grade_preset(tmp_path, settings) == manual
