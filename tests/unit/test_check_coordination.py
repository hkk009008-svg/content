"""TDD tests for scripts/check_coordination.py — coordination-state linter.

Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_coordination.py -q

Mirrors the check_doc_claims.py verifier pattern (CoordIssue dataclass,
run() aggregator, main() exit codes). Fixtures are real tmp_path trees —
no mocking. The linter exists because the cursor developed three diverging
representations (seen/*.txt vs event footers vs commit messages) with no
checker; every check here pins a drift class observed in production on
2026-06-10.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_coordination import (  # noqa: E402
    CoordIssue,
    KNOWN_KINDS,
    run,
    main,
)

# A deterministic "now" for every test — checks must not read the wall clock
# when the caller supplies one.
NOW = "2026-06-12T12:00:00Z"
SINCE = "2026-06-12"


# ---------------------------------------------------------------------------
# Fixture helper
# ---------------------------------------------------------------------------

GOOD_EVENT_NAME = "2026-06-12T10-00-00Z-director-to-operator-coordination.md"
GOOD_EVENT_BODY = (
    "# Director → Operator: subject line\n\n"
    "**When:** 2026-06-12T10:00:00Z · **From:** director (online)\n\n"
    "body prose\n"
)


def make_coord(tmp_path, events=None, cursors=None):
    """Build a coordination/ tree. events = {filename: body};
    cursors = {role: timestamp-content}."""
    root = tmp_path / "coordination"
    (root / "mailbox" / "sent").mkdir(parents=True)
    (root / "mailbox" / "seen").mkdir(parents=True)
    for name, body in (events or {}).items():
        (root / "mailbox" / "sent" / name).write_text(body)
    # 4-seat protocol: every role in check_coordination.ROLES needs a cursor or
    # the linter FATALs cursor_missing. Seed all four; per-test overrides apply.
    default_cursors = {"director": "2026-01-01T00:00:00Z",
                       "director2": "2026-01-01T00:00:00Z",
                       "operator": "2026-01-01T00:00:00Z",
                       "operator2": "2026-01-01T00:00:00Z"}
    default_cursors.update(cursors or {})
    for role, ts in default_cursors.items():
        (root / "mailbox" / "seen" / f"{role}.txt").write_text(ts + "\n")
    return root


def fatals(issues):
    return [i for i in issues if i.severity == "FATAL"]


def advisories(issues):
    return [i for i in issues if i.severity == "ADVISORY"]


# ---------------------------------------------------------------------------
# Clean fixture
# ---------------------------------------------------------------------------

def test_clean_fixture_yields_only_info(tmp_path):
    root = make_coord(
        tmp_path,
        events={GOOD_EVENT_NAME: GOOD_EVENT_BODY},
        cursors={"operator": "2026-06-12T10:00:00Z"},
    )
    issues = run(root, since=SINCE, now=NOW)
    assert fatals(issues) == []
    assert advisories(issues) == []
    # The unread report is informational and always present (one per role).
    assert any(i.severity == "INFO" and "unread" in i.message for i in issues)


# ---------------------------------------------------------------------------
# Cursor checks
# ---------------------------------------------------------------------------

def test_unparseable_cursor_is_fatal(tmp_path):
    root = make_coord(tmp_path, cursors={"director": "not-a-timestamp"})
    issues = run(root, since=SINCE, now=NOW)
    assert any(i.kind == "cursor_unparseable" for i in fatals(issues))


def test_future_dated_cursor_is_fatal(tmp_path):
    root = make_coord(tmp_path, cursors={"director": "2026-06-13T00:00:00Z"})
    issues = run(root, since=SINCE, now=NOW)
    assert any(i.kind == "cursor_future" for i in fatals(issues))


def test_cursor_matching_no_event_is_advisory(tmp_path):
    # Cursor strictly between two events addressed to the role, matching
    # neither -> a hand-typed watermark that never existed. ADVISORY.
    root = make_coord(
        tmp_path,
        events={
            GOOD_EVENT_NAME: GOOD_EVENT_BODY,
            "2026-06-12T11-00-00Z-director-to-operator-coordination.md":
                GOOD_EVENT_BODY.replace("10:00:00", "11:00:00"),
        },
        cursors={"operator": "2026-06-12T10:30:00Z"},
    )
    issues = run(root, since=SINCE, now=NOW)
    assert any(i.kind == "cursor_orphan" for i in advisories(issues))


def test_cursor_matching_archived_event_is_allowed(tmp_path):
    # An event can be moved sent/ -> archive/ after consumption; a cursor
    # pointing at it is legitimate, not an orphan (review M-1).
    root = make_coord(
        tmp_path,
        events={
            GOOD_EVENT_NAME: GOOD_EVENT_BODY,
            "2026-06-12T11-00-00Z-director-to-operator-coordination.md":
                GOOD_EVENT_BODY.replace("10:00:00", "11:00:00"),
        },
        cursors={"operator": "2026-06-12T10:30:00Z"},
    )
    arch = root / "mailbox" / "archive"
    arch.mkdir()
    (arch / "2026-06-12T10-30-00Z-director-to-operator-reply.md").write_text("x\n")
    issues = run(root, since=SINCE, now=NOW)
    assert not any(i.kind == "cursor_orphan" for i in issues)


def test_cursor_older_than_all_events_is_allowed(tmp_path):
    # A cursor pointing before every retained event is the archived-events
    # case, not an error.
    root = make_coord(
        tmp_path,
        events={GOOD_EVENT_NAME: GOOD_EVENT_BODY},
        cursors={"operator": "2026-01-01T00:00:00Z"},
    )
    issues = run(root, since=SINCE, now=NOW)
    assert not any(i.kind == "cursor_orphan" for i in issues)


# ---------------------------------------------------------------------------
# Filename convention
# ---------------------------------------------------------------------------

def test_bad_filename_is_fatal(tmp_path):
    root = make_coord(tmp_path, events={"random-notes.md": "x\n"})
    issues = run(root, since=SINCE, now=NOW)
    assert any(i.kind == "bad_filename" for i in fatals(issues))


def test_self_addressed_event_is_fatal(tmp_path):
    root = make_coord(
        tmp_path,
        events={"2026-06-12T10-00-00Z-director-to-director-coordination.md":
                GOOD_EVENT_BODY},
    )
    issues = run(root, since=SINCE, now=NOW)
    assert any(i.kind == "self_addressed" for i in fatals(issues))


# ---------------------------------------------------------------------------
# Envelope checks (since-gated: legacy frontmatter-era events are exempt)
# ---------------------------------------------------------------------------

def test_missing_when_line_is_advisory_after_since(tmp_path):
    root = make_coord(
        tmp_path,
        events={GOOD_EVENT_NAME: "# no envelope here\n\nbody\n"},
    )
    issues = run(root, since=SINCE, now=NOW)
    assert any(i.kind == "missing_when" for i in advisories(issues))


def test_pre_since_event_is_exempt_from_envelope_checks(tmp_path):
    old = "2026-06-01T10-00-00Z-director-to-operator-coordination.md"
    root = make_coord(tmp_path, events={old: "---\nkind: coordination\n---\n"})
    issues = run(root, since=SINCE, now=NOW)
    assert not any(i.kind == "missing_when" for i in issues)


def test_when_mismatching_filename_is_advisory(tmp_path):
    body = GOOD_EVENT_BODY.replace("10:00:00", "10:00:01")
    root = make_coord(tmp_path, events={GOOD_EVENT_NAME: body})
    issues = run(root, since=SINCE, now=NOW)
    assert any(i.kind == "when_mismatch" for i in advisories(issues))


def test_unknown_kind_is_advisory(tmp_path):
    name = "2026-06-12T10-00-00Z-director-to-operator-totallynovel.md"
    root = make_coord(
        tmp_path,
        events={name: GOOD_EVENT_BODY},
    )
    issues = run(root, since=SINCE, now=NOW)
    assert any(i.kind == "unknown_kind" for i in advisories(issues))
    assert "coordination" in KNOWN_KINDS and "verification-report" in KNOWN_KINDS
    # observed-in-practice kinds registered 2026-06-14 (cleared ci_smoke advisory)
    assert "measurement-report" in KNOWN_KINDS and "wrap" in KNOWN_KINDS


# ---------------------------------------------------------------------------
# Unread report + exit codes
# ---------------------------------------------------------------------------

def test_unread_report_counts_per_role(tmp_path):
    root = make_coord(
        tmp_path,
        events={
            GOOD_EVENT_NAME: GOOD_EVENT_BODY,
            "2026-06-12T11-00-00Z-director-to-operator-coordination.md":
                GOOD_EVENT_BODY.replace("10:00:00", "11:00:00"),
        },
        cursors={"operator": "2026-06-12T10:00:00Z"},
    )
    issues = run(root, since=SINCE, now=NOW)
    # Exact role prefix — "operator" is a substring of "operator2" (4-seat).
    op = [i for i in issues
          if i.kind == "unread" and i.message.startswith("operator:")]
    assert len(op) == 1 and "1" in op[0].message


def test_main_exit_codes(tmp_path, capsys):
    clean = make_coord(
        tmp_path / "clean",
        events={GOOD_EVENT_NAME: GOOD_EVENT_BODY},
        cursors={"operator": "2026-06-12T10:00:00Z"},
    )
    assert main(["--root", str(clean), "--since", SINCE, "--now", NOW]) == 0
    broken = make_coord(
        tmp_path / "broken", cursors={"director": "garbage"},
    )
    assert main(["--root", str(broken), "--since", SINCE, "--now", NOW]) == 1
    out = capsys.readouterr().out
    assert "cursor_unparseable" in out


# ── standalone cursor-only commit lint (lever #5, audit wf_6be2ee18-f4b) ──

import subprocess as _sp  # noqa: E402


def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _sp.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return repo


def _commit(repo, msg):
    _sp.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True, text=True)
    _sp.run(["git", "-C", str(repo), "commit", "-q", "-m", msg], check=True, capture_output=True, text=True)


def test_standalone_cursor_only_commit_is_advisory(tmp_path):
    repo = _init_repo(tmp_path)
    seen = repo / "coordination" / "mailbox" / "seen"
    seen.mkdir(parents=True)
    (seen / "operator.txt").write_text("2026-06-13T10:00:00Z\n")
    _commit(repo, "coord: cursor advance")
    root = make_coord(tmp_path)
    issues = run(root, since=SINCE, now=NOW, git_root=repo)
    assert any(i.kind == "standalone_cursor_commit" and i.severity == "ADVISORY" for i in issues)


def test_cursor_commit_with_sent_event_is_not_flagged(tmp_path):
    repo = _init_repo(tmp_path)
    seen = repo / "coordination" / "mailbox" / "seen"
    seen.mkdir(parents=True)
    sent = repo / "coordination" / "mailbox" / "sent"
    sent.mkdir(parents=True)
    (seen / "operator.txt").write_text("2026-06-13T10:00:00Z\n")
    (sent / "2026-06-13T10-00-00Z-operator-to-all-fyi.md").write_text("body\n")
    _commit(repo, "coord: event + cursor (folded)")
    root = make_coord(tmp_path)
    issues = run(root, since=SINCE, now=NOW, git_root=repo)
    assert not any(i.kind == "standalone_cursor_commit" for i in issues)
