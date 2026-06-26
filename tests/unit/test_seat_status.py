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

# Resolvable now: seat_status's module load inserted scripts/ onto sys.path.
import bus_unread  # noqa: E402


def _write_event(root: Path, filename: str) -> None:
    sent = root / "coordination/mailbox/sent"
    sent.mkdir(parents=True, exist_ok=True)
    (sent / filename).write_text("# event\n")


def _render_mailbox(root: Path, seat: str) -> str:
    buf = StringIO()
    with redirect_stdout(buf):
        seat_status.mailbox(str(root), seat)
    return buf.getvalue()


def _render_heartbeats(root: Path, seat: str) -> str:
    buf = StringIO()
    with redirect_stdout(buf):
        seat_status.heartbeats(str(root), seat, 15)
    return buf.getvalue()


def test_coordinator_mailbox_reports_unread_from_cursor(tmp_path: Path) -> None:
    # Slice 2.5 (§7): coordinator is a first-class receiving seat now — it reads
    # its real seen cursor and reports UNREAD on the normal path. The OLD
    # send-only "unpinned / ALL-SCOPE" special-case strings are gone.
    seen = tmp_path / "coordination/mailbox/seen"
    seen.mkdir(parents=True, exist_ok=True)
    (seen / "coordinator.txt").write_text("2026-06-15T09:00:00Z\n")
    _write_event(tmp_path, "2026-06-15T10-00-00Z-director-to-all-status.md")
    _write_event(tmp_path, "2026-06-15T11-00-00Z-operator-to-coordinator-status.md")

    out = _render_mailbox(tmp_path, "coordinator")

    assert "mailbox — unread for 'coordinator'" in out
    assert "cursor: 2026-06-15T09:00:00Z" in out
    assert "UNREAD: 2" in out
    assert "consume via coordination/bin/consume-events coordinator" in out
    # OLD send-only special-case strings must be GONE.
    assert "not used; coordinator is unpinned" not in out
    assert "coordinator/all scope" not in out
    assert "ALL-SCOPE EVENTS" not in out


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


def _write_scalar_cursor(root: Path, seat: str, seq: str) -> None:
    seen = root / "coordination/mailbox/seen"
    seen.mkdir(parents=True, exist_ok=True)
    (seen / f"{seat}.txt").write_text(f"{seq}\n")


def test_scalar_cursor_mailbox_surfaces_live_bus_count(tmp_path: Path, monkeypatch) -> None:
    # De-degrade (ADR-062): a migrated (scalar-cursor) seat's real unread lives on the
    # signed ref-bus, NOT the legacy sent/*.md filename path (which returns 0 for a scalar
    # cursor — a silent under-report). The scalar branch must print the REAL ref-bus count,
    # not the old hard-coded "UNREAD: 0 / ref-bus-tracked".
    _write_scalar_cursor(tmp_path, "operator", "765")
    monkeypatch.setattr(bus_unread, "bus_unread_count", lambda root, seat, **k: 3)

    out = _render_mailbox(tmp_path, "operator")

    assert "cursor: 765" in out
    assert "UNREAD: 3 / ref-bus" in out
    assert "ref-bus-tracked" not in out  # the old degraded fixed-0 string is gone


def test_scalar_cursor_mailbox_empty_bus_is_real_zero(tmp_path: Path, monkeypatch) -> None:
    # A reachable-but-empty bus is a REAL 0 (distinct from the None/error sentinel below).
    _write_scalar_cursor(tmp_path, "operator", "765")
    monkeypatch.setattr(bus_unread, "bus_unread_count", lambda root, seat, **k: 0)

    out = _render_mailbox(tmp_path, "operator")

    assert "UNREAD: 0 / ref-bus" in out
    assert "ref-bus-tracked" not in out


def test_scalar_cursor_mailbox_bus_error_is_visible_not_silent_zero(
    tmp_path: Path, monkeypatch
) -> None:
    # silent-gate-degradation guard: a bus ERROR (bus_unread_count -> None) must surface a
    # VISIBLE "(unavailable: ref-bus)" sentinel — NEVER a silent/misleading 0.
    _write_scalar_cursor(tmp_path, "operator", "765")
    monkeypatch.setattr(bus_unread, "bus_unread_count", lambda root, seat, **k: None)

    out = _render_mailbox(tmp_path, "operator")

    assert "(unavailable: ref-bus)" in out
    assert "UNREAD: 0" not in out


def test_heartbeats_are_pair_seat_only_no_coordinators(tmp_path: Path) -> None:
    # Slice 2.5 review-fix: coordinators have NO presence heartbeat by design,
    # so heartbeats() must iterate the 4 PAIR seats (protocol_mailbox.SEATS),
    # never the 6-seat receiving roster. Reverting heartbeats() back to the
    # 6-seat roster makes coordinator2 reappear as "(no heartbeat file)" → RED.
    (tmp_path / "coordination/presence").mkdir(parents=True, exist_ok=True)

    # Invoke AS a coordinator (a real use case post-Slice-2.5) so a 6-seat loop
    # would print the *other* coordinator's missing-heartbeat line.
    out = _render_heartbeats(tmp_path, "coordinator")

    # The 4 pair seats are probed (none have a file here → all show as missing).
    for pair_seat in ("director", "director2", "operator", "operator2"):
        assert pair_seat in out, f"expected pair seat {pair_seat!r} in heartbeat output"
    # Coordinators must NOT appear as heartbeat lines at all.
    assert "coordinator2" not in out
    assert "coordinator " not in out  # padded "coordinator" column would have a trailing space
    # No spurious "(no heartbeat file)" line FOR a coordinator.
    for line in out.splitlines():
        if "(no heartbeat file)" in line or "(missing" in line:
            assert "coordinator" not in line, f"coordinator leaked into heartbeat line: {line!r}"
