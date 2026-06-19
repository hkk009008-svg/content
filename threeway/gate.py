"""The mechanical merge-gate (spec §4, §6.3, §6.4).

Read-side (this part): verify EVERY load-bearing event's signature against the
committed public-key registry, reject bus_id mismatches (replay), reject unknown
signer seats, then reduce only verified events. The gate NEVER executes candidate
code; it acts only on signed facts + a signed ci_result.
"""
from __future__ import annotations

from cryptography.exceptions import InvalidSignature

from threeway import LOAD_BEARING_KINDS
from threeway.envelope import verify_event
from threeway.keys import PublicKeyRegistry
from threeway.reducer import reduce


class GateError(Exception):
    pass


def _seat(signer: str) -> str:
    return signer.split(":", 1)[0]


def verify_and_reduce(events, registry_dir, bus_id: str):
    reg = PublicKeyRegistry(registry_dir)
    verified = []
    for ev in events:
        if ev.kind in LOAD_BEARING_KINDS:
            if ev.bus_id != bus_id:
                raise GateError(f"bus_id mismatch (replay?): {ev.bus_id!r} != {bus_id!r}")
            seat = _seat(ev.signer)
            try:
                pub = reg.get(seat)
            except KeyError as e:
                raise GateError(f"unknown signer seat: {seat!r}") from e
            try:
                verify_event(ev, pub)
            except InvalidSignature as e:
                raise GateError(f"invalid signature on {ev.kind} {ev.id}") from e
        verified.append(ev)
    return reduce(verified)
