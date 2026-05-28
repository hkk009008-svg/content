"""Tests for llm.prompt_optimizer — specifically the intent_notes parameter.

Covers:
(a) When intent_notes is non-empty, the text reaches the LLM user-prompt
    (verified via mock at the ensemble boundary).
(b) Empty/absent intent_notes leaves behavior unchanged (existing callers
    unaffected — no regression on existing call shapes).
(c) The fallback path (_fallback_optimize) handles intent_notes without
    error, and the notes are reflected in image_prompt when provided.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_ensemble_mock(json_spec: dict) -> MagicMock:
    """Build a mock ensemble whose competitive_generate returns a winner with
    winner_content equal to *json_spec* (dict, so the raw-is-dict branch fires).
    """
    result_mock = MagicMock()
    result_mock.winner_content = json_spec
    ensemble_mock = MagicMock()
    ensemble_mock.competitive_generate.return_value = result_mock
    return ensemble_mock


def _valid_spec() -> dict:
    """Minimal spec that passes _coerce_to_valid_keys without substitution."""
    return {
        "image_prompt": "a woman stands alone in an empty corridor",
        "video_prompt": "slow dolly-in",
        "purpose": "static_portrait",
        "shot_type": "portrait",
        "suggested_image_api": "FLUX_DEV",
        "suggested_video_api": "AUTO",
        "suggested_lipsync": None,
        "negative_constraints": "plastic skin",
        "identity_anchor": "Jane: dark hair, pale skin",
        "camera": "85mm f/1.4",
        "lighting": "cold rim light",
        "color_palette": "cold blue",
        "reasoning": "static portrait, character lead",
    }


# ---------------------------------------------------------------------------
# (a) intent_notes reaches the LLM user-prompt
# ---------------------------------------------------------------------------

def test_intent_notes_present_in_llm_user_prompt():
    """When intent_notes is non-empty, the prompt sent to the ensemble must
    include a DIRECTOR'S INTENT section with the exact notes text.
    """
    from llm.prompt_optimizer import optimize_shot_prompt

    notes = "emphasize isolation, cold tones"
    ensemble_mock = _minimal_ensemble_mock(_valid_spec())

    optimize_shot_prompt(
        user_input="a woman stands in a corridor",
        intent_notes=notes,
        ensemble=ensemble_mock,
    )

    # Retrieve the user_prompt passed to competitive_generate
    call_kwargs = ensemble_mock.competitive_generate.call_args
    user_prompt_arg = call_kwargs.kwargs.get("user_prompt") or call_kwargs.args[1] if call_kwargs.args else None
    # Fallback: try positional kwargs approach
    if user_prompt_arg is None:
        all_kwargs = call_kwargs[1] if call_kwargs[1] else {}
        user_prompt_arg = all_kwargs.get("user_prompt", "")

    assert notes in user_prompt_arg, (
        f"intent_notes text should appear in LLM user_prompt; got:\n{user_prompt_arg!r}"
    )
    assert "DIRECTOR'S INTENT" in user_prompt_arg, (
        "DIRECTOR'S INTENT section header should appear in LLM user_prompt"
    )


def test_intent_notes_section_ordering_in_user_prompt():
    """DIRECTOR'S INTENT section should appear between USER INTENT and SCENE CONTEXT."""
    from llm.prompt_optimizer import optimize_shot_prompt

    notes = "handheld camera, claustrophobic framing"
    ensemble_mock = _minimal_ensemble_mock(_valid_spec())

    optimize_shot_prompt(
        user_input="man in a phone booth",
        intent_notes=notes,
        scene_context="downtown alley scene",
        ensemble=ensemble_mock,
    )

    call_kwargs = ensemble_mock.competitive_generate.call_args
    user_prompt_arg = (call_kwargs.kwargs.get("user_prompt") or
                       (call_kwargs.args[1] if len(call_kwargs.args) > 1 else ""))

    pos_user_intent = user_prompt_arg.find("USER INTENT")
    pos_director_intent = user_prompt_arg.find("DIRECTOR'S INTENT")
    pos_scene_context = user_prompt_arg.find("SCENE CONTEXT")

    assert pos_user_intent < pos_director_intent < pos_scene_context, (
        "DIRECTOR'S INTENT must appear after USER INTENT and before SCENE CONTEXT; "
        f"positions: USER_INTENT={pos_user_intent}, DIRECTOR_INTENT={pos_director_intent}, "
        f"SCENE_CONTEXT={pos_scene_context}"
    )


# ---------------------------------------------------------------------------
# (b) Empty / absent intent_notes — no regression
# ---------------------------------------------------------------------------

def test_empty_intent_notes_omits_director_section():
    """Empty string (default) should NOT inject a DIRECTOR'S INTENT section."""
    from llm.prompt_optimizer import optimize_shot_prompt

    ensemble_mock = _minimal_ensemble_mock(_valid_spec())

    optimize_shot_prompt(
        user_input="a crowd at a concert",
        intent_notes="",          # explicit empty
        ensemble=ensemble_mock,
    )

    call_kwargs = ensemble_mock.competitive_generate.call_args
    user_prompt_arg = (call_kwargs.kwargs.get("user_prompt") or
                       (call_kwargs.args[1] if len(call_kwargs.args) > 1 else ""))

    assert "DIRECTOR'S INTENT" not in user_prompt_arg, (
        "Empty intent_notes must not inject DIRECTOR'S INTENT section"
    )


