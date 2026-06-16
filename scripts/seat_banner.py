#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

from codex_protocol_model import render_seat_contract


REQUIRED = ("objective", "permissions", "scope", "verify", "done")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the Codex seat contract.")
    parser.add_argument("--objective", default="")
    parser.add_argument("--permissions", default="")
    parser.add_argument("--scope", default="")
    parser.add_argument("--verify", default="")
    parser.add_argument("--done", default="")
    parser.add_argument("--require-complete", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    missing = [name for name in REQUIRED if not getattr(args, name).strip()]
    if args.require_complete and missing:
        print("missing contract fields: " + ", ".join(missing), file=sys.stderr)
        return 2
    print(
        render_seat_contract(
            os.environ,
            objective=args.objective or "(unset)",
            permissions=args.permissions or "(unset)",
            scope=args.scope or "(unset)",
            verification=args.verify or "(unset)",
            done=args.done or "(unset)",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
