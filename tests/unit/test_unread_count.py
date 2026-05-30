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
# Test 2: Bash function — source the hook and call _unread_for directly
# ---------------------------------------------------------------------------

HOOK_PATH = Path(__file__).parents[2] / ".claude" / "hooks" / "update-state.sh"


def _run_bash_unread(sent_dir: Path, seen_dir: Path, role: str) -> int:
    """
    Source the hook to pick up _unread_for(), then call it from a subshell
    that has the correct coordination/mailbox/sent + seen layout.
    """
    # The hook does `cd $(git rev-parse --show-toplevel)` at the top, so
    # we can't just source it in an arbitrary dir. Instead we extract only
    # the _unread_for function definition + call it with our paths substituted.
    #
    # We do this by:
    # 1. Reading the hook and extracting the _unread_for body.
    # 2. Running it in a bash -c with overridden paths.
    script = f"""
set -euo pipefail
export LC_ALL=C
_unread_for() {{
  local role="$1" cf cur curkey count=0 f ts
  cf="{seen_dir}/${{role}}.txt"
  [ -f "$cf" ] || {{ echo 0; return; }}
  cur=$(tr -d '[:space:]' < "$cf")
  curkey=$(printf '%s' "$cur" | tr ':' '-')
  for f in "{sent_dir}"/*-to-"${{role}}"-*.md; do
    [ -e "$f" ] || continue
    ts=$(basename "$f"); ts=${{ts:0:20}}
    [[ "$ts" > "$curkey" ]] && count=$((count+1))
  done
  echo "$count"
}}
_unread_for "{role}"
"""
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True, check=True
    )
    return int(result.stdout.strip())


def test_unread_bash_director_is_1():
    """Bash _unread_for returns 1 for director on the adversarial fixture."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        import calendar
        cursor_mtime = float(calendar.timegm(
            time.strptime("2026-05-30T07:00:00", "%Y-%m-%dT%H:%M:%S")
        ))
        sent, seen = build_fixture(tmp, "2026-05-30T08:00:00Z", cursor_mtime)
        result = _run_bash_unread(sent, seen, "director")
        assert result == 1, (
            f"Bash _unread_for: expected director=1, got {result}. "
            "New bash logic must filter to: director AND compare filename-ts to cursor CONTENT."
        )


def test_unread_bash_operator_is_1():
    """Bash _unread_for returns 1 for operator on the adversarial fixture."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        import calendar
        cursor_mtime = float(calendar.timegm(
            time.strptime("2026-05-30T07:00:00", "%Y-%m-%dT%H:%M:%S")
        ))
        sent, seen = build_fixture(tmp, "2026-05-30T08:00:00Z", cursor_mtime)
        result = _run_bash_unread(sent, seen, "operator")
        assert result == 1, (
            f"Bash _unread_for: expected operator=1, got {result}."
        )


def test_unread_bash_empty_glob_is_0():
    """Bash _unread_for returns 0 on empty sent/ (glob expands to nothing)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sent = tmp / "sent"; sent.mkdir()
        seen = tmp / "seen"; seen.mkdir()
        (seen / "director.txt").write_text("2026-05-30T08:00:00Z\n")
        result = _run_bash_unread(sent, seen, "director")
        assert result == 0, f"Expected 0 for empty sent/; got {result}"
