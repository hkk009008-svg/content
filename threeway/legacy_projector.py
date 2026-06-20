"""Legacy coordination/ mailbox -> threeway carrier-event projection (spec §5a).

READ-ONLY. project() reads coordination/mailbox/sent/<ts>-<from>-to-<to>-<kind>.md
files and returns threeway.envelope.Event objects carrying each legacy event as the
existing non-load-bearing `event_sent` kind. NO refs/threeway/events writes, NO
RefEventStore, NO append — this module has no write path by construction (the §8
clause-6 no-dual-write pin depends on that). Events are UNSIGNED: signing is a
cutover concern (§5c); event_sent is not load-bearing so the gate never reads a
carrier signature.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from threeway.envelope import Event

# Filename grammar — kept in lockstep with check_coordination.py:55 _EVENT_NAME_RE
# (re-grep both if the seat roster changes; Slice 2.5 Phase A adds coordinator2 there
# and MUST add it here too). ts is the dash-form timestamp; full filename is the
# secondary total-order key (spec §6).
_EVENT_NAME_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-"
    r"(?P<frm>director|director2|operator|operator2|coordinator|coordinator2)-"
    r"to-(?P<to>director|director2|operator|operator2|coordinator|coordinator2|all)-"
    r"(?P<kind>[a-z0-9-]+)\.md$"
)

# best-effort body parsers — two corpus formats exist (YAML frontmatter vs the
# **When:**·**From:** H1 header). These feed payload fields ONLY; routing comes from
# the FILENAME (never the body). Absent -> None, never an error.
_WHEN_RE = re.compile(r"\*\*When:\*\*\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")
_YAML_WHEN_RE = re.compile(r"^when:\s*(.+?)\s*$", re.M)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
_YAML_SUBJ_RE = re.compile(r"^subject:\s*(.+?)\s*$", re.M)
_CURSOR_RE = re.compile(r"^Cursor at send:\s*(.+?)\s*$", re.M)

BRIEF_ID = "legacy-import"


def _subject(body: str) -> str | None:
    m = _H1_RE.search(body)
    if m:
        return m.group(1)
    m = _YAML_SUBJ_RE.search(body)
    return m.group(1) if m else None


def _when(body: str) -> str | None:
    m = _WHEN_RE.search(body)
    if m:
        return m.group(1)
    m = _YAML_WHEN_RE.search(body)
    return m.group(1) if m else None


def _cursor(body: str) -> str | None:
    m = _CURSOR_RE.search(body)
    return m.group(1) if m else None


def project(sent_dir) -> list[Event]:
    """Read every sent/*.md whose name matches the grammar -> carrier Events, in the
    spec §6 total order (filename ts, then full filename). Filenames that do not match
    the grammar are skipped (the live corpus has zero such files; a stray non-event
    .md must not become a carrier)."""
    sent = Path(sent_dir)
    files = sorted(
        (p for p in sent.iterdir() if p.name.endswith(".md") and _EVENT_NAME_RE.match(p.name)),
        # total order: (ts group, full filename). ts is a prefix of the name, but key
        # on (ts, name) explicitly so the contract is legible and same-second groups
        # break on full filename deterministically.
        key=lambda p: (_EVENT_NAME_RE.match(p.name).group("ts"), p.name),
    )
    events: list[Event] = []
    for p in files:
        m = _EVENT_NAME_RE.match(p.name)
        body = p.read_text(encoding="utf-8", errors="replace")
        # NB: subject_sha = sha256(SOURCE FILENAME), the §5a injectivity keystone.
        # Filenames are unique even within a same-second group, so idempotency_key
        # (sender:kind:subject_sha:payload_digest) is injective over the corpus. Do NOT
        # base it on the body (terse identical bodies would collide).
        subject_sha = hashlib.sha256(p.name.encode()).hexdigest()
        events.append(Event(
            id=p.name,                       # filename is unique -> a stable event id
            seq=0,                            # seq is assigned at cutover append, not here
            bus_id="prod",
            schema_version="threeway/1",
            kind="event_sent",               # carrier (not the legacy kind)
            sender=m.group("frm"),
            recipient=m.group("to"),         # 'all' preserved as-is (one event, no fan-out)
            signer=f"migration-importer:legacy:{m.group('frm')}",
            payload={
                "legacy_kind": m.group("kind"),
                "subject": _subject(body),
                "when": _when(body),
                "cursor_at_send": _cursor(body),
                "body": body,
                "recipient": m.group("to"),
                "source_filename": p.name,
            },
            brief_id=BRIEF_ID,
            subject_sha=subject_sha,
            # UNSIGNED: signature stays None (signing is the §5c cutover concern).
        ))
    return events
