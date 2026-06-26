#!/usr/bin/env python3
"""Read-only protocol effectiveness report for the four-seat process.

The command observes durable protocol evidence and emits a coordinator-facing
summary plus a structured JSON artifact. It never consumes mailbox cursors,
sends mailbox events, edits inventory, claims locks, or performs git writes.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from protocol_mailbox import COORDINATION_KINDS, SEATS
from status import collect_mailbox
import bus_unread  # de-degrade: real ref-bus unread for migrated (scalar) cursors

INVENTORY_COLS = (
    "id",
    "subsystem",
    "file:line",
    "severity",
    "priority",
    "fail-mode",
    "repro",
    "xfail-pin",
    "lane-owner",
    "shared-lock",
    "wave",
    "status",
    "verifier",
    "notes",
)
CLASSIFICATIONS = {
    "verified_progress",
    "blocked_progress",
    "coordination_only",
    "no_op_evidence",
    "stale_or_conflicted",
    "unknown",
}
MAILBOX_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-"
    r"(?P<sender>[A-Za-z0-9_]+)-to-(?P<recipient>[A-Za-z0-9_]+)-"
    r"(?P<kind>.+)\.md$"
)
GO_RE = re.compile(r"\bGO\b|verification-report.*\bPASS\b", re.IGNORECASE | re.DOTALL)
VERDICT_RE = re.compile(r"^\s*(?:VERDICT|Verdict)\s*:\s*(?P<value>.+?)\s*$", re.MULTILINE)
FAIL_RE = re.compile(r"\bFAIL\b|\bNO[- ]GO\b|\bBLOCKED\b|\bNITS\b", re.IGNORECASE)
NO_OP_RE = re.compile(r"\b(no[- ]op|idle|standby|no current work|correctly idle)\b", re.IGNORECASE)
STALE_RE = re.compile(r"\b(stale|conflict|contradict|drift|race|unread split)\b", re.IGNORECASE)
EVIDENCE_RE = re.compile(
    r"\b(passed|xfailed|verification-report|evidence|operator\d?\s+GO|Lane V GO|impl.?verifier)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MailboxFilename:
    filename: str
    timestamp: str
    sender: str
    recipient: str
    kind: str
    parse_error: str | None = None


@dataclass(frozen=True)
class Classification:
    category: str
    source: str
    id: str
    reason: str
    confidence: str = "medium"
    details: dict[str, Any] | None = None


def run(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    """Run a command with the shared index, returning output without raising."""
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
    return Path(__file__).resolve().parent.parent


def now_local() -> datetime:
    return datetime.now().astimezone()


def normalize_ts(ts: str) -> str:
    """Normalize ISO-ish mailbox timestamps to filename dash form."""
    return ts.strip().replace(":", "-")


def parse_mailbox_filename(filename: str) -> MailboxFilename:
    """Parse a mailbox event filename, failing closed on unexpected shape."""
    name = Path(filename).name
    match = MAILBOX_RE.match(name)
    if not match:
        return MailboxFilename(name, "", "", "", "unknown", "unparsable mailbox filename")
    return MailboxFilename(
        filename=name,
        timestamp=match.group("ts"),
        sender=match.group("sender"),
        recipient=match.group("recipient"),
        kind=match.group("kind"),
    )


def addressed_to(event: MailboxFilename, seat: str) -> bool:
    return event.recipient in (seat, "all")


def parse_mailbox_event(filename: str, text: str) -> Classification:
    """Classify one mailbox event from filename + body text."""
    event = parse_mailbox_filename(filename)
    if event.parse_error:
        return Classification("unknown", "mailbox", event.filename, event.parse_error, "high")

    body = text or ""
    ident = event.filename
    details = {
        "timestamp": event.timestamp,
        "sender": event.sender,
        "recipient": event.recipient,
        "kind": event.kind,
    }
    if event.kind == "verification-report":
        verdict = verification_report_verdict(body)
        if verdict == "go":
            return Classification(
                "verified_progress",
                "mailbox",
                ident,
                "operator verification-report contains a GO/PASS signal",
                "high",
                details,
            )
        if verdict == "blocked":
            return Classification(
                "blocked_progress",
                "mailbox",
                ident,
                "verification-report contains FAIL/NITS/BLOCKED evidence",
                "high",
                details,
            )
        return Classification(
            "unknown",
            "mailbox",
            ident,
            "verification-report lacks an unambiguous GO or FAIL signal",
            "high",
            details,
        )
    if STALE_RE.search(body):
        return Classification(
            "stale_or_conflicted",
            "mailbox",
            ident,
            "event body reports stale, drift, conflict, race, or unread split evidence",
            "medium",
            details,
        )
    if event.kind == "verify-request":
        return Classification(
            "blocked_progress",
            "mailbox",
            ident,
            "verify-request indicates work is pending operator GO",
            "medium",
            details,
        )
    if event.kind == "status" and NO_OP_RE.search(body):
        return Classification(
            "no_op_evidence",
            "mailbox",
            ident,
            "status event reports no-op, idle, or standby evidence",
            "medium",
            details,
        )
    if NO_OP_RE.search(body):
        return Classification(
            "no_op_evidence",
            "mailbox",
            ident,
            "event body reports no-op, idle, or standby evidence",
            "low",
            details,
        )
    if event.kind in COORDINATION_KINDS or event.kind.startswith("verify-"):
        return Classification(
            "coordination_only",
            "mailbox",
            ident,
            f"mailbox kind '{event.kind}' is coordination/status evidence, not correctness proof",
            "medium",
            details,
        )
    return Classification(
        "unknown",
        "mailbox",
        ident,
        f"mailbox kind '{event.kind}' is not classified",
        "high",
        details,
    )


def verification_report_verdict(text: str) -> str:
    """Return go, blocked, or unknown for a verification-report body."""
    for match in VERDICT_RE.finditer(text or ""):
        value = match.group("value").strip().lower()
        if re.search(r"\b(no[- ]go|fail|blocked|nits)\b", value):
            return "blocked"
        if re.search(r"\b(go|pass)\b", value):
            return "go"
    if FAIL_RE.search(text or ""):
        return "blocked"
    if GO_RE.search(text or ""):
        return "go"
    return "unknown"


def parse_inventory_rows(text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Parse remediation inventory Markdown rows with fail-closed errors."""
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells == list(INVENTORY_COLS) or set(cells[0] or "-") <= {"-"}:
            continue
        if len(cells) != len(INVENTORY_COLS):
            if len(cells) > 1:
                errors.append(f"line {lineno}: expected {len(INVENTORY_COLS)} cells, got {len(cells)}")
            continue
        row = dict(zip(INVENTORY_COLS, cells))
        if not row["id"] or row["id"] == "id":
            continue
        rows.append(row)
    return rows, errors


