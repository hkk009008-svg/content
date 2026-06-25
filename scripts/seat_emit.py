#!/usr/bin/env python3
"""seat_emit.py — a real interactive seat signs ITS OWN T1 control-plane fact with ITS OWN key
(SP2 spec §3.2). Replaces scripts/bootstrap_emit.py. Static seat↔kind authority is enforced BEFORE
construction; the key is load_private(<explicit seat arg>), never derived from a caller-supplied
signer (the bootstrap_emit.py:50 injection hole)."""
import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:                      # ADR-055 self-bootstrap
    sys.path.insert(0, str(_REPO_ROOT))

from threeway import gitcas                              # noqa: E402
from threeway.envelope import Event                      # noqa: E402
from threeway.keys import load_private                   # noqa: E402
from threeway.loop import PAIR_A, PAIR_B, build_candidate_events  # noqa: E402
from threeway.refstore import AppendContentionExceeded, RefEventStore  # noqa: E402

SEATS = ("director", "director2", "operator", "operator2", "coordinator", "coordinator2")

# Static seat↔kind authority (T1 facts only; T2/T3 emission is a deferred follow-on).
AUTHORITY = {
    "coordinator":  {"candidate", "release_requested", "candidate_aborted"},
    "coordinator2": {"candidate", "release_requested", "candidate_aborted"},
    "operator":     {"attestation"},
    "operator2":    {"attestation"},
}
# The seat determines the pair (and thus the canonical event signer). No --pair-vs-seat conflict.
SEAT_PAIR = {"coordinator": PAIR_A, "operator": PAIR_A, "coordinator2": PAIR_B, "operator2": PAIR_B}
# provider derived from PairConfig (no operator_provider field — key on role).
PROVIDER = {}
for _p in (PAIR_A, PAIR_B):
    PROVIDER[_p.coordinator] = _p.coordinator_provider
    PROVIDER[_p.primary_verifier] = _p.verifier_provider


def _namespaced(pair, cid):
    return cid if ":" in cid else f"{pair.pair}:{cid}"


def _build_event(a) -> Event:
    """Build the seat's one fact, hard-binding the seat. Mirrors bootstrap_emit's shapes."""
    pair = SEAT_PAIR[a.seat]
    if a.fact == "candidate_aborted":
        cid = _namespaced(pair, a.candidate_id)
        ev = Event(
            id=f"candidate_aborted-{pair.coordinator}-{cid}", seq=0, bus_id=a.bus_id,
            schema_version="threeway/1", kind="candidate_aborted", sender=pair.coordinator,
            recipient="all", signer="", payload={"candidate_id": cid},
            brief_id=a.brief_id, brief_version=a.brief_version, candidate_id=cid,
        )
    else:
        repo = Path(a.repo_dir)
        base_sha = gitcas.rev_parse(repo, a.staging_base)
        branch_sha = gitcas.rev_parse(repo, a.branch)
        if base_sha is None:
            raise ValueError(f"cannot resolve staging-base ref {a.staging_base!r}")
        if branch_sha is None:
            raise ValueError(f"cannot resolve branch ref {a.branch!r}")
        cid = _namespaced(pair, a.candidate_id)
        tree, clean = gitcas.merge_tree(repo, base_sha, branch_sha)
        if not clean:
            raise ValueError("merge not clean — cannot compute integration_sha")
        integ = gitcas.commit_tree(repo, tree, [base_sha, branch_sha], f"threeway merge {cid}")
        events = build_candidate_events(base_sha, branch_sha, integ, {}, bus_id=a.bus_id,
                                        tier=a.tier, pair=pair, candidate_id=a.candidate_id)
        phase = getattr(a, "phase", None)
        ev = next((e for e in events
                   if e.kind == a.fact and (phase is None or e.payload.get("kind") == phase)), None)
        if ev is None:
            raise ValueError(f"builder produced no {a.fact}/{phase} event")
    # Hard-bind the seat identity into the (unsigned) signer tail; --session is audit-only. Event is a
    # mutable dataclass and `signer` is outside the 14-field signed view, so this does not affect the sig.
    ev.signer = f"{a.seat}:{PROVIDER[a.seat]}:{a.session}"
    assert ev.sender == a.seat, f"builder sender {ev.sender} != seat {a.seat}"   # authority-table invariant
    return ev


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A seat emits its own signed T1 bus fact.")
    ap.add_argument("seat", choices=SEATS)                # all 6 — body rejects non-emitters with rc2
    ap.add_argument("fact")
    ap.add_argument("--candidate-id", required=True)
    ap.add_argument("--pair", default="A", choices=["A", "B"])   # accepted for symmetry; SEAT_PAIR wins
    ap.add_argument("--staging-base", default=None)
    ap.add_argument("--branch", default=None)
    ap.add_argument("--tier", default="T1", choices=["T0", "T1", "T2", "T3"])
    ap.add_argument("--phase", default=None, choices=["preliminary", "release"])
    ap.add_argument("--brief-id", default="b1")
    ap.add_argument("--brief-version", type=int, default=1)
    ap.add_argument("--session", default=None)
    ap.add_argument("--bus-id", default="prod")
    ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--remote", default="origin")
    a = ap.parse_args(argv)
    a.session = a.session or "s1"

    # AUTHORITY CHECK FIRST — before any PairConfig/build work, so a bad (seat,fact) is rc2 not a crash.
    if a.fact not in AUTHORITY.get(a.seat, set()):
        print(f"seat {a.seat} may not emit {a.fact}", file=sys.stderr)
        return 2
    if a.fact != "candidate_aborted" and (a.staging_base is None or a.branch is None):
        print(f"{a.fact} requires --staging-base and --branch", file=sys.stderr)
        return 2
    if a.fact == "attestation" and a.phase is None:
        print("attestation requires --phase preliminary|release", file=sys.stderr)
        return 2

    try:
        ev = _build_event(a)
        store = RefEventStore(Path(a.repo_dir), remote=(a.remote or None))
        store.append(ev, load_private(a.seat))           # <-- EXPLICIT seat key, not signer-derived
    except FileNotFoundError as e:
        print(f"Error loading seat key: {e}", file=sys.stderr); return 1
    except AppendContentionExceeded as e:
        print(f"Bus contention, not emitted: {e}", file=sys.stderr); return 1
    except ValueError as e:
        print(f"Not emitted: {e}", file=sys.stderr); return 1
    except subprocess.CalledProcessError as e:
        print(f"Not emitted: git failed ({e})", file=sys.stderr); return 1
    print(f"Emitted {ev.kind}{'/' + a.phase if a.phase else ''} for {ev.candidate_id} (seq {ev.seq}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
