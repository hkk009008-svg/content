"""Final-review M-1: the CineDecompose shot-decomposition prompt's R4 aspect
descriptor must be orientation-aware. Before the fix it hardcoded "widescreen",
so a 9:16 project produced the self-contradictory instruction "9:16 widescreen"
to gpt-4o, biasing shot framing horizontal for a vertical deliverable. These
pin that a portrait project is described as vertical, and that 16:9 is unchanged.
"""
from domain.scene_decomposer import _build_cinedecompose_system_prompt


def _prompt(aspect):
    return _build_cinedecompose_system_prompt(
        target_shots=3,
        char_descriptions=[],
        loc_description="a room",
        loc_lighting="soft",
        loc_time="day",
        loc_weather="clear",
        style_ctx="",
        research_ctx="",
        global_settings=({"aspect_ratio": aspect} if aspect else {}),
    )


def test_portrait_prompt_says_vertical_not_widescreen():
    p = _prompt("9:16")
    assert "9:16 vertical (portrait)" in p
    assert "9:16 widescreen" not in p


def test_landscape_prompt_still_says_widescreen():
    # 16:9 behavior is byte-identical to before the fix.
    p = _prompt("16:9")
    assert "16:9 widescreen" in p


def test_default_aspect_is_widescreen():
    # No aspect_ratio key → default 16:9 → widescreen.
    p = _prompt(None)
    assert "16:9 widescreen" in p