def classify_inventory_row(row: dict[str, str]) -> Classification:
    """Classify a row without treating status=verified alone as proof."""
    row_id = row.get("id", "(missing-id)")
    status = row.get("status", "").lower()
    verifier = row.get("verifier", "")
    notes = row.get("notes", "")
    evidence_text = f"{verifier}\n{notes}"
    details = {
        "wave": row.get("wave"),
        "status": row.get("status"),
        "severity": row.get("severity"),
        "lane_owner": row.get("lane-owner"),
    }

    if status == "verified":
        verdict = verification_report_verdict(evidence_text)
        if verdict == "blocked":
            return Classification(
                "blocked_progress",
                "inventory",
                row_id,
                "verified row includes NO-GO/FAIL/BLOCKED evidence",
                "high",
                details,
            )
        if verdict == "go" and EVIDENCE_RE.search(evidence_text):
            return Classification(
                "verified_progress",
                "inventory",
                row_id,
                "verified row includes operator GO and evidence signals",
                "medium",
                details,
            )
        return Classification(
            "unknown",
            "inventory",
            row_id,
            "status=verified without sufficient operator GO/evidence signal",
            "high",
            details,
        )
    if status in {"open", "fixing", "fixed", "provisional", "attested"}:
        reason = {
            "open": "row remains open",
            "fixing": "row is in-flight",
            "fixed": "row is fixed but missing operator GO",
            "provisional": "provisional row is not gate-clearable",
            "attested": "attested row needs explicit exemption before gate success",
        }.get(status, "row is not verified")
        return Classification("blocked_progress", "inventory", row_id, reason, "medium", details)
    return Classification(
        "unknown",
        "inventory",
        row_id,
        f"inventory status '{row.get('status', '')}' is unrecognized",
        "high",
        details,
    )


