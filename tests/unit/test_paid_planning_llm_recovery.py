"""Durable no-replay authority for token-billed planning LLM calls."""

from __future__ import annotations

import json
import types
from unittest.mock import MagicMock

import pytest

from cost_tracker import CostTracker
from paid_provider import PaidCallBudgetBlocked, PaidCallDeferred


def _openai_response(text: str = "ok", *, input_tokens: int = 1000, output_tokens: int = 200):
    return types.SimpleNamespace(
        usage=types.SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        ),
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))],
    )


def _openai_client(*, response=None, error: Exception | None = None):
    create = MagicMock(side_effect=error)
    if error is None:
        create.return_value = response
    return (
        types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(create=create),
            )
        ),
        create,
    )


def _anthropic_client(*, response=None, error: Exception | None = None):
    create = MagicMock(side_effect=error)
    if error is None:
        create.return_value = response
    return (
        types.SimpleNamespace(messages=types.SimpleNamespace(create=create)),
        create,
    )


def _ensemble(tracker: CostTracker, client):
    from llm.ensemble import LLMEnsemble

    ensemble = LLMEnsemble.__new__(LLMEnsemble)
    ensemble.cost_tracker = tracker
    ensemble.video_id = "planning-project"
    ensemble.openai_client = client
    return ensemble


def _paid_rows(tracker: CostTracker):
    return [
        dict(row)
        for row in tracker.conn.execute(
            "SELECT * FROM paid_attempts ORDER BY created_at, attempt_id"
        ).fetchall()
    ]


def _cost_rows(tracker: CostTracker):
    return [
        dict(row)
        for row in tracker.conn.execute(
            "SELECT * FROM cost_log ORDER BY timestamp, id"
        ).fetchall()
    ]


def test_ensemble_success_reconciles_token_cost_once_and_restart_does_not_replay(tmp_path):
    db_path = str(tmp_path / "planning.db")
    response = _openai_response(input_tokens=1000, output_tokens=200)

    first = CostTracker(db_path=db_path, budget_usd=1.0)
    first.default_video_id = "planning-project"
    client, create = _openai_client(response=response)
    assert _ensemble(first, client)._generate_openai(
        "gpt-4o",
        "system",
        "user",
        operation="llm_ensemble_candidate",
        attempt_scope="candidate:0",
    ) == ("gpt-4o", "ok")
    assert create.call_count == 1

    attempts = _paid_rows(first)
    assert len(attempts) == 1
    assert attempts[0]["state"] == "succeeded"
    # 1,000 * $2.50/M + 200 * $10/M = $0.0045. The legacy post-call
    # log_llm path is suppressed under paid-attempt authority, so there is one
    # and only one durable money row.
    costs = _cost_rows(first)
    assert len(costs) == 1
    assert costs[0]["cost_usd"] == pytest.approx(0.0045)
    assert attempts[0]["reconciled_cost_usd"] == pytest.approx(0.0045)
    first.close()

    restarted = CostTracker(db_path=db_path, budget_usd=1.0)
    restarted.default_video_id = "planning-project"
    retry_client, retry_create = _openai_client(response=response)
    with pytest.raises(PaidCallDeferred, match="automatic replay blocked"):
        _ensemble(restarted, retry_client)._generate_openai(
            "gpt-4o",
            "system",
            "user",
            operation="llm_ensemble_candidate",
            attempt_scope="candidate:0",
        )
    retry_create.assert_not_called()
    assert len(_cost_rows(restarted)) == 1
    restarted.close()


def test_ensemble_ambiguous_exception_stays_unknown_and_restart_does_not_submit(tmp_path):
    db_path = str(tmp_path / "ambiguous.db")
    first = CostTracker(db_path=db_path, budget_usd=1.0)
    first.default_video_id = "planning-project"
    client, create = _openai_client(error=TimeoutError("lost response"))

    with pytest.raises(PaidCallDeferred, match="outcome is unknown"):
        _ensemble(first, client)._generate_openai(
            "gpt-4o",
            "system",
            "ambiguous user",
            operation="llm_ensemble_candidate",
            attempt_scope="candidate:0",
        )
    assert create.call_count == 1
    assert _paid_rows(first)[0]["state"] == "accepted_unknown"
    assert _cost_rows(first) == []
    first.close()

    restarted = CostTracker(db_path=db_path, budget_usd=1.0)
    restarted.default_video_id = "planning-project"
    retry_client, retry_create = _openai_client(response=_openai_response())
    with pytest.raises(PaidCallDeferred, match="automatic replay blocked"):
        _ensemble(restarted, retry_client)._generate_openai(
            "gpt-4o",
            "system",
            "ambiguous user",
            operation="llm_ensemble_candidate",
            attempt_scope="candidate:0",
        )
    retry_create.assert_not_called()
    restarted.close()


