#!/usr/bin/env python3
"""Read-only active mailbox monitor for the four-seat protocol.

This is a watchboard, not a coordination actor. It reads mailbox cursors,
sent events, and heartbeat files; it never consumes cursors, sends events,
claims work, edits inventory, or stages files.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


import protocol_mailbox

SEATS = protocol_mailbox.RECEIVING_SEATS
MODE = "read-only-no-consume"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVENT_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-"
    r"(?P<frm>director|director2|operator|operator2|coordinator)"
    r"-to-(?P<to>director|director2|operator|operator2|all)-"
    r"(?P<kind>[a-z0-9-]+)\.md$"
)


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts.strip(), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except (TypeError, ValueError):
        return None


def _dash_to_colon(ts_dash: str) -> str:
    return ts_dash[:11] + ts_dash[11:].replace("-", ":")


def _colon_to_dash(ts: str) -> str:
    return ts.replace(":", "-")


def _fmt_age(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    s = int(seconds)
    if s < 0:
        return "future?"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h{(s % 3600) // 60:02d}m"
    return f"{s // 86400}d{(s % 86400) // 3600:02d}h"


def _event_infos(sent_dir: Path) -> list[dict]:
    if not sent_dir.is_dir():
        return []
    infos = []
    for path in sorted(sent_dir.iterdir()):
        if not path.is_file():
            continue
        match = _EVENT_RE.match(path.name)
        if not match:
            continue
        info = match.groupdict()
        info["filename"] = path.name
        info["ts"] = _dash_to_colon(info["ts"])
        infos.append(info)
    return infos


def _read_cursor(root: Path, seat: str) -> str:
    try:
        return (root / "coordination/mailbox/seen" / f"{seat}.txt").read_text(
            encoding="utf-8"
        ).strip()
    except Exception as exc:
        return f"(unavailable: {exc})"


def _unread_events(events: list[dict], cursor: str, seat: str) -> list[dict]:
    cursor_dash = _colon_to_dash(cursor)
    if _parse_iso(cursor) is None:
        return []
    return [
        event
        for event in events
        if event["to"] in (seat, "all") and _colon_to_dash(event["ts"]) > cursor_dash
    ]


def _broadcast_receipt(cursor: str, latest_broadcast: dict | None) -> str:
    if latest_broadcast is None:
        return "no-broadcast"
    if _parse_iso(cursor) is None:
        return "unknown"
    return (
        "consumed"
        if _colon_to_dash(cursor) >= _colon_to_dash(latest_broadcast["ts"])
        else "unread"
    )


def _heartbeat(root: Path, seat: str, now_dt: datetime, stale_min: int) -> dict:
    path = root / "coordination/presence" / f"{seat}-heartbeat.ts"
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return {"state": "MISSING", "raw": "", "age": "unknown", "sha": None}
    except Exception as exc:
        return {
            "state": "UNAVAILABLE",
            "raw": "",
            "age": "unknown",
            "sha": None,
            "error": str(exc),
        }

    parts = raw.split()
    ts = _parse_iso(parts[0] if parts else "")
    if ts is None:
        return {"state": "UNPARSEABLE", "raw": raw, "age": "unknown", "sha": None}
    age_seconds = (now_dt - ts).total_seconds()
    state = "ONLINE" if age_seconds <= stale_min * 60 else "STALE"
    return {
        "state": state,
        "raw": raw,
        "age": _fmt_age(age_seconds),
        "sha": parts[1] if len(parts) > 1 else None,
    }


def _latest_coordinator_broadcast(events: list[dict]) -> dict | None:
    broadcasts = [
        event for event in events if event["frm"] == "coordinator" and event["to"] == "all"
    ]
    if not broadcasts:
        return None
    latest = broadcasts[-1]
    return {"filename": latest["filename"], "ts": latest["ts"], "kind": latest["kind"]}


def collect_monitor_state(
    repo_root: Path | str,
    *,
    now: str | None = None,
    stale_min: int = 15,
) -> dict:
    """Collect a read-only mailbox/presence snapshot."""
    root = Path(repo_root)
    now_dt = _parse_iso(now) if now else datetime.now(timezone.utc)
    if now_dt is None:
        raise ValueError(f"invalid --now timestamp: {now!r}")
    generated_at = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    events = _event_infos(root / "coordination/mailbox/sent")
    latest_broadcast = _latest_coordinator_broadcast(events)

    seats = {}
    for seat in SEATS:
        cursor = _read_cursor(root, seat)
        unread = _unread_events(events, cursor, seat)
        seats[seat] = {
            "cursor": cursor,
            "unread_count": len(unread),
            "latest_unread": unread[-1]["filename"] if unread else None,
            "broadcast_receipt": _broadcast_receipt(cursor, latest_broadcast),
            # Heartbeats are pair-seat only — coordinators have no presence
            # heartbeat by doctrine (matches draft_handoff._peer_heartbeats);
            # use an n/a sentinel so they are never heartbeat-attention flagged.
            "heartbeat": (
                _heartbeat(root, seat, now_dt, stale_min)
                if seat in protocol_mailbox.SEATS
                else {"state": "n/a", "raw": "", "age": "n/a", "sha": None}
            ),
        }

    receipt_summary = {"consumed": 0, "unread": 0, "unknown": 0}
    for seat_state in seats.values():
        receipt = seat_state["broadcast_receipt"]
        if receipt in ("consumed", "unread"):
            receipt_summary[receipt] += 1
        else:
            receipt_summary["unknown"] += 1

    alerts = []
    unread_seats = [
        f"{seat}={seat_state['unread_count']}"
        for seat, seat_state in seats.items()
        if seat_state["unread_count"]
    ]
    if unread_seats:
        alerts.append("unread mail present: " + ", ".join(unread_seats))
    if latest_broadcast is not None:
        pending = [
            seat
            for seat, seat_state in seats.items()
            if seat_state["broadcast_receipt"] == "unread"
        ]
        if pending:
            alerts.append(
                "coordinator broadcast has unconsumed seats: " + ", ".join(pending)
            )
    heartbeat_attention = [
        f"{seat}={seat_state['heartbeat']['state']}"
        for seat, seat_state in seats.items()
        if seat_state["heartbeat"]["state"] not in ("ONLINE", "n/a")
    ]
    if heartbeat_attention:
        alerts.append("heartbeat attention: " + ", ".join(heartbeat_attention))

    return {
        "generated_at": generated_at,
        "mode": MODE,
        "latest_coordinator_broadcast": latest_broadcast,
        "receipt_summary": receipt_summary,
        "seats": seats,
        "alerts": alerts,
    }


def render_snapshot(state: dict) -> str:
    """Render a human-readable monitor snapshot."""
    lines = [
        "# Mailbox Monitor",
        "mode: read-only; no cursor consumption; no mailbox send",
        f"generated_at: {state['generated_at']}",
    ]
    latest = state.get("latest_coordinator_broadcast")
    if latest:
        lines.append(
            "latest coordinator broadcast: "
            f"{latest['filename']} ({latest['ts']})"
        )
    else:
        lines.append("latest coordinator broadcast: (none)")

    summary = state["receipt_summary"]
    lines.append(
        "receipt split: "
        f"consumed={summary['consumed']} unread={summary['unread']} "
        f"unknown={summary['unknown']}"
    )
    lines.append("")
    lines.append("SEATS")
    for seat in SEATS:
        seat_state = state["seats"][seat]
        heartbeat = seat_state["heartbeat"]
        lines.append(
            f"{seat:<11}unread={seat_state['unread_count']} "
            f"latest={seat_state['latest_unread'] or '-'} "
            f"cursor={seat_state['cursor']} "
            f"receipt={seat_state['broadcast_receipt']} "
            f"heartbeat={heartbeat['state']} age={heartbeat['age']}"
        )

    lines.append("")
    if state["alerts"]:
        lines.append("ALERTS")
        lines.extend(f"- {alert}" for alert in state["alerts"])
    else:
        lines.append("ALERTS")
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _fingerprint(state: dict) -> dict:
    stable = copy.deepcopy(state)
    stable.pop("generated_at", None)
    for seat_state in stable["seats"].values():
        seat_state["heartbeat"].pop("age", None)
        seat_state["heartbeat"].pop("raw", None)
    return stable


def _emit(state: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(state, indent=2, sort_keys=True))
    else:
        print(render_snapshot(state), end="")
    sys.stdout.flush()


def repo_root() -> Path:
    return _REPO_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only active mailbox monitor for four-seat coordination.",
    )
    parser.add_argument("--root", default=str(repo_root()), help="repository root")
    parser.add_argument("--once", action="store_true", help="render one snapshot (default)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--watch", action="store_true", help="poll and print changes")
    parser.add_argument("--interval", type=float, default=5.0, help="watch poll seconds")
    parser.add_argument("--stale-min", type=int, default=15, help="heartbeat stale minutes")
    parser.add_argument("--iterations", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--now", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not args.watch:
        _emit(
            collect_monitor_state(root, now=args.now, stale_min=args.stale_min),
            args.json,
        )
        return 0

    last = None
    iterations = 0
    while True:
        state = collect_monitor_state(root, now=args.now, stale_min=args.stale_min)
        current = _fingerprint(state)
        if current != last:
            _emit(state, args.json)
            last = current
        iterations += 1
        if args.iterations is not None and iterations >= args.iterations:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
