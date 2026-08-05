"""Provider observation coverage for optional Tavily/Firecrawl research."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _assert_observation(
    tracker,
    *,
    provider: str,
    engine: str,
    operation: str,
    status: str,
    latency_ms: int = 125,
) -> None:
    tracker.record_provider_observation.assert_called_once_with(
        provider=provider,
        engine=engine,
        operation=operation,
        status=status,
        latency_ms=latency_ms,
    )


def test_web_search_records_success_and_project_scoped_durable_analytics(
    monkeypatch, tmp_path
) -> None:
    from cost_tracker import CostTracker
    import web_research

    client = MagicMock()
    client.search.return_value = {
        "results": [{"title": "Lighting", "content": "Soft side light"}]
    }
    monkeypatch.setattr(web_research, "_get_tavily", lambda: client)

    with CostTracker(db_path=str(tmp_path / "research.db")) as tracker:
        tracker.default_video_id = "project-research"
        assert "Lighting" in web_research.search_web(
            "cinema lighting",
            cost_tracker=tracker,
        )

        analytics = tracker.get_provider_usage_analytics("project-research")
        metric = analytics["by_engine"]["TAVILY_SEARCH"]
        assert "tavily" in analytics["by_provider"]
        assert metric["succeeded"] == 1
        assert metric["failed_observed"] == 0
        assert metric["charged_cost_usd"] == 0.0


def test_web_search_records_failure_latency(monkeypatch) -> None:
    import web_research

    tracker = MagicMock()
    client = MagicMock()
    client.search.side_effect = RuntimeError("offline")
    monkeypatch.setattr(web_research, "_get_tavily", lambda: client)
    monkeypatch.setattr(
        web_research.time,
        "perf_counter",
        MagicMock(side_effect=[10.0, 10.125]),
    )

    assert web_research.search_web("lighting", cost_tracker=tracker).startswith(
        "Search failed:"
    )
    _assert_observation(
        tracker,
        provider="tavily",
        engine="TAVILY_SEARCH",
        operation="web_research_search",
        status="failed",
    )


def test_web_scrape_records_success_and_remote_failure(monkeypatch) -> None:
    import firecrawl_adapter
    import web_research

    success_tracker = MagicMock()
    monkeypatch.setattr(
        web_research.time,
        "perf_counter",
        MagicMock(side_effect=[20.0, 20.125]),
    )
    monkeypatch.setattr(
        firecrawl_adapter,
        "scrape_markdown",
        lambda *_args, **_kwargs: "reference",
    )
    assert web_research.scrape_url(
        "https://cinema.example.org/reference",
        cost_tracker=success_tracker,
    ) == "reference"
    _assert_observation(
        success_tracker,
        provider="firecrawl",
        engine="FIRECRAWL_SCRAPE",
        operation="web_research_scrape",
        status="succeeded",
    )

    failure_tracker = MagicMock()
    monkeypatch.setattr(
        web_research.time,
        "perf_counter",
        MagicMock(side_effect=[30.0, 30.125]),
    )

    def fail(*_args, **_kwargs):
        raise firecrawl_adapter.FirecrawlScrapeError("safe")

    monkeypatch.setattr(firecrawl_adapter, "scrape_markdown", fail)
    assert "Scrape failed" in web_research.scrape_url(
        "https://cinema.example.org/reference",
        cost_tracker=failure_tracker,
    )
    _assert_observation(
        failure_tracker,
        provider="firecrawl",
        engine="FIRECRAWL_SCRAPE",
        operation="web_research_scrape",
        status="failed",
    )


def test_web_scrape_does_not_blame_provider_for_local_configuration(
    monkeypatch,
) -> None:
    import firecrawl_adapter
    import web_research

    tracker = MagicMock()

    def fail(*_args, **_kwargs):
        raise firecrawl_adapter.FirecrawlConfigurationError("safe")

    monkeypatch.setattr(firecrawl_adapter, "scrape_markdown", fail)
    assert "not configured" in web_research.scrape_url(
        "https://cinema.example.org/reference",
        cost_tracker=tracker,
    )
    tracker.record_provider_observation.assert_not_called()


def test_tool_round_threads_shared_tracker_into_research_dispatch(monkeypatch) -> None:
    import web_research

    tracker = MagicMock()
    tool_call = SimpleNamespace(
        id="tool-1",
        function=SimpleNamespace(
            name="tavily_search",
            arguments=json.dumps({"query": "cinematic fog"}),
        ),
    )
    tool_response = SimpleNamespace(
        usage=None,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(tool_calls=[tool_call], content=None)
            )
        ],
    )
    final_response = SimpleNamespace(
        usage=None,
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="complete"))
        ],
    )
    create = MagicMock(side_effect=[tool_response, final_response])
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    dispatch = MagicMock(return_value="tool result")
    monkeypatch.setattr(web_research, "_get_tavily", lambda: object())
    monkeypatch.setattr(web_research, "handle_tool_call", dispatch)

    assert web_research.run_with_tools(
        client,
        "gpt-4o",
        "system",
        "user",
        max_tool_rounds=1,
        cost_tracker=tracker,
    ) == "complete"
    dispatch.assert_called_once_with(
        "tavily_search",
        {"query": "cinematic fog"},
        cost_tracker=tracker,
    )


@pytest.mark.parametrize(
    ("function_name", "arguments", "provider_result", "operation"),
    [
        (
            "research_cinematography",
            ("tense", "warehouse", "running"),
            {"results": [{"content": "hard side light"}]},
            "research_cinematography",
        ),
        (
            "research_location_visual",
            ("misty forest",),
            {"images": ["https://images.example.org/forest.jpg"]},
            "research_location_visual",
        ),
        (
            "research_music_reference",
            ("tense", "chase"),
            {"results": [{"content": "staccato strings"}]},
            "research_music_reference",
        ),
        (
            "research_trending_topics",
            ("cinema",),
            {"results": [{"title": "Practical lighting"}]},
            "research_trending_topics",
        ),
    ],
)
def test_research_engine_tavily_helpers_record_success(
    monkeypatch,
    function_name,
    arguments,
    provider_result,
    operation,
) -> None:
    import research_engine

    tracker = MagicMock()
    client = MagicMock()
    client.search.return_value = provider_result
    monkeypatch.setattr(research_engine, "_get_tavily", lambda: client)
    monkeypatch.setattr(
        research_engine.time,
        "perf_counter",
        MagicMock(side_effect=[40.0, 40.125]),
    )

    getattr(research_engine, function_name)(*arguments, cost_tracker=tracker)
    _assert_observation(
        tracker,
        provider="tavily",
        engine="TAVILY_SEARCH",
        operation=operation,
        status="succeeded",
    )


@pytest.mark.parametrize(
    ("function_name", "arguments", "operation"),
    [
        (
            "research_cinematography",
            ("tense", "warehouse", "running"),
            "research_cinematography",
        ),
        (
            "research_location_visual",
            ("misty forest",),
            "research_location_visual",
        ),
        (
            "research_music_reference",
            ("tense", "chase"),
            "research_music_reference",
        ),
        (
            "research_trending_topics",
            ("cinema",),
            "research_trending_topics",
        ),
    ],
)
def test_research_engine_tavily_helpers_record_failure(
    monkeypatch,
    function_name,
    arguments,
    operation,
) -> None:
    import research_engine

    tracker = MagicMock()
    client = MagicMock()
    client.search.side_effect = RuntimeError("offline")
    monkeypatch.setattr(research_engine, "_get_tavily", lambda: client)
    monkeypatch.setattr(
        research_engine.time,
        "perf_counter",
        MagicMock(side_effect=[50.0, 50.125]),
    )

    getattr(research_engine, function_name)(*arguments, cost_tracker=tracker)
    _assert_observation(
        tracker,
        provider="tavily",
        engine="TAVILY_SEARCH",
        operation=operation,
        status="failed",
    )


def test_research_engine_firecrawl_records_success_and_failure(monkeypatch) -> None:
    import firecrawl_adapter
    import research_engine

    success_tracker = MagicMock()
    monkeypatch.setattr(
        research_engine.time,
        "perf_counter",
        MagicMock(side_effect=[60.0, 60.125]),
    )
    monkeypatch.setattr(
        firecrawl_adapter,
        "scrape_markdown",
        lambda *_args, **_kwargs: "technique",
    )
    assert research_engine.scrape_technique_reference(
        "https://cinema.example.org/technique",
        cost_tracker=success_tracker,
    ) == "technique"
    _assert_observation(
        success_tracker,
        provider="firecrawl",
        engine="FIRECRAWL_SCRAPE",
        operation="scrape_technique_reference",
        status="succeeded",
    )

    failure_tracker = MagicMock()
    monkeypatch.setattr(
        research_engine.time,
        "perf_counter",
        MagicMock(side_effect=[70.0, 70.125]),
    )

    def fail(*_args, **_kwargs):
        raise firecrawl_adapter.FirecrawlResultError("safe")

    monkeypatch.setattr(firecrawl_adapter, "scrape_markdown", fail)
    assert research_engine.scrape_technique_reference(
        "https://cinema.example.org/technique",
        cost_tracker=failure_tracker,
    ) == ""
    _assert_observation(
        failure_tracker,
        provider="firecrawl",
        engine="FIRECRAWL_SCRAPE",
        operation="scrape_technique_reference",
        status="failed",
    )


def test_location_and_music_thread_the_shared_tracker(monkeypatch, tmp_path) -> None:
    import research_engine
    from audio.music import generate_fal_bgm
    from domain.location_manager import create_location_with_images

    tracker = object()
    location_research = MagicMock(return_value=[])
    music_research = MagicMock(return_value="")
    monkeypatch.setattr(
        research_engine,
        "research_location_visual",
        location_research,
    )
    monkeypatch.setattr(
        research_engine,
        "research_music_reference",
        music_research,
    )
    monkeypatch.setattr(
        "domain.location_manager._loc_dir",
        lambda *_args: str(tmp_path),
    )
    monkeypatch.setattr("domain.location_manager.add_location", lambda *_a, **_k: None)

    create_location_with_images(
        {"id": "project-research", "locations": []},
        "Forest",
        "Misty forest",
        auto_research=True,
        cost_tracker=tracker,
    )
    location_research.assert_called_once_with(
        "Misty forest",
        cost_tracker=tracker,
    )

    fal_client = SimpleNamespace(
        subscribe=MagicMock(side_effect=RuntimeError("offline"))
    )
    monkeypatch.setitem(sys.modules, "fal_client", fal_client)
    assert generate_fal_bgm(
        "tense",
        str(tmp_path / "bgm.mp3"),
        cost_tracker=tracker,
    ) is False
    music_research.assert_called_once_with(
        "tense",
        "",
        cost_tracker=tracker,
    )


def test_both_scene_decomposition_paths_thread_the_shared_tracker(
    monkeypatch,
) -> None:
    import openai
    import research_engine
    import web_research
    import domain.scene_decomposer as scene_decomposer

    tracker = object()
    research = MagicMock(return_value="")
    scene = {
        "id": "scene-research",
        "title": "Arrival",
        "action": "A figure enters.",
        "duration_seconds": 5,
    }
    location = {"description": "misty station"}
    shot = {
        "prompt": "[SHOT] figure [SCENE] station [ACTION] enters [OUTFIT] coat [QUALITY] film",
        "camera": scene_decomposer.CAMERA_MOTIONS[0],
        "visual_effect": scene_decomposer.VISUAL_EFFECTS[0],
        "target_api": "AUTO",
        "scene_foley": "room tone",
        "characters_in_frame": [],
        "action_context": "entering",
    }
    payload = {"shots": [shot, shot]}

    monkeypatch.setattr(
        scene_decomposer,
        "settings",
        SimpleNamespace(openai_api_key="test-key"),
    )
    monkeypatch.setattr(openai, "OpenAI", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(research_engine, "research_cinematography", research)
    monkeypatch.setattr(
        web_research,
        "run_with_tools",
        lambda *_args, **_kwargs: json.dumps(payload),
    )

    scene_decomposer.decompose_scene(
        scene,
        [],
        location,
        {"aspect_ratio": "16:9"},
        cost_tracker=tracker,
    )
    research.assert_called_once_with(
        "cinematic",
        "misty station",
        "A figure enters.",
        cost_tracker=tracker,
    )

    class Ensemble:
        def __init__(self, **_kwargs):
            pass

        def competitive_generate(self, **_kwargs):
            return SimpleNamespace(
                winner_index=0,
                winner_content=payload,
                scores=[1.0],
                reasoning="fixture",
                models_used=["gpt-4o"],
            )

    research.reset_mock()
    monkeypatch.setattr(scene_decomposer, "LLMEnsemble", Ensemble)
    scene_decomposer.competitive_decompose_scene(
        scene,
        [],
        location,
        {"aspect_ratio": "16:9"},
        cost_tracker=tracker,
    )
    research.assert_called_once_with(
        "cinematic",
        "misty station",
        "A figure enters.",
        cost_tracker=tracker,
    )


def test_location_endpoint_supplies_the_project_tracker(monkeypatch, tmp_path) -> None:
    import domain.project_manager as project_manager
    import web_server

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path))
    project = project_manager.create_project("Research location")
    tracker = object()
    creator = MagicMock(return_value={"id": "loc-research"})
    monkeypatch.setattr(web_server, "create_location_with_images", creator)
    monkeypatch.setattr(
        web_server,
        "_get_or_build_core",
        lambda _pid: SimpleNamespace(cost_tracker=tracker),
    )
    web_server.app.testing = True

    response = web_server.app.test_client().post(
        f"/api/projects/{project['id']}/locations",
        data={"name": "Forest", "description": "Misty forest"},
    )

    assert response.status_code == 201
    assert creator.call_args.kwargs["cost_tracker"] is tracker


def test_style_research_threads_the_shared_tracker(monkeypatch) -> None:
    import openai
    import research_engine
    import web_research
    import llm.style_director as style_director

    tracker = object()
    cinematography = MagicMock(return_value="")
    aesthetic = MagicMock(return_value="")
    monkeypatch.setattr(
        style_director,
        "settings",
        SimpleNamespace(openai_api_key="test-key", tavily_api_key="test-key"),
    )
    monkeypatch.setattr(research_engine, "research_cinematography", cinematography)
    monkeypatch.setattr(style_director, "_research_aesthetic", aesthetic)
    monkeypatch.setattr(openai, "OpenAI", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        web_research,
        "run_with_tools",
        lambda *_args, **_kwargs: json.dumps(
            style_director._default_style_rules("tense", "", "suspense")
        ),
    )

    style_director.generate_style_rules(
        "Film",
        mood="tense",
        reference_films="Blade Runner",
        cost_tracker=tracker,
    )
    cinematography.assert_called_once_with(
        "tense",
        "general cinematic setting",
        "tense film",
        cost_tracker=tracker,
    )
    aesthetic.assert_called_once_with(
        "Blade Runner",
        cost_tracker=tracker,
    )


def test_direct_style_tavily_request_records_outcome_and_latency(monkeypatch) -> None:
    import requests
    import llm.style_director as style_director

    success_tracker = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "results": [{"title": "Film", "content": "high contrast"}]
    }
    monkeypatch.setattr(
        style_director,
        "settings",
        SimpleNamespace(tavily_api_key="test-key"),
    )
    monkeypatch.setattr(requests, "post", MagicMock(return_value=response))
    monkeypatch.setattr(
        style_director.time,
        "perf_counter",
        MagicMock(side_effect=[80.0, 80.125]),
    )

    assert "high contrast" in style_director._research_aesthetic(
        "Film",
        cost_tracker=success_tracker,
    )
    _assert_observation(
        success_tracker,
        provider="tavily",
        engine="TAVILY_SEARCH",
        operation="research_aesthetic",
        status="succeeded",
    )

    failure_tracker = MagicMock()
    monkeypatch.setattr(
        requests,
        "post",
        MagicMock(return_value=MagicMock(status_code=503)),
    )
    monkeypatch.setattr(
        style_director.time,
        "perf_counter",
        MagicMock(side_effect=[90.0, 90.125]),
    )
    assert style_director._research_aesthetic(
        "Film",
        cost_tracker=failure_tracker,
    ) == ""
    _assert_observation(
        failure_tracker,
        provider="tavily",
        engine="TAVILY_SEARCH",
        operation="research_aesthetic",
        status="failed",
    )