def test_ensemble_budget_reservation_blocks_before_sdk_call(tmp_path):
    tracker = CostTracker(db_path=str(tmp_path / "budget.db"), budget_usd=0.01)
    tracker.default_video_id = "planning-project"
    client, create = _openai_client(response=_openai_response())

    with pytest.raises(PaidCallBudgetBlocked):
        _ensemble(tracker, client)._generate_openai(
            "gpt-4o",
            "system",
            "user",
            operation="llm_ensemble_candidate",
            attempt_scope="candidate:0",
        )
    create.assert_not_called()
    assert _paid_rows(tracker)[0]["state"] == "blocked_budget"
    assert _cost_rows(tracker) == []
    tracker.close()


def test_anthropic_cache_write_and_read_tokens_use_differential_rates(tmp_path):
    from llm.ensemble import LLMEnsemble

    tracker = CostTracker(db_path=str(tmp_path / "cache-cost.db"), budget_usd=1.0)
    tracker.default_video_id = "planning-project"
    response = types.SimpleNamespace(
        usage=types.SimpleNamespace(
            input_tokens=100,
            cache_creation_input_tokens=1000,
            cache_read_input_tokens=2000,
            output_tokens=20,
        ),
        content=[types.SimpleNamespace(text="cached")],
    )
    client, create = _anthropic_client(response=response)
    ensemble = LLMEnsemble.__new__(LLMEnsemble)
    ensemble.cost_tracker = tracker
    ensemble.video_id = "planning-project"
    ensemble.anthropic_client = client

    assert ensemble._generate_anthropic(
        "claude-sonnet-4-6",
        "cacheable system",
        "user",
        operation="llm_ensemble_candidate",
        attempt_scope="candidate:0",
    ) == ("claude-sonnet-4-6", "cached")
    assert create.call_count == 1
    # Base: 100*$3/M; 5m write: 1000*$3.75/M; read: 2000*$0.30/M;
    # output: 20*$15/M => $0.00495 total.
    costs = _cost_rows(tracker)
    assert len(costs) == 1
    assert costs[0]["cost_usd"] == pytest.approx(0.00495)
    assert _paid_rows(tracker)[0]["reconciled_cost_usd"] == pytest.approx(0.00495)
    tracker.close()


def test_anthropic_reservation_prices_possible_cache_write_not_base_input(tmp_path):
    from llm.ensemble import LLMEnsemble

    # With 100k input bytes and the fixed 4,096-token output cap, base-input
    # pricing would admit this under $0.40. The 5m cache-write upper bound is
    # above $0.40 and must block before the SDK boundary.
    tracker = CostTracker(db_path=str(tmp_path / "cache-budget.db"), budget_usd=0.40)
    tracker.default_video_id = "planning-project"
    response = types.SimpleNamespace(
        usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
        content=[types.SimpleNamespace(text="must not run")],
    )
    client, create = _anthropic_client(response=response)
    ensemble = LLMEnsemble.__new__(LLMEnsemble)
    ensemble.cost_tracker = tracker
    ensemble.video_id = "planning-project"
    ensemble.anthropic_client = client

    with pytest.raises(PaidCallBudgetBlocked):
        ensemble._generate_anthropic(
            "claude-sonnet-4-6",
            "x" * 100_000,
            "user",
            operation="llm_ensemble_candidate",
            attempt_scope="candidate:0",
        )
    create.assert_not_called()
    assert _paid_rows(tracker)[0]["state"] == "blocked_budget"
    tracker.close()


