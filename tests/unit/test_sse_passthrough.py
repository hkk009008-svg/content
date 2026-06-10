"""SSE whitelist lift (NF-3 / P1-3, STRATEGIC_REVIEW-2026-06-10).

``make_progress_callback`` used to bind 17 named fields and silently discard
``**kwargs`` — so producer extras (``engine`` on MOTION, ``spent``/``budget``
on BUDGET_EXCEEDED, ``performance_engine`` on the performance SKIP path)
never reached the UI. These tests pin the pass-through: extras flow,
lean-ness filtering holds (None/"" dropped; 0 and False are real data), and
non-JSON-serializable values are dropped rather than killing the SSE
generator (web_server.py's /stream json.dumps's every event).
"""

import json
import queue

from web_services import make_progress_callback


def _emit(**kwargs):
    """Emit one event through the real callback and return it."""
    q = queue.Queue()
    cb = make_progress_callback(q)
    cb(
        kwargs.pop("stage", "STAGE"),
        kwargs.pop("detail", "detail"),
        kwargs.pop("percent", 50),
        **kwargs,
    )
    return q.get_nowait()


class TestKwargPassthrough:
    def test_engine_passes_through(self):
        ev = _emit(stage="MOTION", engine="KLING_NATIVE")
        assert ev["engine"] == "KLING_NATIVE"

    def test_spent_and_budget_pass_through(self):
        ev = _emit(stage="BUDGET_EXCEEDED", spent=12.5, budget=10.0)
        assert ev["spent"] == 12.5
        assert ev["budget"] == 10.0

    def test_zero_spent_is_kept(self):
        """0.0 is real data, not a sentinel — the pre-spend gate fires at $0
        spent when the first call's estimate already exceeds the cap."""
        ev = _emit(stage="BUDGET_EXCEEDED", spent=0.0, budget=0.05)
        assert ev["spent"] == 0.0

    def test_false_is_kept(self):
        """Booleans are real data (e.g. identity_all_matched=False)."""
        ev = _emit(identity_all_matched=False)
        assert ev["identity_all_matched"] is False

    def test_none_and_empty_string_dropped(self):
        ev = _emit(engine="", performance_engine=None)
        assert "engine" not in ev
        assert "performance_engine" not in ev

    def test_non_serializable_dropped_not_fatal(self):
        """One bad value must not kill the stream — it is dropped, the rest
        of the event (including other extras) still emits and serializes."""
        ev = _emit(engine="VEO_NATIVE", bad=object())
        assert "bad" not in ev
        assert ev["engine"] == "VEO_NATIVE"
        json.dumps(ev)  # the emitted event is stream-safe

    def test_named_fields_unchanged(self):
        """The existing 17-field contract is untouched by the lift."""
        q = queue.Queue()
        cb = make_progress_callback(q)
        cb("S", "d", 10, shot_id="sh1", identity_score=0.9, take_kind="motion")
        ev = q.get_nowait()
        assert ev["shot_id"] == "sh1"
        assert ev["identity_score"] == 0.9
        assert ev["take_kind"] == "motion"
        assert ev["stage"] == "S"
