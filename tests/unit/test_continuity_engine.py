"""Provider-neutral continuity reference and stable-seed tests."""

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from continuity_engine import ContinuityEngine
from domain.continuity_engine import _stable_scene_seed


def _make_engine(char_a_ref="/ref/char_a.jpg", char_b_ref="/ref/char_b.jpg"):
    project = {
        "id": "proj_test",
        "characters": [
            {"id": "char_a", "name": "Alice"},
            {"id": "char_b", "name": "Bob"},
        ],
        "global_settings": {},
    }
    with (
        mock.patch(
            "domain.project_manager.get_project_dir",
            return_value="/tmp/proj_test",
        ),
        mock.patch(
            "domain.continuity_engine.get_character_embedding",
            return_value=None,
        ),
        mock.patch("identity.make_validator", return_value=mock.MagicMock()),
    ):
        engine = ContinuityEngine(project)

    references = {"char_a": char_a_ref, "char_b": char_b_ref}
    engine.character_tracker.get_reference_image = mock.MagicMock(
        side_effect=lambda character_id: references.get(character_id)
    )
    engine.character_tracker.get_multi_angle_refs = mock.MagicMock(
        side_effect=lambda character_id: [f"/angles/{character_id}-profile.jpg"]
    )
    return engine


@pytest.fixture
def engine_two_chars():
    return _make_engine()


def test_primary_and_secondary_reference_assets_are_explicit(engine_two_chars):
    enhanced = engine_two_chars.enhance_shot_prompt(
        {
            "characters_in_frame": ["char_a", "char_b"],
            "prompt": "The characters meet",
        },
        {"id": "scene_1", "shots": []},
    )
    config = enhanced["continuity_config"]

    assert config["primary_character"] == "char_a"
    assert config["primary_reference"] == "/ref/char_a.jpg"
    # The canonical now LEADS the video reference set. It previously did not
    # appear in it at all: phase_c_ffmpeg.py iterates `multi_angle_refs[:N]`
    # with no prepend and uploads `valid_refs[0]` as Kling's frontal image, so
    # the frontal slot was filled by whatever angle happened to come first.
    assert config["multi_angle_refs"] == [
        "/ref/char_a.jpg",
        "/angles/char_a-profile.jpg",
    ]
    assert config["secondary_chars"] == [
        {
            "char_id": "char_b",
            "reference": "/ref/char_b.jpg",
            "multi_angle_refs": [
                "/ref/char_b.jpg",
                "/angles/char_b-profile.jpg",
            ],
            "identity_anchor": "Bob",
        }
    ]
    assert "approved reference identity" in enhanced["prompt"]


def test_unregistered_secondary_character_is_not_claimed():
    engine = _make_engine(char_b_ref=None)
    enhanced = engine.enhance_shot_prompt(
        {
            "characters_in_frame": ["char_a", "char_b"],
            "prompt": "The characters meet",
        },
        {"id": "scene_1", "shots": []},
    )
    assert enhanced["continuity_config"]["secondary_chars"] == []


def test_only_existing_approved_reference_is_forwarded(engine_two_chars, tmp_path):
    approved = tmp_path / "approved.png"
    approved.write_bytes(b"approved-reference")

    with_reference = engine_two_chars.enhance_shot_prompt(
        {"characters_in_frame": [], "prompt": "An empty room"},
        {"id": "scene_1", "shots": []},
        continuity_reference_path=str(approved),
    )
    missing_reference = engine_two_chars.enhance_shot_prompt(
        {"characters_in_frame": [], "prompt": "An empty room"},
        {"id": "scene_1", "shots": []},
        continuity_reference_path=str(tmp_path / "missing.png"),
    )

    assert with_reference["continuity_config"]["continuity_reference"] == str(
        approved
    )
    assert missing_reference["continuity_config"]["continuity_reference"] is None


def test_mutable_img2img_controls_are_absent(engine_two_chars):
    enhanced = engine_two_chars.enhance_shot_prompt(
        {"characters_in_frame": [], "prompt": "An empty room"},
        {"id": "scene_1", "shots": []},
    )
    config = enhanced["continuity_config"]
    assert "init_image" not in config
    assert "use_img2img" not in config
    assert "denoise_strength" not in config


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
    assert _scene_seed_from_subprocess(
        "scene_cross_process", 1
    ) == _scene_seed_from_subprocess("scene_cross_process", 987654)


@pytest.mark.parametrize("scene_id", ["", "scene_1", "장면_마지막"])
def test_stable_scene_seed_is_a_31_bit_integer(scene_id):
    seed = _stable_scene_seed(scene_id)
    assert type(seed) is int
    assert 0 <= seed <= 0x7FFFFFFF


def test_stable_scene_seed_known_sha256_vector():
    assert _stable_scene_seed("scene_é") == 2_007_738_919


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
        {
            "id": "scene_with_location",
            "location_id": "loc_a",
            "shots": [],
        },
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
    enhanced = engine_two_chars.enhance_shot_prompt(
        {"characters_in_frame": [], "prompt": "p"},
        scene,
    )
    assert enhanced["continuity_config"]["scene_seed"] == _stable_scene_seed(
        scene["id"]
    )


# ---------------------------------------------------------------------------
# canonical_first — slot 0 carries a semantic role downstream
# ---------------------------------------------------------------------------

def test_canonical_leads_the_reference_set() -> None:
    """Slot 0 is Kling's FRONTAL image, and nothing else establishes it.

    `phase_c_ffmpeg.py` iterates `multi_angle_refs[:N]` with no canonical
    prepended, then uploads `valid_refs[0]` as `frontal_image_url`. Before this
    normalisation slot 0 was whatever the character record happened to list
    first — on this project a left profile, so Kling was told a profile was the
    frontal view.
    """

    from domain.continuity_engine import canonical_first

    assert canonical_first("canon.jpg", ["profile.jpg", "3q.jpg"]) == [
        "canon.jpg", "profile.jpg", "3q.jpg",
    ]


def test_canonical_first_is_idempotent_and_never_duplicates() -> None:
    """A record already ordered canonical-first must be left alone.

    The character record for this project lists the canonical at slot 0. If
    this helper appended rather than deduplicated, that record would spend two
    of a provider's four slots on the same image.
    """

    from domain.continuity_engine import canonical_first

    already = ["canon.jpg", "profile.jpg"]
    assert canonical_first("canon.jpg", already) == already
    assert canonical_first("canon.jpg", ["profile.jpg", "canon.jpg", "3q.jpg"]) == [
        "canon.jpg", "profile.jpg", "3q.jpg",
    ]


def test_canonical_first_tolerates_a_missing_canonical_and_empty_entries() -> None:
    """A character with no canonical still yields a usable ordered set."""

    from domain.continuity_engine import canonical_first

    assert canonical_first(None, ["profile.jpg"]) == ["profile.jpg"]
    assert canonical_first("", ["profile.jpg"]) == ["profile.jpg"]
    assert canonical_first("canon.jpg", ["", "profile.jpg", None]) == [
        "canon.jpg", "profile.jpg",
    ]


def test_enhanced_shot_puts_the_canonical_at_slot_zero() -> None:
    """End to end: a record listing a profile first still yields canonical-first."""

    from domain.continuity_engine import canonical_first

    # The record's own order, as this project's looked before it was rewritten.
    record_order = ["/ref/left_profile.jpg", "/ref/three_quarter.jpg"]
    ordered = canonical_first("/ref/canonical.jpg", record_order)

    assert ordered[0] == "/ref/canonical.jpg"
    # And the coverage that follows it is preserved, not reshuffled.
    assert ordered[1:] == record_order
