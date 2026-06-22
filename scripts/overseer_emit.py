#!/usr/bin/env python3
"""overseer_emit.py — human-operated overseer signing CLI (threeway scope-b sub-project 1).

Emits each overseer-authority fact (brief/assignment/cycle_go/release_order/
approver_roster/re_verify_challenge) signed with the OVERSEER key only. Mirrors the
payload/envelope shapes built by threeway.loop.build_candidate_events (the implicit
spec — a wrong key name makes the reducer/predicate silently drop the fact).
"""
import argparse
import sys
from pathlib import Path

# ADR-055: bare `python scripts/overseer_emit.py` puts scripts/ (not the repo root) on
# sys.path[0]; put the repo root first so `import threeway` resolves.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from threeway.envelope import Event
from threeway.keys import load_private
from threeway.refstore import AppendContentionExceeded, RefEventStore

BUS = "prod"
OVERSEER_SIGNER = "overseer:mech:cli"   # seat MUST be "overseer"; signed with the overseer key


def _emit(repo_dir, remote, ev: Event) -> Event:
    """Append+sign ev with the overseer key. seq=0 in; store assigns seq then signs."""
    private_key = load_private("overseer")            # overseer key ONLY
    store = RefEventStore(Path(repo_dir), remote=(remote or None))
    return store.append(ev, private_key)              # never pre-sign


def _build_event(kind, payload, candidate_id, *, brief_id="b1", brief_version=1,
                 subject_sha=None, bus_id=BUS, ev_id=None) -> Event:
    return Event(
        id=ev_id or f"{kind}-overseer-{candidate_id}", seq=0, bus_id=bus_id,
        schema_version="threeway/1", kind=kind, sender="overseer", recipient="all",
        signer=OVERSEER_SIGNER, payload=payload, brief_id=brief_id,
        brief_version=brief_version, candidate_id=candidate_id, subject_sha=subject_sha,
    )


def _cmd_brief(a) -> Event:
    payload = {"brief_id": a.brief_id, "assigned_tier": a.assigned_tier,
               "allowed_paths": list(a.allowed_paths)}
    return _build_event("brief", payload, a.candidate_id, brief_id=a.brief_id,
                        brief_version=a.brief_version, bus_id=a.bus_id)


def _cmd_assignment(a) -> Event:
    payload = {"pair": a.pair, "builder": a.builder, "builder_provider": a.builder_provider,
               "primary_verifier": a.primary_verifier,
               "primary_verifier_provider": a.primary_verifier_provider,
               "executing_coordinator": a.executing_coordinator}
    return _build_event("assignment", payload, a.candidate_id, bus_id=a.bus_id)


def _cmd_cycle_go(a) -> Event:
    payload = {"brief_id": a.brief_id, "brief_version": a.brief_version,
               "tier": a.tier, "policy_digest": a.policy_digest}
    return _build_event("cycle_go", payload, a.candidate_id,
                        brief_id=a.brief_id, brief_version=a.brief_version, bus_id=a.bus_id)


def _cmd_release_order(a) -> Event:
    return _build_event("release_order", {"candidate_id": a.candidate_id}, a.candidate_id,
                        subject_sha=a.integration_sha, bus_id=a.bus_id)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Threeway overseer signing CLI.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(p):
        p.add_argument("--candidate-id", required=True, help="full pair-namespaced id, e.g. A:c1")
        p.add_argument("--bus-id", default=BUS)
        p.add_argument("--repo-dir", default=".")
        p.add_argument("--remote", default="origin", help='"" or "none" = local mode')

    pb = sub.add_parser("brief"); _common(pb)
    pb.add_argument("--brief-id", default="b1")
    pb.add_argument("--brief-version", type=int, default=1)
    pb.add_argument("--assigned-tier", required=True, choices=["T0", "T1", "T2", "T3"])
    pb.add_argument("--allowed-paths", nargs="+", required=True)
    pb.set_defaults(fn=_cmd_brief)

    pa = sub.add_parser("assignment"); _common(pa)
    for f in ("pair", "builder", "builder-provider", "primary-verifier",
              "primary-verifier-provider", "executing-coordinator"):
        pa.add_argument(f"--{f}", required=True)
    pa.set_defaults(fn=_cmd_assignment)

    pc = sub.add_parser("cycle_go"); _common(pc)
    pc.add_argument("--brief-id", default="b1")
    pc.add_argument("--brief-version", type=int, default=1)
    pc.add_argument("--tier", required=True, choices=["T0", "T1", "T2", "T3"])
    pc.add_argument("--policy-digest", required=True)
    pc.set_defaults(fn=_cmd_cycle_go)

    pr = sub.add_parser("release_order"); _common(pr)
    pr.add_argument("--integration-sha", required=True)
    pr.set_defaults(fn=_cmd_release_order)

    args = ap.parse_args(argv)
    if (args.remote or "").lower() in ("", "none"):
        args.remote = None
    try:
        ev = _emit(args.repo_dir, args.remote, args.fn(args))
    except FileNotFoundError as e:
        print(f"Error loading overseer key: {e}", file=sys.stderr); return 1
    except AppendContentionExceeded as e:
        print(f"Bus contention, not emitted: {e}", file=sys.stderr); return 1
    print(f"Emitted {ev.kind} for {ev.candidate_id} (seq {ev.seq}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
