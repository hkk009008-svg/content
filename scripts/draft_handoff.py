#!/usr/bin/env python3
"""Draft a read-only handoff from live protocol evidence.

The output is intentionally a draft: it automates evidence capture and a
reviewable Markdown scaffold, but it does not consume mailbox cursors, send
mailbox events, edit inventory, or decide that a seat is done.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from status import collect_mailbox

SEATS = ("director", "director2", "operator", "operator2", "coordinator")


@dataclass(frozen=True)
class HandoffContext:
    repo: Path
    seat: str
    wave: int
    generated_at: str
    head: str
    branch: str
    origin_relation: str
    recent_commits: str
    mailbox_cursor: str
    mailbox_unread: str
    mailbox_events: list[str]
    coordinator_events: list[str]
    peer_heartbeats: list[str]
    staged_scope: str
    unstaged_scope: str
    locks: str
    product_oracle: str
    wave_gate: str
    smoke: str


def run(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    """Run a command with the shared git index, returning output without raising."""
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except Exception as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def repo_root() -> Path:
    code, out, _ = run(["git", "rev-parse", "--show-toplevel"], Path.cwd())
    if code == 0 and out:
        return Path(out)
    return Path.cwd()


def now_local() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _normalize_cursor(cursor: str) -> str:
    return cursor.replace(":", "-")


def _event_ts(name: str) -> str:
    return name[:20] if len(name) >= 20 else ""


def _is_addressed(name: str, seat: str) -> bool:
    if seat == "coordinator":
        return "-to-coordinator-" in name or "-to-all-" in name
    return f"-to-{seat}-" in name or "-to-all-" in name


def _mailbox_events(root: Path, seat: str, cursor: str = "", limit: int = 12) -> list[str]:
    sent = root / "coordination" / "mailbox" / "sent"
    if not sent.exists():
        return []
    names = sorted(p.name for p in sent.glob("*.md") if _is_addressed(p.name, seat))
    if seat != "coordinator" and cursor and not cursor.startswith("("):
        cursor_norm = _normalize_cursor(cursor)
        names = [name for name in names if _event_ts(name) > cursor_norm]
    return names[-limit:]


def _coordinator_events(root: Path, limit: int = 8) -> list[str]:
    sent = root / "coordination" / "mailbox" / "sent"
    if not sent.exists():
        return []
    names = sorted(
        p.name
        for p in sent.glob("*.md")
        if "-coordinator-to-" in p.name
    )
    return names[-limit:]


def _peer_heartbeats(root: Path, seat: str) -> list[str]:
    presence = root / "coordination" / "presence"
    if not presence.exists():
        return ["(presence directory missing)"]
    peers = []
    for peer in ("director", "director2", "operator", "operator2"):
        if peer == seat:
            continue
        path = presence / f"{peer}-heartbeat.ts"
        if path.exists():
            raw = path.read_text(encoding="utf-8").strip()
            peers.append(f"{peer}: {raw or '(empty heartbeat)'}")
        else:
            peers.append(f"{peer}: (missing heartbeat)")
    return peers


def _path_listing(root: Path, rel: str, pattern: str = "*") -> str:
    base = root / rel
    if not base.exists():
        return "(missing)"
    names = sorted(str(path.relative_to(root)) for path in base.glob(pattern) if path.is_file())
    return "\n".join(names) if names else "(none)"


def collect_context(root: Path, seat: str, wave: int, smoke: bool = False) -> HandoffContext:
    mailbox = collect_mailbox(root)
    if seat == "coordinator":
        cursor = "(not used; coordinator is unpinned)"
        events = _mailbox_events(root, seat)
        unread = f"all-scope {len(events)} shown"
    else:
        cursor = str(mailbox.get(f"mailbox_{seat}_cursor", "(missing)"))
        unread = str(mailbox.get(f"mailbox_{seat}_unread", "(missing)"))
        events = _mailbox_events(root, seat, cursor)

    _, head, _ = run(["git", "log", "-1", "--format=%h %s"], root)
    _, branch, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    code, counts, err = run(["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"], root)
    if code == 0 and counts:
        behind, ahead = (counts.split() + ["?", "?"])[:2]
        origin_relation = f"{ahead} ahead, {behind} behind"
    else:
        origin_relation = f"unavailable ({err or 'no upstream'})"
    _, recent, _ = run(["git", "log", "--oneline", "-5"], root)
    _, staged, _ = run(["git", "diff", "--cached", "--name-status"], root)
    _, status, _ = run(["git", "status", "--short"], root)

    py = str(root / ".venv" / "bin" / "python")
    if not Path(py).exists():
        py = sys.executable
    _, wave_out, wave_err = run([py, "scripts/wave_gate_check.py", str(wave)], root)
    if smoke:
        _, smoke_out, smoke_err = run([py, "scripts/ci_smoke.py"], root, timeout=180)
        smoke_text = smoke_out or smoke_err or "(no output)"
    else:
        smoke_text = "not run; pass --smoke to include scripts/ci_smoke.py"

    return HandoffContext(
        repo=root,
        seat=seat,
        wave=wave,
        generated_at=now_local(),
        head=head or "(unknown)",
        branch=branch or "(unknown)",
        origin_relation=origin_relation,
        recent_commits=recent or "(none)",
        mailbox_cursor=cursor,
        mailbox_unread=unread,
        mailbox_events=events,
        coordinator_events=_coordinator_events(root),
        peer_heartbeats=_peer_heartbeats(root, seat),
        staged_scope=staged or "(none)",
        unstaged_scope=status or "(none)",
        locks=_path_listing(root, "coordination/locks"),
        product_oracle=_path_listing(root, "logs", "product-oracle-*.json"),
        wave_gate=wave_out or wave_err or "(no output)",
        smoke=smoke_text,
    )


def _bullet(items: list[str]) -> str:
    if not items:
        return "- (none)"
    return "\n".join(f"- `{item}`" for item in items)


def _fence(text: str) -> str:
    return f"```text\n{text}\n```"


def render_handoff(ctx: HandoffContext) -> str:
    seat_command = (
        ".venv/bin/python .agents/skills/four-seat-protocol/scripts/"
        f"seat_status.py {ctx.seat} --wave {ctx.wave}"
    )
    if ctx.seat == "coordinator":
        first_prompt = "continue as coordinator"
    else:
        first_prompt = f"continue as {ctx.seat}"

    return f"""# HANDOFF DRAFT - {ctx.seat}

