#!/usr/bin/env python3
"""Mechanical merge-gate daemon: poll the threeway bus and run the release predicate.

For every candidate referenced by a `release_requested` / `release_order` event, invoke
`threeway.gate.run_gate`, which independently verify+reduces the signed bus and, on a satisfied
predicate, CAS-merges the candidate's integration_sha onto main. run_gate is TOTAL: it returns a
`GateResult` whose `.outcome` is one of {COMPLETED, REJECTED, PENDING} and never raises after its CAS.
"""
from __future__ import annotations

import argparse
import signal
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

# Module-level stop flag, flipped by a SIGTERM/SIGINT handler so the daemon can be
# shut down between poll iterations WITHOUT aborting an in-flight poll_once (which
# could leave the CAS merge half-done). Checked only at the TOP of the loop body.
_STOP = False


def _handle_stop(_signum, _frame):
    # Async-signal-safe: only flip the flag (no I/O); the loop observes it at the next top.
    global _STOP
    _STOP = True


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


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Threeway merge-gate daemon.")
    ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--registry-dir", default="coordination/threeway/keys")
    ap.add_argument("--bus-id", default="prod")
    # SAFETY (ADR-056 DD-1): default to the protected TEST ref, NEVER real refs/heads/main.
    # The library predicate default is already the safe test-main; the daemon must not
    # override it back to production main. An operator may still pass --main-ref explicitly.
    ap.add_argument("--main-ref", default="refs/threeway/test-main")
    # DD-3: when set, the RefEventStore is a clone of the live authoritative bus repo
    # (push/fetch CAS against this remote); None = local co-located bus.
    ap.add_argument("--remote", default=None, help="authoritative bus remote (live bus); default local")
    ap.add_argument("--interval", type=int, default=10, help="polling interval seconds")
    ap.add_argument("--run-once", action="store_true")
    return ap


def main(argv=None) -> int:
    args = _build_argparser().parse_args(argv)
    try:
        load_private("merge-gate")   # precondition: we hold the merge-gate credential
    except Exception as e:
        print(f"FATAL: could not load merge-gate credential: {e}", file=sys.stderr)
        return 1
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    print("merge-gate daemon started.")
    while True:
        if _STOP:
            # Requested clean shutdown -> exit 0 (NOT 130/143): a supervisor must read this
            # as a normal stop, not a crash to restart-as-failure.
            print("merge-gate daemon stopped.")
            return 0
        try:
            store = RefEventStore(Path(args.repo_dir), remote=args.remote)
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
