#!/usr/bin/env python3
"""Build and sign a dry-run threeway ci_result event artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from threeway.envelope import Event, sign_event, to_json_obj
from threeway.keys import load_private


def _die(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keystore", required=True, type=Path)
    parser.add_argument("--bus-id", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--integration-sha", required=True)
    parser.add_argument("--policy-digest", required=True)
    parser.add_argument("--result", required=True, choices=("PASS", "FAIL"))
    parser.add_argument("--evidence-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--event-id")
    args = parser.parse_args(argv)

    try:
        if len(args.integration_sha) != 40:
            raise ValueError("--integration-sha must be a 40-character commit sha")
        if not args.evidence_manifest.exists():
            raise FileNotFoundError(f"missing evidence manifest: {args.evidence_manifest}")
        os.environ["THREEWAY_KEYSTORE"] = str(args.keystore)
        private_key = load_private("ci")
        evidence_digest = _sha256_file(args.evidence_manifest)
        event = Event(
            id=args.event_id or f"ci-{args.candidate_id.replace(':', '-')}-{args.integration_sha[:12]}",
            seq=0,
            bus_id=args.bus_id,
            schema_version="threeway/1",
            kind="ci_result",
            sender="ci",
            recipient="merge-gate",
            signer="ci:codex:dry-run",
            payload={
                "candidate_id": args.candidate_id,
                "integration_sha": args.integration_sha,
                "policy_digest": args.policy_digest,
                "result": args.result,
                "evidence_manifest": str(args.evidence_manifest),
                "evidence_manifest_digest": evidence_digest,
            },
            candidate_id=args.candidate_id,
            subject_sha=args.integration_sha,
        )
        sign_event(event, private_key)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(to_json_obj(event), indent=2, sort_keys=True) + "\n")
        print(str(args.output))
        return 0
    except Exception as exc:
        return _die(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
