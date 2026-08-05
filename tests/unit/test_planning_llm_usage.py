"""Project-scoped cost and trace evidence for production planning LLM calls.

These tests cover project-scoped usage and latency observations, including the
legacy narrow-tracker path. Durable no-replay and atomic-budget behavior for the
real project tracker is pinned separately in ``test_paid_planning_llm_recovery``.
"""

from __future__ import annotations

import logging
import types
from unittest.mock import MagicMock, call


def _messages_client(*responses):
    create = MagicMock(side_effect=responses if len(responses) > 1 else None)
    if len(responses) == 1:
        create.return_value = responses[0]
    return types.SimpleNamespace(messages=types.SimpleNamespace(create=create)), create


def _openai_client(response=None, *, error=None):
    create = MagicMock(side_effect=error)
    if error is None:
        create.return_value = response
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create),
        )
    )
    return client, create


def test_pipeline_core_threads_one_project_tracker_to_planning_clients(
    monkeypatch, tmp_path
):
    import cinema.core as core_module

    project = {"id": "project-usage", "global_settings": {"budget_limit_usd": 4.0}}
    tracker = MagicMock()
    director = MagicMock()
    ensemble = MagicMock()
    director_ctor = MagicMock(return_value=director)
    ensemble_ctor = MagicMock(return_value=ensemble)

    monkeypatch.setattr(core_module, "load_project", lambda _pid: project)
    monkeypatch.setattr(core_module, "get_project_dir", lambda _pid: str(tmp_path))
    monkeypatch.setattr(core_module, "CostTracker", MagicMock(return_value=tracker))
    monkeypatch.setattr(core_module, "ContinuityEngine", MagicMock())
    monkeypatch.setattr(core_module, "ChiefDirector", director_ctor)
    monkeypatch.setattr(core_module, "LLMEnsemble", ensemble_ctor)

    core = core_module.build_pipeline_core("project-usage")

    assert core.cost_tracker is tracker
    assert tracker.default_video_id == "project-usage"
    director_ctor.assert_called_once_with(
        project,
        cost_tracker=tracker,
        video_id="project-usage",
    )
    ensemble_ctor.assert_called_once_with(
        settings=project["global_settings"],
        cost_tracker=tracker,
        video_id="project-usage",
    )


def test_ensemble_records_project_scoped_tokens_and_success_trace(caplog):
    from llm.ensemble import LLMEnsemble

    tracker = MagicMock()
    response = types.SimpleNamespace(
        usage=types.SimpleNamespace(prompt_tokens=120, completion_tokens=30),
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="ok"))],
    )
    client, _create = _openai_client(response)
    ensemble = LLMEnsemble.__new__(LLMEnsemble)
    ensemble.cost_tracker = tracker
    ensemble.video_id = "project-usage"
    ensemble.openai_client = client

    caplog.set_level(logging.INFO, logger="llm.ensemble")
    assert ensemble._generate_openai(
        "gpt-4o",
        "system",
        "user",
        operation="llm_ensemble_candidate",
    ) == ("gpt-4o", "ok")

    tracker.log_llm.assert_called_once_with(
        model="gpt-4o",
        operation="llm_ensemble_candidate",
        input_tokens=120,
        output_tokens=30,
        video_id="project-usage",
    )
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "Planning LLM request completed"
    )
    assert record.provider == "openai"
    assert record.engine == "gpt-4o"
    assert record.status == "succeeded"
    assert record.video_id == "project-usage"
    assert record.latency_ms >= 0
    tracker.record_provider_observation.assert_called_once_with(
        provider="openai",
        engine="gpt-4o",
        operation="llm_ensemble_candidate",
        status="succeeded",
        latency_ms=record.latency_ms,
        video_id="project-usage",
    )


def test_ensemble_failed_request_has_trace_but_no_token_cost(caplog):
    from llm.ensemble import LLMEnsemble

    tracker = MagicMock()
    client, _create = _openai_client(error=RuntimeError("offline"))
    ensemble = LLMEnsemble.__new__(LLMEnsemble)
    ensemble.cost_tracker = tracker
    ensemble.video_id = "project-usage"
    ensemble.openai_client = client

    caplog.set_level(logging.INFO, logger="llm.ensemble")
    model, content = ensemble._generate_single(
        "gpt-4o",
        "system",
        "user",
        operation="llm_ensemble_candidate",
    )

    assert (model, content) == ("gpt-4o", None)
    tracker.log_llm.assert_not_called()
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "Planning LLM request failed"
    )
    assert record.status == "failed"
    assert record.video_id == "project-usage"
    tracker.record_provider_observation.assert_called_once_with(
        provider="openai",
        engine="gpt-4o",
        operation="llm_ensemble_candidate",
        status="failed",
        latency_ms=record.latency_ms,
        video_id="project-usage",
    )


