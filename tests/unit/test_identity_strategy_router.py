import json

import pytest

from cinema.shots.controller import _resolve_identity_strategy
from cinema.shots.strategy import (
    NO_IDENTITY_ASSET,
    REFERENCE_MULTI_CHAR,
    REFERENCE_PRIMARY_ONLY,
    CharIdentitySpec,
    IdentityStrategy,
)
from gemini_image_native import GEMINI_MULTIREF_MAX_REFS


def _shot(characters, primary=""):
    return {
        "characters_in_frame": characters,
        "primary_character": primary,
    }


def _context(*, secondary=(), multi_angle_refs=()):
    return {
        "primary_reference": "/refs/a.jpg",
        "identity_anchor": "character a",
        "multi_angle_refs": list(multi_angle_refs),
        "secondary_chars": list(secondary),
    }


def _reference(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(name.encode("utf-8"))
    return str(path)


def _secondary(index):
    return {
        "char_id": f"char_{index}",
        "reference": f"/refs/{index}.jpg",
        "identity_anchor": f"character {index}",
        "multi_angle_refs": [f"/refs/{index}-profile.jpg"],
    }


def test_no_character_or_primary_reference_has_no_identity_asset():
    no_chars = _resolve_identity_strategy(
        _shot([]),
        {"identity_backend": "gemini_multiref"},
        _context(),
    )
    assert no_chars.mechanism_tag == NO_IDENTITY_ASSET
    assert no_chars.conditioned_chars == []

    no_ref = _resolve_identity_strategy(
        _shot(["char_a", "char_b"]),
        {"identity_backend": "local_flux2_klein"},
        {"primary_reference": None, "secondary_chars": []},
    )
    assert no_ref.mechanism_tag == NO_IDENTITY_ASSET
    assert no_ref.unconditioned_chars == ["char_a", "char_b"]


def test_local_missing_primary_does_not_promote_secondary_identity(tmp_path):
    secondary = _reference(tmp_path, "secondary.jpg")
    continuity = _reference(tmp_path, "continuity.jpg")

    strategy = _resolve_identity_strategy(
        _shot(["char_a", "char_b"], primary="char_a"),
        {"identity_backend": "local_flux2_klein"},
        {
            "primary_reference": str(tmp_path / "missing-primary.jpg"),
            "multi_angle_refs": [str(tmp_path / "missing-primary-angle.jpg")],
            "secondary_chars": [
                {"char_id": "char_b", "reference": secondary}
            ],
            "continuity_reference": continuity,
        },
    )

    assert strategy.mechanism_tag == NO_IDENTITY_ASSET
    assert strategy.conditioned_chars == []
    assert strategy.unconditioned_chars == ["char_a", "char_b"]
    assert strategy.flux2_reference_paths == (continuity,)
    assert strategy.flux2_continuity_reference == continuity


def test_local_primary_angle_can_supply_missing_canonical_reference(tmp_path):
    primary_angle = _reference(tmp_path, "primary-angle.jpg")

    strategy = _resolve_identity_strategy(
        _shot(["char_a"], primary="char_a"),
        {"identity_backend": "local_flux2_klein"},
        {
            "primary_reference": None,
            "multi_angle_refs": [primary_angle],
        },
    )

    assert strategy.mechanism_tag == REFERENCE_PRIMARY_ONLY
    assert strategy.conditioned_chars == [
        CharIdentitySpec(char_id="char_a", reference=primary_angle)
    ]
    assert strategy.flux2_reference_paths == (primary_angle,)


@pytest.mark.parametrize(
    "backend",
    ["gemini_multiref", "local_flux2_klein"],
)
def test_single_character_uses_provider_neutral_primary_reference(backend, tmp_path):
    context = _context(multi_angle_refs=("/refs/a-profile.jpg",))
    expected_reference = "/refs/a.jpg"
    expected_angle = "/refs/a-profile.jpg"
    if backend == "local_flux2_klein":
        expected_reference = _reference(tmp_path, "a.jpg")
        expected_angle = _reference(tmp_path, "a-profile.jpg")
        context.update(
            primary_reference=expected_reference,
            multi_angle_refs=[expected_angle],
        )
    strategy = _resolve_identity_strategy(
        _shot(["char_a"]),
        {"identity_backend": backend},
        context,
    )
    assert strategy.mechanism_tag == REFERENCE_PRIMARY_ONLY
    assert strategy.primary_char_id == "char_a"
    assert strategy.unconditioned_chars == []
    assert strategy.conditioned_chars == [
        CharIdentitySpec(
            char_id="char_a",
            reference=expected_reference,
            identity_anchor="character a",
            fidelity="reference",
            multi_angle_refs=(expected_angle,),
        )
    ]


def test_multi_character_strategy_preserves_reference_provenance(tmp_path):
    primary = _reference(tmp_path, "a.jpg")
    secondary = _reference(tmp_path, "1.jpg")
    secondary_angle = _reference(tmp_path, "1-profile.jpg")
    strategy = _resolve_identity_strategy(
        _shot(["char_a", "char_1", "char_unregistered"]),
        {"identity_backend": "local_flux2_klein"},
        {
            **_context(),
            "primary_reference": primary,
            "secondary_chars": [{
                **_secondary(1),
                "reference": secondary,
                "multi_angle_refs": [secondary_angle],
            }],
        },
    )
    assert strategy.mechanism_tag == REFERENCE_MULTI_CHAR
    assert [item.char_id for item in strategy.conditioned_chars] == [
        "char_a",
        "char_1",
    ]
    assert strategy.secondary_specs[0].multi_angle_refs == (
        secondary_angle,
    )
    assert strategy.unconditioned_chars == ["char_unregistered"]


def test_gemini_and_local_caps_are_explicit(tmp_path):
    secondaries = [_secondary(index) for index in range(1, 15)]
    in_frame = ["char_a", *[item["char_id"] for item in secondaries]]

    gemini = _resolve_identity_strategy(
        _shot(in_frame),
        {"identity_backend": "gemini_multiref"},
        _context(secondary=secondaries),
    )
    local_secondaries = []
    for index, item in enumerate(secondaries, 1):
        local_secondaries.append({
            **item,
            "reference": _reference(tmp_path, f"{index}.jpg"),
            "multi_angle_refs": [_reference(tmp_path, f"{index}-profile.jpg")],
        })
    local = _resolve_identity_strategy(
        _shot(in_frame),
        {"identity_backend": "local_flux2_klein"},
        {
            **_context(),
            "primary_reference": _reference(tmp_path, "a.jpg"),
            "secondary_chars": local_secondaries,
        },
    )

    assert len(gemini.conditioned_chars) == GEMINI_MULTIREF_MAX_REFS
    # Four IMAGE slots: primary canonical, secondary-1 canonical + angle,
    # then secondary-2 canonical. This is three conditioned characters, not
    # the old and incorrect four-character budget.
    assert len(local.conditioned_chars) == 3
    assert gemini.mechanism_tag == local.mechanism_tag == REFERENCE_MULTI_CHAR
    assert len(gemini.unconditioned_chars) == len(in_frame) - GEMINI_MULTIREF_MAX_REFS
    assert len(local.unconditioned_chars) == len(in_frame) - 3
    assert local.unconditioned_chars[0] == "char_3"


def test_local_allocation_deduplicates_and_ignores_missing_refs(tmp_path):
    primary = _reference(tmp_path, "primary.jpg")
    primary_angle = _reference(tmp_path, "primary-angle.jpg")
    secondary_angle = _reference(tmp_path, "secondary-angle.jpg")
    continuity = _reference(tmp_path, "continuity.jpg")

    strategy = _resolve_identity_strategy(
        _shot(["char_a", "char_b", "char_c"]),
        {"identity_backend": "local_flux2_klein"},
        {
            "primary_reference": primary,
            "identity_anchor": "character a",
            "multi_angle_refs": [str(tmp_path / "." / "primary.jpg"), primary_angle],
            "secondary_chars": [
                {
                    "char_id": "char_b",
                    "reference": str(tmp_path / "missing.jpg"),
                    "multi_angle_refs": [secondary_angle],
                },
                {
                    "char_id": "char_c",
                    "reference": str(tmp_path),
                    "multi_angle_refs": [],
                },
            ],
            "continuity_reference": continuity,
        },
    )

    assert strategy.flux2_reference_paths == (
        primary,
        primary_angle,
        secondary_angle,
        continuity,
    )
    assert [spec.char_id for spec in strategy.conditioned_chars] == [
        "char_a",
        "char_b",
    ]
    assert strategy.conditioned_chars[0].multi_angle_refs == (primary_angle,)
    assert strategy.conditioned_chars[1].reference == secondary_angle
    assert strategy.unconditioned_chars == ["char_c"]
    assert strategy.flux2_continuity_reference == continuity


def test_local_fifth_character_is_unconditioned_at_four_image_cap(tmp_path):
    character_ids = [f"char_{index}" for index in range(1, 6)]
    strategy = _resolve_identity_strategy(
        _shot(character_ids, primary="char_1"),
        {"identity_backend": "local_flux2_klein"},
        {
            "primary_reference": _reference(tmp_path, "char-1.jpg"),
            "secondary_chars": [
                {
                    "char_id": char_id,
                    "reference": _reference(tmp_path, f"{char_id}.jpg"),
                }
                for char_id in character_ids[1:]
            ],
        },
    )

    assert [spec.char_id for spec in strategy.conditioned_chars] == character_ids[:4]
    assert strategy.unconditioned_chars == ["char_5"]
    assert len(strategy.flux2_reference_paths) == 4


def test_metadata_is_json_safe_and_contains_no_retired_provider_controls():
    strategy = IdentityStrategy(
        mechanism_tag=REFERENCE_MULTI_CHAR,
        primary_char_id="char_a",
        conditioned_chars=[
            CharIdentitySpec(
                char_id="char_a",
                reference="/refs/a.jpg",
                identity_anchor="character a",
                multi_angle_refs=("/refs/a-profile.jpg",),
            )
        ],
        unconditioned_chars=["char_b"],
    )
    metadata = strategy.to_metadata_dict()
    assert json.loads(json.dumps(metadata)) == metadata
    assert "char_lora_path" not in metadata
    assert "char_lora_strength" not in metadata
