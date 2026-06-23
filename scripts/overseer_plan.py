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
from threeway.rework import REWORK_CAP, should_escalate

SCHEMA = "overseer-decision/1"
_TIERS = ("T0", "T1", "T2", "T3")
_ASSIGNMENT_FIELDS = ("pair", "builder", "builder_provider", "primary_verifier",
                      "primary_verifier_provider", "executing_coordinator")
# Ordered set of overseer facts overseer_plan may EMIT. release_order is deliberately EXCLUDED — it
# AUTHORIZES the merge (DD-4, generalized in ADR-058 DD-1: overseer_plan emits only requirement-ADDING /
# decision-PUBLISHING facts, never the gate-REMOVING one). approver_roster + re_verify_challenge are
# T3-only and gated in plan(); both can only make the gate STRICTER, so auto-emitting them is fail-safe.
_EMITTABLE = ("brief", "assignment", "cycle_go", "approver_roster", "re_verify_challenge")


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
    if raw["tier"] not in _TIERS:
        raise DecisionError(f"tier {raw['tier']!r} invalid — must be one of {_TIERS}")
    if raw["tier"] == "T3":
        approvers = raw.get("approvers")
        if not isinstance(approvers, list) or len({a for a in approvers if isinstance(a, str)}) < 2:
            raise DecisionError("a T3 decision requires 'approvers': a list of >=2 distinct seats "
                                "(the overseer approver_roster must authorize 2 distinct human approvals)")
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
    raw.setdefault("approvers", [])
    return raw


def _policy_digest(decision) -> str:
    return decision["policy_digest"] or default_policy().policy_digest()


def plan(decision, state, *, escalate=False):
    """Return (emittable, owed).
    emittable: absent overseer facts among (brief, assignment, cycle_go), canonical order.
    owed: [(fact, owner)] for everything else still missing (release_order + non-overseer facts).

    escalate (ADR-060): when the rework circuit-breaker is tripped (> REWORK_CAP AUTHORIZED reworks
    for this brief version), WITHHOLD a new `cycle_go` — the fact that authorizes another cycle.
    This is the fail-safe / requirement-ADDING direction (ADR-058 DD-1): the breaker can only HALT
    auto-progression, never advance it. The other emittable overseer facts are unaffected."""
    cid = decision["candidate_id"]
    bid = decision["brief_id"]
    ver = decision["brief_version"]
    pv = decision["assignment"]["primary_verifier"]
    pair = decision["assignment"]["pair"]
    tier = decision["tier"]
    is_t3 = tier == "T3"

    cand = state.candidate(cid)
    integ = cand.payload.get("integration_sha") if cand else None

    # (present, eligible) per emittable overseer fact, keyed by _EMITTABLE (release_order is NOT a key,
    # so it can never be emitted — the Q4 guard; an unknown key here raises a loud KeyError). The two
    # T3 facts are eligible only at T3; re_verify_challenge also needs the candidate's integration_sha.
    _spec = {
        "brief":               (state.brief(bid, ver),          True),
        "assignment":          (state.assignment(pair),         True),
        "cycle_go":            (state.cycle_go(bid, ver),       True),
        "approver_roster":     (state.approver_roster(cid),     is_t3),
        "re_verify_challenge": (state.re_verify_challenge(cid), is_t3 and integ is not None),
    }
    emittable = [f for f in _EMITTABLE if _spec[f][1] and _spec[f][0] is None
                 and not (escalate and f == "cycle_go")]   # ADR-060: breaker withholds a new cycle_go

    owed = []
    if cand is None:
        owed.append(("candidate", "coordinator"))
    if state.effective_attestation(cid, "preliminary", pv) is None:
        owed.append(("attestation:preliminary", pv))
    if state.effective_attestation(cid, "release", pv) is None:
        owed.append(("attestation:release", pv))
    if integ and state.ci_result(integ) is None:
        owed.append(("ci_result", "ci"))
    # tier-specific NON-overseer approvals — overseer_plan never holds these keys (DD-1)
    if tier in ("T2", "T3"):
        owed.append(("co_sign", "mirror-pair primary_verifier"))
    if is_t3:
        if state.re_verify(cid, pv) is None:
            owed.append(("re_verify", pv))
        for _ in range(max(0, 2 - _rostered_approvals(state, cid, integ))):
            owed.append(("human_approval", "rostered chief"))
    if state.release_order(cid) is None:
        owed.append(("release_order", "overseer-manual"))  # DD-4: surfaced, NEVER emitted here
    return emittable, owed


