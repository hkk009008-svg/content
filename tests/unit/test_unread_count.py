"""C2 regression test for v5.7 M2 unread-count fix.

Adversarial synthetic fixture (per DRAFT §1 validated regression):
  cursor CONTENT: 2026-05-30T08:00:00Z  (cursor file mtime forced to 07:00)
  events:
    2026-05-30T07-00-00Z-operator-to-director-old.md  (before cursor — NOT counted)
    2026-05-30T09-00-00Z-operator-to-director-new.md  (after cursor — counted)
    2026-05-30T09-30-00Z-director-to-operator-reply.md (wrong direction for director)

Old `find -newer <cursor-mtime>` logic: cursor mtime = 07:00 → all 3 files are
newer → director=3 (WRONG: counts own-sends + before-cursor event).

New to:-filter + content-ts logic:
  director: only files matching *-to-director-*.md whose 20-char filename token
            > "2026-05-30T08-00-00Z" → exactly 1 (the 09:00 event).
  operator: only files matching *-to-operator-*.md whose 20-char filename token
            > "2026-05-30T08-00-00Z" → exactly 1 (the 09:30 event).
"""
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# The pure-Python reimplementation of _unread_for() from the hook.
# This lets us unit-test the logic without shelling out to bash per assertion,
# while a second test validates the bash function itself via subprocess.
# ---------------------------------------------------------------------------

def _unread_for(mailbox_sent_dir: Path, seen_dir: Path, role: str) -> int:
    """Python mirror of the bash _unread_for() in update-state.sh (v5.7 M2)."""
    cf = seen_dir / f"{role}.txt"
    if not cf.exists():
        return 0
    cur = cf.read_text().strip()               # e.g. 2026-05-30T08:00:00Z
    curkey = cur.replace(":", "-")             # e.g. 2026-05-30T08-00-00Z
    count = 0
    for f in mailbox_sent_dir.glob(f"*-to-{role}-*.md"):
        ts = f.name[:20]                       # fixed-width ISO token
        # LC_ALL=C byte-order compare == chronological for fixed-width ISO
        if ts > curkey:
            count += 1
    return count


def build_fixture(tmp: Path, cursor_content: str, cursor_mtime_ts: float):
    """
    Create the adversarial fixture inside tmp/.
    Returns (sent_dir, seen_dir).
    """
    sent = tmp / "sent"
    seen = tmp / "seen"
    sent.mkdir(parents=True)
    seen.mkdir(parents=True)

    # Cursor files — content is the ISO timestamp the agent last read to
    for role in ("director", "operator"):
        cf = seen / f"{role}.txt"
        cf.write_text(cursor_content + "\n")
        # Force cursor file mtime to 07:00 (simulates the old bug: mtime < all events)
        os.utime(cf, (cursor_mtime_ts, cursor_mtime_ts))

    # Event files — we only need their names; content is irrelevant for the count
    events = [
        "2026-05-30T07-00-00Z-operator-to-director-old.md",    # BEFORE cursor content
        "2026-05-30T09-00-00Z-operator-to-director-new.md",    # AFTER cursor content
        "2026-05-30T09-30-00Z-director-to-operator-reply.md",  # AFTER cursor, wrong dir
    ]
    for name in events:
        ef = sent / name
        ef.write_text(f"# {name}\n")
        # Give all event files an mtime of 09:45 (well after cursor mtime 07:00)
        # This is what makes the OLD find-newer-mtime logic return 3 (all newer).
        late_ts = cursor_mtime_ts + 10_800  # +3h from 07:00 = 10:00
        os.utime(ef, (late_ts, late_ts))

    return sent, seen


# ---------------------------------------------------------------------------
# Test 1: Python logic (fast, no subprocess)
# ---------------------------------------------------------------------------

def test_unread_python_director_is_1():
    """New logic returns 1 for director (only the 09:00 op→dir event counts)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # cursor content = 08:00; cursor mtime forced to 07:00
        import calendar
        cursor_mtime = calendar.timegm(
            time.strptime("2026-05-30T07:00:00", "%Y-%m-%dT%H:%M:%S")
        )
        sent, seen = build_fixture(tmp, "2026-05-30T08:00:00Z", float(cursor_mtime))
        result = _unread_for(sent, seen, "director")
        assert result == 1, (
            f"Expected director unread=1, got {result}. "
            "New logic should count only events addressed to director "
            "whose filename-timestamp > cursor content (08:00). "
            "The 07:00 op→dir event is before the cursor; "
            "the 09:30 dir→op event is not addressed to director."
        )


def test_unread_python_operator_is_1():
    """New logic returns 1 for operator (only the 09:30 dir→op event counts)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        import calendar
        cursor_mtime = calendar.timegm(
            time.strptime("2026-05-30T07:00:00", "%Y-%m-%dT%H:%M:%S")
        )
        sent, seen = build_fixture(tmp, "2026-05-30T08:00:00Z", float(cursor_mtime))
        result = _unread_for(sent, seen, "operator")
        assert result == 1, (
            f"Expected operator unread=1, got {result}. "
            "Only the 09:30 dir→op event is addressed to operator and after cursor."
        )