def test_chief_director_real_tracker_never_retries_ambiguous_image_call(tmp_path):
    from llm.chief_director import ChiefDirector

    tracker = CostTracker(db_path=str(tmp_path / "chief.db"), budget_usd=10.0)
    tracker.default_video_id = "planning-project"
    create = MagicMock(
        side_effect=[
            TimeoutError("unknown provider outcome"),
            types.SimpleNamespace(
                usage=types.SimpleNamespace(input_tokens=10, output_tokens=10),
                content=[types.SimpleNamespace(text="should not run")],
            ),
        ]
    )
    director = ChiefDirector.__new__(ChiefDirector)
    director.project = {"id": "planning-project", "global_settings": {}}
    director.cost_tracker = tracker
    director.video_id = "planning-project"
    director.provider = "anthropic"
    director.client = types.SimpleNamespace(
        messages=types.SimpleNamespace(create=create)
    )

    with pytest.raises(PaidCallDeferred, match="outcome is unknown"):
        director._call_llm(
            "system",
            "user",
            image_b64s=["encoded-image"],
            operation="chief_director_quality_review",
        )
    assert create.call_count == 1
    assert _paid_rows(tracker)[0]["state"] == "accepted_unknown"
    tracker.close()


def test_cinema_director_success_uses_fenced_token_settlement(tmp_path):
    from llm.director import CinemaDirector

    tracker = CostTracker(db_path=str(tmp_path / "director.db"), budget_usd=1.0)
    tracker.default_video_id = "planning-project"
    client, create = _openai_client(
        response=_openai_response("{}", input_tokens=400, output_tokens=50)
    )
    director = CinemaDirector.__new__(CinemaDirector)
    director.project = {"id": "planning-project", "global_settings": {}}
    director.cost_tracker = tracker
    director.video_id = "planning-project"
    director.provider = "openai"
    director.client = client

    assert director._call_llm("translate") == "{}"
    assert create.call_count == 1
    assert _paid_rows(tracker)[0]["state"] == "succeeded"
    costs = _cost_rows(tracker)
    assert len(costs) == 1
    assert costs[0]["cost_usd"] == pytest.approx(0.0015)
    tracker.close()


def test_style_director_fences_sdk_and_suppresses_run_with_tools_double_count(
    monkeypatch, tmp_path
):
    import openai
    import web_research
    import llm.style_director as style_director

    tracker = CostTracker(db_path=str(tmp_path / "style.db"), budget_usd=1.0)
    tracker.default_video_id = "planning-project"
    response = _openai_response(
        json.dumps({"director_vision": "fenced"}),
        input_tokens=400,
        output_tokens=50,
    )
    client, create = _openai_client(response=response)

    def fake_run_with_tools(client_arg, model, **kwargs):
        sdk_response = client_arg.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": kwargs["user_prompt"]}],
            response_format=kwargs["response_format"],
        )
        # Mirror web_research's legacy accounting call. The production wrapper
        # must suppress it because the paid-attempt reconciliation already owns
        # this exact response cost.
        kwargs["cost_tracker"].log_llm(
            model=model,
            operation="web_research_final",
            input_tokens=400,
            output_tokens=50,
        )
        return sdk_response.choices[0].message.content

    monkeypatch.setattr(
        style_director,
        "settings",
        types.SimpleNamespace(openai_api_key="sk-test"),
    )
    monkeypatch.setattr(openai, "OpenAI", MagicMock(return_value=client))
    monkeypatch.setattr(web_research, "run_with_tools", fake_run_with_tools)

    rules = style_director.generate_style_rules(
        "Fenced Film",
        use_web_research=False,
        cost_tracker=tracker,
    )
    assert rules["director_vision"] == "fenced"
    assert create.call_count == 1
    assert create.call_args.kwargs["max_tokens"] == 4096
    assert _paid_rows(tracker)[0]["state"] == "succeeded"
    costs = _cost_rows(tracker)
    assert len(costs) == 1
    assert costs[0]["cost_usd"] == pytest.approx(0.0015)
    tracker.close()