def parse_gate_output(stdout: str, stderr: str, exit_code: int) -> dict[str, Any]:
    """Parse scripts/wave_gate_check.py output into conservative counters."""
    text = "\n".join(part for part in (stdout, stderr) if part)
    report: dict[str, Any] = {
        "exit_code": exit_code,
        "verdict": "UNKNOWN",
        "counts": {},
        "gate_rows": None,
        "executable_selectors": None,
        "product_oracle_blockers": [],
        "pytest_exit": None,
        "pytest_command": "",
        "failed_tests": [],
        "parse_errors": [],
        "raw_tail": "\n".join(text.splitlines()[-40:]),
    }
    first = re.search(r"Wave\s+\d+\s+gate:\s+(?P<verdict>\w+)\s+counts=(?P<counts>\{.*?\})", text)
    if first:
        report["verdict"] = first.group("verdict")
        try:
            counts = ast.literal_eval(first.group("counts"))
            if isinstance(counts, dict):
                report["counts"] = counts
            else:
                report["parse_errors"].append("gate counts did not parse to a dict")
        except (SyntaxError, ValueError) as exc:
            report["parse_errors"].append(f"could not parse gate counts: {exc}")
    else:
        report["parse_errors"].append("could not parse gate verdict line")

    shape = re.search(r"gate rows:\s+(?P<rows>\d+);\s+executable selectors:\s+(?P<selectors>\d+)", text)
    if shape:
        report["gate_rows"] = int(shape.group("rows"))
        report["executable_selectors"] = int(shape.group("selectors"))
    for match in re.finditer(r"PRODUCT ORACLE BLOCKER:\s+(?P<msg>.+)", text):
        report["product_oracle_blockers"].append(match.group("msg").strip())
    pytest_match = re.search(r"PYTEST:\s+exit=(?P<exit>\d+)\s+command=(?P<command>.+)", text)
    if pytest_match:
        report["pytest_exit"] = int(pytest_match.group("exit"))
        report["pytest_command"] = pytest_match.group("command").strip()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAILED "):
            report["failed_tests"].append(stripped)
    return report


def classify_gate_report(report: dict[str, Any], wave: int) -> list[Classification]:
    classes: list[Classification] = []
    details = {
        "wave": wave,
        "exit_code": report.get("exit_code"),
        "verdict": report.get("verdict"),
    }
    if report.get("parse_errors"):
        for err in report["parse_errors"]:
            classes.append(Classification("unknown", "gate", f"wave-{wave}", err, "high", details))
    if report.get("product_oracle_blockers"):
        classes.append(
            Classification(
                "blocked_progress",
                "gate",
                f"wave-{wave}-product-oracle",
                "wave gate reports missing or invalid product-oracle artifact",
                "high",
                {"blockers": report["product_oracle_blockers"]},
            )
        )
    if report.get("pytest_exit") not in (None, 0):
        classes.append(
            Classification(
                "blocked_progress",
                "gate",
                f"wave-{wave}-pytest",
                "wave gate executable pin suite is still red",
                "high",
                {
                    "pytest_exit": report.get("pytest_exit"),
                    "failed_tests": report.get("failed_tests", [])[:20],
                },
            )
        )
    if report.get("verdict") == "MET":
        classes.append(
            Classification(
                "verified_progress",
                "gate",
                f"wave-{wave}",
                "wave gate reports MET; still requires protocol evidence for row-level claims",
                "medium",
                details,
            )
        )
    elif report.get("verdict") == "UNMET" and not classes:
        classes.append(
            Classification(
                "blocked_progress",
                "gate",
                f"wave-{wave}",
                "wave gate reports UNMET",
                "medium",
                details,
            )
        )
    return classes


def parse_commit(raw: str) -> dict[str, Any]:
    """Parse a NUL-separated git log line."""
    parts = raw.split("\x00")
    if len(parts) != 3:
        return {"hash": "", "timestamp": None, "subject": raw, "parse_error": "unparsable git log line"}
    short, epoch, subject = parts
    try:
        timestamp = datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    except ValueError:
        timestamp = None
    return {"hash": short, "timestamp": timestamp, "subject": subject, "parse_error": None}


