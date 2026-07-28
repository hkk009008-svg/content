"""Final-review M-1: the CineDecompose shot-decomposition prompt's R4 aspect
descriptor must be orientation-aware. Before the fix it hardcoded "widescreen",
so a 9:16 project produced the self-contradictory instruction "9:16 widescreen"
to gpt-4o, biasing shot framing horizontal for a vertical deliverable. These
pin that a portrait project is described as vertical, and that 16:9 is unchanged.
"""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import domain.scene_decomposer as sd
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


def test_hedra_c3_purged_from_catalog():
    # WS4 Task 4: the LLM-routing catalog still listed HEDRA_C3 as status:"live"
    # and ranked it first for lipsync, even though Tasks 1-3 removed the Hedra
    # engine entirely. Repoint policy: default lipsync = SYNC_SO_V3 (sync-3,
    # overlay/dialogue primary) / OMNIHUMAN_V1_5 (talking-head-generation primary).
    import domain.scene_decomposer as sd, domain.language_defaults as ld
    assert "HEDRA_C3" not in sd.API_REGISTRY
    assert all("HEDRA_C3" not in v for v in sd.PURPOSE_API_RANKING.values())
    for cfg in ld.PIPELINE_LANGUAGE_DEFAULTS.values():
        assert "HEDRA_C3" not in cfg.get("lipsync_engine_priority", [])
    assert sd.PURPOSE_API_RANKING["dialogue_close_up"][0] == "SYNC_SO_V3"
    assert sd.PURPOSE_API_RANKING["talking_head_full"][0] == "OMNIHUMAN_V1_5"


_REQUIRED_SHOT_FIELDS = [
    "prompt",
    "camera",
    "visual_effect",
    "target_api",
    "scene_foley",
    "characters_in_frame",
    "action_context",
]


def _valid_shot():
    return {
        "prompt": "[SHOT] test [SCENE] room [ACTION] walk [OUTFIT] coat [QUALITY] film",
        "camera": sd.CAMERA_MOTIONS[0],
        "visual_effect": sd.VISUAL_EFFECTS[0],
        "target_api": sd.TARGET_APIS[0],
        "scene_foley": "room tone",
        "characters_in_frame": ["char_a"],
        "action_context": "walking",
    }


def _valid_payload(n=2):
    return {"shots": [_valid_shot() for _ in range(n)]}


def _schema_from_rendered_prompt(rendered_prompt):
    schema_text = rendered_prompt.split("JSON Schema:\n", 1)[1]
    schema, _end = json.JSONDecoder().raw_decode(schema_text)
    return schema


def _shot_item_schema(schema):
    return schema["properties"]["shots"]["items"]


