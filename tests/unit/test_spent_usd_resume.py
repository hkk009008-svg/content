"""Regression tests for spent-usd-reset-on-resume.

The budget gate reads CostTracker.spent_usd, but SQLite is the durable store.
After a process restart, checkpoint resume must seed the in-memory accumulator
from prior rows for the current project/video id before more paid work is
admitted.
"""

from __future__ import annotations

import types

import pytest


def _make_store(tmp_path, runstate, cost_tracker, project_id="proj-1"):
    from cinema.checkpoint import CheckpointStore

    core = types.SimpleNamespace(
        project={"id": project_id, "scenes": []},
        temp_dir=str(tmp_path),
        cost_tracker=cost_tracker,
    )
    lifecycle = types.SimpleNamespace(report_progress=lambda *a, **k: None)
    return CheckpointStore(core, lifecycle, runstate)


def test_cost_tracker_rehydrates_spent_usd_from_video(tmp_path):
    from cost_tracker import API_COST_USD, CostTracker

    db_path = str(tmp_path / "cost.db")

    writer = CostTracker(db_path=db_path, budget_usd=1.0)
    writer.log_api(
        provider="runway",
        model="RUNWAY",
        operation="motion",
        cost_usd=0.75,
        video_id="proj-1",
    )
    writer.log_api(
        provider="veo",
        model="VEO",
        operation="motion",
        cost_usd=99.0,
        video_id="other-project",
    )
    writer.close()

    resumed = CostTracker(db_path=db_path, budget_usd=1.0)
    assert resumed.spent_usd == 0.0, "precondition: constructor starts a fresh accumulator"
    assert API_COST_USD["SORA_2"] == pytest.approx(0.60), "test depends on priced SORA_2"

    restored = resumed.rehydrate_spent_usd_from_video("proj-1")

    assert restored == pytest.approx(0.75)
    assert resumed.spent_usd == pytest.approx(0.75)
    assert resumed.would_exceed("SORA_2") is True
    resumed.close()


def test_checkpoint_restore_rehydrates_budget_spend(tmp_path):
    from cinema.runstate import RunState
    from cost_tracker import CostTracker

    db_path = str(tmp_path / "cost.db")

    writer = CostTracker(db_path=db_path, budget_usd=1.0)
    writer.log_api(
        provider="runway",
        model="RUNWAY",
        operation="motion",
        cost_usd=0.75,
        video_id="proj-1",
    )
    writer.close()

    resumed = CostTracker(db_path=db_path, budget_usd=1.0)
    runstate = RunState()
    store = _make_store(tmp_path, runstate, resumed, project_id="proj-1")
    store._save_checkpoint()

    assert resumed.spent_usd == 0.0, "precondition: checkpoint restore has not run"

    store._restore_from_checkpoint()

    assert resumed.spent_usd == pytest.approx(0.75)
    assert resumed.would_exceed("SORA_2") is True
    resumed.close()
