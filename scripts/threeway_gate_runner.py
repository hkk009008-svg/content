#!/usr/bin/env python3
"""Safe dry-run wrapper for the threeway merge gate.

Production refs are deliberately out of scope for ready-not-live adoption.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from threeway.gate import GateResult, _RepoAdapter, run_gate, verify_and_reduce
from threeway.predicate import evaluate
from threeway.policy import default_policy
from threeway.store import EventStore

DEFAULT_TEST_MAIN_REF = "refs/threeway/test-main"
_PROTECTED_MAIN_REFS = {"main", "origin/main", "refs/heads/main", "refs/remotes/origin/main"}


def _die(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _refuses_protected_main(ref: str) -> bool:
    return ref in _PROTECTED_MAIN_REFS


def _dry_run(candidate_id: str, store: EventStore, repo: Path, registry: Path, bus_id: str,
             main_ref: str) -> GateResult:
    state = verify_and_reduce(store.all_events(), registry_dir=registry, bus_id=bus_id)
    decision = evaluate(candidate_id, state, _RepoAdapter(repo), default_policy(), main_ref=main_ref)
    return GateResult(decision.outcome, decision.reason)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--store-dir", required=True, type=Path)
    parser.add_argument("--bus-id", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--main-ref", default=DEFAULT_TEST_MAIN_REF)
    parser.add_argument("--json", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    mode.add_argument("--execute", dest="dry_run", action="store_false")
    args = parser.parse_args(argv)

    if _refuses_protected_main(args.main_ref):
        return _die(f"threeway gate runner refuses protected main ref: {args.main_ref}")
    if not args.dry_run and args.main_ref != DEFAULT_TEST_MAIN_REF:
        return _die(f"--execute is allowed only against {DEFAULT_TEST_MAIN_REF} in ready-not-live mode")

    try:
        store = EventStore(args.store_dir)
        if args.dry_run:
            result = _dry_run(args.candidate_id, store, args.repo, args.registry, args.bus_id, args.main_ref)
        else:
            result = run_gate(
                args.candidate_id,
                store,
                args.repo,
                registry_dir=args.registry,
                bus_id=args.bus_id,
                main_ref=args.main_ref,
            )
        payload = {
            "candidate_id": args.candidate_id,
            "dry_run": args.dry_run,
            "main_ref": args.main_ref,
            "outcome": result.outcome,
            "reason": result.reason,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"{payload['outcome']}: {payload['reason']}")
        return 0
    except Exception as exc:
        return _die(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
