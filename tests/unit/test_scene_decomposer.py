"""Typed compatibility and purpose-ranking tests for scene decomposition."""
from __future__ import annotations

from datetime import date

import domain.scene_decomposer as sd
from domain.provider_catalog import RuntimeSnapshot


PRE_SUNSET = date(2026, 9, 23)


def _fal_snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        credentials={"fal_key"},
        modules={"fal_client"},
    )


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


def test_nonvideo_rankings_do_not_change_with_video_runtime_snapshot():
    without_runtime = sd.rank_apis_for_purpose(
        "narration",
        snapshot=RuntimeSnapshot(),
        on_date=PRE_SUNSET,
    )
    with_fal_runtime = sd.rank_apis_for_purpose(
        "narration",
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert without_runtime == with_fal_runtime
