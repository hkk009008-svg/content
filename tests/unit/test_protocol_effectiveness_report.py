"""Tests for scripts/protocol_effectiveness_report.py."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import protocol_effectiveness_report as report  # noqa: E402


INVENTORY = """\
# Remediation Inventory

| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |
|----|-----------|-----------|----------|----------|-----------|-------|-----------|------------|-------------|------|--------|----------|-------|
| row-go | money | cost_tracker.py:1 | CRITICAL | 1 | leak | yes | tests/unit/test_row_go.py | B |  | 2 | verified | operator GO 2026-06-15 | Lane V GO evidence: focused test passed |
| row-fixed | gates | web_server.py:2 | MAJOR | 2 | missing check | yes | tests/unit/test_row_fixed.py | B |  | 2 | fixed |  | fix landed, operator GO missing |
| row-status-only | identity | quality_max.py:3 | MAJOR | 3 | stale | yes | tests/unit/test_row_status_only.py | A |  | 2 | verified |  | status-only verified claim |
"""


def test_mailbox_filename_and_event_classification() -> None:
    parsed = report.parse_mailbox_filename(
        "2026-06-15T10-05-00Z-operator-to-all-verification-report.md"
    )

    assert parsed.timestamp == "2026-06-15T10-05-00Z"
    assert parsed.sender == "operator"
    assert parsed.recipient == "all"
    assert parsed.kind == "verification-report"

    classification = report.parse_mailbox_event(
        parsed.filename,
        "VERDICT: GO\nEvidence: tests passed.",
    )

    assert classification.category == "verified_progress"


def test_verification_report_no_go_fails_closed_before_go_keyword() -> None:
    classification = report.parse_mailbox_event(
        "2026-06-15T10-05-00Z-operator-to-all-verification-report.md",
        "VERDICT: NO-GO\nThis report mentions GO only as the blocked target.",
    )

    assert classification.category == "blocked_progress"


def test_inventory_verified_status_alone_is_unknown() -> None:
    rows, errors = report.parse_inventory_rows(INVENTORY)

    assert errors == []
    by_id = {row["id"]: report.classify_inventory_row(row) for row in rows}
    assert by_id["row-go"].category == "verified_progress"
    assert by_id["row-fixed"].category == "blocked_progress"
    assert by_id["row-status-only"].category == "unknown"
    assert "status=verified without sufficient operator GO" in by_id["row-status-only"].reason


def test_inventory_no_go_does_not_count_as_verified_progress() -> None:
    classification = report.classify_inventory_row(
        {
            "id": "row-no-go",
            "wave": "2",
            "status": "verified",
            "severity": "MAJOR",
            "lane-owner": "A",
            "verifier": "operator NO-GO",
            "notes": "NO-GO evidence: focused test still fails",
        }
    )

    assert classification.category == "blocked_progress"


def test_gate_output_parsing_and_blocker_classification() -> None:
    gate = report.parse_gate_output(
        "\n".join(
            [
                "Wave 2 gate: UNMET  counts={'verified': 1, 'open': 1}",
                "  gate rows: 2; executable selectors: 2",
                "  PRODUCT ORACLE BLOCKER: Wave 2 requires logs/product-oracle-*.json",
                "  PYTEST: exit=1 command=python -m pytest tests/unit/test_row.py --runxfail",
                "    FAILED tests/unit/test_row.py::test_blocks",
            ]
        ),
        "",
        1,
    )

    classes = report.classify_gate_report(gate, wave=2)

    assert gate["verdict"] == "UNMET"
    assert gate["counts"] == {"verified": 1, "open": 1}
    assert gate["pytest_exit"] == 1
    assert any(item.id == "wave-2-product-oracle" for item in classes)
    assert any(item.id == "wave-2-pytest" for item in classes)


def test_collect_report_synthetic_cycle_is_read_only_and_fail_closed(tmp_path, monkeypatch) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "REMEDIATION-INVENTORY.md").write_text(INVENTORY, encoding="utf-8")
    sent = tmp_path / "coordination" / "mailbox" / "sent"
    sent.mkdir(parents=True)
    (sent / "2026-06-15T10-00-00Z-director-to-operator-verify-request.md").write_text(
        "# Verify request\nPlease verify row-go.\n",
        encoding="utf-8",
    )
    (sent / "2026-06-15T10-05-00Z-operator-to-all-verification-report.md").write_text(
        "# Verification\nVERDICT: GO\nEvidence: 1 passed.\n",
        encoding="utf-8",
    )
    (sent / "2026-06-15T10-06-00Z-coordinator-to-all-coordination.md").write_text(
        "# Route\nCoordinator routing update.\n",
        encoding="utf-8",
    )
    (sent / "2026-06-15T10-07-00Z-director2-to-all-status.md").write_text(
        "# Status\nstandby; correctly idle.\n",
        encoding="utf-8",
    )
    (sent / "2026-06-15T10-08-00Z-operator2-to-all-status.md").write_text(
        "# Status\nstale handoff contradicted by newer HEAD.\n",
        encoding="utf-8",
    )
    (sent / "not-a-mailbox.md").write_text("# malformed\n", encoding="utf-8")
    locks = tmp_path / "coordination" / "locks"
    locks.mkdir(parents=True)
    (locks / ".gitkeep").write_text("", encoding="utf-8")

    commands: list[list[str]] = []

    def fake_run(cmd, cwd, timeout=120):
        commands.append([str(part) for part in cmd])
        if cmd[:3] == ["git", "log", "-1"]:
            return 0, "abc1234 docs(spec): protocol effectiveness loop design", ""
        if cmd[:2] == ["git", "log"] and any(str(arg).startswith("--format=") for arg in cmd):
            return (
                0,
                "abc1234\x001781470000\x00fix(example): attempted repair\n"
                "def5678\x001781470060\x00docs(handoff): refresh handoff",
                "",
            )
        if cmd[1:] == ["scripts/wave_gate_check.py", "2"]:
            return (
                1,
                "\n".join(
                    [
                        "Wave 2 gate: UNMET  counts={'verified': 1, 'open': 1}",
                        "  gate rows: 2; executable selectors: 2",
                        "  PRODUCT ORACLE BLOCKER: Wave 2 requires logs/product-oracle-*.json",
                        "  PYTEST: exit=1 command=python -m pytest tests/unit/test_row.py --runxfail",
                        "    FAILED tests/unit/test_row.py::test_blocks",
                    ]
                ),
                "",
            )
        if cmd[:2] == ["git", "ls-tree"]:
            return 0, "docs/HANDOFF-old.md\n", ""
        if cmd[:3] == ["git", "status", "--short"]:
            return 0, "?? docs/HANDOFF-draft.md\n", ""
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(report, "run", fake_run)
    monkeypatch.setattr(
        report,
        "collect_mailbox",
        lambda root: {
            "mailbox_director_cursor": "2026-06-15T09:00:00Z",
            "mailbox_director_unread": 1,
            "mailbox_director2_cursor": "2026-06-15T10:07:00Z",
            "mailbox_director2_unread": 0,
            "mailbox_operator_cursor": "2026-06-15T09:00:00Z",
            "mailbox_operator_unread": 1,
            "mailbox_operator2_cursor": "2026-06-15T10:08:00Z",
            "mailbox_operator2_unread": 0,
        },
    )
    monkeypatch.setattr(
        report,
        "now_local",
        lambda: datetime(2026, 6, 16, 5, 30, tzinfo=timezone.utc),
    )

    artifact = report.collect_report(
        tmp_path,
        wave=2,
        commit_limit=5,
        event_limit=20,
        gate_timeout=10,
    )

    counts = artifact["metrics"]["classification_counts"]
    assert artifact["artifact_kind"] == "protocol-effectiveness"
    assert artifact["wave"] == 2
    assert counts["verified_progress"] >= 2
    assert counts["blocked_progress"] >= 3
    assert counts["coordination_only"] >= 2
    assert counts["no_op_evidence"] >= 1
    assert counts["stale_or_conflicted"] >= 1
    assert counts["unknown"] >= 2
    assert artifact["metrics"]["active_locks"] == []
    assert artifact["metrics"]["route_to_go_seconds"][0]["seconds"] == 300
    assert any(
        item["id"] == "row-status-only" and item["category"] == "unknown"
        for item in artifact["classifications"]
    )

    flattened = " ".join(" ".join(cmd) for cmd in commands)
    assert "consume-events" not in flattened
    assert "send-event" not in flattened
    assert "claim-lock" not in flattened
    assert all(cmd[:2] not in (["git", "add"], ["git", "commit"]) for cmd in commands)


def test_collect_locks_ignores_gitkeep(tmp_path) -> None:
    locks = tmp_path / "coordination" / "locks"
    locks.mkdir(parents=True)
    (locks / ".gitkeep").write_text("", encoding="utf-8")
    (locks / "W2-web_server.py.lock").write_text("owner=director2\n", encoding="utf-8")

    assert report.collect_locks(tmp_path) == ["W2-web_server.py.lock"]


def test_route_to_go_seconds_ignores_no_go_reports() -> None:
    events = [
        (
            report.parse_mailbox_filename(
                "2026-06-15T10-00-00Z-director-to-operator-verify-request.md"
            ),
            "Please verify.",
        ),
        (
            report.parse_mailbox_filename(
                "2026-06-15T10-05-00Z-operator-to-all-verification-report.md"
            ),
            "VERDICT: NO-GO\nStill blocked.",
        ),
    ]

    assert report.route_to_go_seconds(events) == []


def test_coord_verify_commit_is_coordination_not_verified_progress() -> None:
    classification = report.classify_commit(
        {
            "hash": "abc1234",
            "timestamp": "2026-06-15T10:00:00+00:00",
            "subject": "coord(verify): request lipsync precheck Lane V",
            "parse_error": None,
        }
    )

    assert classification.category == "coordination_only"


def test_blocked_reason_counts_does_not_bucket_blocked_as_lock() -> None:
    counts = report.blocked_reason_counts(
        [
            report.Classification(
                "blocked_progress",
                "mailbox",
                "event",
                "blocked target remains pending",
            )
        ]
    )

    assert counts == {"blocked progress": 1}


def test_main_stdout_only_does_not_write_artifact(tmp_path, monkeypatch, capsys) -> None:
    sample = {
        "artifact_kind": "protocol-effectiveness",
        "wave": 2,
        "generated_at": "2026-06-16T05:30:00+00:00",
        "head": "abc1234 sample",
        "summary": {
            "headline": "synthetic summary",
            "gate_verdict": "UNMET",
            "classification_counts": {},
            "top_blockers": {},
        },
        "metrics": {
            "blocked_reason_counts": {"product oracle": 1},
            "seat_utilization": [
                {"seat": "director", "state": "unread", "unread": 1},
            ],
        },
        "recommendations": ["Route product-oracle artifact work first."],
        "classifications": [],
    }

    monkeypatch.setattr(report, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(report, "collect_report", lambda *args: sample)
    monkeypatch.setattr(
        report,
        "write_artifact",
        lambda *args: (_ for _ in ()).throw(AssertionError("unexpected artifact write")),
    )

    rc = report.main(["--wave", "2", "--stdout-only"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "(stdout-only; no artifact written)" in out
    assert "synthetic summary" in out
