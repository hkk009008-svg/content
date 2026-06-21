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

# A leading dash-form timestamp token — the cheap "this LOOKS like a carrier event"
# discriminator. A sent/ .md with this prefix that nonetheless fails the full _EVENT_NAME_RE
# grammar is a SUSPECTED event (raise — never silently drop during the irreversible cutover);
# a file without it is clearly not an event (skip). Shared with cursor_backfill so the append
# order and the cursor numbering classify every filename identically (ADR-050).
_TS_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-")


class MalformedEventFilename(ValueError):
    """A sent/ filename looks like a carrier event (leading dash-ts token + .md) but does
    not match the full <ts>-<from>-to-<to>-<kind> grammar. The irreversible cutover must NOT
    silently drop it (legacy_projector) NOR silently count it in the cursor numbering
    (cursor_backfill); BOTH layers raise this, so the append-seq numbering and the cursor-seq
    numbering stay provably congruent (ADR-050)."""


def is_event_filename(name: str) -> bool:
    """True iff `name` is a fully-grammatical carrier-event filename — THE single source of
    truth for 'which sent/ files become events', shared by project() (append order) and
    cursor_backfill (cursor numbering)."""
    return bool(_EVENT_NAME_RE.match(name))


def ts_of(name: str) -> str:
    """The spec §6 primary sort key: the filename's leading ts group. The caller guarantees
    `name` is an event filename (is_event_filename)."""
    return _EVENT_NAME_RE.match(name).group("ts")


def ordered_event_names(names) -> list[str]:
    """Filter an iterable of sent/ filenames to the carrier events, in spec §6 total order
    ((ts, full filename) — total even within a same-second group). THE shared classifier:
    a fully-grammatical name is kept; a ts-prefixed .md that fails the grammar RAISES
    MalformedEventFilename (a suspected-but-unparseable event must abort the cutover, never
    be silently dropped/counted); any other file (no leading dash-ts, or not .md) is skipped."""
    events: list[str] = []
    for n in names:
        if is_event_filename(n):
            events.append(n)
        elif n.endswith(".md") and _TS_PREFIX.match(n):
            raise MalformedEventFilename(
                f"sent/ filename looks like a carrier event but fails the grammar: {n!r}")
        # else: clearly not an event -> skip
    return sorted(events, key=lambda n: (ts_of(n), n))


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
    """Read every sent/*.md that is a carrier event -> carrier Events, in the spec §6 total
    order (filename ts, then full filename). Membership + order come from the SHARED
    classifier (ordered_event_names), so this append order is provably congruent with the
    cursor backfill's seq numbering (ADR-050). A clean non-event .md is skipped (a stray
    non-event must not become a carrier); a ts-prefixed .md that fails the carrier grammar
    RAISES MalformedEventFilename (a suspected-but-unparseable event must not be silently
    dropped during the irreversible cutover)."""
    sent = Path(sent_dir)
    names = ordered_event_names(p.name for p in sent.iterdir())
    events: list[Event] = []
    for name in names:
        p = sent / name
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
