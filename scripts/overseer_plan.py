#!/usr/bin/env python3
"""overseer_plan.py — auto-decompose one chief decision into the overseer facts emittable now.

Reads a JSON decision file (overseer-decision/1) + the live bus, computes which overseer facts
(brief/assignment/cycle_go) are ABSENT and therefore emittable, and — on --confirm — emits them by
REUSING scripts/overseer_emit.main (one signing path; ADR-057 DD-5). Dry-run by default. NEVER emits
release_order (the merge-authorization key stays a deliberate manual `overseer_emit` act; ADR-057 DD-4).
Surfaces every still-owed fact (release_order + the non-overseer candidate/attestation/ci_result) by owner.
"""
import argparse
import json
import sys
from pathlib import Path

# ADR-055: bare `python scripts/overseer_plan.py` puts scripts/ (not the repo root) on sys.path[0];
# put the repo root first so `import threeway` / `from scripts import overseer_emit` resolve.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import overseer_emit
from threeway.gate import verify_and_reduce
from threeway.policy import default_policy
from threeway.refstore import RefEventStore

SCHEMA = "overseer-decision/1"
_TIERS_SUPPORTED = ("T0", "T1")
_ASSIGNMENT_FIELDS = ("pair", "builder", "builder_provider", "primary_verifier",
                      "primary_verifier_provider", "executing_coordinator")
# overseer facts overseer_plan may EMIT; release_order is deliberately excluded (DD-4).
_EMITTABLE = ("brief", "assignment", "cycle_go")


class DecisionError(ValueError):
    """Malformed or unsupported decision file (-> exit 2)."""


