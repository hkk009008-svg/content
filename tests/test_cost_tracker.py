"""Comprehensive tests for cost_tracker.py."""

import os
import sys
import tempfile

import pytest

# Ensure project root is on sys.path so we can import cost_tracker directly.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cost_tracker import CostEntry, CostTracker, PRICING, _detect_provider


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
