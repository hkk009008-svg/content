"""4-seat coordination protocol regression tests (operator 2026-06-13).

The two-seat vocabulary {director, operator} is extended to four
{director, director2, operator, operator2} plus an `all` broadcast TARGET
(a `to` only — never a sender, never a cursor/seen file). These tests pin the
four synced vocabulary spots so they cannot drift apart again:
  - scripts/check_coordination.py  (_EVENT_NAME_RE + ROLES + orphan-`all`)
  - scripts/status.py              (count_unread: `all` counts for every seat)
  - coordination/bin/send-event    (FROM/TO enum incl. `all` target)
  - coordination/bin/consume-events(ROLE enum + `-to-(role|all)-` consume)

`coordinator` is a later addition: a send-only pseudo-seat (a valid `from`
only, never a `to`, no cursor — the mirror of `all`). It lets the read-only
oversight seat notify the four real seats without becoming a consumer.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_coordination  # noqa: E402
from status import count_unread  # noqa: E402

SEND_EVENT = _REPO_ROOT / "coordination" / "bin" / "send-event"
CONSUME_EVENTS = _REPO_ROOT / "coordination" / "bin" / "consume-events"

FOUR_CURSORS = {
    "director": "2026-06-01T00:00:00Z",
    "director2": "2026-06-01T00:00:00Z",
    "operator": "2026-06-01T00:00:00Z",
    "operator2": "2026-06-01T00:00:00Z",
}

FIXTURE_KINDS = ("coordination", "decision", "fyi")


def _make_coord(tmp_path, events=None, cursors=None):
    root = tmp_path / "coordination"
    (root / "mailbox" / "sent").mkdir(parents=True)
    (root / "mailbox" / "seen").mkdir(parents=True)
    for name, body in (events or {}).items():
        (root / "mailbox" / "sent" / name).write_text(body)
    cur = dict(FOUR_CURSORS)
    cur.update(cursors or {})
    for role, ts in cur.items():
        (root / "mailbox" / "seen" / f"{role}.txt").write_text(ts + "\n")
    return root


def _fatals(issues):
    return [i for i in issues if i.severity == "FATAL"]


# --- check_coordination: Pair-B + broadcast lint clean -----------------------

def test_pair_b_and_broadcast_events_lint_clean(tmp_path):
    events = {
        "2026-06-13T01-00-00Z-director2-to-operator2-decision.md":
            "**When:** 2026-06-13T01:00:00Z\n",
        "2026-06-13T02-00-00Z-director-to-all-fyi.md":
            "**When:** 2026-06-13T02:00:00Z\n",
        "2026-06-13T03-00-00Z-operator2-to-director-verification-report.md":
            "**When:** 2026-06-13T03:00:00Z\n",
    }
    root = _make_coord(tmp_path, events=events)
    issues = check_coordination.run(root, since="2026-06-11",
                                    now="2026-06-14T00:00:00Z")
    assert _fatals(issues) == [], [str(i) for i in _fatals(issues)]


def test_garbage_filename_still_fatal_under_4seat(tmp_path):
    root = _make_coord(tmp_path, events={"not-an-event.md": "x\n"})
    issues = check_coordination.run(root, now="2026-06-14T00:00:00Z")
    assert any(i.kind == "bad_filename" for i in _fatals(issues))


def test_all_broadcast_satisfies_seat_cursor_no_orphan(tmp_path):
    # operator2's cursor sits exactly on an `all` event -> addressed, not orphan.
    events = {"2026-06-13T05-00-00Z-director-to-all-status.md":
              "**When:** 2026-06-13T05:00:00Z\n"}
    root = _make_coord(tmp_path, events=events,
                       cursors={"operator2": "2026-06-13T05:00:00Z"})
    issues = check_coordination.run(root, now="2026-06-14T00:00:00Z")
    assert not any(i.kind == "cursor_orphan" for i in issues)


# --- status.count_unread: `all` counts for every seat ------------------------

def test_count_unread_counts_all_and_pair_b():
    cursor = "2026-06-13T00:00:00Z"
    files = [
        "2026-06-13T01-00-00Z-director2-to-operator2-decision.md",  # -> operator2
        "2026-06-13T02-00-00Z-director-to-all-fyi.md",              # -> all
        "2026-06-13T03-00-00Z-operator-to-director-reply.md",       # -> director
    ]
    assert count_unread(cursor, files, "operator2") == 2   # own + broadcast
    assert count_unread(cursor, files, "director") == 2    # own + broadcast
    assert count_unread(cursor, files, "director2") == 1   # broadcast only
    assert count_unread(cursor, files, "operator") == 1    # broadcast only


# --- bin round-trip: send director2->operator2 + broadcast, consume operator2 -

def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


@pytest.fixture()
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=_env())
    sent = tmp_path / "coordination" / "mailbox" / "sent"
    seen = tmp_path / "coordination" / "mailbox" / "seen"
    sent.mkdir(parents=True)
    seen.mkdir(parents=True)
    (tmp_path / "coordination" / "mailbox" / "kinds.txt").write_text(
        "\n".join(FIXTURE_KINDS) + "\n",
        encoding="utf-8",
    )
    for role, ts in FOUR_CURSORS.items():
        (seen / f"{role}.txt").write_text(ts + "\n")
    return tmp_path


def _run(script, args, repo_dir, stdin=""):
    return subprocess.run([str(script), *args], cwd=repo_dir, env=_env(),
                          input=stdin, capture_output=True, text=True)


def test_send_and_consume_pair_b_and_broadcast(repo):
    # Pair B point-to-point + a broadcast (distinct filenames -> no same-second
    # collision even if both stamp the same UTC second).
    r1 = _run(SEND_EVENT, ["director2", "operator2", "decision", "lane B call"],
              repo, stdin="body\n")
    assert r1.returncode == 0, r1.stderr
    r2 = _run(SEND_EVENT, ["director", "all", "fyi", "everyone heads up"],
              repo, stdin="body\n")
    assert r2.returncode == 0, r2.stderr

    names = sorted(p.name for p in (repo / "coordination/mailbox/sent").iterdir())
    assert any("-director2-to-operator2-decision.md" in n for n in names)
    assert any("-director-to-all-fyi.md" in n for n in names)

    # operator2 consumes events addressed to itself OR to `all` -> cursor advances.
    rc = _run(CONSUME_EVENTS, ["operator2"], repo)
    assert rc.returncode == 0, rc.stderr
    cur = (repo / "coordination/mailbox/seen/operator2.txt").read_text().strip()
    assert cur > "2026-06-01T00:00:00Z"   # advanced past the seed


def test_send_event_rejects_all_as_sender(repo):
    # `all` is a TARGET only — never a valid FROM.
    r = _run(SEND_EVENT, ["all", "director", "fyi", "x"], repo)
    assert r.returncode != 0
    assert not list((repo / "coordination/mailbox/sent").iterdir())


# --- coordinator: send-only pseudo-seat (valid <from> only, never <to>) -------

def test_coordinator_as_sender_lints_clean(tmp_path):
    # coordinator is a valid <from> (read-only oversight seat); to a real seat
    # and to `all` both lint clean.
    events = {
        "2026-06-13T06-00-00Z-coordinator-to-director-coordination.md":
            "**When:** 2026-06-13T06:00:00Z\n",
        "2026-06-13T07-00-00Z-coordinator-to-all-fyi.md":
            "**When:** 2026-06-13T07:00:00Z\n",
    }
    root = _make_coord(tmp_path, events=events)
    issues = check_coordination.run(root, since="2026-06-11",
                                    now="2026-06-14T00:00:00Z")
    assert _fatals(issues) == [], [str(i) for i in _fatals(issues)]


def test_coordinator_as_target_is_valid_filename(tmp_path):
    # Slice 2.5 (§4b): coordinator is now a first-class <to>; -to-coordinator-
    # parses cleanly — no bad_filename FATAL. (Old send-only doctrine inverted.)
    root = _make_coord(
        tmp_path,
        events={"2026-06-13T08-00-00Z-director-to-coordinator-fyi.md":
                "**When:** 2026-06-13T08:00:00Z\n"})
    issues = check_coordination.run(root, now="2026-06-14T00:00:00Z")
    assert not any(i.kind == "bad_filename" for i in _fatals(issues))


def test_coordinator_not_a_role_no_cursor_required(tmp_path):
    # coordinator is NOT in ROLES, so no seen/coordinator.txt is ever expected.
    assert "coordinator" not in check_coordination.ROLES
    root = _make_coord(tmp_path)  # only the 4 real cursors exist
    issues = check_coordination.run(root, now="2026-06-14T00:00:00Z")
    assert not any(i.kind == "cursor_missing" for i in _fatals(issues))


def test_send_event_accepts_coordinator_from(repo):
    r = _run(SEND_EVENT,
             ["coordinator", "director", "coordination", "oversight note"],
             repo, stdin="body\n")
    assert r.returncode == 0, r.stderr
    names = sorted(p.name for p in (repo / "coordination/mailbox/sent").iterdir())
    assert any("-coordinator-to-director-coordination.md" in n for n in names)


def test_send_event_accepts_coordinator_as_target(repo):
    # Slice 2.5: coordinator is now a first-class receiving seat — a valid TO.
    # (Inverts the OLD send-only doctrine: this send formerly exited 2.)
    r = _run(SEND_EVENT, ["director", "coordinator", "fyi", "x"], repo)
    assert r.returncode == 0, r.stderr
    names = sorted(p.name for p in (repo / "coordination/mailbox/sent").iterdir())
    assert any("-director-to-coordinator-fyi.md" in n for n in names)
