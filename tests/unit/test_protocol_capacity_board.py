"""Tests for the hard-gated protocol capacity scheduler."""

from __future__ import annotations

import json
import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_ROOT = Path(__file__).resolve().parent.parent.parent

import protocol_capacity as capacity  # noqa: E402
import protocol_capacity_board as board  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _packet(
    packet_id: str,
    owner: str,
    *,
    packet_type: str | None = None,
    status: str = "active",
    wave: int = 4,
    cycle: str = "2026-06-17-wave4-open",
    paths: list[str] | None = None,
    locks: list[str] | None = None,
    deps: list[str] | None = None,
    rows: list[str] | None = None,
    done_evidence: list[str] | None = None,
    next_recipient: str | None = None,
) -> dict:
    if packet_type is None:
        if owner == "coordinator":
            packet_type = "coordinator-route"
        elif owner.startswith("operator"):
            packet_type = "operator-verification"
        else:
            packet_type = "director-implementation"
    return {
        "id": packet_id,
        "wave": wave,
        "cycle": cycle,
        "owner": owner,
        "packet_type": packet_type,
        "row_ids": rows if rows is not None else ["identity-arcface-embselect"],
        "allowed_paths": paths if paths is not None else [],
        "lock_keys": locks if locks is not None else [],
        "dependencies": deps if deps is not None else [],
        "acceptance": ["acceptance evidence recorded"],
        "done_evidence": done_evidence if done_evidence is not None else [],
        "next_recipient": next_recipient,
        "status": status,
    }


def _write_packet(root: Path, payload: dict) -> None:
    _write_json(root / "coordination/capacity/packets" / f"{payload['id']}.json", payload)


def _write_valid_cycle(root: Path) -> None:
    packets = [
        _packet(
            "wave4-route-coordinator",
            "coordinator",
            packet_type="coordinator-route",
            paths=["coordination/capacity/packets"],
        ),
        _packet(
            "wave4-identity-director",
            "director",
            paths=["identity/validator.py", "tests/unit/test_identity.py"],
            next_recipient="operator",
        ),
        _packet(
            "wave4-identity-operator",
            "operator",
            packet_type="blocked",
            status="blocked",
            deps=["wave4-identity-director"],
        ),
        _packet(
            "wave4-docs-director2",
            "director2",
            packet_type="blocked",
            status="blocked",
            deps=["wave4-identity-operator"],
            paths=["docs/protocol/codex/continuation.md"],
            next_recipient="operator2",
        ),
        _packet(
            "wave4-docs-operator2",
            "operator2",
            packet_type="blocked",
            status="blocked",
            deps=["wave4-docs-director2"],
        ),
    ]
    for packet in packets:
        _write_packet(root, packet)