def test_unread_python_no_cursor_is_0():
    """_unread_for returns 0 when the cursor file does not exist."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sent = tmp / "sent"
        seen = tmp / "seen"
        sent.mkdir(); seen.mkdir()
        (sent / "2026-05-30T09-00-00Z-operator-to-director-x.md").write_text("x")
        result = _unread_for(sent, seen, "director")
        assert result == 0, f"Expected 0 when no cursor file; got {result}"


def test_unread_python_empty_sent_is_0():
    """_unread_for returns 0 when there are no events in sent/."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sent = tmp / "sent"
        seen = tmp / "seen"
        sent.mkdir(); seen.mkdir()
        (seen / "director.txt").write_text("2026-05-30T08:00:00Z\n")
        result = _unread_for(sent, seen, "director")
        assert result == 0, f"Expected 0 for empty sent/; got {result}"


# ---------------------------------------------------------------------------
# Test 2: Bash logic — exercise the REAL _unread_for() FROM the hook.
#
# Per Lane V I1/M-2 (both seats flagged it): the test must guard the PRODUCTION
# function, not a re-pasted copy. We slice _unread_for() verbatim out of
# .claude/hooks/update-state.sh with awk and run THAT under bash, against a
# fixture laid out at the hook's real RELATIVE paths
# (coordination/mailbox/{sent,seen}) under a temp cwd. So a regression in the
# hook's own _unread_for is caught here — not just in a copy.
# ---------------------------------------------------------------------------

HOOK_PATH = Path(__file__).parents[2] / ".claude" / "hooks" / "update-state.sh"


def _extract_unread_for() -> str:
    """Slice the real `_unread_for() { … }` body out of the hook (not a copy)."""
    func = subprocess.run(
        ["awk", r'/^_unread_for\(\) \{/{p=1} p{print} p&&/^\}/{exit}', str(HOOK_PATH)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert func.strip().startswith("_unread_for()") and func.rstrip().endswith("}"), (
        f"failed to extract _unread_for() from {HOOK_PATH}:\n{func!r}"
    )
    return func


def _build_real_fixture(tmp: Path, cursor_content: str, cursor_mtime_ts: float,
                        with_events: bool = True) -> Path:
    """Lay out the adversarial fixture at the hook's REAL relative paths
    (coordination/mailbox/{sent,seen}) under tmp; return tmp (the cwd to run in)."""
    mb = tmp / "coordination" / "mailbox"
    sent = mb / "sent"; seen = mb / "seen"
    sent.mkdir(parents=True); seen.mkdir(parents=True)
    for role in ("director", "operator"):
        cf = seen / f"{role}.txt"
        cf.write_text(cursor_content + "\n")
        os.utime(cf, (cursor_mtime_ts, cursor_mtime_ts))  # force mtime to expose the old bug
    if with_events:
        for name in (
            "2026-05-30T07-00-00Z-operator-to-director-old.md",    # before cursor content
            "2026-05-30T09-00-00Z-operator-to-director-new.md",    # after cursor content
            "2026-05-30T09-30-00Z-director-to-operator-reply.md",  # after, wrong direction
        ):
            (sent / name).write_text(f"# {name}\n")
    return tmp


def _run_real_unread_for(workdir: Path, role: str) -> int:
    """Run the REAL extracted _unread_for() under bash with cwd=workdir (which
    holds coordination/mailbox/{sent,seen}). Guards the production function."""
    script = (
        "set -euo pipefail\n"
        "export LC_ALL=C\n"
        f'cd "{workdir}"\n'
        f"{_extract_unread_for()}\n"
        f'_unread_for "{role}"\n'
    )
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True, check=True
    )
    return int(result.stdout.strip())


def _cursor_mtime_0700() -> float:
    import calendar
    return float(calendar.timegm(time.strptime("2026-05-30T07:00:00", "%Y-%m-%dT%H:%M:%S")))


def test_unread_real_hook_director_is_1():
    """The REAL hook _unread_for returns 1 for director on the adversarial fixture."""
    with tempfile.TemporaryDirectory() as td:
        wd = _build_real_fixture(Path(td), "2026-05-30T08:00:00Z", _cursor_mtime_0700())
        result = _run_real_unread_for(wd, "director")
        assert result == 1, (
            f"REAL hook _unread_for: expected director=1, got {result}. "
            "Must filter to: director AND compare filename-ts to cursor CONTENT (not mtime)."
        )


def test_unread_real_hook_operator_is_1():
    """The REAL hook _unread_for returns 1 for operator on the adversarial fixture."""
    with tempfile.TemporaryDirectory() as td:
        wd = _build_real_fixture(Path(td), "2026-05-30T08:00:00Z", _cursor_mtime_0700())
        result = _run_real_unread_for(wd, "operator")
        assert result == 1, f"REAL hook _unread_for: expected operator=1, got {result}."


def test_unread_real_hook_empty_glob_is_0():
    """The REAL hook _unread_for returns 0 on empty sent/ (literal glob, no match)."""
    with tempfile.TemporaryDirectory() as td:
        wd = _build_real_fixture(Path(td), "2026-05-30T08:00:00Z", _cursor_mtime_0700(),
                                 with_events=False)
        result = _run_real_unread_for(wd, "director")
        assert result == 0, f"Expected 0 for empty sent/; got {result}"
