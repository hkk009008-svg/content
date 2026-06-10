"""TDD tests for coordination/bin/send-event and coordination/bin/consume-events.

Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_coordination_bin.py -q

The scripts make correct mailbox bookkeeping a single invocation instead of
three hand-synchronized edits (event file + seen/<role>.txt + commit prose) —
the manual version produced a live three-way cursor divergence on 2026-06-10.
Tests exercise the REAL scripts via subprocess inside throwaway git repos
(mirroring tests/unit/test_unread_count.py's bash-under-test approach).
GIT_INDEX_FILE is stripped from the child env: the per-seat index redirect
must never leak into a temp repo (documented pytest hazard).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEND_EVENT = _REPO_ROOT / "coordination" / "bin" / "send-event"
CONSUME_EVENTS = _REPO_ROOT / "coordination" / "bin" / "consume-events"

EVENT_NAME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-"
    r"(director|operator)-to-(director|operator)-[a-z0-9-]+\.md$"
)


def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


@pytest.fixture()
def repo(tmp_path):
    """Throwaway git repo with the coordination skeleton."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=_env())
    sent = tmp_path / "coordination" / "mailbox" / "sent"
    seen = tmp_path / "coordination" / "mailbox" / "seen"
    sent.mkdir(parents=True)
    seen.mkdir(parents=True)
    (seen / "director.txt").write_text("2026-06-01T00:00:00Z\n")
    (seen / "operator.txt").write_text("2026-06-01T00:00:00Z\n")
    return tmp_path


def _run(script, args, repo_dir, stdin=""):
    return subprocess.run(
        [str(script), *args],
        cwd=repo_dir, env=_env(), input=stdin,
        capture_output=True, text=True,
    )


def _staged(repo_dir):
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo_dir, env=_env(), capture_output=True, text=True, check=True,
    )
    return out.stdout.split()


# ---------------------------------------------------------------------------
# send-event
# ---------------------------------------------------------------------------

def test_send_event_writes_convention_file_and_stages(repo):
    r = _run(SEND_EVENT, ["operator", "director", "coordination", "test subject"],
             repo, stdin="the body prose\n")
    assert r.returncode == 0, r.stderr
    sent = repo / "coordination" / "mailbox" / "sent"
    files = [p.name for p in sent.iterdir()]
    assert len(files) == 1 and EVENT_NAME_RE.match(files[0])
    assert "-operator-to-director-coordination.md" in files[0]
    text = (sent / files[0]).read_text()
    # Envelope: H1 + When (colon form, matching the filename ts) + From + body
    # + a Cursor-at-send line sourced from the sender's seen file (cannot drift).
    # filename token is dash form; colon form swaps the time separators back
    ts_colon = files[0][:11] + files[0][11:20].replace("-", ":")
    assert text.startswith("# Operator → Director: test subject")
    assert f"**When:** {ts_colon}" in text
    assert "**From:** operator" in text
    assert "the body prose" in text
    assert "Cursor at send: 2026-06-01T00:00:00Z" in text
    assert _staged(repo) == [f"coordination/mailbox/sent/{files[0]}"]
    # stdout reports the created path so the seat can cite it in the commit.
    assert files[0] in r.stdout


def test_send_event_rejects_unknown_kind(repo):
    r = _run(SEND_EVENT, ["operator", "director", "Bogus_Kind", "x"], repo)
    assert r.returncode != 0
    assert not list((repo / "coordination" / "mailbox" / "sent").iterdir())


def test_send_event_rejects_self_addressed(repo):
    r = _run(SEND_EVENT, ["operator", "operator", "coordination", "x"], repo)
    assert r.returncode != 0
    assert not list((repo / "coordination" / "mailbox" / "sent").iterdir())


# ---------------------------------------------------------------------------
# consume-events
# ---------------------------------------------------------------------------

def _seed_events(repo):
    sent = repo / "coordination" / "mailbox" / "sent"
    for ts in ("2026-06-12T10-00-00Z", "2026-06-12T11-00-00Z"):
        (sent / f"{ts}-operator-to-director-coordination.md").write_text("x\n")
    # An event in the other direction must NOT count for director.
    (sent / "2026-06-12T12-00-00Z-director-to-operator-reply.md").write_text("x\n")


def test_consume_events_advances_to_newest_and_stages(repo):
    _seed_events(repo)
    r = _run(CONSUME_EVENTS, ["director"], repo)
    assert r.returncode == 0, r.stderr
    cursor = (repo / "coordination" / "mailbox" / "seen" / "director.txt").read_text().strip()
    assert cursor == "2026-06-12T11:00:00Z"   # newest addressed-to-director, colon form
    assert _staged(repo) == ["coordination/mailbox/seen/director.txt"]
    assert "2026-06-01T00:00:00Z -> 2026-06-12T11:00:00Z" in r.stdout


def test_consume_events_explicit_target(repo):
    _seed_events(repo)
    r = _run(CONSUME_EVENTS, ["director", "--to", "2026-06-12T10:00:00Z"], repo)
    assert r.returncode == 0, r.stderr
    cursor = (repo / "coordination" / "mailbox" / "seen" / "director.txt").read_text().strip()
    assert cursor == "2026-06-12T10:00:00Z"


def test_consume_events_refuses_regression(repo):
    _seed_events(repo)
    seen = repo / "coordination" / "mailbox" / "seen" / "director.txt"
    seen.write_text("2026-06-12T11:00:00Z\n")
    r = _run(CONSUME_EVENTS, ["director", "--to", "2026-06-12T10:00:00Z"], repo)
    assert r.returncode != 0
    assert seen.read_text().strip() == "2026-06-12T11:00:00Z"


def test_consume_events_rejects_nonexistent_target(repo):
    _seed_events(repo)
    r = _run(CONSUME_EVENTS, ["director", "--to", "2026-06-12T10:30:00Z"], repo)
    assert r.returncode != 0


def test_consume_events_rejects_malformed_target(repo):
    # A non-timestamp --to (e.g. a glob/regex fragment) must be rejected by
    # format BEFORE any matching logic runs (review M-2) — never written to
    # the cursor file, never grep'd against the mailbox.
    _seed_events(repo)
    seen = repo / "coordination" / "mailbox" / "seen" / "director.txt"
    before = seen.read_text()
    r = _run(CONSUME_EVENTS, ["director", "--to", ".*"], repo)
    assert r.returncode != 0
    assert "malformed" in r.stderr
    assert seen.read_text() == before


def test_consume_events_noop_when_nothing_unread(repo):
    # No events addressed to operator beyond the cursor -> exit 0, no change,
    # nothing staged (idempotent; safe to call in any wrap sequence).
    _seed_events(repo)
    seen = repo / "coordination" / "mailbox" / "seen" / "operator.txt"
    seen.write_text("2026-06-12T12:00:00Z\n")
    r = _run(CONSUME_EVENTS, ["operator"], repo)
    assert r.returncode == 0, r.stderr
    assert seen.read_text().strip() == "2026-06-12T12:00:00Z"
    assert _staged(repo) == []
