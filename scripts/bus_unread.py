#!/usr/bin/env python3
"""bus_unread.py — the REAL ref-bus unread for a migrated (scalar-cursor) seat.

After the Slice-2.5 cutover, a seat's ``coordination/mailbox/seen/<seat>.txt`` holds a
scalar ``seq`` SENTINEL (its live cursor is the git ref ``refs/threeway/cursors/<seat>``).
The legacy dashboards compute unread from ``sent/*.md`` ISO filenames and correctly return
0 for a scalar cursor — the legacy filename path cannot see the signed bus. But "0" silently
UNDER-reports: real unread for a migrated seat lives on the ref-bus. This helper is the
de-degrade — it reads the signed bus LOCALLY (no network) and returns the real unread,
mirroring ``consume_bus.py``'s filter exactly (``seq > cursor`` ∧ ``bus_id`` ∧ addressed).

Design contract:
* LOCAL ONLY — ``RefEventStore(remote=None)`` never ``_sync()``s (every ``_sync`` call site
  guards on ``self._remote is not None``), so a dashboard with a "NEVER hangs" constraint
  (status.py) can call this without a network round-trip.
* The live cursor is ``store.cursor_seq(seat)`` (the ref-bus head the seat advances via
  consume_bus), NOT the frozen ``seen/*.txt`` scalar (a migration-time sentinel that goes
  stale as the seat consumes). Reading the seen scalar would re-over-count everything since.
* Returns ``None`` on ANY failure (corrupt cursor blob, not-a-repo, …) so callers render a
  visible "(unavailable)" sentinel — NEVER a silent 0 (silent-gate-degradation bug class).
  An empty bus is a real ``0``/``[]``, distinct from ``None``.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:                      # ADR-055 self-bootstrap (no PYTHONPATH)
    sys.path.insert(0, str(_REPO_ROOT))

from threeway.refstore import RefEventStore               # noqa: E402


def is_migrated_cursor(cursor) -> bool:
    """True iff *cursor* is a scalar ``seq`` (post-cutover sentinel), not an ISO ts or
    an "(unavailable)" string. Tolerates surrounding whitespace; "" / blank are False."""
    return bool(cursor) and str(cursor).strip().isdigit()


def bus_unread_events(repo_root, seat: str, *, bus_id: str = "prod") -> list | None:
    """Signed-bus events addressed to *seat* past its LIVE ref-bus cursor, LOCAL refs only.

    Mirrors consume_bus.py's filter (seq > cursor ∧ bus_id ∧ recipient ∈ {seat, "all"}).
    Returns ``None`` if the bus is unavailable/corrupt (caller degrades to a sentinel);
    an empty list means a reachable-but-empty bus.
    """
    try:
        store = RefEventStore(Path(repo_root), remote=None)   # remote=None => no _sync => LOCAL ONLY
        cursor = store.cursor_seq(seat)
        # O(unread): read only the blobs past the cursor, NOT the whole bus. all_events()
        # over the live bus is ~14s (subprocess git per blob); a dashboard calls this once
        # per seat, so the seq>cursor floor (iter_events_since) is load-bearing for the
        # "status.py NEVER hangs" contract. The seq gate lives in iter_events_since (pinned
        # non-vacuous in test_threeway_refstore.py); here we apply only the bus_id+addressee
        # domain filters.
        events = list(store.iter_events_since(cursor))
    except Exception:
        # Dashboard never-crash + silent-degradation guard: a corrupt cursor blob or a
        # non-bus repo surfaces as None, never a traceback and never a misleading 0.
        return None
    return [ev for ev in events if ev.bus_id == bus_id and ev.recipient in (seat, "all")]


def bus_unread_count(repo_root, seat: str, *, bus_id: str = "prod") -> int | None:
    """Count of :func:`bus_unread_events`; ``None`` propagates the unavailable signal."""
    evs = bus_unread_events(repo_root, seat, bus_id=bus_id)
    return None if evs is None else len(evs)


def format_unread(ev) -> str:
    """Compact one-line descriptor for an unread bus event — there is no legacy filename
    to surface for a migrated seat, so dashboards print this instead."""
    ref = ev.candidate_id or ev.brief_id or "-"
    base = f"seq{ev.seq}:{ev.kind}:{ev.sender}->{ev.recipient}"
    return base if ref == "-" else f"{base}:{ref}"
