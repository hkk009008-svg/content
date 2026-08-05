from __future__ import annotations

import multiprocessing
import threading
import time
from pathlib import Path

import pytest
from filelock import FileLock

import project_manager
import web_server
from pipeline_jobs import PipelineJobStore


class _NoopDispatcher:
    def wake(self) -> None:
        pass


def _hold_cross_process_operation_lock(
    path: str,
    ready,
    release,
) -> None:
    """Spawn-safe lock holder for the admission/admin race regression."""

    with FileLock(path, timeout=5, mode=0o600):
        ready.set()
        release.wait(5)


@pytest.fixture()
def isolated_queue(tmp_path, monkeypatch):
    current = web_server._pipeline_job_dispatcher
    if current is not None:
        current.stop(wait=True, timeout=2)
    jobs = PipelineJobStore(tmp_path / "pipeline-jobs.db")
    original_store = web_server._pipeline_job_store
    web_server._pipeline_job_store = jobs
    web_server._pipeline_job_dispatcher = None
    web_server.app.config["TESTING"] = True
    yield jobs
    dispatcher = web_server._pipeline_job_dispatcher
    if dispatcher is not None:
        dispatcher.stop(wait=True, timeout=2)
    with web_server._pipelines_lock:
        web_server._running_pipelines.clear()
        buses = list(web_server._progress_queues.values())
        web_server._progress_queues.clear()
    for bus in buses:
        bus.close()
    web_server._pipeline_job_store = original_store
    # A stopped dispatcher cannot be restarted; let later tests/runtime
    # lazily construct a fresh one against the restored store.
    web_server._pipeline_job_dispatcher = None


