from __future__ import annotations

import importlib.util
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / ".agents/skills/four-seat-protocol/scripts/seat_status.py"
_SPEC = importlib.util.spec_from_file_location("seat_status_script", _SCRIPT)
assert _SPEC is not None
assert _SPEC.loader is not None
seat_status = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seat_status)


def _write_event(root: Path, filename: str) -> None:
    sent = root / "coordination/mailbox/sent"
    sent.mkdir(parents=True, exist_ok=True)
    (sent / filename).write_text("# event\n")


def _render_mailbox(root: Path, seat: str) -> str:
    buf = StringIO()
    with redirect_stdout(buf):
        seat_status.mailbox(str(root), seat)
    return buf.getvalue()


def test_coordinator_mailbox_scope_is_not_reported_as_unread(tmp_path: Path) -> None:
    _write_event(tmp_path, "2026-06-15T10-00-00Z-director-to-all-status.md")
    _write_event(tmp_path, "2026-06-15T11-00-00Z-operator-to-coordinator-status.md")

    out = _render_mailbox(tmp_path, "coordinator")

    assert "mailbox — coordinator/all scope" in out
    assert "cursor: (not used; coordinator is unpinned)" in out
    assert "ALL-SCOPE EVENTS: 2" in out
    assert "UNREAD:" not in out
    assert "consume via coordination/bin/consume-events" not in out


def test_live_seat_mailbox_still_reports_unread_from_cursor(tmp_path: Path) -> None:
    seen = tmp_path / "coordination/mailbox/seen"
    seen.mkdir(parents=True, exist_ok=True)
    (seen / "operator.txt").write_text("2026-06-15T10:00:00Z\n")
    _write_event(tmp_path, "2026-06-15T09-00-00Z-director-to-operator-status.md")
    _write_event(tmp_path, "2026-06-15T11-00-00Z-director-to-operator-status.md")
    _write_event(tmp_path, "2026-06-15T12-00-00Z-director-to-all-status.md")
    _write_event(tmp_path, "2026-06-15T13-00-00Z-operator-to-director-status.md")

    out = _render_mailbox(tmp_path, "operator")

    assert "cursor: 2026-06-15T10:00:00Z" in out
    assert "UNREAD: 2" in out
    assert "2026-06-15T11-00-00Z-director-to-operator-status.md" in out
    assert "2026-06-15T12-00-00Z-director-to-all-status.md" in out
    assert "consume via coordination/bin/consume-events operator" in out
