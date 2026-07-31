"""Typed compatibility and purpose-ranking tests for scene decomposition."""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import domain.scene_decomposer as sd
from domain.provider_catalog import RuntimeSnapshot


PRE_SUNSET = date(2026, 9, 23)


def _fal_snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        credentials={"fal_key"},
        modules={"fal_client"},
    )


def _veo_snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        credentials={"google_api_key"},
        modules={"google.genai"},
    )


def _valid_shot(target_api: str = "AUTO") -> dict:
    return {
        "prompt": "[SHOT] test [SCENE] room [ACTION] walk [OUTFIT] coat [QUALITY] film",
        "camera": sd.CAMERA_MOTIONS[0],
        "visual_effect": sd.VISUAL_EFFECTS[0],
        "target_api": target_api,
        "scene_foley": "room tone",
        "characters_in_frame": ["char_a"],
        "action_context": "walking",
    }


# ---------------------------------------------------------------------------
# Legacy update compatibility vs dynamic authoring eligibility
# ---------------------------------------------------------------------------

def test_target_apis_preserves_legacy_update_round_trip_compatibility():
    compatibility_only = {"SORA_NATIVE", "KLING_NATIVE", "LTX", "SORA_2"}

    assert sd.TARGET_APIS == list(sd.API_REGISTRY.keys())
    assert compatibility_only <= set(sd.TARGET_APIS)

    eligible = sd.get_eligible_target_apis(
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert eligible == ["AUTO", "KLING_3_0", "SEEDANCE", "VEO"]
    assert compatibility_only.isdisjoint(eligible)


def test_target_apis_does_not_claim_live_truth_when_runtime_changes_after_import():
    compatibility_snapshot = list(sd.TARGET_APIS)

    without_runtime = sd.get_eligible_target_apis(
        snapshot=RuntimeSnapshot(),
        on_date=PRE_SUNSET,
    )
    with_fal_runtime = sd.get_eligible_target_apis(
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )

    assert without_runtime == ["AUTO"]
    assert with_fal_runtime == ["AUTO", "KLING_3_0", "SEEDANCE", "VEO"]
    assert sd.TARGET_APIS == compatibility_snapshot
    assert sd.TARGET_APIS != without_runtime
    assert sd.TARGET_APIS != with_fal_runtime


# ---------------------------------------------------------------------------
# API_REGISTRY — GEMINI_OMNI entry shape
# ---------------------------------------------------------------------------

def test_gemini_omni_registry_row_preserves_history_but_projects_disabled_truth():
    assert "GEMINI_OMNI" in sd.API_REGISTRY
    entry = sd.API_REGISTRY["GEMINI_OMNI"]
    assert entry["category"] == "native"
    assert entry["modality"] == "video"
    assert entry["status"] == "disabled"
    assert entry["dispatchable"] is False
    assert entry["selectable"] is False
    assert entry["native_audio"] is True
    assert entry["per_shot_cost"] == 0.56


def test_registry_projection_statuses_and_raw_history_are_separate():
    assert sd.API_REGISTRY["AUTO"]["status"] == "live"
    assert sd.API_REGISTRY["SORA_2"]["status"] == "retired"
    assert sd.API_REGISTRY["GEMINI_OMNI"]["status"] == "disabled"

    assert sd._LEGACY_API_REGISTRY_SEED["SORA_2"]["status"] == "live"
    assert sd._LEGACY_API_REGISTRY_SEED["GEMINI_OMNI"]["status"] == "live"
    assert (
        sd._LEGACY_API_REGISTRY_SEED["AUTO"]["best_for"]
        is not sd.API_REGISTRY["AUTO"]["best_for"]
    )
    for key in ("SORA_2", "GEMINI_OMNI", "KLING_3_0"):
        for field in ("description", "best_for", "per_shot_cost"):
            assert (
                sd.API_REGISTRY[key][field]
                == sd._LEGACY_API_REGISTRY_SEED[key][field]
            )


def test_gemini_omni_best_for_covers_ws2_shot_purposes():
    best_for = sd.API_REGISTRY["GEMINI_OMNI"]["best_for"]
    for purpose in (
        "dialogue_close_up",
        "talking_head_full",
        "static_portrait",
        "action_motion",
        "establishing_shot",
    ):
        assert purpose in best_for


# ---------------------------------------------------------------------------
# PURPOSE_API_RANKING — GEMINI_OMNI placement per purpose
# ---------------------------------------------------------------------------

def test_gemini_omni_leads_action_motion_ranking():
    assert sd.PURPOSE_API_RANKING["action_motion"][0] == "GEMINI_OMNI"


def test_gemini_omni_leads_static_portrait_ranking():
    assert sd.PURPOSE_API_RANKING["static_portrait"][0] == "GEMINI_OMNI"


def test_gemini_omni_leads_establishing_shot_ranking():
    assert sd.PURPOSE_API_RANKING["establishing_shot"][0] == "GEMINI_OMNI"


def test_gemini_omni_second_in_dialogue_close_up_behind_sync_so_v3():
    # Historical ordering stays intact. The compatibility projection marks
    # GEMINI_OMNI disabled, so the dialogue-routing walk skips it at runtime.
    ranking = sd.PURPOSE_API_RANKING["dialogue_close_up"]
    assert ranking[0] == "SYNC_SO_V3"
    assert ranking[1] == "GEMINI_OMNI"


def test_gemini_omni_present_in_talking_head_full_after_generation_engines():
    ranking = sd.PURPOSE_API_RANKING["talking_head_full"]
    assert ranking.index("GEMINI_OMNI") > ranking.index("OMNIHUMAN_V1_5")
    assert ranking.index("GEMINI_OMNI") > ranking.index("RUNWAY_ACT_ONE")


def test_gemini_omni_out_of_ws2_scope_purposes_unchanged():
    # The WS2 spec's shot-type table only covers Portrait/Medium/Wide/Action/
    # Landscape/Dialogue; these purposes were explicitly left untouched.
    for purpose in (
        "macro_detail",
        "style_locked_sequence",
        "narration",
        "music_score",
        "foley",
        "upscale_image",
        "upscale_video",
        "product_hero",
        "product_in_scene",
        "product_reveal_motion",
    ):
        assert "GEMINI_OMNI" not in sd.PURPOSE_API_RANKING[purpose]


def test_no_duplicate_apis_within_gemini_omni_rankings():
    for purpose in ("dialogue_close_up", "talking_head_full", "action_motion",
                     "static_portrait", "establishing_shot"):
        ranking = sd.PURPOSE_API_RANKING[purpose]
        assert len(ranking) == len(set(ranking)), f"duplicate entry in {purpose}"


# ---------------------------------------------------------------------------
# BILLING_PROVIDERS — separate Gemini-Developer-API bucket, NOT merged into Vertex
# ---------------------------------------------------------------------------

def test_gemini_omni_billed_under_google_gemini_api():
    assert sd.BILLING_PROVIDERS["GOOGLE_GEMINI_API"] == ["GEMINI_OMNI"]


def test_gemini_omni_not_folded_into_google_vertex():
    # Vertex (aiplatform) and the Gemini Developer API (generativelanguage) are
    # separately-enabled, separately-billed GCP surfaces; Omni Flash is
    # Gemini-Developer-API-only (not on Vertex today).
    assert "GEMINI_OMNI" not in sd.BILLING_PROVIDERS["GOOGLE_VERTEX"]
    assert sd.BILLING_PROVIDERS["GOOGLE_VERTEX"] == ["VEO_NATIVE"]


def test_every_api_registry_video_native_key_has_a_billing_provider():
    # Sanity: GEMINI_OMNI shouldn't be double-billed under two providers.
    owners = [
        provider for provider, keys in sd.BILLING_PROVIDERS.items()
        if "GEMINI_OMNI" in keys
    ]
    assert owners == ["GOOGLE_GEMINI_API"]


# ---------------------------------------------------------------------------
# rank_apis_for_purpose() — the orchestrator-facing walk
# ---------------------------------------------------------------------------

def test_rank_apis_for_purpose_action_motion_uses_typed_runtime_truth():
    ranked = sd.rank_apis_for_purpose(
        "action_motion",
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert [key for key, _info in ranked] == ["SEEDANCE", "KLING_3_0"]
    assert ranked[0][1]["status"] == "live"


def test_rank_apis_for_purpose_respects_max_cost_excluding_gemini_omni():
    # GEMINI_OMNI's per_shot_cost is 0.56; a budget cap below that must skip it.
    ranked = sd.rank_apis_for_purpose(
        "action_motion",
        max_per_shot_cost=0.50,
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert all(key != "GEMINI_OMNI" for key, _info in ranked)


def test_rank_apis_for_purpose_dialogue_excludes_nonvideo_and_broken_entries():
    snapshot = RuntimeSnapshot(
        credentials={"google_api_key"},
        modules={"google.genai"},
    )
    ranked = dict(
        sd.rank_apis_for_purpose(
            "dialogue_close_up",
            snapshot=snapshot,
            on_date=PRE_SUNSET,
        )
    )
    assert list(ranked) == ["VEO_NATIVE"]
    assert ranked["VEO_NATIVE"]["modality"] == "video"
    assert ranked["VEO_NATIVE"]["native_audio"] is True


def test_legacy_dialogue_walk_no_longer_surfaces_broken_gemini():
    winner = None
    for key in sd.PURPOSE_API_RANKING["dialogue_close_up"]:
        info = sd.API_REGISTRY.get(key, {})
        if info.get("native_audio") and info.get("modality") == "video" and info.get("status") == "live":
            winner = key
            break
    assert winner == "VEO_NATIVE"


def test_nonvideo_purpose_rows_preserve_legacy_membership_order_and_status():
    expected = {
        "narration": ["ELEVENLABS_V3", "CARTESIA_SONIC_2", "OPENAI_AUDIO"],
        "music_score": ["SUNO_V5"],
        "foley": ["STABLE_AUDIO_FOLEY"],
        "upscale_image": ["SUPIR_V0Q"],
        "upscale_video": ["SEEDVR2"],
    }
    nonvideo_purposes = set(sd.PURPOSE_API_RANKING) - sd._VIDEO_AUTHORING_PURPOSES
    assert nonvideo_purposes == set(expected)

    for purpose, expected_keys in expected.items():
        without_runtime = sd.rank_apis_for_purpose(
            purpose,
            snapshot=RuntimeSnapshot(),
            on_date=PRE_SUNSET,
        )
        with_fal_runtime = sd.rank_apis_for_purpose(
            purpose,
            snapshot=_fal_snapshot(),
            on_date=PRE_SUNSET,
        )
        assert [key for key, _info in without_runtime] == expected_keys
        assert with_fal_runtime == without_runtime
        assert all(info["status"] == "live" for _key, info in without_runtime)
        assert all(
            info == sd._LEGACY_API_REGISTRY_SEED[key]
            and info is not sd._LEGACY_API_REGISTRY_SEED[key]
            and info["best_for"] is not sd._LEGACY_API_REGISTRY_SEED[key]["best_for"]
            for key, info in without_runtime
        )


def test_nonvideo_ranking_results_are_deeply_isolated_from_legacy_seed():
    seed_row = sd._LEGACY_API_REGISTRY_SEED["OPENAI_AUDIO"]
    original_label = seed_row["label"]
    original_best_for = list(seed_row["best_for"])

    first_row = dict(sd.rank_apis_for_purpose("narration"))["OPENAI_AUDIO"]
    first_row["label"] = "mutated caller label"
    first_row["best_for"].append("mutated_caller_purpose")

    assert seed_row["label"] == original_label
    assert seed_row["best_for"] == original_best_for

    subsequent_row = dict(sd.rank_apis_for_purpose("narration"))["OPENAI_AUDIO"]
    assert subsequent_row["label"] == original_label
    assert subsequent_row["best_for"] == original_best_for
    assert subsequent_row is not first_row
    assert subsequent_row["best_for"] is not first_row["best_for"]


def test_nonvideo_rankings_preserve_representative_legacy_fields():
    representatives = {
        "narration": (
            "OPENAI_AUDIO",
            {"label": "OpenAI gpt-4o-audio", "modality": "tts",
             "status": "live", "per_shot_cost": 0.012},
        ),
        "music_score": (
            "SUNO_V5",
            {"label": "Suno V5", "modality": "music",
             "status": "live", "per_shot_cost": 0.10},
        ),
        "foley": (
            "STABLE_AUDIO_FOLEY",
            {"label": "Stable Audio (Foley)", "modality": "foley",
             "status": "live", "per_shot_cost": 0.03},
        ),
        "upscale_image": (
            "SUPIR_V0Q",
            {"label": "SUPIR-v0Q (image)", "modality": "upscale",
             "status": "live", "per_shot_cost": 0.02},
        ),
        "upscale_video": (
            "SEEDVR2",
            {"label": "SeedVR2", "modality": "upscale",
             "status": "live", "per_shot_cost": 0.08},
        ),
    }

    for purpose, (key, expected_fields) in representatives.items():
        ranked = dict(sd.rank_apis_for_purpose(purpose))
        assert key in ranked
        for field, expected_value in expected_fields.items():
            assert ranked[key][field] == expected_value


def test_nonvideo_status_filter_uses_legacy_planned_rows():
    expected_planned = {
        "narration": ["F5_TTS"],
        "music_score": ["ELEVENLABS_MUSIC", "STABLE_AUDIO_2"],
        "foley": ["ADOBE_AUDIO_AI"],
        "upscale_image": ["CCSR"],
        "upscale_video": ["TOPAZ_ASTRA"],
    }

    for purpose, expected_keys in expected_planned.items():
        ranked = sd.rank_apis_for_purpose(
            purpose,
            status_filter=("planned",),
        )
        assert [key for key, _info in ranked] == expected_keys
        assert all(info["status"] == "planned" for _key, info in ranked)


def test_video_authoring_ranking_rows_are_deeply_isolated_from_registry():
    # Same-file MINOR (review companion to FIX SLICE R1): rank_apis_for_purpose
    # used to deepcopy `info` only on the eligible_video_keys-is-None (legacy
    # non-video) branch, so a video-authoring ranking row aliased the live
    # API_REGISTRY entry — a caller mutating a returned row would corrupt
    # module-level registry state for every later purpose lookup.
    ranked = dict(
        sd.rank_apis_for_purpose(
            "action_motion",
            snapshot=_fal_snapshot(),
            on_date=PRE_SUNSET,
        )
    )
    row = ranked["SEEDANCE"]
    assert row is not sd.API_REGISTRY["SEEDANCE"]
    original_label = sd.API_REGISTRY["SEEDANCE"]["label"]

    row["label"] = "mutated by caller"

    assert sd.API_REGISTRY["SEEDANCE"]["label"] == original_label


# ---------------------------------------------------------------------------
# FIX SLICE R1 — the LLM-authoring boundary (_validate_raw_shot /
# _enrich_validated_shots) must see project-disabled/aspect state, mirroring
# the terminal update_scene_shots() write boundary (commit f414e8a2). Before
# this fix, evaluate_shot_target() was called without api_engines/
# aspect_ratio at this boundary — an LLM-authored shot naming a project-
# disabled or aspect-incompatible engine was accepted un-coerced.
# ---------------------------------------------------------------------------

def test_validate_raw_shot_coerces_project_disabled_engine_to_auto():
    # Live-repro seed from the review: VEO_NATIVE is runtime-available but
    # the project has disabled it via global_settings.api_engines.
    raw = _valid_shot("VEO_NATIVE")
    validated = sd._validate_raw_shot(
        raw,
        index=0,
        snapshot=_veo_snapshot(),
        on_date=PRE_SUNSET,
        api_engines={"VEO_NATIVE": {"enabled": False}},
    )
    assert validated["target_api"] == "AUTO"
    assert validated["_target_api_policy_reason"] == "project_disabled"


def test_validate_raw_shot_coerces_aspect_incompatible_engine_to_auto(monkeypatch):
    import domain.video_engine_policy as video_engine_policy

    monkeypatch.setattr(
        video_engine_policy,
        "is_video_aspect_compatible",
        lambda _key, _aspect: False,
    )
    raw = _valid_shot("KLING_3_0")
    validated = sd._validate_raw_shot(
        raw,
        index=0,
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
        aspect_ratio="9:16",
    )
    assert validated["target_api"] == "AUTO"
    assert validated["_target_api_policy_reason"] == "aspect_incompatible"


def test_validate_raw_shot_without_project_state_still_accepts_live_target():
    # Regression guard for the new optional parameters: omitting
    # api_engines/aspect_ratio must not change behavior for an
    # already-eligible target (both default to policy-neutral).
    raw = _valid_shot("KLING_3_0")
    validated = sd._validate_raw_shot(
        raw,
        index=0,
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert validated["target_api"] == "KLING_3_0"
    assert "_target_api_policy_reason" not in validated


def test_enrich_validated_shots_threads_project_disabled_state_into_records():
    shots = [_valid_shot("VEO_NATIVE"), _valid_shot("VEO_NATIVE")]
    records = sd._enrich_validated_shots(
        shots,
        scene={"id": "scene_policy", "action": "walk"},
        characters=[{"id": "char_a", "name": "Alice"}],
        target_shots=2,
        snapshot=_veo_snapshot(),
        on_date=PRE_SUNSET,
        api_engines={"VEO_NATIVE": {"enabled": False}},
    )
    assert [record["target_api"] for record in records] == ["AUTO", "AUTO"]
    assert [record["target_api_policy_reason"] for record in records] == [
        "project_disabled",
        "project_disabled",
    ]


def test_project_video_engine_context_extracts_settings_dict_shape():
    api_engines, aspect_ratio = sd._project_video_engine_context(
        {"api_engines": {"KLING_3_0": {"enabled": False}}, "aspect_ratio": "9:16"}
    )
    assert api_engines == {"KLING_3_0": {"enabled": False}}
    assert aspect_ratio == "9:16"


def test_project_video_engine_context_defaults_on_non_dict_settings():
    api_engines, aspect_ratio = sd._project_video_engine_context(None)
    assert api_engines == {}
    assert aspect_ratio is None


def _mock_llm_scaffolding(monkeypatch):
    """Shared decompose_scene()/competitive_decompose_scene() network mocks."""
    import openai
    import research_engine

    monkeypatch.setattr(
        research_engine, "research_cinematography", lambda *a, **k: None
    )
    monkeypatch.setattr(sd, "settings", SimpleNamespace(openai_api_key="test-key"))
    monkeypatch.setattr(openai, "OpenAI", MagicMock(return_value=MagicMock()))


def test_decompose_scene_threads_project_disabled_state_from_global_settings(
    monkeypatch,
):
    # Entry-point proof: decompose_scene() must source api_engines/
    # aspect_ratio from its `global_settings` param (the same source
    # update_scene_shots() reads at the terminal write boundary) and carry
    # them all the way to the persisted shot record.
    import web_research

    _mock_llm_scaffolding(monkeypatch)
    scene = {
        "id": "scene_a",
        "title": "A Scene",
        "action": "Alice walks.",
        "duration_seconds": 5,  # target_shots == 2
    }
    characters = [{"id": "char_a", "name": "Alice"}]
    location = {"description": "a room"}
    global_settings = {
        "aspect_ratio": "16:9",
        "api_engines": {"VEO_NATIVE": {"enabled": False}},
    }

    monkeypatch.setattr(
        web_research,
        "run_with_tools",
        lambda *a, **k: json.dumps(
            {"shots": [_valid_shot("VEO_NATIVE"), _valid_shot("VEO_NATIVE")]}
        ),
    )

    shots = sd.decompose_scene(
        scene,
        characters,
        location,
        global_settings,
        runtime_snapshot=_veo_snapshot(),
        on_date=PRE_SUNSET,
    )

    assert len(shots) == 2
    assert all(shot["target_api"] == "AUTO" for shot in shots)
    assert all(
        shot["target_api_policy_reason"] == "project_disabled" for shot in shots
    )


def test_competitive_decompose_scene_calls_evaluator_with_project_settings(
    monkeypatch,
):
    """Spy proof: competitive_decompose_scene must call the shared policy
    evaluator, once per raw shot, with the ``api_engines``/``aspect_ratio``
    sourced from the project's ``global_settings`` — the same evaluator
    ``test_generated_shot_validation_calls_the_same_policy_evaluator`` in
    ``test_web_server_video_targets.py`` spies on at the authoring boundary.
    Unlike a monkeypatched compatibility predicate, this stays RED if the
    threading is ever dropped from ``_enrich_validated_shots``'s call.
    """
    from domain.video_engine_policy import VideoTargetDecision

    _mock_llm_scaffolding(monkeypatch)
    scene = {
        "id": "scene_b",
        "title": "B Scene",
        "action": "Bob runs.",
        "duration_seconds": 5,  # target_shots == 2
    }
    characters = [{"id": "char_b", "name": "Bob"}]
    location = {"description": "a street"}
    global_settings = {
        "aspect_ratio": "9:16",
        "api_engines": {"SEEDANCE": {"enabled": False}},
    }

    class FixedEnsemble:
        def __init__(self, **kwargs):
            pass

        def competitive_generate(self, **kwargs):
            return SimpleNamespace(
                winner_index=0,
                winner_content={
                    "shots": [_valid_shot("KLING_3_0"), _valid_shot("SEEDANCE")]
                },
                scores=[1.0],
                reasoning="best",
                models_used=["gpt-4o"],
            )

    monkeypatch.setattr(sd, "LLMEnsemble", FixedEnsemble)

    evaluator = MagicMock(
        side_effect=lambda requested, **kwargs: VideoTargetDecision(
            requested=requested if isinstance(requested, str) else "",
            target=requested if isinstance(requested, str) else "AUTO",
            accepted=True,
        )
    )
    monkeypatch.setattr(sd, "evaluate_shot_target", evaluator)

    shots = sd.competitive_decompose_scene(
        scene,
        characters,
        location,
        global_settings,
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )

    assert len(shots) == 2
    assert evaluator.call_count == 2
    evaluator.assert_any_call(
        "KLING_3_0",
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
        api_engines=global_settings["api_engines"],
        aspect_ratio=global_settings["aspect_ratio"],
    )
    evaluator.assert_any_call(
        "SEEDANCE",
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
        api_engines=global_settings["api_engines"],
        aspect_ratio=global_settings["aspect_ratio"],
    )


def test_competitive_decompose_scene_coerces_aspect_incompatible_engine_via_real_policy(
    monkeypatch,
):
    """End-to-end proof through the REAL policy (no monkeypatched
    predicate): a 9:16 project plus an aspect-incompatible engine in the raw
    LLM output must coerce to AUTO with the policy reason recorded, mirroring
    the aspect_incompatible cases already exercised for engine choice in
    ``test_web_server_video_targets.py``
    (``test_project_config_applies_project_aspect_policy`` /
    ``test_direct_shot_write_applies_latest_project_policy``).

    ``is_video_aspect_compatible`` itself is never stubbed — only the
    portrait-capability allowlist DATA it reads is narrowed by one engine, so
    the real compatibility arithmetic (``aspect_ratio != "9:16" or key in
    PORTRAIT_CAPABLE_VIDEO_ENGINES``) still runs and genuinely decides the
    outcome from the threaded aspect_ratio.
    """
    import domain.video_engine_policy as video_engine_policy

    _mock_llm_scaffolding(monkeypatch)
    monkeypatch.setattr(
        video_engine_policy,
        "PORTRAIT_CAPABLE_VIDEO_ENGINES",
        video_engine_policy.PORTRAIT_CAPABLE_VIDEO_ENGINES - {"KLING_3_0"},
    )
    scene = {
        "id": "scene_b",
        "title": "B Scene",
        "action": "Bob runs.",
        "duration_seconds": 5,  # target_shots == 2
    }
    characters = [{"id": "char_b", "name": "Bob"}]
    location = {"description": "a street"}
    global_settings = {"aspect_ratio": "9:16"}

    class FixedEnsemble:
        def __init__(self, **kwargs):
            pass

        def competitive_generate(self, **kwargs):
            return SimpleNamespace(
                winner_index=0,
                winner_content={
                    "shots": [_valid_shot("KLING_3_0"), _valid_shot("KLING_3_0")]
                },
                scores=[1.0],
                reasoning="best",
                models_used=["gpt-4o"],
            )

    monkeypatch.setattr(sd, "LLMEnsemble", FixedEnsemble)

    shots = sd.competitive_decompose_scene(
        scene,
        characters,
        location,
        global_settings,
        runtime_snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )

    assert len(shots) == 2
    assert all(shot["target_api"] == "AUTO" for shot in shots)
    assert all(
        shot["target_api_policy_reason"] == "aspect_incompatible" for shot in shots
    )