def test_absent_intent_notes_default_unaffected():
    """Callers that pass no intent_notes at all must get identical behaviour
    to callers that existed before this parameter was added.
    """
    from llm.prompt_optimizer import optimize_shot_prompt

    ensemble_mock = _minimal_ensemble_mock(_valid_spec())

    result = optimize_shot_prompt(
        user_input="sunset over the ocean",
        ensemble=ensemble_mock,
    )

    # The result must be a valid spec dict with the expected keys
    assert "image_prompt" in result
    assert "purpose" in result
    assert "shot_type" in result

    # Confirm the ensemble was called (LLM path, not error path)
    assert ensemble_mock.competitive_generate.called


def test_whitespace_only_intent_notes_omits_section():
    """Whitespace-only intent_notes should be treated the same as empty."""
    from llm.prompt_optimizer import optimize_shot_prompt

    ensemble_mock = _minimal_ensemble_mock(_valid_spec())

    optimize_shot_prompt(
        user_input="empty room",
        intent_notes="   \t\n  ",
        ensemble=ensemble_mock,
    )

    call_kwargs = ensemble_mock.competitive_generate.call_args
    user_prompt_arg = (call_kwargs.kwargs.get("user_prompt") or
                       (call_kwargs.args[1] if len(call_kwargs.args) > 1 else ""))

    assert "DIRECTOR'S INTENT" not in user_prompt_arg, (
        "Whitespace-only intent_notes must not inject DIRECTOR'S INTENT section"
    )


# ---------------------------------------------------------------------------
# (c) Fallback path handles intent_notes
# ---------------------------------------------------------------------------

def test_fallback_with_intent_notes_no_error():
    """_fallback_optimize with intent_notes must not raise."""
    from llm.prompt_optimizer import _fallback_optimize

    result = _fallback_optimize(
        user_input="detective in a rain-soaked alley",
        characters=[{"id": "c1", "name": "Det. Kim", "physical_traits": "tall, trench coat"}],
        location={"description": "alley", "lighting": "rain-slick reflections"},
        global_settings={"music_mood": "noir", "color_palette": "desaturated"},
        intent_notes="emphasize isolation, cold tones",
    )
    assert isinstance(result, dict)
    assert "image_prompt" in result


def test_fallback_intent_notes_reflected_in_image_prompt():
    """When intent_notes is non-empty, the fallback image_prompt must
    include the notes text (prepended as Director's intent prefix).
    """
    from llm.prompt_optimizer import _fallback_optimize

    notes = "emphasize isolation, cold tones"
    result = _fallback_optimize(
        user_input="detective in a rain-soaked alley",
        characters=[{"id": "c1", "name": "Det. Kim", "physical_traits": "tall, trench coat"}],
        location={"description": "dark alley", "lighting": "rain reflections"},
        global_settings={},
        intent_notes=notes,
    )
    assert notes in result["image_prompt"], (
        f"intent_notes should appear in fallback image_prompt; got:\n{result['image_prompt']!r}"
    )
    assert "Director's intent" in result["image_prompt"]


def test_fallback_empty_intent_notes_no_prefix():
    """Empty intent_notes must not inject a Director's intent prefix in fallback."""
    from llm.prompt_optimizer import _fallback_optimize

    result = _fallback_optimize(
        user_input="detective in a rain-soaked alley",
        characters=[],
        location={},
        global_settings={},
        intent_notes="",
    )
    assert "Director's intent" not in result["image_prompt"], (
        "Empty intent_notes must not insert Director's intent prefix in fallback"
    )


def test_fallback_product_shot_intent_notes_no_error():
    """Product shots in the fallback path must not error when intent_notes is set."""
    from llm.prompt_optimizer import _fallback_optimize

    result = _fallback_optimize(
        user_input="luxury watch on white marble",
        characters=[],
        location={},
        global_settings={},
        objects=[{"name": "Watch", "brand": "Lumex", "surface_type": "metallic", "material_traits": "stainless steel"}],
        primary_subject="object",
        intent_notes="show the dial detail, dramatic side lighting",
    )
    assert isinstance(result, dict)
    assert "image_prompt" in result
    # Product shot image_prompt comes from the product branch (no Director's intent prefix)
    # — intent_notes silently tolerated, no error
    assert result["purpose"] in ("product_hero", "product_in_scene", "product_reveal_motion")


# ---------------------------------------------------------------------------
# (a+b) LLM path: ensemble failure falls back with intent_notes propagated
# ---------------------------------------------------------------------------

def test_llm_failure_fallback_propagates_intent_notes(capsys):
    """If the ensemble.competitive_generate raises, the fallback path is called
    with intent_notes — the notes should still appear in image_prompt.
    """
    from llm.prompt_optimizer import optimize_shot_prompt

    failing_ensemble = MagicMock()
    failing_ensemble.competitive_generate.side_effect = RuntimeError("LLM timeout")

    notes = "slow zoom, melancholy"
    result = optimize_shot_prompt(
        user_input="a boy stares out the window",
        intent_notes=notes,
        ensemble=failing_ensemble,
    )

    assert isinstance(result, dict)
    assert "image_prompt" in result
    assert notes in result["image_prompt"], (
        "intent_notes must propagate through LLM-failure → fallback path"
    )
