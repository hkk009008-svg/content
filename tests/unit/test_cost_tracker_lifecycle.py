"""Regression coverage for optional CostTracker connection ownership."""

from __future__ import annotations

import gc
import types

import pytest

from cost_tracker import CostTracker
from cost_tracker_lifecycle import cost_tracker_scope


def test_owned_tracker_closes_after_success(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIMENTS_DB_PATH", str(tmp_path / "owned-success.db"))

    with cost_tracker_scope() as tracker:
        tracker.log_api(
            provider="test",
            model="lifecycle",
            operation="success",
            cost_usd=0.0,
        )

    assert tracker._closed is True
    del tracker
    gc.collect()


def test_owned_tracker_closes_after_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIMENTS_DB_PATH", str(tmp_path / "owned-error.db"))
    tracker = None

    with pytest.raises(RuntimeError, match="synthetic logging failure"):
        with cost_tracker_scope() as tracker:
            raise RuntimeError("synthetic logging failure")

    assert tracker is not None
    assert tracker._closed is True
    del tracker
    gc.collect()


def test_injected_tracker_remains_caller_owned(tmp_path):
    tracker = CostTracker(db_path=str(tmp_path / "injected.db"))
    try:
        with cost_tracker_scope(tracker) as yielded:
            assert yielded is tracker
            yielded.log_api(
                provider="test",
                model="lifecycle",
                operation="injected",
                cost_usd=0.0,
            )

        assert tracker._closed is False
        tracker.conn.execute("SELECT 1").fetchone()
    finally:
        tracker.close()


@pytest.mark.parametrize(
    ("logger", "args"),
    [
        ("performance.live_portrait", (5.0, "shot", "project")),
        ("performance.viggle", ("shot", "project")),
    ],
)
def test_performance_fallback_closes_when_logging_raises(
    logger,
    args,
    monkeypatch,
):
    import importlib
    import cost_tracker as cost_tracker_module

    created = []

    class FailingTracker:
        def __init__(self, budget_usd=None):
            self.closed = False
            created.append(self)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.closed = True
            return False

        def log_api(self, **kwargs):
            raise RuntimeError("synthetic write failure")

    monkeypatch.setattr(cost_tracker_module, "CostTracker", FailingTracker)
    module = importlib.import_module(logger)

    module._cost_log(*args)

    assert len(created) == 1
    assert created[0].closed is True


def test_web_research_fallback_closes_after_logging(monkeypatch):
    import cost_tracker as cost_tracker_module
    import web_research

    created = []

    class TrackingCostTracker:
        def __init__(self, budget_usd=None):
            self.closed = False
            self.logged = False
            created.append(self)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.closed = True
            return False

        def log_llm(self, **kwargs):
            self.logged = True

    response = types.SimpleNamespace(
        usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content="research complete"),
        )],
    )
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=lambda **kwargs: response),
        ),
    )

    monkeypatch.setattr(cost_tracker_module, "CostTracker", TrackingCostTracker)
    monkeypatch.setattr(web_research, "_get_tavily", lambda: None)
    monkeypatch.setattr(
        web_research.firecrawl_adapter,
        "is_available",
        lambda _key: False,
    )

    result = web_research.run_with_tools(
        client,
        "gpt-4o",
        "system",
        "user",
    )

    assert result == "research complete"
    assert len(created) == 1
    assert created[0].logged is True
    assert created[0].closed is True
