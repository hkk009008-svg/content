from __future__ import annotations

import fcntl
import os
import threading
import time
import uuid

import pytest

from pipeline_jobs import (
    JobExecutionContext,
    PipelineJobDispatcher,
    PipelineJobStore,
    pipeline_job_db_path,
    pipeline_queue_concurrency,
    safe_error_summary,
)


def store(tmp_path) -> PipelineJobStore:
    return PipelineJobStore(tmp_path / "pipeline-jobs.db")


def stopped_worker(jobs: PipelineJobStore, index: int = 0) -> str:
    """Return a worker ID whose durable process fence is provably unlocked."""

    token = uuid.uuid4().hex
    path = jobs.worker_fence_path(token, create_dir=True)
    path.write_text("stopped test worker\n", encoding="utf-8")
    return f"test-host:123:{token}:{index}"


@pytest.mark.parametrize("value", ["0", "9", "many", "1.5", ""])
def test_concurrency_env_is_fail_closed(value):
    with pytest.raises(ValueError):
        pipeline_queue_concurrency(value)


def test_concurrency_accepts_only_documented_range():
    assert pipeline_queue_concurrency("1") == 1
    assert pipeline_queue_concurrency(8) == 8


@pytest.mark.parametrize("value", ["", ":memory:", "file:data/jobs.db"])
def test_job_db_rejects_non_durable_paths(value):
    with pytest.raises(ValueError):
        pipeline_job_db_path(value)


def test_enqueue_is_idempotent_and_keeps_original_resume_intent(tmp_path):
    jobs = store(tmp_path)

    first, created = jobs.enqueue("project-a", resume=False)
    duplicate, duplicate_created = jobs.enqueue("project-a", resume=True)

    assert created is True
    assert duplicate_created is False
    assert duplicate.job_id == first.job_id
    assert duplicate.requested_resume is False
    assert jobs.project_snapshot("project-a")["position"] == 1


