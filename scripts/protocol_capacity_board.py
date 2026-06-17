#!/usr/bin/env python3
"""Render or validate the four-seat protocol capacity board."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import protocol_capacity


_REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a read-only hard-gated protocol capacity board.",
    )
    parser.add_argument("--root", default=str(_REPO_ROOT), help=argparse.SUPPRESS)
    parser.add_argument("--wave", type=int, required=True)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--validate-route",
        default=None,
        help="coordinator task-board mailbox event to validate",
    )
    parser.add_argument(
        "--require-packets",
        action="store_true",
        help="exit nonzero when a wave has no capacity packets",
    )
    args = parser.parse_args(argv)

    if args.validate_route:
        result = protocol_capacity.validate_route(
            Path(args.root),
            args.wave,
            Path(args.validate_route),
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print(protocol_capacity.render_route_validation(result), end="")
        return 0 if result.valid else 1

    report = protocol_capacity.collect_capacity_report(Path(args.root), args.wave)
    if args.require_packets:
        report = protocol_capacity.require_packets(report)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(protocol_capacity.render_capacity_board(report), end="")
    return 0 if not report.blocking_issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
