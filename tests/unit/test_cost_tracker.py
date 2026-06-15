"""Comprehensive tests for cost_tracker.py."""

import os
import sys
import tempfile

import pytest


from cost_tracker import API_COST_USD, CostEntry, CostTracker, PRICING, _detect_provider


# ===================================================================
# 1. _detect_provider — all branches
# ===================================================================


class TestDetectProvider:
    def test_claude_model(self):
        assert _detect_provider("claude-sonnet-4-20250514") == "anthropic"

    def test_claude_case_insensitive(self):
        assert _detect_provider("Claude-Opus-4") == "anthropic"

    def test_gpt_model(self):
        assert _detect_provider("gpt-4o") == "openai"

    def test_gpt_case_insensitive(self):
        assert _detect_provider("GPT-4.1-mini") == "openai"

    def test_o_prefix_model(self):
        assert _detect_provider("o4-mini") == "openai"

    def test_gemini_model(self):
        assert _detect_provider("gemini-2.5-flash") == "google"

    def test_gemini_case_insensitive(self):
        assert _detect_provider("Gemini-2.5-pro") == "google"

    def test_unknown_model(self):
        assert _detect_provider("llama-3") == "unknown"

    def test_empty_string(self):
        assert _detect_provider("") == "unknown"


# ===================================================================
# 2. log() — inserts record and returns CostEntry
# ===================================================================


class TestLog:
    def test_log_returns_cost_entry(self, cost_tracker):
        entry = cost_tracker.log(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            operation="script_generation",
            cost_usd=0.045,
            input_tokens=1000,
            output_tokens=2000,
            shot_id="shot_01",
            video_id="vid_01",
        )
        assert isinstance(entry, CostEntry)
        assert entry.provider == "anthropic"
        assert entry.model == "claude-sonnet-4-20250514"
        assert entry.operation == "script_generation"
        assert entry.cost_usd == 0.045
        assert entry.input_tokens == 1000
        assert entry.output_tokens == 2000
        assert entry.shot_id == "shot_01"
        assert entry.video_id == "vid_01"
        assert entry.timestamp  # non-empty ISO string

    def test_log_persists_to_db(self, cost_tracker):
        cost_tracker.log(
            provider="openai",
            model="gpt-4o",
            operation="classification",
            cost_usd=0.01,
        )
        row = cost_tracker.conn.execute(
            "SELECT COUNT(*) AS cnt FROM cost_log"
        ).fetchone()
        assert row["cnt"] == 1

    def test_log_defaults(self, cost_tracker):
        entry = cost_tracker.log(
            provider="google",
            model="gemini-2.5-flash",
            operation="draft",
            cost_usd=0.001,
        )
        assert entry.input_tokens == 0
        assert entry.output_tokens == 0
        assert entry.shot_id == ""
        assert entry.video_id == ""


# ===================================================================
# 3. log_llm() — correct cost calculation and provider detection
# ===================================================================