def _write_route(root: Path, body: str) -> Path:
    path = (
        root
        / "coordination/mailbox/sent"
        / "2026-06-17T00-00-00Z-coordinator-to-all-coordination.md"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _valid_route_body() -> str:
    return """# Coordinator -> All: Wave 4 task-board route

Packet IDs:
- `wave4-route-coordinator`
- `wave4-identity-director`
- `wave4-identity-operator`
- `wave4-docs-director2`
- `wave4-docs-operator2`

Join condition:
- operator and operator2 GO, capacity board valid, smoke OK.

Boundaries:
- No push, lock claim, paid API spend, pod spend, or production generation is authorized.
"""


def test_valid_cycle_renders_one_packet_per_actor(tmp_path: Path) -> None:
    _write_valid_cycle(tmp_path)

    report = capacity.collect_capacity_report(tmp_path, 4)

    assert report.blocking_issues == []
    assert [row["owner"] for row in report.actor_rows] == [
        "coordinator",
        "director",
        "director2",
        "operator",
        "operator2",
    ]
    assert "wave4-identity-director" in capacity.render_capacity_board(report)


def test_malformed_packet_json_fails_closed(tmp_path: Path) -> None:
    packet_dir = tmp_path / "coordination/capacity/packets"
    packet_dir.mkdir(parents=True)
    (packet_dir / "bad.json").write_text("{not-json", encoding="utf-8")

    report = capacity.collect_capacity_report(tmp_path, 4)

    assert any(issue["gate"] == "SCHEMA" for issue in report.blocking_issues)
    assert "bad.json" in report.blocking_issues[0]["message"]


def test_invalid_owner_and_status_fail_schema(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        _packet("bad-owner", "director") | {"owner": "assistant", "status": "busy"},
    )

    report = capacity.collect_capacity_report(tmp_path, 4)

    messages = "\n".join(issue["message"] for issue in report.blocking_issues)
    assert "invalid owner" in messages
    assert "invalid status" in messages


def test_wip_limit_detects_two_active_packets_for_one_actor(tmp_path: Path) -> None:
    _write_valid_cycle(tmp_path)
    _write_packet(
        tmp_path,
        _packet(
            "wave4-second-director",
            "director",
            paths=["identity/other.py"],
            rows=["another-row"],
        ),
    )

    report = capacity.collect_capacity_report(tmp_path, 4)

    assert any(issue["gate"] == "G2" for issue in report.blocking_issues)


def test_path_and_lock_collisions_are_blocking(tmp_path: Path) -> None:
    _write_valid_cycle(tmp_path)
    _write_packet(
        tmp_path,
        _packet(
            "wave4-director2-overlap",
            "director2",
            paths=["identity/validator.py"],
            locks=["identity-validator"],
        ),
    )
    _write_packet(
        tmp_path,
        _packet(
            "wave4-director-lock",
            "director",
            paths=["identity/director_only.py"],
            locks=["identity-validator"],
            rows=["different-row"],
        ),
    )

    report = capacity.collect_capacity_report(tmp_path, 4)

    gates = [issue["gate"] for issue in report.blocking_issues]
    assert "G2" in gates
    assert "G3" in gates


def test_dependency_missing_and_cycle_are_blocking(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        _packet("cycle-a", "director", deps=["cycle-b"], paths=["a.py"]),
    )
    _write_packet(
        tmp_path,
        _packet("cycle-b", "director2", deps=["cycle-a"], paths=["b.py"]),
    )
    _write_packet(
        tmp_path,
        _packet("missing-dep", "operator", deps=["does-not-exist"], packet_type="blocked", status="blocked"),
    )

    report = capacity.collect_capacity_report(tmp_path, 4)

    messages = "\n".join(issue["message"] for issue in report.blocking_issues)
    assert "missing dependency does-not-exist" in messages
    assert "dependency cycle" in messages


def test_director_done_requires_evidence_and_verify_request(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        _packet(
            "done-without-evidence",
            "director",
            status="done",
            paths=["identity/validator.py"],
        ),
    )

    report = capacity.collect_capacity_report(tmp_path, 4)

    assert any(issue["gate"] == "G5" for issue in report.blocking_issues)


def test_operator_active_requires_verify_request_and_target_commit(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        _packet(
            "operator-without-target",
            "operator",
            packet_type="operator-verification",
            status="active",
        ),
    )

    report = capacity.collect_capacity_report(tmp_path, 4)

    messages = "\n".join(issue["message"] for issue in report.blocking_issues)
    assert "missing verify_request" in messages
    assert "target_commit or commit_range" in messages


def test_operator_done_requires_go_nits_or_fail_evidence(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        _packet(
            "operator-done-without-verdict",
            "operator",
            packet_type="operator-verification",
            status="done",
            done_evidence=["pytest passed"],
        )
        | {
            "verify_request": "coordination/mailbox/sent/request.md",
            "target_commit": "abc1234",
            "scope_files": ["scripts/protocol_capacity.py"],
        },
    )

    report = capacity.collect_capacity_report(tmp_path, 4)

    assert any(issue["gate"] == "G6" for issue in report.blocking_issues)


def test_closed_cycle_requires_join_evidence(tmp_path: Path) -> None:
    for packet in [
        _packet(
            "wave4-join",
            "coordinator",
            packet_type="coordinator-join",
            status="done",
            done_evidence=["capacity board valid", "smoke OK"],
        ),
        _packet(
            "wave4-director-done",
            "director",
            status="done",
            done_evidence=[
                "committed diff",
                "verify-request coordination/mailbox/sent/request.md",
                "operator GO coordination/mailbox/sent/go.md",
            ],
        ),
        _packet(
            "wave4-operator-done",
            "operator",
            packet_type="operator-verification",
            status="done",
            done_evidence=["GO coordination/mailbox/sent/go.md"],
        )
        | {
            "verify_request": "coordination/mailbox/sent/request.md",
            "target_commit": "abc1234",
            "scope_files": ["identity/validator.py"],
        },
    ]:
        _write_packet(tmp_path, packet)

    report = capacity.collect_capacity_report(tmp_path, 4)

    assert any(issue["gate"] == "G8" for issue in report.blocking_issues)


def test_exact_exception_bypasses_matching_issue_only(tmp_path: Path) -> None:
    _write_valid_cycle(tmp_path)
    _write_packet(
        tmp_path,
        _packet(
            "wave4-director2-overlap",
            "director2",
            paths=["identity/validator.py"],
            rows=["identity-arcface-embselect"],
        ),
    )
    _write_packet(
        tmp_path,
        _packet(
            "wave4-second-director",
            "director",
            paths=["identity/director_two.py"],
            rows=["different-row"],
        ),
    )
    _write_json(
        tmp_path / "coordination/protocol-exceptions/exact.json",
        {
            "id": "EX-exact",
            "created_at": "2026-06-17T00:00:00Z",
            "approving_actor": "coordinator",
            "bypassed_gate": "G3",
            "reason": "docs-only bootstrap collision accepted",
            "scope": {
                "packet_ids": ["wave4-identity-director", "wave4-director2-overlap"],
                "row_ids": ["identity-arcface-embselect"],
                "paths": ["identity/validator.py"],
            },
            "expiry": {"type": "condition", "value": "operator GO"},
            "convergence_condition": "operator verifies the exact overlap",
            "status": "active",
        },
    )
    _write_json(
        tmp_path / "coordination/protocol-exceptions/mismatch.json",
        {
            "id": "EX-mismatch",
            "created_at": "2026-06-17T00:00:00Z",
            "approving_actor": "coordinator",
            "bypassed_gate": "G2",
            "reason": "wrong packet scope",
            "scope": {
                "packet_ids": ["not-the-director-packet"],
                "row_ids": ["identity-arcface-embselect"],
                "paths": ["identity/validator.py"],
            },
            "expiry": {"type": "condition", "value": "operator GO"},
            "convergence_condition": "operator verifies the exact overlap",
            "status": "active",
        },
    )

    report = capacity.collect_capacity_report(tmp_path, 4)

    assert not any(issue["gate"] == "G3" for issue in report.blocking_issues)
    assert any(issue["gate"] == "G2" for issue in report.blocking_issues)


def test_validate_route_accepts_complete_task_board(tmp_path: Path) -> None:
    _write_valid_cycle(tmp_path)
    route = _write_route(tmp_path, _valid_route_body())

    result = capacity.validate_route(tmp_path, 4, route)

    assert result.valid
    assert result.blocking_issues == []


def test_validate_route_rejects_missing_packets_and_join_condition(tmp_path: Path) -> None:
    _write_valid_cycle(tmp_path)
    route = _write_route(
        tmp_path,
        """# Coordinator -> All: incomplete task-board

Packet IDs:
- `wave4-route-coordinator`
""",
    )

    result = capacity.validate_route(tmp_path, 4, route)

    messages = "\n".join(issue["message"] for issue in result.blocking_issues)
    assert "missing packet ids" in messages
    assert "missing join condition" in messages


def test_validate_route_rejects_forbidden_side_effects(tmp_path: Path) -> None:
    _write_valid_cycle(tmp_path)
    route = _write_route(
        tmp_path,
        _valid_route_body()
        + "\nThis route authorizes push, pod spend, and lock claim immediately.\n",
    )

    result = capacity.validate_route(tmp_path, 4, route)

    assert any(issue["gate"] == "G7" for issue in result.blocking_issues)
    assert "forbidden side effect" in result.blocking_issues[0]["message"]


def test_validate_route_cli_returns_nonzero_for_invalid_route(
    tmp_path: Path,
    capsys,
) -> None:
    _write_valid_cycle(tmp_path)
    route = _write_route(tmp_path, "# Coordinator -> All: incomplete task-board\n")

    rc = board.main(["--root", str(tmp_path), "--wave", "4", "--validate-route", str(route)])

    assert rc == 1
    output = capsys.readouterr().out
    assert "route valid: false" in output
    assert "missing packet ids" in output


def test_cli_text_board_outputs_actor_rows(tmp_path: Path, capsys) -> None:
    _write_valid_cycle(tmp_path)

    rc = board.main(["--root", str(tmp_path), "--wave", "4"])

    assert rc == 0
    output = capsys.readouterr().out
    assert "# Protocol Capacity Board" in output
    assert "director    packets=wave4-identity-director status=active" in output


def test_cli_json_board_outputs_machine_readable_contract(
    tmp_path: Path,
    capsys,
) -> None:
    _write_valid_cycle(tmp_path)

    rc = board.main(["--root", str(tmp_path), "--wave", "4", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["artifact_kind"] == "protocol-capacity-board"
    assert payload["valid"] is True
    assert payload["actor_rows"][1]["owner"] == "director"


def test_sample_packet_and_exception_fixtures_parse(tmp_path: Path) -> None:
    packet = json.loads(
        (_ROOT / "tests/fixtures/protocol_capacity/sample-packet.json").read_text(
            encoding="utf-8"
        )
    )
    exception = json.loads(
        (_ROOT / "tests/fixtures/protocol_capacity/sample-exception.json").read_text(
            encoding="utf-8"
        )
    )
    _write_packet(tmp_path, packet)
    _write_json(tmp_path / "coordination/protocol-exceptions/sample.json", exception)

    report = capacity.collect_capacity_report(tmp_path, 4)

    assert report.packets[0].id == "wave4-identity-arcface-embselect-director"
    assert report.exceptions[0].id == "EX-2026-06-17-wave4-identity-fixture"
