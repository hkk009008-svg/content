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
from threeway.approval_authority import (                # noqa: E402
    current_reverify_challenge_nonce,
    event_by_id,
    required_mirror_cosigner,
    required_re_verifier,
    resolve_candidate_context,
    signer_seat,
)
from threeway.envelope import Event                      # noqa: E402
from threeway.gate import verify_and_reduce              # noqa: E402
from threeway.keys import load_private                   # noqa: E402
from threeway.loop import PAIR_A, PAIR_B, build_candidate_events  # noqa: E402
from threeway.refstore import AppendContentionExceeded, RefEventStore  # noqa: E402

SEATS = ("director", "director2", "operator", "operator2", "coordinator", "coordinator2")

AUTHORITY = {
    "coordinator":  {"candidate", "release_requested", "candidate_aborted", "attestation_revoked"},
    "coordinator2": {"candidate", "release_requested", "candidate_aborted", "attestation_revoked"},
    "operator":     {"attestation", "co_sign", "re_verify", "attestation_revoked"},
    "operator2":    {"attestation", "co_sign", "re_verify", "attestation_revoked"},
    "director":     {"attestation_revoked"},
    "director2":    {"attestation_revoked"},
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


def _state_and_events(a):
    store = RefEventStore(Path(a.repo_dir), remote=(a.remote or None))
    events = store.all_events()
    state = verify_and_reduce(events, registry_dir=a.registry_dir, bus_id=a.bus_id)
    return store, events, state


def _dynamic_event(a) -> Event:
    store, events, state = _state_and_events(a)
    if a.fact in {"co_sign", "re_verify"}:
        ctx = resolve_candidate_context(state, a.candidate_id)
        if a.fact == "co_sign":
            required = required_mirror_cosigner(state, ctx)
            if required != a.seat:
                raise PermissionError(f"required co_sign seat is {required or '(none)'}, not {a.seat}")
            return Event(
                id=f"co_sign-{a.seat}-{ctx.candidate_id}", seq=0, bus_id=a.bus_id,
                schema_version="threeway/1", kind="co_sign", sender=a.seat, recipient="all",
                signer=f"{a.seat}:{PROVIDER[a.seat]}:{a.session}", payload={"verdict": a.verdict},
                brief_id=ctx.brief_id, brief_version=ctx.brief_version,
                candidate_id=ctx.candidate_id, subject_sha=ctx.integration_sha,
            )
        required = required_re_verifier(state, ctx)
        if required != a.seat:
            raise PermissionError(f"required re_verify seat is {required}, not {a.seat}")
        nonce = current_reverify_challenge_nonce(state, ctx)
        if nonce is None:
            raise PermissionError("no current re_verify_challenge for candidate integration_sha")
        return Event(
            id=f"re_verify-{a.seat}-{ctx.candidate_id}", seq=0, bus_id=a.bus_id,
            schema_version="threeway/1", kind="re_verify", sender=a.seat, recipient="all",
            signer=f"{a.seat}:{PROVIDER[a.seat]}:{a.session}",
            payload={"verdict": a.verdict, "challenge_nonce": nonce},
            brief_id=ctx.brief_id, brief_version=ctx.brief_version,
            candidate_id=ctx.candidate_id, subject_sha=ctx.integration_sha,
        )
    if a.fact == "attestation_revoked":
        target = event_by_id(events, a.revokes_event_id)
        if target is None or signer_seat(target.signer) != a.seat:
            raise PermissionError("seat may only revoke its own prior fact")
        return Event(
            id=f"attestation_revoked-{a.seat}-{a.revokes_event_id}", seq=0, bus_id=a.bus_id,
            schema_version="threeway/1", kind="attestation_revoked", sender=a.seat,
            recipient="all", signer=f"{a.seat}:{PROVIDER.get(a.seat, 'seat')}:{a.session}",
            payload={}, brief_id=target.brief_id, brief_version=target.brief_version,
            candidate_id=target.candidate_id, subject_sha=target.subject_sha,
            revokes_event_id=a.revokes_event_id,
        )
    raise ValueError(f"unsupported dynamic fact {a.fact}")


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
    ap.add_argument("--registry-dir", default="coordination/threeway/keys")
    ap.add_argument("--verdict", default="GO", choices=["GO", "NITS", "FAIL"])
    ap.add_argument("--revokes-event-id", default=None)
    a = ap.parse_args(argv)
    a.session = a.session or "s1"

    # AUTHORITY CHECK FIRST — before any PairConfig/build work, so a bad (seat,fact) is rc2 not a crash.
    if a.fact not in AUTHORITY.get(a.seat, set()):
        print(f"seat {a.seat} may not emit {a.fact}", file=sys.stderr)
        return 2
    if a.fact in {"co_sign", "re_verify"}:
        if ":" not in a.candidate_id:
            print(f"{a.fact} requires pair-namespaced --candidate-id", file=sys.stderr)
            return 2
    elif a.fact == "attestation_revoked":
        if not a.revokes_event_id:
            print("attestation_revoked requires --revokes-event-id", file=sys.stderr)
            return 2
    elif a.fact != "candidate_aborted" and (a.staging_base is None or a.branch is None):
        print(f"{a.fact} requires --staging-base and --branch", file=sys.stderr)
        return 2
    if a.fact == "attestation" and a.phase is None:
        print("attestation requires --phase preliminary|release", file=sys.stderr)
        return 2

    try:
        if a.fact in {"co_sign", "re_verify", "attestation_revoked"}:
            ev = _dynamic_event(a)
        else:
            ev = _build_event(a)
        store = RefEventStore(Path(a.repo_dir), remote=(a.remote or None))
        store.append(ev, load_private(a.seat))           # <-- EXPLICIT seat key, not signer-derived
    except PermissionError as e:
        print(str(e), file=sys.stderr); return 2
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
