#!/usr/bin/env python3
"""consume_bus.py — read signed-bus events addressed to a seat past its cursor and advance the
seat's LOCAL cursor. The bus analog of coordination/bin/consume-events. Raw read: signature
verification is the gate's job, not the consume path (SP2 spec §3.1)."""
import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:                      # ADR-055 self-bootstrap (no PYTHONPATH)
    sys.path.insert(0, str(_REPO_ROOT))

from threeway.refstore import (                          # noqa: E402
    CursorContentionExceeded, CursorCorruptionError, RefEventStore,
)

# The 6 cursor/interactive seats (== cursor_backfill.SEATS), NOT the full keyed-seat universe
# (which also has overseer/ci/merge-gate); only these 6 have per-seat read cursors.
SEATS = ("director", "director2", "operator", "operator2", "coordinator", "coordinator2")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read bus events addressed to a seat; advance its cursor.")
    ap.add_argument("seat", choices=SEATS)
    ap.add_argument("--kinds", default=None, help="comma-separated kind allowlist")
    ap.add_argument("--no-advance", action="store_true")
    ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--bus-id", default="prod")
    a = ap.parse_args(argv)
    remote = (a.remote or None)                          # "" -> None (local); RefEventStore checks `is not None`
    seat = a.seat
    store = RefEventStore(Path(a.repo_dir), remote=remote)
    try:
        cursor = store.cursor_seq(seat)
        events = list(store.iter_events())              # collect ONCE (iter_events re-fetches per call)
    except CursorCorruptionError as e:
        print(f"cursor blob corrupt for {seat}: {e}", file=sys.stderr)
        return 1
    tip = max((ev.seq for ev in events), default=0)     # full-snapshot watermark (empty-safe)
    kinds = set(a.kinds.split(",")) if a.kinds else None
    shown = [
        ev for ev in events
        if ev.seq > cursor and ev.bus_id == a.bus_id and ev.recipient in (seat, "all")
        and (kinds is None or ev.kind in kinds)
    ]
    for ev in shown:
        ref = ev.candidate_id or ev.brief_id or "-"
        ssha = (ev.subject_sha or "")[:12] or "-"
        print(f"{ev.seq}\t{ev.kind}\t{ev.sender}\t{ref}\t{ssha}")
    if not a.no_advance:
        try:
            store.advance_cursor(seat, tip)             # local CAS; monotonic no-op for seq<=cur
        except (CursorContentionExceeded, CursorCorruptionError) as e:   # advance re-reads the cursor blob
            print(f"cursor advance failed for {seat}: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
