"""Tests for cinema.shots.strategy — IdentityStrategy promise types (P1-1, spec §3d).

Tasks 5 and 6 will extend this file with router (_resolve_identity_strategy) tests.
"""
from cinema.shots.strategy import (
    IdentityStrategy, CharIdentitySpec,
    PRIMARY_ONLY, KONTEXT_MULTI_CHAR, MAX_TIER_PRIMARY_ONLY, NO_IDENTITY_ASSET,
)


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
