#!/usr/bin/env python3
"""Strict read-only protocol validation bundle."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CommandResult:
    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str


def run_command(cmd: list[str], cwd: Path, timeout: int = 120) -> CommandResult:
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return CommandResult(
        cmd=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _python() -> str:
    return sys.executable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run strict read-only protocol checks.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--wave", type=int, required=True)
    parser.add_argument("--route", default=None)
    args = parser.parse_args(argv)

    root = Path(args.root)
    py = _python()
    commands = [
        [py, "scripts/check_coordination.py"],
        [py, "scripts/protocol_capacity_board.py", "--wave", str(args.wave)],
    ]
    if args.route:
        commands.append(
            [
                py,
                "scripts/protocol_capacity_board.py",
                "--wave",
                str(args.wave),
                "--require-packets",
            ]
        )
        commands.append(
            [
                py,
                "scripts/protocol_capacity_board.py",
                "--wave",
                str(args.wave),
                "--validate-route",
                args.route,
            ]
        )
    commands.extend(
        [
            [
                py,
                "-m",
                "pytest",
                "tests/unit/test_codex_protocol_model.py",
                "tests/unit/test_codex_protocol_artifacts.py",
                "tests/unit/test_protocol_capacity_board.py",
                "tests/unit/test_coordination_bin.py",
                "tests/unit/test_check_coordination.py",
                "-q",
            ],
            [py, "scripts/ci_smoke.py"],
        ]
    )

    for cmd in commands:
        result = run_command(cmd, root)
        print("$ " + " ".join(cmd))
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode != 0:
            print("PROTOCOL DOCTOR: FAIL")
            return result.returncode
    print("PROTOCOL DOCTOR: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