def test_style_tool_loop_cannot_submit_final_call_after_ambiguous_tool_round(
    monkeypatch, tmp_path
):
    import openai
    import web_research
    import llm.style_director as style_director

    tracker = CostTracker(db_path=str(tmp_path / "style-unknown.db"), budget_usd=1.0)
    tracker.default_video_id = "planning-project"
    client, create = _openai_client(error=TimeoutError("lost response"))

    def swallowing_tool_loop(client_arg, model, **_kwargs):
        try:
            client_arg.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "tool round"}],
                tools=[{"type": "function", "function": {"name": "search"}}],
            )
        except Exception:
            pass
        # web_research proceeds to its final phase after a tool-round error.
        # The proxy must replay the local deferred exception, not call the SDK.
        return client_arg.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "final"}],
        )

    monkeypatch.setattr(
        style_director,
        "settings",
        types.SimpleNamespace(openai_api_key="sk-test"),
    )
    monkeypatch.setattr(openai, "OpenAI", MagicMock(return_value=client))
    monkeypatch.setattr(web_research, "run_with_tools", swallowing_tool_loop)

    with pytest.raises(PaidCallDeferred, match="outcome is unknown"):
        style_director.generate_style_rules(
            "Ambiguous Film",
            use_web_research=False,
            cost_tracker=tracker,
        )
    assert create.call_count == 1
    assert _paid_rows(tracker)[0]["state"] == "accepted_unknown"
    tracker.close()


def test_competitive_scene_decomposer_does_not_swallow_paid_deferred(
    monkeypatch,
):
    import research_engine
    import domain.scene_decomposer as scene_decomposer

    class AmbiguousEnsemble:
        def __init__(self, **_kwargs):
            pass

        def competitive_generate(self, **_kwargs):
            raise PaidCallDeferred("ensemble outcome unknown")

    fallback = MagicMock(return_value=[])
    monkeypatch.setattr(scene_decomposer, "LLMEnsemble", AmbiguousEnsemble)
    monkeypatch.setattr(scene_decomposer, "decompose_scene", fallback)
    monkeypatch.setattr(
        research_engine,
        "research_cinematography",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(PaidCallDeferred, match="ensemble outcome unknown"):
        scene_decomposer.competitive_decompose_scene(
            {
                "id": "scene-1",
                "title": "Ambiguous",
                "action": "A figure enters.",
                "duration_seconds": 5,
            },
            [],
            {"description": "a room"},
            {"aspect_ratio": "16:9"},
        )
    fallback.assert_not_called()


def test_single_scene_decomposer_ambiguity_never_reaches_replacement_sdk_call(
    monkeypatch, tmp_path
):
    import openai
    import research_engine
    import web_research
    import domain.scene_decomposer as scene_decomposer

    db_path = str(tmp_path / "scene-decompose.db")
    first = CostTracker(db_path=db_path, budget_usd=1.0)
    first.default_video_id = "planning-project"
    first_client, first_create = _openai_client(error=TimeoutError("lost response"))

    def swallowing_tool_loop(client_arg, model, **_kwargs):
        try:
            client_arg.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "tool round"}],
                tools=[{"type": "function", "function": {"name": "search"}}],
            )
        except Exception:
            pass
        return client_arg.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "final"}],
        )

    monkeypatch.setattr(
        scene_decomposer,
        "settings",
        types.SimpleNamespace(openai_api_key="sk-test"),
    )
    openai_ctor = MagicMock(return_value=first_client)
    monkeypatch.setattr(openai, "OpenAI", openai_ctor)
    monkeypatch.setattr(web_research, "run_with_tools", swallowing_tool_loop)
    monkeypatch.setattr(
        research_engine,
        "research_cinematography",
        lambda *_args, **_kwargs: None,
    )
    scene = {
        "id": "scene-1",
        "title": "Ambiguous",
        "action": "A figure enters.",
        "duration_seconds": 5,
    }
    location = {"description": "a room"}
    global_settings = {"aspect_ratio": "16:9"}

    with pytest.raises(PaidCallDeferred, match="outcome is unknown"):
        scene_decomposer.decompose_scene(
            scene,
            [],
            location,
            global_settings,
            cost_tracker=first,
        )
    assert first_create.call_count == 1
    assert _paid_rows(first)[0]["state"] == "accepted_unknown"
    assert first.conn.execute(
        "SELECT COUNT(*) FROM provider_observations WHERE provider = 'openai'"
    ).fetchone()[0] == 0
    first.close()

    restarted = CostTracker(db_path=db_path, budget_usd=1.0)
    restarted.default_video_id = "planning-project"
    retry_client, retry_create = _openai_client(response=_openai_response("{}"))
    openai_ctor.return_value = retry_client
    with pytest.raises(PaidCallDeferred, match="automatic replay blocked"):
        scene_decomposer.decompose_scene(
            scene,
            [],
            location,
            global_settings,
            cost_tracker=restarted,
        )
    retry_create.assert_not_called()
    restarted.close()