def test_chief_director_retry_logs_only_successful_response_usage(caplog):
    from llm.chief_director import ChiefDirector

    tracker = MagicMock()
    response = types.SimpleNamespace(
        usage=types.SimpleNamespace(input_tokens=250, output_tokens=40),
        content=[types.SimpleNamespace(text='{"decision":"RETRY"}')],
    )
    client, create = _messages_client(RuntimeError("image rejected"), response)
    director = ChiefDirector.__new__(ChiefDirector)
    director.project = {"id": "project-usage", "global_settings": {}}
    director.cost_tracker = tracker
    director.video_id = "project-usage"
    director.provider = "anthropic"
    director.client = client

    caplog.set_level(logging.INFO, logger="llm.chief_director")
    result = director._call_llm(
        "system",
        "user",
        image_b64s=["encoded-image"],
        operation="chief_director_quality_review",
    )

    assert result == '{"decision":"RETRY"}'
    assert create.call_count == 2
    tracker.log_llm.assert_called_once_with(
        model="claude-sonnet-4-6",
        operation="chief_director_quality_review",
        input_tokens=250,
        output_tokens=40,
        video_id="project-usage",
    )
    statuses = [
        record.status
        for record in caplog.records
        if record.getMessage().startswith("Chief Director LLM request")
    ]
    assert statuses == ["failed", "succeeded"]
    observation_latencies = [
        record.latency_ms
        for record in caplog.records
        if record.getMessage().startswith("Chief Director LLM request")
    ]
    assert tracker.record_provider_observation.call_args_list == [
        call(
            provider="anthropic",
            engine="claude-sonnet-4-6",
            operation="chief_director_quality_review",
            status="failed",
            latency_ms=observation_latencies[0],
            video_id="project-usage",
        ),
        call(
            provider="anthropic",
            engine="claude-sonnet-4-6",
            operation="chief_director_quality_review",
            status="succeeded",
            latency_ms=observation_latencies[1],
            video_id="project-usage",
        ),
    ]


def test_usage_alias_falls_through_when_primary_sdk_field_is_absent():
    from llm.chief_director import ChiefDirector
    from llm.director import CinemaDirector

    usage = types.SimpleNamespace(input_tokens=17)
    assert ChiefDirector._usage_count(usage, "prompt_tokens", "input_tokens") == 17
    assert CinemaDirector._usage_count(usage, "prompt_tokens", "input_tokens") == 17


def test_cinema_director_records_direct_intent_translation_usage(caplog):
    from llm.director import CinemaDirector

    tracker = MagicMock()
    response = types.SimpleNamespace(
        usage=types.SimpleNamespace(prompt_tokens=90, completion_tokens=15),
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="{}"))],
    )
    client, _create = _openai_client(response)
    director = CinemaDirector.__new__(CinemaDirector)
    director.project = {"id": "project-usage", "global_settings": {}}
    director.cost_tracker = tracker
    director.video_id = "project-usage"
    director.provider = "openai"
    director.client = client

    caplog.set_level(logging.INFO, logger="llm.director")
    assert director._call_llm("translate this") == "{}"

    tracker.log_llm.assert_called_once_with(
        model="gpt-4o",
        operation="cinema_director_translate_intent",
        input_tokens=90,
        output_tokens=15,
        video_id="project-usage",
    )
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "Cinema Director LLM request completed"
    )
    assert record.status == "succeeded"
    assert record.video_id == "project-usage"
    tracker.record_provider_observation.assert_called_once_with(
        provider="openai",
        engine="gpt-4o",
        operation="cinema_director_translate_intent",
        status="succeeded",
        latency_ms=record.latency_ms,
        video_id="project-usage",
    )


def test_intent_translator_accepts_shared_tracker_scope(monkeypatch):
    import llm.director as director_module

    tracker = MagicMock()
    instance = MagicMock()
    instance.translate_intent.return_value = {"revised_prompt": "ok"}
    constructor = MagicMock(return_value=instance)
    monkeypatch.setattr(director_module, "CinemaDirector", constructor)

    result = director_module.intent_translator(
        {"prose": "move closer"},
        {"id": "take-1"},
        {"id": "scene-1"},
        project={"id": "project-usage"},
        cost_tracker=tracker,
        video_id="project-usage",
    )

    assert result == {"revised_prompt": "ok"}
    constructor.assert_called_once_with(
        project={"id": "project-usage"},
        cost_tracker=tracker,
        video_id="project-usage",
    )