class TestLogLLM:
    def test_cost_calculation_claude(self, cost_tracker):
        model = "claude-sonnet-4-20250514"
        input_tokens = 1_000_000
        output_tokens = 1_000_000
        entry = cost_tracker.log_llm(
            model=model,
            operation="script_generation",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        expected_cost = (
            (input_tokens / 1_000_000) * PRICING[model]["input"]
            + (output_tokens / 1_000_000) * PRICING[model]["output"]
        )
        assert entry.cost_usd == pytest.approx(expected_cost)
        assert entry.provider == "anthropic"

    def test_cost_calculation_openai(self, cost_tracker):
        model = "gpt-4o"
        entry = cost_tracker.log_llm(
            model=model,
            operation="classification",
            input_tokens=500_000,
            output_tokens=100_000,
        )
        expected_cost = (
            (500_000 / 1_000_000) * PRICING[model]["input"]
            + (100_000 / 1_000_000) * PRICING[model]["output"]
        )
        assert entry.cost_usd == pytest.approx(expected_cost)
        assert entry.provider == "openai"

    def test_cost_calculation_google(self, cost_tracker):
        model = "gemini-2.5-flash"
        entry = cost_tracker.log_llm(
            model=model,
            operation="draft",
            input_tokens=2_000_000,
            output_tokens=500_000,
        )
        expected_cost = (
            (2_000_000 / 1_000_000) * PRICING[model]["input"]
            + (500_000 / 1_000_000) * PRICING[model]["output"]
        )
        assert entry.cost_usd == pytest.approx(expected_cost)
        assert entry.provider == "google"

    def test_o_prefix_model_provider(self, cost_tracker):
        model = "o4-mini"
        entry = cost_tracker.log_llm(
            model=model,
            operation="reasoning",
            input_tokens=100_000,
            output_tokens=50_000,
        )
        assert entry.provider == "openai"
        expected_cost = (
            (100_000 / 1_000_000) * PRICING[model]["input"]
            + (50_000 / 1_000_000) * PRICING[model]["output"]
        )
        assert entry.cost_usd == pytest.approx(expected_cost)


# ===================================================================
# 4. log_llm() with unknown model — falls back to $0.00
# ===================================================================


class TestLogLLMUnknownModel:
    def test_unknown_model_zero_cost(self, cost_tracker):
        entry = cost_tracker.log_llm(
            model="llama-3-70b",
            operation="generation",
            input_tokens=1_000_000,
            output_tokens=500_000,
        )
        assert entry.cost_usd == 0.0
        assert entry.provider == "unknown"

    def test_unknown_model_still_records_tokens(self, cost_tracker):
        entry = cost_tracker.log_llm(
            model="mistral-large",
            operation="chat",
            input_tokens=200,
            output_tokens=300,
        )
        assert entry.input_tokens == 200
        assert entry.output_tokens == 300


# ===================================================================
# 5. log_api() — direct cost logging
# ===================================================================


class TestLogAPI:
    def test_log_api_returns_entry(self, cost_tracker):
        entry = cost_tracker.log_api(
            provider="fal",
            model="kling-v2",
            operation="video_generation",
            cost_usd=0.15,
            shot_id="shot_03",
            video_id="vid_02",
        )
        assert isinstance(entry, CostEntry)
        assert entry.provider == "fal"
        assert entry.cost_usd == 0.15
        assert entry.input_tokens == 0
        assert entry.output_tokens == 0

    def test_log_api_persists(self, cost_tracker):
        cost_tracker.log_api(
            provider="runway",
            model="gen3",
            operation="video_generation",
            cost_usd=0.25,
        )
        row = cost_tracker.conn.execute(
            "SELECT cost_usd FROM cost_log WHERE provider = 'runway'"
        ).fetchone()
        assert row["cost_usd"] == pytest.approx(0.25)


# ===================================================================
# 6. get_video_cost() — aggregation with multiple records
# ===================================================================


class TestGetVideoCost:
    def test_aggregation(self, cost_tracker):
        vid = "vid_agg"
        # LLM call
        cost_tracker.log_llm(
            model="claude-sonnet-4-20250514",
            operation="script_generation",
            input_tokens=100_000,
            output_tokens=50_000,
            video_id=vid,
            shot_id="shot_a",
        )
        # API call
        cost_tracker.log_api(
            provider="fal",
            model="kling-v2",
            operation="video_generation",
            cost_usd=0.15,
            video_id=vid,
            shot_id="shot_b",
        )
        # Another LLM call, same video
        cost_tracker.log_llm(
            model="gpt-4o",
            operation="classification",
            input_tokens=50_000,
            output_tokens=10_000,
            video_id=vid,
            shot_id="shot_a",
        )

        result = cost_tracker.get_video_cost(vid)

        assert result["total_usd"] > 0
        assert result["llm_usd"] > 0
        assert result["api_usd"] == pytest.approx(0.15)
        assert result["total_usd"] == pytest.approx(
            result["llm_usd"] + result["api_usd"]
        )
        assert "anthropic" in result["breakdown_by_provider"]
        assert "fal" in result["breakdown_by_provider"]
        assert "openai" in result["breakdown_by_provider"]
        assert "script_generation" in result["breakdown_by_operation"]
        assert "video_generation" in result["breakdown_by_operation"]
        assert "classification" in result["breakdown_by_operation"]
        # shot_a and shot_b
        assert result["shot_count"] == 2

    # ===============================================================
    # 7. get_video_cost() — empty result
    # ===============================================================

    def test_empty_video_cost(self, cost_tracker):
        result = cost_tracker.get_video_cost("nonexistent_video")
        assert result["total_usd"] == 0.0
        assert result["llm_usd"] == 0.0
        assert result["api_usd"] == 0.0
        assert result["breakdown_by_provider"] == {}
        assert result["breakdown_by_operation"] == {}
        assert result["shot_count"] == 0


# ===================================================================
# 8. get_session_cost() — total within 24h
# ===================================================================


class TestGetSessionCost:
    def test_session_cost_includes_recent(self, cost_tracker):
        cost_tracker.log(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            operation="gen",
            cost_usd=0.10,
        )
        cost_tracker.log(
            provider="openai",
            model="gpt-4o",
            operation="gen",
            cost_usd=0.05,
        )
        total = cost_tracker.get_session_cost()
        assert total == pytest.approx(0.15)

    def test_session_cost_empty(self, cost_tracker):
        assert cost_tracker.get_session_cost() == 0.0


# ===================================================================
# 9. get_cost_per_second() — normal and division by zero
# ===================================================================


class TestGetCostPerSecond:
    def test_normal_calculation(self, cost_tracker):
        vid = "vid_cps"
        cost_tracker.log_api(
            provider="fal",
            model="kling-v2",
            operation="video_generation",
            cost_usd=0.30,
            video_id=vid,
        )
        cps = cost_tracker.get_cost_per_second(vid, video_duration_seconds=10.0)
        assert cps == pytest.approx(0.03)

    def test_zero_duration_returns_zero(self, cost_tracker):
        vid = "vid_zero"
        cost_tracker.log_api(
            provider="fal",
            model="kling-v2",
            operation="video_generation",
            cost_usd=0.30,
            video_id=vid,
        )
        cps = cost_tracker.get_cost_per_second(vid, video_duration_seconds=0.0)
        assert cps == 0.0

    def test_negative_duration_returns_zero(self, cost_tracker):
        cps = cost_tracker.get_cost_per_second("vid_neg", video_duration_seconds=-5.0)
        assert cps == 0.0


# ===================================================================
# 10. check_budget() — within budget and over budget
# ===================================================================


class TestCheckBudget:
    def test_within_budget(self, cost_tracker):
        within, alternatives = cost_tracker.check_budget(
            budget_remaining_usd=1.00, estimated_cost_usd=0.50
        )
        assert within is True
        assert alternatives == []

    def test_exactly_at_budget(self, cost_tracker):
        within, alternatives = cost_tracker.check_budget(
            budget_remaining_usd=0.50, estimated_cost_usd=0.50
        )
        assert within is True
        assert alternatives == []

    def test_over_budget(self, cost_tracker):
        within, alternatives = cost_tracker.check_budget(
            budget_remaining_usd=0.10, estimated_cost_usd=0.50
        )
        assert within is False
        assert len(alternatives) > 0
        # Verify alternatives are actionable strings
        for alt in alternatives:
            assert isinstance(alt, str)
            assert len(alt) > 10


# ===================================================================
# 11. get_summary() — no data
# ===================================================================


class TestGetSummaryEmpty:
    def test_no_data(self, cost_tracker):
        summary = cost_tracker.get_summary()
        assert summary == "No cost data recorded yet."


# ===================================================================
# 12. get_summary() — with data, formatted output
# ===================================================================


class TestGetSummaryWithData:
    def test_summary_contains_expected_sections(self, cost_tracker):
        cost_tracker.log_llm(
            model="claude-sonnet-4-20250514",
            operation="script_generation",
            input_tokens=500_000,
            output_tokens=100_000,
        )
        cost_tracker.log_api(
            provider="fal",
            model="kling-v2",
            operation="video_generation",
            cost_usd=0.15,
        )

        summary = cost_tracker.get_summary()

        # Header
        assert "CINEMA PIPELINE COST SUMMARY" in summary
        # Total spend line
        assert "Total Spend:" in summary
        assert "$" in summary
        # Call counts
        assert "LLM Calls:" in summary
        assert "API Calls:" in summary
        # Token totals
        assert "Total Input Tokens:" in summary
        assert "Total Output Tokens:" in summary
        # Provider breakdown
        assert "Spend by Provider" in summary
        assert "anthropic" in summary
        assert "fal" in summary
        # Operation breakdown
        assert "Spend by Operation" in summary
        assert "script_generation" in summary
        assert "video_generation" in summary
        # Efficiency section
        assert "Efficiency Metrics" in summary
        assert "Avg cost per LLM call" in summary

    def test_summary_api_only(self, cost_tracker):
        """When only API calls exist, efficiency metrics may differ."""
        cost_tracker.log_api(
            provider="runway",
            model="gen3",
            operation="video_generation",
            cost_usd=0.25,
        )
        summary = cost_tracker.get_summary()
        assert "CINEMA PIPELINE COST SUMMARY" in summary
        assert "API Calls:" in summary
        # No LLM calls, so no efficiency metrics section
        assert "Avg cost per LLM call" not in summary


# ===================================================================
# 13. record_api_call() — table lookup, override, unknown, accumulator,
#                         provider derivation, return value
# ===================================================================


class TestRecordAPICall:
    def test_record_api_call_known_api_uses_table(self, cost_tracker):
        """Known api_name pulls cost from API_COST_USD table."""
        cost = cost_tracker.record_api_call("SORA_2")
        assert cost == pytest.approx(API_COST_USD["SORA_2"])

    def test_record_api_call_explicit_override(self, cost_tracker):
        """Explicit cost_usd wins over the table lookup."""
        cost = cost_tracker.record_api_call("SORA_2", cost_usd=0.99)
        assert cost == pytest.approx(0.99)

    def test_record_api_call_unknown_warns_and_zero(self, cost_tracker):
        """Unknown API emits UserWarning and records $0.00 cost."""
        with pytest.warns(UserWarning, match="Unknown API"):
            cost = cost_tracker.record_api_call("TOTALLY_UNKNOWN_API_XYZ")
        assert cost == pytest.approx(0.0)
        # Accumulator must not move on the zero-cost path — the budget
        # gate would otherwise drift on every unknown-API call.
        assert cost_tracker.spent_usd == pytest.approx(0.0)

    def test_record_api_call_updates_spent_usd(self, cost_tracker):
        """spent_usd accumulator reflects each recorded call."""
        assert cost_tracker.spent_usd == pytest.approx(0.0)
        cost_tracker.record_api_call("VEO")
        cost_tracker.record_api_call("FLUX_PRO")
        expected = API_COST_USD["VEO"] + API_COST_USD["FLUX_PRO"]
        assert cost_tracker.spent_usd == pytest.approx(expected)

    # Lipsync is mandatory for dialogue shots (F1b). The controller records the
    # cascade-winning engine as LIPSYNC_<engine> (cinema/shots/controller.py).
    # Every name the cascade can emit (lip_sync.py `extra={"engine": ...}`) MUST
    # be priced, or the budget gate silently undercounts each dialogue shot.
    @pytest.mark.parametrize("cascade_engine", [
        "syncSoV3", "MuseTalk", "LatentSync", "SyncV2",
        "hedra", "kling", "omnihuman", "aurora",
        None,  # cascade reports no engine → controller uses "default"
    ])
    def test_record_api_call_lipsync_engine_priced(self, cost_tracker, cascade_engine):
        """Each lipsync cascade engine resolves to a non-zero, no-warning cost."""
        import warnings
        # Mirror the controller's namespacing: LIPSYNC_<engine|default>.
        api_name = f"LIPSYNC_{cascade_engine or 'default'}"
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any "Unknown API" warning fails here
            cost = cost_tracker.record_api_call(api_name, operation="lipsync")
        assert cost > 0.0, f"{api_name} priced at $0 — budget gate would undercount"

    @pytest.mark.parametrize("api_name,expected_provider", [
        ("SORA_2", "openai"),
        ("VEO", "google"),
        ("FLUX_PULID", "fal"),
        ("RUNWAY_GEN4", "runway"),
        ("KLING_3_0", "kling"),
        ("TOTALLY_UNKNOWN_API_XYZ", "unknown"),
    ])
    def test_record_api_call_provider_derivation(self, cost_tracker, api_name, expected_provider):
        """Provider is derived from api_name prefix via the internal map."""
        if expected_provider == "unknown":
            with pytest.warns(UserWarning):
                cost_tracker.record_api_call(api_name)
        else:
            cost_tracker.record_api_call(api_name)
        row = cost_tracker.conn.execute(
            "SELECT provider FROM cost_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["provider"] == expected_provider

    def test_record_api_call_returns_cost(self, cost_tracker):
        """Return value equals the cost actually recorded."""
        returned = cost_tracker.record_api_call("FLUX_KONTEXT", cost_usd=0.04)
        assert returned == pytest.approx(0.04)
        row = cost_tracker.conn.execute(
            "SELECT cost_usd FROM cost_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["cost_usd"] == pytest.approx(0.04)

    # --- Image-backend provenance (pod-PuLID vs FAL fallback) -------------
    # The keyframe cost site used to hardcode FLUX_KONTEXT/QUALITY_MAX from
    # quality_tier, so a generation that ran on the ComfyUI/PuLID pod was
    # indistinguishable from a FAL fallback in cost_log (both provider='fal').
    # The backend that actually ran is now threaded out of generate_ai_broll
    # and recorded here; pod backends must log a provider distinct from 'fal'.
    @pytest.mark.parametrize("api_name,expected_provider", [
        ("COMFYUI_PULID", "comfyui"),       # production pod PuLID
        ("QUALITY_MAX",   "comfyui"),       # N=8 best-of — also the pod
        ("FLUX_KONTEXT",  "fal"),           # FAL identity-preserving fallback
        ("FLUX_PRO",      "fal"),           # FAL last-resort
        ("FLUX_SCHNELL",  "fal"),           # FAL fast fallback
        ("POLLINATIONS",  "pollinations"),  # free fallback
    ])
    def test_image_backend_provider_provenance(self, cost_tracker, api_name, expected_provider):
        cost_tracker.record_api_call(api_name, operation="keyframe_generation")
        row = cost_tracker.conn.execute(
            "SELECT provider, model FROM cost_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["provider"] == expected_provider
        assert row["model"] == api_name

    def test_new_image_backend_names_have_cost_entries(self):
        """Threaded backend names must exist in API_COST_USD so real
        generations don't warn + silently record $0.00."""
        for name in ("COMFYUI_PULID", "FLUX_SCHNELL", "POLLINATIONS"):
            assert name in API_COST_USD, f"{name} missing from API_COST_USD"
        assert API_COST_USD["COMFYUI_PULID"] > 0.0   # pod GPU time isn't free
        assert API_COST_USD["POLLINATIONS"] == 0.0   # pollinations is free


class TestRecordAPICallAudioTracking:
    """M-B2 closure (cycle-16 Tier B): audio sites now have API_COST_USD
    entries + record_api_call invocations at success points.

    Pre-fix gaps surfaced by Tier B run:
      - STABILITY_FOLEY had entry but no production invocation (Lane V confirmed)
      - SUNO_V5 had neither entry nor invocation
      - FAL_STABLE_AUDIO had neither entry nor invocation (production BGM path)
      - ELEVENLABS had neither entry nor invocation (TTS path; Cartesia was
        added cycle-15 v0.9.8 but ElevenLabs asymmetry was filed for later)

    Post-fix all four entries exist; invocations live at the success-path
    return points of each generator (or call-site for ElevenLabs to mirror
    Cartesia pattern).
    """

    @pytest.mark.parametrize("api_name,expected_cost", [
        ("STABILITY_FOLEY", 0.03),
        ("CARTESIA_SONIC_2", 0.008),
        ("ELEVENLABS", 0.01),
        ("SUNO_V5", 0.50),
        ("FAL_STABLE_AUDIO", 0.10),
    ])
    def test_audio_api_costs_present_in_table(self, api_name, expected_cost):
        """Each audio API has a cost-table entry (M-B2 §1 closure)."""
        assert api_name in API_COST_USD
        assert API_COST_USD[api_name] == pytest.approx(expected_cost)

    def test_stability_foley_records_via_table(self, cost_tracker):
        """STABILITY_FOLEY recording exercised — Lane V flagged zero
        production invocation pre-fix."""
        cost = cost_tracker.record_api_call("STABILITY_FOLEY", operation="scene_foley")
        assert cost == pytest.approx(0.03)
        assert cost_tracker.spent_usd == pytest.approx(0.03)

    def test_elevenlabs_records_via_table(self, cost_tracker):
        cost = cost_tracker.record_api_call("ELEVENLABS", operation="dialogue_tts")
        assert cost == pytest.approx(0.01)

    def test_suno_v5_records_via_table(self, cost_tracker):
        cost = cost_tracker.record_api_call("SUNO_V5", operation="bgm")
        assert cost == pytest.approx(0.50)

    def test_fal_stable_audio_records_via_table(self, cost_tracker):
        cost = cost_tracker.record_api_call("FAL_STABLE_AUDIO", operation="bgm")
        assert cost == pytest.approx(0.10)

    def test_audio_tier_b_cumulative_total(self, cost_tracker):
        """A canonical Tier B-shape run (1 line ElevenLabs + 1 BGM FAL +
        1 foley) accumulates the expected sum."""
        cost_tracker.record_api_call("ELEVENLABS", operation="dialogue_tts")
        cost_tracker.record_api_call("FAL_STABLE_AUDIO", operation="bgm")
        cost_tracker.record_api_call("STABILITY_FOLEY", operation="scene_foley")
        expected = 0.01 + 0.10 + 0.03
        assert cost_tracker.spent_usd == pytest.approx(expected)


# ===================================================================
# 14. Budget gate — would_exceed() and is_over_budget()
# ===================================================================


class TestBudgetGate:
    def test_would_exceed_with_no_budget_returns_false(self, db_path):
        """Without a budget cap, would_exceed always returns False."""
        tracker = CostTracker(db_path=db_path, budget_usd=None)
        assert tracker.would_exceed("SORA_2") is False
        tracker.close()

    def test_would_exceed_under_budget(self, db_path):
        """Returns False when one more LTX call stays within a $1.00 cap."""
        tracker = CostTracker(db_path=db_path, budget_usd=1.00)
        tracker.spent_usd = 0.30
        # Lock the invariant so a future tariff change for LTX breaks
        # the precondition (test author updates) instead of silently
        # rendering the assertion vacuous.
        assert tracker.spent_usd + API_COST_USD["LTX"] < tracker.budget_usd
        assert tracker.would_exceed("LTX") is False
        tracker.close()

    def test_would_exceed_over_budget(self, db_path):
        """Returns True when one more SORA_2 call would push spent past the cap."""
        tracker = CostTracker(db_path=db_path, budget_usd=1.00)
        tracker.spent_usd = 0.80
        assert tracker.spent_usd + API_COST_USD["SORA_2"] > tracker.budget_usd
        assert tracker.would_exceed("SORA_2") is True
        tracker.close()

    def test_is_over_budget_no_cap(self, db_path):
        """Without a budget cap, is_over_budget always returns False."""
        tracker = CostTracker(db_path=db_path, budget_usd=None)
        tracker.record_api_call("SORA_2")
        tracker.record_api_call("RUNWAY_GEN4")
        assert tracker.is_over_budget() is False
        tracker.close()

    def test_is_over_budget_post_record(self, db_path):
        """After recording enough calls to exceed the cap, is_over_budget returns True."""
        tracker = CostTracker(db_path=db_path, budget_usd=0.50)
        assert API_COST_USD["SORA_2"] > tracker.budget_usd  # one call exceeds cap
        tracker.record_api_call("SORA_2")
        assert tracker.is_over_budget() is True
        tracker.close()

    # NF-2 regression (docs/STRATEGIC_REVIEW-2026-06-10.md): make_project()
    # defaults budget_limit_usd to 0 and the settings UI documents 0 as
    # "unlimited" — a zero budget must behave like NO budget, not like a cap
    # the first recorded call exceeds.

    def test_zero_budget_is_unlimited_for_is_over_budget(self, db_path):
        """budget_usd=0.0 (the default-project value) must not trip the gate."""
        tracker = CostTracker(db_path=db_path, budget_usd=0.0)
        tracker.record_api_call("KLING_NATIVE")
        assert tracker.is_over_budget() is False
        tracker.close()

    def test_zero_budget_is_unlimited_for_would_exceed(self, db_path):
        """budget_usd=0 (int form) must not trip the pre-spend check either."""
        tracker = CostTracker(db_path=db_path, budget_usd=0)
        assert tracker.would_exceed("SORA_2") is False
        tracker.close()


class TestDbPathResolution:
    """T7: CostTracker resolves db_path from the EXPERIMENTS_DB_PATH env var
    (the same var config.settings.experiments_db_path reads), so configuring
    it actually takes effect. Precedence: explicit arg > env > legacy default."""

    def test_env_var_honored_when_no_explicit_path(self, tmp_path, monkeypatch):
        target = str(tmp_path / "env.db")
        monkeypatch.setenv("EXPERIMENTS_DB_PATH", target)
        tracker = CostTracker()
        assert tracker.db_path == target
        tracker.close()

    def test_explicit_arg_overrides_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXPERIMENTS_DB_PATH", str(tmp_path / "env.db"))
        explicit = str(tmp_path / "explicit.db")
        tracker = CostTracker(db_path=explicit)
        assert tracker.db_path == explicit
        tracker.close()

    def test_legacy_default_when_env_unset(self, tmp_path, monkeypatch):
        monkeypatch.delenv("EXPERIMENTS_DB_PATH", raising=False)
        monkeypatch.chdir(tmp_path)  # keep the relative default db inside tmp
        (tmp_path / "data").mkdir()
        tracker = CostTracker()
        assert tracker.db_path == "data/experiments.db"
        tracker.close()


class TestVerifiedPricePins:
    """Pins for prices VERIFIED against provider pages (not estimates).
    Operator INFO 2026-06-11T02:01:00Z: without a direct pin, an accidental
    revert of a verified price passes the suite (test:517 passes an explicit
    override, so it never reads the constant)."""

    def test_flux_kontext_price_is_the_verified_2026_06_11_value(self):
        from cost_tracker import API_COST_USD
        # fal.ai model page for flux-pro/kontext/max/multi (the variant
        # production calls): "$0.08 per image". The old 0.04 was the non-max tier.
        assert API_COST_USD["FLUX_KONTEXT"] == 0.08


class TestApiCostUsdCompleteness:
    """Every dispatched video engine must be priced, else would_exceed() returns
    0.0 for it and the pre-spend budget gate (controller.generate_motion_take,
    ADR-022) silently admits it near budget. Capacity audit wf_6be2ee18-f4b."""

    def test_seedance_priced_in_api_cost_usd(self):
        assert "SEEDANCE" in API_COST_USD
        assert API_COST_USD["SEEDANCE"] > 0

    def test_fal_svd_priced_in_api_cost_usd(self):
        assert "FAL_SVD" in API_COST_USD
        assert API_COST_USD["FAL_SVD"] > 0

    @pytest.mark.parametrize("engine", ["ACT_ONE", "LIVE_PORTRAIT", "VIGGLE"])
    def test_performance_capture_engines_priced_in_api_cost_usd(self, engine):
        assert engine in API_COST_USD
        assert API_COST_USD[engine] > 0
