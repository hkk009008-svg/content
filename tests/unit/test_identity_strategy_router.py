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


@pytest.mark.parametrize(
    "backend",
    ["gemini_multiref", "local_flux2_klein"],
)
def test_single_character_uses_provider_neutral_primary_reference(backend):
    strategy = _resolve_identity_strategy(
        _shot(["char_a"]),
        {"identity_backend": backend},
        _context(multi_angle_refs=("/refs/a-profile.jpg",)),
    )
    assert strategy.mechanism_tag == REFERENCE_PRIMARY_ONLY
    assert strategy.primary_char_id == "char_a"
    assert strategy.unconditioned_chars == []
    assert strategy.conditioned_chars == [
        CharIdentitySpec(
            char_id="char_a",
            reference="/refs/a.jpg",
            identity_anchor="character a",
            fidelity="reference",
            multi_angle_refs=("/refs/a-profile.jpg",),
        )
    ]


def test_multi_character_strategy_preserves_reference_provenance():
    strategy = _resolve_identity_strategy(
        _shot(["char_a", "char_1", "char_unregistered"]),
        {"identity_backend": "local_flux2_klein"},
        _context(secondary=[_secondary(1)]),
    )
    assert strategy.mechanism_tag == REFERENCE_MULTI_CHAR
    assert [item.char_id for item in strategy.conditioned_chars] == [
        "char_a",
        "char_1",
    ]
    assert strategy.secondary_specs[0].multi_angle_refs == (
        "/refs/1-profile.jpg",
    )
    assert strategy.unconditioned_chars == ["char_unregistered"]


def test_gemini_and_local_caps_are_explicit():
    secondaries = [_secondary(index) for index in range(1, 15)]
    in_frame = ["char_a", *[item["char_id"] for item in secondaries]]

    gemini = _resolve_identity_strategy(
        _shot(in_frame),
        {"identity_backend": "gemini_multiref"},
        _context(secondary=secondaries),
    )
    local = _resolve_identity_strategy(
        _shot(in_frame),
        {"identity_backend": "local_flux2_klein"},
        _context(secondary=secondaries),
    )

    assert len(gemini.conditioned_chars) == GEMINI_MULTIREF_MAX_REFS
    assert len(local.conditioned_chars) == 10
    assert gemini.mechanism_tag == local.mechanism_tag == REFERENCE_MULTI_CHAR
    assert len(gemini.unconditioned_chars) == len(in_frame) - GEMINI_MULTIREF_MAX_REFS
    assert len(local.unconditioned_chars) == len(in_frame) - 10


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