def load_decision(path) -> dict:
    """Read + validate the JSON decision. Raise DecisionError on any problem."""
    try:
        raw = json.loads(Path(path).read_text())
    except FileNotFoundError as e:
        raise DecisionError(f"decision file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise DecisionError(f"decision file is not valid JSON: {e}") from e
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        got = raw.get("schema") if isinstance(raw, dict) else type(raw).__name__
        raise DecisionError(f"decision schema must be {SCHEMA!r}, got {got!r}")
    for f in ("candidate_id", "brief_id", "tier", "allowed_paths", "assignment"):
        if f not in raw:
            raise DecisionError(f"decision missing required field: {f!r}")
    if raw["tier"] not in _TIERS_SUPPORTED:
        raise DecisionError(f"tier {raw['tier']!r} unsupported — overseer_plan handles T0/T1 only "
                            "(T2/T3 approver_roster/re_verify_challenge are a documented fast-follow)")
    if not isinstance(raw["allowed_paths"], list) or not raw["allowed_paths"]:
        raise DecisionError("allowed_paths must be a non-empty list")
    asg = raw["assignment"]
    if not isinstance(asg, dict):
        raise DecisionError("assignment must be an object")
    for f in _ASSIGNMENT_FIELDS:
        if not asg.get(f):
            raise DecisionError(f"assignment missing required field: {f!r}")
    raw.setdefault("brief_version", 1)
    raw.setdefault("policy_digest", None)
    return raw


def _policy_digest(decision) -> str:
    return decision["policy_digest"] or default_policy().policy_digest()


def plan(decision, state):
    """Return (emittable, owed).
    emittable: absent overseer facts among (brief, assignment, cycle_go), canonical order.
    owed: [(fact, owner)] for everything else still missing (release_order + non-overseer facts)."""
    cid = decision["candidate_id"]
    bid = decision["brief_id"]
    ver = decision["brief_version"]
    pv = decision["assignment"]["primary_verifier"]
    pair = decision["assignment"]["pair"]

    emittable = []
    if state.brief(bid, ver) is None:
        emittable.append("brief")
    if state.assignment(pair) is None:
        emittable.append("assignment")
    if state.cycle_go(bid, ver) is None:
        emittable.append("cycle_go")

    owed = []
    cand = state.candidate(cid)
    if cand is None:
        owed.append(("candidate", "coordinator"))
    if state.effective_attestation(cid, "preliminary", pv) is None:
        owed.append(("attestation:preliminary", pv))
    if state.effective_attestation(cid, "release", pv) is None:
        owed.append(("attestation:release", pv))
    if cand is not None:
        integ = cand.payload.get("integration_sha")
        if integ and state.ci_result(integ) is None:
            owed.append(("ci_result", "ci"))
    if state.release_order(cid) is None:
        owed.append(("release_order", "overseer-manual"))  # DD-4: surfaced, NEVER emitted here
    return emittable, owed


def _emit_argv(fact, decision, repo_dir, remote, bus_id):
    cid = decision["candidate_id"]
    bid = decision["brief_id"]
    tier = decision["tier"]
    ver = decision["brief_version"]
    asg = decision["assignment"]
    tail = ["--repo-dir", repo_dir, "--remote", remote, "--bus-id", bus_id]
    if fact == "brief":
        return ["brief", "--candidate-id", cid, "--brief-id", bid, "--assigned-tier", tier,
                "--allowed-paths", *decision["allowed_paths"], *tail]
    if fact == "assignment":
        return ["assignment", "--candidate-id", cid, "--pair", asg["pair"],
                "--builder", asg["builder"], "--builder-provider", asg["builder_provider"],
                "--primary-verifier", asg["primary_verifier"],
                "--primary-verifier-provider", asg["primary_verifier_provider"],
                "--executing-coordinator", asg["executing_coordinator"], *tail]
    if fact == "cycle_go":
        return ["cycle_go", "--candidate-id", cid, "--brief-id", bid, "--brief-version", str(ver),
                "--tier", tier, "--policy-digest", _policy_digest(decision), *tail]
    raise ValueError(f"{fact!r} is not an overseer_plan-emittable fact")  # release_order never reaches here


def _read_state(repo_dir, registry_dir, remote, bus_id):
    store = RefEventStore(Path(repo_dir), remote=(remote or None))
    return verify_and_reduce(store.all_events(), registry_dir=registry_dir, bus_id=bus_id)


def _print_plan(emittable, owed, *, confirm):
    if emittable:
        print(f"{'EMITTING' if confirm else 'WOULD EMIT'} (overseer): {', '.join(emittable)}")
    else:
        print("Nothing to emit (all emittable overseer facts already present).")
    if owed:
        print("OWED (not overseer_plan's to emit):")
        for fact, owner in owed:
            print(f"  - {fact}  [{owner}]")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Auto-decompose a chief decision into the overseer facts emittable now.")
    ap.add_argument("--decision", required=True, help="path to an overseer-decision/1 JSON file")
    ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--registry-dir", default="coordination/threeway/keys")
    ap.add_argument("--remote", default="origin", help='"" or "none" = local mode')
    ap.add_argument("--bus-id", default="prod")
    ap.add_argument("--confirm", action="store_true", help="actually emit (default: dry-run)")
    args = ap.parse_args(argv)

    try:
        decision = load_decision(args.decision)
    except DecisionError as e:
        print(f"Invalid decision: {e}", file=sys.stderr)
        return 2

    remote = None if (args.remote or "").lower() in ("", "none") else args.remote
    state = _read_state(args.repo_dir, args.registry_dir, remote, args.bus_id)
    emittable, owed = plan(decision, state)
    _print_plan(emittable, owed, confirm=args.confirm)

    if not args.confirm:
        return 0
    for fact in emittable:
        # Reuse overseer_emit (one signing path). Pass the RAW --remote so overseer_emit applies its own
        # ""/none -> None normalization; forward --bus-id so the write namespace == the read namespace.
        rc = overseer_emit.main(_emit_argv(fact, decision, args.repo_dir, args.remote, args.bus_id))
        if rc != 0:
            print(f"overseer_plan: emit of {fact!r} failed (rc {rc}); stopping.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
