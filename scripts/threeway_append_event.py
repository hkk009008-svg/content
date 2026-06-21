#!/usr/bin/env python3
"""Sign and append one explicit threeway event in pre-live mode.

This is intentionally narrow: callers must name the signer seat, bus id, registry,
keystore, and input event JSON. There is no generated private-key fallback.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from threeway import THREEWAY_KINDS
from threeway.envelope import from_json_obj, to_json_obj, well_formed
from threeway.keys import PublicKeyRegistry, load_private, public_hex
from threeway.store import EventStore


_KIND_AUTHORITY: dict[str, set[str]] = {
    "brief": {"overseer"},
    "brief_superseded": {"overseer"},
    "assignment": {"overseer"},
    "cycle_go": {"overseer"},
    "release_order": {"overseer"},
    "re_verify_challenge": {"overseer"},
    "approver_roster": {"overseer"},
    "candidate": {"coordinator", "coordinator2"},
    "candidate_aborted": {"coordinator", "coordinator2"},
    "release_requested": {"coordinator", "coordinator2"},
    "attestation": {"operator", "operator2"},
    "attestation_revoked": {"operator", "operator2", "overseer"},
    "co_sign": {"operator", "operator2"},
    "re_verify": {"operator", "operator2"},
    "human_approval": {"chief-gemini", "chief-chatgpt"},
    "ci_result": {"ci"},
    "merge_completed": {"merge-gate"},
    "event_sent": {"migration-importer"},
    "event_acknowledged": {"migration-importer"},
    "event_rejected": {"migration-importer"},
    "event_timed_out": {"migration-importer"},
    "event_retried": {"migration-importer"},
    "dead_letter": {"migration-importer"},
}


def _seat_from_signer(signer: str) -> str:
    return signer.split(":", 1)[0]


def _die(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _validate_authority(event, seat: str, bus_id: str) -> None:
    if not well_formed(event):
        raise ValueError("event envelope is not structurally well-formed")
    if event.kind not in THREEWAY_KINDS:
        raise ValueError(f"unknown threeway event kind: {event.kind!r}")
    if event.bus_id != bus_id:
        raise ValueError(f"event bus_id {event.bus_id!r} != requested bus_id {bus_id!r}")
    signer_seat = _seat_from_signer(event.signer)
    if signer_seat != seat:
        raise ValueError(f"event signer seat {signer_seat!r} != requested seat {seat!r}")
    allowed = _KIND_AUTHORITY.get(event.kind, set())
    if seat not in allowed:
        raise ValueError(
            f"{event.kind} may only be signed by {', '.join(sorted(allowed))}; got {seat}"
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-json", required=True, type=Path)
    parser.add_argument("--store-dir", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--keystore", required=True, type=Path)
    parser.add_argument("--bus-id", required=True)
    parser.add_argument("--seat", required=True)
    parser.add_argument("--dry-run", action="store_true", help="sign and print, but do not append")
    args = parser.parse_args(argv)

    try:
        event = from_json_obj(json.loads(args.event_json.read_text()))
        _validate_authority(event, args.seat, args.bus_id)
        os.environ["THREEWAY_KEYSTORE"] = str(args.keystore)
        private_key = load_private(args.seat)
        registry_pub = PublicKeyRegistry(args.registry).get(args.seat)
        derived_pub = public_hex(private_key)
        if registry_pub != derived_pub:
            raise ValueError(f"private key for {args.seat!r} does not match registry public key")
        if args.dry_run:
            from threeway.envelope import sign_event

            sign_event(event, private_key)
            print(json.dumps(to_json_obj(event), indent=2, sort_keys=True))
            return 0
        appended = EventStore(args.store_dir).append(event, private_key)
        print(json.dumps(to_json_obj(appended), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        return _die(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