def _rostered_approvals(state, cid, integ):
    """Count distinct rostered, sha-bound, affirmative human_approvals already present (mirrors
    tier._two_distinct_human_approvals' filters; for the owed-surface progress count only)."""
    roster = state.approver_roster(cid)
    allowed = set(roster.payload.get("approvers", [])) if roster else set()
    seats = set()
    for ev in state.human_approvals(cid):
        seat = ev.signer.split(":", 1)[0]
        if (seat in allowed and ev.payload.get("integration_sha") == integ
                and ev.payload.get("decision") == "approve"):
            seats.add(seat)
    return len(seats)


def _emit_argv(fact, decision, repo_dir, remote, bus_id, integ=None):
    cid = decision["candidate_id"]
    bid = decision["brief_id"]
    tier = decision["tier"]
    ver = decision["brief_version"]
    asg = decision["assignment"]
    tail = ["--repo-dir", repo_dir, "--remote", remote, "--bus-id", bus_id]
    if fact == "brief":
        return ["brief", "--candidate-id", cid, "--brief-id", bid, "--assigned-tier", tier,
                "--brief-version", str(ver), "--allowed-paths", *decision["allowed_paths"], *tail]
    if fact == "assignment":
        return ["assignment", "--candidate-id", cid, "--pair", asg["pair"],
                "--builder", asg["builder"], "--builder-provider", asg["builder_provider"],
                "--primary-verifier", asg["primary_verifier"],
                "--primary-verifier-provider", asg["primary_verifier_provider"],
                "--executing-coordinator", asg["executing_coordinator"], *tail]
    if fact == "cycle_go":
        return ["cycle_go", "--candidate-id", cid, "--brief-id", bid, "--brief-version", str(ver),
                "--tier", tier, "--policy-digest", _policy_digest(decision), *tail]
    if fact == "approver_roster":
        return ["approver_roster", "--candidate-id", cid,
                "--approvers", *decision["approvers"], *tail]
    if fact == "re_verify_challenge":
        # overseer_emit mints a fresh nonce when --nonce is omitted; integ is the candidate's
        # integration_sha (the challenge subject_sha the gate echo-binds).
        return ["re_verify_challenge", "--candidate-id", cid, "--integration-sha", integ, *tail]
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
    # ADR-060: the rework circuit-breaker. Count only AUTHORIZED reworks for this brief version;
    # when tripped, withhold the new cycle_go and surface ESCALATE for chief review.
    escalate = should_escalate(state, decision["brief_id"], decision["brief_version"])
    emittable, owed = plan(decision, state, escalate=escalate)
    if escalate:
        print(f"⚠ ESCALATE: > {REWORK_CAP} authorized reworks for "
              f"{decision['brief_id']} v{decision['brief_version']} — withholding cycle_go "
              f"(chief manual review required; emit a new brief_version to resume).")
    _print_plan(emittable, owed, confirm=args.confirm)

    if not args.confirm:
        return 0
    cand = state.candidate(decision["candidate_id"])
    integ = cand.payload.get("integration_sha") if cand else None
    for fact in emittable:
        # Reuse overseer_emit (one signing path). Pass the RAW --remote so overseer_emit applies its own
        # ""/none -> None normalization; forward --bus-id so the write namespace == the read namespace.
        rc = overseer_emit.main(_emit_argv(fact, decision, args.repo_dir, args.remote, args.bus_id, integ))
        if rc != 0:
            print(f"overseer_plan: emit of {fact!r} failed (rc {rc}); stopping.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
