#!/usr/bin/env python3
"""Coordination-state linter — protocol v6.0.

Machine-checks the director↔operator coordination invariants that previously
lived only in seat discipline and drifted (the 2026-06-10 three-way cursor
divergence: seen/*.txt vs event footers vs commit messages). Mirrors the
check_doc_claims.py verifier pattern.

Public API
----------
CoordIssue                       dataclass for a single finding
KNOWN_KINDS                      accepted event-kind tokens (filename position)
run(coord_root, since, now)  ->  list[CoordIssue]
main(argv=None)              ->  int   (exit 0 = no FATAL, 1 = FATAL present)

Severities
----------
FATAL    — structurally broken state (unparseable/future cursor, filename
           convention violation, self-addressed event). Exit-code-affecting.
ADVISORY — drift that needs a human eye but doesn't break the machinery
           (orphan cursor, missing/mismatched **When:** envelope, novel kind).
INFO     — unread-count report (always emitted, never a failure).

Also hard-fails coordinator "All-Seat Handoff" artifacts that do not cite real
live-seat mailbox/handoff artifacts for all four seats. Subagent reports are
advisory evidence, not live-seat protocol authority.

The envelope checks are gated on --since (default 2026-06-11, the v6.0
adoption date): pre-adoption events used a YAML-frontmatter format and are
exempt. Filename checks are NOT gated — all 270 legacy events were verified
conforming at adoption time.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from protocol_mailbox import KNOWN_KINDS, SEATS
from status import count_unread

# 4-seat protocol (two director-operator pairs). `all` is a broadcast TARGET
# only — NOT a role (no seen/all.txt); every real seat counts `-to-all-` events
# as addressed to it (see _check_cursors orphan test + status.count_unread).
# Seat names stay aligned with coordination/bin/{send-event,consume-events}
# and status._EVENT_RE; mailbox kinds come from protocol_mailbox.KNOWN_KINDS.
ROLES = SEATS

# `coordinator`/`coordinator2` are first-class <to> targets in the event-name regex
# above (Slice 2.5 §4b). They are NOT yet in ROLES and have no seen cursor — that
# reconciliation (widen ROLES + seed seen/coordinator{,2}.txt) lands in the Slice 2.5
# cursor/ROLES task (Task 5), which removes the remaining send-only special-casing.
_EVENT_NAME_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-"
    r"(?P<frm>director|director2|operator|operator2|coordinator|coordinator2)"
    r"-to-(?P<to>director|director2|operator|operator2|coordinator|coordinator2|all)-"
    r"(?P<kind>[a-z0-9-]+)\.md$"
)

_CURSOR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# A commit whose entire changeset is seen/*.txt is a standalone cursor advance —
# cursor advances should ride the next substantive commit (capacity audit
# wf_6be2ee18-f4b, lever #5). Detected opt-in via run(git_root=...).
_SEEN_ONLY_RE = re.compile(r"^coordination/mailbox/seen/[^/]+\.txt$")

_WHEN_RE = re.compile(r"\*\*When:\*\*\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")

_ALL_SEAT_HANDOFF_RE = re.compile(r"^#{1,3}\s+All[- ]Seat Handoff\b", re.I | re.M)
_PENDING_LIVE_SEAT_MARKERS = (
    "does not claim that the four live seats completed handoffs",
    "live-seat work still owed",
    "still need to publish their own seat-owned",
    "real live-seat artifacts to land",
)
_LIVE_SEAT_ARTIFACT_RES = {
    role: (
        re.compile(rf"\bdocs/HANDOFF-{role}-\d{{4}}-\d{{2}}-\d{{2}}", re.I),
        re.compile(
            rf"\bcoordination/mailbox/sent/\d{{4}}-\d{{2}}-\d{{2}}T"
            rf"\d{{2}}-\d{{2}}-\d{{2}}Z-{role}-to-"
            rf"(?:director|director2|operator|operator2|coordinator|coordinator2|all)-[a-z0-9-]+\.md\b",
            re.I,
        ),
    )
    for role in ROLES
}


@dataclass
class CoordIssue:
    path: str
    kind: str        # cursor_missing | cursor_unparseable | cursor_future |
                     # cursor_orphan | bad_filename | self_addressed |
                     # missing_when | when_mismatch | unknown_kind | unread
    severity: str    # FATAL | ADVISORY | INFO
    message: str


def _dash(ts: str) -> str:
    return ts.replace(":", "-")


def _colon(ts_dash: str) -> str:
    # 2026-06-12T10-00-00Z -> 2026-06-12T10:00:00Z (date part untouched)
    return ts_dash[:11] + ts_dash[11:].replace("-", ":")


def _event_names(coord_root: Path, subdir: str = "sent") -> list[str]:
    d = coord_root / "mailbox" / subdir
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.name.endswith(".md"))


def _check_cursors(coord_root: Path, now: str,
                   names: list[str]) -> list[CoordIssue]:
    issues: list[CoordIssue] = []
    for role in ROLES:
        cf = coord_root / "mailbox" / "seen" / f"{role}.txt"
        rel = f"mailbox/seen/{role}.txt"
        if not cf.exists():
            issues.append(CoordIssue(rel, "cursor_missing", "FATAL",
                                     f"{role} cursor file missing"))
            continue
        cur = cf.read_text().strip()
        if not _CURSOR_RE.match(cur):
            issues.append(CoordIssue(rel, "cursor_unparseable", "FATAL",
                                     f"{role} cursor not an ISO UTC timestamp: {cur!r}"))
            continue
        if cur > now:
            issues.append(CoordIssue(rel, "cursor_future", "FATAL",
                                     f"{role} cursor {cur} is in the future (now {now})"))
            continue
        # The watermark should be the timestamp of a real event addressed to
        # this role — in sent/ OR archive/ (events move there after
        # consumption). Older-than-everything is also allowed; anything else
        # that matches no event is a hand-typed orphan.
        all_names = names + _event_names(coord_root, "archive")
        addressed = [m.group("ts") for m in map(_EVENT_NAME_RE.match, all_names)
                     if m and m.group("to") in (role, "all")]
        cur_dash = _dash(cur)
        if addressed and cur_dash not in addressed and cur_dash > min(addressed):
            issues.append(CoordIssue(
                rel, "cursor_orphan", "ADVISORY",
                f"{role} cursor {cur} matches no event addressed to {role}"))
    return issues


def _check_events(coord_root: Path, since: str,
                  names: list[str]) -> list[CoordIssue]:
    issues: list[CoordIssue] = []
    sent = coord_root / "mailbox" / "sent"
    for name in names:
        rel = f"mailbox/sent/{name}"
        m = _EVENT_NAME_RE.match(name)
        if not m:
            issues.append(CoordIssue(rel, "bad_filename", "FATAL",
                                     "filename violates <ts>-<from>-to-<to>-<kind>.md"))
            continue
        if m.group("frm") == m.group("to"):
            issues.append(CoordIssue(rel, "self_addressed", "FATAL",
                                     f"event addressed to its own sender ({m.group('frm')})"))
        if m.group("kind") not in KNOWN_KINDS:
            issues.append(CoordIssue(rel, "unknown_kind", "ADVISORY",
                                     f"kind {m.group('kind')!r} not in KNOWN_KINDS"))
        if m.group("ts") < since:        # pre-adoption: envelope exempt
            continue
        text = (sent / name).read_text(errors="replace")
        when = _WHEN_RE.search(text)
        if not when:
            issues.append(CoordIssue(rel, "missing_when", "ADVISORY",
                                     "no '**When:** <ISO-UTC>' envelope line"))
        elif _dash(when.group(1)) != m.group("ts"):
            issues.append(CoordIssue(
                rel, "when_mismatch", "ADVISORY",
                f"**When:** {when.group(1)} != filename ts {_colon(m.group('ts'))}"))
    return issues


def _unread_report(coord_root: Path, names: list[str]) -> list[CoordIssue]:
    issues: list[CoordIssue] = []
    for role in ROLES:
        cf = coord_root / "mailbox" / "seen" / f"{role}.txt"
        if not cf.exists():
            continue
        cur = cf.read_text().strip()
        n = count_unread(cur, names, role)
        issues.append(CoordIssue(f"mailbox/seen/{role}.txt", "unread", "INFO",
                                 f"{role}: {n} unread event(s)"))
    return issues


def _check_standalone_cursor_commits(git_root, n: int = 30) -> list[CoordIssue]:
    """ADVISORY: flag recent commits whose entire changeset is seen/*.txt.

    Standalone cursor-only commits inflate coordination overhead — the cursor
    advance should ride the next substantive commit (capacity audit
    wf_6be2ee18-f4b, lever #5). Best-effort + opt-in: returns [] if git is
    unavailable or git_root is not a repo. Never raises.
    """
    issues: list[CoordIssue] = []
    try:
        log = subprocess.run(["git", "log", "--format=%h", f"-{n}"],
                             cwd=str(git_root), capture_output=True, text=True, timeout=5)
        if log.returncode != 0:
            return issues
        for sha in log.stdout.split():
            dt = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "-r", "--root", "--name-only", sha],
                cwd=str(git_root), capture_output=True, text=True, timeout=5)
            files = [f for f in dt.stdout.splitlines() if f.strip()]
            if files and all(_SEEN_ONLY_RE.match(f) for f in files):
                issues.append(CoordIssue(
                    "coordination/mailbox/seen/", "standalone_cursor_commit", "ADVISORY",
                    f"commit {sha} changes only seen/*.txt — fold cursor advances into "
                    f"the next substantive commit (lever #5)"))
    except Exception:
        pass
    return issues


def _has_live_seat_artifact(text: str, role: str) -> bool:
    return any(rx.search(text) for rx in _LIVE_SEAT_ARTIFACT_RES[role])


def _check_coordinator_handoff_theater(docs_root: Path | str | None) -> list[CoordIssue]:
    """FATAL: coordinator cannot substitute helper output for live-seat handoffs.

    A coordinator artifact may route all seats, and it may record that live-seat
    handoffs are still owed. But if it presents an "All-Seat Handoff" as a
    completed aggregate, it must cite real live-seat mailbox or handoff artifacts
    for all four seats. Spawned subagent reports are advisory evidence only.
    """
    if docs_root is None:
        return []
    docs_root = Path(docs_root)
    if not docs_root.is_dir():
        return []

    issues: list[CoordIssue] = []
    for path in sorted(docs_root.glob("HANDOFF-coordinator-*.md")):
        text = path.read_text(errors="replace")
        lower = text.lower()
        if not _ALL_SEAT_HANDOFF_RE.search(text):
            continue
        if any(marker in lower for marker in _PENDING_LIVE_SEAT_MARKERS):
            continue
        missing = [role for role in ROLES if not _has_live_seat_artifact(text, role)]
        if missing:
            issues.append(CoordIssue(
                f"docs/{path.name}",
                "coordinator_handoff_theater",
                "FATAL",
                "coordinator All-Seat Handoff lacks live-seat artifacts for "
                f"{', '.join(missing)}; subagent reports do not satisfy live-seat "
                "handoffs, cursors, or operator/coordinator authority",
            ))
    return issues


def run(coord_root: Path | str, since: str = "2026-06-11",
        now: str | None = None, git_root: Path | str | None = None,
        docs_root: Path | str | None = None) -> list[CoordIssue]:
    coord_root = Path(coord_root)
    if now is None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    names = _event_names(coord_root)
    issues: list[CoordIssue] = []
    issues += _check_cursors(coord_root, now, names)
    issues += _check_events(coord_root, since, names)
    issues += _unread_report(coord_root, names)
    if git_root is not None:
        issues += _check_standalone_cursor_commits(git_root)
    issues += _check_coordinator_handoff_theater(docs_root)
    return issues


def main(argv=None) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(repo_root / "coordination"),
                    help="coordination/ directory (default: repo's)")
    ap.add_argument("--since", default="2026-06-11",
                    help="envelope checks apply to events on/after this date")
    ap.add_argument("--now", default=None, help=argparse.SUPPRESS)  # test aid
    ap.add_argument("--git-root", default=None,
                    help="repo root; when given, ADVISORY-flag standalone cursor-only "
                         "commits in recent history (lever #5). Omitted = skipped.")
    ap.add_argument("--docs-root", default=str(repo_root / "docs"),
                    help="docs/ directory for coordinator handoff protocol checks")
    args = ap.parse_args(argv)

    issues = run(args.root, since=args.since, now=args.now, git_root=args.git_root,
                 docs_root=args.docs_root)
    fatal = [i for i in issues if i.severity == "FATAL"]
    advisory = [i for i in issues if i.severity == "ADVISORY"]
    for i in issues:
        print(f"{i.severity:8s} {i.kind:18s} {i.path} — {i.message}")
    if not fatal and not advisory:
        print(f"OK — coordination clean ({len(issues)} INFO)")
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