This is an automated evidence draft, not a final authority decision. It is
designed to speed up handoff writing while keeping the seat responsible for
reviewing scope, ownership, and next action.

Generated: `{ctx.generated_at}`
Repo: `{ctx.repo}`

## Snapshot, Not Truth

Trust order for the next session: user instruction, current git/filesystem,
mailbox bodies, then this handoff draft. Refresh live state before acting.
Do not consume mailbox cursors from this draft tool, and do not treat receipt
evidence as proof that assigned work is complete.

## Refresh Live State First

{_fence(seat_command + chr(10) + "env -u GIT_INDEX_FILE git log --oneline -5")}

For coordinator work, also read recent `coordination/mailbox/sent/` bodies before
routing or reconciling. For live-seat work, surface the unread count before
processing mail and consume cursors only as an intentional mutation.

## Git

- branch: `{ctx.branch}`
- HEAD: `{ctx.head}`
- origin/main: `{ctx.origin_relation}`

{_fence(ctx.recent_commits)}

## Mailbox

- seat cursor: `{ctx.mailbox_cursor}`
- seat unread: `{ctx.mailbox_unread}`

Relevant seat mail:

{_bullet(ctx.mailbox_events)}

Recent coordinator/all mail:

{_bullet(ctx.coordinator_events)}

## Peer Heartbeats

{_bullet(ctx.peer_heartbeats)}

## Working Tree Scope

Staged scope:

{_fence(ctx.staged_scope)}

Status scope:

{_fence(ctx.unstaged_scope)}

Human Review Required: confirm this scope is owned by `{ctx.seat}` before
staging, committing, routing, or deleting anything. Preserve unrelated seat WIP.

## Gate, Locks, And Artifacts

Wave {ctx.wave} gate:

{_fence(ctx.wave_gate)}

Smoke:

{_fence(ctx.smoke)}

Locks:

{_fence(ctx.locks)}

Product-oracle artifacts:

{_fence(ctx.product_oracle)}

## Next-Seat Notes To Fill In

- Current owned task:
- Files the next seat may edit:
- Files or staged work the next seat must preserve:
- Verification already run:
- Verification still owed:
- Lock, push, pod-spend, and paid-API status:
- Exact next action:

## Clean Focused Session Transplant

Open the clean session with:

{_fence(first_prompt)}

Then say:

{_fence("Read this handoff as a snapshot, refresh live mailbox and git state before acting, preserve unrelated WIP, and follow the role boundary for this seat.")}
"""


def write_output(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def default_output_path(root: Path, seat: str) -> Path:
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d")
    return root / "docs" / f"HANDOFF-{seat}-{stamp}-automated-draft.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft a read-only protocol handoff.")
    parser.add_argument("seat", choices=SEATS)
    parser.add_argument("--wave", type=int, default=2)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument(
        "--output",
        nargs="?",
        const="auto",
        help="Write Markdown to path, or use an automatic docs/HANDOFF-* path.",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    text = render_handoff(collect_context(root, args.seat, args.wave, args.smoke))
    if args.output:
        output = default_output_path(root, args.seat) if args.output == "auto" else Path(args.output)
        if not output.is_absolute():
            output = root / output
        write_output(output, text)
        print(output)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
