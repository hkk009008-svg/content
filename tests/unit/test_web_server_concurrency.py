"""
tests/unit/test_web_server_concurrency.py — Thread-stress tests for
the _running_pipelines / _progress_queues race fixes (Session 9).

Audit ref: docs/AUDIT-P3-1-concurrency-2026-05-24.md (commit e164505)
Feat ref:  bfa60bf — feat(web): close _running_pipelines / _progress_queues race surfaces

Uses threading.Barrier for deterministic race overlap and
threading.Event for controllable blocking of the fake CinemaPipeline
ctor. Flask's app.test_client() is used for single-threaded HTTP-level
tests. For race tests that need multiple threads hitting the same
endpoint simultaneously, we call api_generate() directly inside a Flask
test_request_context — Flask's test_client is not safe to call from
multiple threads (contextvar LookupError). The brief explicitly
sanctions this fallback.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import web_server
from web_server import (
    _PIPELINE_PENDING,
    _ensure_progress_queue,
    _get_running_pipeline,
    _pipelines_lock,
    _progress_queues,
    _running_pipelines,
    api_generate,
    app,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_pipeline_state():
    """Clear _running_pipelines and _progress_queues before and after each
    test so tests don't leak state into each other."""
    with _pipelines_lock:
        _running_pipelines.clear()
        _progress_queues.clear()
    yield
    with _pipelines_lock:
        _running_pipelines.clear()
        _progress_queues.clear()