def classify_commit(commit: dict[str, Any]) -> Classification:
    subject = str(commit.get("subject", ""))
    ident = str(commit.get("hash") or subject or "(unknown-commit)")
    details = {"subject": subject, "timestamp": commit.get("timestamp")}
    if commit.get("parse_error"):
        return Classification("unknown", "git", ident, str(commit["parse_error"]), "high", details)
    lowered = subject.lower()
    if lowered.startswith("fix("):
        return Classification(
            "blocked_progress",
            "git",
            ident,
            "fix commit is attempted progress; row remains unproven until operator GO/gate evidence",
            "low",
            details,
        )
    if lowered.startswith("coord(verify)") or "verification-report" in lowered:
        return Classification(
            "coordination_only",
            "git",
            ident,
            "verification-related commit subject is coordination evidence, not operator GO proof",
            "medium",
            details,
        )
    if lowered.startswith("docs(handoff)") or "handoff" in lowered or lowered.startswith("coord("):
        return Classification(
            "coordination_only",
            "git",
            ident,
            "commit subject is handoff/coordination protocol movement",
            "medium",
            details,
        )
    if lowered.startswith("docs(spec)") or lowered.startswith("docs("):
        return Classification(
            "coordination_only",
            "git",
            ident,
            "documentation/spec commit is planning context, not verified row progress",
            "medium",
            details,
        )
    return Classification("unknown", "git", ident, "commit subject not classified", "low", details)


def mailbox_cursor_unread(
    seat: str,
    cursor: str,
    events: list[MailboxFilename],
    repo_root: Path | None = None,
) -> tuple[int, list[str]]:
    """Return unread count and filenames without mutating the cursor.

    For a migrated (scalar) cursor, unread lives on the signed ref-bus, not the legacy
    ISO filenames (the lexical `event.timestamp > cursor` compare mis-counts a scalar).
    With *repo_root* given, return the REAL ref-bus unread (count + descriptors) — ADR-062;
    without it (pure call) return (0, []), the legacy empty. A bus ERROR also yields (0, [])
    here: the report's authoritative 'reported_unread' (from status) carries the sentinel.
    """
    if cursor and cursor.strip().isdigit():
        if repo_root is None:
            return 0, []
        evs = bus_unread.bus_unread_events(repo_root, seat)
        if evs is None:
            return 0, []
        return len(evs), [bus_unread.format_unread(ev) for ev in evs]
    cursor_norm = normalize_ts(cursor)
    unread = [
        event.filename
        for event in events
        if not event.parse_error and addressed_to(event, seat) and event.timestamp > cursor_norm
    ]
    return len(unread), unread


def classify_seat_utilization(
    seat: str,
    unread_count: int,
    recent_sent: list[Classification],
    heartbeat_age_seconds: float | None,
) -> dict[str, Any]:
    """Conservatively classify one seat's current utilization from evidence."""
    seat_sent = [
        item
        for item in recent_sent
        if item.details and item.details.get("sender") == seat
    ]
    latest_category = seat_sent[-1].category if seat_sent else "unknown"
    if heartbeat_age_seconds is not None and heartbeat_age_seconds > 15 * 60:
        state = "stale"
    elif unread_count > 0:
        state = "unread"
    elif latest_category == "verified_progress":
        state = "verification"
    elif latest_category == "no_op_evidence":
        state = "no-op"
    elif latest_category == "coordination_only":
        state = "routing-only"
    else:
        state = "unknown"
    return {
        "seat": seat,
        "state": state,
        "unread": unread_count,
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "latest_sent_category": latest_category,
    }


def classify_unknown(source: str, ident: str, reason: str) -> Classification:
    """Small pure helper for fail-closed unknown classifications."""
    return Classification("unknown", source, ident, reason, "high")