def test_concurrent_stores_return_one_stable_active_job(tmp_path):
    path = tmp_path / "shared.db"
    left = PipelineJobStore(path)
    right = PipelineJobStore(path)
    barrier = threading.Barrier(2)
    results: list[tuple[str, bool]] = []

    def enqueue(jobs: PipelineJobStore):
        barrier.wait()
        job, created = jobs.enqueue("project-a", resume=False)
        results.append((job.job_id, created))

    threads = [threading.Thread(target=enqueue, args=(left,)), threading.Thread(target=enqueue, args=(right,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(3)

    assert len(results) == 2
    assert len({job_id for job_id, _ in results}) == 1
    assert sorted(created for _, created in results) == [False, True]


def test_claim_enforces_global_cap_across_store_instances(tmp_path):
    path = tmp_path / "shared.db"
    left = PipelineJobStore(path)
    right = PipelineJobStore(path)
    left.enqueue("project-a", resume=False)
    left.enqueue("project-b", resume=False)

    claimed = left.claim("worker-left", max_concurrency=1, lease_seconds=30)
    blocked = right.claim("worker-right", max_concurrency=1, lease_seconds=30)

    assert claimed is not None
    assert blocked is None
    left.finish(claimed.job_id, "worker-left", state="succeeded")
    second = right.claim("worker-right", max_concurrency=1, lease_seconds=30)
    assert second is not None
    assert second.project_id != claimed.project_id


def test_expired_worker_reclaims_same_job_as_checkpoint_resume(tmp_path):
    path = tmp_path / "shared.db"
    first_store = PipelineJobStore(path)
    second_store = PipelineJobStore(path)
    queued, _ = first_store.enqueue("project-a", resume=False)
    first = first_store.claim(
        stopped_worker(first_store),
        max_concurrency=1,
        lease_seconds=2,
        now=queued.created_at + 1,
    )
    assert first is not None and first.effective_resume is False

    recovered = second_store.claim(
        "replacement-worker",
        max_concurrency=1,
        lease_seconds=30,
        now=queued.created_at + 4,
    )

    assert recovered is not None
    assert recovered.job_id == queued.job_id
    assert recovered.resume_required is True
    assert recovered.effective_resume is True
    assert recovered.attempt_count == 2


def test_cancel_before_claim_is_terminal_and_never_claimed(tmp_path):
    jobs = store(tmp_path)
    queued, _ = jobs.enqueue("project-a", resume=False)

    cancelled = jobs.cancel_project("project-a")

    assert cancelled is not None
    assert cancelled.job_id == queued.job_id
    assert cancelled.state == "cancelled"
    assert jobs.claim("worker", max_concurrency=1) is None


def test_running_cancel_intent_wins_over_worker_success(tmp_path):
    jobs = store(tmp_path)
    jobs.enqueue("project-a", resume=False)
    running = jobs.claim("worker", max_concurrency=1)
    assert running is not None

    requested = jobs.cancel_project("project-a")
    finished = jobs.finish(running.job_id, "worker", state="succeeded")

    assert requested is not None and requested.cancel_requested is True
    assert finished is not None and finished.state == "cancelled"


def test_expired_cancelled_worker_is_not_requeued(tmp_path):
    jobs = store(tmp_path)
    queued, _ = jobs.enqueue("project-a", resume=False)
    running = jobs.claim(
        stopped_worker(jobs), max_concurrency=1, lease_seconds=1,
        now=queued.created_at + 1,
    )
    assert running is not None
    jobs.cancel_project("project-a")

    assert jobs.recover_expired(now=queued.created_at + 3) == 1
    recovered = jobs.project_job("project-a")
    assert recovered is not None and recovered.state == "cancelled"
    assert jobs.claim("replacement", max_concurrency=1, now=queued.created_at + 4) is None


def test_expired_lease_is_not_reclaimed_while_owner_process_fence_is_live(tmp_path):
    jobs = store(tmp_path)
    queued, _ = jobs.enqueue("project-a", resume=False)
    token = uuid.uuid4().hex
    fence_path = jobs.worker_fence_path(token, create_dir=True)
    descriptor = os.open(fence_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    worker_id = f"test-host:123:{token}:0"
    try:
        running = jobs.claim(
            worker_id,
            max_concurrency=1,
            lease_seconds=1,
            now=queued.created_at + 1,
        )
        assert running is not None

        assert jobs.recover_expired(now=queued.created_at + 3) == 0
        still_running = jobs.project_job("project-a", active_only=True)
        assert still_running is not None and still_running.state == "running"
        assert "owner fence remains active" in (still_running.safe_error or "")
        assert jobs.claim(
            "replacement", max_concurrency=1, now=queued.created_at + 4
        ) is None
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def test_unverifiable_expired_owner_fails_closed_instead_of_replaying(tmp_path):
    jobs = store(tmp_path)
    queued, _ = jobs.enqueue("project-a", resume=False)
    running = jobs.claim(
        "legacy-worker-without-fence",
        max_concurrency=1,
        lease_seconds=1,
        now=queued.created_at + 1,
    )
    assert running is not None

    assert jobs.recover_expired(now=queued.created_at + 3) == 0
    snapshot = jobs.project_snapshot("project-a", active_only=True)
    assert snapshot is not None and snapshot["state"] == "running"
    assert "owner fence is unverifiable" in (snapshot["error"] or "")


def test_operator_can_abandon_only_exact_expired_unverifiable_job(tmp_path):
    jobs = store(tmp_path)
    queued, _ = jobs.enqueue("project-a", resume=False)
    running = jobs.claim(
        "legacy-worker-without-fence",
        max_concurrency=1,
        lease_seconds=1,
        now=queued.created_at + 1,
    )
    assert running is not None

    active, outcome = jobs.abandon_unverifiable(
        "project-a", running.job_id, now=queued.created_at + 1.5
    )
    assert outcome == "lease_active"
    assert active is not None and active.state == "running"

    abandoned, outcome = jobs.abandon_unverifiable(
        "project-a", running.job_id, now=queued.created_at + 3
    )
    assert outcome == "abandoned"
    assert abandoned is not None and abandoned.state == "cancelled"
    assert abandoned.cancel_requested is True
    assert "Operator abandoned expired job" in (abandoned.safe_error or "")

    unchanged, outcome = jobs.abandon_unverifiable(
        "project-a", running.job_id, now=queued.created_at + 4
    )
    assert outcome == "not_running"
    assert unchanged is not None and unchanged.state == "cancelled"


def test_operator_cannot_abandon_expired_job_with_live_owner_fence(tmp_path):
    jobs = store(tmp_path)
    queued, _ = jobs.enqueue("project-a", resume=False)
    token = uuid.uuid4().hex
    fence_path = jobs.worker_fence_path(token, create_dir=True)
    descriptor = os.open(fence_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        running = jobs.claim(
            f"test-host:123:{token}:0",
            max_concurrency=1,
            lease_seconds=1,
            now=queued.created_at + 1,
        )
        assert running is not None
        active, outcome = jobs.abandon_unverifiable(
            "project-a", running.job_id, now=queued.created_at + 3
        )
        assert outcome == "owner_live"
        assert active is not None and active.state == "running"
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def test_dispatcher_stop_leaves_active_lease_for_recovery(tmp_path):
    jobs = store(tmp_path)
    jobs.enqueue("project-a", resume=False)
    entered = threading.Event()
    release = threading.Event()

    def handler(_job, _context: JobExecutionContext):
        entered.set()
        release.wait(3)

    dispatcher = PipelineJobDispatcher(
        jobs,
        handler,
        concurrency=1,
        lease_seconds=1,
        poll_seconds=0.01,
    )
    dispatcher.start()
    dispatcher.wake()
    assert entered.wait(2)

    dispatcher.stop(wait=False)
    active = jobs.project_job("project-a", active_only=True)
    assert active is not None and active.state == "running"

    release.set()
    dispatcher.stop(wait=True, timeout=2)
    still_active = jobs.project_job("project-a", active_only=True)
    assert still_active is not None and still_active.state == "running"


def test_dispatcher_cancels_local_handler_when_heartbeat_authority_is_lost(
    tmp_path, monkeypatch
):
    jobs = store(tmp_path)
    jobs.enqueue("project-a", resume=False)
    entered = threading.Event()
    cancelled = threading.Event()

    def handler(_job, context: JobExecutionContext):
        entered.set()
        deadline = time.monotonic() + 3
        while not context.cancel_requested and time.monotonic() < deadline:
            time.sleep(0.01)
        if context.lease_lost:
            cancelled.set()

    def failed_heartbeat(*_args, **_kwargs):
        raise OSError("simulated durable-store outage")

    monkeypatch.setattr(jobs, "heartbeat", failed_heartbeat)
    dispatcher = PipelineJobDispatcher(
        jobs,
        handler,
        concurrency=1,
        lease_seconds=0.3,
        poll_seconds=0.01,
    )
    dispatcher.start()
    dispatcher.wake()
    assert entered.wait(2)
    assert cancelled.wait(2)

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = jobs.project_job("project-a")
        if job is not None and job.state == "cancelled":
            break
        time.sleep(0.01)
    assert jobs.project_job("project-a").state == "cancelled"
    dispatcher.stop(wait=True, timeout=2)


def test_safe_error_summary_is_bounded_and_redacts_secretish_values():
    error = RuntimeError(
        "token=do-not-print\nprovider disappeared "
        "https://cdn.example/output?Signature=url-secret&Expires=123"
    )
    summary = safe_error_summary(error, limit=80)
    assert "do-not-print" not in summary
    assert "url-secret" not in summary
    assert "[redacted]" in summary
    assert "\n" not in summary
    assert len(summary) <= 80
