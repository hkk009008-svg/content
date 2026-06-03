"""
tests/unit/test_style_director.py — Characterization tests for llm/style_director.py.

These tests LOCK IN EXISTING behavior. They do NOT assert idealized behavior.
Where candidate bugs are present, the ACTUAL behavior is asserted and annotated.

Offline only — no network, no LLM, no real API keys required.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PHOTOREALISM_LITERAL = (
    "Visible skin pores with subsurface scattering, shallow depth of field "
    "f/1.4-2.8 with circular bokeh, natural film grain ISO 400, micro-detail "
    "in fabric weave and material texture, volumetric atmospheric lighting, "
    "no AI artifacts, no smooth plastic skin, no over-saturated colors"
)

_ALL_7_KEYS = {
    "director_vision",
    "cinematography_rules",
    "color_grading_palette",
    "lighting_rules",
    "sound_design",
    "photorealism_rules",
    "composition_rules",
}


def _fake_settings(*, openai_api_key: str = "", tavily_api_key: str = ""):
    return SimpleNamespace(openai_api_key=openai_api_key, tavily_api_key=tavily_api_key)


# ---------------------------------------------------------------------------
# Test 1 — no openai_api_key → returns _default_style_rules immediately
# ---------------------------------------------------------------------------

def test_no_openai_key_returns_default():
    """No API key → immediate _default_style_rules, all 7 keys present."""
    fake = _fake_settings(openai_api_key="")
    with patch("llm.style_director.settings", new=fake):
        from llm.style_director import generate_style_rules
        result = generate_style_rules("TestFilm")

    assert set(result.keys()) == _ALL_7_KEYS
    assert result["photorealism_rules"] == PHOTOREALISM_LITERAL


# ---------------------------------------------------------------------------
# Test 2 — _default_style_rules mood → palette mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mood,expected_fragment", [
    ("melancholic", "Desaturated cool tones"),
    ("tense", "High contrast"),
    ("hopeful", "Warm golden tones"),
    ("dark", "Low-key lighting"),
    ("cinematic", "Balanced contrast"),
    ("unknown_mood", "Balanced contrast"),  # unknown → "cinematic" fallback
])
def test_default_mood_palettes(mood, expected_fragment):
    from llm.style_director import _default_style_rules
    result = _default_style_rules(mood, "", "suspense")
    assert expected_fragment in result["color_grading_palette"]


def test_default_color_palette_override():
    """Explicit color_palette arg overrides mood palette."""
    from llm.style_director import _default_style_rules
    result = _default_style_rules("cinematic", "golden hour orange", "uplifting")
    assert result["color_grading_palette"] == "golden hour orange"


# ---------------------------------------------------------------------------
# Test 3 — LLM success: well-formed JSON returned as-is
# ---------------------------------------------------------------------------

def test_llm_success_returns_parsed_dict():
    """run_with_tools returns well-formed 7-key JSON → parsed dict returned as-is."""
    llm_payload = {k: f"value_{k}" for k in _ALL_7_KEYS}
    raw_json = json.dumps(llm_payload)

    fake = _fake_settings(openai_api_key="sk-fake")
    mock_client = MagicMock()

    with (
        patch("llm.style_director.settings", new=fake),
        patch("openai.OpenAI", return_value=mock_client),
        patch("research_engine.research_cinematography", return_value=""),
        patch("web_research.run_with_tools", return_value=raw_json),
    ):
        from llm.style_director import generate_style_rules
        result = generate_style_rules("TestFilm")

    assert result == llm_payload


# ---------------------------------------------------------------------------
# Test 4 — LLM returns malformed JSON → json.loads raises → _default_style_rules
# ---------------------------------------------------------------------------

def test_llm_malformed_json_falls_back_to_default():
    """run_with_tools returns 'INVALID' → json.loads raises → fallback to _default_style_rules."""
    fake = _fake_settings(openai_api_key="sk-fake")
    mock_client = MagicMock()

    with (
        patch("llm.style_director.settings", new=fake),
        patch("openai.OpenAI", return_value=mock_client),
        patch("research_engine.research_cinematography", return_value=""),
        patch("web_research.run_with_tools", return_value="INVALID"),
    ):
        from llm.style_director import generate_style_rules
        result = generate_style_rules("TestFilm", mood="tense")

    assert set(result.keys()) == _ALL_7_KEYS
    assert result["photorealism_rules"] == PHOTOREALISM_LITERAL


# ---------------------------------------------------------------------------
# Test 5 — LLM raises → _default_style_rules fallback
# ---------------------------------------------------------------------------

def test_llm_raises_falls_back_to_default():
    """run_with_tools raises RuntimeError → exception caught → fallback."""
    fake = _fake_settings(openai_api_key="sk-fake")
    mock_client = MagicMock()

    with (
        patch("llm.style_director.settings", new=fake),
        patch("openai.OpenAI", return_value=mock_client),
        patch("research_engine.research_cinematography", return_value=""),
        patch("web_research.run_with_tools", side_effect=RuntimeError("boom")),
    ):
        from llm.style_director import generate_style_rules
        result = generate_style_rules("TestFilm", mood="dark")

    assert set(result.keys()) == _ALL_7_KEYS
    assert result["photorealism_rules"] == PHOTOREALISM_LITERAL


# ---------------------------------------------------------------------------
# Test 6 — style_rules_to_prompt_suffix: all keys present → full suffix
# ---------------------------------------------------------------------------

def test_suffix_all_keys_present():
    """Full style dict → suffix contains Color grading, Lighting, photorealism literal, composition.

    DIVERGENCE FROM DISPATCH MAP: the map said composition_rules gets a "composition: " label.
    Actual code (line 191-192) appends the raw value with NO label — same shape as photorealism_rules.
    Test asserts ACTUAL behavior.
    """
    from llm.style_director import style_rules_to_prompt_suffix
    rules = {
        "color_grading_palette": "warm tones",
        "lighting_rules": "soft key light",
        "photorealism_rules": PHOTOREALISM_LITERAL,
        "composition_rules": "rule of thirds",
    }
    suffix = style_rules_to_prompt_suffix(rules)

    assert "Color grading: warm tones" in suffix
    assert "Lighting: soft key light" in suffix
    assert PHOTOREALISM_LITERAL in suffix
    # DIVERGENCE: no "composition: " label — value injected verbatim (same as photorealism_rules)
    assert "rule of thirds" in suffix
    assert "composition: rule of thirds" not in suffix


# ---------------------------------------------------------------------------
# Test 7 — suffix empty dict → ""
# ---------------------------------------------------------------------------

def test_suffix_empty_dict():
    from llm.style_director import style_rules_to_prompt_suffix
    assert style_rules_to_prompt_suffix({}) == ""


# ---------------------------------------------------------------------------
# Test 8 — photorealism injected verbatim without a label
# ---------------------------------------------------------------------------

def test_suffix_photorealism_injected_without_label():
    """photorealism_rules value is appended with NO 'Photorealism:' label."""
    from llm.style_director import style_rules_to_prompt_suffix
    rules = {"photorealism_rules": PHOTOREALISM_LITERAL}
    suffix = style_rules_to_prompt_suffix(rules)
    # Value is present verbatim
    assert PHOTOREALISM_LITERAL in suffix
    # No label was prepended
    assert "Photorealism:" not in suffix
    assert "photorealism_rules:" not in suffix


# ---------------------------------------------------------------------------
# Test 9 — _to_str dict → "k: v"
# ---------------------------------------------------------------------------

def test_to_str_dict():
    from llm.style_director import _to_str
    result = _to_str({"key1": "val1", "key2": "val2"})
    assert result == "key1: val1, key2: val2"


# ---------------------------------------------------------------------------
# Test 10 — _to_str list → "a, b"
# ---------------------------------------------------------------------------

def test_to_str_list():
    from llm.style_director import _to_str
    assert _to_str(["alpha", "beta"]) == "alpha, beta"


def test_to_str_str_identity():
    from llm.style_director import _to_str
    assert _to_str("hello") == "hello"


def test_to_str_other():
    from llm.style_director import _to_str
    assert _to_str(42) == "42"


# ---------------------------------------------------------------------------
# Test 11 — _research_aesthetic: no tavily_api_key → returns ""
# ---------------------------------------------------------------------------

def test_research_aesthetic_no_tavily_key():
    """_research_aesthetic returns '' immediately when tavily_api_key is absent."""
    fake = _fake_settings(tavily_api_key="")
    with patch("llm.style_director.settings", new=fake):
        from llm.style_director import _research_aesthetic
        result = _research_aesthetic("Blade Runner 2049")
    assert result == ""


# ---------------------------------------------------------------------------
# Test 12 — use_web_research=False → _research_aesthetic NOT called
# ---------------------------------------------------------------------------

def test_use_web_research_false_does_not_call_research_aesthetic():
    """_research_aesthetic should NOT be called when use_web_research=False."""
    fake = _fake_settings(openai_api_key="sk-fake", tavily_api_key="tv-fake")
    mock_client = MagicMock()
    llm_payload = {k: f"v_{k}" for k in _ALL_7_KEYS}

    with (
        patch("llm.style_director.settings", new=fake),
        patch("openai.OpenAI", return_value=mock_client),
        patch("research_engine.research_cinematography", return_value=""),
        patch("web_research.run_with_tools", return_value=json.dumps(llm_payload)),
        patch("llm.style_director._research_aesthetic") as mock_ra,
    ):
        from llm.style_director import generate_style_rules
        generate_style_rules(
            "TestFilm",
            reference_films="Blade Runner",
            use_web_research=False,
        )

    assert mock_ra.call_count == 0


# ---------------------------------------------------------------------------
# FIX G1 — research_cinematography gated by use_web_research
# ---------------------------------------------------------------------------

def test_research_honors_use_web_research_false():
    """
    FIX (G1): research_cinematography must NOT be called when use_web_research=False.
    Both research calls (research_cinematography and _research_aesthetic) must be
    consistently gated behind the use_web_research flag.
    """
    fake = _fake_settings(openai_api_key="sk-fake")
    mock_client = MagicMock()
    llm_payload = {k: f"v_{k}" for k in _ALL_7_KEYS}

    with (
        patch("llm.style_director.settings", new=fake),
        patch("openai.OpenAI", return_value=mock_client),
        patch("research_engine.research_cinematography", return_value="") as mock_rc,
        patch("web_research.run_with_tools", return_value=json.dumps(llm_payload)),
    ):
        from llm.style_director import generate_style_rules
        generate_style_rules("TestFilm", use_web_research=False)

    # FIX (G1): research_cinematography NOT called when use_web_research=False
    assert mock_rc.call_count == 0


def test_research_default_is_true():
    """
    FIX (G1): use_web_research default must be True — research on by default.
    """
    import inspect
    from llm.style_director import generate_style_rules
    assert inspect.signature(generate_style_rules).parameters["use_web_research"].default is True


# ---------------------------------------------------------------------------
# G4 FIX — missing keys back-filled from defaults so photorealism_rules can't vanish
# ---------------------------------------------------------------------------

def test_g4_missing_photorealism_rules_backfilled():
    """
    FIX (G4): When run_with_tools returns valid JSON that is MISSING
    'photorealism_rules', generate_style_rules must back-fill it from
    _default_style_rules so the key is always present and the photorealism
    formula is injected into every shot's prompt.

    The fix merges defaults UNDER the LLM output (LLM values win on present keys;
    absent keys are back-filled). This is purely additive — callers that receive
    all 7 keys see no change; callers that relied on a partial dict now get the
    missing keys silently back-filled with a ⚠️ warning.
    """
    partial_payload = {k: f"v_{k}" for k in _ALL_7_KEYS - {"photorealism_rules"}}
    assert "photorealism_rules" not in partial_payload

    fake = _fake_settings(openai_api_key="sk-fake")
    mock_client = MagicMock()

    with (
        patch("llm.style_director.settings", new=fake),
        patch("openai.OpenAI", return_value=mock_client),
        patch("research_engine.research_cinematography", return_value=""),
        patch("web_research.run_with_tools", return_value=json.dumps(partial_payload)),
    ):
        from llm.style_director import generate_style_rules
        result = generate_style_rules("TestFilm")

    # FIX (G4): missing key back-filled — photorealism_rules is now present
    assert "photorealism_rules" in result

    # Downstream consequence: style_rules_to_prompt_suffix now injects the formula
    from llm.style_director import style_rules_to_prompt_suffix
    suffix = style_rules_to_prompt_suffix(result)
    assert PHOTOREALISM_LITERAL in suffix  # photorealism formula present


# ---------------------------------------------------------------------------
# FIX G3 — openai.OpenAI constructed INSIDE the try block for fallback
# ---------------------------------------------------------------------------

def test_openai_construction_failure_falls_back_to_defaults(monkeypatch):
    """
    FIX (G3): If openai.OpenAI() construction raises, the exception must be caught
    by the try/except that returns _default_style_rules — not propagate uncaught.
    Moving client construction inside the try block closes this gap.
    """
    import openai as _openai_module

    def _raise(*args, **kwargs):
        raise RuntimeError("OpenAI client construction failed")

    fake = _fake_settings(openai_api_key="sk-fake")
    monkeypatch.setattr("llm.style_director.settings", fake)
    monkeypatch.setattr(_openai_module, "OpenAI", _raise)

    from llm.style_director import generate_style_rules
    rules = generate_style_rules("TestFilm")

    # FIX (G3): construction failure caught → falls back to _default_style_rules
    assert set(rules.keys()) == _ALL_7_KEYS
    assert rules["photorealism_rules"] == PHOTOREALISM_LITERAL


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

def test_default_sound_design_uses_music_mood():
    from llm.style_director import _default_style_rules
    result = _default_style_rules("cinematic", "", "cyberpunk")
    assert "cyberpunk" in result["sound_design"]


def test_suffix_partial_keys_only_present_keys_included():
    """Only present/truthy keys contribute to the suffix.

    DIVERGENCE FROM DISPATCH MAP: composition_rules has NO "composition: " label.
    Actual code appends the raw value verbatim (same as photorealism_rules).
    """
    from llm.style_director import style_rules_to_prompt_suffix
    rules = {
        "color_grading_palette": "cool tones",
        # lighting_rules absent → no "Lighting:" segment
        # photorealism_rules absent → no photorealism segment
        "composition_rules": "leading lines",
    }
    suffix = style_rules_to_prompt_suffix(rules)
    assert "Color grading: cool tones" in suffix
    # DIVERGENCE: composition_rules appended verbatim, no "composition: " label
    assert "leading lines" in suffix
    assert "composition: leading lines" not in suffix
    assert "Lighting:" not in suffix
    assert PHOTOREALISM_LITERAL not in suffix


def test_suffix_join_with_period():
    """Parts are joined with '. '."""
    from llm.style_director import style_rules_to_prompt_suffix
    rules = {
        "color_grading_palette": "A",
        "composition_rules": "B",
    }
    suffix = style_rules_to_prompt_suffix(rules)
    assert ". " in suffix


def test_to_str_empty_list():
    from llm.style_director import _to_str
    assert _to_str([]) == ""


def test_to_str_empty_dict():
    from llm.style_director import _to_str
    assert _to_str({}) == ""
