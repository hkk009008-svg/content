#!/usr/bin/env python3
"""Read-only preflight for a future threeway authority cutover."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from threeway import cursor_backfill, gitcas, legacy_projector
from threeway.divergence import diverge
from threeway.refstore import EVENTS_REF


def _mailbox_base(coord_root: Path) -> Path:
    return cursor_backfill._mailbox_base(coord_root)


def _threeway_refs(repo: Path) -> list[str]:
    refs: list[str] = []
    for ref in (EVENTS_REF,):
        oid = gitcas.rev_parse(repo, ref)
        if oid:
            refs.append(ref)
    return refs


def build_report(repo: Path, coord_root: Path) -> dict:
    mailbox = _mailbox_base(coord_root)
    sent = mailbox / "sent"
    seen = mailbox / "seen"
    if not sent.exists() or not seen.exists():
        return {
            "mode": "ready-not-live",
            "cutover_execute_allowed": False,
            "ready_to_flip": False,
            "projected_events": 0,
            "divergence_ok": False,
            "drifts": [f"missing legacy mailbox paths: sent={sent.exists()} seen={seen.exists()}"],
            "threeway_refs_present": _threeway_refs(repo),
            "events_ref": EVENTS_REF,
        }
    projected = legacy_projector.project(sent)
    divergence = diverge(projected, sent, seen)
    refs = _threeway_refs(repo)
    ready_to_flip = bool(projected) and divergence.ok and not refs
    return {
        "mode": "ready-not-live",
        "cutover_execute_allowed": False,
        "ready_to_flip": ready_to_flip,
        "projected_events": len(projected),
        "divergence_ok": divergence.ok,
        "drifts": divergence.drifts,
        "threeway_refs_present": refs,
        "events_ref": EVENTS_REF,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--coord-root", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_report(args.repo, args.coord_root)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        status = "OK" if report["ready_to_flip"] else "BLOCKED"
        print(f"threeway cutover check: {status}; execute_allowed=false")
        for drift in report["drifts"]:
            print(f"- {drift}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
