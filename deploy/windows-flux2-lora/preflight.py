#!/usr/bin/env python3
"""Offline static preflight for the FLUX.2 Klein LoRA candidate."""

from __future__ import annotations

import json
import sys

sys.dont_write_bytecode = True

from contract import ContractError, ROOT, validate_package


def main() -> int:
    try:
        candidate = validate_package(ROOT)
    except ContractError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(
        json.dumps(
            {
                "capability": candidate["capability"],
                "state": candidate["readiness"]["state"],
                "execution_proven": False,
                "training_canary": "not_run",
                "inference_canary": "not_run",
                "status": "static_preflight_passed",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
