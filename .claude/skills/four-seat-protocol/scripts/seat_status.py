#!/usr/bin/env python3
"""seat_status.py — one-shot session-start orientation for a campaign seat.

A seat normally re-derives "where am I" by hand every session: git log, a live
unread-mailbox recompute, each peer's heartbeat freshness, the wave gate. That
ritual is 4-7 separate commands and it's identical every time, so it belongs in
a script. This composes the EXISTING repo commands/state; it adds nothing under
coordination/bin or scripts/, and it is strictly READ-ONLY — it never stages,
commits, or advances a cursor (that distinction matters: the real
`consume-events` stages the cursor file; an orientation check must not).

    .venv/bin/python .claude/skills/four-seat-protocol/scripts/seat_status.py <seat> [opts]
      <seat>            director | director2 | operator | operator2 | coordinator | coordinator2
      --wave N          also report `scripts/wave_gate_check.py N`
      --commits N       recent commits to show (default 12)
      --stale-min M     heartbeat older than M minutes => STALE (default 15)
      --smoke           also run scripts/ci_smoke.py (heavy; off by default)

Exit status is always 0 on a successful render — this is an orientation read,
not a gate. Use `wave_gate_check.py` / `ci_smoke.py` directly when you need a
PASS/FAIL exit code to cite (R-EVIDENCE).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import bus_unread  # de-degrade: real ref-bus unread for migrated (scalar) cursors
import protocol_mailbox
from codex_protocol_model import CENTRAL_INVARIANT, MODEL_SOURCE

SEATS = protocol_mailbox.RECEIVING_SEATS


def run(cmd, cwd=None):
    """Run a command, returning (exit_code, stdout, stderr) — never raises."""
    try:
        p = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=120
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as exc:  # missing binary, timeout, etc.
        return 127, "", str(exc)


def repo_root():
    code, out, _ = run(["git", "rev-parse", "--show-toplevel"])
    return out if code == 0 and out else os.getcwd()


def _parse_cursor_ts(s: str) -> datetime | None:
    """Parse a colon-ISO cursor like 2026-06-14T16:19:09Z."""
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, AttributeError):
        return None


def _filename_ts_to_dt(fname: str) -> datetime | None:
    """The first 20 chars of an event filename are a dash-format timestamp:
    2026-06-14T16-19-09Z  ->  datetime. Mirrors consume-events' colon()."""
    head = fname[:20]
    if len(head) < 20 or head[10] != "T" or head[19] != "Z":
        return None
    date_part, time_part = head[0:10], head[11:19].replace("-", ":")
    return _parse_cursor_ts(f"{date_part}T{time_part}Z")