@pytest.fixture()
def client():
    """Flask test client with testing mode enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _make_fake_pipeline_class(
    *,
    block_event: threading.Event | None = None,
    store_ref: list | None = None,
):
    """Return a fake CinemaPipeline class.

    block_event: if provided, __init__ will block until the event is set.
    store_ref:   if provided, the constructed instance is appended so the
                 test can inspect it.
    """

    class FakeCinemaPipeline:
        def __init__(self, pid, core=None, progress_callback=None):
            if block_event is not None:
                block_event.wait()
            self.pid = pid
            self.cancelled = False
            if store_ref is not None:
                store_ref.append(self)

        def generate(self, resume=False):
            return "done"

        def cancel(self):
            self.cancelled = True

        def pause(self):
            pass

        def resume(self):
            pass

        def get_state(self):
            return {"paused": False, "cancelled": self.cancelled}

    return FakeCinemaPipeline


def _fake_load_project(pid):
    return {"id": pid, "name": "Test", "scenes": [], "characters": []}


def _fake_get_or_build_core(pid):
    return MagicMock()


# ---------------------------------------------------------------------------
# Test 1 — Exactly one concurrent POST /generate wins; the other gets 409
# ---------------------------------------------------------------------------

def test_concurrent_generate_only_one_wins():
    """Spin 2 threads that call api_generate() for the same pid simultaneously.
    The sentinel-pattern lock guarantees exactly one 200 and one 409.

    Uses threading.Barrier(2) to maximize race overlap. Patches
    CinemaPipeline with a fake that has a blocking init so the race
    window is observable.

    NOTE: Flask's test_client cannot be called from multiple threads
    (contextvar LookupError). We call api_generate() directly inside a
    test_request_context() — equivalent semantics; brief sanctions fallback.
    """
    pid = "test_proj_concurrent"
    ctor_entered = threading.Event()
    ctor_release = threading.Event()
    barrier = threading.Barrier(2)
    results: list[int] = []

    class SlowFake:
        def __init__(self, _pid, core=None, progress_callback=None):
            ctor_entered.set()
            # Block until the test joins both racing threads (see below).
            # Timeout > t.join(5) safety margin guards against test-thread hang.
            ctor_release.wait(timeout=10.0)

        def generate(self, resume=False):
            return "done"

        def cancel(self):
            pass

    with (
        patch("web_server.CinemaPipeline", SlowFake),
        patch("web_server.load_project", side_effect=lambda p: _fake_load_project(p)),
        patch("web_server._get_or_build_core", side_effect=lambda p: MagicMock()),
    ):
        def do_generate():
            barrier.wait()  # both threads enter simultaneously
            with app.test_request_context(
                f"/api/projects/{pid}/generate",
                method="POST",
                json={},
            ):
                resp = api_generate(pid)
                # Response is a tuple (response, status) or a Response object
                if isinstance(resp, tuple):
                    results.append(resp[1])
                else:
                    results.append(resp.status_code)

        t1 = threading.Thread(target=do_generate)
        t2 = threading.Thread(target=do_generate)
        t1.start()
        t2.start()

        # Wait for the winning bg thread to enter SlowFake.__init__
        # (sentinel installed, ctor blocked on ctor_release).
        ctor_entered.wait(timeout=3.0)

        # Join test threads BEFORE releasing the bg thread. With the bg
        # thread still blocked, the sentinel stays in _running_pipelines,
        # so the loser thread MUST see it and return 409. Without this
        # ordering, in cold runs (no prior warm-up of Flask's request
        # context) the winning bg-thread could complete generate() and
        # pop the sentinel before the losing thread arrives at the lock,
        # letting it also become a winner.
        t1.join(timeout=5)
        t2.join(timeout=5)

        # Both test threads have recorded their lock-race result. Now
        # release the bg thread so its finally-block cleanup runs.
        ctor_release.set()

    assert sorted(results) == [200, 409], (
        f"Expected exactly one 200 and one 409, got {results}"
    )


# ---------------------------------------------------------------------------
# Test 2 — Sentinel is visible during construction, replaced by real pipeline
# ---------------------------------------------------------------------------

def test_pending_sentinel_visible_during_construction(client):
    """Block CinemaPipeline.__init__ on a threading.Event. While blocked,
    assert _running_pipelines[pid] IS _PIPELINE_PENDING. Then release and
    assert it is replaced with the real fake pipeline."""
    pid = "test_proj_sentinel"
    ctor_release = threading.Event()
    real_instances: list = []
    ctor_entered = threading.Event()

    class BlockingFake:
        def __init__(self, _pid, core=None, progress_callback=None):
            ctor_entered.set()
            ctor_release.wait(timeout=5.0)
            real_instances.append(self)

        def generate(self, resume=False):
            return "done"

        def cancel(self):
            pass

    with (
        patch("web_server.CinemaPipeline", BlockingFake),
        patch("web_server.load_project", side_effect=lambda p: _fake_load_project(p)),
        patch("web_server._get_or_build_core", side_effect=lambda p: MagicMock()),
    ):
        resp = client.post(f"/api/projects/{pid}/generate", json={})
        assert resp.status_code == 200

        # Background thread is now inside the blocking ctor
        ctor_entered.wait(timeout=2.0)

        # Sentinel MUST be in the dict during the ctor window
        assert pid in _running_pipelines, "slot should be reserved"
        assert _running_pipelines[pid] is _PIPELINE_PENDING, (
            "slot should hold sentinel during ctor"
        )

        # Release the ctor
        ctor_release.set()

        # Wait for background thread to replace sentinel
        deadline = time.time() + 3.0
        while time.time() < deadline:
            current = _running_pipelines.get(pid)
            if current is not None and current is not _PIPELINE_PENDING:
                break
            time.sleep(0.01)

        # Sentinel replaced with real instance (or already cleaned up)
        if pid in _running_pipelines:
            assert _running_pipelines[pid] is not _PIPELINE_PENDING


# ---------------------------------------------------------------------------
# Test 3 — Reader helper returns None for both absent AND sentinel states
# ---------------------------------------------------------------------------

def test_reader_helper_skips_sentinel():
    """_get_running_pipeline must return None for absent pid AND sentinel.
    It must return the real pipeline only when a real object is stored."""
    pid = "test_proj_reader"

    # Case 1: absent
    assert _get_running_pipeline(pid) is None

    # Case 2: sentinel
    with _pipelines_lock:
        _running_pipelines[pid] = _PIPELINE_PENDING
    assert _get_running_pipeline(pid) is None

    # Case 3: real pipeline
    fake = MagicMock()
    with _pipelines_lock:
        _running_pipelines[pid] = fake
    assert _get_running_pipeline(pid) is fake

    # Cleanup
    with _pipelines_lock:
        _running_pipelines.pop(pid, None)


# ---------------------------------------------------------------------------
# Test 4 — Cancel during sentinel window returns 404 (not 500 AttributeError)
# ---------------------------------------------------------------------------

def test_reader_handles_sentinel_gracefully(client):
    """Directly populate _running_pipelines[pid] = _PIPELINE_PENDING (simulating
    the construct window). Call /cancel. Must return 404, NOT 500 (which would
    indicate _get_running_pipeline let a bare object() through to .cancel()).
    """
    pid = "test_proj_cancel_sentinel"
    with _pipelines_lock:
        _running_pipelines[pid] = _PIPELINE_PENDING

    resp = client.post(f"/api/projects/{pid}/cancel", json={})
    assert resp.status_code == 404, (
        f"Expected 404 during sentinel window, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Test 5 — Concurrent _ensure_progress_queue returns the same queue instance
# ---------------------------------------------------------------------------

def test_concurrent_ensure_progress_queue_returns_same_queue():
    """Two threads calling _ensure_progress_queue for the same pid must
    both get back the SAME queue.Queue instance (no orphan-queue race).

    Uses threading.Barrier(2) to maximize overlap at the check-then-create
    window.
    """
    pid = "test_proj_queue_race"
    barrier = threading.Barrier(2)
    returned_queues: list[queue.Queue] = []

    def call_ensure():
        barrier.wait()
        q = _ensure_progress_queue(pid)
        returned_queues.append(q)

    t1 = threading.Thread(target=call_ensure)
    t2 = threading.Thread(target=call_ensure)
    t1.start()
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert len(returned_queues) == 2
    assert returned_queues[0] is returned_queues[1], (
        "Both threads must receive the same queue.Queue instance"
    )


# ---------------------------------------------------------------------------
# Test 6 — Four-thread pressure test (bonus: maximizes race window coverage)
# ---------------------------------------------------------------------------

def test_four_concurrent_generate_only_one_wins():
    """Four threads race on the same pid via direct api_generate() calls.
    Exactly one must get 200; the rest must all get 409.
    Uses Barrier(4) for maximum overlap.

    NOTE: Flask test_client is not thread-safe. Direct api_generate()
    call inside test_request_context is used (brief sanctions fallback).
    """
    pid = "test_proj_4way"
    barrier = threading.Barrier(4)
    results: list[int] = []
    ctor_entered = threading.Event()
    ctor_release = threading.Event()

    class SlowFake:
        def __init__(self, _pid, core=None, progress_callback=None):
            ctor_entered.set()
            # See test_concurrent_generate_only_one_wins above for why
            # we wait longer than t.join(5). Same ordering invariant.
            ctor_release.wait(timeout=10.0)

        def generate(self, resume=False):
            return "done"

        def cancel(self):
            pass

    with (
        patch("web_server.CinemaPipeline", SlowFake),
        patch("web_server.load_project", side_effect=lambda p: _fake_load_project(p)),
        patch("web_server._get_or_build_core", side_effect=lambda p: MagicMock()),
    ):
        def do_generate():
            barrier.wait()
            with app.test_request_context(
                f"/api/projects/{pid}/generate",
                method="POST",
                json={},
            ):
                resp = api_generate(pid)
                if isinstance(resp, tuple):
                    results.append(resp[1])
                else:
                    results.append(resp.status_code)

        threads = [threading.Thread(target=do_generate) for _ in range(4)]
        for t in threads:
            t.start()

        # Wait for the winning bg thread to enter SlowFake.__init__
        # (sentinel installed, ctor blocked on ctor_release).
        ctor_entered.wait(timeout=3.0)

        # Join all 4 test threads BEFORE releasing the bg thread. With
        # the bg thread still blocked, the sentinel stays in
        # _running_pipelines, so threads B/C/D MUST see it and return
        # 409. Without this ordering, in cold runs (no prior warm-up
        # of Flask's request context) the winning bg-thread could
        # complete generate() and pop the sentinel before the slower
        # test threads arrived at the lock, letting them also become
        # winners (observed: [200,409,200,200] instead of one 200).
        for t in threads:
            t.join(timeout=5)

        # All 4 lock-race verdicts recorded; release the bg thread so
        # its finally-block cleanup runs.
        ctor_release.set()

    assert results.count(200) == 1, f"Expected exactly 1 success, got {results}"
    assert results.count(409) == 3, f"Expected exactly 3 conflicts, got {results}"


# ---------------------------------------------------------------------------
# Test 7 — After pipeline finishes, the slot is cleaned up (no leak)
# ---------------------------------------------------------------------------

def test_pipeline_slot_cleaned_after_completion(client):
    """After a successful generate run completes, _running_pipelines[pid]
    should no longer exist (finally block pops it)."""
    pid = "test_proj_cleanup"
    done = threading.Event()

    class FastFake:
        def __init__(self, _pid, core=None, progress_callback=None):
            pass

        def generate(self, resume=False):
            done.set()
            return "done"

        def cancel(self):
            pass

    with (
        patch("web_server.CinemaPipeline", FastFake),
        patch("web_server.load_project", side_effect=lambda p: _fake_load_project(p)),
        patch("web_server._get_or_build_core", side_effect=lambda p: MagicMock()),
    ):
        resp = client.post(f"/api/projects/{pid}/generate", json={})
        assert resp.status_code == 200

        # Wait for the pipeline to finish and clean up
        done.wait(timeout=3.0)
        deadline = time.time() + 3.0
        while pid in _running_pipelines and time.time() < deadline:
            time.sleep(0.01)

    assert pid not in _running_pipelines, (
        "Slot should be cleaned up after pipeline completes"
    )
