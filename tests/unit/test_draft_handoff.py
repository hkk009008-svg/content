"""Tests for scripts/draft_handoff.py."""

from __future__ import annotations

import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import draft_handoff  # noqa: E402


def _sample_context() -> draft_handoff.HandoffContext:
    return draft_handoff.HandoffContext(
        repo=Path("/repo"),
        seat="director2",
        wave=2,
        generated_at="2026-06-16T05:30:00+0900",
        head="abc1234 fix(example): sample",
        branch="main",
        origin_relation="21 ahead, 0 behind",
        recent_commits="abc1234 fix(example): sample\nfedcba9 docs(example): prior",
        mailbox_cursor="2026-06-15T20:04:46Z",
        mailbox_unread="0",
        mailbox_events=["2026-06-15T20-04-46Z-operator2-to-all-status.md"],
        coordinator_events=[
            "2026-06-15T19-59-27Z-coordinator-to-all-coordination.md"
        ],
        peer_heartbeats=[
            "director ONLINE last 0m ago",
            "operator ONLINE last 0m ago",
        ],
        staged_scope="M\tcinema/shots/controller.py",
        unstaged_scope="?? docs/HANDOFF-operator.md",
        locks="coordination/locks/.gitkeep",
        product_oracle="(none)",
        wave_gate="Wave 2 gate: UNMET counts={'verified': 23, 'open': 6, 'fixed': 1}",
        smoke="RESULT: no ceremony detected\nOK",
    )


def test_render_handoff_marks_snapshot_and_requires_live_refresh() -> None:
    text = draft_handoff.render_handoff(_sample_context())

    assert "# HANDOFF DRAFT - director2" in text
    assert "automated evidence draft" in text
    assert "Snapshot, Not Truth" in text
    assert "Refresh Live State First" in text
    assert "seat_status.py director2 --wave 2" in text
    assert "env -u GIT_INDEX_FILE git log --oneline -5" in text
    assert "Human Review Required" in text
    assert "Do not consume mailbox cursors from this draft tool" in text
    assert "M\tcinema/shots/controller.py" in text


def test_render_handoff_includes_clean_session_transplant_prompt() -> None:
    text = draft_handoff.render_handoff(_sample_context())

    assert "Clean Focused Session Transplant" in text
    assert "continue as director2" in text
    assert "Read this handoff as a snapshot" in text
    assert "refresh live mailbox and git state before acting" in text


def test_collect_context_does_not_consume_or_send_mail(tmp_path, monkeypatch) -> None:
    sent = tmp_path / "coordination" / "mailbox" / "sent"
    seen = tmp_path / "coordination" / "mailbox" / "seen"
    sent.mkdir(parents=True)
    seen.mkdir(parents=True)
    (seen / "operator.txt").write_text("2026-06-15T20:00:00Z\n", encoding="utf-8")
    (sent / "2026-06-15T20-04-46Z-operator2-to-all-status.md").write_text(
        "# Operator2 status\n", encoding="utf-8"
    )
    (sent / "2026-06-15T19-59-27Z-coordinator-to-all-coordination.md").write_text(
        "# Coordinator route\n", encoding="utf-8"
    )
    locks = tmp_path / "coordination" / "locks"
    locks.mkdir(parents=True)
    (locks / ".gitkeep").write_text("", encoding="utf-8")

    commands: list[list[str]] = []

    def fake_run(cmd, cwd, timeout=120):
        commands.append(cmd)
        if cmd[:3] == ["git", "log", "-1"]:
            return 0, "abc1234 fix(example): sample", ""
        if cmd[:2] == ["git", "rev-parse"]:
            return 0, "main", ""
        if cmd[:3] == ["git", "rev-list", "--left-right"]:
            return 0, "0 21", ""
        if cmd[:2] == ["git", "log"]:
            return 0, "abc1234 fix(example): sample", ""
        if cmd[:3] == ["git", "diff", "--cached"]:
            return 0, "", ""
        if cmd[:3] == ["git", "status", "--short"]:
            return 0, "?? docs/HANDOFF-operator.md", ""
        if cmd[1:] == ["scripts/wave_gate_check.py", "2"]:
            return 1, "Wave 2 gate: UNMET", ""
        if cmd[1:] == ["scripts/ci_smoke.py"]:
            return 0, "OK", ""
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(draft_handoff, "run", fake_run)
    monkeypatch.setattr(
        draft_handoff,
        "now_local",
        lambda: "2026-06-16T05:30:00+0900",
    )

    context = draft_handoff.collect_context(tmp_path, "operator", wave=2, smoke=True)

    flattened = " ".join(" ".join(cmd) for cmd in commands)
    assert "consume-events" not in flattened
    assert "send-event" not in flattened
    assert context.mailbox_cursor == "2026-06-15T20:00:00Z"
    assert context.mailbox_unread == "1"
    assert context.mailbox_events == [
        "2026-06-15T20-04-46Z-operator2-to-all-status.md"
    ]
    assert context.coordinator_events == [
        "2026-06-15T19-59-27Z-coordinator-to-all-coordination.md"
    ]


def test_collect_context_handles_coordinator_without_cursor(tmp_path, monkeypatch) -> None:
    sent = tmp_path / "coordination" / "mailbox" / "sent"
    sent.mkdir(parents=True)
    (sent / "2026-06-15T19-59-27Z-coordinator-to-all-coordination.md").write_text(
        "# Coordinator route\n", encoding="utf-8"
    )
    (sent / "2026-06-15T20-04-46Z-operator2-to-all-status.md").write_text(
        "# Operator2 status\n", encoding="utf-8"
    )

    def fake_run(cmd, cwd, timeout=120):
        if cmd[:3] == ["git", "log", "-1"]:
            return 0, "abc1234 fix(example): sample", ""
        if cmd[:2] == ["git", "rev-parse"]:
            return 0, "main", ""
        if cmd[:3] == ["git", "rev-list", "--left-right"]:
            return 0, "0 21", ""
        if cmd[:2] == ["git", "log"]:
            return 0, "abc1234 fix(example): sample", ""
        if cmd[:3] == ["git", "diff", "--cached"]:
            return 0, "", ""
        if cmd[:3] == ["git", "status", "--short"]:
            return 0, "", ""
        if cmd[1:] == ["scripts/wave_gate_check.py", "2"]:
            return 1, "Wave 2 gate: UNMET", ""
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(draft_handoff, "run", fake_run)
    monkeypatch.setattr(
        draft_handoff,
        "now_local",
        lambda: "2026-06-16T05:30:00+0900",
    )

    context = draft_handoff.collect_context(tmp_path, "coordinator", wave=2)

    assert context.mailbox_cursor == "(not used; coordinator is unpinned)"
    assert context.mailbox_unread == "all-scope 2 shown"
    assert context.mailbox_events == [
        "2026-06-15T19-59-27Z-coordinator-to-all-coordination.md",
        "2026-06-15T20-04-46Z-operator2-to-all-status.md",
    ]
