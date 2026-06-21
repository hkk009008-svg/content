#!/usr/bin/env python3
"""Emit a signed `ci_result` event to the threeway signed bus (the CI seat's fact).

Usage: sign_ci_result.py --integration-sha <sha> [--result PASS|FAIL] [--repo-dir .] [--remote origin]

`ci_result` is reduced/keyed by `subject_sha` (= the integration sha), must be signed by the
trusted `ci` seat, and carries {result, policy_digest} (see threeway/predicate.py:152-161 and
threeway/loop.py:104). We bind candidate_id too when the candidate is already on the bus
(informational; the reducer keys ci_result on subject_sha, not candidate_id).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from threeway.envelope import Event
from threeway.keys import load_private
from threeway.policy import default_policy
from threeway.refstore import RefEventStore

CI_BUS = "prod"


def _find_candidate_id(store, integration_sha: str) -> str | None:
    """The candidate_id whose candidate event declares this integration_sha (in its payload), if
    present. Informational only — ci_result is reduced by subject_sha."""
    for ev in store.iter_events():
        if ev.kind == "candidate" and ev.payload.get("integration_sha") == integration_sha:
            return ev.candidate_id
    return None


def emit_ci_result(store, integration_sha: str, result: str, private_key,
                   *, signer: str = "ci:mech:ci-runner", policy=None) -> Event:
    """Build, sign (via store.append) and append a ci_result Event bound to integration_sha.
    Returns the appended Event — store.append assigns the seq and the signature."""
    pol = policy or default_policy()
    cid = _find_candidate_id(store, integration_sha)
    ev = Event(
        id=(f"ci_result-ci-{cid}" if cid else f"ci_result-{integration_sha}"),
        seq=0,                                   # store.append assigns the real seq
        bus_id=CI_BUS,
        schema_version="threeway/1",
        kind="ci_result",
        sender="ci",
        recipient="all",
        signer=signer,                           # seat 'ci' -> verified against ci.pub
        payload={"result": result, "policy_digest": pol.policy_digest()},
        candidate_id=cid,
        subject_sha=integration_sha,
        brief_id="ci",
    )
    return store.append(ev, private_key)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sign + emit a ci_result event to the threeway bus.")
    ap.add_argument("--integration-sha", required=True, help="the exact integration commit SHA tested")
    ap.add_argument("--result", default="PASS", choices=["PASS", "FAIL"])
    ap.add_argument("--repo-dir", default=".", help="git repo holding refs/threeway/*")
    ap.add_argument("--remote", default=None,
                    help="authoritative bus remote for RefEventStore push-CAS (for CI runners)")
    args = ap.parse_args(argv)
    try:
        private_key = load_private("ci")
    except Exception as e:
        print(f"Error loading CI private key: {e}", file=sys.stderr)
        return 1
    store = RefEventStore(Path(args.repo_dir), remote=args.remote)
    ev = emit_ci_result(store, args.integration_sha, args.result, private_key)
    print(f"Signed + emitted ci_result ({args.result}) for {args.integration_sha} (seq {ev.seq}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