def test_real_fenced_llm_calls_emit_one_analytics_sample_each_not_two(
    monkeypatch, tmp_path
):
    import openai
    import web_research
    import llm.style_director as style_director
    from llm.chief_director import ChiefDirector
    from llm.director import CinemaDirector

    tracker = CostTracker(db_path=str(tmp_path / "analytics.db"), budget_usd=1.0)
    tracker.default_video_id = "planning-project"
    style_payload = json.dumps({"director_vision": "one sample"})
    responses = [
        _openai_response("candidate", input_tokens=100, output_tokens=10),
        _openai_response("{}", input_tokens=110, output_tokens=11),
        _openai_response('{"decision":"APPROVED"}', input_tokens=120, output_tokens=12),
        _openai_response(style_payload, input_tokens=130, output_tokens=13),
    ]
    create = MagicMock(side_effect=responses)
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create),
        )
    )

    ensemble = _ensemble(tracker, client)
    assert ensemble._generate_openai(
        "gpt-4o",
        "system-a",
        "user-a",
        operation="llm_ensemble_candidate",
        attempt_scope="candidate:0",
    ) == ("gpt-4o", "candidate")

    cinema_director = CinemaDirector.__new__(CinemaDirector)
    cinema_director.project = {"id": "planning-project", "global_settings": {}}
    cinema_director.cost_tracker = tracker
    cinema_director.video_id = "planning-project"
    cinema_director.provider = "openai"
    cinema_director.client = client
    assert cinema_director._call_llm("translate-b") == "{}"

    chief = ChiefDirector.__new__(ChiefDirector)
    chief.project = {"id": "planning-project", "global_settings": {}}
    chief.cost_tracker = tracker
    chief.video_id = "planning-project"
    chief.provider = "openai"
    chief.client = client
    assert chief._call_llm(
        "system-c",
        "user-c",
        operation="chief_director_quality_review",
    ) == '{"decision":"APPROVED"}'

    def fake_run_with_tools(client_arg, model, **kwargs):
        response = client_arg.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": kwargs["user_prompt"]}],
            response_format=kwargs["response_format"],
        )
        # Mirror both legacy writes in the real helper. The fenced tracker view
        # must suppress only this OpenAI observation/cost pair.
        kwargs["cost_tracker"].record_provider_observation(
            provider="openai",
            engine=model,
            operation="web_research_final",
            status="succeeded",
            latency_ms=1,
        )
        kwargs["cost_tracker"].log_llm(
            model=model,
            operation="web_research_final",
            input_tokens=130,
            output_tokens=13,
        )
        return response.choices[0].message.content

    monkeypatch.setattr(
        style_director,
        "settings",
        types.SimpleNamespace(openai_api_key="sk-test"),
    )
    monkeypatch.setattr(openai, "OpenAI", MagicMock(return_value=client))
    monkeypatch.setattr(web_research, "run_with_tools", fake_run_with_tools)
    rules = style_director.generate_style_rules(
        "Analytics Film",
        use_web_research=False,
        cost_tracker=tracker,
    )
    assert rules["director_vision"] == "one sample"

    assert create.call_count == 4
    assert len(_paid_rows(tracker)) == 4
    assert len(_cost_rows(tracker)) == 4
    assert tracker.conn.execute(
        "SELECT COUNT(*) FROM provider_observations WHERE provider = 'openai'"
    ).fetchone()[0] == 0

    metric = tracker.get_provider_usage_analytics(
        "planning-project"
    )["by_provider"]["openai"]
    assert metric["terminal_count"] == 4
    assert metric["sample_count"] == 4
    assert metric["succeeded"] == 4
    assert metric["failed_observed"] == 0
    assert metric["health"]["sample_minimum"] == 5
    assert metric["health"]["status"] == "unknown"
    assert metric["health"]["reasons"] == [
        "insufficient_terminal_samples:4/5"
    ]
    tracker.close()
