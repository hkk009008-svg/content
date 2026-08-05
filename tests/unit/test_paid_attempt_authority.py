"""Offline tests for paid-task ownership and atomic budget authority."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace
import sqlite3
import threading

import httpx
import pytest

from cost_tracker import CostTracker
import performance.act_two as act_two
import phase_c_ffmpeg
from cinema.context import PipelineContext
from domain.provider_catalog import RuntimeSnapshot
from performance.runway_tasks import (
    call_with_backoff,
    cancel_runway_attempt,
    retry_after_seconds,
    retry_delay_seconds,
)


def _reserve(
    tracker: CostTracker,
    attempt_id: str,
    *,
    cost: float = 0.75,
    engine: str = "RUNWAY_GEN4",
) -> dict:
    return tracker.reserve_paid_attempt(
        attempt_id=attempt_id,
        provider="runway",
        engine=engine,
        operation="motion_generation",
        estimated_cost_usd=cost,
        shot_id="shot-1",
        video_id="project-1",
        request_fingerprint="a" * 64,
    )


def test_native_ltx_pricing_is_model_resolution_duration_aware() -> None:
    common = {
        "backend": "native",
        "operation": "image_to_video",
        "model": "ltx-2-3-pro",
        "audio": False,
    }
    assert CostTracker.estimate_call_cost_usd(
        "LTX", 10, resolution="1080p", **common
    ) == pytest.approx(0.80)
    assert CostTracker.estimate_call_cost_usd(
        "LTX", 10, resolution="1440p", **common
    ) == pytest.approx(1.60)
    assert CostTracker.estimate_call_cost_usd(
        "LTX", 10, resolution="4K", **common
    ) == pytest.approx(3.20)


def test_native_ltx_unknown_audio_profile_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported LTX pricing profile"):
        CostTracker.estimate_call_cost_usd(
            "LTX",
            8,
            backend="native",
            operation="image_to_video",
            model="ltx-2-3-pro",
            resolution="4k",
            audio=True,
        )


def test_file_ledger_uses_wal_and_memory_uses_memory_journal(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "ledger.db")) as tracker:
        assert tracker.journal_mode == "wal"
    memory = CostTracker(db_path=":memory:")
    assert memory.journal_mode == "memory"
    memory.close()
    memory.close()  # idempotent shutdown


def test_atomic_budget_reservation_blocks_one_of_two_process_peers(tmp_path) -> None:
    db = str(tmp_path / "race.db")
    first = CostTracker(db_path=db, budget_usd=1.0)
    second = CostTracker(db_path=db, budget_usd=1.0)
    barrier = threading.Barrier(2)

    def reserve(tracker: CostTracker, attempt_id: str) -> dict:
        barrier.wait()
        return _reserve(tracker, attempt_id)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, (first, second), ("attempt-a", "attempt-b")))
        assert sum(bool(result["acquired"]) for result in results) == 1
        assert {result["state"] for result in results} == {"submitting", "blocked_budget"}
    finally:
        first.close()
        second.close()


def test_duplicate_workers_cannot_claim_same_attempt_twice(tmp_path) -> None:
    db = str(tmp_path / "duplicate.db")
    first = CostTracker(db_path=db, budget_usd=5.0)
    second = CostTracker(db_path=db, budget_usd=5.0)
    barrier = threading.Barrier(2)

    def reserve(tracker: CostTracker) -> dict:
        barrier.wait()
        return _reserve(tracker, "same-attempt")

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, (first, second)))
        assert sum(bool(result["acquired"]) for result in results) == 1
        assert all(result["state"] == "submitting" for result in results)
    finally:
        first.close()
        second.close()


def test_attempt_id_cannot_be_reused_for_a_different_request_identity(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "identity.db"), budget_usd=5.0) as tracker:
        _reserve(tracker, "same-attempt")
        with pytest.raises(ValueError, match="different request identity"):
            tracker.reserve_paid_attempt(
                attempt_id="same-attempt",
                provider="runway",
                engine="RUNWAY_GEN4",
                operation="motion_generation",
                estimated_cost_usd=0.75,
                shot_id="different-shot",
                video_id="project-1",
                request_fingerprint="b" * 64,
            )

        unchanged = tracker.get_paid_attempt("same-attempt")
        assert unchanged["shot_id"] == "shot-1"
        assert unchanged["request_fingerprint"] == "a" * 64


def test_budget_mutation_is_durable_authority_for_stale_process_peer(tmp_path) -> None:
    db = str(tmp_path / "budget-mutation.db")
    authority = CostTracker(db_path=db, budget_usd=1.0)
    stale_peer = CostTracker(db_path=db, budget_usd=10.0)
    try:
        authority.set_video_budget("project-1", 1.0)
        assert _reserve(authority, "before-mutation", cost=0.4)["acquired"] is True
        authority.set_video_budget("project-1", 0.5)
        blocked = _reserve(stale_peer, "after-mutation", cost=0.2)
        assert blocked["state"] == "blocked_budget"
        assert blocked["acquired"] is False
    finally:
        authority.close()
        stale_peer.close()


def test_accepted_unknown_remains_reserved_and_operator_visible(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "unknown.db"), budget_usd=2.0) as tracker:
        attempt = _reserve(tracker, "unknown-attempt", cost=0.5)
        tracker.update_paid_attempt(
            attempt["attempt_id"],
            state="accepted_unknown",
            provider_job_id="runway-task-1",
            detail="retrieval lost",
        )
        snapshot = tracker.get_paid_attempts_snapshot("project-1")
        assert snapshot["accepted_unknown_count"] == 1
        assert snapshot["active_reservation_usd"] == pytest.approx(0.5)


def test_billed_moderation_reconciles_once_and_releases_reservation(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "moderation.db"), budget_usd=2.0) as tracker:
        attempt = _reserve(tracker, "moderated-attempt", cost=0.5)
        tracker.update_paid_attempt(
            attempt["attempt_id"],
            state="running",
            provider_job_id="runway-moderated-1",
        )
        for _ in range(2):
            tracker.reconcile_paid_attempt(
                attempt["attempt_id"],
                state="failed_billed",
                actual_cost_usd=0.5,
                provider_job_id="runway-moderated-1",
                failure_code="SAFETY.INPUT",
            )
        snapshot = tracker.get_paid_attempts_snapshot("project-1")
        assert snapshot["billed_failure_count"] == 1
        assert snapshot["active_reservation_usd"] == 0.0
        assert tracker.get_video_cost("project-1")["total_usd"] == pytest.approx(0.5)


def test_concurrent_reconcile_is_one_atomic_invoice(tmp_path) -> None:
    db = str(tmp_path / "reconcile-race.db")
    first = CostTracker(db_path=db, budget_usd=2.0)
    second = CostTracker(db_path=db, budget_usd=2.0)
    attempt = _reserve(first, "reconcile-race", cost=0.5)
    first.update_paid_attempt(
        attempt["attempt_id"],
        state="running",
        provider_job_id="runway-race-1",
    )
    barrier = threading.Barrier(2)

    def reconcile(tracker: CostTracker) -> dict:
        barrier.wait()
        return tracker.reconcile_paid_attempt(
            attempt["attempt_id"],
            state="succeeded",
            actual_cost_usd=0.5,
            provider_job_id="runway-race-1",
            provider_status="SUCCEEDED",
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reconcile, (first, second)))
        assert [result["state"] for result in results] == ["succeeded", "succeeded"]
        count = first.conn.execute(
            "SELECT COUNT(*) FROM cost_log WHERE provider = ? AND provider_job_id = ?",
            ("runway", "runway-race-1"),
        ).fetchone()[0]
        assert count == 1
        settled = first.get_paid_attempt(attempt["attempt_id"])
        assert settled["reserved_cost_usd"] == 0.0
        assert settled["reconciled_cost_usd"] == pytest.approx(0.5)
    finally:
        first.close()
        second.close()


def test_reconcile_rolls_back_invoice_when_terminal_transition_fails(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "rollback.db"), budget_usd=2.0) as tracker:
        attempt = _reserve(tracker, "rollback-attempt", cost=0.5)
        tracker.update_paid_attempt(
            attempt["attempt_id"],
            state="running",
            provider_job_id="runway-rollback-1",
        )
        tracker.conn.execute(
            """
            CREATE TRIGGER reject_paid_terminal
            BEFORE UPDATE ON paid_attempts
            WHEN NEW.attempt_id = 'rollback-attempt' AND NEW.state = 'succeeded'
            BEGIN
                SELECT RAISE(ABORT, 'injected terminal failure');
            END
            """
        )
        tracker.conn.commit()

        with pytest.raises(sqlite3.IntegrityError, match="injected terminal failure"):
            tracker.reconcile_paid_attempt(
                attempt["attempt_id"],
                state="succeeded",
                actual_cost_usd=0.5,
                provider_job_id="runway-rollback-1",
            )

        assert tracker.get_video_cost("project-1")["total_usd"] == 0.0
        unchanged = tracker.get_paid_attempt(attempt["attempt_id"])
        assert unchanged["state"] == "running"
        assert unchanged["reserved_cost_usd"] == pytest.approx(0.5)
        assert unchanged["reconciled_cost_usd"] is None


def test_terminal_attempt_cannot_regress_or_change_verdict(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "terminal.db"), budget_usd=2.0) as tracker:
        attempt = _reserve(tracker, "terminal-attempt", cost=0.5)
        tracker.reconcile_paid_attempt(
            attempt["attempt_id"],
            state="succeeded",
            actual_cost_usd=0.5,
            provider_job_id="runway-terminal-1",
        )

        with pytest.raises(ValueError, match="illegal paid-attempt transition"):
            tracker.update_paid_attempt(attempt["attempt_id"], state="running")
        with pytest.raises(ValueError, match="illegal paid-attempt transition"):
            tracker.reconcile_paid_attempt(
                attempt["attempt_id"],
                state="failed_billed",
                actual_cost_usd=0.5,
                provider_job_id="runway-terminal-1",
            )

        settled = tracker.get_paid_attempt(attempt["attempt_id"])
        assert settled["state"] == "succeeded"
        assert tracker.get_video_cost("project-1")["total_usd"] == pytest.approx(0.5)


def test_terminal_invoice_key_cannot_be_rebound_after_attempt_key_settlement(
    tmp_path,
) -> None:
    with CostTracker(db_path=str(tmp_path / "invoice-key.db"), budget_usd=2.0) as tracker:
        attempt = _reserve(tracker, "invoice-key-attempt", cost=0.5)
        tracker.reconcile_paid_attempt(
            attempt["attempt_id"],
            state="succeeded",
            actual_cost_usd=0.5,
        )

        with pytest.raises(ValueError, match="provider_job_id is immutable"):
            tracker.reconcile_paid_attempt(
                attempt["attempt_id"],
                state="succeeded",
                actual_cost_usd=0.5,
                provider_job_id="late-provider-job-id",
            )

        rows = tracker.conn.execute(
            "SELECT provider_job_id FROM cost_log WHERE video_id = ?",
            ("project-1",),
        ).fetchall()
        assert [row["provider_job_id"] for row in rows] == [
            "attempt:invoice-key-attempt"
        ]


class _DeleteClient:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.tasks = self

    def delete(self, *, id: str) -> None:  # noqa: A002 - provider signature
        if self.error:
            raise self.error


def test_ambiguous_cancellation_stays_reserved_unknown(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "cancel.db"), budget_usd=2.0) as tracker:
        attempt = _reserve(tracker, "cancel-attempt", cost=0.5)
        tracker.update_paid_attempt(
            attempt["attempt_id"],
            state="running",
            provider_job_id="runway-cancel-1",
        )
        result = cancel_runway_attempt(
            tracker,
            attempt["attempt_id"],
            api_key="offline",
            client_factory=lambda **_: _DeleteClient(error=TimeoutError("lost")),
        )
        assert result["state"] == "accepted_unknown"
        assert tracker.get_paid_attempts_snapshot("project-1")["active_reservation_usd"] == pytest.approx(0.5)


def test_acknowledged_cancellation_waits_for_terminal_provider_state(tmp_path) -> None:
    with CostTracker(db_path=str(tmp_path / "cancel-ack.db"), budget_usd=2.0) as tracker:
        attempt = _reserve(tracker, "cancel-ack", cost=0.5)
        tracker.update_paid_attempt(
            attempt["attempt_id"], state="running", provider_job_id="runway-cancel-2"
        )
        result = cancel_runway_attempt(
            tracker,
            attempt["attempt_id"],
            api_key="offline",
            client_factory=lambda **_: _DeleteClient(),
        )
        assert result["state"] == "cancel_requested"
        assert result["active"] is True


def test_retry_after_seconds_and_http_date_are_honored() -> None:
    numeric = SimpleNamespace(response=SimpleNamespace(headers={"Retry-After": "7"}))
    assert retry_after_seconds(numeric) == 7.0
    assert retry_delay_seconds(numeric, 0, random_value=lambda: 0.0) == 7.0

    now = datetime(2026, 8, 5, tzinfo=timezone.utc)
    date_value = format_datetime(now + timedelta(seconds=9), usegmt=True)
    dated = SimpleNamespace(response=SimpleNamespace(headers={"Retry-After": date_value}))
    assert retry_after_seconds(dated, now=now) == pytest.approx(9.0)


def test_transient_503_retrieval_uses_bounded_backoff_then_succeeds() -> None:
    class Transient503(RuntimeError):
        status_code = 503

    calls = 0
    sleeps: list[float] = []

    def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise Transient503("retry")
        return "done"

    assert call_with_backoff(
        operation,
        attempts=4,
        sleep=sleeps.append,
        random_value=lambda: 0.0,
    ) == "done"
    assert calls == 3
    assert sleeps == [0.5, 1.0]


class _CreateEndpoint:
    def __init__(self, *, task_id: str = "act-task-1", forbid: bool = False):
        self.task_id = task_id
        self.forbid = forbid
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.forbid:
            raise AssertionError("restart must retrieve the existing task, not submit")
        return SimpleNamespace(id=self.task_id)


class _TaskEndpoint:
    def __init__(self, *tasks):
        self.tasks = list(tasks)

    def retrieve(self, *, id: str):  # noqa: A002 - provider signature
        if len(self.tasks) > 1:
            return self.tasks.pop(0)
        return self.tasks[0]


class _UploadEndpoint:
    def __init__(self, *, forbid: bool = False, error: BaseException | None = None):
        self.forbid = forbid
        self.error = error
        self.calls = []

    def create_ephemeral(self, *, file):
        self.calls.append(file)
        if self.forbid:
            raise AssertionError("restart must retrieve the existing task, not upload")
        if self.error is not None:
            raise self.error
        return SimpleNamespace(uri=f"runway://act-input-{len(self.calls)}")


class _ActClient:
    def __init__(
        self,
        create: _CreateEndpoint,
        tasks: _TaskEndpoint,
        uploads: _UploadEndpoint | None = None,
    ):
        self.character_performance = create
        self.tasks = tasks
        self.uploads = uploads or _UploadEndpoint()


def _act_files(tmp_path):
    keyframe = tmp_path / "keyframe.jpg"
    driving = tmp_path / "driving.mp4"
    output = tmp_path / "output.mp4"
    keyframe.write_bytes(b"jpeg")
    driving.write_bytes(b"mp4")
    return str(keyframe), str(driving), str(output)


def _install_act_client(monkeypatch, client: _ActClient) -> None:
    import runwayml

    monkeypatch.setattr(runwayml, "RunwayML", lambda **_: client)
    monkeypatch.setattr(
        act_two,
        "settings",
        SimpleNamespace(runwayml_api_secret="offline-key"),
    )


def test_act_two_restart_resumes_same_accepted_task_without_duplicate_submit(
    monkeypatch, tmp_path
) -> None:
    keyframe, driving, output = _act_files(tmp_path)
    db = str(tmp_path / "act-restart.db")
    create_first = _CreateEndpoint(task_id="act-restart-task")
    uploads_first = _UploadEndpoint()
    _install_act_client(
        monkeypatch,
        _ActClient(
            create_first,
            _TaskEndpoint(SimpleNamespace(status="PENDING")),
            uploads_first,
        ),
    )
    first = CostTracker(db_path=db, budget_usd=2.0)
    try:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            poll_timeout_s=0,
            duration_s=5.0,
            shot_id="shot-act",
            video_id="project-act",
            cost_tracker=first,
        ) is None
        pending = first.get_latest_paid_attempt(
            video_id="project-act",
            shot_id="shot-act",
            engine="ACT_ONE",
            operation="performance_capture",
        )
        assert pending["state"] == "accepted_unknown"
        assert pending["provider_job_id"] == "act-restart-task"
        assert len(uploads_first.calls) == 2
    finally:
        first.close()

    create_restart = _CreateEndpoint(forbid=True)
    uploads_restart = _UploadEndpoint(forbid=True)
    _install_act_client(
        monkeypatch,
        _ActClient(
            create_restart,
            _TaskEndpoint(
                SimpleNamespace(
                    status="SUCCEEDED",
                    output=["https://offline.test/output.mp4"],
                )
            ),
            uploads_restart,
        ),
    )

    def download(_url, destination, **_kwargs):
        with open(destination, "wb") as handle:
            handle.write(b"video")
        return destination

    monkeypatch.setattr(act_two, "safe_download", download)
    resumed = CostTracker(db_path=db, budget_usd=2.0)
    try:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            poll_timeout_s=0,
            duration_s=5.0,
            shot_id="shot-act",
            video_id="project-act",
            cost_tracker=resumed,
        ) == output
        assert create_restart.calls == 0
        assert uploads_restart.calls == []
        settled = resumed.get_latest_paid_attempt(
            video_id="project-act",
            shot_id="shot-act",
            engine="ACT_ONE",
            operation="performance_capture",
        )
        assert settled["state"] == "succeeded"
        assert resumed.get_video_cost("project-act")["total_usd"] == pytest.approx(0.25)
    finally:
        resumed.close()


def test_act_two_remote_checkpoint_failure_keeps_known_task_reserved(
    monkeypatch,
    tmp_path,
) -> None:
    keyframe, driving, output = _act_files(tmp_path)
    task_id = "d9f3cd8d-55c8-4a26-b2c4-b3ea0b0d7f9b"
    create = _CreateEndpoint(task_id=task_id)
    _install_act_client(
        monkeypatch,
        _ActClient(create, _TaskEndpoint(SimpleNamespace(status="PENDING"))),
    )

    def fail_checkpoint(_task_id: str) -> None:
        raise OSError("remote authority unavailable")

    db = str(tmp_path / "checkpoint-failure.db")
    with CostTracker(db_path=db, budget_usd=2.0) as tracker:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            duration_s=5.0,
            shot_id="shot-checkpoint",
            video_id="project-checkpoint",
            cost_tracker=tracker,
            task_acceptance_callback=fail_checkpoint,
        ) is None
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-checkpoint",
            shot_id="shot-checkpoint",
            engine="ACT_ONE",
            operation="performance_capture",
        )
        assert create.calls == 1
        assert attempt["state"] == "accepted_unknown"
        assert attempt["provider_job_id"] == task_id

    forbidden_create = _CreateEndpoint(forbid=True)
    _install_act_client(
        monkeypatch,
        _ActClient(
            forbidden_create,
            _TaskEndpoint(SimpleNamespace(status="PENDING")),
            _UploadEndpoint(forbid=True),
        ),
    )
    with CostTracker(db_path=db, budget_usd=2.0) as tracker:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            poll_timeout_s=0,
            duration_s=5.0,
            shot_id="shot-checkpoint",
            video_id="project-checkpoint",
            cost_tracker=tracker,
        ) is None
        assert forbidden_create.calls == 0


def test_act_two_preclaim_failure_stops_after_uploads_and_before_provider_post(
    monkeypatch,
    tmp_path,
) -> None:
    keyframe, driving, output = _act_files(tmp_path)
    create = _CreateEndpoint(forbid=True)
    uploads = _UploadEndpoint()
    _install_act_client(
        monkeypatch,
        _ActClient(create, _TaskEndpoint(SimpleNamespace(status="PENDING")), uploads),
    )

    def fail_preclaim() -> None:
        raise OSError("deployment authority response was ambiguous")

    with CostTracker(db_path=str(tmp_path / "preclaim.db"), budget_usd=2.0) as tracker:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            duration_s=5.0,
            shot_id="shot-preclaim",
            video_id="project-preclaim",
            cost_tracker=tracker,
            task_submission_callback=fail_preclaim,
        ) is None
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-preclaim",
            shot_id="shot-preclaim",
            engine="ACT_ONE",
            operation="performance_capture",
        )
        assert len(uploads.calls) == 2
        assert create.calls == 0
        assert attempt["state"] == "accepted_unknown"
        assert attempt["provider_job_id"] == ""


def test_act_two_claim_create_and_remote_ack_order_is_strict(
    monkeypatch,
    tmp_path,
) -> None:
    keyframe, driving, output = _act_files(tmp_path)
    events = []
    create = _CreateEndpoint(task_id="d9f3cd8d-55c8-4a26-b2c4-b3ea0b0d7f9b")
    original_create = create.create

    def ordered_create(**kwargs):
        events.append("create")
        return original_create(**kwargs)

    create.create = ordered_create
    _install_act_client(
        monkeypatch,
        _ActClient(create, _TaskEndpoint(SimpleNamespace(status="PENDING"))),
    )
    with CostTracker(db_path=str(tmp_path / "ordering.db"), budget_usd=2.0) as tracker:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            poll_timeout_s=0,
            duration_s=5.0,
            shot_id="shot-order",
            video_id="project-order",
            cost_tracker=tracker,
            task_submission_callback=lambda: events.append("claim"),
            task_acceptance_callback=lambda _task_id: events.append("ack"),
        ) is None
    assert events == ["claim", "create", "ack"]


def test_act_two_unexpected_post_exception_stays_accepted_unknown(
    monkeypatch,
    tmp_path,
) -> None:
    keyframe, driving, output = _act_files(tmp_path)
    create = _CreateEndpoint()
    create.error = ValueError("response parsing failed after POST")

    def raising_create(**_kwargs):
        create.calls += 1
        raise create.error

    create.create = raising_create
    _install_act_client(
        monkeypatch,
        _ActClient(create, _TaskEndpoint(SimpleNamespace(status="PENDING"))),
    )
    with CostTracker(db_path=str(tmp_path / "ambiguous.db"), budget_usd=2.0) as tracker:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            duration_s=5.0,
            shot_id="shot-ambiguous",
            video_id="project-ambiguous",
            cost_tracker=tracker,
        ) is None
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-ambiguous",
            shot_id="shot-ambiguous",
            engine="ACT_ONE",
            operation="performance_capture",
        )
        assert create.calls == 1
        assert attempt["state"] == "accepted_unknown"
        assert attempt["provider_job_id"] == ""


def test_act_two_upload_failure_releases_unbilled_reservation_without_submit(
    monkeypatch, tmp_path
) -> None:
    keyframe, driving, output = _act_files(tmp_path)
    create = _CreateEndpoint(forbid=True)
    uploads = _UploadEndpoint(error=OSError("upload failed"))
    _install_act_client(
        monkeypatch,
        _ActClient(create, _TaskEndpoint(SimpleNamespace(status="PENDING")), uploads),
    )

    with CostTracker(db_path=str(tmp_path / "act-upload.db"), budget_usd=2.0) as tracker:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            duration_s=5.0,
            shot_id="shot-upload",
            video_id="project-upload",
            cost_tracker=tracker,
        ) is None
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-upload",
            shot_id="shot-upload",
            engine="ACT_ONE",
            operation="performance_capture",
        )
        assert create.calls == 0
        assert len(uploads.calls) == 1
        assert attempt["state"] == "failed_unbilled"
        assert attempt["provider_job_id"] == ""
        assert attempt["failure_code"] == "UPLOAD_OSERROR"
        assert tracker.get_paid_attempts_snapshot("project-upload")["active_reservation_usd"] == 0


def test_act_two_post_accept_auth_error_keeps_task_reserved(monkeypatch, tmp_path) -> None:
    import runwayml

    keyframe, driving, output = _act_files(tmp_path)
    request = httpx.Request(
        "GET", "https://api.dev.runwayml.com/v1/tasks/act-auth-task"
    )
    response = httpx.Response(401, request=request)
    auth_error = runwayml.AuthenticationError(
        "expired while retrieving", response=response, body=None
    )

    class _AuthFailureTasks:
        def retrieve(self, *, id: str):  # noqa: A002 - provider signature
            raise auth_error

    create = _CreateEndpoint(task_id="act-auth-task")
    _install_act_client(
        monkeypatch,
        _ActClient(create, _AuthFailureTasks()),
    )

    with CostTracker(db_path=str(tmp_path / "act-auth.db"), budget_usd=2.0) as tracker:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            duration_s=5.0,
            shot_id="shot-auth",
            video_id="project-auth",
            cost_tracker=tracker,
        ) is None
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-auth",
            shot_id="shot-auth",
            engine="ACT_ONE",
            operation="performance_capture",
        )
        assert attempt["state"] == "accepted_unknown"
        assert attempt["provider_job_id"] == "act-auth-task"
        assert attempt["billed"] is None
        assert tracker.get_paid_attempts_snapshot("project-auth")[
            "active_reservation_usd"
        ] == pytest.approx(0.25)
        assert tracker.get_video_cost("project-auth")["total_usd"] == 0


def test_act_two_safety_failure_is_billed_and_not_ambiguous(monkeypatch, tmp_path) -> None:
    keyframe, driving, output = _act_files(tmp_path)
    _install_act_client(
        monkeypatch,
        _ActClient(
            _CreateEndpoint(task_id="act-moderated"),
            _TaskEndpoint(
                SimpleNamespace(
                    status="FAILED",
                    output=None,
                    failure="SAFETY.INPUT",
                )
            ),
        ),
    )
    with CostTracker(db_path=str(tmp_path / "act-moderated.db"), budget_usd=2.0) as tracker:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            duration_s=5.0,
            shot_id="shot-moderated",
            video_id="project-moderated",
            cost_tracker=tracker,
        ) is None
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-moderated",
            shot_id="shot-moderated",
            engine="ACT_ONE",
            operation="performance_capture",
        )
        assert attempt["state"] == "failed_billed"
        assert attempt["failure_code"] == "SAFETY.INPUT"
        assert tracker.get_video_cost("project-moderated")["total_usd"] == pytest.approx(0.25)


def test_act_two_download_failure_keeps_billed_task_reserved(monkeypatch, tmp_path) -> None:
    keyframe, driving, output = _act_files(tmp_path)
    _install_act_client(
        monkeypatch,
        _ActClient(
            _CreateEndpoint(task_id="act-download"),
            _TaskEndpoint(
                SimpleNamespace(
                    status="SUCCEEDED",
                    output=["https://offline.test/output.mp4"],
                )
            ),
        ),
    )
    monkeypatch.setattr(act_two, "safe_download", lambda *_a, **_k: None)
    with CostTracker(db_path=str(tmp_path / "act-download.db"), budget_usd=2.0) as tracker:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            duration_s=5.0,
            shot_id="shot-download",
            video_id="project-download",
            cost_tracker=tracker,
        ) is None
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-download",
            shot_id="shot-download",
            engine="ACT_ONE",
            operation="performance_capture",
        )
        assert attempt["state"] == "accepted_unknown"
        assert attempt["billed"] is True
        assert tracker.get_paid_attempts_snapshot("project-download")["active_reservation_usd"] == pytest.approx(0.25)


def test_act_two_output_then_ledger_failure_stays_recoverable(monkeypatch, tmp_path) -> None:
    keyframe, driving, output = _act_files(tmp_path)
    _install_act_client(
        monkeypatch,
        _ActClient(
            _CreateEndpoint(task_id="act-ledger"),
            _TaskEndpoint(
                SimpleNamespace(
                    status="SUCCEEDED",
                    output=["https://offline.test/output.mp4"],
                )
            ),
        ),
    )

    def download(_url, destination, **_kwargs):
        with open(destination, "wb") as handle:
            handle.write(b"video")
        return destination

    monkeypatch.setattr(act_two, "safe_download", download)
    tracker = CostTracker(db_path=str(tmp_path / "act-ledger.db"), budget_usd=2.0)
    original = tracker.reconcile_paid_attempt
    monkeypatch.setattr(
        tracker,
        "reconcile_paid_attempt",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("ledger unavailable")),
    )
    try:
        assert act_two.generate_act_two_performance(
            keyframe,
            "",
            output,
            driving_video_path=driving,
            duration_s=5.0,
            shot_id="shot-ledger",
            video_id="project-ledger",
            cost_tracker=tracker,
        ) is None
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-ledger",
            shot_id="shot-ledger",
            engine="ACT_ONE",
            operation="performance_capture",
        )
        assert attempt["state"] == "accepted_unknown"
        assert attempt["provider_job_id"] == "act-ledger"
        assert (tmp_path / "output.mp4").exists()
    finally:
        monkeypatch.setattr(tracker, "reconcile_paid_attempt", original)
        tracker.close()


def test_runway_gen4_network_loss_then_restart_resumes_without_fallback_or_resubmit(
    monkeypatch, tmp_path
) -> None:
    import runwayml
    import performance.runway_tasks as runway_tasks

    image = tmp_path / "frame.jpg"
    image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 16)
    output = tmp_path / "runway.mp4"
    db = str(tmp_path / "runway-restart.db")
    create = _CreateEndpoint(task_id="runway-restart-task")
    unavailable_tasks = _TaskEndpoint(TimeoutError("network lost"))

    def retrieve_unavailable(*, id: str):  # noqa: A002 - provider signature
        raise TimeoutError("network lost")

    unavailable_tasks.retrieve = retrieve_unavailable
    first_client = SimpleNamespace(
        image_to_video=create,
        tasks=unavailable_tasks,
    )
    monkeypatch.setattr(runwayml, "RunwayML", lambda **_: first_client)
    monkeypatch.setattr(runway_tasks.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "settings",
        SimpleNamespace(
            runwayml_api_secret="offline",
            ltx_api_key="",
            fal_key="",
        ),
    )
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        lambda: RuntimeSnapshot(
            credentials={"runwayml_api_secret"},
            modules={"runwayml"},
        ),
    )
    monkeypatch.setattr(phase_c_ffmpeg, "_accept_or_reject", lambda *_: True)
    ctx = PipelineContext(
        global_settings={"aspect_ratio": "16:9", "cascade_retry_limit": 0}
    )
    cascade: dict = {}
    first = CostTracker(db_path=db, budget_usd=5.0)
    try:
        assert phase_c_ffmpeg.generate_ai_video(
            str(image),
            "zoom_in_slow",
            "RUNWAY_GEN4",
            str(output),
            shot_type="medium",
            ctx=ctx,
            _cascade_out=cascade,
            cost_tracker=first,
            shot_id="shot-runway",
            video_id="project-runway",
        ) is None
        assert cascade["attempt_history"] == ["RUNWAY_GEN4"]
        assert cascade["deferred_job"]["reason"] == "retrieval_ambiguous"
        attempt = first.get_latest_paid_attempt(
            video_id="project-runway",
            shot_id="shot-runway",
            engine="RUNWAY_GEN4",
            operation="motion_generation",
        )
        assert attempt["state"] == "accepted_unknown"
        assert attempt["provider_job_id"] == "runway-restart-task"
    finally:
        first.close()

    create_restart = _CreateEndpoint(forbid=True)
    second_client = SimpleNamespace(
        image_to_video=create_restart,
        tasks=_TaskEndpoint(
            SimpleNamespace(
                status="SUCCEEDED",
                output=["https://offline.test/runway.mp4"],
            )
        ),
    )
    monkeypatch.setattr(runwayml, "RunwayML", lambda **_: second_client)

    def download(_url, destination, **_kwargs):
        with open(destination, "wb") as handle:
            handle.write(b"video")
        return destination

    monkeypatch.setattr(phase_c_ffmpeg, "safe_download", download)
    resumed = CostTracker(db_path=db, budget_usd=5.0)
    try:
        assert phase_c_ffmpeg.generate_ai_video(
            str(image),
            "zoom_in_slow",
            "RUNWAY_GEN4",
            str(output),
            shot_type="medium",
            ctx=ctx,
            _cascade_out={},
            cost_tracker=resumed,
            shot_id="shot-runway",
            video_id="project-runway",
        ) == str(output)
        assert create_restart.calls == 0
        settled = resumed.get_latest_paid_attempt(
            video_id="project-runway",
            shot_id="shot-runway",
            engine="RUNWAY_GEN4",
            operation="motion_generation",
        )
        assert settled["state"] == "succeeded"
        assert resumed.get_video_cost("project-runway")["total_usd"] == pytest.approx(0.50)
    finally:
        resumed.close()


def test_runway_permanent_billed_failure_never_enters_paid_fallback_chain(
    monkeypatch, tmp_path
) -> None:
    import runwayml

    image = tmp_path / "moderated.jpg"
    image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 16)
    create = _CreateEndpoint(task_id="runway-safety-task")
    client = SimpleNamespace(
        image_to_video=create,
        tasks=_TaskEndpoint(
            SimpleNamespace(
                status="FAILED",
                output=None,
                failure="SAFETY.INPUT",
            )
        ),
    )
    monkeypatch.setattr(runwayml, "RunwayML", lambda **_: client)
    fal_tripwire = SimpleNamespace(
        upload_file=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("permanent Runway failure must not enter VEO fallback")
        ),
        subscribe=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("permanent Runway failure must not enter VEO fallback")
        ),
    )
    monkeypatch.setattr(phase_c_ffmpeg, "fal_client", fal_tripwire, raising=False)
    monkeypatch.setattr(phase_c_ffmpeg, "FAL_AVAILABLE", True)
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "settings",
        SimpleNamespace(
            runwayml_api_secret="offline",
            ltx_api_key="",
            fal_key="offline",
        ),
    )
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        lambda: RuntimeSnapshot(
            credentials={"runwayml_api_secret", "fal_key"},
            modules={"runwayml", "fal_client"},
        ),
    )
    cascade: dict = {}
    with CostTracker(db_path=str(tmp_path / "runway-safety.db"), budget_usd=5.0) as tracker:
        assert phase_c_ffmpeg.generate_ai_video(
            str(image),
            "zoom_in_slow",
            "RUNWAY_GEN4",
            str(tmp_path / "moderated.mp4"),
            video_fallbacks=["VEO"],
            shot_type="medium",
            ctx=PipelineContext(global_settings={"aspect_ratio": "16:9"}),
            _cascade_out=cascade,
            cost_tracker=tracker,
            shot_id="shot-safety",
            video_id="project-safety",
        ) is None
        assert cascade["attempt_history"] == ["RUNWAY_GEN4"]
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-safety",
            shot_id="shot-safety",
            engine="RUNWAY_GEN4",
            operation="motion_generation",
        )
        assert attempt["state"] == "failed_billed"
        assert tracker.get_video_cost("project-safety")["total_usd"] == pytest.approx(0.5)
