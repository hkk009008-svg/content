#!/usr/bin/env python3
"""Mechanical merge-gate daemon: poll the threeway bus and run the release predicate.

For every candidate referenced by a `release_requested` / `release_order` event, invoke
`threeway.gate.run_gate`, which independently verify+reduces the signed bus and, on a satisfied
predicate, CAS-merges the candidate's integration_sha onto main. run_gate is TOTAL: it returns a
`GateResult` whose `.outcome` is one of {COMPLETED, REJECTED, PENDING} and never raises after its CAS.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Bootstrap sys.path so a bare `python scripts/run_merge_gate.py` (the documented merge-gate runner)
# imports the repo-root `threeway` package regardless of CWD: running a file puts scripts/ on
# sys.path[0], not the repo root. Mirrors scripts/ci_smoke.py.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from threeway.gate import run_gate
from threeway.keys import load_private
from threeway.refstore import RefEventStore

_RELEASE_KINDS = ("release_requested", "release_order")


def collect_candidate_ids(store) -> set:
    """Every candidate_id referenced by a release_requested / release_order event on the bus.
    A RAW scan (run_gate re-verifies authority), so a forged request can only waste a gate run."""
    cids = set()
    for ev in store.iter_events():
        if ev.kind in _RELEASE_KINDS and ev.candidate_id:
            cids.add(ev.candidate_id)
    return cids


def poll_once(store, *, repo, registry_dir, bus_id, main_ref):
    """Run the gate once over every release-requested candidate.
    Returns [(candidate_id, GateResult)] sorted by candidate_id (deterministic)."""
    out = []
    for cid in sorted(collect_candidate_ids(store)):
        res = run_gate(candidate_id=cid, store=store, repo=repo, registry_dir=registry_dir,
                       bus_id=bus_id, main_ref=main_ref)
        out.append((cid, res))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Threeway merge-gate daemon.")
    ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--registry-dir", default="coordination/threeway/keys")
    ap.add_argument("--bus-id", default="prod")
    ap.add_argument("--main-ref", default="refs/heads/main")
    ap.add_argument("--interval", type=int, default=10, help="polling interval seconds")
    ap.add_argument("--run-once", action="store_true")
    args = ap.parse_args(argv)
    try:
        load_private("merge-gate")   # precondition: we hold the merge-gate credential
    except Exception as e:
        print(f"FATAL: could not load merge-gate credential: {e}", file=sys.stderr)
        return 1
    print("merge-gate daemon started.")
    while True:
        try:
            store = RefEventStore(Path(args.repo_dir))
            for cid, res in poll_once(store, repo=Path(args.repo_dir),
                                      registry_dir=args.registry_dir, bus_id=args.bus_id,
                                      main_ref=args.main_ref):
                if res.outcome == "COMPLETED":
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] MERGED {cid}")
                elif res.outcome != "PENDING":
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {res.outcome} {cid}: {res.reason}")
        except Exception as e:
            print(f"merge-gate iteration error: {e}", file=sys.stderr)
        if args.run_once:
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
