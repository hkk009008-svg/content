"""Tests for scripts/mailbox_monitor.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import mailbox_monitor as monitor  # noqa: E402


NOW = "2026-06-16T04:30:00Z"


def _repo(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "coordination/mailbox/sent").mkdir(parents=True)
    (root / "coordination/mailbox/seen").mkdir(parents=True)
    (root / "coordination/presence").mkdir(parents=True)
    for seat in monitor.SEATS:
        (root / "coordination/mailbox/seen" / f"{seat}.txt").write_text(
            "2026-06-16T04:00:00Z\n",
            encoding="utf-8",
        )
    return root


def _event(root: Path, name: str, body: str = "# event\n") -> None:
    (root / "coordination/mailbox/sent" / name).write_text(body, encoding="utf-8")


def _cursor(root: Path, seat: str, ts: str) -> None:
    (root / "coordination/mailbox/seen" / f"{seat}.txt").write_text(
        f"{ts}\n",
        encoding="utf-8",
    )


def _heartbeat(root: Path, seat: str, line: str) -> None:
    (root / "coordination/presence" / f"{seat}-heartbeat.ts").write_text(
        f"{line}\n",
        encoding="utf-8",
    )


def test_snapshot_reports_unread_latest_event_and_preserves_cursors(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _event(root, "2026-06-16T04-05-00Z-coordinator-to-all-coordination.md")
    _event(root, "2026-06-16T04-10-00Z-operator-to-director-status.md")
    _event(root, "2026-06-16T04-12-00Z-director2-to-all-status.md")
    before = (root / "coordination/mailbox/seen/director.txt").read_text(
        encoding="utf-8"
    )

    state = monitor.collect_monitor_state(root, now=NOW)

    director = state["seats"]["director"]
    assert director["unread_count"] == 3
    assert director["latest_unread"] == "2026-06-16T04-12-00Z-director2-to-all-status.md"
    assert director["broadcast_receipt"] == "unread"
    after = (root / "coordination/mailbox/seen/director.txt").read_text(
        encoding="utf-8"
    )
    assert after == before
    assert not (root / "coordination/mailbox/seen/coordinator.txt").exists()


def test_latest_coordinator_broadcast_receipt_split_is_cursor_based(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _event(root, "2026-06-16T04-01-00Z-coordinator-to-all-coordination.md")
    _event(root, "2026-06-16T04-05-00Z-coordinator-to-all-coordination.md")
    _cursor(root, "director", "2026-06-16T04:06:00Z")
    _cursor(root, "operator", "2026-06-16T04:05:00Z")
    _cursor(root, "director2", "2026-06-16T04:04:59Z")
    _cursor(root, "operator2", "2026-06-16T03:59:00Z")

    state = monitor.collect_monitor_state(root, now=NOW)

    assert (
        state["latest_coordinator_broadcast"]["filename"]
        == "2026-06-16T04-05-00Z-coordinator-to-all-coordination.md"
    )
    assert state["seats"]["director"]["broadcast_receipt"] == "consumed"
    assert state["seats"]["operator"]["broadcast_receipt"] == "consumed"
    assert state["seats"]["director2"]["broadcast_receipt"] == "unread"
    assert state["seats"]["operator2"]["broadcast_receipt"] == "unread"
    assert state["receipt_summary"] == {"consumed": 2, "unread": 2, "unknown": 0}


def test_heartbeat_freshness_is_reported_without_affecting_receipt(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _heartbeat(root, "director", "2026-06-16T04:20:00Z abc1234")
    _heartbeat(root, "operator", "2026-06-16T04:00:00Z def5678")
    _heartbeat(root, "operator2", "not-a-timestamp")

    state = monitor.collect_monitor_state(root, now=NOW, stale_min=15)

    assert state["seats"]["director"]["heartbeat"]["state"] == "ONLINE"
    assert state["seats"]["director"]["heartbeat"]["age"] == "10m"
    assert state["seats"]["operator"]["heartbeat"]["state"] == "STALE"
    assert state["seats"]["director2"]["heartbeat"]["state"] == "MISSING"
    assert state["seats"]["operator2"]["heartbeat"]["state"] == "UNPARSEABLE"


def test_render_snapshot_surfaces_read_only_mode_and_active_alerts(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _event(root, "2026-06-16T04-05-00Z-coordinator-to-all-coordination.md")
    _heartbeat(root, "director", "2026-06-16T04:00:00Z abc1234")

    state = monitor.collect_monitor_state(root, now=NOW, stale_min=15)
    rendered = monitor.render_snapshot(state)

    assert "mode: read-only; no cursor consumption; no mailbox send" in rendered
    assert "latest coordinator broadcast: 2026-06-16T04-05-00Z-coordinator-to-all-coordination.md" in rendered
    assert "receipt split: consumed=0 unread=4 unknown=0" in rendered
    assert "director   unread=1" in rendered
    assert "heartbeat=STALE" in rendered
    assert "ALERTS" in rendered
    assert "coordinator broadcast has unconsumed seats" in rendered


def test_main_json_outputs_machine_readable_snapshot(tmp_path: Path, capsys) -> None:
    root = _repo(tmp_path)
    _event(root, "2026-06-16T04-05-00Z-coordinator-to-all-coordination.md")

    rc = monitor.main(["--root", str(root), "--json", "--now", NOW])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "read-only-no-consume"
    assert payload["seats"]["director"]["unread_count"] == 1
    assert payload["latest_coordinator_broadcast"]["ts"] == "2026-06-16T04:05:00Z"
