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

import json
from datetime import date
from unittest.mock import MagicMock

import pytest

from domain.provider_catalog import RuntimeSnapshot


PRE_SUNSET = date(2026, 9, 23)


def _fal_snapshot():
    return RuntimeSnapshot(
        credentials={"fal_key"},
        modules={"fal_client"},
    )


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


def _structured_prompt(prefix: str) -> str:
    return (
        f"[SHOT] {prefix}-shot "
        f"[SCENE] {prefix}-scene "
        f"[ACTION] {prefix}-action "
        f"[OUTFIT] {prefix}-outfit "
        f"[QUALITY] {prefix}-quality"
    )


def _valid_spec(image_prompt: str = "") -> dict:
    """Minimal spec that passes _coerce_to_valid_keys without substitution."""
    return {
        "image_prompt": image_prompt or _structured_prompt("optimizer"),
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
    """Product fallbacks retain intent notes in the structured image prompt."""
    from llm.prompt_optimizer import _fallback_optimize

    notes = "show the dial detail, dramatic side lighting"
    result = _fallback_optimize(
        user_input="luxury watch on white marble",
        characters=[],
        location={},
        global_settings={},
        objects=[{"name": "Watch", "brand": "Lumex", "surface_type": "metallic", "material_traits": "stainless steel"}],
        primary_subject="object",
        intent_notes=notes,
    )
    assert isinstance(result, dict)
    assert "image_prompt" in result
    assert notes in result["image_prompt"]
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


# ---------------------------------------------------------------------------
# Five-section image-prompt contract
# ---------------------------------------------------------------------------

def test_invalid_optimizer_prompt_preserves_every_structured_source_section():
    from llm.prompt_optimizer import optimize_shot_prompt
    from phase_c_assembly import _parse_structured_prompt

    source = _structured_prompt("source-sentinel")
    ensemble_mock = _minimal_ensemble_mock(
        _valid_spec(image_prompt="untagged optimizer prose"),
    )

    result = optimize_shot_prompt(
        user_input=source,
        ensemble=ensemble_mock,
    )

    assert result["image_prompt"] == source
    parsed = _parse_structured_prompt(result["image_prompt"])
    assert list(parsed) == ["SHOT", "SCENE", "ACTION", "OUTFIT", "QUALITY"]
    for tag in ("SHOT", "SCENE", "ACTION", "OUTFIT", "QUALITY"):
        assert f"source-sentinel-{tag.lower()}" == parsed[tag]


def test_valid_optimizer_structured_replacement_is_accepted():
    from llm.prompt_optimizer import optimize_shot_prompt

    source = _structured_prompt("source")
    replacement = _structured_prompt("replacement")
    ensemble_mock = _minimal_ensemble_mock(
        _valid_spec(image_prompt=replacement),
    )

    result = optimize_shot_prompt(
        user_input=source,
        ensemble=ensemble_mock,
    )

    assert result["image_prompt"] == replacement
    assert "source-" not in result["image_prompt"]


@pytest.mark.parametrize(
    "invalid_prompt",
    [
        "[SHOT] shot [SCENE] scene [ACTION] action [QUALITY] quality",
        (
            "[SHOT] shot [SCENE] scene [ACTION] action [OUTFIT] outfit "
            "[SHOT] duplicate [QUALITY] quality"
        ),
        (
            "[SHOT] shot [ACTION] action [SCENE] scene [OUTFIT] outfit "
            "[QUALITY] quality"
        ),
        (
            "[SHOT] shot [SCENE] scene [ACTION] action [OUTFIT]   "
            "[QUALITY] quality"
        ),
    ],
    ids=["missing", "duplicated", "out-of-order", "empty"],
)
def test_invalid_optimizer_section_shapes_are_rejected(invalid_prompt):
    from llm.prompt_optimizer import (
        _normalize_structured_image_prompt,
        optimize_shot_prompt,
    )

    source = _structured_prompt("original")
    ensemble_mock = _minimal_ensemble_mock(
        _valid_spec(image_prompt=invalid_prompt),
    )

    result = optimize_shot_prompt(
        user_input=source,
        ensemble=ensemble_mock,
    )

    assert _normalize_structured_image_prompt(invalid_prompt) is None
    assert result["image_prompt"] == source


def test_character_fallback_is_parseable_and_preserves_source_and_intent():
    from llm.prompt_optimizer import (
        _fallback_optimize,
        _normalize_structured_image_prompt,
    )
    from phase_c_assembly import _parse_structured_prompt

    source_detail = "detective wearing the crimson-coat-sentinel in the rain"
    intent_detail = "intent-sentinel: emphasize isolation"
    result = _fallback_optimize(
        user_input=source_detail,
        characters=[
            {
                "id": "c1",
                "name": "Detective",
                "physical_traits": "tall, weathered",
            },
        ],
        location={
            "description": "alley-sentinel",
            "lighting": "rain-reflection-sentinel",
        },
        global_settings={
            "music_mood": "noir-sentinel",
            "color_palette": "desaturated-sentinel",
        },
        intent_notes=intent_detail,
    )

    prompt = result["image_prompt"]
    assert _normalize_structured_image_prompt(prompt) == prompt
    parsed = _parse_structured_prompt(prompt)
    assert list(parsed) == ["SHOT", "SCENE", "ACTION", "OUTFIT", "QUALITY"]
    assert source_detail in parsed["ACTION"]
    assert intent_detail in parsed["ACTION"]
    assert "crimson-coat-sentinel" in parsed["OUTFIT"]
    assert "alley-sentinel" in parsed["SCENE"]
    assert all(parsed[tag].strip() for tag in parsed)


def test_product_fallback_is_parseable_and_preserves_product_detail():
    from llm.prompt_optimizer import (
        _fallback_optimize,
        _normalize_structured_image_prompt,
    )
    from phase_c_assembly import _parse_structured_prompt

    source_detail = "chronometer-sentinel on white marble"
    intent_detail = "intent-sentinel: reveal the sapphire crown"
    result = _fallback_optimize(
        user_input=source_detail,
        characters=[],
        location={
            "description": "studio-sentinel",
            "lighting": "controlled-light-sentinel",
        },
        global_settings={"color_palette": "cobalt-sentinel"},
        objects=[
            {
                "name": "Chronometer",
                "brand": "Lumex-sentinel",
                "surface_type": "metallic",
                "material_traits": "steel-sentinel",
                "texture_anchor": "sapphire-crown-sentinel",
            },
        ],
        primary_subject="object",
        intent_notes=intent_detail,
    )

    prompt = result["image_prompt"]
    assert _normalize_structured_image_prompt(prompt) == prompt
    parsed = _parse_structured_prompt(prompt)
    assert list(parsed) == ["SHOT", "SCENE", "ACTION", "OUTFIT", "QUALITY"]
    assert source_detail in parsed["ACTION"]
    assert intent_detail in parsed["ACTION"]
    assert "steel-sentinel" in parsed["ACTION"]
    assert "Lumex-sentinel" in parsed["OUTFIT"]
    assert "sapphire-crown-sentinel" in parsed["OUTFIT"]
    assert "controlled-light-sentinel" in parsed["SCENE"]
    assert all(parsed[tag].strip() for tag in parsed)


def test_optimizer_system_prompt_requires_exact_five_section_contract():
    from llm.prompt_optimizer import _OPTIMIZER_SYSTEM_PROMPT

    expected_structure = (
        "[SHOT] <framing and camera prose> "
        "[SCENE] <environment and lighting prose>\n"
        "   [ACTION] <subject action prose> "
        "[OUTFIT] <wardrobe or product styling prose>\n"
        "   [QUALITY] <render-quality prose>"
    )
    assert expected_structure in _OPTIMIZER_SYSTEM_PROMPT
    assert "under 150 words" in _OPTIMIZER_SYSTEM_PROMPT
    assert "MUST occur exactly once, in that order" in _OPTIMIZER_SYSTEM_PROMPT
    assert "non-empty" in _OPTIMIZER_SYSTEM_PROMPT


@pytest.mark.parametrize(
    "path",
    ["direct-fallback", "invalid-response", "llm-exception"],
)
def test_literal_canonical_tag_in_source_is_escaped_and_round_trips(path):
    from llm.prompt_optimizer import _fallback_optimize, optimize_shot_prompt
    from phase_c_assembly import _parse_structured_prompt

    source = "actor holds slate marked [SCENE] 7"
    if path == "direct-fallback":
        result = _fallback_optimize(source, [], {}, {})
    elif path == "invalid-response":
        result = optimize_shot_prompt(
            user_input=source,
            ensemble=_minimal_ensemble_mock(
                _valid_spec(image_prompt="invalid free prose"),
            ),
        )
    else:
        failing_ensemble = MagicMock()
        failing_ensemble.competitive_generate.side_effect = RuntimeError("timeout")
        result = optimize_shot_prompt(
            user_input=source,
            ensemble=failing_ensemble,
        )

    prompt = result["image_prompt"]
    assert prompt.count("[SCENE]") == 1
    assert "［SCENE］ 7" in prompt
    parsed = _parse_structured_prompt(prompt)
    assert list(parsed) == ["SHOT", "SCENE", "ACTION", "OUTFIT", "QUALITY"]
    assert "actor holds slate marked ［SCENE］ 7" in parsed["ACTION"]


def test_join_prompt_clauses_preserves_terminal_punctuation_exactly():
    from llm.prompt_optimizer import _join_prompt_clauses

    assert _join_prompt_clauses(
        "period.",
        "ellipsis...",
        "unicode…",
        "question?",
        "bang!",
        "plain",
    ) == "period. ellipsis... unicode… question? bang! plain."


def test_terminal_ellipsis_survives_fallback_and_invalid_optimizer_response():
    from llm.prompt_optimizer import _fallback_optimize, optimize_shot_prompt
    from phase_c_assembly import _parse_structured_prompt

    source = "the actor listens, hesitates, and pauses..."
    results = [
        _fallback_optimize(source, [], {}, {}),
        optimize_shot_prompt(
            user_input=source,
            ensemble=_minimal_ensemble_mock(
                _valid_spec(image_prompt="invalid free prose"),
            ),
        ),
    ]

    for result in results:
        assert source in _parse_structured_prompt(result["image_prompt"])["ACTION"]


@pytest.mark.parametrize(
    ("source_words", "objects", "primary_subject"),
    [
        (130, [], "character"),
        (
            100,
            [{"name": "Chronometer", "material_traits": "brushed steel"}],
            "object",
        ),
    ],
)
def test_long_unstructured_source_compacts_enrichment_without_data_loss(
    source_words,
    objects,
    primary_subject,
):
    from llm.prompt_optimizer import (
        _fallback_optimize,
        _image_prompt_word_count,
        optimize_shot_prompt,
    )
    from phase_c_assembly import _parse_structured_prompt

    source = " ".join(f"source-detail-{index}" for index in range(source_words))
    results = [
        _fallback_optimize(
            source,
            [],
            {},
            {},
            objects=objects,
            primary_subject=primary_subject,
        ),
        optimize_shot_prompt(
            user_input=source,
            objects=objects,
            primary_subject=primary_subject,
            ensemble=_minimal_ensemble_mock(
                _valid_spec(image_prompt="invalid free prose"),
            ),
        ),
    ]

    for result in results:
        prompt = result["image_prompt"]
        assert _image_prompt_word_count(prompt) <= 150
        assert source in _parse_structured_prompt(prompt)["ACTION"]


def test_overlong_optimizer_candidate_uses_compact_lossless_fallback():
    from llm.prompt_optimizer import (
        _image_prompt_word_count,
        _normalize_structured_image_prompt,
        optimize_shot_prompt,
    )
    from phase_c_assembly import _parse_structured_prompt

    source = " ".join(f"source-detail-{index}" for index in range(70))
    candidate_action = " ".join(
        f"candidate-detail-{index}"
        for index in range(151)
    )
    candidate = (
        "[SHOT] candidate-shot [SCENE] candidate-scene "
        f"[ACTION] {candidate_action} "
        "[OUTFIT] candidate-outfit [QUALITY] candidate-quality"
    )

    result = optimize_shot_prompt(
        user_input=source,
        ensemble=_minimal_ensemble_mock(
            _valid_spec(image_prompt=candidate),
        ),
    )

    prompt = result["image_prompt"]
    assert _normalize_structured_image_prompt(prompt) == prompt
    assert _image_prompt_word_count(prompt) <= 150
    assert candidate_action not in prompt
    assert source in _parse_structured_prompt(prompt)["ACTION"]


def test_overlong_authoritative_structured_source_is_preserved_exactly():
    from llm.prompt_optimizer import (
        _fallback_optimize,
        _image_prompt_word_count,
        optimize_shot_prompt,
    )

    source_action = " ".join(
        f"authoritative-detail-{index}"
        for index in range(151)
    )
    source = (
        "  [SHOT] source-shot [SCENE] source-scene "
        f"[ACTION] {source_action} "
        "[OUTFIT] source-outfit [QUALITY] source-quality\n"
    )
    candidate_action = " ".join(
        f"candidate-detail-{index}"
        for index in range(151)
    )
    candidate = (
        "[SHOT] candidate-shot [SCENE] candidate-scene "
        f"[ACTION] {candidate_action} "
        "[OUTFIT] candidate-outfit [QUALITY] candidate-quality"
    )

    fallback = _fallback_optimize(source, [], {}, {})
    optimized = optimize_shot_prompt(
        user_input=source,
        ensemble=_minimal_ensemble_mock(
            _valid_spec(image_prompt=candidate),
        ),
    )

    assert _image_prompt_word_count(source) > 150
    assert fallback["image_prompt"] == source
    assert optimized["image_prompt"] == source


@pytest.mark.parametrize(
    "bad_payload",
    [[], ["shot"], 42, "text", None],
)
def test_wrong_top_level_json_type_falls_back(bad_payload):
    """Valid JSON with a non-object root must not crash outside the recovery boundary."""
    from llm.prompt_optimizer import optimize_shot_prompt

    notes = "recover-me"
    ensemble = MagicMock()
    result_mock = MagicMock()
    result_mock.winner_content = json.dumps(bad_payload)
    ensemble.competitive_generate.return_value = result_mock

    result = optimize_shot_prompt(
        user_input="a figure waits by the door",
        intent_notes=notes,
        ensemble=ensemble,
    )

    assert isinstance(result, dict)
    assert "image_prompt" in result
    assert notes in result["image_prompt"]


def test_coerce_normalizes_shot_type_before_purpose():
    from llm.prompt_optimizer import _coerce_to_valid_keys

    spec = _coerce_to_valid_keys(
        {"purpose": "bogus", "shot_type": "bogus"},
        has_chars=False,
        has_dialogue=False,
    )
    assert spec["shot_type"] == "landscape"
    assert spec["purpose"] == "establishing_shot"


def test_optimizer_prompt_enum_and_guidance_use_injected_typed_policy():
    from llm.prompt_optimizer import (
        _OPTIMIZER_SYSTEM_PROMPT_TEMPLATE,
        _build_optimizer_system_prompt,
    )

    rendered = _build_optimizer_system_prompt(
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert (
        '"suggested_video_api":    string,  '
        "// AUTO | KLING_3_0 | SEEDANCE | VEO"
    ) in rendered
    assert "action_motion: video_api=SEEDANCE or KLING_3_0" in rendered
    for stale in ("GEMINI_OMNI", "SORA_2", "SORA_NATIVE", "RUNWAY_ACT_ONE"):
        assert stale not in rendered
        assert stale not in _OPTIMIZER_SYSTEM_PROMPT_TEMPLATE


def test_optimizer_prompt_keeps_auto_when_no_concrete_engine_is_ready():
    from llm.prompt_optimizer import _build_optimizer_system_prompt

    rendered = _build_optimizer_system_prompt(
        snapshot=RuntimeSnapshot(),
        on_date=PRE_SUNSET,
    )
    assert '"suggested_video_api":    string,  // AUTO' in rendered
    assert "action_motion: video_api=AUTO" in rendered


@pytest.mark.parametrize(
    ("suggestion", "reason"),
    [
        # Slice 3 re-admitted GEMINI_OMNI: under _fal_snapshot() (no google
        # credential/module) the truthful denial is runtime availability,
        # not product support (invariant 4).
        ("GEMINI_OMNI", "runtime_unavailable"),
        ("SORA_2", "retired"),
        ("SORA_NATIVE", "not_selectable"),
        ("RUNWAY_ACT_ONE", "non_video"),
        ("VEO_NATIVE", "runtime_unavailable"),
        ("MADE_UP_ENGINE", "unknown"),
    ],
)
def test_optimizer_coerces_ineligible_video_suggestion_to_auto_with_reason(
    suggestion,
    reason,
):
    from llm.prompt_optimizer import _coerce_to_valid_keys

    spec = _valid_spec()
    spec["suggested_video_api"] = suggestion
    result = _coerce_to_valid_keys(
        spec,
        has_chars=True,
        has_dialogue=False,
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert result["suggested_video_api"] == "AUTO"
    assert f"video target coerced to AUTO ({reason})" in result["reasoning"]


def test_optimizer_keeps_ready_selectable_suggestion_without_reason_mutation():
    from llm.prompt_optimizer import _coerce_to_valid_keys

    spec = _valid_spec()
    spec["suggested_video_api"] = "KLING_3_0"
    original_reasoning = spec["reasoning"]
    result = _coerce_to_valid_keys(
        spec,
        has_chars=True,
        has_dialogue=False,
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert result["suggested_video_api"] == "KLING_3_0"
    assert result["reasoning"] == original_reasoning


# ---------------------------------------------------------------------------
# FIX SLICE R2 — the optimizer coercion boundary (_coerce_to_valid_keys) must
# see project-disabled/aspect state, mirroring the LLM-authoring boundary
# fixed in _validate_raw_shot (commit 1b822551). Before this fix,
# evaluate_shot_target() was called from here without api_engines/
# aspect_ratio — an optimizer-suggested video engine that was project-
# disabled or aspect-incompatible was accepted un-coerced and stashed into
# take metadata for later motion routing.
# ---------------------------------------------------------------------------

def test_coerce_project_disabled_engine_to_auto_with_reason():
    from llm.prompt_optimizer import _coerce_to_valid_keys

    spec = _valid_spec()
    spec["suggested_video_api"] = "KLING_3_0"
    result = _coerce_to_valid_keys(
        spec,
        has_chars=True,
        has_dialogue=False,
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
        api_engines={"KLING_3_0": {"enabled": False}},
    )
    assert result["suggested_video_api"] == "AUTO"
    assert "video target coerced to AUTO (project_disabled)" in result["reasoning"]


def test_coerce_aspect_incompatible_engine_to_auto_with_reason(monkeypatch):
    import domain.video_engine_policy as video_engine_policy

    monkeypatch.setattr(
        video_engine_policy,
        "is_video_aspect_compatible",
        lambda _key, _aspect: False,
    )
    from llm.prompt_optimizer import _coerce_to_valid_keys

    spec = _valid_spec()
    spec["suggested_video_api"] = "KLING_3_0"
    result = _coerce_to_valid_keys(
        spec,
        has_chars=True,
        has_dialogue=False,
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
        aspect_ratio="9:16",
    )
    assert result["suggested_video_api"] == "AUTO"
    assert "video target coerced to AUTO (aspect_incompatible)" in result["reasoning"]


def test_coerce_without_project_state_still_accepts_live_target():
    # Regression guard for the new optional parameters: omitting
    # api_engines/aspect_ratio must not change behavior for an
    # already-eligible target (both default to policy-neutral).
    from llm.prompt_optimizer import _coerce_to_valid_keys

    spec = _valid_spec()
    spec["suggested_video_api"] = "KLING_3_0"
    original_reasoning = spec["reasoning"]
    result = _coerce_to_valid_keys(
        spec,
        has_chars=True,
        has_dialogue=False,
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert result["suggested_video_api"] == "KLING_3_0"
    assert result["reasoning"] == original_reasoning


def test_optimize_shot_prompt_threads_engine_context_into_coercion_boundary(
    monkeypatch,
):
    """Entry-point proof: optimize_shot_prompt() must source api_engines/
    aspect_ratio from its `global_settings` param and carry them into the
    _coerce_to_valid_keys -> evaluate_shot_target boundary (the same source
    the terminal update_scene_shots() write boundary reads).
    """
    import llm.prompt_optimizer as prompt_optimizer

    captured = {}
    real_evaluate_shot_target = prompt_optimizer.evaluate_shot_target

    def _spy(*args, **kwargs):
        captured["api_engines"] = kwargs.get("api_engines")
        captured["aspect_ratio"] = kwargs.get("aspect_ratio")
        return real_evaluate_shot_target(*args, **kwargs)

    monkeypatch.setattr(prompt_optimizer, "evaluate_shot_target", _spy)

    ensemble_mock = _minimal_ensemble_mock(_valid_spec())
    global_settings = {
        "api_engines": {"KLING_3_0": {"enabled": False}},
        "aspect_ratio": "9:16",
    }

    prompt_optimizer.optimize_shot_prompt(
        user_input="a woman stands in a corridor",
        global_settings=global_settings,
        ensemble=ensemble_mock,
    )

    assert captured["api_engines"] == {"KLING_3_0": {"enabled": False}}
    assert captured["aspect_ratio"] == "9:16"


def test_nonvideo_lipsync_ranking_keeps_historical_purpose_order():
    from llm.prompt_optimizer import _top_live_api_for_purpose

    assert _top_live_api_for_purpose(
        "dialogue_close_up",
        "lipsync",
        snapshot=RuntimeSnapshot(),
        on_date=PRE_SUNSET,
    ) == "SYNC_SO_V3"


def test_optimizer_llm_path_uses_same_injected_enum_and_write_fence():
    from llm.prompt_optimizer import optimize_shot_prompt

    spec = _valid_spec()
    spec["suggested_video_api"] = "SORA_2"
    ensemble = _minimal_ensemble_mock(spec)
    result = optimize_shot_prompt(
        user_input="a runner crosses the frame",
        characters=[{"id": "char_a", "name": "A"}],
        ensemble=ensemble,
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )

    sent_prompt = ensemble.competitive_generate.call_args.kwargs["system_prompt"]
    assert "// AUTO | KLING_3_0 | SEEDANCE | VEO" in sent_prompt
    assert result["suggested_video_api"] == "AUTO"
    assert "retired" in result["reasoning"]
    ensemble.competitive_generate.assert_called_once()


# ---------------------------------------------------------------------------
# FIX SLICE R3 — the no-LLM fallback path (_fallback_optimize) must see the
# same project-disabled/aspect-incompatible state R2 threaded into the LLM
# path's _coerce_to_valid_keys -> evaluate_shot_target boundary. Before this
# fix, _fallback_optimize picked suggested_video_api via
# _top_live_api_for_purpose alone (no api_engines/aspect_ratio), so a
# heuristic top-ranked engine that was disabled for the project or
# aspect-incompatible could reach take metadata un-coerced whenever the LLM
# ensemble was unavailable or raised.
# ---------------------------------------------------------------------------

def test_fallback_disabled_top_ranked_engine_not_suggested():
    """A project-disabled top-ranked engine must not reach the fallback
    spec's suggested_video_api."""
    from llm.prompt_optimizer import _fallback_optimize, _top_live_api_for_purpose

    # Confirm the un-coerced ranking pick really would have been KLING_3_0
    # under this runtime state, so the assertion below actually exercises
    # coercion rather than a ranking accident.
    uncoerced = _top_live_api_for_purpose(
        "static_portrait", "video",
        snapshot=_fal_snapshot(), on_date=PRE_SUNSET,
    )
    assert uncoerced == "KLING_3_0"

    result = _fallback_optimize(
        user_input="a woman stands in a corridor",
        characters=[{"id": "c1", "name": "A"}],
        location={},
        global_settings={},
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
        api_engines={"KLING_3_0": {"enabled": False}},
    )
    assert result["purpose"] == "static_portrait"
    assert result["suggested_video_api"] != "KLING_3_0"
    assert result["suggested_video_api"] == "AUTO"


def test_fallback_aspect_incompatible_engine_not_suggested(monkeypatch):
    """A project-aspect-incompatible top-ranked engine must not reach the
    fallback spec's suggested_video_api.

    Narrows the real PORTRAIT_CAPABLE_VIDEO_ENGINES allowlist by one engine
    (mirrors tests/unit/test_scene_decomposer.py::test_competitive_decompose_
    scene_coerces_aspect_incompatible_engine_via_real_policy) instead of
    monkeypatching is_video_aspect_compatible module-wide. The module-wide
    monkeypatch was unsound: the top-rank selection path
    (_top_live_api_for_purpose -> rank_apis_for_purpose ->
    resolve_video_ranking) calls evaluate_shot_target without an
    aspect_ratio (defaults to None), so a predicate that returns False
    regardless of its aspect argument rejects every candidate at the RANKING
    stage too. _top_live_api_for_purpose then returns "AUTO" directly from
    an empty ranking, and the assertion below passed whether or not the R3
    evaluate_shot_target wrap under test was even present (mock bleed).
    Narrowing the real allowlist data instead leaves the ranking stage
    (aspect_ratio=None, so the narrowed engine is still compatible there)
    untouched and only makes the wrap's own aspect_ratio="9:16" call reject
    the pick.
    """
    import domain.video_engine_policy as video_engine_policy
    from llm.prompt_optimizer import _fallback_optimize, _top_live_api_for_purpose

    monkeypatch.setattr(
        video_engine_policy,
        "PORTRAIT_CAPABLE_VIDEO_ENGINES",
        video_engine_policy.PORTRAIT_CAPABLE_VIDEO_ENGINES - {"KLING_3_0"},
    )

    # Confirm the un-coerced ranking pick really would have been KLING_3_0
    # under this runtime state (the ranking stage's own evaluate_shot_target
    # call passes no aspect_ratio, so narrowing the allowlist doesn't affect
    # it), so the assertion below actually exercises the wrap under test
    # rather than a ranking accident.
    uncoerced = _top_live_api_for_purpose(
        "static_portrait", "video",
        snapshot=_fal_snapshot(), on_date=PRE_SUNSET,
    )
    assert uncoerced == "KLING_3_0"

    result = _fallback_optimize(
        user_input="a woman stands in a corridor",
        characters=[{"id": "c1", "name": "A"}],
        location={},
        global_settings={},
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
        aspect_ratio="9:16",
    )
    assert result["purpose"] == "static_portrait"
    assert result["suggested_video_api"] != "KLING_3_0"
    assert result["suggested_video_api"] == "AUTO"


def test_fallback_without_project_state_still_accepts_live_target():
    # Regression guard for the new optional parameters: omitting
    # api_engines/aspect_ratio must not change the existing fallback
    # suggestion for an already-eligible target.
    from llm.prompt_optimizer import _fallback_optimize

    result = _fallback_optimize(
        user_input="a woman stands in a corridor",
        characters=[{"id": "c1", "name": "A"}],
        location={},
        global_settings={},
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert result["suggested_video_api"] == "KLING_3_0"


def test_fallback_path_threads_engine_context_into_video_suggestion(monkeypatch):
    """Entry-point proof for the no-LLM path: optimize_shot_prompt() must
    carry api_engines/aspect_ratio from global_settings into the
    evaluate_shot_target call _fallback_optimize now applies to its
    ranked suggested_video_api pick — mirroring R2's LLM-path proof
    (test_optimize_shot_prompt_threads_engine_context_into_coercion_boundary)
    for the fallback path the LLM ensemble raising exercises.
    """
    import llm.prompt_optimizer as prompt_optimizer

    captured = {}
    real_evaluate_shot_target = prompt_optimizer.evaluate_shot_target

    def _spy(*args, **kwargs):
        captured["api_engines"] = kwargs.get("api_engines")
        captured["aspect_ratio"] = kwargs.get("aspect_ratio")
        return real_evaluate_shot_target(*args, **kwargs)

    monkeypatch.setattr(prompt_optimizer, "evaluate_shot_target", _spy)

    failing_ensemble = MagicMock()
    failing_ensemble.competitive_generate.side_effect = RuntimeError("timeout")
    global_settings = {
        "api_engines": {"KLING_3_0": {"enabled": False}},
        "aspect_ratio": "9:16",
    }

    result = prompt_optimizer.optimize_shot_prompt(
        user_input="a woman stands in a corridor",
        characters=[{"id": "c1", "name": "A"}],
        global_settings=global_settings,
        ensemble=failing_ensemble,
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )

    assert captured["api_engines"] == {"KLING_3_0": {"enabled": False}}
    assert captured["aspect_ratio"] == "9:16"
    assert result["suggested_video_api"] != "KLING_3_0"
