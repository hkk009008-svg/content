"""Tests for llm_router.py — pure logic only, no API calls or mocking."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import copy
import time

import pytest

from llm_router import (
    COST_PER_1M,
    ROUTING_TABLE,
    CinemaLLMRouter,
    CostEntry,
    LLMResponse,
    _calc_cost,
    _provider_for_model,
    get_routing_table,
)


# ---------------------------------------------------------------------------
# _provider_for_model
# ---------------------------------------------------------------------------


class TestProviderForModel:
    def test_claude_models_return_anthropic(self):
        assert _provider_for_model("claude-sonnet-4-20250514") == "anthropic"
        assert _provider_for_model("claude-opus-4-20250918") == "anthropic"
        assert _provider_for_model("claude-haiku-4-5") == "anthropic"
        assert _provider_for_model("claude-anything") == "anthropic"

    def test_gemini_models_return_google(self):
        assert _provider_for_model("gemini-2.5-flash") == "google"
        assert _provider_for_model("gemini-2.5-pro") == "google"
        assert _provider_for_model("gemini-future-model") == "google"

    def test_other_models_return_openai(self):
        assert _provider_for_model("gpt-4.1") == "openai"
        assert _provider_for_model("gpt-4.1-mini") == "openai"
        assert _provider_for_model("gpt-4o") == "openai"
        assert _provider_for_model("o4-mini") == "openai"
        assert _provider_for_model("some-unknown-model") == "openai"


# ---------------------------------------------------------------------------
# _calc_cost
# ---------------------------------------------------------------------------


class TestCalcCost:
    def test_known_model_cost(self):
        # claude-sonnet-4: input=3.00, output=15.00 per 1M
        cost = _calc_cost("claude-sonnet-4-20250514", 1_000_000, 1_000_000)
        assert cost == pytest.approx(3.00 + 15.00)

    def test_known_model_partial_tokens(self):
        # gpt-4.1-mini: input=0.40, output=1.60 per 1M
        cost = _calc_cost("gpt-4.1-mini", 500, 200)
        expected = (500 * 0.40 + 200 * 1.60) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_zero_tokens(self):
        cost = _calc_cost("claude-sonnet-4-20250514", 0, 0)
        assert cost == 0.0

    def test_unknown_model_returns_zero(self):
        cost = _calc_cost("nonexistent-model", 10_000, 5_000)
        assert cost == 0.0

    def test_all_known_models_produce_positive_cost(self):
        for model in COST_PER_1M:
            cost = _calc_cost(model, 1000, 1000)
            assert cost > 0.0, f"{model} should produce positive cost"

    def test_output_only(self):
        cost = _calc_cost("gpt-4.1-nano", 0, 1_000_000)
        assert cost == pytest.approx(0.40)

    def test_input_only(self):
        cost = _calc_cost("gpt-4.1-nano", 1_000_000, 0)
        assert cost == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# COST_PER_1M dict
# ---------------------------------------------------------------------------


class TestCostTable:
    def test_all_entries_have_input_and_output(self):
        for model, rates in COST_PER_1M.items():
            assert "input" in rates, f"{model} missing 'input' rate"
            assert "output" in rates, f"{model} missing 'output' rate"

    def test_all_rates_are_positive(self):
        for model, rates in COST_PER_1M.items():
            assert rates["input"] > 0, f"{model} input rate should be positive"
            assert rates["output"] > 0, f"{model} output rate should be positive"

    def test_expected_models_present(self):
        expected = [
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250918",
            "claude-haiku-4-5",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "gpt-4o",
            "o4-mini",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        ]
        for model in expected:
            assert model in COST_PER_1M, f"{model} missing from COST_PER_1M"


# ---------------------------------------------------------------------------
# ROUTING_TABLE dict
# ---------------------------------------------------------------------------


class TestRoutingTable:
    def test_all_entries_have_primary_and_fallback(self):
        for task_type, route in ROUTING_TABLE.items():
            assert "primary" in route, f"{task_type} missing 'primary'"
            assert "fallback" in route, f"{task_type} missing 'fallback'"

    def test_all_primary_models_in_cost_table(self):
        for task_type, route in ROUTING_TABLE.items():
            assert route["primary"] in COST_PER_1M, (
                f"{task_type} primary '{route['primary']}' not in COST_PER_1M"
            )

    def test_all_fallback_models_in_cost_table(self):
        for task_type, route in ROUTING_TABLE.items():
            assert route["fallback"] in COST_PER_1M, (
                f"{task_type} fallback '{route['fallback']}' not in COST_PER_1M"
            )

    def test_expected_task_types_present(self):
        expected = [
            "creative_scene",
            "structured_json",
            "video_analysis",
            "classification",
            "quality_review",
            "identity_vision",
            "coherence_vision",
            "shot_quality",
            "scene_decompose",
            "chief_director",
        ]
        for task in expected:
            assert task in ROUTING_TABLE, f"'{task}' missing from ROUTING_TABLE"

    def test_primary_differs_from_fallback(self):
        for task_type, route in ROUTING_TABLE.items():
            assert route["primary"] != route["fallback"], (
                f"{task_type}: primary and fallback are the same model"
            )


# ---------------------------------------------------------------------------
# get_routing_table
# ---------------------------------------------------------------------------


class TestGetRoutingTable:
    def test_no_settings_returns_deep_copy(self):
        table = get_routing_table()
        assert table == ROUTING_TABLE
        # Verify it is a copy, not the same object
        assert table is not ROUTING_TABLE
        for key in table:
            assert table[key] is not ROUTING_TABLE[key]

    def test_none_settings_returns_deep_copy(self):
        table = get_routing_table(settings=None)
        assert table == ROUTING_TABLE

    def test_empty_settings_returns_unmodified(self):
        table = get_routing_table(settings={})
        assert table == ROUTING_TABLE

    def test_creative_llm_override_claude_sonnet(self):
        table = get_routing_table(settings={"creative_llm": "claude-sonnet"})
        assert table["creative_scene"]["primary"] == "claude-sonnet-4-20250514"
        assert table["scene_decompose"]["primary"] == "claude-sonnet-4-20250514"
        assert table["chief_director"]["primary"] == "claude-sonnet-4-20250514"

    def test_creative_llm_override_gpt4o(self):
        table = get_routing_table(settings={"creative_llm": "gpt-4o"})
        assert table["creative_scene"]["primary"] == "gpt-4o"
        assert table["scene_decompose"]["primary"] == "gpt-4o"
        assert table["chief_director"]["primary"] == "gpt-4o"

    def test_creative_llm_auto_does_not_change(self):
        table = get_routing_table(settings={"creative_llm": "auto"})
        assert table == ROUTING_TABLE

    def test_creative_llm_unknown_value_does_not_change(self):
        table = get_routing_table(settings={"creative_llm": "unknown-model"})
        assert table == ROUTING_TABLE

    def test_quality_judge_llm_override_claude_opus(self):
        table = get_routing_table(settings={"quality_judge_llm": "claude-opus"})
        assert table["quality_review"]["primary"] == "claude-opus-4-20250918"

    def test_quality_judge_llm_override_gpt4o(self):
        table = get_routing_table(settings={"quality_judge_llm": "gpt-4o"})
        assert table["quality_review"]["primary"] == "gpt-4o"

    def test_quality_judge_llm_override_gemini_pro(self):
        table = get_routing_table(settings={"quality_judge_llm": "gemini-pro"})
        assert table["quality_review"]["primary"] == "gemini-2.5-pro"

    def test_quality_judge_llm_auto_does_not_change(self):
        table = get_routing_table(settings={"quality_judge_llm": "auto"})
        assert table["quality_review"]["primary"] == ROUTING_TABLE["quality_review"]["primary"]

    def test_both_overrides_together(self):
        table = get_routing_table(settings={
            "creative_llm": "gpt-4o",
            "quality_judge_llm": "gemini-pro",
        })
        assert table["creative_scene"]["primary"] == "gpt-4o"
        assert table["scene_decompose"]["primary"] == "gpt-4o"
        assert table["chief_director"]["primary"] == "gpt-4o"
        assert table["quality_review"]["primary"] == "gemini-2.5-pro"

    def test_does_not_mutate_original_routing_table(self):
        original = copy.deepcopy(ROUTING_TABLE)
        get_routing_table(settings={"creative_llm": "gpt-4o"})
        assert ROUTING_TABLE == original

    def test_creative_override_does_not_affect_other_tasks(self):
        table = get_routing_table(settings={"creative_llm": "gpt-4o"})
        # These should remain unchanged
        assert table["structured_json"]["primary"] == ROUTING_TABLE["structured_json"]["primary"]
        assert table["video_analysis"]["primary"] == ROUTING_TABLE["video_analysis"]["primary"]
        assert table["classification"]["primary"] == ROUTING_TABLE["classification"]["primary"]
        assert table["quality_review"]["primary"] == ROUTING_TABLE["quality_review"]["primary"]

    def test_fallbacks_unchanged_by_overrides(self):
        table = get_routing_table(settings={
            "creative_llm": "gpt-4o",
            "quality_judge_llm": "gemini-pro",
        })
        for task_type in ROUTING_TABLE:
            assert table[task_type]["fallback"] == ROUTING_TABLE[task_type]["fallback"]


# ---------------------------------------------------------------------------
# CostEntry dataclass
# ---------------------------------------------------------------------------


class TestCostEntry:
    def test_auto_fills_timestamp(self):
        before = time.time()
        entry = CostEntry(
            model="gpt-4.1",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
        )
        after = time.time()
        assert before <= entry.timestamp <= after

    def test_explicit_timestamp_preserved(self):
        entry = CostEntry(
            model="gpt-4.1",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            timestamp=12345.0,
        )
        assert entry.timestamp == 12345.0

    def test_zero_timestamp_gets_replaced(self):
        entry = CostEntry(
            model="gpt-4.1",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            timestamp=0.0,
        )
        assert entry.timestamp > 0.0

    def test_default_cache_fields(self):
        entry = CostEntry(
            model="gpt-4.1",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
        )
        assert entry.cache_read_tokens == 0
        assert entry.cache_write_tokens == 0

    def test_explicit_cache_fields(self):
        entry = CostEntry(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.01,
            cache_read_tokens=200,
            cache_write_tokens=100,
        )
        assert entry.cache_read_tokens == 200
        assert entry.cache_write_tokens == 100


# ---------------------------------------------------------------------------
# LLMResponse dataclass
# ---------------------------------------------------------------------------


class TestLLMResponse:
    def test_basic_creation(self):
        resp = LLMResponse(
            content="Hello world",
            model="gpt-4.1",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0001,
        )
        assert resp.content == "Hello world"
        assert resp.model == "gpt-4.1"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5
        assert resp.cost_usd == 0.0001
        assert resp.tool_calls is None

    def test_with_tool_calls(self):
        calls = [{"id": "1", "name": "fn", "input": {}}]
        resp = LLMResponse(
            content="",
            model="gpt-4.1",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0001,
            tool_calls=calls,
        )
        assert resp.tool_calls == calls


# ---------------------------------------------------------------------------
# CinemaLLMRouter — pure logic (no API calls)
# ---------------------------------------------------------------------------


class TestCinemaLLMRouter:
    def test_get_cost_summary_empty(self):
        router = CinemaLLMRouter()
        summary = router.get_cost_summary()
        assert summary["total_cost_usd"] == 0.0
        assert summary["total_calls"] == 0
        assert summary["by_provider"] == {}
        assert summary["by_model"] == {}

    def test_get_cost_summary_with_entries(self):
        router = CinemaLLMRouter()
        router._cost_log.append(CostEntry(
            model="gpt-4.1",
            provider="openai",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.006,
        ))
        router._cost_log.append(CostEntry(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            input_tokens=2000,
            output_tokens=1000,
            cost_usd=0.021,
        ))

        summary = router.get_cost_summary()
        assert summary["total_calls"] == 2
        assert summary["total_cost_usd"] == pytest.approx(0.027)
        assert summary["by_provider"]["openai"] == pytest.approx(0.006)
        assert summary["by_provider"]["anthropic"] == pytest.approx(0.021)
        assert summary["by_model"]["gpt-4.1"]["calls"] == 1
        assert summary["by_model"]["gpt-4.1"]["input_tokens"] == 1000
        assert summary["by_model"]["gpt-4.1"]["output_tokens"] == 500
        assert summary["by_model"]["gpt-4.1"]["cost_usd"] == pytest.approx(0.006)
        assert summary["by_model"]["claude-sonnet-4-20250514"]["calls"] == 1

    def test_get_cost_summary_aggregates_same_model(self):
        router = CinemaLLMRouter()
        router._cost_log.append(CostEntry(
            model="gpt-4.1", provider="openai",
            input_tokens=100, output_tokens=50, cost_usd=0.001,
        ))
        router._cost_log.append(CostEntry(
            model="gpt-4.1", provider="openai",
            input_tokens=200, output_tokens=100, cost_usd=0.002,
        ))

        summary = router.get_cost_summary()
        assert summary["total_calls"] == 2
        assert summary["by_model"]["gpt-4.1"]["calls"] == 2
        assert summary["by_model"]["gpt-4.1"]["input_tokens"] == 300
        assert summary["by_model"]["gpt-4.1"]["output_tokens"] == 150
        assert summary["by_model"]["gpt-4.1"]["cost_usd"] == pytest.approx(0.003)

    def test_get_cost_summary_tracks_cache_tokens(self):
        router = CinemaLLMRouter()
        router._cost_log.append(CostEntry(
            model="claude-sonnet-4-20250514", provider="anthropic",
            input_tokens=1000, output_tokens=500, cost_usd=0.01,
            cache_read_tokens=300, cache_write_tokens=150,
        ))
        summary = router.get_cost_summary()
        model_info = summary["by_model"]["claude-sonnet-4-20250514"]
        assert model_info["cache_read_tokens"] == 300
        assert model_info["cache_write_tokens"] == 150

    def test_reset_costs(self):
        router = CinemaLLMRouter()
        router._cost_log.append(CostEntry(
            model="gpt-4.1", provider="openai",
            input_tokens=100, output_tokens=50, cost_usd=0.001,
        ))
        assert len(router._cost_log) == 1
        router.reset_costs()
        assert len(router._cost_log) == 0
        summary = router.get_cost_summary()
        assert summary["total_calls"] == 0
        assert summary["total_cost_usd"] == 0.0

    def test_call_unknown_task_type_raises(self):
        router = CinemaLLMRouter()
        with pytest.raises(ValueError, match="Unknown task_type 'nonexistent'"):
            router.call(
                task_type="nonexistent",
                messages=[{"role": "user", "content": "test"}],
            )

    def test_call_unknown_task_type_lists_valid_types(self):
        router = CinemaLLMRouter()
        with pytest.raises(ValueError, match="Valid types:"):
            router.call(
                task_type="bogus_task",
                messages=[{"role": "user", "content": "test"}],
            )

    def test_lazy_init_clients_are_none(self):
        router = CinemaLLMRouter()
        assert router._anthropic_client is None
        assert router._openai_client is None
        assert router._gemini_configured is False