def _fmt_age(delta_seconds: float) -> str:
    s = int(delta_seconds)
    if s < 0:
        return "future?"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h{(s % 3600) // 60:02d}m"
    return f"{s // 86400}d{(s % 86400) // 3600:02d}h"


def section(title: str):
    print(f"\n── {title} " + "─" * max(2, 58 - len(title)))


def git_head(root: str):
    section("HEAD")
    _, head, _ = run(["git", "log", "-1", "--format=%h  %s"], cwd=root)
    _, branch, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    print(f"branch {branch}")
    print(head or "(no commits)")
    code, counts, _ = run(
        ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"],
        cwd=root,
    )
    if code == 0 and counts:
        behind, ahead = (counts.split() + ["?", "?"])[:2]
        print(f"vs origin/main: {ahead} ahead, {behind} behind")
    else:
        print("vs origin/main: (no upstream / offline)")


def git_log(root: str, n: int):
    section(f"recent commits (last {n})")
    _, out, _ = run(["git", "log", "--oneline", f"-{n}"], cwd=root)
    print(out or "(none)")


def mailbox(root: str, seat: str):
    section(f"mailbox — unread for '{seat}' (live recompute, read-only)")
    seen = os.path.join(root, "coordination", "mailbox", "seen", f"{seat}.txt")
    sent = os.path.join(root, "coordination", "mailbox", "sent")
    cursor_dt = None
    cursor_raw = "(missing)"
    if os.path.exists(seen):
        with open(seen) as fh:
            cursor_raw = fh.readline().strip()
        if bus_unread.is_migrated_cursor(cursor_raw):
            # Migrated (Slice-2.5) seat: real unread lives on the signed ref-bus, NOT the
            # legacy sent/*.md filename path (which returns 0 for a scalar cursor — a silent
            # under-report). Short-circuit BEFORE _parse_cursor_ts so the `cursor_dt is None`
            # "count everything" branch is never reached. None => a VISIBLE "(unavailable)"
            # sentinel, never a silent 0 (silent-gate-degradation). Mirrors scripts/status.py
            # collect_mailbox; the LIVE cursor is the ref (store.cursor_seq), not this scalar.
            print(f"cursor: {cursor_raw}")
            n = bus_unread.bus_unread_count(root, seat)
            if n is None:
                print("UNREAD: (unavailable: ref-bus)")
            else:
                print(f"UNREAD: {n} / ref-bus")
                if n:
                    print("→ Rule #8: surface this count in your FIRST user-facing turn; "
                          "consume via scripts/consume_bus.py " + seat)
            return
        cursor_dt = _parse_cursor_ts(cursor_raw)
    print(f"cursor: {cursor_raw}")
    if not os.path.isdir(sent):
        print("no sent/ dir — 0 unread")
        return
    addressed = sorted(
        f
        for f in os.listdir(sent)
        if f.endswith(".md")
        and (f"-to-{seat}-" in f or "-to-all-" in f)
    )
    unread = []
    for f in addressed:
        ts = _filename_ts_to_dt(f)
        if ts is None:
            continue
        if cursor_dt is None or ts > cursor_dt:
            unread.append(f)
    print(f"UNREAD: {len(unread)}")
    for f in unread[-12:]:  # newest tail, cap the print
        print(f"  • {f}")
    if len(unread) > 12:
        print(f"  … and {len(unread) - 12} older")
    if unread:
        print("→ Rule #8: surface this count in your FIRST user-facing turn; "
              "consume via coordination/bin/consume-events " + seat)


def heartbeats(root: str, me: str, stale_min: int):
    section(f"peer heartbeats (STALE > {stale_min}m)")
    now = datetime.now(timezone.utc)
    pres = os.path.join(root, "coordination", "presence")
    # heartbeats are pair-seat only — coordinators have no presence heartbeat
    for seat in protocol_mailbox.SEATS:
        if seat == me:
            continue
        hb = os.path.join(pres, f"{seat}-heartbeat.ts")
        if not os.path.exists(hb):
            print(f"  {seat:10s} (no heartbeat file)")
            continue
        with open(hb) as fh:
            raw = fh.readline().strip()
        ts_str = raw.split()[0] if raw else ""
        sha = raw.split()[1] if len(raw.split()) > 1 else "?"
        ts = _parse_cursor_ts(ts_str)
        if ts is None:
            print(f"  {seat:10s} (unparseable: {raw!r})")
            continue
        age = (now - ts).total_seconds()
        flag = "ONLINE" if age <= stale_min * 60 else "STALE"
        print(f"  {seat:10s} {flag:6s} last {_fmt_age(age)} ago "
              f"@ {ts_str} ({sha})")


def wave_gate(root: str, wave: str):
    section(f"wave gate — wave {wave}")
    py = os.path.join(root, ".venv", "bin", "python")
    py = py if os.path.exists(py) else sys.executable
    code, out, err = run(
        [py, "scripts/wave_gate_check.py", str(wave)], cwd=root
    )
    if out:
        print(out)
    if err:
        print(err)
    print(f"→ exit {code} ({'MET' if code == 0 else 'UNMET'})")


def smoke(root: str):
    section("§15 smoke (scripts/ci_smoke.py)")
    py = os.path.join(root, ".venv", "bin", "python")
    py = py if os.path.exists(py) else sys.executable
    code, out, err = run([py, "scripts/ci_smoke.py"], cwd=root)
    tail = (out or err).splitlines()[-6:]
    print("\n".join(tail) if tail else "(no output)")
    print(f"→ exit {code} ({'clean' if code == 0 else 'FAILED — stop, fix first'})")


def main(argv=None):
    ap = argparse.ArgumentParser(description="One-shot seat session-start status.")
    ap.add_argument("seat", choices=SEATS)
    ap.add_argument("--wave", default=None)
    ap.add_argument("--commits", type=int, default=12)
    ap.add_argument("--stale-min", type=int, default=15)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    root = repo_root()
    print(f"SEAT STATUS — {args.seat}   (read-only; nothing staged/committed)")
    print(f"repo: {root}")
    git_head(root)
    git_log(root, args.commits)
    mailbox(root, args.seat)
    heartbeats(root, args.seat, args.stale_min)
    if args.wave is not None:
        wave_gate(root, args.wave)
    if args.smoke:
        smoke(root)
    else:
        section("reminders")
        print("smoke NOT run (--smoke to include). R-START still requires a "
              "clean ci_smoke before non-trivial work.")
        print(f"harness model: {MODEL_SOURCE}; {CENTRAL_INVARIANT}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
