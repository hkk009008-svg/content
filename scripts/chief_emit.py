#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from threeway.approval_authority import event_by_id, rostered_approvers, signer_seat  # noqa: E402
from threeway.envelope import Event  # noqa: E402
from threeway.gate import verify_and_reduce  # noqa: E402
from threeway.keys import PublicKeyRegistry, load_private  # noqa: E402
from threeway.refstore import AppendContentionExceeded, RefEventStore  # noqa: E402


def _state_events_store(args):
    store = RefEventStore(Path(args.repo_dir), remote=(args.remote or None))
    events = store.all_events()
    state = verify_and_reduce(events, registry_dir=args.registry_dir, bus_id=args.bus_id)
    return state, events, store


def _build_human_approval(args):
    state, events, store = _state_events_store(args)
    try:
        PublicKeyRegistry(args.registry_dir).get(args.approver)
    except KeyError:
        raise PermissionError(f"approver {args.approver} has no public registry key")
    if args.approver not in rostered_approvers(state, args.candidate_id):
        raise PermissionError(f"approver {args.approver} is not rostered for {args.candidate_id}")
    return Event(
        id=f"human_approval-{args.approver}-{args.candidate_id}", seq=0, bus_id=args.bus_id,
        schema_version="threeway/1", kind="human_approval", sender=args.approver,
        recipient="all", signer=f"{args.approver}:human:cli",
        payload={"approver_identity": args.approver, "integration_sha": args.integration_sha,
                 "decision": args.decision},
        candidate_id=args.candidate_id, subject_sha=args.integration_sha,
    )


def _build_revoke(args):
    state, events, store = _state_events_store(args)
    target = event_by_id(events, args.revokes_event_id)
    if target is None or signer_seat(target.signer) != args.approver:
        raise PermissionError("chief may only revoke its own prior fact")
    return Event(
        id=f"attestation_revoked-{args.approver}-{args.revokes_event_id}", seq=0,
        bus_id=args.bus_id, schema_version="threeway/1", kind="attestation_revoked",
        sender=args.approver, recipient="all", signer=f"{args.approver}:human:cli",
        payload={}, candidate_id=target.candidate_id, subject_sha=target.subject_sha,
        revokes_event_id=args.revokes_event_id,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Chief approver threeway signing CLI.")
    parser.add_argument("approver")
    parser.add_argument("fact", choices=["human_approval", "attestation_revoked"])
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--integration-sha")
    parser.add_argument("--decision", default="approve", choices=["approve"])
    parser.add_argument("--revokes-event-id")
    parser.add_argument("--registry-dir", default="coordination/threeway/keys")
    parser.add_argument("--repo-dir", default=".")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--bus-id", default="prod")
    args = parser.parse_args(argv)
    if (args.remote or "").lower() in ("", "none"):
        args.remote = None
    if args.fact == "human_approval" and not args.integration_sha:
        print("human_approval requires --integration-sha", file=sys.stderr)
        return 2
    if args.fact == "attestation_revoked" and not args.revokes_event_id:
        print("attestation_revoked requires --revokes-event-id", file=sys.stderr)
        return 2
    try:
        ev = _build_human_approval(args) if args.fact == "human_approval" else _build_revoke(args)
        RefEventStore(Path(args.repo_dir), remote=(args.remote or None)).append(ev, load_private(args.approver))
    except PermissionError as exc:
        print(str(exc), file=sys.stderr); return 2
    except FileNotFoundError as exc:
        print(f"Error loading chief key: {exc}", file=sys.stderr); return 1
    except AppendContentionExceeded as exc:
        print(f"Bus contention, not emitted: {exc}", file=sys.stderr); return 1
    except ValueError as exc:
        print(f"Not emitted: {exc}", file=sys.stderr); return 1
    print(f"Emitted {ev.kind} for {ev.candidate_id} (seq {ev.seq}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
