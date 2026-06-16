#!/usr/bin/env python3
"""Read-only hard-gated capacity scheduler for the four-seat protocol."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


SEAT_ORDER = ("coordinator", "director", "director2", "operator", "operator2")
PACKET_TYPES = {
    "director-implementation",
    "director-brief",
    "director-cosign",
    "operator-verification",
    "operator-doc-sync",
    "coordinator-route",
    "coordinator-reconcile",
    "coordinator-join",
    "receipt-only",
    "idle",
    "blocked",
}
STATUSES = {"ready", "active", "blocked", "done", "excepted"}
ACTIVE_STATUSES = {"ready", "active"}
CURRENT_STATUSES = {"ready", "active", "blocked"}
HANDOFF_ARTIFACT_RE = re.compile(r"\bdocs/HANDOFF-[^\s`]+\.md\b", re.IGNORECASE)
HANDOFF_REQUIRED_RE = re.compile(
    r"\b("
    r"standby|idle|no routed next work|no current work|no new [a-z -]*task|"
    r"context switch|transplant|state-transfer|state transfer|handoff|"
    r"closeout|closed cycle|cycle complete"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Packet:
    id: str
    wave: int
    cycle: str
    owner: str
    packet_type: str
    row_ids: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    lock_keys: tuple[str, ...]
    dependencies: tuple[str, ...]
    acceptance: tuple[str, ...]
    done_evidence: tuple[str, ...]
    next_recipient: str | None
    status: str
    verify_request: str | None
    target_commit: str | None
    commit_range: str | None
    scope_files: tuple[str, ...]
    path: str

    @property
    def is_active_wip(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def is_current(self) -> bool:
        return self.status in CURRENT_STATUSES

    @property
    def is_implementation(self) -> bool:
        return "implementation" in self.packet_type

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "wave": self.wave,
            "cycle": self.cycle,
            "owner": self.owner,
            "packet_type": self.packet_type,
            "row_ids": list(self.row_ids),
            "allowed_paths": list(self.allowed_paths),
            "lock_keys": list(self.lock_keys),
            "dependencies": list(self.dependencies),
            "acceptance": list(self.acceptance),
            "done_evidence": list(self.done_evidence),
            "next_recipient": self.next_recipient,
            "status": self.status,
            "verify_request": self.verify_request,
            "target_commit": self.target_commit,
            "commit_range": self.commit_range,
            "scope_files": list(self.scope_files),
            "path": self.path,
        }


@dataclass(frozen=True)
class ProtocolException:
    id: str
    created_at: str
    approving_actor: str
    bypassed_gate: str
    reason: str
    scope: dict[str, tuple[str, ...]]
    expiry: dict[str, Any]
    convergence_condition: str
    status: str
    path: str

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "approving_actor": self.approving_actor,
            "bypassed_gate": self.bypassed_gate,
            "reason": self.reason,
            "scope": {key: list(value) for key, value in self.scope.items()},
            "expiry": self.expiry,
            "convergence_condition": self.convergence_condition,
            "status": self.status,
            "path": self.path,
        }


@dataclass(frozen=True)
class CapacityReport:
    root: str
    wave: int
    packets: tuple[Packet, ...]
    exceptions: tuple[ProtocolException, ...]
    issues: tuple[dict[str, Any], ...]

    @property
    def blocking_issues(self) -> list[dict[str, Any]]:
        return [issue for issue in self.issues if not issue.get("excepted_by")]

    @property
    def actor_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for owner in SEAT_ORDER:
            current = [
                packet for packet in self.packets if packet.owner == owner and packet.is_current
            ]
            rows.append(
                {
                    "owner": owner,
                    "packet_ids": [packet.id for packet in current],
                    "statuses": [packet.status for packet in current],
                    "packet_types": [packet.packet_type for packet in current],
                }
            )
        return rows

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": "protocol-capacity-board",
            "root": self.root,
            "wave": self.wave,
            "packets": [packet.to_dict() for packet in self.packets],
            "exceptions": [exception.to_dict() for exception in self.exceptions],
            "actor_rows": self.actor_rows,
            "issues": list(self.issues),
            "blocking_issues": self.blocking_issues,
            "valid": not self.blocking_issues,
        }


@dataclass(frozen=True)
class RouteValidation:
    route_path: str
    report: CapacityReport
    route_issues: tuple[dict[str, Any], ...]

    @property
    def blocking_issues(self) -> list[dict[str, Any]]:
        return [*self.report.blocking_issues, *self.route_issues]

    @property
    def valid(self) -> bool:
        return not self.blocking_issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": "protocol-capacity-route-validation",
            "route_path": self.route_path,
            "valid": self.valid,
            "route_issues": list(self.route_issues),
            "blocking_issues": self.blocking_issues,
            "board": self.report.to_dict(),
        }


def collect_capacity_report(root: Path | str, wave: int) -> CapacityReport:
    root_path = Path(root)
    packet_issues: list[dict[str, Any]] = []
    exception_issues: list[dict[str, Any]] = []
    packets = _load_packets(root_path, wave, packet_issues)
    exceptions = _load_exceptions(root_path, exception_issues)
    issues = [*packet_issues, *exception_issues, *_validate_packets(packets)]
    issues = _apply_exceptions(issues, exceptions)
    return CapacityReport(
        root=str(root_path),
        wave=wave,
        packets=tuple(packets),
        exceptions=tuple(exceptions),
        issues=tuple(issues),
    )


def validate_route(root: Path | str, wave: int, route_path: Path | str) -> RouteValidation:
    report = collect_capacity_report(root, wave)
    path = Path(route_path)
    route_issues = _validate_route_file(path, report)
    route_issues = _apply_exceptions(route_issues, list(report.exceptions))
    blocking_route_issues = [
        issue for issue in route_issues if not issue.get("excepted_by")
    ]
    return RouteValidation(
        route_path=str(path),
        report=report,
        route_issues=tuple(blocking_route_issues),
    )


def render_capacity_board(report: CapacityReport) -> str:
    lines = [
        "# Protocol Capacity Board",
        f"wave: {report.wave}",
        f"valid: {str(not report.blocking_issues).lower()}",
        "",
        "ACTORS",
    ]
    for row in report.actor_rows:
        packet_ids = ", ".join(row["packet_ids"]) if row["packet_ids"] else "-"
        statuses = ", ".join(row["statuses"]) if row["statuses"] else "-"
        lines.append(f"{row['owner']:<11} packets={packet_ids} status={statuses}")

    lines.append("")
    if report.blocking_issues:
        lines.append("BLOCKING ISSUES")
        for issue in report.blocking_issues:
            lines.append(f"- {issue['gate']}: {issue['message']}")
    else:
        lines.append("BLOCKING ISSUES")
        lines.append("- none")

    excepted = [issue for issue in report.issues if issue.get("excepted_by")]
    if excepted:
        lines.append("")
        lines.append("EXCEPTED ISSUES")
        for issue in excepted:
            lines.append(f"- {issue['gate']}: {issue['message']} ({issue['excepted_by']})")
    return "\n".join(lines) + "\n"


def render_route_validation(result: RouteValidation) -> str:
    lines = [
        "# Protocol Capacity Route Validation",
        f"route: {result.route_path}",
        f"route valid: {str(result.valid).lower()}",
        "",
    ]
    if result.blocking_issues:
        lines.append("BLOCKING ISSUES")
        for issue in result.blocking_issues:
            lines.append(f"- {issue['gate']}: {issue['message']}")
    else:
        lines.append("BLOCKING ISSUES")
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _load_packets(root: Path, wave: int, issues: list[dict[str, Any]]) -> list[Packet]:
    packet_dir = root / "coordination/capacity/packets"
    packets: list[Packet] = []
    if not packet_dir.is_dir():
        return packets
    for path in sorted(packet_dir.glob("*.json")):
        data = _read_json(path, issues)
        if data is None:
            continue
        packet = _parse_packet(path, data, issues)
        if packet and packet.wave == wave:
            packets.append(packet)
    return packets


def _load_exceptions(root: Path, issues: list[dict[str, Any]]) -> list[ProtocolException]:
    exception_dir = root / "coordination/protocol-exceptions"
    exceptions: list[ProtocolException] = []
    if not exception_dir.is_dir():
        return exceptions
    for path in sorted(exception_dir.glob("*.json")):
        data = _read_json(path, issues)
        if data is None:
            continue
        exception = _parse_exception(path, data, issues)
        if exception:
            exceptions.append(exception)
    return exceptions


def _read_json(path: Path, issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(_issue("SCHEMA", f"{path.name}: unreadable JSON ({exc})"))
        return None
    if not isinstance(data, dict):
        issues.append(_issue("SCHEMA", f"{path.name}: top-level JSON is not an object"))
        return None
    return data


def _parse_packet(
    path: Path,
    data: dict[str, Any],
    issues: list[dict[str, Any]],
) -> Packet | None:
    required = {
        "id",
        "wave",
        "cycle",
        "owner",
        "packet_type",
        "row_ids",
        "allowed_paths",
        "lock_keys",
        "dependencies",
        "acceptance",
        "done_evidence",
        "status",
    }
    missing = sorted(required - data.keys())
    local_issues: list[str] = []
    if missing:
        local_issues.append("missing required fields: " + ", ".join(missing))
    if data.get("owner") not in SEAT_ORDER:
        local_issues.append(f"invalid owner {data.get('owner')!r}")
    if data.get("packet_type") not in PACKET_TYPES:
        local_issues.append(f"invalid packet_type {data.get('packet_type')!r}")
    if data.get("status") not in STATUSES:
        local_issues.append(f"invalid status {data.get('status')!r}")
    if not isinstance(data.get("wave"), int):
        local_issues.append("wave must be an integer")
    for field in ("row_ids", "allowed_paths", "lock_keys", "dependencies", "acceptance", "done_evidence"):
        if not _is_str_list(data.get(field)):
            local_issues.append(f"{field} must be a list of strings")
    next_recipient = data.get("next_recipient")
    if next_recipient is not None and next_recipient not in SEAT_ORDER:
        local_issues.append(f"invalid next_recipient {next_recipient!r}")
    if "scope_files" in data and not _is_str_list(data.get("scope_files")):
        local_issues.append("scope_files must be a list of strings")

    if local_issues:
        for message in local_issues:
            issues.append(_issue("SCHEMA", f"{path.name}: {message}"))
        return None

    return Packet(
        id=str(data["id"]),
        wave=int(data["wave"]),
        cycle=str(data["cycle"]),
        owner=str(data["owner"]),
        packet_type=str(data["packet_type"]),
        row_ids=tuple(data["row_ids"]),
        allowed_paths=tuple(data["allowed_paths"]),
        lock_keys=tuple(data["lock_keys"]),
        dependencies=tuple(data["dependencies"]),
        acceptance=tuple(data["acceptance"]),
        done_evidence=tuple(data["done_evidence"]),
        next_recipient=next_recipient,
        status=str(data["status"]),
        verify_request=_optional_str(data.get("verify_request")),
        target_commit=_optional_str(data.get("target_commit")),
        commit_range=_optional_str(data.get("commit_range")),
        scope_files=tuple(data.get("scope_files", [])),
        path=_display_path(path),
    )


def _parse_exception(
    path: Path,
    data: dict[str, Any],
    issues: list[dict[str, Any]],
) -> ProtocolException | None:
    required = {
        "id",
        "created_at",
        "approving_actor",
        "bypassed_gate",
        "reason",
        "scope",
        "expiry",
        "convergence_condition",
        "status",
    }
    missing = sorted(required - data.keys())
    local_issues: list[str] = []
    if missing:
        local_issues.append("missing required fields: " + ", ".join(missing))
    if data.get("status") not in {"active", "expired", "closed"}:
        local_issues.append(f"invalid status {data.get('status')!r}")
    if not isinstance(data.get("scope"), dict):
        local_issues.append("scope must be an object")
    if not isinstance(data.get("expiry"), dict):
        local_issues.append("expiry must be an object")

    scope: dict[str, tuple[str, ...]] = {}
    if isinstance(data.get("scope"), dict):
        for key in ("packet_ids", "row_ids", "paths"):
            value = data["scope"].get(key, [])
            if not _is_str_list(value):
                local_issues.append(f"scope.{key} must be a list of strings")
            else:
                scope[key] = tuple(value)

    if local_issues:
        for message in local_issues:
            issues.append(_issue("SCHEMA", f"{path.name}: {message}"))
        return None

    return ProtocolException(
        id=str(data["id"]),
        created_at=str(data["created_at"]),
        approving_actor=str(data["approving_actor"]),
        bypassed_gate=str(data["bypassed_gate"]),
        reason=str(data["reason"]),
        scope=scope,
        expiry=dict(data["expiry"]),
        convergence_condition=str(data["convergence_condition"]),
        status=str(data["status"]),
        path=_display_path(path),
    )


def _validate_packets(packets: list[Packet]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    issues.extend(_validate_coverage(packets))
    issues.extend(_validate_wip_limit(packets))
    issues.extend(_validate_path_and_lock_isolation(packets))
    issues.extend(_validate_dependencies(packets))
    issues.extend(_validate_director_done_boundary(packets))
    issues.extend(_validate_operator_verification_boundary(packets))
    issues.extend(_validate_join_gate(packets))
    return issues


def _validate_coverage(packets: list[Packet]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    cycles = sorted({packet.cycle for packet in packets if packet.is_current})
    for cycle in cycles:
        current = [packet for packet in packets if packet.cycle == cycle and packet.is_current]
        if not any(packet.is_active_wip for packet in current):
            continue
        for owner in SEAT_ORDER:
            owned = [packet for packet in current if packet.owner == owner]
            if len(owned) != 1:
                issues.append(
                    _issue(
                        "G1",
                        f"cycle {cycle}: {owner} has {len(owned)} current packets",
                        packet_ids=[packet.id for packet in owned],
                    )
                )
    return issues


def _validate_wip_limit(packets: list[Packet]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    cycles = sorted({packet.cycle for packet in packets})
    for cycle in cycles:
        for owner in SEAT_ORDER:
            active = [
                packet
                for packet in packets
                if packet.cycle == cycle and packet.owner == owner and packet.is_active_wip
            ]
            if len(active) > 1:
                issues.append(
                    _issue(
                        "G2",
                        f"cycle {cycle}: {owner} has {len(active)} ready/active packets",
                        packet_ids=[packet.id for packet in active],
                        row_ids=_merged(active, "row_ids"),
                        paths=_merged(active, "allowed_paths"),
                    )
                )
    return issues


def _validate_path_and_lock_isolation(packets: list[Packet]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    active_impl = [
        packet for packet in packets if packet.is_active_wip and packet.is_implementation
    ]
    for idx, left in enumerate(active_impl):
        for right in active_impl[idx + 1 :]:
            if left.id == right.id:
                continue
            shared_paths = sorted(set(left.allowed_paths) & set(right.allowed_paths))
            shared_locks = sorted(set(left.lock_keys) & set(right.lock_keys))
            if not shared_paths and not shared_locks:
                continue
            detail = []
            if shared_paths:
                detail.append("paths=" + ", ".join(shared_paths))
            if shared_locks:
                detail.append("locks=" + ", ".join(shared_locks))
            issues.append(
                _issue(
                    "G3",
                    f"{left.id} and {right.id} overlap " + "; ".join(detail),
                    packet_ids=[left.id, right.id],
                    row_ids=sorted(set(left.row_ids) | set(right.row_ids)),
                    paths=shared_paths,
                    lock_keys=shared_locks,
                )
            )
    return issues


def _validate_dependencies(packets: list[Packet]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    by_id = {packet.id: packet for packet in packets}
    for packet in packets:
        for dep in packet.dependencies:
            if dep not in by_id:
                issues.append(
                    _issue(
                        "G4",
                        f"{packet.id}: missing dependency {dep}",
                        packet_ids=[packet.id],
                        row_ids=list(packet.row_ids),
                    )
                )

    graph = {packet.id: list(packet.dependencies) for packet in packets}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, stack: list[str]) -> list[str] | None:
        if node in visiting:
            return [*stack, node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for dep in graph.get(node, []):
            if dep not in graph:
                continue
            cycle = visit(dep, stack)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in graph:
        cycle = visit(node, [])
        if cycle:
            issues.append(
                _issue(
                    "G4",
                    "dependency cycle: " + " -> ".join(cycle),
                    packet_ids=cycle,
                )
            )
            break
    return issues


def _validate_director_done_boundary(packets: list[Packet]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for packet in packets:
        if packet.packet_type != "director-implementation" or packet.status != "done":
            continue
        evidence = _evidence_text(packet)
        missing: list[str] = []
        if not packet.done_evidence:
            missing.append("done_evidence")
        if "verify-request" not in evidence and "verification not needed" not in evidence:
            missing.append("verify-request or verification-not-needed reason")
        if missing:
            issues.append(
                _issue(
                    "G5",
                    f"{packet.id}: missing " + ", ".join(missing),
                    packet_ids=[packet.id],
                    row_ids=list(packet.row_ids),
                    paths=list(packet.allowed_paths),
                )
            )
    return issues


def _validate_operator_verification_boundary(packets: list[Packet]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for packet in packets:
        if packet.packet_type != "operator-verification" or packet.status not in {"active", "done"}:
            continue
        missing: list[str] = []
        if not packet.verify_request:
            missing.append("verify_request")
        if not packet.target_commit and not packet.commit_range:
            missing.append("target_commit or commit_range")
        if not packet.scope_files and not packet.row_ids:
            missing.append("scope_files or row_ids")
        evidence = _evidence_text(packet)
        if packet.status == "done" and not re.search(r"\b(GO|NITS|FAIL)\b", evidence, re.IGNORECASE):
            missing.append("GO/NITS/FAIL evidence")
        if missing:
            issues.append(
                _issue(
                    "G6",
                    f"{packet.id}: missing " + ", ".join(missing),
                    packet_ids=[packet.id],
                    row_ids=list(packet.row_ids),
                    paths=list(packet.scope_files or packet.allowed_paths),
                )
            )
    return issues


def _validate_join_gate(packets: list[Packet]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    cycles = sorted({packet.cycle for packet in packets})
    for cycle in cycles:
        cycle_packets = [packet for packet in packets if packet.cycle == cycle]
        if not cycle_packets or not all(
            packet.status in {"done", "excepted"} for packet in cycle_packets
        ):
            continue
        joins = [packet for packet in cycle_packets if packet.packet_type == "coordinator-join"]
        if not joins:
            issues.append(
                _issue(
                    "G8",
                    f"cycle {cycle}: closed cycle missing coordinator-join packet",
                    packet_ids=[packet.id for packet in cycle_packets],
                    row_ids=_merged(cycle_packets, "row_ids"),
                )
            )
            continue
        for join in joins:
            evidence = _evidence_text(join)
            missing = [
                label
                for label, needle in (
                    ("capacity board evidence", "capacity board"),
                    ("smoke OK evidence", "smoke ok"),
                    ("handoff or next trigger", "next trigger"),
                )
                if needle not in evidence
            ]
            if (
                HANDOFF_REQUIRED_RE.search(evidence)
                and not HANDOFF_ARTIFACT_RE.search(evidence)
            ):
                missing.append("handoff artifact")
            if missing:
                issues.append(
                    _issue(
                        "G8",
                        f"{join.id}: missing " + ", ".join(missing),
                        packet_ids=[join.id],
                        row_ids=list(join.row_ids),
                    )
                )
    return issues


def _apply_exceptions(
    issues: list[dict[str, Any]],
    exceptions: list[ProtocolException],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for issue in issues:
        match = next(
            (
                exception
                for exception in exceptions
                if _exception_matches_issue(exception, issue)
            ),
            None,
        )
        if match:
            excepted = dict(issue)
            excepted["excepted_by"] = match.id
            out.append(excepted)
        else:
            out.append(issue)
    return out


def _validate_route_file(path: Path, report: CapacityReport) -> list[dict[str, Any]]:
    try:
        body = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [_issue("G7", f"{path.name}: unreadable route ({exc})")]

    issues: list[dict[str, Any]] = []
    name = path.name
    if "-coordinator-to-all-" not in name:
        issues.append(_issue("G7", f"{name}: route must be coordinator-to-all"))
    if "task-board" not in body.lower():
        issues.append(_issue("G7", f"{name}: route is missing task-board marker"))

    expected_ids = {packet.id for packet in report.packets}
    if not expected_ids:
        issues.append(_issue("G7", f"no capacity packets for wave {report.wave}"))
    named_ids = {packet_id for packet_id in expected_ids if packet_id in body}
    missing = sorted(expected_ids - named_ids)
    if missing:
        issues.append(
            _issue(
                "G7",
                "missing packet ids: " + ", ".join(missing),
                packet_ids=missing,
            )
        )

    if not re.search(r"(?im)^join condition\s*:", body):
        issues.append(_issue("G7", f"{name}: missing join condition"))

    forbidden = _forbidden_side_effects(body)
    if forbidden:
        issues.append(
            _issue(
                "G7",
                "forbidden side effect authorization: " + ", ".join(forbidden),
            )
        )
    return issues


def _forbidden_side_effects(body: str) -> list[str]:
    terms = {
        "push": r"\bpush\b|\bforce-push\b",
        "lock claim": r"\block claim\b|\block-claim\b|\bclaim lock\b",
        "paid API spend": r"\bpaid api spend\b|\bpaid-api spend\b",
        "pod spend": r"\bpod spend\b",
        "production generation": r"\bproduction generation\b",
    }
    auth = r"\b(authorizes?|authorized|allows?|grants?)\b"
    found: list[str] = []
    for line in body.splitlines():
        lowered = line.lower()
        normalized = lowered.strip().lstrip("-* ").strip()
        if normalized.startswith("no "):
            continue
        for label, pattern in terms.items():
            if re.search(auth, lowered) and re.search(pattern, lowered):
                if label not in found:
                    found.append(label)
    return found


def _exception_matches_issue(exception: ProtocolException, issue: dict[str, Any]) -> bool:
    if not exception.is_active or exception.bypassed_gate != issue.get("gate"):
        return False
    scope = exception.scope
    has_scoped_issue_value = False
    for issue_key, scope_key in (
        ("packet_ids", "packet_ids"),
        ("row_ids", "row_ids"),
        ("paths", "paths"),
    ):
        issue_values = set(issue.get(issue_key) or [])
        if not issue_values:
            continue
        has_scoped_issue_value = True
        scope_values = set(scope.get(scope_key) or [])
        if not issue_values <= scope_values:
            return False
    return has_scoped_issue_value


def _issue(
    gate: str,
    message: str,
    *,
    packet_ids: list[str] | None = None,
    row_ids: list[str] | None = None,
    paths: list[str] | None = None,
    lock_keys: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "gate": gate,
        "message": message,
        "packet_ids": packet_ids or [],
        "row_ids": row_ids or [],
        "paths": paths or [],
        "lock_keys": lock_keys or [],
    }


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _evidence_text(packet: Packet) -> str:
    return "\n".join(packet.done_evidence).lower()


def _display_path(path: Path) -> str:
    return path.as_posix()


def _merged(packets: list[Packet], field: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for packet in packets:
        for value in getattr(packet, field):
            if value not in seen:
                values.append(value)
                seen.add(value)
    return values
