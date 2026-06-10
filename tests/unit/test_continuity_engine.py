"""
Tests for continuity_engine.py — TemporalConsistencyManager denoise logic.
Isolated unit tests: no external APIs, no DeepFace, no project files needed.
"""

import sys
import os


import tempfile
import pytest

from continuity_engine import TemporalConsistencyManager


# ---------------------------------------------------------------------------
# TemporalConsistencyManager — denoise strength ladder
# ---------------------------------------------------------------------------


class TestGetDenoiseStrength:
    def setup_method(self):
        self.mgr = TemporalConsistencyManager()
        # Simulate having a previous image so we're not in "first shot" mode
        self.mgr.last_generated_image = "/tmp/fake_prev.jpg"
        self.mgr.current_scene_id = "scene_1"

    def test_first_shot_returns_055(self):
        """shot_index=0 -> 0.55 (first shot of scene, max creative freedom)."""
        mgr = TemporalConsistencyManager()  # fresh, no previous image
        strength = mgr.get_denoise_strength(shot_index=0)
        assert strength == 0.55

    def test_first_shot_even_with_scenes(self):
        """shot_index=0 always returns 0.55 regardless of scene data."""
        mgr = TemporalConsistencyManager()
        strength = mgr.get_denoise_strength(
            shot_index=0,
            previous_scene={"location_id": "loc_a"},
            current_scene={"location_id": "loc_b"},
        )
        assert strength == 0.55

    def test_no_previous_image_returns_055(self):
        """If last_generated_image is None, treat as first shot."""
        mgr = TemporalConsistencyManager()
        mgr.current_scene_id = "scene_1"
        strength = mgr.get_denoise_strength(shot_index=2)
        assert strength == 0.55

    def test_location_change_returns_050(self):
        """Different location between scenes -> 0.50."""
        strength = self.mgr.get_denoise_strength(
            shot_index=1,
            previous_scene={"location_id": "office"},
            current_scene={"location_id": "street"},
        )
        assert strength == 0.50

    def test_location_change_via_shots_returns_050(self):
        """Different location via shot dicts (no scene) -> 0.50."""
        strength = self.mgr.get_denoise_strength(
            shot_index=1,
            previous_shot={"location_id": "office"},
            current_shot={"location_id": "street"},
        )
        assert strength == 0.50

    def test_same_location_shot_1_returns_040(self):
        """Same location, shot_index=1 -> 0.40 (early shot, slight creative room)."""
        strength = self.mgr.get_denoise_strength(
            shot_index=1,
            previous_scene={"location_id": "office"},
            current_scene={"location_id": "office"},
        )
        assert strength == 0.40

    def test_same_location_shot_2_returns_030(self):
        """Same location, shot_index=2 -> 0.30 (tightest)."""
        strength = self.mgr.get_denoise_strength(
            shot_index=2,
            previous_scene={"location_id": "office"},
            current_scene={"location_id": "office"},
        )
        assert strength == 0.30

    def test_same_location_shot_5_returns_030(self):
        """Same location, shot_index >= 2 always returns 0.30."""
        strength = self.mgr.get_denoise_strength(
            shot_index=5,
            previous_scene={"location_id": "office"},
            current_scene={"location_id": "office"},
        )
        assert strength == 0.30

    def test_no_location_data_shot_1_returns_040(self):
        """No location data provided, shot_index=1 -> 0.40 (fallback same-location early)."""
        strength = self.mgr.get_denoise_strength(shot_index=1)
        assert strength == 0.40

    def test_no_location_data_shot_3_returns_030(self):
        """No location data provided, shot_index >= 2 -> 0.30 (fallback same-location later)."""
        strength = self.mgr.get_denoise_strength(shot_index=3)
        assert strength == 0.30

    def test_denoise_range_bounded(self):
        """All denoise values should be within [0.30, 0.55]."""
        test_cases = [
            (0, {}),
            (1, {}),
            (2, {}),
            (5, {}),
            (1, {"previous_scene": {"location_id": "a"}, "current_scene": {"location_id": "b"}}),
        ]
        for idx, kwargs in test_cases:
            # Reset for each test
            mgr = TemporalConsistencyManager()
            mgr.last_generated_image = "/tmp/fake.jpg"
            mgr.current_scene_id = "s1"
            strength = mgr.get_denoise_strength(idx, **kwargs)
            assert 0.30 <= strength <= 0.55, f"shot_index={idx}, kwargs={kwargs} -> {strength}"


# ---------------------------------------------------------------------------
# should_use_img2img
# ---------------------------------------------------------------------------


class TestShouldUseImg2Img:
    def test_first_shot_of_scene_returns_false(self):
        mgr = TemporalConsistencyManager()
        assert mgr.should_use_img2img("scene_1", shot_index=0) is False

    def test_new_scene_resets_and_returns_false(self):
        mgr = TemporalConsistencyManager()
        mgr.last_generated_image = "/tmp/prev.jpg"
        mgr.current_scene_id = "scene_1"
        # Switch to new scene -> resets
        assert mgr.should_use_img2img("scene_2", shot_index=1) is False
        assert mgr.last_generated_image is None

    def test_subsequent_shot_same_scene_returns_true(self):
        mgr = TemporalConsistencyManager()
        mgr.last_generated_image = "/tmp/prev.jpg"
        mgr.current_scene_id = "scene_1"
        assert mgr.should_use_img2img("scene_1", shot_index=1) is True

    def test_no_previous_image_returns_false(self):
        mgr = TemporalConsistencyManager()
        mgr.current_scene_id = "scene_1"
        assert mgr.should_use_img2img("scene_1", shot_index=1) is False

    def test_shot_index_0_always_false_even_with_image(self):
        mgr = TemporalConsistencyManager()
        mgr.last_generated_image = "/tmp/prev.jpg"
        mgr.current_scene_id = "scene_1"
        assert mgr.should_use_img2img("scene_1", shot_index=0) is False


