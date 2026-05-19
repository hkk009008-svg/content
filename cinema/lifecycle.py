"""LifecycleService — pause/resume/cancel + progress reporting for phases.

Phase 6 epilogue → cinema_pipeline migration Slice A. Introduces a
protocol that the legacy ``cinema_pipeline.CinemaPipeline`` will adopt
in Slice E (replacing its ad-hoc ``self.cancelled`` / ``self.paused`` /
``self._resume_event`` / ``self.progress`` quartet with a single
injectable service).

Phases poll the service voluntarily at pause-safe points; the driver
doesn't enforce when. The non-interactive CLI (``main.py``) gets
``NullLifecycle`` which never blocks and silently swallows progress.
The interactive web server gets ``ThreadedLifecycle`` which is backed
by ``threading.Event`` for cancel and pause, a per-gate ``Event`` for
operator review gates, and an optional progress-callback closure
(typically ``web_services.make_progress_callback``).

See ``docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md`` §3.1 for the design
rationale (Option C: inject the service via PipelineContext).
"""

from __future__ import annotations

import threading
from typing import Callable, Dict, Optional, Protocol


class LifecycleService(Protocol):
    """Pause/resume/cancel control + progress reporting for pipeline phases."""

    def is_cancelled(self) -> bool:
        """True if the run has been cancelled. Phases poll at pause-points."""
        ...

    def check_pause(self) -> None:
        """Block if the run is paused; return immediately if running or cancelled."""
        ...

    def wait_for_gate(
        self,
        name: str,
        predicate: Callable[[], bool],
        poll_interval: float = 0.5,
    ) -> bool:
        """Block until ``predicate()`` returns True OR the run is cancelled.

        Returns True if the gate opened (predicate satisfied), False if
        the run was cancelled while waiting. ``poll_interval`` controls
        how often the predicate is re-evaluated when no explicit signal
        is received.
        """
        ...

    def report_progress(
        self,
        stage: str,
        detail: str,
        percent: float = 0,
        **kwargs,
    ) -> None:
        """Emit a progress event (for SSE streaming or CLI banner)."""
        ...


class NullLifecycle:
    """No-op LifecycleService.

    Cancel always returns False, pause never blocks, gates open
    immediately, progress is silently dropped. Used by the
    non-interactive CLI and as the default for ``PipelineContext.lifecycle``
    so phase code can call ``ctx.lifecycle.X()`` unconditionally.
    """

    def is_cancelled(self) -> bool:
        return False

    def check_pause(self) -> None:
        return None

    def wait_for_gate(
        self,
        name: str,
        predicate: Callable[[], bool],
        poll_interval: float = 0.5,
    ) -> bool:
        # Non-interactive path: if the predicate is already true, fine;
        # otherwise return True to let the phase proceed. The caller is
        # responsible for setting up state so gates auto-satisfy in CLI.
        return True

    def report_progress(
        self,
        stage: str,
        detail: str,
        percent: float = 0,
        **kwargs,
    ) -> None:
        return None


class ThreadedLifecycle:
    """Event-backed LifecycleService for interactive / web-server runs.

    Implementation details:

    - Cancel is a plain bool, polled by phases via ``is_cancelled()`` and
      flipped by external code via ``cancel()``. Setting it also signals
      every gate event so any blocked ``wait_for_gate`` unblocks promptly.

    - Pause is a ``threading.Event`` initialised set (= unpaused).
      ``pause()`` clears it; ``check_pause()`` blocks on ``.wait()``;
      ``resume()`` sets it again.

    - Gates are per-name ``threading.Event`` objects, lazily created.
      ``signal_gate(name)`` unblocks any waiter on that gate. The
      predicate is still polled (every ``poll_interval`` seconds) as a
      fallback in case the signal is missed or the gate state is
      external (e.g. a project-state flag on disk).

    - Progress is delegated to an injectable callback. Typically that
      callback is ``web_services.make_progress_callback(queue)`` for
      the SSE pipeline.
    """

    def __init__(self, progress_callback: Optional[Callable] = None):
        self._cancelled = False
        self._paused = False
        self._resume_event = threading.Event()
        self._resume_event.set()  # start unpaused
        self._gate_events: Dict[str, threading.Event] = {}
        self._gate_lock = threading.Lock()
        self._progress_cb = progress_callback

    # -- Imperative control (called by external code / web endpoints) --

    def cancel(self) -> None:
        self._cancelled = True
        self._resume_event.set()  # unblock any waiter so cancel propagates
        with self._gate_lock:
            for ev in self._gate_events.values():
                ev.set()

    def pause(self) -> None:
        if not self._paused:
            self._paused = True
            self._resume_event.clear()

    def resume(self) -> None:
        if self._paused:
            self._paused = False
            self._resume_event.set()

    def is_paused(self) -> bool:
        return self._paused

    def signal_gate(self, name: str) -> None:
        """Wake any waiter on ``name`` so they re-evaluate their predicate."""
        with self._gate_lock:
            ev = self._gate_events.get(name)
        if ev is not None:
            ev.set()

    # -- Protocol methods (called by phase code) --

    def is_cancelled(self) -> bool:
        return self._cancelled

    def check_pause(self) -> None:
        # ``Event.wait()`` with no timeout returns immediately when set,
        # blocks otherwise. Returns None.
        self._resume_event.wait()

    def wait_for_gate(
        self,
        name: str,
        predicate: Callable[[], bool],
        poll_interval: float = 0.5,
    ) -> bool:
        with self._gate_lock:
            ev = self._gate_events.setdefault(name, threading.Event())
        while not self._cancelled:
            if predicate():
                return True
            # Either an explicit signal_gate(name) wakes us early, or the
            # poll_interval timeout fires. Either way we re-check the
            # predicate at the top of the loop.
            ev.wait(timeout=poll_interval)
            ev.clear()
        return False

    def report_progress(
        self,
        stage: str,
        detail: str,
        percent: float = 0,
        **kwargs,
    ) -> None:
        if self._progress_cb is not None:
            self._progress_cb(stage, detail, percent, **kwargs)
