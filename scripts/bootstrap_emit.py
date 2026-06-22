#!/usr/bin/env python3
"""bootstrap_emit.py — TEMPORARY interactive-seat fact shim (threeway scope-b sub-project 1).

REPLACED by sub-project 2 (real seat<->bus wiring). Emits the facts the interactive
seats own — candidate + release_requested (pair COORDINATOR key) and the two
attestations (pair PRIMARY_VERIFIER key) — so a human can drive a full brief->merge
flow today. Reuses threeway.loop.build_candidate_events for the canonical shapes.
"""
import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from threeway import gitcas
from threeway.keys import load_private
from threeway.loop import PAIR_A, PAIR_B, build_candidate_events
from threeway.refstore import AppendContentionExceeded, RefEventStore

_PAIRS = {"A": PAIR_A, "B": PAIR_B}


def _candidate_set(a):
    """Return (pair, events) for the candidate, computing the deterministic integ."""
    pair = _PAIRS[a.pair]
    base_sha = gitcas.rev_parse(Path(a.repo_dir), a.staging_base)   # gitcas.py:39 -> str | None
    branch_sha = gitcas.rev_parse(Path(a.repo_dir), a.branch)
    # Raise ValueError (caught by main() -> clean rc 1) rather than SystemExit, so main()
    # honors its `-> int` contract even on an in-process error-path call.
    if base_sha is None:
        raise ValueError(f"cannot resolve staging-base ref {a.staging_base!r}")
    if branch_sha is None:
        raise ValueError(f"cannot resolve branch ref {a.branch!r}")
    cid = a.candidate_id if ":" in a.candidate_id else f"{pair.pair}:{a.candidate_id}"
    tree, clean = gitcas.merge_tree(Path(a.repo_dir), base_sha, branch_sha)
    if not clean:
        raise ValueError("merge not clean — cannot compute integration_sha")
    integ = gitcas.commit_tree(Path(a.repo_dir), tree, [base_sha, branch_sha],
                               f"threeway merge {cid}")
    events = build_candidate_events(base_sha, branch_sha, integ, {}, bus_id=a.bus_id,
                                    tier=a.tier, pair=pair, candidate_id=a.candidate_id)
    return pair, events


def _append(a, ev) -> None:
    seat = ev.signer.split(":", 1)[0]
    store = RefEventStore(Path(a.repo_dir), remote=(a.remote or None))
    store.append(ev, load_private(seat))


def _pick(events, kind, phase=None):
    for ev in events:
        if ev.kind == kind and (phase is None or ev.payload.get("kind") == phase):
            return ev
    raise ValueError(f"builder produced no {kind}/{phase} event")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Threeway interactive-seat bootstrap emitter (TEMPORARY).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(p):
        p.add_argument("--candidate-id", required=True)
        p.add_argument("--pair", default="A", choices=["A", "B"])
        p.add_argument("--staging-base", required=True, help="ref or sha")
        p.add_argument("--branch", required=True, help="ref or sha")
        p.add_argument("--tier", default="T1", choices=["T0", "T1", "T2", "T3"])
        p.add_argument("--bus-id", default="prod")
        p.add_argument("--repo-dir", default=".")
        p.add_argument("--remote", default="origin")

    for name in ("candidate", "release_requested"):
        p = sub.add_parser(name); _common(p); p.set_defaults(kind=name, phase=None)
    pat = sub.add_parser("attestation"); _common(pat)
    pat.add_argument("--phase", required=True, choices=["preliminary", "release"])
    pat.set_defaults(kind="attestation")

    args = ap.parse_args(argv)
    if (args.remote or "").lower() in ("", "none"):
        args.remote = None
    phase = getattr(args, "phase", None)
    try:
        _, events = _candidate_set(args)
        ev = _pick(events, args.kind, phase)
        _append(args, ev)
    except FileNotFoundError as e:
        print(f"Error loading seat key: {e}", file=sys.stderr); return 1
    except AppendContentionExceeded as e:
        print(f"Bus contention, not emitted: {e}", file=sys.stderr); return 1
    except ValueError as e:
        print(f"Not emitted: {e}", file=sys.stderr); return 1
    print(f"Emitted {ev.kind}{'/' + phase if phase else ''} for {ev.candidate_id} (seq {ev.seq}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
