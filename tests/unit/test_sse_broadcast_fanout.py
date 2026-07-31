"""
tests/unit/test_sse_broadcast_fanout.py — Slice 11a: broadcast-safe SSE
event fan-out with replay.

Defect (audit, pre-11a): every project had exactly ONE queue.Queue in
_progress_queues, and every /stream subscriber called .get() on that SAME
queue. A queue.Queue hands each item to exactly one getter, so two
concurrent listeners competed for the same events instead of each
observing every event, and there were no event ids at all, so a
reconnecting client could not replay anything it missed while
disconnected.

This file pins the replacement contract implemented by _ProjectEventBus /
_ensure_progress_queue / _make_progress_cb / api_stream in web_server.py:

  1. Two subscribers both receive the same published event (bus-level and
     real HTTP-level, including through the actual /generate daemon).
  2. A reconnect presenting Last-Event-ID replays exactly the missed
     suffix, in order, tagged `replayed: true`.
  3. A disconnecting subscriber is removed from the bus (no leak).
  4. The replay buffer cap is enforced; an id older than the cap is
     reported as an explicit GAP event, never silently skipped.
  5. Concurrent publish/subscribe/unsubscribe does not deadlock.

RED proof (run separately, not part of the pytest suite): a standalone
harness at the scratchpad path used during implementation loads a
git-HEAD snapshot of the pre-11a web_server.py in complete isolation
(via importlib, never touching the real module) and exercises the exact
production entry points (_ensure_progress_queue, _make_progress_cb) to
show that today's single queue.Queue delivers a published event to only
ONE of two competing .get() callers — the identical "two subscribers
both receive the same event" scenario pinned in this file, demonstrated
failing against the unmodified code.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from web_server import (
    _EVENT_REPLAY_CAP,
    _ProjectEventBus,
    _SUBSCRIBER_INBOX_CAP,
    _ensure_progress_queue,
    _make_progress_cb,
    _pipelines_lock,
    _progress_queues,
    _running_pipelines,
    app,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_pipeline_state():
    """Clear _running_pipelines and _progress_queues before and after each
    test — mirrors tests/unit/test_web_server_concurrency.py's fixture so
    this file can safely exercise the real /generate + /stream routes
    without leaking state into (or picking up state from) other tests."""
    with _pipelines_lock:
        _running_pipelines.clear()
        _progress_queues.clear()
    yield
    with _pipelines_lock:
        _running_pipelines.clear()
        _progress_queues.clear()


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _sse_body(chunk: bytes) -> dict:
    """Parse one `data: {...}\\n\\n` (optionally `id: N\\n`-prefixed) wire
    frame back into its JSON body for robust (order-independent) asserts."""
    text = chunk.decode()
    return json.loads(text.split("data: ", 1)[1])


# ---------------------------------------------------------------------------
# 0. The replay buffer cap is a real, bounded, documented constant
# ---------------------------------------------------------------------------

def test_replay_cap_is_a_bounded_documented_constant():
    assert isinstance(_EVENT_REPLAY_CAP, int)
    assert _EVENT_REPLAY_CAP > 0
    bus = _ProjectEventBus()
    assert bus._buffer.maxlen == _EVENT_REPLAY_CAP


# ---------------------------------------------------------------------------
# 1. Two subscribers both receive the same event
# ---------------------------------------------------------------------------

def test_two_subscribers_both_receive_the_same_event_bus_level():
    """Bus-level pin of the exact defect: TWO independent subscribers,
    ONE publish, BOTH must observe it (not one stealing it from the
    other, as a shared queue.Queue.get() would)."""
    bus = _ProjectEventBus()
    sub1 = bus.subscribe(None)
    sub2 = bus.subscribe(None)

    event = {"stage": "KEYFRAME", "detail": "rendering", "percent": 40}
    event_id = bus.publish(event)

    kind1, id1, evt1 = sub1.inbox.get(timeout=1)
    kind2, id2, evt2 = sub2.inbox.get(timeout=1)

    assert (kind1, id1, evt1) == ("event", event_id, event)
    assert (kind2, id2, evt2) == ("event", event_id, event)


def test_two_subscribers_both_receive_the_same_event_http_level(client):
    """Same defect, through the real Flask /stream route and wire format:
    publish once, then attach two independent HTTP subscribers -- both
    must see the identical event (each via its own snapshot), proving
    fan-out end-to-end rather than only at the bus's Python API.

    (Publish-before-attach is deliberate: Werkzeug's test client blocks
    a GET on a streaming response until its first SSE frame is ready, so
    attaching before anything exists would stall on the 30s heartbeat
    instead of exercising the fan-out path. True concurrent-live fan-out
    -- both subscribers already blocked, then one publish reaches both --
    is pinned at the bus level above and, end-to-end through the real
    daemon, by test_generate_daemon_broadcasts_to_two_stream_subscribers_
    and_cleans_up below.)
    """
    pid = "proj_fanout_http"
    bus = _ensure_progress_queue(pid)
    event_id = bus.publish({"stage": "MOTION", "detail": "shot 3", "percent": 55})

    resp1 = client.get(f"/api/projects/{pid}/stream")
    resp2 = client.get(f"/api/projects/{pid}/stream")
    assert resp1.status_code == 200
    assert resp2.status_code == 200

    chunk1 = next(iter(resp1.response))
    chunk2 = next(iter(resp2.response))

    assert chunk1.startswith(f"id: {event_id}\n".encode())
    assert chunk2.startswith(f"id: {event_id}\n".encode())
    body1 = _sse_body(chunk1)
    body2 = _sse_body(chunk2)
    assert body1["stage"] == "MOTION" and body1["id"] == event_id
    assert body2["stage"] == "MOTION" and body2["id"] == event_id

    resp1.response.close()
    resp2.response.close()


def test_generate_daemon_broadcasts_to_two_stream_subscribers_and_cleans_up(client):
    """End-to-end: the REAL /generate route + run_pipeline daemon thread,
    with two real /stream HTTP subscribers attached while it runs. Both
    must see DONE then END live — and the daemon's finally-block cleanup
    (Bundle-C 3.2) must still pop _progress_queues[pid] afterward.

    Werkzeug's test client blocks a GET on a streaming response until its
    first SSE frame is ready, so subscribers attach only AFTER the fake
    pipeline's first progress event is already buffered (each client.get()
    then resolves instantly off that snapshot instead of stalling on the
    30s heartbeat); DONE and END are then observed live, proving real
    fan-out through the full HTTP + daemon stack.
    """
    pid = "proj_full_daemon"
    keyframe_published = threading.Event()
    proceed = threading.Event()

    class FakeCinemaPipeline:
        def __init__(self, _pid, core=None, progress_callback=None):
            self._cb = progress_callback

        def generate(self, resume=False):
            self._cb("KEYFRAME", "shot 1 rendering", 30)
            keyframe_published.set()
            proceed.wait(timeout=5.0)
            return "ok"

    with (
        patch("web_server.CinemaPipeline", FakeCinemaPipeline),
        patch("web_server.load_project", return_value={"id": pid, "scenes": [], "characters": []}),
        patch("web_server._get_or_build_core", return_value=MagicMock()),
    ):
        gen_resp = client.post(f"/api/projects/{pid}/generate", json={})
        assert gen_resp.status_code == 200
        assert keyframe_published.wait(timeout=2.0), "daemon never published KEYFRAME"

        stream1 = client.get(f"/api/projects/{pid}/stream")
        stream2 = client.get(f"/api/projects/{pid}/stream")
        assert stream1.status_code == 200
        assert stream2.status_code == 200
        it1 = iter(stream1.response)
        it2 = iter(stream2.response)

        proceed.set()

        keyframe1 = _sse_body(next(it1))
        keyframe2 = _sse_body(next(it2))
        assert keyframe1["stage"] == "KEYFRAME"
        assert keyframe2["stage"] == "KEYFRAME"

        done1 = _sse_body(next(it1))
        done2 = _sse_body(next(it2))
        assert done1["stage"] == "DONE"
        assert done2["stage"] == "DONE"

        end1 = _sse_body(next(it1))
        end2 = _sse_body(next(it2))
        assert end1["stage"] == "END"
        assert end2["stage"] == "END"

        stream1.response.close()
        stream2.response.close()

    deadline = time.time() + 3.0
    while pid in _progress_queues and time.time() < deadline:
        time.sleep(0.01)
    assert pid not in _progress_queues, "daemon finally-block must still release the bus"
    assert pid not in _running_pipelines


# ---------------------------------------------------------------------------
# 2. Reconnect with Last-Event-ID replays exactly the missed suffix
# ---------------------------------------------------------------------------

def test_reconnect_with_last_event_id_replays_exactly_missed_suffix_bus_level():
    bus = _ProjectEventBus()
    id1 = bus.publish({"stage": "A", "detail": "one", "percent": 10})
    id2 = bus.publish({"stage": "B", "detail": "two", "percent": 20})
    id3 = bus.publish({"stage": "C", "detail": "three", "percent": 30})

    sub = bus.subscribe(id1)

    assert sub.gap is None
    assert sub.backlog == [
        (id2, {"stage": "B", "detail": "two", "percent": 20}),
        (id3, {"stage": "C", "detail": "three", "percent": 30}),
    ]


def test_reconnect_at_latest_id_gets_no_backlog_and_no_gap():
    bus = _ProjectEventBus()
    id1 = bus.publish({"stage": "A", "detail": "one", "percent": 10})
    sub = bus.subscribe(id1)
    assert sub.backlog == []
    assert sub.gap is None


def test_reconnect_last_event_id_header_replays_missed_suffix_on_the_wire(client):
    pid = "proj_reconnect_http"
    bus = _ensure_progress_queue(pid)
    bus.publish({"stage": "A", "detail": "one", "percent": 10})
    id2 = bus.publish({"stage": "B", "detail": "two", "percent": 20})
    id3 = bus.publish({"stage": "C", "detail": "three", "percent": 30})

    resp = client.get(f"/api/projects/{pid}/stream", headers={"Last-Event-ID": "1"})
    it = iter(resp.response)
    chunk_b = next(it)
    chunk_c = next(it)
    resp.response.close()

    assert chunk_b.startswith(f"id: {id2}\n".encode())
    body_b = _sse_body(chunk_b)
    assert body_b == {"stage": "B", "detail": "two", "percent": 20, "id": id2, "replayed": True}

    assert chunk_c.startswith(f"id: {id3}\n".encode())
    body_c = _sse_body(chunk_c)
    assert body_c == {"stage": "C", "detail": "three", "percent": 30, "id": id3, "replayed": True}


def test_last_event_id_query_param_fallback_when_header_absent(client):
    pid = "proj_query_param_fallback"
    bus = _ensure_progress_queue(pid)
    id1 = bus.publish({"stage": "A", "detail": "one", "percent": 10})
    id2 = bus.publish({"stage": "B", "detail": "two", "percent": 20})

    resp = client.get(f"/api/projects/{pid}/stream?last_event_id={id1}")
    it = iter(resp.response)
    chunk = next(it)
    resp.response.close()

    body = _sse_body(chunk)
    assert body["stage"] == "B"
    assert body["id"] == id2


def test_last_event_id_header_wins_over_query_param(client):
    pid = "proj_header_wins"
    bus = _ensure_progress_queue(pid)
    id1 = bus.publish({"stage": "A", "detail": "one", "percent": 10})
    id2 = bus.publish({"stage": "B", "detail": "two", "percent": 20})

    # Header claims id2 (nothing left to replay); query param claims id1
    # (would replay B). The header must win, so the subscriber's backlog
    # is empty at attach time and the first thing it sees must be the
    # NEXT live event, not the B replay a wrongly-honored query param
    # would produce.
    #
    # Werkzeug's test client blocks a GET on a streaming response until
    # its first SSE frame is ready, so with an empty backlog client.get()
    # itself would stall until something is published. Publish the next
    # event from a background thread shortly after subscribing -- a plain
    # bus.publish() from another thread only touches the bus (thread-safe
    # by design), never the Flask test client, which is the thing that
    # is unsafe to call concurrently.
    published: dict = {}

    def publish_next_shortly():
        time.sleep(0.15)
        published["id"] = bus.publish({"stage": "C", "detail": "three", "percent": 30})

    threading.Thread(target=publish_next_shortly, daemon=True).start()

    resp = client.get(
        f"/api/projects/{pid}/stream?last_event_id={id1}",
        headers={"Last-Event-ID": str(id2)},
    )
    it = iter(resp.response)
    chunk = next(it)
    resp.response.close()

    body = _sse_body(chunk)
    assert body["stage"] == "C"
    assert body["id"] == published["id"]


def test_malformed_last_event_id_falls_back_to_snapshot_not_error(client):
    pid = "proj_malformed_header"
    bus = _ensure_progress_queue(pid)
    bus.publish({"stage": "A", "detail": "one", "percent": 10})

    resp = client.get(f"/api/projects/{pid}/stream", headers={"Last-Event-ID": "not-a-number"})
    assert resp.status_code == 200
    it = iter(resp.response)
    chunk = next(it)
    resp.response.close()

    body = _sse_body(chunk)
    assert body["stage"] == "A"
    assert body["replayed"] is True


# ---------------------------------------------------------------------------
# 3. A subscriber that disconnects is cleaned up
# ---------------------------------------------------------------------------

def test_unsubscribe_removes_the_subscriber_bus_level():
    bus = _ProjectEventBus()
    sub = bus.subscribe(None)
    assert len(bus._subscribers) == 1

    bus.unsubscribe(sub.sub_id)
    assert len(bus._subscribers) == 0

    # Publishing afterward must not error or resurrect the entry.
    bus.publish({"stage": "X", "detail": "y", "percent": 1})
    assert len(bus._subscribers) == 0


def test_unsubscribe_is_safe_to_call_twice():
    bus = _ProjectEventBus()
    sub = bus.subscribe(None)
    bus.unsubscribe(sub.sub_id)
    bus.unsubscribe(sub.sub_id)  # must not raise
    assert len(bus._subscribers) == 0


def test_http_disconnect_removes_the_subscriber(client):
    """Closing the client's response (as Werkzeug does when a real client
    disconnects) must run the route generator's finally-block and detach
    it from the bus -- no leaked subscriber/inbox."""
    pid = "proj_disconnect_http"
    bus = _ensure_progress_queue(pid)
    # Pre-publish so the fresh subscriber's snapshot backlog is non-empty
    # -- the very first `next()` resolves from the in-memory backlog list,
    # not from a blocking queue.get(), so this test is fast and
    # deterministic regardless of how the WSGI test transport buffers.
    bus.publish({"stage": "S", "detail": "already happened", "percent": 5})

    resp = client.get(f"/api/projects/{pid}/stream")
    assert resp.status_code == 200
    assert len(bus._subscribers) == 1

    it = iter(resp.response)
    next(it)  # consume the snapshot backlog frame
    resp.response.close()  # simulates the client disconnecting

    assert len(bus._subscribers) == 0


# ---------------------------------------------------------------------------
# 4. Buffer cap enforced + gap reported (never silently skipped)
# ---------------------------------------------------------------------------

def test_buffer_cap_enforced_and_gap_reported_bus_level():
    bus = _ProjectEventBus(cap=3)
    for i in range(1, 6):  # ids 1..5; cap=3 retains only 3,4,5
        bus.publish({"stage": "S", "detail": str(i), "percent": i})

    sub = bus.subscribe(1)  # claims to have seen id 1 -> id 2 is unrecoverable

    assert sub.gap == (2, 2)
    assert [eid for eid, _ in sub.backlog] == [3, 4, 5]


def test_buffer_cap_never_grows_past_cap():
    bus = _ProjectEventBus(cap=3)
    for i in range(1, 11):
        bus.publish({"stage": "S", "detail": str(i), "percent": i})
    assert len(bus._buffer) == 3
    assert [eid for eid, _ in bus._buffer] == [8, 9, 10]


def test_gap_reported_on_the_wire_when_reconnecting_past_the_cap(client):
    pid = "proj_gap_http"
    with _pipelines_lock:
        _progress_queues[pid] = _ProjectEventBus(cap=2)
    bus = _progress_queues[pid]
    for i in range(1, 5):  # ids 1..4; cap=2 retains only 3,4
        bus.publish({"stage": "S", "detail": str(i), "percent": i})

    resp = client.get(f"/api/projects/{pid}/stream", headers={"Last-Event-ID": "1"})
    it = iter(resp.response)
    gap_chunk = next(it)
    chunk3 = next(it)
    chunk4 = next(it)
    resp.response.close()

    assert not gap_chunk.startswith(b"id:")  # control frame carries no id
    gap_body = _sse_body(gap_chunk)
    assert gap_body["stage"] == "GAP"
    assert gap_body["gap_from"] == 2
    assert gap_body["gap_to"] == 2

    body3 = _sse_body(chunk3)
    body4 = _sse_body(chunk4)
    assert body3 == {"stage": "S", "detail": "3", "percent": 3, "id": 3, "replayed": True}
    assert body4 == {"stage": "S", "detail": "4", "percent": 4, "id": 4, "replayed": True}


# ---------------------------------------------------------------------------
# Snapshot contract for a late/fresh joiner (no known position)
# ---------------------------------------------------------------------------

def test_fresh_subscriber_gets_snapshot_of_latest_event_only():
    bus = _ProjectEventBus()
    bus.publish({"stage": "A", "detail": "one", "percent": 10})
    bus.publish({"stage": "B", "detail": "two", "percent": 20})
    latest_id = bus.publish({"stage": "C", "detail": "three", "percent": 30})

    sub = bus.subscribe(None)

    assert sub.gap is None
    assert sub.backlog == [(latest_id, {"stage": "C", "detail": "three", "percent": 30})]


def test_fresh_subscriber_before_any_event_gets_empty_backlog():
    bus = _ProjectEventBus()
    sub = bus.subscribe(None)
    assert sub.backlog == []
    assert sub.gap is None
    assert sub.closed is False


def test_subscribe_after_close_reports_closed_and_route_ends_immediately(client):
    """A subscriber attaching AFTER close() already broadcast its terminal
    sentinel would otherwise block forever on an inbox nothing will ever
    fill -- subscribe() must report closed=True so the route can end the
    stream right away instead of hanging."""
    pid = "proj_closed_http"
    with _pipelines_lock:
        _progress_queues[pid] = _ProjectEventBus()
    bus = _progress_queues[pid]
    bus.publish({"stage": "DONE", "detail": "ok", "percent": 100})
    bus.close()

    sub = bus.subscribe(None)
    assert sub.closed is True
    assert sub.backlog == [(1, {"stage": "DONE", "detail": "ok", "percent": 100})]

    resp = client.get(f"/api/projects/{pid}/stream")
    it = iter(resp.response)
    chunk1 = next(it)
    chunk2 = next(it)
    resp.response.close()

    body1 = _sse_body(chunk1)
    body2 = _sse_body(chunk2)
    assert body1["stage"] == "DONE" and body1["replayed"] is True
    assert body2["stage"] == "END"


def test_ensure_progress_queue_replaces_a_closed_bus():
    pid = "proj_stale_closed"
    old_bus = _ensure_progress_queue(pid)
    old_bus.close()

    new_bus = _ensure_progress_queue(pid)
    assert new_bus is not old_bus
    assert new_bus.closed is False


def test_stream_404_when_no_generation_in_progress(client):
    resp = client.get("/api/projects/nonexistent_pid_xyz/stream")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# _make_progress_cb wiring (production callback -> bus.put -> fan-out)
# ---------------------------------------------------------------------------

def test_make_progress_cb_publishes_into_the_explicit_bus():
    bus = _ProjectEventBus()
    cb = _make_progress_cb("unused_pid_since_bus_is_explicit", bus)
    sub = bus.subscribe(None)

    cb("STAGE", "hello", 50)

    kind, event_id, event = sub.inbox.get(timeout=1)
    assert kind == "event"
    assert event["stage"] == "STAGE"
    assert event["detail"] == "hello"
    assert event["percent"] == 50


def test_make_progress_cb_is_noop_when_no_bus_registered():
    cb = _make_progress_cb("proj_no_bus_at_all")
    cb("STAGE", "detail", 10)  # must not raise


# ---------------------------------------------------------------------------
# 5. Concurrency: publish while subscribing/unsubscribing does not deadlock
# ---------------------------------------------------------------------------

def test_concurrent_publish_subscribe_unsubscribe_does_not_deadlock():
    bus = _ProjectEventBus()
    stop = threading.Event()
    errors: list[Exception] = []
    published_ids: list[int] = []
    ids_lock = threading.Lock()

    def publisher():
        i = 0
        while not stop.is_set():
            try:
                # publish() + record must be one atomic step from this
                # test's point of view: bus.publish() already serializes
                # id assignment correctly under its OWN lock, but without
                # ids_lock spanning both calls here, two publisher threads
                # could be descheduled between "get my id back" and
                # "append it", letting a later-assigned id get appended
                # first -- a race in this test's bookkeeping, not in the
                # bus. Holding ids_lock across both makes the recorded
                # order provably match assignment order.
                with ids_lock:
                    event_id = bus.publish({"stage": "TICK", "detail": str(i), "percent": i % 100})
                    published_ids.append(event_id)
                i += 1
            except Exception as e:  # pragma: no cover - failure path
                errors.append(e)

    def subscriber_churn():
        while not stop.is_set():
            try:
                sub = bus.subscribe(None)
                # Drain whatever arrived without blocking, then detach.
                try:
                    while True:
                        sub.inbox.get_nowait()
                except Exception:
                    pass
                bus.unsubscribe(sub.sub_id)
            except Exception as e:  # pragma: no cover - failure path
                errors.append(e)

    threads = (
        [threading.Thread(target=publisher) for _ in range(3)]
        + [threading.Thread(target=subscriber_churn) for _ in range(3)]
    )
    for t in threads:
        t.start()

    time.sleep(0.5)
    stop.set()
    for t in threads:
        t.join(timeout=5)

    assert not errors, f"unexpected errors from concurrent access: {errors}"
    assert all(not t.is_alive() for t in threads), "a thread failed to join -- possible deadlock"
    assert len(published_ids) > 0
    assert published_ids == sorted(published_ids), "ids must stay monotonic under concurrent publish"
    assert len(set(published_ids)) == len(published_ids), "ids must stay unique under concurrent publish"
    assert len(bus._subscribers) == 0, "every churned subscriber must have been unsubscribed"


def test_concurrent_subscribe_during_close_never_hangs():
    """Races close() against subscribe() many times -- whichever one wins
    the lock first, the subscriber must end up with a consistent view
    (either woken by close()'s broadcast, or told closed=True up front)
    rather than hanging forever on an inbox nothing will ever fill."""
    for _ in range(200):
        bus = _ProjectEventBus()
        result: dict = {}

        def do_subscribe():
            result["sub"] = bus.subscribe(None)

        t_close = threading.Thread(target=bus.close)
        t_sub = threading.Thread(target=do_subscribe)
        t_close.start()
        t_sub.start()
        t_close.join(timeout=2)
        t_sub.join(timeout=2)

        assert not t_close.is_alive()
        assert not t_sub.is_alive()
        sub = result["sub"]
        if not sub.closed:
            # subscribe() beat close(): it must have been registered in
            # time to receive close()'s broadcast.
            kind, _id, _evt = sub.inbox.get(timeout=2)
            assert kind == "end"


# ---------------------------------------------------------------------------
# 6. FIX-SSE: bounded subscriber inbox -- a slow/never-draining subscriber
#    degrades on its own (capped + explicit GAP), and never blocks the
#    publisher or any other subscriber.
#
# Defect (audit, pre-fix): each subscriber's live-delivery inbox
# (queue.Queue(), constructed in _ProjectEventBus.subscribe) had no
# maxsize -- a client that opens /stream and never reads its HTTP
# response accumulates one entry per publish() in server memory for the
# entire run's lifetime; N such clients multiply it. This is the same
# class of bug the replay buffer's `deque(maxlen=...)` already solved for
# the SHARED history -- it just hadn't been applied to each subscriber's
# own PRIVATE queue yet.
#
# RED proof (run separately, not part of the pytest suite): a scratchpad
# copy of the pre-fix web_server.py (queue.Queue() with no maxsize) was
# exercised with test_slow_subscriber_inbox_is_capped_not_unbounded's
# exact scenario -- publish _SUBSCRIBER_INBOX_CAP + 100 events to a
# subscriber that never reads sub.inbox -- and sub.inbox.qsize() came
# back as _SUBSCRIBER_INBOX_CAP + 100 (unbounded growth), failing the
# `<= _SUBSCRIBER_INBOX_CAP` assertion below. Against the fixed code in
# this tree, the same scenario caps at _SUBSCRIBER_INBOX_CAP. That test
# uses ONLY the default constructor (no inbox_cap= override) so it is a
# like-for-like comparison against the pre-fix public API.
# ---------------------------------------------------------------------------

def test_slow_subscriber_inbox_is_capped_not_unbounded():
    """The core defect, pinned directly: publish comfortably past the
    default cap to a subscriber that never drains at all, and require
    the inbox to stay bounded instead of growing 1:1 with publish count
    (which is exactly what an unbounded queue.Queue() would do)."""
    bus = _ProjectEventBus()
    sub = bus.subscribe(None)

    n_published = _SUBSCRIBER_INBOX_CAP + 100
    for i in range(n_published):
        bus.publish({"stage": "TICK", "detail": str(i), "percent": i % 100})

    assert sub.inbox.qsize() <= _SUBSCRIBER_INBOX_CAP
    assert bus._subscribers  # the subscriber itself is still attached


def test_slow_subscriber_overflow_keeps_the_newest_entries_and_drops_the_rest():
    """Overflow must drop the OLDEST undelivered entries, never the
    newest -- a subscriber that eventually starts draining should see
    unbroken, ordered, recent history rather than a stale front it
    never asked to keep."""
    bus = _ProjectEventBus(inbox_cap=3)
    sub = bus.subscribe(None)

    ids = [bus.publish({"stage": "TICK", "detail": str(i), "percent": i}) for i in range(5)]

    remaining_ids = []
    while True:
        try:
            _kind, event_id, _evt = sub.inbox.get_nowait()
        except queue.Empty:
            break
        remaining_ids.append(event_id)

    assert remaining_ids == ids[2:], "must keep exactly the newest inbox_cap entries, in order"


def test_slow_subscriber_overflow_records_one_coalesced_gap():
    """Every dropped id is reported, never silently lost, and a run of
    drops between two live reads coalesces into ONE (gap_from, gap_to)
    range rather than one notice per dropped event."""
    bus = _ProjectEventBus(inbox_cap=3)
    sub = bus.subscribe(None)

    ids = [bus.publish({"stage": "TICK", "detail": str(i), "percent": i}) for i in range(5)]

    assert sub.inbox.qsize() == 3
    gap = bus.pop_gap(sub.sub_id)
    assert gap == (ids[0], ids[1]), "must cover exactly the two evicted ids, coalesced"
    # pop_gap is take-and-clear: nothing left to report a second time.
    assert bus.pop_gap(sub.sub_id) is None


def test_slow_subscriber_overflow_gap_reported_on_the_wire_http_level(client):
    """End-to-end: a real /stream HTTP subscriber that never reads past
    its first frame, while events are published well past its bounded
    inbox -- the GAP control frame this fix introduces must actually
    reach the wire (not just _ProjectEventBus.pop_gap's Python API),
    immediately before the next live event, and name exactly the
    dropped id range."""
    pid = "proj_slow_overflow_http"
    bus = _ProjectEventBus(inbox_cap=2)
    with _pipelines_lock:
        _progress_queues[pid] = bus
    # Non-empty snapshot backlog so the initial client.get() resolves
    # from the in-memory backlog list instead of blocking on a live
    # queue.get() -- same idiom as test_http_disconnect_removes_the_subscriber.
    bus.publish({"stage": "SEED", "detail": "before subscribe", "percent": 0})

    resp = client.get(f"/api/projects/{pid}/stream")
    it = iter(resp.response)
    seed_chunk = next(it)
    assert _sse_body(seed_chunk)["stage"] == "SEED"

    # Five more live publishes against a cap of 2, with this subscriber
    # never draining its inbox in between -- three of them must be
    # dropped (the two oldest survivors plus every publish beyond cap).
    ids = [bus.publish({"stage": "TICK", "detail": str(i), "percent": i}) for i in range(5)]

    gap_chunk = next(it)
    assert not gap_chunk.startswith(b"id:"), "GAP is a control frame -- no id: framing line"
    gap_body = _sse_body(gap_chunk)
    assert gap_body["stage"] == "GAP"
    assert gap_body["gap_from"] == ids[0]
    assert gap_body["gap_to"] == ids[2]

    live_chunk = next(it)
    live_body = _sse_body(live_chunk)
    assert live_body == {"stage": "TICK", "detail": "3", "percent": 3, "id": ids[3]}
    assert "replayed" not in live_body, "this is a live delivery, not a replay"

    resp.response.close()


def test_healthy_subscriber_unaffected_by_a_slow_subscriber_on_the_same_bus():
    """The defining isolation guarantee: one slow (never-draining)
    subscriber's overflow must never cost a DIFFERENT, healthy
    subscriber on the SAME bus a single event."""
    bus = _ProjectEventBus(inbox_cap=3)
    slow = bus.subscribe(None)
    healthy = bus.subscribe(None)

    for i in range(10):
        event_id = bus.publish({"stage": "TICK", "detail": str(i), "percent": i})
        # The healthy subscriber drains immediately after every publish,
        # so its own inbox never approaches the cap -- it must still see
        # every event, in order, with its real id.
        kind, got_id, evt = healthy.inbox.get(timeout=1)
        assert (kind, got_id, evt["detail"]) == ("event", event_id, str(i))

    assert slow.inbox.qsize() == 3, "the slow subscriber's inbox is capped"
    assert bus.pop_gap(slow.sub_id) is not None, "the slow subscriber's drops were recorded"
    assert bus.pop_gap(healthy.sub_id) is None, "the healthy subscriber lost nothing"


def test_publish_does_not_block_on_a_never_draining_subscriber():
    """The publisher-side guarantee: publish() must never stall waiting
    for a slow subscriber's inbox to free up. Proven directly rather
    than inferred from _deliver's use of put_nowait/get_nowait: publish
    thousands of events, well past the bounded cap, against a
    subscriber that never reads a single item, from a background
    thread, and require that thread to finish promptly. A blocking
    put() on a full bounded queue (maxsize= alone, without the
    put_nowait/evict fallback this fix adds) would hang this thread
    forever, since nothing ever drains -- this test would then fail via
    the join timeout instead of completing quickly."""
    bus = _ProjectEventBus(inbox_cap=4)
    bus.subscribe(None)  # attached, but never read from again

    done = threading.Event()

    def publish_a_lot():
        for i in range(2000):
            bus.publish({"stage": "TICK", "detail": str(i), "percent": i % 100})
        done.set()

    t = threading.Thread(target=publish_a_lot, daemon=True)
    t.start()
    t.join(timeout=5.0)

    assert not t.is_alive(), "publish() blocked (thread failed to finish) on a slow subscriber"
    assert done.is_set(), "publish() blocked on a slow subscriber's full inbox"


def test_close_does_not_block_on_a_never_draining_subscriber():
    """close() shares _deliver with publish() -- the /generate daemon's
    finally block calls close() from its own thread and must never hang
    it waiting for room in a subscriber's already-full, never-drained
    inbox."""
    bus = _ProjectEventBus(inbox_cap=4)
    sub = bus.subscribe(None)
    for i in range(20):  # comfortably past cap, never drained
        bus.publish({"stage": "TICK", "detail": str(i), "percent": i})

    t = threading.Thread(target=bus.close, daemon=True)
    t.start()
    t.join(timeout=5.0)

    assert not t.is_alive(), "close() blocked on a slow subscriber's full inbox"
    assert bus.closed is True
    # The terminal sentinel itself is subject to the same cap/eviction --
    # it must still have been delivered (queue holds inbox_cap items,
    # the last of which is the "end" sentinel) rather than silently lost.
    kind = None
    try:
        while True:
            kind, _id, _evt = sub.inbox.get_nowait()
    except queue.Empty:
        pass
    assert kind == "end", "the terminal sentinel must survive overflow eviction too"
