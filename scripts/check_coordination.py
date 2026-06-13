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

The envelope checks are gated on --since (default 2026-06-11, the v6.0
adoption date): pre-adoption events used a YAML-frontmatter format and are
exempt. Filename checks are NOT gated — all 270 legacy events were verified
conforming at adoption time.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from status import count_unread

# 4-seat protocol (two director-operator pairs). `all` is a broadcast TARGET
# only — NOT a role (no seen/all.txt); every real seat counts `-to-all-` events
# as addressed to it (see _check_cursors orphan test + status.count_unread).
# Keep in sync with coordination/bin/{send-event,consume-events} + status._EVENT_RE.
ROLES = ("director", "director2", "operator", "operator2")

# Union of the kinds documented in coordination/README.md and every kind
# observed in filename position across the 270 events extant at adoption.
KNOWN_KINDS = frozenset({
    # README enum (v2/v4/v5)
    "dispatch-claim", "findings", "decision", "query", "status",
    "fold-notice", "verify-request", "verification-report",
    "doc-sync-notice", "scout-request", "scout-report", "memory-candidate",
    # observed-in-practice additions
    "coordination", "proposal", "proposal-reply", "acknowledgement",
    "reply", "fyi", "discussion", "convergence",
})

# `coordinator` is a send-only pseudo-seat: a valid <from> only, never a <to>,
# no seen cursor (mirror of `all`, which is <to>-only). Deliberately NOT added
# to ROLES, so no seen/coordinator.txt is expected.
_EVENT_NAME_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-"
    r"(?P<frm>director|director2|operator|operator2|coordinator)"
    r"-to-(?P<to>director|director2|operator|operator2|all)-"
    r"(?P<kind>[a-z0-9-]+)\.md$"
)

_CURSOR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_WHEN_RE = re.compile(r"\*\*When:\*\*\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")


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


def run(coord_root: Path | str, since: str = "2026-06-11",
        now: str | None = None) -> list[CoordIssue]:
    coord_root = Path(coord_root)
    if now is None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    names = _event_names(coord_root)
    issues: list[CoordIssue] = []
    issues += _check_cursors(coord_root, now, names)
    issues += _check_events(coord_root, since, names)
    issues += _unread_report(coord_root, names)
    return issues


def main(argv=None) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(repo_root / "coordination"),
                    help="coordination/ directory (default: repo's)")
    ap.add_argument("--since", default="2026-06-11",
                    help="envelope checks apply to events on/after this date")
    ap.add_argument("--now", default=None, help=argparse.SUPPRESS)  # test aid
    args = ap.parse_args(argv)

    issues = run(args.root, since=args.since, now=args.now)
    fatal = [i for i in issues if i.severity == "FATAL"]
    advisory = [i for i in issues if i.severity == "ADVISORY"]
    for i in issues:
        print(f"{i.severity:8s} {i.kind:18s} {i.path} — {i.message}")
    if not fatal and not advisory:
        print(f"OK — coordination clean ({len(issues)} INFO)")
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
