"""
Tests for continuity_engine.py — TemporalConsistencyManager denoise logic.
Isolated unit tests: no external APIs, no DeepFace, no project files needed.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from continuity_engine import TemporalConsistencyManager
from domain.continuity_engine import _stable_scene_seed


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
# get_denoise_strength — explicit anchor overrides mutable chaining history
# (Slice 7 defect 1: denoise strength must derive from the REAL anchor/
# init-image condition, not TemporalConsistencyManager's own mutable
# last_generated_image/shot_index history).
# ---------------------------------------------------------------------------


class TestGetDenoiseStrengthExplicitAnchor:
    def test_first_shot_with_explicit_anchor_is_not_max_creative_freedom(self):
        """A first shot (shot_index=0) WITH an explicit, real anchor image IS
        chaining from a real init image — it must not get the
        no-image-to-chain-from 0.55 strength."""
        mgr = TemporalConsistencyManager()  # fresh: no prior chaining history
        strength = mgr.get_denoise_strength(shot_index=0, has_explicit_anchor=True)
        assert strength != 0.55
        assert strength == 0.40  # falls through to the early-shot fallback rung

    def test_first_shot_without_anchor_keeps_max_creative_freedom(self):
        """Control: without an explicit anchor, shot_index=0 still returns
        first-shot strength — the anchor condition is what must flip it."""
        mgr = TemporalConsistencyManager()
        strength = mgr.get_denoise_strength(shot_index=0, has_explicit_anchor=False)
        assert strength == 0.55

    def test_explicit_anchor_still_honors_location_change(self):
        """The anchor bypasses ONLY the first-shot short-circuit — the
        transition-type ladder underneath (location continuity) still runs."""
        mgr = TemporalConsistencyManager()
        strength = mgr.get_denoise_strength(
            shot_index=0,
            has_explicit_anchor=True,
            previous_scene={"location_id": "office"},
            current_scene={"location_id": "street"},
        )
        assert strength == 0.50

    def test_explicit_anchor_ignores_mutable_chaining_history(self):
        """has_explicit_anchor must come from the caller's real anchor/init
        condition, not self.last_generated_image — the result must be the
        same whether or not this manager instance happens to already carry
        prior chaining state."""
        with_history = TemporalConsistencyManager()
        with_history.last_generated_image = "/tmp/fake_prev.jpg"
        with_history.current_scene_id = "scene_1"

        fresh = TemporalConsistencyManager()  # last_generated_image is None

        assert with_history.get_denoise_strength(
            shot_index=0, has_explicit_anchor=True
        ) == fresh.get_denoise_strength(shot_index=0, has_explicit_anchor=True)


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
        # Exact values — a reference/anchor swap or a dropped angle list must
        # fail loud (Task 7's allocator consumes these verbatim).
        assert sec[0]["reference"] == "/ref/char_b.jpg"
        assert sec[0]["multi_angle_refs"] == ["/angles/char_b_front.jpg"]
        assert isinstance(sec[0]["identity_anchor"], str)

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


# ---------------------------------------------------------------------------
# ContinuityEngine.enhance_shot_prompt — end-to-end explicit-anchor denoise
# (Slice 7 defect 1 acceptance: first shot WITH an explicit anchor uses
# continuity strength; first shot WITHOUT one uses first-shot strength).
# ---------------------------------------------------------------------------


class TestEnhanceShotPromptExplicitAnchorDenoise:
    def test_first_shot_with_real_anchor_file_uses_continuity_strength(
        self, engine_two_chars, tmp_path
    ):
        anchor_path = str(tmp_path / "anchor.jpg")
        with open(anchor_path, "w") as f:
            f.write("fake anchor image data")

        enhanced = engine_two_chars.enhance_shot_prompt(
            {"characters_in_frame": [], "prompt": "p"},
            {"id": "scene_1", "shots": []},
            None,
            0,
            approved_anchor_image=anchor_path,
        )

        cc = enhanced["continuity_config"]
        assert cc["use_img2img"] is True
        assert cc["init_image"] == anchor_path
        # Not the first-shot-with-no-image 0.55 — a real anchor is a real
        # init image, so the transition-type ladder applies.
        assert cc["denoise_strength"] != 0.55
        assert cc["denoise_strength"] == 0.40

    def test_first_shot_without_anchor_uses_first_shot_strength(self, engine_two_chars):
        enhanced = engine_two_chars.enhance_shot_prompt(
            {"characters_in_frame": [], "prompt": "p"},
            {"id": "scene_1", "shots": []},
            None,
            0,
        )
        cc = enhanced["continuity_config"]
        assert cc["use_img2img"] is False
        assert cc["denoise_strength"] == 1.0

    def test_nonexistent_anchor_path_falls_back_to_first_shot_strength(
        self, engine_two_chars
    ):
        """A path that fails os.path.exists is not a real anchor condition —
        must behave identically to no anchor at all, never crash."""
        enhanced = engine_two_chars.enhance_shot_prompt(
            {"characters_in_frame": [], "prompt": "p"},
            {"id": "scene_1", "shots": []},
            None,
            0,
            approved_anchor_image="/nonexistent/anchor.jpg",
        )
        cc = enhanced["continuity_config"]
        assert cc["use_img2img"] is False
        assert cc["denoise_strength"] == 1.0


# ---------------------------------------------------------------------------
# ContinuityEngine.enhance_shot_prompt — stable scene seeds
# ---------------------------------------------------------------------------


def _scene_seed_from_subprocess(scene_id: str, python_hash_seed: int) -> int:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = str(python_hash_seed)
    code = (
        "import sys\n"
        "from domain.continuity_engine import _stable_scene_seed\n"
        "print(_stable_scene_seed(sys.argv[1]))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, scene_id],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip().splitlines()[-1])


def test_scene_seed_is_stable_across_python_hash_seeds():
    first = _scene_seed_from_subprocess("scene_cross_process", 1)
    second = _scene_seed_from_subprocess("scene_cross_process", 987654)

    assert first == second


@pytest.mark.parametrize("scene_id", ["", "scene_1", "장면_마지막"])
def test_stable_scene_seed_is_31_bit_int(scene_id):
    seed = _stable_scene_seed(scene_id)

    assert type(seed) is int
    assert 0 <= seed <= 0x7FFFFFFF


def test_stable_scene_seed_known_sha256_vector():
    # UTF-8 SHA-256 starts f7 ab aa 27; big-endian 0xf7abaa27 masked to
    # 31 bits is 0x77abaa27.
    assert _stable_scene_seed("scene_é") == 2_007_738_919


def test_representative_scene_ids_have_different_stable_seeds():
    assert _stable_scene_seed("scene_alpha") != _stable_scene_seed("scene_beta")


@pytest.mark.parametrize("location_seed", [0, 482901])
def test_explicit_location_seed_wins(engine_two_chars, location_seed):
    engine_two_chars.location_persistence.get_prompt = mock.MagicMock(
        return_value=""
    )
    engine_two_chars.location_persistence.get_seed = mock.MagicMock(
        return_value=location_seed
    )

    enhanced = engine_two_chars.enhance_shot_prompt(
        {"characters_in_frame": [], "prompt": "p"},
        {"id": "scene_with_location", "location_id": "loc_a", "shots": []},
        None,
        0,
    )

    assert enhanced["continuity_config"]["location_seed"] == location_seed
    assert enhanced["continuity_config"]["scene_seed"] == location_seed


def test_missing_location_seed_uses_stable_fallback(engine_two_chars):
    engine_two_chars.location_persistence.get_prompt = mock.MagicMock(
        return_value=""
    )
    engine_two_chars.location_persistence.get_seed = mock.MagicMock(
        return_value=None
    )
    scene = {
        "id": "scene_without_location_seed",
        "location_id": "loc_legacy",
        "shots": [],
    }

    first = engine_two_chars.enhance_shot_prompt(
        {"characters_in_frame": [], "prompt": "p"},
        scene,
        None,
        0,
    )
    second = engine_two_chars.enhance_shot_prompt(
        {"characters_in_frame": [], "prompt": "p"},
        scene,
        None,
        0,
    )

    expected = _stable_scene_seed(scene["id"])
    assert first["continuity_config"]["scene_seed"] == expected
    assert second["continuity_config"]["scene_seed"] == expected