def safe_read(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return "", str(exc)


def recent_mailbox_events(root: Path, limit: int) -> list[tuple[MailboxFilename, str]]:
    sent = root / "coordination" / "mailbox" / "sent"
    if not sent.exists():
        return []
    paths = sorted(p for p in sent.glob("*.md") if p.is_file())[-limit:]
    out: list[tuple[MailboxFilename, str]] = []
    for path in paths:
        text, err = safe_read(path)
        parsed = parse_mailbox_filename(path.name)
        if err:
            parsed = MailboxFilename(path.name, "", "", "", "unknown", err)
        out.append((parsed, text))
    return out


def heartbeat_age(root: Path, seat: str, generated_at: datetime) -> float | None:
    path = root / "coordination" / "presence" / f"{seat}-heartbeat.ts"
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    except OSError:
        return None
    return max(0.0, (generated_at - mtime).total_seconds())


def collect_locks(root: Path) -> list[str]:
    lock_dir = root / "coordination" / "locks"
    if not lock_dir.exists():
        return []
    return sorted(p.name for p in lock_dir.glob("*") if p.is_file() and p.name != ".gitkeep")


def collect_handoff_drafts(root: Path) -> dict[str, Any]:
    committed_code, committed_out, _ = run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", "docs"],
        root,
    )
    committed = [
        line
        for line in committed_out.splitlines()
        if Path(line).name.startswith("HANDOFF-") and line.endswith(".md")
    ] if committed_code == 0 else []
    status_code, status_out, _ = run(["git", "status", "--short", "--", "docs"], root)
    dirty = [
        line
        for line in status_out.splitlines()
        if "HANDOFF-" in line
    ] if status_code == 0 else []
    return {"committed_count": len(committed), "dirty": dirty}


def route_to_go_seconds(events: list[tuple[MailboxFilename, str]]) -> list[dict[str, Any]]:
    """Measure request/route to GO report latency where evidence is pairable."""
    requests: list[MailboxFilename] = []
    samples: list[dict[str, Any]] = []
    for event, text in events:
        if event.parse_error:
            continue
        if event.kind == "verify-request" or (
            event.sender == "coordinator" and event.kind == "coordination"
        ):
            requests.append(event)
            continue
        if event.kind != "verification-report" or verification_report_verdict(text) != "go":
            continue
        candidates = [
            req
            for req in requests
            if req.timestamp < event.timestamp
            and (req.recipient in (event.sender, "all") or req.sender == "coordinator")
        ]
        if not candidates:
            continue
        start = candidates[-1]
        start_dt = mailbox_ts_to_datetime(start.timestamp)
        end_dt = mailbox_ts_to_datetime(event.timestamp)
        if not start_dt or not end_dt:
            continue
        samples.append(
            {
                "request": start.filename,
                "report": event.filename,
                "seconds": int((end_dt - start_dt).total_seconds()),
            }
        )
    return samples