@pytest.fixture()
def queued_project(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    monkeypatch.setattr("domain.project_manager.PROJECTS_DIR", str(projects))
    return project_manager.create_project("Durable Queue")


def test_generate_is_202_idempotent_and_pipeline_state_has_queue(
    isolated_queue, queued_project, monkeypatch
):
    monkeypatch.setattr(web_server, "_ensure_pipeline_dispatcher", lambda: _NoopDispatcher())
    pid = queued_project["id"]

    with web_server.app.test_client() as client:
        first = client.post(f"/api/projects/{pid}/generate")
        second = client.post(f"/api/projects/{pid}/generate", json={"resume": True})
        state = client.get(f"/api/projects/{pid}/pipeline-state")

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.get_json()["job_id"] == second.get_json()["job_id"]
    assert first.get_json()["idempotent"] is False
    assert second.get_json()["idempotent"] is True
    # The first accepted intent is immutable; a duplicate click cannot turn a
    # fresh paid run into a different resume mode.
    assert second.get_json()["resume"] is False
    body = state.get_json()
    assert body["running"] is True
    assert body["allowed_actions"] == ["cancel"]
    assert body["queue"]["state"] == "queued"
    assert body["queue"]["position"] == 1


def test_cancel_before_claim_is_durable_and_closes_start_authority(
    isolated_queue, queued_project, monkeypatch
):
    monkeypatch.setattr(web_server, "_ensure_pipeline_dispatcher", lambda: _NoopDispatcher())
    pid = queued_project["id"]

    with web_server.app.test_client() as client:
        accepted = client.post(f"/api/projects/{pid}/generate")
        cancelled = client.post(f"/api/projects/{pid}/cancel")
        state = client.get(f"/api/projects/{pid}/pipeline-state")

    assert accepted.status_code == 202
    assert cancelled.status_code == 200
    assert cancelled.get_json()["cancelled"] is True
    assert cancelled.get_json()["queue"]["state"] == "cancelled"
    assert state.get_json()["running"] is False
    assert state.get_json()["allowed_actions"] == ["start"]
    assert isolated_queue.claim("should-not-run", max_concurrency=1) is None


def test_expired_unverifiable_job_requires_acknowledgement_before_abandonment(
    isolated_queue, queued_project
):
    pid = queued_project["id"]
    queued, _ = isolated_queue.enqueue(pid, resume=False)
    running = isolated_queue.claim(
        "legacy-worker-without-fence",
        max_concurrency=1,
        lease_seconds=1,
        now=time.time() - 5,
    )
    assert running is not None

    with web_server.app.test_client() as client:
        missing_ack = client.post(
            f"/api/projects/{pid}/queue/abandon",
            json={"job_id": running.job_id},
        )
        abandoned = client.post(
            f"/api/projects/{pid}/queue/abandon",
            json={
                "job_id": running.job_id,
                "acknowledge_paid_work_risk": True,
            },
        )
        state = client.get(f"/api/projects/{pid}/pipeline-state")

    assert missing_ack.status_code == 400
    assert missing_ack.get_json()["code"] == "operator_acknowledgement_required"
    assert abandoned.status_code == 200
    assert abandoned.get_json()["abandoned"] is True
    assert abandoned.get_json()["queue"]["state"] == "cancelled"
    assert state.get_json()["queue"]["state"] == "cancelled"
    assert state.get_json()["allowed_actions"][0] == "start"


def test_unknown_project_never_creates_project_or_queue_artifacts(
    isolated_queue, tmp_path, monkeypatch
):
    projects = tmp_path / "projects"
    monkeypatch.setattr("domain.project_manager.PROJECTS_DIR", str(projects))

    with web_server.app.test_client() as client:
        response = client.post("/api/projects/missing-project/generate")

    assert response.status_code == 404
    assert not (projects / "missing-project").exists()
    assert isolated_queue.project_job("missing-project") is None


def test_cross_process_admin_lock_and_queue_row_exclude_both_race_orderings(
    isolated_queue, queued_project, monkeypatch
):
    monkeypatch.setattr(web_server, "_ensure_pipeline_dispatcher", lambda: _NoopDispatcher())
    monkeypatch.setattr(web_server, "HTTP_PROJECT_TIMEOUT", 0.1)
    pid = queued_project["id"]
    project_root = Path(web_server.get_project_dir(pid)).parent
    lock_path = str(project_root / f".{pid}.operation.lock")
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_cross_process_operation_lock,
        args=(lock_path, ready, release),
    )
    process.start()
    try:
        assert ready.wait(5), "child never acquired the cross-process admin lock"
        with web_server.app.test_client() as client:
            blocked_generate = client.post(f"/api/projects/{pid}/generate")
        assert blocked_generate.status_code == 409
        assert blocked_generate.get_json()["code"] == "project_locked"
        assert isolated_queue.project_job(pid) is None
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(2)
    assert process.exitcode == 0

    # Reverse ordering: once SQLite owns an active queue row, a later admin
    # operation may acquire the short admission lock but must still refuse the
    # delete. The project remains present for the eventual worker.
    with web_server.app.test_client() as client:
        accepted = client.post(f"/api/projects/{pid}/generate")
        blocked_delete = client.delete(f"/api/projects/{pid}")
    assert accepted.status_code == 202
    assert blocked_delete.status_code == 409
    assert blocked_delete.get_json()["code"] == "project_busy"
    assert Path(web_server.get_project_dir(pid), "project.json").is_file()


def test_bounded_dispatcher_runs_pipeline_and_records_terminal_state(
    isolated_queue, queued_project, monkeypatch
):
    pid = queued_project["id"]
    calls: list[bool] = []
    generated = threading.Event()

    class FakePipeline:
        def __init__(self, _pid, core=None, progress_callback=None):
            self.paused = False
            self.cancelled = False

        def generate(self, resume=False):
            calls.append(resume)
            generated.set()
            return "final.mp4"

        def cancel(self):
            self.cancelled = True

    monkeypatch.setattr(web_server, "CinemaPipeline", FakePipeline)
    monkeypatch.setattr(web_server, "_get_or_build_core", lambda _pid: object())

    with web_server.app.test_client() as client:
        response = client.post(f"/api/projects/{pid}/generate", json={"resume": True})

    assert response.status_code == 202
    assert generated.wait(2)
    job_id = response.get_json()["job_id"]
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = isolated_queue.get(job_id)
        if job is not None and job.state == "succeeded":
            break
        time.sleep(0.01)
    assert job is not None and job.state == "succeeded"
    assert calls == [True]
    worker_threads = [
        thread for thread in threading.enumerate()
        if thread.name.startswith("pipeline-queue-worker-")
    ]
    assert len(worker_threads) <= 1
