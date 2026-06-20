"""Divergence-check: projected carrier-event SET vs the live legacy mailbox (spec §5b).

READ-ONLY. Compares on the RAW event set — NEVER reduce()/EffectiveState (legacy kinds
are 100% disjoint from the threeway governance vocabulary; reduce() would silently
drop them). Returns a Report(.ok, .drifts). No bus writes, no RefEventStore.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from threeway.legacy_projector import _EVENT_NAME_RE

# self-consistency body parsers (best-effort; both corpus formats)
_HDR_FROM_RE = re.compile(r"\*\*From:\*\*\s+(\w+)")
_HDR_WHEN_RE = re.compile(r"\*\*When:\*\*\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")
_YAML_FROM_RE = re.compile(r"^from:\s*(\w+)\s*$", re.M)


@dataclass
class Report:
    ok: bool
    drifts: list[str] = field(default_factory=list)


def _seen_value(seen_dir: Path, seat: str) -> str | None:
    f = seen_dir / f"{seat}.txt"
    if not f.exists():
        return None
    v = f.read_text().strip()
    return v or None


def _colon_ts(dash_ts: str) -> str:
    # filename dash-form 2026-06-01T10-00-00Z -> ISO colon-form for cursor comparison
    return dash_ts[:11] + dash_ts[11:].replace("-", ":")


def diverge(projected_events, sent_dir, seen_dir) -> Report:
    sent = Path(sent_dir)
    seen = Path(seen_dir)
    drifts: list[str] = []

    on_disk = {p.name for p in sent.iterdir()
               if p.name.endswith(".md") and _EVENT_NAME_RE.match(p.name)}
    proj_names = [e.payload["source_filename"] for e in projected_events]
    proj_set = set(proj_names)

    # (1) SET bijection with a NON-EMPTY FLOOR (spec §8 clause 5).
    if not on_disk:
        drifts.append("bijection: live sent set is EMPTY (non-empty floor violated)")
    if len(projected_events) != len(on_disk):
        drifts.append(
            f"bijection: projected count {len(projected_events)} != "
            f"sent file count {len(on_disk)}")
    if proj_set != on_disk:
        only_proj = proj_set - on_disk
        only_disk = on_disk - proj_set
        drifts.append(f"bijection: identity-set mismatch "
                      f"(only_projected={sorted(only_proj)}, only_disk={sorted(only_disk)})")

    # the §6 total order assigns 1-based seq over the sorted projection (the projector
    # emits seq=0; we order here so the cursor equivalence is exact without mutating it).
    ordered = sorted(projected_events,
                     key=lambda e: (_EVENT_NAME_RE.match(e.payload["source_filename"]).group("ts"),
                                    e.payload["source_filename"]))
    seq_of = {e.payload["source_filename"]: i for i, e in enumerate(ordered, start=1)}

    # (2)+(3) per-event field + filename<->envelope self-consistency.
    for e in projected_events:
        name = e.payload["source_filename"]
        m = _EVENT_NAME_RE.match(name)
        if m is None:
            drifts.append(f"field: projected event {name} has an ungrammatical source_filename")
            continue
        if e.sender != m.group("frm"):
            drifts.append(f"field[{name}]: from {e.sender} != filename {m.group('frm')}")
        if e.recipient != m.group("to"):
            drifts.append(f"field[{name}]: to {e.recipient} != filename {m.group('to')}")
        if e.payload.get("legacy_kind") != m.group("kind"):
            drifts.append(f"field[{name}]: kind {e.payload.get('legacy_kind')} != "
                          f"filename {m.group('kind')}")
        p = sent / name
        if p.exists():
            disk_body = p.read_text(encoding="utf-8", errors="replace")
            if e.payload.get("body") != disk_body:
                drifts.append(f"field[{name}]: body diverges from on-disk file")
            # filename <-> envelope self-consistency (best-effort: only when present)
            fm = _HDR_FROM_RE.search(disk_body) or _YAML_FROM_RE.search(disk_body)
            if fm and fm.group(1) != m.group("frm"):
                drifts.append(f"self-consistency[{name}]: header From {fm.group(1)} "
                              f"!= filename {m.group('frm')}")
            wm = _HDR_WHEN_RE.search(disk_body)
            if wm and e.payload.get("when") != wm.group(1):
                drifts.append(f"field[{name}]: when {e.payload.get('when')} != header {wm.group(1)}")

    # (4) per-seat cursor + strictly-greater unread (spec §8 clause 4).
    # NON-VACUITY KEYSTONE: the LEGACY side reads the on-disk sent/*.md `to` tokens
    # directly (the legacy checker's own view), while the PROJECTION side reads the
    # projected events' `e.recipient` seq-view. These are two INDEPENDENT derivations:
    # on a faithful projection they agree, but a projection that mis-routes one event
    # (e.recipient != the disk filename's `to`) makes them drift WITHOUT touching the
    # bijection (the source_filename set is unchanged). This is what isolates clause #4
    # from the floor/identity-set checks (test_cursor_clause_isolated_..._MUTATION).
    # the AUTHORITATIVE receiving-seat set is "seats with a seen/<seat>.txt cursor":
    # Phase A seeds ALL receiving seats, INCLUDING the broadcast-only coordinators that
    # are never a direct (non-`all`) recipient on disk. Deriving from disk `to` tokens
    # alone would silently SKIP those seats (vacuous agreement, not verified agreement).
    seated = {f.stem for f in seen.glob("*.txt")}
    disk_addressed: dict[str, list[str]] = {}     # seat -> [colon_ts...] from DISK
    for name in sorted(on_disk):
        m = _EVENT_NAME_RE.match(name)
        to = m.group("to")
        cts = _colon_ts(m.group("ts"))
        if to != "all":
            disk_addressed.setdefault(to, []).append(cts)
        else:                                       # broadcast counts for EVERY seated seat
            for seat in seated:
                disk_addressed.setdefault(seat, []).append(cts)
    # every seated seat (incl. the broadcast-only coordinators) is checked; the LEGACY and
    # PROJECTION views are still two INDEPENDENT derivations (disk `to`+broadcasts-to-all-
    # seated vs `e.recipient in (seat,'all')`). The cur-is-None guard below safely skips a
    # truly un-seeded seat that nonetheless appears via a disk/projection recipient.
    seats = sorted(seated | set(disk_addressed) |
                   {e.recipient for e in projected_events if e.recipient != "all"})
    for seat in seats:
        cur = _seen_value(seen, seat)
        if cur is None:
            continue  # un-seeded seat: cursor clause not applicable (Phase A seeds these)
        # LEGACY (disk): strictly-greater unread = on-disk events addressed to seat with ts > cursor
        legacy_unread = sum(1 for cts in disk_addressed.get(seat, []) if cts > cur)
        # PROJECTION (events): addressed via e.recipient; consumed-seq = highest seq whose
        # colon-ts <= cursor; unread = events with seq > consumed.
        addressed = [e for e in ordered if e.recipient in (seat, "all")]
        consumed = 0
        for e in addressed:
            ts = _colon_ts(_EVENT_NAME_RE.match(e.payload["source_filename"]).group("ts"))
            if ts <= cur:
                consumed = max(consumed, seq_of[e.payload["source_filename"]])
        proj_unread = sum(1 for e in addressed
                          if seq_of[e.payload["source_filename"]] > consumed)
        if legacy_unread != proj_unread:
            drifts.append(f"cursor[{seat}]: legacy unread {legacy_unread} != "
                          f"projection unread {proj_unread}")

    return Report(ok=not drifts, drifts=drifts)
