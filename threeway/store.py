"""Append-only signed-JSON event store (Slice 1, single-writer).

seq = (max existing seq) + 1; files named <seq:08d>-<id>.json so lexical order is
seq order. This is the Slice-1 substrate; Slice 2 replaces it with one git commit
per event on refs/threeway/events + an index ref + an expected-old-OID append-CAS
push loop (spec §8). The public read/iter API is intended to stay stable across
that swap.

iter_events()/all_events() are RAW readers — they do NOT verify signatures.
Signature/bus_id/signer verification is the merge-gate's single chokepoint
(threeway.gate.verify_and_reduce, §6.4); the store never silently trusts or
silently rejects, it just reads what was written.
"""
from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from threeway.envelope import Event, from_json_obj, sign_event, to_json_obj, well_formed


class EventIdCollision(ValueError):
    # ADR-037: event `id` must be globally unique (the gate/reducer key on id alone). A
    # colliding id would persist a second blob the consumers treat as a duplicate — refuse it.
    pass


class EventStore:
    def __init__(self, events_dir: str | Path):
        self._dir = Path(events_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _next_seq(self) -> int:
        seqs = [int(p.name.split("-", 1)[0]) for p in self._dir.glob("*.json")]
        return (max(seqs) + 1) if seqs else 1

    def append(self, ev: Event, private_key: Ed25519PrivateKey) -> Event:
        # ADR-037: event id must be globally unique (Rule #13 — mirror the refstore guard).
        # Files are <seq>-<id>.json; a colliding id would persist a second blob the gate
        # rejects as a duplicate. Refuse it here rather than corrupt the bus.
        if any(p.name.split("-", 1)[-1] == f"{ev.id}.json" for p in self._dir.glob("*.json")):
            raise EventIdCollision(f"event id already present: {ev.id!r}")
        ev.seq = self._next_seq()
        sign_event(ev, private_key)
        path = self._dir / f"{ev.seq:08d}-{ev.id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(to_json_obj(ev), indent=2, ensure_ascii=False))
        tmp.replace(path)  # atomic
        return ev

    def iter_events(self):
        for path in sorted(self._dir.glob("*.json")):
            # DROP-NOT-RAISE (Rule-13 sibling of ADR-046): mirror RefEventStore._iter_local —
            # a malformed file blob (non-JSON, missing a from_json_obj-required key, or a
            # wrong-typed field) must be INVISIBLE, never an uncaught raise that would wedge a
            # reader/scan if a live caller is ever wired to this (currently dormant) Slice-1 store.
            try:
                ev = from_json_obj(json.loads(path.read_text()))
            except (ValueError, KeyError, TypeError, UnicodeDecodeError):  # JSONDecodeError <: ValueError
                continue
            if not well_formed(ev):
                continue
            yield ev

    def all_events(self) -> list[Event]:
        return list(self.iter_events())
