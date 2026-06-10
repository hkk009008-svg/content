"""Tests for cinema.shots.strategy — IdentityStrategy promise types (P1-1, spec §3d).

Tasks 5 and 6 will extend this file with router (_resolve_identity_strategy) tests.
"""
from cinema.shots.strategy import (
    IdentityStrategy, CharIdentitySpec,
    PRIMARY_ONLY, KONTEXT_MULTI_CHAR, MAX_TIER_PRIMARY_ONLY, NO_IDENTITY_ASSET,
)
from cinema.shots.controller import _resolve_identity_strategy

SETTINGS_NO_LORA = {"quality_tier": "production"}
CC_TWO_REGISTERED = {
    "primary_reference": "/r/a.jpg", "identity_anchor": "anchor a",
    "secondary_chars": [{"char_id": "char_b", "reference": "/r/b.jpg",
                         "multi_angle_refs": ["/r/b1.jpg"],
                         "identity_anchor": "anchor b"}],
}
CC_PRIMARY_ONLY = {"primary_reference": "/r/a.jpg", "identity_anchor": "anchor a",
                   "secondary_chars": []}


def _shot(chars, primary=""):
    return {"characters_in_frame": chars, "primary_character": primary}


def test_single_char_with_ref_is_primary_only_and_matches_todays_bundle():
    s = _resolve_identity_strategy(
        _shot(["char_a"]), "production",
        {"char_lora_paths": {"char_a": "/l/a.safetensors"},
         "char_lora_strengths": {"char_a": 0.55}},
        CC_PRIMARY_ONLY,
    )
    assert s.mechanism_tag == "PRIMARY_ONLY"
    # zero-regression invariant: identical to today's controller.py:544-549 derivation
    assert s.primary_char_id == "char_a"
    assert s.char_lora_path == "/l/a.safetensors"
    assert s.char_lora_strength == 0.55
    assert [c.char_id for c in s.conditioned_chars] == ["char_a"]
    assert s.unconditioned_chars == []


def test_two_char_production_with_refs_is_kontext_multi():
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "production",
                                   SETTINGS_NO_LORA, CC_TWO_REGISTERED)
    assert s.mechanism_tag == "KONTEXT_MULTI_CHAR"
    assert [c.char_id for c in s.conditioned_chars] == ["char_a", "char_b"]
    # V-5: the router must carry the secondary's angle refs into the spec —
    # they feed the slot allocator downstream.
    assert s.conditioned_chars[1].multi_angle_refs == ("/r/b1.jpg",)


def test_two_char_max_tier_is_max_primary_only_with_secondary_unconditioned():
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "max",
                                   SETTINGS_NO_LORA, CC_TWO_REGISTERED)
    assert s.mechanism_tag == "MAX_TIER_PRIMARY_ONLY"
    assert [c.char_id for c in s.conditioned_chars] == ["char_a"]
    assert s.unconditioned_chars == ["char_b"]


def test_secondary_without_ref_is_unconditioned():
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "production",
                                   SETTINGS_NO_LORA, CC_PRIMARY_ONLY)
    assert s.mechanism_tag == "PRIMARY_ONLY"
    assert s.unconditioned_chars == ["char_b"]


def test_kontext_secondary_cap_is_two():
    cc = dict(CC_TWO_REGISTERED)
    cc["secondary_chars"] = [
        {"char_id": f"char_{i}", "reference": f"/r/{i}.jpg",
         "multi_angle_refs": [], "identity_anchor": ""} for i in "bcd"
    ]
    s = _resolve_identity_strategy(_shot(["char_a", "char_b", "char_c", "char_d"]),
                                   "production", SETTINGS_NO_LORA, cc)
    assert len(s.conditioned_chars) == 3          # primary + 2 (Kontext-tier cap)
    assert s.unconditioned_chars == ["char_d"]


def test_no_chars_or_no_primary_ref_is_no_identity_asset():
    s = _resolve_identity_strategy(_shot([]), "production", SETTINGS_NO_LORA,
                                   {"primary_reference": None, "secondary_chars": []})
    assert s.mechanism_tag == "NO_IDENTITY_ASSET"
    assert s.conditioned_chars == []


def test_to_metadata_dict_is_json_safe_and_complete():
    s = IdentityStrategy(
        mechanism_tag=KONTEXT_MULTI_CHAR,
        primary_char_id="char_a",
        char_lora_path=None,
        char_lora_strength=None,
        conditioned_chars=[
            CharIdentitySpec(char_id="char_a", reference="/r/a.jpg",
                             identity_anchor="anchor a", fidelity="reference"),
            CharIdentitySpec(char_id="char_b", reference="/r/b.jpg",
                             identity_anchor="anchor b", fidelity="reference",
                             multi_angle_refs=("/r/b1.jpg",)),
        ],
        unconditioned_chars=["char_c"],
    )
    import json
    md = s.to_metadata_dict()
    json.dumps(md)  # must not raise
    assert md["mechanism_tag"] == "KONTEXT_MULTI_CHAR"
    assert [c["char_id"] for c in md["conditioned_chars"]] == ["char_a", "char_b"]
    assert md["unconditioned_chars"] == ["char_c"]
    # V-5 pin: multi_angle_refs must survive the to_dict chain — Task 7's
    # allocator reads it off these dicts via Task 6's kwarg; without it,
    # secondaries can never fill their allocated slots.
    assert md["conditioned_chars"][1]["multi_angle_refs"] == ["/r/b1.jpg"]
