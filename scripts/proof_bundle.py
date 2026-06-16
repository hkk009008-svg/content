#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

from mailbox_monitor import collect_monitor_state, render_snapshot


SEAT_STATUS = ".agents/skills/four-seat-protocol/scripts/seat_status.py"
SEATS = ("director", "director2", "operator", "operator2", "coordinator")
_REPO_ROOT = Path(__file__).resolve().parent.parent


def build_commands(root: Path, *, seat: str, wave: int, smoke: bool) -> list[list[str]]:
    py = str(root / ".venv" / "bin" / "python")
    commands = [
        [py, str(root / SEAT_STATUS), seat, "--wave", str(wave)],
        ["env", "-u", "GIT_INDEX_FILE", "git", "log", "--oneline", "-5"],
        [
            "env",
            "-u",
            "GIT_INDEX_FILE",
            py,
            str(root / "scripts/wave_gate_check.py"),
            str(wave),
        ],
    ]
    if smoke:
        commands.append(
            ["env", "-u", "GIT_INDEX_FILE", py, str(root / "scripts/ci_smoke.py")]
        )
    return commands


def collect_mailbox_bodies(
    root: Path, filenames: list[str], *, limit: int
) -> list[tuple[str, str]]:
    sent = root / "coordination" / "mailbox" / "sent"
    bodies = []
    for name in filenames[:limit]:
        if Path(name).name != name:
            raise ValueError(f"mailbox filename must be a basename: {name!r}")
        path = sent / name
        bodies.append((name, path.read_text(encoding="utf-8")))
    return bodies


def run_command(command: list[str], root: Path) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout + proc.stderr


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a read-only proof bundle for Codex protocol decisions."
    )
    parser.add_argument("--root", default=str(_REPO_ROOT), help="repository root")
    parser.add_argument("--seat", choices=SEATS, required=True)
    parser.add_argument("--wave", type=int, default=2)
    parser.add_argument("--smoke", action="store_true", help="include ci_smoke.py")
    parser.add_argument(
        "--mailbox",
        action="append",
        default=[],
        help="mailbox sent-event filename to include; repeat for multiple files",
    )
    parser.add_argument("--mailbox-limit", type=int, default=5)
    parser.add_argument("--stale-min", type=int, default=15)
    parser.add_argument("--now", default=None, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)

    print("# Proof Bundle")
    print("mode: read-only; no cursor consumption; no mailbox send")
    print(f"root: {root}")
    print(f"seat: {args.seat}")
    print(f"wave: {args.wave}")
    print("")

    first_failure = 0
    print("## Commands")
    for command in build_commands(root, seat=args.seat, wave=args.wave, smoke=args.smoke):
        print(f"$ {shlex.join(command)}")
        returncode, output = run_command(command, root)
        print(f"exit: {returncode}")
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
        else:
            print("(no output)")
        print("")
        if returncode and not first_failure:
            first_failure = returncode

    print("## Mailbox Monitor")
    state = collect_monitor_state(root, now=args.now, stale_min=args.stale_min)
    print(render_snapshot(state), end="")

    print("## Mailbox Bodies")
    bodies = collect_mailbox_bodies(
        root, list(args.mailbox), limit=max(args.mailbox_limit, 0)
    )
    if not bodies:
        print("(none requested)")
    for name, body in bodies:
        print(f"### {name}")
        print(body, end="" if body.endswith("\n") else "\n")

    return first_failure


if __name__ == "__main__":
    raise SystemExit(main())
