"""Unit tests for domain/scene_decomposer.py's WS2 (Google-first) routing data:
API_REGISTRY, PURPOSE_API_RANKING, BILLING_PROVIDERS, and rank_apis_for_purpose().

Scope: GEMINI_OMNI's registration and ranking placement per the WS2 spec
(config/prompts/pipeline_context.md + workflow_selector.py carry the parallel
shot-type-level wiring; those are covered by test_workflow_selector.py and
test_cascade_logic.py). This file is the previously-missing dedicated
coverage for scene_decomposer.py's own purpose-ranking exports — the
production data was already landed (commits 13f1be52/dc66697b); this closes
the test-coverage gap on it.
"""
from __future__ import annotations

import domain.scene_decomposer as sd


# ---------------------------------------------------------------------------
# API_REGISTRY — GEMINI_OMNI entry shape
# ---------------------------------------------------------------------------

def test_gemini_omni_registered_in_api_registry():
    assert "GEMINI_OMNI" in sd.API_REGISTRY
    entry = sd.API_REGISTRY["GEMINI_OMNI"]
    assert entry["category"] == "native"
    assert entry["modality"] == "video"
    assert entry["status"] == "live"
    assert entry["native_audio"] is True
    assert entry["per_shot_cost"] == 0.56


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
    # SYNC_SO_V3 (lipsync, not a video engine) stays the top pick; GEMINI_OMNI
    # is the first VIDEO+native_audio candidate the dialogue-routing walk
    # (cinema/shots/controller.py:_resolve_dialogue_routing) will select.
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

def test_rank_apis_for_purpose_action_motion_returns_gemini_omni_first():
    ranked = sd.rank_apis_for_purpose("action_motion")
    assert ranked[0][0] == "GEMINI_OMNI"
    assert ranked[0][1]["status"] == "live"


def test_rank_apis_for_purpose_respects_max_cost_excluding_gemini_omni():
    # GEMINI_OMNI's per_shot_cost is 0.56; a budget cap below that must skip it.
    ranked = sd.rank_apis_for_purpose("action_motion", max_per_shot_cost=0.50)
    assert all(key != "GEMINI_OMNI" for key, _info in ranked)


def test_rank_apis_for_purpose_dialogue_close_up_gemini_omni_is_video():
    # Confirms the entry rank_apis_for_purpose surfaces for GEMINI_OMNI really
    # is a video engine (not accidentally shadowed by a differently-keyed
    # lipsync entry), matching the dialogue-native-audio walk's own filter.
    ranked = dict(sd.rank_apis_for_purpose("dialogue_close_up"))
    assert ranked["GEMINI_OMNI"]["modality"] == "video"
    assert ranked["GEMINI_OMNI"]["native_audio"] is True


def test_dialogue_native_audio_walk_selects_gemini_omni():
    # Mirrors cinema/shots/controller.py:_resolve_dialogue_routing's own walk
    # (first live video engine with native_audio=True in the purpose ranking)
    # without importing controller.py's heavy-dep-laden module.
    winner = None
    for key in sd.PURPOSE_API_RANKING["dialogue_close_up"]:
        info = sd.API_REGISTRY.get(key, {})
        if info.get("native_audio") and info.get("modality") == "video" and info.get("status") == "live":
            winner = key
            break
    assert winner == "GEMINI_OMNI"
