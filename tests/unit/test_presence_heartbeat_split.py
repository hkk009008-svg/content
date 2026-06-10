"""Regression tests for _stamp_presence() in .claude/hooks/update-state.sh
(protocol v6.0 Tier 2 — presence heartbeat split, user-authorized 2026-06-11).

The pre-split hook sed-edited coordination/presence/<seat>.md in place on
every tool call, which (a) livelocked the seat's own Write-tool edits to the
file (hook rewrote it between the tool's read and write; documented workaround
was Bash heredocs) and (b) made the hook-stamped `updated:` field move while
the seat-owned `status:`/`current_task:` prose went stale — two recorded
misattribution incidents. Post-split: the hook writes ONLY a single-line
atomic heartbeat file `<seat>-heartbeat.ts`; the .md is wholly seat-owned.

Mirrors test_skip_worktree_clear.py: awk-slices the REAL function out of the
hook so the tests guard production, not a copy. Git is not required by the
function (HEAD resolution falls back to '?'), so fixtures are plain tmp dirs.
"""
import os
import subprocess
from pathlib import Path

HOOK_PATH = Path(__file__).parents[2] / ".claude" / "hooks" / "update-state.sh"


def _extract_stamp_presence() -> str:
    """Slice the real `_stamp_presence() { … }` body out of the hook with awk."""
    func = subprocess.run(
        ["awk",
         r'/^_stamp_presence\(\) \{/{p=1} p{print} p&&/^\}/{exit}',
         str(HOOK_PATH)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert func.strip().startswith("_stamp_presence()") and func.rstrip().endswith("}"), (
        f"failed to extract _stamp_presence() from {HOOK_PATH}:\n{func!r}"
    )
    return func


def _run(tmp_dir: Path, seat: str | None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # The outer dev session exports BOTH of these — control them explicitly
    # or the test stamps the real seat's identity.
    env.pop("CLAUDE_SEAT", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env.pop("GIT_INDEX_FILE", None)
    if seat is not None:
        env["CLAUDE_SEAT"] = seat
    return subprocess.run(
        ["bash", "-c", _extract_stamp_presence() + "\n_stamp_presence"],
        cwd=tmp_dir, env=env, capture_output=True, text=True,
    )


def test_extract_stamp_presence_sanity():
    func = _extract_stamp_presence()
    assert "_stamp_presence" in func
    assert "heartbeat.ts" in func, "function must write the heartbeat file"


def test_writes_single_line_heartbeat(tmp_path):
    r = _run(tmp_path, "testseat")
    assert r.returncode == 0, r.stderr
    hb = tmp_path / "coordination" / "presence" / "testseat-heartbeat.ts"
    assert hb.exists()
    lines = hb.read_text().splitlines()
    assert len(lines) == 1
    # "<ISO-UTC> <short-head-or-?>"
    ts, head = lines[0].split(" ")
    assert len(ts) == 20 and ts.endswith("Z") and "T" in ts
    assert head  # '?' outside a git repo


def test_does_not_touch_seat_intent_file(tmp_path):
    # THE livelock pin: a pre-existing seat-owned .md must be byte-identical
    # after the hook stamp — the hook has no business in that file anymore.
    pdir = tmp_path / "coordination" / "presence"
    pdir.mkdir(parents=True)
    intent = pdir / "testseat.md"
    original = "seat: testseat\nstatus: online\ncurrent_task: hands off\nupdated: 1999-01-01T00:00:00Z\n"
    intent.write_text(original)
    r = _run(tmp_path, "testseat")
    assert r.returncode == 0, r.stderr
    assert intent.read_text() == original


def test_overwrite_not_append(tmp_path):
    _run(tmp_path, "testseat")
    r = _run(tmp_path, "testseat")
    assert r.returncode == 0, r.stderr
    hb = tmp_path / "coordination" / "presence" / "testseat-heartbeat.ts"
    assert len(hb.read_text().splitlines()) == 1


def test_no_seat_resolved_no_write(tmp_path):
    r = _run(tmp_path, seat=None)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "coordination" / "presence").exists()


def test_hook_has_no_presence_md_writer_left():
    # Static guard against regression: nothing in the hook may sed/printf into
    # presence/<seat>.md anymore. The .ts heartbeat is the only hook target.
    text = HOOK_PATH.read_text()
    assert '${_SEAT}.md' not in text and '${seat}.md' not in text, (
        "hook must not reference the seat-owned presence .md file"
    )