def mailbox_ts_to_datetime(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def category_counts(classifications: list[Classification]) -> dict[str, int]:
    counts = {name: 0 for name in sorted(CLASSIFICATIONS)}
    for item in classifications:
        counts[item.category] = counts.get(item.category, 0) + 1
    return counts


def blocked_reason_counts(classifications: list[Classification]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in classifications:
        reason = item.reason.lower()
        if item.category == "unknown":
            key = "parse error"
        elif "product-oracle" in reason or "product oracle" in reason:
            key = "product oracle"
        elif "pin" in reason or "pytest" in reason or "gate" in reason:
            key = "open pins"
        elif "missing operator go" in reason or "pending operator go" in reason:
            key = "missing GO"
        elif re.search(r"\block\b", reason):
            key = "lock"
        elif "push" in reason:
            key = "push"
        elif "spend" in reason:
            key = "spend"
        elif "unread split" in reason or "unread" in reason:
            key = "unread split"
        elif item.category == "blocked_progress":
            key = "blocked progress"
        else:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_recommendations(metrics: dict[str, Any], gate: dict[str, Any]) -> list[str]:
    recs: list[str] = []
    blocked = metrics.get("blocked_reason_counts", {})
    seat_states = {
        item["seat"]: item["state"]
        for item in metrics.get("seat_utilization", [])
    }
    if blocked.get("product oracle", 0) or gate.get("product_oracle_blockers"):
        recs.append("Route product-oracle artifact work before more status-only handoffs.")
    if blocked.get("open pins", 0):
        recs.append("Prioritize the red executable pin clusters before declaring gate movement.")
    if any(state == "unread" for state in seat_states.values()):
        recs.append("Resolve unread splits before claiming all seats received the latest route.")
    if metrics.get("duplicate_verification_count", 0):
        recs.append("Avoid another verification pass unless it states a genuinely new question.")
    if metrics.get("verified_rows_delta", 0) == 0 and metrics.get("mailbox_events_per_verified_row", 0):
        recs.append("Reduce coordination churn by routing one concrete blocker per active seat.")
    if not recs:
        recs.append("Use the latest verified blocker mix to build the next capacity board.")
    return recs


def duplicate_verification_count(classifications: list[Classification]) -> int:
    reports: dict[str, int] = {}
    for item in classifications:
        if item.source != "mailbox" or not item.details:
            continue
        if item.details.get("kind") != "verification-report":
            continue
        text_key = item.reason
        reports[text_key] = reports.get(text_key, 0) + 1
    return sum(max(0, count - 1) for count in reports.values())


def collect_report(root: Path, wave: int, commit_limit: int, event_limit: int, gate_timeout: int) -> dict[str, Any]:
    generated = now_local()
    generated_at = generated.isoformat(timespec="seconds")
    code, head, _ = run(["git", "log", "-1", "--format=%h %s"], root)
    if code != 0 or not head:
        head = "(unknown)"

    mailbox_pairs = recent_mailbox_events(root, event_limit)
    mailbox_classifications = [
        parse_mailbox_event(event.filename, text) if not event.parse_error else classify_unknown("mailbox", event.filename, event.parse_error)
        for event, text in mailbox_pairs
    ]

    inventory_text, inventory_error = safe_read(root / "docs" / "REMEDIATION-INVENTORY.md")
    inventory_rows, inventory_errors = parse_inventory_rows(inventory_text) if not inventory_error else ([], [inventory_error])
    wave_rows = [row for row in inventory_rows if row.get("wave") == str(wave)]
    inventory_classifications = [classify_inventory_row(row) for row in wave_rows]
    inventory_classifications.extend(
        classify_unknown("inventory", f"parse-error-{idx}", err)
        for idx, err in enumerate(inventory_errors, start=1)
    )

    gate_code, gate_out, gate_err = run(
        [sys.executable, "scripts/wave_gate_check.py", str(wave)],
        root,
        timeout=gate_timeout,
    )
    gate = parse_gate_output(gate_out, gate_err, gate_code)
    gate["command"] = shlex.join([sys.executable, "scripts/wave_gate_check.py", str(wave)])
    gate_classifications = classify_gate_report(gate, wave)

    log_code, log_out, log_err = run(
        ["git", "log", f"-{commit_limit}", "--format=%h%x00%ct%x00%s"],
        root,
    )
    commits = [parse_commit(line) for line in log_out.splitlines()] if log_code == 0 else [
        {"hash": "", "timestamp": None, "subject": log_err or "git log failed", "parse_error": "git log failed"}
    ]
    commit_classifications = [classify_commit(commit) for commit in commits]

    classifications = (
        mailbox_classifications
        + inventory_classifications
        + gate_classifications
        + commit_classifications
    )
    counts = category_counts(classifications)
    verified_progress = max(
        0,
        sum(1 for item in inventory_classifications if item.category == "verified_progress"),
    )
    mailbox_event_count = len(mailbox_pairs)
    handoffs = collect_handoff_drafts(root)
    mailbox_data = collect_mailbox(root)
    parsed_events = [event for event, _ in mailbox_pairs]
    unread_splits: dict[str, Any] = {}
    seat_utilization: list[dict[str, Any]] = []
    for seat in SEATS:
        cursor = str(mailbox_data.get(f"mailbox_{seat}_cursor", ""))
        computed_unread, unread_names = mailbox_cursor_unread(seat, cursor, parsed_events, repo_root=root)
        reported_unread = mailbox_data.get(f"mailbox_{seat}_unread", computed_unread)
        unread_splits[seat] = {
            "cursor": cursor,
            "reported_unread": reported_unread,
            "sampled_unread": computed_unread,
            "sampled_unread_events": unread_names,
        }
        try:
            unread_count = int(reported_unread)
        except (TypeError, ValueError):
            unread_count = computed_unread
        seat_utilization.append(
            classify_seat_utilization(
                seat,
                unread_count,
                mailbox_classifications,
                heartbeat_age(root, seat, generated),
            )
        )

    route_samples = route_to_go_seconds(mailbox_pairs)
    avg_route_to_go = (
        sum(sample["seconds"] for sample in route_samples) / len(route_samples)
        if route_samples
        else None
    )
    blocked_counts = blocked_reason_counts(classifications)
    locks = collect_locks(root)
    if locks:
        blocked_counts["lock"] = blocked_counts.get("lock", 0) + len(locks)

    metrics: dict[str, Any] = {
        "verified_rows_delta": verified_progress,
        "wave_gate_blocker_delta": None,
        "route_to_go_seconds": route_samples,
        "route_to_go_seconds_avg": avg_route_to_go,
        "mailbox_events_per_verified_row": (
            mailbox_event_count / verified_progress if verified_progress else mailbox_event_count
        ),
        "handoff_commits_per_verified_row": (
            handoffs["committed_count"] / verified_progress if verified_progress else handoffs["committed_count"]
        ),
        "seat_utilization": seat_utilization,
        "duplicate_verification_count": duplicate_verification_count(classifications),
        "stale_claim_count": counts.get("stale_or_conflicted", 0),
        "blocked_reason_counts": blocked_counts,
        "classification_counts": counts,
        "unread_splits": unread_splits,
        "active_locks": locks,
        "handoffs": handoffs,
    }
    headline = (
        f"{verified_progress} Wave {wave} rows have operator-GO evidence in inventory sample; "
        f"{counts.get('coordination_only', 0)} coordination-only classifications; "
        f"Wave {wave} gate {gate.get('verdict', 'UNKNOWN')}."
    )
    summary = {
        "headline": headline,
        "gate_verdict": gate.get("verdict", "UNKNOWN"),
        "classification_counts": counts,
        "top_blockers": blocked_counts,
    }
    return {
        "artifact_kind": "protocol-effectiveness",
        "wave": wave,
        "generated_at": generated_at,
        "head": head,
        "summary": summary,
        "metrics": metrics,
        "classifications": [asdict(item) for item in classifications],
        "recommendations": build_recommendations(metrics, gate),
        "evidence": {
            "gate": gate,
            "recent_commits": commits,
            "mailbox_event_limit": event_limit,
            "inventory_rows_for_wave": len(wave_rows),
        },
    }


def artifact_path(root: Path, generated_at: str) -> Path:
    stamp = generated_at.replace(":", "-")
    return root / "logs" / f"protocol-effectiveness-{stamp}.json"


def write_artifact(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_summary(report: dict[str, Any], output: Path | None) -> str:
    summary = report["summary"]
    metrics = report["metrics"]
    lines = [
        "# Protocol Effectiveness Report",
        f"- wave: {report['wave']}",
        f"- generated_at: {report['generated_at']}",
        f"- head: {report['head']}",
        f"- artifact: {output if output else '(stdout-only; no artifact written)'}",
        f"- headline: {summary['headline']}",
        f"- blockers: {json.dumps(metrics['blocked_reason_counts'], sort_keys=True)}",
        "- seat utilization:",
    ]
    for seat in metrics["seat_utilization"]:
        lines.append(f"  - {seat['seat']}: {seat['state']} (unread={seat['unread']})")
    lines.append("- recommendations:")
    for rec in report["recommendations"]:
        lines.append(f"  - {rec}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a read-only protocol effectiveness report.",
    )
    parser.add_argument("--wave", type=int, default=2)
    parser.add_argument("--commits", type=int, default=25)
    parser.add_argument("--mailbox-events", type=int, default=120)
    parser.add_argument("--gate-timeout", type=int, default=300)
    parser.add_argument(
        "--stdout-only",
        action="store_true",
        help="Print the Markdown summary without writing the JSON artifact.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON artifact path. Ignored when --stdout-only is set.",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    report = collect_report(root, args.wave, args.commits, args.mailbox_events, args.gate_timeout)
    output: Path | None = None
    if not args.stdout_only:
        output = args.output if args.output else artifact_path(root, report["generated_at"])
        if not output.is_absolute():
            output = root / output
        write_artifact(output, report)
    print(render_summary(report, output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
