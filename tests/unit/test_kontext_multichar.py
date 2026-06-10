from phase_c_assembly import _allocate_ref_slots, _build_multichar_kontext_prompt


def test_two_char_allocation_3_2():
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/a/4.jpg"],
        secondary_chars=[{"char_id": "char_b", "reference": "/b/c.jpg",
                          "multi_angle_refs": ["/b/1.jpg", "/b/2.jpg"]}],
    )
    assert paths == ["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/b/c.jpg", "/b/1.jpg"]
    assert slot_map == {"primary": [1, 2, 3], "char_b": [4, 5]}


def test_three_char_allocation_3_2_1_and_six_cap():
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg"],
        secondary_chars=[
            {"char_id": "char_b", "reference": "/b/c.jpg",
             "multi_angle_refs": ["/b/1.jpg"]},
            {"char_id": "char_c", "reference": "/c/c.jpg",
             "multi_angle_refs": ["/c/1.jpg", "/c/2.jpg"]},
        ],
    )
    assert len(paths) == 6
    assert slot_map == {"primary": [1, 2, 3], "char_b": [4, 5], "char_c": [6]}


def test_thin_secondary_does_not_inflate_primary():
    """Slots are CONTIGUOUS and shares are FIXED (primary 3 / sec-1 2 / sec-2 1):
    a thin secondary leaves the cap unfilled rather than reordering slots."""
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/a/4.jpg", "/a/5.jpg"],
        secondary_chars=[{"char_id": "char_b", "reference": "/b/c.jpg",
                          "multi_angle_refs": []}],
    )
    assert slot_map["primary"] == [1, 2, 3]   # fixed at 3 when secondaries exist
    assert slot_map["char_b"] == [4]          # canonical only — nothing to fill with
    assert len(paths) == 4                    # cap is a ceiling, not a quota


def test_single_char_alone_keeps_all_six():
    paths, slot_map = _allocate_ref_slots(
        primary_refs=[f"/a/{i}.jpg" for i in range(8)], secondary_chars=[],
    )
    assert slot_map == {"primary": [1, 2, 3, 4, 5, 6]}
    assert len(paths) == 6


def test_multichar_prompt_addresses_each_slot():
    prompt = _build_multichar_kontext_prompt(
        {"SCENE": "a rooftop cafe", "ACTION": "talking", "OUTFIT": "",
         "SHOT": "Medium two-shot"},
        char_blocks=[(1, "a woman with auburn hair"), (4, "a man with a grey beard")],
    )
    assert "@Image1 is a woman with auburn hair" in prompt
    assert "@Image4 is a man with a grey beard" in prompt
    assert "Do NOT blend or average" in prompt
    assert "Do NOT transfer clothing" in prompt   # S1 wardrobe cross-bleed pin
    assert "CHANGE BACKGROUND: a rooftop cafe." in prompt
    assert prompt.count("PRESERVE IDENTITY") == 2
