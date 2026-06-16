#!/usr/bin/env python3
"""Read-only continuation readiness bridge for the four-seat agent process.

This command is for non-seat bridge sessions: it replays the safe orientation
checks without consuming mailbox cursors, sending events, editing inventory, or
claiming director/operator work.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from codex_protocol_model import (
    DURABLE_STATE_ARTIFACTS,
    MODEL_SOURCE,
    render_agent_extension_summary,
    render_runtime_env_contract,
    render_seat_subagent_development,
    render_start_session_inhabitance,
    render_surface_summary,
)
from status import collect_mailbox

SEATS = ("director", "director2", "operator", "operator2")


def run(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    """Run a command and return (exit code, stdout, stderr), never raising."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def repo_root() -> Path:
    code, out, _ = run(["git", "rev-parse", "--show-toplevel"], Path.cwd())
    if code == 0 and out:
        return Path(out)
    return Path.cwd()


def section(title: str) -> None:
    print(f"\n## {title}")


def _trim(text: str, lines: int = 8) -> str:
    split = text.splitlines()
    if len(split) <= lines:
        return text
    return "\n".join(split[: lines - 1] + [f"... ({len(split) - lines + 1} more lines)"])


def render_git(root: Path, commits: int) -> None:
    section("Git")
    _, head, _ = run(["git", "log", "-1", "--format=%h %s"], root)
    code, counts, err = run(
        ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"],
        root,
    )
    print(f"head: {head or '(unknown)'}")
    if code == 0 and counts:
        behind, ahead = (counts.split() + ["?", "?"])[:2]
        print(f"origin/main: {ahead} ahead / {behind} behind")
    else:
        print(f"origin/main: unavailable ({err or 'no upstream'})")
    _, log, _ = run(["git", "log", "--oneline", f"-{commits}"], root)
    print("recent:")
    print(_trim(log or "(none)", lines=commits))


def render_mailbox(root: Path) -> None:
    section("Mailbox")
    data = collect_mailbox(root)
    print("mode: read-only; cursors are not consumed")
    for seat in SEATS:
        print(
            f"{seat:<9} unread={data.get(f'mailbox_{seat}_unread', '(missing)')} "
            f"cursor={data.get(f'mailbox_{seat}_cursor', '(missing)')}"
        )
    print("if acting as a seat, surface unread count first, then use consume-events intentionally")


def render_wave(root: Path, wave: int) -> None:
    section(f"Wave {wave}")
    code, out, err = run([sys.executable, "scripts/wave_gate_check.py", str(wave)], root)
    print(out or err or "(no output)")
    print(f"wave_gate_check exit: {code} ({'MET' if code == 0 else 'UNMET'})")
    print("note: per ADR-027, this is process state; correctness still requires executed evidence")


def render_ceremony(root: Path) -> None:
    section("Ceremony")
    code, out, err = run([sys.executable, "scripts/check_no_ceremony.py"], root)
    print(_trim(out or err or "(no output)", lines=12))
    print(f"check_no_ceremony exit: {code}")


def render_environment(root: Path, smoke: bool) -> None:
    section("Environment")
    venv_python = root / ".venv" / "bin" / "python"
    if venv_python.exists():
        py = str(venv_python)
        print(f"venv: present ({py})")
    else:
        py = sys.executable
        print("venv: MISSING (.venv/bin/python not found)")
        print(f"fallback python: {py}")
    if not smoke:
        print("smoke: not run; pass --smoke to execute scripts/ci_smoke.py")
        return
    code, out, err = run([py, "scripts/ci_smoke.py"], root, timeout=180)
    print(_trim(out or err or "(no output)", lines=12))
    print(f"ci_smoke exit: {code}")


def render_codex(root: Path) -> None:
    section("Codex Harness Model")
    skill = root / ".agents" / "skills" / "four-seat-protocol" / "SKILL.md"
    hooks = root / ".codex" / "hooks.json"
    agents_dir = root / ".codex" / "agents"
    agents = sorted(p.name for p in agents_dir.glob("*.toml")) if agents_dir.exists() else []

    print(_trim(render_surface_summary(), lines=8))
    print("durable state: " + ", ".join(DURABLE_STATE_ARTIFACTS))
    print(render_agent_extension_summary(agents))
    print(render_seat_subagent_development())
    print(render_start_session_inhabitance(agents))
    print(render_runtime_env_contract(os.environ))
    print(f"skill: {'present' if skill.exists() else 'missing'} ({skill})")
    print(f"hooks: {'present' if hooks.exists() else 'missing'} ({hooks})")
    print(f"custom agents: {', '.join(agents) if agents else '(none)'}")
    print("bridge command: .venv/bin/python scripts/continuation_readiness.py --smoke")
    print("mailbox monitor: .venv/bin/python scripts/mailbox_monitor.py --once")
    print("handoff draft: .venv/bin/python scripts/draft_handoff.py <seat> --wave 2 --output")
    print(
        "seat command: .venv/bin/python "
        ".agents/skills/four-seat-protocol/scripts/seat_status.py <seat> --wave 2"
    )
    print(
        "seat env: CODEX_SEAT=<seat> plus per-seat GIT_INDEX_FILE; "
        "CODEX_SEAT=coordinator is a compatibility launch for coordinator mode"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the read-only continuation readiness bridge report.",
    )
    parser.add_argument("--wave", type=int, default=2)
    parser.add_argument("--commits", type=int, default=5)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument(
        "--skip-ceremony",
        action="store_true",
        help="Skip scripts/check_no_ceremony.py in the report.",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    print("# Continuation Readiness Bridge")
    print(f"repo: {root}")
    print("role: readiness bridge; no seat claim, cursor consumption, mailbox send, or inventory edit")
    render_codex(root)
    render_git(root, args.commits)
    render_mailbox(root)
    render_wave(root, args.wave)
    if not args.skip_ceremony:
        render_ceremony(root)
    render_environment(root, args.smoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