def _capture_both_path_prompts(monkeypatch):
    import openai
    import research_engine
    import web_research

    captured = {}
    scene = {
        "id": "scene_a",
        "title": "A Scene",
        "action": "Alice walks into the room.",
        "duration_seconds": 5,
    }
    characters = [
        {
            "id": "char_a",
            "name": "Alice",
            "physical_traits": "green eyes, black hair — MUST NOT REACH PROMPT",
        }
    ]
    location = {"description": "a room"}
    settings = {"aspect_ratio": "16:9"}

    monkeypatch.setattr(
        research_engine,
        "research_cinematography",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(sd, "settings", SimpleNamespace(openai_api_key="test-key"))
    monkeypatch.setattr(openai, "OpenAI", MagicMock(return_value=MagicMock()))

    def fake_run_with_tools(*args, **kwargs):
        captured["direct"] = kwargs["system_prompt"]
        captured["direct_user"] = kwargs["user_prompt"]
        return json.dumps(_valid_payload(2))

    monkeypatch.setattr(web_research, "run_with_tools", fake_run_with_tools)
    sd.decompose_scene(scene, characters, location, settings)

    class FakeEnsemble:
        def __init__(self, **kwargs):
            pass

        def competitive_generate(self, **kwargs):
            captured["competitive"] = kwargs["system_prompt"]
            captured["competitive_user"] = kwargs["user_prompt"]
            return SimpleNamespace(
                winner_index=0,
                winner_content=_valid_payload(2),
                scores=[9.0],
                reasoning="fixture",
                models_used=["gpt-4o"],
            )

    monkeypatch.setattr(sd, "LLMEnsemble", FakeEnsemble)
    sd.competitive_decompose_scene(scene, characters, location, settings)
    return captured


def test_shared_shot_schema_preserves_shape_required_fields_and_enums():
    schema = sd._build_cinedecompose_shot_schema()
    assert schema["type"] == "object"
    assert schema["required"] == ["shots"]
    shots = schema["properties"]["shots"]
    assert shots["type"] == "array"
    assert shots["minItems"] == 2
    assert shots["maxItems"] == 5

    item = _shot_item_schema(schema)
    assert item["type"] == "object"
    properties = item["properties"]
    assert list(properties) == _REQUIRED_SHOT_FIELDS
    assert item["required"] == _REQUIRED_SHOT_FIELDS
    assert {name: definition["type"] for name, definition in properties.items()} == {
        "prompt": "string",
        "camera": "string",
        "visual_effect": "string",
        "target_api": "string",
        "scene_foley": "string",
        "characters_in_frame": "array",
        "action_context": "string",
    }
    assert properties["camera"]["enum"] == sd.CAMERA_MOTIONS
    assert properties["visual_effect"]["enum"] == sd.VISUAL_EFFECTS
    assert properties["target_api"]["enum"] == sd.TARGET_APIS
    assert properties["characters_in_frame"]["items"] == {"type": "string"}


def test_shared_shot_schema_enum_lists_are_mutation_isolated():
    enum_sources = {
        "camera": sd.CAMERA_MOTIONS,
        "visual_effect": sd.VISUAL_EFFECTS,
        "target_api": sd.TARGET_APIS,
    }
    first = sd._build_cinedecompose_shot_schema()

    for field, source in enum_sources.items():
        enum_values = _shot_item_schema(first)["properties"][field]["enum"]
        assert enum_values is not source
        enum_values.append(f"FIRST_ONLY_{field}")

    second = sd._build_cinedecompose_shot_schema()
    for field, source in enum_sources.items():
        first_values = _shot_item_schema(first)["properties"][field]["enum"]
        second_values = _shot_item_schema(second)["properties"][field]["enum"]
        assert first_values is not second_values
        assert second_values is not source
        assert second_values == source
        assert f"FIRST_ONLY_{field}" not in source
        assert f"FIRST_ONLY_{field}" not in second_values


def test_rendered_schema_respects_hc1_identity_firewall():
    rendered = sd._render_cinedecompose_system_prompt(_prompt("16:9"))
    assert "HC1-IDENTITY_FIREWALL" in rendered
    assert "ALL character physical descriptions" not in rendered

    prompt_description = (
        _shot_item_schema(_schema_from_rendered_prompt(rendered))["properties"][
            "prompt"
        ]["description"]
    )
    assert "location, action, wardrobe, and cinematic quality" in prompt_description
    assert "reference/PuLID locking" in prompt_description


def test_direct_and_competitive_paths_render_identical_canonical_schema(monkeypatch):
    captured = _capture_both_path_prompts(monkeypatch)
    direct_schema = _schema_from_rendered_prompt(captured["direct"])
    competitive_schema = _schema_from_rendered_prompt(captured["competitive"])

    assert direct_schema == competitive_schema
    assert direct_schema == sd._build_cinedecompose_shot_schema()


def test_both_paths_call_shared_schema_factory(monkeypatch):
    canonical = sd._build_cinedecompose_shot_schema()
    calls = []

    def marked_schema():
        calls.append("called")
        schema = deepcopy(canonical)
        schema["x-shared-schema-marker"] = "factory"
        return schema

    monkeypatch.setattr(sd, "_build_cinedecompose_shot_schema", marked_schema)
    captured = _capture_both_path_prompts(monkeypatch)

    assert calls == ["called", "called"]
    for path in ("direct", "competitive"):
        schema = _schema_from_rendered_prompt(captured[path])
        assert schema["x-shared-schema-marker"] == "factory"


def test_decomposer_prompts_omit_physical_traits(monkeypatch):
    captured = _capture_both_path_prompts(monkeypatch)
    for path in ("direct", "competitive"):
        assert "green eyes" not in captured[path]
        assert "MUST NOT REACH PROMPT" not in captured[path]
        assert "Alice (ID: char_a)" in captured[path]
        assert '{"shots"' in captured[f"{path}_user"] or '{"shots":' in captured[f"{path}_user"]


def test_validate_raw_shot_rejects_invalid_enum_and_prompt():
    bad = _valid_shot()
    bad["camera"] = "not_a_real_camera"
    with pytest.raises(ValueError, match="invalid camera"):
        sd._validate_raw_shot(bad, index=0)

    missing_section = _valid_shot()
    missing_section["prompt"] = "[SHOT] only one section"
    with pytest.raises(ValueError, match="SHOT|five"):
        sd._validate_raw_shot(missing_section, index=0)


def test_enrich_rejects_wrong_shot_count():
    scene = {"id": "s1", "action": "walk"}
    with pytest.raises(ValueError, match="expected 2-5 shots, got 1"):
        sd._enrich_validated_shots(
            [_valid_shot()],
            scene=scene,
            characters=[{"id": "char_a", "name": "Alice"}],
            target_shots=2,
        )
    with pytest.raises(ValueError, match="exactly 3"):
        sd._enrich_validated_shots(
            [_valid_shot(), _valid_shot()],
            scene=scene,
            characters=[{"id": "char_a", "name": "Alice"}],
            target_shots=3,
        )


def test_parse_rejects_arbitrary_nested_dict():
    with pytest.raises(ValueError, match="shots"):
        sd._parse_decomposition_payload({"frames": [_valid_shot(), _valid_shot()]})


def test_invalid_llm_payload_falls_back_on_both_paths(monkeypatch):
    import openai
    import research_engine
    import web_research

    scene = {
        "id": "scene_a",
        "title": "A Scene",
        "action": "Alice walks.",
        "duration_seconds": 5,
    }
    characters = [{"id": "char_a", "name": "Alice"}]
    location = {"description": "a room"}
    settings = {"aspect_ratio": "16:9"}

    monkeypatch.setattr(
        research_engine, "research_cinematography", lambda *a, **k: None
    )
    monkeypatch.setattr(sd, "settings", SimpleNamespace(openai_api_key="test-key"))
    monkeypatch.setattr(openai, "OpenAI", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        web_research,
        "run_with_tools",
        lambda *a, **k: json.dumps({"shots": [_valid_shot()]}),  # count=1, need 2
    )

    direct = sd.decompose_scene(scene, characters, location, settings)
    assert len(direct) >= 1  # fallback path
    assert all("prompt" in s for s in direct)

    class BadEnsemble:
        def __init__(self, **kwargs):
            pass

        def competitive_generate(self, **kwargs):
            return SimpleNamespace(
                winner_index=0,
                winner_content={"shots": [_valid_shot()]},
                scores=[1.0],
                reasoning="bad",
                models_used=["gpt-4o"],
            )

    # Competitive falls back to direct, which also fails validation → fallback_decompose
    monkeypatch.setattr(sd, "LLMEnsemble", BadEnsemble)
    competitive = sd.competitive_decompose_scene(scene, characters, location, settings)
    assert len(competitive) >= 1
    assert all("prompt" in s for s in competitive)
