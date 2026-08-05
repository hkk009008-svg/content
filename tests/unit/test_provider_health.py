"""Provider usage analytics and AUTO health-routing tests (offline)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from cost_tracker import CostTracker
import phase_c_ffmpeg


BASE = datetime(2026, 8, 5, tzinfo=timezone.utc)


def _terminal_attempt(
    tracker: CostTracker,
    *,
    attempt_id: str,
    engine: str,
    provider: str,
    state: str,
    offset_s: float,
    latency_s: float = 30.0,
    video_id: str = "project-health",
) -> None:
    attempt = tracker.reserve_paid_attempt(
        attempt_id=attempt_id,
        provider=provider,
        engine=engine,
        operation="motion_generation",
        estimated_cost_usd=0.5,
        shot_id=attempt_id,
        video_id=video_id,
        request_fingerprint=(attempt_id * 64)[:64],
    )
    tracker.reconcile_paid_attempt(
        attempt["attempt_id"],
        state=state,
        actual_cost_usd=0.5 if state in {"succeeded", "failed_billed"} else None,
        provider_job_id=f"job-{attempt_id}",
    )
    created = BASE + timedelta(seconds=offset_s)
    updated = created + timedelta(seconds=latency_s)
    tracker.conn.execute(
        "UPDATE paid_attempts SET created_at = ?, updated_at = ? WHERE attempt_id = ?",
        (created.isoformat(), updated.isoformat(), attempt_id),
    )
    tracker.conn.commit()


def _metric(tracker: CostTracker, engine: str) -> dict:
    return tracker.get_provider_usage_analytics()["by_engine"][engine]


def test_low_sample_health_is_unknown_not_healthy(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "low.db")) as tracker:
        for index in range(4):
            _terminal_attempt(
                tracker,
                attempt_id=f"low-{index}",
                engine="RUNWAY_GEN4",
                provider="runway",
                state="succeeded",
                offset_s=index * 60,
            )
        metric = _metric(tracker, "RUNWAY_GEN4")
        assert metric["success_rate"] == 1.0
        assert metric["health"]["status"] == "unknown"
        assert metric["health"]["score"] is None
        assert metric["health"]["reasons"] == ["insufficient_terminal_samples:4/5"]


def test_three_consecutive_failures_make_provider_unhealthy(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "streak.db")) as tracker:
        states = ["succeeded", "succeeded", "failed_unbilled", "failed_billed", "failed_unbilled"]
        for index, state in enumerate(states):
            _terminal_attempt(
                tracker,
                attempt_id=f"streak-{index}",
                engine="RUNWAY_GEN4",
                provider="runway",
                state=state,
                offset_s=index * 60,
            )
        metric = _metric(tracker, "RUNWAY_GEN4")
        assert metric["consecutive_failures"] == 3
        assert metric["health"]["status"] == "unhealthy"
        assert "consecutive_failures:3" in metric["health"]["reasons"]


def test_three_failures_are_unhealthy_even_before_normal_sample_minimum(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "short-streak.db")) as tracker:
        for index in range(3):
            _terminal_attempt(
                tracker,
                attempt_id=f"short-streak-{index}",
                engine="RUNWAY_GEN4",
                provider="runway",
                state="failed_unbilled",
                offset_s=index * 60,
            )

        metric = _metric(tracker, "RUNWAY_GEN4")
        assert metric["sample_count"] == 3
        assert metric["consecutive_failures"] == 3
        assert metric["health"]["status"] == "unhealthy"
        assert metric["health"]["score"] is not None
        assert metric["health"]["reasons"] == ["consecutive_failures:3"]


def test_slow_p95_latency_makes_provider_unhealthy(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "slow.db")) as tracker:
        for index in range(5):
            _terminal_attempt(
                tracker,
                attempt_id=f"slow-{index}",
                engine="VEO",
                provider="fal",
                state="succeeded",
                offset_s=index * 1200,
                latency_s=1000 if index == 4 else 60,
            )
        metric = _metric(tracker, "VEO")
        assert metric["p95_terminal_latency_s"] == 1000.0
        assert metric["health"]["status"] == "unhealthy"
        assert "p95_latency_at_least_900s:1000.0" in metric["health"]["reasons"]


def test_malformed_timestamp_fails_health_closed_to_unknown(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "malformed.db")) as tracker:
        for index in range(5):
            _terminal_attempt(
                tracker,
                attempt_id=f"bad-{index}",
                engine="VEO_NATIVE",
                provider="google",
                state="succeeded",
                offset_s=index * 60,
            )
        tracker.conn.execute(
            "UPDATE paid_attempts SET updated_at = 'not-a-timestamp' WHERE attempt_id = 'bad-4'"
        )
        tracker.conn.commit()
        metric = _metric(tracker, "VEO_NATIVE")
        assert metric["data_valid"] is False
        assert metric["health"] == {
            "status": "unknown",
            "score": None,
            "sample_minimum": 5,
            "reasons": ["malformed_or_nonfinite_durable_evidence"],
        }


def test_usage_metrics_include_cost_reservation_counts_and_latency(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "metrics.db")) as tracker:
        for index in range(5):
            _terminal_attempt(
                tracker,
                attempt_id=f"metric-{index}",
                engine="RUNWAY_GEN4",
                provider="runway",
                state="succeeded",
                offset_s=index * 60,
                latency_s=20 + index,
            )
        active = tracker.reserve_paid_attempt(
            attempt_id="metric-active",
            provider="runway",
            engine="RUNWAY_GEN4",
            operation="motion_generation",
            estimated_cost_usd=0.75,
            shot_id="active-shot",
            video_id="project-health",
        )
        tracker.update_paid_attempt(
            active["attempt_id"],
            state="accepted_unknown",
            provider_job_id="job-active",
        )
        metric = tracker.get_provider_usage_analytics("project-health")["by_engine"]["RUNWAY_GEN4"]
        assert metric["terminal_count"] == 5
        assert metric["active_count"] == 1
        assert metric["accepted_unknown"] == 1
        assert metric["success_rate"] == 1.0
        assert metric["charged_cost_usd"] == pytest.approx(2.5)
        assert metric["reconciled_cost_usd"] == pytest.approx(2.5)
        assert metric["active_reservation_usd"] == pytest.approx(0.75)
        assert metric["average_terminal_latency_s"] == 22.0
        assert metric["p95_terminal_latency_s"] == 24.0


def test_two_accepted_unknown_jobs_quarantine_provider_without_terminal_samples(
    tmp_path,
) -> None:
    with CostTracker(db_path=str(tmp_path / "unknown-quarantine.db")) as tracker:
        for index in range(2):
            attempt = tracker.reserve_paid_attempt(
                attempt_id=f"unknown-{index}",
                provider="runway",
                engine="RUNWAY_GEN4",
                operation="motion_generation",
                estimated_cost_usd=0.5,
                shot_id=f"shot-{index}",
                video_id="project-health",
            )
            tracker.update_paid_attempt(
                attempt["attempt_id"],
                state="accepted_unknown",
                provider_job_id=f"job-unknown-{index}",
            )

        metric = _metric(tracker, "RUNWAY_GEN4")
        assert metric["sample_count"] == 0
        assert metric["health"] == {
            "status": "unhealthy",
            "score": 0.0,
            "sample_minimum": 5,
            "reasons": ["accepted_unknown_quarantine:2"],
        }


def test_usage_analytics_reads_new_rows_across_process_connections(tmp_path) -> None:
    db = str(tmp_path / "restart.db")
    writer = CostTracker(db_path=db)
    reader = CostTracker(db_path=db)
    try:
        _terminal_attempt(
            writer,
            attempt_id="restart-visible",
            engine="SEEDANCE",
            provider="fal",
            state="succeeded",
            offset_s=0,
        )
        assert reader.get_provider_usage_analytics()["by_engine"]["SEEDANCE"]["succeeded"] == 1
    finally:
        writer.close()
        reader.close()


def test_planning_observations_and_token_cost_are_durable_and_scoped(tmp_path) -> None:
    db = str(tmp_path / "planning-observations.db")
    with CostTracker(db_path=db) as writer:
        writer.default_video_id = "project-observed"
        for index, status in enumerate(
            ["succeeded", "succeeded", "failed", "succeeded", "succeeded"]
        ):
            writer.record_provider_observation(
                provider="openai",
                engine="gpt-4o",
                operation="planning",
                status=status,
                latency_ms=(index + 1) * 100,
            )
        writer.log_llm(
            model="gpt-4o",
            operation="planning",
            input_tokens=1_000_000,
            output_tokens=0,
        )

    with CostTracker(db_path=db) as reader:
        analytics = reader.get_provider_usage_analytics("project-observed")
        metric = analytics["by_engine"]["gpt-4o"]
        assert metric["terminal_count"] == 5
        assert metric["sample_count"] == 5
        assert metric["succeeded"] == 4
        assert metric["failed_observed"] == 1
        assert metric["success_rate"] == 0.8
        assert metric["average_terminal_latency_s"] == 0.3
        assert metric["p95_terminal_latency_s"] == 0.5
        assert metric["token_cost_usd"] == pytest.approx(2.5)
        assert metric["charged_cost_usd"] == pytest.approx(2.5)
        assert reader.get_provider_usage_analytics("another-project")[
            "by_engine"
        ] == {}


def test_three_observed_failures_quarantine_planning_provider(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "planning-streak.db")) as tracker:
        for index in range(3):
            tracker.record_provider_observation(
                provider="anthropic",
                engine="claude-sonnet-4-6",
                operation="planning",
                status="failed",
                latency_ms=10 + index,
                video_id="project-health",
            )

        metric = _metric(tracker, "claude-sonnet-4-6")
        assert metric["failed_observed"] == 3
        assert metric["consecutive_failures"] == 3
        assert metric["health"]["status"] == "unhealthy"


def test_terminal_limit_is_bounded_and_bool_does_not_coerce_to_one(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "limit.db")) as tracker:
        assert tracker.get_provider_usage_analytics(terminal_limit=50000)["terminal_limit"] == 1000
        assert tracker.get_provider_usage_analytics(terminal_limit=0)["terminal_limit"] == 1
        assert tracker.get_provider_usage_analytics(terminal_limit=True)["terminal_limit"] == 200


def _seed_health(tracker: CostTracker, engine: str, provider: str, states: list[str]) -> None:
    for index, state in enumerate(states):
        _terminal_attempt(
            tracker,
            attempt_id=f"{engine.lower()}-{index}",
            engine=engine,
            provider=provider,
            state=state,
            offset_s=index * 60,
            video_id="global-history",
        )


def _policy(candidates: tuple[str, ...]):
    return SimpleNamespace(candidates=candidates, rejections=())


def test_auto_filters_unhealthy_but_explicit_target_remains_available(monkeypatch, tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "routing.db"), budget_usd=20.0) as tracker:
        _seed_health(
            tracker,
            "RUNWAY_GEN4",
            "runway",
            ["succeeded", "succeeded", "failed_unbilled", "failed_billed", "failed_unbilled"],
        )
        _seed_health(tracker, "VEO", "fal", ["succeeded"] * 5)
        calls: list[dict] = []
        monkeypatch.setattr(
            phase_c_ffmpeg,
            "filter_automatic_dispatch_candidates",
            lambda *_a, **_k: _policy(("RUNWAY_GEN4", "VEO")),
        )
        monkeypatch.setattr(
            phase_c_ffmpeg,
            "filter_dispatch_candidates",
            lambda *_a, **_k: _policy(("RUNWAY_GEN4",)),
        )
        monkeypatch.setattr(
            phase_c_ffmpeg,
            "_execute_admitted_video_chain",
            lambda *_a, **kwargs: calls.append(kwargs) or "captured",
        )

        cascade: dict = {}
        assert phase_c_ffmpeg.generate_ai_video(
            "frame.jpg", "static", "AUTO", "out.mp4",
            video_fallbacks=["RUNWAY_GEN4", "VEO"],
            cost_tracker=tracker,
            _cascade_out=cascade,
        ) == "captured"
        assert calls[-1]["admitted_candidates"] == ("VEO",)
        assert cascade["provider_health"][0]["status"] == "unhealthy"

        assert phase_c_ffmpeg.generate_ai_video(
            "frame.jpg", "static", "RUNWAY_GEN4", "out.mp4",
            cost_tracker=tracker,
        ) == "captured"
        assert calls[-1]["admitted_candidates"] == ("RUNWAY_GEN4",)


def test_auto_keeps_unknown_low_sample_history(monkeypatch, tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "unknown-routing.db")) as tracker:
        _seed_health(tracker, "RUNWAY_GEN4", "runway", ["failed_unbilled"] * 2)
        calls: list[dict] = []
        monkeypatch.setattr(
            phase_c_ffmpeg,
            "filter_automatic_dispatch_candidates",
            lambda *_a, **_k: _policy(("RUNWAY_GEN4",)),
        )
        monkeypatch.setattr(
            phase_c_ffmpeg,
            "_execute_admitted_video_chain",
            lambda *_a, **kwargs: calls.append(kwargs) or "captured",
        )
        assert phase_c_ffmpeg.generate_ai_video(
            "frame.jpg", "static", "AUTO", "out.mp4", cost_tracker=tracker
        ) == "captured"
        assert calls[-1]["admitted_candidates"] == ("RUNWAY_GEN4",)


def test_auto_all_unhealthy_returns_no_eligible_provider(monkeypatch, tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "none.db")) as tracker:
        _seed_health(tracker, "RUNWAY_GEN4", "runway", ["failed_unbilled"] * 5)
        monkeypatch.setattr(
            phase_c_ffmpeg,
            "filter_automatic_dispatch_candidates",
            lambda *_a, **_k: _policy(("RUNWAY_GEN4",)),
        )
        monkeypatch.setattr(
            phase_c_ffmpeg,
            "_execute_admitted_video_chain",
            lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("no unhealthy provider may be revived")
            ),
        )
        cascade: dict = {}
        assert phase_c_ffmpeg.generate_ai_video(
            "frame.jpg",
            "static",
            "AUTO",
            "out.mp4",
            cost_tracker=tracker,
            _cascade_out=cascade,
        ) is None
        assert cascade["policy_error"]["code"] == "no_eligible_provider"
        assert cascade["policy_error"]["reason"] == "all_candidates_unhealthy"