# ---------------------------------------------------------------------------
# record_generated / reset
# ---------------------------------------------------------------------------


class TestRecordAndReset:
    def test_record_generated_stores_path_and_scene(self):
        mgr = TemporalConsistencyManager()
        mgr.record_generated("/tmp/shot_001.jpg", "scene_a")
        assert mgr.last_generated_image == "/tmp/shot_001.jpg"
        assert mgr.current_scene_id == "scene_a"

    def test_reset_clears_state(self):
        mgr = TemporalConsistencyManager()
        mgr.record_generated("/tmp/shot_001.jpg", "scene_a")
        mgr.reset()
        assert mgr.last_generated_image is None
        assert mgr.current_scene_id is None

    def test_get_init_image_returns_none_when_no_image(self):
        mgr = TemporalConsistencyManager()
        assert mgr.get_init_image() is None

    def test_get_init_image_returns_none_when_file_missing(self):
        mgr = TemporalConsistencyManager()
        mgr.last_generated_image = "/nonexistent/path/image.jpg"
        assert mgr.get_init_image() is None

    def test_get_init_image_returns_path_when_file_exists(self, tmp_path):
        img_path = str(tmp_path / "test.jpg")
        with open(img_path, "w") as f:
            f.write("fake image data")
        mgr = TemporalConsistencyManager()
        mgr.last_generated_image = img_path
        assert mgr.get_init_image() == img_path


# ---------------------------------------------------------------------------
# ContinuityEngine.enhance_shot_prompt — secondary_chars population (P1-1)
# ---------------------------------------------------------------------------


import unittest.mock as mock
from continuity_engine import ContinuityEngine


def _make_engine(char_a_ref="/ref/char_a.jpg", char_b_ref="/ref/char_b.jpg"):
    """
    Build a ContinuityEngine with stubbed file-system dependencies.

    Patches:
    - get_project_dir (called in __init__ for cache_dir)
    - get_character_embedding (called in CharacterContinuityTracker.__init__)
    - identity.make_validator (avoids DeepFace/disk I/O)

    After construction, character_tracker methods are replaced with Mocks so
    tests control get_reference_for_pulid / get_multi_angle_refs return values.
    """
    project = {
        "id": "proj_test",
        "characters": [
            {"id": "char_a", "name": "Alice"},
            {"id": "char_b", "name": "Bob"},
        ],
        "global_settings": {"adaptive_pulid": False},
    }

    with (
        mock.patch("domain.project_manager.get_project_dir", return_value="/tmp/proj_test"),
        mock.patch("domain.continuity_engine.get_character_embedding", return_value=None),
        mock.patch("identity.make_validator", return_value=mock.MagicMock()),
    ):
        engine = ContinuityEngine(project)

    # Replace tracker methods with mocks; callers in enhance_shot_prompt
    # go through self.character_tracker.* so patching at this level is
    # the same level the plan specifies.
    def _ref_for_pulid(cid):
        if cid == "char_a":
            return char_a_ref
        if cid == "char_b":
            return char_b_ref
        return None

    engine.character_tracker.get_reference_for_pulid = mock.MagicMock(side_effect=_ref_for_pulid)
    engine.character_tracker.get_multi_angle_refs = mock.MagicMock(
        side_effect=lambda cid: [f"/angles/{cid}_front.jpg"]
    )
    # get_primary_character is not patched — real logic (returns chars[0])
    return engine


@pytest.fixture
def engine_two_chars():
    return _make_engine(char_a_ref="/ref/char_a.jpg", char_b_ref="/ref/char_b.jpg")


@pytest.fixture
def engine_two_chars_b_unregistered():
    # char_b has no reference (unregistered)
    return _make_engine(char_a_ref="/ref/char_a.jpg", char_b_ref=None)


class TestContinuityEngineSecondaryChars:
    def test_secondary_chars_populated_for_registered_second_char(self, engine_two_chars):
        """chars_in_frame[1:] with a registered reference appear in secondary_chars."""
        enhanced = engine_two_chars.enhance_shot_prompt(
            {"characters_in_frame": ["char_a", "char_b"], "prompt": "p"},
            {"id": "s1", "shots": []}, None, 0,
        )
        sec = enhanced["continuity_config"]["secondary_chars"]
        assert [c["char_id"] for c in sec] == ["char_b"]
        assert sec[0]["reference"]            # the registered ref path
        assert "identity_anchor" in sec[0] and "multi_angle_refs" in sec[0]

    def test_secondary_chars_skips_unregistered(self, engine_two_chars_b_unregistered):
        enhanced = engine_two_chars_b_unregistered.enhance_shot_prompt(
            {"characters_in_frame": ["char_a", "char_b"], "prompt": "p"},
            {"id": "s1", "shots": []}, None, 0,
        )
        assert enhanced["continuity_config"]["secondary_chars"] == []

    def test_secondary_chars_empty_for_single_char(self, engine_two_chars):
        enhanced = engine_two_chars.enhance_shot_prompt(
            {"characters_in_frame": ["char_a"], "prompt": "p"},
            {"id": "s1", "shots": []}, None, 0,
        )
        assert enhanced["continuity_config"]["secondary_chars"] == []
